"""
EMPIRE V49 · HEADROOM.JS INTEGRATION
=====================================
Auto-hide page headers on scroll down, reveal on scroll up.
Uses headroom.js (WickyNilliams) loaded from unpkg CDN.

CSS classes applied by headroom.js:
  .headroom--pinned    — header is visible (scrolling up)
  .headroom--unpinned  — header is hidden (scrolled down)
  .headroom--top       — header is at the very top of the page
  .headroom--not-top   — header is below the top

Integration:
  from empire_headroom_js import EMPIRE_HEADROOM_CSS, EMPIRE_HEADROOM_JS
  head = empire_head(..., extra=EMPIRE_HEADROOM_CSS)
  # EMPIRE_HEADROOM_JS goes in meta_html or at end of body as <script>
"""

# ── Headroom.js CSS — transitions for the pinned/unpinned states ────────
EMPIRE_HEADROOM_CSS = """
/* Headroom.js — auto-hide header on scroll */
.headroom {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  transition: transform 0.25s var(--ease-out-empire);
  will-change: transform;
}
.headroom--pinned {
  transform: translateY(0);
}
.headroom--unpinned {
  transform: translateY(-100%);
}
.headroom--top {
  /* At the very top — no shadow needed */
}
.headroom--not-top {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
}
""".strip()

# ── Headroom.js script — load + auto-initialize on known Empire selectors ──
EMPIRE_HEADROOM_JS = """
<script src="https://unpkg.com/headroom.js@0.12.0/dist/headroom.min.js"></script>
<script>
(function() {
  if (typeof Headroom === 'undefined') return;

  // Wait for DOM to be fully ready before scanning for header elements
  function initHeadroom() {
    var selectors = [
      '.fleet-topbar',       // Fleet Dashboard
      '.nav',                // Command SPA sidebar
      '.topbar',             // Command SPA top bar
      '.header',             // Agent OS, Outreach
      '.head',               // Generic page header
      '.brand',              // Demo page
    ];

    var headerEl = null;
    for (var i = 0; i < selectors.length; i++) {
      headerEl = document.querySelector(selectors[i]);
      if (headerEl) {
        headerEl.classList.add('headroom');
        var hr = new Headroom(headerEl, {
          tolerance: 5,
          offset: 80,
          classes: {
            initial: 'headroom',
            pinned: 'headroom--pinned',
            unpinned: 'headroom--unpinned',
            top: 'headroom--top',
            notTop: 'headroom--not-top',
          }
        });
        hr.init();
        break;
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHeadroom);
  } else {
    initHeadroom();
  }
})();
</script>
""".strip()
