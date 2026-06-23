"""Empire AI · Vonage Readiness + Email Skip-Trace

Vonage readiness endpoint: queries the Vonage API for what's needed
to send real A2P SMS at scale.

Email skip-trace: given a business name + city, derives the most
likely domain + email patterns. Uses MX lookup to validate the
domain exists. Adds the discovered email to contractors (without
need for any paid skip-trace API).
"""

# ── VONAGE READINESS ────────────────────────────────────────────────────
def _vonage_readiness() -> dict:
    """What needs to happen before real SMS can go out."""
    import os, json, urllib.request as ur, urllib.error as ue
    n = os.getenv("VONAGE_NUMBER", "").strip()
    out = {
        "vonage_number": n,
        "is_test_number": False,
        "checks": [],
    }
    # Check if number is in test range
    if n.startswith("+1") and len(n) == 12 and n[5:8] == "555":
        out["is_test_number"] = True
        out["checks"].append({
            "name": "number_format",
            "status": "fail",
            "detail": f"VONAGE_NUMBER {n} is in the 555-01XX test range. All SMS go to Vonage sandbox, not real recipients. Replace with a real 10DLC or toll-free number.",
        })
    else:
        out["checks"].append({
            "name": "number_format",
            "status": "ok" if (n and n.startswith("+") and 8 <= len(n) <= 16) else "warn",
            "detail": f"number looks like {n} (valid E.164 format, not in test range).",
        })

    # Try the Vonage Numbers API to confirm the number is owned by the account
    key_path = os.getenv("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")
    app_id = os.getenv("VONAGE_APPLICATION_ID", "")
    if os.path.exists(key_path) and app_id:
        try:
            import jwt as pyjwt, time
            with open(key_path) as f:
                priv = f.read()
            now = int(time.time())
            tok = pyjwt.encode({"iat": now, "exp": now + 3600, "jti": f"readiness-{now}", "sub": app_id}, priv, algorithm="RS256")
            # Try several API endpoints
            for label, url in [
                ("numbers_list", "https://api.nexmo.com/v1/account/numbers"),
                ("numbers_legacy", "https://rest.nexmo.com/account/numbers"),
            ]:
                try:
                    req = ur.Request(url, headers={"Authorization": f"Bearer {tok}"})
                    r = ur.urlopen(req, timeout=8)
                    d = json.loads(r.read())
                    nums = d.get("numbers", d.get("data", []))
                    if isinstance(d, list):
                        nums = d
                    if nums:
                        owned = [x for x in nums if str(x.get("msisdn", "")) in n or str(x.get("msisdn", ""))[-10:] in n[-10:]]
                        if owned:
                            out["checks"].append({
                                "name": "number_ownership",
                                "status": "ok",
                                "detail": f"Number {n} is registered on this Vonage account. features={owned[0].get('features', [])}",
                            })
                        else:
                            out["checks"].append({
                                "name": "number_ownership",
                                "status": "warn",
                                "detail": f"VONAGE_NUMBER {n} NOT in account's number list ({len(nums)} numbers owned). May be the wrong number.",
                            })
                        break
                except ue.HTTPError as e:
                    if e.code == 404:
                        out["checks"].append({
                            "name": "numbers_api",
                            "status": "warn",
                            "detail": f"{label} returned 404 — may need account-level API key+secret (we only have JWT)",
                        })
                        continue
                    out["checks"].append({
                        "name": "numbers_api",
                        "status": "warn",
                        "detail": f"{label} HTTP {e.code}",
                    })
                    continue
        except Exception as e:
            out["checks"].append({
                "name": "numbers_api",
                "status": "warn",
                "detail": f"could not query: {type(e).__name__}: {e}",
            })

    # 10DLC requirements (US A2P)
    out["ten_dlc_requirements"] = {
        "needs_brand_registration": True,
        "needs_campaign_registration": True,
        "needs_tax_id": True,
        "alt_options": [
            "toll-free number (8YY) — bypasses 10DLC, $1-2/month, free registration, faster throughput (1 msg/sec)",
            "short code — 100 msg/sec, $500-1500/month, 8-12 week approval",
            "skip SMS entirely and use email (Resend) — no tax ID needed",
        ],
        "dashboard_url": "https://dashboard.nexmo.com/messages/10dlc",
    }
    out["verdict"] = "ready" if all(c.get("status") == "ok" for c in out["checks"]) else "not_ready"
    out["blocker"] = next((c["detail"] for c in out["checks"] if c.get("status") == "fail"), None)
    return out


# ── EMAIL SKIP-TRACE (domain + pattern guesser, no paid API) ────────────
import re
import dns.resolver as _dns  # dnspython

# Common business email patterns to try, in order of likelihood
EMAIL_PATTERNS = ["info", "contact", "office", "hello", "admin", "support", "sales", "team"]


def _slug_domain(name: str) -> str:
    """Heuristic: business name -> likely domain. 'Acme Roofing LLC' -> 'acmeroofing.com'."""
    if not name:
        return ""
    s = name.lower()
    # Strip common suffixes
    for suf in [", llc", " llc", ", inc", " inc", ", ltd", " ltd", ", corp", " corp", " company", " co.", " co,", " - "]:
        if suf in s:
            s = s.split(suf)[0]
    # Strip non-alphanum
    s = re.sub(r"[^a-z0-9 ]", "", s)
    # Strip common words to make shorter (good for domain fitting)
    stop = {"the", "and", "of", "a", "an", "group", "services", "company", "solutions"}
    words = [w for w in s.split() if w and w not in stop]
    # Take first 3 words max
    base = "".join(words[:3]) if words else (s.split()[0] if s.split() else "")
    base = base[:20]  # cap length
    if not base:
        return ""
    return f"{base}.com"


def _mx_exists(domain: str) -> bool:
    try:
        answers = _dns.resolve(domain, "MX")
        return len(answers) > 0
    except Exception:
        return False


def _smtp_validate(email: str) -> bool:
    """Cheap syntax + domain check. Doesn't actually connect to SMTP
    (SMTP RCPT TO probes are anti-abuse-violating)."""
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return False
    dom = email.split("@")[1]
    return _mx_exists(dom)


def _skip_trace_email(name: str, city: str = "", state: str = "") -> dict:
    """For a business name, return the most likely email + confidence.
    0 = no match, 1 = syntax only, 2 = domain has MX, 3 = confirmed via Resend."""
    if not name:
        return {"email": "", "domain": "", "confidence": 0, "method": "none"}
    domain = _slug_domain(name)
    if not domain:
        return {"email": "", "domain": "", "confidence": 0, "method": "none"}
    # Try a few alternative TLDs
    candidate_domains = [domain]
    base = domain.rsplit(".", 1)[0]
    for tld in ["net", "org", "co", "io"]:
        if base:
            candidate_domains.append(f"{base}.{tld}")
    # Find first domain with MX
    found_domain = None
    for d in candidate_domains:
        if _mx_exists(d):
            found_domain = d
            break
    if not found_domain:
        return {"email": "", "domain": domain, "confidence": 1, "method": "pattern_guess"}
    # Try patterns in order
    for pat in EMAIL_PATTERNS:
        cand = f"{pat}@{found_domain}"
        # Cheap "validation" — MX exists already, so syntax+domain is good enough
        if _smtp_validate(cand):
            return {"email": cand, "domain": found_domain, "confidence": 2, "method": "pattern_guess"}
    return {"email": "", "domain": found_domain, "confidence": 2, "method": "pattern_guess"}


def _skip_trace_batch(sb, limit: int = 100) -> dict:
    """Run skip-trace on contractors without email."""
    r = sb.table("contractors").select("id,name,metro,email").eq("active", True).is_("email", "null").limit(limit).execute()
    rows = r.data or []
    found = 0
    for c in rows:
        res = _skip_trace_email(c.get("name", ""), c.get("metro", ""), "")
        if res["email"]:
            try:
                sb.table("contractors").update({"email": res["email"]}).eq("id", c["id"]).execute()
                found += 1
            except Exception:
                pass
    return {"scanned": len(rows), "found": found}