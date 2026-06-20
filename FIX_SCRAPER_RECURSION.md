# Fix: RecursionError in predictive_camofox_scraper.py

## Problem
The `enhanced_run_cycle` method is calling itself in a loop, causing:
```
RecursionError: maximum recursion depth exceeded
```

This happened during earlier pipeline wiring attempts.

## Location
File: `bots/predictive_camofox_scraper.py`
Around line 129 (inside `enhanced_run_cycle`)

## Fix

**Option 1 (Recommended)**: Remove the broken override entirely

Delete or comment out these lines if they exist:

```python
# REMOVE THIS
enhanced_run_cycle = run_cycle

# REMOVE THIS ENTIRE METHOD
async def enhanced_run_cycle(self):
    result = await self.run_cycle()
    ...
```

**Option 2**: Replace `enhanced_run_cycle` with a clean `run_cycle`

Replace the broken method with this clean version:

```python
async def run_cycle(self):
    niches = ["roofing", "hvac", "solar", "restoration", "public_adjuster", "commercial"]
    metros = ["texas", "florida", "california", "arizona"]
    results = []
    for niche in niches:
        for metro in metros:
            results.extend(await self.scrape_niche(niche, metro))
    await self._agi_self_improvement()
    log.info(f"[Camofox] Cycle complete — {len(results)} opportunities")
    return {"opportunities": results, "count": len(results)}
```

## After Fix
Run this to verify:
```bash
python3 -m py_compile bots/predictive_camofox_scraper.py
```

Then re-run the full pipeline test:
```bash
cd /root/empire-v49
PYTHONPATH=. python3 scripts/full_pipeline_test.py
```

## Notes
- The recursion was introduced during wiring attempts
- The original `run_cycle` method should be restored
- All other agents are working correctly
