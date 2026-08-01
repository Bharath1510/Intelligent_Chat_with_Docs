import os
import uuid
import shutil
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.config import settings
from app.db.base import get_db
from app.db.models import Document
from app.services.ocr_service import ocr_service
from app.services.rag_service import rag_service
from app.core.logging import logger

router = APIRouter(prefix="/documents", tags=["Document Ingestion & OCR"])


class OCRConfirmPayload(BaseModel):
    edited_text: str


def _run_ocr(document_id: str):
    """Run OCR extraction synchronously (replaces Celery task)."""
    from app.db.base import SessionLocal
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(f"Document {document_id} not found for OCR task")
            return

        doc.status = "processing"
        db.commit()

        logger.info(f"Starting OCR extraction for file: {doc.file_path}")
        result = ocr_service.extract_text_from_file(doc.file_path)

        doc.ocr_raw_text = result.get("text", "")
        doc.ocr_edited_text = result.get("text", "")
        doc.total_pages = result.get("total_pages", 1)
        doc.ocr_metadata = result.get("blocks", [])
        doc.status = "ocr_ready"
        db.commit()

        logger.info(f"OCR extraction finished for document {document_id}")
    except Exception as e:
        logger.error(f"OCR task failed for document {document_id}: {e}")
        try:
            doc.status = "failed"
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


def _run_indexing(document_id: str):
    """Run vector indexing synchronously (replaces Celery task)."""
    from app.db.base import SessionLocal
    db = SessionLocal()
    try:
        logger.info(f"Starting indexing for document {document_id}")
        chunks_indexed = rag_service.index_document(db, document_id)
        logger.info(f"Indexed {chunks_indexed} chunks for document {document_id}")
    except Exception as e:
        logger.error(f"Indexing failed for document {document_id}: {e}")
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.status = "failed"
            db.commit()
    finally:
        db.close()


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension {ext} not allowed. Supported formats: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    file_id = str(uuid.uuid4())
    stored_filename = f"{file_id}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, stored_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size = os.path.getsize(file_path)

    doc = Document(
        id=file_id,
        filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        content_type=file.content_type or "application/octet-stream",
        status="uploaded"
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Run OCR in background (FastAPI BackgroundTasks replaces Celery)
    background_tasks.add_task(_run_ocr, doc.id)

    return {
        "message": "File uploaded successfully. OCR processing started.",
        "document_id": doc.id,
        "filename": doc.filename,
        "status": doc.status
    }


@router.get("")
def list_documents(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Document)
    if status_filter:
        query = query.filter(Document.status == status_filter)

    docs = query.order_by(Document.created_at.desc()).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "file_size": d.file_size,
            "content_type": d.content_type,
            "status": d.status,
            "total_pages": d.total_pages,
            "created_at": d.created_at,
            "updated_at": d.updated_at
        }
        for d in docs
    ]


@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{document_id}/status")
def get_document_status(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "total_pages": doc.total_pages
    }


@router.get("/{document_id}/review")
def get_ocr_review_data(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "ocr_raw_text": doc.ocr_raw_text or "",
        "ocr_edited_text": doc.ocr_edited_text or doc.ocr_raw_text or "",
        "blocks": doc.ocr_metadata or [],
        "total_pages": doc.total_pages
    }


@router.put("/{document_id}/confirm")
def confirm_and_index_document(
    document_id: str,
    payload: OCRConfirmPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc.ocr_edited_text = payload.edited_text
    doc.status = "processing"
    db.commit()

    # Run indexing in background
    background_tasks.add_task(_run_indexing, doc.id)

    return {
        "message": "OCR text saved. Indexing started.",
        "document_id": doc.id,
        "status": doc.status
    }


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove physical file if exists
    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception as e:
            logger.warning(f"File delete error: {e}")

    db.delete(doc)
    db.commit()

    return {"message": "Document deleted successfully"}
