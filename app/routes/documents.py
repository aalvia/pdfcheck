"""Rutas de facturas. Aquí no vive la regla de negocio: solo HTTP."""

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import Settings
from app.deps import get_db, get_settings
from app.errors import ApiError, UploadRejected
from app.models.invoice import INVOICE_STATUSES
from app.schemas.invoice import (
    InvoiceDetail,
    InvoiceSummary,
    NotificationResponse,
    ProcessResponse,
    invoice_detail,
    invoice_summary,
)
from app.services.document_service import (
    ProcessResult,
    get_invoice,
    list_invoices,
    notify_invoice,
    process_pdf,
)

router = APIRouter()


async def _read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        if total + len(chunk) > max_bytes:
            megabytes = max_bytes // (1024 * 1024)
            raise UploadRejected(
                f"El archivo supera el máximo de {megabytes} MB.",
                "file_too_large",
            )
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _to_response(result: ProcessResult) -> ProcessResponse:
    detail = invoice_detail(result.invoice)
    return ProcessResponse(
        code=result.code,
        message=result.message,
        created=result.created,
        simulated_extraction=detail.simulated_extraction,
        extraction_mode=detail.extraction_mode,
        notification_simulated=detail.notification_simulated,
        invoice=detail,
    )


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(..., description="Factura en PDF"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Recibe un PDF y recorre extracción, validación, guardado, integración y aviso.

    Códigos: 201 válida, 202 revisión humana, 409 duplicada, 422 requiere OCR,
    503 el proveedor de IA no respondió, 400 el archivo no es un PDF usable.
    La notificación de este flujo es simulada.
    """
    content = await _read_limited(file, settings.max_upload_bytes)
    result = process_pdf(db, settings, filename=file.filename, content=content)
    payload = _to_response(result)
    return JSONResponse(status_code=result.http_status, content=payload.model_dump(mode="json"))


@router.get("", response_model=list[InvoiceSummary])
def list_documents(
    status: str | None = Query(default=None, description="requires_ocr, ai_unavailable, needs_review o processed"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Lista facturas guardadas. No incluye el texto completo del PDF."""
    if status is not None and status not in INVOICE_STATUSES:
        allowed = ", ".join(INVOICE_STATUSES)
        raise ApiError(400, "invalid_status", f"Estado no reconocido. Use uno de: {allowed}.")
    return [invoice_summary(invoice) for invoice in list_invoices(db, status=status, offset=offset, limit=limit)]


@router.get("/{invoice_id}", response_model=InvoiceDetail)
def get_document(invoice_id: int, db: Session = Depends(get_db)):
    """Devuelve una factura, incluido el texto extraído para auditoría."""
    invoice = get_invoice(db, invoice_id)
    if invoice is None:
        raise ApiError(404, "not_found", "Factura no encontrada.")
    return invoice_detail(invoice)


@router.post("/{invoice_id}/notify", response_model=NotificationResponse)
def notify_document(invoice_id: int, db: Session = Depends(get_db)):
    """Regenera el aviso del área administrativa. Sigue siendo simulado."""
    invoice = get_invoice(db, invoice_id)
    if invoice is None:
        raise ApiError(404, "not_found", "Factura no encontrada.")
    message = notify_invoice(db, invoice)
    return NotificationResponse(
        id=invoice.id,
        notification_status=invoice.notification_status,
        notification_simulated=True,
        message=message,
    )
