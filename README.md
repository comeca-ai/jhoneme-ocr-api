# Jhoneme OCR API — FastAPI gateway

A lightweight FastAPI service that accepts a PDF or image upload and forwards it to the already-running PaddleOCR service. **No OCR models run in this gateway.**

## Routes

- `GET /health` — service health
- `GET /docs` — FastAPI Swagger UI
- `GET /openapi.json` — OpenAPI schema
- `POST /v1/ocr` — multipart upload, requires `X-API-Key` header. Returns `text`, `lines`, and original PaddleX response in `raw`.

## Railway deployment

1. Push this repository to `comeca-ai/jhoneme-ocr-api`.
2. Add a **new Railway service** from this GitHub repository. Do not alter the running PaddleOCR service.
3. Configure its service variables:
   - `PADDLEOCR_URL` — existing PaddleOCR base URL, WITHOUT trailing `/ocr`.
   - `PADDLEOCR_USERNAME` — `admin` unless changed in existing service.
   - `PADDLEOCR_PASSWORD` — the existing PaddleOCR password, **never commit it**.
   - `GATEWAY_API_KEY` — a newly generated long random value to share securely with the consuming service.
   - Optional `MAX_FILE_BYTES` (default 10485760) and `OCR_TIMEOUT_SECONDS` (default 300).
4. Generate a Railway public domain for this new service. Its healthcheck path may be set to `/health`.
5. Open `https://YOUR-FASTAPI-DOMAIN/docs`; use **Authorize** by editing the `X-API-Key` header field on the POST request (Swagger shows a header input).

For safer network configuration later, use Railway private networking to reach the backend and disable unnecessary public access to it after confirming Caddy health and authentication.

## Test

```bash
curl https://YOUR-FASTAPI-DOMAIN/health
curl -X POST https://YOUR-FASTAPI-DOMAIN/v1/ocr \
  -H "X-API-Key: $GATEWAY_API_KEY" \
  -F 'file=@documento.png'
```

The service rejects missing/wrong keys, unsupported file types, invalid signatures, oversized files and upstream timeouts. Documents are held in memory only for request processing; avoid sharing OCR responses and files in application logs. Files containing sensitive information require appropriate retention and access controls in the consuming company.

## Local run

```bash
pip install -r requirements.txt
export PADDLEOCR_URL='https://paddleocr-production-d016.up.railway.app'
export PADDLEOCR_USERNAME='admin'
export PADDLEOCR_PASSWORD='YOUR_EXISTING_PASSWORD'
export GATEWAY_API_KEY='A_LONG_RANDOM_KEY'
uvicorn main:app --reload
```

## Limitations

- Single gateway key in MVP; not yet individual keys, metering or billing per company.
- `text` is a best-effort extraction from recognized PaddleX fields; use `raw` to access full boxes/confidence.
- Multipart uploads are base64-encoded toward PaddleOCR, increasing upstream request size. Configure the existing `PADDLEOCR_MAX_BODY` appropriately for larger files; cap in this gateway is 10 MB by default.
- OCR latency depends on Railway CPU and number of pages. Do not expose untrusted URL-fetch functionality.
