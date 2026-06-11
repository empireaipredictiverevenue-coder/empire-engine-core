const html = (s) => s.join("");

// The EXACT pattern from the code: return html`...${expr ? html`...`}...`;
function renderLead() {
  const noteInputs = {}, l = {id: 1}, busy = null;
  return html`
    ${noteInputs[l.id] !== undefined && noteInputs[l.id].trim() !== (l.notes || "").trim() ? html`
      <button class="ld-note-save" disabled=${busy === l.id + ":note"}
        onClick=${() => saveNote(l.id)}>
        ${busy === l.id + ":note" ? "..." : (l.notes ? "Update" : "Save")}
      </button>
    `}
  `;
}
console.log(renderLead());
