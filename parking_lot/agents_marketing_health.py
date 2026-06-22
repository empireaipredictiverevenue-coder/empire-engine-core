"""
EMPIRE V49 · MARKETING SKILLS DAILY HEALTH CHECK
==================================================
Runs once daily (05:00 UTC via crontab). Validates all 45 marketing skills:

  1. SKILL.md file exists on disk and is non-empty
  2. Skill is registered in the ImmutableSkillRegistry
  3. ask_llm is wired on the skill instance
  4. Version and description are set
  5. Skill can be instantiated without error

Logs to logs/agent_marketing_health.log and Supabase agent_activity table.
Sends Telegram alert if any skill fails its health check.
"""

import os
import sys
import json
import uuid
import logging
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from skills.marketing_skills import register_marketing_skills, MARKETING_SKILL_CLASSES, _MARKETING_SKILLS_DIR
from skills.registry import ImmutableSkillRegistry

# ── Config ───────────────────────────────────────────────────────────
AGENT_NAME = "marketing_health"
MARKETING_COUNT = len(MARKETING_SKILL_CLASSES)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Logging
_log = logging.getLogger(AGENT_NAME)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [marketing-health] %(levelname)s %(message)s",
)


# ── Helpers ──────────────────────────────────────────────────────────

def _sb():
    """Lazy supabase client."""
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _telegram_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _telegram_chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "")


def _send_telegram_alert(text: str):
    """Best-effort Telegram alert. Silent on failure."""
    import urllib.request as _ur
    tok = _telegram_token()
    chat = _telegram_chat_id()
    if not tok or not chat:
        _log.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set; skipping alert")
        return
    try:
        payload = json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
        req = _ur.Request(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        _ur.urlopen(req, timeout=10)
    except Exception as e:
        _log.warning(f"telegram alert failed: {e}")


# ── Health Check ─────────────────────────────────────────────────────

def run_once() -> dict:
    """Run the full health check. Returns results dict."""
    started_at = datetime.now(timezone.utc)
    results = []

    # Wire up a minimal registry with a fake ask_llm for wiring verification
    async def _fake_llm(system: str, user: str) -> str:
        return "health check"

    reg = ImmutableSkillRegistry()
    try:
        register_marketing_skills(reg, ask_llm=_fake_llm)
    except Exception as e:
        _log.error(f"registry wiring failed: {e}")
        return {"ok": False, "error": str(e), "passed": 0, "failed": 1, "total": MARKETING_COUNT}

    for cls in MARKETING_SKILL_CLASSES:
        check = {
            "name": cls.name,
            "skill_name": cls.skill_name,
            "passed": True,
            "issues": [],
        }

        # 1. SKILL.md exists and non-empty
        md_path = os.path.join(_MARKETING_SKILLS_DIR, cls.skill_name, "SKILL.md")
        md_exists = os.path.exists(md_path)
        md_size = os.path.getsize(md_path) if md_exists else 0
        if not md_exists:
            check["issues"].append("SKILL.md missing")
            check["passed"] = False
        elif md_size < 100:
            check["issues"].append(f"SKILL.md too small ({md_size}b)")
            check["passed"] = False

        # 2. Registered in registry
        skill = reg.get(cls.name)
        if skill is None:
            check["issues"].append("not registered in registry")
            check["passed"] = False

        # 3. ask_llm wired
        if skill is not None:
            has_llm = getattr(skill, "ask_llm", None) is not None
            if not has_llm:
                check["issues"].append("ask_llm not wired")
                check["passed"] = False

        # 4. Version set
        if skill is not None and not skill.version:
            check["issues"].append("version not set")
            check["passed"] = False

        # 5. Description set
        if skill is not None and not skill.description:
            check["issues"].append("description not set")
            check["passed"] = False

        results.append(check)

    # Aggregate
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    failed_names = [r["name"] for r in results if not r["passed"]]
    failed_issues = {r["name"]: r["issues"] for r in results if not r["passed"]}

    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "total": MARKETING_COUNT,
        "results": results,
        "failed_names": failed_names,
        "failed_issues": failed_issues,
        "started_at": started_at.isoformat(),
    }


# ── Logging ──────────────────────────────────────────────────────────

def log_to_agent_activity(started_at, status: str, summary: str, meta: dict) -> None:
    """Log the health check run to Supabase agent_activity."""
    try:
        sb = _sb()
        sb.table("agent_activity").insert({
            "agent_name": AGENT_NAME,
            "run_id": str(uuid.uuid4()),
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "rows_seen": meta.get("total", 0),
            "rows_processed": meta.get("passed", 0),
            "rows_errored": meta.get("failed", 0),
            "summary": summary[:500],
            "meta": meta if isinstance(meta, dict) else {},
        }).execute()
    except Exception as e:
        _log.warning(f"failed to log to agent_activity: {e}")


# ── Entry Point ──────────────────────────────────────────────────────

def main() -> int:
    _log.info(f"starting marketing skills health check ({MARKETING_COUNT} skills)")

    result = run_once()
    started_at = datetime.fromisoformat(result["started_at"])

    # Trim meta to avoid oversized payload
    activity_meta = {
        "passed": result["passed"],
        "failed": result["failed"],
        "total": result["total"],
        "failed_issues": result.get("failed_issues", {}),
    }

    if result["ok"]:
        _log.info(f"ALL {result['passed']}/{result['total']} skills healthy ✅")
        log_to_agent_activity(
            started_at, "ok",
            f"{result['passed']}/{result['total']} marketing skills healthy",
            activity_meta,
        )
        return 0

    # Failures — log error, alert
    _log.warning(
        f"{result['failed']}/{result['total']} skills FAILED: "
        f"{result['failed_names']}"
    )
    for name, issues in result["failed_issues"].items():
        _log.warning(f"  ❌ {name}: {'; '.join(issues)}")

    summary = (
        f"{result['passed']}/{result['total']} marketing skills healthy, "
        f"{result['failed']} failed"
    )
    log_to_agent_activity(started_at, "error", summary, activity_meta)

    # Telegram alert
    alert_lines = [
        f"🔴 Marketing Skills Health Check — {result['failed']} failures",
        f"  {result['passed']}/{result['total']} healthy",
        "",
    ]
    for name, issues in result["failed_issues"].items():
        alert_lines.append(f"  ❌ {name}: {'; '.join(issues)}")
    _send_telegram_alert("\n".join(alert_lines))

    return 1


if __name__ == "__main__":
    sys.exit(main())
