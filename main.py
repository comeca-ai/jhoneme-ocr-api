import base64
import hmac
import os
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

MAX_FILE_BYTES = int(os.getenv('MAX_FILE_BYTES', str(10 * 1024 * 1024)))
OCR_TIMEOUT = float(os.getenv('OCR_TIMEOUT_SECONDS', '300'))
OCR_URL = os.getenv('PADDLEOCR_URL', '').rstrip('/')
OCR_USER = os.getenv('PADDLEOCR_USERNAME', 'admin')
OCR_PASSWORD = os.getenv('PADDLEOCR_PASSWORD', '')
GATEWAY_KEY = os.getenv('GATEWAY_API_KEY', '')


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = [name for name, value in {
        'PADDLEOCR_URL': OCR_URL,
        'PADDLEOCR_PASSWORD': OCR_PASSWORD,
        'GATEWAY_API_KEY': GATEWAY_KEY,
    }.items() if not value]
    if missing:
        raise RuntimeError('Missing environment variables: ' + ', '.join(missing))
    yield


app = FastAPI(
    title='Jhoneme OCR API', version='0.1.0',
    description='Gateway privado para o PaddleOCR. Envie uma imagem ou PDF em multipart/form-data.',
    lifespan=lifespan,
)


def require_key(x_api_key: Annotated[str | None, Header(alias='X-API-Key')] = None):
    if not GATEWAY_KEY or not x_api_key or not hmac.compare_digest(x_api_key, GATEWAY_KEY):
        raise HTTPException(status_code=401, detail='Invalid API key')


@app.get('/health', tags=['Status'])
def health():
    return {'status': 'ok', 'service': 'jhoneme-ocr-api'}


def collect_text(obj) -> list[str]:
    """Best-effort extraction, keeping original upstream response for full fidelity."""
    found = []
    def walk(value):
        if isinstance(value, dict):
            for key in ('rec_texts', 'texts'):
                texts = value.get(key)
                if isinstance(texts, list):
                    found.extend(s for s in texts if isinstance(s, str))
            for key, child in value.items():
                if key not in ('rec_texts', 'texts'):
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(obj)
    return found


@app.post('/v1/ocr', dependencies=[Depends(require_key)], tags=['OCR'])
async def ocr(file: Annotated[UploadFile, File(description='Imagem PNG/JPEG/WEBP ou PDF')]):
    filename = (file.filename or '').lower()
    content_type = (file.content_type or '').lower()
    is_pdf = content_type == 'application/pdf' or filename.endswith('.pdf')
    is_image = content_type in ('image/jpeg', 'image/png', 'image/webp') or filename.endswith(('.jpg', '.jpeg', '.png', '.webp'))
    if not (is_pdf or is_image):
        raise HTTPException(415, 'Upload a PNG, JPEG, WEBP or PDF')
    data = await file.read(MAX_FILE_BYTES + 1)
    if not data:
        raise HTTPException(400, 'Empty file')
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, 'File exceeds upload size limit')
    if is_pdf and not data.startswith(b'%PDF-'):
        raise HTTPException(415, 'Invalid PDF')
    if is_image and not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff') or (data.startswith(b'RIFF') and data[8:12] == b'WEBP')):
        raise HTTPException(415, 'Invalid image')

    payload = {'file': base64.b64encode(data).decode('ascii'), 'fileType': 0 if is_pdf else 1}
    try:
        async with httpx.AsyncClient(timeout=OCR_TIMEOUT, follow_redirects=False) as client:
            response = await client.post(
                f'{OCR_URL}/ocr', json=payload, auth=(OCR_USER, OCR_PASSWORD),
            )
        response.raise_for_status()
        result = response.json()
    except httpx.TimeoutException:
        raise HTTPException(504, 'OCR processing timed out')
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, 'OCR engine unavailable or returned an invalid response')

    lines = collect_text(result)
    return {'success': True, 'text': '\n'.join(lines), 'lines': lines, 'raw': result}
