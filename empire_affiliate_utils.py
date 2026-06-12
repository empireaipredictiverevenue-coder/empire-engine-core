"""
EMPIRE V49 · Affiliate Utils
=============================
Lightweight utility functions for affiliate-code resolution.
Extracted from hub.py so unit tests can import them without
triggering hub.py's heavy module-level side effects.
"""


def _resolve_affiliate_code_from_request(
    cookies: dict,
    query_params: dict,
    body: dict,
) -> str | None:
    """Resolve affiliate_code from three sources in priority order:
    1. Cookie: affiliate_ref (set by /track/aff/{code} landing page)
    2. URL query params: ?affiliate_code=XYZ or ?ref=XYZ or ?utm_source=...
    3. Request body fields: {affiliate_code, ref, utm_source}

    Filters out empty strings and common UTM defaults like "(direct)".
    Returns the first non-filtered value found, or None.
    """
    # 1. Cookie
    aff = cookies.get("affiliate_ref") or None
    if aff:
        return aff

    # 2. URL query params
    qp = query_params
    aff = (
        qp.get("affiliate_code")
        or qp.get("ref")
        or _safe_utm_value(qp.get("utm_source"))
    )
    if aff:
        return aff

    # 3. Request body fields
    aff = (
        body.get("affiliate_code")
        or body.get("ref")
        or _safe_utm_value(body.get("utm_source"))
    )
    if aff:
        return aff

    return None


def _safe_utm_value(value: str | None) -> str | None:
    """Sanitize a UTM source value.

    Returns None for empty/whitespace-only values and common
    UTM defaults (direct, organic, social, email, none),
    case-insensitively.  Strips leading/trailing whitespace
    for legitimate values so '  partner  ' becomes 'partner'.
    """
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    _FILTERED = {"(direct)", "direct", "organic", "social", "email", "none"}
    if stripped.lower() in _FILTERED:
        return None
    return stripped
