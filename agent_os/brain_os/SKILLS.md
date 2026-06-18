# BRAIN · Skills Registry

## Registered Skills

### 1. `brain.decide`
Evaluate a lead + alert pair and produce a GO/NO-GO decision.
- Input: lead (warehouse_name, phone, email, address, city, state, asset_value), alert_summary (event, severity, urgency, area), niche
- Output: decision (GO/NO-GO), confidence (0-1), reasoning, strategy
- Dependencies: brain.personality.get, brain.vault.context

### 2. `brain.vault.context`
Load all vault knowledge into a context string for prompt injection.
- Input: none
- Output: concatenated markdown from all vault notes
- Cache: 5-minute TTL

### 3. `brain.vault.read`
Read content of a specific vault note by path.
- Input: path (relative to vault root)
- Output: markdown content

### 4. `brain.vault.search`
Search vault knowledge for relevant snippets.
- Input: query string
- Output: list of matching sections with context

### 5. `brain.memory.retrieve`
Retrieve relevant memories (past decisions, outcomes) similar to current context.
- Input: query, limit (default 5), similarity threshold
- Output: list of memory records with similarity scores

### 6. `brain.memory.record`
Store a new memory (decision + outcome) for future retrieval.
- Input: lead info, decision details, outcome
- Output: memory_id

### 7. `brain.outcome.attach`
Link an outcome (settled, rejected, etc.) back to the original decision.
- Input: decision_id, outcome, actual_fee (optional), notes
- Output: ok

### 8. `brain.learn.tune`
Adjust urgency thresholds and calibration based on recent outcome data.
- Input: lookback_days (default 7)
- Output: list of thresholds adjusted and new values

### 9. `brain.personality.get`
Get the operator-configured personality profile for a niche, with voice, tone, and strategy preferences.
- Input: niche
- Output: personality profile
