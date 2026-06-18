# Memory & Learning

> *How the brain stores, retrieves, and learns from past decisions.*

## Memory Architecture

Every brain decision is stored in `brain_memory` with:
- A text embedding (OpenAI text-embedding-3-small, 1536d)
- The decision (GO/NO_GO) and reasoning
- Context: city, severity, asset_value, urgency
- Outcome: settled/denied/withdrawn (attached later)

When a new lead arrives, the brain retrieves the 5 most similar past
decisions by embedding cosine similarity. Those become few-shot examples
in the system prompt.

## Learning Loop

```
Decision → Memory → Outcome → Analysis → Threshold Tune
   ↑                                          |
   └──────────────────────────────────────────┘
```

1. Brain decides GO/NO_GO → stored in brain_memory
2. Claim settles/denies → outcome attached to memory
3. Nightly: BrainLearning scans last 90 days of outcomes
4. For each (city, severity, asset_band) bucket:
   - Compute win_rate, avg_fee, expected_value
   - Find urgency floor where expected_value >= $500
5. Write optimal floors to brain_config
6. Next brain call reads current floor for this lead's bucket

## Key Insight

The brain doesn't learn in real-time. It learns in batches (nightly).
This prevents noisy single-outcome swings while still trending toward
what works.

## When to Override

If a particular niche or metro consistently underperforms:
- Lower the confidence_threshold for that niche (more conservative)
- Raise the urgency_floor (need stronger storms to trigger outreach)
- Or switch to a different personality profile via the SPA
