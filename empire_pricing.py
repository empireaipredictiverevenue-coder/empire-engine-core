"""
EMPIRE V49 · PRICING PAGE
=========================
Standalone public pricing page served at /pricing.
Lists all Empire AI products with tiers, descriptions, and pricing.

Pro tip: uses the Empire design system (empire_tokens) for consistent look.
"""

from empire_tokens import empire_head


def pricing_page() -> str:
    pricing_css = """
    /* ── PAGE SPECIFIC ──────────────────────────────────────────────── */
    .pr-wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 48px 32px 80px;
      position: relative;
      z-index: 1;
    }
    .pr-header {
      text-align: center;
      margin-bottom: 56px;
      animation: empire-fade-up 0.6s var(--ease-out-empire) both;
    }
    .pr-eyebrow {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.32em;
      text-transform: uppercase;
      margin-bottom: 12px;
    }
    .pr-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 44px;
      letter-spacing: -0.04em;
      color: var(--empire-white);
      line-height: 1.1;
      margin-bottom: 16px;
    }
    .pr-title em {
      font-style: italic;
      font-weight: 700;
      color: var(--signal-teal);
    }
    .pr-sub {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      max-width: 640px;
      margin: 0 auto;
      line-height: 1.7;
    }
    .pr-nav {
      display: flex;
      justify-content: center;
      gap: 8px;
      margin-bottom: 48px;
      flex-wrap: wrap;
    }
    .pr-nav-btn {
      padding: 8px 18px;
      font-family: var(--font-mono);
      font-size: 9px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      border: 1px solid var(--empire-border);
      background: transparent;
      color: var(--empire-mist);
      cursor: pointer;
      border-radius: var(--radius-pill);
      transition: all 0.2s var(--ease-snap);
    }
    .pr-nav-btn:hover {
      color: var(--empire-white);
      border-color: var(--empire-border-hi);
    }
    .pr-nav-btn.active {
      color: var(--signal-teal);
      border-color: var(--signal-teal-soft);
      background: var(--signal-teal-soft);
    }

    /* ── SECTION ────────────────────────────────────────────────────── */
    .pr-section {
      margin-bottom: 64px;
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .pr-section:last-child { margin-bottom: 0; }
    .pr-section-h {
      display: flex;
      align-items: baseline;
      gap: 16px;
      margin-bottom: 28px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--empire-divider);
    }
    .pr-section-num {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--signal-teal);
      letter-spacing: 0.12em;
    }
    .pr-section-title {
      font-weight: 500;
      font-size: 20px;
      letter-spacing: -0.02em;
      color: var(--empire-white);
    }
    .pr-section-sub {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.14em;
      text-transform: uppercase;
      margin-left: auto;
    }

    /* ── PRODUCT CARDS (3-column) ───────────────────────────────────── */
    .pr-prods {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }
    .pr-card {
      background: var(--empire-surface);
      border: 1px solid var(--empire-border);
      padding: 28px 24px;
      position: relative;
      overflow: hidden;
      transition: all 0.25s var(--ease-snap);
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .pr-card:hover {
      border-color: var(--signal-teal-soft);
      transform: translateY(-2px);
      box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }
    .pr-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 2px;
      background: linear-gradient(90deg, var(--signal-teal), var(--strike-cyan));
      opacity: 0.6;
    }
    .pr-card-icon {
      width: 36px;
      height: 36px;
      border-radius: var(--radius-sm);
      background: var(--signal-teal-soft);
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 16px;
      font-size: 18px;
      color: var(--signal-teal);
    }
    .pr-card-name {
      font-weight: 600;
      font-size: 17px;
      color: var(--empire-white);
      margin-bottom: 8px;
      letter-spacing: -0.01em;
    }
    .pr-card-desc {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.6;
      margin-bottom: 18px;
    }
    .pr-card-badges {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }
    .pr-bdg {
      display: inline-block;
      padding: 3px 8px;
      font-family: var(--font-mono);
      font-size: 8px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      border-radius: var(--radius-xs);
      border: 1px solid;
    }
    .pr-bdg.teal  { color: var(--signal-teal); border-color: rgba(68,229,184,0.25); background: var(--signal-teal-soft); }
    .pr-bdg.cyan  { color: var(--strike-cyan); border-color: rgba(90,200,250,0.25); background: var(--strike-cyan-soft); }
    .pr-bdg.amber { color: var(--status-amber); border-color: rgba(245,166,35,0.25); background: var(--status-amber-soft); }
    .pr-bdg.muted { color: var(--empire-fog); border-color: var(--empire-divider); }
    .pr-card-features {
      list-style: none;
      padding: 0;
      margin: 0 0 20px;
    }
    .pr-card-features li {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-silver);
      padding: 5px 0;
      border-bottom: 1px solid var(--empire-divider);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .pr-card-features li:last-child { border-bottom: none; }
    .pr-card-features li::before {
      content: '→';
      color: var(--signal-teal);
      font-weight: 700;
      flex-shrink: 0;
    }
    .pr-card-price {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 32px;
      color: var(--signal-teal);
      line-height: 1;
      margin-bottom: 4px;
    }
    .pr-card-price small {
      font-size: 14px;
      color: var(--empire-mist);
      font-weight: 400;
    }
    .pr-card-price-sub {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-fog);
      margin-bottom: 18px;
    }
    .pr-card-cta {
      display: inline-block;
      padding: 10px 22px;
      background: transparent;
      border: 1px solid var(--signal-teal);
      color: var(--signal-teal);
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      cursor: pointer;
      transition: all 0.2s var(--ease-snap);
      text-decoration: none;
      font-weight: 600;
    }
    .pr-card-cta:hover {
      background: var(--signal-teal);
      color: var(--empire-black);
    }

    /* ── TIER TABLE ─────────────────────────────────────────────────── */
    .pr-tier-table {
      width: 100%;
      border-collapse: collapse;
      background: var(--empire-surface);
      border: 1px solid var(--empire-border);
      margin-bottom: 24px;
    }
    .pr-tier-table thead th {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      text-align: left;
      padding: 14px 16px;
      border-bottom: 1px solid var(--empire-divider);
      background: var(--empire-elevated);
      font-weight: 500;
    }
    .pr-tier-table thead th:first-child { border-radius: 0; }
    .pr-tier-table tbody td {
      padding: 14px 16px;
      border-bottom: 1px solid var(--empire-divider);
      font-size: 12px;
      color: var(--empire-silver);
      vertical-align: top;
    }
    .pr-tier-table tbody tr:last-child td { border-bottom: none; }
    .pr-tier-table tbody tr:hover { background: var(--empire-elevated); }
    .pr-tier-name {
      font-weight: 600;
      color: var(--empire-white);
      font-size: 13px;
    }
    .pr-tier-price {
      font-family: var(--font-mono);
      color: var(--signal-teal);
      font-weight: 500;
    }
    .pr-tier-features {
      font-size: 11px;
      line-height: 1.6;
    }
    .pr-tier-bdg {
      display: inline-block;
      font-family: var(--font-mono);
      font-size: 8px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      padding: 2px 7px;
      border-radius: var(--radius-xs);
      border: 1px solid;
      margin-left: 6px;
      vertical-align: middle;
    }
    .pr-tier-bdg.popular {
      color: var(--signal-teal);
      border-color: var(--signal-teal-soft);
      background: var(--signal-teal-soft);
    }
    .pr-tier-bdg.enterprise {
      color: var(--strike-cyan);
      border-color: rgba(90,200,250,0.2);
      background: var(--strike-cyan-soft);
    }

    /* ── STRIKE PACKS GRID ──────────────────────────────────────────── */
    .pr-packs {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
    }
    .pr-pack {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 22px 20px;
      text-align: center;
      transition: all 0.2s var(--ease-snap);
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .pr-pack:hover {
      border-color: var(--strike-cyan-soft);
      transform: translateY(-1px);
    }
    .pr-pack-tier {
      font-family: var(--font-mono);
      font-size: 8px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 8px;
    }
    .pr-pack-tier.standard   { color: var(--empire-mist); }
    .pr-pack-tier.combo      { color: var(--strike-cyan); }
    .pr-pack-tier.whale      { color: var(--signal-teal); }
    .pr-pack-tier.enterprise { color: var(--status-amber); }
    .pr-pack-name {
      font-weight: 600;
      font-size: 15px;
      color: var(--empire-white);
      margin-bottom: 6px;
    }
    .pr-pack-desc {
      font-size: 11px;
      color: var(--empire-mist);
      line-height: 1.5;
      margin-bottom: 14px;
    }
    .pr-pack-price {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 28px;
      color: var(--strike-cyan);
      line-height: 1;
      margin-bottom: 2px;
    }
    .pr-pack-price small {
      font-size: 12px;
      color: var(--empire-fog);
    }
    .pr-pack-ppl {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-fog);
      margin-bottom: 12px;
    }
    .pr-pack-lanes {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      margin-bottom: 12px;
    }
    .pr-pack-channels {
      display: flex;
      gap: 4px;
      justify-content: center;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    .pr-pack-channel {
      font-family: var(--font-mono);
      font-size: 7px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      padding: 2px 6px;
      border-radius: 2px;
      border: 1px solid var(--empire-divider);
      color: var(--empire-fog);
    }

    /* ── FAQ / NOTE ─────────────────────────────────────────────────── */
    .pr-note {
      margin-top: 48px;
      padding: 24px;
      background: var(--empire-surface);
      border: 1px solid var(--empire-border);
      border-left: 3px solid var(--signal-teal);
    }
    .pr-note-title {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--signal-teal);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }
    .pr-note-body {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.7;
      max-width: 720px;
    }
    .pr-note-body a {
      color: var(--signal-teal);
      text-decoration: none;
    }
    .pr-note-body a:hover {
      text-decoration: underline;
    }

    /* ── RESPONSIVE ─────────────────────────────────────────────────── */
    @media (max-width: 900px) {
      .pr-prods { grid-template-columns: 1fr; }
      .pr-packs { grid-template-columns: repeat(2, 1fr); }
      .pr-title { font-size: 32px; }
      .pr-wrap { padding: 32px 20px 60px; }
    }
    @media (max-width: 540px) {
      .pr-packs { grid-template-columns: 1fr; }
    }

    /* ── FOOTER ─────────────────────────────────────────────────────── */
    .pr-foot {
      margin-top: 64px;
      padding-top: 24px;
      border-top: 1px solid var(--empire-divider);
      text-align: center;
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.24em;
      text-transform: uppercase;
    }
    .pr-foot a {
      color: var(--empire-mist);
      text-decoration: none;
      transition: color 0.2s;
    }
    .pr-foot a:hover { color: var(--signal-teal); }
    .pr-foot .sep {
      padding: 0 8px;
      color: var(--empire-shadow);
    }
    """

    head = empire_head(
        title="Empire AI · Pricing & Products",
        extra=pricing_css,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="pr-wrap">

  <!-- HERO -->
  <div class="pr-header">
    <div class="pr-eyebrow">Products & Pricing</div>
    <h1 class="pr-title">Autonomous <em>Revenue</em> Engine</h1>
    <p class="pr-sub">
      Six integrated products powering a closed-loop revenue machine —
      from lead generation and AI-powered outreach to settlement tracking and predictive analytics.
    </p>
  </div>

  <!-- ──────────────────────────────────────────────────────────────────── -->
  <!-- SECTION 1: SUITE PRODUCTS                                          -->
  <!-- ──────────────────────────────────────────────────────────────────── -->
  <div class="pr-section">
    <div class="pr-section-h">
      <span class="pr-section-num">01</span>
      <span class="pr-section-title">Suite Products</span>
      <span class="pr-section-sub">SaaS subscription · per-feature</span>
    </div>

    <div class="pr-prods">

      <!-- Product 1: Inbound Router -->
      <div class="pr-card" style="animation-delay: 0.05s">
        <div class="pr-card-icon"><i class="ti ti-phone-incoming"></i></div>
        <div class="pr-card-name">Inbound Router</div>
        <div class="pr-card-desc">
          Traffic control &amp; intelligent routing for inbound leads.
          Parse intent, score urgency, and dispatch to the right channel.
        </div>
        <div class="pr-card-badges">
          <span class="pr-bdg teal">Router SaaS</span>
          <span class="pr-bdg cyan">API</span>
        </div>
        <ul class="pr-card-features">
          <li>Real-time call triage with AI intent parsing</li>
          <li>Multi-channel dispatch (voice, SMS, email)</li>
          <li>Urgency scoring &amp; priority queuing</li>
          <li>Per-call usage metering</li>
        </ul>
        <div class="pr-card-price">$499 <small>/mo</small></div>
        <div class="pr-card-price-sub">+ $0.25 per routed call</div>
        <a href="/auth/login" class="pr-card-cta">Get started</a>
      </div>

      <!-- Product 2: Data Vault -->
      <div class="pr-card" style="animation-delay: 0.10s">
        <div class="pr-card-icon"><i class="ti ti-database"></i></div>
        <div class="pr-card-name">Data Vault</div>
        <div class="pr-card-desc">
          Secure data retention &amp; asset storage with configurable
          retention policies, encryption, and compliance logging.
        </div>
        <div class="pr-card-badges">
          <span class="pr-bdg teal">Data Enterprise</span>
          <span class="pr-bdg amber">HIPAA-ready</span>
        </div>
        <ul class="pr-card-features">
          <li>Configurable retention policies (30-365 days)</li>
          <li>AES-256 encryption at rest &amp; in transit</li>
          <li>Full audit trail with compliance reporting</li>
          <li>Automated archival &amp; purge workflows</li>
        </ul>
        <div class="pr-card-price">$799 <small>/mo</small></div>
        <div class="pr-card-price-sub">+ $0.02 per stored record/mo</div>
        <a href="/auth/login" class="pr-card-cta">Get started</a>
      </div>

      <!-- Product 3: Buyer Spy AI -->
      <div class="pr-card" style="animation-delay: 0.15s">
        <div class="pr-card-icon"><i class="ti ti-eye"></i></div>
        <div class="pr-card-name">Buyer Spy AI</div>
        <div class="pr-card-desc">
          Network bypass &amp; buyer intelligence. Analyze transcripts,
          map buyer networks, and uncover hidden buying signals.
        </div>
        <div class="pr-card-badges">
          <span class="pr-bdg teal">Spy Data</span>
          <span class="pr-bdg cyan">AI-powered</span>
        </div>
        <ul class="pr-card-features">
          <li>Deep transcript analysis with SI entity extraction</li>
          <li>Buyer network mapping &amp; relationship scoring</li>
          <li>Real-time buying signal detection</li>
          <li>API access for custom integrations</li>
        </ul>
        <div class="pr-card-price">$1,499 <small>/mo</small></div>
        <div class="pr-card-price-sub">+ $5 per analysis</div>
        <a href="/auth/login" class="pr-card-cta">Get started</a>
      </div>

    </div>
  </div>

  <!-- ──────────────────────────────────────────────────────────────────── -->
  <!-- SECTION 2: SUITE TIERS                                              -->
  <!-- ──────────────────────────────────────────────────────────────────── -->
  <div class="pr-section">
    <div class="pr-section-h">
      <span class="pr-section-num">02</span>
      <span class="pr-section-title">Suite Tiers</span>
      <span class="pr-section-sub">All-Access bundles</span>
    </div>

    <table class="pr-tier-table">
      <thead>
        <tr>
          <th>Tier</th>
          <th>Monthly</th>
          <th>Products</th>
          <th>Features</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><span class="pr-tier-name">Router SaaS</span></td>
          <td class="pr-tier-price">$499/mo</td>
          <td><span class="pr-bdg teal">Inbound Router</span></td>
          <td class="pr-tier-features">Up to 500 routed calls/mo · email dispatch · basic analytics</td>
        </tr>
        <tr>
          <td><span class="pr-tier-name">Data Enterprise</span> <span class="pr-tier-bdg popular">Popular</span></td>
          <td class="pr-tier-price">$799/mo</td>
          <td><span class="pr-bdg teal">Data Vault</span></td>
          <td class="pr-tier-features">50K stored records · 90-day retention · compliance audit log</td>
        </tr>
        <tr>
          <td><span class="pr-tier-name">Spy Data</span></td>
          <td class="pr-tier-price">$1,499/mo</td>
          <td><span class="pr-bdg teal">Buyer Spy AI</span></td>
          <td class="pr-tier-features">100 analyses/mo · network mapping · API access</td>
        </tr>
        <tr>
          <td><span class="pr-tier-name">All Access</span> <span class="pr-tier-bdg enterprise">Best Value</span></td>
          <td class="pr-tier-price">$2,499/mo</td>
          <td><span class="pr-bdg teal">All 3 Products</span></td>
          <td class="pr-tier-features">Everything included · priority support · custom SLA · dedicated onboarding</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- ──────────────────────────────────────────────────────────────────── -->
  <!-- SECTION 3: ADVANCED PRODUCTS                                       -->
  <!-- ──────────────────────────────────────────────────────────────────── -->
  <div class="pr-section">
    <div class="pr-section-h">
      <span class="pr-section-num">03</span>
      <span class="pr-section-title">Advanced Products</span>
      <span class="pr-section-sub">Enterprise-grade</span>
    </div>

    <div class="pr-prods">

      <!-- Product 4: Omni Bridge -->
      <div class="pr-card" style="animation-delay: 0.05s">
        <div class="pr-card-icon"><i class="ti ti-bridge"></i></div>
        <div class="pr-card-name">Omni Bridge</div>
        <div class="pr-card-desc">
          End-to-end voice-to-social pipeline. Deepgram STT → AI analysis →
          Zernio social distribution. Close the loop from call to content.
        </div>
        <div class="pr-card-badges">
          <span class="pr-bdg cyan">Premium</span>
          <span class="pr-bdg amber">Add-on</span>
        </div>
        <ul class="pr-card-features">
          <li>Real-time Deepgram speech-to-text</li>
          <li>AI-powered content extraction &amp; summarization</li>
          <li>Auto-publish to Zernio social network</li>
          <li>Analytics dashboard with engagement tracking</li>
        </ul>
        <div class="pr-card-price">$999 <small>/mo</small></div>
        <div class="pr-card-price-sub">+ $0.10 per audio minute processed</div>
        <a href="/auth/login" class="pr-card-cta">Get started</a>
      </div>

      <!-- Product 5: Agent Orchestrator -->
      <div class="pr-card" style="animation-delay: 0.10s">
        <div class="pr-card-icon"><i class="ti ti-robot"></i></div>
        <div class="pr-card-name">Agent Orchestrator</div>
        <div class="pr-card-desc">
          Spawn and manage autonomous AI agents. Define goals, monitor
          execution, and scale your workforce programmatically.
        </div>
        <div class="pr-card-badges">
          <span class="pr-bdg cyan">Premium</span>
          <span class="pr-bdg muted">API-first</span>
        </div>
        <ul class="pr-card-features">
          <li>Declarative agent goal definitions</li>
          <li>Parallel agent execution with dependency resolution</li>
          <li>Step-by-step execution tracing &amp; replay</li>
          <li>Custom tool integration via plugin API</li>
        </ul>
        <div class="pr-card-price">$1,999 <small>/mo</small></div>
        <div class="pr-card-price-sub">+ $0.50 per agent-step executed</div>
        <a href="/auth/login" class="pr-card-cta">Get started</a>
      </div>

      <!-- Product 6: B2B Pro -->
      <div class="pr-card" style="animation-delay: 0.15s">
        <div class="pr-card-icon"><i class="ti ti-building"></i></div>
        <div class="pr-card-name">B2B Pro</div>
        <div class="pr-card-desc">
          Enterprise B2B intelligence — property data, lead marketplace,
          contractor prospecting, and competitive intelligence in one platform.
        </div>
        <div class="pr-card-badges">
          <span class="pr-bdg cyan">Premium</span>
          <span class="pr-bdg teal">Enterprise</span>
        </div>
        <ul class="pr-card-features">
          <li>Commercial property intelligence &amp; valuation</li>
          <li>Lead marketplace with verified buyer network</li>
          <li>Contractor prospecting &amp; trust scoring</li>
          <li>Competitive intelligence feeds</li>
        </ul>
        <div class="pr-card-price">$2,999 <small>/mo</small></div>
        <div class="pr-card-price-sub">+ $10 per lead purchased</div>
        <a href="/auth/login" class="pr-card-cta">Get started</a>
      </div>

    </div>
  </div>

  <!-- ──────────────────────────────────────────────────────────────────── -->
  <!-- SECTION 4: STRIKE PACKS                                             -->
  <!-- ──────────────────────────────────────────────────────────────────── -->
  <div class="pr-section">
    <div class="pr-section-h">
      <span class="pr-section-num">04</span>
      <span class="pr-section-title">Strike Packs</span>
      <span class="pr-section-sub">Per-lead subscriptions · 32 lanes</span>
    </div>

    <p class="pr-sub" style="text-align:left; margin:0 0 28px; font-size:11px;">
      Productized lead lanes targeting specific niches. Each Strike Pack covers a set of lanes
      with configurable daily/monthly caps and delivery channels. Pricing is monthly + per lead delivered.
    </p>

    <div class="pr-packs">

      <!-- Standard -->
      <div class="pr-pack" style="animation-delay: 0.05s">
        <div class="pr-pack-tier standard">Standard</div>
        <div class="pr-pack-name">Roofing Strike</div>
        <div class="pr-pack-desc">Storm-damaged roofing leads in high-risk corridors</div>
        <div class="pr-pack-price">$499 <small>/mo</small></div>
        <div class="pr-pack-ppl">+ $5 per lead</div>
        <div class="pr-pack-lanes">4 lanes · 150 leads/mo cap</div>
        <div class="pr-pack-channels">
          <span class="pr-pack-channel">Email</span>
          <span class="pr-pack-channel">SMS</span>
        </div>
        <a href="/auth/login" class="pr-card-cta" style="font-size:9px; padding:8px 16px;">Subscribe</a>
      </div>

      <!-- Combo -->
      <div class="pr-pack" style="animation-delay: 0.10s">
        <div class="pr-pack-tier combo">Combo</div>
        <div class="pr-pack-name">Property Strike</div>
        <div class="pr-pack-desc">Multi-niche property leads (roofing, siding, gutters, windows)</div>
        <div class="pr-pack-price">$999 <small>/mo</small></div>
        <div class="pr-pack-ppl">+ $8 per lead</div>
        <div class="pr-pack-lanes">8 lanes · 500 leads/mo cap</div>
        <div class="pr-pack-channels">
          <span class="pr-pack-channel">Email</span>
          <span class="pr-pack-channel">SMS</span>
          <span class="pr-pack-channel">Voice</span>
        </div>
        <a href="/auth/login" class="pr-card-cta" style="font-size:9px; padding:8px 16px;">Subscribe</a>
      </div>

      <!-- Whale -->
      <div class="pr-pack" style="animation-delay: 0.15s">
        <div class="pr-pack-tier whale">Whale</div>
        <div class="pr-pack-name">Commercial Strike</div>
        <div class="pr-pack-desc">High-value commercial property leads with API delivery</div>
        <div class="pr-pack-price">$2,999 <small>/mo</small></div>
        <div class="pr-pack-ppl">+ $25 per lead</div>
        <div class="pr-pack-lanes">16 lanes · 2,000 leads/mo cap</div>
        <div class="pr-pack-channels">
          <span class="pr-pack-channel">Email</span>
          <span class="pr-pack-channel">SMS</span>
          <span class="pr-pack-channel">Voice</span>
          <span class="pr-pack-channel">API</span>
        </div>
        <a href="/auth/login" class="pr-card-cta" style="font-size:9px; padding:8px 16px;">Subscribe</a>
      </div>

      <!-- Enterprise -->
      <div class="pr-pack" style="animation-delay: 0.20s">
        <div class="pr-pack-tier enterprise">Enterprise</div>
        <div class="pr-pack-name">Full Spectrum</div>
        <div class="pr-pack-desc">All 32 lanes · unlimited caps · dedicated support</div>
        <div class="pr-pack-price">$7,999 <small>/mo</small></div>
        <div class="pr-pack-ppl">+ $15 per lead</div>
        <div class="pr-pack-lanes">32 lanes · unlimited</div>
        <div class="pr-pack-channels">
          <span class="pr-pack-channel">Email</span>
          <span class="pr-pack-channel">SMS</span>
          <span class="pr-pack-channel">Voice</span>
          <span class="pr-pack-channel">API</span>
          <span class="pr-pack-channel">Webhook</span>
        </div>
        <a href="/auth/login" class="pr-card-cta" style="font-size:9px; padding:8px 16px;">Subscribe</a>
      </div>

    </div>
  </div>

  <!-- ──────────────────────────────────────────────────────────────────── -->
  <!-- SECTION 5: ADDITIONAL NOTES                                        -->
  <!-- ──────────────────────────────────────────────────────────────────── -->
  <div class="pr-note">
    <div class="pr-note-title">Enterprise &amp; Custom Pricing</div>
    <div class="pr-note-body">
      Need custom lane assignments, dedicated SLA tiers (enhanced/premium), webhook delivery,
      or a private API key for programmatic access? All Strike Packs support these features
      out of the box. Contact us at <a href="mailto:ops@empire-ai.co.uk">ops@empire-ai.co.uk</a>
      or sign in to configure your subscription at <a href="/command">the command dashboard</a>.
    </div>
  </div>

  <div class="pr-note" style="margin-top:16px; border-left-color: var(--strike-cyan);">
    <div class="pr-note-title">Revenue Share Model</div>
    <div class="pr-note-body">
      In addition to subscription pricing, Empire AI charges a <strong style="color:var(--empire-white);">3% fee</strong>
      on settled insurance claims facilitated through the platform.
      This per-claim fee covers contractor dispatch, AI-powered negotiation,
      and compliance infrastructure. No settlement, no fee.
    </div>
  </div>

  <!-- FOOTER -->
  <div class="pr-foot">
    <a href="/">Empire AI</a>
    <span class="sep">·</span>
    <a href="/command">Command Dashboard</a>
    <span class="sep">·</span>
    <a href="mailto:ops@empire-ai.co.uk">Contact</a>
    <br>
    <span style="letter-spacing:0.12em; color:var(--empire-shadow); margin-top:8px; display:block;">
      All prices in USD · Subject to change · Enterprise agreements available
    </span>
  </div>

</div>

</body>
</html>"""
