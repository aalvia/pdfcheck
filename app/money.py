"""Importes en centavos.

Los montos no se guardan como float. Un entero de centavos evita errores de
redondeo y hace exacta la tolerancia de 0.02 (2 centavos) de la guía.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

TOTAL_TOLERANCE_CENTS = 2
_MONEY = Decimal("0.01")


def parse_amount(value: str) -> Decimal:
    cleaned = value.strip().replace(" ", "").replace("$", "")
    cleaned = re.sub(r"(?i)usd", "", cleaned)
    if not cleaned or not re.fullmatch(r"[0-9.,]+", cleaned):
        raise ValueError("importe inválido")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("importe inválido") from exc
    return amount.quantize(_MONEY, rounding=ROUND_HALF_UP)


def to_cents(value: Decimal) -> int:
    quantized = value.quantize(_MONEY, rounding=ROUND_HALF_UP)
    return int((quantized * 100).to_integral_value(rounding=ROUND_HALF_UP))


def cents_to_float(cents: int | None) -> float | None:
    if cents is None:
        return None
    return float(Decimal(cents) / Decimal(100))
