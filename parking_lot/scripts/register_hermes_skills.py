"""
EMPIRE V49 · REGISTER HERMES SKILLS
=====================================
Scans brain_vault/skills/ for vault skill notes and registers them
with the ImmutableSkillRegistry via VaultSkillDiscoverer.

Run this after adding new SKILL.md files to brain_vault/skills/.

Usage:
    python scripts/register_hermes_skills.py
    python scripts/register_hermes_skills.py --list   # List registered skills only
"""

import os
import sys
import logging

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from skills import ImmutableSkillRegistry, VaultSkillDiscoverer
from skills.marketing_skills import register_marketing_skills

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)
log = logging.getLogger("register_hermes_skills")


def register_all_skills(ask_llm=None) -> dict:
    """Register all skills: vault notes + marketing skills + dynamic skills.
    
    If ask_llm is provided (async callable(system, user) -> str), it is wired
    as a dependency on all vault skills and marketing skills so they can execute
    their instructions via LLM. Without ask_llm, skills register in analysis-only
    mode (returning instructions without executing them).
    
    Returns a summary dict with counts and skill names.
    """
    registry = ImmutableSkillRegistry()
    
    # 1. Scan and register vault skill notes (brain_vault/skills/*.md)
    #    Wire ask_llm if provided so skills can execute via LLM
    discoverer = VaultSkillDiscoverer(registry, ask_llm=ask_llm)
    vault_result = discoverer.scan_and_register()
    
    # 2. Register marketing skills (45 skills from skills/marketingskills/)
    register_marketing_skills(registry, ask_llm=ask_llm)
    
    # 3. Snapshot the registry
    snapshot = registry.snapshot()
    
    return {
        "vault_skills": vault_result,
        "marketing_skills": {
            "registered": len([s for s in snapshot.get("skills", {}).keys() if s.startswith("marketing.")]),
        },
        "total_skills": snapshot.get("total_skills", 0),
        "all_skills": list(snapshot.get("skills", {}).keys()),
        "llm_wired": ask_llm is not None,
    }


def list_skills():
    """Print all registered skills by reusing register_all_skills()."""
    result = register_all_skills()
    
    print(f"\n{'='*60}")
    print(f"HERMES SKILL REGISTRY — {result['total_skills']} total skills")
    print(f"{'='*60}")
    
    # Group by domain
    domains = {}
    for name in sorted(result["all_skills"]):
        domain = name.split(".")[0] if "." in name else "other"
        domains.setdefault(domain, []).append(name)
    
    for domain in sorted(domains.keys()):
        print(f"\n  [{domain.upper()}]")
        for name in sorted(domains[domain]):
            print(f"    {name}")
    
    print(f"\n  Total: {result['total_skills']} skills")
    print(f"  Vault skills: {result['vault_skills']['registered']}")
    print(f"  Marketing skills: {result['marketing_skills']['registered']}")
    print(f"  LLM wired: {result['llm_wired']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Register Hermes skills from vault notes")
    parser.add_argument("--list", action="store_true", help="List all registered skills")
    args = parser.parse_args()
    
    if args.list:
        list_skills()
    else:
        result = register_all_skills()
        print(f"Registered {result['total_skills']} total skills")
        print(f"  Vault skills: {result['vault_skills']['registered']} new, "
              f"{result['vault_skills']['skipped']} skipped, "
              f"{result['vault_skills']['failed']} failed")
        print(f"  Marketing skills: {result['marketing_skills']['registered']}")
        print(f"\nAll skills: {len(result['all_skills'])}")
        
        # Print the new vault skills
        new_skills = [s for s in result['vault_skills'].get('skills', [])]
        if new_skills:
            print(f"\nNew vault skills:")
            for s in new_skills:
                print(f"  ✓ {s}")
