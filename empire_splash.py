"""
Empire V49 · Cinematic Splash Gateway
======================================
The entry point. Per V47 spec: "cinematic splash page. The Empire AI logo
fades into the Hub upon 1.5s of focused interaction."

Public route at `/` — operator clicks anywhere (focused interaction) and
1.5s later the hub takes over via fetch + view replace. No flash. No flicker.

Wire-up in hub.py:
    from empire_splash import splash_page

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTMLResponse(splash_page())

    # Move the old master_hub to /command (now reached via splash)
    @app.get("/command", response_class=HTMLResponse)
    async def hub():
        return HTMLResponse(...)
"""

from empire_tokens import empire_head


def splash_page(redirect_to: str = "/command") -> str:
    """
    Returns the cinematic splash HTML.
    `redirect_to` is the URL the splash advances to after 1.5s focus.
    """
    splash_css = """
    html, body {
      height: 100vh;
      overflow: hidden;
      cursor: pointer;
    }

    body {
      display: flex;
      align-items: center;
      justify-content: center;
      background: var(--empire-black);
      position: relative;
    }

    /* Cinematic backdrop — deeper than the normal canvas */
    .splash-canvas {
      position: fixed;
      inset: 0;
      background:
        radial-gradient(ellipse 80% 60% at 30% 30%, rgba(68, 229, 184, 0.08) 0%, transparent 50%),
        radial-gradient(ellipse 80% 60% at 70% 70%, rgba(90, 200, 250, 0.06) 0%, transparent 50%),
        radial-gradient(ellipse at center, var(--empire-canvas) 0%, var(--empire-black) 80%);
      animation: empire-fade-in 1.2s ease-out both;
    }

    /* Particle nodes (the dots in the logo backdrop) */
    .splash-particles {
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0.6;
    }
    .splash-particle {
      position: absolute;
      width: 3px; height: 3px;
      border-radius: 50%;
      background: var(--signal-teal);
      box-shadow: 0 0 8px var(--signal-teal-glow);
      animation: empire-pulse 3s ease-in-out infinite;
    }
    .splash-particle.cyan {
      background: var(--strike-cyan);
      box-shadow: 0 0 8px var(--strike-cyan-glow);
    }

    /* Faint network lines connecting some particles */
    .splash-net {
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0.15;
    }

    /* Center stage */
    .splash-stage {
      position: relative;
      z-index: 2;
      text-align: center;
      animation: empire-fade-up 1.5s 0.3s var(--ease-out-empire) both;
    }

    .splash-mark {
      width: 280px; height: 140px;
      margin: 0 auto 32px;
      position: relative;
    }

    /* The E built from wave + pulse — pure SVG */
    .splash-mark svg {
      width: 100%; height: 100%;
      filter: drop-shadow(0 0 32px rgba(68, 229, 184, 0.3))
              drop-shadow(0 0 64px rgba(90, 200, 250, 0.15));
    }

    .splash-wordmark {
      display: flex;
      align-items: baseline;
      justify-content: center;
      gap: 12px;
      margin-bottom: 8px;
    }
    .splash-empire {
      font-family: var(--font-display);
      font-weight: 700;
      font-size: 42px;
      letter-spacing: 0.32em;
      color: var(--empire-white);
    }
    .splash-ai {
      font-family: var(--font-display);
      font-weight: 700;
      font-size: 42px;
      letter-spacing: 0.32em;
      background: linear-gradient(180deg, var(--signal-teal) 0%, var(--strike-cyan) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .splash-tag {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      letter-spacing: 0.42em;
      text-transform: uppercase;
      margin-bottom: 20px;
    }


    .splash-prompt {
      display: inline-flex;
      align-items: center;
      gap: 12px;
      padding: 12px 24px;
      border: 1px solid var(--empire-border);
      border-radius: var(--radius-pill);
      background: var(--empire-glass);
      backdrop-filter: blur(20px);
      transition: all 0.3s var(--ease-out-empire);
    }
    .splash-prompt:hover {
      border-color: var(--signal-teal);
      box-shadow: var(--glow-soft);
    }
    .splash-prompt-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: var(--signal-teal);
      box-shadow: var(--glow-signal);
      animation: empire-pulse 1.8s ease-in-out infinite;
    }
    .splash-prompt-text {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-silver);
      letter-spacing: 0.18em;
      text-transform: uppercase;
    }

    /* The 1.5s focus progress bar */
    .splash-progress {
      position: fixed;
      bottom: 0; left: 0; right: 0;
      height: 2px;
      background: transparent;
      z-index: 10;
    }
    .splash-progress-fill {
      height: 100%;
      width: 0;
      background: linear-gradient(90deg, var(--signal-teal) 0%, var(--strike-cyan) 100%);
      box-shadow: 0 0 12px var(--signal-teal-glow);
      transition: width 1.5s linear;
    }
    .splash-progress-fill.engaged {
      width: 100%;
    }

    /* Engaged state — wash everything into the canvas */
    body.engaged .splash-canvas {
      animation: splash-warp 0.6s 0.9s var(--ease-out-empire) forwards;
    }
    body.engaged .splash-stage {
      animation: splash-recede 0.8s var(--ease-out-empire) forwards;
    }
    body.engaged .splash-particles {
      animation: splash-disperse 1.2s ease-out forwards;
    }

    @keyframes splash-warp {
      to {
        background: var(--empire-canvas);
        opacity: 0.2;
      }
    }
    @keyframes splash-recede {
      to {
        transform: scale(0.92);
        opacity: 0;
        filter: blur(8px);
      }
    }
    @keyframes splash-disperse {
      to {
        opacity: 0;
        transform: scale(1.4);
      }
    }

    .splash-auth {
      position: fixed;
      top: 20px; right: 24px;
      z-index: 5;
    }
    .splash-auth a {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-fog);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      text-decoration: none;
      padding: 8px 14px;
      border: 1px solid var(--empire-border);
      border-radius: var(--radius-sm);
      transition: all 0.2s var(--ease-out-empire);
    }
    .splash-auth a:hover {
      color: var(--signal-teal);
      border-color: var(--signal-teal);
      box-shadow: var(--glow-soft);
    }

    .splash-foot {
      position: fixed;
      bottom: 24px; left: 0; right: 0;
      text-align: center;
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.32em;
      text-transform: uppercase;
      z-index: 3;
    }
    .splash-foot a {
      color: var(--empire-mist);
      text-decoration: none;
      transition: color 0.2s;
    }
    .splash-foot a:hover {
      color: var(--signal-teal);
    }
    """

    head = empire_head(
        title="Empire AI · Gateway",
        extra=splash_css,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="splash-canvas"></div>

<div class="splash-particles" id="particles" aria-hidden="true"></div>

<svg class="splash-net" id="net" aria-hidden="true" preserveAspectRatio="none"></svg>

<main class="splash-stage" role="main">
  <div class="splash-mark">
    <svg viewBox="0 0 280 140" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Empire AI logo">
      <defs>
        <linearGradient id="wave-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#1FB890"/>
          <stop offset="100%" stop-color="#44E5B8"/>
        </linearGradient>
        <linearGradient id="pulse-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#44E5B8"/>
          <stop offset="100%" stop-color="#5AC8FA"/>
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="2" result="blur"/>
          <feMerge>
            <feMergeNode in="blur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>

      <!-- Wave side (teal flowing curve forming the left of the E) -->
      <path d="M 60 30
               Q 80 25, 100 35
               Q 120 45, 100 60
               Q 80 75, 100 90
               Q 120 105, 100 115
               L 70 115"
            fill="none"
            stroke="url(#wave-grad)"
            stroke-width="7"
            stroke-linecap="round"
            stroke-linejoin="round"
            filter="url(#glow)"/>

      <!-- Pulse side (cyan ECG spike forming the right of the E) -->
      <path d="M 130 70
               L 150 70
               L 158 50
               L 168 95
               L 178 35
               L 188 100
               L 198 60
               L 220 60"
            fill="none"
            stroke="url(#pulse-grad)"
            stroke-width="7"
            stroke-linecap="round"
            stroke-linejoin="round"
            filter="url(#glow)"/>
    </svg>
  </div>

  <div class="splash-wordmark">
    <span class="splash-empire">EMPIRE</span>
    <span class="splash-ai">AI</span>
  </div>
  <div class="splash-tag">Predictive Revenue</div>


  <button class="splash-prompt" type="button" id="splash-engage" aria-label="Enter the empire">
    <span class="splash-prompt-dot"></span>
    <span class="splash-prompt-text">Press anywhere to enter</span>
  </button>
</main>

<div class="splash-auth">
  <a href="/auth/login">Sign in</a>
</div>

<div class="splash-progress">
  <div class="splash-progress-fill" id="progress"></div>
</div>

<div class="splash-foot">
  <a href="https://empire-ai.co.uk">Autonomous Engine</a>
  &nbsp;·&nbsp;
  <a href="/docs">API</a>
</div>

<script>
(function() {{
  // ── Generate ambient particles ──
  const particles = document.getElementById('particles');
  const count = 24;
  for (let i = 0; i < count; i++) {{
    const p = document.createElement('div');
    p.className = 'splash-particle' + (Math.random() > 0.6 ? ' cyan' : '');
    p.style.left = Math.random() * 100 + '%';
    p.style.top = Math.random() * 100 + '%';
    p.style.animationDelay = (Math.random() * 3) + 's';
    p.style.animationDuration = (2 + Math.random() * 3) + 's';
    particles.appendChild(p);
  }}

  // ── Draw network lines between nearby particles ──
  const net = document.getElementById('net');
  const w = window.innerWidth;
  const h = window.innerHeight;
  net.setAttribute('viewBox', `0 0 ${{w}} ${{h}}`);
  const points = [];
  for (let i = 0; i < count; i++) {{
    points.push({{ x: Math.random() * w, y: Math.random() * h }});
  }}
  for (let i = 0; i < points.length; i++) {{
    for (let j = i + 1; j < points.length; j++) {{
      const dx = points[i].x - points[j].x;
      const dy = points[i].y - points[j].y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 200) {{
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', points[i].x);
        line.setAttribute('y1', points[i].y);
        line.setAttribute('x2', points[j].x);
        line.setAttribute('y2', points[j].y);
        line.setAttribute('stroke', '#44E5B8');
        line.setAttribute('stroke-width', '0.5');
        line.setAttribute('opacity', String(1 - dist / 200));
        net.appendChild(line);
      }}
    }}
  }}

  // ── Engagement: 1.5s of focused interaction (V47 spec) ──
  const REDIRECT = {redirect_to!r};
  const progress = document.getElementById('progress');
  const engageBtn = document.getElementById('splash-engage');

  let engaged = false;
  let timer = null;

  function engage() {{
    if (engaged) return;
    engaged = true;
    progress.classList.add('engaged');
    timer = setTimeout(() => {{
      document.body.classList.add('engaged');
      // Wait for the wash-out animation, then navigate
      setTimeout(() => {{ location.href = REDIRECT; }}, 700);
    }}, 1500);
  }}

  function abort() {{
    if (!engaged) return;
    engaged = false;
    progress.classList.remove('engaged');
    clearTimeout(timer);
  }}

  // Engage on any of: click, touch, keypress, focus
  ['mousedown', 'touchstart', 'keydown'].forEach(evt => {{
    document.addEventListener(evt, engage, {{ passive: true, once: false }});
  }});
  ['mouseup', 'touchend'].forEach(evt => {{
    document.addEventListener(evt, abort, {{ passive: true }});
  }});
  engageBtn.addEventListener('focus', engage);
  engageBtn.addEventListener('blur', abort);

  // Auto-skip if the operator already has a session token (returning visitor)
  // — slight delay so they still see the splash for a beat
  const hasSession = localStorage.getItem('hub_token');
  if (hasSession) {{
    setTimeout(() => {{
      document.body.classList.add('engaged');
      setTimeout(() => {{ location.href = REDIRECT; }}, 800);
    }}, 1800);
  }}
}})();
</script>

</body>
</html>"""
