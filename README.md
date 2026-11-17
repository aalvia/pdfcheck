# Diosmar — automatización de facturas

MVP para la prueba técnica: recibe un PDF, extrae sus datos, los valida, los guarda, avisa a un sistema administrativo simulado y deja una notificación simulada.

No usa APIs de pago. El modo normal es `auto`: primero lee las etiquetas y, si falta algún dato, consulta Ollama. Una factura completa por etiquetas no llama al modelo. En este equipo Ollama ya está instalado con `qwen2.5:1.5b`. Para repetir el proyecto en otra computadora, sigue [INSTALACION.md](INSTALACION.md).

## Cómo ejecutarlo

Desde PowerShell, en esta carpeta:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Abrir http://127.0.0.1:8000/docs

Las facturas quedan en el archivo `diosmar.db`, junto al proyecto. Cómo abrirlo está en [INSTALACION.md](INSTALACION.md), en la sección «Ver la base de datos».

El entorno virtual ya está creado con Python 3.12. La guía pide 3.11 o superior. En este equipo no está instalado el 3.11; el 3.12 cumple el requisito.

Si hubiera que recrear el entorno:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\generate_samples.py
```

## Qué hace cada modo

| Variable | Valor por defecto | Efecto |
| --- | --- | --- |
| `AI_MODE` | `auto` | Primero lee etiquetas. Si falta proveedor, RUC, número, fecha o un importe, llama a Ollama. |
| `AI_MODE` | `mock` | Solo etiquetas. No llama al modelo aunque falten datos. |
| `AI_MODE` | `ollama` | Solo el modelo. Si Ollama no responde, guarda el PDF como `ai_unavailable` y no inventa datos. |
| `EXTERNAL_SYSTEM_MODE` | `mock` | Acepta la factura dentro del mismo proceso y devuelve una referencia `MOCK-`. |
| `EXTERNAL_SYSTEM_MODE` | `http` | Hace `POST` con timeout a `EXTERNAL_SYSTEM_URL`. |
| Notificaciones | siempre simuladas | Se escriben en el log y en la base, con el prefijo `[SIMULADO]`. No sale un correo. |

El modo mock no rellena un ejemplo fijo. Si el PDF no trae la etiqueta, el campo queda vacío y la factura pasa a revisión.

## Flujo

1. `POST /api/documents/upload` recibe el PDF.
2. Se rechaza si no termina en `.pdf`, no empieza por `%PDF` o supera 10 MB.
3. Se guarda con un nombre interno (`uuid.pdf`). El nombre del usuario no se usa como ruta.
4. PyMuPDF extrae solo el texto que ya está en el archivo.
5. Si no hay texto, el estado es `requires_ocr`. No se inventan datos.
6. En modo `auto` se leen las etiquetas. Si la factura queda incompleta, el mismo texto se envía a Ollama.
7. Las reglas de negocio deciden si está `processed` o `needs_review`.
8. RUC + número de factura no se insertan dos veces.
9. La factura se confirma en SQLite **antes** de llamar al sistema externo.
10. Solo una factura válida se envía al sistema administrativo.
11. Se registra una notificación simulada.

## Resultados que debes esperar

Sube los PDF de `samples/` en Swagger:

| Archivo | HTTP | Qué decir |
| --- | --- | --- |
| `factura_valida.pdf` | 201 | Datos del ejemplo, integración `sent_mock`, aviso simulado. |
| El mismo PDF otra vez | 409 | Duplicado. No se inserta de nuevo. |
| `factura_vacia.pdf` | 422 | Hace falta OCR. Campos vacíos. |
| `factura_total_incorrecto.pdf` | 202 | Guardada para revisión. No sale al sistema externo. |
| `factura_incompleta.pdf` | 202 | Falta el proveedor. |
| `factura_sin_etiquetas.pdf` | 202 | No hay etiquetas, así que entra Ollama. Puede tardar. Lo que el modelo invente y no esté en el PDF se descarta. |
| `ollama 1.pdf` | 201 si el modelo lee bien | Frases completas, sin etiquetas. Distribuidora El Sol, total 230.00. |
| `ollama 2.pdf` | 201 si el modelo lee bien | Alimentos del Pacifico, total 92.58. |
| `ollama 3.pdf` | 201 si el modelo lee bien | Panaderia La Espiga, total 57.50. |
| `ollama 4.pdf` | 201 si el modelo lee bien | Ferreteria El Martillo, total 46.00. Reservado para probar el alta. |
| `ollama 5.pdf` | 201 si el modelo lee bien | Textiles Andinos, total 172.79. Reservado para probar el alta. |
| `ollama 6.pdf` | 201 si el modelo lee bien | Clinica Santa Rosa, total 345.00. Reservado para probar el alta. |

## Endpoints

| Método | Ruta | Función |
| --- | --- | --- |
| `GET` | `/health` | La API y SQLite responden. |
| `POST` | `/api/documents/upload` | Procesa un PDF. |
| `GET` | `/api/documents` | Lista facturas, sin el texto completo. |
| `GET` | `/api/documents/{id}` | Detalle, con el texto extraído. |
| `POST` | `/api/documents/{id}/notify` | Regenera el aviso simulado. |
| `POST` | `/api/mock/admin/invoices` | Contrato del sistema externo. Es un mock. |

Ejemplo con la API ya levantada:

```powershell
curl.exe -F "file=@samples/factura_valida.pdf;type=application/pdf" http://127.0.0.1:8000/api/documents/upload
curl.exe http://127.0.0.1:8000/api/documents
```

## Mapa de archivos

| Archivo | Responsabilidad |
| --- | --- |
| `app/main.py` | Crea la aplicación, abre la base al arrancar, expone `/health` y traduce errores a JSON. |
| `app/config.py` | Lee `.env`. Aquí se cambia de mock a Ollama sin tocar las rutas. |
| `app/database.py` | Motor SQLite y una sesión por petición. |
| `app/deps.py` | Entrega configuración y sesión a las rutas. |
| `app/errors.py` | Errores de negocio (`invalid_file`, `not_found`, fallo de IA). |
| `app/money.py` | Importes en centavos. La tolerancia de 0.02 son 2 centavos. |
| `app/models/invoice.py` | Tabla `invoices` y la unicidad RUC + número. |
| `app/schemas/extraction.py` | Contrato interno de la extracción. Descarta campos extra de la IA. |
| `app/schemas/invoice.py` | Contratos HTTP de respuesta y del sistema administrativo. |
| `app/routes/documents.py` | Recibe HTTP. No contiene las reglas. |
| `app/routes/mock_admin.py` | Endpoint simulado del sistema externo, marcado como mock. |
| `app/services/pdf_service.py` | Valida el archivo y extrae texto con PyMuPDF. |
| `app/services/ai_service.py` | Proveedor mock u Ollama. El prompt prohíbe inventar. |
| `app/services/validation_service.py` | RUC de 13 dígitos, formato de factura, fecha y cuadre de importes. |
| `app/services/integration_service.py` | Envío al sistema administrativo, en mock o por HTTP con timeout. |
| `app/services/notification_service.py` | Arma el aviso y deja escrito que no es un correo real. |
| `app/services/document_service.py` | Ordena los ocho pasos del flujo. |
| `tests/` | Cubre el camino feliz, OCR, duplicado, revisión, fallo externo y el prompt de Ollama. |
| `samples/` | PDFs para la demostración. |

## Decisiones para defender

- **FastAPI.** API REST rápida, validación con Pydantic y Swagger en `/docs`.
- **SQLite.** Un archivo local, suficiente para el simulacro. En producción sería PostgreSQL.
- **Centavos enteros.** No se guarda dinero como `float`.
- **Proveedor de IA intercambiable.** Las rutas no saben si detrás hay reglas o Ollama.
- **No se confía en la IA.** Hace falta JSON, los campos extra se tiran y, si un dato no está escrito en el PDF, se descarta. Un total que no cuadra no sale de la empresa.
- **El mock no inventa.** Solo lee etiquetas. Por eso `simulated_extraction` es verdadero: no hubo un modelo.
- **OCR ausente no se disimula.** Sin texto, la respuesta es `requires_ocr`.
- **Duplicados.** Consulta previa y además una restricción única en la base.
- **Si el sistema externo falla, la factura ya está guardada.** Por eso se hace `commit` antes de integrarla.
- **El mock administrativo corre en el mismo proceso.** Una llamada HTTP al propio servidor, con un solo worker, se bloquearía esperándose a sí misma. El endpoint `/api/mock/admin/invoices` existe para mostrar el contrato en Swagger.
- **Sin autenticación.** Es un MVP local. No lo expondría a internet.
- **PyMuPDF 1.x.** La serie 2 instala un runtime de modelos. Con 8 GB no aporta nada porque aquí solo se necesita el texto. La guía importa `fitz`; en la versión 1.28 ese nombre ya avisa que queda obsoleto, así que el código usa `import pymupdf`. Es la misma librería.

## Cómo explicarlo en dos minutos

Desarrollé una API con FastAPI que recibe facturas PDF. PyMuPDF extrae el texto real; si el PDF es una imagen, respondo que hace falta OCR y no invento datos. El texto pasa por un proveedor intercambiable: hoy es un extractor por etiquetas, marcado como simulado, y puede cambiarse a Ollama sin tocar las rutas. Pydantic y las reglas de negocio revisan el RUC, el número, la fecha y que subtotal más impuesto cuadren con el total, con dos centavos de tolerancia. No exijo un IVA fijo porque la tarifa cambia. Si algo no cuadra, guardo la factura para revisión humana y no la envío al sistema administrativo. Si cuadra, evito duplicados por RUC más número, la guardo en SQLite con los montos en centavos y la entrego a un sistema externo simulado. Si ese sistema no responde, la factura no se pierde. La notificación queda en el log con el prefijo simulado: no sale un correo real. Para producción faltan autenticación, OCR, una cola, reintentos, PostgreSQL y una pantalla de revisión humana.

## Qué no está hecho

- No hay Ollama ni Tesseract instalados.
- No hay correo SMTP.
- No hay login.
- El RUC se valida por longitud (13 dígitos), no por el dígito verificador.
- El modo mock solo entiende etiquetas y montos simples, no una factura con diseño libre.
- No hay cola de mensajes ni reintento automático de la integración.

## Configuración

Los valores viven en `.env`. La plantilla sin secretos es `.env.example`. Este proyecto no tiene claves: la base es un archivo local y los servicios externos son simulados.
