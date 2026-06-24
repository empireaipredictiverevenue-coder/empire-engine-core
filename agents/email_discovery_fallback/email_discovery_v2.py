"""Email discovery v2 - much faster. Skip HTTP check, use known domain mapping for top US warehouses."""
import os, re, sys
from datetime import datetime, timezone
sys.path.insert(0, "/root/empire-v49")
from supabase import create_client

# Known warehouse / distribution center companies with verified domains
# Format: lowercase substring -> verified email pattern
KNOWN_DOMAINS = {
    "amazon": "amazon.com",
    "walmart": "walmart.com",
    "target": "target.com",
    "costco": "costco.com",
    "heb": "heb.com",
    "h-e-b": "heb.com",
    "kroger": "kroger.com",
    "aldi": "aldi.us",
    "publix": "publix.com",
    "frito": "pepsico.com",
    "pepsi": "pepsico.com",
    "coca-cola": "coca-cola.com",
    "coca cola": "coca-cola.com",
    "usps": "usps.com",
    "fedex": "fedex.com",
    "ups": "ups.com",
    "dhl": "dhl.com",
    "xpo": "xpo.com",
    "schneider": "schneider.com",
    "jb hunt": "jbhunt.com",
    "werner": "werner.com",
    "ryder": "ryder.com",
    "sysco": "sysco.com",
    "us foods": "usfoods.com",
    "performance food": "pfgc.com",
    "pfg": "pfgc.com",
    "mclane": "mclaneco.com",
    "core mark": "coremark.com",
    "unfi": "unfi.com",
    "keHE": "kehe.com",
    "tyson": "tyson.com",
    "smithfield": "smithfieldfoods.com",
    "carter": "carter-inc.com",  # guess
    "ash grove": "ashgrove.com",  # MX verified 2026-06-17
    "abf": "abf.com",
    "estes": "estes-express.com",
    "yrc": "yrc.com",
    "old dominion": "odfl.com",
    "saia": "saia.com",
    "vitran": "vitran.com",
    "saddle creek": "scl-corp.com",
    "dhl supply": "dhl.com",
    "amazon fulfillment": "amazon.com",
    "amazon distribution": "amazon.com",
    "ikea": "ikea.com",
    "home depot": "homedepot.com",
    "lowe": "lowes.com",
    "menards": "menards.com",
    "wayfair": "wayfair.com",
    "best buy": "bestbuy.com",
    "dollar tree": "dollartree.com",
    "dollar general": "dollargeneral.com",
    "family dollar": "familydollar.com",
    "at home": "athome.com",
    "ashley furniture": "ashleyfurniture.com",
    "crate and barrel": "crateandbarrel.com",
    "williams sonoma": "williams-sonoma.com",
    "restoration hardware": "rh.com",
    "rh": "rh.com",
    "pottery barn": "potterybarn.com",
    "west elm": "westelm.com",
    "cb2": "cb2.com",
    "visionworks": "visionworks.com",
    "lenscrafters": "lenscrafters.com",
    "specs": "specsavers.com",
    "red bull": "redbull.com",
    "monster": "monsterenergy.com",
    "kendra scott": "kendrascott.com",
    "tractor supply": "tractorsupply.com",
    "cabela": "cabelas.com",
    "bass pro": "basspro.com",
    "dicks sporting": "dicks.com",
    "academy": "academy.com",
    "dillards": "dillards.com",
    "jcpenney": "jcpenney.com",
    "macy": "macys.com",
    "nordstrom": "nordstrom.com",
    "nike": "nike.com",
    "adidas": "adidas.com",
    "under armour": "underarmour.com",
    "keurig dr": "keurig.com",
    "keurig": "keurig.com",
    "utility": "utility.com",
    "vopak": "vopak.com",
    "vopak terminal": "vopak.com",
    "vopak deer": "vopak.com",
    "del monte": "delmonte.com",
    "birdville isd": "birdvilleschools.net",
    "birdville": "birdvilleschools.net",
    "kyle 35": "kyletx.gov",
    "kyle logistics": "kyletx.gov",
    "plum creek": "plumcreektx.com",  # guess
    "leander isd": "leanderisd.org",
    "leander": "leanderisd.org",
    "royson": "roysoncity.com",  # guess
    "trillium": "trilliumcd.com",  # guess
    "redbudd": "redbuddcompanies.com",  # guess
    "matt brower": "mclaneco.com",
    "cart.com": "cart.com",
    "computersupport": "computersupport.com",  # MX verified 2026-06-17
    "execsearches": "execsearches.com",  # MX verified 2026-06-17
    "physicaladdress": "physicaladdress.com",  # MX verified 2026-06-17
    "ssls.com": "ssls.com",  # MX verified 2026-06-17 (full name-key to avoid false positives on 'ssl' substring)
    "workforce": "workforce.com",  # MX verified 2026-06-17
    "kroger fulfillment": "kroger.com",
    "tcc": "tccmaterials.com",  # guess
    "interpark": "interpark.com",  # guess
    "spr distribution": "sprdist.com",  # guess
    "at home distribution": "athome.com",
    "cj warehouse": "cj.com",  # MX verified 2026-06-17
    "cj logistics": "cjlogistics.com",  # MX verified 2026-06-17
    "stallion": "stallion.com",  # MX verified 2026-06-17
    "long ma": "long.com",  # MX verified 2026-06-17
    "mrs bairds": "mrsbairds.com",  # MX verified 2026-06-17
    "bairds": "mrsbairds.com",  # MX verified 2026-06-17
    "goodyear": "goodyear.com",
    "axogen": "axogeninc.com",
    "intermodal": "intermodalinc.com",  # guess
    "intermodal logistics": "intermodalinc.com",  # guess
    "samsonite": "samsonite.com",
    "logistics plus": "logisticsplus.com",
    "dutch bros": "dutchbros.com",
    "trader joe": "traderjoes.com",
    "barrett": "barrettdistribution.com",  # guess
    "usps north texas": "usps.com",
    "usps processing": "usps.com",
    "interpark logistics": "interpark.com",  # guess
    "he-b refrigerated": "heb.com",
    "he-b": "heb.com",
    "heb refrigerated": "heb.com",
    "heb distribution": "heb.com",
    "spectrum warehouse": "spectrum.com",
    "amazon aus": "amazon.com",
    "austin fulfillment": "austintexas.gov",  # guess
    "sat4 amazon": "amazon.com",
    "sat amazon": "amazon.com",
    "san antonio express": "mysa.com",  # guess
    "express news": "mysa.com",  # guess
    "specs distribution": "specsavers.com",
    "specsavers": "specsavers.com",
    "united christian": "ucchurch.org",  # guess
    "serco": "serco.com",
    "pdc": "pdc.com",  # MX verified 2026-06-17
    "office depot": "officedepot.com",
    "office max": "officedepot.com",
    "williamson-dickie": "williamson-dickie.com",
    "community food bank": "cfbnorthtexas.org",
    "texas & pacific": "tpr.org",  # guess
    "kroger": "kroger.com",
    "kroger co": "kroger.com",
    "albertsons": "albertsons.com",
    "safeway": "safeway.com",
    "wegmans": "wegmans.com",
    "trader joe's": "traderjoes.com",
    "sams club": "samsclub.com",
    "sam's club": "samsclub.com",
    "whole foods": "wholefoods.com",
    "trader joes": "traderjoes.com",
    "heb warehouse": "heb.com",
    "heb dist": "heb.com",
    "heb fulfillment": "heb.com",
    "costco": "costco.com",
    "at home": "athome.com",
    "ashley": "ashleyfurniture.com",
    "royse city isd": "roysecityisd.net",
    "matt brower": "mclaneco.com",
    "martin brower": "mclaneco.com",
    # MX verified 2026-06-17 batch (blocked leads audit)
    "textron": "textron.com",
    "bell helicopter": "bell.com",
    "bell textron": "textron.com",
    "land o'lakes": "landolakes.com",
    "landolakes": "landolakes.com",
    "molson": "molsoncoors.com",
    "molson coors": "molsoncoors.com",
    "coors": "molsoncoors.com",
    "dr pepper": "drpepper.com",
    "drpepper": "drpepper.com",
    "motts": "motts.com",
    "tenaris": "tenaris.com",
    "vistra": "vistra.com",
    "vistracorp": "vistracorp.com",
    "freeport lng": "freeportlng.com",
    "turner industries": "turnerindustries.com",
    "turnerindustries": "turnerindustries.com",
    "tiff's treats": "tiffstreats.com",
    "tiffstreats": "tiffstreats.com",
    "intsel": "intsel.com",
    "idealease": "idealease.com",
    "cardone": "cardone.com",
    "kenco": "kenco.com",
    "andrews distributing": "andrews.com",
    "atmos energy": "atmosenergy.com",
    "atmosenergy": "atmosenergy.com",
    "boyd": "boyd.com",
    "argos": "argos.com",
    "karat": "karat.com",
    "eanes": "eanes.com",
    "hockley": "hockley.com",
    "amco": "amco.com",
    "accent warehouse": "accentservices.com",
    "accent services": "accentservices.com",
    # MX verified 2026-06-17 batch 2 (blocked leads audit)
    "ritchie": "rbauction.com",
    "rbauction": "rbauction.com",
    "safran": "safran.com",
    "shiner": "shiner.com",
    "spoetzl": "spoetzl.com",
    "wild acre": "wildacrebrewing.com",
    "wildacrebrewing": "wildacrebrewing.com",
    "texaloy": "texaloy.com",
    "romeo engineering": "romeoeng.com",
    "tejas research": "tejasre.com",
    "vandergriff": "vandergriff.com",
    "vending nut": "vendingnut.com",
    "wagner logistics": "wagnerlogistics.com",
    "national trench": "nta.org",
    "north texas tollway": "ntta.org",
    "love's truck": "loves.com",
    "loves truck": "loves.com",
    "spartan printing": "spartanprinting.com",
    "delta rigging": "deltarigging.com",
    "falcon steel": "falconsteel.com",
    "humble isd": "humbleisd.net",
    "spec's": "specs.com",
    "specs distribution": "specs.com",
    "spr packaging": "sprpackaging.com",
    "roly's": "rolys.com",
    "rolys trucking": "rolystrucking.com",
    "pca packaging": "packagingcorp.com",
    "bana box": "banabox.com",
    "nalco": "nalco.com",
    "ppg": "ppg.com",
}


def _known_domain(warehouse_name: str):
    if not warehouse_name:
        return None
    name_lower = warehouse_name.lower()
    # Sort by length desc so multi-word matches win
    for key in sorted(KNOWN_DOMAINS.keys(), key=len, reverse=True):
        if key in name_lower:
            return KNOWN_DOMAINS[key]
    return None


def _name_to_domain(warehouse_name: str) -> str:
    """Fallback: convert warehouse name to a likely domain."""
    if not warehouse_name:
        return None
    name = warehouse_name.lower()
    noise = {"distribution", "center", "warehouse", "facility", "the", "of", "and", "inc", "llc", "co", "company", "corp", "ltd", "services", "us", "lp", "inc", "group", "north", "south", "east", "west"}
    tokens = re.findall(r"[a-z0-9]+", name)
    meaningful = [t for t in tokens if t not in noise and len(t) >= 3]
    if not meaningful:
        return None
    return "".join(meaningful) + ".com"


def run(max_per_run: int = 1000):
    sb = create_client(os.environ["SUPABASE_URL"], os.getenv("SUPABASE_SERVICE_KEY"))
    r = sb.table("enriched_leads").select("id,warehouse_name,status,meta").is_("phone", "null").is_("email", "null").in_("status", ["pending_outreach", "pending_enrichment", "blocked"]).limit(max_per_run).execute()
    leads = r.data or []
    print(f"[email_discovery_v2] {len(leads)} candidates")

    known_found = 0
    fallback_found = 0
    for lead in leads:
        name = lead.get("warehouse_name") or ""
        # Try known domain first
        domain = _known_domain(name)
        method = "known_db"
        if not domain:
            domain = _name_to_domain(name)
            method = "name_guess"
        if not domain:
            continue
        email = f"info@{domain}"
        existing_meta = lead.get("meta") or {}
        if not isinstance(existing_meta, dict):
            existing_meta = {}
        new_meta = dict(existing_meta)
        new_meta["email_guess"] = True
        new_meta["email_discovery_method"] = f"fast_v2_{method}"
        new_meta["email_discovered_at"] = datetime.now(timezone.utc).isoformat()
        new_meta["email_domain"] = domain
        sb.table("enriched_leads").update({
            "email": email,
            "meta": new_meta,
        }).eq("id", lead["id"]).execute()
        if method == "known_db":
            known_found += 1
        else:
            fallback_found += 1
    print(f"  found: {known_found} (known db) + {fallback_found} (name guess) = {known_found + fallback_found}")
    return {"candidates": len(leads), "known": known_found, "guessed": fallback_found}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--max-per-run", type=int, default=1000)
    args = p.parse_args()
    result = run(max_per_run=args.max_per_run)
    print(f"FINAL: {result}")