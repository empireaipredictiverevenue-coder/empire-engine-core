# locked-directive.md — what "done" means

## The metric

Empire AI's success is measured by 4 steps, in order:

1. **Splash live at empire-ai.co.uk** — DONE (2026-06-13)
2. **1 real lead in Supabase** — DONE (Americold Logistics,
   +18176243982, replied YES 2026-06-14)
3. **1 real contractor recruited** — NOT YET
4. **1 real fee earned** — NOT YET

**Current score: 2/4.** Steps 3 and 4 are unblocked by a human
deciding to be a real person at the other end. Code can't make a
human say yes.

## Why the order matters

- Step 1 (splash) proves we can render a public page.
- Step 2 (real lead) proves the pipeline produces a real person
  who replies.
- Step 3 (real contractor) proves the network has at least one
  human who accepts the dispatch terms.
- Step 4 (real fee) proves the revenue model closes — a settled
  insurance claim with a 3% fee.

Steps 1-2 are "we built it." Steps 3-4 are "they used it and paid."
**the gap is on the human side, not the code side.**

## What blocks step 3 (the current bottleneck)

- 31 contractor rows in the DB, but **all are either:**
  - **2 real DFW roofers** (DFW Commercial Roofing Co, the original
    "seed_for_test" from before this session) — actual businesses
  - **24 Wichita roofers** (from bots/prospector.py's first run,
    many with fictional 555-XX phones that 422 at Vonage)
  - **5 DFW hand-seeded** by striker on 2026-06-14 with
    `apexroofdfw.com / dfwstormshield.com / lonestarroof.com /
    texaspremierroof.com / northtexasroofing.com` — **all FICTITIOUS**,
    flagged in the seed script. No real human at those numbers.
- The contractor_outreach recruiter runs every 4h, enrolling
  active contractors in the v2 contractor_recruit sequence.
  **but no fictional contractor can reply YES.** so step 3 is
  blocked on recruiting at least one real DFW roofer.

## What blocks step 4 (downstream of step 3)

- A real contractor accepts a dispatch (responds YES or self-onboards
  at /contractors).
- A real property owner says YES to that contractor's outreach
  (already happened: Americold).
- The contractor closes a real insurance claim.
- Empire gets 3% of the gross settlement, paid within 30 days.

## What the code can and can't do for steps 3-4

- **Code can**: make the pipeline fast and reliable (done),
  make the offers clear (done: free-trial pitch, no-call ask),
  make the landing page convert (done: /contractors, self-onboard
  form, FAQ, chat widget pending buffy), make the dispatcher
  honest (done: STOP footers, DNC checks, bad-phone counter).
- **Code can't**: pick up a phone, introduce yourself to a DFW
  roofer, explain the offer, and wait for them to say yes. **a
  human (you, the operator) has to do that.** the code's job is
  to make the path from "yes" to "paid" friction-free.

## See also

- [`architecture.md`](architecture.md) — the funnel
- [`contractor-recruit.md`](contractor-recruit.md) — the v2 copy
  that lands when a contractor self-onboards or replies YES
- [`prospector.md`](prospector.md) — why the existing contractor
  pool is mostly fiction

## log

- 2026-06-14: created (initial scaffold; score 2/4 at this time)
