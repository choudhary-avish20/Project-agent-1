/*
 * chat-ui.js -- builds the meeting-room sidebar (transcript feed + typed
 * chat input) and wires it to LiveKit's built-in text stream topics.
 * Loaded BEFORE agent-runtime.js (see runtime_injector.py), which calls
 * window.AgentChatUI.init(room) once the room is connected.
 *
 * Reuses LiveKit's own text stream conventions instead of inventing a new
 * one on our own data channel:
 *   - "lk.transcription": AgentSession publishes both the visitor's STT
 *     transcript and the agent's spoken text here by default -- nothing
 *     to configure in orchestrator.py, it's already on.
 *   - "lk.chat": AgentSession listens here by default and treats incoming
 *     text exactly like a spoken user turn -- also already on.
 *
 * NOTE ON VERSIONS: same caveat as agent-runtime.js -- the exact method
 * names below (registerTextStreamHandler, reader.readAll, sendText) are
 * written against LiveKit's documented "Text and transcriptions" feature
 * at the time this was written. Marked CHECK-ME where I'm least certain.
 */
window.AgentChatUI = (function () {
  const STORAGE_KEY = "demo_transcript"; // sessionStorage: survives Option A's per-page reconnects
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
    const wrap = document.createElement("div");
    wrap.style.marginBottom = "10px";

    const label = document.createElement("div");
    label.textContent = speaker === "agent" ? "Agent" : "You";
    label.style.cssText =
      "font-size:12px;font-weight:600;margin-bottom:2px;color:" +
      (speaker === "agent" ? "#0F6E56" : "#5F5E5A");

    const body = document.createElement("div");
    body.textContent = text;
    body.style.cssText = "font-size:13px;line-height:1.4;color:#2C2C2A";

    wrap.appendChild(label);
    wrap.appendChild(body);
    listEl.appendChild(wrap);
    listEl.scrollTop = listEl.scrollHeight;
  }

  function wrapPageContent() {
    // Move everything currently in <body> into a wrapper div, so the
    // sidebar can sit next to the page as a real layout sibling instead
    // of floating on top of it. Only individual properties are set on
    // body.style (not the whole cssText) so we don't clobber any inline
    // styles the original page already had.
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

  function buildSidebar() {
    wrapPageContent();

    const panel = document.createElement("div");
    panel.style.cssText = [
      "position:sticky",
      "top:0",
      "align-self:flex-start",
      "flex:0 0 300px",
      "width:300px",
      "height:100vh",
      "background:#ffffff",
      "border-left:1px solid #e5e3da",
      "z-index:999999",
      "display:flex",
      "flex-direction:column",
      "font-family:sans-serif",
      "box-shadow:-2px 0 8px rgba(0,0,0,0.08)",
    ].join(";");

    const header = document.createElement("div");
    header.textContent = "Transcript";
    header.style.cssText =
      "padding:12px 14px;border-bottom:1px solid #e5e3da;font-size:13px;font-weight:600;color:#2C2C2A";

    listEl = document.createElement("div");
    listEl.style.cssText = "flex:1;overflow-y:auto;padding:12px 14px";

    const inputRow = document.createElement("div");
    inputRow.style.cssText =
      "display:flex;gap:6px;padding:10px;border-top:1px solid #e5e3da";

    const input = document.createElement("input");
    input.placeholder = "Type a message";
    input.style.cssText =
      "flex:1;font-size:13px;padding:6px 8px;border:1px solid #d3d1c7;border-radius:6px";

    const sendBtn = document.createElement("button");
    sendBtn.textContent = "Send";
    sendBtn.type = "button";
    sendBtn.style.cssText =
      "font-size:13px;padding:6px 10px;border:1px solid #d3d1c7;border-radius:6px;background:#fff;cursor:pointer";

    inputRow.appendChild(input);
    inputRow.appendChild(sendBtn);

    panel.appendChild(header);
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
      "[chat-ui] sidebar ready, restored",
      loadTranscript().length,
      "message(s)",
    );
  }

  return { init };
})();
