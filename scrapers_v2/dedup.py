from typing import List
from models import Lead

def deduplicate(leads: List[Lead], existing: set) -> List[Lead]:
    """
    Deduplicate leads using website + phone + email fingerprint.
    `existing` should be a set of fingerprints from the database.
    """
    unique = []
    for lead in leads:
        fingerprint = f"{lead.website}|{lead.phone}|{lead.email}"
        if fingerprint not in existing:
            unique.append(lead)
            existing.add(fingerprint)
    return unique
