/*
 * chat-ui.js -- builds the meeting room hud
 */
window.AgentChatUI = (function () {
  const STORAGE_KEY = "demo_transcript";
  const STYLE_ID = "agent-chat-injected-styles";
  let listEl = null;

  function loadTranscript() {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]");
    } catch {
      return [];
    }
  }

  function saveTranscript(messages) {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
  }

  function appendMessage(speaker, text) {
    const messages = loadTranscript();
    messages.push({ speaker, text });
    saveTranscript(messages);
    renderMessage(speaker, text);
  }

  function renderMessage(speaker, text) {
    const isAgent = speaker === "agent";

    const wrap = document.createElement("div");
    wrap.style.cssText =
      "margin-bottom:10px;display:flex;flex-direction:column;max-width:100%;" +
      (isAgent ? "align-items:flex-start;" : "align-items:flex-end;");

    const label = document.createElement("div");
    label.textContent = isAgent ? "Agent" : "You";
    label.style.cssText =
      "font-size:10.5px;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;margin-bottom:4px;color:" +
      (isAgent ? "#8ab4f8" : "rgba(255,255,255,0.55)");

    const bubble = document.createElement("div");
    bubble.textContent = text;
    bubble.style.cssText =
      "font-size:14px;line-height:1.5;padding:10px 14px;max-width:260px;word-wrap:break-word;box-shadow:0 3px 10px rgba(0,0,0,0.15);" +
      (isAgent
        ? "color:#ffffff;background:rgba(44,44,52,0.96);border:1px solid rgba(255,255,255,0.1);border-radius:16px 16px 16px 4px;"
        : "color:#0f0f12;background:#8ab4f8;border:1px solid rgba(255,255,255,0.2);border-radius:16px 16px 4px 16px;font-weight:500;");

    wrap.appendChild(label);
    wrap.appendChild(bubble);
    listEl.appendChild(wrap);
    listEl.scrollTop = listEl.scrollHeight;
  }

  function wrapPageContent() {
    const wrapper = document.createElement("div");
    wrapper.id = "agent-demo-content-wrapper";
    wrapper.style.cssText = "flex:1 1 auto;min-width:0";
    while (document.body.firstChild) {
      wrapper.appendChild(document.body.firstChild);
    }
    document.body.appendChild(wrapper);

    Object.assign(document.body.style, {
      display: "flex",
      alignItems: "flex-start",
      margin: "0",
      minHeight: "100vh",
    });
  }

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
      .agent-chat-list {
        scrollbar-width: thin;
        scrollbar-color: rgba(255,255,255,0.18) transparent;
      }
      .agent-chat-list::-webkit-scrollbar {
        width: 4px;
      }
      .agent-chat-list::-webkit-scrollbar-thumb {
        background: rgba(255,255,255,0.18);
        border-radius: 2px;
      }
      .agent-chat-input::placeholder {
        color: rgba(255,255,255,0.4);
      }
      .agent-chat-input:focus {
        border-color: #8ab4f8;
        background: rgba(18, 18, 22, 0.98);
      }
      .agent-chat-send:hover {
        opacity: 0.85;
      }
      .agent-chat-send:active {
        transform: scale(0.96);
      }
    `;
    document.head.appendChild(style);
  }

  function buildSidebar() {
    injectStyles();

    const panel = document.createElement("div");
    panel.style.cssText = [
      "position:fixed",
      "bottom:0",
      "right:0",
      "width:380px",
      "height:34vh",
      "min-height:240px",
      "max-height:380px",
      "z-index:999999",
      "display:flex",
      "flex-direction:column",
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif",
      "pointer-events:none",
    ].join(";");

    listEl = document.createElement("div");
    listEl.className = "agent-chat-list";
    listEl.style.cssText =
      "flex:1;overflow-y:auto;padding:14px 16px 6px;pointer-events:auto";

    const inputRow = document.createElement("div");
    inputRow.style.cssText =
      "flex-shrink:0;display:flex;align-items:center;gap:8px;padding:10px 14px 14px;pointer-events:auto";

    const input = document.createElement("input");
    input.className = "agent-chat-input";
    input.placeholder = "Type a message";
    input.style.cssText =
      "flex:1;font-size:13px;padding:8px 12px;border:1px solid rgba(255,255,255,0.22);border-radius:20px;background:rgba(18,18,22,0.96);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);color:#ffffff;outline:none;transition:border-color .15s,background .15s";

    const sendBtn = document.createElement("button");
    sendBtn.className = "agent-chat-send";
    sendBtn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 19V5M12 5L5 12M12 5L19 12" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
    sendBtn.type = "button";
    sendBtn.style.cssText =
      "width:34px;height:34px;display:flex;align-items:center;justify-content:center;border:none;border-radius:50%;background:#8ab4f8;color:#0f0f12;cursor:pointer;transition:opacity .15s,transform .1s;flex-shrink:0;padding:0;";

    inputRow.appendChild(input);
    inputRow.appendChild(sendBtn);

    const controlsRow = document.createElement("div");
    controlsRow.style.cssText =
      "flex-shrink:0;display:flex;justify-content:flex-end;gap:8px;padding:10px 14px 0;pointer-events:auto";

    const muteBtn = document.createElement("button");
    muteBtn.type = "button";
    muteBtn.title = "Mute microphone";
    muteBtn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M19 11a7 7 0 0 1-14 0M12 18v3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
    muteBtn.style.cssText =
      "width:30px;height:30px;display:flex;align-items:center;justify-content:center;border:1px solid rgba(255,255,255,0.22);border-radius:50%;background:rgba(18,18,22,0.9);color:#ffffff;cursor:pointer;flex-shrink:0;padding:0;transition:background .15s";

    const endBtn = document.createElement("button");
    endBtn.type = "button";
    endBtn.title = "End call";
    endBtn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
    </svg>`;
    endBtn.style.cssText =
      "width:30px;height:30px;display:flex;align-items:center;justify-content:center;border:none;border-radius:50%;background:#e05a4e;color:#ffffff;cursor:pointer;flex-shrink:0;padding:0;";

    controlsRow.appendChild(muteBtn);
    controlsRow.appendChild(endBtn);

    panel.appendChild(controlsRow);
    panel.appendChild(listEl);
    panel.appendChild(inputRow);
    document.body.appendChild(panel);

    return { input, sendBtn, muteBtn, endBtn };
  }

  function restoreTranscript() {
    loadTranscript().forEach((m) => renderMessage(m.speaker, m.text));
  }

  let _input = null;
  let _sendBtn = null;
  let _muteBtn = null;
  let _endBtn = null;
  let _room = null;
  let _muted = false;
  let _liveKitWired = false;

  function sendTyped() {
    if (!_input) return;
    const value = _input.value.trim();
    if (!value) return;

    appendMessage("visitor", value);
    _input.value = "";

    if (_room) {
      _room.localParticipant.sendText(value, { topic: "lk.chat" });
    } else {
      setTimeout(() => {
        appendMessage(
          "agent",
          'Mock response: Received "' + value + '". (No live room connected)',
        );
      }, 1000);
    }
  }

  function init(room) {
    const { input, sendBtn, muteBtn, endBtn } = buildSidebar();
    _input = input;
    _sendBtn = sendBtn;
    _muteBtn = muteBtn;
    _endBtn = endBtn;
    restoreTranscript();
    wireControlButtons();

    sendBtn.addEventListener("click", sendTyped);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") sendTyped();
    });

    if (!room) {
      console.log("[chat-ui] Running in isolated mode (no LiveKit room).");
      console.log(
        "[chat-ui] Isolated sidebar ready, restored",
        loadTranscript().length,
        "message(s)",
      );
      return;
    }

    wireRoom(room);
  }

  function wireControlButtons() {
    if (!_muteBtn || !_endBtn) return;

    _muteBtn.addEventListener("click", async () => {
      if (!_room) {
        console.warn("[chat-ui] mute clicked but no live room connected yet");
        return;
      }
      const nextMuted = !_muted;
      try {
        await _room.localParticipant.setMicrophoneEnabled(!nextMuted);
        _muted = nextMuted;
        _muteBtn.style.background = _muted ? "#e05a4e" : "rgba(18,18,22,0.9)";
        _muteBtn.title = _muted ? "Unmute microphone" : "Mute microphone";
      } catch (e) {
        console.warn("[chat-ui] failed to toggle microphone:", e);
      }
    });

    _endBtn.addEventListener("click", async () => {
      if (!_room) {
        console.warn(
          "[chat-ui] end call clicked but no live room connected yet",
        );
        return;
      }
      _endBtn.disabled = true;
      if (_input) _input.disabled = true;
      if (_sendBtn) _sendBtn.disabled = true;
      appendMessage("agent", "-- call ended --");
      try {
        await _room.localParticipant.publishData(
          new TextEncoder().encode(JSON.stringify({ type: "end_call" })),
          { reliable: true, topic: "agent-channel" }
        );
      } catch (e) {
        console.warn("[chat-ui] failed to send end_call signal:", e);
      }
      sessionStorage.removeItem(STORAGE_KEY);
      sessionStorage.removeItem("demo_room_name");
      sessionStorage.removeItem("demo_identity");

      try {
        await _room.disconnect();
      } catch (e) {
        console.warn("[chat-ui] error disconnecting:", e);
      }
    });
  }

  function wireRoom(room) {
    if (_liveKitWired) return;
    _liveKitWired = true;
    _room = room;

    if (!_input || !_sendBtn) {
      console.warn(
        "[chat-ui] wireRoom called before sidebar was built -- call init() first.",
      );
      return;
    }

    room.registerTextStreamHandler(
      "lk.transcription",
      async (reader, participantInfo) => {
        const text = await reader.readAll();
        if (!text) return;
        const isAgent =
          participantInfo.identity !== room.localParticipant.identity;
        appendMessage(isAgent ? "agent" : "visitor", text);
      },
    );

    console.log(
      "[chat-ui] LiveKit sidebar wired, restored",
      loadTranscript().length,
      "message(s)",
    );
  }

  function simulateAgentMessage(text) {
    appendMessage("agent", text);
  }

  function clearTranscript() {
    sessionStorage.removeItem(STORAGE_KEY);
    if (listEl) {
      listEl.innerHTML = "";
    }
  }

  return { init, wireRoom, simulateAgentMessage, clearTranscript };
})();
