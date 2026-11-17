import json
from decimal import Decimal

import pytest
import requests

from app.config import Settings
from app.schemas.extraction import build_extracted
from app.errors import AIExtractionError
from app.services.ai_service import (
    MOCK_MODEL_NAME,
    MockAIProvider,
    OllamaAIProvider,
    extract_invoice,
    extract_json_object,
    ground_to_source,
)
from app.services.pdf_service import ensure_valid_pdf
from tests.helpers import VALID_INVOICE


def test_mock_reads_labeled_invoice():
    extracted = MockAIProvider().extract(VALID_INVOICE)
    assert extracted.simulated is True
    assert extracted.mode == "mock"
    assert extracted.model_name == MOCK_MODEL_NAME
    assert extracted.supplier == "Comercial ABC"
    assert extracted.ruc == "0991234567001"
    assert extracted.invoice_number == "001-001-000012345"
    assert extracted.invoice_date is not None
    assert extracted.invoice_date.isoformat() == "2026-11-13"
    assert extracted.subtotal == Decimal("100.00")
    assert extracted.tax == Decimal("15.00")
    assert extracted.total == Decimal("115.00")


def test_mock_amounts_and_date_formats():
    text = """Proveedor: Comercial ABC
RUC: 0991234567001
Numero: 001-001-000012345
Fecha: 13/11/2026
Subtotal: 100,00
Impuestos: 15,00
Total: 115,00
"""
    extracted = MockAIProvider().extract(text)
    assert extracted.invoice_date is not None
    assert extracted.invoice_date.isoformat() == "2026-11-13"
    assert extracted.subtotal == Decimal("100.00")
    assert extracted.tax == Decimal("15.00")
    assert extracted.total == Decimal("115.00")


def test_mock_does_not_invent_unlabeled_values():
    text = "Comercial ABC nos debe 115 dolares. RUC 0991234567001. Total 115."
    extracted = MockAIProvider().extract(text)
    assert extracted.supplier is None
    assert extracted.ruc is None
    assert extracted.invoice_number is None
    assert extracted.subtotal is None
    assert extracted.total is None
    assert extracted.simulated is True


def test_json_fence_is_accepted():
    data = extract_json_object('```json\n{"supplier": "Comercial ABC"}\n```')
    assert data == {"supplier": "Comercial ABC"}


def test_ollama_sends_a_strict_prompt(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "supplier": "Comercial ABC",
                            "ruc": "0991234567001",
                            "invoice_number": "001-001-000012345",
                            "date": "2026-11-13",
                            "subtotal": 100,
                            "tax": 15,
                            "total": 115,
                        }
                    )
                }
            }

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.services.ai_service.requests.post", fake_post)
    settings = Settings(ai_mode="ollama", ollama_model="qwen2.5:1.5b", ollama_timeout_seconds=12)
    extracted = OllamaAIProvider(settings).extract("Proveedor: Comercial ABC")

    assert captured["url"].endswith("/api/chat")
    assert captured["json"]["format"] == "json"
    assert captured["json"]["options"]["temperature"] == 0
    assert captured["json"]["model"] == "qwen2.5:1.5b"
    assert captured["timeout"] == 12
    assert "No inventes" in captured["json"]["messages"][0]["content"]
    assert extracted.simulated is False
    assert extracted.supplier == "Comercial ABC"
    assert extracted.mode == "ollama"


def test_ollama_failure_does_not_return_fake_data(monkeypatch):
    def boom(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr("app.services.ai_service.requests.post", boom)
    settings = Settings(ai_mode="ollama")
    with pytest.raises(Exception) as caught:
        OllamaAIProvider(settings).extract("Proveedor: Comercial ABC")
    assert "No se pudo usar Ollama" in str(caught.value)


def test_invalid_amount_from_model_becomes_a_warning_not_a_guess():
    extracted = build_extracted(
        {"supplier": "Comercial ABC", "subtotal": "cien", "tax": 15, "total": 15},
        mode="ollama",
        simulated=False,
        model_name="qwen2.5:1.5b",
    )
    assert extracted.subtotal is None
    assert extracted.supplier == "Comercial ABC"
    assert any("subtotal" in warning for warning in extracted.warnings)


def test_invented_date_is_removed_when_the_document_does_not_contain_it():
    text = "Comercial ABC nos debe 115 dolares. RUC 0991234567001. Total 115."
    extracted = build_extracted(
        {
            "supplier": "Comercial ABC",
            "ruc": "0991234567001",
            "date": "2023-04-01",
            "subtotal": 115,
            "tax": 15,
            "total": 115,
        },
        mode="ollama",
        simulated=False,
        model_name="qwen2.5:1.5b",
    )
    ground_to_source(text, extracted)
    assert extracted.supplier == "Comercial ABC"
    assert extracted.ruc == "0991234567001"
    assert extracted.invoice_date is None
    assert extracted.total == Decimal("115.00")
    assert extracted.tax is None
    assert any("fecha" in warning.lower() for warning in extracted.warnings)
    assert any("impuesto" in warning.lower() for warning in extracted.warnings)


def test_labeled_date_stays_when_it_is_written_in_the_document():
    extracted = MockAIProvider().extract(VALID_INVOICE)
    ground_to_source(VALID_INVOICE, extracted)
    assert extracted.invoice_date is not None
    assert extracted.invoice_date.isoformat() == "2026-11-13"
    assert extracted.warnings == []


UNLABELED = """Comercial ABC
RUC 0991234567001
Factura 001-001-000012348
Fecha 2026-11-13
Subtotal 100.00
Impuesto 15.00
Total 115.00
"""


def test_auto_keeps_labels_when_the_invoice_is_complete(monkeypatch):
    def fail(self, text):
        raise AssertionError("Ollama no debía usarse")

    monkeypatch.setattr(OllamaAIProvider, "extract", fail)
    result = extract_invoice(Settings(ai_mode="auto"), VALID_INVOICE)
    assert result.mode == "mock"
    assert result.supplier == "Comercial ABC"
    assert result.invoice_number == "001-001-000012345"


def test_auto_calls_ollama_when_labels_are_missing(monkeypatch):
    def fake(self, text):
        return build_extracted(
            {
                "supplier": "Comercial ABC",
                "ruc": "0991234567001",
                "invoice_number": "001-001-000012348",
                "date": "2026-11-13",
                "subtotal": "100.00",
                "tax": "15.00",
                "total": "115.00",
            },
            mode="ollama",
            simulated=False,
            model_name="qwen2.5:1.5b",
        )

    monkeypatch.setattr(OllamaAIProvider, "extract", fake)
    result = extract_invoice(Settings(ai_mode="auto"), UNLABELED)
    assert result.mode == "ollama"
    assert result.simulated is False
    assert result.invoice_number == "001-001-000012348"
    assert result.warnings == []


def test_auto_keeps_labels_if_ollama_is_down(monkeypatch):
    def down(self, text):
        raise AIExtractionError("No se pudo usar Ollama")

    monkeypatch.setattr(OllamaAIProvider, "extract", down)
    result = extract_invoice(Settings(ai_mode="auto"), UNLABELED)
    assert result.mode == "mock"
    assert any("Ollama no respondió" in warning for warning in result.warnings)


def test_pdf_policy_rejects_extension_magic_and_size():
    with pytest.raises(Exception):
        ensure_valid_pdf("nota.txt", b"%PDF-1.4", 1000)
    with pytest.raises(Exception):
        ensure_valid_pdf("factura.pdf", b"no-es-pdf", 1000)
    with pytest.raises(Exception) as caught:
        ensure_valid_pdf("factura.pdf", b"%PDF" + b"x" * 20, 10)
    assert caught.value.code == "file_too_large"
    assert ensure_valid_pdf("factura.pdf", b"%PDF-1.4", 100) == "factura.pdf"
