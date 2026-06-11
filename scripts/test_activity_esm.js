const html = (s) => s.join("");

// This is the exact pattern from the error
function test(err) {
  if (err) return html`<div class="stub"><div class="stub-title">Could not load Activity Log</div><div class="stub-body">${err}</div></div>`;
}
