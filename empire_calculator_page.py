"""
EMPIRE V49 · CONTRACTOR ROI CALCULATOR PAGE
============================================
Interactive HTML page at /calculator/roi with real-time sliders for
leads/month, CPL, close rate, and avg job value — shows ROI, profit,
and breakeven instantly. No API calls — all client-side math.

Wire-up in hub.py:
    from empire_calculator_page import calculator_roi_page

    @app.get("/calculator/roi", response_class=HTMLResponse)
    async def calculator_roi():
        return HTMLResponse(calculator_roi_page())
"""

from empire_tokens import empire_head


def calculator_roi_page() -> str:
    extra_css = """
    .cr-wrap {
      max-width: 960px;
      margin: 0 auto;
      padding: 48px 32px 80px;
    }

    /* ── HEADER ─────────────────────────────────────────────────── */
    .cr-header {
      text-align: center;
      margin-bottom: 48px;
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .cr-eyebrow {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.32em;
      text-transform: uppercase;
      margin-bottom: 12px;
    }
    .cr-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 44px;
      letter-spacing: -0.04em;
      color: var(--empire-white);
      line-height: 1.1;
      margin-bottom: 16px;
    }
    .cr-title em {
      font-style: italic;
      font-weight: 700;
      color: var(--signal-teal);
    }
    .cr-sub {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      max-width: 520px;
      margin: 0 auto;
      line-height: 1.7;
    }

    /* ── SLIDERS (2x2 grid) ─────────────────────────────────────── */
    .cr-sliders {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 32px;
      margin-bottom: 40px;
    }
    .cr-slider-group {
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .cr-slider-group:nth-child(1) { animation-delay: 0.05s; }
    .cr-slider-group:nth-child(2) { animation-delay: 0.10s; }
    .cr-slider-group:nth-child(3) { animation-delay: 0.15s; }
    .cr-slider-group:nth-child(4) { animation-delay: 0.20s; }

    .cr-slider-label {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 8px;
    }
    .cr-slider-label-name {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      font-weight: 600;
    }
    .cr-slider-label-value {
      font-family: var(--font-mono);
      font-size: 18px;
      font-weight: 600;
      color: var(--signal-teal);
      font-feature-settings: 'tnum' 1;
      transition: color 0.2s;
    }
    .cr-slider-label-value.positive { color: var(--signal-teal); }
    .cr-slider-label-value.neutral  { color: var(--strike-cyan); }
    .cr-slider-label-value.negative { color: var(--status-red); }

    .cr-slider-track {
      position: relative;
      height: 6px;
      background: rgba(10, 26, 47, 0.8);
      border-radius: 3px;
      cursor: pointer;
    }
    .cr-slider-fill {
      position: absolute;
      top: 0; left: 0;
      height: 100%;
      background: linear-gradient(90deg, var(--signal-teal), var(--strike-cyan));
      border-radius: 3px;
      pointer-events: none;
      transition: width 0.05s linear;
    }
    .cr-slider-track input[type="range"] {
      -webkit-appearance: none;
      appearance: none;
      position: absolute;
      top: -7px; left: 0;
      width: 100%; height: 20px;
      background: transparent;
      cursor: pointer;
      margin: 0;
      z-index: 2;
    }
    .cr-slider-track input[type="range"]::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: 20px; height: 20px;
      border-radius: 50%;
      background: var(--empire-surface);
      border: 2px solid var(--signal-teal);
      box-shadow: 0 0 12px var(--signal-teal-glow), 0 2px 8px rgba(0,0,0,0.4);
      cursor: pointer;
      transition: all 0.15s var(--ease-snap);
    }
    .cr-slider-track input[type="range"]::-webkit-slider-thumb:hover {
      transform: scale(1.15);
      border-color: var(--strike-cyan);
    }
    .cr-slider-track input[type="range"]::-moz-range-thumb {
      width: 20px; height: 20px;
      border-radius: 50%;
      background: var(--empire-surface);
      border: 2px solid var(--signal-teal);
      box-shadow: 0 0 12px var(--signal-teal-glow);
      cursor: pointer;
    }
    .cr-slider-hint {
      margin-top: 6px;
      font-family: var(--font-mono);
      font-size: 8px;
      color: var(--empire-fog);
      letter-spacing: 0.12em;
    }

    /* ── KPI GRID ───────────────────────────────────────────────── */
    .cr-kpis {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 36px;
    }
    .cr-kpi {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 20px;
      text-align: center;
      position: relative;
      overflow: hidden;
      transition: all 0.25s var(--ease-out-empire);
      animation: empire-fade-up 0.4s var(--ease-out-empire) both;
    }
    .cr-kpi:nth-child(1) { animation-delay: 0.10s; }
    .cr-kpi:nth-child(2) { animation-delay: 0.15s; }
    .cr-kpi:nth-child(3) { animation-delay: 0.20s; }
    .cr-kpi:nth-child(4) { animation-delay: 0.25s; }
    .cr-kpi:hover {
      border-color: var(--empire-border);
      transform: translateY(-2px);
    }
    .cr-kpi::before {
      content: '';
      position: absolute; top: 0; left: 0;
      width: 2px; height: 100%;
      background: var(--accent, var(--signal-teal));
    }
    .cr-kpi:nth-child(1) { --accent: var(--status-amber); }
    .cr-kpi:nth-child(2) { --accent: var(--strike-cyan); }
    .cr-kpi:nth-child(3) { --accent: var(--signal-teal); }
    .cr-kpi:nth-child(4) { --accent: var(--signal-teal); }

    .cr-kpi-label {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 8px;
      font-weight: 600;
    }
    .cr-kpi-value {
      font-family: var(--font-mono);
      font-weight: 600;
      font-size: 28px;
      line-height: 1;
      color: var(--empire-white);
      font-feature-settings: 'tnum' 1;
      transition: color 0.3s;
    }
    .cr-kpi-value.positive { color: var(--signal-teal); }
    .cr-kpi-value.negative { color: var(--status-red); }
    .cr-kpi-value.neutral  { color: var(--strike-cyan); }
    .cr-kpi-sub {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      margin-top: 6px;
    }

    /* ── ROI METER ──────────────────────────────────────────────── */
    .cr-meter-section {
      margin-bottom: 36px;
    }
    .cr-meter-label {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      font-weight: 600;
      margin-bottom: 14px;
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .cr-meter-label .cr-big-roi {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 44px;
      letter-spacing: -0.04em;
      transition: color 0.3s;
    }
    .cr-meter-label .cr-big-roi.positive { color: var(--signal-teal); }
    .cr-meter-label .cr-big-roi.negative { color: var(--status-red); }
    .cr-meter-bar {
      position: relative;
      height: 12px;
      background: rgba(10, 26, 47, 0.8);
      border-radius: 6px;
      overflow: hidden;
      margin-bottom: 8px;
    }
    .cr-meter-fill {
      height: 100%;
      border-radius: 6px;
      transition: width 0.25s var(--ease-out-empire), background 0.3s;
      min-width: 2px;
    }
    .cr-meter-fill.positive {
      background: linear-gradient(90deg, var(--signal-teal), var(--strike-cyan));
      box-shadow: 0 0 16px var(--signal-teal-glow);
    }
    .cr-meter-fill.negative {
      background: linear-gradient(90deg, var(--status-red), var(--status-amber));
      box-shadow: 0 0 16px rgba(255, 71, 87, 0.4);
    }
    .cr-meter-labels {
      display: flex;
      justify-content: space-between;
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.08em;
    }
    .cr-meter-tick {
      position: absolute;
      top: 0;
      width: 2px;
      height: 100%;
      background: rgba(122, 140, 163, 0.15);
      pointer-events: none;
    }

    /* ── BREAKEVEN STATS ROW ────────────────────────────────────── */
    .cr-breakeven {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 40px;
    }
    .cr-be-card {
      background: var(--empire-elevated);
      border: 1px solid var(--empire-divider);
      padding: 16px;
      text-align: center;
      animation: empire-fade-up 0.4s var(--ease-out-empire) both;
    }
    .cr-be-card:nth-child(1) { animation-delay: 0.20s; }
    .cr-be-card:nth-child(2) { animation-delay: 0.25s; }
    .cr-be-card:nth-child(3) { animation-delay: 0.30s; }
    .cr-be-card:nth-child(4) { animation-delay: 0.35s; }

    .cr-be-label {
      font-family: var(--font-mono);
      font-size: 8px;
      color: var(--empire-fog);
      letter-spacing: 0.16em;
      text-transform: uppercase;
      margin-bottom: 5px;
    }
    .cr-be-value {
      font-family: var(--font-mono);
      font-weight: 600;
      font-size: 16px;
      color: var(--empire-white);
      font-feature-settings: 'tnum' 1;
    }
    .cr-be-value.positive { color: var(--signal-teal); }
    .cr-be-value.negative { color: var(--status-red); }

    /* ── MONTHLY PROJECTIONS TABLE ──────────────────────────────── */
    .cr-proj-section {
      margin-bottom: 40px;
    }
    .cr-proj-header {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      font-weight: 600;
      margin-bottom: 14px;
    }
    .cr-table-wrap {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      overflow: hidden;
    }
    .cr-proj-table {
      width: 100%;
      border-collapse: collapse;
    }
    .cr-proj-table thead th {
      font-family: var(--font-mono);
      font-size: 8px;
      color: var(--empire-mist);
      letter-spacing: 0.16em;
      text-transform: uppercase;
      text-align: left;
      padding: 12px 16px;
      border-bottom: 1px solid var(--empire-divider);
      background: rgba(0,0,0,0.2);
      font-weight: 600;
    }
    .cr-proj-table thead th:last-child { text-align: right; }
    .cr-proj-table tbody td {
      padding: 11px 16px;
      border-bottom: 1px solid var(--empire-divider);
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-silver);
      font-feature-settings: 'tnum' 1;
    }
    .cr-proj-table tbody td:last-child { text-align: right; }
    .cr-proj-table tbody tr:last-child td { border-bottom: none; }
    .cr-proj-table tbody tr:hover { background: rgba(68, 229, 184, 0.03); }
    .cr-proj-table .profit-row td { color: var(--signal-teal); }
    .cr-proj-table .loss-row td { color: var(--status-red); }
    .cr-proj-table .total-row td {
      font-weight: 700;
      color: var(--empire-white);
      border-top: 2px solid var(--signal-teal-soft);
    }

    /* ── SCENARIO COMPARISON ────────────────────────────────────── */
    .cr-scenario-section {
      margin-bottom: 36px;
    }
    .cr-scenario-inner {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
    }
    .cr-scenario {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 20px;
      text-align: center;
      transition: all 0.25s var(--ease-snap);
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .cr-scenario:nth-child(1) { animation-delay: 0.10s; }
    .cr-scenario:nth-child(2) { animation-delay: 0.15s; }
    .cr-scenario:nth-child(3) { animation-delay: 0.20s; }
    .cr-scenario:hover {
      border-color: var(--signal-teal-soft);
      transform: translateY(-2px);
    }
    .cr-scenario-tier {
      font-family: var(--font-mono);
      font-size: 8px;
      color: var(--empire-fog);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 6px;
    }
    .cr-scenario-name {
      font-weight: 600;
      font-size: 15px;
      color: var(--empire-white);
      margin-bottom: 10px;
    }
    .cr-scenario-desc {
      font-size: 11px;
      color: var(--empire-mist);
      line-height: 1.5;
      margin-bottom: 12px;
    }
    .cr-scenario-roi {
      font-family: var(--font-mono);
      font-size: 22px;
      font-weight: 200;
      color: var(--signal-teal);
      margin-bottom: 4px;
    }
    .cr-scenario-profit {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--empire-mist);
    }
    .cr-scenario-btn {
      margin-top: 12px;
      display: inline-block;
      padding: 6px 14px;
      font-family: var(--font-mono);
      font-size: 8px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      background: var(--signal-teal-soft);
      color: var(--signal-teal);
      border: 1px solid rgba(68, 229, 184, 0.25);
      cursor: pointer;
      transition: all 0.2s;
      border-radius: var(--radius-xs);
    }
    .cr-scenario-btn:hover {
      background: var(--signal-teal);
      color: #0A1A2F;
    }

    /* ── FOOTER ─────────────────────────────────────────────────── */
    .cr-foot {
      margin-top: 60px;
      padding-top: 24px;
      border-top: 1px solid var(--empire-divider);
      text-align: center;
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.24em;
      text-transform: uppercase;
    }
    .cr-foot a { color: var(--empire-mist); text-decoration: none; }
    .cr-foot a:hover { color: var(--signal-teal); }

    /* ── RESPONSIVE ─────────────────────────────────────────────── */
    @media (max-width: 800px) {
      .cr-sliders { grid-template-columns: 1fr; gap: 20px; }
      .cr-kpis { grid-template-columns: repeat(2, 1fr); }
      .cr-breakeven { grid-template-columns: repeat(2, 1fr); }
      .cr-scenario-inner { grid-template-columns: 1fr; }
      .cr-title { font-size: 32px; }
      .cr-wrap { padding: 32px 20px 60px; }
      .cr-meter-label { flex-direction: column; align-items: flex-start; gap: 4px; }
      .cr-meter-label .cr-big-roi { font-size: 32px; }
    }
    @media (max-width: 480px) {
      .cr-kpis { grid-template-columns: 1fr; }
      .cr-breakeven { grid-template-columns: 1fr; }
    }
    """

    head = empire_head(
        title="Contractor ROI Calculator · Empire AI",
        extra=extra_css,
        page="",
        description="Estimate your ROI as a restoration contractor with Empire AI. Adjust leads per month, CPL, close rate, and job value to see real-time profit projections and breakeven analysis.",
        keywords="contractor ROI calculator, lead generation ROI, restoration contractor profit, Empire AI calculator",
        canonical="https://empire-ai.co.uk/calculator/roi",
    )

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="cr-wrap">

  <!-- ── HEADER ────────────────────────────────────────────────── -->
  <div class="cr-header">
    <div class="cr-eyebrow">Interactive Estimator</div>
    <h1 class="cr-title">Contractor <em>ROI Calculator</em></h1>
    <p class="cr-sub">
      Adjust the sliders below to see your estimated monthly returns,
      breakeven point, and annual projections — all calculated in real time.
    </p>
  </div>

  <!-- ── SLIDERS ───────────────────────────────────────────────── -->
  <div class="cr-sliders">

    <div class="cr-slider-group">
      <div class="cr-slider-label">
        <span class="cr-slider-label-name">Leads / Month</span>
        <span class="cr-slider-label-value" id="cr-val-leads">100</span>
      </div>
      <div class="cr-slider-track">
        <div class="cr-slider-fill" id="cr-fill-leads" style="width:18%"></div>
        <input type="range" id="cr-slider-leads" min="10" max="500" value="100" step="5"
               oninput="calc()">
      </div>
      <div class="cr-slider-hint">10 – 500 leads</div>
    </div>

    <div class="cr-slider-group">
      <div class="cr-slider-label">
        <span class="cr-slider-label-name">Cost Per Lead (CPL)</span>
        <span class="cr-slider-label-value" id="cr-val-cpl">$50</span>
      </div>
      <div class="cr-slider-track">
        <div class="cr-slider-fill" id="cr-fill-cpl" style="width:23%"></div>
        <input type="range" id="cr-slider-cpl" min="5" max="200" value="50" step="1"
               oninput="calc()">
      </div>
      <div class="cr-slider-hint">$5 – $200 per lead</div>
    </div>

    <div class="cr-slider-group">
      <div class="cr-slider-label">
        <span class="cr-slider-label-name">Close Rate</span>
        <span class="cr-slider-label-value" id="cr-val-close">10%</span>
      </div>
      <div class="cr-slider-track">
        <div class="cr-slider-fill" id="cr-fill-close" style="width:23%"></div>
        <input type="range" id="cr-slider-close" min="1" max="40" value="10" step="1"
               oninput="calc()">
      </div>
      <div class="cr-slider-hint">1% – 40%</div>
    </div>

    <div class="cr-slider-group">
      <div class="cr-slider-label">
        <span class="cr-slider-label-name">Avg Job Value</span>
        <span class="cr-slider-label-value" id="cr-val-job">$10,000</span>
      </div>
      <div class="cr-slider-track">
        <div class="cr-slider-fill" id="cr-fill-job" style="width:18%"></div>
        <input type="range" id="cr-slider-job" min="1000" max="50000" value="10000" step="500"
               oninput="calc()">
      </div>
      <div class="cr-slider-hint">$1,000 – $50,000</div>
    </div>

  </div>

  <!-- ── KPI CARDS ─────────────────────────────────────────────── -->
  <div class="cr-kpis">
    <div class="cr-kpi">
      <div class="cr-kpi-label">Monthly Ad Spend</div>
      <div class="cr-kpi-value neutral" id="cr-spend">$5,000</div>
      <div class="cr-kpi-sub">leads × CPL</div>
    </div>
    <div class="cr-kpi">
      <div class="cr-kpi-label">Closed Deals</div>
      <div class="cr-kpi-value neutral" id="cr-deals">10</div>
      <div class="cr-kpi-sub">per month</div>
    </div>
    <div class="cr-kpi">
      <div class="cr-kpi-label">Monthly Revenue</div>
      <div class="cr-kpi-value positive" id="cr-revenue">$100,000</div>
      <div class="cr-kpi-sub">deals × job value</div>
    </div>
    <div class="cr-kpi">
      <div class="cr-kpi-label">Gross Profit</div>
      <div class="cr-kpi-value positive" id="cr-profit">$95,000</div>
      <div class="cr-kpi-sub">revenue − ad spend</div>
    </div>
  </div>

  <!-- ── ROI METER ─────────────────────────────────────────────── -->
  <div class="cr-meter-section">
    <div class="cr-meter-label" style="margin-bottom:0;">
      <span>Return on Ad Spend (ROAS)</span>
      <span class="cr-big-roi positive" id="cr-roi-big">1,900%</span>
    </div>
    <div class="cr-meter-bar">
      <div class="cr-meter-fill positive" id="cr-meter-fill" style="width:95%"></div>
      <div class="cr-meter-tick" style="left:25%"></div>
      <div class="cr-meter-tick" style="left:50%"></div>
      <div class="cr-meter-tick" style="left:75%"></div>
    </div>
    <div class="cr-meter-labels">
      <span>0%</span>
      <span>Breakeven (100%)</span>
      <span>2,000%+</span>
    </div>
  </div>

  <!-- ── BREAKEVEN STATS ───────────────────────────────────────── -->
  <div class="cr-breakeven">
    <div class="cr-be-card">
      <div class="cr-be-label">Breakeven Leads</div>
      <div class="cr-be-value positive" id="cr-be-leads">1</div>
    </div>
    <div class="cr-be-card">
      <div class="cr-be-label">Breakeven Spend</div>
      <div class="cr-be-value positive" id="cr-be-spend">$50</div>
    </div>
    <div class="cr-be-card">
      <div class="cr-be-label">Revenue / Lead</div>
      <div class="cr-be-value positive" id="cr-be-rpl">$1,000</div>
    </div>
    <div class="cr-be-card">
      <div class="cr-be-label">Profit / Lead</div>
      <div class="cr-be-value positive" id="cr-be-ppl">$950</div>
    </div>
  </div>

  <!-- ── MONTHLY PROJECTIONS ──────────────────────────────────── -->
  <div class="cr-proj-section">
    <div class="cr-proj-header">Projections</div>
    <div class="cr-table-wrap">
      <table class="cr-proj-table">
        <thead>
          <tr>
            <th>Period</th>
            <th>Ad Spend</th>
            <th>Deals</th>
            <th>Revenue</th>
            <th>Profit</th>
            <th style="text-align:right">Cumulative Profit</th>
          </tr>
        </thead>
        <tbody id="cr-proj-body">
          <tr class="profit-row"><td>Month 1</td><td>$5,000</td><td>10</td><td>$100,000</td><td>$95,000</td><td>$95,000</td></tr>
          <tr class="profit-row"><td>Month 3</td><td>$15,000</td><td>30</td><td>$300,000</td><td>$285,000</td><td>$285,000</td></tr>
          <tr class="profit-row"><td>Month 6</td><td>$30,000</td><td>60</td><td>$600,000</td><td>$570,000</td><td>$570,000</td></tr>
          <tr class="profit-row"><td>Month 12</td><td>$60,000</td><td>120</td><td>$1,200,000</td><td>$1,140,000</td><td>$1,140,000</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- ── SCENARIO COMPARISON ───────────────────────────────────── -->
  <div class="cr-scenario-section">
    <div class="cr-proj-header">Compare Scenarios</div>
    <div class="cr-scenario-inner">
      <div class="cr-scenario">
        <div class="cr-scenario-tier">Conservative</div>
        <div class="cr-scenario-name">50 leads · 8% close</div>
        <div class="cr-scenario-desc">Low volume, moderate conversion — realistic early-stage projection</div>
        <div class="cr-scenario-roi" id="cr-scenario-con-roi">—</div>
        <div class="cr-scenario-profit" id="cr-scenario-con-profit">—/mo</div>
        <button class="cr-scenario-btn" onclick="applyScenario('conservative')">Apply</button>
      </div>
      <div class="cr-scenario">
        <div class="cr-scenario-tier">Realistic</div>
        <div class="cr-scenario-name">100 leads · 12% close</div>
        <div class="cr-scenario-desc">Steady volume with solid conversion — target for established contractors</div>
        <div class="cr-scenario-roi" id="cr-scenario-real-roi">—</div>
        <div class="cr-scenario-profit" id="cr-scenario-real-profit">—/mo</div>
        <button class="cr-scenario-btn" onclick="applyScenario('realistic')">Apply</button>
      </div>
      <div class="cr-scenario">
        <div class="cr-scenario-tier">Aggressive</div>
        <div class="cr-scenario-name">300 leads · 15% close</div>
        <div class="cr-scenario-desc">High volume, strong conversion — for growth-mode contractors</div>
        <div class="cr-scenario-roi" id="cr-scenario-agg-roi">—</div>
        <div class="cr-scenario-profit" id="cr-scenario-agg-profit">—/mo</div>
        <button class="cr-scenario-btn" onclick="applyScenario('aggressive')">Apply</button>
      </div>
    </div>
  </div>

  <!-- ── FOOTER ────────────────────────────────────────────────── -->
  <div class="cr-foot">
    <a href="/">Empire AI</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/pricing">Pricing</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/mrr">MRR</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/ppl">Pay-Per-Lead</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/for-contractors">For Contractors</a>
    <br>
    <span style="letter-spacing:0.12em;color:var(--empire-shadow);margin-top:8px;display:block;">
      Estimates are for illustration only. Actual results vary by market, season, and campaign performance.
    </span>
  </div>

</div>

<script>
(function() {{
  'use strict';

  // Default CPL for scenario calculations
  var defaultCpl = 50;

  function fmtCurrency(n) {{
    if (n >= 0) return '$' + n.toLocaleString(undefined, {{ minimumFractionDigits: 0, maximumFractionDigits: 0 }});
    return '-$' + Math.abs(n).toLocaleString(undefined, {{ minimumFractionDigits: 0, maximumFractionDigits: 0 }});
  }}

  function fmtCurrency2(n) {{
    return '$' + n.toLocaleString(undefined, {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
  }}

  function fmtPct(n) {{
    return n.toFixed(1) + '%';
  }}

  // ── MAIN CALCULATOR ─────────────────────────────────────────
  window.calc = function() {{
    var leads   = parseInt(document.getElementById('cr-slider-leads').value);
    var cpl     = parseInt(document.getElementById('cr-slider-cpl').value);
    var closePct = parseInt(document.getElementById('cr-slider-close').value);
    var jobVal  = parseInt(document.getElementById('cr-slider-job').value);

    var closeRate = closePct / 100;

    // Slider value displays + fill width
    document.getElementById('cr-val-leads').textContent = leads;
    document.getElementById('cr-val-cpl').textContent = '$' + cpl;
    document.getElementById('cr-val-close').textContent = closePct + '%';
    document.getElementById('cr-val-job').textContent = '$' + jobVal.toLocaleString();

    document.getElementById('cr-fill-leads').style.width = Math.min(100, (leads / 500) * 100) + '%';
    document.getElementById('cr-fill-cpl').style.width = Math.min(100, (cpl / 200) * 100) + '%';
    document.getElementById('cr-fill-close').style.width = Math.min(100, (closePct / 40) * 100) + '%';
    document.getElementById('cr-fill-job').style.width = Math.min(100, (jobVal / 50000) * 100) + '%';

    // Core metrics
    var spend      = leads * cpl;
    var closedDeals = Math.floor(leads * closeRate);
    var monthlyRev  = closedDeals * jobVal;
    var profit      = monthlyRev - spend;

    // ROI / ROAS
    var roas = spend > 0 ? (monthlyRev / spend) * 100 : 0;
    var roiPct = spend > 0 ? (profit / spend) * 100 : 0;

    // Breakeven
    var beLeads  = Math.ceil(cpl / (jobVal * closeRate));  // leads to recoup spend
    if (!isFinite(beLeads) || beLeads < 1) beLeads = 1;
    var beSpend  = beLeads * cpl;
    var revPerLead = jobVal * closeRate;  // expected revenue per lead
    var profitPerLead = revPerLead - cpl;

    // ── Update KPIs ───────────────────────────────────────────
    document.getElementById('cr-spend').textContent = fmtCurrency(spend);
    document.getElementById('cr-deals').textContent = closedDeals;
    document.getElementById('cr-revenue').textContent = fmtCurrency(monthlyRev);
    document.getElementById('cr-profit').textContent = fmtCurrency(profit);

    // Colorize profit
    var profitEl = document.getElementById('cr-profit');
    profitEl.className = 'cr-kpi-value ' + (profit >= 0 ? 'positive' : 'negative');

    // ── ROI Meter ─────────────────────────────────────────────
    var roiDisplay = roiPct >= 0 ? fmtPct(roiPct) : '-' + fmtPct(Math.abs(roiPct));
    document.getElementById('cr-roi-big').textContent = roiDisplay;
    document.getElementById('cr-roi-big').className = 'cr-big-roi ' + (roiPct >= 0 ? 'positive' : 'negative');

    // Map ROI to meter width: 0% = 0%, 100% = 25%, 500% = 62%, 2000%+ = 100%
    var meterPct = 0;
    if (roiPct <= 0) {{
      meterPct = 0;
    }} else if (roiPct >= 2000) {{
      meterPct = 100;
    }} else {{
      meterPct = (Math.log(roiPct + 1) / Math.log(2001)) * 100;
    }}
    var meterFill = document.getElementById('cr-meter-fill');
    meterFill.style.width = Math.max(2, meterPct) + '%';
    meterFill.className = 'cr-meter-fill ' + (roiPct >= 0 ? 'positive' : 'negative');

    // ── Breakeven stats ───────────────────────────────────────
    document.getElementById('cr-be-leads').textContent = beLeads;
    document.getElementById('cr-be-spend').textContent = fmtCurrency(beSpend);
    document.getElementById('cr-be-rpl').textContent = fmtCurrency2(revPerLead);
    document.getElementById('cr-be-ppl').textContent = fmtCurrency2(profitPerLead);

    // Colorize profit/lead
    var bePpl = document.getElementById('cr-be-ppl');
    bePpl.className = 'cr-be-value ' + (profitPerLead >= 0 ? 'positive' : 'negative');

    // ── Monthly projections ───────────────────────────────────
    var projBody = document.getElementById('cr-proj-body');
    var periods = [1, 3, 6, 12];
    var rows = '';
    var cumProfit = 0;
    for (var i = 0; i < periods.length; i++) {{
      var m = periods[i];
      var mSpend = spend * m;
      var mDeals = closedDeals * m;
      var mRevenue = monthlyRev * m;
      var mProfit = mRevenue - mSpend;
      cumProfit += mProfit;
      var cls = mProfit >= 0 ? 'profit-row' : 'loss-row';
      rows += '<tr class="' + cls + '">' +
        '<td>Month ' + m + '</td>' +
        '<td>' + fmtCurrency(mSpend) + '</td>' +
        '<td>' + mDeals + '</td>' +
        '<td>' + fmtCurrency(mRevenue) + '</td>' +
        '<td>' + fmtCurrency(mProfit) + '</td>' +
        '<td>' + fmtCurrency(cumProfit) + '</td>' +
      '</tr>';
    }}
    projBody.innerHTML = rows;

    // ── Scenario comparisons ─────────────────────────────────
    // Conservative: 50 leads, 8% close (CPL stays same)
    var conLeads = 50;
    var conClose = 0.08;
    var conSpend = conLeads * cpl;
    var conDeals = Math.floor(conLeads * conClose);
    var conRev = conDeals * jobVal;
    var conProfit = conRev - conSpend;
    var conRoi = conSpend > 0 ? (conProfit / conSpend) * 100 : 0;
    document.getElementById('cr-scenario-con-roi').textContent = (conRoi >= 0 ? '' : '-') + Math.abs(conRoi).toFixed(0) + '%';
    document.getElementById('cr-scenario-con-roi').style.color = conRoi >= 0 ? 'var(--signal-teal)' : 'var(--status-red)';
    document.getElementById('cr-scenario-con-profit').textContent = fmtCurrency(conProfit) + '/mo';

    // Realistic: 100 leads, 12% close
    var realLeads = 100;
    var realClose = 0.12;
    var realSpend = realLeads * cpl;
    var realDeals = Math.floor(realLeads * realClose);
    var realRev = realDeals * jobVal;
    var realProfit = realRev - realSpend;
    var realRoi = realSpend > 0 ? (realProfit / realSpend) * 100 : 0;
    document.getElementById('cr-scenario-real-roi').textContent = (realRoi >= 0 ? '' : '-') + Math.abs(realRoi).toFixed(0) + '%';
    document.getElementById('cr-scenario-real-roi').style.color = realRoi >= 0 ? 'var(--signal-teal)' : 'var(--status-red)';
    document.getElementById('cr-scenario-real-profit').textContent = fmtCurrency(realProfit) + '/mo';

    // Aggressive: 300 leads, 15% close
    var aggLeads = 300;
    var aggClose = 0.15;
    var aggSpend = aggLeads * cpl;
    var aggDeals = Math.floor(aggLeads * aggClose);
    var aggRev = aggDeals * jobVal;
    var aggProfit = aggRev - aggSpend;
    var aggRoi = aggSpend > 0 ? (aggProfit / aggSpend) * 100 : 0;
    document.getElementById('cr-scenario-agg-roi').textContent = (aggRoi >= 0 ? '' : '-') + Math.abs(aggRoi).toFixed(0) + '%';
    document.getElementById('cr-scenario-agg-roi').style.color = aggRoi >= 0 ? 'var(--signal-teal)' : 'var(--status-red)';
    document.getElementById('cr-scenario-agg-profit').textContent = fmtCurrency(aggProfit) + '/mo';
  }};

  // ── SCENARIO APPLY ──────────────────────────────────────────
  window.applyScenario = function(scenario) {{
    var leads, close, jobVal, cpl;
    switch (scenario) {{
      case 'conservative':
        leads = 50; close = 8; break;
      case 'realistic':
        leads = 100; close = 12; break;
      case 'aggressive':
        leads = 300; close = 15; break;
    }}
    cpl = parseInt(document.getElementById('cr-slider-cpl').value);
    jobVal = parseInt(document.getElementById('cr-slider-job').value);

    document.getElementById('cr-slider-leads').value = leads;
    document.getElementById('cr-slider-close').value = close;
    calc();
    // Scroll to top of calculator
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
  }};

  // ── INIT ────────────────────────────────────────────────────
  calc();
}})();
</script>

</body>
</html>"""
