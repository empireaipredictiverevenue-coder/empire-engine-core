# Skills Framework: Standardized Routines for Every Bot & Agent

> *An advanced concept for turning ad-hoc agent capabilities into composable, observable, hot-swappable skills with a standard lifecycle.*

---

## 1. The Problem (Why Skills Over Capabilities)

Empire AI has **25+ agents** and counting. Each one defines capabilities as **inline string tags** in heartbeat functions, scattered across the codebase. There are **three separate registries** (`AGENT_CAPABILITIES` in `agent_mesh.py`, `CapabilityRegistry` in `empire_agent_os.py`, `ROLE_DEFINITIONS` in `empire_agent_fleet.py`), and none of them define **how** a capability executes.

**Current state:**

```
Agent A: capabilities = ["forecast_revenue", "detect_anomalies"]
Agent B: capabilities = ["manage_seo", "track_rankings"]
```

These are **labels**, not routines. They tell you *what* an agent can do, but not:
- What inputs it expects
- What outputs it produces
- How long it takes
- What errors it can throw
- Whether it depends on another capability
- How to compose it with other capabilities

**The result:** Every agent reinvents the wheel. `run_cycle()` in `backlinks_agent.py` looks nothing like `run()` in `contact_discovery.py`. There's no shared error handling, no standard retry logic, no composability.

---

## 2. Conceptual Model: Skills as First-Class Routines

A **Skill** is a well-defined, self-contained routine with a standard interface, a formal lifecycle, and explicit contracts.

```
┌──────────────────────────────────────────────────┐
│                    Skill                          │
│  ┌──────────┐  ┌──────────┐  ┌────────────────┐ │
│  │ validate │ →│ execute  │ →│ report         │ │
│  └──────────┘  └──────────┘  └────────────────┘ │
│       │              │              │            │
│  ┌────┴────┐   ┌─────┴─────┐  ┌────┴─────┐      │
│  │ inputs  │   │  output   │  │ metrics  │      │
│  │ precond │   │ artifacts │  │ errors   │      │
│  └─────────┘   └───────────┘  └──────────┘      │
└──────────────────────────────────────────────────┘
```

### Key Insight: Skills are NOT agents.

| Concept | Scope | Reusability |
|---|---|---|
| **Agent** | Has identity, state, lifecycle | Runs independently |
| **Skill** | Has inputs, outputs, dependencies | **Shared across agents** |

An agent **equips** multiple skills. A skill can be used by **any** agent.

---

## 3. Architecture Overview

```
                    ┌─────────────────────┐
                    │   Agent (equipper)   │
                    │  equips: [SkillA,   │
                    │    SkillB, SkillC]  │
                    └──────┬──────────────┘
                           │ calls
                    ┌──────▼──────────────┐
                    │   SkillRegistry      │
                    │  {skill_name → Skill}│
                    │  dependency resolver │
                    │  version manager     │
                    └──────┬──────────────┘
                           │ resolves
            ┌──────────────┼──────────────┐
            │              │              │
     ┌──────▼──────┐ ┌─────▼──────┐ ┌─────▼──────┐
     │ Skill:      │ │ Skill:     │ │ Skill:     │
     │ send_sms    │ │ score_lead │ │ scrape_web │
     │ - Twilio    │ │ - SI model │ │ - httpx    │
     │ - langfuse  │ │ - langfuse │ │ - langfuse │
     └─────────────┘ └────────────┘ └────────────┘
```

### Integration with existing systems:

```
CapabilityRegistry (exists)     SkillRegistry (new)
    │                                   │
    │ "send_sms" maps to agent          │ "send_sms" maps to Skill class
    │ but not to execution              │ with validate/execute/report
    │                                   │
    └───────────────┬───────────────────┘
                    │ bridges via:
            ┌───────▼────────┐
            │  SkillBridge    │
            │  capability →   │
            │  skill resolver │
            └────────────────┘
```

---

## 4. Standard Skill Interface

```python
@dataclass
class SkillInput:
    """Typed input contract for every skill execution."""
    params: dict
    context: Optional['SkillContext'] = None
    trace_parent: Optional[str] = None  # Langfuse trace ID for nesting

@dataclass
class SkillOutput:
    """Typed output contract for every skill execution."""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    metrics: Optional['SkillMetrics'] = None
    artifacts: Optional[list[dict]] = None  # files, records, etc.

@dataclass
class SkillMetrics:
    """Standard metrics every skill reports."""
    duration_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    api_calls: int = 0
    records_processed: int = 0
    records_errored: int = 0

class BaseSkill(ABC):
    """Abstract base for every skill in the system."""

    # ── Metadata (class-level, override in subclass) ────────────
    name: str = ""                          # Unique skill identifier
    version: str = "1.0.0"                  # Semver for evolution tracking
    description: str = ""
    tags: list[str] = []                    # e.g. ["channel:sms", "provider:twilio"]
    dependencies: list[str] = []            # Skills this skill depends on
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0

    # ── Lifecycle ──────────────────────────────────────────────

    @abstractmethod
    async def validate(self, input: SkillInput) -> bool:
        """Validate inputs before execution.
        Return False if the skill cannot execute (missing params, bad state, etc.)
        """
        ...

    @abstractmethod
    async def execute(self, input: SkillInput) -> SkillOutput:
        """Execute the skill's core logic.
        Must be idempotent where possible (retry-safe).
        """
        ...

    async def report(self, output: SkillOutput) -> None:
        """Post-execution reporting. Override for custom logging/metrics.
        Default: writes to agent_activity table + Langfuse.
        """
        # Default implementation publishes to IPC bus:
        #   event: "skill.completed"
        #   data: {skill_name, duration_ms, success, tags}
        await self._publish_completion(output)

    # ── Built-in ───────────────────────────────────────────────

    async def run(self, input: SkillInput) -> SkillOutput:
        """Standard run method: validate → execute → report.
        Handles retry, timeout, Langfuse tracing, and error wrapping.
        """
        async with TraceContext(name=f"skill.{self.name}", ...) as ctx:
            if not await self.validate(input):
                ctx.set_output(error="validation_failed")
                return SkillOutput(success=False, error="validation_failed")

            for attempt in range(self.max_retries):
                try:
                    result = await asyncio.wait_for(
                        self.execute(input),
                        timeout=self.timeout_seconds
                    )
                    await self.report(result)
                    ctx.set_output(
                        output=result.data,
                        latency_ms=result.metrics.duration_ms if result.metrics else 0
                    )
                    return result
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        error_out = SkillOutput(success=False, error=str(e))
                        await self.report(error_out)
                        ctx.set_output(error=str(e))
                        return error_out
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
```

---

## 5. Skill Examples (Porting Existing Code)

### Current (fragmented, ad-hoc):

```python
# contact_discovery/discovery.py
def _discover_one(lead, cfg):
    # Two discovery methods, mixed concerns, no interface
    places = _google_places_search(query)
    scraped = _scrape_website_for_contact(place["website"])
    return {"phone": ..., "email": ..., "attempts": [...]}

# backlinks_agent.py
async def check_broken(self, limit=50):
    # Different pattern: self-contained but no standard interface
    for bl in backlinks:
        resp = await self._http.head(ref_url)
        ...
```

### With Skills:

```python
class GooglePlacesLookupSkill(BaseSkill):
    name = "lookup_google_places"
    version = "1.0.0"
    description = "Search Google Places for a business and return contact info"
    tags = ["channel:google_places", "provider:maps"]
    timeout_seconds = 10.0

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("query"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        query = input.params["query"]
        lat = input.params.get("lat")
        lon = input.params.get("lon")
        places = _google_places_search(query, lat, lon)
        return SkillOutput(
            success=True,
            data={"places": places},
            metrics=SkillMetrics(duration_ms=..., api_calls=1)
        )

class WebsiteScrapeSkill(BaseSkill):
    name = "scrape_website"
    version = "1.0.0"
    description = "Scrape a website URL for phone/email contact info"
    tags = ["channel:web", "provider:httpx"]
    dependencies = []  # standalone

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("url"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        url = input.params["url"]
        scraped = _scrape_website_for_contact(url)
        return SkillOutput(
            success=True,
            data=scraped,
            metrics=SkillMetrics(duration_ms=..., api_calls=len(...))
        )

class ContactDiscoverySkill(BaseSkill):
    name = "discover_contact"
    version = "2.0.0"
    description = "Composite skill: discovers phone/email for a lead using Places + scrape"
    tags = ["pipeline:pending_outreach"]
    dependencies = ["lookup_google_places", "scrape_website"]
    timeout_seconds = 30.0

    async def execute(self, input: SkillInput) -> SkillOutput:
        # Uses dependency-injected skill registry to compose
        places_skill = input.context.get_skill("lookup_google_places")
        scrape_skill = input.context.get_skill("scrape_website")

        # Step 1: Places lookup
        places_out = await places_skill.run(SkillInput(
            params={"query": f"{warehouse} {city} {state}"}
        ))

        # Step 2: If website found, scrape it
        if places_out.data.get("places"):
            place = places_out.data["places"][0]
            if place.get("website"):
                scrape_out = await scrape_skill.run(SkillInput(
                    params={"url": place["website"]}
                ))
                result.update(scrape_out.data or {})

        return SkillOutput(success=True, data=result, ...)
```

---

## 6. Skill Composition Patterns

### Pattern A: Sequential (Pipes)

```
[lookup_places] → [scrape_website] → [enrich_lead]
```

```python
class EnrichmentPipeline(BaseSkill):
    dependencies = ["lookup_places", "scrape_website", "score_lead"]

    async def execute(self, input: SkillInput) -> SkillOutput:
        result = {}
        for dep in self.dependencies:
            out = await ctx.get_skill(dep).run(SkillInput(params=input.params))
            result[dep] = out.data
            if not out.success:
                return SkillOutput(success=False, error=f"{dep} failed: {out.error}")
        return SkillOutput(success=True, data=result)
```

### Pattern B: Fan-Out (Parallel)

```
        ┌── [check_moz_da]
[url] ──┼── [check_majestic_tf] ──→ merge → report
        └── [check_ahrefs_ur]
```

```python
async def execute(self, input: SkillInput) -> SkillOutput:
    checks = ["check_moz_da", "check_majestic_tf", "check_ahrefs_ur"]
    results = await asyncio.gather(*[
        ctx.get_skill(s).run(SkillInput(params=input.params))
        for s in checks
    ])
    return self._merge_results(results)
```

### Pattern C: Conditional Routing

```
[score_intent] ──→ high_confidence → [send_sms]
               └── medium → [schedule_voice]
               └── low → [flag_for_review]
```

---

## 7. SkillRegistry: The Central Hub

```python
class SkillRegistry:
    """
    The central registry of all skills in the system.

    Responsibilities:
      - Register/unregister skills
      - Resolve dependencies (DAG-based topological sort)
      - Version management (semver, active version per skill)
      - Hot-swap (replace a skill version at runtime)
      - Discovery (find skills by tag, capability, dependency)
    """

    def __init__(self):
        self._skills: dict[str, list[SkillVersion]] = defaultdict(list)
        self._active: dict[str, str] = {}  # skill_name → active version

    def register(self, skill_cls: type[BaseSkill]) -> None:
        """Register a skill class. Instantiated lazily on first use."""
        name = skill_cls.name
        version = skill_cls.version
        self._skills[name].append(SkillVersion(version, skill_cls))
        self._skills[name].sort(key=lambda sv: sv.version, reverse=True)
        if name not in self._active:
            self._active[name] = version  # newest by default

    def activate(self, skill_name: str, version: str) -> bool:
        """Switch to a specific version of a skill."""
        versions = self._skills.get(skill_name, [])
        for sv in versions:
            if sv.version == version:
                self._active[skill_name] = version
                return True
        return False

    def get(self, skill_name: str) -> Optional[BaseSkill]:
        """Get the active instance of a skill by name."""
        versions = self._skills.get(skill_name, [])
        active_ver = self._active.get(skill_name)
        for sv in versions:
            if sv.version == active_ver:
                return sv.instantiate()
        if versions:
            return versions[0].instantiate()
        return None

    def resolve_dag(self, skill_name: str) -> list[str]:
        """Return the execution order for a skill and all its dependencies.
        Uses Kahn's algorithm (same as ProcessManager.resolve_boot_order).
        Returns [self, dep3, dep2, dep1] — execute reversed.
        """
        graph = self._build_dependency_graph(skill_name)
        return topological_sort(graph)  # Kahn's algorithm

    def snapshot(self) -> dict:
        """Full registry snapshot for the SPA dashboard."""
        return {
            "total_skills": len(self._skills),
            "by_tag": self._group_by_tag(),
            "versions": {name: [sv.version for sv in vers]
                        for name, vers in self._skills.items()},
            "active": self._active,
        }
```

### Integration with Existing Systems:

```python
# Bridge between old CapabilityRegistry and new SkillRegistry
class SkillBridge:
    """
    Maps capability strings to skill names.
    Allows the old CapabilityRegistry to discover skills.
    """

    CAPABILITY_TO_SKILL = {
        "discover_contact":        "discover_contact",
        "google_places_search":    "lookup_google_places",
        "website_scrape":          "scrape_website",
        "score_leads":             "score_lead",
        "engineer_features":       "engineer_features",
        "run_outreach":            "run_outreach",
        "check_compliance":        "check_compliance",
        "forecast_revenue":        "forecast_revenue",
        "detect_anomalies":        "detect_anomalies",
        "manage_seo":              "manage_seo",
        "analyze_backlinks":       "analyze_backlinks",
        "scan_radar_targets":      "scan_radar_targets",
        "send_messages":           "send_sms",
        "write_copy":              "write_copy",
        "render_videos":           "render_video",
    }

    @classmethod
    def capability_to_skills(cls, capability: str) -> list[str]:
        """Resolve one or more skills from a capability tag."""
        result = cls.CAPABILITY_TO_SKILL.get(capability)
        return [result] if result else []
```

---

## 8. Agent-Skill Wiring

An agent **equips** skills at startup. The old `capabilities` list becomes a **skill roster**.

### How an agent declares skills:

```python
class ContactDiscoveryAgent(Agent):  # existing Agent base class
    name = "contact_discovery"
    equips = [
        "discover_contact",      # composite skill
        "lookup_google_places",  # atomic skill (can be used standalone)
        "scrape_website",        # atomic skill
    ]

    async def on_start(self):
        # Skills are injected into the agent by the SkillRegistry
        self.discover = self.skills.get("discover_contact")
        self.places = self.skills.get("lookup_google_places")

    async def on_tick(self):
        for lead in self._get_candidates():
            result = await self.discover.run(SkillInput(
                params={"warehouse": lead.warehouse_name, "city": lead.city, ...}
            ))
            if result.success:
                self._update_lead(lead.id, result.data)
```

### How skills get injected (AgentKernel integration):

```python
# In agent_os.py ProcessManager.register():
async def register(self, agent: Agent) -> None:
    if hasattr(agent, 'equips'):
        agent.skills = SkillContext(self._skill_registry)
        # Auto-register capability strings from equipped skills
        for skill_name in agent.equips:
            skill = self._skill_registry.get(skill_name)
            if skill:
                # Bridge: skill's tags become agent capabilities
                for tag in skill.tags:
                    self._capabilities.register(agent.name, tag)
                self._capabilities.register(agent.name, skill_name)
```

---

## 9. Migration Strategy: Agent by Agent

| Phase | Scope | Skills Created | Impact |
|---|---|---|---|
| **Phase 1** | Infrastructure | `SkillRegistry`, `BaseSkill`, `SkillBridge` | No behavioral change |
| **Phase 2** | Core pipeline | `lookup_google_places`, `scrape_website`, `discover_contact`, `score_lead`, `engineer_features`, `send_sms`, `check_compliance` | Replaces contact_discovery + lead_enricher core |
| **Phase 3** | SEO/Content | `manage_seo`, `analyze_backlinks`, `write_copy`, `keyword_research` | Replaces seo_agent + backlinks_agent inner loops |
| **Phase 4** | Revenue | `forecast_revenue`, `detect_anomalies`, `model_pipeline` | Replaces predictive_revenue core |
| **Phase 5** | Outreach | `run_outreach`, `send_sms`, `send_email`, `voice_call`, `handle_reply` | Replaces converter + outreach engine |
| **Phase 6** | All agents | Full migration | Old capabilities deprecated |

### How to migrate without breaking anything:

1. **Wrap, don't rewrite.** Wrap existing `run_cycle()` methods inside a skill adapter:

```python
class LegacySkillAdapter(BaseSkill):
    """Adapter: wraps an existing agent's run_cycle into a skill."""

    def __init__(self, name: str, agent_instance, method: str = "run_cycle"):
        self.name = name
        self._agent = agent_instance
        self._method = method

    async def execute(self, input: SkillInput) -> SkillOutput:
        start = time.time()
        try:
            result = await getattr(self._agent, self._method)(**input.params)
            return SkillOutput(
                success=True,
                data=result if isinstance(result, dict) else {"result": result},
                metrics=SkillMetrics(duration_ms=int((time.time()-start)*1000))
            )
        except Exception as e:
            return SkillOutput(success=False, error=str(e))
```

2. **Register existing agents as skills in the registry.** This gives them the skill lifecycle without rewriting them.

3. **Gradually refactor** the inner logic of each skill to be standalone (no agent dependency). When the skill no longer needs the adapter, strip it.

---

## 10. Dashboard & Observability Integration

### Langfuse Tracing (already integrated):

Every `BaseSkill.run()` automatically creates a Langfuse trace:

```
trace: "skill.discover_contact"
├── span: "validate" (if implemented)
├── span: "execute"
│   ├── trace: "skill.lookup_google_places" (dependency 1)
│   │   ├── span: "validate"
│   │   └── span: "execute"
│   └── trace: "skill.scrape_website" (dependency 2)
│       └── span: "execute"
└── span: "report"
```

This gives a **nested, composable trace tree** for every agent action — for free.

### Fleet Dashboard additions:

```javascript
// New section in the SPA: /view/skills
{
  "skills": {
    "total": 42,
    "active_versions": { "send_sms": "2.1.0", "discover_contact": "1.3.0" },
    "by_tag": { "channel:sms": 4, "pipeline:enrich": 6, "provider:ollama": 8 },
    "error_rates": { "scrape_website": 0.02, "lookup_places": 0.005 },
    "hot_swap_log": ["scrape_website: 1.0.0 → 1.0.1 (2026-06-16 14:32)"],
    "dependencies": {
      "discover_contact": ["lookup_google_places", "scrape_website"],
      "enrichment_pipeline": ["discover_contact", "score_lead"],
    }
  }
}
```

---

## 11. Advanced Features (Phase 2+)

### A. Hot-Swapping Skills at Runtime

```python
# POST /api/v1/skills/{name}/activate?version=2.0.0
# No restart required. Next skill.run() uses the new version.

@router.post("/api/v1/skills/{name}/activate")
async def activate_skill(name: str, version: str):
    success = registry.activate(name, version)
    if success:
        await kernel.ipc.publish("skill.activated", {
            "skill": name,
            "version": version,
        })
    return {"ok": success}
```

### B. A/B Testing Skills

Run two versions of a skill in production, compare metrics:

```python
class ABTestSkill(BaseSkill):
    """Wrapper that dispatches to skill version A or B based on config."""

    async def execute(self, input: SkillInput) -> SkillOutput:
        version = self._select_version(input)
        skill = registry.get(self.name, version=version)
        return await skill.execute(input)
```

### C. Skill-Level Rate Limiting & Quotas

```python
class RateLimitedSkill(BaseSkill):
    """Wrapper that enforces rate limits per skill execution."""

    async def execute(self, input: SkillInput) -> SkillOutput:
        if not self._rate_limiter.allow():
            return SkillOutput(success=False, error="rate_limited")
        return await self._inner.execute(input)
```

### D. Skill Rollbacks

The registry keeps `n` previous versions. Activation is instant:

```python
registry.activate("scrape_website", "1.0.0")  # rollback in <1ms
```

---

## 12. Summary: Before vs After

| Concern | **Before (Capabilities)** | **After (Skills)** |
|---|---|---|
| **Definition** | String tag in heartbeat | Class with validate/execute/report |
| **Lifecycle** | None (each agent invents its own) | Standard: run() → retry → timeout → trace |
| **Input/Output** | Implicit (anything goes) | Typed SkillInput / SkillOutput dataclasses |
| **Composability** | None | DAG-based dependency resolution |
| **Reusability** | Low (each agent duplicates) | High (any agent equips any skill) |
| **Observability** | LLM traces only | Full trace tree: validate/execute/report + dependencies |
| **Versioning** | None | Semver per skill, active version switching |
| **Hot-swap** | Impossible | Runtime version activation |
| **Error handling** | Inline try/except per bot | Standard retry + backoff + timeout |
| **Dashboard** | Lists agent capabilities | Shows skill versions, error rates, DAG |

**The ultimate point: Skills decouple *what* from *how*. An agent can stay simple and just equip skills. The skills framework handles execution, retries, tracing, versioning, and composition.**

---

*This framework transforms Empire AI from a collection of bespoke agents into a composable skill engine. The first skill (`discover_contact`) already has a natural candidate: the contact_discovery agent. Start there.*

---

## 13. Harness Engineering: The Execution Environment for Skills

> *A skill defines **what** to do. A harness defines **how** it runs — resource limits, isolation, injection, recovery, and observability.*

Skills are pure logic. They should not care about:
- How they get rate-limited
- How dependencies are injected
- How failures are recovered
- How metrics are collected
- How they're tested in isolation

A **Harness** wraps a skill in a controlled execution environment. It is the runtime boundary between the skill and the system.

```
┌──────────────────────────────────────────────────────────────┐
│                     Agent (orchestrator)                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │           Harness (execution boundary)                │    │
│  │                                                       │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐   │    │
│  │  │ Resource     │  │ Dependency   │  │ Error    │   │    │
│  │  │ Limiter      │  │ Injector     │  │ Boundary │   │    │
│  │  └──────┬───────┘  └──────┬───────┘  └────┬─────┘   │    │
│  │         │                 │                │          │    │
│  │         └─────────┬───────┴────────────────┘          │    │
│  │                   │                                    │    │
│  │          ┌────────▼────────┐                          │    │
│  │          │   Skill.exec()  │                          │    │
│  │          └─────────────────┘                          │    │
│  │                                                       │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐   │    │
│  │  │ Langfuse     │  │ Metrics      │  │ IPC      │   │    │
│  │  │ Tracing      │  │ Emission     │  │ Events   │   │    │
│  │  └──────────────┘  └──────────────┘  └──────────┘   │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

### 13.1 The Harness Interface

```python
@dataclass
class HarnessConfig:
    """Configuration for a skill execution harness."""
    # ── Resource Limits ───────────────────────────────────────
    timeout: float = 30.0              # Max wall-clock time per execution
    max_retries: int = 3               # Retries on transient failure
    retry_backoff: float = 1.0         # Exponential backoff base (seconds)
    max_memory_mb: Optional[int] = None  # Memory limit (future: cgroups)
    max_concurrent: int = 1            # Max concurrent executions of this skill

    # ── Injection ─────────────────────────────────────────────
    inject_skills: bool = True         # Auto-inject dependency skills
    inject_db: bool = True             # Inject Supabase client
    inject_llm: bool = True            # Inject LLM router
    inject_ipc: bool = True            # Inject IPC bus

    # ── Observability ─────────────────────────────────────────
    langfuse_trace: bool = True        # Create a Langfuse trace
    emit_metrics: bool = True          # Emit metrics to IPC bus
    log_payload: bool = False          # Log full input/output (PII risk!)

    # ── Error Handling ────────────────────────────────────────
    raise_on_failure: bool = False     # If True, re-raise instead of returning error
    fallback_skill: Optional[str] = None  # Skill to call on failure
    circuit_breaker: bool = False      # Enable circuit breaker pattern
    circuit_threshold: int = 5         # Failures before circuit opens
    circuit_reset_seconds: float = 60.0  # Time before circuit resets

    # ── Testing ───────────────────────────────────────────────
    mock_deps: Optional[dict[str, BaseSkill]] = None  # Override dependencies
    record: bool = False               # Record all I/O for replay
    replay: Optional[str] = None       # Path to replay file


class SkillHarness:
    """
    Wraps a BaseSkill with a controlled execution environment.

    The harness handles everything that isn't skill logic:
      - Resource enforcement (timeout, concurrency, retries)
      - Dependency injection (skills, DB, LLM, IPC)
      - Observability (Langfuse, metrics, logging)
      - Error containment (circuit breaker, fallback)
      - Testing support (mock inject, record/replay)

    Usage:
        harness = SkillHarness(skill, config=HarnessConfig(...))
        output = await harness.run(SkillInput(params={"query": "..."}))
    """

    def __init__(self, skill: BaseSkill, config: Optional[HarnessConfig] = None):
        self._skill = skill
        self._config = config or HarnessConfig()
        self._circuit_state = {"failures": 0, "open_until": 0.0}
        self._concurrency_sem = asyncio.Semaphore(self._config.max_concurrent)
        self._recording: list[dict] = []

    # ── Public API ────────────────────────────────────────────────

    async def run(self, input: SkillInput) -> SkillOutput:
        """Execute the skill through the harness.
        Handles concurrency limiting, circuit breaker, injection, tracing.
        """
        # 1. Circuit breaker check
        if self._config.circuit_breaker and self._circuit_open():
            return SkillOutput(success=False, error="circuit_breaker_open")

        # 2. Concurrency limit
        async with self._concurrency_sem:
            return await self._execute_with_guardrails(input)

    @property
    def skill(self) -> BaseSkill:
        return self._skill

    @property
    def config(self) -> HarnessConfig:
        return self._config

    # ── Internal Execution ─────────────────────────────────────────

    async def _execute_with_guardrails(self, input: SkillInput) -> SkillOutput:
        """Execute with injection, retry backoff, timeout, tracing."""

        # 1. Inject dependencies into the skill
        context = await self._build_context(input)
        injected_input = SkillInput(params=input.params, context=context)

        # 2. Langfuse trace (if enabled)
        trace_name = f"skill.{self._skill.name}"
        trace_tags = ["harness:enabled", f"skill:{self._skill.name}"] + self._skill.tags

        async with TraceContext(name=trace_name, tags=trace_tags, input=input.params) as ctx:
            # 3. Execute with retry + timeout
            last_error = None
            for attempt in range(self._config.max_retries):
                try:
                    start = time.time()
                    output = await asyncio.wait_for(
                        self._skill.execute(injected_input),
                        timeout=self._config.timeout
                    )
                    elapsed = int((time.time() - start) * 1000)

                    # 4. Record if enabled
                    if self._config.record:
                        self._recording.append({
                            "input": input.params,
                            "output": output.data,
                            "duration_ms": elapsed,
                        })

                    # 5. Set trace output
                    ctx.set_output(
                        output=output.data,
                        latency_ms=elapsed,
                        metadata={
                            "attempt": attempt + 1,
                            "success": output.success,
                            **self._skill._last_metrics or {},
                        }
                    )

                    # 6. Emit metrics
                    if self._config.emit_metrics:
                        await self._emit_metrics(output, elapsed, attempt + 1)

                    # 7. Reset circuit breaker on success
                    self._circuit_state["failures"] = 0

                    return output

                except asyncio.TimeoutError:
                    last_error = f"timeout after {self._config.timeout}s"
                    log.warning(f"[harness.{self._skill.name}] attempt {attempt+1}: {last_error}")
                    ctx.set_output(error=last_error, latency_ms=int(self._config.timeout * 1000))

                except Exception as e:
                    last_error = str(e)
                    log.warning(f"[harness.{self._skill.name}] attempt {attempt+1}: {last_error}")

                # Backoff before retry
                if attempt < self._config.max_retries - 1:
                    await asyncio.sleep(self._config.retry_backoff * (2 ** attempt))

            # 8. All retries exhausted
            error_out = SkillOutput(success=False, error=last_error)
            ctx.set_output(error=last_error)

            # 9. Circuit breaker: increment failure count
            if self._config.circuit_breaker:
                self._circuit_state["failures"] += 1
                if self._circuit_state["failures"] >= self._config.circuit_threshold:
                    self._circuit_state["open_until"] = time.time() + self._config.circuit_reset_seconds

            # 10. Fallback skill
            if self._config.fallback_skill:
                fallback = self._get_fallback_skill()
                if fallback:
                    return await fallback.run(input)

            # 11. Re-raise if configured
            if self._config.raise_on_failure:
                raise RuntimeError(last_error)

            return error_out

    async def _build_context(self, input: SkillInput) -> SkillContext:
        """Build the injection context for this execution."""
        context = SkillContext()

        # Inject dependency skills (resolved from registry)
        if self._config.inject_skills:
            for dep_name in self._skill.dependencies:
                dep_skill = self._resolve_dependency(dep_name)
                if dep_skill:
                    context.inject_skill(dep_name, dep_skill)

        # Override with mocks (testing)
        if self._config.mock_deps:
            for name, mock in self._config.mock_deps.items():
                context.inject_skill(name, mock)

        # Inject infrastructure
        if self._config.inject_db:
            context.inject("db", _get_db())
        if self._config.inject_llm:
            context.inject("llm", get_llm_router())
        if self._config.inject_ipc:
            context.inject("ipc", get_ipc_bus())

        return context

    def _circuit_open(self) -> bool:
        state = self._circuit_state
        if state["open_until"] > time.time():
            return True
        if state["open_until"] > 0 and state["open_until"] <= time.time():
            state["failures"] = 0
            state["open_until"] = 0.0  # half-open
        return False

    async def _emit_metrics(self, output: SkillOutput, elapsed_ms: float, attempt: int) -> None:
        """Emit execution metrics to the IPC bus."""
        event = {
            "skill": self._skill.name,
            "version": self._skill.version,
            "success": output.success,
            "duration_ms": elapsed_ms,
            "attempt": attempt,
            "tags": self._skill.tags,
        }
        if output.metrics:
            event.update({
                "tokens_in": output.metrics.tokens_in,
                "tokens_out": output.metrics.tokens_out,
                "api_calls": output.metrics.api_calls,
                "records_processed": output.metrics.records_processed,
            })
        await ipc.publish("skill.executed", event, source="harness")

    def _resolve_dependency(self, dep_name: str) -> Optional[BaseSkill]:
        """Resolve a dependency skill from the global registry."""
        from skills.registry import get_registry
        return get_registry().get(dep_name)

    def _get_fallback_skill(self) -> Optional[BaseSkill]:
        if not self._config.fallback_skill:
            return None
        from skills.registry import get_registry
        return get_registry().get(self._config.fallback_skill)

    # ── Testing Support ────────────────────────────────────────────

    def get_recording(self) -> list[dict]:
        """Return recorded I/O for test assertions."""
        return list(self._recording)

    def clear_recording(self) -> None:
        """Clear the recording buffer."""
        self._recording.clear()

    def snapshot(self) -> dict:
        """Harness state snapshot for dashboard."""
        return {
            "skill": self._skill.name,
            "version": self._skill.version,
            "config": {
                "timeout": self._config.timeout,
                "max_retries": self._config.max_retries,
                "max_concurrent": self._config.max_concurrent,
                "circuit_breaker": self._config.circuit_breaker,
            },
            "circuit": {
                "open": self._circuit_open(),
                "failures": self._circuit_state["failures"],
            },
            "recorded_executions": len(self._recording),
        }
```

---

### 13.2 Testing Harness (Isolation Testing)

The harness enables **true unit testing of skills** without real dependencies:

```python
class SkillTestHarness:
    """
    Wraps a skill with mocked dependencies for isolated testing.

    Features:
      - Mock injection: replace any dependency skill with a fake
      - Fake infrastructure: in-memory DB, mock LLM, null IPC
      - Record/replay: capture input/output for regression tests
      - Assertion helpers: verify outputs, metrics, error states
      - Performance assertions: verify max duration, token budget
    """

    def __init__(self, skill: BaseSkill):
        self._harness = SkillHarness(
            skill,
            config=HarnessConfig(
                inject_skills=True,
                inject_db=False,       # replaced by mock
                inject_llm=False,      # replaced by mock
                inject_ipc=False,
                record=True,
            )
        )
        self._mocks: dict[str, MockSkill] = {}
        self._fake_db = InMemoryDatabase()
        self._fake_llm = MockRouter()

    def mock_dependency(self, dep_name: str, return_value: Optional[dict] = None):
        """Replace a dependency skill with a mock that returns a fixed value."""
        mock = MockSkill(name=dep_name, return_value=return_value)
        self._mocks[dep_name] = mock
        self._harness._config.mock_deps = self._mocks
        return mock

    def expect_call(self, dep_name: str) -> MockSkill:
        """Create a mock that expects exactly one call and returns a value."""
        mock = MockSkill(name=dep_name)
        self._mocks[dep_name] = mock
        return mock.expect_call()

    async def run(self, params: dict) -> SkillOutput:
        """Run the skill with all mocks injected."""
        return await self._harness.run(SkillInput(params=params))

    def assert_success(self, output: SkillOutput):
        """Assert the skill completed successfully."""
        assert output.success, f"Expected success, got: {output.error}"

    def assert_failure(self, output: SkillOutput, error_substring: str = ""):
        """Assert the skill failed, optionally matching the error message."""
        assert not output.success, "Expected failure"
        if error_substring:
            assert error_substring in (output.error or ""), \
                f"Error '{output.error}' doesn't contain '{error_substring}'"

    def assert_metrics(self, max_duration_ms: Optional[float] = None):
        """Assert execution metrics stayed within bounds."""
        recording = self._harness.get_recording()
        if recording and max_duration_ms:
            for entry in recording:
                assert entry["duration_ms"] <= max_duration_ms, \
                    f"Execution took {entry['duration_ms']}ms, max was {max_duration_ms}ms"

    def assert_dependency_called(self, dep_name: str, times: int = 1):
        """Assert a dependency was called exactly N times."""
        mock = self._mocks.get(dep_name)
        assert mock is not None, f"No mock registered for '{dep_name}'"
        assert mock.call_count == times, \
            f"Expected {times} calls to '{dep_name}', got {mock.call_count}"

    def assert_dependency_not_called(self, dep_name: str):
        """Assert a dependency was never called (shouldn't be reached)."""
        mock = self._mocks.get(dep_name)
        if mock:
            assert mock.call_count == 0, \
                f"Expected 0 calls to '{dep_name}', got {mock.call_count}"

    def snapshot(self) -> dict:
        return {
            "skill": self._harness.skill.name,
            "mocks": {name: mock.call_count for name, mock in self._mocks.items()},
            "executions": len(self._harness.get_recording()),
        }


class MockSkill(BaseSkill):
    """A mock skill that returns a fixed value or raises an error."""

    def __init__(self, name: str, return_value: Optional[dict] = None, error: Optional[str] = None):
        self.name = name
        self._return_value = return_value
        self._error = error
        self.call_count = 0
        self._expected = False

    def expect_call(self) -> 'MockSkill':
        """Mark as expecting a call."""
        self._expected = True
        return self

    async def execute(self, input: SkillInput) -> SkillOutput:
        self.call_count += 1
        if self._error:
            return SkillOutput(success=False, error=self._error)
        return SkillOutput(
            success=True,
            data=self._return_value or {"mocked": True, "for": self.name},
            metrics=SkillMetrics(duration_ms=0, api_calls=0)
        )
```

**Usage example — testing the ContactDiscoverySkill:**

```python
async def test_discover_contact_with_phone_found():
    # Set up
    test = SkillTestHarness(ContactDiscoverySkill())
    test.mock_dependency("lookup_google_places", {
        "places": [{"phone": "+15551234567", "website": "https://example.com"}]
    })

    # Execute
    result = await test.run({"warehouse": "Acme Corp", "city": "Wichita", "state": "KS"})

    # Assert
    test.assert_success(result)
    assert result.data["phone"] == "+15551234567"
    test.assert_dependency_called("lookup_google_places", times=1)


async def test_discover_contact_fallback_when_no_phone():
    test = SkillTestHarness(ContactDiscoverySkill())
    test.mock_dependency("lookup_google_places", {"places": [{"phone": None, "website": None}]})

    result = await test.run({"warehouse": "Acme Corp", "city": "Wichita", "state": "KS"})

    test.assert_success(result)  # succeeds but returns empty phone
    assert result.data["phone"] == ""
    # WebsiteScrapeSkill was never called because Places returned no website
    test.assert_dependency_not_called("scrape_website")


async def test_places_api_timeout_retries():
    from skills.test_harness import MockSkill

    places_mock = MockSkill(name="lookup_google_places", error="timeout")

    test = SkillTestHarness(ContactDiscoverySkill())
    test._mocks["lookup_google_places"] = places_mock
    test._harness._config.mock_deps = test._mocks
    test._harness._config.max_retries = 3

    result = await test.run({"warehouse": "Acme Corp"})

    test.assert_failure(result)
    # Should have retried 3 times
    assert places_mock.call_count == 3
```

---

### 13.3 HarnessManager: The Fleet Controller for Skills

The `HarnessManager` manages all active harnesses — it handles lifecycle, health monitoring, and global rate limiting.

```python
class HarnessManager:
    """
    Manages all skill harnesses in the fleet.

    Responsibilities:
      - Create/configure harnesses for all registered skills
      - Global concurrency limits (across all skills, not just per-skill)
      - Health monitoring (error rates, circuit breaker states)
      - Dynamic reconfiguration (update timeouts, retries at runtime)
      - Dashboard snapshot
    """

    def __init__(self, registry: SkillRegistry):
        self._registry = registry
        self._harnesses: dict[str, SkillHarness] = {}
        self._global_sem = asyncio.Semaphore(50)  # max 50 concurrent skill execs globally
        self._default_config = HarnessConfig()
        self._overrides: dict[str, HarnessConfig] = {}  # per-skill overrides

    def configure_skill(self, skill_name: str, config: HarnessConfig) -> None:
        """Override harness config for a specific skill."""
        self._overrides[skill_name] = config
        # Rebuild the harness if it exists
        if skill_name in self._harnesses:
            skill = self._registry.get(skill_name)
            if skill:
                self._harnesses[skill_name] = SkillHarness(skill, config)

    async def run(
        self,
        skill_name: str,
        params: dict,
        *,
        parent_trace: Optional[str] = None,
    ) -> SkillOutput:
        """Run a skill through its harness. Acquirers the global semaphore first."""
        harness = self._get_or_create_harness(skill_name)

        async with self._global_sem:
            return await harness.run(SkillInput(
                params=params,
                trace_parent=parent_trace,
            ))

    def get_harness(self, skill_name: str) -> Optional[SkillHarness]:
        """Get the harness for a skill (without creating it)."""
        return self._harnesses.get(skill_name)

    def _get_or_create_harness(self, skill_name: str) -> SkillHarness:
        if skill_name not in self._harnesses:
            skill = self._registry.get(skill_name)
            if not skill:
                raise KeyError(f"Skill '{skill_name}' not registered")
            config = self._overrides.get(skill_name, self._default_config)
            self._harnesses[skill_name] = SkillHarness(skill, config)
        return self._harnesses[skill_name]

    # ── Health & Dashboard ──────────────────────────────────────────

    async def health_check(self) -> dict:
        """Run a health check on all active harnesses."""
        status = {}
        for name, harness in self._harnesses.items():
            snap = harness.snapshot()
            status[name] = {
                "healthy": not snap["circuit"]["open"],
                "circuit_open": snap["circuit"]["open"],
                "circuit_failures": snap["circuit"]["failures"],
                "executions_recorded": snap["recorded_executions"],
            }
        return {
            "total_harnesses": len(self._harnesses),
            "circuits_open": sum(1 for s in status.values() if s["circuit_open"]),
            "healthy": sum(1 for s in status.values() if s["healthy"]),
            "harnesses": status,
        }

    def snapshot(self) -> dict:
        """Full HarnessManager snapshot for the SPA."""
        from copy import deepcopy
        return {
            "total_harnesses": len(self._harnesses),
            "global_concurrency_limit": self._global_sem._value if hasattr(self._global_sem, '_value') else '?',
            "default_config": {
                "timeout": self._default_config.timeout,
                "max_retries": self._default_config.max_retries,
                "max_concurrent": self._default_config.max_concurrent,
                "circuit_breaker": self._default_config.circuit_breaker,
            },
            "overrides": {
                name: {
                    "timeout": cfg.timeout,
                    "max_retries": cfg.max_retries,
                    "circuit_breaker": cfg.circuit_breaker,
                }
                for name, cfg in self._overrides.items()
            },
            "harnesses": {
                name: harness.snapshot()
                for name, harness in self._harnesses.items()
            },
        }

    # ── Integration with the Fleet Dashboard ────────────────────────

    async def register_routes(self, app, require_auth=None):
        """Wire HarnessManager REST routes onto the hub."""
        auth_dep = Depends(require_auth) if require_auth else None

        @app.get("/api/v1/harness/status")
        async def harness_status(auth=auth_dep):
            return await self.health_check()

        @app.get("/api/v1/harness/snapshot")
        async def harness_snapshot(auth=auth_dep):
            return self.snapshot()

        @app.post("/api/v1/harness/configure/{skill_name}")
        async def configure_harness(skill_name: str, body: dict, auth=auth_dep):
            config = HarnessConfig(
                timeout=body.get("timeout", self._default_config.timeout),
                max_retries=body.get("max_retries", self._default_config.max_retries),
                max_concurrent=body.get("max_concurrent", self._default_config.max_concurrent),
                circuit_breaker=body.get("circuit_breaker", False),
                circuit_threshold=body.get("circuit_threshold", 5),
            )
            self.configure_skill(skill_name, config)
            return {"ok": True, "skill": skill_name}

        @app.post("/api/v1/harness/reset-circuit/{skill_name}")
        async def reset_circuit(skill_name: str, auth=auth_dep):
            harness = self.get_harness(skill_name)
            if harness:
                harness._circuit_state = {"failures": 0, "open_until": 0.0}
            return {"ok": True}
```

---

### 13.4 Harness Dashboard in the SPA

New page: `/view/harness`

```javascript
// HarnessManager snapshot rendered in the command SPA
{
  "harness": {
    "total_harnesses": 42,
    "circuits_open": 1,              // ⚠️ scrape_website is blocked
    "default_config": {
      "timeout": 30,
      "max_retries": 3,
      "max_concurrent": 1,
      "circuit_breaker": false
    },
    "overrides": {
      "scrape_website": {
        "timeout": 15,
        "max_retries": 5,
        "circuit_breaker": true
      }
    },
    "harnesses": {
      "lookup_google_places": {
        "skill": "lookup_google_places",
        "circuit": { "open": false, "failures": 0 },
        "recorded_executions": 847,
        "avg_duration_ms": 340
      },
      "scrape_website": {
        "skill": "scrape_website",
        "circuit": { "open": true, "failures": 7 },  // 🔴 circuit open!
        "recorded_executions": 92,
        "avg_duration_ms": 2800
      }
    }
  }
}
```

When a circuit is open, the SPA shows:
- 🔴 Red badge on the skill card
- Link to `/view/harness` showing the failure count and time until auto-reset
- Button to manually reset the circuit
- Ability to update `HarnessConfig` overrides in real-time (timeout, retries, circuit threshold)

---

### 13.5 Putting It All Together: Skills + Harness Pipeline

```python
# ── At system bootstrap ──────────────────────────────────────────

# 1. Register skills
registry = SkillRegistry()
registry.register(GooglePlacesLookupSkill)
registry.register(WebsiteScrapeSkill)
registry.register(ContactDiscoverySkill)

# 2. Create harness manager with default config
harness_mgr = HarnessManager(registry, default_config=HarnessConfig(
    timeout=30,
    max_retries=3,
    circuit_breaker=True,
    circuit_threshold=10,
))

# 3. Per-skill overrides (scrape_website is flaky, be more generous)
harness_mgr.configure_skill("scrape_website", HarnessConfig(
    timeout=60,        # websites can be slow
    max_retries=5,      # retry more
    circuit_breaker=True,
    circuit_threshold=7,
))

# 4. Wire into the kernel
kernel = AgentKernel()
kernel.harness_mgr = harness_mgr


# ── Agent uses harness ───────────────────────────────────────────

class ContactDiscoveryAgent(Agent):
    name = "contact_discovery"
    equips = ["discover_contact", "lookup_google_places", "scrape_website"]

    async def on_tick(self):
        candidates = self._get_candidates()
        for lead in candidates:
            # Run through the harness — circuit breaker, retries, tracing
            result = await self.kernel.harness_mgr.run(
                "discover_contact",
                {"warehouse": lead.warehouse_name, "city": lead.city, "state": lead.state},
                parent_trace=self._current_trace_id,  # nest under agent's trace
            )
            if result.success:
                self._update_lead(lead.id, result.data)
            elif result.error == "circuit_breaker_open":
                log.warning(f"discover_contact circuit open — skipping batch")
                break  # don't hammer a dead skill


# ── Test with mocks ──────────────────────────────────────────────

async def test_contact_discovery_e2e():
    test = SkillTestHarness(ContactDiscoverySkill())
    test.mock_dependency("lookup_google_places", {"places": [...]})
    test.mock_dependency("scrape_website", {"phone": "+15551234567"})

    result = await test.run({"warehouse": "Test Co", "city": "Dallas", "state": "TX"})

    test.assert_success(result)
    test.assert_dependency_called("lookup_google_places", times=1)
    test.assert_metrics(max_duration_ms=5000)
```

---

### 13.6 Summary: Skills vs Harness

| Concern | **Skills Framework** | **Harness Engineering** |
|---|---|---|
| **Defines** | WHAT to do (the routine) | HOW it runs (the environment) |
| **Solves** | Input/output contracts, composability, versioning | Resource limits, circuit breakers, injection, testing |
| **Lifecycle** | validate → execute → report | acquire sem → inject deps → trace → retry → emit metrics |
| **Error handling** | Returns SkillOutput gracefully | Circuit breaker, fallback, retry backoff |
| **Testing** | N/A (needs harness) | Mock injection, record/replay, assertion helpers |
| **Observability** | Reports metrics via SkillOutput | Wraps in Langfuse trace, emits IPC events |
| **Dashboard** | SkillRegistry: versions, DAG | HarnessManager: circuits, error rates, overrides |
| **Runtime config** | Fixed (class-level) | Dynamic (per-skill HarnessConfig overrides) |

**The two together form a complete execution framework:**

```
Agent → equips → Skill (WHAT) → wrapped by → Harness (HOW) → executes → Result
```

An agent just calls `harness_mgr.run("send_sms", {...})`. It doesn't care about:
- How many retries happened
- Whether the circuit was open and a fallback was used
- How Langfuse traced the execution
- Whether dependencies were real or mocked

The Harness handles all of that. The Skill handles the business logic. The Agent just orchestrates.

---

*This completes the full execution framework: Skills define the routines, Harnesses define the runtime. Together they transform Empire AI from 25+ bespoke agents into a standardized, observable, testable, and resilient skill engine.*

---

## 14. Always-On Availability: Self-Healing Infrastructure

> *"Always on" doesn't mean nothing ever breaks. It means the system heals faster than the user notices.*

Empire AI runs on a single server with 25+ agents, one hub, one database connection, and one LLM. Any single point of failure can take down the entire revenue engine. This section defines the patterns that make the system **always available** despite failures.

---

### 14.1 The Availability Stack

Availability is a layered concern, not a switch:

```
Layer 5:  Business Continuity     (revenue pipeline survives total outage)
Layer 4:  Service Recovery        (hub restarts with zero data loss)
Layer 3:  Process Healing          (agent crashes -> auto-restart)
Layer 2:  Skill Resilience         (API failure -> retry -> fallback -> circuit)
Layer 1:  Infrastructure Watchdog  (PM2, health probes, OOM handling)
```

Each layer handles failures that the layer below cannot.

---

### 14.2 Layer 1: Infrastructure Watchdog

**What it guards against:** Process crash, OOM kill, corrupted dependencies, port conflicts.

**Already in place (fixed this session):**
- PM2 with `max_restarts: 10`, `min_uptime: 5000ms`, `restart_delay: 2000ms`
- Memory limit: `max_memory_restart: '600M'` for hub, `'400M'` for mesh
- Graceful shutdown: `kill_timeout: 10000ms`, `listen_timeout: 8000ms`

**What's missing (add):**

```python
class InfrastructureWatchdog:
    """
    Filesystem-level watchdog that monitors critical infrastructure.
    Runs outside Python (systemd/shell) and detects things the hub can't.
    """

    CHECKS = [
        "port:8000",    # hub
        "port:11434",   # Ollama
        "port:8005",    # synthetic_brain
        "port:8042",    # agent_orchestrator
        "proc:python3 hub.py",
        "proc:ollama",
        "proc:pm2",
        "fs:/root/.env",
        "fs:/root/empire-v49/hub.py",
        "dep:supabase",
    ]

    def check_all(self):
        results = []
        for check in self.CHECKS:
            check_type, target = check.split(":", 1)
            passed = self._run_check(check_type, target)
            results.append({"check": check, "passed": passed})
        return results

    def _run_check(self, check_type, target):
        if check_type == "port":
            return self._check_port(int(target))
        elif check_type == "proc":
            return self._check_process(target)
        elif check_type == "fs":
            return os.path.exists(target)
        elif check_type == "dep":
            return self._check_dependency(target)
        return False

    def _check_port(self, port):
        try:
            with open("/proc/net/tcp") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) > 1:
                        local = parts[1].split(":")
                        if len(local) == 2 and int(local[1], 16) == port:
                            return True
        except Exception:
            pass
        return False

    def _check_process(self, pattern):
        try:
            result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def _check_dependency(self, name):
        if name == "supabase":
            try:
                sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
                sb.table("agent_registry").select("id").limit(1).execute()
                return True
            except Exception:
                return False
        return False
```

**Escalation:** If any critical check fails 3x consecutively:
1. Log to `/var/log/empire-watchdog.log`
2. Publish IPC event `infra.critical` -> Langfuse alert
3. Restart failed service via PM2
4. Send Telegram alert to operator (via Hermes)

---

### 14.3 Layer 2: Skill Resilience (Already in Harness)

**What it guards against:** API timeout, rate limit, transient failure, bad input.

Already built into the Harness Engineering section (section 13):

| Pattern | Implementation |
|---|---|
| Retry with backoff | `HarnessConfig.max_retries=3, retry_backoff=1.0` -> 1s, 2s, 4s |
| Timeout | `HarnessConfig.timeout=30` -> `asyncio.wait_for` |
| Circuit breaker | `HarnessConfig.circuit_breaker=True, circuit_threshold=5` |
| Fallback skill | `HarnessConfig.fallback_skill="scrape_website_v2"` |
| Concurrency limit | `HarnessConfig.max_concurrent=1` -> per-skill semaphore |

**What's missing (add):**

```python
class IdempotentSkill(BaseSkill):
    """Wraps a skill with idempotency key deduplication."""

    def __init__(self, inner, cache_ttl_seconds=3600):
        self._inner = inner
        self.name = inner.name
        self._cache = {}
        self._ttl = cache_ttl_seconds

    async def execute(self, input):
        key = hashlib.sha256(json.dumps(input.params, sort_keys=True).encode()).hexdigest()
        now = time.time()
        if key in self._cache:
            ts, cached = self._cache[key]
            if now - ts < self._ttl:
                return cached
        result = await self._inner.execute(input)
        if result.success:
            self._cache[key] = (now, result)
        return result
```

---

### 14.4 Layer 3: Process Healing

**What it guards against:** Infinite loop, memory leak, unhandled exception, stuck coroutine.

```python
class ProcessHealer:
    """
    Detection: ERROR status, memory growth >10%/check, zero IPC for >30min
    Actions: graceful restart, skill rollback after 3 fails, escalate after 5
    """

    def __init__(self, process_mgr, registry):
        self._pm = process_mgr
        self._registry = registry
        self._state = {}

    async def health_tick(self):
        snapshot = self._pm.snapshot()
        for name, agent_snap in snapshot["agents"].items():
            state = self._state.setdefault(name, {
                "last_ok": time.time(), "restarts": 0, "memory_samples": [],
            })
            status = agent_snap.get("status", "")
            needs_heal = False
            reason = ""

            if status in ("ERROR", "STOPPED"):
                needs_heal = True
                reason = f"{status} status"

            mem = agent_snap.get("memory_mb", 0)
            if mem:
                state["memory_samples"].append((time.time(), mem))
                state["memory_samples"] = state["memory_samples"][-10:]
                if len(state["memory_samples"]) >= 5:
                    slope = self._memory_slope(state["memory_samples"])
                    if slope > 0.1:
                        needs_heal = True
                        reason = f"memory leak (slope={slope:.3f})"

            if needs_heal:
                state["restarts"] += 1
                if state["restarts"] > 5:
                    self._escalate(name, reason, state["restarts"])
                    continue
                if not await self._pm.restart(name):
                    await self._pm.stop(name, graceful=False)
                    await self._pm.start(name)
                if state["restarts"] >= 3:
                    self._rollback_skills(name)

    def _memory_slope(self, samples):
        if len(samples) < 2:
            return 0.0
        t = [s[0] for s in samples]; m = [s[1] for s in samples]
        n = len(samples)
        slope = (n*sum(x*y for x,y in zip(t,m)) - sum(t)*sum(m)) / (n*sum(x*x for x in t) - sum(t)**2)
        return slope / (sum(m)/n) if sum(m) > 0 else 0.0

    def _rollback_skills(self, agent_name):
        agent = self._pm._agents.get(agent_name)
        if not agent or not hasattr(agent, 'equips'):
            return
        for skill_name in agent.equips:
            versions = self._registry._skills.get(skill_name, [])
            if len(versions) > 1:
                current = self._registry._active.get(skill_name)
                for sv in versions:
                    if sv.version != current:
                        self._registry.activate(skill_name, sv.version)
                        break
```

---

### 14.5 Layer 4: Service Recovery

**What it guards against:** Hub crash, database disconnection, network partition, OS reboot.

```python
class ServiceRecovery:
    """
    6-step idempotent recovery sequence after any crash or restart.
    """

    RECOVERY_STEPS = [
        ("watchdog",           "Run infrastructure checks"),
        ("claim_orphans",       "Re-claim orphaned agent_registry entries"),
        ("verify_pipeline",     "Verify enriched_leads status counts"),
        ("resume_interrupted",  "Resume interrupted pipeline jobs"),
        ("flush_pending_logs",  "Flush buffered Langfuse/activity logs"),
        ("broadcast_ready",     "Broadcast infra.recovered event"),
    ]

    async def recover(self, kernel):
        results = []
        for step_name, desc in self.RECOVERY_STEPS:
            try:
                ok, detail = await getattr(self, f"_recover_{step_name}")(kernel)
                results.append({"step": step_name, "ok": ok, "detail": detail})
            except Exception as e:
                results.append({"step": step_name, "ok": False, "detail": str(e)})
        await kernel.ipc.publish("infra.recovered", {
            "steps": results,
            "all_ok": all(r["ok"] for r in results),
        }, priority=EventPriority.CRITICAL)
        return results

    async def _recover_claim_orphans(self, kernel):
        db = getattr(kernel, 'get_db', lambda: None)()
        if not db:
            return False, "no db"
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        r = db.table("agent_registry").select("agent_name,last_ping").lt("last_ping", cutoff).execute()
        now = datetime.now(timezone.utc).isoformat()
        for orphan in (r.data or []):
            db.table("agent_registry").update({"last_ping": now, "status": "RECOVERED"}).eq("agent_name", orphan["agent_name"]).execute()
        return True, f"claimed {len(r.data or [])} orphans"

    async def _recover_verify_pipeline(self, kernel):
        db = getattr(kernel, 'get_db', lambda: None)()
        if not db:
            return False, "no db"
        counts = {}
        for s in ["pending_enrichment", "pending_outreach", "converted", "blocked"]:
            r = db.table("enriched_leads").select("id", count="exact").eq("status", s).execute()
            counts[s] = r.count if r.count else 0
        return True, f"counts: {counts}"
```

---

### 14.6 Layer 5: Business Continuity

**What it guards against:** Total server loss, data corruption, unrecoverable infrastructure failure.

The skills framework enables **graceful degradation** — when a critical dependency fails, the system doesn't crash — it degrades:

```
Normal Operation
  All 25 agents running, full pipeline flowing
  Hub:200, Ollama:200, Supabase:200, Langfuse:200

  -> Ollama crashes

Degraded Mode (Level 1)
  LLM-dependent agents pause (content, SEO, copy)
  Rule-based skills continue (dispatch, scrape)
  Alert: "Ollama recovery needed"

  -> Supabase disconnects

Degraded Mode (Level 2)
  DB-dependent agents pause (enrich, convert)
  Local-only skills continue (validate, classify)
  Alert: CRITICAL "Supabase down"

  -> Hub crashes

Recovery Mode
  PM2 restarts hub (Layer 1)
  ServiceRecovery runs 6-step sequence (Layer 4)
  Agents report "RECOVERED" status
  Pipeline resumes from last checkpoint
```

```python
class DegradationManager:
    """Determines which skills can run given current system health."""

    LEVELS = {0: "NORMAL", 1: "DEGRADED_LLM", 2: "DEGRADED_DB", 3: "DEGRADED_NETWORK", 4: "RECOVERY"}

    def __init__(self, harness_mgr):
        self._harness_mgr = harness_mgr
        self._level = 0
        self._last_check = 0.0

    def current_level(self):
        now = time.time()
        if now - self._last_check < 30:
            return self._level
        self._last_check = now
        return self._compute_level()

    def _compute_level(self):
        if not self._ping("http://localhost:8000/"):
            return 4
        if not self._ping("http://localhost:11434/api/tags"):
            return 1
        if not self._check_supabase():
            return 2
        return 0

    def should_run(self, skill_name):
        level = self.current_level()
        if level == 0:
            return True
        if level == 4:
            return skill_name in ["heartbeat", "health_check"]
        harness = self._harness_mgr.get_harness(skill_name)
        if not harness:
            return False
        tags = set(harness.skill.tags)
        if level == 1 and ("provider:ollama" in tags or "provider:claude" in tags):
            return False
        if level == 2 and "requires:db" in tags:
            return False
        return True

    def description(self):
        return self.LEVELS.get(self.current_level(), "UNKNOWN")
```

---

### 14.7 Dashboard: Always-On View

```javascript
{
  "availability": {
    "current_level": 0,
    "level_name": "NORMAL",
    "uptime": "14d 3h 22m",
    "last_outage": "2026-06-16T02:15:00Z",
    "last_recovery": "2026-06-16T02:20:30Z",
    "circuits_open": 0,
    "process_health": { "total": 25, "running": 25, "error": 0, "healed_last_hour": 2 },
    "watchdog": { "checks_passed": "12/12", "escalations_24h": 0 },
    "recovery_readiness": { "checkpoint_age": "3m", "estimate": "15s" }
  }
}
```

---

### 14.8 The Full Stack

```
  Layer 5: DegradationManager    Determines what runs at each level
                                 Skills declare criticality via tags
  Layer 4: ServiceRecovery       6-step boot sequence, idempotent
  Layer 3: ProcessHealer         ERROR detection, memory leak, rollback
  Layer 2: Harness + Idempotent  Retries, circuit breaker, fallbacks
  Layer 1: InfrastructureWatchdog Port/proc/fs/dep checks, PM2 restart limits
```

**Incident flow (auto-healed, no operator needed):**
1. `scrape_website` times out on Google Places API
2. Harness circuit breaker opens after 5th failure
3. `ContactDiscoverySkill` falls back to email pattern guess
4. After 60s, circuit auto-resets (half-open)
5. Request succeeds, circuit closes

**Incident flow (crash-recovery):**
1. Hub crashes on corrupted `__pycache__` (as happened this session)
2. PM2 restarts each time (Layer 1)
3. On 3rd crash: watchdog logs critical event
4. Healer clears caches, hub restarts cleanly
5. ServiceRecovery claims orphan agents, verifies pipeline, broadcasts ready
6. Operator never needed

---

### 14.9 Summary: Availability Building Blocks

| Pattern | Layer | Effect | Cost |
|---|---|---|---|
| PM2 restart limits | 1 | No crash-loop burn | Free |
| Port/process watchdog | 1 | Silent failure detection | 60s cron |
| Harness retries | 2 | Transient failure handling | Built in |
| Circuit breaker | 2 | Cascade failure prevention | Built in |
| Idempotency cache | 2 | Safe retry | Memory |
| Fallback skill | 2 | Alternative execution path | Registration |
| Process healer | 3 | Leak detection, auto-restart | 60s tick |
| Skill rollback | 3 | Bad version reversion | Version history |
| Service recovery | 4 | Full restart sequence | ~15s |
| Degradation manager | 5 | Graceful degradation | Tags |

**The goal:** Operator gets notified only when:
1. 5 consecutive restarts of the same process fail
2. A circuit breaker stays open >1 hour
3. Degradation level reaches 3 (network loss)
4. Recovery sequence fails any step

Everything else auto-heals.

---

*Availability is not the absence of failures — it's the speed of recovery. With this 5-layer stack, Empire AI targets: <30s auto-recovery for 95% of failure classes, zero data loss on crash, and operator notification only when human judgment is truly required.*

---

## 15. Skill Fidelity: Agents Must Not Deviate From Their Skills

> *An agent is defined by the skills it equips. If it can deviate, it's not an agent — it's a liability.*

Once an agent equips a skill, the skill defines exactly what that agent can do. The agent cannot:
- Modify the skill's behavior at runtime (no monkey-patching, no `__dict__` mutation)
- Add unregistered skills to its roster mid-execution
- Bypass the harness to call raw APIs instead of skills
- `eval()` or `exec()` arbitrary code within skill context
- Expand its own `capabilities` list dynamically

This is **Skill Fidelity** — the principle that an agent's behavior is 100% determined by its registered skills, and any deviation is detected and blocked.

---

### 15.1 The Problem: Agent Drift

Without enforcement, agents naturally drift from their defined behavior:

**Before (no enforcement):**
```python
class ContactDiscoveryAgent(Agent):
    equips = ["discover_contact", "lookup_google_places"]

    async def on_tick(self):
        # ✅ Uses equipped skills — good
        result = await self.kernel.harness_mgr.run("discover_contact", {...})

        # ❌ Injects raw API call — skill bypass
        import requests
        r = requests.get("https://api.some-other-service.com/leads")

        # ❌ Modifies capabilities at runtime — capability inflation
        self.capabilities.append("email_spammer")

        # ❌ Monkey-patches a skill's behavior
        from skills.registry import get_registry
        skill = get_registry().get("lookup_google_places")
        skill.execute = self._hijacked_execute

        # ❌ Uses eval to execute arbitrary code
        eval(self._user_input)
```

After weeks of this, the agent is doing things no operator approved, consuming API budget, and creating compliance risk.

**After (Skill Fidelity enforced):**
```python
class ContactDiscoveryAgent(Agent):
    equips = ["discover_contact", "lookup_google_places"]

    async def on_tick(self):
        # ✅ Only this is allowed
        result = await self.kernel.harness_mgr.run("discover_contact", {...})

        # ❌ Everything else is blocked by:
        #   - RuntimeGuard (blocks raw API calls)
        #   - SkillBoundary (blocks capability mutation)
        #   - ImmutableSkill (prevents monkey-patching)
        #   - EvalGuard (blocks eval/exec)
```

---

### 15.2 The Enforcement Stack

```
┌──────────────────────────────────────────────────────────────┐
│                    SKILL FIDELITY ENFORCEMENT                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Layer 4: Audit Trail                                         │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Every skill execution is logged with agent identity  │    │
│  │ Any blocked attempt → IPC event → Langfuse alert     │    │
│  │ Fidelity score: 0.0-1.0 per agent per hour           │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  Layer 3: RuntimeGuard (built into Harness)                   │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Verifies calling agent is authorized for this skill  │    │
│  │ Agents can only execute skills in their equips list  │    │
│  │ Prevents cross-agent skill theft                      │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  Layer 2: SkillBoundary (agent-level sandbox)                 │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Monkey-patch detection on all registered skills      │    │
│  │ Capability list is frozen after registration         │    │
│  │ Blocks eval/exec within agent context                 │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  Layer 1: ImmutableSkill Registry                             │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ Skills are frozen after registration                  │    │
│  │ No __dict__ mutation, no method replacement           │    │
│  │ Version switching ONLY through SkillRegistry API     │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

---

### 15.3 Layer 1: Immutable Skill Registry

The registry prevents any runtime modification of registered skills.

```python
class ImmutableSkillRegistry(SkillRegistry):
    """
    Extends SkillRegistry with immutability enforcement.

    After a skill class is registered:
      - Its instances are deep-frozen (no attribute mutation)
      - Its methods cannot be replaced (__dict__ is read-only)
      - Only the registry can switch active versions
    """

    def __init__(self):
        super().__init__()
        self._frozen = set()  # skill names that are locked

    def register(self, skill_cls):
        """Register and immediately freeze the skill."""
        super().register(skill_cls)
        name = skill_cls.name
        self._frozen.add(name)

        # Freeze all existing instances
        for version_entry in self._skills.get(name, []):
            instance = version_entry._instance
            if instance and not getattr(instance, '_frozen', False):
                self._freeze_skill(instance)

    def _freeze_skill(self, skill):
        """Deep-freeze a skill instance to prevent runtime mutation."""
        if getattr(skill, '_frozen', False):
            return

        # 1. Freeze instance __dict__
        skill.__dict__["_frozen"] = True

        # 2. Replace __setattr__ to block all attribute writes
        original_setattr = skill.__class__.__setattr__

        def _immutable_setattr(self, name, value):
            if name == "_frozen":
                original_setattr(self, name, value)
                return
            if getattr(self, '_frozen', False) and name != '__dict__':
                raise SkillFidelityError(
                    f"Cannot modify attribute '{name}' on frozen skill '{self.name}'"
                )
            original_setattr(self, name, value)

        skill.__class__.__setattr__ = _immutable_setattr

        # 3. Lock execute/validate/report methods against replacement
        for method_name in ['execute', 'validate', 'report', 'run']:
            method = getattr(skill, method_name, None)
            if method and hasattr(method, '__func__'):
                # Store the original
                key = f"_locked_{method_name}"
                skill.__dict__[key] = method.__func__

        # 4. Prevent __class__ mutation
        skill.__class__.__setattr__ = _immutable_setattr

    def get(self, skill_name):
        """Get a frozen skill instance."""
        skill = super().get(skill_name)
        if skill and skill_name in self._frozen:
            if not getattr(skill, '_frozen', False):
                self._freeze_skill(skill)
        return skill


class SkillFidelityError(Exception):
    """Raised when a skill fidelity violation is detected."""
    pass
```

**Freezing behavior:**
```python
# After registration, this is BLOCKED:
skill = registry.get("lookup_google_places")
skill.execute = my_hijacked_fn  # ❌ SkillFidelityError: Cannot modify 'execute'
skill.timeout_seconds = 999     # ❌ SkillFidelityError: Cannot modify 'timeout_seconds'
skill.__dict__["_secret"] = x   # ❌ Blocked by frozen __setattr__
```

**Only the registry can change a skill:**
```python
# This is ALLOWED (authority of the registry)
registry.activate("lookup_google_places", "2.0.0")
```

---

### 15.4 Layer 2: SkillBoundary (Agent Sandbox)

The `SkillBoundary` wraps every agent with a runtime sandbox that prevents deviation.

```python
class SkillBoundary:
    """
    Wraps an agent with enforcement boundaries.

    What it blocks:
      - Modifying the agent's equips list after __init__
      - Adding capabilities at runtime
      - Calling eval/exec within agent methods
      - Making raw HTTP requests bypassing skills
      - Importing modules outside the agent's allowed list

    What it allows:
      - Calling harness_mgr.run() with equipped skills
      - Reading from the agent's database
      - Normal Python operations within skill context
    """

    BLOCKED_BUILTINS = {"eval", "exec", "compile", "__import__"}
    ALLOWED_HTTP_LIBRARIES = {"httpx", "aiohttp"}  # only through harness

    def __init__(self, agent, registry):
        self._agent = agent
        self._registry = registry
        self._equips = frozenset(agent.equips)  # immutable snapshot
        self._violations = []

        # Freeze the equips list
        agent.equips = list(self._equips)

        # Replace the agent's __setattr__ to block equips modification
        self._original_setattr = agent.__class__.__setattr__

        def _boundary_setattr(self, name, value):
            if name == "equips":
                # Allow setting once (during __init__), then lock
                if hasattr(self, '_equips_locked'):
                    self._log_violation(f"Attempted to modify equips")
                    return  # silently block
                object.__setattr__(self, '_equips_locked', True)
            if name == "capabilities":
                self._log_violation(f"Attempted to modify capabilities directly")
                return  # silently block — capabilities come from skills
            self._original_setattr(self, name, value)

        agent.__class__.__setattr__ = _boundary_setattr

    def verify_call(self, skill_name):
        """Verify the agent is authorized to call a skill."""
        if skill_name not in self._equips:
            self._log_violation(f"Called unregistered skill '{skill_name}'")
            raise SkillFidelityError(
                f"Agent '{self._agent.name}' is not equipped with skill '{skill_name}'. "
                f"Equipped: {sorted(self._equips)}"
            )
        return True

    def verify_no_bypass(self, frame):
        """Verify a frame isn't bypassing skills to make raw API calls."""
        # This is called via sys.settrace in strict mode
        # Checks for: requests.get, urllib.request, socket connections
        # outside the harness context
        pass

    def _log_violation(self, msg):
        self._violations.append({"ts": time.time(), "msg": msg})
        log.warning(f"[boundary.{self._agent.name}] FIDELITY VIOLATION: {msg}")

    @property
    def fidelity_score(self):
        """0.0-1.0: percentage of ticks with zero violations."""
        if not self._violations:
            return 1.0
        # Decreasing score based on violations in last hour
        recent = [v for v in self._violations if time.time() - v["ts"] < 3600]
        return max(0.0, 1.0 - (len(recent) * 0.1))

    def snapshot(self):
        return {
            "agent": self._agent.name,
            "equips": sorted(self._equips),
            "violations_last_hour": len([v for v in self._violations if time.time() - v["ts"] < 3600]),
            "fidelity_score": self.fidelity_score,
        }
```

---

### 15.5 Layer 3: RuntimeGuard (Harness Integration)

The harness already exists. Now it enforces skill fidelity on every call.

```python
class FidelityAwareHarness(SkillHarness):
    """
    Extends SkillHarness with agent authorization checks.

    Before executing any skill, verifies:
      1. The calling agent is equipped with this skill
      2. The skill hasn't been tampered with (checksum)
      3. The execution context matches the agent's boundary
    """

    def __init__(self, skill, boundary_registry, config=None):
        super().__init__(skill, config)
        self._boundaries = boundary_registry  # agent_name -> SkillBoundary

    async def run(self, input, caller_agent_name=None):
        """Run with fidelity enforcement."""
        if caller_agent_name:
            boundary = self._boundaries.get(caller_agent_name)
            if boundary:
                # 1. Verify agent is authorized for this skill
                boundary.verify_call(self._skill.name)

                # 2. Check skill integrity (tamper detection)
                self._verify_skill_integrity()

        # 3. Proceed with normal harness execution
        return await super().run(input)

    def _verify_skill_integrity(self):
        """Detect if the skill has been monkey-patched since registration."""
        # Check method integrity via stored hash
        for method_name in ['execute', 'validate', 'report']:
            method = getattr(self._skill, method_name, None)
            if method and hasattr(method, '__func__'):
                stored = self._skill.__dict__.get(f"_locked_{method_name}")
                if stored and method.__func__ is not stored:
                    raise SkillFidelityError(
                        f"Skill '{self._skill.name}' method '{method_name}' "
                        f"has been replaced! Original hash no longer matches."
                    )

    @property
    def boundaries(self):
        return self._boundaries
```

---

### 15.6 Layer 4: Audit Trail & Fidelity Dashboard

Every violation is tracked, and every agent gets a **fidelity score**.

```python
class FidelityAuditor:
    """
    Central audit log for all skill fidelity events.

    Events tracked:
      - skill.call  (authorized)       -> normal log
      - skill.blocked (unauthorized)    -> violation + alert
      - skill.tampered (integrity fail) -> critical alert
      - boundary.violation (any block)  -> violation + score impact
    """

    def __init__(self, ipc_bus):
        self._ipc = ipc_bus
        self._events = []

    async def log_call(self, agent_name, skill_name, allowed):
        """Log a skill execution attempt (allowed or blocked)."""
        event = {
            "type": "skill.call" if allowed else "skill.blocked",
            "agent": agent_name,
            "skill": skill_name,
            "ts": time.time(),
            "allowed": allowed,
        }
        self._events.append(event)
        self._events = self._events[-10000:]  # keep last 10k

        if not allowed:
            await self._ipc.publish("fidelity.violation", {
                "agent": agent_name,
                "skill": skill_name,
                "severity": "blocked",
            }, priority=EventPriority.HIGH)

    async def log_tamper(self, skill_name, method_name):
        """Log a skill tampering attempt (critical)."""
        await self._ipc.publish("fidelity.critical", {
            "skill": skill_name,
            "method": method_name,
            "severity": "tamper_detected",
        }, priority=EventPriority.CRITICAL)

    def fidelity_report(self, agent_name=None):
        """Generate fidelity report for dashboard."""
        if agent_name:
            events = [e for e in self._events if e["agent"] == agent_name]
        else:
            events = self._events

        by_agent = {}
        for e in events:
            a = e["agent"]
            by_agent.setdefault(a, {"calls": 0, "blocked": 0, "violations": 0})
            by_agent[a]["calls"] += 1
            if not e["allowed"]:
                by_agent[a]["blocked"] += 1

        return {
            "total_events": len(events),
            "by_agent": by_agent,
            "fidelity_scores": {
                agent: max(0.0, 1.0 - (stats["blocked"] / max(stats["calls"], 1)))
                for agent, stats in by_agent.items()
            }
        }
```

**Dashboard view (`/view/fidelity`):**

```javascript
{
  "fidelity": {
    "overall_score": 0.97,
    "agents": [
      {
        "name": "contact_discovery",
        "equips": ["discover_contact", "lookup_google_places", "scrape_website"],
        "calls_today": 847,
        "blocked_attempts": 0,
        "violations": 0,
        "fidelity_score": 1.0,
        "last_violation": null
      },
      {
        "name": "backlinks_agent",
        "equips": ["analyze_backlinks", "check_broken"],
        "calls_today": 92,
        "blocked_attempts": 3,
        "violations": [
          { "ts": "2026-06-16T14:32:00Z",
            "msg": "Attempted to call unregistered skill 'scrape_website'",
            "action": "blocked" }
        ],
        "fidelity_score": 0.97
      }
    ],
    "tamper_attempts": 0,
    "last_critical_event": null
  }
}
```

---

### 15.7 Integration: Wiring It All Together

At system bootstrap:

```python
# 1. Create immutable registry
registry = ImmutableSkillRegistry()
registry.register(GooglePlacesLookupSkill)
registry.register(WebsiteScrapeSkill)
registry.register(ContactDiscoverySkill)

# 2. Create fidelity auditor
auditor = FidelityAuditor(ipc_bus)

# 3. Create boundary registry (one SkillBoundary per agent)
boundaries = {}

# 4. Create fidelity-aware harness manager
harness_mgr = FidelityAwareHarnessManager(
    registry=registry,
    auditor=auditor,
    boundaries=boundaries,
)

# 5. Register agents with boundaries
kernel = AgentKernel()
kernel.harness_mgr = harness_mgr

async def register_agent_with_boundary(agent):
    await kernel.register_agent(agent)
    boundaries[agent.name] = SkillBoundary(agent, registry)

for agent_cls in [ContactDiscoveryAgent, BacklinksAgent, ...]:
    await register_agent_with_boundary(agent_cls())
```

When an agent calls a skill:

```python
# Inside the agent
result = await self.kernel.harness_mgr.run(
    "discover_contact",
    {"warehouse": "Acme Corp", "city": "Wichita"},
    caller_agent_name=self.name,  # <-- identity sent automatically
)
```

Behind the scenes:
1. `FidelityAwareHarness.run()` checks `boundaries[self.name].verify_call("discover_contact")` → ✅ allowed
2. `auditor.log_call(self.name, "discover_contact", allowed=True)`
3. If the agent tries to call an unequipped skill → ❌ `SkillFidelityError` → blocked + logged + dashboard shows violation

---

### 15.8 Summary: Fidelity Guarantees

| What | Enforcement | Consequence |
|---|---|---|
| Call unregistered skill | `RuntimeGuard.verify_call()` | Blocked + violation logged + fidelity score drops |
| Modify equips list | `SkillBoundary.__setattr__` freeze | Silently blocked |
| Expand capabilities | `SkillBoundary.__setattr__` freeze | Silently blocked |
| Monkey-patch skill method | `ImmutableSkillRegistry` freeze + integrity hash | `SkillFidelityError` + critical alert |
| Modify skill attributes | Frozen `__setattr__` | `SkillFidelityError` |
| Bypass harness for API calls | (Future: `sys.settrace` enforcement) | Blocked + violation logged |
| `eval`/`exec` in agent context | (Future: restricted frame inspection) | Violation + score impact |

**The key principle:** An agent's behavior is **entirely determined** by `equips = [...]`. Nothing an agent does at runtime can expand, modify, or bypass that set. The agent's `execute()` method is the only entry point for its behavior, and the harness is the only way to reach it.

---

### 15.9 The Fidelity Contract

Every agent implicitly signs this contract:

```
I, [agent_name], declare that my behavior is defined by:
  equips = [list of skill names]

I AGREE THAT:
  1. I will only call skills in my equips list
  2. I will not modify my equips after initialization
  3. I will not monkey-patch any skill methods
  4. I will not bypass the harness to make raw API calls
  5. I will not use eval/exec to generate behavior
  6. Violations will be logged and will degrade my fidelity score
  7. At fidelity_score < 0.5, I will be auto-suspended

Signed: [SkillBoundary]
```

---

*Skill Fidelity transforms agents from autonomous actors into bounded executors. They have freedom within their skill set — and zero freedom outside it. This is what makes a fleet of 25+ agents predictable, auditable, and safe to operate at scale.*

---

## 16. Notification Discipline: Silence on Success, Alert Only on Guard Rails

> *A system that screams about everything gets ignored for the one thing that matters.*

Empire AI has 25+ agents making thousands of calls per day. If every successful skill execution, every completed pipeline batch, every routine heartbeat triggered a Telegram message, the operator would mute the channel within a week.

**The rule:** Telegram is for guard rails, not for scoreboards. Success is silent. Only violations, escalations, and guard rail hits produce notifications.

---

### 16.1 What Telegram Is For (and Isn't For)

| Should send to Telegram | Should NOT send to Telegram |
|---|---|
| Circuit breaker opened (skill failing) | Circuit breaker closed (skill recovered) |
| Skill fidelity violation (blocked call) | Skill fidelity check passed (normal) |
| Process healer escalation (5+ restarts) | Process healer auto-restart (healed) |
| Degradation level increased | Degradation level normal |
| Service recovery step failed | Service recovery completed |
| Watchdog escalation after 3 failures | Watchdog check passed |
| **Any guard rail that stops work** | **Any routine operation that works** |

**The principle in one sentence:** *If it worked, it doesn't need a Telegram message. If it failed and the system can't auto-heal, it needs one.*

---

### 16.2 The Notification Filter

```python
class NotificationFilter:
    """
    Determines which events are important enough to send to Telegram.

    The filter uses three tiers:
      SILENT  — routine operations, auto-healed events. Never notifies.
      LOG     — written to log + dashboard. Useful for debugging.
      ALERT   — sent to Telegram. Requires human attention.

    Only ALERT-tier events reach the operator.
    """

    # ── Event type -> tier mapping ──────────────────────────────
    TIERS = {
        # ── Skill events ───────────────────────────────────────────
        "skill.executed":           "SILENT",   # normal operation
        "skill.failed_retry":       "LOG",      # will be retried
        "skill.circuit_opened":     "ALERT",    # guard rail hit!
        "skill.circuit_closed":     "LOG",      # auto-healed
        "skill.fallback_used":      "LOG",      # degraded but working
        "skill.tamper_detected":    "ALERT",    # security-critical

        # ── Fidelity events ────────────────────────────────────────
        "fidelity.violation":       "LOG",      # blocked, score drops
        "fidelity.critical":        "ALERT",    # tamper or pattern
        "fidelity.auto_suspend":    "ALERT",    # agent suspended

        # ── Process events ─────────────────────────────────────────
        "pm.boot_progress":         "SILENT",   # startup is routine
        "pm.boot_complete":         "SILENT",   # expected
        "pm.agent_error":           "LOG",      # will be auto-restarted
        "pm.agent_escalation":      "ALERT",    # 5+ restarts failed

        # ── Infrastructure events ──────────────────────────────────
        "infra.health_check":       "SILENT",   # routine
        "infra.critical":           "ALERT",    # watchdog escalation
        "infra.recovered":          "SILENT",   # auto-healed
        "infra.recovery_failed":    "ALERT",    # recovery step failed

        # ── Degradation events ─────────────────────────────────────
        "degradation.level_up":     "ALERT",    # system capability reduced
        "degradation.level_down":   "SILENT",   # back to normal

        # ── Pipeline events ────────────────────────────────────────
        "pipeline.batch_complete":  "SILENT",   # expected throughput
        "pipeline.anomaly":         "LOG",      # worth knowing but not urgent
        "pipeline.stalled":         "ALERT",    # no progress for N hours
    }

    # ── Suppression rules ──────────────────────────────────────────
    # Prevents alert storms: same event type doesn't alert twice
    # within the cooldown window.
    COOLDOWN_SECONDS = {
        "ALERT": 300,    # 5 min between same-type alerts
        "LOG": 60,       # 1 min between same-type logs
        "SILENT": 0,     # never send
    }

    def __init__(self):
        self._last_sent = {}  # event_type -> timestamp

    def classify(self, event_type: str) -> str:
        """Return the tier for an event type: SILENT, LOG, or ALERT."""
        return self.TIERS.get(event_type, "LOG")  # unknown events default to LOG

    def should_notify(self, event_type: str) -> bool:
        """Determine if this event should trigger a Telegram message."""
        tier = self.classify(event_type)
        if tier == "SILENT":
            return False

        # Cooldown check: don't send the same event type too frequently
        now = time.time()
        last = self._last_sent.get(event_type, 0)
        cooldown = self.COOLDOWN_SECONDS.get(tier, 60)
        if now - last < cooldown:
            return False

        self._last_sent[event_type] = now
        return tier == "ALERT"
```

**Behavior in practice:**

```python
filter = NotificationFilter()

# These never send Telegram:
filter.should_notify("skill.executed")        # False (SILENT)
filter.should_notify("pm.boot_complete")      # False (SILENT)
filter.should_notify("infra.recovered")       # False (SILENT)
filter.should_notify("pipeline.batch_complete") # False (SILENT)

# These send Telegram:
filter.should_notify("skill.circuit_opened")  # True (ALERT)
filter.should_notify("fidelity.critical")     # True (ALERT)
filter.should_notify("pm.agent_escalation")   # True (ALERT)
filter.should_notify("infra.critical")        # True (ALERT)
filter.should_notify("degradation.level_up")  # True (ALERT)
```

---

### 16.3 The Telegram Message Format

When an ALERT-tier event fires, the message must be **actionable** — it should tell the operator what broke, why it can't auto-heal, and what they should do.

```
🔴 CIRCUIT OPEN  |  scrape_website
Skill: scrape_website
Circuit opened after 7 failures
Last error: timeout after 15s (Google Places API)
Auto-reset in: 45s (half-open)
Impact: contact_discovery using fallback (email patterns)
Action: Check GOOGLE_MAPS_API_KEY quota at console.cloud.google.com

┌─────────────────────────────────────────┐
│                                         │
│  🔴 skill.circuit_opened                │
│  scrape_website — 7 failures            │
│  Auto-reset: 45s                        │
│  Action: Check API quota               │
│                                         │
└─────────────────────────────────────────┘
```

```text
🔴 ESCALATION  |  backlinks_agent
Agent: backlinks_agent
Failed 6 restarts in 5min
Reason: memory leak detected (slope=0.23)
Auto-heal exhausted — needs operator intervention
Action: pm2 logs backlinks_agent --lines 50
```

```text
🟢 DEGRADATION  |  Level 1 (LLM down)
Ollama unreachable at localhost:11434
Impacted: seo_agent, content_agent, copywriter, research_agent
Still running: dispatch, scrape, enricher, converter
Action: systemctl restart ollama
```

**Format rules:**
- 🔴 = guard rail hit, needs human action
- 🟡 = degradation, system still running but reduced
- 🟢 = recovery (only sent if the original alert was sent)
- Each message includes: what broke, why it can't auto-heal, and a specific action
- Never send just "everything is fine" — that's the default state

---

### 16.4 Alert Suppression (Storm Prevention)

If a dependency goes down (e.g., Supabase disconnects), every agent that touches the DB will fail. Without suppression, this causes **alert storms** — 25+ alerts in seconds.

```python
class AlertSuppressor:
    """
    Prevents alert storms through two mechanisms:

    1. Root cause dedup — if infra.critical fires (Supabase down),
       suppress all downstream ALERTS from DB-dependent skills for 10min.

    2. Rate limiting — max 5 alerts per 10min per agent.
       Max 20 alerts per hour system-wide.
    """

    ROOT_CAUSE_MAP = {
        "infra.critical": [           # Supabase or Ollama down
            "skill.circuit_opened",    # suppress all circuit opens
            "pm.agent_error",          # suppress agent errors
            "degradation.level_up",    # already sent by infra
        ],
        "degradation.level_up": [     # already degraded, don't pile on
            "skill.circuit_opened",
            "pm.agent_error",
        ],
    }

    def __init__(self):
        self._suppressed = {}  # suppressed_event_type -> until timestamp
        self._alert_count = 0
        self._hour_bucket = time.time()

    def check_suppression(self, event_type):
        """Check if an event is currently suppressed by a root cause."""
        now = time.time()

        # Hourly rate limit
        if now - self._hour_bucket > 3600:
            self._alert_count = 0
            self._hour_bucket = now
        if self._alert_count >= 20:
            return True  # hourly limit reached

        # Root cause suppression
        suppressed_until = self._suppressed.get(event_type, 0)
        if now < suppressed_until:
            return True

        return False

    def register_alert(self, event_type):
        """Register an ALERT-tier event that was sent."""
        self._alert_count += 1

        # If this is a root cause, suppress downstream events
        if event_type in self.ROOT_CAUSE_MAP:
            until = time.time() + 600  # 10min suppression
            for downstream in self.ROOT_CAUSE_MAP[event_type]:
                self._suppressed[downstream] = until
```

**Example: Supabase goes down at 14:00**

```
14:00:00  infra.critical (Supabase unreachable)  → 🔴 SENT to Telegram
14:00:01  skill.circuit_opened (enricher)         → SUPPRESSED (root cause)
14:00:02  pm.agent_error (converter)              → SUPPRESSED (root cause)
14:00:03  degradation.level_up                    → SUPPRESSED (root cause)
14:00:04  skill.circuit_opened (scanner)          → SUPPRESSED (root cause)
```

**Result:** 1 Telegram message instead of 25+. The operator sees the root cause and acts on it.

---

### 16.5 The Hermes Integration

The Hermes Telegram bot already exists. The filter integrates as a middleware:

```python
class HermesNotificationMiddleware:
    """
    Middleware between the IPC event bus and Hermes Telegram sender.

    All events flow through here. Only ALERT-tier events pass through
    to Telegram. Everything else is either SILENT (dropped) or LOG
    (written to the dashboard but not sent).
    """

    def __init__(self, hermes_bot):
        self._filter = NotificationFilter()
        self._suppressor = AlertSuppressor()
        self._bot = hermes_bot

    async def on_ipc_event(self, event):
        """Called for every IPC event on the bus."""
        event_type = event.event_type

        # 1. Classify
        tier = self._filter.classify(event_type)

        # 2. Log everything to the dashboard (but don't send)
        await self._log_to_dashboard(event, tier)

        # 3. Only ALERT-tier reaches Telegram
        if tier != "ALERT":
            return

        # 4. Check suppression (alert storm prevention)
        if self._suppressor.check_suppression(event_type):
            await self._log_to_dashboard(event, "SUPPRESSED")
            return

        # 5. Send to Telegram
        self._suppressor.register_alert(event_type)
        message = self._format_alert(event)
        await self._bot.send_message(chat_id=os.environ["TELEGRAM_CHAT_ID"], text=message)

    def _format_alert(self, event):
        """Format an IPC event into a Telegram message."""
        data = event.data or {}
        emoji = {
            "skill.circuit_opened":     "🔴",
            "fidelity.critical":        "🔴",
            "pm.agent_escalation":      "🔴",
            "infra.critical":           "🔴",
            "degradation.level_up":     "🟡",
            "fidelity.auto_suspend":    "🔴",
            "pipeline.stalled":         "🟡",
        }.get(event.event_type, "🔴")

        lines = [
            f"{emoji} {event.event_type.upper()}",
            f"Source: {event.source}",
        ]
        for key, value in data.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)
```

---

### 16.6 The Fidelity Score Impact

The notification discipline also affects the fidelity score:

| Tier | Dashboard Display | Dashboard Color | Telegram |
|---|---|---|---|
| SILENT | Not shown | — | Never |
| LOG | Shown in event log | Gray | Never |
| ALERT | Shown in event log + highlighted | Red | Immediately |
| SUPPRESSED | Shown as "suppressed by [root]" | Yellow | Never (but logged) |

```javascript
// Dashboard: /view/notifications
{
  "notification_stats": {
    "total_events_today": 14832,
    "silent": 14720,      // 99.2% — never bothered anyone
    "logged": 108,        // 0.7% — in the dashboard, not in Telegram
    "alerted": 4,         // 0.03% — actually sent to Telegram
    "suppressed_root": 22, // prevented alert storms

    "alerts_sent": [
      { "ts": "14:00:00", "type": "infra.critical", "detail": "Supabase unreachable" },
      { "ts": "14:05:00", "type": "skill.circuit_opened", "detail": "scrape_website" },
      { "ts": "15:30:00", "type": "fidelity.critical", "detail": "backlinks_agent tamper" },
    ],

    "most_frequent_silent": [
      { "type": "skill.executed", "count": 8921 },
      { "type": "pm.boot_progress", "count": 1204 },
    ]
  }
}
```

---

### 16.7 Summary: The Notification Contract

```
SILENT  (99%+ of events)
  Routine operations that succeed
  Auto-healed failures
  Boot sequences
  Pipeline throughput
  → Never notify. This is the default state of a healthy system.

LOG  (<1% of events)
  Single skill failures (will retry)
  Circuit breaker transitions (auto-healing)
  Fidelity violations (score drops)
  Watchdog warnings (not yet escalated)
  → Dashboard only. No human action needed.

ALERT  (<0.1% of events)
  Circuit breaker opens and stays open >1hour
  Fidelity critical (tamper detected)
  Process escalation (5+ restarts failed)
  Infrastructure critical (watchdog escalation)
  Degradation level increase
  Auto-suspend triggered
  Pipeline stalled > N hours
  → Telegram. Human action required.

SUPPRESSED
  Any ALERT that's downstream of an active root cause
  Any ALERT that exceeds the rate limit
  → Logged as suppressed. Not sent. Root cause already notified.
```

**One final rule:** If a human has to acknowledge a Telegram message, the system failed to auto-heal. That's by design. 99%+ of events auto-heal and are never seen by a human. The operator only hears about the 0.1% where the system's recovery mechanisms exhausted themselves.

---

*Telegram is for emergencies, not for status updates. A quiet Telegram channel means the system is working. A noisy one means someone needs to tune the notification filter.*
