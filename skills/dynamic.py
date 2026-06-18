"""
EMPIRE V49 · DYNAMIC SKILL DISCOVERY
======================================
The brain can create new skills from vault notes at runtime.

How it works:
  1. A vault note with YAML frontmatter containing `type: skill` defines a new skill
  2. VaultSkillDiscoverer scans vault directories, parses frontmatter, and generates
     DynamicSkill subclasses
  3. Each DynamicSkill reads its instructions from the vault note and executes them
     via LLM call (or inline Python mode)
  4. The registry holds these alongside static skills — same lifecycle, same harness

Vault Note Format:
  ---
  type: skill
  name: custom.storm.research
  version: 1.0.0
  description: Research storm claims data for a specific city
  tags: [domain:custom, mode:sync]
  timeout_seconds: 30
  max_retries: 2
  execution_mode: llm
  required_params:
    - city
    - state
  dependencies:
    - brain.vault.search
  ---
  Research storm damage claims in the specified city. Use the brain.vault.search
  skill to find relevant storm history in the vault, then synthesize a summary
  of recent storm events, common damage types, and average claim values.
"""

import os
import re
import json
import yaml
import time
import logging
import asyncio
from typing import Any, Callable, Optional, Type
from dataclasses import dataclass, field

from .base import BaseSkill, SkillInput, SkillOutput, SkillMetrics
from .registry import ImmutableSkillRegistry, SkillRegistry


log = logging.getLogger("empire.skills.dynamic")


# ─────────────────────────────────────────────────────────────────────────────
# VAULT PATHS (reuse from brain_skills)
# ─────────────────────────────────────────────────────────────────────────────

VAULT_REPO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "brain_vault")
VAULT_HERMES = os.path.expanduser("~/.hermes/brain_vault")


# ─────────────────────────────────────────────────────────────────────────────
# VAULT NOTE PARSER (YAML frontmatter)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SkillNote:
    """Parsed vault note containing a skill definition."""
    name: str
    vault_path: str
    frontmatter: dict
    body: str
    version: str = "1.0.0"
    description: str = ""
    tags: list[str] = field(default_factory=lambda: ["domain:custom"])
    timeout_seconds: float = 60.0
    max_retries: int = 2
    execution_mode: str = "llm"
    required_params: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    instructions: str = ""


_FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n?(.*)', re.DOTALL)


def parse_vault_note(filepath: str) -> Optional[SkillNote]:
    """Parse a vault .md file and return a SkillNote if it has type: skill frontmatter.

    Returns None if the file doesn't have skill frontmatter or is malformed.
    """
    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, "r") as f:
            content = f.read(10000)
    except Exception as e:
        log.warning(f"[dynamic] cannot read {filepath}: {e}")
        return None

    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None

    try:
        fm = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        log.warning(f"[dynamic] YAML parse error in {filepath}: {e}")
        return None

    if not isinstance(fm, dict) or fm.get("type") != "skill":
        return None

    body = match.group(2).strip()
    name = fm.get("name", "").strip()
    if not name:
        log.warning(f"[dynamic] skill note at {filepath} has no 'name' in frontmatter")
        return None

    return SkillNote(
        name=name,
        vault_path=filepath,
        frontmatter=fm,
        body=body,
        version=str(fm.get("version", "1.0.0")),
        description=fm.get("description", "").strip(),
        tags=fm.get("tags", ["domain:custom"]),
        timeout_seconds=float(fm.get("timeout_seconds", 60.0)),
        max_retries=int(fm.get("max_retries", 2)),
        execution_mode=fm.get("execution_mode", "llm"),
        required_params=fm.get("required_params", []),
        dependencies=fm.get("dependencies", []),
        instructions=body,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DYNAMIC SKILL — base class for vault-defined skills
# ─────────────────────────────────────────────────────────────────────────────


class DynamicSkill(BaseSkill):
    """A skill whose behavior is defined by a vault note.

    Each vault note with type:skill frontmatter generates a DynamicSkill subclass
    with the note's metadata. The execute() method reads the vault note instructions
    and delegates to an LLM (or inline Python logic).

    Subclasses only override metadata (name, version, description, etc.) and
    inherit the concrete lifecycle from DynamicSkill.
    """

    name = "dynamic.skill"
    version = "1.0.0"
    description = "A vault-defined dynamic skill"
    tags = ["domain:dynamic", "mode:sync"]
    timeout_seconds = 60.0
    max_retries = 2
    retry_delay = 1.0

    def __init__(self):
        super().__init__()
        self.vault_path: str = ""
        self.execution_mode: str = "llm"
        self.required_params: list[str] = []
        self.instructions: str = ""
        # Injected dependency: async callable(system_prompt: str, user_prompt: str) -> str
        self.ask_llm: Optional[Callable[[str, str], Any]] = None

    # ── Re-read vault note on each execute for fresh content ───────────

    def _reload_from_vault(self) -> bool:
        """Re-read the vault note to get fresh instructions and metadata.

        This allows vault notes to be edited while the system is running
        without requiring a skill re-registration.
        """
        note = parse_vault_note(self.vault_path)
        if note is None:
            return False
        self.instructions = note.instructions
        self.required_params = note.required_params
        self.execution_mode = note.execution_mode
        self.description = note.description
        self.timeout_seconds = note.timeout_seconds
        return True

    #    ── Lifecycle ─────────────────────────────────────────────────────

    async def _read_vault_instructions(self) -> tuple[list[str], str, str]:
        """Read the vault note for fresh instructions, required_params, and description.

        Does NOT mutate self — returns data directly. This avoids SkillFidelityError
        on frozen instances while still allowing vault note edits to take effect
        without re-registration.
        """
        note = parse_vault_note(self.vault_path)
        if note is not None:
            return (note.required_params, note.instructions, note.execution_mode)
        # Fall back to wired values if vault read fails
        # Note: accessing self.required_params and self.instructions on a frozen
        # instance is safe — it's read-only, not mutation
        return (self.required_params, self.instructions, self.execution_mode)

    async def validate(self, input: SkillInput) -> bool:
        """Check required params defined in the vault note frontmatter."""
        required, _instructions, _mode = await self._read_vault_instructions()
        for param in required:
            if param not in input.params:
                log.warning(
                    f"[{self.name}] missing required param '{param}' — "
                    f"required: {required}, got: {list(input.params.keys())}"
                )
                return False
        return True

    async def execute(self, input: SkillInput) -> SkillOutput:
        """Execute the skill based on its execution_mode.

        llm mode:   Read vault note fresh, construct prompt from instructions + params,
                    call the injected ask_llm, return the result.
        python mode: Execute inline Python logic (future expansion — for now
                     falls through to llm mode with a warning).

        Note: reads the vault note on every execution so edits take effect
        without re-registration. Does NOT mutate frozen instance attributes.
        """
        required, instructions, mode = await self._read_vault_instructions()

        start = time.time()

        if mode == "llm" and self.ask_llm is not None:
            return await self._execute_llm(instructions, input, start)
        elif mode == "python":
            log.warning(f"[{self.name}] python execution_mode not yet implemented, falling back to llm")
            if self.ask_llm is not None:
                return await self._execute_llm(instructions, input, start)
            return SkillOutput(
                success=False,
                error="python execution_mode not implemented and no ask_llm available",
                metrics=SkillMetrics(duration_ms=int((time.time() - start) * 1000)),
            )
        else:
            return SkillOutput(
                success=False,
                error=f"No ask_llm available for {self.name} (execution_mode={mode})",
                metrics=SkillMetrics(duration_ms=int((time.time() - start) * 1000)),
            )

    async def _execute_llm(self, instructions: str, input: SkillInput, start: float) -> SkillOutput:
        """Execute via LLM: build prompt from vault instructions + params."""
        # Build system prompt from vault instructions
        system = (
            f"You are executing skill '{self.name}'. "
            f"{self.description}\n\n"
            f"## Instructions\n{instructions}\n\n"
            f"Respond with the result of executing these instructions against the input. "
            f"Be thorough and precise. Return ONLY the result — no commentary."
        )

        # Build user prompt from input params
        user_lines = ["## Input Parameters"]
        for key, value in input.params.items():
            if isinstance(value, (dict, list)):
                user_lines.append(f"{key}: {json.dumps(value, indent=2)}")
            else:
                user_lines.append(f"{key}: {value}")
        user = "\n".join(user_lines)

        try:
            result = await self.ask_llm(system, user)
            elapsed_ms = int((time.time() - start) * 1000)
            return SkillOutput(
                success=True,
                data={"result": result, "skill": self.name, "execution_mode": "llm"},
                metrics=SkillMetrics(duration_ms=elapsed_ms, api_calls=1),
            )
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            log.error(f"[{self.name}] LLM execution failed: {e}")
            return SkillOutput(
                success=False,
                error=f"llm execution error: {e}",
                metrics=SkillMetrics(duration_ms=elapsed_ms, api_calls=0, records_errored=1),
            )


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY — create a DynamicSkill subclass from a SkillNote
# ─────────────────────────────────────────────────────────────────────────────


def make_skill_class(note: SkillNote) -> Type[DynamicSkill]:
    """Dynamically create a DynamicSkill subclass configured from a vault note.

    Each vault note gets its own class with unique metadata, allowing
    the ImmutableSkillRegistry to register and freeze it like any other skill.
    The class is created at module scope for pickling/debugging but returned
    for registration.
    """
    # Sanitize name for class name (Python identifier)
    safe_name = note.name.replace(".", "_").replace("-", "_")
    class_name = f"DynamicSkill_{safe_name}"

    # Create the subclass with vault note metadata as class attributes
    dyn_cls = type(class_name, (DynamicSkill,), {
        "name": note.name,
        "version": note.version,
        "description": note.description,
        "tags": note.tags,
        "timeout_seconds": note.timeout_seconds,
        "max_retries": note.max_retries,
        "dependencies": note.dependencies,
        "__module__": __name__,
    })

    return dyn_cls


def register_dynamic_skill(
    registry: ImmutableSkillRegistry,
    note: SkillNote,
    ask_llm: Optional[Callable[[str, str], Any]] = None,
) -> Optional[str]:
    """Create, wire, and register a dynamic skill from a vault note.

    Returns the skill name on success, None on failure.
    """
    try:
        # 1. Create the class
        skill_cls = make_skill_class(note)

        # 2. Register (adds to registry, marks as frozen)
        registry.register(skill_cls)

        # 3. Wire vault-instance data before freeze
        #    wire_dependency creates the instance and sets attributes
        registry.wire_dependency(note.name, "vault_path", note.vault_path)
        registry.wire_dependency(note.name, "execution_mode", note.execution_mode)
        registry.wire_dependency(note.name, "required_params", note.required_params)
        registry.wire_dependency(note.name, "instructions", note.instructions)

        # 4. Wire LLM callable if provided
        if ask_llm is not None:
            registry.wire_dependency(note.name, "ask_llm", ask_llm)

        log.info(f"[dynamic] registered skill '{note.name}' v{note.version} from {note.vault_path}")
        return note.name

    except Exception as e:
        log.error(f"[dynamic] failed to register skill from {note.vault_path}: {e}")
        return None


def unregister_dynamic_skill(registry: ImmutableSkillRegistry, skill_name: str) -> bool:
    """Unregister a dynamic skill from the registry."""
    try:
        ok = registry.unregister(skill_name)
        if ok:
            # Also remove from _frozen set
            if hasattr(registry, "_frozen"):
                registry._frozen.discard(skill_name)
            log.info(f"[dynamic] unregistered skill '{skill_name}'")
        return ok
    except Exception as e:
        log.warning(f"[dynamic] failed to unregister '{skill_name}': {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# VAULT SKILL DISCOVERER
# ─────────────────────────────────────────────────────────────────────────────


class VaultSkillDiscoverer:
    """Scans vault directories for skill-defining notes and manages them.

    Responsibilities:
      - Scan vault notes for type: skill frontmatter
      - Generate and register DynamicSkill subclasses
      - Track note → skill mapping (for updates / re-scan)
      - Generate new vault skill notes from descriptions
    """

    def __init__(
        self,
        registry: ImmutableSkillRegistry,
        ask_llm: Optional[Callable[[str, str], Any]] = None,
    ):
        self.registry = registry
        self.ask_llm = ask_llm
        # vault_path → skill_name mapping
        self._tracked: dict[str, str] = {}
        # skill_name → vault_path reverse mapping
        self._reverse: dict[str, str] = {}

    # ── Discovery ─────────────────────────────────────────────────────

    def scan_and_register(self) -> dict:
        """Scan all vault directories, discover skill notes, register them.

        Returns a summary dict with registered, skipped, and failed counts.
        """
        registered = 0
        skipped = 0
        failed = 0
        errors: list[str] = []

        found = self._discover_notes()
        for note in found:
            if note.name in self._reverse:
                # Already registered — skip (could add re-registration later)
                log.debug(f"[dynamic] skill '{note.name}' already registered, skipping")
                skipped += 1
                continue

            result = register_dynamic_skill(self.registry, note, ask_llm=self.ask_llm)
            if result:
                self._tracked[note.vault_path] = note.name
                self._reverse[note.name] = note.vault_path
                registered += 1
            else:
                failed += 1
                errors.append(note.name)

        return {
            "registered": registered,
            "skipped": skipped,
            "failed": failed,
            "errors": errors,
            "total": len(self._tracked),
            "skills": list(self._reverse.keys()),
        }

    def _discover_notes(self) -> list[SkillNote]:
        """Walk vault directories and parse skill-defining notes."""
        notes: list[SkillNote] = []

        for vault_dir in [VAULT_REPO, VAULT_HERMES]:
            if not os.path.isdir(vault_dir):
                continue
            for root, _dirs, files in os.walk(vault_dir):
                for f in files:
                    if not f.endswith(".md"):
                        continue
                    filepath = os.path.join(root, f)
                    note = parse_vault_note(filepath)
                    if note is not None:
                        notes.append(note)

        return notes

    # ── Skill Note Generation ─────────────────────────────────────────

    async def generate_skill_note(
        self,
        name: str,
        description: str,
        instructions: str,
        *,
        tags: Optional[list[str]] = None,
        required_params: Optional[list[str]] = None,
        dependencies: Optional[list[str]] = None,
        execution_mode: str = "llm",
        timeout_seconds: float = 60.0,
        overwrite: bool = False,
    ) -> dict:
        """Create a new vault note with a skill definition.

        Returns dict with {'ok': True, 'path': ..., 'name': ...} or error dict.
        """
        # Determine target directory
        target_dir = os.path.join(VAULT_REPO, "skills")
        os.makedirs(target_dir, exist_ok=True)

        # Sanitize name to a safe filename
        safe_name = name.replace(".", "_").replace("-", "_")
        filepath = os.path.join(target_dir, f"{safe_name}.md")

        if os.path.exists(filepath) and not overwrite:
            return {
                "ok": False,
                "error": f"Skill note already exists at {filepath} (use overwrite=true to replace)",
                "path": filepath,
            }

        # Build YAML frontmatter
        fm = {
            "type": "skill",
            "name": name,
            "version": "1.0.0",
            "description": description,
            "tags": tags or ["domain:custom", "mode:sync"],
            "timeout_seconds": timeout_seconds,
            "max_retries": 2,
            "execution_mode": execution_mode,
            "required_params": required_params or [],
        }
        if dependencies:
            fm["dependencies"] = dependencies

        # Write the note
        content = f"---\n{yaml.dump(fm, default_flow_style=False, sort_keys=False).strip()}\n---\n\n{instructions.strip()}\n"

        try:
            with open(filepath, "w") as f:
                f.write(content)
        except Exception as e:
            return {"ok": False, "error": f"Failed to write note: {e}"}

        # Parse back to verify + register
        note = parse_vault_note(filepath)
        if note is None:
            return {"ok": False, "error": "Generated note failed validation", "path": filepath}

        if note.name in self._reverse:
            # Re-register: unregister old, register new
            old_name = note.name
            unregister_dynamic_skill(self.registry, old_name)
            self._tracked.pop(self._reverse.get(old_name, ""), None)
            self._reverse.pop(old_name, None)

        result = register_dynamic_skill(self.registry, note, ask_llm=self.ask_llm)
        if result:
            self._tracked[note.vault_path] = note.name
            self._reverse[note.name] = note.vault_path

        return {
            "ok": True,
            "path": filepath,
            "name": name,
            "registered": result is not None,
        }

    # ── AI-Powered Generation ─────────────────────────────────────────

    async def generate_from_description(
        self,
        description: str,
        *,
        ask_llm: Optional[Callable[[str, str], Any]] = None,
    ) -> dict:
        """Use an LLM to generate a vault skill note from a natural language description.

        The LLM proposes:
          - name (dotted notation, e.g. 'custom.storm.research')
          - description
          - required_params
          - tags
          - dependencies
          - instructions (the actual skill behavior)

        Returns the same format as generate_skill_note().
        """
        llm = ask_llm or self.ask_llm
        if llm is None:
            return {"ok": False, "error": "No ask_llm available for AI generation"}

        system = (
            "You are a skill architect for the Empire AI Skills Framework. "
            "Given a user's description of a new skill, generate a complete vault skill note "
            "with YAML frontmatter and instruction body. "
            "Return ONLY valid JSON with these keys:\n"
            "  - name: dotted skill name (e.g., 'custom.storm.research')\n"
            "  - description: one-sentence description\n"
            "  - tags: list of domain tags (e.g., ['domain:custom', 'mode:sync'])\n"
            "  - timeout_seconds: max execution time (15-120)\n"
            "  - required_params: list of parameter names the skill needs\n"
            "  - dependencies: list of other skill names it depends on (or empty list)\n"
            "  - instructions: the detailed instructions the LLM should follow when executing this skill\n"
            "  - execution_mode: 'llm' (always)\n\n"
            "The instructions should be clear, actionable, and include what the skill should return."
        )

        try:
            result = await llm(system, description)
            # Parse JSON from LLM response
            data = json.loads(result)
        except json.JSONDecodeError:
            return {"ok": False, "error": "LLM returned invalid JSON for skill generation"}
        except Exception as e:
            return {"ok": False, "error": f"LLM call failed: {e}"}

        name = data.get("name", "").strip()
        if not name:
            return {"ok": False, "error": "LLM did not provide a skill name"}

        return await self.generate_skill_note(
            name=name,
            description=data.get("description", ""),
            instructions=data.get("instructions", "Execute the skill according to its description."),
            tags=data.get("tags"),
            required_params=data.get("required_params"),
            dependencies=data.get("dependencies"),
            execution_mode=data.get("execution_mode", "llm"),
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
        )

    # ── Snapshot & Management ─────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return the current state of tracked skills."""
        return {
            "tracked_count": len(self._tracked),
            "skills": list(self._reverse.keys()),
            "notes": {path: name for path, name in self._tracked.items()},
        }

    def list_discovered(self) -> list[dict]:
        """List all discovered dynamic skills with their note paths."""
        results = []
        for vault_path, skill_name in self._tracked.items():
            skill = self.registry.get(skill_name)
            results.append({
                "name": skill_name,
                "vault_path": vault_path,
                "version": skill.version if skill else "?",
                "description": skill.description if skill else "",
                "tags": skill.tags if skill else [],
                "registered": skill is not None,
            })
        return results


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def is_skill_note(filepath: str) -> bool:
    """Quick check: does a vault note define a skill?"""
    if not filepath.endswith(".md"):
        return False
    note = parse_vault_note(filepath)
    return note is not None
