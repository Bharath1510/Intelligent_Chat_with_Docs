import io

def test_document_upload_flow(client):
    # Register & Login as Editor
    reg = client.post("/api/v1/auth/register", json={
        "email": "editor@example.com",
        "password": "Password123!",
        "full_name": "Editor User",
        "role": "Editor"
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload test document file
    file_content = b"Enterprise OCR Test File Content\nSection 1: Architecture."
    files = {"file": ("test_doc.pdf", io.BytesIO(file_content), "application/pdf")}

    upload_res = client.post("/api/v1/documents/upload", files=files, headers=headers)
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["document_id"]

    # Check status
    status_res = client.get(f"/api/v1/documents/{doc_id}/status", headers=headers)
    assert status_res.status_code == 200

    # Get review data
    review_res = client.get(f"/api/v1/documents/{doc_id}/review", headers=headers)
    assert review_res.status_code == 200

    # Confirm & index edited text
    confirm_res = client.put(
        f"/api/v1/documents/{doc_id}/confirm",
        json={"edited_text": "Corrected OCR Text: Section 1: Architecture."},
        headers=headers
    )
    assert confirm_res.status_code == 200
