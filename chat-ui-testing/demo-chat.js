/*
 * demo-chat.js -- builds the meeting-room sidebar (transcript feed + typed
 * chat input) and wires it to LiveKit's built-in text stream topics.
 *
 * Modified for testing/isolated usage in chat-ui-testing folder.
 * If initialized without a LiveKit room object, it runs in standalone mode
 * and mock-responds to visitor messages to facilitate styling testing.
 */
window.AgentChatUI = (function () {
  const STORAGE_KEY = "demo_transcript"; // sessionStorage: survives Option A's per-page reconnects
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

    panel.appendChild(listEl);
    panel.appendChild(inputRow);
    document.body.appendChild(panel);

    return { input, sendBtn };
  }

  function restoreTranscript() {
    loadTranscript().forEach((m) => renderMessage(m.speaker, m.text));
  }

  function init(room) {
    const { input, sendBtn } = buildSidebar();
    restoreTranscript();

    if (!room) {
      console.log("[demo-chat] Running in isolated mode (no LiveKit room).");

      function sendTypedMock() {
        const value = input.value.trim();
        if (!value) return;
        appendMessage("visitor", value);
        input.value = "";

        // Simulate a mock agent response after 1 second
        setTimeout(() => {
          appendMessage(
            "agent",
            'Mock response: Received "' + value + '". This is a test response.',
          );
        }, 1000);
      }

      sendBtn.addEventListener("click", sendTypedMock);
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") sendTypedMock();
      });

      console.log(
        "[demo-chat] Isolated sidebar ready, restored",
        loadTranscript().length,
        "message(s)",
      );
      return;
    }

    // CHECK-ME: confirm registerTextStreamHandler's callback signature
    // (reader, participantInfo) against the current JS SDK docs.
    room.registerTextStreamHandler(
      "lk.transcription",
      async (reader, participantInfo) => {
        // CHECK-ME: confirm reader.readAll() is the current convenience method
        // for a completed text stream (vs manually iterating chunks).
        const text = await reader.readAll();
        if (!text) return;
        const isAgent =
          participantInfo.identity !== room.localParticipant.identity;
        appendMessage(isAgent ? "agent" : "visitor", text);
      },
    );

    function sendTyped() {
      const value = input.value.trim();
      if (!value) return;
      // CHECK-ME: confirm sendText's name/signature against current docs.
      room.localParticipant.sendText(value, { topic: "lk.chat" });
      // typed input isn't re-echoed back on lk.transcription (no STT involved),
      // so echo it locally right away rather than waiting for a round trip.
      appendMessage("visitor", value);
      input.value = "";
    }

    sendBtn.addEventListener("click", sendTyped);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") sendTyped();
    });

    console.log(
      "[demo-chat] LiveKit sidebar ready, restored",
      loadTranscript().length,
      "message(s)",
    );
  }

  // Helper for external testing / simulation
  function simulateAgentMessage(text) {
    appendMessage("agent", text);
  }

  // Clear storage utility
  function clearTranscript() {
    sessionStorage.removeItem(STORAGE_KEY);
    if (listEl) {
      listEl.innerHTML = "";
    }
  }

  return { init, simulateAgentMessage, clearTranscript };
})();
