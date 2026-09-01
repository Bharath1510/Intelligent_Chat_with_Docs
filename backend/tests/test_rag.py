"""Unit checks for the retrieval logic the chat answers depend on."""
import pytest

from app.services.rag_service import split_pages
from app.services.embedding_service import embedding_service
from app.db.vector_store import SQLiteVectorRepository


def test_split_pages_recovers_page_numbers_from_markers():
    text = "--- Page 1 ---\nalpha\n\n--- Page 7 ---\nbeta"
    assert split_pages(text) == [(1, "alpha"), (7, "beta")]


def test_split_pages_keeps_text_without_markers_on_page_one():
    assert split_pages("no markers here") == [(1, "no markers here")]


def test_split_pages_keeps_preamble_before_first_marker():
    pages = split_pages("intro text\n--- Page 2 ---\nbody")
    assert pages == [(1, "intro text"), (2, "body")]


def test_lexical_vectors_rank_overlapping_text_above_unrelated_text():
    """
    The offline fallback must produce vectors whose cosine reflects word overlap,
    otherwise every chat query scores ~0 and retrieval returns nothing usable.
    """
    query = embedding_service._lexical_vector("quarterly revenue growth")
    related = embedding_service._lexical_vector("revenue growth was strong this quarterly period")
    unrelated = embedding_service._lexical_vector("the cat sat quietly on a warm mat")

    cos = SQLiteVectorRepository._cosine_similarity
    assert cos(query, related) > cos(query, unrelated)
    assert cos(query, related) > 0.2


def test_embed_documents_returns_one_vector_per_input():
    vectors = embedding_service.embed_documents(["first text", "second text", "third text"])
    assert len(vectors) == 3
    assert all(len(v) == embedding_service.dimension for v in vectors)


def test_cosine_similarity_handles_empty_vectors():
    assert SQLiteVectorRepository._cosine_similarity([], [1.0, 2.0]) == 0.0


def test_active_model_resolves_provider_before_reporting(monkeypatch):
    """
    Chunks are labelled with active_model *before* they are embedded. If reading it
    doesn't initialise the provider first, the first document indexed after a
    restart gets Gemini vectors labelled 'local', and retrieval then filters that
    document out entirely — it indexes fine but can never answer.
    """
    from app.services import embedding_service as mod

    import google.genai

    service = mod.EmbeddingService()
    monkeypatch.setattr(mod.settings, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(mod.settings, "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: object())

    # Read it cold, exactly as index_document does before embedding anything.
    assert service.active_model == "gemini-embedding-001"


def test_configured_provider_failure_raises_instead_of_degrading(monkeypatch):
    """
    A transient Gemini error must not silently produce local vectors: the document
    would be stored as 'indexed' while being unsearchable next to Gemini-embedded
    ones. It must fail so the caller can mark it failed and offer a retry.
    """
    from app.services.embedding_service import EmbeddingService, EmbeddingProviderError

    service = EmbeddingService()
    service._initialized = True
    service.active_model = "gemini-embedding-001"

    class BoomClient:
        class models:
            @staticmethod
            def embed_content(**kwargs):
                raise RuntimeError("429 RESOURCE_EXHAUSTED")

    service._genai_client = BoomClient()
    monkeypatch.setattr("app.services.embedding_service.EMBED_BACKOFF_SECONDS", 0)

    with pytest.raises(EmbeddingProviderError, match="unavailable after"):
        service.embed_documents(["some chunk text"])


def test_no_provider_configured_still_uses_local_vectors():
    """Local embedding is a supported mode when no key is set, not an error."""
    from app.services.embedding_service import EmbeddingService

    service = EmbeddingService()
    service._initialized = True
    service._genai_client = None

    vectors = service.embed_documents(["alpha beta", "gamma"])
    assert len(vectors) == 2
    assert any(v != 0.0 for v in vectors[0])


@pytest.mark.parametrize("blocks", [[], None])
def test_ocr_service_never_invents_text(blocks):
    """
    Regression guard: the old fallback returned hardcoded prose when extraction
    produced nothing, so the app indexed and chatted about content that was
    never in the file. Failure must surface as an error instead.
    """
    from app.services.ocr_service import OCRService, OCRExtractionError

    service = OCRService()
    service._initialized = True
    service._paddle = object()  # engine "present" but returns nothing
    service._ocr_blocks = lambda *a, **k: blocks or []

    with pytest.raises(OCRExtractionError):
        service._process_image("scan.png")
