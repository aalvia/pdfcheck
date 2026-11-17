"""Proveedor de extracción intercambiable.

MOCK no es un modelo: lee etiquetas del texto y marca la salida como simulada.
OLLAMA pide JSON a un modelo local. Si no responde, se aborta la extracción;
no hay un ejemplo fijo escondido detrás.
"""

import json
import logging
import re
from decimal import Decimal

import requests

from app.config import Settings
from app.errors import AIExtractionError
from app.schemas.extraction import ExtractedInvoice, build_extracted

logger = logging.getLogger(__name__)

MOCK_MODEL_NAME = "regex-etiquetas"
OLLAMA_ATTEMPTS = 2

SYSTEM_PROMPT = """Eres un extractor de datos de facturas para la empresa Diosmar.
Devuelve únicamente un objeto JSON con estas claves:
supplier, ruc, invoice_number, date, subtotal, tax, total.
Reglas:
- Usa solo datos que aparezcan de forma explícita en el texto.
- Si un dato no está, escribe null.
- No calcules totales ni completes campos por contexto.
- No inventes proveedor, RUC, fechas ni importes.
- date debe ser YYYY-MM-DD si el texto trae una fecha reconocible; si no, null.
- subtotal, tax y total son números, sin símbolos de moneda.
- No agregues explicaciones ni Markdown.
"""

SUPPLIER_RE = re.compile(
    r"(?im)^(?:proveedor|raz[oó]n\s+social|supplier)\s*:\s*(.+?)\s*$"
)
RUC_RE = re.compile(r"(?im)^ruc\s*:\s*(\S+)\s*$")
NUMBER_RE = re.compile(
    r"(?im)^(?:n[uú]mero(?:\s+de\s+factura)?|invoice(?:\s+number)?|no\.?)\s*:\s*(\S+)\s*$"
)
DATE_RE = re.compile(r"(?im)^fecha\s*:\s*(\S+)\s*$")
SUBTOTAL_RE = re.compile(
    r"(?im)^subtotal\s*:\s*(?:usd\s*|\$\s*)?([0-9]{1,10}(?:[.,][0-9]{1,2})?)\s*$"
)
TAX_RE = re.compile(
    r"(?im)^(?:impuestos?|iva|tax)\s*:\s*(?:usd\s*|\$\s*)?([0-9]{1,10}(?:[.,][0-9]{1,2})?)\s*$"
)
TOTAL_RE = re.compile(
    r"(?im)^total\s*:\s*(?:usd\s*|\$\s*)?([0-9]{1,10}(?:[.,][0-9]{1,2})?)\s*$"
)


def _labeled(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


class MockAIProvider:
    """Extractor por etiquetas. Sirve para demostrar el flujo sin consumir RAM de un modelo."""

    def extract(self, text: str) -> ExtractedInvoice:
        data = {
            "supplier": _labeled(SUPPLIER_RE, text),
            "ruc": _labeled(RUC_RE, text),
            "invoice_number": _labeled(NUMBER_RE, text),
            "date": _labeled(DATE_RE, text),
            "subtotal": _labeled(SUBTOTAL_RE, text),
            "tax": _labeled(TAX_RE, text),
            "total": _labeled(TOTAL_RE, text),
        }
        logger.info("Extracción MOCK por etiquetas. No es un modelo de IA.")
        return build_extracted(
            data,
            mode="mock",
            simulated=True,
            model_name=MOCK_MODEL_NAME,
        )


class OllamaAIProvider:
    def __init__(self, settings: Settings):
        self.settings = settings

    def extract(self, text: str) -> ExtractedInvoice:
        content = self._complete(text[:15_000])
        try:
            payload = extract_json_object(content)
        except (ValueError, json.JSONDecodeError) as exc:
            fragment = " ".join(content.split())[:180]
            raise AIExtractionError(
                "Ollama no devolvió JSON utilizable. No se inventaron datos. "
                f"Fragmento: {fragment}"
            ) from exc
        return build_extracted(
            payload,
            mode="ollama",
            simulated=False,
            model_name=self.settings.ollama_model,
        )

    def _complete(self, text: str) -> str:
        url = self.settings.ollama_base_url.rstrip("/") + "/api/chat"
        payload = {
            "model": self.settings.ollama_model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "options": {"temperature": 0},
        }
        last_error: Exception | None = None
        for attempt in range(1, OLLAMA_ATTEMPTS + 1):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    timeout=self.settings.ollama_timeout_seconds,
                )
                response.raise_for_status()
                body = response.json()
                content = body.get("message", {}).get("content", "")
                if not isinstance(content, str) or not content.strip():
                    raise AIExtractionError("Ollama respondió sin contenido utilizable.")
                return content
            except AIExtractionError:
                raise
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                logger.warning("Intento %s de Ollama falló: %s", attempt, exc)
        raise AIExtractionError(
            "No se pudo usar Ollama en "
            f"{self.settings.ollama_base_url}. El documento no se interpreta con datos inventados. "
            f"Detalle: {last_error}"
        )


def extract_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, count=1, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise ValueError("La respuesta no contiene un objeto JSON.")
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("La respuesta JSON no es un objeto.")
    return data


def get_ai_provider(settings: Settings) -> MockAIProvider | OllamaAIProvider:
    if settings.ai_mode == "ollama":
        return OllamaAIProvider(settings)
    return MockAIProvider()


def _labels_are_complete(extracted: ExtractedInvoice) -> bool:
    return all(
        (
            extracted.supplier,
            extracted.ruc,
            extracted.invoice_number,
            extracted.invoice_date,
            extracted.subtotal is not None,
            extracted.tax is not None,
            extracted.total is not None,
        )
    )


def extract_invoice(settings: Settings, text: str) -> ExtractedInvoice:
    """Elige cómo interpretar el texto.

    mock usa solo etiquetas. ollama usa solo el modelo. auto prueba las
    etiquetas y llama a Ollama únicamente cuando falta algún dato.
    """
    if settings.ai_mode == "ollama":
        return ground_to_source(text, OllamaAIProvider(settings).extract(text))

    labeled = ground_to_source(text, MockAIProvider().extract(text))
    if settings.ai_mode == "mock" or _labels_are_complete(labeled):
        return labeled

    logger.info("Las etiquetas no completaron la factura. Se consulta Ollama.")
    try:
        return ground_to_source(text, OllamaAIProvider(settings).extract(text))
    except AIExtractionError as exc:
        labeled.warnings.append(
            "Las etiquetas no completaron la factura y Ollama no respondió: " + str(exc)
        )
        return labeled


def _amount_in_text(text: str, value: Decimal) -> bool:
    quantized = value.quantize(Decimal("0.01"))
    candidates = {format(quantized, "f")}
    if quantized == quantized.to_integral():
        candidates.add(str(int(quantized)))
    for candidate in list(candidates):
        if "." in candidate:
            candidates.add(candidate.replace(".", ","))
    for candidate in candidates:
        if re.search(rf"(?<!\d){re.escape(candidate)}(?!\d)", text):
            return True
    return False


def _date_in_text(text: str, extracted: ExtractedInvoice) -> bool:
    found = []
    if extracted.date_raw:
        found.append(extracted.date_raw)
    if extracted.invoice_date is not None:
        found.append(extracted.invoice_date.isoformat())
        found.append(extracted.invoice_date.strftime("%d/%m/%Y"))
    return any(candidate and candidate in text for candidate in found)


def ground_to_source(text: str, extracted: ExtractedInvoice) -> ExtractedInvoice:
    """Quita datos que el modelo devolvió y que no están escritos en el PDF."""
    if extracted.supplier and extracted.supplier.lower() not in text.lower():
        extracted.warnings.append("El proveedor no aparece en el documento y se descartó.")
        extracted.supplier = None
    if extracted.ruc and extracted.ruc not in text:
        extracted.warnings.append("El RUC no aparece en el documento y se descartó.")
        extracted.ruc = None
    if extracted.invoice_number and extracted.invoice_number not in text:
        extracted.warnings.append("El número de factura no aparece en el documento y se descartó.")
        extracted.invoice_number = None
    if extracted.date_raw and not _date_in_text(text, extracted):
        extracted.warnings.append("La fecha no aparece en el documento y se descartó.")
        extracted.invoice_date = None
        extracted.date_raw = None
    for attr, label in (("subtotal", "subtotal"), ("tax", "impuesto"), ("total", "total")):
        value = getattr(extracted, attr)
        if value is not None and not _amount_in_text(text, value):
            extracted.warnings.append(f"El {label} no aparece en el documento y se descartó.")
            setattr(extracted, attr, None)
    return extracted
