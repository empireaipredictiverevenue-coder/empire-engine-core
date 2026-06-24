"""
EMPIRE V49 · SKILLS INIT
===========================
One-shot initialization of the Skills Framework.
Called from hub.py during engine initialization.
Wires the SkillRegistry, HarnessManager, boundaries, discovery, and REST routes.
"""

import os
import logging
from typing import Any, Callable, Optional

from skills.registry import ImmutableSkillRegistry
from skills.harness import HarnessManager, HarnessConfig
from skills.boundary import SkillBoundary, FidelityAuditor
from skills.brain_skills import register_brain_skills
from skills.trading_skills import register_trading_skills
from skills.marketing_skills import register_marketing_skills
from skills.email_skills import register_email_skills
from skills.design_skills import register_design_skills
from skills.hermes_skills import register_hermes_skills
from skills.query_skills import register_query_skills
from skills.traffic_skills import register_traffic_skills
from skills.dynamic import VaultSkillDiscoverer


log = logging.getLogger("empire.skills.init")


# ─────────────────────────────────────────────────────────────────────────────
# INIT SKILLS FRAMEWORK
# ─────────────────────────────────────────────────────────────────────────────


class SkillsFramework:
    """
    Container for the complete Skills Framework initialization.
    Instantiated once during hub bootstrap and wired into REST routes.
    """

    def __init__(self):
        self.registry = ImmutableSkillRegistry()
        self.harness_mgr: Optional[HarnessManager] = None
        self.auditor = FidelityAuditor()
        self.boundaries: dict[str, SkillBoundary] = {}
        self.discoverer: Optional[VaultSkillDiscoverer] = None
        self._ask_llm: Optional[Callable[[str, str], Any]] = None
        self._initialized = False

    def init(
        self,
        brain_decider: Any = None,
        brain_memory: Any = None,
        brain_learning: Any = None,
        brain_personality: Any = None,
        ask_llm: Optional[Callable[[str, str], Any]] = None,
        default_config: Optional[HarnessConfig] = None,
        auto_discover_skills: bool = True,
    ):
        """Initialize the Skills Framework with brain engines.

        Args:
            brain_decider: BrainDecider instance for lead evaluation
            brain_memory: BrainMemory instance for memory skills
            brain_learning: BrainLearning instance for learning/tuning
            brain_personality: BrainPersonality instance for personality profiles
            ask_llm: Async callable(system_prompt, user_prompt) -> str for LLM-backed skills
            default_config: Default HarnessConfig (timeout, circuit breaker, etc.)
            auto_discover_skills: If True, scan vault notes for type:skill definitions
                                   and register them automatically after init
        """
        if self._initialized:
            log.warning("[skills] already initialized — skipping")
            return

        self._ask_llm = ask_llm

        # 1. Create vault skill discoverer (before skill registration so it can be wired)
        self.discoverer = VaultSkillDiscoverer(
            registry=self.registry,
            ask_llm=ask_llm,
        )

        # 2. Register all default skills
        config = default_config or HarnessConfig(
            timeout=30.0,
            max_retries=3,
            circuit_breaker=True,
            circuit_threshold=5,
        )

        # 3. Register brain skills with wired dependencies (including discoverer)
        register_brain_skills(
            registry=self.registry,
            brain_decider=brain_decider,
            brain_memory=brain_memory,
            brain_learning=brain_learning,
            brain_personality=brain_personality,
            discoverer=self.discoverer,
        )

        # 4. Register trading skills (market analysis, meme sniper, risk assessment, etc.)
        register_trading_skills(registry=self.registry)

        # 5. Register marketing skills (emails, ads, SEO, referrals, CRO, etc.)
        #    Wraps SKILL.md prompt templates from skills/marketingskills/
        #    Wires ask_llm so skills can execute SKILL.md instructions via LLM
        register_marketing_skills(registry=self.registry, ask_llm=ask_llm)

        # 5a. Register email skills (strategy, deliverability, compliance, sequences, copy, analytics, provider config)
        #     Wires ask_llm so skills can execute email marketing guidance via LLM
        register_email_skills(registry=self.registry, ask_llm=ask_llm)

        # 5b. Register design skills (UI, UX, visual, motion, accessibility, design ops)
        #     Wires ask_llm so skills can execute design guidance via LLM
        register_design_skills(registry=self.registry, ask_llm=ask_llm)

        # 5c. Register hermes mesh skills (task queue ops, fleet agents, autoresearch, external tools)
        #     29 skills that make the mesh dispatch layer invocable via HarnessManager.run()
        register_hermes_skills(registry=self.registry)

        # 5d. Register traffic skills (budget allocation, channel optimization, native ads, affiliate, etc.)
        #     12 skills: traffic.* namespace for the traffic_director role
        #     Wires ask_llm so skills can execute traffic management guidance via LLM
        register_traffic_skills(registry=self.registry, ask_llm=ask_llm)

        # 5d(ii). Register traffic_director boundary for skill fidelity enforcement
        #         Locks traffic_director to only call traffic.* skills
        self.register_agent_boundary(
            agent_name="traffic_director",
            equips=[
                "traffic.budget-allocation",
                "traffic.mix-optimization",
                "traffic.native-ads",
                "traffic.ppc",
                "traffic.affiliate",
                "traffic.seo",
                "traffic.email-sms",
                "traffic.content-distribution",
                "traffic.community-engagement",
                "traffic.reporting",
                "traffic.channel-activation",
                "traffic.search-ads",
                "traffic.social-ads",
            ],
        )

        # 5e. Register query & knowledge skills (DB query, RAG vector search, knowledge base)
        #     3 skills: query.db.sql, query.rag.search, query.kb.search
        register_query_skills(
            registry=self.registry,
            ask_llm=ask_llm,
            supabase_client=None,  # wired later if exec_sql RPC is available
        )

        # 6. Auto-discover vault-defined skills
        if auto_discover_skills:
            try:
                discovery_result = self.discoverer.scan_and_register()
                if discovery_result["registered"] > 0:
                    log.info(
                        f"[skills] auto-discovered {discovery_result['registered']} vault skills: "
                        f"{', '.join(discovery_result['skills'])}"
                    )
                elif discovery_result["total"] > 0:
                    log.info(f"[skills] {discovery_result['total']} vault skills already registered")
                else:
                    log.info("[skills] no vault skill notes found (add notes with type:skill frontmatter)")
            except Exception as e:
                log.warning(f"[skills] vault skill auto-discovery failed: {e}")

        # 7. Create harness manager
        self.harness_mgr = HarnessManager(
            registry=self.registry,
            default_config=config,
        )

        self._initialized = True
        log.info(
            f"[skills] initialized · {len(self.registry._skills)} skills · "
            f"circuit_breaker={config.circuit_breaker} · "
            f"discoverer={'ready' if self.discoverer else 'none'}"
        )

    def register_agent_boundary(self, agent_name: str, equips: list[str]) -> SkillBoundary:
        """Register an agent's boundary for skill fidelity enforcement."""
        boundary = SkillBoundary(agent_name, equips, self.registry)
        self.boundaries[agent_name] = boundary
        log.info(f"[skills] boundary registered for {agent_name} · {len(equips)} skills")
        return boundary

    def wire_routes(self, app, require_auth=None):
        """Wire skills REST routes onto the hub, including dynamic discovery routes."""
        from empire_skills_routes import register_skills_routes
        register_skills_routes(
            app=app,
            registry=self.registry,
            harness_mgr=self.harness_mgr,
            auditor=self.auditor,
            boundaries=self.boundaries,
            require_auth=require_auth,
            discoverer=self.discoverer,
        )

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def snapshot(self) -> dict:
        """Full Skills Framework snapshot."""
        if not self._initialized:
            return {"status": "not_initialized"}
        return {
            "status": "initialized",
            "registry": self.registry.snapshot(),
            "harness": self.harness_mgr.snapshot() if self.harness_mgr else {},
            "boundaries": {
                name: b.snapshot() for name, b in self.boundaries.items()
            },
            "fidelity": self.auditor.report(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# BRAIN VAULT AUTO-DISCOVERY
# ─────────────────────────────────────────────────────────────────────────────


def load_vault_context() -> str:
    """Load vault knowledge into a context string for brain prompt injection.
    
    Reads all .md notes from brain_vault/knowledge/ and builds a context block
    that can be injected into the brain's system prompt.
    """
    vault_repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_vault")
    vault_hermes = os.path.expanduser("~/.hermes/brain_vault")

    context_parts = ["── BRAIN VAULT KNOWLEDGE ──"]
    note_count = 0

    for vault_dir in [vault_repo, vault_hermes]:
        if not os.path.isdir(vault_dir):
            continue
        for root, _dirs, files in os.walk(vault_dir):
            for f in sorted(files):
                if not f.endswith(".md") or f in ("SOUL.md", "SKILLS.md"):
                    continue
                filepath = os.path.join(root, f)
                rel_path = os.path.relpath(filepath, vault_dir)
                try:
                    with open(filepath, "r") as fh:
                        content = fh.read(5000)
                    # Extract title from first heading
                    title = rel_path.replace(".md", "").replace("/", " › ").replace("_", " ").title()
                    context_parts.append(f"\n## {title}\n{content[:2000]}")
                    note_count += 1
                except Exception:
                    continue

    context = "\n".join(context_parts)
    log.info(f"[vault] loaded {note_count} knowledge notes into context")
    return context


# ─────────────────────────────────────────────────────────────────────────────
import time as _vault_time

_VAULT_CACHE: dict = {"context": "", "soul": "", "at": 0.0}
_VAULT_TTL = 300.0  # 5 minute cache


def load_brain_soul() -> str:
    """Load the brain's SOUL.md and SKILLS.md for prompt injection.
    Cached for 5 minutes."""
    now = _vault_time.time()
    if _VAULT_CACHE["soul"] and (now - _VAULT_CACHE["at"]) < _VAULT_TTL:
        return _VAULT_CACHE["soul"]

    vault_repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_vault")
    parts = []

    for fname in ["SOUL.md", "SKILLS.md"]:
        fpath = os.path.join(vault_repo, fname)
        if os.path.exists(fpath):
            try:
                with open(fpath, "r") as f:
                    parts.append(f.read(8000))
            except Exception:
                continue

    result = "\n\n".join(parts)
    _VAULT_CACHE["soul"] = result
    _VAULT_CACHE["at"] = now
    return result


def load_vault_context() -> str:
    """Load vault knowledge into a context string for brain prompt injection.
    Cached for 5 minutes."""
    now = _vault_time.time()
    if _VAULT_CACHE["context"] and (now - _VAULT_CACHE["at"]) < _VAULT_TTL:
        return _VAULT_CACHE["context"]

    vault_repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain_vault")
    vault_hermes = os.path.expanduser("~/.hermes/brain_vault")

    context_parts = ["── BRAIN VAULT KNOWLEDGE ──"]
    note_count = 0

    for vault_dir in [vault_repo, vault_hermes]:
        if not os.path.isdir(vault_dir):
            continue
        for root, _dirs, files in os.walk(vault_dir):
            for f in sorted(files):
                if not f.endswith(".md") or f in ("SOUL.md", "SKILLS.md"):
                    continue
                filepath = os.path.join(root, f)
                rel_path = os.path.relpath(filepath, vault_dir)
                try:
                    with open(filepath, "r") as fh:
                        content = fh.read(5000)
                    title = rel_path.replace(".md", "").replace("/", " › ").replace("_", " ").title()
                    context_parts.append(f"\n## {title}\n{content[:2000]}")
                    note_count += 1
                except Exception:
                    continue

    context = "\n".join(context_parts)
    _VAULT_CACHE["context"] = context
    _VAULT_CACHE["at"] = now
    log.info(f"[vault] loaded {note_count} knowledge notes into context")
    return context


def build_brain_context(base_prompt: str = "") -> str:
    """Build the full context block for brain prompt injection.
    Cached for 5 minutes."""
    soul = load_brain_soul()
    vault = load_vault_context()

    parts = [base_prompt] if base_prompt else []
    if soul:
        parts.append(soul)
    if vault:
        parts.append(vault)

    return "\n\n".join(parts)


# Singleton for hub.py import
skills_framework = SkillsFramework()
