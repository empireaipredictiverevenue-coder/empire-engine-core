"""Tests for empire_psychology_mind_map.py — Sales Psychology Mind Map."""

import pytest
from empire_psychology_mind_map import (
    PsychologyMindMap,
    PERSUASION_PRINCIPLES,
    BUYER_PERSONA_PROFILES,
    NICHE_PSYCHOLOGY_PROFILES,
    _DEFAULT_NICHE_PROFILE,
)


class TestDataIntegrity:
    """Verify that the knowledge base data is self-consistent."""

    def test_principles_have_required_fields(self):
        """Each persuasion principle has all required keys."""
        required = {"id", "name", "founder", "category", "description", "tactics",
                     "niche_relevance", "persona_affinity"}
        for key, p in PERSUASION_PRINCIPLES.items():
            missing = required - set(p.keys())
            assert not missing, f"Principle '{key}' missing: {missing}"
            assert p["id"] == key, f"Principle '{key}' id mismatch"

    def test_persona_profiles_are_complete(self):
        """Each buyer persona has all required keys."""
        required = {"key", "label", "description", "dominant_principles",
                     "effective_techniques", "best_closer_persona", "script_tone",
                     "opening_philosophy", "keywords", "decision_style"}
        for key, profile in BUYER_PERSONA_PROFILES.items():
            missing = required - set(profile.keys())
            assert not missing, f"Persona '{key}' missing: {missing}"

    def test_dominant_principles_exist(self):
        """All referenced dominant principles actually exist in PERSUASION_PRINCIPLES."""
        for p_key, profile in BUYER_PERSONA_PROFILES.items():
            for dp in profile.get("dominant_principles", []):
                assert dp in PERSUASION_PRINCIPLES, \
                    f"Persona '{p_key}' references unknown principle '{dp}'"

    def test_niche_profiles_have_weightings(self):
        """Each niche profile has principle_weights covering all principles."""
        for niche, profile in NICHE_PSYCHOLOGY_PROFILES.items():
            weights = profile.get("principle_weights", {})
            for p_key in PERSUASION_PRINCIPLES:
                assert p_key in weights, \
                    f"Niche '{niche}' missing principle weight for '{p_key}'"

    def test_niche_profiles_persona_distribution_sums(self):
        """Each niche's persona distribution sums to ~1.0."""
        for niche, profile in NICHE_PSYCHOLOGY_PROFILES.items():
            total = sum(profile.get("persona_distribution", {}).values())
            assert abs(total - 1.0) < 0.02, \
                f"Niche '{niche}' persona distribution sums to {total} (expected ~1.0)"

    def test_default_niche_profile_is_valid(self):
        """The default fallback profile has all required fields."""
        assert _DEFAULT_NICHE_PROFILE is not None
        assert "dominant_persona" in _DEFAULT_NICHE_PROFILE
        assert "principle_weights" in _DEFAULT_NICHE_PROFILE
        assert len(_DEFAULT_NICHE_PROFILE["principle_weights"]) == len(PERSUASION_PRINCIPLES)


class TestPsychologyMindMap:
    """Core PsychologyMindMap class functionality."""

    def test_snapshot_returns_full_structure(self):
        """snapshot() returns expected top-level keys."""
        mm = PsychologyMindMap()
        s = mm.snapshot()
        assert "mind_map" in s
        assert "effectiveness" in s
        assert "niche_profiles_count" in s
        assert "persona_count" in s
        assert "principles_count" in s
        assert "techniques_count" in s
        assert "ts" in s

    def test_snapshot_counts(self):
        """snapshot() counts match the data module constants."""
        mm = PsychologyMindMap()
        s = mm.snapshot()
        assert s["persona_count"] == len(BUYER_PERSONA_PROFILES)
        assert s["principles_count"] == len(PERSUASION_PRINCIPLES)
        assert s["niche_profiles_count"] == len(NICHE_PSYCHOLOGY_PROFILES)

    def test_build_mind_map_returns_valid_graph(self):
        """build_mind_map() returns nodes and edges with valid structure."""
        mm = PsychologyMindMap()
        graph = mm.build_mind_map()
        assert "nodes" in graph
        assert "edges" in graph
        assert "summary" in graph
        assert len(graph["nodes"]) > 0
        assert len(graph["edges"]) > 0

        # Check nodes have required fields
        for node in graph["nodes"]:
            assert "id" in node
            assert "type" in node
            assert "label" in node
            assert node["type"] in ("niche", "persona", "principle", "technique")

        # Check edges have required fields
        for edge in graph["edges"]:
            assert "source" in edge
            assert "target" in edge
            assert "weight" in edge

    def test_mind_map_graph_summary(self):
        """Graph summary counts match."""
        mm = PsychologyMindMap()
        graph = mm.build_mind_map()
        s = graph["summary"]
        assert s["total_nodes"] == len(graph["nodes"])
        assert s["total_edges"] == len(graph["edges"])
        assert s["personas"] == len(BUYER_PERSONA_PROFILES)
        assert s["principles"] == len(PERSUASION_PRINCIPLES)

    def test_get_mind_map_caches(self):
        """get_mind_map() returns the same object after build."""
        mm = PsychologyMindMap()
        g1 = mm.get_mind_map()
        g2 = mm.get_mind_map()
        assert g1 is g2  # cached

    def test_get_principles_for_persona(self):
        """get_principles_for_persona() returns principles sorted by affinity descending."""
        mm = PsychologyMindMap()
        principles = mm.get_principles_for_persona("analytical")
        assert len(principles) > 0
        # Check descending affinity
        affinities = [p["affinity"] for p in principles]
        assert affinities == sorted(affinities, reverse=True)

    def test_get_principles_for_unknown_persona(self):
        """get_principles_for_persona() returns [] for unknown persona."""
        mm = PsychologyMindMap()
        assert mm.get_principles_for_persona("nonexistent") == []


class TestPersonaDetection:
    """Buyer persona detection from text."""

    def test_detect_analytical(self):
        """'data', 'statistics' keywords → analytical persona."""
        mm = PsychologyMindMap()
        r = mm.get_persona_for_lead_text("show me the data and statistics to prove it")
        assert r["persona"] == "analytical"
        assert r["confidence"] > 0
        assert r["label"] == "The Analyst"
        assert "all_scores" in r

    def test_detect_price_sensitive(self):
        """'cost', 'expensive' keywords → price_sensitive."""
        mm = PsychologyMindMap()
        r = mm.get_persona_for_lead_text("how much does this cost? is it expensive?")
        # Depending on keyword overlap, confidence should be non-zero
        assert r["persona"] != "unknown"
        assert r["confidence"] > 0

    def test_detect_unknown(self):
        """Gibberish text returns unknown persona."""
        mm = PsychologyMindMap()
        r = mm.get_persona_for_lead_text("")
        assert r["persona"] == "unknown"
        assert r["confidence"] == 0.0

    def test_detect_short_text(self):
        """Very short text returns unknown persona."""
        mm = PsychologyMindMap()
        r = mm.get_persona_for_lead_text("ok")
        assert r["persona"] == "unknown"


class TestNicheProfiles:
    """Niche-specific psychology profiles."""

    def test_get_niche_profile_known(self):
        """Known niche returns its profile."""
        mm = PsychologyMindMap()
        profile = mm.get_niche_profile("Roofing Restoration")
        assert profile is not None
        assert profile["niche"] == "Roofing Restoration"
        assert "dominant_persona" in profile
        assert "principle_weights" in profile

    def test_get_niche_profile_unknown(self):
        """Unknown niche falls back to default profile."""
        mm = PsychologyMindMap()
        profile = mm.get_niche_profile("Nonexistent Niche 9000")
        assert profile is not None
        assert profile["niche"] == "Nonexistent Niche 9000"
        # Should have default principle weights
        assert len(profile.get("principle_weights", {})) == len(PERSUASION_PRINCIPLES)

    def test_get_all_niche_profiles(self):
        """get_all_niche_profiles() returns all defined profiles."""
        mm = PsychologyMindMap()
        profiles = mm.get_all_niche_profiles()
        assert len(profiles) == len(NICHE_PSYCHOLOGY_PROFILES)

    def test_get_niche_persona_breakdown(self):
        """get_niche_persona_breakdown() returns expected structure."""
        mm = PsychologyMindMap()
        bd = mm.get_niche_persona_breakdown("Roofing Restoration")
        assert bd["niche"] == "Roofing Restoration"
        assert "dominant_persona" in bd
        assert "best_closer_persona" in bd
        assert "decision_speed" in bd
        assert "breakdown" in bd
        assert len(bd["breakdown"]) > 0
        # Each breakdown entry has approach data
        for entry in bd["breakdown"]:
            assert "persona" in entry
            assert "percentage" in entry
            assert "approach" in entry


class TestRecommendedApproach:
    """Persona-based recommendation engine."""

    def test_recommended_approach_returns_valid(self):
        """get_recommended_approach() returns expected structure."""
        mm = PsychologyMindMap()
        ra = mm.get_recommended_approach("analytical")
        assert ra["persona"] == "analytical"
        assert "persona_label" in ra
        assert "best_closer_persona" in ra
        assert "script_tone" in ra
        assert "opening_philosophy" in ra
        assert "top_principles" in ra
        assert len(ra["top_principles"]) == 5
        assert "recommended_techniques" in ra
        assert len(ra["recommended_techniques"]) > 0

    def test_recommended_approach_with_niche(self):
        """get_recommended_approach() with niche includes niche-adjusted affinities."""
        mm = PsychologyMindMap()
        ra = mm.get_recommended_approach("analytical", "Roofing Restoration")
        assert ra["niche_adjusted"] is True
        assert ra["niche"] == "Roofing Restoration"
        # Niche-adjusted affinities should be present
        for p in ra["top_principles"]:
            assert "niche_adjusted_affinity" in p

    def test_recommended_approach_unknown_persona(self):
        """get_recommended_approach() returns error for unknown persona."""
        mm = PsychologyMindMap()
        ra = mm.get_recommended_approach("nonexistent")
        assert "error" in ra

    def test_technique_patterns_exist(self):
        """Recommended techniques have valid patterns."""
        mm = PsychologyMindMap()
        ra = mm.get_recommended_approach("analytical")
        for tech in ra["recommended_techniques"]:
            assert "technique" in tech
            assert "pattern" in tech
            assert "principle_source" in tech


class TestEffectivenessTracking:
    """Effectiveness tracking for psychology-strategy combinations."""

    def test_record_and_query_effectiveness(self):
        """Recording effectiveness and querying returns correct data."""
        mm = PsychologyMindMap()
        mm.record_effectiveness("Roofing Restoration", "analytical", "authority", True)
        mm.record_effectiveness("Roofing Restoration", "analytical", "authority", False)
        mm.record_effectiveness("Roofing Restoration", "analytical", "authority", True)

        result = mm.get_effectiveness(
            niche="Roofing Restoration",
            persona_key="analytical",
            principle_key="authority",
        )
        assert result["total_records"] == 1
        assert result["results"][0]["attempts"] == 3
        assert result["results"][0]["successes"] == 2
        assert result["results"][0]["conversion_rate"] == round(2 / 3, 3)

    def test_effectiveness_filters(self):
        """Effectiveness query filters work correctly."""
        mm = PsychologyMindMap()
        mm.record_effectiveness("NicheA", "p1", "authority", True)
        mm.record_effectiveness("NicheB", "p2", "scarcity", False)

        r = mm.get_effectiveness(niche="NicheA")
        assert r["total_records"] == 1
        assert r["filtered"] is True

        r = mm.get_effectiveness()
        assert r["total_records"] == 2
        assert r["filtered"] is False

    def test_effectiveness_summary(self):
        """get_effectiveness_summary() returns aggregate stats."""
        mm = PsychologyMindMap()
        mm.record_effectiveness("NicheA", "analytical", "authority", True)
        mm.record_effectiveness("NicheA", "analytical", "authority", True)

        s = mm.get_effectiveness_summary()
        assert s["total_attempts"] == 2
        assert s["total_successes"] == 2
        assert s["overall_conversion_rate"] == 1.0
        assert s["total_combinations_tracked"] == 1

    def test_effectiveness_summary_empty(self):
        """get_effectiveness_summary() is safe with no data."""
        mm = PsychologyMindMap()
        s = mm.get_effectiveness_summary()
        assert s["total_attempts"] == 0
        assert s["total_successes"] == 0
        assert s["overall_conversion_rate"] == 0
        assert s["best_persona"] is None
        assert s["best_principle"] is None
        assert s["best_niche"] is None


class TestAdaptiveWeights:
    """Dynamic principle weight adjustment based on effectiveness data."""

    def test_get_adjusted_weights_no_live_data(self):
        """Without live data, adjusted weights = base weights."""
        mm = PsychologyMindMap()
        w1 = mm.get_adjusted_principle_weights("Roofing Restoration")
        assert len(w1) == len(PERSUASION_PRINCIPLES)
        # All values should be < 1.0 and > 0
        for v in w1.values():
            assert 0 < v <= 1.0

    def test_get_adjusted_weights_with_live_data(self):
        """Live data adjusts weights after minimum samples."""
        mm = PsychologyMindMap()
        # Record enough data to trigger adjustment
        for i in range(5):
            mm.record_effectiveness("Roofing Restoration", "analytical", "authority", True)
        mm.record_effectiveness("Roofing Restoration", "analytical", "authority", False)

        w = mm.get_adjusted_principle_weights("Roofing Restoration")
        # Authority should be adjusted (6 attempts >= 5 min sample)
        assert "authority" in w

    def test_get_adjusted_weights_unknown_niche(self):
        """Unknown niche returns default weights."""
        mm = PsychologyMindMap()
        w = mm.get_adjusted_principle_weights("UnknownNiche")
        assert len(w) == len(PERSUASION_PRINCIPLES)


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_detect_persona_partial_match(self):
        """Partial keyword matches return the best match."""
        mm = PsychologyMindMap()
        # "prove" matches skeptical, "data" matches analytical
        r = mm.get_persona_for_lead_text("prove it with data")
        assert r["persona"] != "unknown"

    def test_mind_map_no_duplicate_nodes(self):
        """Mind map graph has no duplicate node IDs."""
        mm = PsychologyMindMap()
        graph = mm.build_mind_map()
        node_ids = [n["id"] for n in graph["nodes"]]
        assert len(node_ids) == len(set(node_ids)), "Duplicate node IDs found"

    def test_niche_profile_with_no_data(self):
        """Niche profile with no effectiveness data doesn't crash."""
        mm = PsychologyMindMap()
        bd = mm.get_niche_persona_breakdown("Roofing Restoration")
        assert bd is not None
        assert len(bd["breakdown"]) == 5  # 5 personas

    def test_record_with_empty_fields(self):
        """Recording with empty fields doesn't crash."""
        mm = PsychologyMindMap()
        mm.record_effectiveness("", "", "", True)
        r = mm.get_effectiveness()
        assert r["total_records"] == 1

    def test_unknown_niche_persona_breakdown(self):
        """Unknown niche returns valid breakdown using default profile."""
        mm = PsychologyMindMap()
        bd = mm.get_niche_persona_breakdown("Completely Unknown Niche 3000")
        assert bd is not None
        assert "error" not in bd
        assert bd["niche"] == "Completely Unknown Niche 3000"
        assert "dominant_persona" in bd
        assert "breakdown" in bd
        assert len(bd["breakdown"]) == 5  # 5 personas from default
