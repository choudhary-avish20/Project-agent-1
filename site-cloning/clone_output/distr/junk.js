/*
 * agent-runtime.js -- lives inside every clone page. Connects to the
 * LiveKit room, publishes the visitor's mic, plays the agent's speech,
 * and executes action commands (click / type / navigate / get_state)
 * sent by orchestrator.py over the room's data channel.
 *
 */
(function () {
  const TOKEN_SERVER_URL = window.TOKEN_SERVER_URL || "http://localhost:8080";
  const DATA_TOPIC = "agent-channel";

  // ---- stable identity across page reloads (Option A: reconnect per page) ----
  function getOrCreate(key, factory) {
    let value = sessionStorage.getItem(key);
    if (!value) {
      value = factory();
      sessionStorage.setItem(key, value);
    }
    return value;
  }
  const roomName = getOrCreate("demo_room_name", () => "demo-" + Math.random().toString(36).slice(2, 10));
  const identity = getOrCreate("demo_identity", () => "visitor-" + Math.random().toString(36).slice(2, 8));

  // ---- current page's filename, matching the slugs stitcher.py rewrote hrefs to ----
  function currentPageFilename() {
    const path = window.location.pathname;
    return path.substring(path.lastIndexOf("/") + 1) || "index.html";
  }

  // ---- gather everything the orchestrator is allowed to act on ----
  function collectElements() {
    return Array.from(document.querySelectorAll("[data-agent-id]"))
      .filter((el) => el.offsetParent !== null) // roughly: currently visible
      .map((el) => ({
        agent_id: el.getAttribute("data-agent-id"),
        role: el.getAttribute("role") || el.tagName.toLowerCase(),
        text: (el.innerText || el.getAttribute("aria-label") || el.getAttribute("placeholder") || "").trim().slice(0, 60),
      }));
  }

  // ---- a visible fake cursor so actions read as "the agent is doing this", not a teleport ----
  let cursorEl = null;
  function getCursor() {
    if (cursorEl) return cursorEl;
    cursorEl = document.createElement("div");
    cursorEl.style.cssText = [
      "position:fixed", "width:16px", "height:16px", "border-radius:50%",
      "background:rgba(255,90,50,0.85)", "border:2px solid white",
      "box-shadow:0 1px 4px rgba(0,0,0,0.4)", "z-index:2147483647",
      "pointer-events:none", "transition:left 0.5s ease, top 0.5s ease",
      "left:-100px", "top:-100px",
    ].join(";");
    document.body.appendChild(cursorEl);
    return cursorEl;
  }

  function moveCursorTo(el) {
    return new Promise((resolve) => {
      const rect = el.getBoundingClientRect();
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      const cursor = getCursor();
      // wait a beat for scrollIntoView to settle before animating the cursor
      setTimeout(() => {
        const r = el.getBoundingClientRect();
        cursor.style.left = r.left + r.width / 2 - 8 + "px";
        cursor.style.top = r.top + r.height / 2 - 8 + "px";
        setTimeout(resolve, 550); // matches the CSS transition duration above
      }, 300);
    });
  }

  function resolveElement(agentId) {
    return document.querySelector(`[data-agent-id="${CSS.escape(agentId)}"]`);
  }

  // ---- executing commands from the orchestrator ----
  async function executeCommand(cmd) {
    try {
      switch (cmd.action) {
        case "get_state":
          return { ok: true, page: currentPageFilename(), elements: collectElements() };

        case "click": {
          const el = resolveElement(cmd.agent_id);
          if (!el) return { ok: false, error: `no element with data-agent-id="${cmd.agent_id}"` };
          await moveCursorTo(el);
          el.click();
          return { ok: true, page: currentPageFilename(), elements: collectElements() };
        }

        case "type": {
          const el = resolveElement(cmd.agent_id);
          if (!el) return { ok: false, error: `no element with data-agent-id="${cmd.agent_id}"` };
          await moveCursorTo(el);
          el.focus();
          el.value = cmd.text;
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
          return { ok: true, page: currentPageFilename(), elements: collectElements() };
        }

        case "navigate":
          // A real navigation, matching Option A: the session will
          // reconnect on the new page rather than staying alive through it.
          window.location.href = cmd.page;
          return { ok: true, navigating: true };

        default:
          return { ok: false, error: `unknown action "${cmd.action}"` };
      }
    } catch (err) {
      return { ok: false, error: String(err) };
    }
  }

  // ---- connect and wire everything up ----
  async function init() {
    // CHECK-ME: confirm this matches LiveKit's current JS quickstart CDN + global name.
    if (!window.LivekitClient) {
      console.error("[agent-runtime] LivekitClient SDK not loaded -- check the CDN <script> tag.");
      return;
    }
    const { Room, RoomEvent } = window.LivekitClient;

    const res = await fetch(`${TOKEN_SERVER_URL}/token?room=${encodeURIComponent(roomName)}&identity=${encodeURIComponent(identity)}`);
    const { token, url } = await res.json();

    const room = new Room();

    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === "audio") {
        const audioEl = track.attach();
        audioEl.style.display = "none";
        document.body.appendChild(audioEl);
      }
    });

    // CHECK-ME: verify the callback argument order/shape against the
    // current SDK -- this assumes (payload: Uint8Array, participant, kind, topic).
    room.on(RoomEvent.DataReceived, async (payload, _participant, _kind, topic) => {
      if (topic !== DATA_TOPIC) return;
      let msg;
      try {
        msg = JSON.parse(new TextDecoder().decode(payload));
      } catch {
        return;
      }
      if (msg.type !== "command") return;

      const result = await executeCommand(msg);
      const reply = JSON.stringify({ type: "command_result", id: msg.id, result });
      // CHECK-ME: confirm publishData's options shape (reliable/topic) against current docs.
      room.localParticipant.publishData(new TextEncoder().encode(reply), { reliable: true, topic: DATA_TOPIC });
    });

    await room.connect(url, token);
    await room.localParticipant.setMicrophoneEnabled(true);

    // announce the page we landed on so the orchestrator can react without being asked
    const pageState = JSON.stringify({ type: "page_state", page: currentPageFilename(), elements: collectElements() });
    room.localParticipant.publishData(new TextEncoder().encode(pageState), { reliable: true, topic: DATA_TOPIC });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();