"""
EMPIRE V49 · STORM LOG TO TARGETS PIPELINE
===========================================
Reads storm_risk_log and applies metro-level risk to active radar_targets.

This agent fills the gap between:
  - warp_scout / storm_alert (which write metro-level risk to storm_risk_log)
  - radar_targets (which need property-level damage_severity + urgency_score)

Logic per run:
  1. Query storm_risk_log for the latest risk data per metro (aggregates
     across days, takes the max risk_rank for each metro)
  2. Filter to metros with risk_rank >= min_risk_rank threshold
  3. For each metro, query active radar_targets in that metro area
     (city-based matching using _METRO_ALIASES)
  4. Map risk_level → damage_severity and risk_rank → urgency_score
  5. Update radar_targets rows (upgrades only — never downgrades)

Cron: every 30 min (runs alongside storm_alert for complementary coverage).

Usage:
    python3 -m agents.storm_log_to_targets
    python3 -m agents.storm_log_to_targets --dry-run
    python3 -m agents.storm_log_to_targets --status
"""

import os
import sys
import json
import uuid
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

from supabase import create_client
from agents.event_emitter import emit_agent_event

log = logging.getLogger("empire.storm_log_to_targets")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

AGENT_NAME = "storm_log_to_targets"

# ── Metro name → city alias matching (sync with empire_satellite_strike.py) ──
_METRO_ALIASES: Dict[str, List[str]] = {
    "Dallas-Fort Worth":   ["dallas", "fort worth", "dfw", "arlington", "plano", "irving", "garland", "mesquite", "carrollton", "frisco", "mckinney", "denton", "lewisville", "richardson", "allen"],
    "Dallas":              ["dallas", "dfw"],
    "Fort Worth":          ["fort worth", "ft worth"],
    "Houston":             ["houston", "sugar land", "the woodlands", "conroe", "pearland", "pasadena", "cypress", "katy", "spring"],
    "Austin":              ["austin", "round rock", "cedar park", "pflugerville", "san marcos", "kyle", "buda"],
    "San Antonio":         ["san antonio", "sa", "new braunfels", "schertz", "converse", "cibolo"],
    "Wichita":             ["wichita", "derby", "haysville", "andover", "maize"],
    "Oklahoma City":       ["oklahoma city", "okc", "norman", "edmond", "moore", "midwest city", "enid", "stillwater"],
    "Kansas City":         ["kansas city", "kc", "overland park", "olathe", "kansas city ks", "independence", "lee's summit", "shawnee", "lenexa"],
    "Tulsa":               ["tulsa", "broken arrow", "owasso", "jenks", "bixby"],
    "New Orleans":         ["new orleans", "nola", "metairie", "kenner", "gretna", "marrero", "chalmette", "slidell"],
    "Memphis":             ["memphis", "germantown", "collierville", "bartlett", "cordova"],
    "Atlanta":             ["atlanta", "marietta", "alpharetta", "roswell", "johns creek", "sandy springs", "smyrna", "dunwoody", "decatur", "cobb", "gwinnett"],
    "Nashville":           ["nashville", "franklin", "murfreesboro", "brentwood", "hendersonville", "smyrna tn", "gallatin"],
    # ── Florida ──
    "Miami":               ["miami", "fort lauderdale", "hialeah", "miami beach", "coral gables", "davie", "pembroke pines", "hollywood fl"],
    "Tampa":               ["tampa", "st petersburg", "clearwater", "brandon", "riverview", "largo", "tampa fl"],
    "Orlando":             ["orlando", "kissimmee", "sanford", "winter park", "maitland", "altamonte springs", "orlando fl"],
    "Jacksonville":        ["jacksonville", "jacksonville beach", "atlantic beach", "neptune beach", "orange park", "fl"],
    "Fort Myers":          ["fort myers", "cape coral", "naples", "bonita springs", "estero"],
    "Pensacola":           ["pensacola", "gulf breeze", "navarre", "pace", "milton fl"],
    "Tallahassee":         ["tallahassee", "crawfordville", "havana"],
    # ── Alabama ──
    "Montgomery":          ["montgomery", "prattville", "millbrook", "wetumpka", "troy al", "pike road"],
    "Huntsville":          ["huntsville", "madison al", "decatur al", "athens al", "florence al", "muscle shoals", "scottsboro", "fort payne", "cullman"],
    "Tuscaloosa":          ["tuscaloosa", "northport", "al"],
    "Dothan":              ["dothan", "enterprise", "ozark", "geneva al", "andalusia"],
    # ── Florida Panhandle ──
    "Panama City":         ["panama city", "panama city beach", "lynn haven", "callaway", "destin", "fort walton beach", "niceville"],
    # ── Mississippi ──
    "Tupelo":              ["tupelo", "corinth", "starkville", "columbus ms", "greenwood ms", "oxford ms"],
    "Hattiesburg":         ["hattiesburg", "laurel ms", "petal", "purvis", "columbia ms"],
    # ── Gulf Coast ──
    "Mobile":              ["mobile", "daphne", "fairhope", "foley", "spanish fort", "al"],
    "Birmingham":          ["birmingham", "hoover", "bessemer", "vestavia", "alabaster", "birmingham al"],
    "Shreveport":          ["shreveport", "bossier city", "benton la", "haughton", "minden la", "natchitoches"],
    "Lafayette LA":        ["lafayette", "new iberia", "broussard", "youngsville", "carencro", "scott la", "crowley", "abbeville", "opelousas"],
    "Baton Rouge":         ["baton rouge", "prarieville", "zachary", "central", "walker", "denham springs", "la"],
    "Jackson MS":          ["jackson ms", "clinton", "byram", "richland", "ridgeland"],
    "Gulfport":            ["gulfport", "biloxi", "ocean springs", "long beach ms", "pass christian", "diberville", "ms"],
    # ── Carolinas ──
    "Charlotte":           ["charlotte", "concord nc", "gastonia", "rock hill", "huntersville", "hickory", "matthews", "pineville", "nc"],
    "Raleigh":             ["raleigh", "durham", "cary", "chapel hill", "apex", "holly springs", "morrisville", "wake forest", "nc"],
    "Wilmington":          ["wilmington nc", "jacksonville nc", "lelände", "carolina beach", "wrightsville beach"],
    "Columbia":            ["columbia sc", "lexington sc", "irmo", "cayce", "west columbia"],
    "Charleston":          ["charleston sc", "mount pleasant", "north charleston", "summerville", "goose creek", "hanahan"],
    "Myrtle Beach":        ["myrtle beach", "conway sc", "north myrtle beach", "surfside beach", "garden city"],
    # ── Midwest / Plains ──
    "Denver":              ["denver", "aurora co", "lakewood", "westminster co", "arvada", "centennial", "thornton", "boulder", "littleton", "broomfield", "highlands ranch", "co"],
    "St. Louis":           ["st louis", "st. louis", "saint louis", "chesterfield", "florissant", "o'fallon mo", "st charles", "st peters", "mo"],
    "Springfield MO":      ["springfield mo", "nixa", "ozark", "republic"],
    "Little Rock":         ["little rock", "north little rock", "conway ar", "sherwood", "benton", "cabot", "ar"],
    "Omaha":               ["omaha", "lincoln", "council bluffs", "bellevue", "papillion", "la vista"],
    "Des Moines":          ["des moines", "ankeny", "west des moines", "urbandale", "clive", "johnston", "ia"],
    "Waco":                ["waco", "woodway", "hewitt", "robinson", "bellmead", "mcgill"],
    "Temple":              ["temple tx", "belton", "harker heights", "nolanville"],
    "Bryan/College Station": ["bryan", "college station", "b/cs"],
    "Tyler":               ["tyler tx", "whitehouse", "bullard"],
    "Lubbock":             ["lubbock", "wolfforth", "shallowater", "slaton"],
    "Amarillo":            ["amarillo", "canyon", "borger"],
    "El Paso":             ["el paso", "socorro", "horizon city"],
    "Corpus Christi":       ["corpus Christi", "portland tx", "kingsville", "alice"],
    # ── Mid-Atlantic / Northeast ──
    "Richmond":            ["richmond va", "henrico", "chesterfield", "midlothian", "glen allen", "va"],
    "Virginia Beach":      ["virginia beach", "norfolk", "chesapeake", "newport news", "hampton", "portsmouth va", "suffolk va", "va beach"],
    "Philadelphia":        ["philadelphia", "philly", "camden", "cherry hill", "upper darby", "bala cynwyd"],
    "New York City":       ["new york", "manhattan", "brooklyn", "queens", "bronx", "staten island", "nyc"],
    "Boston":              ["boston", "cambridge ma", "somerville", "newton", "quincy", "brookline ma"],
    # ── Ohio Valley ──
    "Indianapolis":        ["indianapolis", "fishers", "carmel", "noblesville", "greenwood", "plainfield", "avon in", "in"],
    "Columbus":            ["columbus oh", "dublin", "gahanna", "westerville", "hilliard", "grove city"],
    "Louisville":          ["louisville", "lexington ky", "bowling green", "owensboro", "elizabethtown", "ky"],
    # ── County-name entries with unique alias lists ───────────────────
    # These counties have city names not covered by parent metro alias lists,
    # so they need their own entries. Most other TX counties resolve via
    # _COUNTY_TO_METRO below.
    "Hunt, TX":          ["greenville tx", "commerce tx", "quinlan", "caddo mills", "lone oak", "wolfe city"],
    "Coryell, TX":       ["gatesville", "copperas cove", "oglesby"],
    "Gregg, TX":         ["longview", "white oak", "kilgore"],
    "Bowie, TX":         ["texarkana"],
    "Webb, TX":          ["laredo"],
    "Hidalgo, TX":       ["mcallen", "edinburg", "pharr", "mission", "weslaco", "donna"],
    "Cameron, TX":       ["brownsville", "harlingen", "san benito", "los fresnos"],
}

# ── NWS county-name → metro alias map ──────────────────────────────────
# NWS areaDesc uses county names (e.g. "Dallas, TX") not metro names.
# storm_alert writes these into storm_risk_log. This map resolves them
# to existing _METRO_ALIASES keys, avoiding duplicated alias lists.
# Add new counties here — not as duplicated lists in _METRO_ALIASES.
_COUNTY_TO_METRO: Dict[str, str] = {
    # ── DFW metro counties ──
    "Dallas, TX":      "Dallas-Fort Worth",
    "Collin, TX":      "Dallas-Fort Worth",
    "Tarrant, TX":     "Dallas-Fort Worth",
    "Denton, TX":      "Dallas-Fort Worth",
    "Ellis, TX":       "Dallas-Fort Worth",
    "Johnson, TX":     "Dallas-Fort Worth",
    "Rockwall, TX":    "Dallas-Fort Worth",
    "Kaufman, TX":     "Dallas-Fort Worth",
    "Parker, TX":      "Dallas-Fort Worth",
    # ── Houston metro counties ──
    "Harris, TX":      "Houston",
    "Montgomery, TX":  "Houston",
    "Fort Bend, TX":   "Houston",
    "Brazoria, TX":    "Houston",
    "Galveston, TX":   "Houston",
    # ── Austin metro counties ──
    "Travis, TX":      "Austin",
    "Williamson, TX":  "Austin",
    "Hays, TX":        "Austin",
    "Bastrop, TX":     "Austin",
    "Caldwell, TX":    "Austin",
    # ── San Antonio metro counties ──
    "Bexar, TX":       "San Antonio",
    "Comal, TX":       "San Antonio",
    "Guadalupe, TX":   "San Antonio",
    # ── Central / West Texas ──
    "McLennan, TX":    "Waco",
    "Bell, TX":        "Temple",
    "Smith, TX":       "Tyler",
    "Lubbock, TX":     "Lubbock",
    "Potter, TX":      "Amarillo",
    "Randall, TX":     "Amarillo",
    "El Paso, TX":     "El Paso",
    "Nueces, TX":      "Corpus Christi",
    # ── Oklahoma ──
    # OKC metro counties
    "Oklahoma, OK":    "Oklahoma City",
    "Cleveland, OK":   "Oklahoma City",
    "Canadian, OK":    "Oklahoma City",
    "McClain, OK":     "Oklahoma City",
    "Logan, OK":       "Oklahoma City",
    "Grady, OK":       "Oklahoma City",
    "Kingfisher, OK":  "Oklahoma City",
    "Lincoln, OK":     "Oklahoma City",
    "Pottawatomie, OK":"Oklahoma City",
    "Seminole, OK":    "Oklahoma City",
    "Pontotoc, OK":    "Oklahoma City",     # Ada
    "Comanche, OK":    "Oklahoma City",     # Lawton
    "Stephens, OK":    "Oklahoma City",     # Duncan
    "Garvin, OK":      "Oklahoma City",     # Pauls Valley
    "Carter, OK":      "Oklahoma City",     # Ardmore
    # Tulsa metro counties
    "Tulsa, OK":       "Tulsa",
    "Rogers, OK":      "Tulsa",
    "Wagoner, OK":     "Tulsa",
    "Creek, OK":       "Tulsa",
    "Osage, OK":       "Tulsa",
    "Okmulgee, OK":    "Tulsa",
    "Washington, OK":  "Tulsa",             # Bartlesville
    "Nowata, OK":      "Tulsa",
    "Mayes, OK":       "Tulsa",             # Pryor Creek
    "Pawnee, OK":      "Tulsa",
    # Southern OK → DFW corridor
    "Bryan, OK":       "Dallas-Fort Worth", # Durant — southern I-35 corridor into TX
    "Love, OK":        "Dallas-Fort Worth", # Marietta
    "Marshall, OK":    "Dallas-Fort Worth", # Madill
    "Johnston, OK":    "Dallas-Fort Worth", # Tishomingo
    "Choctaw, OK":     "Dallas-Fort Worth", # Hugo
    "McCurtain, OK":   "Dallas-Fort Worth", # Idabel — far SE OK
    # Northern OK → Wichita corridor
    "Kay, OK":         "Wichita",           # Ponca City
    # ── Kansas ──
    "Sedgwick, KS":    "Wichita",
    "Butler, KS":      "Wichita",
    "Harvey, KS":      "Wichita",
    "Johnson, KS":     "Kansas City",
    "Wyandotte, KS":   "Kansas City",
    # ── Missouri ──
    "Jackson, MO":     "Kansas City",
    "Clay, MO":        "Kansas City",
    "Platte, MO":      "Kansas City",
    "Greene, MO":      "Springfield MO",
    "Christian, MO":   "Springfield MO",
    "Webster, MO":     "Springfield MO",
    "St. Louis, MO":   "St. Louis",
    "St. Charles, MO": "St. Louis",
    "Jefferson, MO":   "St. Louis",
    "Franklin, MO":    "St. Louis",
    # ── Arkansas ──
    # Central AR — Little Rock metro
    "Pulaski, AR":     "Little Rock",
    "Faulkner, AR":    "Little Rock",
    "Saline, AR":      "Little Rock",
    "Lonoke, AR":      "Little Rock",
    "Grant, AR":       "Little Rock",
    "Jefferson, AR":   "Little Rock",       # Pine Bluff
    "Garland, AR":     "Little Rock",       # Hot Springs
    "Conway, AR":      "Little Rock",       # Morrilton
    "Perry, AR":       "Little Rock",
    "Hot Spring, AR":  "Little Rock",       # Malvern
    "Clark, AR":       "Little Rock",       # Arkadelphia
    "Dallas, AR":      "Little Rock",
    "Cleveland, AR":   "Little Rock",
    "Lincoln, AR":     "Little Rock",
    "Desha, AR":       "Little Rock",
    "Drew, AR":        "Little Rock",       # Monticello
    "Bradley, AR":     "Little Rock",       # Warren
    "Ouachita, AR":    "Little Rock",       # Camden
    "Calhoun, AR":     "Little Rock",
    "Union, AR":       "Little Rock",       # El Dorado
    "Columbia, AR":    "Little Rock",       # Magnolia
    "Nevada, AR":      "Little Rock",
    "Hempstead, AR":   "Little Rock",       # Hope
    "Howard, AR":      "Little Rock",       # Nashville
    "Sevier, AR":      "Little Rock",       # De Queen
    "Little River, AR":"Little Rock",       # Ashdown
    "Miller, AR":      "Dallas-Fort Worth", # Texarkana — TX border
    "Lafayette, AR":   "Dallas-Fort Worth", # Lewisville, south AR near TX
    # Eastern AR — Memphis corridor
    "Crittenden, AR":  "Memphis",           # West Memphis — part of Memphis metro
    "Mississippi, AR": "Memphis",           # Blytheville
    "Poinsett, AR":    "Memphis",           # Harrisburg
    "Cross, AR":       "Memphis",           # Wynne
    "St. Francis, AR": "Memphis",           # Forrest City
    "Craighead, AR":   "Memphis",           # Jonesboro — closer to Memphis than LR
    "Greene, AR":      "Memphis",           # Paragould
    "Clay, AR":        "Memphis",           # Corning/Piggott
    # ── Louisiana ──
    # New Orleans metro parishes
    "Orleans, LA":     "New Orleans",
    "Jefferson, LA":   "New Orleans",
    "St. Tammany, LA": "New Orleans",
    "St. Bernard, LA": "New Orleans",
    "Plaquemines, LA": "New Orleans",
    "St. Charles, LA": "New Orleans",
    "St. John the Baptist, LA": "New Orleans",  # LaPlace
    "St. James, LA":   "New Orleans",
    "Lafourche, LA":   "New Orleans",           # Thibodaux
    "Terrebonne, LA":  "New Orleans",           # Houma
    "Tangipahoa, LA":  "New Orleans",           # Hammond
    "Washington, LA":  "New Orleans",           # Bogalusa
    "Assumption, LA":  "New Orleans",           # Napoleonville
    "St. Mary, LA":    "New Orleans",           # Morgan City
    # Shreveport / Northwest Louisiana parishes
    "Caddo, LA":       "Shreveport",
    "Bossier, LA":     "Shreveport",
    "Webster, LA":     "Shreveport",            # Minden
    "Claiborne, LA":   "Shreveport",            # Homer
    "Bienville, LA":   "Shreveport",            # Arcadia
    "Red River, LA":   "Shreveport",            # Coushatta
    "DeSoto, LA":      "Shreveport",            # Mansfield
    "Sabine, LA":      "Shreveport",            # Many
    "Natchitoches, LA": "Shreveport",           # Natchitoches
    "Winn, LA":        "Shreveport",            # Winnfield
    "Grant, LA":       "Shreveport",            # Colfax — could also be Baton Rouge/Alexandria
    "Caldwell, LA":    "Shreveport",            # Columbia — panhandle border
    "La Salle, LA":    "Shreveport",            # Jena
    "Jackson, LA":     "Shreveport",            # Jonesboro
    "Lincoln, LA":     "Shreveport",            # Ruston
    "Union, LA":       "Shreveport",            # Farmerville
    "Morehouse, LA":   "Shreveport",            # Bastrop
    "Ouachita, LA":    "Shreveport",            # Monroe — NE LA hub
    "Richland, LA":    "Shreveport",            # Rayville
    "Franklin, LA":    "Shreveport",            # Winnsboro
    "Madison, LA":     "Shreveport",            # Tallulah
    "Tensas, LA":      "Shreveport",            # St. Joseph
    "Catahoula, LA":   "Shreveport",            # Harrisonburg
    "Concordia, LA":   "Shreveport",            # Vidalia
    # Lafayette / Acadiana parishes
    "Lafayette, LA":   "Lafayette LA",          # Lafayette
    "Acadia, LA":      "Lafayette LA",          # Crowley
    "Vermilion, LA":   "Lafayette LA",          # Abbeville
    "St. Martin, LA":  "Lafayette LA",          # St. Martinville
    "Iberia, LA":      "Lafayette LA",          # New Iberia
    "St. Landry, LA":  "Lafayette LA",          # Opelousas
    "Evangeline, LA":  "Lafayette LA",          # Ville Platte
    "Jefferson Davis, LA": "Lafayette LA",      # Jennings
    "Allen, LA":       "Lafayette LA",          # Oberlin
    "Beauregard, LA":  "Lafayette LA",          # DeRidder
    "Calcasieu, LA":   "Lafayette LA",          # Lake Charles — SW LA hub
    "Cameron, LA":     "Lafayette LA",          # Cameron
    # Baton Rouge metro parishes
    "East Baton Rouge, LA": "Baton Rouge",
    "Livingston, LA":  "Baton Rouge",
    "Ascension, LA":   "Baton Rouge",
    "West Baton Rouge, LA": "Baton Rouge",      # Port Allen
    "Iberville, LA":   "Baton Rouge",           # Plaquemine
    "Pointe Coupee, LA": "Baton Rouge",         # New Roads
    "East Feliciana, LA": "Baton Rouge",        # Clinton
    "West Feliciana, LA": "Baton Rouge",        # St. Francisville
    "St. Helena, LA":  "Baton Rouge",
    "Avoyelles, LA":   "Baton Rouge",           # Marksville
    "Rapides, LA":     "Baton Rouge",           # Alexandria
    # ── Mississippi ──
    # Jackson MS metro
    "Hinds, MS":        "Jackson MS",
    "Rankin, MS":       "Jackson MS",
    "Madison, MS":      "Jackson MS",
    "Copiah, MS":       "Jackson MS",
    "Yazoo, MS":        "Jackson MS",
    "Warren, MS":       "Jackson MS",    # Vicksburg
    "Simpson, MS":      "Jackson MS",
    "Lincoln, MS":      "Jackson MS",    # Brookhaven
    "Claiborne, MS":    "Jackson MS",    # Port Gibson
    "Adams, MS":        "Jackson MS",    # Natchez
    "Wilkinson, MS":    "Jackson MS",    # Woodville
    "Amite, MS":        "Jackson MS",    # Liberty
    "Pike, MS":         "Jackson MS",    # McComb
    "Franklin, MS":     "Jackson MS",    # Meadville
    "Issaquena, MS":    "Jackson MS",
    "Sharkey, MS":      "Jackson MS",    # Rolling Fork
    "Humphreys, MS":    "Jackson MS",    # Belzoni
    "Holmes, MS":       "Jackson MS",    # Durant
    "Carroll, MS":      "Jackson MS",    # Vaiden
    "Montgomery, MS":   "Jackson MS",    # Winona
    "Grenada, MS":      "Jackson MS",    # Grenada
    "Yalobusha, MS":    "Jackson MS",    # Coffeeville
    "Leflore, MS":      "Jackson MS",    # Greenwood
    "Attala, MS":       "Jackson MS",    # Kosciusko
    "Leake, MS":        "Jackson MS",    # Carthage
    "Scott, MS":        "Jackson MS",    # Forest
    "Lawrence, MS":     "Jackson MS",    # Monticello
    # Gulfport / MS Coast
    "Harrison, MS":     "Gulfport",
    "Hancock, MS":      "Gulfport",
    "Jackson, MS":      "Gulfport",
    "Pearl River, MS":  "Gulfport",      # Picayune
    "Stone, MS":        "Gulfport",
    "George, MS":       "Gulfport",
    "Greene, MS":       "Gulfport",
    "Wayne, MS":        "Gulfport",       # Waynesboro
    # Hattiesburg / Pine Belt
    "Forrest, MS":      "Hattiesburg",    # Hattiesburg
    "Lamar, MS":        "Hattiesburg",    # Lumberton
    "Perry, MS":        "Hattiesburg",
    "Jones, MS":        "Hattiesburg",    # Laurel
    "Covington, MS":    "Hattiesburg",    # Collins
    "Jefferson Davis, MS": "Hattiesburg", # Prentiss
    "Marion, MS":       "Hattiesburg",    # Columbia
    "Walthall, MS":     "Hattiesburg",    # Tylertown
    "Smith, MS":        "Hattiesburg",
    "Jasper, MS":       "Hattiesburg",    # Bay Springs
    "Clarke, MS":       "Hattiesburg",    # Quitman
    "Lauderdale, MS":   "Hattiesburg",    # Meridian
    "Kemper, MS":       "Hattiesburg",
    "Neshoba, MS":      "Hattiesburg",    # Philadelphia
    "Winston, MS":      "Hattiesburg",    # Louisville
    "Noxubee, MS":      "Hattiesburg",    # Macon
    # Tupelo / Northeast MS
    "Lee, MS":          "Tupelo",
    "Pontotoc, MS":     "Tupelo",
    "Union, MS":        "Tupelo",        # New Albany
    "Prentiss, MS":     "Tupelo",        # Booneville
    "Alcorn, MS":       "Tupelo",        # Corinth
    "Tishomingo, MS":   "Tupelo",        # Iuka
    "Itawamba, MS":     "Tupelo",        # Fulton
    "Monroe, MS":       "Tupelo",        # Amory
    "Chickasaw, MS":    "Tupelo",        # Houston
    "Calhoun, MS":      "Tupelo",        # Pittsboro
    "Lafayette, MS":    "Tupelo",        # Oxford
    "Marshall, MS":     "Tupelo",        # Holly Springs
    "Benton, MS":       "Tupelo",
    "Tippah, MS":       "Tupelo",        # Ripley
    "Washington, MS":   "Tupelo",        # Greenville
    "Sunflower, MS":    "Tupelo",        # Indianola
    "Bolivar, MS":      "Tupelo",        # Cleveland
    "Coahoma, MS":      "Tupelo",        # Clarksdale
    "Quitman, MS":      "Tupelo",        # Marks
    "Tallahatchie, MS": "Tupelo",        # Charleston
    "Panola, MS":       "Tupelo",        # Batesville
    "Tate, MS":         "Tupelo",        # Senatobia
    "Oktibbeha, MS":    "Tupelo",        # Starkville
    "Lowndes, MS":      "Tupelo",        # Columbus MS
    "Clay, MS":         "Tupelo",        # West Point
    "Webster, MS":      "Tupelo",
    "Choctaw, MS":      "Tupelo",        # Ackerman

    # ── Alabama ──
    # Mobile metro
    "Mobile, AL":       "Mobile",
    "Baldwin, AL":      "Mobile",
    "Washington, AL":   "Mobile",       # Chatom
    "Clarke, AL":       "Mobile",       # Grove Hill
    "Monroe, AL":       "Mobile",       # Monroeville
    "Conecuh, AL":      "Mobile",       # Evergreen
    "Choctaw, AL":      "Mobile",       # Butler
    "Escambia, AL":     "Mobile",       # Atmore / Brewton
    # Birmingham metro
    "Jefferson, AL":    "Birmingham",
    "Shelby, AL":       "Birmingham",
    "St. Clair, AL":    "Birmingham",    # Pell City
    "Blount, AL":       "Birmingham",    # Oneonta
    "Walker, AL":       "Birmingham",    # Jasper
    "Bibb, AL":         "Birmingham",    # Centreville
    "Talladega, AL":    "Birmingham",    # Talladega
    "Calhoun, AL":      "Birmingham",    # Anniston
    "Chilton, AL":      "Birmingham",    # Clanton
    "Coosa, AL":        "Birmingham",    # Rockford
    "Tallapoosa, AL":   "Birmingham",    # Alexander City
    "Clay, AL":         "Birmingham",    # Ashland
    "Randolph, AL":     "Birmingham",    # Roanoke
    "Cleburne, AL":     "Birmingham",    # Heflin
    "Etowah, AL":       "Birmingham",    # Gadsden
    # Montgomery metro
    "Montgomery, AL":   "Montgomery",
    "Autauga, AL":      "Montgomery",    # Prattville
    "Elmore, AL":       "Montgomery",    # Wetumpka
    "Lowndes, AL":      "Montgomery",    # Hayneville
    "Macon, AL":        "Montgomery",    # Tuskegee
    "Bullock, AL":      "Montgomery",    # Union Springs
    "Pike, AL":         "Montgomery",    # Troy
    "Dallas, AL":       "Montgomery",    # Selma
    "Wilcox, AL":       "Montgomery",    # Camden
    "Butler, AL":       "Montgomery",    # Greenville
    "Crenshaw, AL":     "Montgomery",    # Luverne
    "Chambers, AL":     "Montgomery",    # Valley / Lafayette
    "Lee, AL":          "Montgomery",    # Auburn / Opelika
    # Huntsville / North Alabama
    "Madison, AL":      "Huntsville",
    "Limestone, AL":    "Huntsville",    # Athens
    "Morgan, AL":       "Huntsville",    # Decatur
    "Marshall, AL":     "Huntsville",    # Albertville
    "Jackson, AL":      "Huntsville",    # Scottsboro
    "DeKalb, AL":       "Huntsville",    # Fort Payne
    "Lauderdale, AL":   "Huntsville",    # Florence
    "Colbert, AL":      "Huntsville",    # Muscle Shoals
    "Franklin, AL":     "Huntsville",    # Russellville
    "Lawrence, AL":     "Huntsville",    # Moulton
    "Marion, AL":       "Huntsville",    # Hamilton
    "Winston, AL":      "Huntsville",    # Double Springs
    "Cullman, AL":      "Huntsville",    # Cullman
    "Cherokee, AL":     "Huntsville",    # Centre
    # Tuscaloosa / West Alabama
    "Tuscaloosa, AL":   "Tuscaloosa",
    "Pickens, AL":      "Tuscaloosa",    # Carrollton
    "Greene, AL":       "Tuscaloosa",    # Eutaw
    "Hale, AL":         "Tuscaloosa",    # Greensboro
    "Sumter, AL":       "Tuscaloosa",    # Livingston
    "Marengo, AL":      "Tuscaloosa",    # Linden
    "Perry, AL":        "Tuscaloosa",    # Marion
    "Fayette, AL":      "Tuscaloosa",    # Fayette
    "Lamar, AL":        "Tuscaloosa",    # Vernon
    # Dothan / Southeast Alabama
    "Houston, AL":      "Dothan",
    "Geneva, AL":       "Dothan",
    "Henry, AL":        "Dothan",       # Abbeville
    "Barbour, AL":      "Dothan",       # Eufaula
    "Russell, AL":      "Dothan",       # Phenix City
    "Dale, AL":         "Dothan",       # Ozark
    "Coffee, AL":       "Dothan",       # Enterprise
    "Covington, AL":    "Dothan",       # Andalusia

    # ── Georgia ──
    "Fulton, GA":      "Atlanta",
    "DeKalb, GA":      "Atlanta",
    "Cobb, GA":        "Atlanta",
    "Gwinnett, GA":    "Atlanta",
    "Clayton, GA":     "Atlanta",
    "Cherokee, GA":    "Atlanta",
    "Forsyth, GA":     "Atlanta",
    # ── Florida ──
    "Miami-Dade, FL":  "Miami",
    "Broward, FL":     "Miami",
    "Palm Beach, FL":  "Miami",
    "Hillsborough, FL": "Tampa",
    "Pinellas, FL":    "Tampa",
    "Pasco, FL":      "Tampa",
    "Orange, FL":      "Orlando",
    "Seminole, FL":    "Orlando",
    "Duval, FL":       "Jacksonville",
    "St. Johns, FL":  "Jacksonville",
    "Lee, FL":         "Fort Myers",
    "Collier, FL":     "Fort Myers",
    "Escambia, FL":    "Pensacola",
    "Santa Rosa, FL":  "Pensacola",
    "Okaloosa, FL":    "Pensacola",    # Fort Walton Beach / Destin
    "Leon, FL":        "Tallahassee",
    "Wakulla, FL":     "Tallahassee",   # Crawfordville
    "Jefferson, FL":   "Tallahassee",   # Monticello
    "Madison, FL":     "Tallahassee",   # Madison
    "Taylor, FL":      "Tallahassee",   # Perry
    "Lafayette, FL":   "Tallahassee",   # Mayo
    "Suwannee, FL":    "Tallahassee",   # Live Oak
    "Hamilton, FL":    "Tallahassee",   # Jasper
    "Columbia, FL":    "Tallahassee",   # Lake City
    "Baker, FL":       "Tallahassee",   # Macclenny
    "Union, FL":       "Tallahassee",   # Lake Butler
    "Bradford, FL":    "Tallahassee",   # Starke
    "Gilchrist, FL":   "Tallahassee",   # Trenton
    "Dixie, FL":       "Tallahassee",   # Cross City
    "Levy, FL":        "Tallahassee",   # Bronson
    "Gadsden, FL":     "Tallahassee",   # Quincy
    "Liberty, FL":     "Tallahassee",   # Bristol
    "Jackson, FL":     "Tallahassee",   # Marianna
    "Walton, FL":      "Panama City",   # DeFuniak Springs
    "Bay, FL":         "Panama City",   # Panama City
    "Gulf, FL":        "Panama City",   # Port St. Joe
    "Franklin, FL":    "Panama City",   # Apalachicola
    "Calhoun, FL":     "Panama City",   # Blountstown
    "Holmes, FL":      "Panama City",   # Bonifay
    "Washington, FL":  "Panama City",   # Chipley

    # ── South Carolina ──
    "Richland, SC":    "Columbia",
    "Lexington, SC":   "Columbia",
    "Charleston, SC":  "Charleston",
    "Berkeley, SC":    "Charleston",
    "Dorchester, SC":  "Charleston",
    "Horry, SC":       "Myrtle Beach",
    # ── North Carolina ──
    "Mecklenburg, NC": "Charlotte",
    "Cabarrus, NC":    "Charlotte",
    "Union, NC":       "Charlotte",
    "Gaston, NC":      "Charlotte",
    "Wake, NC":        "Raleigh",
    "Durham, NC":      "Raleigh",
    "Orange, NC":      "Raleigh",
    "Johnston, NC":    "Raleigh",
    "New Hanover, NC": "Wilmington",
    "Brunswick, NC":   "Wilmington",
    # ── Tennessee ──
    "Davidson, TN":    "Nashville",
    "Williamson, TN":  "Nashville",
    "Rutherford, TN":  "Nashville",
    "Wilson, TN":      "Nashville",
    "Sumner, TN":      "Nashville",
    "Shelby, TN":      "Memphis",
    "DeSoto, MS":     "Memphis",
    # ── Virginia / Mid-Atlantic ──
    "Henrico, VA":     "Richmond",
    "Chesterfield, VA": "Richmond",
    "Norfolk, VA":     "Virginia Beach",
    "Chesapeake, VA":  "Virginia Beach",
    # ── Colorado / Plains ──
    "Denver, CO":      "Denver",
    "Arapahoe, CO":    "Denver",
    "Jefferson, CO":   "Denver",
    "Douglas, NE":     "Omaha",
    "Polk, IA":        "Des Moines",
    # ── Ohio Valley ──
    "Marion, IN":      "Indianapolis",
    "Franklin, OH":    "Columbus",
    "Jefferson, KY":   "Louisville",
}

# ── Risk rank → damage_severity + urgency_score mapping ──────────────────
# risk_rank from storm_predictor: 1=Thunderstorm, 2=Marginal, 3=Slight,
# 4=Enhanced, 5=Moderate, 6=High
# urgency_score: 1-10 scale consistent with storm_alert.py
_RISK_RANK_MAP: Dict[int, Tuple[str, int]] = {
    1: ("Light",     2),   # Thunderstorm
    2: ("Light",     3),   # Marginal
    3: ("Moderate",  5),   # Slight
    4: ("Moderate",  7),   # Enhanced
    5: ("Severe",    8),   # Moderate
    6: ("Severe",    9),   # High
}

# Minimum risk_rank to act on (4 = Enhanced or higher)
DEFAULT_MIN_RISK_RANK = 4


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


def _read_config(sb):
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if not r.data:
        return {"enabled": True, "dry_run": True, "min_risk_rank": DEFAULT_MIN_RISK_RANK}
    row = r.data[0]
    cfg = row.get("config_json") or {}
    return {
        "enabled":      row.get("enabled", True),
        "dry_run":      row.get("dry_run", True),
        "min_risk_rank": cfg.get("min_risk_rank", DEFAULT_MIN_RISK_RANK),
    }


def _update_config(sb, status, finished_at):
    sb.table("agent_config").update({
        "last_run_at": finished_at,
        "last_run_status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("agent_name", AGENT_NAME).execute()


def _log_activity(sb, run_id, started_at, status,
                  rows_seen=0, rows_processed=0, rows_blocked=0, rows_errored=0,
                  error=None, summary=None):
    return emit_agent_event(
        sb=sb, agent_name=AGENT_NAME, run_id=run_id,
        started_at=started_at, status=status,
        rows_seen=rows_seen, rows_processed=rows_processed,
        rows_blocked=rows_blocked, rows_errored=rows_errored,
        error=error, summary=summary,
    )


def _fetch_metro_risk(sb, lookback_hours: int = 48) -> List[Dict]:
    """Query storm_risk_log for the latest risk per metro (max risk_rank)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    r = sb.table("storm_risk_log") \
        .select("metro, risk_level, risk_rank") \
        .gte("created_at", cutoff) \
        .execute()
    rows = r.data or []
    if not rows:
        return []

    # Aggregate per-metro: take the highest risk_rank seen in the lookback window
    metro_risk: Dict[str, Dict] = {}
    for row in rows:
        metro = (row.get("metro") or "").strip()
        rank = int(row.get("risk_rank") or 0)
        if not metro:
            continue
        current = metro_risk.get(metro)
        if not current or rank > current["risk_rank"]:
            metro_risk[metro] = {
                "metro": metro,
                "risk_level": row.get("risk_level", ""),
                "risk_rank": rank,
            }

    return list(metro_risk.values())


def _find_targets_for_metro(sb, metro: str, aliases: List[str]) -> List[Dict]:
    """Query active radar_targets in a metro by matching city against aliases."""
    try:
        # Build OR filter: city ILIKE any of the aliases
        or_parts = ",".join([f"city.ilike.%{a}%" for a in aliases])
        r = sb.table("radar_targets") \
            .select("id, city, state, damage_severity, urgency_score") \
            .eq("status", "active") \
            .or_(or_parts) \
            .execute()
        return r.data or []
    except Exception as e:
        log.warning(f"[{AGENT_NAME}] radar_targets query for metro={metro} failed: {e}")
        return []


def run_once(dry_run_override: Optional[bool] = None) -> dict:
    """Run one pipeline cycle.

    1. Fetch latest per-metro risk from storm_risk_log
    2. For each risk metro, find active radar_targets
    3. Map risk → damage_severity + urgency_score
    4. Update radar_targets (upgrades only)
    5. Log to storm_risk_log + agent_activity
    """
    started_at = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    sb = _sb()
    cfg = _read_config(sb)
    dry_run = cfg["dry_run"] if dry_run_override is None else dry_run_override
    min_rank = cfg["min_risk_rank"]

    if not cfg["enabled"]:
        msg = "agent disabled in agent_config — skipping"
        log.info(msg)
        _log_activity(sb, run_id, started_at, "skipped", summary=msg)
        return {"status": "skipped", "reason": msg}

    # ── 1. Fetch metro risk data ──────────────────────────────────────
    metro_risks = _fetch_metro_risk(sb, lookback_hours=48)
    if not metro_risks:
        summary = "storm_risk_log has no entries in the last 48h — nothing to apply"
        log.info(summary)
        _log_activity(sb, run_id, started_at, "ok", summary=summary)
        return {"status": "ok", "note": summary}

    # Filter by min_risk_rank
    qualifying = [m for m in metro_risks if m["risk_rank"] >= min_rank]
    if not qualifying:
        summary = (
            f"{len(metro_risks)} metros with risk data, "
            f"none above min_risk_rank={min_rank}"
        )
        log.info(summary)
        _log_activity(sb, run_id, started_at, "ok", summary=summary)
        return {"status": "ok", "note": summary, "metros_scanned": len(metro_risks)}

    log.info(
        f"[{AGENT_NAME}] {len(qualifying)} qualifying metros "
        f"(out of {len(metro_risks)} total): "
        + ", ".join(f"{m['metro']}(rank={m['risk_rank']})" for m in qualifying)
    )

    # ── 2. Find targets per qualifying metro ──────────────────────────
    total_targets_found = 0
    updates_to_apply: Dict[str, Tuple[str, int]] = {}  # target_id → (severity, urgency)
    severity_fill: Dict[str, str] = {}  # target_id → severity (fill when missing)

    for metro in qualifying:
        metro_name = metro["metro"]
        aliases = _METRO_ALIASES.get(metro_name)
        # Fall back: check if it's a county name that maps to a metro
        if not aliases:
            parent = _COUNTY_TO_METRO.get(metro_name)
            if parent:
                aliases = _METRO_ALIASES.get(parent)
                if aliases:
                    log.info(f"[{AGENT_NAME}] resolved county '{metro_name}' -> metro '{parent}'")
        if not aliases:
            log.debug(f"[{AGENT_NAME}] no alias map for metro={metro_name}, skipping")
            continue

        targets = _find_targets_for_metro(sb, metro["metro"], aliases)
        total_targets_found += len(targets)

        # Map risk → severity + urgency
        sev, urg = _RISK_RANK_MAP.get(metro["risk_rank"], ("Moderate", 5))

        for t in targets:
            tid = t["id"]
            old_sev = (t.get("damage_severity") or "").lower()
            old_urg = int(t.get("urgency_score") or 0)

            # Case 1: urgency needs upgrading → set both severity and urgency
            current = updates_to_apply.get(tid)
            current_urg = current[1] if current else old_urg

            if urg > current_urg:
                updates_to_apply[tid] = (sev, urg)
            # Case 2: urgency already at or above threshold, but severity missing
            # → fill severity without changing urgency
            elif not old_sev or old_sev == "":
                severity_fill[tid] = sev

    # ── 3. Apply updates (urgency + severity) ─────────────────────────
    updated = 0
    errors = 0
    if not dry_run:
        now_iso = datetime.now(timezone.utc).isoformat()

        # Apply urgency upgrades (existing behavior)
        for tid, (sev, urg) in updates_to_apply.items():
            try:
                sb.table("radar_targets").update({
                    "damage_severity": sev,
                    "urgency_score": urg,
                    "updated_at": now_iso,
                }).eq("id", tid).execute()
                updated += 1
            except Exception as e:
                log.warning(f"Failed to update target {tid[:12]}: {e}")
                errors += 1

        # Apply severity-only fills (targets with urgency already high enough)
        filled = 0
        for tid, sev in severity_fill.items():
            # Don't double-update if this target was already in updates_to_apply
            if tid in updates_to_apply:
                continue
            try:
                sb.table("radar_targets").update({
                    "damage_severity": sev,
                    "updated_at": now_iso,
                }).eq("id", tid).execute()
                filled += 1
                updated += 1
            except Exception as e:
                log.warning(f"Failed to severity-fill target {tid[:12]}: {e}")
                errors += 1

        if filled:
            log.info(f"[{AGENT_NAME}] severity_fill: set damage_severity on {filled} targets (urgency already sufficient)")

    total_upgraded = len(updates_to_apply) + len(severity_fill)
    summary = (
        f"[{'DRY-RUN' if dry_run else 'LIVE'}] "
        f"metros={len(qualifying)} "
        f"targets_found={total_targets_found} "
        f"targets_upgraded={len(updates_to_apply)} "
        f"severity_filled={len(severity_fill)} "
        f"targets_updated={updated} "
        f"errors={errors}"
    )
    log.info(summary)
    finished_at = _log_activity(
        sb, run_id, started_at, "ok",
        rows_seen=total_targets_found,
        rows_processed=updated,
        rows_errored=errors,
        summary=summary[:500],
    )
    _update_config(sb, "ok", finished_at)

    return {
        "status": "ok",
        "metros_qualifying": len(qualifying),
        "metros_detail": [
            {"metro": m["metro"], "risk_level": m["risk_level"], "risk_rank": m["risk_rank"]}
            for m in qualifying
        ],
        "targets_found": total_targets_found,
        "targets_upgraded": len(updates_to_apply),
        "severity_filled": len(severity_fill),
        "targets_updated": updated,
        "errors": errors,
        "dry_run": dry_run,
    }


# ── DEFAULT INTERVAL ───────────────────────────────────────────────────
DEFAULT_INTERVAL_SECONDS = 3600  # 1 hour


# ── Loop mode ───────────────────────────────────────────────────────────

async def run_loop(interval_seconds: Optional[int] = None):
    """Run storm_log_to_targets.run_once() in an infinite loop."""
    delay = interval_seconds or DEFAULT_INTERVAL_SECONDS
    log.info(f"[{AGENT_NAME}] running in loop mode (interval={delay}s)")
    while True:
        started = datetime.now(timezone.utc)
        try:
            result = run_once(dry_run_override=None)
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            log.info(f"[{AGENT_NAME}] cycle done in {elapsed:.1f}s — status={result.get('status')}")
        except Exception as e:
            log.exception(f"[{AGENT_NAME}] cycle failed: {e}")
        slept = (datetime.now(timezone.utc) - started).total_seconds()
        await asyncio.sleep(max(10, delay - slept))


def show_status():
    """Print agent status and recent run history."""
    sb = _sb()
    r = sb.table("agent_config").select("*").eq("agent_name", AGENT_NAME).limit(1).execute()
    if r.data:
        row = r.data[0]
        cfg = row.get("config_json") or {}
        print(f"agent:         {AGENT_NAME}")
        print(f"enabled:       {row.get('enabled')}")
        print(f"dry_run:       {row.get('dry_run')}")
        print(f"min_risk_rank: {cfg.get('min_risk_rank', DEFAULT_MIN_RISK_RANK)}")
        print(f"last_run_at:   {row.get('last_run_at')}")
        print(f"last_status:   {row.get('last_run_status')}")
    else:
        print(f"agent:         {AGENT_NAME}  (not initialized — run once to create config)")
    print()
    r2 = sb.table("agent_activity").select(
        "started_at,status,rows_seen,rows_processed,summary"
    ).eq("agent_name", AGENT_NAME).order("started_at", desc=True).limit(5).execute()
    print("recent runs:")
    for row in r2.data:
        sa = (row.get("started_at") or "")[:19]
        st = row.get("status", "")
        rs = row.get("rows_seen", 0)
        rp = row.get("rows_processed", 0)
        sm = (row.get("summary") or "")[:80]
        print(f"  {sa}  {st:10}  seen={rs}  updated={rp}  {sm}")
    print()
    # Show storm_risk_log entries
    r3 = sb.table("storm_risk_log").select("created_at,metro,risk_level,risk_rank") \
        .eq("source", AGENT_NAME).order("created_at", desc=True).limit(8).execute()
    if r3.data:
        print("recent storm_risk_log entries (from this agent):")
        for row in r3.data:
            ca = (row.get("created_at") or "")[:19]
            m  = (row.get("metro") or "")[:30]
            rl = row.get("risk_level", "")
            rr = row.get("risk_rank", 0)
            print(f"  {ca}  {m:30s}  {rl:12}  rank={rr}")


def main():
    p = argparse.ArgumentParser(
        description="Empire AI Storm Log → Radar Targets Pipeline"
    )
    p.add_argument("--dry-run", action="store_true",
                   help="report only, no DB writes")
    p.add_argument("--status", action="store_true",
                   help="print last run + stats")
    p.add_argument("--loop", action="store_true",
                   help="run in loop mode (replaces cron)")
    p.add_argument("--interval", type=int, default=None,
                   help=f"loop interval in seconds (default: {DEFAULT_INTERVAL_SECONDS})")
    args = p.parse_args()
    if args.loop:
        asyncio.run(run_loop(interval_seconds=args.interval))
        return
    if args.status:
        show_status()
        return
    result = run_once(dry_run_override=True if args.dry_run else None)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
