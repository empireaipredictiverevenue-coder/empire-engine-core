"""
Property-based tests for the multi-source affiliate auto-tag logic.

Uses Hypothesis to generate random inputs and verify invariants that
hold for any valid input, catching edge cases that example-based tests
might miss.
"""

from hypothesis import given, assume, settings, HealthCheck, strategies as st
from empire_affiliate_utils import _resolve_affiliate_code_from_request, _safe_utm_value

# ── Text strategies ─────────────────────────────────────────────────
# Affiliate code / ref values: arbitrary non-empty strings that won't
# produce false collisions with filtered UTM values.
_aff_code = st.text(
    min_size=1,
    max_size=40,
    alphabet=st.characters(blacklist_categories=("Cs",), whitelist_categories=("L", "N", "P", "S")),
    # Avoid generating values that look like filtered UTM defaults
).filter(lambda s: s.strip() and s.strip().lower() not in {
    "(direct)", "direct", "organic", "social", "email", "none",
})

# Any text including empty, whitespace, etc.
_any_text = st.text(max_size=40)

# ── Dict strategies ──────────────────────────────────────────────────
# Dictionaries that may or may not contain the relevant keys.

@st.composite
def _three_sources(draw):
    """Draw (cookies, query_params, body) with random values."""
    cookies = draw(st.dictionaries(
        st.sampled_from(["affiliate_ref", "session", "other"]),
        st.one_of(st.none(), _any_text),
        min_size=0, max_size=5,
    ))
    query_keys = st.sampled_from(
        ["affiliate_code", "ref", "utm_source", "page", "source", "campaign"]
    )
    query_params = draw(st.dictionaries(query_keys, st.one_of(st.none(), _any_text), min_size=0, max_size=8))
    body_keys = st.sampled_from(
        ["affiliate_code", "ref", "utm_source", "name", "phone", "email", "metro"]
    )
    body = draw(st.dictionaries(body_keys, st.one_of(st.none(), _any_text), min_size=0, max_size=8))
    return cookies, query_params, body


# ═══════════════════════════════════════════════════════════════════
# PROPERTY: COOKIE PRIORITY
# ═══════════════════════════════════════════════════════════════════


class TestCookiePriority:
    """If cookie has a non-empty affiliate_ref, it must always win."""

    @given(
        aff_ref=_aff_code,
        query_params=st.dictionaries(
            st.sampled_from(["affiliate_code", "ref", "utm_source"]),
            _any_text, min_size=0, max_size=6,
        ),
        body=st.dictionaries(
            st.sampled_from(["affiliate_code", "ref", "utm_source"]),
            _any_text, min_size=0, max_size=6,
        ),
    )
    def test_cookie_wins_over_query_and_body(self, aff_ref, query_params, body):
        result = _resolve_affiliate_code_from_request(
            cookies={"affiliate_ref": aff_ref},
            query_params=query_params,
            body=body,
        )
        assert result == aff_ref, (
            f"Cookie '{aff_ref}' should win over query={query_params} body={body}"
        )

    @given(_three_sources())
    @settings(suppress_health_check=[HealthCheck.filter_too_much])
    def test_cookie_value_is_returned_as_is(self, sources):
        cookies, query_params, body = sources
        aff_ref = cookies.get("affiliate_ref")
        assume(aff_ref and aff_ref.strip())
        result = _resolve_affiliate_code_from_request(
            cookies=cookies, query_params=query_params, body=body,
        )
        assert result == aff_ref


# ═══════════════════════════════════════════════════════════════════
# PROPERTY: EMPTY/MISSING COOKIE FALLS THROUGH
# ═══════════════════════════════════════════════════════════════════


class TestCookieFallthrough:
    """When cookie is empty/missing, the next source is checked."""

    @given(query_code=_aff_code, body_code=_aff_code)
    def test_missing_cookie_checks_query(self, query_code, body_code):
        result = _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"affiliate_code": query_code},
            body={"affiliate_code": body_code},
        )
        assert result == query_code

    @given(query_code=_aff_code, body_code=_aff_code)
    def test_empty_cookie_checks_query(self, query_code, body_code):
        result = _resolve_affiliate_code_from_request(
            cookies={"affiliate_ref": "", "session": "abc"},
            query_params={"affiliate_code": query_code},
            body={"affiliate_code": body_code},
        )
        assert result == query_code

    @given(cookies=st.dictionaries(st.text(min_size=1), _any_text, min_size=0, max_size=5))
    def test_no_affiliate_ref_key_falls_through(self, cookies):
        assume("affiliate_ref" not in cookies)
        result = _resolve_affiliate_code_from_request(
            cookies=cookies,
            query_params={"affiliate_code": "fallback-val"},
            body={},
        )
        assert result == "fallback-val"


# ═══════════════════════════════════════════════════════════════════
# PROPERTY: WITHIN-SOURCE PRIORITY (QUERY PARAMS)
# ═══════════════════════════════════════════════════════════════════


class TestQueryParamPriority:
    """Query param priority: affiliate_code > ref > utm_source."""

    @given(
        affiliate_code=_aff_code,
        ref_val=_aff_code,
    )
    def test_affiliate_code_beats_ref(self, affiliate_code, ref_val):
        result = _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"affiliate_code": affiliate_code, "ref": ref_val},
            body={},
        )
        assert result == affiliate_code

    @given(
        affiliate_code=_aff_code,
        utm_val=_aff_code,
    )
    def test_affiliate_code_beats_utm(self, affiliate_code, utm_val):
        result = _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"affiliate_code": affiliate_code, "utm_source": utm_val},
            body={},
        )
        assert result == affiliate_code

    @given(ref_val=_aff_code, utm_val=_aff_code)
    def test_ref_beats_utm(self, ref_val, utm_val):
        result = _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"ref": ref_val, "utm_source": utm_val},
            body={},
        )
        assert result == ref_val

    @given(utm_val=_aff_code)
    def test_utm_fallback(self, utm_val):
        """When only utm_source is present, it must be returned (stripped)."""
        expected = _safe_utm_value(utm_val)
        result = _resolve_affiliate_code_from_request(
            cookies={},
            query_params={"utm_source": utm_val},
            body={},
        )
        assert result == expected, f"Expected {expected!r}, got {result!r}"


# ═══════════════════════════════════════════════════════════════════
# PROPERTY: WITHIN-SOURCE PRIORITY (BODY)
# ═══════════════════════════════════════════════════════════════════


class TestBodyPriority:
    """Body field priority: affiliate_code > ref > utm_source."""

    @given(affiliate_code=_aff_code, ref_val=_aff_code)
    def test_affiliate_code_beats_ref(self, affiliate_code, ref_val):
        result = _resolve_affiliate_code_from_request(
            cookies={}, query_params={},
            body={"affiliate_code": affiliate_code, "ref": ref_val},
        )
        assert result == affiliate_code

    @given(affiliate_code=_aff_code, utm_val=_aff_code)
    def test_affiliate_code_beats_utm(self, affiliate_code, utm_val):
        result = _resolve_affiliate_code_from_request(
            cookies={}, query_params={},
            body={"affiliate_code": affiliate_code, "utm_source": utm_val},
        )
        assert result == affiliate_code

    @given(ref_val=_aff_code, utm_val=_aff_code)
    def test_ref_beats_utm(self, ref_val, utm_val):
        result = _resolve_affiliate_code_from_request(
            cookies={}, query_params={},
            body={"ref": ref_val, "utm_source": utm_val},
        )
        assert result == ref_val


# ═══════════════════════════════════════════════════════════════════
# PROPERTY: NOISE INVARIANCE
# ═══════════════════════════════════════════════════════════════════


class TestNoiseInvariance:
    """Adding unrelated keys does not change the result."""

    @given(
        extra_cookie_keys=st.dictionaries(
            st.text(min_size=1, max_size=10).filter(
                lambda k: k != "affiliate_ref"
            ),
            _any_text, min_size=1, max_size=5,
        ),
    )
    def test_noise_keys_in_cookies_do_not_affect_body_fallback(self, extra_cookie_keys):
        """Extra cookie keys shouldn't prevent body fallback."""
        cookies = {**extra_cookie_keys, "affiliate_ref": ""}
        result = _resolve_affiliate_code_from_request(
            cookies=cookies, query_params={},
            body={"affiliate_code": "body-value"},
        )
        assert result == "body-value"

    @given(
        extra_query_keys=st.dictionaries(
            st.text(min_size=1, max_size=10).filter(
                lambda k: k not in ("affiliate_code", "ref", "utm_source")
            ),
            _any_text, min_size=1, max_size=5,
        ),
    )
    def test_noise_in_query_does_not_affect_body(self, extra_query_keys):
        query_params = {**extra_query_keys}
        result = _resolve_affiliate_code_from_request(
            cookies={}, query_params=query_params,
            body={"affiliate_code": "body-val"},
        )
        assert result == "body-val"


# ═══════════════════════════════════════════════════════════════════
# PROPERTY: ALL-EMPTY RETURNS NONE
# ═══════════════════════════════════════════════════════════════════


class TestAllEmpty:
    """When all sources are empty/missing, result must be None."""

    @given(
        cookies=st.dictionaries(st.text(min_size=1), st.none() | st.just(""), min_size=0, max_size=5),
        query_params=st.dictionaries(st.text(min_size=1), st.none() | st.just(""), min_size=0, max_size=5),
        body=st.dictionaries(st.text(min_size=1), st.none() | st.just(""), min_size=0, max_size=5),
    )
    def test_empty_values_return_none(self, cookies, query_params, body):
        result = _resolve_affiliate_code_from_request(
            cookies=cookies, query_params=query_params, body=body,
        )
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# PROPERTY: _safe_utm_value INVARIANTS
# ═══════════════════════════════════════════════════════════════════


class TestSafeUtmValueProperties:
    """Invariants for the UTM value sanitizer."""

    @given(value=st.none() | st.just("") | st.text(max_size=10).filter(lambda s: s.strip() == ""))
    def test_empty_or_whitespace_returns_none(self, value):
        assert _safe_utm_value(value) is None

    @given(
        st.sampled_from([
            "(direct)", "direct", "DIRECT", "(DIRECT)", "Direct",
            "organic", "ORGANIC", "Organic",
            "social", "SOCIAL", "Social",
            "email", "EMAIL", "Email",
            "none", "NONE", "None",
        ])
    )
    def test_filtered_values_return_none(self, value):
        assert _safe_utm_value(value) is None, f"Expected None for '{value}'"

    @given(value=_aff_code)
    def test_invalid_values_stripped_passthrough(self, value):
        """Legitimate values pass through (stripped but unchanged)."""
        result = _safe_utm_value(value)
        assert result == value.strip()

    @given(value=_aff_code)
    def test_whitespace_is_stripped(self, value):
        """Leading/trailing whitespace is stripped."""
        result = _safe_utm_value("  " + value + "  ")
        assert result == value.strip()

    @given(value=_aff_code)
    def test_idempotent(self, value):
        """Applying _safe_utm_value twice is idempotent."""
        once = _safe_utm_value(value)
        twice = _safe_utm_value(once)
        assert once == twice


# ═══════════════════════════════════════════════════════════════════
# PROPERTY: FULL PIPELINE WITH RANDOM DISTRIBUTION
# ═══════════════════════════════════════════════════════════════════


class TestRandomDistribution:
    """Fuzz the full function with random inputs and verify no crashes."""

    @given(
        cookies=st.dictionaries(st.text(max_size=20), _any_text, min_size=0, max_size=10),
        query_params=st.dictionaries(st.text(max_size=20), _any_text, min_size=0, max_size=10),
        body=st.dictionaries(st.text(max_size=20), _any_text, min_size=0, max_size=10),
    )
    def test_fuzz_no_crash(self, cookies, query_params, body):
        """Never crashes, always returns str or None."""
        result = _resolve_affiliate_code_from_request(
            cookies=cookies, query_params=query_params, body=body,
        )
        assert result is None or isinstance(result, str)
