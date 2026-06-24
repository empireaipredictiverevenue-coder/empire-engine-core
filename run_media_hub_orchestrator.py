#!/usr/bin/env python3
"""PM2 daemon wrapper for media-hub-orchestrator.

Polls media_pipeline_runs for pending jobs and executes them via
MediaOrchestrator.run_pipeline(). Uses atomic UPDATE ... RETURNING
to claim jobs, preventing duplicate execution across instances.

Env vars:
  MEDIA_HUB_POLL_SEC — poll interval in seconds (default 30)
  SUPABASE_URL / SUPABASE_SERVICE_KEY — required
"""
import sys, os, time, asyncio, json, logging

# ── Ensure project root on sys.path ──────────────────────────────────
sys.path.insert(0, "/root/empire-v49")

log = logging.getLogger("media-hub-orchestrator")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

POLL_SEC = int(os.getenv("MEDIA_HUB_POLL_SEC", "30"))
INSTANCE_ID = os.getenv("PM2_INSTANCE", f"orchestrator-{os.getpid()}")
STALE_TIMEOUT_SEC = int(os.getenv("MEDIA_HUB_STALE_TIMEOUT", "3600"))  # 1 hour

# ── Lazy Supabase singleton (created once, reused) ──────────────────
_sb_client = None


def _sb():
    global _sb_client
    if _sb_client is not None:
        return _sb_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _sb_client = create_client(url, key)
        return _sb_client
    except Exception as e:
        log.warning(f"[orchestrator] Supabase init failed: {e}")
        return None


# ── Poll cycle ──────────────────────────────────────────────────────
_cycle_count = 0


async def _poll_once():
    """One orchestrator cycle: claim + execute pending pipeline runs."""
    global _cycle_count
    _cycle_count += 1

    sb = _sb()
    if sb is None:
        if _cycle_count % 20 == 1:
            log.info(f"[orchestrator] heartbeat: Supabase not configured (cycle={_cycle_count})")
        return

    try:
        # ── 1. Reap stale running jobs ──────────────────────────────
        if _cycle_count % 20 == 1 or _cycle_count <= 2:
            try:
                from datetime import datetime, timezone, timedelta
                stale_cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STALE_TIMEOUT_SEC)).isoformat()
                stale_r = sb.table("media_pipeline_runs") \
                    .select("run_id").eq("status", "running") \
                    .lt("claimed_at", stale_cutoff).limit(10).execute()
                if stale_r.data:
                    run_ids = [row["run_id"] for row in stale_r.data]
                    sb.table("media_pipeline_runs").update({
                        "status": "pending",
                        "claimed_by": None,
                        "claimed_at": None,
                    }).in_("run_id", run_ids).execute()
                    log.warning(f"[orchestrator] reset {len(run_ids)} stale running jobs → pending")
            except Exception as e:
                log.warning(f"[orchestrator] stale reaper failed: {e}")

        # ── 2. Atomic claim: UPDATE ... RETURNING ──────────────────
        try:
            claim_r = sb.rpc(
                "claim_pending_pipeline",
                {"p_instance": INSTANCE_ID, "p_limit": 3},
            ).execute()
            claimed = claim_r.data or []
        except Exception:
            # RPC may not exist; fall back to two-step SELECT → UPDATE
            pending_r = sb.table("media_pipeline_runs").select("*") \
                .eq("status", "pending") \
                .order("created_at") \
                .limit(3).execute()
            pending = pending_r.data or []
            claimed = []
            for job in pending:
                try:
                    upd = sb.table("media_pipeline_runs").update({
                        "status": "running",
                        "claimed_by": INSTANCE_ID,
                        "claimed_at": "now()",
                    }).eq("run_id", job["run_id"]).eq("status", "pending").execute()
                    if upd.data:
                        claimed.append(job)
                except Exception as e:
                    log.warning(f"[orchestrator] claim failed for {job.get('run_id','?')}: {e}")

        if not claimed:
            # Heartbeat every 20 idle cycles
            if _cycle_count % 20 == 1:
                log.info(f"[orchestrator] heartbeat: idle (cycle={_cycle_count}, no pending jobs)")
            return

        log.info(f"[orchestrator] claimed {len(claimed)} job(s)")

        # ── 3. Execute each pipeline ────────────────────────────────
        from products.media_automation_hub.orchestrator import get_orchestrator
        orch = get_orchestrator()

        for job in claimed:
            pipeline_name = job.get("pipeline_name", "")
            run_id = job.get("run_id", "")
            ctx = (job.get("context") or {})  # context is the input, result is output

            if not pipeline_name:
                log.warning(f"[orchestrator] skipping job {run_id}: missing pipeline_name")
                continue

            try:
                result = await orch.run_pipeline(pipeline_name, ctx=ctx)
                status = result.get("status", "failed")
                log.info(f"[orchestrator] pipeline={pipeline_name} run={run_id[:8]} "
                         f"status={status} ({len(result.get('stages',[]))} stages)")

                # ── Persist result ─────────────────────────────────
                try:
                    sb.table("media_pipeline_runs").update({
                        "status": status,
                        "result": result.get("output") or result,
                        "error": result.get("error", ""),
                        "finished_at": result.get("finished_at"),
                        "duration_ms": result.get("duration_ms", 0),
                    }).eq("run_id", run_id).execute()
                except Exception as e:
                    log.warning(f"[orchestrator] result persist failed for {run_id}: {e}")
            except Exception as e:
                log.exception(f"[orchestrator] pipeline {pipeline_name} crashed: {e}")
                try:
                    from datetime import datetime as _dt, timezone as _tz
                    sb.table("media_pipeline_runs").update({
                        "status": "failed",
                        "error": str(e)[:500],
                        "finished_at": _dt.now(_tz.utc).isoformat(),
                    }).eq("run_id", run_id).execute()
                except Exception as e2:
                    log.warning(f"[orchestrator] error persist failed for {run_id}: {e2}")

    except Exception as e:
        log.exception(f"[orchestrator] poll cycle failed: {e}")


async def _main_loop():
    """Continuous polling loop."""
    log.info(f"[orchestrator] started (instance={INSTANCE_ID}, poll={POLL_SEC}s, "
             f"stale_timeout={STALE_TIMEOUT_SEC}s)")
    while True:
        try:
            await _poll_once()
        except Exception:
            log.exception("[orchestrator] _poll_once crashed — continuing")
        await asyncio.sleep(POLL_SEC)


if __name__ == "__main__":
    asyncio.run(_main_loop())
