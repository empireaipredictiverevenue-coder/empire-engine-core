#!/usr/bin/env python3
"""
EMPIRE V49 · NIGHTLY MODEL BENCHMARK + AUTO-SWITCH
==================================================
Runs the synthetic_brain benchmark nightly (N=20), writes the summary to
the `model_benchmark` Supabase table, and — if the active Ollama model has
fallen below 70% success rate for 3 consecutive nights — switches the worker
to a backup model and notifies the operator.

Cron example (see PIPELINE_CRON.md):
  0 3 * * * cd /root/empire-v49 && \
    set -a && . /root/.env && set +a && \
    ./venv/bin/python scripts/nightly_model_benchmark.py >> logs/nightly_benchmark.log 2>&1

Env vars (with defaults):
  OLLAMA_MODEL_PRIMARY   — currently-active model (default: "llama3.2:3b")
  OLLAMA_MODEL_BACKUP    — fallback model to switch to (default: "llama3.1:latest")
  OLLAMA_PORT            — synthetic_brain uvicorn port (default: 8005)
  NTFY_TOPIC             — ntfy.sh topic for operator alerts (optional)
  NTFY_TOKEN             — ntfy.sh bearer token (optional)
  BENCHMARK_N_CALLS      — N calls per night (default: 20)
  SUCCESS_THRESHOLD      — success rate below this triggers a switch (default: 0.70)
  CONSECUTIVE_NIGHTS     — how many nights in a row must be below threshold (default: 3)
  DRY_RUN                — if "1", run the benchmark + DB writes but DO NOT switch

CLI:
  --dry-run     Same as DRY_RUN=1; logs every action, skips the actual switch
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Allow `python3 scripts/nightly_model_benchmark.py` to import from /root/empire-v49
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env")
except ImportError:
    pass  # dotenv optional in CI

# ── CONFIG ──────────────────────────────────────────────────────────
PRIMARY_MODEL = os.environ.get("OLLAMA_MODEL_PRIMARY", "llama3.2:3b")
BACKUP_MODEL = os.environ.get("OLLAMA_MODEL_BACKUP", "llama3.1:latest")
PORT = int(os.environ.get("OLLAMA_PORT", "8005"))
N_CALLS = int(os.environ.get("BENCHMARK_N_CALLS", "20"))
SUCCESS_THRESHOLD = float(os.environ.get("SUCCESS_THRESHOLD", "0.70"))
CONSECUTIVE_NIGHTS = int(os.environ.get("CONSECUTIVE_NIGHTS", "3"))
SYNTHETIC_BRAIN_URL = f"http://127.0.0.1:{PORT}/api/v1/synthetic/run"
API_KEY = os.environ.get("SYNTHETIC_BRAIN_API_KEY", "test-key-please-change-in-production")
OBJECTIVE = "Roofing lead gen ad, +15551234567"
TIMEOUT_S = 45
CSV_DIR = ROOT / "builds" / "nightly"
CSV_DIR.mkdir(parents=True, exist_ok=True)


# ── SUPABASE CLIENT ─────────────────────────────────────────────────
def _sb():
    """Lazy-init Supabase client. Returns None if creds missing (script still
    runs the benchmark + writes CSV, just skips DB persistence)."""
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)


# ── BENCHMARK RUN ───────────────────────────────────────────────────
# Reuse scripts/benchmark_synthetic_brain.py instead of reimplementing the
# call/validate/CSV-write loop. This keeps both scripts in lockstep when
# the benchmark logic changes and matches the "reuse, don't reimplement"
# mandate. The script writes a CSV with the same schema (call, http, time_s,
# json_valid, fields_str, error) which we then parse for the summary stats.
BENCHMARK_SCRIPT = ROOT / "scripts" / "benchmark_synthetic_brain.py"


def run_benchmark(n_calls: int, csv_path: Path) -> dict:
    """Subprocess the existing benchmark script, parse the CSV, return summary.
    Catches subprocess.TimeoutExpired (Ollama hung on a call) and returns a
    minimal 'all failed' summary so the script can still log to model_benchmark
    + record a model_alert instead of crashing with a traceback."""
    print(f"    delegating to {BENCHMARK_SCRIPT.name} (N={n_calls}, csv={csv_path})")
    try:
        result = subprocess.run(
            ["python3", str(BENCHMARK_SCRIPT), str(csv_path), str(n_calls)],
            capture_output=True, text=True, timeout=n_calls * TIMEOUT_S + 60,
        )
        if result.returncode != 0:
            print(f"    [warn] benchmark script exited {result.returncode}: {result.stderr[-300:]}")
    except subprocess.TimeoutExpired as e:
        print(f"    [FAIL] benchmark subprocess timed out after {e.timeout}s — treating as all-failed")
        # Write a minimal CSV so the summary parser doesn't crash on a missing file
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["call", "http", "time_s", "json_valid", "fields_str", "error"])
            for i in range(1, n_calls + 1):
                w.writerow([i, 0, n_calls * TIMEOUT_S, False, False, "subprocess_timeout"])
        return _summarize([])
    rows: list[dict] = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            # Coerce the bool-ish strings from the CSV back into real bools
            row["json_valid"] = row["json_valid"] == "True"
            row["fields_str"] = row["fields_str"] == "True"
            row["http"] = int(row["http"])
            row["time_s"] = float(row["time_s"])
            row["call"] = int(row["call"])
            rows.append(row)
    return _summarize(rows)


def _summarize(rows: list[dict]) -> dict:
    """Compute summary stats from the benchmark rows."""
    n = len(rows)
    successes = [r for r in rows if r["http"] == 200 and r["json_valid"] and r["fields_str"]]
    times = sorted(r["time_s"] for r in successes)
    return {
        "n_calls": n,
        "success_count": len(successes),
        "success_rate": round(len(successes) / n, 3) if n else 0.0,
        "p50_latency_s": round(statistics.median(times), 2) if times else 0.0,
        "p95_latency_s": round(_pct(times, 0.95), 2) if len(times) >= 2 else (times[0] if times else 0.0),
        "max_latency_s": round(max(times, default=0.0), 2),
    }


def _pct(sorted_vals: list[float], p: float) -> float:
    """Return the p-th percentile of a sorted list (linear interp)."""
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


# ── DB PERSISTENCE ──────────────────────────────────────────────────
def save_to_supabase(rows: list[dict], summary: dict, model: str, csv_path: Path, note: str = "") -> None:
    sb = _sb()
    if sb is None:
        print(f"  [skip] supabase creds missing — not writing to model_benchmark")
        return
    try:
        sb.table("model_benchmark").insert({
            "model": model,
            "n_calls": summary["n_calls"],
            "success_count": summary["success_count"],
            "success_rate": summary["success_rate"],
            "p50_latency_s": summary["p50_latency_s"],
            "p95_latency_s": summary["p95_latency_s"],
            "max_latency_s": summary["max_latency_s"],
            "csv_path": str(csv_path),
            "note": note,
        }).execute()
        print(f"  [ok] wrote model_benchmark row for {model} (success_rate={summary['success_rate']})")
    except Exception as e:
        print(f"  [warn] model_benchmark insert failed: {e}")


def recent_success_rates(model: str, n_nights: int) -> list[float]:
    """Return the last n_nights' success_rate for `model`, oldest → newest."""
    sb = _sb()
    if sb is None:
        return []
    try:
        r = sb.table("model_benchmark") \
            .select("success_rate,created_at") \
            .eq("model", model) \
            .order("created_at", desc=True) \
            .limit(n_nights) \
            .execute()
        rows = list(reversed(r.data or []))
        return [float(row["success_rate"]) for row in rows]
    except Exception as e:
        print(f"  [warn] recent_success_rates query failed: {e}")
        return []


def record_alert(from_model: str, to_model: str, reason: str,
                 consecutive_nights: int, success_rates: list[float],
                 switched: bool, ntfy_sent: bool, note: str = "") -> None:
    sb = _sb()
    if sb is None:
        return
    try:
        sb.table("model_alerts").insert({
            "from_model": from_model,
            "to_model": to_model,
            "reason": reason,
            "consecutive_nights": consecutive_nights,
            "success_rates": success_rates,
            "switched": switched,
            "ntfy_sent": ntfy_sent,
            "note": note,
        }).execute()
        print(f"  [ok] wrote model_alerts row (switched={switched})")
    except Exception as e:
        print(f"  [warn] model_alerts insert failed: {e}")


# ── WORKER SWITCH ───────────────────────────────────────────────────
def switch_worker(from_model: str, to_model: str) -> bool:
    """Kill the current worker + start a new one with `to_model`. Returns True on success."""
    if from_model == to_model:
        print(f"  [skip] from_model == to_model ({to_model}) — no switch needed")
        return True

    # 1. Find the current worker PIDs (the children whose cmdline doesn't match pkill -f)
    try:
        out = subprocess.check_output(["lsof", "-ti", f":{PORT}"], text=True)
        pids = [int(p) for p in out.split() if p.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pids = []

    print(f"  [switch] current worker PIDs: {pids}")

    # 2. SIGTERM, wait 3s, SIGKILL stragglers
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(3)
    try:
        out = subprocess.check_output(["lsof", "-ti", f":{PORT}"], text=True)
        remaining = [int(p) for p in out.split() if p.strip()]
        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if remaining:
            time.sleep(2)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # 3. Confirm port is free
    try:
        out = subprocess.check_output(["lsof", "-ti", f":{PORT}"], text=True)
        if out.strip():
            print(f"  [FAIL] port {PORT} still held by PIDs: {out.strip()}")
            return False
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    print(f"  [ok] port {PORT} is free")

    # 4. Start new worker (setsid + disown so it survives our shell exit)
    log_path = ROOT / "synthetic_brain.log"
    cmd = (
        f'setsid bash -c \'SYNTHETIC_BRAIN_API_KEY="{API_KEY}" '
        f'OLLAMA_MODEL="{to_model}" exec uvicorn synthetic_brain:app '
        f'--host 127.0.0.1 --port {PORT} --workers 2\' '
        f'>> {log_path} 2>&1 < /dev/null & disown'
    )
    subprocess.Popen(cmd, shell=True, start_new_session=True)
    time.sleep(7)

    # 5. Verify the new worker is up AND auth is still enforced
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/docs", timeout=5) as resp:
            assert resp.getcode() == 200
        # Auth probe: no key -> 401, right key -> 200.
        # NOTE: urllib.request.urlopen() raises HTTPError on 4xx/5xx by default
        # (it does NOT return them via getcode()), so we catch the exception
        # and use its `.code` attribute. Without this try/except, a correctly-
        # configured worker (returning 401) would crash the whole switch_worker()
        # call instead of returning False.
        req_no_key = urllib.request.Request(
            SYNTHETIC_BRAIN_URL,
            data=b'{"objective":"auth probe"}',
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req_no_key, timeout=10) as resp:
                no_key_code = resp.getcode()
        except urllib.error.HTTPError as e:
            no_key_code = e.code
        if no_key_code != 401:
            print(f"  [FAIL] auth probe failed: no-key returned {no_key_code} (expected 401)")
            return False
        req_with_key = urllib.request.Request(
            SYNTHETIC_BRAIN_URL,
            data=b'{"objective":"auth probe"}',
            method="POST",
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        )
        try:
            with urllib.request.urlopen(req_with_key, timeout=45) as resp:
                with_key_code = resp.getcode()
        except urllib.error.HTTPError as e:
            with_key_code = e.code
        if with_key_code != 200:
            print(f"  [FAIL] auth probe failed: with-key returned {with_key_code} (expected 200)")
            return False
        print(f"  [ok] new worker auth: no-key=401, with-key=200 (correct)")
        return True
    except Exception as e:
        print(f"  [FAIL] new worker did not start cleanly: {e}")
        return False


def get_active_model() -> str | None:
    """Read the active model from the running worker's env (via /proc/<pid>/environ)."""
    try:
        out = subprocess.check_output(["lsof", "-ti", f":{PORT}"], text=True)
        pids = [int(p) for p in out.split() if p.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for pid in pids:
        try:
            with open(f"/proc/{pid}/environ", "rb") as f:
                env = f.read().decode(errors="ignore").split("\x00")
            for kv in env:
                if kv.startswith("OLLAMA_MODEL="):
                    return kv.split("=", 1)[1]
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return None


# ── NTFY ────────────────────────────────────────────────────────────
def send_ntfy(title: str, body: str) -> bool:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print(f"  [skip] NTFY_TOPIC not set — no operator alert sent")
        return False
    try:
        cmd = ["curl", "-sS", "-m", "10",
               "-H", f"Title: {title}",
               "-H", "Priority: high",
               "-H", "Tags: warning"]
        token = os.environ.get("NTFY_TOKEN", "").strip()
        if token:
            cmd += ["-H", f"Authorization: Bearer {token}"]
        cmd += ["-d", body, f"https://ntfy.sh/{topic}"]
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"  [ok] ntfy sent to {topic}")
        return True
    except Exception as e:
        print(f"  [warn] ntfy send failed: {e}")
        return False


# ── MAIN ────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="Run the benchmark + write to DB but DO NOT switch the worker")
    args = parser.parse_args()
    dry_run = args.dry_run or os.environ.get("DRY_RUN") == "1"

    started = datetime.now(timezone.utc)
    print(f"=== Nightly model benchmark starting at {started.isoformat()} ===")
    print(f"  primary={PRIMARY_MODEL}  backup={BACKUP_MODEL}  port={PORT}  n_calls={N_CALLS}  threshold={SUCCESS_THRESHOLD}  dry_run={dry_run}")

    # 0. Detect the actually-active model from the running worker (overrides PRIMARY_MODEL)
    active = get_active_model()
    if active and active != PRIMARY_MODEL:
        print(f"  [info] active model on port {PORT} is {active!r} (not the default {PRIMARY_MODEL!r}) — using that")
        target_model = active
    else:
        target_model = PRIMARY_MODEL

    # 1. Run the benchmark (delegates to scripts/benchmark_synthetic_brain.py)
    print(f"\n  [1/3] Running {N_CALLS}-call benchmark on {target_model}...")
    ts = started.strftime("%Y%m%d_%H%M%S")
    csv_path = CSV_DIR / f"nightly_{target_model.replace(':', '_')}_{ts}.csv"
    summary = run_benchmark(N_CALLS, csv_path)
    rows = []  # not used downstream beyond the CSV path
    print(f"    success: {summary['success_count']}/{summary['n_calls']}  "
          f"p50={summary['p50_latency_s']}s  p95={summary['p95_latency_s']}s  max={summary['max_latency_s']}s")

    # 2. Save summary to model_benchmark
    print(f"    csv: {csv_path}")
    print(f"\n  [2/3] Writing to model_benchmark...")
    save_to_supabase(rows, summary, target_model, csv_path)

    # 4. Check the 3-night threshold
    print(f"\n  [3/3] Checking {CONSECUTIVE_NIGHTS}-night threshold...")
    recent = recent_success_rates(target_model, CONSECUTIVE_NIGHTS)
    print(f"    last {len(recent)} nights' success rates: {recent}")
    if len(recent) < CONSECUTIVE_NIGHTS:
        print(f"    not enough history yet (need {CONSECUTIVE_NIGHTS}, have {len(recent)}) — no switch")
    else:
        below = all(r < SUCCESS_THRESHOLD for r in recent)
        if not below:
            print(f"    rates are not ALL below {SUCCESS_THRESHOLD} — no switch needed")
        else:
            print(f"    !! {CONSECUTIVE_NIGHTS} consecutive nights all below {SUCCESS_THRESHOLD} — TRIGGERING SWITCH !!")
            reason = f"{CONSECUTIVE_NIGHTS} consecutive nights < {SUCCESS_THRESHOLD * 100:.0f}% success"
            switched = False
            ntfy_sent = False
            if dry_run:
                print(f"    [DRY-RUN] would switch {target_model} → {BACKUP_MODEL}")
            else:
                switched = switch_worker(target_model, BACKUP_MODEL)
                if switched:
                    ntfy_sent = send_ntfy(
                        title="EMPIRE synthetic_brain: auto model switch",
                        body=f"Switched {target_model} → {BACKUP_MODEL}\n"
                             f"Reason: {reason}\n"
                             f"Rates: {recent}\n"
                             f"Time: {started.isoformat()}",
                    )
            record_alert(
                from_model=target_model,
                to_model=BACKUP_MODEL,
                reason=reason,
                consecutive_nights=CONSECUTIVE_NIGHTS,
                success_rates=recent,
                switched=switched,
                ntfy_sent=ntfy_sent,
                note=("DRY_RUN — no actual switch" if dry_run else ""),
            )

    duration_s = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
    print(f"\n=== Done in {duration_s}s ===")


if __name__ == "__main__":
    main()
