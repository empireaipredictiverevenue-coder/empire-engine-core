# BRAIN SKILLS — Cognitive Capability Registry

> *Every skill the brain can execute. Skills are the atomic units of cognition.*

---

## Skill Architecture

Each skill has:
- `name` — unique identifier
- `version` — semver for evolution tracking
- `description` — what it does
- `inputs` — expected parameters
- `outputs` — what it returns
- `dependencies` — other skills it may call
- `tags` — for discovery (`domain:brain`, `mode:sync`)
- `timeout` — max execution time

```
skill.execute(input) → SkillOutput
         │
         ├── success: bool
         ├── data: dict
         ├── error: str (if failed)
         └── metrics: {duration_ms, tokens, api_calls}
```

---

## Registered Skills

### 1. `brain.decide`
| Field | Value |
|---|---|
| **Version** | 2.0.0 |
| **Description** | Evaluate a lead + alert and return GO/NO_GO with calibrated confidence |
| **Tags** | `domain:brain`, `mode:sync`, `critical:true` |
| **Timeout** | 120s |
| **Dependencies** | `brain.memory.retrieve`, `brain.vault.context` |

**Inputs:**
- `lead` — dict with warehouse_name, address, city, state, phone, email, asset_value
- `alert` — dict with event, severity, urgency, area
- `niche` — optional niche override

**Outputs:**
- `decision` — "GO" | "NO_GO"
- `confidence` — float 0.0-1.0
- `reasoning` — one-sentence explanation
- `memory_context` — number of similar past leads used
- `strategy` — recommended outreach strategy

---

### 2. `brain.memory.retrieve`
| Field | Value |
|---|---|
| **Version** | 1.0.0 |
| **Description** | Find similar past decisions from brain_memory using embedding similarity |
| **Tags** | `domain:brain`, `mode:sync`, `requires:embedding` |
| **Timeout** | 15s |

**Inputs:**
- `lead` — dict with address, city, severity, asset_value
- `k` — number of similar leads to retrieve (default 5)
- `only_with_outcomes` — filter to settled/denied only (default true)

**Outputs:**
- `memories` — list of similar past decisions with outcomes
- `count` — number retrieved

---

### 3. `brain.memory.record`
| Field | Value |
|---|---|
| **Version** | 1.0.0 |
| **Description** | Store a new brain decision with embedding for future retrieval |
| **Tags** | `domain:brain`, `mode:sync`, `requires:embedding` |
| **Timeout** | 10s |

**Inputs:**
- `lead_id` — the evaluated lead's ID
- `decision` — GO or NO_GO
- `urgency` — urgency score 1-10
- `reasoning` — one-sentence explanation
- `address` — for embedding
- `city` — for embedding
- `severity` — for embedding
- `asset_value` — for embedding

**Outputs:**
- `memory_id` — the stored record ID
- `ok` — success boolean

---

### 4. `brain.outcome.attach`
| Field | Value |
|---|---|
| **Version** | 1.0.0 |
| **Description** | Link a claim outcome back to the original brain decision |
| **Tags** | `domain:brain`, `mode:sync` |
| **Timeout** | 10s |

**Inputs:**
- `lead_id` — the lead whose claim settled/denied/withdrawn
- `outcome` — "settled" | "denied" | "withdrawn"
- `actual_fee` — fee earned if settled

**Outputs:**
- `ok` — success boolean

---

### 5. `brain.learn.tune`
| Field | Value |
|---|---|
| **Version** | 1.0.0 |
| **Description** | Nightly: recompute urgency floors from real outcomes |
| **Tags** | `domain:brain`, `mode:cron` |
| **Timeout** | 60s |
| **Dependencies** | `brain.memory.retrieve` |

**Inputs:**
- `lookback_days` — how many days of data to analyze (default 90)

**Outputs:**
- `tuned` — number of (city, severity, asset_band) buckets updated
- `rows_analyzed` — total outcomes processed

---

### 6. `brain.personality.get`
| Field | Value |
|---|---|
| **Version** | 1.0.0 |
| **Description** | Get the effective personality profile for a niche + operator |
| **Tags** | `domain:brain`, `mode:sync` |
| **Timeout** | 5s |

**Inputs:**
- `niche` — the target niche
- `operator_id` — optional operator for per-operator overrides

**Outputs:**
- `persona` — conservative | aggressive | balanced
- `confidence_threshold` — minimum confidence for GO
- `urgency_floor` — minimum urgency
- `temperature` — LLM temperature
- `custom_prompt_suffix` — operator notes

---

### 7. `brain.vault.read`
| Field | Value |
|---|---|
| **Version** | 1.0.0 |
| **Description** | Read a note from the brain vault knowledge base |
| **Tags** | `domain:brain`, `mode:sync` |
| **Timeout** | 5s |

**Inputs:**
- `path` — path relative to brain_vault/ root
- `max_chars` — max characters to read (default 5000)

**Outputs:**
- `content` — the note content
- `path` — the resolved path
- `size` — content length

---

### 8. `brain.vault.search`
| Field | Value |
|---|---|
| **Version** | 1.0.0 |
| **Description** | Search the brain vault for notes matching a keyword |
| **Tags** | `domain:brain`, `mode:sync` |
| **Timeout** | 5s |

**Inputs:**
- `query` — keyword or phrase to search for
- `max_results` — max notes to return (default 5)

**Outputs:**
- `results` — list of matching note paths and excerpts
- `count` — number of matches

---

## Skill Dependency Graph

```
brain.decide
├── brain.memory.retrieve     (pull similar past decisions)
├── brain.personality.get     (get effective personality)
└── brain.vault.context       (load vault knowledge)

brain.learn.tune
└── brain.memory.retrieve     (pull outcomes for analysis)

brain.vault.context           (standalone — no deps)
brain.memory.record           (standalone)
brain.outcome.attach          (standalone)
brain.vault.read              (standalone)
brain.vault.search            (standalone)
```

---

## Skill Fidelity Rules

1. `brain.decide` is the **only** skill that may call other skills
2. No skill may call `brain.decide` recursively
3. `brain.learn.tune` may only run during low-activity hours (cron)
4. `brain.vault.*` skills are read-only — they never write to the vault
5. Every skill execution is logged to agent_activity via the event bus
6. Skills that fail 5+ consecutive times trigger a circuit breaker
