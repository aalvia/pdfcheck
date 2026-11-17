"""Lectura de PDF con PyMuPDF.

Solo devuelve texto que ya está en el archivo. Un escaneado abre bien y aun
así puede venir vacío: en ese caso no se inventa contenido.
"""

from pathlib import Path

from app.errors import UploadRejected

PDF_MAGIC = b"%PDF"
RAW_TEXT_LIMIT = 20_000


def ensure_valid_pdf(filename: str | None, content: bytes, max_bytes: int) -> str:
    original = Path(filename or "").name
    if not original or original in {".", ".."}:
        raise UploadRejected("El archivo debe llamarse con extensión .pdf.")
    if not original.lower().endswith(".pdf"):
        raise UploadRejected("Solo se aceptan archivos PDF.")
    if not content:
        raise UploadRejected("El archivo está vacío.")
    if len(content) > max_bytes:
        megabytes = max_bytes // (1024 * 1024)
        raise UploadRejected(
            f"El archivo supera el máximo de {megabytes} MB.",
            "file_too_large",
        )
    if not content.startswith(PDF_MAGIC):
        raise UploadRejected("El contenido no es un PDF válido.")
    return original[:200]


def extract_text(file_path: Path) -> str:
    import pymupdf

    try:
        document = pymupdf.open(file_path)
    except Exception as exc:
        raise UploadRejected(
            "No se pudo abrir el PDF. Verifique que no esté dañado.",
            "invalid_pdf",
        ) from exc
    try:
        parts = [(page.get_text() or "") for page in document]
    finally:
        document.close()
    return "\n".join(parts).strip()


def clip_text(text: str) -> str:
    if len(text) <= RAW_TEXT_LIMIT:
        return text
    return text[:RAW_TEXT_LIMIT] + "\n[texto truncado para proteger memoria]"
