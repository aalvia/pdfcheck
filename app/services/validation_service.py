"""Reglas de negocio posteriores al esquema.

Pydantic ya convirtió tipos. Aquí se decide si la factura puede salir de la
empresa o si un humano debe revisarla. No se asume una tarifa de IVA fija:
solo que subtotal + impuesto cuadre con el total, con 0.02 de tolerancia.
"""

import re

from app.money import TOTAL_TOLERANCE_CENTS, to_cents
from app.schemas.extraction import ExtractedInvoice

RUC_RE = re.compile(r"^\d{13}$")
INVOICE_NUMBER_RE = re.compile(r"^\d{3}-\d{3}-\d{9}$")


def validate_invoice(extracted: ExtractedInvoice) -> list[str]:
    errors = list(extracted.warnings)

    if not extracted.supplier:
        errors.append("Falta el proveedor.")
    elif len(extracted.supplier) < 2:
        errors.append("El proveedor es demasiado corto.")

    if not extracted.ruc:
        errors.append("Falta el RUC.")
    elif not RUC_RE.fullmatch(extracted.ruc):
        errors.append("El RUC debe tener 13 dígitos.")

    if not extracted.invoice_number:
        errors.append("Falta el número de factura.")
    elif not INVOICE_NUMBER_RE.fullmatch(extracted.invoice_number):
        errors.append("El número de factura debe tener el formato 001-001-000000001.")

    if extracted.date_raw is None:
        errors.append("Falta la fecha.")
    elif extracted.invoice_date is None:
        errors.append(f"La fecha no es válida: {extracted.date_raw}.")

    amounts = (
        (extracted.subtotal, "Falta el subtotal.", "El subtotal no puede ser negativo."),
        (extracted.tax, "Falta el impuesto.", "El impuesto no puede ser negativo."),
        (extracted.total, "Falta el total.", "El total no puede ser negativo."),
    )
    present = True
    for value, missing, negative in amounts:
        if value is None:
            errors.append(missing)
            present = False
        elif value < 0:
            errors.append(negative)
            present = False

    if present:
        difference = abs(
            to_cents(extracted.subtotal) + to_cents(extracted.tax) - to_cents(extracted.total)
        )
        if difference > TOTAL_TOLERANCE_CENTS:
            errors.append("El total no coincide con subtotal + impuesto (tolerancia 0.02).")

    return errors
