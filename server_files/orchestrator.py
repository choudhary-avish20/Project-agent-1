"""
orchestrator.py — the LLM brain of the demo joins the LiveKit room 
    python orchestrator.py dev
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
AGENT_ACTION_WINDOW_S = 8.0

# Try to find a valid flow JSON file
candidates = [
    Path("pages-flow.json"),
    Path("pages_flow.json"),
    Path("demo-flow.json"),
    Path("demo_flow.json"),
]

DEMO_FLOW_PATH = None
for p in candidates:
    if p.exists():
        DEMO_FLOW_PATH = p
        break

if DEMO_FLOW_PATH is None:
    # Default fallback path just for logging/reporting if not found
    DEMO_FLOW_PATH = Path("pages-flow.json")


def load_demo_flow() -> dict | None:
    if not DEMO_FLOW_PATH.exists():
        print(f"[orchestrator] no {DEMO_FLOW_PATH} found -- running without a scripted demo flow")
        return None
    try:
        flow = json.loads(DEMO_FLOW_PATH.read_text(encoding="utf-8"))
        print(f"[orchestrator] loaded demo flow with {len(flow.get('steps', []))} step(s)")
        return flow
    except Exception as e:
        print(f"[orchestrator] warning: could not load {DEMO_FLOW_PATH}: {e}")
        return None


def build_roadmap_summary(flow: dict) -> str:
    lines = [f"{i}. [{s['id']}] {s['page']} -- {s['goal']}" for i, s in enumerate(flow.get("steps", []))]
    return "\n".join(lines)


DEMO_FLOW = load_demo_flow()
DEMO_ROADMAP = build_roadmap_summary(DEMO_FLOW) if DEMO_FLOW else None

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

        roadmap_block = (
            f"\n\nDemo roadmap (in order, for your own orientation -- don't read this list "
            f"aloud verbatim):\n{DEMO_ROADMAP}"
            if DEMO_ROADMAP
            else ""
        )

        super().__init__(
            instructions=(
                "You are a friendly, upbeat product guide giving a live spoken demo "
                "of this website to a visitor, following a scripted walkthrough.\n\n"
                "Use get_demo_script to see the current step's goal and talking points "
                "-- that script is your source for what to SAY. Use get_page_elements "
                "only to find a data-agent-id when you actually need to click or type "
                "something; never narrate by reading out the raw element list, and "
                "don't re-describe things (like the navbar) that aren't part of the "
                "current step's talking points, even if they're visible on the page.\n\n"
                "To ensure you only talk about what the visitor can see on screen, "
                "only describe or reference elements that have 'in_viewport': True "
                "in get_page_elements. If a target element or content is off-screen "
                "('in_viewport': False), call scroll('down') or scroll('up') to scroll "
                "the page and bring it into view before you talk about it.\n\n"
                "Each step names the page it belongs to. If you're not already there, "
                "call navigate() to that page before covering its talking points.\n\n"
                "When you've covered a step, call advance_demo_step to move on and get "
                "the next step's script. If the visitor asks something off-script, "
                "answer it briefly, then continue from the current step -- don't "
                "restart or skip ahead just because of a question. If the visitor "
                "explicitly asks to jump to a different part of the demo (by name, "
                "e.g. 'skip to custom orders'), call jump_to_step with the matching "
                "step id from the roadmap. Narrate what you're about to do in a short "
                "sentence *before* calling a tool, so the visitor isn't sitting in "
                "silence while the action runs.\n\n"
                "NAVIGATION RULES — CRITICAL, FOLLOW EXACTLY:\n"
                "This site is a static clone of a React SPA. Many buttons and links "
                "exist in the HTML but have NO working handler. Clicking them either "
                "does nothing or causes a timeout. You MUST follow these rules:\n\n"
                "1. NEVER click hero CTA buttons: button-view-collection, "
                "button-custom-orders. They have no handler. "
                "To go to a new page, ALWAYS call navigate('filename.html') directly.\n\n"
                "2. NEVER click any product card link or image link "
                "(e.g. a-sunset-bloom-dress, a-garden-party-blouse, a-cosmic-dreams-top, "
                "a-spring-meadow-cardigan, a-ocean-waves-tunic, a-autumn-leaves-jacket, "
                "a-moonlight-serenade-dress, a-butterfly-garden-skirt, or any numbered "
                "anchor like a-9, a-14, a-19, a-24 etc.). These point to /product/1 "
                "which is an SPA route that does not exist as a page file. "
                "Use navigate('product_:id.html') instead.\n\n"
                "3. NEVER click Add to Cart buttons (button-add-to-cart) or wishlist "
                "icon buttons (button-27, button-10, button-11, button-15, button-16, "
                "button-20, button-21, button-25, button-26 etc.) — they have no handler.\n\n"
                "4. NEVER click form submit buttons: button-submit-my-custom-order-request, "
                "button-send-message. The forms have no backend; clicking these does nothing.\n\n"
                "5. NEVER click the mobile hamburger menu button (button-6 on every page) "
                "— it toggles a mobile nav drawer that is non-functional in the clone.\n\n"
                "6. NEVER click pagination links: a-previous, a-next, a-1, a-2, a-3 "
                "on the collections page — they are href='#' anchors with no function.\n\n"
                "7. NEVER click footer utility links: a-size-guide, a-care-instructions, "
                "a-returns-exchanges, a-faq — they are all href='#' placeholders.\n\n"
                "8. NEVER click external links: a-see-more, a-7, a-12 "
                "(Instagram links) — they open a new browser tab and you will lose "
                "control of the demo page.\n\n"
                "9. SAFE to click on the product page: color selector buttons "
                "(button-burgundy-rose, button-blush-pink, button-cream-ivory, "
                "button-deep-rose), size buttons (button-xs through button-xxl), "
                "and tab buttons (tab-description, tab-care-instructions, "
                "tab-shipping-info) — these have working inline JS handlers.\n\n"
                "10. SAFE to click on the about page: carousel buttons "
                "(button-go-to-slide-1 through button-go-to-slide-4) — they work.\n\n"
                "11. SAFE to use navigate() at any time to move between pages. "
                "Valid page filenames: index.html, collections.html, product_:id.html, "
                "custom-orders.html, about.html, contact.html." + roadmap_block
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
        self._state["last_agent_action_at"] = time.monotonic()
        return await self._send_command("click", {"agent_id": agent_id})

    @function_tool
    async def type_text(self, context: RunContext, agent_id: str, text: str) -> dict:
        return await self._send_command("type", {"agent_id": agent_id, "text": text})

    @function_tool
    async def navigate(self, context: RunContext, page: str) -> dict:
        self._state["last_agent_action_at"] = time.monotonic()
        print(f"[orchestrator] navigate() called, timestamp recorded -- pid={os.getpid()}")
        return await self._send_command("navigate", {"page": page})

    @function_tool
    async def scroll(self, context: RunContext, direction: str) -> dict:
        """Scroll the page. direction must be 'up' or 'down'."""
        self._state["last_agent_action_at"] = time.monotonic()
        print(f"[orchestrator] scroll() called ({direction}) -- pid={os.getpid()}")
        return await self._send_command("scroll", {"direction": direction})

    @function_tool
    async def get_demo_script(self, context: RunContext) -> dict:
        """Get the goal and talking points for the current demo step."""
        return self._step_payload(self._state.get("demo_step_index", 0))

    @function_tool
    async def advance_demo_step(self, context: RunContext) -> dict:
        """Move to the next step in the demo and get its script, navigating the browser if needed."""
        if not DEMO_FLOW:
            return {"ok": False, "error": "no demo flow is configured"}
        steps = DEMO_FLOW.get("steps", [])
        next_index = self._state.get("demo_step_index", 0) + 1
        if next_index >= len(steps):
            self._state["demo_step_index"] = len(steps) - 1
            return {"ok": True, "done": True, "outro": DEMO_FLOW.get("outro", "")}
        self._state["demo_step_index"] = next_index
        
        payload = self._step_payload(next_index)
        target_page = payload.get("page")
        if target_page and target_page != self._state.get("current_page"):
            self._state["last_agent_action_at"] = time.monotonic()
            print(f"[orchestrator] advance_demo_step navigating to {target_page} -- pid={os.getpid()}")
            await self._send_command("navigate", {"page": target_page})
        return payload

    @function_tool
    async def jump_to_step(self, context: RunContext, step_id: str) -> dict:
        """Jump directly to a named step in the demo roadmap, navigating the browser if needed."""
        if not DEMO_FLOW:
            return {"ok": False, "error": "no demo flow is configured"}
        steps = DEMO_FLOW.get("steps", [])
        for i, step in enumerate(steps):
            if step.get("id") == step_id:
                self._state["demo_step_index"] = i
                payload = self._step_payload(i)
                target_page = payload.get("page")
                if target_page and target_page != self._state.get("current_page"):
                    self._state["last_agent_action_at"] = time.monotonic()
                    print(f"[orchestrator] jump_to_step navigating to {target_page} -- pid={os.getpid()}")
                    await self._send_command("navigate", {"page": target_page})
                return payload
        available = [s.get("id") for s in steps]
        return {"ok": False, "error": f"no step named '{step_id}'", "available_steps": available}

    def _step_payload(self, index: int) -> dict:
        if not DEMO_FLOW:
            return {"ok": False, "error": "no demo flow is configured"}
        steps = DEMO_FLOW.get("steps", [])
        if not steps or index >= len(steps):
            return {"ok": False, "error": "step index out of range"}
        step = steps[index]
        return {
            "ok": True,
            "step_index": index,
            "total_steps": len(steps),
            "id": step.get("id"),
            "page": step.get("page"),
            "goal": step.get("goal"),
            "talking_points": step.get("talking_points", []),
            "focus_elements": step.get("focus_elements", []),
        }

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
    room_state = ROOM_STATE.setdefault(
        room.name, {"current_page": None, "elements": [], "demo_step_index": 0}
    )

    saved_ctx = load_history(room.name)
    if saved_ctx is not None:
        print(f"[orchestrator] restored {len(saved_ctx.items)} prior item(s) for room {room.name}")

    agent = DemoGuideAgent(room, room_state, chat_ctx=saved_ctx)
    session = AgentSession(
        stt="deepgram/nova-3",
        llm="openai/gpt-4.1-mini",
        tts="cartesia/sonic-3",
        turn_handling={
            "interruption": {
                "enabled": True,
                "min_duration": 0.2,
                "backchannel_boundary": (0.0, 0.0),
            }
        }
    )

    session.on("conversation_item_added", lambda ev: save_history(room.name, session.history))

    session_started = False
    call_ending = False
    page_state_ready = asyncio.Event()

    async def _end_call():
        nonlocal call_ending
        if call_ending:
            return
        call_ending = True
        print(f"[orchestrator] end_call received -- pid={os.getpid()} room={room.name}, shutting down")

        try:
            await session.aclose()
        except Exception as e:
            print(f"[orchestrator] warning during session close: {e}")

        ROOM_STATE.pop(room.name, None)
        try:
            _state_file(room.name).unlink(missing_ok=True)
        except Exception as e:
            print(f"[orchestrator] warning: could not remove persisted history: {e}")

        try:
            await ctx.delete_room()
        except Exception as e:
            print(f"[orchestrator] warning: could not delete room: {e}")

        ctx.shutdown(reason="call ended by visitor")

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
        elif msg.get("type") == "end_call":
            asyncio.create_task(_end_call())
        elif msg.get("type") == "page_state":
            room_state["current_page"] = msg.get("page")
            room_state["elements"] = msg.get("elements", [])
            page_state_ready.set()  # signal that the browser is connected and ready
            
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
            if not session_started:
                return
            caused_by_agent = (
                (seconds_since_action is not None and seconds_since_action < AGENT_ACTION_WINDOW_S)
                or (nav_future is not None and not nav_future.done())
            )
            if caused_by_agent:
                print("[orchestrator] suppressing auto-narration (agent-initiated nav)")
                return
            print("[orchestrator] firing auto-narration (visitor-initiated nav)")
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
        # Wait for the browser's agent_runtime.js to connect and publish its first
        # page_state before greeting. Without this, get_page_elements always times
        # out on a cold start because the LLM's first tool call fires before the
        # browser has finished room.connect() + mic permission.
        try:
            await asyncio.wait_for(page_state_ready.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            print(f"[orchestrator] warning: browser did not send page_state within 15s, greeting anyway")
        
        intro_text = DEMO_FLOW.get("intro") if DEMO_FLOW else None
        greeting_instructions = (
            f"{intro_text} Then call get_demo_script to see the first step and begin."
            if intro_text
            else "Greet the visitor warmly and offer to walk them through the product."
        )
        await session.generate_reply(instructions=greeting_instructions)


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))