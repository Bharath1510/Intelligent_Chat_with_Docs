import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.base import get_db
from app.db.models import ChatSession, ChatMessage
from app.services.rag_service import rag_service

router = APIRouter(prefix="/chat", tags=["Chat & Streaming"])


class CreateSessionPayload(BaseModel):
    title: Optional[str] = "New Chat Session"
    document_ids: Optional[List[str]] = None


class MessagePayload(BaseModel):
    session_id: str
    query: str
    document_ids: Optional[List[str]] = None


@router.post("/sessions")
def create_chat_session(
    payload: CreateSessionPayload,
    db: Session = Depends(get_db),
):
    session = ChatSession(
        title=payload.title or "New Chat Session",
        document_ids=payload.document_ids
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "id": session.id,
        "title": session.title,
        "document_ids": session.document_ids,
        "created_at": session.created_at
    }


@router.get("/sessions")
def list_chat_sessions(db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()
    return [
        {
            "id": s.id,
            "title": s.title,
            "document_ids": s.document_ids,
            "created_at": s.created_at,
            "updated_at": s.updated_at
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).all()

    return [
        {
            "id": m.id,
            "sender": m.sender,
            "text": m.text,
            "citations": m.citations,
            "created_at": m.created_at
        }
        for m in messages
    ]


@router.get("/stream")
async def stream_chat_query(
    session_id: str = Query(...),
    query: str = Query(...),
    doc_ids: Optional[str] = Query(None),  # Comma-separated doc IDs
    db: Session = Depends(get_db),
):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Record user message
    user_msg = ChatMessage(session_id=session_id, sender="user", text=query)
    db.add(user_msg)
    db.commit()

    # Parse scoped doc IDs
    document_ids_list = None
    if doc_ids:
        document_ids_list = [d.strip() for d in doc_ids.split(",") if d.strip()]
    elif session.document_ids:
        document_ids_list = session.document_ids

    async def event_generator():
        collected_tokens = []
        collected_citations = []

        async for chunk_str in rag_service.generate_rag_response_stream(
            db, query, doc_ids=document_ids_list
        ):
            yield chunk_str
            # Parse internal payload to save complete assistant response
            if chunk_str.startswith("data: "):
                try:
                    data = json.loads(chunk_str[6:].strip())
                    if data.get("type") == "token":
                        collected_tokens.append(data.get("content", ""))
                    elif data.get("type") == "citations":
                        collected_citations = data.get("content", [])
                except Exception:
                    pass

        # Save assistant message to DB
        assistant_text = "".join(collected_tokens)
        assistant_msg = ChatMessage(
            session_id=session_id,
            sender="assistant",
            text=assistant_text,
            citations=collected_citations
        )
        db.add(assistant_msg)
        session.title = query[:40] if session.title == "New Chat Session" else session.title
        db.commit()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
