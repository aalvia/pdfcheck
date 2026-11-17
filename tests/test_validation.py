from datetime import date
from decimal import Decimal

from app.money import to_cents
from app.schemas.extraction import ExtractedInvoice
from app.services.validation_service import validate_invoice


def invoice(**overrides) -> ExtractedInvoice:
    data = dict(
        supplier="Comercial ABC",
        ruc="0991234567001",
        invoice_number="001-001-000012345",
        invoice_date=date(2026, 11, 13),
        date_raw="2026-11-13",
        subtotal=Decimal("100.00"),
        tax=Decimal("15.00"),
        total=Decimal("115.00"),
        mode="mock",
        simulated=True,
        model_name="regex-etiquetas",
        warnings=[],
    )
    data.update(overrides)
    return ExtractedInvoice(**data)


def test_valid_invoice_has_no_errors():
    assert validate_invoice(invoice()) == []


def test_tolerance_of_two_cents_is_accepted():
    assert to_cents(Decimal("115.02")) - to_cents(Decimal("115.00")) == 2
    assert validate_invoice(invoice(total=Decimal("115.02"))) == []


def test_three_cents_of_difference_go_to_review():
    errors = validate_invoice(invoice(total=Decimal("115.03")))
    assert any("no coincide" in error for error in errors)


def test_missing_ruc_and_bad_ruc_are_different_errors():
    assert any("Falta el RUC" in error for error in validate_invoice(invoice(ruc=None)))
    errors = validate_invoice(invoice(ruc="123"))
    assert any("13 dígitos" in error for error in errors)
    assert not any("Falta el RUC" in error for error in errors)


def test_invalid_date_is_reported_without_guessing():
    errors = validate_invoice(invoice(invoice_date=None, date_raw="ayer"))
    assert any("no es válida" in error for error in errors)


def test_does_not_require_a_fixed_tax_rate():
    errors = validate_invoice(
        invoice(subtotal=Decimal("100.00"), tax=Decimal("12.00"), total=Decimal("112.00"))
    )
    assert errors == []
