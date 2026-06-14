#!/usr/bin/env python3
"""update _discover_one to use _google_places_search and _scrape_contact_page."""
import pathlib
p = pathlib.Path("/root/empire-v49/agents/contact_discovery/discovery.py")
src = p.read_text()

old = '''def _discover_one(lead: dict, cfg: dict) -> dict:
    """Attempt discovery for a single lead. Returns
    {phone, email, source, attempts} — fields not found are empty strings."""
    warehouse = lead.get("warehouse_name") or ""
    address = lead.get("address") or ""
    city = lead.get("city") or ""
    state = lead.get("state") or ""
    result = {"phone": "", "email": "", "source": "", "attempts": []}

    # Method 1: web search for the warehouse_name + city + "phone"
    if warehouse and city:
        q = f'"{warehouse}" "{city}" {state} phone contact'
        results = _search_duckduckgo(q, max_results=3)
        for snippet, url in results:
            result["attempts"].append({"method": "ddg_search", "q": q, "url": url, "snippet": snippet[:120]})
            phone = _extract_phone_from_text(snippet)
            if phone and not result["phone"]:
                result["phone"] = phone
                result["source"] = f"ddg_search:{url}"
            email = _extract_email_from_text(snippet)
            if email and not result["email"]:
                result["email"] = email
                result["source"] = result["source"] or f"ddg_search:{url}"
            if result["phone"] and result["email"]:
                break

    # Method 2: web search for the address + "phone"
    if not result["phone"] and address:
        q = f'"{address}" phone contact'
        results = _search_duckduckgo(q, max_results=2)
        for snippet, url in results:
            result["attempts"].append({"method": "ddg_search_addr", "q": q, "url": url, "snippet": snippet[:120]})
            phone = _extract_phone_from_text(snippet)
            if phone and not result["phone"]:
                result["phone"] = phone
                result["source"] = f"ddg_search_addr:{url}"
            if result["phone"]:
                break

    # Method 3: email pattern guess (logged, not auto-claimed — domain not verified)
    if not result["email"] and warehouse:
        patterns = _email_pattern_guess(warehouse, city)
        # only log the first 3 patterns as suggestions — don't claim them as "found"
        result["attempts"].append({
            "method": "email_pattern_suggestions",
            "patterns": [p for p, _ in patterns[:3]],
            "note": "patterns not verified — operator should manually MX-check before use",
        })

    return result'''

new = '''def _discover_one(lead: dict, cfg: dict) -> dict:
    """Attempt discovery for a single lead. Returns
    {phone, email, source, attempts} — fields not found are empty strings."""
    warehouse = lead.get("warehouse_name") or ""
    address = lead.get("address") or ""
    city = lead.get("city") or ""
    state = lead.get("state") or ""
    result = {"phone": "", "email": "", "source": "", "attempts": []}

    # Method 1: Google Places text search — best ROI for businesses with public profiles
    if warehouse:
        q = f"{warehouse} {city} {state}".strip()
        places = _google_places_search(q)
        for place in places:
            result["attempts"].append({
                "method": "google_places",
                "q": q,
                "name": place.get("name"),
                "address": place.get("address", "")[:80],
            })
            if place.get("phone") and not result["phone"]:
                cleaned = _clean_phone(place["phone"])
                if cleaned:
                    result["phone"] = cleaned
                    result["source"] = f"google_places:{place.get('name','')}"
            if place.get("website") and not result["email"]:
                # we have a website — scrape its contact pages
                scraped = _scrape_contact_page(place["website"])
                if scraped["phone"] and not result["phone"]:
                    result["phone"] = scraped["phone"]
                    result["source"] = f"website_scrape:{place['website']}"
                if scraped["email"]:
                    result["email"] = scraped["email"]
                    result["source"] = result["source"] or f"website_scrape:{place['website']}"
            if result["phone"] and result["email"]:
                break

    # Method 2: if we still don't have a phone, try the address as a query
    if not result["phone"] and address:
        places = _google_places_search(address)
        for place in places:
            result["attempts"].append({
                "method": "google_places_addr",
                "q": address,
                "name": place.get("name"),
            })
            if place.get("phone"):
                cleaned = _clean_phone(place["phone"])
                if cleaned:
                    result["phone"] = cleaned
                    result["source"] = result["source"] or f"google_places_addr:{place.get('name','')}"
                    break

    # Method 3: email pattern suggestions (logged, not auto-claimed — domain not verified)
    if not result["email"] and warehouse:
        patterns = _email_pattern_guess(warehouse, city)
        result["attempts"].append({
            "method": "email_pattern_suggestions",
            "patterns": [p for p, _ in patterns[:3]],
            "note": "patterns not verified — operator should manually MX-check before use",
        })

    return result'''

assert old in src, "old _discover_one not found"
src = src.replace(old, new)
p.write_text(src)
print("replaced _discover_one")
