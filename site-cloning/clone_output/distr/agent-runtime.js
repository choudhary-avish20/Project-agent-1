/*
 * agent-runtime.js -- lives inside every clone page. Connects to the
 * LiveKit room, publishes the visitor's mic, plays the agent's speech,
 * and executes action commands (click / type / navigate / get_state)
 * sent by orchestrator.py over the room's data channel.
 *
 */
(function () {
  const TOKEN_SERVER_URL = window.TOKEN_SERVER_URL || "http://localhost:8081";
  const DATA_TOPIC = "agent-channel";

  function getOrCreate(key, factory) {
    let value = sessionStorage.getItem(key);
    if (!value) {
      value = factory();
      sessionStorage.setItem(key, value);
    }
    return value;
  }
  const roomName = getOrCreate(
    "demo_room_name",
    () => "demo-" + Math.random().toString(36).slice(2, 10),
  );
  const identity = getOrCreate(
    "demo_identity",
    () => "visitor-" + Math.random().toString(36).slice(2, 8),
  );

  function currentPageFilename() {
    const path = window.location.pathname;
    return path.substring(path.lastIndexOf("/") + 1) || "index.html";
  }

  function collectElements() {
    return Array.from(document.querySelectorAll("[data-agent-id]"))
      .filter((el) => el.offsetParent !== null) // roughly: currently visible
      .map((el) => ({
        agent_id: el.getAttribute("data-agent-id"),
        role: el.getAttribute("role") || el.tagName.toLowerCase(),
        text: (
          el.innerText ||
          el.getAttribute("aria-label") ||
          el.getAttribute("placeholder") ||
          ""
        )
          .trim()
          .slice(0, 60),
      }));
  }

  let cursorEl = null;

  //fake cursor!
  function getCursor() {
    if (cursorEl) return cursorEl;
    cursorEl = document.createElement("div");
    cursorEl.style.cssText = [
      "position:fixed",
      "width:16px",
      "height:16px",
      "border-radius:50%",
      "background:rgba(255,90,50,0.85)",
      "border:2px solid white",
      "box-shadow:0 1px 4px rgba(0,0,0,0.4)",
      "z-index:2147483647",
      "pointer-events:none",
      "transition:left 0.5s ease, top 0.5s ease",
      "left:-100px",
      "top:-100px",
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

  //tools for the llm
  async function executeCommand(cmd) {
    try {
      switch (cmd.action) {
        case "get_state":
          return {
            ok: true,
            page: currentPageFilename(),
            elements: collectElements(),
          };

        case "click": {
          const el = resolveElement(cmd.agent_id);
          if (!el)
            return {
              ok: false,
              error: `no element with data-agent-id="${cmd.agent_id}"`,
            };
          await moveCursorTo(el);

          // Check if the element (or its closest ancestor) is a link that navigates
          const anchor = el.closest("a[href]");
          let willNavigate = false;
          if (anchor) {
            const href = anchor.getAttribute("href");
            const target = anchor.getAttribute("target");
            if (
              href &&
              !href.startsWith("#") &&
              !href.startsWith("javascript:") &&
              target !== "_blank"
            ) {
              willNavigate = true;
            }
          }

          el.click();

          if (willNavigate) {
            return { ok: true, navigating: true };
          }
          return {
            ok: true,
            page: currentPageFilename(),
            elements: collectElements(),
          };
        }

        case "type": {
          const el = resolveElement(cmd.agent_id);
          if (!el)
            return {
              ok: false,
              error: `no element with data-agent-id="${cmd.agent_id}"`,
            };
          await moveCursorTo(el);
          el.focus();
          el.value = cmd.text;
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
          return {
            ok: true,
            page: currentPageFilename(),
            elements: collectElements(),
          };
        }

        case "navigate":
          window.location.href = cmd.page;
          return { ok: true, navigating: true };

        default:
          return { ok: false, error: `unknown action "${cmd.action}"` };
      }
    } catch (err) {
      return { ok: false, error: String(err) };
    }
  }

  async function init() {
    console.log("[agent-runtime] init() started");

    // Build the chat sidebar immediately — before any network calls — so it
    // always appears even if the token server or LiveKit is unavailable.
    if (window.AgentChatUI) {
      window.AgentChatUI.init(); // no room yet: sidebar builds in mock/isolated mode
      console.log("[agent-runtime] ✅ chat UI sidebar built");
    } else {
      console.warn(
        "[agent-runtime] chat-ui.js not loaded -- skipping sidebar UI",
      );
    }

    if (!window.LivekitClient) {
      console.error(
        "[agent-runtime] LivekitClient SDK not loaded -- check the CDN <script> tag.",
      );
      return;
    }
    console.log("[agent-runtime] LivekitClient SDK found");
    const { Room, RoomEvent } = window.LivekitClient;

    console.log(
      `[agent-runtime] fetching token from ${TOKEN_SERVER_URL}/token  room=${roomName}  identity=${identity}`,
    );
    const res = await fetch(
      `${TOKEN_SERVER_URL}/token?room=${encodeURIComponent(roomName)}&identity=${encodeURIComponent(identity)}`,
    );
    if (!res.ok) {
      console.error(
        `[agent-runtime] token fetch failed: ${res.status} ${res.statusText}`,
      );
      return;
    }
    const { token, url } = await res.json();
    console.log(`[agent-runtime] token received, LiveKit URL: ${url}`);

    const room = new Room();

    room.on(RoomEvent.TrackSubscribed, (track) => {
      console.log(
        "[agent-runtime] 🔊 Track subscribed:",
        track.kind,
        track.sid,
      );
      if (track.kind === "audio") {
        const audioEl = track.attach();
        audioEl.style.display = "none";
        document.body.appendChild(audioEl);
        console.log("[agent-runtime] 🔊 Audio track attached to DOM");
      }
    });

    room.on(
      RoomEvent.DataReceived,
      async (payload, participant, _kind, topic) => {
        if (topic !== DATA_TOPIC) return;
        let msg;
        try {
          msg = JSON.parse(new TextDecoder().decode(payload));
        } catch {
          return;
        }
        console.log(
          "[agent-runtime] 📩 Data received from:",
          participant ? participant.identity : "unknown",
          "msg:",
          msg,
        );
        if (msg.type !== "command") return;

        const result = await executeCommand(msg);
        const reply = JSON.stringify({
          type: "command_result",
          id: msg.id,
          result,
        });
        console.log("[agent-runtime] 📤 Sending command result reply:", reply);
        room.localParticipant.publishData(new TextEncoder().encode(reply), {
          reliable: true,
          topic: DATA_TOPIC,
        });
      },
    );

    console.log("[agent-runtime] connecting to LiveKit room...");
    await room.connect(url, token);
    console.log("[agent-runtime] ✅ connected to room:", roomName);

    // Now wire the real LiveKit transcription/chat to the already-visible sidebar
    if (window.AgentChatUI && window.AgentChatUI.wireRoom) {
      window.AgentChatUI.wireRoom(room);
      console.log("[agent-runtime] ✅ chat UI wired to LiveKit room");
    }

    try {
      await room.localParticipant.setMicrophoneEnabled(true);
      console.log("[agent-runtime] ✅ microphone enabled");
    } catch (micErr) {
      console.warn(
        "[agent-runtime] ⚠️ microphone not available:",
        micErr.message,
      );
    }

    const pageState = JSON.stringify({
      type: "page_state",
      page: currentPageFilename(),
      elements: collectElements(),
    });
    room.localParticipant.publishData(new TextEncoder().encode(pageState), {
      reliable: true,
      topic: DATA_TOPIC,
    });
    console.log(
      "[agent-runtime] ✅ page_state announced:",
      currentPageFilename(),
      "with",
      collectElements().length,
      "elements",
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
