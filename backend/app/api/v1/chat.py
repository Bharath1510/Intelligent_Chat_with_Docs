import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.base import get_db, SessionLocal
from app.db.models import ChatSession, ChatMessage
from app.services.rag_service import rag_service
from app.core.logging import logger

router = APIRouter(prefix="/chat", tags=["Chat & Streaming"])

DEFAULT_TITLE = "New Chat Session"


class CreateSessionPayload(BaseModel):
    title: Optional[str] = DEFAULT_TITLE
    document_ids: Optional[List[str]] = None


def _serialize_session(s: ChatSession) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "document_ids": s.document_ids,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


@router.post("/sessions")
def create_chat_session(payload: CreateSessionPayload, db: Session = Depends(get_db)):
    session = ChatSession(
        title=payload.title or DEFAULT_TITLE,
        document_ids=payload.document_ids or None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info(f"Chat session created: {session.id}")
    return _serialize_session(session)


@router.get("/sessions")
def list_chat_sessions(db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()
    return [_serialize_session(s) for s in sessions]


@router.delete("/sessions/{session_id}")
def delete_chat_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    db.delete(session)
    db.commit()
    logger.info(f"Chat session deleted: {session_id}")
    return {"message": "Chat session deleted"}


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
            "created_at": m.created_at,
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

    if doc_ids:
        document_ids_list = [d.strip() for d in doc_ids.split(",") if d.strip()]
    else:
        document_ids_list = session.document_ids or None

    async def event_generator():
        # The request-scoped session is closed once this response starts streaming,
        # so the generator gets its own that it owns for the whole stream.
        stream_db = SessionLocal()
        collected_tokens: List[str] = []
        collected_citations: List[dict] = []
        try:
            stream_db.add(ChatMessage(session_id=session_id, sender="user", text=query))
            stream_db.commit()

            async for chunk_str in rag_service.generate_rag_response_stream(
                stream_db, query, doc_ids=document_ids_list
            ):
                yield chunk_str
                if not chunk_str.startswith("data: "):
                    continue
                try:
                    data = json.loads(chunk_str[6:].strip())
                except json.JSONDecodeError:
                    continue
                if data.get("type") == "token":
                    collected_tokens.append(data.get("content", ""))
                elif data.get("type") == "citations":
                    collected_citations = data.get("content", [])
        except Exception as e:
            logger.exception(f"Chat stream failed for session {session_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        finally:
            try:
                assistant_text = "".join(collected_tokens)
                if assistant_text:
                    stream_db.add(ChatMessage(
                        session_id=session_id,
                        sender="assistant",
                        text=assistant_text,
                        citations=collected_citations,
                    ))
                chat_session = stream_db.query(ChatSession).filter(
                    ChatSession.id == session_id
                ).first()
                if chat_session and chat_session.title == DEFAULT_TITLE:
                    chat_session.title = query[:40]
                stream_db.commit()
                logger.info(
                    f"Chat turn stored for session {session_id}: "
                    f"{len(assistant_text)} chars, {len(collected_citations)} citations"
                )
            except Exception as e:
                logger.exception(f"Could not persist chat turn for {session_id}: {e}")
            finally:
                stream_db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
