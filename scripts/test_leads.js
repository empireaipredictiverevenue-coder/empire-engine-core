const html = (s) => s.join("");
const noteInputs = {}, l = {id:1, notes:""}, busy = null;
const statusActions = [];
const renderNotes = () => "";
const saveNote = () => {};
// Start of Leads function
function LeadsTest() {
  const [allLeads, setAllLeads] = useState(null);
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState(null);
  const [noteInputs, setNoteInputs] = useState({});
              statusActions.push({ label: 'Contact', status: 'contacted', cls: 'go' });
            } else if (status === 'contacted') {
              statusActions.push({ label: 'Qualify', status: 'qualified', cls: 'go' });
            }
            if (status !== 'closed' && status !== 'rejected') {
              statusActions.push({ label: 'Close', status: 'closed', cls: 'ghost' });
              statusActions.push({ label: 'Reject', status: 'rejected', cls: 'danger' });
            }
            return html`
            <div class="ld-lead" key=${l.id}>
              <div class="ld-lead-row">
                <div>
                  <div class="ld-lead-name">${l.name || '—'}</div>
                  <div class="ld-lead-contact">${l.phone || ''}${l.email ? ' · ' + l.email : ''}</div>
                </div>
                <span class=${'ld-bdg ' + status}>${status}</span>
              </div>
              ${l.city ? html`<div class="ld-lead-meta">${l.city}</div>` : ''}
              <div class="ld-lead-meta">
                <span class="ld-bdg source">${source}</span>
                <span>${created}</span>
              </div>
              ${renderNotes(l.notes, l.id)}
              <div class="ld-notes">
                <input class="ld-notes-in" value=${noteInputs[l.id] !== undefined ? noteInputs[l.id] : (l.notes || '')}
                  onChange=${e => setNoteInputs(n => ({...n, [l.id]: e.target.value}))}
                  onKeyDown=${e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); saveNote(l.id); } }}
                  placeholder=${l.notes ? 'edit note…' : 'add a note…'} />
                ${noteInputs[l.id] !== undefined && noteInputs[l.id].trim() !== (l.notes || '').trim() ? html`
                  <button class="ld-note-save" disabled=${busy === l.id + ':note'}
                    onClick=${() => saveNote(l.id)}>
                    ${busy === l.id + ':note' ? '…' : (l.notes ? 'Update' : 'Save')}
                  </button>
                `}
              </div>
              ${statusActions.length > 0 ? html`
` : ''}
            </div>
          `;
        }))}

}
console.log(LeadsTest.toString());
