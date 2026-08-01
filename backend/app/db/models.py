import uuid
import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, JSON
from sqlalchemy.orm import relationship
from app.db.base import Base


def _utcnow():
    """Naive UTC, matching the existing column values; utcnow() is deprecated in 3.12+."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=False)
    content_type = Column(String(100), nullable=False)
    # uploaded -> processing (OCR) -> ocr_ready -> indexing -> indexed | failed
    status = Column(String(50), default="uploaded")
    ocr_raw_text = Column(Text, nullable=True)
    ocr_edited_text = Column(Text, nullable=True)
    total_pages = Column(Integer, default=1)
    ocr_metadata = Column(JSON, nullable=True)  # bounding boxes, confidence per block
    error_message = Column(Text, nullable=True)  # why status == "failed", shown in the UI
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, default=1)
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    embedding_json = Column(Text, nullable=True)  # JSON-serialized float vector (SQLite-compatible)
    chunk_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    document = relationship("Document", back_populates="chunks")

    @property
    def embedding(self):
        """Deserialize embedding from JSON text."""
        if self.embedding_json:
            return json.loads(self.embedding_json)
        return None

    @embedding.setter
    def embedding(self, value):
        """Serialize embedding list to JSON text."""
        if value is not None:
            self.embedding_json = json.dumps(value)
        else:
            self.embedding_json = None


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), default="New Chat")
    document_ids = Column(JSON, nullable=True)  # List of scoped doc IDs, null/empty = all docs
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    sender = Column(String(50), nullable=False)  # user, assistant
    text = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True)  # [{doc_id, filename, page_number, snippet}]
    created_at = Column(DateTime, default=_utcnow)

    session = relationship("ChatSession", back_populates="messages")
