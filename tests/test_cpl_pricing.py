"""
tests/test_cpl_pricing.py
===========================
Unit tests for the CPLPricingEngine — a pure static class with no
external dependencies. Operates entirely on the in-memory CPL_BENCHMARKS
dictionary and _LANE_NICHE_MAP.

Tests cover all 11 public methods:
  - list_niches, get_niche, get_sub_niche, find_sub_niche
  - cpl_range, recommend_model, roi_estimate
  - suggest_sell_price, lane_pricing, margin_calculator, summary

All tests are unit-quality — the CPLPricingEngine has no external dependencies.
"""

import pytest
from empire_pricing import CPLPricingEngine, CPL_BENCHMARKS, _LANE_NICHE_MAP, cpl_engine

# ─────────────────────────────────────────────────────────────────
# INSTANCE & FIXTURES
# ─────────────────────────────────────────────────────────────────


@pytest.fixture
def engine() -> CPLPricingEngine:
    """Return a fresh CPLPricingEngine instance for each test."""
    return CPLPricingEngine()


# ═════════════════════════════════════════════════════════════════
# list_niches
# ═════════════════════════════════════════════════════════════════

class TestListNiches:

    def test_returns_sorted_list(self, engine):
        """list_niches() should return all niche names sorted alphabetically."""
        niches = engine.list_niches()
        assert isinstance(niches, list)
        assert len(niches) > 0
        assert niches == sorted(niches), "should be sorted alphabetically"
        # Spot-check known niches
        assert "Home Services" in niches
        assert "Legal" in niches
        assert "Insurance" in niches

    def test_includes_all_benchmark_keys(self, engine):
        """Every key in CPL_BENCHMARKS should appear in list_niches()."""
        niches = engine.list_niches()
        expected = set(CPL_BENCHMARKS.keys())
        assert set(niches) == expected, "list_niches should match CPL_BENCHMARKS keys"


# ═════════════════════════════════════════════════════════════════
# get_niche
# ═════════════════════════════════════════════════════════════════

class TestGetNiche:

    def test_returns_niche_data(self, engine):
        """get_niche() should return the full benchmark dict for a valid niche."""
        legal = engine.get_niche("Legal")
        assert legal is not None
        assert legal["icon"] == "⚖️"
        assert "Personal Injury" in legal.get("sub_niches", {})

    def test_returns_none_for_unknown(self, engine):
        """get_niche() should return None for a non-existent niche."""
        assert engine.get_niche("Fake Niche") is None

    def test_returns_none_for_empty_string(self, engine):
        """get_niche() should return None for empty string."""
        assert engine.get_niche("") is None

    def test_case_sensitive(self, engine):
        """get_niche() is case-sensitive — wrong case should return None."""
        assert engine.get_niche("legal") is None  # lowercase
        assert engine.get_niche("HOME SERVICES") is None  # uppercase


# ═════════════════════════════════════════════════════════════════
# get_sub_niche
# ═════════════════════════════════════════════════════════════════

class TestGetSubNiche:

    def test_returns_sub_niche_data(self, engine):
        """get_sub_niche() should return data for a valid sub-niche."""
        data = engine.get_sub_niche("Legal", "Personal Injury")
        assert data is not None
        assert "ppl" in data
        assert "ppc" in data
        assert data["best"] == "both"

    def test_returns_sub_niche_for_roofing(self, engine):
        """Roofing Restoration is its own niche — should have data."""
        data = engine.get_sub_niche("Roofing Restoration", "Roofing Restoration")
        assert data is not None
        assert data["ppl"] == (162, 228)

    def test_returns_none_for_unknown_niche(self, engine):
        """get_sub_niche() should return None if the niche doesn't exist."""
        assert engine.get_sub_niche("Fake", "Sub") is None

    def test_returns_none_for_unknown_sub_niche(self, engine):
        """get_sub_niche() should return None if the sub-niche doesn't exist."""
        assert engine.get_sub_niche("Legal", "Fake Sub") is None

    def test_returns_none_for_empty_sub_niche(self, engine):
        """get_sub_niche() should return None for empty sub-niche string."""
        assert engine.get_sub_niche("Legal", "") is None

    def test_seo_sub_niches_have_none_cpl(self, engine):
        """SEO sub-niches have None CPL ranges (service-based pricing)."""
        for sn in ["Local SEO", "E-commerce SEO", "Technical SEO"]:
            data = engine.get_sub_niche("SEO", sn)
            assert data is not None
            assert data["ppl"] == (None, None)
            assert data["ppc"] == (None, None)
            assert data["best"] == "service"


# ═════════════════════════════════════════════════════════════════
# find_sub_niche
# ═════════════════════════════════════════════════════════════════

class TestFindSubNiche:

    def test_finds_exact_match(self, engine):
        """find_sub_niche() should return (niche, sub_niche, data) for exact match."""
        found = engine.find_sub_niche("Personal Injury")
        assert found is not None
        niche, sn, data = found
        assert niche == "Legal"
        assert sn == "Personal Injury"
        assert "ppl" in data

    def test_finds_partial_match(self, engine):
        """find_sub_niche() should find by partial match (case-insensitive)."""
        found = engine.find_sub_niche("medicare")
        assert found is not None
        assert "Medicare" in found[1]  # sub_niche name contains "Medicare"

    def test_returns_none_for_no_match(self, engine):
        """find_sub_niche() should return None when nothing matches."""
        assert engine.find_sub_niche("zzzzz_not_a_real_sub_niche_999") is None

    def test_finds_addiction_treatment(self, engine):
        """Addiction Treatment is a Healthcare sub-niche — should find it."""
        found = engine.find_sub_niche("Addiction Treatment")
        assert found is not None
        assert found[0] == "Healthcare"
        assert found[1] == "Addiction Treatment"

    def test_case_insensitive(self, engine):
        """find_sub_niche() is case-insensitive."""
        found_upper = engine.find_sub_niche("PERSONAL INJURY")
        found_lower = engine.find_sub_niche("personal injury")
        found_mixed = engine.find_sub_niche("Personal Injury")
        assert found_upper == found_lower == found_mixed

    def test_empty_query_returns_none(self, engine):
        """Empty query should return None."""
        assert engine.find_sub_niche("") is None


# ═════════════════════════════════════════════════════════════════
# cpl_range
# ═════════════════════════════════════════════════════════════════

class TestCplRange:

    def test_ppl_range_for_roofing(self, engine):
        """cpl_range() should return the PPL range for Roofing."""
        data = engine.get_sub_niche("Home Services", "Roofing")
        low, high = engine.cpl_range(data, "ppl")
        assert low == 162
        assert high == 228

    def test_ppc_range_for_roofing(self, engine):
        """cpl_range() should return the PPC range for Roofing."""
        data = engine.get_sub_niche("Home Services", "Roofing")
        low, high = engine.cpl_range(data, "ppc")
        assert low == 11
        assert high == 258

    def test_ppl_range_for_plumbing(self, engine):
        """Plumbing has PPL data — should return valid range."""
        data = engine.get_sub_niche("Home Services", "Plumbing")
        low, high = engine.cpl_range(data, "ppl")
        assert low == 57
        assert high == 183

    def test_none_range_for_seo(self, engine):
        """SEO sub-niches have no CPL data — should return (None, None)."""
        data = engine.get_sub_niche("SEO", "Local SEO")
        low, high = engine.cpl_range(data, "ppl")
        assert low is None
        assert high is None

    def test_unknown_model_defaults_to_ppc(self, engine):
        """cpl_range() defaults to PPC for unrecognized model strings."""
        data = engine.get_sub_niche("Home Services", "Roofing")
        low, high = engine.cpl_range(data, "unknown_model")
        assert low == 11   # defaults to PPC range
        assert high == 258


# ═════════════════════════════════════════════════════════════════
# recommend_model
# ═════════════════════════════════════════════════════════════════

class TestRecommendModel:

    def test_recommends_both_for_roofing(self, engine):
        """Roofing's best model is 'both' — recommend_model should return that."""
        rec = engine.recommend_model("Home Services", "Roofing")
        assert rec["recommended"] == "both"
        assert rec["sub_niche"] == "Roofing"
        assert "ppl" in rec["reasoning"]
        assert "ppc" in rec["reasoning"]

    def test_recommends_ppc_for_plumbing(self, engine):
        """Plumbing's best model is 'ppc' (emergency-driven)."""
        rec = engine.recommend_model("Home Services", "Plumbing")
        assert rec["recommended"] == "ppc"
        assert rec["sub_niche"] == "Plumbing"

    def test_recommends_ppl_for_mortgage_refinance(self, engine):
        """Mortgage Refinance's best model is 'ppl' (long consideration cycle)."""
        rec = engine.recommend_model("Financial Services", "Mortgage Refinance")
        assert rec["recommended"] == "ppl"
        assert rec["sub_niche"] == "Mortgage Refinance"

    def test_recommends_service_for_seo(self, engine):
        """SEO's best model is 'service' (not a lead-gen model)."""
        rec = engine.recommend_model("SEO", "Local SEO")
        assert rec["recommended"] == "service"

    def test_returns_error_for_unknown_niche(self, engine):
        """recommend_model() should return an error dict for unknown niche."""
        rec = engine.recommend_model("Fake Niche")
        assert "error" in rec
        assert rec["error"] == "niche not found"

    def test_niche_level_recommendation_without_sub_niche(self, engine):
        """recommend_model() without sub_niche should return niche-level best model."""
        rec = engine.recommend_model("Senior Care")
        assert rec["recommended"] == "ppc"
        assert rec["sub_niche"] is None

    def test_cpl_ranges_included_in_recommendation(self, engine):
        """recommend_model() should include CPL ranges in the response."""
        rec = engine.recommend_model("Insurance", "Medicare Advantage")
        assert "cpl_ranges" in rec
        assert rec["cpl_ranges"]["ppl"]["low"] == 35
        assert rec["cpl_ranges"]["ppl"]["high"] == 85
        assert rec["cpl_ranges"]["ppc"]["low"] == 55
        assert rec["cpl_ranges"]["ppc"]["high"] == 110

    def test_sub_niche_has_notes_and_trigger(self, engine):
        """recommend_model() should include trigger and notes metadata."""
        rec = engine.recommend_model("Healthcare", "Addiction Treatment")
        assert "trigger" in rec
        assert rec["trigger"] != ""
        assert "notes" in rec


# ═════════════════════════════════════════════════════════════════
# roi_estimate
# ═════════════════════════════════════════════════════════════════

class TestRoiEstimate:

    def test_roi_basic_calculation(self, engine):
        """roi_estimate() should calculate a reasonable ROI for a valid niche."""
        roi = engine.roi_estimate("Roofing Restoration", "Roofing Restoration",
                                  monthly_volume=100, model="ppl")
        assert roi["niche"] == "Roofing Restoration"
        assert roi["sub_niche"] == "Roofing Restoration"
        assert roi["cpl_midpoint"] == 195.0  # (162 + 228) / 2
        assert roi["monthly_volume"] == 100
        assert roi["monthly_acquisition_cost"] == 19500.0  # 195 × 100
        assert roi["sell_price_per_lead"] == 487.5  # 195 × 2.5
        assert roi["close_rate"] == 0.15  # PPL default
        assert roi["monthly_revenue"] == 7312.5  # 487.5 × 100 × 0.15
        assert roi["gross_margin"] == -12187.5  # 7312.5 - 19500
        assert roi["breakeven_volume"] == 267  # ceil(19500 / (487.5 × 0.15)) = ceil(266.67) = 267
        assert "roi_percentage" in roi

    def test_roi_with_ppc_model(self, engine):
        """PPC model should use PPC CPL range and higher close rate (0.30)."""
        roi = engine.roi_estimate("Roofing Restoration", "Roofing Restoration",
                                  monthly_volume=100, model="ppc")
        assert roi["model"] == "ppc"
        assert roi["cpl_midpoint"] == 134.5  # (11 + 258) / 2
        assert roi["close_rate"] == 0.30
        assert roi["breakeven_volume"] > 0

    def test_roi_with_custom_sell_price(self, engine):
        """roi_estimate() should accept a custom sell_price_per_lead."""
        roi = engine.roi_estimate("Legal", "Personal Injury",
                                  sell_price_per_lead=1000.0,
                                  monthly_volume=50, model="ppl")
        assert roi["sell_price_per_lead"] == 1000.0
        assert roi["monthly_revenue"] == 7500.0  # 1000 × 50 × 0.15

    def test_roi_falls_back_to_first_sub_niche(self, engine):
        """roi_estimate() without a sub_niche should fall back to first sub-niche."""
        roi = engine.roi_estimate("Insurance")
        assert roi["sub_niche"] is not None
        assert roi["cpl_midpoint"] > 0

    def test_roi_returns_error_for_unknown(self, engine):
        """roi_estimate() should return an error dict for unknown niche."""
        roi = engine.roi_estimate("Fake Niche")
        assert "error" in roi

    def test_roi_breakeven_increases_with_lower_sell_price(self, engine):
        """Lower sell price should require more volume to break even."""
        roi_low = engine.roi_estimate("Roofing Restoration", "Roofing Restoration",
                                       sell_price_per_lead=300.0, model="ppl")
        roi_high = engine.roi_estimate("Roofing Restoration", "Roofing Restoration",
                                        sell_price_per_lead=600.0, model="ppl")
        assert roi_low["breakeven_volume"] > roi_high["breakeven_volume"]

    def test_roi_ppl_vs_ppc_tradeoff(self, engine):
        """PPL should have lower CPL but lower close rate than PPC. Both should yield valid breakevens."""
        roi_ppl = engine.roi_estimate("Legal", "Class Action", model="ppl")
        roi_ppc = engine.roi_estimate("Legal", "Class Action", model="ppc")
        assert roi_ppl["close_rate"] < roi_ppc["close_rate"]
        assert roi_ppl["breakeven_volume"] > 0
        assert roi_ppc["breakeven_volume"] > 0


# ═════════════════════════════════════════════════════════════════
# suggest_sell_price
# ═════════════════════════════════════════════════════════════════

class TestSuggestSellPrice:

    def test_suggested_price_with_default_margin(self, engine):
        """suggest_sell_price() should calculate using formula CPL / (1 - margin)."""
        result = engine.suggest_sell_price("Roofing Restoration", "Roofing Restoration",
                                           target_margin_pct=60.0, model="ppl")
        # CPL midpoint = (162 + 228) / 2 = 195
        # Suggested = 195 / (1 - 0.60) = 195 / 0.40 = 487.5
        assert result["cpl_midpoint"] == 195.0
        assert result["suggested_sell_price"] == 487.5
        assert result["target_margin_pct"] == 60.0
        assert result["actual_margin_pct"] == 60.0
        assert result["markup_multiple"] == 2.5  # 487.5 / 195

    def test_suggested_price_with_different_margin(self, engine):
        """A 70% target margin should produce a higher sell price."""
        result = engine.suggest_sell_price("Roofing Restoration", "Roofing Restoration",
                                           target_margin_pct=70.0, model="ppl")
        # 195 / (1 - 0.70) = 195 / 0.30 = 650.0
        assert result["suggested_sell_price"] == 650.0
        assert result["markup_multiple"] == pytest.approx(3.33, rel=0.01)

    def test_suggested_price_lower_margin(self, engine):
        """A 40% target margin should produce a lower sell price."""
        result = engine.suggest_sell_price("Roofing Restoration", "Roofing Restoration",
                                           target_margin_pct=40.0, model="ppl")
        # 195 / (1 - 0.40) = 195 / 0.60 = 325.0
        assert result["suggested_sell_price"] == 325.0

    def test_returns_error_for_unknown_sub_niche(self, engine):
        """suggest_sell_price() should return error dict for unknown sub-niche."""
        result = engine.suggest_sell_price("Legal", "Fake Sub")
        assert "error" in result

    def test_ppc_model_pricing(self, engine):
        """suggest_sell_price() should work with PPC model."""
        result = engine.suggest_sell_price("Home Services", "Plumbing",
                                           target_margin_pct=60.0, model="ppc")
        # PPC CPL for Plumbing = (14 + 150) / 2 = 82
        # Suggested = 82 / 0.40 = 205.0
        assert result["cpl_midpoint"] == 82.0
        assert result["suggested_sell_price"] == 205.0

    def test_suggested_price_formula_included(self, engine):
        """suggest_sell_price() should include the formula string."""
        result = engine.suggest_sell_price("Roofing Restoration", "Roofing Restoration")
        assert "formula" in result
        assert "/" in result["formula"]


# ═════════════════════════════════════════════════════════════════
# lane_pricing
# ═════════════════════════════════════════════════════════════════

class TestLanePricing:

    def test_all_38_lanes_returned(self, engine):
        """lane_pricing() should return data for all 38 lanes."""
        result = engine.lane_pricing()
        assert result["total_lanes"] == 38
        assert len(result["lanes"]) == 38

    def test_lane_0_roofing(self, engine):
        """Lane 0 should be Roofing Restoration with valid CPL data."""
        result = engine.lane_pricing()
        lane0 = result["lanes"][0]
        assert lane0["lane_id"] == 0
        assert lane0["niche"] == "Roofing Restoration"
        assert lane0["sub_niche"] == "Roofing Restoration"
        assert lane0["cpl_available"] is True
        assert lane0["cpl"]["ppl"]["low"] == 162
        assert lane0["cpl"]["ppl"]["high"] == 228

    def test_lane_10_legal(self, engine):
        """Lane 10 should be Legal/Personal Injury with CPL data."""
        result = engine.lane_pricing()
        lane10 = next(l for l in result["lanes"] if l["lane_id"] == 10)
        assert lane10["niche"] == "Legal"
        assert lane10["sub_niche"] == "Personal Injury"
        assert lane10["cpl_available"] is True
        assert lane10["cpl"]["ppl"]["low"] == 250

    def test_seo_lanes_have_no_cpl(self, engine):
        """SEO lanes (7-9) have service-based pricing — cpl_available should be False."""
        result = engine.lane_pricing()
        for lid in [7, 8, 9]:
            lane = next(l for l in result["lanes"] if l["lane_id"] == lid)
            assert lane["cpl_available"] is False

    def test_lane_has_notes_and_trigger(self, engine):
        """Lanes with CPL data should include trigger and notes fields."""
        result = engine.lane_pricing()
        lane0 = next(l for l in result["lanes"] if l["lane_id"] == 0)
        assert "trigger" in lane0
        assert "notes" in lane0

    def test_lane_has_strategy_and_best_model(self, engine):
        """Each lane should include strategy and best_model fields."""
        result = engine.lane_pricing()
        lane0 = result["lanes"][0]
        assert lane0["strategy"] == "AGGRESSIVE_STRIKE"
        assert lane0["best_model"] is not None

    def test_every_lane_has_unique_lane_id(self, engine):
        """Each lane should have a unique lane_id."""
        result = engine.lane_pricing()
        ids = [l["lane_id"] for l in result["lanes"]]
        assert len(ids) == len(set(ids)), "lane IDs should be unique"
        assert sorted(ids) == list(range(38))

    def test_lane_roi_included(self, engine):
        """Each lane should include ROI data (except SEO/service lanes)."""
        result = engine.lane_pricing(model="ppl", monthly_volume=100)
        lane0 = result["lanes"][0]
        assert "roi" in lane0
        assert "monthly_acquisition_cost" in lane0["roi"]

    def test_lane_suggested_pricing_included(self, engine):
        """Each lane should include suggested_pricing (except SEO)."""
        result = engine.lane_pricing()
        lane10 = next(l for l in result["lanes"] if l["lane_id"] == 10)
        assert "suggested_pricing" in lane10
        assert lane10["suggested_pricing"]["target_margin_pct"] == 60.0

    def test_all_38_lanes_match_expected_niches(self, engine):
        """Verify that all 38 lanes have the expected niche assignments."""
        result = engine.lane_pricing()
        expected = {
            0: "Roofing Restoration", 5: "HVAC", 7: "SEO", 10: "Legal",
            15: "Insurance", 18: "Financial Services", 20: "Consumer CPA",
            22: "Senior Care",            24: "Healthcare", 25: "Education",
            27: "Healthcare", 29: "Business Services", 34: "Home Services",
            35: "Home Services", 36: "Home Services", 37: "Home Services",
        }
        for lid, expected_niche in expected.items():
            lane = next(l for l in result["lanes"] if l["lane_id"] == lid)
            assert lane["niche"] == expected_niche, f"Lane {lid} should be {expected_niche}"


# ═════════════════════════════════════════════════════════════════
# margin_calculator
# ═════════════════════════════════════════════════════════════════

class TestMarginCalculator:

    def test_margin_basic_calculation(self, engine):
        """margin_calculator() should compute margin/profit at a given sell price."""
        m = engine.margin_calculator("Roofing Restoration", "Roofing Restoration",
                                     sell_price=500.0, monthly_volume=100, model="ppl")
        # CPL midpoint = 195. Acquisition = 195 * 100 = 19,500
        # Revenue = 500 * 100 = 50,000
        # Profit = 50,000 - 19,500 = 30,500
        # Margin = 30,500 / 50,000 = 61.0%
        assert m["cpl_midpoint"] == 195.0
        assert m["sell_price"] == 500.0
        assert m["markup_multiple"] == pytest.approx(2.56, rel=0.01)
        assert m["monthly_volume"] == 100
        assert m["monthly_acquisition_cost"] == 19500.0
        assert m["monthly_revenue"] == 50000.0
        assert m["monthly_gross_profit"] == 30500.0
        assert m["margin_pct"] == pytest.approx(61.0, rel=0.01)
        assert m["annual_revenue"] == 600000.0
        assert m["annual_profit"] == 366000.0

    def test_margin_at_cost(self, engine):
        """If sell_price equals CPL midpoint, margin should be 0%."""
        m = engine.margin_calculator("Roofing Restoration", "Roofing Restoration",
                                     sell_price=195.0, monthly_volume=50, model="ppl")
        assert m["margin_pct"] == 0.0
        assert m["monthly_gross_profit"] == 0.0

    def test_margin_below_cost(self, engine):
        """If sell_price is below CPL midpoint, margin should be negative."""
        m = engine.margin_calculator("Roofing Restoration", "Roofing Restoration",
                                     sell_price=100.0, monthly_volume=50, model="ppl")
        assert m["margin_pct"] < 0

    def test_margin_with_ppc_model(self, engine):
        """margin_calculator() should work with PPC model."""
        m = engine.margin_calculator("Home Services", "Plumbing",
                                     sell_price=250.0, monthly_volume=100, model="ppc")
        assert m["model"] == "ppc"
        assert m["monthly_gross_profit"] > 0

    def test_margin_scales_with_volume(self, engine):
        """Doubling volume should double acquisition cost, revenue, and profit."""
        m1 = engine.margin_calculator("Legal", "Personal Injury",
                                       sell_price=800.0, monthly_volume=100, model="ppl")
        m2 = engine.margin_calculator("Legal", "Personal Injury",
                                       sell_price=800.0, monthly_volume=200, model="ppl")
        assert m2["monthly_acquisition_cost"] == 2 * m1["monthly_acquisition_cost"]
        assert m2["monthly_revenue"] == 2 * m1["monthly_revenue"]
        assert m2["monthly_gross_profit"] == 2 * m1["monthly_gross_profit"]
        # Margin % should be the same (scales linearly)
        assert m2["margin_pct"] == m1["margin_pct"]

    def test_returns_error_for_unknown(self, engine):
        """margin_calculator() should return error dict for unknown sub-niche."""
        m = engine.margin_calculator("Fake", "Sub", sell_price=100.0)
        assert "error" in m

    def test_returns_error_for_no_cpl_data(self, engine):
        """margin_calculator() should return error for niche with no CPL data (SEO)."""
        m = engine.margin_calculator("SEO", "Local SEO", sell_price=500.0, model="ppl")
        assert "error" in m


# ═════════════════════════════════════════════════════════════════
# summary
# ═════════════════════════════════════════════════════════════════

class TestSummary:

    def test_summary_returns_all_niches(self, engine):
        """summary() should return data for all niches."""
        s = engine.summary()
        assert len(s) == len(CPL_BENCHMARKS)
        assert "Home Services" in s
        assert "SEO" in s

    def test_summary_has_key_fields(self, engine):
        """Each niche in summary should have expected fields."""
        s = engine.summary()
        home = s["Home Services"]
        assert "icon" in home
        assert "sub_niche_count" in home
        assert "best_model" in home
        assert "volume" in home
        assert home["sub_niche_count"] == 11  # Home Services has 11 sub-niches
        assert home["best_model"] == "both"
        assert home["volume"] == "highest"

    def test_summary_avg_cpl_values(self, engine):
        """Average CPL values should be reasonable positive numbers."""
        s = engine.summary()
        for niche_name, data in s.items():
            if data["avg_cpl_ppl"] is not None:
                assert data["avg_cpl_ppl"] > 0
            if data["avg_cpl_ppc"] is not None:
                assert data["avg_cpl_ppc"] > 0

    def test_summary_seo_has_no_avg_cpl(self, engine):
        """SEO is service-based — should not have avg CPL values."""
        seo = engine.summary()["SEO"]
        assert seo["avg_cpl_ppl"] is None
        assert seo["avg_cpl_ppc"] is None
        assert seo["best_model"] == "service"

    def test_summary_sub_niche_counts_correct(self, engine):
        """Sub-niche counts should match CPL_BENCHMARKS structure."""
        s = engine.summary()
        for niche_name, data in s.items():
            expected_count = len(CPL_BENCHMARKS[niche_name].get("sub_niches", {}))
            assert data["sub_niche_count"] == expected_count, \
                f"{niche_name}: expected {expected_count} sub-niches, got {data['sub_niche_count']}"


# ═════════════════════════════════════════════════════════════════
# CONVENIENCE ALIAS
# ═════════════════════════════════════════════════════════════════

class TestConvenienceAlias:

    def test_cpl_engine_is_instance(self):
        """cpl_engine should be a CPLPricingEngine instance."""
        from empire_pricing import cpl_engine
        assert isinstance(cpl_engine, CPLPricingEngine)

    def test_cpl_engine_works(self):
        """cpl_engine convenience alias should work for all methods."""
        from empire_pricing import cpl_engine
        assert len(cpl_engine.list_niches()) > 0
        assert cpl_engine.get_niche("Legal") is not None
        assert "recommended" in cpl_engine.recommend_model("Home Services", "Roofing")


# ═════════════════════════════════════════════════════════════════
# MATHEMATICAL CORRECTNESS — CROSS-CHECKING FORMULAS
# ═════════════════════════════════════════════════════════════════

class TestMathematicalCorrectness:

    def test_suggest_sell_price_inverse_margin(self, engine):
        """If we suggest a price at 60% margin, margin_calculator should return ~60%."""
        suggest = engine.suggest_sell_price("Roofing Restoration", "Roofing Restoration",
                                            target_margin_pct=60.0, model="ppl")
        margin = engine.margin_calculator("Roofing Restoration", "Roofing Restoration",
                                           sell_price=suggest["suggested_sell_price"],
                                           monthly_volume=100, model="ppl")
        assert margin["margin_pct"] == pytest.approx(60.0, abs=0.1)

    def test_breakeven_scales_linear_with_volume(self, engine):
        """Doubling monthly volume should double the breakeven volume (linear scaling)."""
        roi_100 = engine.roi_estimate("Roofing Restoration", "Roofing Restoration",
                                       monthly_volume=100, model="ppl")
        roi_200 = engine.roi_estimate("Roofing Restoration", "Roofing Restoration",
                                       monthly_volume=200, model="ppl")
        # Acquisition cost doubles, per-unit revenue stays same → breakeven doubles
        # 100 leads: ceil(19500 / 73.125) = ceil(266.67) = 267
        # 200 leads: ceil(39000 / 73.125) = ceil(533.33) = 534
        assert roi_100["breakeven_volume"] == 267
        assert roi_200["breakeven_volume"] == 534

    def test_breakeven_formula(self, engine):
        """Breakeven volume = ceil(acquisition_cost / (sell_price × close_rate))."""
        roi = engine.roi_estimate("Legal", "Personal Injury",
                                   sell_price_per_lead=1000.0,
                                   monthly_volume=50, model="ppl")
        # CPL midpoint = (250 + 600) / 2 = 425
        # acq = 425 * 50 = 21250
        # rev_per_sold = 1000 * 0.15 = 150
        # breakeven = ceil(21250 / 150) = ceil(141.67) = 142
        assert roi["breakeven_volume"] == 142

    def test_markup_multiple_correct(self, engine):
        """Markup multiple = sell_price / CPL midpoint."""
        suggest = engine.suggest_sell_price("Roofing Restoration", "Roofing Restoration",
                                            target_margin_pct=60.0, model="ppl")
        # markup = 487.5 / 195.0 = 2.5
        assert suggest["markup_multiple"] == pytest.approx(2.5, rel=0.01)

    def test_suggested_price_at_various_margins_monotonic(self, engine):
        """Higher target margin should always produce a higher suggested sell price."""
        margins = [10, 20, 30, 40, 50, 60, 70, 80]
        prices = []
        for m in margins:
            result = engine.suggest_sell_price("Roofing Restoration", "Roofing Restoration",
                                                target_margin_pct=float(m), model="ppl")
            prices.append(result["suggested_sell_price"])
        # Each subsequent price should be higher (monotonically increasing)
        assert all(prices[i] < prices[i+1] for i in range(len(prices)-1)), \
            f"Prices should increase with margin: {prices}"


# ═════════════════════════════════════════════════════════════════
# IDEMPOTENCY & CONCURRENCY — AUTO-REFRESH SAFETY
# ═════════════════════════════════════════════════════════════════
# These tests validate the backend guarantees that the frontend auto-refresh
# (30s polling of /api/v1/cpl/lanes) depends on:
#   1. Idempotency — same params always produce identical results
#   2. Rapid calls — no state mutation between calls
#   3. Volume independence — lane structure doesn't change with volume
#   4. Model consistency — PPL and PPC share the same lane structure
#   5. Cross-model data — lanes that support both have both PPL and PPC CPL data


class TestIdempotencyAndConcurrency:
    """
    Tests for the auto-refresh safety guarantees:
    idempotency, rapid sequential calls, volume stability, model consistency.
    """

    def test_idempotent_calls_return_identical_data(self, engine):
        """Two calls with identical params should return identical lane data."""
        r1 = engine.lane_pricing(model="both", monthly_volume=100)
        r2 = engine.lane_pricing(model="both", monthly_volume=100)
        assert r1["total_lanes"] == r2["total_lanes"]
        for i in range(38):
            assert r1["lanes"][i]["lane_id"] == r2["lanes"][i]["lane_id"]
            assert r1["lanes"][i]["niche"] == r2["lanes"][i]["niche"]
            assert r1["lanes"][i]["cpl_available"] == r2["lanes"][i]["cpl_available"]
            if r1["lanes"][i]["cpl_available"]:
                assert r1["lanes"][i]["cpl"] == r2["lanes"][i]["cpl"]

    def test_rapid_sequential_calls_all_valid(self, engine):
        """10 rapid sequential calls (simulating 5 min of 30s auto-refresh) should all return valid data."""
        for i in range(10):
            result = engine.lane_pricing(model="both", monthly_volume=100)
            assert len(result["lanes"]) == 38, f"Call {i}: expected 38 lanes, got {len(result['lanes'])}"
            # Every lane should have a valid structure
            for lane in result["lanes"]:
                assert "lane_id" in lane
                assert "niche" in lane
                assert "sub_niche" in lane
                assert "cpl_available" in lane
                if lane["cpl_available"]:
                    assert "cpl" in lane
                    assert "roi" in lane
                    assert "suggested_pricing" in lane

    def test_different_volumes_same_lane_structure(self, engine):
        """Different monthly_volume values should not change lane structure or IDs."""
        volumes = [1, 10, 50, 100, 500, 1000, 10000]
        reference = engine.lane_pricing(model="both", monthly_volume=100)
        for vol in volumes:
            result = engine.lane_pricing(model="both", monthly_volume=vol)
            assert result["total_lanes"] == reference["total_lanes"]
            for i in range(38):
                assert result["lanes"][i]["lane_id"] == reference["lanes"][i]["lane_id"]
                assert result["lanes"][i]["niche"] == reference["lanes"][i]["niche"]
                assert result["lanes"][i]["cpl_available"] == reference["lanes"][i]["cpl_available"]
                # CPL data should be identical regardless of volume
                if result["lanes"][i]["cpl_available"]:
                    assert result["lanes"][i]["cpl"] == reference["lanes"][i]["cpl"]

    def test_ppl_and_ppc_models_same_lane_structure(self, engine):
        """PPL and PPC models should produce the same lane IDs and structure."""
        ppl = engine.lane_pricing(model="ppl", monthly_volume=100)
        ppc = engine.lane_pricing(model="ppc", monthly_volume=100)
        assert ppl["total_lanes"] == ppc["total_lanes"]
        for i in range(38):
            assert ppl["lanes"][i]["lane_id"] == ppc["lanes"][i]["lane_id"]
            assert ppl["lanes"][i]["niche"] == ppc["lanes"][i]["niche"]
            assert ppl["lanes"][i]["cpl_available"] == ppc["lanes"][i]["cpl_available"]
            # Lane structure is always the same regardless of query model
            # best_model reflects the stored value, not the query param

    def test_lanes_with_both_models_have_ppl_and_ppc_cpl(self, engine):
        """Lanes with CPL data should have both PPL and PPC data in their cpl dict."""
        result = engine.lane_pricing(model="both", monthly_volume=100)
        priced = [l for l in result["lanes"] if l["cpl_available"]]
        assert len(priced) > 0
        for lane in priced:
            assert "cpl" in lane
            assert "ppl" in lane["cpl"], f"Lane {lane['lane_id']}: expected PPL data"
            assert "ppc" in lane["cpl"], f"Lane {lane['lane_id']}: expected PPC data"
            assert lane["cpl"]["ppl"]["low"] is not None
            assert lane["cpl"]["ppc"]["low"] is not None

    def test_service_lanes_consistent_across_calls(self, engine):
        """Service lanes (SEO) should be consistently marked and have no CPL data."""
        for _ in range(5):
            result = engine.lane_pricing(model="both", monthly_volume=100)
            # Service lanes are identified by cpl_available=False, not best_model
            service_lanes = [l for l in result["lanes"] if not l["cpl_available"]]
            assert len(service_lanes) == 3, f"Expected 3 service lanes, got {len(service_lanes)}"
            for lane in service_lanes:
                assert lane["cpl_available"] is False
                assert lane["niche"] == "SEO"
                assert lane["strategy"] is not None

    def test_lane_ids_stable_across_model_switches(self, engine):
        """Lane IDs should be stable whether querying PPL, PPC, or both models."""
        models = ["both", "ppl", "ppc"]
        references = {}
        for m in models:
            r = engine.lane_pricing(model=m, monthly_volume=100)
            references[m] = {l["lane_id"]: l["niche"] for l in r["lanes"]}
        # All model views should have the same lane_id -> niche mapping
        assert references["both"] == references["ppl"] == references["ppc"]

    def test_no_state_leak_between_calls(self, engine):
        """Calling with different params should not affect subsequent calls (no mutable state)."""
        engine.lane_pricing(model="ppl", monthly_volume=9999)
        engine.lane_pricing(model="ppc", monthly_volume=1)
        # Subsequent call should be clean
        result = engine.lane_pricing(model="both", monthly_volume=100)
        assert result["total_lanes"] == 38
        lane0 = result["lanes"][0]
        assert lane0["cpl"]["ppl"]["low"] == 162  # Roofing data should be intact
        assert lane0["cpl"]["ppc"]["low"] == 11
