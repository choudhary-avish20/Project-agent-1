"""
orchestrator.py — the LLM brain of the demo joins the LiveKit room as an
agent participant, handles voice via AgentSession (LiveKit Inference for
STT/LLM/TTS), and drives the clone's agent-runtime.js over the room's data
channel by exposing click/type/navigate/get_page_elements as LLM tools.
"""

import asyncio
import json
import uuid
from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, JobContext, RunContext, function_tool

load_dotenv()

DATA_TOPIC = "agent-channel"
COMMAND_TIMEOUT_S = 6.0

# Keyed by room name so a brief reconnect (stitcher.py's hard page
# navigation disconnects the WebRTC session) doesn't lose conversation
# context. This only survives as long as the room itself stays alive across
# the gap -- LiveKit's empty-room grace period comfortably covers a normal
# page load. If reloads ever take longer than that, this in-memory dict
# won't survive it and would need to move to real storage (a small file or
# Redis) instead.
ROOM_STATE: dict[str, dict] = {}
PENDING_COMMANDS: dict[str, "asyncio.Future"] = {}


class DemoGuideAgent(Agent):
    def __init__(self, room: rtc.Room, room_state: dict):
        super().__init__(
            instructions=(
                "You are a friendly, upbeat product guide giving a live spoken demo "
                "of this website to a visitor. Before clicking or typing anything, "
                "call get_page_elements to see what's actually available on the "
                "current page -- never guess a data-agent-id. Narrate what you're "
                "about to do in a short sentence *before* calling a tool, so the "
                "visitor isn't sitting in silence while the action runs."
            )
        )
        self._room = room
        self._state = room_state

    @function_tool
    async def get_page_elements(self, context: RunContext) -> dict:
        return await self._send_command("get_state", {})

    @function_tool
    async def click(self, context: RunContext, agent_id: str) -> dict:
        return await self._send_command("click", {"agent_id": agent_id})

    @function_tool
    async def type_text(self, context: RunContext, agent_id: str, text: str) -> dict:
        return await self._send_command("type", {"agent_id": agent_id, "text": text})

    @function_tool
    async def navigate(self, context: RunContext, page: str) -> dict:
        return await self._send_command("navigate", {"page": page})

    async def _send_command(self, action: str, params: dict) -> dict:
        command_id = str(uuid.uuid4())
        message = json.dumps({"type": "command", "id": command_id, "action": action, **params})

        loop = asyncio.get_event_loop()
        result_future: asyncio.Future = loop.create_future()
        PENDING_COMMANDS[command_id] = result_future

        await self._room.local_participant.publish_data(
            message.encode("utf-8"), reliable=True, topic=DATA_TOPIC
        )

        try:
            return await asyncio.wait_for(result_future, timeout=COMMAND_TIMEOUT_S)
        except asyncio.TimeoutError:
            return {"ok": False, "error": f"no response from page within {COMMAND_TIMEOUT_S}s"}
        finally:
            PENDING_COMMANDS.pop(command_id, None)


async def entrypoint(ctx: JobContext):
    await ctx.connect()
    room = ctx.room
    room_state = ROOM_STATE.setdefault(room.name, {"current_page": None, "elements": []})

    agent = DemoGuideAgent(room, room_state)
    session = AgentSession(
        stt="deepgram/nova-3",
        llm="openai/gpt-4.1-mini",
        tts="cartesia/sonic-3",
    )

    session_started = False

    def on_data_received(packet: rtc.DataPacket):
        if packet.topic != DATA_TOPIC:
            return
        try:
            msg = json.loads(packet.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return

        if msg.get("type") == "command_result":
            future = PENDING_COMMANDS.get(msg.get("id"))
            if future and not future.done():
                future.set_result(msg.get("result", {}))
        elif msg.get("type") == "page_state":
            room_state["current_page"] = msg.get("page")
            room_state["elements"] = msg.get("elements", [])
            # Only react to page changes once the session is fully running;
            # early page_state messages arrive before session.start() finishes.
            if not session_started:
                return
            # The page changed under us -- either we navigated, or the
            # visitor clicked around on their own. Either way, let the
            # agent notice and react instead of staying silent about it.
            async def _react_to_page_change(page_name: str):
                try:
                    await session.generate_reply(
                        instructions=(
                            f"You're now on page '{page_name}'. "
                            "Briefly acknowledge what's here in one natural sentence, "
                            "without reading out raw element ids."
                        )
                    )
                except RuntimeError:
                    pass  # session closed (participant disconnected)
            asyncio.create_task(_react_to_page_change(room_state["current_page"]))

    room.on("data_received", on_data_received)

    await session.start(room=room, agent=agent)
    session_started = True
    await session.generate_reply(
        instructions="Greet the visitor warmly and offer to walk them through the product."
    )


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))