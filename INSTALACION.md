# Replicar el proyecto en otra computadora

Esta guía deja el mismo sistema que hay en este equipo: la API de facturas, el modo sin modelo y Ollama con el modelo pequeño `qwen2.5:1.5b`.

Sirve para Windows de 64 bits, con unos 8 GB de RAM y al menos 6 GB libres en disco. No hace falta tarjeta gráfica. No hay que pagar APIs.

## Qué se instala y para qué

| Pieza | Para qué sirve | ¿Hace falta? |
| --- | --- | --- |
| Python 3.12 | Ejecuta la API. La guía de la prueba acepta 3.11 o superior. | Sí |
| Librerías de `requirements.txt` | FastAPI, SQLite, lectura de PDF y pruebas. | Sí |
| Ollama | Programa que corre un modelo de lenguaje en la propia PC. | Solo si quieres interpretar facturas sin etiquetas |
| Modelo `qwen2.5:1.5b` | Lee el texto y propone proveedor, RUC, número, fecha e importes. Pesa cerca de 1 GB. | Solo junto con Ollama |
| Tesseract | Leería una factura escaneada, que es una foto y no tiene texto. | No. Esta versión no lo llama. Si el PDF no tiene texto, la API responde `requires_ocr` |

PyMuPDF lee el texto que el PDF ya trae. En modo `auto`, si las etiquetas no completan la factura, ese mismo texto pasa a Ollama. Si el PDF no tiene texto, el proceso se detiene: Ollama no se usa para inventar una factura escaneada. Tesseract iría antes, para convertir una imagen en texto, y esta versión no lo llama.

## 1. Instalar Python

1. Abre https://www.python.org/downloads/windows/
2. Descarga Python 3.12 de 64 bits.
3. En el instalador marca **Add python.exe to PATH**.
4. Cierra y vuelve a abrir PowerShell.
5. Comprueba:

```powershell
py -3.12 --version
```

Tiene que mostrar `Python 3.12.x`. Si la otra PC solo tiene 3.11, usa `py -3.11` en los comandos siguientes.

## 2. Copiar el proyecto

Copia la carpeta del proyecto, por ejemplo a `C:\dev\diosmar-automation`.

No copies estas cosas de la PC vieja. Se regeneran en la nueva:

- `.venv`
- `diosmar.db`
- `__pycache__`
- los PDF dentro de `uploads`

Sí copia `samples`, `app`, `tests`, `scripts`, `requirements.txt`, `.env.example` y este archivo.

Abre PowerShell en la carpeta copiada. Los comandos de abajo asumen que ya estás dentro de ella.

## 3. Crear el entorno e instalar librerías

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` pide PyMuPDF 1.x a propósito. La serie 2 instala un runtime de modelos y pesa de más para una PC de 8 GB.

Comprueba:

```powershell
.\.venv\Scripts\python.exe -c "import fastapi, pymupdf, pydantic, sqlalchemy; print('Entorno Diosmar OK')"
```

Tiene que imprimir `Entorno Diosmar OK`.

## 4. Configuración

```powershell
Copy-Item .env.example .env
```

El archivo `.env` queda en modo automático:

```text
AI_MODE=auto
OLLAMA_MODEL=qwen2.5:1.5b
OLLAMA_TIMEOUT_SECONDS=180
```

`auto` lee primero las etiquetas. Si con eso la factura está completa, no llama al modelo y responde enseguida. Si falta algún dato, consulta Ollama. `factura_valida.pdf` se puede probar antes de instalar Ollama.

## 5. Probar el proyecto sin modelo

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\generate_samples.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abre http://127.0.0.1:8000/docs

En `POST /api/documents/upload` sube `samples\factura_valida.pdf`. El resultado esperado es HTTP 201, proveedor Comercial ABC y total 115.00. La respuesta lleva `simulated_extraction: true` porque no intervino un modelo.

Para detener el servidor, en esa ventana de PowerShell pulsa Ctrl+C.

## 6. Instalar Ollama

1. Abre https://ollama.com/download
2. Descarga `OllamaSetup.exe`. En esta PC el archivo pesó unos 1,7 GB.
3. Ejecútalo con doble clic y acepta la instalación.
4. Cierra y abre PowerShell otra vez.

Comprueba:

```powershell
ollama --version
```

Si PowerShell no reconoce `ollama`, usa la ruta directa:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" --version
```

En esta computadora quedó instalado Ollama 0.40.16 en `C:\Users\trabajo\AppData\Local\Programs\Ollama\ollama.exe`. La API local responde en http://127.0.0.1:11434

Instalación silenciosa, la que se usó aquí, por si la otra PC se prepara sin asistente:

```powershell
$setup = Join-Path $env:TEMP "OllamaSetup.exe"
curl.exe -L --fail -o $setup "https://ollama.com/download/OllamaSetup.exe"
Start-Process -FilePath $setup -ArgumentList "/VERYSILENT","/NORESTART" -Wait
```

## 7. Descargar el modelo

Con la PC conectada a internet:

```powershell
ollama pull qwen2.5:1.5b
ollama list
```

`ollama list` debe mostrar `qwen2.5:1.5b`. La descarga es de unos 986 MB. La primera respuesta del modelo, en una PC de 8 GB sin tarjeta gráfica, puede tardar cerca de un minuto. Las siguientes suelen bajar a unos segundos si el modelo sigue en memoria.

Para soltar la memoria cuando ya no lo uses:

```powershell
ollama stop qwen2.5:1.5b
```

El modelo sigue en disco. La próxima factura lo vuelve a cargar.

## 8. Dejar el modo automático

No hace falta cambiar `.env` para que Ollama entre cuando las etiquetas fallan. `AI_MODE=auto` ya lo hace.

Arranca el servidor:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abre http://127.0.0.1:8000/health

Tiene que decir `"ai_mode": "auto"`.

Si quieres que todas las facturas pasen por el modelo, aunque las etiquetas estén completas, cambia la línea a `AI_MODE=ollama` y reinicia. Deja `OLLAMA_TIMEOUT_SECONDS=180`.

## 9. Probar una factura sin etiquetas

Sube `samples\factura_sin_etiquetas.pdf` en `/docs`.

Ese PDF dice: «Comercial ABC nos debe 115 dolares. RUC 0991234567001. Total 115.» No trae líneas `Proveedor:` ni `Fecha:`.

En la prueba real de este equipo el resultado fue HTTP 202, `needs_review`, con:

- `simulated_extraction: false`
- `ai_model: qwen2.5:1.5b`
- proveedor `Comercial ABC`
- RUC `0991234567001`
- la fecha que inventó el modelo, `2023-04-01`, se descartó porque no está escrita en el PDF
- faltan número de factura e impuesto, así que no se envió al sistema administrativo

Eso es lo correcto. El modelo propone y el programa solo conserva lo que aparece en el documento. Si falta un dato o el total no cuadra, la factura queda para una persona.

`samples\factura_vacia.pdf` sigue respondiendo `requires_ocr`. Ollama no se usa ahí: no hay texto y no se inventa una factura. Para ese caso haría falta un OCR, y esta versión no lo tiene conectado.

## 10. Usar solo etiquetas

`factura_valida.pdf` ya responde enseguida en modo `auto`, porque las etiquetas están completas y Ollama no se llama.

Para impedir cualquier llamada al modelo, en `.env`:

```text
AI_MODE=mock
```

Reinicia el servidor. Una factura sin etiquetas quedará en revisión y no se consultará Ollama.

## Ver la base de datos

La base no es un servidor aparte. Es el archivo `diosmar.db`, en la misma carpeta del proyecto. En esta PC está en `G:\mar\diosmar.db`. La crea la API la primera vez que arranca. La tabla se llama `invoices`.

Los importes están en centavos: `23000` es `230.00`.

Para ver las facturas sin instalar nada más, en PowerShell dentro de la carpeta del proyecto:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; con = sqlite3.connect('diosmar.db'); rows = con.execute('select id, supplier, ruc, invoice_number, printf(''%.2f'', total_cents / 100.0), status from invoices order by id'); print('\n'.join(str(row) for row in rows))"
```

También puedes consultarlas por la API, con el servidor encendido: http://127.0.0.1:8000/api/documents

Si quieres una ventana para abrir el archivo, instala DB Browser for SQLite desde https://sqlitebrowser.org/ y abre `diosmar.db`. En la pestaña **Browse Data** elige la tabla `invoices`. No hace falta para que el proyecto funcione.

No abras `diosmar.db` con Word ni con el Bloc de notas: es un archivo binario. Al copiar el proyecto a otra PC no copies este archivo si quieres empezar sin facturas.

## Problemas frecuentes

| Qué pasa | Qué hacer |
| --- | --- |
| `py` no reconoce Python | Reinstala Python con **Add python.exe to PATH** y abre una PowerShell nueva. |
| El puerto 8000 está ocupado | Ya hay un servidor encendido. Abre http://127.0.0.1:8000/docs o cierra la ventana anterior con Ctrl+C. |
| `ollama` no se reconoce | Usa `& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"`. |
| La carga del PDF tarda y termina en `ai_unavailable` | Ollama no está abierto o el modelo aún carga. Revisa `ollama list` y sube `OLLAMA_TIMEOUT_SECONDS`. |
| La PC se pone lenta | Cierra navegadores y deja de usar el modelo con `ollama stop qwen2.5:1.5b`. |
| Quieres el mismo resultado de siempre | Vuelve `AI_MODE` a `mock`. |

La explicación de cada archivo del programa está en `README.md`.
