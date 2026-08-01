from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "DocuBrain AI — OCR + RAG Document Chat",
        "engine": "PaddleOCR + LangChain + Gemini"
    }
