import json
import math
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.db.models import DocumentChunk, Document
from app.core.logging import logger


class VectorStoreRepository(ABC):
    """Abstract interface — can be swapped for Qdrant, Pinecone, etc."""

    @abstractmethod
    def add_chunks(self, db: Session, chunks: List[Dict[str, Any]]) -> List[str]:
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

    def vector_search(self, db: Session, query_vector: List[float], top_k: int = 5, doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Cosine similarity search computed in Python over SQLite-stored embeddings."""
        query = db.query(DocumentChunk, Document.filename).join(
            Document, DocumentChunk.document_id == Document.id
        )
        if doc_ids:
            query = query.filter(DocumentChunk.document_id.in_(doc_ids))
        all_chunks = query.all()

        scored = []
        for chunk, doc_name in all_chunks:
            if not chunk.embedding_json:
                continue
            emb = json.loads(chunk.embedding_json)
            sim = self._cosine_similarity(query_vector, emb)
            scored.append({
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "text": chunk.chunk_text,
                "doc_name": doc_name,
                "similarity": sim,
                "score": sim,
            })

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    def hybrid_search(self, db: Session, query_text: str, query_vector: List[float], top_k: int = 5, doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Reciprocal Rank Fusion (RRF) between vector cosine search and keyword BM25-style match.
        """
        vec_results = self.vector_search(db, query_vector, top_k=top_k * 2, doc_ids=doc_ids)

        # Simple keyword ranking for RRF
        keywords = [k.lower() for k in query_text.split() if len(k) > 2]
        query = db.query(DocumentChunk, Document.filename).join(
            Document, DocumentChunk.document_id == Document.id
        )
        if doc_ids:
            query = query.filter(DocumentChunk.document_id.in_(doc_ids))
        all_chunks = query.all()

        kw_scored = []
        for chunk, doc_name in all_chunks:
            text_lower = chunk.chunk_text.lower()
            matches = sum(1 for kw in keywords if kw in text_lower)
            if matches > 0:
                kw_scored.append({
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.chunk_text,
                    "doc_name": doc_name,
                    "match_count": matches
                })
        kw_scored.sort(key=lambda x: x["match_count"], reverse=True)

        # Apply Reciprocal Rank Fusion (RRF, k=60)
        rrf_scores = {}
        chunks_by_id = {}

        for rank, item in enumerate(vec_results, 1):
            cid = item["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (60 + rank))
            chunks_by_id[cid] = item

        for rank, item in enumerate(kw_scored[:top_k * 2], 1):
            cid = item["chunk_id"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (60 + rank))
            if cid not in chunks_by_id:
                item["similarity"] = 0.5
                chunks_by_id[cid] = item

        combined = []
        for cid, score in rrf_scores.items():
            item = chunks_by_id[cid].copy()
            item["score"] = round(score * 100, 4)
            combined.append(item)

        combined.sort(key=lambda x: (x.get("similarity", 0), x["score"]), reverse=True)
        return combined[:top_k]

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a)) or 1e-9
        norm_b = math.sqrt(sum(b * b for b in vec_b)) or 1e-9
        return dot / (norm_a * norm_b)
