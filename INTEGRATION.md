EMPIRE V49 · INTEGRATION GUIDE
================================

Drop these four new modules into the same directory as hub.py:
  - empire_tokens.py       (PR 1 · design system)
  - empire_layout.py       (PR 2 · shared chrome)
  - empire_live.py         (PR 3 · WebSocket broadcaster)
  - empire_splash.py       (PR 4 · cinematic gateway)
  - empire_command_deck.py (PR 4 · new Owner Mode flagship)

Then make these surgical edits to hub.py. Backend logic is NOT touched.
Only the presentation layer + a few startup hooks.


───────────────────────────────────────────────────────────────────────────────
STEP 1 · IMPORTS (top of hub.py, after existing imports)
───────────────────────────────────────────────────────────────────────────────

    # Empire V49 modules
    from empire_tokens import EMPIRE_TOKENS_CSS, EMPIRE_BASE_CSS, EMPIRE_COMPONENTS_CSS, EMPIRE_FONTS, empire_head
    from empire_layout import base_layout, standalone_layout
    from empire_live import live_broadcaster, websocket_endpoint, stats_heartbeat
    from empire_splash import splash_page
    from empire_command_deck import command_deck_view
    import empire_live


───────────────────────────────────────────────────────────────────────────────
STEP 2 · INJECT AUTH TOKEN INTO LIVE MODULE (right after HUB_TOKEN is defined)
───────────────────────────────────────────────────────────────────────────────

    HUB_TOKEN = os.environ.get("HUB_SECRET_TOKEN", "Empire_Alpha_99")

    # Empire V49 — share auth with the live broadcaster
    empire_live.HUB_TOKEN = HUB_TOKEN


───────────────────────────────────────────────────────────────────────────────
STEP 3 · REGISTER WEBSOCKET (anywhere after `app = FastAPI()`)
───────────────────────────────────────────────────────────────────────────────

    # Empire V49 — live broadcast WebSocket
    app.add_api_websocket_route("/ws/live", websocket_endpoint)


───────────────────────────────────────────────────────────────────────────────
STEP 4 · START HEARTBEAT (add inside @app.on_event("startup"))
───────────────────────────────────────────────────────────────────────────────

Inside the existing _startup_subconscious() function, ADD this line:

    @app.on_event("startup")
    async def _startup_subconscious():
        if SUBCONSCIOUS_ENABLED:
            asyncio.create_task(subconscious_loop())
        else:
            print("[subconscious] disabled via SUBCONSCIOUS_ENABLED=0")

        if SOLANA_WATCH_ENABLED:
            asyncio.create_task(watch_revenue())
        else:
            print("[solana]       Revenue watcher disabled via SOLANA_WATCH_ENABLED=0")

        # ────────────────────────────────────────────────────────────
        # Empire V49 — live broadcast heartbeat
        # ────────────────────────────────────────────────────────────
        asyncio.create_task(stats_heartbeat(
            lambda: SUBCONSCIOUS_STATE,
            lambda: SOLANA_STATE,
        ))
        print("[live]         WebSocket broadcaster: ONLINE · /ws/live")


───────────────────────────────────────────────────────────────────────────────
STEP 5 · BROADCAST EVENTS FROM THE SUBCONSCIOUS LOOP
───────────────────────────────────────────────────────────────────────────────

Find the section inside _subconscious_cycle() where a strike is detected
(around the `# STRIKE` comment, right after `strikes += 1`). Add this AFTER
the existing strike_log insert:

                    # Empire V49 — broadcast to live dashboards
                    await live_broadcaster.broadcast({
                        "type":     "strike",
                        "target":   p["address"],
                        "event":    alert["event"],
                        "severity": severity,
                        "area":     alert["area"],
                        "distance": round(dist, 1),
                    })

And inside the brain decision block, right after the SUBCONSCIOUS_STATE update
that sets last_decision, ADD:

                        # Empire V49 — push brain decision to live dashboards
                        await live_broadcaster.broadcast({
                            "type":      "brain",
                            "decision":  analysis["decision"],
                            "target":    p.get("address", ""),
                            "urgency":   analysis.get("urgency", 0),
                            "reasoning": analysis.get("reasoning", ""),
                            "asset_value": asset_val_num,
                        })


───────────────────────────────────────────────────────────────────────────────
STEP 6 · BROADCAST REVENUE EVENTS FROM SOLANA WATCHER
───────────────────────────────────────────────────────────────────────────────

Inside _solana_cycle(), find the block where SOLANA_STATE["last_transfer"]
is set. Right after that block, ADD:

                # Empire V49 — push to live dashboards
                await live_broadcaster.broadcast({
                    "type": "settlement",
                    "transfer": {
                        "amount": round(usdc_in, 4),
                        "sig":    sig,
                        "ts":     datetime.now(timezone.utc).isoformat(),
                    },
                })


───────────────────────────────────────────────────────────────────────────────
STEP 7 · SWAP THE ROOT ROUTE TO THE CINEMATIC SPLASH
───────────────────────────────────────────────────────────────────────────────

REPLACE the existing @app.get("/", response_class=HTMLResponse) function
(the master_hub function — about 250 lines) with these two clean routes:

    # ─────────────────────────────────────────────────────────────────────
    # ROOT — Cinematic Splash Gateway (V47 spec)
    # ─────────────────────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def splash():
        """Cinematic splash. 1.5s focused interaction → /command."""
        return HTMLResponse(content=splash_page(redirect_to="/command"))


    # ─────────────────────────────────────────────────────────────────────
    # /command — Cinematic Command Deck (Owner Mode, V49 flagship)
    # ─────────────────────────────────────────────────────────────────────
    @app.get("/command", response_class=HTMLResponse)
    async def command_deck(token: str = Query("")):
        """The new flagship. Replaces the old master_hub shell."""
        return HTMLResponse(content=command_deck_view(token=token))


    # The OLD master_hub view is preserved at /hub for transition continuity.
    # After 7 days of confirmed Command Deck stability, this route can be deleted.
    @app.get("/hub", response_class=HTMLResponse)
    async def legacy_hub():
        """Legacy V47 hub. Will be removed after V49 burn-in."""
        # ... keep the OLD master_hub HTML here unchanged for now ...


───────────────────────────────────────────────────────────────────────────────
STEP 8 · WIRE EXISTING VIEWS TO base_layout() (optional, recommended)
───────────────────────────────────────────────────────────────────────────────

This is the PR 2 payoff. Each of the 8 view functions currently rebuilds its
own <head>, sidebar, and ticker — about 50 lines of duplicated HTML each.

Refactor pattern (example for view_scout):

OLD (the current /view/scout):
    @app.get("/view/scout", response_class=HTMLResponse)
    async def view_scout(token: str = Query("")):
        return HTMLResponse(content=f'''<!DOCTYPE html>
        <html lang="en"><head><meta charset="UTF-8">{VIEW_CSS}</head>
        <body>
        <div class="page">
          <div class="page-header">...</div>
          ...everything...
        </div>
        <script>...</script>
        </body></html>''')

NEW (using base_layout):
    @app.get("/view/scout", response_class=HTMLResponse)
    async def view_scout(token: str = Query("")):
        content = '''
        <div class="e-page">
          <div class="e-page-header">
            <div>
              <div class="e-page-title"><em>Warp</em> Scout</div>
              <div class="e-page-sub">NWS Live Radar · TX OK FL GA NC · 60s refresh</div>
            </div>
            <div class="e-pulse-pill"><span class="e-pulse-dot"></span><span>Scanning</span></div>
          </div>
          <div class="e-grid e-grid-3">
            <div class="e-stat teal"><div class="e-stat-label">Active Alerts</div><div class="e-stat-value teal" id="s-alerts">—</div></div>
            <div class="e-stat cyan"><div class="e-stat-label">Targets Tracked</div><div class="e-stat-value" id="s-permits">—</div></div>
            <div class="e-stat amber"><div class="e-stat-label">Locks Acquired</div><div class="e-stat-value amber" id="s-locks">—</div></div>
          </div>
          <div id="radar-feed" style="margin-top:20px;"></div>
        </div>
        '''

        extra_js = '''<script>
        // ...same scanSky() and event handlers from before, but using
        // window.EMPIRE_TOKEN instead of an inlined TOKEN constant...
        </script>'''

        return HTMLResponse(base_layout(
            title="Warp Scout",
            content=content,
            active_module="scout",
            extra_js=extra_js,
        ))

The VIEW_CSS constant (~150 lines at the bottom of hub.py) can be deleted
entirely once all 8 views are migrated.


───────────────────────────────────────────────────────────────────────────────
STEP 9 · DEPLOY ON DOKKU
───────────────────────────────────────────────────────────────────────────────

Once the patch is in and you've tested locally, deploy to Hetzner.

On your Hetzner box (one-time setup):
    wget -NP . https://dokku.com/install/v0.34.0/bootstrap.sh
    sudo DOKKU_TAG=v0.34.0 bash bootstrap.sh

    # Create the apps
    dokku apps:create empire-ai-uk
    dokku apps:create nationalstormhub

    # Wire domains
    dokku domains:add empire-ai-uk empire-ai.co.uk
    dokku domains:add empire-ai-uk www.empire-ai.co.uk
    dokku letsencrypt:enable empire-ai-uk

    # Set environment variables (run these against EACH app as appropriate)
    dokku config:set empire-ai-uk \\
      SUPABASE_URL=... \\
      SUPABASE_SERVICE_KEY=... \\
      ANTHROPIC_API_KEY=... \\
      HUB_SECRET_TOKEN=... \\
      NTFY_TOPIC=... \\
      RESEND_API_KEY=... \\
      VONAGE_NUMBER=... \\
      EMPIRE_VAULT_WALLET=egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM

    # Allow WebSockets through the nginx proxy (Dokku does this by default
    # but verify; if needed:
    dokku proxy:report empire-ai-uk

On your dev machine:
    cd /path/to/empire-revenue-pulse
    git remote add dokku dokku@your-hetzner-ip:empire-ai-uk
    git push dokku main

That's it. Dokku reads the Procfile, builds the image, and live-deploys.
Subsequent updates: just `git push dokku main`.
