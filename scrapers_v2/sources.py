from typing import List, Dict

SOURCES: List[Dict] = [
    {
        "vertical": "Public Adjuster",
        "scraper": "public_adjuster_async",
        "urls": [
            "https://www.bbb.org/search?term=public+adjuster&location=Texas",
        ],
        "rate_limit": 3.0,
        "priority": 1
    },
    {
        "vertical": "Restoration",
        "scraper": "restoration_async",
        "urls": [
            "https://www.bbb.org/search?term=restoration&location=Texas",
        ],
        "rate_limit": 3.0,
        "priority": 1
    },
    {
        "vertical": "Commercial", "scraper": "commercial_async", "urls": ["https://www.bbb.org/search?term=commercial+contractor&location=Texas"], "rate_limit": 3.0, "priority": 1
    },
    {
        "vertical": "HVAC", "scraper": "hvac_async", "urls": ["https://www.bbb.org/search?term=hvac&location=Texas"], "rate_limit": 3.0, "priority": 1
    },
    {
        "vertical": "Solar", "scraper": "solar_async", "urls": ["https://www.bbb.org/search?term=solar+installer&location=Texas"], "rate_limit": 3.0, "priority": 1
    },
    # Add more verticals here as we expand
]
