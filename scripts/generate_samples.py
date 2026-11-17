"""Genera PDFs de ejemplo para probar el flujo en Swagger."""

from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "samples"

VALID = """FACTURA
Proveedor: Comercial ABC
RUC: 0991234567001
Numero: 001-001-000012345
Fecha: 2026-11-13
Subtotal: 100.00
Impuestos: 15.00
Total: 115.00
"""

MISMATCH = VALID.replace("Numero: 001-001-000012345", "Numero: 001-001-000012346").replace(
    "Total: 115.00", "Total: 999.00"
)
INCOMPLETE = "\n".join(
    line.replace("Numero: 001-001-000012345", "Numero: 001-001-000012347")
    for line in VALID.splitlines()
    if not line.startswith("Proveedor:")
)
UNLABELED = "Comercial ABC nos debe 115 dolares. RUC 0991234567001. Total 115."

# Frases completas, sin lineas "Campo: valor". El lector de etiquetas no las completa
# y el modo auto envia el texto a Ollama. Los datos si estan escritos en el PDF.
OLLAMA_1 = """Nota de compra
El proveedor es Distribuidora El Sol.
El RUC es 1791234567001.
El numero de factura es 001-001-000045678.
La fecha es 2026-11-10.
El subtotal es 200.00.
El impuesto es 30.00.
El total es 230.00.
"""

OLLAMA_2 = """Cuenta recibida
Esta cuenta la emite Alimentos del Pacifico.
Su RUC es 0998765432001.
El comprobante es 002-002-000078901.
La emision fue el 14/11/2026.
La base es 80.50.
El IVA cobrado es 12.08.
El valor final es 92.58.
"""

OLLAMA_3 = """Pedido de panaderia
Panaderia La Espiga atendio este pedido.
El registro tributario es 0912345678001.
La factura corresponde al 003-001-000011111.
Se entrego el 2026-11-01.
Antes de impuestos el monto es 50.00.
El impuesto sumado es 7.50.
Hay que pagar 57.50.
"""

OLLAMA_4 = """Compra de ferreteria
El proveedor es Ferreteria El Martillo.
El RUC es 1891112223001.
El numero de factura es 004-001-000022222.
La fecha es 2026-10-20.
El subtotal es 40.00.
El impuesto es 6.00.
El total es 46.00.
"""

OLLAMA_5 = """Venta de telas
Esta venta la hace Textiles Andinos.
Su RUC es 1095556667001.
El comprobante es 005-003-000033333.
La emision fue el 02/11/2026.
La base es 150.25.
El IVA cobrado es 22.54.
El valor final es 172.79.
"""

OLLAMA_6 = """Servicio medico
Clinica Santa Rosa presto este servicio.
El registro tributario es 0991112223001.
La factura corresponde al 006-001-000044444.
Se atendio el 2026-09-15.
Antes de impuestos el monto es 300.00.
El impuesto sumado es 45.00.
Hay que pagar 345.00.
"""


def write_pdf(path: Path, text: str) -> None:
    document = pymupdf.open()
    try:
        page = document.new_page()
        y = 780
        for line in text.splitlines():
            if line:
                page.insert_text((72, y), line, fontsize=12, fontname="helv")
            y -= 16
        document.save(path)
    finally:
        document.close()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write_pdf(OUT / "factura_valida.pdf", VALID)
    write_pdf(OUT / "factura_vacia.pdf", "")
    write_pdf(OUT / "factura_total_incorrecto.pdf", MISMATCH)
    write_pdf(OUT / "factura_incompleta.pdf", INCOMPLETE)
    write_pdf(OUT / "factura_sin_etiquetas.pdf", UNLABELED)
    write_pdf(OUT / "ollama 1.pdf", OLLAMA_1)
    write_pdf(OUT / "ollama 2.pdf", OLLAMA_2)
    write_pdf(OUT / "ollama 3.pdf", OLLAMA_3)
    write_pdf(OUT / "ollama 4.pdf", OLLAMA_4)
    write_pdf(OUT / "ollama 5.pdf", OLLAMA_5)
    write_pdf(OUT / "ollama 6.pdf", OLLAMA_6)
    print(f"PDFs de ejemplo en {OUT}")


if __name__ == "__main__":
    main()
