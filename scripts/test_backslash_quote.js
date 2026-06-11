const html = (s) => s.join("");

// Test with the EXACT backslash-quote pattern from the actual code
function test(err) {
  if (err) return html`<div class=\"stub\"><div class=\"stub-title\">Could not load Activity Log</div><div class=\"stub-body\">${err}</div></div>`;
}
