"""Contrato interno entre la extracción y la validación.

La salida de la IA se recorta a estos campos. Lo que el modelo agregue se
descarta. Un importe ilegible se vacía y pasa a revisión; no se adivina.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.money import parse_amount

TEXT_FIELDS = ("supplier", "ruc", "invoice_number", "date")
AMOUNT_FIELDS = (
    ("subtotal", "subtotal"),
    ("tax", "impuesto"),
    ("total", "total"),
)


class InvoiceFields(BaseModel):
    model_config = ConfigDict(extra="ignore")

    supplier: str | None = None
    ruc: str | None = None
    invoice_number: str | None = None
    date: str | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None

    @field_validator("supplier", mode="before")
    @classmethod
    def clean_supplier(cls, value: object) -> str | None:
        if value is None:
            return None
        text = " ".join(str(value).split())
        return text or None

    @field_validator("ruc", "invoice_number", "date", mode="before")
    @classmethod
    def clean_token(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class ExtractedInvoice:
    def __init__(
        self,
        *,
        supplier: str | None,
        ruc: str | None,
        invoice_number: str | None,
        invoice_date: date | None,
        date_raw: str | None,
        subtotal: Decimal | None,
        tax: Decimal | None,
        total: Decimal | None,
        mode: str,
        simulated: bool,
        model_name: str | None,
        warnings: list[str],
    ):
        self.supplier = supplier
        self.ruc = ruc
        self.invoice_number = invoice_number
        self.invoice_date = invoice_date
        self.date_raw = date_raw
        self.subtotal = subtotal
        self.tax = tax
        self.total = total
        self.mode = mode
        self.simulated = simulated
        self.model_name = model_name
        self.warnings = warnings


def parse_date(value: str | None) -> tuple[date | None, str | None]:
    if value is None:
        return None, None
    raw = value.strip()[:40]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date(), raw
        except ValueError:
            continue
    return None, raw


def sanitize_payload(data: dict) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    cleaned: dict = {}
    for field in TEXT_FIELDS:
        value = data.get(field)
        if value is None:
            cleaned[field] = None
        elif isinstance(value, str):
            cleaned[field] = value
        else:
            warnings.append(f"El campo {field} no vino como texto y se dejó vacío.")
            cleaned[field] = None
    for field, label in AMOUNT_FIELDS:
        value = data.get(field)
        if value is None or value == "":
            cleaned[field] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
            warnings.append(f"El {label} no es un número válido y se dejó vacío.")
            cleaned[field] = None
            continue
        try:
            if isinstance(value, str):
                cleaned[field] = parse_amount(value)
            else:
                cleaned[field] = Decimal(str(value))
        except (InvalidOperation, ValueError, ArithmeticError):
            warnings.append(f"El {label} no es un número válido y se dejó vacío.")
            cleaned[field] = None
    return cleaned, warnings


def _fit(value: str | None, limit: int) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    if len(value) <= limit:
        return value, False
    return value[:limit], True


def build_extracted(
    data: dict,
    *,
    mode: str,
    simulated: bool,
    model_name: str | None,
) -> ExtractedInvoice:
    cleaned, warnings = sanitize_payload(data)
    try:
        parsed = InvoiceFields.model_validate(cleaned)
    except ValidationError as exc:
        raise ValueError("La extracción no cumple el esquema.") from exc

    supplier, supplier_clipped = _fit(parsed.supplier, 200)
    if supplier_clipped:
        warnings.append("El proveedor venía demasiado largo y se recortó.")
    ruc, _ = _fit(parsed.ruc, 32)
    invoice_number, _ = _fit(parsed.invoice_number, 40)
    invoice_date, date_raw = parse_date(parsed.date)

    return ExtractedInvoice(
        supplier=supplier,
        ruc=ruc,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        date_raw=date_raw,
        subtotal=parsed.subtotal,
        tax=parsed.tax,
        total=parsed.total,
        mode=mode,
        simulated=simulated,
        model_name=model_name,
        warnings=warnings,
    )
