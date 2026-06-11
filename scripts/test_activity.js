const html = (s) => s.join("");
const err = null;
const entries = null;
function ActivityLogTest() {
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
}
console.log(ActivityLogTest.toString());
