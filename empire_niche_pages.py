"""Empire AI · Niche Landing Pages + Map View

Per-niche SEO landing pages with live stats:
  /for-roofing
  /for-hvac
  /for-restoration
  /for-solar
  /for-electrical
  /for-plumbing
  /for-general_contractor

Plus the killer product: /map — a real Mapbox map of all contractors +
storm targets. Filter by niche, metro, urgency.

Wired into hub.py as:
    from empire_niche_pages import register_niche_routes
    register_niche_routes(app, get_db=get_db)
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

try:
    from dotenv import load_dotenv
    from pathlib import Path
    _r = Path(__file__).resolve().parent
    load_dotenv(_r.parent / ".env")
except Exception:
    pass

from supabase import create_client

log = logging.getLogger("empire_niche_pages")


# ── NICHE DEFINITIONS ─────────────────────────────────────────────────────
NICHES = [
    {
        "slug": "roofing",
        "title": "Roofing Leads",
        "sub": "Storm-verified roofing jobs in your service area. Pay 3% on settled claims only.",
        "hero_emoji": "🏠",
        "keywords": ["roofing", "roof", "roofer", "hail", "storm damage roof", "shingle"],
        "tier_a": ["hail", "wind", "storm", "missing shingles", "leak"],
        "tier_b": ["repair", "replace", "insurance claim", "adjuster"],
    },
    {
        "slug": "hvac",
        "title": "HVAC Leads",
        "sub": "Heating & cooling emergencies after storms. Routed by ZIP, ready-to-close.",
        "hero_emoji": "❄️",
        "keywords": ["hvac", "heating", "cooling", "ac", "furnace", "air conditioning", "heat pump"],
        "tier_a": ["no ac", "no heat", "emergency", "broken"],
        "tier_b": ["install", "replace", "service", "tune-up"],
    },
    {
        "slug": "restoration",
        "title": "Restoration Leads",
        "sub": "Water/fire/mold mitigation. Insurance-claim-driven, high-ticket jobs.",
        "hero_emoji": "💧",
        "keywords": ["restoration", "water damage", "fire damage", "mold", "mitigation"],
        "tier_a": ["flood", "burst pipe", "fire", "mold"],
        "tier_b": ["remediation", "drying", "rebuild"],
    },
    {
        "slug": "solar",
        "title": "Solar Leads",
        "sub": "Pre-screened homeowners considering solar. 1 commission per install, $0 lead cost.",
        "hero_emoji": "☀️",
        "keywords": ["solar", "panel", "pv", "inverter", "battery"],
        "tier_a": ["quote", "comparison", "incentive"],
        "tier_b": ["install", "financing"],
    },
    {
        "slug": "electrical",
        "title": "Electrical Leads",
        "sub": "Storm-damaged electrical systems, panel upgrades, generator installs.",
        "hero_emoji": "⚡",
        "keywords": ["electrician", "electrical", "panel", "wiring", "generator"],
        "tier_a": ["outage", "sparking", "panel damage", "code violation"],
        "tier_b": ["upgrade", "install", "rewire"],
    },
    {
        "slug": "plumbing",
        "title": "Plumbing Leads",
        "sub": "Burst pipes, water damage, emergency plumbing after storms.",
        "hero_emoji": "🔧",
        "keywords": ["plumber", "plumbing", "pipe", "drain", "water heater"],
        "tier_a": ["burst", "leak", "flood", "no water"],
        "tier_b": ["repair", "replace", "install"],
    },
    {
        "slug": "general_contractor",
        "title": "General Contractor Leads",
        "sub": "Full-service GC jobs from storm damage. Higher contract value, longer cycles.",
        "hero_emoji": "🏗️",
        "keywords": ["general contractor", "gc", "remodel", "renovation", "build"],
        "tier_a": ["storm rebuild", "major repair", "full remodel"],
        "tier_b": ["addition", "renovation"],
    },
]

NICHE_BY_SLUG = {n["slug"]: n for n in NICHES}


# ── LIVE STATS PER NICHE ──────────────────────────────────────────────────
def _niche_stats(sb, slug: str) -> dict:
    """Use the niche column directly for O(1) filter (no Python keyword scan)."""
    niche = NICHE_BY_SLUG.get(slug)
    if not niche:
        return {}
    # Contractors with this niche (active only) — cap to keep page fast
    r = sb.table("contractors").select("metro").eq("active", True).eq("niche", slug).limit(800).execute()
    metros: Counter = Counter()
    for c in (r.data or []):
        metros[c.get("metro") or "?"] += 1
    contractor_count = sum(metros.values())

    # Leads: just grab the most recent 50 in last 7d, no order (faster).
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    r2 = sb.table("enriched_leads").select("id,address,city,state,score,phone,created_at").gte("created_at", cutoff).limit(50).execute()
    leads = r2.data or []
    return {
        "slug": slug,
        "contractors_active": contractor_count,
        "top_metros": metros.most_common(8),
        "leads_7d": len(leads),
        "leads_top": leads[:5],
    }


# ── HTML RENDERER ─────────────────────────────────────────────────────────
def _niche_page_html(niche: dict, stats: dict) -> str:
    title = f"{niche['title']} · Empire AI"
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{title}</title>
<meta name="description" content="{html.escape(niche['sub'])}" />
<style>
  :root {{ --bg:#07111E; --card:#0A1726; --border:rgba(255,255,255,.08); --text:#E8EEF6; --muted:#8FA0B5; --teal:#6FCFC0; --green:#88DDD0; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:linear-gradient(180deg,#07111E 0%,#050B14 100%); color:var(--text); font-family: system-ui, -apple-system, sans-serif; }}
  .wrap {{ max-width: 1100px; margin: 0 auto; padding: 56px 32px 96px; }}
  .hero {{ text-align: center; margin-bottom: 56px; }}
  .emoji {{ font-size: 56px; margin-bottom: 14px; }}
  .eyebrow {{ font-family: ui-monospace, monospace; font-size: 10px; color: var(--teal); letter-spacing: .32em; text-transform: uppercase; margin-bottom: 12px; }}
  h1 {{ font-size: 48px; font-weight: 200; letter-spacing: -.035em; color: #fff; margin: 0 0 16px; line-height: 1.05; }}
  h1 em {{ font-style: italic; color: var(--teal); font-weight: 700; }}
  .sub {{ font-size: 16px; color: var(--muted); max-width: 700px; margin: 0 auto; line-height: 1.7; }}
  .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: 4px; margin: 48px 0; }}
  .stat {{ background: var(--card); padding: 26px 20px; text-align: center; }}
  .stat-n {{ font-size: 38px; font-weight: 300; color: var(--teal); letter-spacing: -.02em; }}
  .stat-l {{ font-family: ui-monospace, monospace; font-size: 9px; color: var(--muted); letter-spacing: .22em; text-transform: uppercase; margin-top: 8px; }}
  .vps {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 48px 0; }}
  .vp {{ background: var(--card); border: 1px solid var(--border); border-radius: 4px; padding: 28px 24px; }}
  .vp-n {{ font-family: ui-monospace, monospace; font-size: 10px; color: var(--teal); letter-spacing: .28em; margin-bottom: 10px; }}
  .vp-t {{ font-size: 20px; font-weight: 400; color: #fff; margin-bottom: 8px; }}
  .vp-b {{ font-size: 13px; line-height: 1.7; color: #B8C5D5; font-weight: 300; }}
  .leads {{ background: var(--card); border: 1px solid var(--border); border-radius: 4px; padding: 28px 32px; margin: 32px 0; }}
  .leads h3 {{ font-size: 22px; font-weight: 300; color: #fff; margin: 0 0 18px; }}
  .leads-row {{ display: grid; grid-template-columns: 1.4fr 1fr 1fr 0.6fr; gap: 14px; padding: 10px 0; border-top: 1px solid var(--border); font-family: ui-monospace, monospace; font-size: 12px; color: #B8C5D5; }}
  .leads-row:first-of-type {{ border-top: 0; font-size: 9px; letter-spacing: .22em; text-transform: uppercase; color: var(--muted); padding: 0 0 8px; }}
  .leads-row strong {{ color: #fff; font-weight: 500; }}
  .score-bar {{ display:inline-block; width:60px; height:4px; background:rgba(255,255,255,.06); border-radius:2px; vertical-align:middle; margin-right:6px; position:relative; }}
  .score-bar > span {{ position:absolute; top:0; left:0; height:100%; background:linear-gradient(90deg,var(--teal),var(--green)); border-radius:2px; }}
  .form {{ background: linear-gradient(180deg, var(--card) 0%, #07111E 100%); border: 1px solid rgba(111,207,192,.25); border-radius: 4px; padding: 44px 40px; margin-top: 32px; }}
  .form h2 {{ font-size: 28px; font-weight: 300; color: #fff; margin: 0 0 8px; letter-spacing: -.02em; }}
  .form-sub {{ font-size: 13px; color: var(--muted); margin-bottom: 24px; line-height: 1.6; }}
  .form-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
  .form-grid .full {{ grid-column: 1 / -1; }}
  .field label {{ font-family: ui-monospace, monospace; font-size: 9px; color: var(--muted); letter-spacing: .22em; text-transform: uppercase; margin-bottom: 6px; display: block; }}
  .field input, .field select {{ width: 100%; background: #050B14; border: 1px solid rgba(255,255,255,.12); color: #fff; padding: 12px 14px; font-size: 14px; font-family: ui-monospace, monospace; border-radius: 3px; }}
  .field input:focus, .field select:focus {{ outline: 0; border-color: var(--teal); }}
  .cta {{ background: var(--teal); color: #07111E; border: 0; font-family: ui-monospace, monospace; font-size: 11px; font-weight: 700; letter-spacing: .28em; text-transform: uppercase; padding: 16px 32px; border-radius: 3px; cursor: pointer; margin-top: 18px; }}
  .cta:hover {{ background: var(--green); }}
  .cta:disabled {{ background: #2A3F52; color: var(--muted); cursor: not-allowed; }}
  .result {{ margin-top: 16px; padding: 12px; border-radius: 3px; font-family: ui-monospace, monospace; font-size: 12px; display: none; }}
  .result.ok {{ display: block; background: rgba(111,207,192,.1); color: var(--teal); border: 1px solid rgba(111,207,192,.3); }}
  .result.err {{ display: block; background: rgba(255,99,99,.1); color: #FF8B8B; border: 1px solid rgba(255,99,99,.3); }}
  .metros {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }}
  .metro-chip {{ background: rgba(111,207,192,.1); color: var(--teal); padding: 4px 10px; border-radius: 99px; font-family: ui-monospace, monospace; font-size: 11px; }}
  @media (max-width: 880px) {{ .stats, .vps, .form-grid {{ grid-template-columns: 1fr; }} h1 {{ font-size: 32px; }} }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div class="emoji">{niche['hero_emoji']}</div>
    <div class="eyebrow">{niche['slug'].replace('_',' ').upper()} · LIVE NETWORK</div>
    <h1>{html.escape(niche['title']).split(' ')[0]} <em>leads</em>, ready to close</h1>
    <p class="sub">{html.escape(niche['sub'])}</p>
  </div>

  <div class="stats">
    <div class="stat"><div class="stat-n">{stats.get('contractors_active', 0):,}</div><div class="stat-l">Active {niche['title']} Pros</div></div>
    <div class="stat"><div class="stat-n">{stats.get('leads_7d', 0):,}</div><div class="stat-l">{niche['title']} Leads (7d)</div></div>
    <div class="stat"><div class="stat-n">3%</div><div class="stat-l">On Settled Claims</div></div>
  </div>

  <div class="vps">
    <div class="vp"><div class="vp-n">01</div><div class="vp-t">Storm-verified, not "interested"</div><div class="vp-b">Every lead is a property hit by an active weather event — not someone who clicked an ad. Our scout refreshes targets every 6 hours from NOAA + NWS.</div></div>
    <div class="vp"><div class="vp-n">02</div><div class="vp-t">Scored &amp; de-duplicated</div><div class="vp-b">Each property gets a buy-signal score based on asset value, age, weather severity. You only see leads above your metro median. No double-dispatch.</div></div>
    <div class="vp"><div class="vp-n">03</div><div class="vp-t">Routed, not blasted</div><div class="vp-b">We text the property owner, qualify them, and route the YES reply to one {niche['slug'].replace('_',' ')} pro with a magic-link accept flow. You're receiving a confirmed lead, not buying a list.</div></div>
  </div>

  <div class="leads">
    <h3>Top {niche['title']} leads right now</h3>
    <div class="leads-row"><span>Address</span><span>City</span><span>Phone</span><span>Score</span></div>
    {"".join(f'<div class="leads-row"><span><strong>{html.escape(l.get("address","—") or "—")}</strong></span><span>{html.escape(l.get("city","—") or "—")}</span><span>{(l.get("phone","") or "—")[-10:]}</span><span><span class="score-bar"><span style="width:{int((l.get("score") or 0)*100)}%"></span></span>{(l.get("score") or 0):.2f}</span></div>' for l in stats.get("leads_top", [])) or '<div class="leads-row"><span colspan="4" style="color:var(--muted)">No active leads — submit your service area to be first when they land.</span></div>'}
    <div style="margin-top: 14px;">
      <div style="font-family:ui-monospace,monospace;font-size:9px;color:var(--muted);letter-spacing:.22em;text-transform:uppercase;margin-bottom:6px;">Top metros</div>
      <div class="metros">{"".join(f'<span class="metro-chip">{html.escape(m or "?")} · {n}</span>' for m,n in stats.get("top_metros",[])) or '<span style="color:var(--muted);font-size:12px">no metros yet</span>'}</div>
    </div>
  </div>

  <div class="form" id="form">
    <h2>Get {niche['title']} delivered to your phone</h2>
    <p class="form-sub">Tell us your service area. We'll text you a sample lead within 5 minutes if one is active. You only pay when it settles.</p>
    <form id="np-form" autocomplete="on">
      <input type="hidden" name="form_source" value="niche_page_{niche['slug']}" />
      <div class="form-grid">
        <div class="field"><label>Your name</label><input name="name" required maxlength="120" placeholder="Pat Smith" /></div>
        <div class="field"><label>Company</label><input name="company" required maxlength="200" placeholder="Smith {niche['slug'].replace('_',' ').title()} LLC" /></div>
        <div class="field"><label>Mobile (E.164)</label><input name="phone" type="tel" required maxlength="20" placeholder="+18175551234" /></div>
        <div class="field"><label>Email</label><input name="email" type="email" maxlength="200" placeholder="pat@example.com" /></div>
        <div class="field"><label>Service area</label><input name="service_area" required value="" placeholder="Dallas, TX" /></div>
        <div class="field"><label>Trade</label>
          <select name="trade" required>
            <option value="">— select —</option>
            {"".join(f'<option value="{n["slug"]}" {"selected" if n["slug"]==niche["slug"] else ""}>{n["title"]}</option>' for n in NICHES)}
          </select>
        </div>
        <div class="field full"><label>License # (optional)</label><input name="license_no" maxlength="80" placeholder="TX ROC #12345" /></div>
      </div>
      <button type="submit" class="cta" id="np-submit">Get {niche['title']} →</button>
      <div class="result" id="np-result"></div>
    </form>
  </div>
</div>

<script>
(function() {{
  const f = document.getElementById('np-form');
  const b = document.getElementById('np-submit');
  const o = document.getElementById('np-result');
  f.addEventListener('submit', async function(ev) {{
    ev.preventDefault();
    b.disabled = true; b.textContent = 'Sending…';
    o.className = 'result'; o.textContent = '';
    try {{
      const fd = new FormData(f);
      const p = Object.fromEntries(fd.entries());
      p.form_source = 'niche_page_{niche['slug']}';
      const r = await fetch('/api/contractors/onboard', {{
        method: 'POST', headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(p)
      }});
      const j = await r.json();
      if (!r.ok || !j.ok) {{
        o.className = 'result err';
        o.textContent = 'Error: ' + (j.error || 'unknown');
        b.disabled = false; b.textContent = 'Get {niche['title']} →';
        return;
      }}
      o.className = 'result ok';
      o.textContent = j.next_step || 'Got it. Check your phone in 5 minutes.';
      b.textContent = '✓ Submitted';
    }} catch(e) {{
      o.className = 'result err';
      o.textContent = 'Network error: ' + e.message;
      b.disabled = false; b.textContent = 'Get {niche['title']} →';
    }}
  }});
}})();
</script>
</body>
</html>'''


# ── MAP VIEW ───────────────────────────────────────────────────────────────
def _map_view_html() -> str:
    return '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Empire AI · Coverage Map</title>
<script src="https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js"></script>
<link href="https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css" rel="stylesheet" />
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; font-family: system-ui, -apple-system, sans-serif; background: #07111E; color: #E8EEF6; }
  #map { position: absolute; top: 0; left: 0; right: 0; bottom: 0; }
  .panel { position: absolute; top: 16px; left: 16px; z-index: 10; background: rgba(10, 23, 38, .92); border: 1px solid rgba(255,255,255,.08); border-radius: 4px; padding: 16px 20px; min-width: 280px; backdrop-filter: blur(8px); }
  .panel h1 { font-size: 18px; font-weight: 300; color: #fff; margin: 0 0 4px; }
  .panel h1 span { color: #6FCFC0; }
  .panel .sub { font-family: ui-monospace, monospace; font-size: 9px; color: #8FA0B5; letter-spacing: .22em; text-transform: uppercase; }
  .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px 16px; margin-top: 14px; }
  .stat .n { font-size: 24px; font-weight: 300; color: #6FCFC0; letter-spacing: -.02em; }
  .stat .l { font-family: ui-monospace, monospace; font-size: 9px; color: #8FA0B5; letter-spacing: .22em; text-transform: uppercase; }
  .filters { margin-top: 14px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.06); }
  .filter-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
  .chip { background: rgba(255,255,255,.05); color: #B8C5D5; padding: 4px 10px; border-radius: 99px; font-family: ui-monospace, monospace; font-size: 10px; cursor: pointer; border: 1px solid transparent; user-select: none; }
  .chip.on { background: rgba(111,207,192,.2); color: #6FCFC0; border-color: rgba(111,207,192,.4); }
  .legend { position: absolute; bottom: 16px; left: 16px; z-index: 10; background: rgba(10,23,38,.92); border: 1px solid rgba(255,255,255,.08); border-radius: 4px; padding: 10px 14px; font-family: ui-monospace, monospace; font-size: 10px; color: #B8C5D5; backdrop-filter: blur(8px); }
  .legend .row { display: flex; align-items: center; gap: 8px; margin: 3px 0; }
  .legend .dot { width: 10px; height: 10px; border-radius: 50%; }
  .legend .dot.c { background: #6FCFC0; }
  .legend .dot.l { background: #FFD580; }
  .legend .dot.s { background: #FF8B8B; }
  .pop { font-family: ui-monospace, monospace; font-size: 11px; color: #fff; padding: 4px 8px; }
  .pop .name { font-weight: 700; color: #6FCFC0; }
  .pop .small { color: #8FA0B5; font-size: 10px; }
  .mapboxgl-popup-content { background: rgba(10,23,38,.95); border: 1px solid rgba(111,207,192,.4); border-radius: 4px; padding: 8px 12px; }
  .mapboxgl-popup-tip { border-top-color: rgba(10,23,38,.95) !important; }
  .spinner { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #6FCFC0; font-family: ui-monospace, monospace; font-size: 11px; letter-spacing: .22em; z-index: 5; }
</style>
</head>
<body>
<div id="map"></div>
<div class="spinner" id="spinner">LOADING COVERAGE…</div>
<div class="panel">
  <h1>Empire <span>Coverage</span></h1>
  <div class="sub">live · empire-ai.co.uk</div>
  <div class="stats">
    <div class="stat"><div class="n" id="s-cont">—</div><div class="l">Contractors</div></div>
    <div class="stat"><div class="n" id="s-lead">—</div><div class="l">Active Leads</div></div>
    <div class="stat"><div class="n" id="s-storm">—</div><div class="l">Storm Targets</div></div>
    <div class="stat"><div class="n" id="s-metro">—</div><div class="l">Metros</div></div>
  </div>
  <div class="filters">
    <div class="sub">Filter</div>
    <div class="filter-row" id="f-niche"></div>
  </div>
</div>
<div class="legend">
  <div class="row"><div class="dot c"></div>Active Contractor</div>
  <div class="row"><div class="dot l"></div>Hot Lead (pending_outreach)</div>
  <div class="row"><div class="dot s"></div>Urgent Storm Target (urgency ≥ 7)</div>
</div>

<script>
const ACTIVE_NICHE = "all";
async function loadGeo() {
  const [cont, lead, storm] = await Promise.all([
    fetch("/api/v1/map/contractors").then(r => r.json()),
    fetch("/api/v1/map/leads").then(r => r.json()),
    fetch("/api/v1/map/storm-targets").then(r => r.json()),
  ]);
  return { cont, lead, storm };
}

async function init() {
  mapboxgl.accessToken = "__MAPBOX_TOKEN__";
  const map = new mapboxgl.Map({
    container: "map",
    style: "mapbox://styles/mapbox/dark-v11",
    center: [-95.4, 30.0],
    zoom: 4,
  });
  map.addControl(new mapboxgl.NavigationControl(), "top-right");
  map.on("load", async () => {
    const { cont, lead, storm } = await loadGeo();
    document.getElementById("spinner").style.display = "none";

    // Stats
    document.getElementById("s-cont").textContent = (cont.features||[]).length.toLocaleString();
    document.getElementById("s-lead").textContent = (lead.features||[]).length.toLocaleString();
    document.getElementById("s-storm").textContent = (storm.features||[]).length.toLocaleString();
    const metros = new Set();
    [...(cont.features||[]), ...(lead.features||[]), ...(storm.features||[])].forEach(f => {
      const m = f.properties && (f.properties.metro || f.properties.city);
      if (m) metros.add(m);
    });
    document.getElementById("s-metro").textContent = metros.size;

    // Filter chips
    const niches = new Set();
    [...(cont.features||[]), ...(lead.features||[]), ...(storm.features||[])].forEach(f => {
      const n = f.properties && f.properties.niche;
      if (n) niches.add(n);
    });
    const chips = document.getElementById("f-niche");
    const allChip = document.createElement("span");
    allChip.className = "chip on"; allChip.textContent = "all";
    allChip.onclick = () => filterLayer("all");
    chips.appendChild(allChip);
    [...niches].sort().forEach(n => {
      const c = document.createElement("span");
      c.className = "chip"; c.textContent = n;
      c.onclick = () => filterLayer(n);
      chips.appendChild(c);
    });

    map.addSource("contractors", { type: "geojson", data: cont });
    map.addSource("leads",      { type: "geojson", data: lead });
    map.addSource("storms",     { type: "geojson", data: storm });

    map.addLayer({ id: "contractors", type: "circle", source: "contractors",
      paint: { "circle-radius": 3, "circle-color": "#6FCFC0", "circle-opacity": 0.7, "circle-stroke-color": "#fff", "circle-stroke-width": 0.5, "circle-stroke-opacity": 0.3 }
    });
    map.addLayer({ id: "leads", type: "circle", source: "leads",
      paint: { "circle-radius": 4, "circle-color": "#FFD580", "circle-opacity": 0.85 }
    });
    map.addLayer({ id: "storms", type: "circle", source: "storms",
      paint: { "circle-radius": ["interpolate", ["linear"], ["get", "urgency_score"], 1, 4, 5, 8, 10, 14], "circle-color": "#FF8B8B", "circle-opacity": 0.9 }
    });

    function pop(f) {
      return new mapboxgl.Popup({ offset: 8 }).setHTML(
        '<div class="pop">' +
          '<div class="name">' + (f.properties.name||"") + '</div>' +
          (f.properties.city ? '<div>' + f.properties.city + (f.properties.state?', '+f.properties.state:'') + '</div>' : '') +
          (f.properties.phone ? '<div class="small">' + f.properties.phone + '</div>' : '') +
          (f.properties.score ? '<div class="small">score: ' + f.properties.score.toFixed(2) + '</div>' : '') +
          (f.properties.urgency_score ? '<div class="small">urgency: ' + f.properties.urgency_score + '/10</div>' : '') +
        '</div>'
      );
    }
    ["contractors","leads","storms"].forEach(layer => {
      map.on("click", layer, e => { e.features[0].coordinates && pop(e.features[0]).setLngLat(e.features[0].geometry.coordinates).addTo(map); });
      map.on("mouseenter", layer, () => map.getCanvas().style.cursor = "pointer");
      map.on("mouseleave", layer, () => map.getCanvas().style.cursor = "");
    });

    window._map = map;
  });
}
function filterLayer(niche) {
  document.querySelectorAll(".chip").forEach(c => c.classList.toggle("on", c.textContent === niche));
  ["contractors","leads","storms"].forEach(layer => {
    if (niche === "all") {
      window._map.setFilter(layer, null);
    } else {
      window._map.setFilter(layer, ["==", ["get","niche"], niche]);
    }
  });
}
init();
</script>
</body>
</html>'''


# ── MAP DATA ENDPOINTS ────────────────────────────────────────────────────
def _contractors_geojson(sb) -> dict:
    """Active contractors as GeoJSON. We have metro strings, not lat/lng.
    Use Mapbox geocoding cache (process-wide dict) for batch performance.
    Falls back to a US-centroid if not found."""
    if not hasattr(_contractors_geojson, "_cache"):
        _contractors_geojson._cache = {}
    cache = _contractors_geojson._cache

    r = sb.table("contractors").select("id,name,phone,metro,niche,trade").eq("active", True).limit(8000).execute()
    contractors = r.data or []

    # Metro centroids (rough — used for placement; replace with real geocoding later)
    METRO_CENTROIDS = {
        "Dallas-Fort Worth": (-96.797, 32.776), "Dallas": (-96.797, 32.776),
        "Houston": (-95.358, 29.760), "Austin": (-97.743, 30.267),
        "San Antonio": (-98.493, 29.424), "Oklahoma City": (-97.516, 35.467),
        "Tulsa": (-95.992, 36.154), "Wichita": (-97.330, 37.688),
        "Kansas City": (-94.578, 39.099), "St. Louis": (-90.199, 38.627),
        "Tampa": (-82.458, 27.951), "Miami": (-80.192, 25.762),
        "Orlando": (-81.379, 28.538), "New York City": (-74.006, 40.713),
        "Memphis": (-90.049, 35.149), "Denver": (-104.990, 39.739),
        "Chicago": (-87.629, 41.878), "Phoenix": (-112.074, 33.448),
        "Los Angeles": (-118.244, 34.052), "Atlanta": (-84.388, 33.749),
    }
    features = []
    skipped = 0
    for c in contractors:
        metro = c.get("metro") or ""
        coords = cache.get(metro) or METRO_CENTROIDS.get(metro)
        if not coords:
            skipped += 1
            continue
        cache.setdefault(metro, coords)
        # tiny jitter so all points in the same metro don't overlap exactly
        import random
        jitter = lambda: random.uniform(-0.06, 0.06)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [coords[0] + jitter(), coords[1] + jitter()]},
            "properties": {
                "name": c.get("name") or "Contractor",
                "phone": c.get("phone"),
                "metro": metro,
                "niche": c.get("niche") or c.get("trade") or "?",
                "kind": "contractor",
            }
        })
    return {"type": "FeatureCollection", "features": features, "skipped_no_metro": skipped}


def _leads_geojson(sb) -> dict:
    """Pending outreach leads as GeoJSON. Uses city → metro centroid."""
    if not hasattr(_leads_geojson, "_cache"):
        _leads_geojson._cache = {}
    cache = _leads_geojson._cache
    METRO_CENTROIDS = _contractors_geojson.__dict__.get("_METRO_CENTROIDS") or {
        "Dallas": (-96.797, 32.776), "Houston": (-95.358, 29.760), "Austin": (-97.743, 30.267),
        "San Antonio": (-98.493, 29.424), "Oklahoma City": (-97.516, 35.467),
        "Tulsa": (-95.992, 36.154), "Wichita": (-97.330, 37.688), "Kansas City": (-94.578, 39.099),
        "St. Louis": (-90.199, 38.627), "Tampa": (-82.458, 27.951), "Miami": (-80.192, 25.762),
        "Orlando": (-81.379, 28.538), "New York City": (-74.006, 40.713), "Memphis": (-90.049, 35.149),
        "Denver": (-104.990, 39.739), "Chicago": (-87.629, 41.878), "Phoenix": (-112.074, 33.448),
        "Los Angeles": (-118.244, 34.052), "Atlanta": (-84.388, 33.749), "Dallas-Fort Worth": (-96.797, 32.776),
    }
    r = sb.table("enriched_leads").select("id,phone,city,state,score,niche,address").eq("status", "pending_outreach").limit(2000).execute()
    features = []
    for l in (r.data or []):
        city = l.get("city") or ""
        coords = cache.get(city) or METRO_CENTROIDS.get(city)
        if not coords:
            continue
        cache.setdefault(city, coords)
        import random
        jitter = lambda: random.uniform(-0.04, 0.04)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [coords[0] + jitter(), coords[1] + jitter()]},
            "properties": {
                "name": l.get("address") or "Lead",
                "phone": l.get("phone"),
                "city": city,
                "state": l.get("state"),
                "score": l.get("score") or 0,
                "niche": l.get("niche") or "?",
                "kind": "lead",
            }
        })
    return {"type": "FeatureCollection", "features": features}


def _storm_targets_geojson(sb) -> dict:
    """Active urgent storm targets as GeoJSON."""
    METRO_CENTROIDS = {
        "Dallas": (-96.797, 32.776), "Houston": (-95.358, 29.760), "Austin": (-97.743, 30.267),
        "San Antonio": (-98.493, 29.424), "Oklahoma City": (-97.516, 35.467),
        "Tulsa": (-95.992, 36.154), "Wichita": (-97.330, 37.688), "Kansas City": (-94.578, 39.099),
        "St. Louis": (-90.199, 38.627), "Tampa": (-82.458, 27.951), "Miami": (-80.192, 25.762),
        "Orlando": (-81.379, 28.538), "Memphis": (-90.049, 35.149), "Denver": (-104.990, 39.739),
        "Chicago": (-87.629, 41.878), "Atlanta": (-84.388, 33.749), "Dallas-Fort Worth": (-96.797, 32.776),
    }
    r = sb.table("radar_targets").select("id,address,city,state,urgency_score,niche,sub_niche").eq("status", "active").gte("urgency_score", 7).limit(2000).execute()
    features = []
    for t in (r.data or []):
        city = t.get("city") or ""
        coords = METRO_CENTROIDS.get(city)
        if not coords:
            continue
        import random
        jitter = lambda: random.uniform(-0.05, 0.05)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [coords[0] + jitter(), coords[1] + jitter()]},
            "properties": {
                "name": t.get("address") or "Storm target",
                "city": city,
                "state": t.get("state"),
                "urgency_score": t.get("urgency_score") or 0,
                "niche": t.get("niche") or t.get("sub_niche") or "?",
                "kind": "storm",
            }
        })
    return {"type": "FeatureCollection", "features": features}


# ── ROUTE REGISTRATION ─────────────────────────────────────────────────────
def register_niche_routes(app, get_db: Optional[Callable] = None):
    from fastapi.responses import HTMLResponse, JSONResponse

    if get_db is None:
        def get_db():
            return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # Niche pages — one route per niche, slug baked in
    from fastapi import HTTPException
    def _make_niche_handler(slug: str):
        async def _handler():
            niche = NICHE_BY_SLUG.get(slug)
            if not niche:
                raise HTTPException(status_code=404, detail="niche not found")
            stats = _niche_stats(get_db(), slug)
            return HTMLResponse(_niche_page_html(niche, stats))
        return _handler

    for n in NICHES:
        app.add_api_route(f"/for-{n['slug']}", _make_niche_handler(n['slug']), methods=["GET"])

    # Map view
    mapbox_token = os.getenv("MAPBOX_TOKEN", "")
    async def _map_view():
        return HTMLResponse(_map_view_html().replace("__MAPBOX_TOKEN__", mapbox_token))

    app.add_api_route("/map", _map_view, methods=["GET"])

    # Map data endpoints
    async def _map_contractors():
        return JSONResponse(_contractors_geojson(get_db()))
    async def _map_leads():
        return JSONResponse(_leads_geojson(get_db()))
    async def _map_storms():
        return JSONResponse(_storm_targets_geojson(get_db()))

    app.add_api_route("/api/v1/map/contractors", _map_contractors, methods=["GET"])
    app.add_api_route("/api/v1/map/leads", _map_leads, methods=["GET"])
    app.add_api_route("/api/v1/map/storm-targets", _map_storms, methods=["GET"])

    log.info(f"niche pages registered: {len(NICHES)} niches + /map + 3 map data endpoints")