"""Sistema administrativo simulado.

Sirve para mostrar el contrato HTTP en Swagger. No es el sistema real de Diosmar
y no debe presentarse como una integración en producción.
"""

from fastapi import APIRouter

from app.schemas.invoice import AdminInvoiceIn, AdminInvoiceOut
from app.services.integration_service import accept_admin_invoice

router = APIRouter()


@router.post("/invoices", response_model=AdminInvoiceOut)
def receive_invoice(payload: AdminInvoiceIn) -> AdminInvoiceOut:
    """Acepta una factura de prueba y devuelve una referencia MOCK-."""
    return accept_admin_invoice(payload)
