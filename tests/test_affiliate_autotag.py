"""
Unit tests for the multi-source affiliate auto-tag middleware logic.

Tests the real functions extracted from hub.py:
  _resolve_affiliate_code_from_request()
  _safe_utm_value()

Priority order:  cookie (affiliate_ref) > query param > body field.
Within each source: affiliate_code > ref > utm_source.
"""

import pytest
from hub import _resolve_affiliate_code_from_request, _safe_utm_value


# ── _safe_utm_value unit tests ───────────────────────────────────────


class TestSafeUtmValue:
    """Direct tests for the UTM value sanitizer."""

    def test_none_returns_none(self):
        assert _safe_utm_value(None) is None

    def test_empty_string_returns_none(self):
        assert _safe_utm_value("") is None

    def test_whitespace_only_returns_none(self):
        assert _safe_utm_value("   ") is None

    @pytest.mark.parametrize("value", [
        "(direct)", "DIRECT", "(DIRECT)", "direct",
        "organic", "ORGANIC",
        "social", "SOCIAL",
        "email", "EMAIL",
        "none", "NONE",
    ])
    def test_common_defaults_are_filtered(self, value):
        assert _safe_utm_value(value) is None, f"'{value}' should be filtered"

    @pytest.mark.parametrize("value", [
        "partner-roofing",
        "affiliate_name",
        "newsletter_affiliate",
        "social-media-campaign",
        "AffiliatePartner",
    ])
    def test_legitimate_values_pass_through(self, value):
        assert _safe_utm_value(value) == value

    def test_whitespace_is_stripped(self):
        assert _safe_utm_value("  partner-roofing  ") == "partner-roofing"


# ── Priority ordering tests ──────────────────────────────────────────


class TestPriorityOrder:
    """Cookie > query param > body field priority ordering."""

    def test_cookie_wins_over_query(self):
        assert _resolve_affiliate_code_from_request(
            cookies={"affiliate_ref": "cookie-123"},
            query_params={"affiliate_code": "query-456"},
            body={},
        ) == "cookie-123"

    def test_cookie_wins_over_body(self):
        assert _resolve_affiliate_code_from_request(
            cookies={"affiliate_ref": "cookie-123"},
            query_params={},
            body={"affiliate_code": "body-789"},
        ) == "cookie-123"

    def test_cookie_wins_over_both(self):
        assert _resolve_affiliate_code_from_request(
            cookies={"affiliate_ref": "cookie-111"},
            query_params={"affiliate_code": "query-222"},
            body={"affiliate_code": "body-333"},
        ) == "cookie-111"

    def test_query_wins_over_body(self):
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"affiliate_code": "query-abc"},
            body={"affiliate_code": "body-xyz"},
        ) == "query-abc"

    def test_body_fallback(self):
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={},
            body={"affiliate_code": "body-only"},
        ) == "body-only"

    def test_returns_none_when_no_sources(self):
        assert _resolve_affiliate_code_from_request(
            cookies={}, query_params={}, body={},
        ) is None


# ── Cookie source tests ──────────────────────────────────────────────


class TestCookieSource:
    def test_empty_cookie_falls_through(self):
        assert _resolve_affiliate_code_from_request(
            cookies={"affiliate_ref": ""},
            query_params={"affiliate_code": "query"},
            body={},
        ) == "query"

    def test_missing_cookie_key_falls_through(self):
        assert _resolve_affiliate_code_from_request(
            cookies={"other": "value"},
            query_params={"affiliate_code": "query-val"},
            body={},
        ) == "query-val"

    def test_cookie_with_special_chars(self):
        assert _resolve_affiliate_code_from_request(
            cookies={"affiliate_ref": "my-affiliate-2026"},
            query_params={},
            body={},
        ) == "my-affiliate-2026"


# ── Query param source tests ─────────────────────────────────────────


class TestQueryParamSource:
    def test_affiliate_code_param(self):
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"affiliate_code": "aff-123"},
            body={},
        ) == "aff-123"

    def test_ref_param(self):
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"ref": "ref-456"},
            body={},
        ) == "ref-456"

    def test_utm_source_param(self):
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"utm_source": "partner-roofing"},
            body={},
        ) == "partner-roofing"

    def test_affiliate_code_beats_ref(self):
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"affiliate_code": "ac-111", "ref": "ref-222"},
            body={},
        ) == "ac-111"

    def test_affiliate_code_beats_utm(self):
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"affiliate_code": "ac-333", "utm_source": "utm-444"},
            body={},
        ) == "ac-333"

    def test_ref_beats_utm(self):
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"ref": "ref-555", "utm_source": "utm-666"},
            body={},
        ) == "ref-555"

    def test_empty_query_param_is_ignored(self):
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"affiliate_code": "", "ref": "ref-777"},
            body={},
        ) == "ref-777"


# ── Body field source tests ──────────────────────────────────────────


class TestBodySource:
    def test_body_affiliate_code(self):
        assert _resolve_affiliate_code_from_request(
            cookies={}, query_params={},
            body={"affiliate_code": "body-aff-123"},
        ) == "body-aff-123"

    def test_body_ref_field(self):
        assert _resolve_affiliate_code_from_request(
            cookies={}, query_params={},
            body={"ref": "body-ref-456"},
        ) == "body-ref-456"

    def test_body_utm_source(self):
        assert _resolve_affiliate_code_from_request(
            cookies={}, query_params={},
            body={"utm_source": "body-utm-789"},
        ) == "body-utm-789"

    def test_body_priority_ordering(self):
        assert _resolve_affiliate_code_from_request(
            cookies={}, query_params={},
            body={"affiliate_code": "ac", "ref": "ref", "utm_source": "utm"},
        ) == "ac"

    def test_body_missing_keys(self):
        assert _resolve_affiliate_code_from_request(
            cookies={}, query_params={},
            body={"name": "John", "phone": "555-0100"},
        ) is None


# ── UTM filtering edge cases ─────────────────────────────────────────


class TestUTMFiltering:
    def test_direct_utm_in_query_falls_through_to_body(self):
        """Filtered (direct) UTM in query should not block body fallback."""
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"utm_source": "(direct)"},
            body={"affiliate_code": "body-ac"},
        ) == "body-ac"

    def test_direct_utm_in_body_returns_none(self):
        assert _resolve_affiliate_code_from_request(
            cookies={}, query_params={},
            body={"utm_source": "(direct)"},
        ) is None

    def test_mixed_case_utm_passes(self):
        assert _resolve_affiliate_code_from_request(
            cookies={}, query_params={},
            body={"utm_source": "AffiliatePartner"},
        ) == "AffiliatePartner"


# ── Complex edge cases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_all_sources_empty_strings(self):
        """Every source has empty/filtered values -> None."""
        assert _resolve_affiliate_code_from_request(
            cookies={"affiliate_ref": ""},
            query_params={"affiliate_code": "", "ref": "", "utm_source": "(direct)"},
            body={"affiliate_code": "", "ref": "", "utm_source": ""},
        ) is None

    def test_cookie_beats_filtered_utm(self):
        """Cookie wins even when query has a filtered UTM."""
        assert _resolve_affiliate_code_from_request(
            cookies={"affiliate_ref": "real-affiliate"},
            query_params={"utm_source": "(direct)"},
            body={},
        ) == "real-affiliate"

    def test_query_ref_without_affiliate_code(self):
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"ref": "standalone-ref"},
            body={"utm_source": "body-utm"},
        ) == "standalone-ref"

    def test_whitespace_only_body_field_not_trimmed(self):
        """Body affiliate_code/ref are NOT trimmed (only utm_source is).
        A whitespace-only string is truthy in Python, so it returns as-is."""
        assert _resolve_affiliate_code_from_request(
            cookies={}, query_params={},
            body={"affiliate_code": "   ", "ref": "real-ref"},
        ) == "   "

    def test_none_values_in_body_dict(self):
        assert _resolve_affiliate_code_from_request(
            cookies={}, query_params={},
            body={"affiliate_code": None, "ref": None, "utm_source": None},
        ) is None

    def test_complex_utm_affiliate(self):
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"utm_source": "newsletter_affiliate_program"},
            body={},
        ) == "newsletter_affiliate_program"

    def test_whitespace_utm_stripped_in_query(self):
        """Whitespace around UTM values is stripped."""
        assert _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"utm_source": "  partner-roofing  "},
            body={},
        ) == "partner-roofing"
