# CURRENT SITE STATUS — 2026-06-22
## Read this before making changes

### BLOCKING ISSUE: Magic link emails not arriving

**The user (philliplivesley@empire-ai.co.uk) cannot sign in because the magic link email never arrives.**

What we know:
- POST /api/v1/auth/login returns `{"ok": true}` — server accepts the request
- Resend API confirms the email was sent (last event: "delivered")
- Email ID from Resend: `5e68eb16-bc7f-4c97-b512-109ac732e6d8`
- Subject: "Empire AI · Your login link"
- Domain `empire-ai.co.uk` is verified in Resend (us-east-1, since 2026-05-03)
- FROM_ADDRESS: `noreply@empire-ai.co.uk`, FROM_NAME: "Empire AI Operations"
- PUBLIC_BASE_URL: `https://empire-ai.co.uk`
- Operator exists in Supabase: philliplivesley@empire-ai.co.uk, role=owner, active=true
- User checked spam — not there either
- Direct magic link generation works (tested server-side): /auth/verify?t=<token> → HTTP 200 "Signed in" page
- The auth verify page was previously crashing (HTTP 500) due to missing `empire_head` import — **this was fixed**

**Likely root cause:** Email delivery issue at the provider level. Resend says "delivered" but the user's email provider (Gmail/Outlook) is silently filtering it. Possible causes:
1. DKIM/SPF/DMARC DNS records for empire-ai.co.uk may be misconfigured or failing
2. The sending IP/reputation may be flagged
3. The email content might look spammy to filters
4. There may be a suppression or block at the recipient's provider

**Suggested next steps to debug:**
1. Check DKIM/SPF/DMARC DNS records for empire-ai.co.uk
2. Try sending to a different email address (Gmail test account)
3. Try a simpler email body (plain text instead of HTML)
4. Check Resend's delivery analytics for bounces/rejections
5. Try using a different sending domain or email provider

### RECENT CHANGES (this session)

1. **Fixed /auth/verify 500 error** — Added `from empire_tokens import empire_head` to `empire_auth.py`. The `_login_page()` and `_verified_page()` functions were calling `empire_head()` without importing it, causing HTTP 500 on magic link verification.

2. **Self-hosted all CDN dependencies** — Zero external CDN calls across the entire site:
   - React 18 + htm: downloaded from esm.sh → `/static/lib/*.mjs` (5 files: react, react-dom, client, htm, scheduler)
   - Headroom.js: downloaded from unpkg → `/static/lib/headroom.min.js`
   - Tabler Icons: downloaded CSS + 3 font files → `/static/lib/tabler-icons/`
   - Google Fonts (Geist, Geist Mono, Inter, JetBrains Mono): downloaded 24 woff2 files → `/static/lib/fonts/`
   - Updated: `empire_command_spa.py`, `empire_fleet_dashboard.py`, `empire_headroom_js.py`, `empire_tokens.py`
   - Removed inline Google Fonts links from 8 portal/email pages

### FILES MODIFIED
- `empire_auth.py` — Added missing import (fixes /auth/verify crash)
- `empire_tokens.py` — EMPIRE_FONTS now uses local CSS files
- `empire_headroom_js.py` — Script src changed to local path
- `empire_fleet_dashboard.py` — Import map uses local /static/lib/ files
- `empire_command_spa.py` — Import map uses local /static/lib/ files (done earlier)
- `empire_advertiser_portal.py` — Updated font link
- `empire_affiliate_portal.py` — Updated font link
- `empire_contractor_portal.py` — Updated font link
- `empire_publisher_portal.py` — Updated font link
- `empire_affiliate_recruit.py` — Updated font link
- `empire_matching.py` — Updated font link
- `empire_partner_onboarding.py` — Updated font link
- `empire_email.py` — Updated _unsub_page font link

### FILES ADDED
- `static/lib/react.mjs`, `static/lib/client.mjs`, `static/lib/htm.mjs`, `static/lib/react-dom.mjs`, `static/lib/scheduler.mjs`
- `static/lib/headroom.min.js`
- `static/lib/tabler-icons/tabler-icons.min.css` + `fonts/` (woff2, woff, ttf)
- `static/lib/fonts/fonts.css` + 24 woff2 files
