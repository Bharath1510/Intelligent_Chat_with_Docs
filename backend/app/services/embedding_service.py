import math
import re
import hashlib
from typing import List
from app.config import settings
from app.core.logging import logger

# Gemini's embed_content accepts a list; batching is what keeps indexing from
# taking one network round-trip per chunk.
EMBED_BATCH_SIZE = 100

_TOKEN_RE = re.compile(r"[a-z0-9]+")


LOCAL_MODEL_ID = "local-lexical-v1"


class EmbeddingService:
    def __init__(self):
        self.dimension = settings.EMBEDDING_DIMENSION
        self._genai_client = None
        self._initialized = False
        # Vectors from different models are not comparable, so chunks record
        # which one produced them and retrieval skips mismatches.
        self.active_model = LOCAL_MODEL_ID

    def _ensure_client(self):
        """Lazy-init so the Gemini key is guaranteed to be loaded from .env."""
        if self._initialized:
            return
        self._initialized = True
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                self._genai_client = genai.Client(api_key=settings.GEMINI_API_KEY)
                self.active_model = settings.GEMINI_EMBEDDING_MODEL
                logger.info(
                    f"Gemini embeddings active: {settings.GEMINI_EMBEDDING_MODEL} "
                    f"@ {self.dimension}d"
                )
            except Exception as e:
                logger.warning(f"Could not initialize Google GenAI SDK: {e}")
        else:
            logger.info("No GEMINI_API_KEY set, using local lexical embeddings.")

    def embed_text(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of texts, batching API calls. Falls back to local lexical
        vectors (per batch) so indexing and retrieval still work without a key.
        """
        if not texts:
            return []

        self._ensure_client()
        vectors: List[List[float]] = []

        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[start:start + EMBED_BATCH_SIZE]
            vectors.extend(self._embed_batch(batch))

        return vectors

    def _embed_batch(self, batch: List[str]) -> List[List[float]]:
        if self._genai_client:
            try:
                from google.genai import types
                response = self._genai_client.models.embed_content(
                    model=settings.GEMINI_EMBEDDING_MODEL,
                    contents=batch,
                    # Ask for the dimension we store rather than truncating after the fact.
                    config=types.EmbedContentConfig(output_dimensionality=self.dimension),
                )
                embeddings = getattr(response, "embeddings", None) or []
                if len(embeddings) == len(batch):
                    # Reduced-dimension Gemini vectors are not unit length.
                    return [self._normalize(list(e.values)) for e in embeddings]
                logger.warning(
                    f"Gemini returned {len(embeddings)} embeddings for {len(batch)} inputs, "
                    "using local vectors for this batch."
                )
            except Exception as e:
                logger.warning(f"Gemini embedding call failed: {e}. Using local vectors.")

        return [self._lexical_vector(t) for t in batch]

    @staticmethod
    def _normalize(vec: List[float]) -> List[float]:
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec] if norm else vec

    def _lexical_vector(self, text: str) -> List[float]:
        """
        Hashed bag-of-words vector. Unlike a random per-text hash, this makes
        cosine similarity reflect real word overlap, so retrieval works offline.
        ponytail: no IDF weighting, add it if ranking quality matters.
        """
        vec = [0.0] * self.dimension
        for token in _TOKEN_RE.findall(text.lower()):
            slot = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % self.dimension
            vec[slot] += 1.0
        return self._normalize(vec)


embedding_service = EmbeddingService()
