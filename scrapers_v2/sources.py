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
    # Add more verticals here as we expand
]
