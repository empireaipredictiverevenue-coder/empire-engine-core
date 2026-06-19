from typing import List
from models import Lead
import hashlib

try:
    from sentence_transformers import SentenceTransformer
    import chromadb
    EMBEDDINGS_AVAILABLE = True
except:
    EMBEDDINGS_AVAILABLE = False

class SemanticDeduplicator:
    def __init__(self):
        self.model = None
        self.collection = None
        if EMBEDDINGS_AVAILABLE:
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
            client = chromadb.Client()
            self.collection = client.get_or_create_collection("leads")

    def is_duplicate(self, lead: Lead) -> bool:
        if not self.collection or not self.model:
            return False  # fallback to basic dedup

        text = f"{lead.name} {lead.address} {lead.city} {lead.phone}"
        embedding = self.model.encode(text).tolist()

        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=1
        )
        if results["distances"] and results["distances"][0][0] < 0.15:
            return True
        return False

    def add(self, lead: Lead):
        if not self.collection or not self.model:
            return
        text = f"{lead.name} {lead.address} {lead.city} {lead.phone}"
        embedding = self.model.encode(text).tolist()
        self.collection.add(
            embeddings=[embedding],
            documents=[text],
            ids=[hashlib.md5(text.encode()).hexdigest()]
        )
