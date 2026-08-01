from typing import Optional, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.base import get_db
from app.services.rag_service import rag_service

router = APIRouter(prefix="/rag", tags=["RAG Services"])


class SearchQuery(BaseModel):
    query: str
    top_k: int = 5
    document_ids: Optional[List[str]] = None


@router.post("/search")
def search_documents(
    query_in: SearchQuery,
    db: Session = Depends(get_db),
):
    chunks = rag_service.retrieve_relevant_chunks(
        db, query=query_in.query, top_k=query_in.top_k, doc_ids=query_in.document_ids
    )
    return {"results": chunks, "count": len(chunks)}
