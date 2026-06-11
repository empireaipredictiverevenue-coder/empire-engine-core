const html = (s) => s.join("");

function ActivityLog() {
  const err = "test";
  if (err) return html`<div class=\"stub\"><div class=\"stub-title\">Could not load Activity Log</div><div class=\"stub-body\">${err}</div></div>`;
  const entries = null;
  if (!entries) return html`<div class=\"stub\"><div class=\"stub-body\">Loading activity log…</div></div>`;
}

console.log("OK");
