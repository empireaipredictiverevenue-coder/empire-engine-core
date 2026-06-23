"""
EMPIRE V49 · CLAIM SETTLEMENT ESTIMATOR PAGE
=============================================
Interactive HTML page at /calculator/claim-estimator with inputs for
roof sq ft, damage type, and location — estimates claim value, 3%
Empire fee, and detailed cost breakdown. All client-side math.

Wire-up in hub.py:
    from empire_claim_estimator_page import claim_estimator_page

    @app.get("/calculator/claim-estimator", response_class=HTMLResponse)
    async def claim_estimator():
        return HTMLResponse(claim_estimator_page())
"""

from empire_tokens import empire_head


def claim_estimator_page() -> str:
    extra_css = """
    .ce-wrap {
      max-width: 960px;
      margin: 0 auto;
      padding: 48px 32px 80px;
    }

    /* ── HEADER ─────────────────────────────────────────────────── */
    .ce-header {
      text-align: center;
      margin-bottom: 48px;
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .ce-eyebrow {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.32em;
      text-transform: uppercase;
      margin-bottom: 12px;
    }
    .ce-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 44px;
      letter-spacing: -0.04em;
      color: var(--empire-white);
      line-height: 1.1;
      margin-bottom: 16px;
    }
    .ce-title em {
      font-style: italic;
      font-weight: 700;
      color: var(--signal-teal);
    }
    .ce-sub {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      max-width: 560px;
      margin: 0 auto;
      line-height: 1.7;
    }

    /* ── INPUT ROW (3-column) ──────────────────────────────────── */
    .ce-inputs {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 28px;
      margin-bottom: 44px;
    }
    .ce-input-group {
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .ce-input-group:nth-child(1) { animation-delay: 0.05s; }
    .ce-input-group:nth-child(2) { animation-delay: 0.10s; }
    .ce-input-group:nth-child(3) { animation-delay: 0.15s; }

    .ce-input-label {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 8px;
    }
    .ce-input-label-name {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      font-weight: 600;
    }
    .ce-input-label-value {
      font-family: var(--font-mono);
      font-size: 18px;
      font-weight: 600;
      color: var(--signal-teal);
      font-feature-settings: 'tnum' 1;
      transition: color 0.2s;
    }
    .ce-slider-track {
      position: relative;
      height: 6px;
      background: rgba(10, 26, 47, 0.8);
      border-radius: 3px;
      cursor: pointer;
    }
    .ce-slider-fill {
      position: absolute;
      top: 0; left: 0;
      height: 100%;
      background: linear-gradient(90deg, var(--signal-teal), var(--strike-cyan));
      border-radius: 3px;
      pointer-events: none;
      transition: width 0.05s linear;
    }
    .ce-slider-track input[type="range"] {
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
    .ce-slider-track input[type="range"]::-webkit-slider-thumb {
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
    .ce-slider-track input[type="range"]::-webkit-slider-thumb:hover {
      transform: scale(1.15);
      border-color: var(--strike-cyan);
    }
    .ce-slider-track input[type="range"]::-moz-range-thumb {
      width: 20px; height: 20px;
      border-radius: 50%;
      background: var(--empire-surface);
      border: 2px solid var(--signal-teal);
      box-shadow: 0 0 12px var(--signal-teal-glow);
      cursor: pointer;
    }

    .ce-select-wrap {
      position: relative;
    }
    .ce-select-wrap select {
      -webkit-appearance: none;
      appearance: none;
      width: 100%;
      padding: 12px 14px;
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      border-radius: var(--radius-xs, 4px);
      font-family: var(--font-mono);
      font-size: 13px;
      color: var(--empire-white);
      cursor: pointer;
      transition: all 0.2s;
    }
    .ce-select-wrap select:hover {
      border-color: var(--signal-teal-soft);
    }
    .ce-select-wrap select:focus {
      outline: none;
      border-color: var(--signal-teal);
      box-shadow: 0 0 0 2px var(--signal-teal-glow);
    }
    .ce-select-wrap::after {
      content: '\\25BE';
      position: absolute;
      right: 12px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--empire-mist);
      pointer-events: none;
      font-size: 14px;
    }
    .ce-select-hint {
      margin-top: 6px;
      font-family: var(--font-mono);
      font-size: 8px;
      color: var(--empire-fog);
      letter-spacing: 0.12em;
    }

    /* ── HERO CLAIM VALUE ──────────────────────────────────────── */
    .ce-hero {
      text-align: center;
      margin-bottom: 40px;
      padding: 32px;
      background: var(--empire-elevated);
      border: 1px solid var(--empire-divider);
      position: relative;
      overflow: hidden;
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
      animation-delay: 0.20s;
    }
    .ce-hero::before {
      content: '';
      position: absolute; top: 0; left: 0;
      width: 100%; height: 3px;
      background: linear-gradient(90deg, var(--signal-teal), var(--strike-cyan), var(--status-amber));
    }
    .ce-hero-label {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-mist);
      letter-spacing: 0.24em;
      text-transform: uppercase;
      font-weight: 600;
      margin-bottom: 6px;
    }
    .ce-hero-value {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 56px;
      letter-spacing: -0.04em;
      color: var(--signal-teal);
      line-height: 1;
      margin-bottom: 8px;
      transition: color 0.3s;
    }
    .ce-hero-value.positive { color: var(--signal-teal); }
    .ce-hero-sub {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-fog);
      letter-spacing: 0.14em;
    }

    /* ── BREAKDOWN GRID ────────────────────────────────────────── */
    .ce-breakdown-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 36px;
    }
    .ce-card {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 20px;
      text-align: center;
      position: relative;
      overflow: hidden;
      transition: all 0.25s var(--ease-out-empire);
      animation: empire-fade-up 0.4s var(--ease-out-empire) both;
    }
    .ce-card:nth-child(1) { animation-delay: 0.10s; }
    .ce-card:nth-child(2) { animation-delay: 0.15s; }
    .ce-card:nth-child(3) { animation-delay: 0.20s; }
    .ce-card:nth-child(4) { animation-delay: 0.25s; }
    .ce-card:hover {
      border-color: var(--empire-border);
      transform: translateY(-2px);
    }
    .ce-card::before {
      content: '';
      position: absolute; top: 0; left: 0;
      width: 2px; height: 100%;
      background: var(--accent, var(--signal-teal));
    }
    .ce-card:nth-child(1) { --accent: var(--strike-cyan); }
    .ce-card:nth-child(2) { --accent: var(--status-amber); }
    .ce-card:nth-child(3) { --accent: var(--signal-teal); }
    .ce-card:nth-child(4) { --accent: var(--status-amber); }

    .ce-card-label {
      font-family: var(--font-mono);
      font-size: 8px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 8px;
      font-weight: 600;
    }
    .ce-card-value {
      font-family: var(--font-mono);
      font-weight: 600;
      font-size: 22px;
      line-height: 1;
      color: var(--empire-white);
      font-feature-settings: 'tnum' 1;
      transition: color 0.3s;
    }
    .ce-card-value.positive { color: var(--signal-teal); }
    .ce-card-value.neutral  { color: var(--strike-cyan); }
    .ce-card-value.accent   { color: var(--status-amber); }
    .ce-card-sub {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      margin-top: 6px;
    }

    /* ── COST BREAKDOWN TABLE ──────────────────────────────────── */
    .ce-detail-section {
      margin-bottom: 40px;
    }
    .ce-detail-header {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      font-weight: 600;
      margin-bottom: 14px;
    }
    .ce-table-wrap {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      overflow: hidden;
    }
    .ce-table {
      width: 100%;
      border-collapse: collapse;
    }
    .ce-table thead th {
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
    .ce-table thead th:last-child { text-align: right; }
    .ce-table thead th:nth-child(2) { text-align: right; }
    .ce-table tbody td {
      padding: 11px 16px;
      border-bottom: 1px solid var(--empire-divider);
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-silver);
      font-feature-settings: 'tnum' 1;
    }
    .ce-table tbody td:last-child { text-align: right; font-weight: 600; color: var(--empire-white); }
    .ce-table tbody td:nth-child(2) { text-align: right; }
    .ce-table tbody tr:last-child td { border-bottom: none; }
    .ce-table tbody tr:hover { background: rgba(68, 229, 184, 0.03); }
    .ce-table .ce-total-row td {
      font-weight: 700;
      color: var(--empire-white);
      border-top: 2px solid var(--signal-teal-soft);
      background: rgba(68, 229, 184, 0.04);
    }

    /* ── FEE BREAKDOWN ─────────────────────────────────────────── */
    .ce-fee-section {
      margin-bottom: 36px;
    }
    .ce-fee-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
    }
    .ce-fee-card {
      background: var(--empire-elevated);
      border: 1px solid var(--empire-divider);
      padding: 20px;
      text-align: center;
      animation: empire-fade-up 0.4s var(--ease-out-empire) both;
    }
    .ce-fee-card:nth-child(1) { animation-delay: 0.15s; }
    .ce-fee-card:nth-child(2) { animation-delay: 0.20s; }
    .ce-fee-card:nth-child(3) { animation-delay: 0.25s; }

    .ce-fee-label {
      font-family: var(--font-mono);
      font-size: 8px;
      color: var(--empire-fog);
      letter-spacing: 0.16em;
      text-transform: uppercase;
      margin-bottom: 6px;
    }
    .ce-fee-value {
      font-family: var(--font-mono);
      font-weight: 600;
      font-size: 18px;
      color: var(--empire-white);
      font-feature-settings: 'tnum' 1;
    }
    .ce-fee-value.positive { color: var(--signal-teal); }
    .ce-fee-value.negative { color: var(--status-red); }

    /* ── DAMAGE TYPE INFO ──────────────────────────────────────── */
    .ce-damage-info {
      margin-bottom: 40px;
    }
    .ce-damage-info-inner {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .ce-damage-attribute {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 16px;
    }
    .ce-da-label {
      font-family: var(--font-mono);
      font-size: 8px;
      color: var(--empire-fog);
      letter-spacing: 0.16em;
      text-transform: uppercase;
      margin-bottom: 4px;
    }
    .ce-da-value {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--empire-white);
    }

    /* ── SCENARIO PRESETS ──────────────────────────────────────── */
    .ce-presets {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-bottom: 36px;
    }
    .ce-preset {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 18px;
      text-align: center;
      transition: all 0.25s var(--ease-snap);
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .ce-preset:nth-child(1) { animation-delay: 0.15s; }
    .ce-preset:nth-child(2) { animation-delay: 0.20s; }
    .ce-preset:nth-child(3) { animation-delay: 0.25s; }
    .ce-preset:hover {
      border-color: var(--signal-teal-soft);
      transform: translateY(-2px);
    }
    .ce-preset-tier {
      font-family: var(--font-mono);
      font-size: 8px;
      color: var(--empire-fog);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 4px;
    }
    .ce-preset-name {
      font-weight: 600;
      font-size: 13px;
      color: var(--empire-white);
      margin-bottom: 6px;
    }
    .ce-preset-desc {
      font-size: 10px;
      color: var(--empire-mist);
      line-height: 1.5;
      margin-bottom: 10px;
    }
    .ce-preset-claim {
      font-family: var(--font-mono);
      font-size: 17px;
      font-weight: 600;
      color: var(--signal-teal);
      margin-bottom: 2px;
    }
    .ce-preset-fee {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-mist);
      margin-bottom: 10px;
    }
    .ce-preset-btn {
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
    .ce-preset-btn:hover {
      background: var(--signal-teal);
      color: #0A1A2F;
    }

    /* ── FOOTER ─────────────────────────────────────────────────── */
    .ce-foot {
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
    .ce-foot a { color: var(--empire-mist); text-decoration: none; }
    .ce-foot a:hover { color: var(--signal-teal); }

    /* ── RESPONSIVE ─────────────────────────────────────────────── */
    @media (max-width: 860px) {
      .ce-inputs { grid-template-columns: 1fr; gap: 20px; }
      .ce-breakdown-grid { grid-template-columns: repeat(2, 1fr); }
      .ce-fee-grid { grid-template-columns: 1fr; }
      .ce-presets { grid-template-columns: 1fr; }
      .ce-damage-info-inner { grid-template-columns: 1fr; }
      .ce-title { font-size: 32px; }
      .ce-hero-value { font-size: 40px; }
      .ce-wrap { padding: 32px 20px 60px; }
    }
    @media (max-width: 480px) {
      .ce-breakdown-grid { grid-template-columns: 1fr; }
    }
    """

    head = empire_head(
        title="Claim Settlement Estimator · Empire AI",
        extra=extra_css,
        page="",
        description="Estimate your insurance claim value as a restoration contractor. Enter roof sq ft, damage type, and location to see estimated settlement, Empire AI's 3% fee, and detailed cost breakdown.",
        keywords="claim estimator, settlement calculator, insurance claim, roof damage, restoration contractor, Empire AI fee",
        canonical="https://empire-ai.co.uk/calculator/claim-estimator",
    )

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="ce-wrap">

  <!-- ── HEADER ────────────────────────────────────────────────── -->
  <div class="ce-header">
    <div class="ce-eyebrow">Estimation Tool</div>
    <h1 class="ce-title">Claim Settlement <em>Estimator</em></h1>
    <p class="ce-sub">
      Enter the property details below to get an estimated insurance
      claim value, Empire&rsquo;s 3% success fee, and a full cost breakdown
      &mdash; all calculated in real time based on industry-standard rates.
    </p>
  </div>

  <!-- ── INPUTS ────────────────────────────────────────────────── -->
  <div class="ce-inputs">

    <!-- Roof Sq Ft -->
    <div class="ce-input-group">
      <div class="ce-input-label">
        <span class="ce-input-label-name">Roof Area</span>
        <span class="ce-input-label-value" id="ce-val-sqft">2,500</span>
      </div>
      <div class="ce-slider-track">
        <div class="ce-slider-fill" id="ce-fill-sqft" style="width:21%"></div>
        <input type="range" id="ce-slider-sqft" min="500" max="10000" value="2500" step="100"
               oninput="calc()">
      </div>
      <div class="ce-select-hint">500 – 10,000 sq ft</div>
    </div>

    <!-- Damage Type -->
    <div class="ce-input-group">
      <div class="ce-input-label">
        <span class="ce-input-label-name">Damage Type</span>
        <span class="ce-input-label-value" id="ce-val-damage">Hail</span>
      </div>
      <div class="ce-select-wrap">
        <select id="ce-select-damage" onchange="calc()">
          <option value="hail">Hail</option>
          <option value="wind">Wind</option>
          <option value="fire" selected>Fire</option>
          <option value="water">Water</option>
          <option value="storm">Storm / Flood</option>
        </select>
      </div>
      <div class="ce-select-hint">Type of damage sustained</div>
    </div>

    <!-- Location -->
    <div class="ce-input-group">
      <div class="ce-input-label">
        <span class="ce-input-label-name">Location</span>
        <span class="ce-input-label-value" id="ce-val-location">Texas</span>
      </div>
      <div class="ce-select-wrap">
        <select id="ce-select-state" onchange="calc()">
          <option value="TX" selected>Texas</option>
          <option value="FL">Florida</option>
          <option value="CA">California</option>
          <option value="CO">Colorado</option>
          <option value="OK">Oklahoma</option>
          <option value="LA">Louisiana</option>
          <option value="NC">North Carolina</option>
          <option value="SC">South Carolina</option>
          <option value="GA">Georgia</option>
          <option value="AL">Alabama</option>
          <option value="TN">Tennessee</option>
          <option value="MO">Missouri</option>
          <option value="IL">Illinois</option>
          <option value="OH">Ohio</option>
          <option value="PA">Pennsylvania</option>
          <option value="NY">New York</option>
          <option value="NJ">New Jersey</option>
          <option value="AZ">Arizona</option>
          <option value="NV">Nevada</option>
          <option value="WA">Washington</option>
          <option value="OR">Oregon</option>
          <option value="MN">Minnesota</option>
          <option value="MI">Michigan</option>
          <option value="IN">Indiana</option>
          <option value="VA">Virginia</option>
          <option value="MD">Maryland</option>
          <option value="MA">Massachusetts</option>
          <option value="CT">Connecticut</option>
          <option value="NE">Nebraska</option>
          <option value="KS">Kansas</option>
          <option value="IA">Iowa</option>
          <option value="WI">Wisconsin</option>
          <option value="KY">Kentucky</option>
          <option value="AR">Arkansas</option>
          <option value="MS">Mississippi</option>
        </select>
      </div>
      <div class="ce-select-hint">Property location (regional cost factor)</div>
    </div>

  </div>

  <!-- ── HERO CLAIM VALUE ──────────────────────────────────────── -->
  <div class="ce-hero">
    <div class="ce-hero-label">Estimated Claim Settlement</div>
    <div class="ce-hero-value positive" id="ce-hero-value">$52,500</div>
    <div class="ce-hero-sub">
      Empire&rsquo;s 3% fee: <strong id="ce-hero-fee">$1,575</strong>
      &nbsp;&middot;&nbsp; Net to contractor: <strong id="ce-hero-net">$50,925</strong>
    </div>
  </div>

  <!-- ── KPI BREAKDOWN GRID ───────────────────────────────────── -->
  <div class="ce-breakdown-grid">
    <div class="ce-card">
      <div class="ce-card-label">Total Per Sq Ft</div>
      <div class="ce-card-value neutral" id="ce-kpi-psf">$21.00</div>
      <div class="ce-card-sub">labor + materials</div>
    </div>
    <div class="ce-card">
      <div class="ce-card-label">Materials</div>
      <div class="ce-card-value" id="ce-kpi-mats">$25,625</div>
      <div class="ce-card-sub">shingles, underlayment, flashing</div>
    </div>
    <div class="ce-card">
      <div class="ce-card-label">Labor</div>
      <div class="ce-card-value" id="ce-kpi-labor">$20,125</div>
      <div class="ce-card-sub">crew + equipment</div>
    </div>
    <div class="ce-card">
      <div class="ce-card-label">Permits &amp; Overhead</div>
      <div class="ce-card-value accent" id="ce-kpi-oh">$6,750</div>
      <div class="ce-card-sub">permits, dump fees, cleanup</div>
    </div>
  </div>

  <!-- ── COST BREAKDOWN TABLE ──────────────────────────────────── -->
  <div class="ce-detail-section">
    <div class="ce-detail-header">Cost Breakdown</div>
    <div class="ce-table-wrap">
      <table class="ce-table">
        <thead>
          <tr>
            <th>Line Item</th>
            <th style="text-align:right">Per Sq Ft</th>
            <th style="text-align:right">Total</th>
          </tr>
        </thead>
        <tbody id="ce-breakdown-body">
          <tr><td>Roofing Materials</td><td>$8.50</td><td>$21,250</td></tr>
          <tr><td>Underlayment &amp; Ice Shield</td><td>$1.75</td><td>$4,375</td></tr>
          <tr><td>Flashing &amp; Vents</td><td>$1.50</td><td>$3,750</td></tr>
          <tr><td>Dump Fees &amp; Disposal</td><td>$0.75</td><td>$1,875</td></tr>
          <tr><td>Labor — Tear-off</td><td>$2.50</td><td>$6,250</td></tr>
          <tr><td>Labor — Install</td><td>$5.50</td><td>$13,750</td></tr>
          <tr><td>Permits &amp; Code Upgrades</td><td>$0.50</td><td>$1,250</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- ── FEE BREAKDOWN ─────────────────────────────────────────── -->
  <div class="ce-fee-section">
    <div class="ce-detail-header">Fee &amp; Net Settlement</div>
    <div class="ce-fee-grid">
      <div class="ce-fee-card">
        <div class="ce-fee-label">Gross Claim</div>
        <div class="ce-fee-value positive" id="ce-fee-gross">$52,500</div>
      </div>
      <div class="ce-fee-card">
        <div class="ce-fee-label">Empire AI Fee (3%)</div>
        <div class="ce-fee-value negative" id="ce-fee-fee">$1,575</div>
      </div>
      <div class="ce-fee-card">
        <div class="ce-fee-label">Net to Contractor</div>
        <div class="ce-fee-value positive" id="ce-fee-net">$50,925</div>
      </div>
    </div>
  </div>

  <!-- ── DAMAGE INFO ───────────────────────────────────────────── -->
  <div class="ce-damage-info">
    <div class="ce-detail-header">Estimation Parameters</div>
    <div class="ce-damage-info-inner">
      <div class="ce-damage-attribute">
        <div class="ce-da-label">Base Cost / Sq Ft</div>
        <div class="ce-da-value" id="ce-damage-base">$19.00</div>
      </div>
      <div class="ce-damage-attribute">
        <div class="ce-da-label">Regional Multiplier</div>
        <div class="ce-da-value" id="ce-damage-mult">1.15×</div>
      </div>
      <div class="ce-damage-attribute">
        <div class="ce-da-label">Deductible Estimate</div>
        <div class="ce-da-value" id="ce-damage-deduct">$5,250 (10%)</div>
      </div>
      <div class="ce-damage-attribute">
        <div class="ce-da-label">Depreciation (RCV → ACV)</div>
        <div class="ce-da-value" id="ce-damage-depr">$5,250</div>
      </div>
    </div>
  </div>

  <!-- ── PRESET SCENARIOS ──────────────────────────────────────── -->
  <div class="ce-detail-header">Quick Scenarios</div>
  <div class="ce-presets">
    <div class="ce-preset">
      <div class="ce-preset-tier">Residential</div>
      <div class="ce-preset-name">1,800 sq ft · Hail</div>
      <div class="ce-preset-desc">Standard suburban roof, moderate hail damage, TX region</div>
      <div class="ce-preset-claim" id="ce-preset-res-claim">—</div>
      <div class="ce-preset-fee" id="ce-preset-res-fee">—</div>
      <button class="ce-preset-btn" onclick="applyPreset('residential')">Apply</button>
    </div>
    <div class="ce-preset">
      <div class="ce-preset-tier">Commercial</div>
      <div class="ce-preset-name">5,000 sq ft · Fire</div>
      <div class="ce-preset-desc">Medium commercial roof with fire damage, FL region</div>
      <div class="ce-preset-claim" id="ce-preset-com-claim">—</div>
      <div class="ce-preset-fee" id="ce-preset-com-fee">—</div>
      <button class="ce-preset-btn" onclick="applyPreset('commercial')">Apply</button>
    </div>
    <div class="ce-preset">
      <div class="ce-preset-tier">Large Loss</div>
      <div class="ce-preset-name">8,000 sq ft · Storm</div>
      <div class="ce-preset-desc">Large commercial roof, storm/flood damage, LA region</div>
      <div class="ce-preset-claim" id="ce-preset-lg-claim">—</div>
      <div class="ce-preset-fee" id="ce-preset-lg-fee">—</div>
      <button class="ce-preset-btn" onclick="applyPreset('large')">Apply</button>
    </div>
  </div>

  <!-- ── FOOTER ────────────────────────────────────────────────── -->
  <div class="ce-foot">
    <a href="/">Empire AI</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/calculator/roi">ROI Calculator</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/pricing">Pricing</a>
    <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
    <a href="/for-contractors">For Contractors</a>
    <br>
    <span style="letter-spacing:0.12em;color:var(--empire-shadow);margin-top:8px;display:block;">
      Estimates are based on industry-average restoration costs and are for illustration only.
      Actual claim values vary by insurer, policy terms, adjuster assessment, and market conditions.
    </span>
  </div>

</div>

<script>
(function() {{
  'use strict';

  // ── Damage type base cost per sq ft ────────────────────────────
  var DAMAGE_BASES = {{
    hail:  {{
      name: 'Hail',
      base: 12.00,       // base cost per sq ft
      materials: 6.50,
      labor: 4.00,
      permits: 0.60,
      deductible_pct: 0.01,
      depr_pct: 0.08,
    }},
    wind:  {{
      name: 'Wind',
      base: 14.00,
      materials: 7.50,
      labor: 4.50,
      permits: 0.60,
      deductible_pct: 0.01,
      depr_pct: 0.10,
    }},
    fire:  {{
      name: 'Fire',
      base: 19.00,
      materials: 9.00,
      labor: 6.00,
      permits: 1.20,
      deductible_pct: 0.01,
      depr_pct: 0.15,
    }},
    water: {{
      name: 'Water',
      base: 15.00,
      materials: 7.00,
      labor: 5.50,
      permits: 0.80,
      deductible_pct: 0.01,
      depr_pct: 0.12,
    }},
    storm: {{
      name: 'Storm / Flood',
      base: 17.00,
      materials: 8.00,
      labor: 5.50,
      permits: 1.00,
      deductible_pct: 0.01,
      depr_pct: 0.14,
    }},
  }};

  // ── Regional cost multipliers ──────────────────────────────────
  var STATE_MULTIPLIERS = {{
    'TX': 1.15, 'FL': 1.20, 'CA': 1.30, 'CO': 1.10,
    'OK': 1.05, 'LA': 1.12, 'NC': 1.08, 'SC': 1.06,
    'GA': 1.04, 'AL': 1.03, 'TN': 1.02, 'MO': 1.02,
    'IL': 1.12, 'OH': 1.08, 'PA': 1.10, 'NY': 1.35,
    'NJ': 1.28, 'AZ': 1.06, 'NV': 1.08, 'WA': 1.18,
    'OR': 1.14, 'MN': 1.10, 'MI': 1.06, 'IN': 1.02,
    'VA': 1.08, 'MD': 1.18, 'MA': 1.25, 'CT': 1.22,
    'NE': 1.00, 'KS': 1.00, 'IA': 1.01, 'WI': 1.06,
    'KY': 0.98, 'AR': 0.97, 'MS': 0.96,
  }};

  var STATE_NAMES = {{
    'TX': 'Texas', 'FL': 'Florida', 'CA': 'California', 'CO': 'Colorado',
    'OK': 'Oklahoma', 'LA': 'Louisiana', 'NC': 'North Carolina', 'SC': 'South Carolina',
    'GA': 'Georgia', 'AL': 'Alabama', 'TN': 'Tennessee', 'MO': 'Missouri',
    'IL': 'Illinois', 'OH': 'Ohio', 'PA': 'Pennsylvania', 'NY': 'New York',
    'NJ': 'New Jersey', 'AZ': 'Arizona', 'NV': 'Nevada', 'WA': 'Washington',
    'OR': 'Oregon', 'MN': 'Minnesota', 'MI': 'Michigan', 'IN': 'Indiana',
    'VA': 'Virginia', 'MD': 'Maryland', 'MA': 'Massachusetts', 'CT': 'Connecticut',
    'NE': 'Nebraska', 'KS': 'Kansas', 'IA': 'Iowa', 'WI': 'Wisconsin',
    'KY': 'Kentucky', 'AR': 'Arkansas', 'MS': 'Mississippi',
  }};

  var FEE_PERCENT = 0.03;

  function fmtCurrency(n) {{
    if (n >= 0) return '$' + n.toLocaleString(undefined, {{ minimumFractionDigits: 0, maximumFractionDigits: 0 }});
    return '-$' + Math.abs(n).toLocaleString(undefined, {{ minimumFractionDigits: 0, maximumFractionDigits: 0 }});
  }}

  function fmtCurrency2(n) {{
    return '$' + n.toLocaleString(undefined, {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
  }}

  // ── MAIN CALCULATOR ─────────────────────────────────────────
  window.calc = function() {{
    var sqft     = parseInt(document.getElementById('ce-slider-sqft').value);
    var damage   = document.getElementById('ce-select-damage').value;
    var state    = document.getElementById('ce-select-state').value;

    var dProfile  = DAMAGE_BASES[damage];
    var mult      = STATE_MULTIPLIERS[state] || 1.0;
    var stateName = STATE_NAMES[state] || state;

    // Update label displays
    document.getElementById('ce-val-sqft').textContent = sqft.toLocaleString();
    document.getElementById('ce-val-damage').textContent = dProfile.name;
    document.getElementById('ce-val-location').textContent = stateName;

    // Fill width
    document.getElementById('ce-fill-sqft').style.width = Math.min(100, ((sqft - 500) / 9500) * 100) + '%';

    // ── Cost calculations ────────────────────────────────────
    var basePsf       = dProfile.base * mult;
    var materialsPsf  = dProfile.materials * mult;
    var laborPsf      = dProfile.labor * mult;
    var permitsPsf    = dProfile.permits * mult;
    var overheadPsf   = permitsPsf + 0.50 * mult;  // dump, cleanup, misc

    var totalMaterials = Math.round(materialsPsf * sqft);
    var totalLabor     = Math.round(laborPsf * sqft);
    var totalOverhead  = Math.round(overheadPsf * sqft);
    var grossClaim     = Math.round(basePsf * sqft);

    // Deductible (1% of claim typical for wind/hail)
    var deductiblePct  = dProfile.deductible_pct;
    var deductible     = Math.round(grossClaim * deductiblePct);

    // Depreciation (RCV → ACV reduction)
    var deprPct        = dProfile.depr_pct;
    var depreciation   = Math.round(grossClaim * deprPct);

    // ACV (Actual Cash Value) = RCV - depreciation
    var acv            = grossClaim - depreciation;

    // Empire fee (3% of gross claim)
    var fee            = Math.round(grossClaim * FEE_PERCENT);
    var netToContractor = grossClaim - fee;

    // ── Update hero ───────────────────────────────────────────
    document.getElementById('ce-hero-value').textContent = fmtCurrency(grossClaim);
    document.getElementById('ce-hero-fee').textContent = fmtCurrency(fee);
    document.getElementById('ce-hero-net').textContent = fmtCurrency(netToContractor);

    // ── Update KPIs ───────────────────────────────────────────
    document.getElementById('ce-kpi-psf').textContent = fmtCurrency2(basePsf);
    document.getElementById('ce-kpi-mats').textContent = fmtCurrency(totalMaterials);
    document.getElementById('ce-kpi-labor').textContent = fmtCurrency(totalLabor);
    document.getElementById('ce-kpi-oh').textContent = fmtCurrency(totalOverhead);

    // ── Update breakdown table ────────────────────────────────
    var tearoffPsf  = (laborPsf * 0.4).toFixed(2);
    var installPsf  = (laborPsf * 0.6).toFixed(2);
    var dumpPsf     = (mult * 0.75).toFixed(2);
    var matsPsf     = (dProfile.materials * mult).toFixed(2);
    var underPsf    = (mult * 1.75).toFixed(2);
    var flashPsf    = (mult * 1.50).toFixed(2);
    var permPsf     = (mult * 0.50).toFixed(2);

    var body = document.getElementById('ce-breakdown-body');
    body.innerHTML =
      '<tr><td>Roofing Materials</td><td>$' + matsPsf + '</td><td>' + fmtCurrency(totalMaterials) + '</td></tr>' +
      '<tr><td>Underlayment &amp; Ice Shield</td><td>$' + underPsf + '</td><td>' + fmtCurrency(Math.round(underPsf * sqft)) + '</td></tr>' +
      '<tr><td>Flashing &amp; Vents</td><td>$' + flashPsf + '</td><td>' + fmtCurrency(Math.round(flashPsf * sqft)) + '</td></tr>' +
      '<tr><td>Dump Fees &amp; Disposal</td><td>$' + dumpPsf + '</td><td>' + fmtCurrency(Math.round(dumpPsf * sqft)) + '</td></tr>' +
      '<tr><td>Labor &mdash; Tear-off</td><td>$' + tearoffPsf + '</td><td>' + fmtCurrency(Math.round(tearoffPsf * sqft)) + '</td></tr>' +
      '<tr><td>Labor &mdash; Install</td><td>$' + installPsf + '</td><td>' + fmtCurrency(Math.round(installPsf * sqft)) + '</td></tr>' +
      '<tr><td>Permits &amp; Code Upgrades</td><td>$' + permPsf + '</td><td>' + fmtCurrency(Math.round(permPsf * sqft)) + '</td></tr>' +
      '<tr class="ce-total-row"><td>Total Estimated Claim</td><td>$' + (basePsf).toFixed(2) + '</td><td>' + fmtCurrency(grossClaim) + '</td></tr>';

    // ── Fee breakdown ─────────────────────────────────────────
    document.getElementById('ce-fee-gross').textContent = fmtCurrency(grossClaim);
    document.getElementById('ce-fee-fee').textContent = fmtCurrency(fee);
    document.getElementById('ce-fee-net').textContent = fmtCurrency(netToContractor);

    // ── Damage info ───────────────────────────────────────────
    document.getElementById('ce-damage-base').textContent = fmtCurrency2(basePsf) + '/sq ft';
    document.getElementById('ce-damage-mult').textContent = mult.toFixed(2) + '×';
    document.getElementById('ce-damage-deduct').textContent = fmtCurrency(deductible) + ' (' + (deductiblePct * 100).toFixed(0) + '%)';
    document.getElementById('ce-damage-depr').textContent = fmtCurrency(depreciation);

    // ── Preset previews ───────────────────────────────────────
    // Residential: 1,800 sqft, hail, TX
    var rSqft = 1800, rDmg = 'hail', rState = 'TX';
    var rBase = DAMAGE_BASES[rDmg].base * (STATE_MULTIPLIERS[rState] || 1.0);
    var rClaim = Math.round(rBase * rSqft);
    var rFee = Math.round(rClaim * FEE_PERCENT);
    document.getElementById('ce-preset-res-claim').textContent = fmtCurrency(rClaim);
    document.getElementById('ce-preset-res-claim').style.color = 'var(--signal-teal)';
    document.getElementById('ce-preset-res-fee').textContent = '3% fee: ' + fmtCurrency(rFee);

    // Commercial: 5,000 sqft, fire, FL
    var cSqft = 5000, cDmg = 'fire', cState = 'FL';
    var cBase = DAMAGE_BASES[cDmg].base * (STATE_MULTIPLIERS[cState] || 1.0);
    var cClaim = Math.round(cBase * cSqft);
    var cFee = Math.round(cClaim * FEE_PERCENT);
    document.getElementById('ce-preset-com-claim').textContent = fmtCurrency(cClaim);
    document.getElementById('ce-preset-com-claim').style.color = 'var(--signal-teal)';
    document.getElementById('ce-preset-com-fee').textContent = '3% fee: ' + fmtCurrency(cFee);

    // Large loss: 8,000 sqft, storm, LA
    var lSqft = 8000, lDmg = 'storm', lState = 'LA';
    var lBase = DAMAGE_BASES[lDmg].base * (STATE_MULTIPLIERS[lState] || 1.0);
    var lClaim = Math.round(lBase * lSqft);
    var lFee = Math.round(lClaim * FEE_PERCENT);
    document.getElementById('ce-preset-lg-claim').textContent = fmtCurrency(lClaim);
    document.getElementById('ce-preset-lg-claim').style.color = 'var(--signal-teal)';
    document.getElementById('ce-preset-lg-fee').textContent = '3% fee: ' + fmtCurrency(lFee);
  }};

  // ── PRESET APPLY ─────────────────────────────────────────────
  window.applyPreset = function(preset) {{
    switch (preset) {{
      case 'residential':
        document.getElementById('ce-slider-sqft').value = 1800;
        document.getElementById('ce-select-damage').value = 'hail';
        document.getElementById('ce-select-state').value = 'TX';
        break;
      case 'commercial':
        document.getElementById('ce-slider-sqft').value = 5000;
        document.getElementById('ce-select-damage').value = 'fire';
        document.getElementById('ce-select-state').value = 'FL';
        break;
      case 'large':
        document.getElementById('ce-slider-sqft').value = 8000;
        document.getElementById('ce-select-damage').value = 'storm';
        document.getElementById('ce-select-state').value = 'LA';
        break;
    }}
    calc();
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
  }};

  // ── INIT ────────────────────────────────────────────────────
  calc();
}})();
</script>

</body>
</html>"""
