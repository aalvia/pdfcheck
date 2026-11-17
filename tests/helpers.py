"""PDFs de prueba en memoria. No forman parte del flujo de producción."""

from pathlib import Path


VALID_INVOICE = """FACTURA
Proveedor: Comercial ABC
RUC: 0991234567001
Numero: 001-001-000012345
Fecha: 2026-11-13
Subtotal: 100.00
Impuestos: 15.00
Total: 115.00
"""


def write_pdf(path: Path, text: str = "") -> Path:
    import pymupdf

    path.parent.mkdir(parents=True, exist_ok=True)
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
    return path
