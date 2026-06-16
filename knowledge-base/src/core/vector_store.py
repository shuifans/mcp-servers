import logging

from .db import Database

log = logging.getLogger(__name__)


class VectorStore:
    collection = "knowledge_chunks"

    def __init__(self, url: str, model_name: str, db: Database, enabled: bool = True):
        self.db, self.enabled, self.model = db, enabled, None
        try:
            if enabled:
                from qdrant_client import QdrantClient
                from qdrant_client.models import Distance, VectorParams
                from sentence_transformers import SentenceTransformer
                self.model = SentenceTransformer(model_name)
                self.client = QdrantClient(url=url, timeout=5)
                dimension = self.model.get_sentence_embedding_dimension()
                if not self.client.collection_exists(self.collection):
                    self.client.create_collection(self.collection, vectors_config=VectorParams(size=dimension, distance=Distance.COSINE))
        except Exception as exc:
            log.warning("Vector search disabled: %s", exc)
            self.enabled = False

    def upsert(self, chunks: list[dict]) -> None:
        if not self.enabled:
            return
        from qdrant_client.models import PointStruct
        vectors = self.model.encode([c["content"] for c in chunks], normalize_embeddings=True).tolist()
        points = [
            PointStruct(
                id=int(c["chunk_id"][:15], 16),
                vector=v,
                payload={"chunk_id": c["chunk_id"], "source_type": c["source_type"]},
            )
            for c, v in zip(chunks, vectors)
        ]
        self.client.upsert(self.collection, points)

    def search(self, query: str, limit: int = 20, sources: list[str] | None = None):
        if not self.enabled:
            return []
        vector = self.model.encode(query, normalize_embeddings=True).tolist()
        hits = self.client.query_points(self.collection, query=vector, limit=limit).points
        results = self.db.get_chunks([x.payload["chunk_id"] for x in hits])
        if sources:
            results = [x for x in results if x.source_type in sources]
        scores = {x.payload["chunk_id"]: x.score for x in hits}
        for result in results:
            result.score = scores[result.chunk_id]
        return results
