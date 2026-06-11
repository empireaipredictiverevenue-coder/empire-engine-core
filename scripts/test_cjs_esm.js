const html = (s) => s.join("");

const noteInputs = {},
  l = {id: 1, notes: ""},
  busy = null;

// Build a function containing the exact failing pattern
function renderLead() {
  return html`
              <div class="ld-lead-meta">${l.city ? html`<div class="meta">${l.city}</div>` : ''}</div>
              ${noteInputs[l.id] !== undefined && noteInputs[l.id].trim() !== (l.notes || '').trim() ? html`
                <button class="ld-note-save" disabled=${busy === l.id + ':note'}
                  onClick=${() => saveNote(l.id)}>
                  ${busy === l.id + ':note' ? '…' : (l.notes ? 'Update' : 'Save')}
                </button>
              `}
`;
}
console.log(renderLead());
