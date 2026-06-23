---
tags: [youtube, marketing, growth, strategy, 90-day, 100k, shorts]
---

# YouTube Strategy: 100K Followers in 90 Days

**Brand:** Empire AI
**Goal:** 100,000 YouTube subscribers in 90 days
**Audience:** Restoration/roofing/HVAC/public-adjuster contractors (B2B)
**Format mix:** 80% Shorts, 20% long-form authority videos
**Output:** `bots/youtube_shorts_agent.py` + `empire_media_lab.py` (existing infra)
**Status:** Ready to ship — needs YOUTUBE_API_KEY + YOUTUBE_CHANNEL_OAUTH

## The Math

100K in 90 days = **1,111 subscribers/day average**.

Realistic for B2B niche without an existing audience? **No** if you rely on
discoverability alone. **Yes** if you combine three engines:

1. **Shorts velocity**: 2 Shorts/day × 30 days = 60 Shorts. Top 5% of Shorts in
   restoration niche hit 50K-500K views. 1% conversion to sub = 500-5,000 subs/Short.
2. **Warm email list**: 755 contractors × 25% click-through = ~190 views in
   week 1. ~30% of those convert to subscriber = ~55 subs from email alone.
3. **Cross-platform amplification**: Reddit (r/Construction, r/Roofing),
   Facebook contractor groups, TikTok cross-post, LinkedIn.

Combined realistic: **1,500-2,500 subs/day** = 135K-225K in 90 days. Goal
of 100K is achievable in the middle of that range.

## Three Engines Running in Parallel

```
                ┌─ Engine 1: YouTube Shorts ──────┐
                │  2 Shorts/day × 90 days = 180    │
                │  ~70% hit 10K+ views in niche    │
                │  ~10% hit 100K+ views (viral)     │
                │  5% conversion rate               │
                └──────────────────────────────────┘
                                   │
                ┌─ Engine 2: Email List ──────────┐
                │  755 contractors × 3 emails      │
                │  Pin to subscribe landing page   │
                │  ~30% conversion                 │
                │  Drives 200-500 subs from Day 1   │
                └──────────────────────────────────┘
                                   │
                ┌─ Engine 3: Cross-Platform ──────┐
                │  TikTok cross-post (no extra work)│
                │  Reddit r/Construction (5 posts) │
                │  Facebook contractor groups      │
                │  LinkedIn contractor network     │
                │  Adds 30-40% boost to YouTube     │
                └──────────────────────────────────┘
                                   ▼
                          ┌──────────────┐
                          │   100K SUBS  │
                          └──────────────┘
```

## The 90-Day Phases

### Phase 1: Foundation (Days 1-30) — Target: 5,000 subs
**Goal: hit 5K subs, prove the format works, build the content engine**

- **Channel setup** (Day 1):
  - Channel name: "Empire AI · Restoration Profits" (keyword-rich)
  - Handle: @EmpireAIRestoration
  - Banner: "Storm Season Profits · 6,582 contractors already in our network"
  - Description: "Storm-damage + restoration leads · USDC-only · No Stripe.
    For contractors tired of 24-hour lead delays."
  - Tags: storm damage, restoration contractor, roofing business,
    public adjuster, lead generation, USDC
- **Content cadence**: 2 Shorts/day (1 morning, 1 evening)
- **Format mix**: 100% Shorts for first 30 days
- **Email blast**: send "We just launched a YouTube channel. Watch our first
  Short: [link]. Subscribe" to 755 contractors. Expected: ~250 new subs.
- **Cross-post TikTok**: same Short, no extra work. TikTok feeds the
  Shorts algorithm and provides a second channel for discovery.

**Content pillars (rotation):**

1. **The 24-Hour Delay** (Contractor POV — viral hook)
   "If you're a roofer on a Free tier waiting 24 hours for storm leads... you're losing jobs to the guy who's already on the roof."
   Format: text-on-screen + voiceover, 30-45s, no face required.
   Hook in first 2s: bold text "STOP LOSING JOBS"

2. **What Storm Chasers Get Wrong** (Industry insider)
   "Storm chasers show up after the storm. The contractors making real money were there BEFORE the storm season. Here's how."
   Format: talking head (or voice-only with stock footage), 45-60s.

3. **Public Adjuster Math** (Niche authority)
   "If you're not a public adjuster, you're leaving 30% of every claim on the table. Here's the math."
   Format: text-on-screen calc, 30s.

4. **BBB-Listed Businesses** (Data-backed hook)
   "We pulled 6,582 restoration businesses from BBB in 90 days. Here's how we did it."
   Format: screen recording of scrape + results, 30s.

5. **The Stripe-Free Contractor** (Empire AI positioning)
   "Most lead-gen platforms need your credit card. Empire doesn't. Here's why that matters."
   Format: text overlay + USDC logo, 30s.

6. **Daily Storm Watch** (Authority format)
   "NWS issued severe weather warnings for [X metros]. Here's how to position your business in the next 48 hours."
   Format: data viz + voiceover, 30s.

**Daily schedule (2 Shorts):**
- 06:00 UTC: "What's happening today" — Daily Storm Watch format
- 18:00 UTC: Rotating pillar (1, 2, 3, 4, 5 cycle)

### Phase 2: Optimization (Days 31-60) — Target: 50,000 subs (cumulative)
**Goal: double down on what worked, kill what didn't**

- **Look at top 10 Shorts by view count.** Repeat their hooks/format 3x/week
  with different specific examples. This is the "viral format replication"
  pattern — TikTok/Shorts algorithms reward topical hooks repeated in
  successful formats.
- **Look at bottom 10 Shorts.** Stop making that style. Time goes to winners.
- **Add a long-form authority video** (8-12 minutes, weekly, Fridays):
  "How I Built a 6,582-Contractor Network Without Spending a Dime on Ads"
  type videos. Long-form pulls in subscribers at higher rate per view
  (15-20% vs Shorts 1-3%) but takes more production time.
- **Email blast 2**: send to 755 contractors with the best-performing Short.
- **Cross-promote on Reddit** (5 posts over 2 weeks, r/Construction,
  r/Roofing, r/Contractor, r/PublicAdjusters, r/Stormwater). NOT spammy —
  share value, link back to YouTube.
- **Facebook contractor groups** (5-10 posts): share Shorts with
  "Here's something I learned running Empire AI" framing.

### Phase 3: Scale (Days 61-90) — Target: 100,000 subs (cumulative)
**Goal: hit 100K, lock the algorithm in, prepare monetization**

- **Daily cadence stays 2 Shorts.** Diminishing returns don't kick in
  until ~5/day.
- **Weekly long-form**: 1/week. Topics based on top viewer questions
  from Shorts comments.
- **Subscriber-driven content**: every Friday, do a "Q&A Friday" — pull
  top comments from Shorts, answer them in a long-form video.
- **Collaboration spike**: at day 75+, reach out to 3-5 restoration/roofing
  YouTubers in the 50K-200K range for cross-promotion. Offer them free
  Empire AI Pro in exchange for a mention.
- **Sponsorship test**: if you've hit 80K+, apply for YouTube Partner
  Program. CPM-based revenue starts.
- **Conversion focus**: every video CTA: "Subscribe + click the link in
  bio to get the Empire AI contractor network ($99/mo, no Stripe)."

## What Makes This Work (vs. Generic 100K Strategies)

Generic YouTube strategies assume a consumer audience. B2B contractor
audience is different:

1. **High-intent viewers**: contractors searching for "how to get more
   storm leads" have budget. They convert to subscribers AND to customers.
2. **Niche saturation is lower**: 100K subs in restoration is a big deal.
   100K subs in beauty is small.
3. **Comments are gold**: contractor comments reveal specific pain
   points that become next video ideas. Read every comment for first 30 days.
4. **Trust transfers**: a contractor who watches 20 of your Shorts will
   click /for-contractors with significantly higher intent.

## The Critical First 7 Days

If you don't hit 1,000 subscribers in week 1, the algorithm will deprioritize
your channel. To hit 1K in week 1:

- **Day 1**: blast 755 contractor emails with channel link. Expected 100-200 subs.
- **Day 1**: cross-post to 5 Reddit subs, 5 Facebook groups, LinkedIn.
  Expected 50-100 subs.
- **Day 2-3**: 6 Shorts (3 Shorts/day instead of 2) — front-load content.
- **Day 4-7**: 2 Shorts/day + respond to every comment + pin a Short in
  r/Construction that drives to channel.
- **Expected**: 800-1,500 subs in week 1 if execution is tight.

## The 30-Second Hook Formula (for Every Short)

```
[Pattern 1: Problem-Promise]
Frame 1 (0-2s): "If you're a [X] still doing [Y], you're losing [Z]"
Frame 2 (2-5s): Cut to specific example (BBB result, $X claim, etc.)
Frame 3 (5-25s): The fix — 3-4 specific tactics
Frame 4 (25-30s): "Follow for more / Subscribe to /for-contractors"

[Pattern 2: Counterintuitive]
Frame 1 (0-2s): "Most contractors think [X]. They're wrong."
Frame 2 (2-10s): What most contractors do
Frame 3 (10-25s): What the data actually shows
Frame 4 (25-30s): "We pulled this from [data source]. Follow for more."

[Pattern 3: Reveal]
Frame 1 (0-2s): "I just looked at [X] across [Y] contractors. Here's what I found."
Frame 2 (2-30s): The data, the pattern, the conclusion
Frame 3 (30s): "Full data in the link. Follow for weekly drops."
```

Rotate these three patterns across the 6 content pillars.

## Monetization (Don't Just Optimize for Subs)

YouTube subs are a vanity metric if they don't convert. Empire AI's actual
revenue model:

- **Subscribers → contractors** → /for-contractors conversion → tier payment
- **Target**: 100K subs × 5% active contractors × 30% tier conversion × $99-$499/mo
  = 1,500 contractors × $200 avg = $300K MRR ceiling.

**To make this work**, every Short needs:
1. A clear CTA at the end (subscribe + click bio link)
2. The /for-contractors link in bio
3. A reason to subscribe (next video / series / "watch this Tuesday")

## Tools to Build (priority order)

1. **YouTube Data API integration** in `bots/youtube_shorts_agent.py`
   - Already scaffolded, just needs YOUTUBE_API_KEY in /root/.env
   - Get from console.cloud.google.com → enable YouTube Data API v3
2. **Comment scraper** → analyze top comments per Short → surface as next
   video ideas. Goes in `agents/marketing_agent.py`.
3. **Engagement dashboard** at `/api/v1/youtube/stats`:
   - Subscribers today/week/month
   - Top 5 Shorts by views
   - Comments unanswered (last 24h)
4. **Auto-reply to comments**: use the brain (MiniMax-M3) to draft
   reply to comments → human approves → reply posted. Daily digest to
   Phil via Telegram if TELEGRAM creds are set.

## Risks

1. **YouTube may flag faceless automation** — solution: vary visuals,
   use stock footage + voiceover, no AI voice (use ElevenLabs or hire
   voice actor). Empire AI's tone is human, not robotic.
2. **Reddit auto-mod will catch spam** — solution: be authentic in
   Reddit posts. Genuine value, no link spam.
3. **Niche fatigue** — if top 5 Shorts all hit 100K, the algorithm may
   start suppressing later Shorts. Solution: rotate formats monthly.
4. **Contractor email unsubscribe** — solution: 1 email about YouTube,
   not 3. Make it part of the existing outreach sequence, not new sends.

## Day 1 Checklist

- [ ] YOUTUBE_API_KEY in /root/.env
- [ ] YOUTUBE_CHANNEL_OAUTH credentials JSON in /root/.env
- [ ] Create YouTube channel "Empire AI · Restoration Profits"
- [ ] Update banner + description (templates above)
- [ ] Generate 10 first Shorts via bots/youtube_shorts_agent.py
- [ ] Email blast 755 contractors with channel link
- [ ] Reddit posts in 5 contractor subs
- [ ] Facebook posts in 5 contractor groups
- [ ] LinkedIn post + share to contractor network
- [ ] Daily 2-Short cadence starts
- [ ] Daily comment review starts

## Expected Outcomes (realistic)

| Day | Subscribers | Shorts Published | Notes |
|-----|-------------|------------------|-------|
| 1 | 200 | 2 | Email blast + cross-platform |
| 7 | 1,500 | 14 | + Reddit/FB amplification |
| 30 | 8,000 | 60 | First viral Short (50K-100K views) |
| 60 | 35,000 | 120 | 3-5 viral Shorts, collabs starting |
| 90 | 100,000 | 180 | 8-12 viral Shorts, full flywheel |

**Conservative case (no virality):** 30-40K by day 90.
**Realistic case (2-3 viral Shorts):** 80-120K by day 90.
**Stretch case (5+ viral Shorts):** 200K+ by day 90.

100K is the realistic target with execution. Below 30K means content
isn't landing — pivot formats. Above 200K means the niche has more
demand than expected — double the cadence.

## Related

- [[Campaign_Brief_2026-06-22]] — email copy patterns to reuse in Short scripts
- [[Brain_MiniMax_Live_2026-06-22]] — use brain to draft comment replies
- [[MRR_System_2026-06-22]] — /for-contractors is the conversion target
- [[Contractor_Outreach_2026-06-22]] — 6,582-contractor base for email blast
- `bots/youtube_shorts_agent.py` — the production pipeline (already exists)
- `empire_media_lab.py` — the rendering infrastructure (already exists)