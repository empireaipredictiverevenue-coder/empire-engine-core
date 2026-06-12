"""
EMPIRE V49 · GOD MODE SWARM GATE
=================================
Processes data array and sends parallel asset requests.

Architecture:
  StrikePackages[] ──► ┌───────────────┐
                       │ Swarm Gate     │
                       │ (N parallel    │
                       │  lanes)        │
                       └───┬───┬───┬────┘
                           │   │   │
       ┌───────────────────┼───┼───┼────────────────────┐
       ▼                   ▼   ▼   ▼                    ▼
  [Target Lead 01]  [Target Lead 02]  [Target Lead 03]  ...
  - Script Engine   - Script Engine   - Script Engine
  - Kokoro Audio    - Kokoro Audio    - Kokoro Audio
  - FFmpeg Render   - FFmpeg Render   - FFmpeg Render
   1080x1920         1080x1920         1080x1920

Each lane:
  1. Local Script Engine   → BrainDecider scores + builds call script
  2. Kokoro Audio Match    → synthetic_brain TTS voiceover (WAV)
  3. FFmpeg 1080x1920      → synthetic_brain /api/v1/synthetic/run (full video ad)
       Render                 or local ffmpeg assembly if synthetic_brain is down

Dependencies (injected):
  - get_db          → Supabase client
  - brain_decider   → BrainDecider instance
  - synthetic_brain_url / _key → for TTS + video render
  - si_strategy     → StrategyEvolution for per-niche genome
  - pain_points     → PainPointLibrary for script hooks
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field, asdict

import httpx

sys.path.insert(0, "/root/empire-v49")

log = logging.getLogger("empire.swarm")

# ── Lane concurrency ───────────────────────────────────────────
DEFAULT_LANE_COUNT = int(os.environ.get("SWARM_LANE_COUNT", "3"))
DEFAULT_LANE_TIMEOUT = int(os.environ.get("SWARM_LANE_TIMEOUT_SEC", "120"))


@dataclass
class SwarmJob:
    """Result of one Swarm Gate lane — a single target processed through the pipeline."""
    target_id: str
    warehouse_name: str
    metro: str
    niche: str
    risk_level: str

    # Script Engine
    script: str = ""
    brain_decision: str = ""
    brain_confidence: float = 0.0
    brain_reasoning: str = ""
    strategy: str = ""

    # Kokoro Audio Match
    audio_path: str = ""
    audio_duration_s: float = 0.0
    voice_profile: str = "am_michael"

    # FFmpeg Render
    video_path: str = ""
    video_status: str = ""
    render_duration_s: float = 0.0

    # Meta
    status: str = "queued"  # queued → scripting → audio → rendering → complete | failed
    error: str = ""
    started_at: str = ""
    completed_at: str = ""


class GodModeSwarmGate:
    """
    Parallel video-ad pipeline for storm-strike warehouse targets.

    Lifecycle:
      swarm.fire(strike_packages) → N parallel lanes → SwarmJob[] results
    """

    def __init__(
        self,
        *,
        get_db: Optional[Callable] = None,
        brain_decider: Any = None,
        si_strategy: Any = None,
        pain_points: Any = None,
        synthetic_brain_url: str = "",
        synthetic_brain_key: str = "",
        lane_count: int = DEFAULT_LANE_COUNT,
        lane_timeout: int = DEFAULT_LANE_TIMEOUT,
    ):
        self.get_db = get_db
        self.brain_decider = brain_decider
        self.si_strategy = si_strategy
        self.pain_points = pain_points
        self.synthetic_brain_url = synthetic_brain_url or os.environ.get("SYNTHETIC_BRAIN_URL", "http://127.0.0.1:8005")
        self.synthetic_brain_key = synthetic_brain_key or os.environ.get("SYNTHETIC_BRAIN_API_KEY", "")
        self.lane_count = lane_count
        self.lane_timeout = lane_timeout

        self.stats = {
            "total_fires": 0,
            "total_lanes_processed": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_videos_rendered": 0,
            "last_fire_at": None,
        }

    # ── PUBLIC: FIRE THE SWARM ──────────────────────────────────
    async def fire(
        self,
        packages: List[Any],
        auto_script: bool = True,
        auto_audio: bool = True,
        auto_render: bool = True,
    ) -> List[SwarmJob]:
        """
        Fire all strike packages through parallel lanes.

        Args:
            packages: List of StrikePackage objects or dicts with same shape
            auto_script: Run Script Engine per lane
            auto_audio:  Run Kokoro Audio Match per lane
            auto_render: Run FFmpeg 1080x1920 Render per lane

        Returns:
            List of SwarmJob results (one per lane).
        """
        self.stats["total_fires"] += 1
        self.stats["last_fire_at"] = datetime.now(timezone.utc).isoformat()

        # Normalize packages to dicts
        pkg_dicts = []
        for p in packages:
            if hasattr(p, "__dataclass_fields__"):
                pkg_dicts.append(asdict(p))
            elif isinstance(p, dict):
                pkg_dicts.append(p)
            else:
                log.warning(f"[swarm] unknown package type: {type(p)}")

        if not pkg_dicts:
            log.info("[swarm] fire: no packages to process")
            return []

        sem = asyncio.Semaphore(self.lane_count)
        log.info(f"[swarm] fire: {len(pkg_dicts)} packages, {self.lane_count} lanes")

        async def _lane(pkg: dict) -> SwarmJob:
            async with sem:
                return await self._process_lane(pkg, auto_script, auto_audio, auto_render)

        jobs = await asyncio.gather(*[_lane(p) for p in pkg_dicts], return_exceptions=True)

        results: List[SwarmJob] = []
        for j in jobs:
            if isinstance(j, Exception):
                log.error(f"[swarm] lane exception: {j}")
                results.append(SwarmJob(
                    target_id="error",
                    warehouse_name="exception",
                    metro="unknown",
                    niche="unknown",
                    risk_level="unknown",
                    status="failed",
                    error=str(j)[:500],
                ))
                self.stats["total_failed"] += 1
            else:
                results.append(j)
                self.stats["total_lanes_processed"] += 1
                if j.status == "complete":
                    self.stats["total_completed"] += 1
                else:
                    self.stats["total_failed"] += 1
                if j.video_path:
                    self.stats["total_videos_rendered"] += 1

        # Log to DB
        self._log_swarm_fire(pkg_dicts, results)

        log.info(
            f"[swarm] fire complete: {len(results)} jobs, "
            f"{self.stats['total_completed']} succeeded, {self.stats['total_failed']} failed "
            f"(cumulative)"
        )
        return results

    # ── PER-LANE PROCESSING ─────────────────────────────────────
    async def _process_lane(
        self, pkg: dict,
        auto_script: bool, auto_audio: bool, auto_render: bool,
    ) -> SwarmJob:
        """Single lane: Script → Audio → Render."""
        target_id = pkg.get("target_id", "")
        name = pkg.get("warehouse_name", "Unknown")
        metro = pkg.get("metro", "")
        niche = pkg.get("niche", "Storm Damage Restoration")
        risk = pkg.get("risk_level", "Slight")

        job = SwarmJob(
            target_id=target_id,
            warehouse_name=name,
            metro=metro,
            niche=niche,
            risk_level=risk,
            status="queued",
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        try:
            # ── Phase 1: Local Script Engine ─────────────────────
            if auto_script:
                job.status = "scripting"
                await self._run_script_engine(pkg, job)

            # ── Phase 2: Kokoro Audio Match ──────────────────────
            if auto_audio and job.script and job.brain_decision == "GO":
                job.status = "audio"
                await self._run_kokoro_audio(pkg, job)

            # ── Phase 3: FFmpeg 1080x1920 Render ─────────────────
            if auto_render and job.script:
                job.status = "rendering"
                await self._run_ffmpeg_render(pkg, job)

            job.status = "complete"
            job.completed_at = datetime.now(timezone.utc).isoformat()

        except asyncio.TimeoutError:
            job.status = "failed"
            job.error = f"lane timeout after {self.lane_timeout}s"
        except Exception as e:
            job.status = "failed"
            job.error = str(e)[:500]
            log.error(f"[swarm] lane failed for {name} ({target_id}): {e}")

        return job

    # ── PHASE 1: LOCAL SCRIPT ENGINE ────────────────────────────
    async def _run_script_engine(self, pkg: dict, job: SwarmJob):
        """Score the lead via BrainDecider, select SI strategy, build the call script."""
        city = pkg.get("city", "")
        state = pkg.get("state", "")
        location = f"{city}, {state}" if state else (city or job.metro)
        name = job.warehouse_name
        niche = job.niche
        phone = pkg.get("phone", "")
        address = pkg.get("address", "")

        # BrainDecider scoring
        if self.brain_decider:
            try:
                alert_ctx = {
                    "event": pkg.get("storm_event", "Storm Activity"),
                    "severity": pkg.get("storm_severity", "Severe"),
                    "urgency": pkg.get("storm_urgency", "Immediate"),
                    "area": location,
                }
                decision = await asyncio.wait_for(
                    self.brain_decider.decide(
                        target={
                            "warehouse_name": name,
                            "address": address,
                            "city": city,
                            "phone": phone,
                            "email": pkg.get("email", ""),
                            "website": "",
                            "raw_tags": {"types": ["commercial", "industrial"]},
                        },
                        alert_summary=alert_ctx,
                    ),
                    timeout=30,
                )
                job.brain_decision = (decision.get("decision") or "NO_GO").upper()
                try:
                    job.brain_confidence = max(0.0, min(1.0, float(decision.get("confidence", 0))))
                except (TypeError, ValueError):
                    job.brain_confidence = 0.5
                job.brain_reasoning = (decision.get("reasoning") or "")[:300]
            except asyncio.TimeoutError:
                decision = {"decision": "GO", "confidence": 0.5, "reasoning": "brain timeout (30s)"}
                job.brain_decision = "GO"
                job.brain_confidence = 0.5
            except Exception as e:
                log.debug(f"[swarm] brain.decide failed for {name}: {e}")
                decision = {"decision": "GO", "confidence": 0.5, "reasoning": "brain unavailable"}
                job.brain_decision = "GO"
                job.brain_confidence = 0.5
        else:
            decision = {"decision": "GO", "confidence": 0.5, "reasoning": "no brain wired"}
            job.brain_decision = "GO"
            job.brain_confidence = 0.5

        # Strategy selection
        if self.si_strategy and job.brain_decision == "GO":
            try:
                job.strategy = self.si_strategy.best_for_niche(niche) or "AGGRESSIVE_STRIKE"
            except Exception:
                job.strategy = "AGGRESSIVE_STRIKE"
        else:
            job.strategy = "AGGRESSIVE_STRIKE"

        # Build script based on strategy
        asset_val = float(pkg.get("asset_value") or 0)
        risk = job.risk_level

        if job.strategy == "AGGRESSIVE_STRIKE":
            opener = f"urgent {risk} storm alert"
            tone = "We have crews standing by and can dispatch immediately."
        elif job.strategy == "RECALL_SNIPER":
            opener = "targeted commercial property assessment"
            tone = "Our predictive models identified your facility as high-priority for storm response."
        elif job.strategy == "FINANCIAL_STRIKE":
            opener = "verified insurance dispatch"
            tone = "We specialize in maximizing commercial claims — our average settlement is 3x higher."
        else:
            opener = f"{risk} storm response program"
            tone = "A specialist is available to assess your property at no upfront cost."

        if job.brain_confidence >= 0.85:
            urgency = "This is time-sensitive — storm windows close fast."
        elif job.brain_confidence >= 0.7:
            urgency = "Call now to secure priority assessment."
        else:
            urgency = "Contact us to learn more."

        script = (
            f"Hello, this is Empire AI Predictive Cloud with an {opener}. "
            f"Our weather intelligence detected severe storm activity near {location}. "
        )

        if asset_val > 0:
            fee = round(asset_val * 0.01)
            script += (
                f"We've identified {name} with an estimated asset value of ${asset_val:,.0f}. "
                f"Our success-only fee on a settled claim would be approximately ${fee:,.0f}. "
            )

        script += (
            f"This matches our {job.strategy.replace('_', ' ').title()} program. "
            f"{tone} {urgency}"
        )

        # Inject pain points if wired
        if self.pain_points and niche:
            try:
                script = self.pain_points.inject_pain_points(niche, script)
            except Exception:
                pass

        job.script = script[:1000]

    # ── PHASE 2: KOKORO AUDIO MATCH ─────────────────────────────
    async def _run_kokoro_audio(self, pkg: dict, job: SwarmJob):
        """Generate voiceover WAV via synthetic_brain Kokoro TTS."""
        if not self.synthetic_brain_key:
            log.debug("[swarm] no SYNTHETIC_BRAIN_API_KEY — skipping audio")
            job.audio_path = "skipped (no API key)"
            return

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{self.synthetic_brain_url}/api/v1/synthetic/synthesize",
                    json={
                        "script": job.script,
                        "voice": job.voice_profile,
                        "speed": 1.1,
                    },
                    headers={"X-API-Key": self.synthetic_brain_key},
                )
                if r.status_code == 200:
                    data = r.json()
                    job.audio_path = data.get("audio_path", "")
                    job.audio_duration_s = float(data.get("duration_s", 0))
                    log.debug(f"[swarm] audio synthesized for {job.warehouse_name}: {job.audio_duration_s:.1f}s")
                else:
                    log.warning(f"[swarm] synthesize failed ({r.status_code}): {r.text[:200]}")
                    job.audio_path = f"synthesize_failed_{r.status_code}"
        except Exception as e:
            log.warning(f"[swarm] Kokoro audio error for {job.warehouse_name}: {e}")
            job.audio_path = f"error: {str(e)[:100]}"

    # ── PHASE 3: FFMPEG 1080x1920 RENDER ────────────────────────
    async def _run_ffmpeg_render(self, pkg: dict, job: SwarmJob):
        """Render the full 1080x1920 vertical video ad via synthetic_brain /api/v1/synthetic/run."""
        if not self.synthetic_brain_key:
            log.debug("[swarm] no SYNTHETIC_BRAIN_API_KEY — skipping render")
            job.video_status = "skipped (no API key)"
            return

        city = pkg.get("city", "")
        state = pkg.get("state", "")
        phone = pkg.get("phone", "") or "Contact Us Now"
        location = f"{city}, {state}" if state else city
        objective = (
            f"Build a high-impact {job.risk_level} storm response ad for "
            f"{job.warehouse_name} in {location}. Use {phone} as the contact number. "
            f"The script is: {job.script[:200]}"
        )

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                r = await client.post(
                    f"{self.synthetic_brain_url}/api/v1/synthetic/run",
                    json={"objective": objective},
                    headers={"X-API-Key": self.synthetic_brain_key},
                )
                if r.status_code == 200:
                    data = r.json()
                    job.video_status = data.get("status", "UNKNOWN")
                    job.video_path = data.get("meta", {}).get("production_location", "")
                    job.render_duration_s = 0.0
                    log.info(f"[swarm] video rendered for {job.warehouse_name}: {job.video_status}")
                else:
                    log.warning(f"[swarm] render failed ({r.status_code}): {r.text[:200]}")
                    job.video_status = f"render_failed_{r.status_code}"
                    job.error = r.text[:300]
        except asyncio.TimeoutError:
            job.video_status = "timeout"
            job.error = "render timeout after 90s"
        except Exception as e:
            log.warning(f"[swarm] FFmpeg render error for {job.warehouse_name}: {e}")
            job.video_status = f"error: {str(e)[:100]}"

    # ── DB LOGGING ──────────────────────────────────────────────
    def _log_swarm_fire(self, packages: List[dict], results: List[SwarmJob]):
        """Persist swarm fire to swarm_gate_jobs table."""
        if not self.get_db:
            return
        try:
            db = self.get_db()
            now = datetime.now(timezone.utc).isoformat()
            rows = []
            for pkg, job in zip(packages, results):
                rows.append({
                    "target_id": job.target_id,
                    "warehouse_name": job.warehouse_name,
                    "metro": job.metro,
                    "niche": job.niche,
                    "risk_level": job.risk_level,
                    "brain_decision": job.brain_decision,
                    "brain_confidence": job.brain_confidence,
                    "strategy": job.strategy,
                    "script": job.script[:500] if job.script else "",
                    "audio_path": job.audio_path[:300] if job.audio_path else "",
                    "video_path": job.video_path[:300] if job.video_path else "",
                    "status": job.status,
                    "error": job.error[:500] if job.error else "",
                    "started_at": job.started_at or now,
                    "completed_at": job.completed_at or now,
                    "created_at": now,
                })
            db.table("swarm_gate_jobs").insert(rows).execute()
        except Exception as e:
            log.debug(f"[swarm] db log failed (table may not exist): {e}")

    # ── SNAPSHOT ────────────────────────────────────────────────
    def snapshot(self) -> Dict:
        return {
            **self.stats,
            "lane_count": self.lane_count,
            "synthetic_brain_wired": bool(self.synthetic_brain_key),
            "brain_decider_wired": self.brain_decider is not None,
            "si_strategy_wired": self.si_strategy is not None,
            "pain_points_wired": self.pain_points is not None,
        }
