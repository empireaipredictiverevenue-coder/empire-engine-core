#!/usr/bin/env python3
"""
EMPIRE V49 · SKILLSPECTOR BRIDGE
=================================
Lightweight security scanner that uses NVIDIA SkillSpector's static analysis
patterns to detect vulnerabilities in agent Python files before deployment.

Does NOT require Python 3.12+ or the SkillSpector package. Uses Python's
built-in `ast` module to extract regex patterns directly from SkillSpector's
source files, then scans agent Python files for matches.

Categories covered (16 total, from SkillSpector):
    PROMPT_INJECTION, DATA_EXFILTRATION, PRIVILEGE_ESCALATION,
    SUPPLY_CHAIN, EXCESSIVE_AGENCY, OUTPUT_HANDLING,
    SYSTEM_PROMPT_LEAKAGE, MEMORY_POISONING, TOOL_MISUSE,
    ROGUE_AGENT, TRIGGER_ABUSE, HARMFUL_CONTENT,
    YARA_MATCH, MCP_LEAST_PRIVILEGE, MCP_TOOL_POISONING,
    CONFIG_LEAKAGE

Usage:
    from bots.skillspector_bridge import scan_agent_file, scan_agent_directory

    findings = scan_agent_file("/root/empire-v49/bots/vonage_engineer_agent.py")
    for f in findings:
        print(f"{f['severity']}: {f['category']} — {f['message']} (line {f['line']})")
"""

import os
import re
import ast
import sys
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger("empire.skillspector_bridge")

# ── SkillSpector source directory ─────────────────────────────────────
SKILLSPECTOR_SRC = "/root/nvidia-skill-spector/src/skillspector"
SKILLSPECTOR_PATTERNS_DIR = os.path.join(SKILLSPECTOR_SRC, "nodes", "analyzers")

# ── Severity mapping ──────────────────────────────────────────────────
# SkillSpector uses confidence scores (0.0-1.0). Map to our severity levels.
SEVERITY_THRESHOLDS = {
    "CRITICAL": 0.85,   # ≥ 0.85 confidence
    "HIGH":     0.65,   # ≥ 0.65
    "MEDIUM":   0.40,   # ≥ 0.40
    "LOW":      0.0,    # ≥ 0.0
}

# ── Category mapping from pattern file names ──────────────────────────
CATEGORY_FILE_MAP = {
    "static_patterns_prompt_injection":       "PROMPT_INJECTION",
    "static_patterns_data_exfiltration":      "DATA_EXFILTRATION",
    "static_patterns_privilege_escalation":   "PRIVILEGE_ESCALATION",
    "static_patterns_supply_chain":           "SUPPLY_CHAIN",
    "static_patterns_excessive_agency":       "EXCESSIVE_AGENCY",
    "static_patterns_output_handling":        "OUTPUT_HANDLING",
    "static_patterns_system_prompt_leakage":  "SYSTEM_PROMPT_LEAKAGE",
    "static_patterns_memory_poisoning":       "MEMORY_POISONING",
    "static_patterns_tool_misuse":            "TOOL_MISUSE",
    "static_patterns_rogue_agent":            "ROGUE_AGENT",
    "static_patterns_harmful_content":        "HARMFUL_CONTENT",
}


@dataclass
class ScanFinding:
    """A single vulnerability finding from a scan."""
    category: str           # e.g., "PROMPT_INJECTION"
    severity: str           # CRITICAL, HIGH, MEDIUM, LOW
    pattern: str            # the regex pattern that matched
    confidence: float       # SkillSpector confidence score (0.0-1.0)
    line: int               # line number in the scanned file
    snippet: str            # the matched line content
    message: str            # human-readable description
    file_path: str = ""     # path of the scanned file
    pattern_name: str = ""  # pattern identifier (e.g., "P1")


# ── Pattern extraction via AST ─────────────────────────────────────────

def _extract_patterns_from_file(
    file_path: str,
    pattern_var_prefixes: tuple = ("P", "E", "PE", "SC", "EA", "OH", "SL", "MP", "TM", "RA", "HC"),
) -> List[Tuple[re.Pattern, float, str]]:
    """Parse a SkillSpector static_patterns_*.py file using AST and extract
    all compiled regex patterns with their confidence scores.

    SkillSpector patterns are defined as module-level lists:
        P1_PATTERNS = [(re.compile(r'...'), 0.85), ...]

    Returns a list of (compiled_regex, confidence_score, pattern_name) tuples.
    """
    patterns = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception as e:
        log.warning(f"[skillspector_bridge] failed to parse {file_path}: {e}")
        return patterns

    for node in ast.walk(tree):
        # Look for assignments to *_PATTERNS variables
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            var_name = target.id
            if not any(var_name.startswith(pfx) for pfx in pattern_var_prefixes):
                continue
            if "_PATTERNS" not in var_name and "_TRIGGERS" not in var_name:
                continue

            # Extract the list of (re.compile(...), confidence) tuples
            if not isinstance(node.value, ast.List):
                continue

            for elt in node.value.elts:
                if not isinstance(elt, ast.Tuple) or len(elt.elts) < 2:
                    continue

                # First element: re.compile(r'...') call
                regex_str = _extract_regex_from_call(elt.elts[0])
                if not regex_str:
                    continue

                # Second element: confidence score (float literal)
                confidence = _extract_confidence(elt.elts[1])
                if confidence is None:
                    confidence = 0.5  # default if not parseable

                try:
                    compiled = re.compile(regex_str, re.IGNORECASE)
                    patterns.append((compiled, confidence, var_name))
                except re.error:
                    log.debug(f"[skillspector_bridge] bad regex in {var_name}: {regex_str[:60]}")

    return patterns


def _extract_regex_from_call(node: ast.AST) -> Optional[str]:
    """Extract the regex string from a re.compile('...') call."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call):
        # re.compile(r'...') or re.compile(r'...', flags)
        if (isinstance(node.func, ast.Attribute) and
                isinstance(node.func.value, ast.Name) and
                node.func.value.id == "re" and
                node.func.attr == "compile"):
            if node.args:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                    return first_arg.value
    return None


def _extract_confidence(node: ast.AST) -> Optional[float]:
    """Extract a float confidence score from an AST node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    return None


def _severity_from_confidence(confidence: float) -> str:
    """Map a confidence score (0.0-1.0) to a severity label."""
    for sev, threshold in sorted(SEVERITY_THRESHOLDS.items(),
                                  key=lambda x: x[1], reverse=True):
        if confidence >= threshold:
            return sev
    return "LOW"


# ── Pattern cache ──────────────────────────────────────────────────────

_pattern_cache: Optional[List[Tuple[re.Pattern, float, str, str]]] = None


def _load_all_patterns() -> List[Tuple[re.Pattern, float, str, str]]:
    """Load all SkillSpector static patterns, caching the result.
    Returns list of (compiled_regex, confidence, pattern_name, category) tuples.
    """
    global _pattern_cache
    if _pattern_cache is not None:
        return _pattern_cache

    if not os.path.isdir(SKILLSPECTOR_PATTERNS_DIR):
        log.warning(f"[skillspector_bridge] SkillSpector patterns dir not found: {SKILLSPECTOR_PATTERNS_DIR}")
        _pattern_cache = []
        return _pattern_cache

    all_patterns = []
    for filename in sorted(os.listdir(SKILLSPECTOR_PATTERNS_DIR)):
        if not filename.startswith("static_patterns_") or not filename.endswith(".py"):
            continue
        file_path = os.path.join(SKILLSPECTOR_PATTERNS_DIR, filename)
        module_name = filename[:-3]  # strip .py

        category = CATEGORY_FILE_MAP.get(module_name, module_name.upper())
        extracted = _extract_patterns_from_file(file_path)

        for regex, confidence, pattern_name in extracted:
            all_patterns.append((regex, confidence, pattern_name, category))

    log.info(f"[skillspector_bridge] loaded {len(all_patterns)} patterns from "
             f"{len(set(c for _, _, _, c in all_patterns))} categories")

    _pattern_cache = all_patterns
    return _pattern_cache


def _clear_pattern_cache() -> None:
    """Clear the pattern cache (for testing or after SkillSpector update)."""
    global _pattern_cache
    _pattern_cache = None


# ── Scanning ───────────────────────────────────────────────────────────

def scan_agent_file(file_path: str) -> List[Dict]:
    """Scan a single agent Python file for SkillSpector vulnerabilities.

    Returns a list of dicts, each with:
        category, severity, pattern, confidence, line, snippet, message,
        file_path, pattern_name
    """
    patterns = _load_all_patterns()
    if not patterns:
        return []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        log.warning(f"[skillspector_bridge] cannot read {file_path}: {e}")
        return []

    findings = []
    for line_num, line in enumerate(lines, start=1):
        for regex, confidence, pattern_name, category in patterns:
            match = regex.search(line)
            if match:
                severity = _severity_from_confidence(confidence)
                snippet = line.strip()[:120]
                findings.append({
                    "category": category,
                    "severity": severity,
                    "pattern": regex.pattern,
                    "confidence": confidence,
                    "line": line_num,
                    "snippet": snippet,
                    "message": f"[{category}] {pattern_name}: {snippet}",
                    "file_path": file_path,
                    "pattern_name": pattern_name,
                })
                break  # one finding per line, per category is enough

    return findings


def scan_agent_directory(
    directory: str,
    file_pattern: str = "*.py",
    exclude_patterns: Optional[List[str]] = None,
    extra_globs: Optional[List[str]] = None,
) -> Dict[str, List[Dict]]:
    """Scan all agent files in a directory.

    By default scans *.py files. Pass extra_globs=['*.md'] to also scan
    SkillSpector-compatible markdown files (e.g. SKILL.md prompt templates).

    Returns dict of {file_path: [findings]}.
    """
    if exclude_patterns is None:
        exclude_patterns = ["__init__.py", "test_", "_test.py", "setup.py"]

    results = {}
    dir_path = Path(directory)
    if not dir_path.is_dir():
        log.warning(f"[skillspector_bridge] not a directory: {directory}")
        return results

    # Collect files from primary and extra globs
    all_files = set(dir_path.rglob(file_pattern))
    for extra_glob in (extra_globs or []):
        all_files.update(dir_path.rglob(extra_glob))

    for file_path in sorted(all_files):
        # Skip excluded files
        fname = file_path.name
        if any(fname.startswith(ex) or ex in fname for ex in exclude_patterns):
            continue
        # Skip symlinks, non-files
        if not file_path.is_file():
            continue

        file_path_str = str(file_path)
        findings = scan_agent_file(file_path_str)
        if findings:
            results[file_path_str] = findings

    return results


def scan_all_agents(
    agent_dirs: Optional[List[str]] = None,
) -> Dict[str, List[Dict]]:
    """Scan all agent directories. Defaults to bots/ and agents/.

    Returns dict of {file_path: [findings]}.
    """
    if agent_dirs is None:
        repo_root = Path(__file__).resolve().parent.parent
        agent_dirs = [
            str(repo_root / "bots"),
            str(repo_root / "agents"),
        ]

    all_findings = {}
    for d in agent_dirs:
        if os.path.isdir(d):
            results = scan_agent_directory(d)
            all_findings.update(results)

    return all_findings


def summarize_findings(findings: Dict[str, List[Dict]]) -> Dict:
    """Produce a summary of scan findings."""
    total_files = len(findings)
    total_findings = sum(len(v) for v in findings.values())

    by_severity = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    by_category = {}
    files_with_critical = []

    for file_path, file_findings in findings.items():
        for f in file_findings:
            sev = f["severity"]
            cat = f["category"]
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_category[cat] = by_category.get(cat, 0) + 1
            if sev == "CRITICAL":
                files_with_critical.append({
                    "file": file_path,
                    "line": f["line"],
                    "message": f["message"],
                })

    return {
        "files_scanned": total_files,
        "total_findings": total_findings,
        "by_severity": by_severity,
        "by_category": by_category,
        "critical_findings": files_with_critical,
        "verdict": "CLEAN" if total_findings == 0 else "VULNERABILITIES_FOUND",
    }


# ── Standalone entry point ─────────────────────────────────────────────

def main():
    """CLI entry point for manual scans."""
    import json
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    repo = Path(__file__).resolve().parent.parent
    findings = scan_all_agents([
        str(repo / "bots"),
        str(repo / "agents"),
    ])
    summary = summarize_findings(findings)

    print(f"\n=== SKILLSPECTOR BRIDGE — AGENT SECURITY SCAN ===")
    print(f"Files scanned:  {summary['files_scanned']}")
    print(f"Findings:       {summary['total_findings']}")
    print(f"By severity:    {json.dumps(summary['by_severity'])}")
    print(f"By category:    {json.dumps(summary['by_category'])}")
    print(f"Verdict:        {summary['verdict']}")

    if summary["critical_findings"]:
        print(f"\n⚠️  CRITICAL FINDINGS ({len(summary['critical_findings'])}):")
        for cf in summary["critical_findings"][:10]:
            print(f"  {cf['file']}:{cf['line']} — {cf['message'][:120]}")

    # Print all findings grouped by file
    for file_path, file_findings in findings.items():
        short_path = file_path.replace(str(repo) + "/", "")
        print(f"\n  {short_path} ({len(file_findings)} findings):")
        for f in file_findings[:5]:
            print(f"    [{f['severity']}] {f['category']} L{f['line']}: {f['snippet'][:100]}")

    return json.dumps(summary, indent=2, default=str)


if __name__ == "__main__":
    print(main())
