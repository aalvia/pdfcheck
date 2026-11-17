"""Envío al sistema administrativo.

En modo mock no hay HTTP: se acepta la factura dentro del mismo proceso.
Una llamada HTTP al propio servidor, con un solo worker, se quedaría
esperándose a sí misma. El modo http sí usa requests, con timeout, y sirve
cuando la URL apunta a otro proceso.
"""

import logging
from dataclasses import dataclass

import requests
from pydantic import ValidationError

from app.config import Settings
from app.models.invoice import Invoice
from app.money import cents_to_float
from app.schemas.invoice import AdminInvoiceIn, AdminInvoiceOut

logger = logging.getLogger(__name__)


@dataclass
class IntegrationResult:
    ok: bool
    mock: bool
    reference: str | None
    error: str | None


def accept_admin_invoice(payload: AdminInvoiceIn) -> AdminInvoiceOut:
    reference = f"MOCK-{payload.invoice_number}"
    logger.info("Sistema administrativo MOCK aceptó %s. No es el sistema real.", reference)
    return AdminInvoiceOut(accepted=True, mock=True, reference=reference)


def _payload(invoice: Invoice) -> AdminInvoiceIn:
    subtotal = cents_to_float(invoice.subtotal_cents)
    tax = cents_to_float(invoice.tax_cents)
    total = cents_to_float(invoice.total_cents)
    if (
        invoice.invoice_date is None
        or subtotal is None
        or tax is None
        or total is None
        or not invoice.supplier
        or not invoice.ruc
        or not invoice.invoice_number
    ):
        raise ValueError("La factura no tiene los datos que exige el sistema administrativo.")
    return AdminInvoiceIn(
        supplier=invoice.supplier,
        ruc=invoice.ruc,
        invoice_number=invoice.invoice_number,
        date=invoice.invoice_date.isoformat(),
        subtotal=subtotal,
        tax=tax,
        total=total,
    )


def send_to_admin(invoice: Invoice, settings: Settings) -> IntegrationResult:
    try:
        payload = _payload(invoice)
    except (ValidationError, ValueError) as exc:
        logger.error("Payload administrativo inválido: %s", exc)
        return IntegrationResult(
            ok=False,
            mock=False,
            reference=None,
            error="No se armó un payload válido para el sistema administrativo.",
        )

    if settings.external_system_mode == "mock":
        accepted = accept_admin_invoice(payload)
        return IntegrationResult(True, True, accepted.reference, None)

    if not settings.external_system_url:
        return IntegrationResult(False, False, None, "Falta EXTERNAL_SYSTEM_URL.")

    try:
        response = requests.post(
            settings.external_system_url,
            json=payload.model_dump(mode="json"),
            timeout=settings.http_timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("El sistema administrativo no respondió: %s", exc)
        return IntegrationResult(False, False, None, str(exc))

    body: dict = {}
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            body = parsed
    except ValueError:
        body = {}
    reference = body.get("reference")
    return IntegrationResult(
        ok=True,
        mock=bool(body.get("mock")),
        reference=None if reference is None else str(reference),
        error=None,
    )
