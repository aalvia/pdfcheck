"""Aviso al área administrativa.

Siempre queda marcado como simulado. Este MVP no abre una conexión SMTP
ni afirma que salió un correo.
"""

import logging

from app.models.invoice import Invoice
from app.money import cents_to_float

logger = logging.getLogger(__name__)


def build_notification(invoice: Invoice) -> str:
    if invoice.invoice_number:
        head = f"Factura {invoice.invoice_number}"
    else:
        head = "Documento sin número de factura"
    if invoice.supplier:
        head += f" de {invoice.supplier}"
    else:
        head += ", proveedor no identificado"
    total = cents_to_float(invoice.total_cents)
    if total is not None:
        head += f", por {total:.2f}"
    else:
        head += ", sin total"
    message = (
        f"[SIMULADO] {head}. "
        f"Estado: {invoice.status}. Integración: {invoice.integration_status}."
    )
    if invoice.integration_error:
        message += f" Detalle: {invoice.integration_error}"
    if invoice.status == "needs_review":
        message += " Quedó para revisión humana y no se envió al sistema administrativo."
    elif invoice.status == "requires_ocr":
        message += " No hay texto seleccionable; no se inventaron datos."
    elif invoice.status == "ai_unavailable":
        message += " La extracción no estuvo disponible; no se inventaron datos."
    elif invoice.integration_status == "failed":
        message += " La factura está guardada aunque el sistema externo falló."
    message += " No se envió un correo real."
    return message


def record_notification(invoice: Invoice) -> str:
    message = build_notification(invoice)
    invoice.notification_status = "simulated"
    invoice.notification_simulated = True
    invoice.notification_message = message
    logger.info(message)
    return message
