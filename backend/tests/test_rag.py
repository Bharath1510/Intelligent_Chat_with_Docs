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
