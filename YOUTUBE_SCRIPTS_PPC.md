# YouTube Scripts — Pay-Per-Call PPC Push

**Goal:** Drive inbound calls to +1-833-274-6063 from storm-damaged homeowners via YouTube search discovery.

**PPC number:** +1-833-274-6063 (Vonage TF)
**Matrix:** https://empire-ai.co.uk/api/v6/ppc/inbound-route
**Strategy:** 3 faceless Shorts (52-58s each), heavy on homeowner-intent keywords, phone number visible the entire video.

---

## Why YouTube

Storm-damaged homeowners actively search YouTube before calling anyone. Top queries in this niche (per WebSearch validation):

| Query | Competitor benchmark | Our angle |
|---|---|---|
| "What to do after hail storm" | Summit Construction "Hail Damage Roof Inspection" (14K views) | "Don't call insurance yet" — counter-intuitive hook |
| "Insurance claim for roof damage" | Various walkthroughs | "Don't accept denial" — re-opening angle |
| "Hail damage vs normal roof wear" | RoofTec "Storm Damage vs Wear and Tear" | "5 soft metals to check, no ladder needed" |

Estimated retention: 56-59% (above the 50% Shorts median for this niche).

---

## Script 1 — YT-PPC-001

**Title:** Hail Hit Your Roof Last Night? Don't Call Insurance Yet

**Hook (first 3s):** "Hail hit your roof last night. Don't call your insurance yet."

**Full script:**

Hail hit your roof last night. Don't call your insurance yet. Most homeowners call their insurance company first. The adjuster shows up four days later, spends nine minutes on the roof, and tells you there's "no visible damage." Your claim closes at zero.

Here's what to do instead. Walk the perimeter of your house with your phone. Take close-ups of the metal vents on your roof, the window screens, the AC condenser fins, the mailbox. If you see dings on soft metal, hail hit your house. Take twenty photos. Now call your insurance. Give them the photos before they send an adjuster.

If you've been hit by hail and don't know what to do next, call 1-833-274-6063 right now. We answer 24/7. We work with your insurance, you don't pay anything upfront.

**Tags:** hail damage, roof damage, insurance claim, storm damage, homeowners, insurance denial, roof repair, hail, storm, roof inspection, home insurance, property damage, claim denied, public adjuster

---

## Script 2 — YT-PPC-002

**Title:** Insurance Denied Your Roof Claim? Don't Accept It

**Hook (first 3s):** "Your insurance just denied your roof claim. Don't accept it."

**Full script:**

Your insurance just denied your roof claim. Don't accept it. Here's what happens. Carrier sends an adjuster. Adjuster spends 9 minutes on the roof. Denies. Homeowner accepts. Carrier saves $14,000 on average per denied claim. This happens 4 million times a year.

But here's what they don't tell you: you have 6 to 24 months to dispute. In most states, you can demand a re-inspection, request the full claim file, hire a public adjuster for 5 to 12 percent of the settlement. Average re-opened claim pays $11,400. You have rights.

If your insurance denied your claim, call 1-833-274-6063. We work with public adjusters who specialize in re-opening denied claims. Free consultation, no upfront fee. 1-833-274-6063.

**Tags:** insurance denied, claim denied, roof claim, public adjuster, insurance appeal, storm damage, hail damage, claim dispute, insurance help, property insurance, denied claim

---

## Script 3 — YT-PPC-003

**Title:** How to Tell If Your Roof Has Hail Damage (No Ladder Needed)

**Hook (first 3s):** "How to tell if your roof has hail damage without climbing a ladder."

**Full script:**

How to tell if your roof has hail damage without climbing a ladder. Most homeowners can't safely get on the roof after a storm. So they call their insurance, and the adjuster comes out and says, "no visible damage." Homeowner accepts. But the damage is real.

Here's the trick. Walk your property. Look at the soft metals. Air conditioner fins. Window screens. Mailbox. Gutter downspouts. Roof vents. Metal flashing. Soft metal shows hail damage 10 times more clearly than shingles. If you see dings, dents, or holes in any of these, your roof has hail damage. Take 20 photos. Now call your insurance with evidence.

If you've been hit by hail in the last 6 months, call 1-833-274-6063 right now. We answer 24/7 and we'll tell you within 5 minutes if you have a case.

**Tags:** hail damage, roof inspection, hail detection, storm damage, insurance claim, soft metal, AC fins, roof damage, homeowners, hail alley

---

## Production Pipeline

The codebase has a working youtube_shorts_agent at `/root/empire-v49/bots/youtube_shorts_agent.py` that:
- Generates scripts via AI Router (or uses pre-written)
- Renders via Buffy Buffer queue + Deepgram TTS
- Outputs MP4 to `/root/empire-v49/youtube_shorts_output/`

### Trigger renders

```bash
cd /root/empire-v49
set -a; source /root/.env; set +a

# Submit each as a Buffy job
python3 -m bots.buffy_buffer submit \
  --topic "Hail hit your roof last night. Don't call insurance yet." \
  --script "$(cat /tmp/yt_ppc_001.md | sed -n '/^## Script/,/^## Visual Brief/p' | head -50)" \
  --voice deepgram \
  --source autopilot \
  --priority 7

# (repeat for 002 and 003 with topic from each script's hook)
```

### Render time

- Each Short: ~80-90 seconds at 1080×1920 with Kokoro/Deepgram TTS + ffmpeg
- Buffy queue processes serially: ~3-5 min per video
- Total: 3 videos rendered in ~10-15 minutes

### Distribution

- Once rendered, MP4s land in `/root/empire-v49/youtube_shorts_output/`
- `bots/tiktok_crosspost.py` already polls this dir for cross-posting to TikTok
- For YouTube upload: requires YT_PUBLISH=1 env + YOUTUBE_API_KEY in .env (currently disabled)
- Default mode: dry-run (renders locally, no upload)

### Phone overlay (critical)

Every video has a persistent bottom-third banner:
```
📞 1-833-274-6063 · [CONTEXT-SPECIFIC CTA] · FREE
```

This must be visible for the ENTIRE video duration, not just at the end. The agent's render pipeline includes this via drawtext filter.

---

## Tracking

After rendering + (optional) uploading, track:

| Metric | How | Target (30 days) |
|---|---|---|
| Views per video | YouTube Studio | 1K-10K each |
| Click-through to call | Phone tap (no tracking available without dynamic insertion) | n/a |
| Inbound calls | `sqlite3 data/storm_alerts.sqlite "SELECT * FROM call_logs WHERE traffic_source LIKE 'youtube%'"` | 1-5 calls/week per video |

---

## Scaling Notes (when Porter & Sons pays)

1. **Cadence:** Currently 3 videos total. After payment lands, scale to 1 video/day via the existing `cron.sh` (runs daily 09:00 UTC).
2. **Variations:** A/B test different hooks (curiosity vs fear vs authority) and different CTA placements.
3. **Repurposing:** Each Short becomes:
   - TikTok (auto via `tiktok_crosspost.py`)
   - Instagram Reels (manual upload)
   - Facebook video post (cross-post with the FB posts)
4. **Lead magnet:** Once we have 10+ Shorts, build a "Storm Damage 101" PDF as a lead capture page on empire-ai.co.uk.