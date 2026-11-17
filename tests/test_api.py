from app.services.integration_service import IntegrationResult, send_to_admin
from tests.conftest import upload
from tests.helpers import VALID_INVOICE, write_pdf


def test_health_reports_mock_and_database(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["ai_mode"] == "mock"
    assert body["external_system_mode"] == "mock"
    assert body["notification_mode"] == "simulated"
    assert body["database"] == "ok"


def test_openapi_lists_the_flow(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/health" in paths
    assert "/api/documents/upload" in paths
    assert "/api/documents/{invoice_id}" in paths
    assert "/api/documents/{invoice_id}/notify" in paths
    assert "/api/mock/admin/invoices" in paths
    listed = [path for path in paths if path.rstrip("/") == "/api/documents"]
    assert listed


def test_valid_pdf_is_stored_and_marked_as_simulated(client, tmp_path):
    response = upload(client, write_pdf(tmp_path / "factura_valida.pdf", VALID_INVOICE))
    assert response.status_code == 201
    body = response.json()
    assert body["code"] == "processed"
    assert body["created"] is True
    assert body["simulated_extraction"] is True
    assert body["extraction_mode"] == "mock"
    assert body["notification_simulated"] is True
    assert "correo real" in body["message"]
    assert "mock" in body["message"].lower()
    invoice = body["invoice"]
    assert invoice["supplier"] == "Comercial ABC"
    assert invoice["ruc"] == "0991234567001"
    assert invoice["invoice_number"] == "001-001-000012345"
    assert invoice["date"] == "2026-11-13"
    assert invoice["subtotal"] == 100
    assert invoice["tax"] == 15
    assert invoice["total"] == 115
    assert invoice["status"] == "processed"
    assert invoice["validation_errors"] == []
    assert invoice["ai_model"] == "regex-etiquetas"
    assert invoice["integration_status"] == "sent_mock"
    assert invoice["integration_reference"].startswith("MOCK-")
    assert invoice["notification_status"] == "simulated"
    assert invoice["notification_message"].startswith("[SIMULADO]")
    assert "Proveedor: Comercial ABC" in invoice["raw_text"]


def test_list_hides_raw_text_and_detail_keeps_it(client, tmp_path):
    created = upload(client, write_pdf(tmp_path / "factura_valida.pdf", VALID_INVOICE)).json()
    invoice_id = created["invoice"]["id"]
    listed = client.get("/api/documents")
    assert listed.status_code == 200
    assert "raw_text" not in listed.json()[0]
    detail = client.get(f"/api/documents/{invoice_id}")
    assert detail.status_code == 200
    assert "Comercial ABC" in detail.json()["raw_text"]
    filtered = client.get("/api/documents?status=processed")
    assert [item["id"] for item in filtered.json()] == [invoice_id]
    assert client.get("/api/documents?status=no-existe").status_code == 400


def test_empty_pdf_requires_ocr_and_invents_nothing(client, tmp_path):
    response = upload(client, write_pdf(tmp_path / "vacio.pdf", ""))
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "requires_ocr"
    assert body["simulated_extraction"] is False
    assert body["invoice"]["supplier"] is None
    assert body["invoice"]["total"] is None
    assert body["invoice"]["integration_status"] == "skipped"
    assert "OCR" in body["message"]


def test_duplicate_is_not_inserted(client, tmp_path):
    first = upload(client, write_pdf(tmp_path / "a.pdf", VALID_INVOICE))
    second = upload(client, write_pdf(tmp_path / "b.pdf", VALID_INVOICE))
    assert second.status_code == 409
    assert second.json()["code"] == "duplicate"
    assert second.json()["created"] is False
    assert second.json()["invoice"]["id"] == first.json()["invoice"]["id"]
    assert len(client.get("/api/documents").json()) == 1


def test_total_mismatch_stays_out_of_the_admin_system(client, tmp_path):
    text = VALID_INVOICE.replace("Total: 115.00", "Total: 999.00")
    response = upload(client, write_pdf(tmp_path / "mala.pdf", text))
    assert response.status_code == 202
    body = response.json()
    assert body["code"] == "needs_review"
    assert body["invoice"]["integration_status"] == "skipped"
    assert any("no coincide" in error for error in body["invoice"]["validation_errors"])


def test_missing_supplier_is_saved_for_review(client, tmp_path):
    text = "\n".join(line for line in VALID_INVOICE.splitlines() if not line.startswith("Proveedor:"))
    response = upload(client, write_pdf(tmp_path / "incompleta.pdf", text))
    assert response.status_code == 202
    errors = " ".join(response.json()["invoice"]["validation_errors"])
    assert "proveedor" in errors.lower()


def test_external_failure_keeps_the_invoice(client, monkeypatch, tmp_path):
    def fail(invoice, settings):
        return IntegrationResult(ok=False, mock=False, reference=None, error="timeout simulado")

    monkeypatch.setattr("app.services.document_service.send_to_admin", fail)
    response = upload(client, write_pdf(tmp_path / "factura_valida.pdf", VALID_INVOICE))
    assert response.status_code == 201
    invoice = response.json()["invoice"]
    assert invoice["status"] == "processed"
    assert invoice["integration_status"] == "failed"
    assert invoice["integration_error"] == "timeout simulado"
    assert "no se perdió" in response.json()["message"].lower() or "no se perdio" in response.json()["message"].lower()
    listed = client.get("/api/documents").json()
    assert listed[0]["id"] == invoice["id"]


def test_notification_endpoint_is_explicitly_simulated(client, tmp_path):
    created = upload(client, write_pdf(tmp_path / "factura_valida.pdf", VALID_INVOICE)).json()
    response = client.post(f"/api/documents/{created['invoice']['id']}/notify")
    assert response.status_code == 200
    body = response.json()
    assert body["notification_simulated"] is True
    assert body["message"].startswith("[SIMULADO]")
    assert "correo real" in body["message"]
    assert client.post("/api/documents/9999/notify").status_code == 404
    assert client.get("/api/documents/9999").json()["code"] == "not_found"


def test_rejects_non_pdf_and_keeps_sql_looking_text_as_data(client, tmp_path):
    rejected = client.post(
        "/api/documents/upload",
        files={"file": ("nota.txt", b"hola", "text/plain")},
    )
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "invalid_file"

    hostile = VALID_INVOICE.replace(
        "Proveedor: Comercial ABC",
        "Proveedor: Robert'); DROP TABLE invoices;--",
    )
    response = upload(client, write_pdf(tmp_path / "hostil.pdf", hostile))
    assert response.status_code == 201
    assert response.json()["invoice"]["supplier"] == "Robert'); DROP TABLE invoices;--"
    assert client.get("/api/documents").status_code == 200


def test_mock_admin_contract(client):
    response = client.post(
        "/api/mock/admin/invoices",
        json={
            "supplier": "Comercial ABC",
            "ruc": "0991234567001",
            "invoice_number": "001-001-000012345",
            "date": "2026-11-13",
            "subtotal": 100,
            "tax": 15,
            "total": 115,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mock"] is True
    assert body["accepted"] is True
    assert body["reference"] == "MOCK-001-001-000012345"
    assert "no es el sistema real" in body["message"].lower()
