"""
Unit tests for the Swarm Gate pipeline:
  - empire_satellite_strike.SatelliteStrikeCore  (scan, niche inference, dedup, sorting)
  - empire_swarm_gate.GodModeSwarmGate           (lane processing, script engine, render, job shapes)

All external dependencies (DB, BrainDecider, synthetic_brain, SI strategy)
are mocked. No real network calls.

Run with:
  pytest tests/test_swarm_gate.py -v
or:
  python3 -m pytest tests/test_swarm_gate.py -v
"""
import os
import sys
import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

# Make project root importable
ROOT = "/root/empire-v49"
sys.path.insert(0, ROOT)

# Env vars required at import time
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "placeholder")
os.environ.setdefault("SYNTHETIC_BRAIN_API_KEY", "test-key")
os.environ.setdefault("SYNTHETIC_BRAIN_URL", "http://127.0.0.1:8005")
os.environ.setdefault("EMPIRE_PUBLIC_BASE_URL", "")
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")

from empire_satellite_strike import (
    SatelliteStrikeCore,
    StrikePackage,
    _METRO_ALIASES,
)
from empire_swarm_gate import (
    GodModeSwarmGate,
    SwarmJob,
    DEFAULT_LANE_COUNT,
    DEFAULT_LANE_TIMEOUT,
)

# ── Helpers ────────────────────────────────────────────────────────

def _make_forecast_row(forecasts=None):
    """Build a storm_forecasts DB row with forecasts JSON."""
    if forecasts is None:
        forecasts = [
            {
                "metro": "Dallas-Fort Worth",
                "risk_level": "Severe",
                "risk_rank": 8,
                "day": 1,
                "event": "Severe Thunderstorm Warning",
                "severity": "Severe",
            },
        ]
    return {"forecasts": json.dumps(forecasts), "count": len(forecasts), "updated_at": datetime.now(timezone.utc).isoformat()}


def _make_target_row(overrides=None):
    """Build a radar_targets DB row."""
    base = {
        "id": "target-001",
        "warehouse_name": "Acme Logistics",
        "name": "Acme Logistics Hub",
        "address": "123 Main St",
        "city": "Dallas",
        "state": "TX",
        "phone": "+12145551234",
        "phone2": "",
        "email": "contact@acme.example.com",
        "asset_value": 2500000,
        "damage_severity": "Severe",
        "source": "radar",
        "meta": {},
    }
    if overrides:
        base.update(overrides)
    return base


def _make_strike_package(**overrides):
    """Build a StrikePackage dataclass for tests."""
    defaults = {
        "target_id": "target-001",
        "warehouse_name": "Acme Logistics",
        "address": "123 Main St",
        "city": "Dallas",
        "state": "TX",
        "phone": "+12145551234",
        "email": "contact@acme.example.com",
        "asset_value": 2500000.0,
        "damage_severity": "Severe",
        "metro": "Dallas-Fort Worth",
        "storm_event": "Severe Thunderstorm Warning",
        "storm_severity": "Severe",
        "storm_urgency": "Immediate",
        "risk_level": "Severe",
        "risk_rank": 8,
        "niche": "Storm Damage Restoration",
    }
    defaults.update(overrides)
    return StrikePackage(**defaults)


# ── Mock DB helpers ────────────────────────────────────────────────

class _MockSupabaseTable:
    """Simulates a Supabase table query chain."""

    def __init__(self, data=None, count=0, raise_on_execute=None):
        self._data = data or []
        self._count = count
        self._raise = raise_on_execute

    def select(self, columns, count=None):  # noqa: A003
        return self

    def order(self, col, desc=None, nulls=None):
        return self

    def limit(self, n):
        return self

    def or_(self, filter_str):  # noqa: A003
        return self

    def eq(self, col, value):
        return self

    def gte(self, col, value):
        return self

    def execute(self):
        if self._raise:
            raise self._raise
        resp = MagicMock()
        resp.data = self._data
        resp.count = self._count if self._count is not None else len(self._data)
        return resp


def _mock_db(forecast_data=None, target_data=None, strike_count=0):
    """Return a get_db callable that returns pre-configured tables.
    
    Pass explicit empty lists to simulate no rows; None uses defaults.
    """
    _fc = forecast_data if forecast_data is not None else [_make_forecast_row()]
    _tg = target_data if target_data is not None else [_make_target_row()]

    def _get_table(name):
        if name == "storm_forecasts":
            return _MockSupabaseTable(data=_fc)
        if name == "radar_targets":
            return _MockSupabaseTable(data=_tg)
        if name == "strike_log":
            return _MockSupabaseTable(data=[{"id": f"s-{i}"} for i in range(strike_count)], count=strike_count)
        if name == "swarm_gate_jobs":
            return _MockSupabaseTable(data=[])
        return _MockSupabaseTable(data=[])
    get_db = MagicMock()
    get_db.return_value.table = MagicMock(side_effect=_get_table)
    return get_db


# ── Mock BrainDecider ──────────────────────────────────────────────

def _mock_brain_decider(decision="GO", confidence=0.9, reasoning="test"):
    """Return a BrainDecider mock with .decide() returning the given response."""
    brain = MagicMock()
    brain.decide = AsyncMock(return_value={
        "decision": decision,
        "confidence": confidence,
        "reasoning": reasoning,
    })
    return brain


def _mock_si_strategy(best="AGGRESSIVE_STRIKE", win_rate=0.65):
    """Return a StrategyEvolution mock."""
    si = MagicMock()
    si.best_for_niche = MagicMock(return_value=best)
    si.get_niche_win_rate = MagicMock(return_value=win_rate)
    return si


def _mock_pain_points():
    """Return a PainPointLibrary mock that returns the script unchanged."""
    pp = MagicMock()
    pp.inject_pain_points = MagicMock(side_effect=lambda niche, script: script)
    return pp


# ════════════════════════════════════════════════════════════════════
#  SATELLITE STRIKE CORE TESTS
# ════════════════════════════════════════════════════════════════════

class TestStrikePackage:
    """StrikePackage dataclass shape and defaults."""

    def test_default_factory_fields(self):
        pkg = StrikePackage(
            target_id="t1",
            warehouse_name="Acme",
        )
        assert pkg.target_id == "t1"
        assert pkg.warehouse_name == "Acme"
        assert pkg.source == "satellite_strike"
        assert isinstance(pkg.meta, dict)
        assert pkg.meta == {}

    def test_all_fields_assignable(self):
        pkg = _make_strike_package()
        assert pkg.risk_rank == 8
        assert pkg.asset_value == 2500000.0
        assert pkg.niche == "Storm Damage Restoration"
        assert pkg.storm_urgency == "Immediate"

    def test_meta_can_be_populated(self):
        pkg = StrikePackage(
            target_id="t1",
            warehouse_name="W",
            meta={"forecast_day": 2, "custom": True},
        )
        assert pkg.meta["forecast_day"] == 2
        assert pkg.meta["custom"] is True


class TestSatelliteScan:
    """SatelliteStrikeCore.scan() — the full scan lifecycle."""

    def test_scan_returns_empty_when_no_db(self):
        """Without a get_db wired, scan returns an empty list."""
        sat = SatelliteStrikeCore(get_db=None)
        async def run():
            return await sat.scan()
        packages = asyncio.run(run())
        assert packages == []

    def test_scan_returns_empty_when_no_forecasts(self):
        """When storm_forecasts is empty, scan returns []."""
        get_db = _mock_db(forecast_data=[])
        sat = SatelliteStrikeCore(get_db=get_db)
        async def run():
            return await sat.scan()
        packages = asyncio.run(run())
        assert packages == []

    def test_scan_skips_below_min_risk_rank(self):
        """Forecasts with risk_rank < min_risk_rank should be skipped."""
        low_risk = json.dumps([
            {"metro": "Dallas-Fort Worth", "risk_level": "Marginal", "risk_rank": 2, "day": 1,
             "event": "Marginal Storm", "severity": "Marginal"},
        ])
        forecast_row = {"forecasts": low_risk, "count": 1, "updated_at": datetime.now(timezone.utc).isoformat()}
        get_db = _mock_db(forecast_data=[forecast_row], target_data=[_make_target_row()])
        sat = SatelliteStrikeCore(get_db=get_db, min_risk_rank=4)
        async def run():
            return await sat.scan()
        packages = asyncio.run(run())
        assert packages == []  # risk_rank 2 < min 4 → skipped

    def test_scan_basic_package_production(self):
        """A single forecast + target produces one StrikePackage."""
        get_db = _mock_db()
        sat = SatelliteStrikeCore(get_db=get_db)
        async def run():
            return await sat.scan()
        packages = asyncio.run(run())
        assert len(packages) == 1
        pkg = packages[0]
        assert pkg.warehouse_name == "Acme Logistics"
        assert pkg.metro == "Dallas-Fort Worth"
        assert pkg.risk_level == "Severe"
        assert pkg.risk_rank == 8
        # _infer_niche: "Severe" doesn't match storm keywords → asset-based fallback
        # asset_value=2,500,000 > 2,000,000 → Industrial Storm Response
        assert pkg.niche == "Industrial Storm Response"

    def test_scan_deduplicates_by_target_id(self):
        """Same target_id from two metros should only appear once."""
        forecasts = json.dumps([
            {"metro": "Dallas-Fort Worth", "risk_level": "Severe", "risk_rank": 7, "day": 1,
             "event": "Thunderstorm", "severity": "Severe"},
            {"metro": "Fort Worth", "risk_level": "Slight", "risk_rank": 4, "day": 1,
             "event": "Wind", "severity": "Slight"},
        ])
        forecast_row = {"forecasts": forecasts, "count": 2, "updated_at": datetime.now(timezone.utc).isoformat()}
        get_db = _mock_db(forecast_data=[forecast_row])
        sat = SatelliteStrikeCore(get_db=get_db)
        async def run():
            return await sat.scan()
        packages = asyncio.run(run())
        assert len(packages) == 1  # deduped

    def test_scan_dispatched_target_is_skipped(self):
        """Targets already in strike_log within the lookback window are skipped."""
        get_db = _mock_db(strike_count=1)
        sat = SatelliteStrikeCore(get_db=get_db)
        async def run():
            return await sat.scan()
        packages = asyncio.run(run())
        assert packages == []

    def test_scan_respects_max_packages(self):
        """Only max_packages are returned even with many targets."""
        targets = [_make_target_row({"id": f"t-{i}", "warehouse_name": f"Target {i}"}) for i in range(50)]
        get_db = _mock_db(target_data=targets)
        sat = SatelliteStrikeCore(get_db=get_db, max_packages=5)
        async def run():
            return await sat.scan()
        packages = asyncio.run(run())
        assert len(packages) == 5

    def test_scan_sorts_by_risk_then_asset(self):
        """Packages should be sorted: highest risk_rank first, then highest asset_value."""
        forecasts = json.dumps([
            {"metro": "Dallas-Fort Worth", "risk_level": "Severe", "risk_rank": 8, "day": 1,
             "event": "Tornado", "severity": "Severe"},
            {"metro": "Houston", "risk_level": "Slight", "risk_rank": 4, "day": 1,
             "event": "Wind", "severity": "Slight"},
        ])
        forecast_row = {"forecasts": forecasts, "count": 2, "updated_at": datetime.now(timezone.utc).isoformat()}

        def _get_table(name):
            if name == "storm_forecasts":
                return _MockSupabaseTable(data=[forecast_row])
            if name == "radar_targets":
                return _MockSupabaseTable(data=[
                    _make_target_row({"id": "t-low", "warehouse_name": "Low Risk", "city": "Dallas", "asset_value": 5000000}),
                    _make_target_row({"id": "t-high", "warehouse_name": "High Risk", "city": "Houston", "asset_value": 100000}),
                ])
            if name == "strike_log":
                return _MockSupabaseTable(data=[])
            return _MockSupabaseTable(data=[])

        get_db = MagicMock()
        get_db.return_value.table = MagicMock(side_effect=_get_table)
        sat = SatelliteStrikeCore(get_db=get_db)
        async def run():
            return await sat.scan()
        packages = asyncio.run(run())
        assert len(packages) == 2
        # Dallas forecast has risk_rank 8, Houston has 4 — Dallas should be first
        assert packages[0].risk_rank >= packages[1].risk_rank

    def test_scan_updates_last_scan_at_and_count(self):
        get_db = _mock_db()
        sat = SatelliteStrikeCore(get_db=get_db)
        async def run():
            return await sat.scan()
        packages = asyncio.run(run())
        assert sat.last_scan_at is not None
        assert sat.last_package_count == len(packages)

    def test_scan_db_fetch_failure_graceful(self):
        """If DB raises, scan returns empty without crashing."""
        get_db = MagicMock()
        get_db.return_value.table = MagicMock(side_effect=Exception("DB down"))
        sat = SatelliteStrikeCore(get_db=get_db)
        async def run():
            return await sat.scan()
        packages = asyncio.run(run())
        assert packages == []


class TestNicheInference:
    """_infer_niche static method maps risk level to niche."""

    def test_tornado(self):
        result = SatelliteStrikeCore._infer_niche(
            {"damage_severity": "Severe"},
            {"risk_level": "Tornado Warning"},
        )
        assert result == "Tornado Damage Repair"

    def test_hurricane(self):
        result = SatelliteStrikeCore._infer_niche({}, {"risk_level": "Hurricane Watch"})
        assert result == "Hurricane Damage Restoration"

    def test_hail(self):
        result = SatelliteStrikeCore._infer_niche({}, {"risk_level": "Hail storm"})
        assert result == "Hail Damage Repair"

    def test_flood(self):
        result = SatelliteStrikeCore._infer_niche({}, {"risk_level": "Flash Flood"})
        assert result == "Flood Damage Restoration"

    def test_thunderstorm(self):
        result = SatelliteStrikeCore._infer_niche({}, {"risk_level": "Severe Thunderstorm"})
        assert result == "Storm Damage Restoration"

    def test_wind(self):
        result = SatelliteStrikeCore._infer_niche({}, {"risk_level": "High Wind Advisory"})
        assert result == "Storm Damage Restoration"

    def test_large_asset_commercial(self):
        result = SatelliteStrikeCore._infer_niche(
            {"asset_value": 15000000},
            {"risk_level": "Generic Storm"},
        )
        assert result == "Commercial Property Restoration"

    def test_medium_asset_industrial(self):
        result = SatelliteStrikeCore._infer_niche(
            {"asset_value": 5000000},
            {"risk_level": "Generic Storm"},
        )
        assert result == "Industrial Storm Response"

    def test_small_asset_roofing_fallback(self):
        result = SatelliteStrikeCore._infer_niche(
            {"asset_value": 500000},
            {"risk_level": "Generic Storm"},
        )
        assert result == "Roofing Restoration"

    def test_case_insensitive_risk_level(self):
        result = SatelliteStrikeCore._infer_niche({}, {"risk_level": "HAIL WARNING"})
        assert result == "Hail Damage Repair"


class TestSatelliteSnapshot:
    """snapshot() returns expected keys and values."""

    def test_snapshot_defaults(self):
        sat = SatelliteStrikeCore()
        snap = sat.snapshot()
        assert snap["last_scan_at"] is None
        assert snap["last_package_count"] == 0
        assert snap["lookback_hours"] == 24
        assert snap["min_risk_rank"] == 4
        assert snap["max_packages"] == 32

    def test_snapshot_custom_config(self):
        sat = SatelliteStrikeCore(lookback_hours=12, min_risk_rank=3, max_packages=10)
        snap = sat.snapshot()
        assert snap["lookback_hours"] == 12
        assert snap["min_risk_rank"] == 3
        assert snap["max_packages"] == 10

    def test_snapshot_after_scan(self):
        get_db = _mock_db()
        sat = SatelliteStrikeCore(get_db=get_db)
        async def run():
            return await sat.scan()
        asyncio.run(run())
        snap = sat.snapshot()
        assert snap["last_scan_at"] is not None
        assert snap["last_package_count"] == 1


class TestMetroAliases:
    """_METRO_ALIASES covers expected key metros."""

    def test_dfw_aliases(self):
        aliases = _METRO_ALIASES["Dallas-Fort Worth"]
        assert "dallas" in aliases
        assert "fort worth" in aliases
        assert "dfw" in aliases

    def test_okc_alias(self):
        aliases = _METRO_ALIASES["Oklahoma City"]
        assert "okc" in aliases


# ════════════════════════════════════════════════════════════════════
#  GOD MODE SWARM GATE TESTS
# ════════════════════════════════════════════════════════════════════

class TestSwarmJob:
    """SwarmJob dataclass shape and defaults."""

    def test_default_fields(self):
        job = SwarmJob(
            target_id="t1",
            warehouse_name="Acme",
            metro="DFW",
            niche="Storm",
            risk_level="Severe",
        )
        assert job.status == "queued"
        assert job.script == ""
        assert job.brain_confidence == 0.0
        assert job.video_status == ""
        assert job.error == ""

    def test_all_fields_assignable(self):
        job = SwarmJob(
            target_id="t1",
            warehouse_name="Acme Logistics",
            metro="Dallas-Fort Worth",
            niche="Tornado Damage Repair",
            risk_level="Severe",
            status="complete",
            script="Hello, this is Empire AI...",
            brain_decision="GO",
            brain_confidence=0.92,
            brain_reasoning="High-value commercial target in tornado path",
            strategy="AGGRESSIVE_STRIKE",
            audio_path="/builds/voiceover.wav",
            audio_duration_s=8.5,
            voice_profile="am_michael",
            video_path="/builds/ad.mp4",
            video_status="SUCCESS",
            render_duration_s=12.3,
            error="",
            started_at="2026-06-12T12:00:00Z",
            completed_at="2026-06-12T12:00:30Z",
        )
        assert job.status == "complete"
        assert job.brain_confidence == 0.92
        assert job.strategy == "AGGRESSIVE_STRIKE"
        assert job.video_status == "SUCCESS"
        assert job.audio_duration_s == 8.5


class TestSwarmGateInit:
    """GodModeSwarmGate constructor and defaults."""

    def test_default_values(self):
        gate = GodModeSwarmGate()
        assert gate.lane_count == DEFAULT_LANE_COUNT
        assert gate.lane_timeout == DEFAULT_LANE_TIMEOUT
        assert gate.synthetic_brain_key == "test-key"
        assert gate.stats["total_fires"] == 0
        assert gate.stats["total_completed"] == 0

    def test_custom_lane_count_and_timeout(self):
        gate = GodModeSwarmGate(lane_count=5, lane_timeout=60)
        assert gate.lane_count == 5
        assert gate.lane_timeout == 60

    def test_explicit_api_key_takes_precedence(self):
        gate = GodModeSwarmGate(synthetic_brain_key="explicit-key")
        assert gate.synthetic_brain_key == "explicit-key"


class TestSwarmFireEmpty:
    """fire() edge cases — empty packages, unknown types."""

    def test_empty_packages_returns_empty(self):
        gate = GodModeSwarmGate()
        async def run():
            return await gate.fire([])
        jobs = asyncio.run(run())
        assert jobs == []

    def test_none_packages_type_is_filtered(self):
        """Unknown types are dropped gracefully."""
        gate = GodModeSwarmGate()
        async def run():
            return await gate.fire([42, "string"])  # neither dataclass nor dict
        jobs = asyncio.run(run())
        assert jobs == []


class TestSwarmFireLaneProcessing:
    """fire() with proper StrikePackage dicts — lane processing through the pipeline."""

    def test_single_package_all_phases(self):
        """A single package flows through script + render with auto_script=True, auto_render=True."""
        brain = _mock_brain_decider(decision="GO", confidence=0.95)
        si = _mock_si_strategy(best="FINANCIAL_STRIKE")
        pp = _mock_pain_points()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
            pain_points=pp,
            synthetic_brain_key="test-key",
            lane_count=3,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=True)
        jobs = asyncio.run(run())

        assert len(jobs) == 1
        job = jobs[0]
        assert job.target_id == "target-001"
        assert job.warehouse_name == "Acme Logistics"
        assert job.metro == "Dallas-Fort Worth"
        assert job.niche == "Storm Damage Restoration"
        assert job.risk_level == "Severe"
        assert job.brain_decision == "GO"
        assert job.brain_confidence == 0.95
        assert job.strategy == "FINANCIAL_STRIKE"
        assert len(job.script) > 0
        assert "Empire AI" in job.script
        # Should be complete since script + render ran (render may fail silently if no real server)
        assert job.status in ("complete", "rendering")  # render may fail w/o real SB server

    def test_single_package_script_only(self):
        """auto_script=True, auto_render=False — only script phase runs."""
        brain = _mock_brain_decider()
        si = _mock_si_strategy(best="RECALL_SNIPER")
        pp = _mock_pain_points()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
            pain_points=pp,
            lane_count=3,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        assert len(jobs) == 1
        job = jobs[0]
        assert job.status == "complete"
        assert len(job.script) > 0
        assert job.strategy == "RECALL_SNIPER"
        assert job.video_path == ""  # no render

    def test_single_package_no_script_or_render(self):
        """auto_script=False, auto_render=False — queued only."""
        brain = _mock_brain_decider()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            lane_count=3,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=False, auto_render=False)
        jobs = asyncio.run(run())

        assert len(jobs) == 1
        job = jobs[0]
        assert job.status == "complete"
        assert job.script == ""  # no script
        assert job.video_path == ""  # no render

    def test_multiple_packages_parallel(self):
        """Multiple packages should be processed (3 packages, 3 lanes)."""
        brain = _mock_brain_decider()
        si = _mock_si_strategy()
        pp = _mock_pain_points()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
            pain_points=pp,
            lane_count=3,
        )

        pkgs = [
            _make_strike_package(target_id="t-A", warehouse_name="Alpha", risk_rank=8, asset_value=5000000.0),
            _make_strike_package(target_id="t-B", warehouse_name="Bravo", risk_rank=6, asset_value=3000000.0),
            _make_strike_package(target_id="t-C", warehouse_name="Charlie", risk_rank=4, asset_value=1000000.0),
        ]

        async def run():
            return await gate.fire(pkgs, auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        assert len(jobs) == 3
        names = {j.warehouse_name for j in jobs}
        assert names == {"Alpha", "Bravo", "Charlie"}
        for job in jobs:
            assert job.status == "complete"
            assert len(job.script) > 0

    def test_package_as_dict_instead_of_dataclass(self):
        """fire() accepts plain dicts with the same shape."""
        brain = _mock_brain_decider()
        si = _mock_si_strategy()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
            lane_count=3,
        )

        pkg_dict = {
            "target_id": "t-dict",
            "warehouse_name": "Dict Co",
            "metro": "Dallas",
            "niche": "Storm Damage Restoration",
            "risk_level": "Severe",
            "phone": "+12145559999",
            "asset_value": 1000000.0,
            "city": "Dallas",
            "state": "TX",
            "address": "456 Elm St",
            "email": "dict@example.com",
            "storm_event": "Thunderstorm",
            "storm_severity": "Severe",
            "storm_urgency": "Immediate",
            "risk_rank": 7,
        }

        async def run():
            return await gate.fire([pkg_dict], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        assert len(jobs) == 1
        assert jobs[0].warehouse_name == "Dict Co"
        assert jobs[0].target_id == "t-dict"


class TestBrainDecisionPaths:
    """BrainDecider can return GO or NO_GO — verify script engine handles both."""

    def test_brain_go_produces_script(self):
        brain = _mock_brain_decider(decision="GO", confidence=0.88)
        si = _mock_si_strategy()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        assert jobs[0].brain_decision == "GO"
        assert jobs[0].brain_confidence == 0.88
        assert len(jobs[0].script) > 0

    def test_brain_no_go_produces_script_with_fallback(self):
        """NO_GO still builds a script but doesn't select a SI strategy."""
        brain = _mock_brain_decider(decision="NO_GO", confidence=0.15)
        si = _mock_si_strategy()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        assert jobs[0].brain_decision == "NO_GO"
        assert jobs[0].strategy == "AGGRESSIVE_STRIKE"  # fallback when NO_GO

    def test_no_brain_decider_defaults_to_go(self):
        """Without a brain_decider, default to GO @ 0.5."""
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=None,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        assert jobs[0].brain_decision == "GO"
        assert jobs[0].brain_confidence == 0.5


class TestScriptEngineStrategies:
    """Script builder uses the strategy name to craft tone/opener."""

    def test_aggressive_strike_tone(self):
        brain = _mock_brain_decider(decision="GO", confidence=0.92)
        si = _mock_si_strategy(best="AGGRESSIVE_STRIKE")
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        script = jobs[0].script
        assert "crews standing by" in script.lower()

    def test_financial_strike_tone(self):
        brain = _mock_brain_decider(decision="GO", confidence=0.85)
        si = _mock_si_strategy(best="FINANCIAL_STRIKE")
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        script = jobs[0].script
        assert "insurance" in script.lower()

    def test_recall_sniper_tone(self):
        brain = _mock_brain_decider(decision="GO", confidence=0.75)
        si = _mock_si_strategy(best="RECALL_SNIPER")
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        script = jobs[0].script
        assert "predictive models" in script.lower()

    def test_confidence_below_0_7_urgency(self):
        """Confidence 0.65: < 0.7 → lowest urgency tier = 'learn more'."""
        brain = _mock_brain_decider(decision="GO", confidence=0.65)
        si = _mock_si_strategy(best="AGGRESSIVE_STRIKE")
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        script = jobs[0].script
        assert "learn more" in script.lower()

    def test_confidence_below_0_4_urgency(self):
        brain = _mock_brain_decider(decision="GO", confidence=0.30)
        si = _mock_si_strategy(best="AGGRESSIVE_STRIKE")
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        script = jobs[0].script
        assert "learn more" in script.lower()

    def test_script_includes_asset_value_when_present(self):
        brain = _mock_brain_decider(decision="GO", confidence=0.90)
        si = _mock_si_strategy()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
        )

        pkg = _make_strike_package(asset_value=7500000.0)

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        script = jobs[0].script
        assert "$7,500,000" in script
        assert "$75,000" in script  # fee = 7.5M * 0.01

    def test_script_no_asset_value_omits_fee(self):
        brain = _mock_brain_decider()
        si = _mock_si_strategy()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
        )

        pkg = _make_strike_package(asset_value=0.0)

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        script = jobs[0].script
        assert "success-only fee" not in script.lower()


class TestPainPointsInjection:
    """When pain_points is wired, it modifies the script."""

    def test_pain_points_called_during_scripting(self):
        brain = _mock_brain_decider()
        si = _mock_si_strategy()
        pp = MagicMock()
        pp.inject_pain_points = MagicMock(return_value="SCRIPT_WITH_PAIN_POINTS")
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
            pain_points=pp,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        assert pp.inject_pain_points.called
        assert jobs[0].script == "SCRIPT_WITH_PAIN_POINTS"

    def test_pain_points_exception_does_not_crash(self):
        brain = _mock_brain_decider()
        si = _mock_si_strategy()
        pp = MagicMock()
        pp.inject_pain_points = MagicMock(side_effect=RuntimeError("PP engine down"))
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
            pain_points=pp,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        assert jobs[0].status == "complete"
        assert len(jobs[0].script) > 0  # script was built before pain points crashed


class TestRenderPhase:
    """FFmpeg 1080x1920 render phase — mock the synthetic_brain HTTP call."""

    def test_render_sends_correct_payload(self):
        """Verify the POST to /api/v1/synthetic/run uses the right shape."""
        brain = _mock_brain_decider()
        si = _mock_si_strategy()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
            synthetic_brain_key="test-key",
            synthetic_brain_url="http://127.0.0.1:8005",
        )

        # Mock the httpx AsyncClient.post
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "SUCCESS",
            "meta": {"production_location": "/builds/swarm_vault/target-001/ad.mp4"},
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        pkg = _make_strike_package()

        async def run():
            gate._http = mock_client
            return await gate.fire([pkg], auto_script=True, auto_render=True)
        jobs = asyncio.run(run())

        assert jobs[0].video_status == "SUCCESS"
        assert jobs[0].video_path == "/builds/swarm_vault/target-001/ad.mp4"
        # Verify the POST payload shape
        assert mock_client.post.called
        call_kwargs = mock_client.post.call_args
        assert "/api/v1/synthetic/run" in call_kwargs[0][0]
        assert "objective" in call_kwargs[1]["json"]

    def test_render_without_api_key_skips(self):
        """No synthetic_brain_key -> render phase skipped gracefully."""
        brain = _mock_brain_decider()
        get_db = _mock_db()

        # Must override both the constructor arg AND the env var
        # because the constructor falls back via `or os.environ.get(...)`.
        with patch.dict(os.environ, {"SYNTHETIC_BRAIN_API_KEY": ""}, clear=False):
            gate = GodModeSwarmGate(
                get_db=get_db,
                brain_decider=brain,
                synthetic_brain_key="",
            )

            pkg = _make_strike_package()

            async def run():
                return await gate.fire([pkg], auto_script=True, auto_render=True)
            jobs = asyncio.run(run())

        assert jobs[0].video_status == "skipped (no API key)"

    def test_render_http_error_captured(self):
        """Non-200 response → video_status reflects the error."""
        brain = _mock_brain_decider()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            synthetic_brain_key="test-key",
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "GPU OOM"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        pkg = _make_strike_package()

        async def run():
            gate._http = mock_client
            return await gate.fire([pkg], auto_script=True, auto_render=True)
        jobs = asyncio.run(run())

        assert "render_failed_500" in jobs[0].video_status


class TestSwarmGateStats:
    """Swarm Gate stats track cumulative fire() results."""

    def test_stats_increment_on_fire(self):
        brain = _mock_brain_decider()
        si = _mock_si_strategy()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
            lane_count=3,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        asyncio.run(run())

        assert gate.stats["total_fires"] == 1
        assert gate.stats["total_lanes_processed"] == 1
        assert gate.stats["total_completed"] == 1
        assert gate.stats["total_failed"] == 0
        assert gate.stats["last_fire_at"] is not None

    def test_stats_accumulate_over_multiple_fires(self):
        brain = _mock_brain_decider()
        si = _mock_si_strategy()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
            lane_count=3,
        )

        async def run():
            await gate.fire([_make_strike_package(target_id="a")], auto_script=True, auto_render=False)
            await gate.fire([_make_strike_package(target_id="b")], auto_script=True, auto_render=False)
        asyncio.run(run())

        assert gate.stats["total_fires"] == 2
        assert gate.stats["total_lanes_processed"] == 2


class TestSwarmGateSnapshot:
    """snapshot() returns expected keys and values."""

    def test_snapshot_defaults(self):
        gate = GodModeSwarmGate()
        snap = gate.snapshot()
        assert snap["total_fires"] == 0
        assert snap["total_completed"] == 0
        assert snap["total_failed"] == 0
        assert snap["lane_count"] == DEFAULT_LANE_COUNT
        assert "synthetic_brain_wired" in snap
        assert "brain_decider_wired" in snap
        assert "si_strategy_wired" in snap
        assert "pain_points_wired" in snap

    def test_snapshot_reflects_wired_deps(self):
        gate = GodModeSwarmGate(
            brain_decider=MagicMock(),
            si_strategy=MagicMock(),
            pain_points=MagicMock(),
            synthetic_brain_key="test-key",
        )
        snap = gate.snapshot()
        assert snap["brain_decider_wired"] is True
        assert snap["si_strategy_wired"] is True
        assert snap["pain_points_wired"] is True
        assert snap["synthetic_brain_wired"] is True

    def test_snapshot_reflects_unwired_deps(self):
        gate = GodModeSwarmGate()
        snap = gate.snapshot()
        assert snap["brain_decider_wired"] is False
        assert snap["si_strategy_wired"] is False
        assert snap["pain_points_wired"] is False


class TestSwarmGateGracefulFailure:
    """Exceptions during lane processing don't crash the swarm."""

    def test_unhandled_lane_exception_wrapped_by_gather(self):
        """When _process_lane raises, fire()'s asyncio.gather(return_exceptions=True)
        wraps it as a SwarmJob with status=failed and error details."""
        brain = _mock_brain_decider()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            lane_count=1,
        )
        gate._process_lane = AsyncMock(side_effect=RuntimeError("Catastrophic lane failure"))

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        assert len(jobs) == 1
        assert jobs[0].status == "failed"
        assert "Catastrophic lane failure" in jobs[0].error
        assert gate.stats["total_failed"] == 1

    def test_brain_timeout_produces_fallback_decision(self):
        """If brain.decide times out, the lane falls back to GO @ 0.5."""
        brain = MagicMock()
        # Simulate timeout by raising TimeoutError (pass class, not instance)
        brain.decide = AsyncMock(side_effect=asyncio.TimeoutError)
        si = _mock_si_strategy()
        get_db = _mock_db()

        gate = GodModeSwarmGate(
            get_db=get_db,
            brain_decider=brain,
            si_strategy=si,
        )

        pkg = _make_strike_package()

        async def run():
            return await gate.fire([pkg], auto_script=True, auto_render=False)
        jobs = asyncio.run(run())

        assert jobs[0].brain_decision == "GO"
        assert jobs[0].brain_confidence == 0.5
        assert "timeout" in jobs[0].brain_reasoning.lower()
        assert jobs[0].status == "complete"
