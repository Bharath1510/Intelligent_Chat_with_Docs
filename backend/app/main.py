import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.core.logging import setup_logging, logger
from app.core.middleware import CorrelationIDMiddleware
from app.db.base import engine, Base, ensure_schema, SessionLocal
from app.db.models import Document, DocumentChunk, ChatSession, ChatMessage
from app.services.ocr_service import ocr_service
from app.api.v1 import ingestion, rag, chat, health

setup_logging()

# Background tasks die with the process, so anything left mid-flight is stale.
_INTERRUPTED_STATUSES = ("processing", "indexing")


def _recover_interrupted_documents():
    db = SessionLocal()
    try:
        stuck = db.query(Document).filter(Document.status.in_(_INTERRUPTED_STATUSES)).all()
        for doc in stuck:
            interrupted_stage = "OCR" if doc.status == "processing" else "Indexing"
            doc.status = "failed"
            doc.error_message = (
                f"{interrupted_stage} was interrupted when the server restarted. "
                "Use Retry to run it again."
            )
            logger.warning(
                f"Recovered interrupted document {doc.filename} ({doc.id}) from {interrupted_stage}"
            )
        if stuck:
            db.commit()
    finally:
        db.close()


def _warm_ocr_engine():
    """First PaddleOCR init downloads models; do it off the request path."""
    status = ocr_service.engine_status()
    if status["available"]:
        logger.info("PaddleOCR engine warm and ready.")
    else:
        logger.error(f"PaddleOCR engine unavailable: {status['error']}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database schema...")
    ensure_schema()
    _recover_interrupted_documents()
    logger.info("Database ready.")
    if not settings.TESTING:
        threading.Thread(target=_warm_ocr_engine, daemon=True).start()
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CorrelationIDMiddleware)

app.include_router(health.router)
# Also under /api/v1 so the frontend reaches it through the same proxied prefix.
app.include_router(health.router, prefix=settings.API_V1_STR)
app.include_router(ingestion.router, prefix=settings.API_V1_STR)
app.include_router(rag.router, prefix=settings.API_V1_STR)
app.include_router(chat.router, prefix=settings.API_V1_STR)


@app.get("/")
def root_redirect():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
        "api_v1": settings.API_V1_STR,
    }
