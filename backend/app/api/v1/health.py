from fastapi import APIRouter
from app.config import settings
from app.services.ocr_service import ocr_service

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    """Reports what is actually loaded, so the UI never advertises a dead engine."""
    ocr = ocr_service.engine_status()
    return {
        "status": "healthy" if ocr["available"] else "degraded",
        "service": settings.PROJECT_NAME,
        "ocr": ocr,
        "llm": {
            "provider": "Google Gemini",
            "model": settings.GEMINI_MODEL,
            "configured": bool(settings.GEMINI_API_KEY),
        },
    }
