"""Tabla de facturas.

La unicidad es RUC + número de factura. En SQLite, varias filas con RUC nulo
no chocan entre sí: así se pueden guardar PDFs sin datos (OCR o IA caída)
sin romper el control de duplicados.
"""

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

REQUIRES_OCR = "requires_ocr"
AI_UNAVAILABLE = "ai_unavailable"
NEEDS_REVIEW = "needs_review"
PROCESSED = "processed"

INVOICE_STATUSES = (REQUIRES_OCR, AI_UNAVAILABLE, NEEDS_REVIEW, PROCESSED)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("ruc", "invoice_number", name="uq_invoice_ruc_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier: Mapped[str | None] = mapped_column(String(200))
    ruc: Mapped[str | None] = mapped_column(String(32), index=True)
    invoice_number: Mapped[str | None] = mapped_column(String(40), index=True)
    invoice_date: Mapped[date | None] = mapped_column(Date)
    subtotal_cents: Mapped[int | None] = mapped_column(Integer)
    tax_cents: Mapped[int | None] = mapped_column(Integer)
    total_cents: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    validation_errors: Mapped[str] = mapped_column(Text, default="[]")
    extraction_mode: Mapped[str | None] = mapped_column(String(16))
    simulated_extraction: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_model: Mapped[str | None] = mapped_column(String(80))
    raw_text: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(String(200))
    stored_filename: Mapped[str] = mapped_column(String(80))
    integration_status: Mapped[str] = mapped_column(String(32), default="skipped")
    integration_reference: Mapped[str | None] = mapped_column(String(128))
    integration_error: Mapped[str | None] = mapped_column(Text)
    notification_status: Mapped[str] = mapped_column(String(32), default="pending")
    notification_simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    notification_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
