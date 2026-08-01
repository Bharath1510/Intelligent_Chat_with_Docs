import json
import math
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import DocumentChunk, Document
from app.core.logging import logger

RRF_K = 60


class VectorStoreRepository(ABC):
    """Abstract interface — can be swapped for Qdrant, Pinecone, etc."""

    @abstractmethod
    def add_chunks(self, db: Session, chunks: List[Dict[str, Any]]) -> List[str]:
        pass

    @abstractmethod
    def delete_by_document(self, db: Session, document_id: str) -> int:
        pass

    @abstractmethod
    def vector_search(self, db: Session, query_vector: List[float], top_k: int = 5, doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def hybrid_search(self, db: Session, query_text: str, query_vector: List[float], top_k: int = 5, doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        pass


class SQLiteVectorRepository(VectorStoreRepository):
    """
    SQLite-backed vector store using JSON-serialized embeddings
    and Python-side cosine similarity. Perfect for portfolio-scale data.
    ponytail: full scan per query, swap in a real vector DB past ~10k chunks.
    """

    def add_chunks(self, db: Session, chunks: List[Dict[str, Any]]) -> List[str]:
        chunk_ids = []
        for item in chunks:
            chunk_obj = DocumentChunk(
                document_id=item["document_id"],
                page_number=item.get("page_number", 1),
                chunk_index=item["chunk_index"],
                chunk_text=item["chunk_text"],
                embedding_json=json.dumps(item["embedding"]) if item.get("embedding") else None,
                chunk_metadata=item.get("metadata", {})
            )
            db.add(chunk_obj)
            chunk_ids.append(chunk_obj.id)
        db.commit()
        return chunk_ids

    def delete_by_document(self, db: Session, document_id: str) -> int:
        """Drop every chunk for a document so re-indexing replaces instead of duplicating."""
        deleted = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).delete(synchronize_session=False)
        db.commit()
        return deleted

    def _load_chunks(self, db: Session, doc_ids: Optional[List[str]] = None):
        """
        Only return chunks embedded by the model we are querying with — vectors from
        two different models share a dimension but not a space, so mixing them
        produces confident nonsense. Mismatched documents need re-indexing.
        """
        from app.services.embedding_service import embedding_service

        query = db.query(DocumentChunk, Document.filename).join(
            Document, DocumentChunk.document_id == Document.id
        )
        if doc_ids:
            query = query.filter(DocumentChunk.document_id.in_(doc_ids))
        rows = query.all()

        active = embedding_service.active_model
        usable, stale = [], set()
        for chunk, doc_name in rows:
            if (chunk.chunk_metadata or {}).get("embed_model", active) == active:
                usable.append((chunk, doc_name))
            else:
                stale.add(doc_name)

        if stale:
            logger.warning(
                f"Skipped chunks embedded with an older model in: {', '.join(sorted(stale))}. "
                f"Re-index them to make them searchable again."
            )
        return usable

    @staticmethod
    def _as_result(chunk, doc_name: str) -> Dict[str, Any]:
        return {
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "page_number": chunk.page_number,
            "chunk_index": chunk.chunk_index,
            "text": chunk.chunk_text,
            "doc_name": doc_name,
        }

    def vector_search(self, db: Session, query_vector: List[float], top_k: int = 5, doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Cosine similarity search computed in Python over SQLite-stored embeddings."""
        scored = []
        for chunk, doc_name in self._load_chunks(db, doc_ids):
            if not chunk.embedding_json:
                continue
            sim = self._cosine_similarity(query_vector, json.loads(chunk.embedding_json))
            item = self._as_result(chunk, doc_name)
            item["similarity"] = sim
            item["score"] = sim
            scored.append(item)

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    def hybrid_search(self, db: Session, query_text: str, query_vector: List[float], top_k: int = 5, doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Reciprocal Rank Fusion between cosine vector search and keyword overlap."""
        rows = self._load_chunks(db, doc_ids)
        if not rows:
            return []

        keywords = {k.lower() for k in query_text.split() if len(k) > 2}

        vec_ranked, kw_ranked, by_id = [], [], {}
        for chunk, doc_name in rows:
            item = self._as_result(chunk, doc_name)
            item["similarity"] = (
                self._cosine_similarity(query_vector, json.loads(chunk.embedding_json))
                if chunk.embedding_json else 0.0
            )
            by_id[chunk.id] = item

            vec_ranked.append(item)
            matches = sum(1 for kw in keywords if kw in chunk.chunk_text.lower())
            if matches:
                item["keyword_matches"] = matches
                kw_ranked.append(item)

        vec_ranked.sort(key=lambda x: x["similarity"], reverse=True)
        kw_ranked.sort(key=lambda x: x["keyword_matches"], reverse=True)

        rrf: Dict[str, float] = {}
        for ranked in (vec_ranked[:top_k * 3], kw_ranked[:top_k * 3]):
            for rank, item in enumerate(ranked, 1):
                rrf[item["chunk_id"]] = rrf.get(item["chunk_id"], 0.0) + 1.0 / (RRF_K + rank)

        combined = []
        for chunk_id, score in rrf.items():
            item = by_id[chunk_id].copy()
            item["score"] = round(score, 6)
            combined.append(item)

        # Fused rank decides the order; similarity only breaks ties.
        combined.sort(key=lambda x: (x["score"], x["similarity"]), reverse=True)
        return combined[:top_k]

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        if not vec_a or not vec_b:
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a)) or 1e-9
        norm_b = math.sqrt(sum(b * b for b in vec_b)) or 1e-9
        return dot / (norm_a * norm_b)
