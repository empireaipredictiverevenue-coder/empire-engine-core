"""
EMPIRE V49 · YOUTUBE CHANNEL LAUNCH PAGE
==============================================
Public launch page for Empire AI's YouTube channel at /channel.
Embeds the first batch of Shorts, shows live subscriber count
fetched from the YouTube Data API (via /api/v1/youtube/stats),
and displays channel growth metrics.

Wire-up in hub.py:
    from empire_channel_page import channel_page

    @app.get("/channel", response_class=HTMLResponse)
    async def youtube_channel():
        return HTMLResponse(channel_page())
"""

from empire_tokens import empire_head
from empire_structured_data import organization_jsonld, webpage_jsonld

# ── Fallback Shorts data (used when YouTube API is not configured) ──
# NOTE: When YOUTUBE_API_KEY is set, the page's JS fetches live data from
# /api/v1/youtube/stats and replaces these with real video embeds.
# Without the API key, we show a config notice instead of broken embeds.
_FALLBACK_SHORTS = []

_CHANNEL_CSS = """
html, body {
  min-height: 100vh;
  background: var(--empire-black);
  color: var(--empire-white);
}

body {
  display: flex;
  flex-direction: column;
}

/* ── HERO SECTION ── */
.ch-hero {
  position: relative;
  padding: 64px 24px 56px;
  text-align: center;
  overflow: hidden;
  background:
    radial-gradient(ellipse 100% 70% at 30% 20%, rgba(68, 229, 184, 0.08) 0%, transparent 60%),
    radial-gradient(ellipse 80% 60% at 70% 80%, rgba(90, 200, 250, 0.05) 0%, transparent 50%);
}

.ch-hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border: 1px solid rgba(68, 229, 184, 0.2);
  border-radius: var(--radius-pill);
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--signal-teal);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-bottom: 24px;
}

.ch-hero-badge-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--signal-teal);
  box-shadow: var(--glow-signal);
  animation: empire-pulse 1.8s ease-in-out infinite;
}

.ch-hero h1 {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: clamp(32px, 6vw, 56px);
  letter-spacing: -0.03em;
  margin-bottom: 12px;
  background: linear-gradient(180deg, #f4f4f5 0%, #a1a1aa 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.ch-hero h1 em {
  background: linear-gradient(180deg, var(--signal-teal) 0%, var(--strike-cyan) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  font-style: normal;
}

.ch-hero p {
  font-size: 16px;
  color: var(--empire-silver);
  line-height: 1.7;
  max-width: 560px;
  margin: 0 auto 32px;
}

/* ── STATS ROW ── */
.ch-stats {
  display: flex;
  justify-content: center;
  gap: 48px;
  flex-wrap: wrap;
  margin-bottom: 32px;
}

.ch-stat {
  text-align: center;
}

.ch-stat-value {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: 32px;
  letter-spacing: -0.02em;
  color: var(--signal-teal);
  transition: all 0.3s ease;
}

.ch-stat-label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--empire-mist);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  margin-top: 4px;
}



/* ── CTA BUTTON ── */
.ch-cta-row {
  display: flex;
  justify-content: center;
  gap: 12px;
  flex-wrap: wrap;
}

.ch-btn {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 14px 32px;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  text-decoration: none;
  border-radius: var(--radius-sm);
  transition: all 0.25s var(--ease-out-empire);
  cursor: pointer;
}

.ch-btn-primary {
  background: var(--signal-teal);
  color: var(--empire-black);
  border: none;
}

.ch-btn-primary:hover {
  box-shadow: var(--glow-signal);
  transform: translateY(-1px);
}

.ch-btn-secondary {
  background: transparent;
  color: var(--empire-white);
  border: 1px solid var(--empire-border);
}

.ch-btn-secondary:hover {
  border-color: var(--signal-teal);
  color: var(--signal-teal);
  box-shadow: var(--glow-soft);
}

/* ── SHORTS GRID ── */
.ch-shorts-section {
  padding: 48px 24px 64px;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
}

.ch-shorts-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 28px;
  flex-wrap: wrap;
  gap: 12px;
}

.ch-shorts-header h2 {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 22px;
  letter-spacing: -0.02em;
  color: var(--empire-white);
}

.ch-shorts-header h2 span {
  color: var(--signal-teal);
}

.ch-shorts-header .ch-count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--empire-mist);
  letter-spacing: 0.08em;
}

.ch-shorts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.ch-short-card {
  background: var(--empire-glass);
  border: 1px solid var(--empire-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: all 0.3s var(--ease-out-empire);
  animation: empire-fade-up 0.6s var(--ease-out-empire) both;
}

.ch-short-card:nth-child(1) { animation-delay: 0.1s; }
.ch-short-card:nth-child(2) { animation-delay: 0.15s; }
.ch-short-card:nth-child(3) { animation-delay: 0.2s; }
.ch-short-card:nth-child(4) { animation-delay: 0.25s; }
.ch-short-card:nth-child(5) { animation-delay: 0.3s; }
.ch-short-card:nth-child(6) { animation-delay: 0.35s; }

.ch-short-card:hover {
  border-color: rgba(68, 229, 184, 0.3);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3), var(--glow-soft);
  transform: translateY(-2px);
}

.ch-short-embed {
  position: relative;
  width: 100%;
  aspect-ratio: 9 / 16;
  background: #000;
  overflow: hidden;
}

.ch-short-embed iframe {
  width: 100%;
  height: 100%;
  border: none;
}

.ch-short-info {
  padding: 14px 16px;
}

.ch-short-title {
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 500;
  color: var(--empire-white);
  line-height: 1.4;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ch-short-meta {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--empire-mist);
  letter-spacing: 0.06em;
}

.ch-short-meta span {
  color: var(--signal-teal);
}

/* ── ABOUT SECTION ── */
.ch-about {
  padding: 56px 24px 64px;
  border-top: 1px solid var(--empire-border);
  max-width: 800px;
  margin: 0 auto;
  text-align: center;
}

.ch-about h2 {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 24px;
  letter-spacing: -0.02em;
  margin-bottom: 16px;
}

.ch-about p {
  font-size: 14px;
  color: var(--empire-silver);
  line-height: 1.8;
  margin-bottom: 12px;
}

.ch-about-tags {
  display: flex;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 20px;
}

.ch-about-tag {
  padding: 6px 14px;
  border: 1px solid var(--empire-border);
  border-radius: var(--radius-pill);
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-mist);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  transition: all 0.2s ease;
}

.ch-about-tag:hover {
  border-color: var(--signal-teal);
  color: var(--signal-teal);
}

/* ── FOOTER ── */
.ch-footer {
  padding: 32px 24px;
  border-top: 1px solid var(--empire-border);
  text-align: center;
}

.ch-footer-links {
  display: flex;
  justify-content: center;
  gap: 24px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.ch-footer-links a {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--empire-fog);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  text-decoration: none;
  transition: color 0.2s;
}

.ch-footer-links a:hover {
  color: var(--signal-teal);
}

.ch-footer-copy {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-fog);
  letter-spacing: 0.08em;
}

.ch-footer-copy a {
  color: var(--empire-mist);
  text-decoration: none;
}

.ch-footer-copy a:hover {
  color: var(--signal-teal);
}

/* ── SETUP NOTICE (no API key) ── */
.ch-setup-notice {
  grid-column: 1 / -1;
  text-align: center;
  padding: 48px 24px;
  border: 1px dashed var(--empire-border);
  border-radius: var(--radius-md);
  background: rgba(255,255,255,0.01);
}

.ch-setup-notice-icon {
  margin-bottom: 16px;
  opacity: 0.5;
}

.ch-setup-notice-title {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  color: var(--empire-white);
  margin-bottom: 8px;
}

.ch-setup-notice-desc {
  font-size: 13px;
  color: var(--empire-mist);
  line-height: 1.6;
  max-width: 420px;
  margin: 0 auto;
}

.ch-setup-notice-desc code {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--signal-teal);
  background: rgba(68,229,184,0.06);
  padding: 2px 6px;
  border-radius: 3px;
}

/* ── RESPONSIVE ── */
@media (max-width: 640px) {
  .ch-hero {
    padding: 48px 16px 40px;
  }
  .ch-stats {
    gap: 24px;
  }
  .ch-stat-value {
    font-size: 26px;
  }
  .ch-shorts-grid {
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 12px;
  }
  .ch-short-info {
    padding: 10px 12px;
  }
  .ch-short-title {
    font-size: 12px;
  }
}
"""

_CHANNEL_PAGE_SCRIPT = """
(function() {
  // ── Fetch live YouTube stats ──
  var subsEl = document.getElementById('ch-subs');
  var viewsEl = document.getElementById('ch-views');
  var videosEl = document.getElementById('ch-videos');
  var countEl = document.getElementById('ch-count');
  var gridEl = document.getElementById('ch-grid');

  fetch('/api/v1/youtube/stats')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      // Update subscriber count with animation
      var subscribers = data.subscribers || 0;
      var viewsTotal = data.views_total || 0;
      var videosTotal = data.videos_total || 0;

      animateValue(subsEl, subscribers, 1200);
      animateValue(viewsEl, viewsTotal, 1200);
      animateValue(videosEl, videosTotal, 1200);

      // If we have real video IDs from the API, update the grid
      if (data.top_shorts && data.top_shorts.length > 0 && data.configured) {
        if (countEl) {
          countEl.textContent = 'Latest ' + data.top_shorts.length + ' videos';
        }
        if (gridEl) {
          gridEl.innerHTML = '';
          data.top_shorts.forEach(function(video, i) {
            var card = document.createElement('div');
            card.className = 'ch-short-card';
            card.style.animationDelay = (0.1 + i * 0.05) + 's';
            card.innerHTML =
              '<div class="ch-short-embed">' +
              '<iframe src="https://www.youtube.com/embed/' + video.video_id +
              '?rel=0&modestbranding=1&playsinline=1" ' +
              'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" ' +
              'allowfullscreen loading="lazy"></iframe></div>' +
              '<div class="ch-short-info">' +
              '<div class="ch-short-title">' + escapeHtml(video.title) + '</div>' +
              '<div class="ch-short-meta">Published <span>' +
              formatDate(video.published) + '</span></div></div>';
            gridEl.appendChild(card);
          });
        }
      }
    })
    .catch(function(err) {
      // Already have fallback data rendered; just keep it
    });

  // ── Animated counter ──
  function animateValue(el, target, duration) {
    if (!el) return;
    var start = 0;
    var startTime = null;
    var suffix = el.getAttribute('data-suffix') || '';

    function step(timestamp) {
      if (!startTime) startTime = timestamp;
      var progress = Math.min((timestamp - startTime) / duration, 1);
      // Cubic ease-out
      var eased = 1 - Math.pow(1 - progress, 3);
      var current = Math.floor(start + (target - start) * eased);

      // Format with commas
      el.textContent = current.toLocaleString() + suffix;

      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        el.textContent = target.toLocaleString() + suffix;
      }
    }
    requestAnimationFrame(step);
  }

  // ── Helpers ──
  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function formatDate(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  }
})();
"""


def channel_page() -> str:
    """Return the YouTube channel launch page HTML."""

    head = empire_head(
        title="Empire AI · YouTube Channel",
        extra=_CHANNEL_CSS,
        page="channel",
        meta_html=(
            organization_jsonld()
            + webpage_jsonld(
                "Empire AI YouTube Channel",
                "Empire AI's YouTube channel — AI-powered storm detection, lead generation for contractors, and restoration industry insights. Watch our Shorts and subscribe.",
                "https://empire-ai.co.uk/channel",
            )
        ),
    )

    # Build the Shorts grid HTML (placeholder cards — live data replaces via JS)
    # When YouTube API is not configured, show a config notice
    shorts_html = ""
    if not _FALLBACK_SHORTS:
        shorts_html = """
<div class="ch-setup-notice">
  <div class="ch-setup-notice-icon">
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#44E5B8" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  </div>
  <div class="ch-setup-notice-title">No videos loaded yet</div>
  <div class="ch-setup-notice-desc">Set <code>YOUTUBE_API_KEY</code> and <code>YOUTUBE_CHANNEL_ID</code> in your environment to enable live Shorts embeds and subscriber stats. New videos will appear here automatically once published.</div>
</div>"""
    else:
        for i, short in enumerate(_FALLBACK_SHORTS):
            delay = 0.1 + i * 0.05
            shorts_html += f"""<div class="ch-short-card" style="animation-delay:{delay}s">
  <div class="ch-short-embed">
    <iframe src="https://www.youtube.com/embed/{short['video_id']}?rel=0&modestbranding=1&playsinline=1"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowfullscreen loading="lazy"></iframe>
  </div>
  <div class="ch-short-info">
    <div class="ch-short-title">{short['title']}</div>
    <div class="ch-short-meta"><span>{short['views']}</span> views</div>
  </div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<!-- ═══════════════ HERO ═══════════════ -->
<section class="ch-hero">
  <div class="ch-hero-badge">
    <span class="ch-hero-badge-dot"></span>
    Empire AI Channel
  </div>

  <h1>Storm Revenue <em>TV</em></h1>

  <p>AI-powered storm detection, contractor lead generation, and restoration industry insights — in 60-second Shorts. New every week.</p>

  <div class="ch-stats">
    <div class="ch-stat">
      <div class="ch-stat-value" id="ch-subs" data-suffix="">--</div>
      <div class="ch-stat-label">Subscribers</div>
    </div>
    <div class="ch-stat">
      <div class="ch-stat-value" id="ch-views" data-suffix="">--</div>
      <div class="ch-stat-label">Total Views</div>
    </div>
    <div class="ch-stat">
      <div class="ch-stat-value" id="ch-videos" data-suffix="">--</div>
      <div class="ch-stat-label">Videos</div>
    </div>
  </div>

  <div class="ch-cta-row">
    <a class="ch-btn ch-btn-primary" href="https://youtube.com/@EmpireAI?sub_confirmation=1" target="_blank" rel="noopener">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19.615 3.184c-3.604-.246-11.631-.245-15.23 0C.488 3.45.029 5.804 0 12c.029 6.185.484 8.549 4.385 8.816 3.6.245 11.626.246 15.23 0C23.512 20.55 23.971 18.196 24 12c-.029-6.185-.484-8.549-4.385-8.816zM9 16V8l8 4-8 4z"/></svg>
      Subscribe
    </a>
    <a class="ch-btn ch-btn-secondary" href="/products/elite-scraper">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      Explore Products
    </a>
  </div>
</section>

<!-- ═══════════════ SHORTS GRID ═══════════════ -->
<section class="ch-shorts-section">
  <div class="ch-shorts-header">
    <h2>Latest <span>Shorts</span></h2>
    <div class="ch-count" id="ch-count">Loading...</div>
  </div>
  <div class="ch-shorts-grid" id="ch-grid">
    {shorts_html}
  </div>
</section>

<!-- ═══════════════ ABOUT ═══════════════ -->
<section class="ch-about">
  <h2>What is Empire AI?</h2>
  <p>Empire AI is a predictive revenue network that uses artificial intelligence to detect severe weather events, identify affected properties, and deliver qualified leads to restoration contractors — all in real-time.</p>
  <p>Our YouTube channel covers storm science, contractor tips, industry insights, and behind-the-scenes looks at the AI systems powering the modern restoration industry.</p>

  <div class="ch-about-tags">
    <span class="ch-about-tag">Storm Damage</span>
    <span class="ch-about-tag">Lead Generation</span>
    <span class="ch-about-tag">AI Technology</span>
    <span class="ch-about-tag">Contractor Tips</span>
    <span class="ch-about-tag">Restoration</span>
    <span class="ch-about-tag">Insurance Claims</span>
  </div>
</section>

<!-- ═══════════════ FOOTER ═══════════════ -->
<footer class="ch-footer">
  <div class="ch-footer-links">
    <a href="/">Empire AI</a>
    <a href="/products/elite-scraper">Products</a>
    <a href="https://youtube.com/@EmpireAI" target="_blank" rel="noopener">YouTube</a>
    <a href="/pricing">Pricing</a>
    <a href="/support">Support</a>
  </div>
  <div class="ch-footer-copy">
    &copy; 2026 <a href="https://empire-ai.co.uk">Empire AI</a> &nbsp;·&nbsp; Predictive Revenue Network
  </div>
</footer>

<script>{_CHANNEL_PAGE_SCRIPT}</script>
</body>
</html>"""


# ── STATS API (used by the page's JS fetch) ──
# The page fetches /api/v1/youtube/stats for live subscriber count + video data.
# This endpoint is already registered by empire_youtube_stats.py in hub.py.
# If YOUTUBE_API_KEY/YOUTUBE_CHANNEL_ID aren't set, the stats endpoint returns
# a stubbed response and the page gracefully shows the fallback Shorts grid.
