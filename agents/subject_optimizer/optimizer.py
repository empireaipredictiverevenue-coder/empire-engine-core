"""
EMPIRE · COLD EMAIL SUBJECT LINE OPTIMIZER
============================================
Autonomous A/B testing loop for cold email subject lines.

Reads historical open rates from subjects.json, scores the current
test against the baseline, and generates new mutations via OpenAI.
Winners are committed to git; losers are rolled back.

Notified via Hermes Telegram on:
  - New champion detected
  - Failed mutation rolled back
  - Low data warnings

Usage:
    python3 -m agents.subject_optimizer.optimizer              # normal run
    python3 -m agents.subject_optimizer.optimizer --dry-run    # no git ops
    python3 -m agents.subject_optimizer.optimizer --force      # skip batch size check

Integration:
    Connect get_current_stats_from_api() to your email platform's
    webhook or tracking database (Instantly, Smartlead, custom SMTP).
"""

import json
import os
import sys
import shlex
import subprocess
import logging
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from openai import OpenAI

log = logging.getLogger("empire.subject_optimizer")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [optimizer] %(message)s",
)

# ── Configuration ──────────────────────────────────────────────────────────

AGENT_DIR = Path(__file__).parent
INSTRUCTIONS_PATH = AGENT_DIR / "instructions.md"
SUBJECTS_PATH = AGENT_DIR / "subjects.json"

MIN_BATCH_SIZE = int(os.environ.get("OPTIMIZER_MIN_BATCH", "1000"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPTIMIZER_OPENAI_MODEL", "gpt-4o")
HERMES_BIN = "/usr/local/bin/hermes"


# ── Hermes Telegram Notification ──────────────────────────────────────────

def _telegram_send(text: str) -> bool:
    """Send a Telegram message via hermes CLI. Best-effort."""
    if not Path(HERMES_BIN).exists():
        log.debug("[optimizer] hermes binary not found, skipping Telegram notification")
        return False
    try:
        result = subprocess.run(
            [HERMES_BIN, "send", "--to", "telegram", text],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            log.info("[optimizer] Telegram notification sent")
            return True
        else:
            log.warning(f"[optimizer] Telegram send returned {result.returncode}: {result.stderr[:200]}")
            return False
    except Exception as e:
        log.debug(f"[optimizer] Telegram send failed: {e}")
        return False


def _notify_champion(subject: str, rate: float, sent: int):
    """Notify when a new champion subject line is found."""
    msg = (
        f"\U0001f3c6 Optimizer: New Champion\n"
        f"Subject: \"{subject}\"\n"
        f"Open Rate: {rate:.1f}%\n"
        f"Sample: {sent} sent\n"
        f"Committed to master."
    )
    _telegram_send(msg)


def _notify_failure(subject: str, rate: float, baseline: float):
    """Notify when a mutation fails to beat the baseline."""
    msg = (
        f"\u274c Optimizer: Mutation Failed\n"
        f"Subject: \"{subject}\"\n"
        f"Scored: {rate:.1f}% (baseline: {baseline:.1f}%)\n"
        f"Rolled back via git reset."
    )
    _telegram_send(msg)


def _notify_low_data(sent: int):
    """Notify when batch size is too small."""
    msg = (
        f"\u23f3 Optimizer: Waiting for Data\n"
        f"Current batch: {sent} sent (need {MIN_BATCH_SIZE})\n"
        f"Next check on the next cron tick."
    )
    _telegram_send(msg)


# ── Git helpers ────────────────────────────────────────────────────────────

def _git(command: str) -> bool:
    """Run a git command relative to the repo root. Returns True on success."""
    result = subprocess.run(
        shlex.split(command),
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.warning(f"[optimizer] git failed: {command[:60]} — {result.stderr[:200]}")
    return result.returncode == 0


# ── Stats (connect to your email platform) ─────────────────────────────────

def get_current_stats() -> tuple:
    """
    Fetch live campaign stats from your email platform.

    Connect this to Instantly, Smartlead, or your custom SMTP database.
    Returns (sent_count, open_count) for the current test batch.

    Default returns placeholder data for dry-run/testing.
    """
    # TODO: Replace with real API/webhook query
    return 1000, 480


# ── Core optimization loop ─────────────────────────────────────────────────

def run_optimization_loop(dry_run: bool = False, force: bool = False):
    """Run one full optimization cycle.

    Args:
        dry_run: If True, skip git operations and file writes.
        force: If True, skip the minimum batch size check.
    """
    log.info("[optimizer] Starting optimization cycle%s",
             " (DRY RUN)" if dry_run else "")

    # ── 1. Read current asset state ───────────────────────────────────
    if not SUBJECTS_PATH.exists():
        log.error(f"[optimizer] subjects.json not found at {SUBJECTS_PATH}")
        return

    with open(SUBJECTS_PATH) as f:
        data = json.load(f)

    current_subject = data.get("current_test", "")
    log.info(f"[optimizer] Current test: '{current_subject}'")

    # ── 2. Scorecard Check: Pull real data from the test batch ────────
    sent, opens = get_current_stats()
    log.info(f"[optimizer] Batch stats: {sent} sent, {opens} opens")

    if sent < MIN_BATCH_SIZE and not force:
        log.info(f"[optimizer] Waiting for more data. Current batch: {sent} (need {MIN_BATCH_SIZE})")
        if not dry_run:
            _notify_low_data(sent)
        return

    current_rate = (opens / sent) * 100 if sent > 0 else 0.0
    log.info(f"[optimizer] Current open rate: {current_rate:.1f}%")

    # Find the historical baseline high score
    baseline_high = 0.0
    if data.get("history"):
        baseline_high = max(h["open_rate_pct"] for h in data["history"])
    log.info(f"[optimizer] Baseline champion: {baseline_high:.1f}%")

    # ── 3. Decision Matrix: Did the mutation win? ─────────────────────
    if current_rate > baseline_high:
        log.info(f"\U0001f3c6 WINNER! {current_rate:.1f}% beats {baseline_high:.1f}%")

        # Log it to history
        if not dry_run:
            data.setdefault("history", []).append({
                "subject": current_subject,
                "sent_count": sent,
                "open_count": opens,
                "open_rate_pct": round(current_rate, 1),
            })

            with open(SUBJECTS_PATH, "w") as f:
                json.dump(data, f, indent=2)

            # Git commit the win
            _git("git add agents/subject_optimizer/subjects.json")
            _git(f"git commit -m 'opt(champion): {current_subject} at {current_rate:.1f}%'")

            # Notify via Telegram
            _notify_champion(current_subject, current_rate, sent)

    else:
        log.info(f"\u274c FAILURE. {current_rate:.1f}% failed to beat {baseline_high:.1f}%")

        if not dry_run:
            # Notify before reset
            _notify_failure(current_subject, current_rate, baseline_high)

            # Roll back the file to wipe out the bad copy variant
            _git("git checkout HEAD agents/subject_optimizer/subjects.json")

            # Reload the clean data state
            with open(SUBJECTS_PATH) as f:
                data = json.load(f)

    # ── 4. Mutation Step: Call OpenAI to create the next variation ────
    if not OPENAI_API_KEY:
        log.warning("[optimizer] OPENAI_API_KEY not set — skipping mutation. "
                    "Set it in /root/.env")
        # Use a sensible fallback for the next test
        new_subject = "quick update on your project"
        data["current_test"] = new_subject
        if not dry_run:
            with open(SUBJECTS_PATH, "w") as f:
                json.dump(data, f, indent=2)
        log.info(f"[optimizer] Fallback mutation: '{new_subject}'")
        return

    try:
        with open(INSTRUCTIONS_PATH) as f:
            instructions = f.read()
    except FileNotFoundError:
        log.error(f"[optimizer] instructions.md not found at {INSTRUCTIONS_PATH}")
        return

    client = OpenAI(api_key=OPENAI_API_KEY)

    prompt = f"Instructions:\n{instructions}\n\nCurrent Data State:\n{json.dumps(data)}"

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an autonomous growth engineering agent. "
                        "Follow the instructions strictly and output raw JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )

        llm_output = json.loads(response.choices[0].message.content)
        new_subject = llm_output.get("new_mutation", "quick update").strip()

        if not new_subject:
            new_subject = "quick update"

        log.info(f"[optimizer] LLM mutation generated: '{new_subject}'")

    except Exception as e:
        log.error(f"[optimizer] LLM call failed: {e}")
        new_subject = "quick update on your project"
        log.info(f"[optimizer] Using fallback: '{new_subject}'")

    # ── 5. Update the asset file for the next batch ────────────────────
    data["current_test"] = new_subject
    if not dry_run:
        with open(SUBJECTS_PATH, "w") as f:
            json.dump(data, f, indent=2)
        log.info(f"[optimizer] Next mutation locked: '{new_subject}'")

    log.info("[optimizer] Cycle complete.")


# ── CLI entry point ────────────────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description="Empire Cold Email Subject Line Optimizer")
    p.add_argument("--dry-run", action="store_true",
                   help="Skip git operations and file writes (print-only)")
    p.add_argument("--force", action="store_true",
                   help="Skip minimum batch size check")
    args = p.parse_args()

    run_optimization_loop(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()
