import io
import pytest

from app.services import ocr_service as ocr_module
from app.api.v1 import ingestion


PDF_BYTES = b"%PDF-1.4 fake body for upload plumbing"


def _upload(client, name="test_doc.pdf", body=PDF_BYTES):
    return client.post(
        "/api/v1/documents/upload",
        files={"file": (name, io.BytesIO(body), "application/pdf")},
    )


def test_health_reports_engine_state(client):
    data = client.get("/health").json()
    assert data["status"] in ("healthy", "degraded")
    assert "available" in data["ocr"]


def test_rejects_unsupported_extension(client):
    res = client.post(
        "/api/v1/documents/upload",
        files={"file": ("notes.exe", io.BytesIO(b"x"), "application/octet-stream")},
    )
    assert res.status_code == 400


def test_full_pipeline_upload_to_indexed(client, monkeypatch):
    """upload -> OCR -> ocr_ready -> confirm -> indexing -> indexed, with chunks stored."""
    monkeypatch.setattr(
        ocr_module.ocr_service,
        "extract_text_from_file",
        lambda path: {
            "text": "--- Page 1 ---\nRevenue grew.\n\n--- Page 2 ---\nCosts fell.",
            "total_pages": 2,
            "blocks": [
                {"block_id": 1, "page": 1, "text": "Revenue grew.", "confidence": 0.99},
                {"block_id": 2, "page": 2, "text": "Costs fell.", "confidence": 0.97},
            ],
            "metadata": {"engine": "stub"},
        },
    )

    doc_id = _upload(client).json()["document_id"]

    # BackgroundTasks run on response close, so OCR has already completed here.
    status = client.get(f"/api/v1/documents/{doc_id}/status").json()
    assert status["status"] == "ocr_ready", status
    assert status["error_message"] is None

    review = client.get(f"/api/v1/documents/{doc_id}/review").json()
    assert review["total_pages"] == 2
    assert len(review["blocks"]) == 2

    confirmed = client.put(
        f"/api/v1/documents/{doc_id}/confirm",
        json={"edited_text": review["ocr_edited_text"]},
    )
    assert confirmed.status_code == 200

    final = client.get(f"/api/v1/documents/{doc_id}/status").json()
    assert final["status"] == "indexed", final
    assert final["chunk_count"] > 0


def test_reindexing_replaces_chunks_instead_of_duplicating(client, monkeypatch):
    monkeypatch.setattr(
        ocr_module.ocr_service,
        "extract_text_from_file",
        lambda path: {
            "text": "Some extracted body text.",
            "total_pages": 1,
            "blocks": [{"block_id": 1, "page": 1, "text": "Some extracted body text.", "confidence": 0.9}],
            "metadata": {"engine": "stub"},
        },
    )
    doc_id = _upload(client).json()["document_id"]

    payload = {"edited_text": "Some extracted body text."}
    client.put(f"/api/v1/documents/{doc_id}/confirm", json=payload)
    first = client.get(f"/api/v1/documents/{doc_id}/status").json()["chunk_count"]

    client.put(f"/api/v1/documents/{doc_id}/confirm", json=payload)
    second = client.get(f"/api/v1/documents/{doc_id}/status").json()["chunk_count"]

    assert first > 0
    assert second == first, "re-confirming must replace chunks, not append duplicates"


def test_ocr_failure_is_recorded_not_swallowed(client, monkeypatch):
    def boom(path):
        raise ocr_module.OCRUnavailableError("engine down")

    monkeypatch.setattr(ocr_module.ocr_service, "extract_text_from_file", boom)
    doc_id = _upload(client).json()["document_id"]

    status = client.get(f"/api/v1/documents/{doc_id}/status").json()
    assert status["status"] == "failed"
    assert "engine down" in status["error_message"]


def test_confirm_rejects_empty_text(client, monkeypatch):
    monkeypatch.setattr(
        ocr_module.ocr_service,
        "extract_text_from_file",
        lambda path: {"text": "hello", "total_pages": 1, "blocks": [], "metadata": {}},
    )
    doc_id = _upload(client).json()["document_id"]
    res = client.put(f"/api/v1/documents/{doc_id}/confirm", json={"edited_text": "   "})
    assert res.status_code == 400


def test_upload_over_size_limit_is_rejected(client, monkeypatch):
    monkeypatch.setattr(ingestion.settings, "MAX_FILE_SIZE_MB", 0.001)
    res = _upload(client, body=b"x" * 50_000)
    assert res.status_code == 413
