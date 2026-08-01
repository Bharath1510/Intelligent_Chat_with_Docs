import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

# Locate .env relative to this file (backend/app/config.py → ../../.env = project root)
_env_file = str(Path(__file__).resolve().parent.parent.parent / ".env")

class Settings(BaseSettings):
    PROJECT_NAME: str = "DocuBrain AI — OCR + RAG Document Chat"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Database (SQLite for simplicity)
    DATABASE_URL: str = "sqlite:///./local_ocr_rag.db"
    
    # AI / Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_EMBEDDING_MODEL: str = "text-embedding-004"
    
    # Storage
    UPLOAD_DIR: str = os.path.join(os.getcwd(), "storage_uploads")
    
    # Limits
    MAX_FILE_SIZE_MB: int = 25
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".png", ".jpg", ".jpeg", ".tiff"]

    model_config = SettingsConfigDict(env_file=_env_file, extra="ignore")

settings = Settings()

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
