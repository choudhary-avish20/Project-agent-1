"""
orchestrator.py — the LLM brain of the demo joins the LiveKit room as an
agent participant, handles voice via AgentSession (LiveKit Inference for
STT/LLM/TTS), and drives the clone's agent-runtime.js over the room's data
channel by exposing click/type/navigate/get_page_elements as LLM tools.
"""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, ChatContext, JobContext, RunContext, function_tool
from livekit.agents.voice.room_io import RoomOptions

load_dotenv()

DATA_TOPIC = "agent-channel"
COMMAND_TIMEOUT_S = 6.0
AGENT_ACTION_WINDOW_S = 2.5

STATE_DIR = Path("room_state")


def _state_file(room_name: str) -> Path:
    STATE_DIR.mkdir(exist_ok=True)
    return STATE_DIR / f"{room_name}.json"


def load_history(room_name: str) -> ChatContext | None:
    path = _state_file(room_name)
    if not path.exists():
        return None
    try:
        return ChatContext.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception as e:
        print(f"[orchestrator] warning: could not load saved history for {room_name}: {e}")
        return None


def save_history(room_name: str, chat_ctx: ChatContext) -> None:
    try:
        _state_file(room_name).write_text(json.dumps(chat_ctx.to_dict()), encoding="utf-8")
    except Exception as e:
        print(f"[orchestrator] warning: could not save history for {room_name}: {e}")

ROOM_STATE: dict[str, dict] = {}
PENDING_COMMANDS: dict[str, "asyncio.Future"] = {}
PENDING_NAVIGATIONS: dict[str, asyncio.Future] = {}


class DemoGuideAgent(Agent):
    def __init__(self, room: rtc.Room, room_state: dict, chat_ctx: ChatContext | None = None):
        extra = {"chat_ctx": chat_ctx} if chat_ctx is not None else {}
        super().__init__(
            instructions=(
                "You are a friendly, upbeat product guide giving a live spoken demo "
                "of this website to a visitor. Before clicking or typing anything, "
                "call get_page_elements to see what's actually available on the "
                "current page -- never guess a data-agent-id. Narrate what you're "
                "about to do in a short sentence *before* calling a tool, so the "
                "visitor isn't sitting in silence while the action runs."
            ),
            **extra,
        )
        self._room = room
        self._state = room_state

    @function_tool
    async def get_page_elements(self, context: RunContext) -> dict:
        return await self._send_command("get_state", {})

    @function_tool
    async def click(self, context: RunContext, agent_id: str) -> dict:
        # A click can land on a real <a href> and cause a full page
        # navigation just like navigate() does -- record it the same way.
        self._state["last_agent_action_at"] = time.monotonic()
        return await self._send_command("click", {"agent_id": agent_id})

    @function_tool
    async def type_text(self, context: RunContext, agent_id: str, text: str) -> dict:
        return await self._send_command("type", {"agent_id": agent_id, "text": text})

    @function_tool
    async def navigate(self, context: RunContext, page: str) -> dict:
        # Record when we last acted, so the page_state handler can tell
        # this navigation was caused by us, not the visitor -- the LLM's
        # own turn (the one making this tool call) will already narrate
        # the result, so the independent auto-narration should stay quiet.
        self._state["last_agent_action_at"] = time.monotonic()
        print(f"[orchestrator] navigate() called, timestamp recorded -- pid={os.getpid()}")
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
            res = await asyncio.wait_for(result_future, timeout=COMMAND_TIMEOUT_S)
            if isinstance(res, dict) and res.get("navigating"):
                print(f"[orchestrator] Action '{action}' is navigating. Waiting for new page_state...")
                nav_future = loop.create_future()
                PENDING_NAVIGATIONS[self._room.name] = nav_future
                try:
                    # Give it a bit more timeout for the page to actually load
                    page_state_res = await asyncio.wait_for(nav_future, timeout=8.0)
                    return page_state_res
                except asyncio.TimeoutError:
                    print(f"[orchestrator] Warning: timed out waiting for page_state after navigation")
                    return {"ok": False, "error": "timeout waiting for new page to load"}
                finally:
                    PENDING_NAVIGATIONS.pop(self._room.name, None)
            return res
        except asyncio.TimeoutError:
            return {"ok": False, "error": f"no response from page within {COMMAND_TIMEOUT_S}s"}
        finally:
            PENDING_COMMANDS.pop(command_id, None)


async def entrypoint(ctx: JobContext):
    await ctx.connect()
    room = ctx.room
    print(f"[orchestrator] entrypoint started -- pid={os.getpid()} room={room.name}")
    room_state = ROOM_STATE.setdefault(room.name, {"current_page": None, "elements": []})

    saved_ctx = load_history(room.name)
    if saved_ctx is not None:
        print(f"[orchestrator] restored {len(saved_ctx.items)} prior item(s) for room {room.name}")

    agent = DemoGuideAgent(room, room_state, chat_ctx=saved_ctx)
    session = AgentSession(
        stt="deepgram/nova-3",
        llm="openai/gpt-4.1-mini",
        tts="cartesia/sonic-3",
    )

    session.on("conversation_item_added", lambda ev: save_history(room.name, session.history))

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
            
            nav_future = PENDING_NAVIGATIONS.get(room.name)
            if nav_future and not nav_future.done():
                nav_future.set_result({
                    "ok": True,
                    "page": msg.get("page"),
                    "elements": msg.get("elements", [])
                })

            last_action_at = room_state.get("last_agent_action_at")
            seconds_since_action = (
                time.monotonic() - last_action_at if last_action_at is not None else None
            )
            print(
                f"[orchestrator] page_state received -- pid={os.getpid()} "
                f"page={room_state['current_page']} "
                f"seconds_since_last_agent_action={seconds_since_action}"
            )
            # Only react to page changes once the session is fully running;
            # early page_state messages arrive before session.start() finishes.
            if not session_started:
                return
            # If the agent acted (click OR navigate) very recently, treat
            # this page change as caused by that action -- the LLM's own
            # tool-call turn is already narrating it, so firing the
            # auto-reply too is exactly what produced the duplicate/
            # overlapping responses. Only auto-narrate when the visitor
            # navigated on their own, with no recent agent action.
            caused_by_agent = (
                seconds_since_action is not None and seconds_since_action < AGENT_ACTION_WINDOW_S
            )
            if caused_by_agent:
                print("[orchestrator] suppressing auto-narration (agent-initiated nav)")
                return
            print("[orchestrator] firing auto-narration (visitor-initiated nav)")
            # The visitor clicked around on their own -- let the agent
            # notice and react instead of staying silent about it.
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

    await session.start(
        room=room,
        agent=agent,
        room_options=RoomOptions(close_on_disconnect=False),
    )
    session_started = True

    if saved_ctx is None:
        await session.generate_reply(
            instructions="Greet the visitor warmly and offer to walk them through the product."
        )


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))