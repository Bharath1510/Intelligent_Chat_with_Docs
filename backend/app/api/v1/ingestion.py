import os
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.config import settings
from app.db.base import get_db, SessionLocal
from app.db.models import Document, DocumentChunk
from app.services.ocr_service import ocr_service
from app.services.rag_service import rag_service
from app.core.logging import logger

router = APIRouter(prefix="/documents", tags=["Document Ingestion & OCR"])

CHUNK_BYTES = 1024 * 1024


class OCRConfirmPayload(BaseModel):
    edited_text: str


def _fail(db: Session, document_id: str, message: str):
    """Record a terminal failure so the UI can show why instead of spinning forever."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if doc:
        doc.status = "failed"
        doc.error_message = message
        db.commit()


def _run_ocr(document_id: str):
    """Extract text with PaddleOCR. Runs as a FastAPI background task."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(f"OCR task: document {document_id} not found")
            return

        doc.status = "processing"
        doc.error_message = None
        db.commit()
        logger.info(f"OCR started for {doc.filename} ({document_id})")

        result = ocr_service.extract_text_from_file(doc.file_path)

        doc.ocr_raw_text = result.get("text", "")
        doc.ocr_edited_text = result.get("text", "")
        doc.total_pages = result.get("total_pages", 1)
        doc.ocr_metadata = result.get("blocks", [])
        doc.status = "ocr_ready"
        doc.error_message = None
        db.commit()

        logger.info(
            f"OCR finished for {doc.filename} ({document_id}): "
            f"{len(doc.ocr_metadata)} blocks, {doc.total_pages} page(s), "
            f"engine={result.get('metadata', {}).get('engine')}"
        )
    except Exception as e:
        logger.exception(f"OCR failed for document {document_id}: {e}")
        _fail(db, document_id, f"OCR failed: {e}")
    finally:
        db.close()


def _run_indexing(document_id: str):
    """Chunk, embed and store vectors. Runs as a FastAPI background task."""
    db = SessionLocal()
    try:
        logger.info(f"Indexing started for document {document_id}")
        chunks_indexed = rag_service.index_document(db, document_id)
        logger.info(f"Indexing finished for document {document_id}: {chunks_indexed} chunks")
    except Exception as e:
        logger.exception(f"Indexing failed for document {document_id}: {e}")
        _fail(db, document_id, f"Indexing failed: {e}")
    finally:
        db.close()


def _save_upload(file: UploadFile, file_path: str) -> int:
    """Stream to disk, aborting if the file exceeds the configured limit."""
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    written = 0
    try:
        with open(file_path, "wb") as buffer:
            while chunk := file.file.read(CHUNK_BYTES):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {settings.MAX_FILE_SIZE_MB}MB limit.",
                    )
                buffer.write(chunk)
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise
    return written


def _serialize(doc: Document) -> dict:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_size": doc.file_size,
        "content_type": doc.content_type,
        "status": doc.status,
        "total_pages": doc.total_pages,
        "error_message": doc.error_message,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension {ext} not allowed. Supported formats: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )

    file_id = str(uuid.uuid4())
    file_path = os.path.join(settings.UPLOAD_DIR, f"{file_id}_{file.filename}")
    file_size = _save_upload(file, file_path)

    doc = Document(
        id=file_id,
        filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        content_type=file.content_type or "application/octet-stream",
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    logger.info(f"Upload accepted: {doc.filename} ({file_size} bytes), id={doc.id}")
    background_tasks.add_task(_run_ocr, doc.id)

    return {
        "message": "File uploaded successfully. OCR processing started.",
        "document_id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
    }


@router.get("")
def list_documents(status_filter: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Document)
    if status_filter:
        query = query.filter(Document.status == status_filter)
    return [_serialize(d) for d in query.order_by(Document.created_at.desc()).all()]


@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return _serialize(doc)


@router.get("/{document_id}/status")
def get_document_status(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "total_pages": doc.total_pages,
        "error_message": doc.error_message,
        "chunk_count": db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).count(),
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
        "total_pages": doc.total_pages,
        "error_message": doc.error_message,
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
    if not payload.edited_text.strip():
        raise HTTPException(status_code=400, detail="Cannot index an empty document.")

    doc.ocr_edited_text = payload.edited_text
    doc.status = "indexing"
    doc.error_message = None
    db.commit()

    logger.info(f"OCR text confirmed for {doc.filename} ({document_id}), indexing queued")
    background_tasks.add_task(_run_indexing, doc.id)

    return {
        "message": "OCR text saved. Indexing started.",
        "document_id": doc.id,
        "status": doc.status,
    }


@router.post("/{document_id}/reprocess")
def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Re-run OCR — the way out of a failed or interrupted extraction."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=410, detail="The uploaded file is no longer on disk.")

    doc.status = "uploaded"
    doc.error_message = None
    db.commit()

    logger.info(f"Reprocess requested for {doc.filename} ({document_id})")
    background_tasks.add_task(_run_ocr, doc.id)
    return {"message": "Reprocessing started.", "document_id": doc.id, "status": doc.status}


@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    filename = doc.filename
    if os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except Exception as e:
            logger.warning(f"Could not delete file for {document_id}: {e}")

    db.delete(doc)
    db.commit()

    logger.info(f"Deleted document {filename} ({document_id}) and its chunks")
    return {"message": "Document deleted successfully"}
