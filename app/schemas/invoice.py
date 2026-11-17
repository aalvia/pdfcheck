"""Contratos HTTP: lo que ve quien llama a la API."""

import json
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.invoice import Invoice
from app.money import cents_to_float


def loads_errors(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [raw]
    if isinstance(data, list):
        return [str(item) for item in data]
    return [str(data)]


class ErrorBody(BaseModel):
    code: str
    message: str


class InvoiceSummary(BaseModel):
    id: int
    supplier: str | None
    ruc: str | None
    invoice_number: str | None
    date: date | None
    subtotal: float | None
    tax: float | None
    total: float | None
    status: str
    validation_errors: list[str]
    extraction_mode: str | None
    simulated_extraction: bool
    ai_model: str | None
    integration_status: str
    integration_reference: str | None
    integration_error: str | None
    notification_status: str
    notification_simulated: bool
    notification_message: str | None
    original_filename: str
    created_at: datetime


class InvoiceDetail(InvoiceSummary):
    raw_text: str | None = None


class ProcessResponse(BaseModel):
    code: str
    message: str
    created: bool
    simulated_extraction: bool
    extraction_mode: str | None
    notification_simulated: bool
    invoice: InvoiceDetail


class NotificationResponse(BaseModel):
    id: int
    notification_status: str
    notification_simulated: bool = True
    message: str


class HealthResponse(BaseModel):
    status: str
    ai_mode: str
    external_system_mode: str
    notification_mode: str
    database: str


class AdminInvoiceIn(BaseModel):
    """Contrato que recibiría el sistema administrativo."""

    supplier: str
    ruc: str
    invoice_number: str
    date: str
    subtotal: float
    tax: float
    total: float
    source: str = "diosmar-automation"


class AdminInvoiceOut(BaseModel):
    accepted: bool
    mock: bool = True
    reference: str
    message: str = Field(
        default="Respuesta simulada. Este endpoint no es el sistema real de Diosmar."
    )


def invoice_summary(invoice: Invoice) -> InvoiceSummary:
    return InvoiceSummary(
        id=invoice.id,
        supplier=invoice.supplier,
        ruc=invoice.ruc,
        invoice_number=invoice.invoice_number,
        date=invoice.invoice_date,
        subtotal=cents_to_float(invoice.subtotal_cents),
        tax=cents_to_float(invoice.tax_cents),
        total=cents_to_float(invoice.total_cents),
        status=invoice.status,
        validation_errors=loads_errors(invoice.validation_errors),
        extraction_mode=invoice.extraction_mode,
        simulated_extraction=invoice.simulated_extraction,
        ai_model=invoice.ai_model,
        integration_status=invoice.integration_status,
        integration_reference=invoice.integration_reference,
        integration_error=invoice.integration_error,
        notification_status=invoice.notification_status,
        notification_simulated=invoice.notification_simulated,
        notification_message=invoice.notification_message,
        original_filename=invoice.original_filename,
        created_at=invoice.created_at,
    )


def invoice_detail(invoice: Invoice) -> InvoiceDetail:
    data = invoice_summary(invoice).model_dump()
    data["raw_text"] = invoice.raw_text
    return InvoiceDetail(**data)
