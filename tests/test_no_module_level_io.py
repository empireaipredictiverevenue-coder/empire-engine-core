"""
EMPIRE V49 · NO MODULE-LEVEL I/O STATIC-ANALYSIS TEST
======================================================
Lint-time check that catches the regression pattern of network/I/O calls
at module top-level (indented 0). The canonical fix is to wrap such calls
in an `os.environ.get("EMPIRE_TESTING") == "1"` guard — see
`empire_agi_governor.py` for the example.

This test uses Python's `ast` module to find top-level statements that
match I/O patterns. It does NOT need to import the module (so it runs
even when the import would fail) and is immune to false positives from
comments, docstrings, and string literals.

Allowed offenders (grandfathered, existing modules with module-level I/O):
    If a NEW file appears with module-level I/O, this test will fail with
    the specific filename, line number, and pattern matched. Add the file
    to ALLOWED_OFFENDERS only if you have a good reason — otherwise, fix
    the file by wrapping the call in a guard or by lazy-initializing the
    client inside a function.

Why AST instead of regex?
    - Skips matches in comments, docstrings, and string literals
    - Skips matches inside functions/classes (only top-level matters)
    - Reports the exact line number of the statement start
    - Handles multi-line statements correctly
"""
import ast
import os
import sys
import unittest
from pathlib import Path


# ─── Project layout ─────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Directories excluded from the scan. Test scripts legitimately touch I/O
# (they're test fixtures, not production code); migrations are SQL;
# node_modules / .git / venvs are obvious.
EXCLUDE_DIRS = {
    "__pycache__",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "env",
    "tests",          # test files are fixtures, allowed to mock I/O freely
    "scripts",        # one-off ops scripts
    "migrations",     # SQL files only
    ".github",        # YAML workflows
    "outreach_drafts",  # text drafts
}

# ─── I/O patterns (matched as full call names) ──────────────────────────
# A top-level statement is flagged if its Call node's name is in this set
# OR if it starts with "requests." (any method on the requests module).
IO_PATTERNS: set[str] = {
    # Supabase
    "create_client",
    "supabase.create_client",
    # httpx (sync + async + standalone)
    "httpx.Client",
    "httpx.AsyncClient",
    "httpx.post",
    "httpx.get",
    "httpx.put",
    "httpx.delete",
    # Any requests.* method is matched via the `requests.` prefix below
}


def _call_name(node: ast.Call) -> str | None:
    """Extract the full dotted call name from an ast.Call node, or None."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return f"{func.value.id}.{func.attr}"
    return None


def _match_io(name: str | None) -> str | None:
    """Return the matched pattern, or None if this is not an I/O call."""
    if name is None:
        return None
    if name in IO_PATTERNS:
        return name
    # requests.* — any method on the requests module
    if name.startswith("requests."):
        return name
    return None


# ─── Files that legitimately have module-level I/O today ───────────────
# These are the existing offenders. Keep this list SMALL and DOCUMENTED.
# If you add a file, write a one-line comment explaining why it must have
# module-level I/O (e.g., "entry-point script that needs a Supabase client
# at startup" or "legacy code, lazy init tracked in ISSUE-1234").
ALLOWED_OFFENDERS: set[str] = {
    # ── Top-level scripts / entry points ──
    "main.py",                   # entry-point: needs sb at startup
    "orchestrator_agent.py",     # legacy orchestrator entry-point
    "test_billing_flow.py",      # billing flow test fixture

    # ── Empire modules with module-level I/O ──
    "empire_outbound_dialer.py", # legacy dialer
    "empire_brain.py",           # brain router
    "empire_partner_onboarding.py",  # partner onboarding
    "empire_switchboard.py",     # switchboard engine

    # ── Bots with module-level I/O ──
    "bots/decision_makers.py",
    "bots/mesh_dispatcher.py",
    "bots/seed_mass_tort_buyer.py",
    "bots/mesh_outreach.py",
    "bots/agi_revenue.py",
    "bots/hermes_controller.py",
    "bots/predictive_revenue.py",
    "bots/quality_analyst.py",
    "bots/mesh_scout.py",
    "bots/agi_lane_engine.py",
    "bots/buyer_outreach.py",
    "bots/mesh_studio_copy.py",
    "bots/storm_predictor.py",
    "bots/mass_tort_bridge.py",
    "bots/prospector.py",
    "bots/angi_scraper.py",
    "bots/mesh_studio_render.py",
    "bots/check_ledger.py",
    "bots/overseer.py",
    "bots/contractor_sniper.py",
}


def _iter_python_files():
    """Yield (rel_path, abs_path) for every .py file under project root."""
    for root, dirs, files in os.walk(_PROJECT_ROOT):
        # In-place filter so os.walk skips excluded directories
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for fname in sorted(files):
            if not fname.endswith(".py"):
                continue
            abs_path = Path(root) / fname
            rel_path = abs_path.relative_to(_PROJECT_ROOT).as_posix()
            yield rel_path, abs_path


def _find_module_level_io(filepath: Path) -> list[tuple[int, str, str]]:
    """
    Parse a .py file and return [(line_no, pattern, line_text)] for
    any TOP-LEVEL statement that matches an I/O pattern. Skips imports,
    skips nested function bodies, and ignores comments/strings.
    """
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError):
        return []
    lines = source.splitlines()
    findings: list[tuple[int, str, str]] = []

    # We only inspect tree.body — these are top-level statements.
    # Function bodies, class bodies, etc. are nested and not checked here.
    for node in tree.body:
        call: ast.Call | None = None
        if isinstance(node, ast.Call):
            call = node
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
        if call is None:
            continue
        matched = _match_io(_call_name(call))
        if matched:
            line_no = getattr(node, "lineno", call.lineno)
            line_text = lines[line_no - 1].strip()[:120] if 0 < line_no <= len(lines) else ""
            findings.append((line_no, matched, line_text))
    return findings


# ─── Tests ──────────────────────────────────────────────────────────────
class TestNoModuleLevelIO(unittest.TestCase):
    """
    No NEW .py file in the project may have a top-level call to
    `create_client(`, `httpx.{Client,AsyncClient,post,get,put,delete}`,
    or `requests.<anything>(`. Existing offenders are grandfathered in
    ALLOWED_OFFENDERS.
    """

    def test_no_new_module_level_io(self):
        """Walk all .py files; fail if any non-allowlisted file has module-level I/O."""
        offenders: list[tuple[str, int, str, str]] = []
        for rel_path, abs_path in _iter_python_files():
            if rel_path in ALLOWED_OFFENDERS:
                continue
            for line_no, pattern, line_text in _find_module_level_io(abs_path):
                offenders.append((rel_path, line_no, pattern, line_text))
        if offenders:
            details = "\n".join(
                f"  - {rel}:{line} matches {pattern!r}\n      {txt}"
                for rel, line, pattern, txt in offenders
            )
            self.fail(
                f"{len(offenders)} NEW module-level I/O call(s) detected. "
                f"Top-level network calls break the EMPIRE_TESTING=1 import contract.\n\n"
                f"{details}\n\n"
                f"Fix: wrap the call in an `os.environ.get('EMPIRE_TESTING') == '1'` "
                f"guard, lazy-initialize the client inside a function, OR — if the "
                f"file legitimately needs module-level I/O — add it to "
                f"ALLOWED_OFFENDERS in tests/test_no_module_level_io.py with a "
                f"comment explaining why."
            )

    def test_allowlist_is_well_formed(self):
        """ALLOWED_OFFENDERS must be non-empty and contain only repo-relative .py paths."""
        self.assertGreater(len(ALLOWED_OFFENDERS), 0,
                           "ALLOWED_OFFENDERS should contain existing offenders")
        for entry in ALLOWED_OFFENDERS:
            self.assertIsInstance(entry, str)
            self.assertTrue(entry.endswith(".py"),
                            f"ALLOWED_OFFENDERS entry {entry!r} must be a .py path")
            # Must not contain absolute path or '..'
            self.assertFalse(os.path.isabs(entry), f"{entry!r} must be repo-relative")
            self.assertNotIn("..", entry, f"{entry!r} must not contain '..'")

    def test_no_self_referential_in_allowlist(self):
        """This test file should never be in ALLOWED_OFFENDERS (it has no I/O)."""
        self_test = "tests/test_no_module_level_io.py"
        self.assertNotIn(
            self_test, ALLOWED_OFFENDERS,
            f"{self_test} must not be in ALLOWED_OFFENDERS — it has no module-level I/O"
        )

    def test_scanner_finds_known_offenders(self):
        """Sanity check: the scanner actually detects known module-level I/O.
        Verifies at least 3 of the well-known files (main.py, bots/predictive_revenue.py,
        empire_switchboard.py) DO have module-level I/O. This catches bugs in the
        scanner itself (e.g., if a refactor breaks AST parsing silently)."""
        sample_files = [
            "main.py",
            "bots/predictive_revenue.py",
            "empire_switchboard.py",
        ]
        for rel in sample_files:
            abs_path = _PROJECT_ROOT / rel
            self.assertTrue(
                abs_path.exists(), f"Sample file {rel} does not exist"
            )
            hits = _find_module_level_io(abs_path)
            self.assertGreater(
                len(hits), 0,
                f"Scanner regression: {rel} should have module-level I/O "
                f"but scanner found none. Check IO_PATTERNS / _call_name / "
                f"_match_io logic."
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
