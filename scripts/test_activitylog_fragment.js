const React = { createElement: h => h, useState: (s) => [null, ()=>{}], useEffect: (f) => {}, useCallback: (f) => f };
const htm = { bind: () => (s) => s.join("") };
const html = htm.bind();
const createRoot = () => ({ render: () => {} });
const apiFetch = async () => ({});
                  onChange=${e => setNoteInputs(n => ({...n, [l.id]: e.target.value}))}
                  onKeyDown=${e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); saveNote(l.id); } }}
                  placeholder=${l.notes ? 'edit note…' : 'add a note…'} />
                ${noteInputs[l.id] !== undefined && noteInputs[l.id].trim() !== (l.notes || '').trim() ? html`
                  <button class="ld-note-save" disabled=${busy === l.id + ':note'}
                    onClick=${() => saveNote(l.id)}>
                    ${busy === l.id + ':note' ? '…' : (l.notes ? 'Update' : 'Save')}
                  </button>
                ` : ''}
              </div>
              ${statusActions.length > 0 ? html`` : ''}
            </div>
          `;
        }))}

// ── ACTIVITY LOG ──────────────────────────────────
function ActivityLog() {  const [entries, setEntries] = useState(null);
  const [err, setErr] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  const reload = useCallback(async () => {
    try {
      const r = await apiFetch('/api/v1/notes/activity').then(x => x.json());
      setEntries(r.entries || []);
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, []);

  useEffect(() => {
    reload();
    const t = setInterval(reload, 15000);
    return () => clearInterval(t);
  }, [reload]);

  if (err) return html`<div class=\"stub\"><div class=\"stub-title\">Could not load Activity Log</div><div class=\"stub-body\">${err}</div></div>`;

  if (!entries) return html`<div class=\"stub\"><div class=\"stub-body\">Loading activity log…</div></div>`;

  // Filter by text or operator name
  let filteredEntries = entries;
  if (searchQuery.trim()) {
    const q = searchQuery.trim().toLowerCase();
    filteredEntries = entries.filter(e =>
      (e.text || '').toLowerCase().includes(q) ||
      (e.operator || '').toLowerCase().includes(q)
    );
  }

  // Group by date
  const groups = {};
  for (const e of filteredEntries) {
    const date = (e.timestamp || '').slice(0, 10);
    if (!groups[date]) groups[date] = [];
    groups[date].push(e);
  }
  const dates = Object.keys(groups).sort().reverse();

  const goToLead = (leadId) => {
