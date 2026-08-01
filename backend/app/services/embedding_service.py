import math
import hashlib
from typing import List
from app.config import settings
from app.core.logging import logger

class EmbeddingService:
    def __init__(self):
        self.dimension = 768
        self._genai_client = None
        self._initialized = False

    def _ensure_client(self):
        """Lazy-init so the Gemini key is guaranteed to be loaded from .env."""
        if self._initialized:
            return
        self._initialized = True
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                self._genai_client = genai.Client(api_key=settings.GEMINI_API_KEY)
                logger.info("Google GenAI client initialized for embeddings.")
            except Exception as e:
                logger.warning(f"Could not initialize Google GenAI SDK: {e}")

    def embed_text(self, text: str) -> List[float]:
        """
        Generates a 768-dimensional embedding vector for text.
        Uses Gemini text-embedding-004 API if key configured, otherwise deterministic normalized hash vector.
        """
        self._ensure_client()
        if self._genai_client and settings.GEMINI_API_KEY:
            try:
                response = self._genai_client.models.embed_content(
                    model=settings.GEMINI_EMBEDDING_MODEL,
                    contents=text
                )
                if response and response.embeddings and len(response.embeddings) > 0:
                    return list(response.embeddings[0].values)[:self.dimension]
                elif response and hasattr(response, 'embedding') and response.embedding:
                    return list(response.embedding.values)[:self.dimension]
            except Exception as e:
                logger.warning(f"Gemini embedding API call failed: {e}. Using fallback vector generator.")

        return self._generate_deterministic_vector(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]

    def _generate_deterministic_vector(self, text: str) -> List[float]:
        import random
        clean_text = text.lower().strip()
        seed = int(hashlib.md5(clean_text.encode('utf-8')).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        vec = [rng.uniform(-1.0, 1.0) for _ in range(self.dimension)]
        norm = math.sqrt(sum(x * x for x in vec)) or 1e-9
        return [x / norm for x in vec]

embedding_service = EmbeddingService()
