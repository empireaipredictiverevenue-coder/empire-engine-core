from typing import List, Set
from models import Lead
import hashlib

class IncrementalCrawler:
    def __init__(self, db_path: str = ".cache.sqlite"):
        self.seen: Set[str] = set()
        self.db_path = db_path
        self._load_cache()

    def _load_cache(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS seen (fingerprint TEXT PRIMARY KEY)")
        for row in conn.execute("SELECT fingerprint FROM seen"):
            self.seen.add(row[0])
        conn.close()

    def make_fingerprint(self, lead: Lead) -> str:
        key = f"{lead.website}|{lead.phone}|{lead.email}|{lead.address}|{lead.city}"
        return hashlib.md5(key.encode()).hexdigest()

    def filter_new(self, leads: List[Lead]) -> List[Lead]:
        new_leads = []
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        for lead in leads:
            fp = self.make_fingerprint(lead)
            if fp not in self.seen:
                self.seen.add(fp)
                conn.execute("INSERT OR IGNORE INTO seen VALUES (?)", (fp,))
                new_leads.append(lead)
        conn.commit()
        conn.close()
        return new_leads
