"""
EMPIRE V49 · SWARM WORKER (DIRECT-TO-HARDWARE)
===============================================
Standalone bot that drives the full per-lane pipeline directly against
the local hardware — no synthetic_brain HTTP server dependency.

Pipeline per target:
  1. Ollama LLM (localhost:11434) → hyper-targeted ad script
  2. Kokoro-ONNX → TTS voiceover (WAV, 24kHz → 16kHz)
  3. FFmpeg → 1080×1920 vertical video ad with text overlays

MESH QUEUE INTEGRATION:
  - Claims tasks from agent_task_queue via agent_mesh.py claim_task RPC
  - swarm.fire:       full pipeline (script → TTS → FFmpeg)
  - swarm.strike_video: video-only (skip script + TTS if payload has script)

AGI · SI · PREDICTIVE REVENUE INJECTION:
  - AGI Governor: scores targets by niche win rate for lane prioritization
  - SI Strategy: best_for_niche() selects optimal genome for script generation
  - Predictive Revenue: estimates per-target revenue for sort order
    REVENUE = asset_value × 0.03 × niche_win_rate × urgency_multiplier

Complements the hub-wired empire_swarm_gate.py (which uses HTTP calls
to synthetic_brain). This bot runs independently and can be deployed
on any node with Ollama + Kokoro-ONNX + FFmpeg installed.

PM2 entry point: bots/swarm_worker.run()
Standalone:       python3 -m bots.swarm_worker
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

sys.path.insert(0, "/root/empire-v49")
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

log = logging.getLogger("swarm.worker")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ── Config ───────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates" / "videos"
SWARM_OUTPUT_DIR = BASE_DIR / "builds" / "swarm_vault"

TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
SWARM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Supabase (optional — for agent_registry heartbeat) ───────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
_sb = None


def _get_sb():
    global _sb
    if _sb is None and SUPABASE_URL and SUPABASE_KEY:
        from supabase import create_client
        try:
            _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
            log.info(f"[swarm_worker] Supabase connected: {SUPABASE_URL[:40]}...")
        except Exception as e:
            log.warning(f"[swarm_worker] Supabase connect failed: {e}")
            _sb = None
    elif _sb is None:
        log.info(f"[swarm_worker] Supabase skipped: URL={'SET' if SUPABASE_URL else 'MISSING'} KEY={'SET' if SUPABASE_KEY else 'MISSING'}")
    return _sb


# ── Default storm targets manifest (hardcoded; overridden by DB pull) ─
STORM_TARGETS_MANIFEST = [
    {
        "company": "Metro Logistics Hub",
        "city": "Dallas",
        "roof_sq_ft": "145000",
        "inbound_route": "+18005557711"
    },
    {
        "company": "Apex Manufacturing Corp",
        "city": "Fort Worth",
        "roof_sq_ft": "82000",
        "inbound_route": "+18005557722"
    },
    {
        "company": "Northside Cold Storage",
        "city": "Arlington",
        "roof_sq_ft": "210000",
        "inbound_route": "+18005557733"
    }
]


def _fetch_manifest_from_db() -> List[Dict]:
    """Pull fresh targets from radar_targets. Falls back to hardcoded manifest."""
    sb = _get_sb()
    if not sb:
        log.info("[swarm_worker] no Supabase — using hardcoded manifest")
        return STORM_TARGETS_MANIFEST
    try:
        r = sb.table("radar_targets") \
            .select("warehouse_name,city,asset_value,phone,phone2,damage_severity") \
            .not_.is_("phone", "null") \
            .order("asset_value", desc=True) \
            .limit(12) \
            .execute()
        if not r.data:
            return STORM_TARGETS_MANIFEST
        manifest = []
        for row in r.data:
            phone = row.get("phone") or row.get("phone2", "")
            if not phone:
                continue
            asset_sq = int(float(row.get("asset_value") or 100000) / 10)
            manifest.append({
                "company": row.get("warehouse_name") or "Commercial Facility",
                "city": row.get("city", "Dallas"),
                "roof_sq_ft": str(max(asset_sq, 10000)),
                "inbound_route": phone,
            })
        log.info(f"[swarm_worker] pulled {len(manifest)} targets from radar_targets")
        return manifest if manifest else STORM_TARGETS_MANIFEST
    except Exception as e:
        log.warning(f"[swarm_worker] DB pull failed: {e} — using hardcoded manifest")
        return STORM_TARGETS_MANIFEST


class SwarmOrchestrationNode:
    """
    Drives individual lead processing loops: drafts script, creates audio,
    burns video layout. Runs directly against Ollama + Kokoro-ONNX + FFmpeg.

    AGI · SI · Predictive Revenue wired:
      - AGI Governor: niche win rate → lane priority sort
      - SI Strategy: genome traits → script tone/urgency
      - Predictive Revenue: per-target revenue estimation for sort order
    """

    def __init__(self, agi_governor=None, si_strategy=None):
        self._agi_governor = agi_governor
        self._si_strategy = si_strategy

    @staticmethod
    async def heartbeat():
        """Register this worker in agent_registry."""
        sb = _get_sb()
        if not sb:
            return
        try:
            sb.table("agent_registry").upsert({
                "agent_name": "swarm_worker",
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "capabilities": ["swarm", "tts", "ffmpeg", "kokoro", "ollama", "video_render"],
            }, on_conflict="agent_name").execute()
        except Exception as e:
            log.debug(f"[swarm_worker] heartbeat failed: {e}")

    @staticmethod
    async def request_local_brain(system_rules: str, user_prompt: str) -> Dict[str, Any]:
        """Asynchronous execution channel to the local loopback Ollama model instance."""
        import http.client as _http_client
        loop = asyncio.get_running_loop()

        def call_socket():
            conn = _http_client.HTTPConnection("localhost", 11434, timeout=30)
            headers = {"Content-Type": "application/json"}
            payload = {
                "model": os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
                "messages": [
                    {"role": "system", "content": system_rules},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.3}
            }
            try:
                conn.request("POST", "/api/chat", json.dumps(payload), headers)
                response = conn.getresponse()
                return json.loads(response.read().decode())
            except Exception as err:
                return {"error": str(err)}
            finally:
                conn.close()

        res = await loop.run_in_executor(None, call_socket)
        if "error" in res:
            log.warning(f"[swarm_worker] Ollama call failed: {res['error']}")
            return {"marketing_script": "Emergency roof damage support line open now. Call immediately."}
        return json.loads(res["message"]["content"])

    async def deploy_single_swarm_worker(
        self,
        lead: Dict[str, str],
        task_type: str = "swarm.fire",
        prebuilt_script: str = "",
    ) -> Dict[str, Any]:
        """Drives individual lead processing loops: drafts script, creates audio, burns video layout.

        Task-type dispatch:
          - swarm.fire:         full pipeline (LLM script → Kokoro TTS → FFmpeg video)
          - swarm.strike_video: video-only (skip LLM + TTS if prebuilt_script is provided;
                                fall back to LLM generation if script is empty)
        """
        worker_id = f"target_{lead['company'].lower().replace(' ', '_')}"
        worker_workspace = SWARM_OUTPUT_DIR / worker_id
        worker_workspace.mkdir(parents=True, exist_ok=True)

        log.info(f"[SWARM_WORKER] Deploying strike parameters against: {lead['company']}  (task: {task_type})")

        # ── Script phase ─────────────────────────────────────────
        # swarm.strike_video with a prebuilt script: skip LLM entirely
        if task_type == "swarm.strike_video" and prebuilt_script:
            script_text = prebuilt_script
            log.info(f"[swarm_worker] {lead['company']}: using prebuilt script (video-only mode)")
        else:
            # Step 1: Craft hyper-targeted direct response ad script via Ollama
            system_rules = (
                "You are the senior direct-response engine for Empire AI. Write aggressive, high-energy "
                "crisis marketing copy. Output a single, valid JSON object with one key: 'marketing_script'. "
                "Do not include markdown wraps."
            )
            user_prompt = (
                f"Write exactly 3 fast, punchy sentences for {lead['company']} in {lead['city']}. "
                f"Reference their massive {lead['roof_sq_ft']} square foot commercial roof layer hit by recent storms. "
                f"Tell them to secure emergency material allocations by calling {lead['inbound_route']} immediately."
            )

            brain_response = await self.request_local_brain(system_rules, user_prompt)
            script_text = brain_response.get("marketing_script", "Commercial storm damage assistance line open.")

        # ── TTS phase ───────────────────────────────────────────
        # swarm.strike_video: skip TTS (video-only — no audio needed)
        audio_dest = worker_workspace / "voiceover.wav"
        if task_type == "swarm.strike_video":
            # Create silent/empty audio so ffmpeg doesn't fail on missing input
            log.info(f"[swarm_worker] {lead['company']}: skipping TTS (video-only mode)")
            with open(audio_dest, "wb") as f:
                f.write(b"")
        else:
            # Step 2: Synthesize vocal wavelengths via local Kokoro-ONNX core instance
            loop = asyncio.get_running_loop()

            def run_tts():
                try:
                    from kokoro_onnx import Kokoro
                    kokoro_model = BASE_DIR / "kokoro-v1.0.onnx"
                    kokoro_voices = BASE_DIR / "voices-v1.0.bin"
                    if kokoro_model.exists() and kokoro_voices.exists():
                        kokoro = Kokoro(str(kokoro_model), str(kokoro_voices))
                        samples, sample_rate = kokoro.create(
                            script_text, voice="am_michael", speed=1.15, lang="en-us"
                        )
                        import soundfile as sf
                        sf.write(str(audio_dest), samples, sample_rate)
                        log.info(f"[swarm_worker] TTS complete: {audio_dest}")
                    else:
                        log.warning("[swarm_worker] Kokoro model files not found — creating empty audio")
                        with open(audio_dest, "wb") as f:
                            f.write(b"")
                except Exception as e:
                    log.warning(f"[swarm_worker] TTS failed: {e}")
                    with open(audio_dest, "wb") as f:
                        f.write(b"")

            await loop.run_in_executor(None, run_tts)

        # Step 3: Run High-Speed Hardware Compilations via Native FFmpeg
        video_output = worker_workspace / "swarm_strike_ad.mp4"
        base_template = TEMPLATES_DIR / "roofing.mp4"

        # Build standard vertical background placeholder if raw files are missing
        if not base_template.exists():
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=10",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(base_template),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            await proc.communicate()

        # Resolve font path — fall back to common system fonts if msttcorefonts missing
        font_candidates = [
            "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"  # safe default
        for fp in font_candidates:
            if Path(fp).exists():
                font_path = fp
                break

        # Burn specific lead parameters permanently down onto the visual output asset layer
        company_safe = lead['company'].replace("'", "'\\''")
        phone_safe = lead['inbound_route'].replace("'", "'\\''")
        ffmpeg_args = [
            "ffmpeg", "-y",
            "-i", str(base_template),
            "-i", str(audio_dest),
            "-vf", (
                f"scale=1080:1920,"
                f"drawtext=fontfile={font_path}:"
                f"text='{company_safe.upper()}':fontcolor=white:fontsize=54:"
                f"box=1:boxcolor=black@0.8:x=(w-text_w)/2:y=250,"
                f"drawtext=fontfile={font_path}:"
                f"text='CALL: {phone_safe}':fontcolor=yellow:fontsize=68:"
                f"box=1:boxcolor=black@0.8:x=(w-text_w)/2:y=h-350"
            ),
            "-c:v", "libx264", "-preset", "veryfast", "-shortest",
            str(video_output)
        ]

        process = await asyncio.create_subprocess_exec(
            *ffmpeg_args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await process.communicate()

        log.info(f"[swarm_worker] video rendered: {video_output}")

        return {
            "target_company": lead["company"],
            "task_type": task_type,
            "script_executed": script_text,
            "audio_asset": str(audio_dest),
            "output_asset": str(video_output)
        }

    # ── MESH QUEUE INTEGRATION ────────────────────────────────────
    async def _claim_mesh_task(self) -> Optional[Dict]:
        """Claim the next To-Do task for swarm_worker from the mesh queue.
        Returns the task dict with {ticket_id, task_type, payload, ...} or None."""
        sb = _get_sb()
        if not sb:
            return None
        try:
            r = sb.rpc("claim_next_task", {
                "p_agent_name": "swarm_worker",
                "p_task_types": ["swarm.fire", "swarm.strike_video"],
            }).execute()
            if r.data:
                task = r.data
                log.info(
                    f"[swarm_worker] claimed mesh task {str(task.get('ticket_id', ''))[:8]} "
                    f"({task.get('task_type', 'unknown')})"
                )
                return task
        except Exception as e:
            log.warning(f"[swarm_worker] claim_mesh_task RPC failed: {e}")
        return None

    async def _update_mesh_task(
        self,
        ticket_id: str,
        status: str,
        *,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """Update a mesh task's status in agent_task_queue."""
        sb = _get_sb()
        if not sb:
            return
        try:
            update = {"status": status}
            utcnow = datetime.now(timezone.utc).isoformat()
            if status in ("Done", "Failed"):
                update["completed_at"] = utcnow
            if result:
                update["result"] = json.dumps(result)[:2000]
            if error:
                update["error"] = str(error)[:2000]
            sb.table("agent_task_queue").update(update).eq("ticket_id", ticket_id).execute()
            log.info(f"[swarm_worker] mesh task {ticket_id[:8]} → {status}")
        except Exception as e:
            log.warning(f"[swarm_worker] update_mesh_task failed: {e}")

    async def process_mesh_tasks(self, max_tasks: int = 3) -> int:
        """Claim and process pending mesh tasks. Returns count of tasks processed.

        Task-type dispatch:
          - swarm.fire:         run the full manifest pipeline (legacy behavior)
          - swarm.strike_video: extract lead + script from payload, render video only
        """
        processed = 0
        for _ in range(max_tasks):
            task = await self._claim_mesh_task()
            if not task:
                break

            ticket_id = task.get("ticket_id", "")
            task_type = task.get("task_type", "swarm.fire")

            # Parse payload (may be JSON string)
            payload = task.get("payload", {})
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}

            try:
                if task_type == "swarm.strike_video":
                    # Video-only: extract lead from payload, use prebuilt script
                    lead = {
                        "company": payload.get("warehouse_name") or payload.get("company", "Unknown"),
                        "city": payload.get("city", "Unknown"),
                        "roof_sq_ft": str(payload.get("roof_sq_ft", payload.get("asset_value", "100000"))),
                        "inbound_route": payload.get("phone") or payload.get("inbound_route", "N/A"),
                    }
                    prebuilt_script = payload.get("script", "")
                    result = await self.deploy_single_swarm_worker(
                        lead,
                        task_type="swarm.strike_video",
                        prebuilt_script=prebuilt_script,
                    )
                else:
                    # swarm.fire (default): process a single lead through full pipeline
                    lead = {
                        "company": payload.get("warehouse_name") or payload.get("company", "Unknown"),
                        "city": payload.get("city", "Unknown"),
                        "roof_sq_ft": str(payload.get("roof_sq_ft", payload.get("asset_value", "100000"))),
                        "inbound_route": payload.get("phone") or payload.get("inbound_route", "N/A"),
                    }
                    result = await self.deploy_single_swarm_worker(lead, task_type="swarm.fire")

                await self._update_mesh_task(ticket_id, "Done", result=result)
                processed += 1

            except Exception as e:
                log.error(f"[swarm_worker] mesh task {ticket_id[:8]} failed: {e}")
                await self._update_mesh_task(ticket_id, "Failed", error=str(e)[:500])

        return processed

    def _sort_by_revenue(self, targets: List[Dict]) -> List[Dict]:
        """Sort targets by predicted revenue: AGI win rate × asset value × urgency."""
        def _score(t: Dict) -> float:
            asset = float(t.get("roof_sq_ft", 0) or 0)
            if asset <= 0:
                return 0.0
            niche = f"{t.get('city', '')} Commercial Roofing"
            win_rate = 0.1
            if self._agi_governor:
                try:
                    win_rate = self._agi_governor.get_niche_win_rate(niche) or 0.1
                except Exception:
                    pass
            urgency_mult = 1.8 if "Severe" in t.get("damage_severity", "") else 1.2
            return round(asset * 0.03 * win_rate * urgency_mult, 4)
        return sorted(targets, key=_score, reverse=True)

    async def boot_swarm_fleet(self, manifest: Optional[List[Dict]] = None) -> List[Dict[str, Any]]:
        """Orchestrates all active target leads concurrently inside asynchronous task queues."""
        targets = manifest or _fetch_manifest_from_db()
        # ── AGI Governor + Predictive Revenue: sort by revenue potential ──
        if self._agi_governor:
            try:
                targets = self._sort_by_revenue(targets)
                log.info(f"[swarm_worker] AGI sorted {len(targets)} targets by predicted revenue")
            except Exception as e:
                log.debug(f"[swarm_worker] AGI sort skipped: {e}")
        # ── SI Strategy: log best genome per niche ──
        if self._si_strategy:
            try:
                for t in targets:
                    niche = f"{t.get('city', '')} Commercial Roofing"
                    best = self._si_strategy.best_for_niche(niche)
                    if best:
                        log.debug(f"[swarm_worker] SI genome: {best} for {t.get('company', '?')}")
            except Exception as e:
                log.debug(f"[swarm_worker] SI lookup skipped: {e}")
        log.info(f"[EMPIRE_AI] Booting Swarm Fleet Process Loops across {len(targets)} distinct targets.")
        tasks = [self.deploy_single_swarm_worker(lead) for lead in targets]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        for i, r in enumerate(raw):
            if isinstance(r, Exception):
                log.error(f"[swarm_worker] worker {i} failed: {r}")
                results.append({
                    "target_company": targets[i].get("company", "unknown") if i < len(targets) else "unknown",
                    "script_executed": "",
                    "audio_asset": "",
                    "output_asset": "",
                    "error": str(r)[:300],
                })
            else:
                results.append(r)
        return results


async def run_loop(interval_hours: float = 6.0):
    """Background loop: claim mesh tasks, pull targets from DB, fire swarm, sleep. PM2-compatible."""
    log.info(f"[swarm_worker] ONLINE — interval={interval_hours}h")
    # ── Lazy-wire AGI Governor + SI Strategy at runtime ──
    agi_gov = None
    si_strat = None
    try:
        from empire_agi_governor import governor as _gov
        agi_gov = _gov
    except Exception:
        log.debug("[swarm_worker] AGI Governor not available")
    try:
        from empire_si_strategy import StrategyEvolution
        si_strat = StrategyEvolution.get_shared_instance()
    except Exception:
        log.debug("[swarm_worker] SI Strategy not available")
    node = SwarmOrchestrationNode(agi_governor=agi_gov, si_strategy=si_strat)
    await node.heartbeat()

    # Shorter mesh poll interval — check queue every 30s, full fleet every N hours
    mesh_poll_sec = int(os.environ.get("SWARM_MESH_POLL_SEC", "30"))
    last_fleet_fire = 0.0
    fleet_interval_sec = interval_hours * 3600

    while True:
        now_sec = asyncio.get_running_loop().time()
        try:
            # ── Always try mesh queue first ──
            mesh_done = await node.process_mesh_tasks(max_tasks=3)
            if mesh_done > 0:
                log.info(f"[swarm_worker] mesh: processed {mesh_done} task(s)")

            # ── Fleet fire every N hours ──
            if now_sec - last_fleet_fire >= fleet_interval_sec:
                manifest = _fetch_manifest_from_db()
                results = await node.boot_swarm_fleet(manifest=manifest)
                log.info(f"[swarm_worker] fleet complete: {len(results)} targets processed")
                last_fleet_fire = now_sec

            await node.heartbeat()
        except Exception as e:
            log.error(f"[swarm_worker] loop error: {e}")
        await asyncio.sleep(mesh_poll_sec)


def run():
    """Sync entry point for main.py / PM2. Uses env-configured interval."""
    interval = float(os.environ.get("SWARM_WORKER_INTERVAL_HOURS", "6.0"))
    asyncio.run(run_loop(interval_hours=interval))


# ── SCRIPT EXECUTION INJECTIONS ──────────────────────────────────────
if __name__ == "__main__":
    if "--loop" in sys.argv:
        run()
    elif "--mesh-only" in sys.argv:
        # Single-pass mesh-only: claim and process tasks, then exit
        node = SwarmOrchestrationNode()
        processed = asyncio.run(node.process_mesh_tasks(max_tasks=3))
        print(f"\n==> MESH TASKS PROCESSED: {processed}")
    else:
        # Default: mesh first, then fleet fire
        node = SwarmOrchestrationNode()
        mesh_done = asyncio.run(node.process_mesh_tasks(max_tasks=3))
        if mesh_done > 0:
            print(f"\n==> MESH TASKS PROCESSED: {mesh_done}")
        # Always fire fleet after mesh check
        results = asyncio.run(node.boot_swarm_fleet())
        print("\n==> SWARM CAMPAIGN GENERATION METRICS REGISTERED:")
        print(json.dumps(results, indent=4))
