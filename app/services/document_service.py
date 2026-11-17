"""Orquesta el flujo de una factura.

1. Guardar el PDF con un nombre interno, nunca la ruta que envió el cliente.
2. Extraer texto. Si no hay, marcar requires_ocr y no inventar datos.
3. Leer etiquetas. En modo auto, si falta algún dato, consultar Ollama.
4. Validar. Si falla, needs_review y no sale hacia el sistema externo.
5. Rechazar duplicados por RUC + número de factura.
6. Confirmar en SQLite antes de integrar, para no perder la factura.
7. Integrar. Si el sistema externo falla, el registro se conserva.
8. Dejar una notificación simulada. No es un correo real.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AIExtractionError
from app.models.invoice import (
    AI_UNAVAILABLE,
    NEEDS_REVIEW,
    PROCESSED,
    REQUIRES_OCR,
    Invoice,
)
from app.money import to_cents
from app.services.ai_service import extract_invoice
from app.services.integration_service import send_to_admin
from app.services.notification_service import record_notification
from app.services.pdf_service import clip_text, ensure_valid_pdf, extract_text
from app.services.validation_service import validate_invoice

logger = logging.getLogger(__name__)

DUPLICATE_MESSAGE = "Ya existe una factura con ese RUC y número. No se insertó de nuevo."


@dataclass
class ProcessResult:
    invoice: Invoice
    http_status: int
    code: str
    message: str
    created: bool


def process_pdf(
    db: Session,
    settings: Settings,
    filename: str | None,
    content: bytes,
) -> ProcessResult:
    original_name = ensure_valid_pdf(filename, content, settings.max_upload_bytes)
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}.pdf"
    path = upload_dir / stored_name
    path.write_bytes(content)
    try:
        return _process_stored_pdf(db, settings, original_name, stored_name, path)
    except Exception:
        db.rollback()
        _delete_if_unreferenced(db, path, stored_name)
        raise


def get_invoice(db: Session, invoice_id: int) -> Invoice | None:
    return db.get(Invoice, invoice_id)


def list_invoices(
    db: Session,
    *,
    status: str | None,
    offset: int,
    limit: int,
) -> list[Invoice]:
    stmt = select(Invoice)
    if status is not None:
        stmt = stmt.where(Invoice.status == status)
    stmt = stmt.order_by(Invoice.created_at.desc(), Invoice.id.desc()).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


def notify_invoice(db: Session, invoice: Invoice) -> str:
    message = record_notification(invoice)
    db.commit()
    db.refresh(invoice)
    return message


def _process_stored_pdf(
    db: Session,
    settings: Settings,
    original_name: str,
    stored_name: str,
    path: Path,
) -> ProcessResult:
    text = extract_text(path)
    if not text.strip():
        invoice = _save_invoice(
            db,
            supplier=None,
            ruc=None,
            invoice_number=None,
            invoice_date=None,
            subtotal_cents=None,
            tax_cents=None,
            total_cents=None,
            status=REQUIRES_OCR,
            errors=[],
            extraction_mode=None,
            simulated_extraction=False,
            ai_model=None,
            raw_text=None,
            original_filename=original_name,
            stored_filename=stored_name,
            integration_status="skipped",
            integration_error="No se integró porque el PDF requiere OCR.",
        )
        _finish(db, invoice)
        return ProcessResult(invoice, 422, REQUIRES_OCR, _message_for(invoice), True)

    try:
        extracted = extract_invoice(settings, text)
    except AIExtractionError as exc:
        invoice = _save_invoice(
            db,
            supplier=None,
            ruc=None,
            invoice_number=None,
            invoice_date=None,
            subtotal_cents=None,
            tax_cents=None,
            total_cents=None,
            status=AI_UNAVAILABLE,
            errors=[str(exc)],
            extraction_mode=settings.ai_mode,
            simulated_extraction=False,
            ai_model=settings.ollama_model if settings.ai_mode == "ollama" else None,
            raw_text=clip_text(text),
            original_filename=original_name,
            stored_filename=stored_name,
            integration_status="skipped",
            integration_error="No se integró porque la extracción no estuvo disponible.",
        )
        _finish(db, invoice)
        return ProcessResult(invoice, 503, AI_UNAVAILABLE, _message_for(invoice), True)

    if extracted.ruc and extracted.invoice_number:
        existing = _find_duplicate(db, extracted.ruc, extracted.invoice_number)
        if existing is not None:
            path.unlink(missing_ok=True)
            return ProcessResult(existing, 409, "duplicate", DUPLICATE_MESSAGE, False)

    errors = validate_invoice(extracted)
    status = PROCESSED if not errors else NEEDS_REVIEW
    try:
        invoice = _save_invoice(
            db,
            supplier=extracted.supplier,
            ruc=extracted.ruc,
            invoice_number=extracted.invoice_number,
            invoice_date=extracted.invoice_date,
            subtotal_cents=_cents(extracted.subtotal),
            tax_cents=_cents(extracted.tax),
            total_cents=_cents(extracted.total),
            status=status,
            errors=errors,
            extraction_mode=extracted.mode,
            simulated_extraction=extracted.simulated,
            ai_model=extracted.model_name,
            raw_text=clip_text(text),
            original_filename=original_name,
            stored_filename=stored_name,
            integration_status="pending" if status == PROCESSED else "skipped",
            integration_error=(
                None
                if status == PROCESSED
                else "No se envió al sistema administrativo porque la factura requiere revisión."
            ),
        )
    except IntegrityError:
        db.rollback()
        path.unlink(missing_ok=True)
        existing = None
        if extracted.ruc and extracted.invoice_number:
            existing = _find_duplicate(db, extracted.ruc, extracted.invoice_number)
        if existing is None:
            raise
        return ProcessResult(existing, 409, "duplicate", DUPLICATE_MESSAGE, False)

    # La factura ya está confirmada. Un fallo externo no puede borrarla.
    if status == PROCESSED:
        integration = send_to_admin(invoice, settings)
        if integration.ok and integration.mock:
            invoice.integration_status = "sent_mock"
            invoice.integration_reference = integration.reference
            invoice.integration_error = None
        elif integration.ok:
            invoice.integration_status = "sent"
            invoice.integration_reference = integration.reference
            invoice.integration_error = None
        else:
            invoice.integration_status = "failed"
            invoice.integration_error = integration.error

    _finish(db, invoice)
    http_status = 201 if status == PROCESSED else 202
    return ProcessResult(invoice, http_status, status, _message_for(invoice), True)


def _save_invoice(db: Session, *, errors: list[str], **fields: object) -> Invoice:
    invoice = Invoice(validation_errors=json.dumps(errors, ensure_ascii=False), **fields)
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    logger.info("Factura guardada id=%s estado=%s", invoice.id, invoice.status)
    return invoice


def _finish(db: Session, invoice: Invoice) -> None:
    record_notification(invoice)
    db.commit()
    db.refresh(invoice)


def _find_duplicate(db: Session, ruc: str, invoice_number: str) -> Invoice | None:
    stmt = select(Invoice).where(
        Invoice.ruc == ruc,
        Invoice.invoice_number == invoice_number,
    )
    return db.scalars(stmt).first()


def _cents(value):
    if value is None:
        return None
    return to_cents(value)


def _delete_if_unreferenced(db: Session, path: Path, stored_name: str) -> None:
    try:
        stmt = select(Invoice.id).where(Invoice.stored_filename == stored_name)
        referenced = db.scalars(stmt).first()
    except Exception:
        referenced = None
    if referenced is None and path.exists():
        path.unlink(missing_ok=True)


def _message_for(invoice: Invoice) -> str:
    if invoice.status == REQUIRES_OCR:
        return (
            "El PDF no tiene texto seleccionable. Se guardó el archivo con estado requires_ocr. "
            "No se inventaron datos: hace falta OCR antes de extraer la factura."
        )
    if invoice.status == AI_UNAVAILABLE:
        errors = json.loads(invoice.validation_errors or "[]")
        detail = f" {errors[0]}" if errors else ""
        return (
            "No se pudo interpretar el documento con el proveedor configurado. "
            "No se inventaron datos ni se envió la factura al sistema administrativo."
            + detail
        )
    if invoice.status == NEEDS_REVIEW:
        errors = json.loads(invoice.validation_errors or "[]")
        detail = " ".join(errors)
        return (
            "La factura se guardó para revisión humana y no se envió al sistema administrativo. "
            + detail
        )
    if invoice.integration_status == "failed":
        return (
            "La factura es válida y quedó guardada, pero el sistema administrativo no respondió. "
            "El registro no se perdió. La notificación es simulada: no se envió un correo real."
        )
    if invoice.integration_status == "sent_mock":
        return (
            "La factura es válida y quedó guardada. El sistema administrativo mock aceptó el envío. "
            "La notificación es simulada: no se envió un correo real."
        )
    return (
        "La factura es válida y quedó guardada. "
        "La notificación es simulada: no se envió un correo real."
    )
