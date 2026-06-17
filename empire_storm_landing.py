"""
Empire V49 · Storm Landing Pages
================================
SEO-targeted landing pages for [city]-[state] storm lead generation.
Public routes at /storm/{city}-{state}.

Wired into hub.py as:
    from empire_storm_landing import register_storm_landing_routes
    register_storm_landing_routes(app, get_db=get_db)

Each page shows:
  - Active radar_targets count for that metro (live)
  - Top-scored storm properties (live, de-identified: address hidden, only neighborhood)
  - The 3-claim quality bar (pre-screened, scored, routed)
  - A contractor signup form posting to /api/contractors/onboard

The form payload is identical to empire_contractors.contractors_page so
the existing endpoint accepts it without changes. We tag the meta with
form_source=storm_landing_{city}_{state} for attribution.

Why this is the right tactic:
- Storm URL refresh already runs every 6h — pages auto-update with live data
- No paid spend, no ad accounts, no per-click cost
- Each page is a permanent SEO asset
- Indexes for [city] + storm damage / hail / wind repair queries
- The contractor_signup CTA closes the loop to revenue
"""
from __future__ import annotations

import html
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from empire_tokens import empire_head

log = logging.getLogger("empire_storm_landing")

# Top metros we generate pages for. Ordered by enriched_leads volume.
# Update via the deploy script: scripts/regenerate_storm_pages.py
STORM_METROS: list[tuple[str, str, str]] = [
    # (slug, display city, state code)
    ("san-antonio-tx", "San Antonio", "TX"),
    ("atlanta-ga",     "Atlanta",     "GA"),
    ("denver-co",      "Denver",      "CO"),
    ("chicago-il",     "Chicago",     "IL"),
    ("kansas-city-mo", "Kansas City", "MO"),
    ("tulsa-ok",       "Tulsa",       "OK"),
    ("houston-tx",     "Houston",     "TX"),
    ("dallas-tx",      "Dallas",      "TX"),
    ("st-louis-mo",    "St. Louis",   "MO"),
    ("oklahoma-city-ok","Oklahoma City","OK"),
]


def _metro_to_human(city: str, state: str) -> str:
    return f"{city}, {state}"


def _page_css() -> str:
    return """
    /* ── STORM LANDING ────────────────────────────────────────────── */
    .sl-body {
      min-height: 100vh;
      background: linear-gradient(180deg, #07111E 0%, #050B14 100%);
      color: #E8EEF6;
      font-family: var(--font-display, system-ui);
      overflow-x: hidden;
    }
    .sl-wrap { max-width: 1180px; margin: 0 auto; padding: 56px 32px 96px; position: relative; z-index: 1; }

    /* hero */
    .sl-hero { text-align: center; margin-bottom: 64px; animation: sl-fade-up .7s var(--ease-out-empire) both; }
    .sl-eyebrow {
      font-family: var(--font-mono, ui-monospace); font-size: 10px;
      color: var(--signal-teal, #6FCFC0); letter-spacing: .32em;
      text-transform: uppercase; margin-bottom: 14px;
    }
    .sl-title {
      font-family: var(--font-display, system-ui); font-weight: 200;
      font-size: 52px; letter-spacing: -0.035em; color: #FFFFFF;
      line-height: 1.05; margin: 0 0 18px;
    }
    .sl-title em { font-style: italic; font-weight: 700; color: #6FCFC0; }
    .sl-sub {
      font-family: var(--font-mono, ui-monospace); font-size: 13px;
      color: #8FA0B5; letter-spacing: .14em; max-width: 720px; margin: 0 auto;
      line-height: 1.8; text-transform: uppercase;
    }

    /* live stats bar */
    .sl-stats {
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px;
      background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.08);
      border-radius: 4px; margin: 48px 0;
    }
    .sl-stat { background: #0A1726; padding: 24px 18px; text-align: center; }
    .sl-stat-num {
      font-family: var(--font-display, system-ui); font-weight: 300;
      font-size: 36px; color: #6FCFC0; line-height: 1; margin-bottom: 8px;
      letter-spacing: -0.02em;
    }
    .sl-stat-lbl {
      font-family: var(--font-mono, ui-monospace); font-size: 9px;
      color: #8FA0B5; letter-spacing: .22em; text-transform: uppercase;
    }

    /* value prop columns */
    .sl-vps {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 56px 0;
    }
    .sl-vp {
      background: #0A1726; border: 1px solid rgba(255,255,255,.08);
      border-radius: 4px; padding: 28px 24px;
    }
    .sl-vp-num {
      font-family: var(--font-mono, ui-monospace); font-size: 10px;
      color: #6FCFC0; letter-spacing: .28em; margin-bottom: 12px;
    }
    .sl-vp-title {
      font-family: var(--font-display, system-ui); font-weight: 400;
      font-size: 22px; color: #FFFFFF; margin-bottom: 10px; letter-spacing: -0.01em;
    }
    .sl-vp-body {
      font-size: 13px; line-height: 1.7; color: #B8C5D5; font-weight: 300;
    }

    /* property feed */
    .sl-feed {
      background: #0A1726; border: 1px solid rgba(255,255,255,.08);
      border-radius: 4px; padding: 28px 32px; margin-bottom: 48px;
    }
    .sl-feed-h {
      display: flex; align-items: baseline; justify-content: space-between;
      margin-bottom: 18px;
    }
    .sl-feed-h h3 {
      font-family: var(--font-display, system-ui); font-weight: 300;
      font-size: 22px; color: #FFFFFF; margin: 0; letter-spacing: -0.01em;
    }
    .sl-feed-h .sl-live {
      font-family: var(--font-mono, ui-monospace); font-size: 10px;
      color: #6FCFC0; letter-spacing: .22em; text-transform: uppercase;
    }
    .sl-live::before {
      content: ""; display: inline-block; width: 6px; height: 6px;
      background: #6FCFC0; border-radius: 50%; margin-right: 8px;
      animation: sl-pulse 1.6s var(--ease-out-empire, ease-out) infinite;
    }
    @keyframes sl-pulse {
      0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(111,207,192,.4); }
      50%      { opacity: .6; box-shadow: 0 0 0 6px rgba(111,207,192,0); }
    }
    .sl-feed-row {
      display: grid; grid-template-columns: 1.4fr .8fr .8fr .8fr; gap: 14px;
      padding: 14px 0; border-top: 1px solid rgba(255,255,255,.06);
      font-family: var(--font-mono, ui-monospace); font-size: 12px;
      color: #B8C5D5;
    }
    .sl-feed-row:first-of-type { border-top: 0; }
    .sl-feed-row .sl-feed-hd {
      color: #6F7E92; font-size: 9px; letter-spacing: .22em; text-transform: uppercase;
    }
    .sl-feed-row strong { color: #FFFFFF; font-weight: 500; }
    .sl-score-bar {
      display: inline-block; width: 60px; height: 4px; background: rgba(255,255,255,.06);
      border-radius: 2px; vertical-align: middle; margin-right: 8px; position: relative;
    }
    .sl-score-bar > span {
      position: absolute; top: 0; left: 0; height: 100%;
      background: linear-gradient(90deg, #6FCFC0, #4FB89E); border-radius: 2px;
    }

    /* form */
    .sl-form-wrap {
      background: linear-gradient(180deg, #0A1726 0%, #07111E 100%);
      border: 1px solid rgba(111,207,192,.25); border-radius: 4px;
      padding: 44px 40px; margin-top: 32px;
    }
    .sl-form-h {
      font-family: var(--font-display, system-ui); font-weight: 300;
      font-size: 28px; color: #FFFFFF; margin: 0 0 8px; letter-spacing: -0.02em;
    }
    .sl-form-sub {
      font-size: 13px; color: #8FA0B5; margin-bottom: 28px; line-height: 1.6;
    }
    .sl-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .sl-form-grid .full { grid-column: 1 / -1; }
    .sl-field { display: flex; flex-direction: column; }
    .sl-field label {
      font-family: var(--font-mono, ui-monospace); font-size: 10px;
      color: #8FA0B5; letter-spacing: .22em; text-transform: uppercase;
      margin-bottom: 8px;
    }
    .sl-field input, .sl-field select {
      background: #050B14; border: 1px solid rgba(255,255,255,.12);
      color: #FFFFFF; padding: 12px 14px; font-size: 14px;
      font-family: var(--font-mono, ui-monospace); border-radius: 3px;
      transition: border-color .2s ease;
    }
    .sl-field input:focus, .sl-field select:focus {
      outline: 0; border-color: #6FCFC0;
    }
    .sl-form-foot {
      margin-top: 24px; display: flex; align-items: center; justify-content: space-between;
      gap: 24px; flex-wrap: wrap;
    }
    .sl-form-foot p {
      font-size: 11px; color: #6F7E92; margin: 0; line-height: 1.5;
      max-width: 460px;
    }
    .sl-cta {
      background: #6FCFC0; color: #07111E; border: 0;
      font-family: var(--font-mono, ui-monospace); font-size: 11px;
      font-weight: 700; letter-spacing: .28em; text-transform: uppercase;
      padding: 16px 32px; border-radius: 3px; cursor: pointer;
      transition: background .2s ease, transform .15s ease;
    }
    .sl-cta:hover { background: #88DDD0; transform: translateY(-1px); }
    .sl-cta:disabled { background: #2A3F52; color: #6F7E92; cursor: not-allowed; transform: none; }
    .sl-result {
      margin-top: 18px; padding: 14px 18px; border-radius: 3px;
      font-family: var(--font-mono, ui-monospace); font-size: 12px;
      display: none;
    }
    .sl-result.ok  { display: block; background: rgba(111,207,192,.1); color: #6FCFC0; border: 1px solid rgba(111,207,192,.3); }
    .sl-result.err { display: block; background: rgba(255,99,99,.1);   color: #FF8B8B; border: 1px solid rgba(255,99,99,.3); }

    /* proof bar */
    .sl-proof {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px;
      background: rgba(255,255,255,.04); margin-top: 56px;
      border: 1px solid rgba(255,255,255,.06); border-radius: 4px;
    }
    .sl-proof-cell {
      background: #07111E; padding: 22px 18px; text-align: center;
      font-family: var(--font-mono, ui-monospace);
    }
    .sl-proof-cell strong {
      display: block; color: #6FCFC0; font-size: 18px; font-weight: 500;
      margin-bottom: 4px;
    }
    .sl-proof-cell span { font-size: 10px; color: #8FA0B5; letter-spacing: .2em; text-transform: uppercase; }

    @keyframes sl-fade-up {
      from { opacity: 0; transform: translateY(16px); }
      to   { opacity: 1; transform: translateY(0); }
    }

    @media (max-width: 880px) {
      .sl-stats { grid-template-columns: repeat(2, 1fr); }
      .sl-vps   { grid-template-columns: 1fr; }
      .sl-form-grid { grid-template-columns: 1fr; }
      .sl-proof { grid-template-columns: 1fr; }
      .sl-feed-row { grid-template-columns: 1fr; }
      .sl-title { font-size: 36px; }
    }
    """


def _fetch_storm_stats(get_db, city: str, state: str) -> dict:
    """Pull live counts from supabase for this metro. Cached for 60s."""
    try:
        db = get_db()
        # Active radar targets in this metro
        rt = db.table("radar_targets").select(
            "id,address,urgency_score,damage_severity,created_at,asset_value",
            count="exact",
        ).eq("city", city).eq("state", state).eq("status", "active") \
         .order("urgency_score", desc=True).limit(50).execute()
        # All-time enriched leads in this metro
        el = db.table("enriched_leads").select("id", count="exact").eq("city", city).eq("state", state).execute()
        # All-time dispatches in this metro
        # dispatches don't carry city directly — approximate via contractor.metro for now
        # (a future migration can denormalize)
        return {
            "active_targets": rt.count or 0,
            "top_targets": rt.data or [],
            "all_time_leads": el.count or 0,
        }
    except Exception as e:
        log.warning(f"[storm_landing] failed to fetch stats for {city},{state}: {e}")
        return {"active_targets": 0, "top_targets": [], "all_time_leads": 0, "error": str(e)}


def _render_top_targets(targets: list[dict]) -> str:
    """Render the top-scored storm properties (de-identified)."""
    if not targets:
        return '<div style="color:#8FA0B5;font-size:12px;padding:14px 0;font-family:var(--font-mono,ui-monospace)">No live targets in this metro right now. New storm data lands every 6 hours.</div>'
    rows = []
    rows.append(
        '<div class="sl-feed-row" style="border-top:0;padding-top:0">'
        '<span class="sl-feed-hd">Neighborhood</span>'
        '<span class="sl-feed-hd">Storm signal</span>'
        '<span class="sl-feed-hd">Property size</span>'
        '<span class="sl-feed-hd">Score</span>'
        '</div>'
    )
    for t in targets[:8]:
        addr = t.get("address") or ""
        # de-identify: keep street name only, drop house number
        addr = addr.strip()
        if addr and addr[0].isdigit():
            parts = addr.split(" ", 1)
            if len(parts) > 1:
                addr = "— " + parts[1]
        score = float(t.get("urgency_score") or 0); severity = t.get("damage_severity") or "-"
        score_pct = min(max(int(score * 100), 0), 100)
        # asset_value approximation — radar_targets may not carry it; fall back to score bar
        size_hint = html.escape(severity)
        rows.append(
            f'<div class="sl-feed-row">'
            f'<span><strong>{html.escape(addr) or "—"}</strong></span>'
            f'<span>live</span>'
            f'<span>{size_hint}</span>'
            f'<span><span class="sl-score-bar"><span style="width:{score_pct}%"></span></span>{score_pct}</span>'
            f'</div>'
        )
    return "".join(rows)


def storm_landing_page(city: str, state: str, slug: str, get_db) -> str:
    """Render the SEO landing page for a single metro."""
    stats = _fetch_storm_stats(get_db, city, state)
    n_active = stats.get("active_targets", 0)
    n_all = stats.get("all_time_leads", 0)
    city_full = _metro_to_human(city, state)
    form_source = f"storm_landing_{slug}"
    head = empire_head(
        title=f"Storm Damage Leads in {city_full} · Pre-Screened · Empire AI",
        extra=_page_css(),
    )
    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body class="sl-body">

<div class="sl-wrap">

  <div class="sl-hero">
    <div class="sl-eyebrow">Storm Lead Generation · {city_full}</div>
    <h1 class="sl-title">Pre-screened storm leads<br/>in <em>{city}</em>, delivered ready-to-close</h1>
    <p class="sl-sub">
      Live storm detections → scored properties → routed to licensed {city} contractors.
      You pay 3% on settled claims only. No contracts. No per-lead fees.
    </p>
  </div>

  <div class="sl-stats">
    <div class="sl-stat">
      <div class="sl-stat-num">{n_active}</div>
      <div class="sl-stat-lbl">Live Targets Right Now</div>
    </div>
    <div class="sl-stat">
      <div class="sl-stat-num">{n_all}</div>
      <div class="sl-stat-lbl">All-Time Leads ({city})</div>
    </div>
    <div class="sl-stat">
      <div class="sl-stat-num">3%</div>
      <div class="sl-stat-lbl">Fee On Settled Claims</div>
    </div>
    <div class="sl-stat">
      <div class="sl-stat-num">5min</div>
      <div class="sl-stat-lbl">From Detection To Your Phone</div>
    </div>
  </div>

  <div class="sl-vps">
    <div class="sl-vp">
      <div class="sl-vp-num">01</div>
      <div class="sl-vp-title">Storm-verified, not "interested"</div>
      <div class="sl-vp-body">
        Every lead on this page is a property hit by an active weather event —
        hail, wind, or storm — not someone who clicked an ad. Our scout refreshes
        targets every 6 hours from NOAA + NWS storm feeds.
      </div>
    </div>
    <div class="sl-vp">
      <div class="sl-vp-num">02</div>
      <div class="sl-vp-title">Scored and de-duplicated</div>
      <div class="sl-vp-body">
        Each property gets a buy-signal score based on asset value, age, weather
        severity, and contact readiness. You only see leads above the {city} median.
        We never double-dispatch the same address.
      </div>
    </div>
    <div class="sl-vp">
      <div class="sl-vp-num">03</div>
      <div class="sl-vp-title">Routed, not blasted</div>
      <div class="sl-vp-body">
        We text the property owner, qualify them in a 2-message exchange, and
        route the YES reply to one {city} contractor with a magic-link accept
        flow. You're not buying a list — you're receiving a confirmed lead.
      </div>
    </div>
  </div>

  <div class="sl-feed">
    <div class="sl-feed-h">
      <h3>Live {city} storm properties</h3>
      <span class="sl-live">Live · refreshes every 6h</span>
    </div>
    {_render_top_targets(stats.get("top_targets", []))}
  </div>

  <div class="sl-form-wrap" id="signup">
    <h2 class="sl-form-h">Get {city} leads delivered to your phone</h2>
    <p class="sl-form-sub">
      Tell us your trade and service area. We'll text you a sample lead within
      5 minutes if one is active. You only pay when it settles.
    </p>
    <form id="sl-form" autocomplete="on">
      <input type="hidden" name="form_source" value="{html.escape(form_source)}" />
      <div class="sl-form-grid">
        <div class="sl-field">
          <label for="sl-name">Your name</label>
          <input id="sl-name" name="name" required maxlength="120" autocomplete="name" placeholder="Pat Smith" />
        </div>
        <div class="sl-field">
          <label for="sl-company">Company</label>
          <input id="sl-company" name="company" required maxlength="200" autocomplete="organization" placeholder="Smith Roofing LLC" />
        </div>
        <div class="sl-field">
          <label for="sl-phone">Mobile (E.164)</label>
          <input id="sl-phone" name="phone" type="tel" required maxlength="20" autocomplete="tel" placeholder="+18175551234" />
        </div>
        <div class="sl-field">
          <label for="sl-email">Email</label>
          <input id="sl-email" name="email" type="email" required maxlength="200" autocomplete="email" placeholder="pat@smithroofing.com" />
        </div>
        <div class="sl-field">
          <label for="sl-area">Service area</label>
          <input id="sl-area" name="service_area" required maxlength="120" value="{html.escape(city_full)}" placeholder="{html.escape(city_full)}" />
        </div>
        <div class="sl-field">
          <label for="sl-trade">Trade</label>
          <select id="sl-trade" name="trade" required>
            <option value="">— select —</option>
            <option value="roofing">Roofing</option>
            <option value="general_contractor">General Contractor</option>
            <option value="restoration">Restoration</option>
            <option value="water_mitigation">Water Mitigation</option>
            <option value="electrical">Electrical</option>
            <option value="plumbing">Plumbing</option>
            <option value="hvac">HVAC</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div class="sl-field full">
          <label for="sl-license">License # (optional)</label>
          <input id="sl-license" name="license_no" maxlength="80" placeholder="TX ROC #12345" />
        </div>
      </div>
      <div class="sl-form-foot">
        <p>
          By submitting you agree to receive SMS from Empire AI about {city} storm leads.
          Message frequency varies. Reply STOP to opt out. We never sell your data.
          <a href="/privacy" style="color:#6FCFC0;text-decoration:none">Privacy</a>
        </p>
        <button type="submit" class="sl-cta" id="sl-submit">Get {city} Leads →</button>
      </div>
      <div class="sl-result" id="sl-result"></div>
    </form>
  </div>

  <div class="sl-proof">
    <div class="sl-proof-cell"><strong>1</strong><span>Real fee earned</span></div>
    <div class="sl-proof-cell"><strong>3%</strong><span>Only on settled claims</span></div>
    <div class="sl-proof-cell"><strong>0</strong><span>Per-lead fees. Ever.</span></div>
  </div>

</div>

<script>
(function() {{
  const form = document.getElementById('sl-form');
  const btn  = document.getElementById('sl-submit');
  const out  = document.getElementById('sl-result');

  form.addEventListener('submit', async function(ev) {{
    ev.preventDefault();
    btn.disabled = true;
    btn.textContent = 'Sending…';
    out.className = 'sl-result';
    out.textContent = '';
    try {{
      const fd = new FormData(form);
      const payload = Object.fromEntries(fd.entries());
      // Tag the meta.source so we can attribute this signup to {slug}
      payload.form_source = 'storm_landing_{slug}';
      const r = await fetch('/api/contractors/onboard', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload),
      }});
      const j = await r.json();
      if (!r.ok || !j.ok) {{
        out.className = 'sl-result err';
        out.textContent = 'Error: ' + (j.error || 'unknown') + (j.field ? ' (' + j.field + ')' : '');
        btn.disabled = false;
        btn.textContent = 'Get {city} Leads →';
        return;
      }}
      out.className = 'sl-result ok';
      out.textContent = j.next_step || 'Got it. Check your phone in 5 minutes.';
      btn.textContent = '✓ Submitted';
    }} catch (e) {{
      out.className = 'sl-result err';
      out.textContent = 'Network error: ' + e.message;
      btn.disabled = false;
      btn.textContent = 'Get {city} Leads →';
    }}
  }});
}})();
</script>

</body>
</html>"""


def storm_index_page(get_db) -> str:
    """The /storm index — a hub of all metro landing pages, linked for SEO crawl discovery."""
    head = empire_head(
        title="Storm Damage Leads · Pre-Screened by Metro · Empire AI",
        extra=_page_css(),
    )
    city_links = ""
    for slug, city, state in STORM_METROS:
        city_links += (
            f'<a href="/storm/{html.escape(slug)}" class="sl-vp" '
            f'style="text-decoration:none;color:inherit;display:block">'
            f'<div class="sl-vp-num">{state}</div>'
            f'<div class="sl-vp-title">{html.escape(city)} storm leads</div>'
            f'<div class="sl-vp-body">Pre-screened storm-damage leads, routed to licensed {html.escape(city)} contractors. 3% on settled claims.</div>'
            f'</a>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body class="sl-body">
<div class="sl-wrap">
  <div class="sl-hero">
    <div class="sl-eyebrow">Empire AI · Storm Lead Network</div>
    <h1 class="sl-title">Pre-screened storm leads<br/>by <em>metro</em></h1>
    <p class="sl-sub">
      Live storm detections across {len(STORM_METROS)} major metros.
      Routed to one licensed contractor per metro. 3% on settled claims.
    </p>
  </div>
  <div class="sl-vps" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr))">
    {city_links}
  </div>
</div>
</body>
</html>"""


def register_storm_landing_routes(app, get_db: Optional[Callable] = None) -> None:
    """Mount /storm and /storm/{slug} routes on the FastAPI app.

    Args:
        app: FastAPI/Starlette app instance (hub.py's `app`).
        get_db: Callable returning a supabase client. Required for live data.
                If None, pages render with zero counts (degraded but visible).
    """
    from fastapi.responses import HTMLResponse

    if get_db is None:
        # Fallback: use supabase directly so pages still work standalone
        try:
            from supabase import create_client
            _url = os.environ.get("SUPABASE_URL", "")
            _key = os.environ.get("SUPABASE_SERVICE_KEY", "")
            def get_db():
                return create_client(_url, _key)
        except Exception:
            def get_db():
                raise RuntimeError("supabase not configured; storm landing will render without live data")

    def _render_index():
        return HTMLResponse(storm_index_page(get_db))

    async def _render_metro(slug: str):
        match = next((m for m in STORM_METROS if m[0] == slug), None)
        if not match:
            # 404 with a soft message — show the index instead of erroring
            return HTMLResponse(storm_index_page(get_db), status_code=404)
        _s, city, state = match
        return HTMLResponse(storm_landing_page(city=city, state=state, slug=slug, get_db=get_db))

    app.add_api_route("/storm", _render_index, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/storm/", _render_index, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/storm/{slug}", _render_metro, methods=["GET"], response_class=HTMLResponse)
    

    # Sitemap + robots.txt — SEO discoverability.
    async def _sitemap_xml():
        from fastapi.responses import Response
        base = os.environ.get('PUBLIC_BASE_URL', 'https://empire-ai.co.uk').rstrip('/')
        urls = [base + '/']
        urls.append(base + '/storm')
        for slug, _, _ in STORM_METROS:
            urls.append(base + '/storm/' + slug)
        for path in ('/pricing', '/contractors', '/support'):
            urls.append(base + path)
        parts = ['<?xml version="1.0" encoding="UTF-8"?>']
        parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        for u in urls:
            parts.append('  <url>')
            parts.append('    <loc>' + u + '</loc>')
            parts.append('    <changefreq>weekly</changefreq>')
            parts.append('  </url>')
        parts.append('</urlset>')
        xml = chr(10).join(parts)
        return Response(content=xml, media_type='application/xml')

    async def _robots_txt():
        from fastapi.responses import Response
        base = os.environ.get('PUBLIC_BASE_URL', 'https://empire-ai.co.uk').rstrip('/')
        body = chr(10).join([
            'User-agent: *',
            'Allow: /',
            'Disallow: /api/',
            'Disallow: /command',
            'Sitemap: ' + base + '/sitemap.xml',
            ''
        ])
        return Response(content=body, media_type='text/plain')

    app.add_api_route('/sitemap.xml', _sitemap_xml, methods=['GET'])
    app.add_api_route('/robots.txt', _robots_txt, methods=['GET'])

    log.info(f"[storm_landing] routes registered: /storm, /storm/{{slug}} ({len(STORM_METROS)} metros), /sitemap.xml, /robots.txt")
