"""
EMPIRE V49 · B2B DASHBOARD
============================
Public dashboard at /b2b showing all 775 B2B leads with filters,
qualification tiers, enrichment status, and outreach actions.

Wire-up in hub.py:
    from empire_b2b_dashboard import b2b_dashboard_page
    @app.get("/b2b", response_class=HTMLResponse)
    async def b2b_dashboard():
        return HTMLResponse(b2b_dashboard_page())
"""

from empire_tokens import empire_head
from empire_structured_data import webpage_jsonld


def b2b_dashboard_page() -> str:
    """Return the full /b2b dashboard HTML with filterable lead table."""

    extra_css = """
    .b2b-wrap { max-width: 1400px; margin: 0 auto; padding: 32px 28px 80px; position: relative; z-index: 1; }

    /* ── HEADER ─────────────────────────────────────────── */
    .b2b-head { margin-bottom: 28px; }
    .b2b-eyebrow { font-family: var(--font-mono); font-size: 10px; color: var(--signal-teal); letter-spacing: 0.28em; text-transform: uppercase; margin-bottom: 8px; }
    .b2b-title { font-family: var(--font-display); font-weight: 200; font-size: 32px; letter-spacing: -0.03em; color: var(--empire-white); line-height: 1.15; }
    .b2b-title em { font-style: italic; color: var(--signal-teal); font-weight: 500; }
    .b2b-sub { font-family: var(--font-mono); font-size: 10px; color: var(--empire-mist); letter-spacing: 0.12em; margin-top: 6px; }

    /* ── STATS ROW ──────────────────────────────────────── */
    .b2b-stats { display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }
    .b2b-stat { background: var(--empire-surface); border: 1px solid var(--empire-border); padding: 16px 20px; min-width: 140px; flex: 1; }
    .b2b-stat-val { font-family: var(--font-mono); font-size: 28px; font-weight: 500; color: var(--empire-white); line-height: 1; }
    .b2b-stat-val.teal { color: var(--signal-teal); }
    .b2b-stat-val.amber { color: var(--status-amber); }
    .b2b-stat-val.cyan { color: var(--strike-cyan); }
    .b2b-stat-lbl { font-family: var(--font-mono); font-size: 9px; color: var(--empire-fog); letter-spacing: 0.14em; text-transform: uppercase; margin-top: 6px; }

    /* ── FILTER BAR ──────────────────────────────────────── */
    .b2b-filters { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }
    .b2b-filters select, .b2b-filters input {
      background: var(--empire-surface); border: 1px solid var(--empire-border);
      color: var(--empire-silver); font-family: var(--font-mono); font-size: 11px;
      padding: 8px 12px; outline: none; transition: border-color 0.2s;
    }
    .b2b-filters select:focus, .b2b-filters input:focus { border-color: var(--signal-teal); }
    .b2b-filter-btn {
      padding: 8px 16px; font-family: var(--font-mono); font-size: 9px; letter-spacing: 0.1em;
      text-transform: uppercase; border: 1px solid var(--empire-border); background: transparent;
      color: var(--empire-mist); cursor: pointer; transition: all 0.15s;
    }
    .b2b-filter-btn:hover { color: var(--empire-white); border-color: var(--empire-border-hi); }
    .b2b-filter-btn.active { color: var(--signal-teal); border-color: var(--signal-teal-soft); background: var(--signal-teal-soft); }

    /* ── TABLE ───────────────────────────────────────────── */
    .b2b-table-wrap { background: var(--empire-surface); border: 1px solid var(--empire-border); overflow-x: auto; }
    .b2b-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .b2b-table thead th {
      font-family: var(--font-mono); font-size: 9px; color: var(--empire-mist);
      letter-spacing: 0.16em; text-transform: uppercase; text-align: left;
      padding: 12px 14px; border-bottom: 1px solid var(--empire-divider);
      background: var(--empire-elevated); font-weight: 500; cursor: pointer;
      white-space: nowrap; user-select: none;
    }
    .b2b-table thead th:hover { color: var(--empire-white); }
    .b2b-table thead th.sorted { color: var(--signal-teal); }
    .b2b-table tbody td {
      padding: 10px 14px; border-bottom: 1px solid var(--empire-divider);
      color: var(--empire-silver); vertical-align: middle;
    }
    .b2b-table tbody tr:hover { background: rgba(255,255,255,0.015); }
    .b2b-table tbody tr:last-child td { border-bottom: none; }

    /* ── CELL STYLES ─────────────────────────────────────── */
    .b2b-company { font-weight: 500; color: var(--empire-white); font-size: 13px; }
    .b2b-mono { font-family: var(--font-mono); font-size: 10px; }
    .b2b-link { color: var(--strike-cyan); text-decoration: none; }
    .b2b-link:hover { text-decoration: underline; }

    /* ── TIER BADGES ─────────────────────────────────────── */
    .b2b-tier { display: inline-block; padding: 3px 10px; font-family: var(--font-mono); font-size: 8px; letter-spacing: 0.12em; text-transform: uppercase; border-radius: 4px; border: 1px solid; font-weight: 600; }
    .b2b-tier.hot  { color: #FF4444; border-color: rgba(255,68,68,0.3); background: rgba(255,68,68,0.06); }
    .b2b-tier.warm { color: #F59E0B; border-color: rgba(245,158,11,0.3); background: rgba(245,158,11,0.06); }
    .b2b-tier.cold { color: var(--empire-fog); border-color: var(--empire-divider); }

    /* ── ENRICHMENT ───────────────────────────────────────── */
    .b2b-enrich { font-family: var(--font-mono); font-size: 9px; color: var(--empire-fog); }
    .b2b-enrich.yes { color: var(--signal-teal); }

    /* ── ACTIONS ──────────────────────────────────────────── */
    .b2b-actions { display: flex; gap: 6px; }
    .b2b-action-btn {
      padding: 5px 10px; font-family: var(--font-mono); font-size: 8px; letter-spacing: 0.1em;
      text-transform: uppercase; border-radius: 3px; cursor: pointer; transition: all 0.15s;
      font-weight: 600; text-decoration: none; white-space: nowrap;
    }
    .b2b-action-btn.draft { color: var(--signal-teal); border: 1px solid var(--signal-teal-soft); background: transparent; }
    .b2b-action-btn.draft:hover { background: var(--signal-teal); color: #000; }
    .b2b-action-btn.qualify { color: var(--strike-cyan); border: 1px solid rgba(90,200,250,0.2); background: transparent; }
    .b2b-action-btn.qualify:hover { background: rgba(90,200,250,0.1); }
    .b2b-action-btn:disabled { opacity: 0.4; cursor: not-allowed; }

    /* ── PAGINATION ───────────────────────────────────────── */
    .b2b-paginate { display: flex; justify-content: center; gap: 8px; margin-top: 20px; align-items: center; }
    .b2b-page-btn { padding: 8px 14px; font-family: var(--font-mono); font-size: 10px; border: 1px solid var(--empire-border); background: transparent; color: var(--empire-mist); cursor: pointer; transition: all 0.15s; }
    .b2b-page-btn:hover { color: var(--empire-white); border-color: var(--empire-border-hi); }
    .b2b-page-btn.active { color: var(--signal-teal); border-color: var(--signal-teal-soft); }
    .b2b-page-info { font-family: var(--font-mono); font-size: 10px; color: var(--empire-fog); }

    /* ── EMPTY ────────────────────────────────────────────── */
    .b2b-empty { text-align: center; padding: 60px 20px; color: var(--empire-fog); font-style: italic; }

    /* ── LOADING ──────────────────────────────────────────── */
    .b2b-loading { display: flex; align-items: center; justify-content: center; padding: 60px 20px; gap: 12px; }
    .b2b-spinner { width: 18px; height: 18px; border-radius: 50%; border: 2px solid var(--empire-border); border-top-color: var(--signal-teal); animation: spin 0.6s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── RESPONSIVE ───────────────────────────────────────── */
    @media (max-width: 900px) {
      .b2b-wrap { padding: 20px 14px 60px; }
      .b2b-title { font-size: 24px; }
      .b2b-stats { flex-direction: column; }
    }

    /* ── FOOTER ───────────────────────────────────────────── */
    .b2b-foot { margin-top: 48px; padding-top: 20px; border-top: 1px solid var(--empire-divider); text-align: center; font-family: var(--font-mono); font-size: 9px; color: var(--empire-fog); letter-spacing: 0.2em; text-transform: uppercase; }
    .b2b-foot a { color: var(--empire-mist); text-decoration: none; }
    .b2b-foot a:hover { color: var(--signal-teal); }
    """

    head = empire_head(
        title="Empire AI · B2B Lead Dashboard",
        extra=extra_css,
        page="b2b",
        meta_html=webpage_jsonld(
            "Empire AI · B2B Lead Dashboard",
            "Filterable dashboard of 775+ B2B leads across all niches and metros. View qualification scores, enrichment status, and draft outreach.",
            "https://empire-ai.co.uk/b2b",
        ),
    )

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>
<h1 class="sr-only">Empire AI · B2B Lead Dashboard</h1>

<div class="b2b-wrap">
  <div class="b2b-head">
    <div class="b2b-eyebrow">B2B Pipeline</div>
    <h2 class="b2b-title">Lead <em>Dashboard</em></h2>
    <div class="b2b-sub">775+ businesses across 35+ niches · Scored, enriched, and ready for outreach</div>
  </div>

  <!-- ── STATS ────────────────────────────────────────────── -->
  <div class="b2b-stats" id="b2b-stats">
    <div class="b2b-stat"><div class="b2b-stat-val" id="stat-total">—</div><div class="b2b-stat-lbl">Total Leads</div></div>
    <div class="b2b-stat"><div class="b2b-stat-val teal" id="stat-hot">—</div><div class="b2b-stat-lbl">Hot (score ≥ 80)</div></div>
    <div class="b2b-stat"><div class="b2b-stat-val amber" id="stat-warm">—</div><div class="b2b-stat-lbl">Warm (50-79)</div></div>
    <div class="b2b-stat"><div class="b2b-stat-val" id="stat-enriched">—</div><div class="b2b-stat-lbl">Website Enriched</div></div>
    <div class="b2b-stat"><div class="b2b-stat-val cyan" id="stat-drafted">—</div><div class="b2b-stat-lbl">Drafts Created</div></div>
  </div>

  <!-- ── FILTERS ──────────────────────────────────────────── -->
  <div class="b2b-filters">
    <select id="filter-tier" onchange="loadLeads()">
      <option value="">All Tiers</option>
      <option value="hot">🔥 Hot</option>
      <option value="warm">🟡 Warm</option>
      <option value="cold">❄ Cold</option>
    </select>
    <select id="filter-niche" onchange="loadLeads()">
      <option value="">All Niches</option>
    </select>
    <select id="filter-metro" onchange="loadLeads()">
      <option value="">All Metros</option>
    </select>
    <input type="text" id="filter-search" placeholder="Search company..." oninput="debounceSearch()" style="min-width:200px;flex:1;">
    <button class="b2b-filter-btn active" id="btn-tier-hot" onclick="setQuickFilter('hot')">Hot</button>
    <button class="b2b-filter-btn" id="btn-tier-warm" onclick="setQuickFilter('warm')">Warm</button>
    <button class="b2b-filter-btn" id="btn-enriched" onclick="setQuickFilter('enriched')">Enriched</button>
    <button class="b2b-filter-btn" id="btn-all" onclick="clearFilters()">All</button>
  </div>

  <!-- ── TABLE ────────────────────────────────────────────── -->
  <div class="b2b-table-wrap">
    <table class="b2b-table">
      <thead>
        <tr>
          <th onclick="sortTable('company_name')" id="th-company_name">Company ▾</th>
          <th onclick="sortTable('niche')" id="th-niche">Niche ▾</th>
          <th onclick="sortTable('metro')" id="th-metro">Metro ▾</th>
          <th onclick="sortTable('lead_score')" id="th-lead_score">Score ▾</th>
          <th>Tier</th>
          <th>Enrichment</th>
          <th>Contact</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody id="leads-tbody">
        <tr><td colspan="8"><div class="b2b-loading"><div class="b2b-spinner"></div> Loading leads...</div></td></tr>
      </tbody>
    </table>
  </div>

  <!-- ── PAGINATION ───────────────────────────────────────── -->
  <div class="b2b-paginate" id="b2b-pagination"></div>

  <!-- ── FOOTER ───────────────────────────────────────────── -->
  <div class="b2b-foot">
    <a href="/">Empire AI</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/command">Command</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/pricing">Pricing</a>
  </div>
</div>

<script>
// ── STATE ──────────────────────────────────────────────────────────
let allLeads = [];
let currentPage = 1;
const PER_PAGE = 50;
let currentSort = {{field: 'lead_score', dir: 'desc'}};
let searchTimeout = null;

// ── API FETCH ──────────────────────────────────────────────────────
async function loadLeads() {{
  const tier = document.getElementById('filter-tier').value;
  const niche = document.getElementById('filter-niche').value;
  const metro = document.getElementById('filter-metro').value;
  const search = document.getElementById('filter-search').value.trim();

  let url = '/api/b2b/leads?limit=1000';
  if (tier) url += '&tier=' + tier;
  if (niche) url += '&niche=' + encodeURIComponent(niche);
  if (metro) url += '&metro=' + encodeURIComponent(metro);
  if (search) url += '&search=' + encodeURIComponent(search);

  try {{
    const resp = await fetch(url);
    const data = await resp.json();
    if (data.ok) {{
      allLeads = data.leads || [];
      currentPage = 1;

      // Update stats
      document.getElementById('stat-total').textContent = data.total || allLeads.length;
      document.getElementById('stat-hot').textContent = data.hot || 0;
      document.getElementById('stat-warm').textContent = data.warm || 0;
      document.getElementById('stat-enriched').textContent = data.enriched || 0;
      document.getElementById('stat-drafted').textContent = data.drafted || 0;

      // Populate niche filter
      if (data.niches) {{
        const sel = document.getElementById('filter-niche');
        sel.innerHTML = '<option value="">All Niches</option>';
        data.niches.forEach(n => {{ sel.innerHTML += '<option value="' + n + '">' + n + '</option>'; }});
      }}

      // Populate metro filter
      if (data.metros) {{
        const sel = document.getElementById('filter-metro');
        sel.innerHTML = '<option value="">All Metros</option>';
        data.metros.forEach(m => {{ sel.innerHTML += '<option value="' + m + '">' + m + '</option>'; }});
      }}

      renderTable();
    }} else {{
      document.getElementById('leads-tbody').innerHTML = '<tr><td colspan="8"><div class="b2b-empty">Error loading leads: ' + (data.error || 'unknown') + '</div></td></tr>';
    }}
  }} catch(e) {{
    document.getElementById('leads-tbody').innerHTML = '<tr><td colspan="8"><div class="b2b-empty">API error: ' + e.message + '</div></td></tr>';
  }}
}}

// ── SORT ────────────────────────────────────────────────────────────
function sortTable(field) {{
  if (currentSort.field === field) {{
    currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
  }} else {{
    currentSort.field = field;
    currentSort.dir = 'desc';
  }}

  // Update header classes
  document.querySelectorAll('.b2b-table thead th').forEach(th => th.classList.remove('sorted'));
  const th = document.getElementById('th-' + field);
  if (th) th.classList.add('sorted');

  allLeads.sort((a, b) => {{
    let va = a[field] || '', vb = b[field] || '';
    if (field === 'lead_score') {{ va = parseFloat(va) || 0; vb = parseFloat(vb) || 0; }}
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    if (va < vb) return currentSort.dir === 'asc' ? -1 : 1;
    if (va > vb) return currentSort.dir === 'asc' ? 1 : -1;
    return 0;
  }});
  currentPage = 1;
  renderTable();
}}

// ── RENDER ──────────────────────────────────────────────────────────
function renderTable() {{
  const start = (currentPage - 1) * PER_PAGE;
  const page = allLeads.slice(start, start + PER_PAGE);
  const tbody = document.getElementById('leads-tbody');

  if (!page.length) {{
    tbody.innerHTML = '<tr><td colspan="8"><div class="b2b-empty">No leads match your filters.</div></td></tr>';
    document.getElementById('b2b-pagination').innerHTML = '';
    return;
  }}

  tbody.innerHTML = page.map(lead => {{
    const tier = lead._tier || 'cold';
    const tierLabel = tier === 'hot' ? 'HOT' : tier === 'warm' ? 'WARM' : 'COLD';
    const score = lead.lead_score || 0;
    const website = lead.website || '';
    const email = lead.email || '';
    const phone = lead.phone || '';
    const enrichment = lead._enriched ? 'yes' : '';
    const contact = [email ? '✉' : '', phone ? '📞' : ''].filter(Boolean).join(' ');

    return `<tr>
      <td><div class="b2b-company">${{lead.company_name || 'Unknown'}}</div>${{lead.city ? '<div class="b2b-mono" style="color:var(--empire-fog);margin-top:2px;">' + lead.city + ', ' + (lead.state || '') + '</div>' : ''}}</td>
      <td><span class="b2b-mono">${{lead.niche || '—'}}</span></td>
      <td><span class="b2b-mono">${{lead.metro || '—'}}</span></td>
      <td><span class="b2b-mono" style="color:${{score >= 80 ? 'var(--status-red)' : score >= 50 ? 'var(--status-amber)' : 'var(--empire-mist)'}}">${{score}}</span></td>
      <td><span class="b2b-tier ${{tier}}">${{tierLabel}}</span></td>
      <td><span class="b2b-enrich ${{enrichment}}">${{enrichment ? '✓ Enriched' : '—'}}</span></td>
      <td><span class="b2b-mono" style="font-size:11px;">${{contact || '—'}}</span></td>
      <td>
        <div class="b2b-actions">
          <button class="b2b-action-btn draft" onclick="draftLead('${{lead.id}}')" ${{!email && !phone ? 'disabled' : ''}}>✎ Draft</button>
          <button class="b2b-action-btn qualify" onclick="qualifyLead('${{lead.id}}')">⇄ Score</button>
        </div>
      </td>
    </tr>`;
  }}).join('');

  // Pagination
  const totalPages = Math.ceil(allLeads.length / PER_PAGE);
  let pagHtml = '';
  if (totalPages > 1) {{
    pagHtml += '<button class="b2b-page-btn" onclick="goToPage(' + (currentPage - 1) + ')" ' + (currentPage <= 1 ? 'disabled' : '') + '>← Prev</button>';
    for (let i = 1; i <= Math.min(totalPages, 10); i++) {{
      pagHtml += '<button class="b2b-page-btn' + (i === currentPage ? ' active' : '') + '" onclick="goToPage(' + i + ')">' + i + '</button>';
    }}
    if (totalPages > 10) pagHtml += '<span class="b2b-page-info">...' + totalPages + '</span>';
    pagHtml += '<button class="b2b-page-btn" onclick="goToPage(' + (currentPage + 1) + ')" ' + (currentPage >= totalPages ? 'disabled' : '') + '>Next →</button>';
  }}
  document.getElementById('b2b-pagination').innerHTML = pagHtml;
}}

// ── ACTIONS ─────────────────────────────────────────────────────────
function goToPage(n) {{
  if (n < 1 || n > Math.ceil(allLeads.length / PER_PAGE)) return;
  currentPage = n;
  renderTable();
  window.scrollTo(0, 200);
}}

async function draftLead(leadId) {{
  try {{
    const resp = await fetch('/api/b2b/draft', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ lead_id: leadId }}),
    }});
    const data = await resp.json();
    if (data.ok) {{
      alert('Draft created for ' + (data.company || 'lead') + ' (' + (data.drafts || []).length + ' drafts)');
    }} else {{
      alert('Draft failed: ' + (data.error || 'unknown'));
    }}
  }} catch(e) {{
    alert('Error: ' + e.message);
  }}
}}

async function qualifyLead(leadId) {{
  try {{
    const resp = await fetch('/api/b2b/qualify', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ lead_id: leadId }}),
    }});
    const data = await resp.json();
    if (data.ok) {{
      const q = data.qualification || {{}};
      alert('Scored: ' + q.score + ' (' + q.tier + ')');
      loadLeads(); // refresh
    }} else {{
      alert('Qualification failed: ' + (data.error || 'unknown'));
    }}
  }} catch(e) {{
    alert('Error: ' + e.message);
  }}
}}

// ── QUICK FILTERS ───────────────────────────────────────────────────
function setQuickFilter(filter) {{
  document.getElementById('filter-tier').value = '';
  document.getElementById('filter-niche').value = '';
  document.getElementById('filter-search').value = '';

  document.querySelectorAll('.b2b-filter-btn').forEach(b => b.classList.remove('active'));

  if (filter === 'hot') {{
    document.getElementById('filter-tier').value = 'hot';
    document.getElementById('btn-tier-hot').classList.add('active');
  }} else if (filter === 'warm') {{
    document.getElementById('filter-tier').value = 'warm';
    document.getElementById('btn-tier-warm').classList.add('active');
  }} else {{
    document.getElementById('btn-all').classList.add('active');
  }}

  loadLeads();
}}

function clearFilters() {{
  document.getElementById('filter-tier').value = '';
  document.getElementById('filter-niche').value = '';
  document.getElementById('filter-metro').value = '';
  document.getElementById('filter-search').value = '';
  document.querySelectorAll('.b2b-filter-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-all').classList.add('active');
  loadLeads();
}}

function debounceSearch() {{
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(loadLeads, 400);
}}

// ── INIT ────────────────────────────────────────────────────────────
loadLeads();
</script>

</body>
</html>"""
