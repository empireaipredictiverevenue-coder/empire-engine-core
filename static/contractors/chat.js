/**
 * Empire AI · Contractor-recruit chat widget
 * ==========================================
 * Vanilla JS floating chat bubble, bottom-right corner.
 * No build step, no dependencies, no React.
 *
 * Click the bubble to expand/collapse. Type a message, press Enter or
 * click Send. Messages POST to /api/contractors/chat, reply renders
 * in a scrollable feed.
 *
 * Rate-limit indicator: shows remaining messages in the session.
 *
 * Date: 2026-06-14
 */
(function () {
  "use strict";

  var SESSION_KEY = "empire-chat-sid";
  var API_ENDPOINT = "/api/contractors/chat";

  // ── Session ID (persisted in sessionStorage) ──────────────────────
  function getSessionId() {
    var sid = sessionStorage.getItem(SESSION_KEY);
    if (!sid) {
      sid = "co_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
      sessionStorage.setItem(SESSION_KEY, sid);
    }
    return sid;
  }

  // ── CSS injected into the page ─────────────────────────────────────
  var STYLE_ID = "empire-chat-style";
  if (!document.getElementById(STYLE_ID)) {
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = [
      "#ecw-bubble {",
      "  position: fixed; bottom: 24px; right: 24px; z-index: 2147483647;",
      "  width: 56px; height: 56px; border-radius: 50%;",
      "  background: linear-gradient(135deg, #4FD1C5 0%, #38B2AC 100%);",
      "  color: #0A1A2F; border: none; cursor: pointer;",
      "  box-shadow: 0 4px 20px rgba(79,209,197,0.35);",
      "  display: flex; align-items: center; justify-content: center;",
      "  transition: transform 0.2s ease, box-shadow 0.2s ease;",
      "  font-size: 24px; line-height: 1;",
      "}",
      "#ecw-bubble:hover { transform: scale(1.08); box-shadow: 0 6px 28px rgba(79,209,197,0.5); }",
      "#ecw-bubble svg { width: 26px; height: 26px; }",
      "",
      "#ecw-panel {",
      "  position: fixed; bottom: 90px; right: 24px; z-index: 2147483646;",
      "  width: 360px; max-height: 520px;",
      "  background: #0F1D33; border: 1px solid rgba(79,209,197,0.2);",
      "  border-radius: 14px; box-shadow: 0 12px 48px rgba(0,0,0,0.5);",
      "  display: none; flex-direction: column; overflow: hidden;",
      "  animation: ecw-slide-up 0.25s ease-out;",
      "  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;",
      "}",
      "#ecw-panel.open { display: flex; }",
      "",
      "@keyframes ecw-slide-up {",
      "  from { opacity: 0; transform: translateY(12px); }",
      "  to   { opacity: 1; transform: translateY(0); }",
      "}",
      "@keyframes ecw-fade-in {",
      "  from { opacity: 0; transform: translateY(6px); }",
      "  to   { opacity: 1; transform: translateY(0); }",
      "}",
      "",
      "#ecw-head {",
      "  padding: 14px 16px; border-bottom: 1px solid rgba(232,238,246,0.08);",
      "  display: flex; justify-content: space-between; align-items: center;",
      "  background: rgba(79,209,197,0.06);",
      "}",
      "#ecw-head-title {",
      "  font-weight: 600; font-size: 14px; color: #E8EEF6;",
      "  display: flex; align-items: center; gap: 8px;",
      "}",
      "#ecw-head-title span { color: #4FD1C5; }",
      "#ecw-head-close {",
      "  background: none; border: 1px solid rgba(232,238,246,0.12);",
      "  color: #94A3B8; cursor: pointer; border-radius: 6px;",
      "  width: 28px; height: 28px; display: flex; align-items: center;",
      "  justify-content: center; font-size: 16px; transition: all 0.15s;",
      "}",
      "#ecw-head-close:hover { color: #FC8181; border-color: rgba(252,129,129,0.3); }",
      "",
      "#ecw-msgs {",
      "  flex: 1; overflow-y: auto; padding: 12px 14px;",
      "  display: flex; flex-direction: column; gap: 10px;",
      "  min-height: 200px; max-height: 360px;",
      "  scrollbar-width: thin; scrollbar-color: rgba(79,209,197,0.2) transparent;",
      "}",
      "#ecw-msgs::-webkit-scrollbar { width: 4px; }",
      "#ecw-msgs::-webkit-scrollbar-thumb { background: rgba(79,209,197,0.2); border-radius: 4px; }",
      "",
      ".ecw-msg {",
      "  max-width: 85%; padding: 10px 14px; border-radius: 12px;",
      "  font-size: 13px; line-height: 1.5; word-break: break-word;",
      "  animation: ecw-fade-in 0.2s ease-out;",
      "}",
      ".ecw-msg.user {",
      "  align-self: flex-end;",
      "  background: linear-gradient(135deg, #4FD1C5 0%, #38B2AC 100%);",
      "  color: #0A1A2F; font-weight: 500;",
      "  border-bottom-right-radius: 4px;",
      "}",
      ".ecw-msg.bot {",
      "  align-self: flex-start;",
      "  background: rgba(232,238,246,0.06); color: #E8EEF6;",
      "  border: 1px solid rgba(232,238,246,0.08);",
      "  border-bottom-left-radius: 4px;",
      "}",
      ".ecw-msg.system {",
      "  align-self: center; font-size: 11px; color: #64748B;",
      "  font-style: italic; background: none; border: none; padding: 6px 0;",
      "  max-width: 100%; text-align: center;",
      "}",
      ".ecw-msg.typing {",
      "  align-self: flex-start;",
      "  background: rgba(232,238,246,0.06); color: #94A3B8;",
      "  border: 1px solid rgba(232,238,246,0.08);",
      "  border-bottom-left-radius: 4px;",
      "  display: flex; align-items: center; gap: 6px; padding: 12px 18px;",
      "}",
      ".ecw-typing-dot {",
      "  width: 6px; height: 6px; border-radius: 50%;",
      "  background: #64748B; animation: ecw-bounce 1.2s infinite;",
      "}",
      ".ecw-typing-dot:nth-child(2) { animation-delay: 0.2s; }",
      ".ecw-typing-dot:nth-child(3) { animation-delay: 0.4s; }",
      "@keyframes ecw-bounce {",
      "  0%, 60%, 100% { transform: translateY(0); }",
      "  30% { transform: translateY(-4px); }",
      "}",
      "",
      "#ecw-input-row {",
      "  padding: 10px 12px; border-top: 1px solid rgba(232,238,246,0.08);",
      "  display: flex; gap: 8px; align-items: center;",
      "}",
      "#ecw-input {",
      "  flex: 1; padding: 10px 12px; border-radius: 10px;",
      "  background: rgba(10,26,47,0.6); color: #E8EEF6;",
      "  border: 1px solid rgba(232,238,246,0.12);",
      "  font-size: 13px; font-family: inherit; outline: none; transition: border-color 0.15s;",
      "}",
      "#ecw-input:focus { border-color: #4FD1C5; }",
      "#ecw-input::placeholder { color: #64748B; }",
      "",
      "#ecw-send {",
      "  flex-shrink: 0; width: 38px; height: 38px; border-radius: 50%;",
      "  background: linear-gradient(135deg, #4FD1C5 0%, #38B2AC 100%);",
      "  color: #0A1A2F; border: none; cursor: pointer;",
      "  display: flex; align-items: center; justify-content: center;",
      "  font-size: 18px; transition: transform 0.15s;",
      "}",
      "#ecw-send:hover { transform: scale(1.1); }",
      "#ecw-send:disabled { opacity: 0.4; cursor: default; transform: none; }",
      "",
      "#ecw-footer {",
      "  padding: 6px 14px; border-top: 1px solid rgba(232,238,246,0.05);",
      "  font-size: 10px; color: #64748B; text-align: center;",
      "  background: rgba(10,26,47,0.3);",
      "}",
      "#ecw-footer span { color: #4FD1C5; }",
      "",
      ".ecw-hidden { display: none !important; }",
    ].join("\n");
    document.head.appendChild(style);
  }

  // ── HTML structure ─────────────────────────────────────────────────
  // Chat bubble
  var bubble = document.createElement("button");
  bubble.id = "ecw-bubble";
  bubble.setAttribute("aria-label", "Open chat");
  bubble.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
  document.body.appendChild(bubble);

  // Chat panel
  var panel = document.createElement("div");
  panel.id = "ecw-panel";
  panel.innerHTML = [
    '<div id="ecw-head">',
    '  <div id="ecw-head-title">EMPIRE <span>AI</span></div>',
    '  <button id="ecw-head-close" aria-label="Close chat">&times;</button>',
    '</div>',
    '<div id="ecw-msgs">',
    '  <div class="ecw-msg system">Hi! Ask me anything about getting leads for your contracting business.</div>',
    '</div>',
    '<div id="ecw-input-row">',
    '  <input id="ecw-input" type="text" placeholder="Type your message..." maxlength="2000" autocomplete="off" />',
    '  <button id="ecw-send" aria-label="Send message">',
    '    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px">',
    '      <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
    '    </svg>',
    '  </button>',
    '</div>',
    '<div id="ecw-footer">Powered by <span>Empire AI</span></div>',
  ].join("");
  document.body.appendChild(panel);

  // ── DOM references ─────────────────────────────────────────────────
  var msgsEl = document.getElementById("ecw-msgs");
  var inputEl = document.getElementById("ecw-input");
  var sendEl = document.getElementById("ecw-send");
  var closeEl = document.getElementById("ecw-head-close");

  var isOpen = false;
  var isSending = false;

  // ── Toggle panel ───────────────────────────────────────────────────
  function openPanel() {
    isOpen = true;
    panel.classList.add("open");
    bubble.classList.add("ecw-hidden");
    setTimeout(function () { inputEl.focus(); }, 100);
  }

  function closePanel() {
    isOpen = false;
    panel.classList.remove("open");
    bubble.classList.remove("ecw-hidden");
  }

  bubble.addEventListener("click", openPanel);
  closeEl.addEventListener("click", closePanel);

  // ── Scroll to bottom ──────────────────────────────────────────────
  function scrollBottom() {
    msgsEl.scrollTop = msgsEl.scrollHeight;
  }

  // ── Add message ────────────────────────────────────────────────────
  function addMessage(text, cls) {
    var div = document.createElement("div");
    div.className = "ecw-msg " + cls;
    div.textContent = text;
    // Remove typing indicator if present
    var typing = msgsEl.querySelector(".ecw-msg.typing");
    if (typing) typing.remove();
    msgsEl.appendChild(div);
    scrollBottom();
  }

  function addTypingIndicator() {
    var div = document.createElement("div");
    div.className = "ecw-msg typing";
    div.innerHTML = '<span class="ecw-typing-dot"></span><span class="ecw-typing-dot"></span><span class="ecw-typing-dot"></span>';
    msgsEl.appendChild(div);
    scrollBottom();
  }

  // ── Send message ──────────────────────────────────────────────────
  function sendMessage() {
    var text = inputEl.value.trim();
    if (!text || isSending) return;

    inputEl.value = "";
    isSending = true;
    sendEl.disabled = true;

    addMessage(text, "user");
    addTypingIndicator();

    var sid = getSessionId();

    fetch(API_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sid, message: text }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok && data.reply) {
          addMessage(data.reply, "bot");
        } else if (data.error === "rate_limited") {
          addMessage("You've reached the message limit for now. Feel free to email contractors@empire-ai.co.uk with any questions.", "bot");
        } else {
          addMessage("Thanks for your question! A team member will follow up with more details.", "bot");
        }
      })
      .catch(function () {
        addMessage("Having trouble connecting. Please try again or email contractors@empire-ai.co.uk.", "bot");
      })
      .finally(function () {
        isSending = false;
        sendEl.disabled = false;
        inputEl.focus();
      });
  }

  // ── Event handlers ─────────────────────────────────────────────────
  sendEl.addEventListener("click", sendMessage);
  inputEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  console.log("[empire-ai chat] widget loaded");
})();
