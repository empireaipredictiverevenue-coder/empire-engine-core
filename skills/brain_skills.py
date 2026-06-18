"""
EMPIRE V49 · BRAIN SKILLS
===========================
Concrete skill implementations that wrap the existing brain modules.
Each skill is a BaseSkill subclass that delegates to the appropriate
brain engine (BrainDecider, BrainMemory, BrainLearning, etc.).

Includes vault skill discovery: the brain can create new skills from
vault notes at runtime via brain.vault.skill.discover and
brain.vault.skill.generate.
"""

import os
import re
import json
import time
import asyncio
import logging
from typing import Any, Optional

from .base import BaseSkill, SkillInput, SkillOutput, SkillMetrics
from .registry import SkillRegistry
from .dynamic import VaultSkillDiscoverer


log = logging.getLogger("empire.skills.brain")


# ─────────────────────────────────────────────────────────────────────────────
# VAULT PATHS
# ─────────────────────────────────────────────────────────────────────────────

VAULT_REPO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "brain_vault")
VAULT_HERMES = os.path.expanduser("~/.hermes/brain_vault")


def _resolve_vault_path(relative_path: str) -> Optional[str]:
    """Resolve a vault path, checking repo first then hermes home."""
    for base in [VAULT_REPO, VAULT_HERMES]:
        full = os.path.normpath(os.path.join(base, relative_path.lstrip("/")))
        if os.path.exists(full) and full.startswith(base):
            return full
    return None


def _parse_wikilinks(content: str, vault_base: str) -> str:
    """Resolve Obsidian-style [[wikilinks]] to note content.
    
    Matches [[Note Name]] and replaces with a brief excerpt of that note's
    first heading and first paragraph, linked via path.
    """
    def _resolve(match):
        note_name = match.group(1)
        # Try exact match, then fuzzy match
        for root, _dirs, files in os.walk(vault_base):
            for f in files:
                if not f.endswith(".md"):
                    continue
                base_name = os.path.splitext(f)[0]
                if note_name.lower() == base_name.lower().replace("_", " ").replace("-", " "):
                    try:
                        with open(os.path.join(root, f)) as fh:
                            excerpt = fh.read(500).split("\n")[0]
                        return f"[{note_name}]({f})" if excerpt.startswith("#") else f"[{note_name}]({f}) — {excerpt[:100]}"
                    except Exception:
                        return f"[{note_name}]"
        return f"[{note_name}]"
    
    return re.sub(r'\[\[([^\]]+)\]\]', _resolve, content)


# ─────────────────────────────────────────────────────────────────────────────
# SKILL: brain.decide (wraps BrainDecider.decide)
# ─────────────────────────────────────────────────────────────────────────────


class BrainDecideSkill(BaseSkill):
    """Evaluate a lead + alert and return GO/NO_GO with calibrated confidence."""
    name = "brain.decide"
    version = "2.0.0"
    description = "Evaluate a lead against a storm alert and return GO/NO_GO with confidence"
    tags = ["domain:brain", "mode:sync", "critical:true"]
    timeout_seconds = 120.0
    dependencies = ["brain.memory.retrieve", "brain.vault.context", "brain.personality.get"]

    def __init__(self):
        super().__init__()
        self.brain_decider: Any = None
        self.brain_memory: Any = None
        self.brain_learning: Any = None
        self.brain_personality: Any = None

    async def validate(self, input: SkillInput) -> bool:
        return (
            bool(input.params.get("lead"))
            and self.brain_decider is not None
        )

    async def execute(self, input: SkillInput) -> SkillOutput:
        lead = input.params["lead"]
        alert = input.params.get("alert", {})
        niche = input.params.get("niche")

        # 1. Retrieve vault context if available
        vault_context = ""
        if input.context:
            vault_skill = input.context.get_skill("brain.vault.context")
            if vault_skill:
                vault_out = await vault_skill.run(SkillInput(params={}))
                if vault_out.success and vault_out.data:
                    vault_context = vault_out.data.get("context", "")

        # 2. Retrieve personality profile
        personality = None
        if input.context:
            personality_skill = input.context.get_skill("brain.personality.get")
            if personality_skill:
                prof_out = await personality_skill.run(SkillInput(
                    params={"niche": niche or "industrial_storage"}
                ))
                if prof_out.success:
                    personality = prof_out.data

        # 3. Call the existing BrainDecider
        target = {
            "warehouse_name": lead.get("warehouse_name") or lead.get("name", ""),
            "address": lead.get("address", ""),
            "city": lead.get("city", ""),
            "phone": lead.get("phone", ""),
            "email": lead.get("email", ""),
        }
        alert_ctx = alert or {
            "event": lead.get("alert_event", "Inbound Lead"),
            "severity": lead.get("alert_severity", "Moderate"),
            "urgency": lead.get("alert_urgency", "Normal"),
            "area": f"{lead.get('city', '')}, {lead.get('state', '')}".strip(", "),
        }

        # Inject vault context + personality into the brain decider's prompt
        if vault_context:
            alert_ctx["_vault_context"] = vault_context[:3000]
        if personality:
            alert_ctx["_personality"] = personality

        result = await self.brain_decider.decide(
            target=target,
            alert_summary=alert_ctx,
            niche=niche,
        )

        return SkillOutput(
            success=True,
            data=result if isinstance(result, dict) else {"decision": str(result)},
            metrics=SkillMetrics(duration_ms=0),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SKILL: brain.vault.read
# ─────────────────────────────────────────────────────────────────────────────


class VaultReadSkill(BaseSkill):
    """Read a note from the brain vault knowledge base with wikilink resolution."""
    name = "brain.vault.read"
    version = "2.0.0"
    description = "Read a note from the brain vault knowledge base by path, resolving [[wikilinks]]"
    tags = ["domain:brain", "mode:sync"]
    timeout_seconds = 5.0

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("path"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        rel_path = input.params["path"].lstrip("/")
        max_chars = int(input.params.get("max_chars", 5000))
        resolve_links = bool(input.params.get("resolve_wikilinks", True))
        resolved = _resolve_vault_path(rel_path)

        if not resolved:
            return SkillOutput(success=False, error=f"vault path not found: {rel_path}")

        try:
            with open(resolved, "r") as f:
                content = f.read(max_chars)

            # Resolve Obsidian [[wikilinks]]
            if resolve_links:
                vault_base = VAULT_REPO if resolved.startswith(VAULT_REPO) else VAULT_HERMES
                content = _parse_wikilinks(content, vault_base)

            return SkillOutput(
                success=True,
                data={"content": content, "path": rel_path, "size": len(content)},
                metrics=SkillMetrics(duration_ms=0, records_processed=1),
            )
        except Exception as e:
            return SkillOutput(success=False, error=f"vault read error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SKILL: brain.vault.search
# ─────────────────────────────────────────────────────────────────────────────


class VaultSearchSkill(BaseSkill):
    """Search the brain vault for notes matching a keyword."""
    name = "brain.vault.search"
    version = "1.0.0"
    description = "Search vault notes by keyword and return matching paths with excerpts"
    tags = ["domain:brain", "mode:sync"]
    timeout_seconds = 10.0
    max_depth = 5  # limit directory traversal depth

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("query"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        query = input.params["query"].lower()
        max_results = int(input.params.get("max_results", 5))

        results = []
        for vault_dir in [VAULT_REPO, VAULT_HERMES]:
            if not os.path.isdir(vault_dir):
                continue
            for root, _dirs, files in os.walk(vault_dir):
                depth = root.replace(vault_dir, "").count(os.sep)
                if depth > self.max_depth:
                    continue
                for f in files:
                    if not f.endswith(".md") or len(results) >= max_results:
                        continue
                    filepath = os.path.join(root, f)
                    rel_path = os.path.relpath(filepath, vault_dir)
                    try:
                        with open(filepath, "r") as fh:
                            content = fh.read(3000)
                        if query in content.lower():
                            idx = content.lower().find(query)
                            start = max(0, idx - 60)
                            end = min(len(content), idx + len(query) + 120)
                            results.append({
                                "path": rel_path,
                                "excerpt": f"...{content[start:end].replace(chr(10), ' ')}...",
                            })
                    except Exception:
                        continue

        return SkillOutput(
            success=True,
            data={"results": results, "count": len(results), "query": query},
            metrics=SkillMetrics(duration_ms=0, records_processed=len(results)),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SKILL: brain.vault.list
# ─────────────────────────────────────────────────────────────────────────────


class VaultListSkill(BaseSkill):
    """List all notes in the brain vault."""
    name = "brain.vault.list"
    version = "1.0.0"
    description = "List all markdown notes in the brain vault"
    tags = ["domain:brain", "mode:sync"]
    timeout_seconds = 5.0

    async def validate(self, input: SkillInput) -> bool:
        return True

    async def execute(self, input: SkillInput) -> SkillOutput:
        notes = []
        for vault_dir, source in [(VAULT_REPO, "repo"), (VAULT_HERMES, "hermes")]:
            if not os.path.isdir(vault_dir):
                continue
            for root, _dirs, files in os.walk(vault_dir):
                for f in files:
                    if not f.endswith(".md"):
                        continue
                    rel_path = os.path.relpath(os.path.join(root, f), vault_dir)
                    notes.append({
                        "path": rel_path,
                        "title": f.replace(".md", "").replace("_", " ").replace("-", " ").title(),
                        "source": source,
                    })

        return SkillOutput(
            success=True,
            data={"notes": notes, "count": len(notes)},
            metrics=SkillMetrics(duration_ms=0, records_processed=len(notes)),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SKILL: brain.vault.context (loads all vault notes with cache + lock)
# ─────────────────────────────────────────────────────────────────────────────


class VaultContextSkill(BaseSkill):
    """Load all vault knowledge into a context string for brain prompt injection."""
    name = "brain.vault.context"
    version = "2.0.0"
    description = "Load vault notes into a context block with [[wikilink]] resolution"
    tags = ["domain:brain", "mode:sync"]
    timeout_seconds = 15.0
    dependencies = ["brain.vault.list", "brain.vault.read"]

    def __init__(self):
        super().__init__()
        self._cache: Optional[dict] = None
        self._cache_at: float = 0
        self._cache_ttl: float = 300
        self._lock = asyncio.Lock()

    async def validate(self, input: SkillInput) -> bool:
        return True

    async def execute(self, input: SkillInput) -> SkillOutput:
        now = time.time()
        if self._cache and (now - self._cache_at) < self._cache_ttl:
            return SkillOutput(
                success=True, data=dict(self._cache),
                metrics=SkillMetrics(duration_ms=0, records_processed=0),
            )

        async with self._lock:
            # Double-check after acquiring lock
            if self._cache and (now - self._cache_at) < self._cache_ttl:
                return SkillOutput(
                    success=True, data=dict(self._cache),
                    metrics=SkillMetrics(duration_ms=0, records_processed=0),
                )

            knowledge_notes = []
            for vault_dir in [VAULT_REPO, VAULT_HERMES]:
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
                                content = fh.read(8000)
                            content = _parse_wikilinks(content, vault_dir)
                            knowledge_notes.append({"path": rel_path, "content": content})
                        except Exception:
                            continue

            context_parts = ["── BRAIN VAULT KNOWLEDGE ──"]
            for note in knowledge_notes:
                title = note["path"].replace(".md", "").replace("/", " › ").replace("_", " ").title()
                context_parts.append(f"\n## {title}\n{note['content'][:2000]}")

            self._cache = {
                "context": "\n".join(context_parts),
                "notes_count": len(knowledge_notes),
            }
            self._cache_at = time.time()

            return SkillOutput(
                success=True, data=self._cache,
                metrics=SkillMetrics(duration_ms=0, records_processed=len(knowledge_notes)),
            )


# ─────────────────────────────────────────────────────────────────────────────
# SKILL: brain.memory.retrieve
# ─────────────────────────────────────────────────────────────────────────────


class MemoryRetrieveSkill(BaseSkill):
    """Retrieve similar past decisions from brain memory."""
    name = "brain.memory.retrieve"
    version = "1.0.0"
    description = "Find similar past decisions using embedding similarity"
    tags = ["domain:brain", "mode:sync", "requires:embedding"]
    timeout_seconds = 15.0

    def __init__(self):
        super().__init__()
        self.brain_memory: Any = None

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("lead")) and self.brain_memory is not None

    async def execute(self, input: SkillInput) -> SkillOutput:
        lead = input.params["lead"]
        memories = await self.brain_memory.retrieve_similar(
            address=lead.get("address", ""),
            city=lead.get("city", ""),
            severity=lead.get("severity", ""),
            asset_value=float(lead.get("asset_value", 0)),
            urgency_signal=lead.get("urgency_signal", ""),
            k=int(input.params.get("k", 5)),
            only_with_outcomes=bool(input.params.get("only_with_outcomes", True)),
        )

        return SkillOutput(
            success=True,
            data={"memories": memories, "count": len(memories)},
            metrics=SkillMetrics(duration_ms=0, records_processed=len(memories)),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SKILL: brain.memory.record
# ─────────────────────────────────────────────────────────────────────────────


class MemoryRecordSkill(BaseSkill):
    """Record a new brain decision with embedding."""
    name = "brain.memory.record"
    version = "1.0.0"
    description = "Store a brain decision with embedding for future retrieval"
    tags = ["domain:brain", "mode:sync", "requires:embedding"]
    timeout_seconds = 10.0

    def __init__(self):
        super().__init__()
        self.brain_memory: Any = None

    async def validate(self, input: SkillInput) -> bool:
        required = ["decision", "address", "city", "severity"]
        return all(input.params.get(k) for k in required) and self.brain_memory is not None

    async def execute(self, input: SkillInput) -> SkillOutput:
        p = input.params
        memory_id = await self.brain_memory.record_decision(
            lead_id=p.get("lead_id"),
            decision=p["decision"],
            urgency=int(p.get("urgency", 5)),
            reasoning=p.get("reasoning", ""),
            address=p["address"],
            city=p["city"],
            severity=p["severity"],
            asset_value=float(p.get("asset_value", 0)),
        )

        return SkillOutput(
            success=True,
            data={"memory_id": memory_id, "ok": memory_id is not None},
            metrics=SkillMetrics(duration_ms=0, records_processed=1),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SKILL: brain.outcome.attach
# ─────────────────────────────────────────────────────────────────────────────


class OutcomeAttachSkill(BaseSkill):
    """Link a claim outcome back to the original brain decision."""
    name = "brain.outcome.attach"
    version = "1.0.0"
    description = "Attach a claim outcome to a previously recorded brain decision"
    tags = ["domain:brain", "mode:sync"]
    timeout_seconds = 10.0

    def __init__(self):
        super().__init__()
        self.brain_memory: Any = None

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("lead_id")) and bool(input.params.get("outcome"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        p = input.params
        ok = await self.brain_memory.attach_outcome(
            lead_id=p["lead_id"],
            outcome=p["outcome"],
            actual_fee=float(p.get("actual_fee", 0)),
        )

        return SkillOutput(
            success=True, data={"ok": ok},
            metrics=SkillMetrics(duration_ms=0, records_processed=1),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SKILL: brain.learn.tune
# ─────────────────────────────────────────────────────────────────────────────


class LearnTuneSkill(BaseSkill):
    """Nightly: recompute urgency floors from real outcomes."""
    name = "brain.learn.tune"
    version = "1.0.0"
    description = "Recompute optimal urgency floors from real settlement outcomes"
    tags = ["domain:brain", "mode:cron"]
    timeout_seconds = 60.0
    max_retries = 1

    def __init__(self):
        super().__init__()
        self.brain_learning: Any = None

    async def validate(self, input: SkillInput) -> bool:
        return self.brain_learning is not None

    async def execute(self, input: SkillInput) -> SkillOutput:
        lookback_days = int(input.params.get("lookback_days", 90))
        result = await self.brain_learning.tune_now(lookback_days=lookback_days)

        return SkillOutput(
            success=True, data=result,
            metrics=SkillMetrics(duration_ms=0, records_processed=result.get("rows", 0)),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SKILL: brain.personality.get
# ─────────────────────────────────────────────────────────────────────────────


class PersonalityGetSkill(BaseSkill):
    """Get the effective personality profile for a niche."""
    name = "brain.personality.get"
    version = "1.0.0"
    description = "Get the effective personality profile for a niche + optional operator"
    tags = ["domain:brain", "mode:sync"]
    timeout_seconds = 5.0

    def __init__(self):
        super().__init__()
        self.brain_personality: Any = None

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("niche")) and self.brain_personality is not None

    async def execute(self, input: SkillInput) -> SkillOutput:
        p = input.params
        profile = self.brain_personality.personality_for_niche(
            niche=p["niche"], operator_id=p.get("operator_id"),
        )

        return SkillOutput(
            success=True, data=profile,
            metrics=SkillMetrics(duration_ms=0, records_processed=1),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SKILL: brain.vault.skill.discover
# ─────────────────────────────────────────────────────────────────────────────


class VaultSkillDiscoverSkill(BaseSkill):
    """Scan vault notes for type:skill definitions and register them dynamically."""
    name = "brain.vault.skill.discover"
    version = "1.0.0"
    description = "Scan vault notes for skill definitions and register them as DynamicSkills at runtime"
    tags = ["domain:brain", "mode:sync", "vault:discovery"]
    timeout_seconds = 30.0
    max_retries = 1

    def __init__(self):
        super().__init__()
        self.discoverer: Optional[VaultSkillDiscoverer] = None

    async def validate(self, input: SkillInput) -> bool:
        return self.discoverer is not None

    async def execute(self, input: SkillInput) -> SkillOutput:
        """Run vault discovery and return registered skills."""
        result = self.discoverer.scan_and_register()
        return SkillOutput(
            success=True,
            data={
                "registered": result["registered"],
                "skipped": result["skipped"],
                "failed": result["failed"],
                "total": result["total"],
                "skills": result["skills"],
            },
            metrics=SkillMetrics(duration_ms=0, records_processed=result["registered"]),
        )


# ─────────────────────────────────────────────────────────────────────────────
# SKILL: brain.vault.skill.generate
# ─────────────────────────────────────────────────────────────────────────────


class VaultSkillGenerateSkill(BaseSkill):
    """Create a new vault skill note and register it dynamically."""
    name = "brain.vault.skill.generate"
    version = "1.0.0"
    description = "Generate a new vault skill note from a description or explicit params, then register it"
    tags = ["domain:brain", "mode:sync", "vault:discovery"]
    timeout_seconds = 120.0
    max_retries = 1

    def __init__(self):
        super().__init__()
        self.discoverer: Optional[VaultSkillDiscoverer] = None

    async def validate(self, input: SkillInput) -> bool:
        return self.discoverer is not None and bool(
            input.params.get("description") or input.params.get("name")
        )

    async def execute(self, input: SkillInput) -> SkillOutput:
        p = input.params

        if p.get("description") and not p.get("name"):
            # AI-powered: generate from description
            if self.discoverer.ask_llm is None:
                return SkillOutput(
                    success=False,
                    error="ask_llm not available — cannot generate skill from description alone",
                )
            result = await self.discoverer.generate_from_description(
                description=p["description"],
            )
        else:
            # Manual: create from explicit params
            result = await self.discoverer.generate_skill_note(
                name=p["name"],
                description=p.get("description", ""),
                instructions=p.get("instructions", "Execute the skill according to its description."),
                tags=p.get("tags"),
                required_params=p.get("required_params"),
                dependencies=p.get("dependencies"),
                execution_mode=p.get("execution_mode", "llm"),
                timeout_seconds=float(p.get("timeout_seconds", 60.0)),
                overwrite=bool(p.get("overwrite", False)),
            )

        return SkillOutput(
            success=result.get("ok", False),
            data=result,
            metrics=SkillMetrics(duration_ms=0, records_processed=1),
        )


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRATION HELPER
# ─────────────────────────────────────────────────────────────────────────────


def register_brain_skills(
    registry: SkillRegistry,
    brain_decider: Any = None,
    brain_memory: Any = None,
    brain_learning: Any = None,
    brain_personality: Any = None,
    discoverer: Optional[VaultSkillDiscoverer] = None,
) -> dict[str, BaseSkill]:
    """Register all brain skills and wire their dependencies.
    
    Uses registry.wire_dependency() to safely set deps on skill instances
    BEFORE the ImmutableSkillRegistry freezes them on first get().
    
    If a VaultSkillDiscoverer is provided (required for hub integration),
    the vault discovery skills are also registered and wired.
    
    Returns a dict of wired skill instances for harness registration.
    """
    # ── Vault skills (no dependencies — register normally) ─────────────
    registry.register(VaultReadSkill)
    registry.register(VaultSearchSkill)
    registry.register(VaultListSkill)
    registry.register(VaultContextSkill)

    # ── Brain.decide (needs brain_decider + friends) ──────────────────
    registry.register(BrainDecideSkill)
    if brain_decider is not None:
        registry.wire_dependency("brain.decide", "brain_decider", brain_decider)
    if brain_memory is not None:
        registry.wire_dependency("brain.decide", "brain_memory", brain_memory)
    if brain_learning is not None:
        registry.wire_dependency("brain.decide", "brain_learning", brain_learning)
    if brain_personality is not None:
        registry.wire_dependency("brain.decide", "brain_personality", brain_personality)
    decide_skill = registry.get("brain.decide")

    # ── Memory skills (need brain_memory) ─────────────────────────────
    memory_names = ["brain.memory.retrieve", "brain.memory.record", "brain.outcome.attach"]
    memory_wired = {}
    for cls, name in [
        (MemoryRetrieveSkill, "brain.memory.retrieve"),
        (MemoryRecordSkill, "brain.memory.record"),
        (OutcomeAttachSkill, "brain.outcome.attach"),
    ]:
        registry.register(cls)
        if brain_memory is not None:
            registry.wire_dependency(name, "brain_memory", brain_memory)
        skill = registry.get(name)
        if skill:
            memory_wired[name] = skill

    # ── Learning skill (needs brain_learning) ─────────────────────────
    registry.register(LearnTuneSkill)
    if brain_learning is not None:
        registry.wire_dependency("brain.learn.tune", "brain_learning", brain_learning)
    learn_skill = registry.get("brain.learn.tune")

    # ── Personality skill (needs brain_personality) ───────────────────
    registry.register(PersonalityGetSkill)
    if brain_personality is not None:
        registry.wire_dependency("brain.personality.get", "brain_personality", brain_personality)
    personality_skill = registry.get("brain.personality.get")

    # ── Vault discovery skills (need VaultSkillDiscoverer) ────────────
    registry.register(VaultSkillDiscoverSkill)
    registry.register(VaultSkillGenerateSkill)
    if discoverer is not None:
        registry.wire_dependency("brain.vault.skill.discover", "discoverer", discoverer)
        registry.wire_dependency("brain.vault.skill.generate", "discoverer", discoverer)

    wired = {
        "brain.decide": decide_skill,
        "brain.memory.retrieve": memory_wired.get("brain.memory.retrieve"),
        "brain.memory.record": memory_wired.get("brain.memory.record"),
        "brain.outcome.attach": memory_wired.get("brain.outcome.attach"),
        "brain.learn.tune": learn_skill,
        "brain.personality.get": personality_skill,
    }
    return {k: v for k, v in wired.items() if v is not None}
