from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .config import settings
from .models import DonationFinalizeRequest, DonationIntentRequest, DonationIntentResponse, DonationOptionsResponse, DonationStatusResponse
from .providers.stripe import StripePaymentProvider
from .services import PaymentService
from .scheduler_auth import verify_scheduler


settings.validate_runtime()
provider = StripePaymentProvider(settings)
service = PaymentService(settings, provider)


async def email_worker() -> None:
    while True:
        try:
            await run_in_threadpool(service.process_pending_emails)
        except Exception as exc:
            logging.getLogger(__name__).warning("Falha no worker local (%s).", type(exc).__name__)
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(email_worker()) if settings.email_enabled and settings.storage_backend == "local" else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="Fundo Centenário Payments",
    version="1.0.0",
    docs_url="/api/docs" if settings.app_env not in {"production", "staging"} else None,
    redoc_url=None,
    openapi_url=None if settings.app_env in {"production", "staging"} else "/openapi.json",
    lifespan=lifespan,
)

request_logger = logging.getLogger("fundo.requests")
request_logger.setLevel(logging.INFO)
request_logger.propagate = False
if not request_logger.handlers:
    request_logger.addHandler(logging.StreamHandler())


@app.middleware("http")
async def request_security(request: Request, call_next):
    started = time.monotonic()
    request_id = uuid.uuid4().hex
    response = None
    if request.method in {"POST", "PUT", "PATCH"}:
        limit = 1_048_576 if request.url.path.startswith("/api/webhooks/") else 32_768
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > limit:
                response = JSONResponse({"detail": "Requisição excede o tamanho permitido."}, status_code=413)
                break
            body.extend(chunk)
        request._body = bytes(body)
    try:
        if response is None:
            response = await call_next(request)
    except Exception as exc:
        # Never log request bodies or SDK exceptions that may contain credentials/PII.
        request_logger.error(json.dumps({"severity": "ERROR", "message": "request_failed",
                                         "request_id": request_id, "error_type": type(exc).__name__}))
        response = JSONResponse({"detail": "Serviço temporariamente indisponível."}, status_code=503)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.app_env in {"production", "staging"}:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    if "text/html" in response.headers.get("content-type", ""):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request_id
    route = request.scope.get("route")
    request_logger.info(json.dumps({"severity": "ERROR" if response.status_code >= 500 else "INFO",
                                   "message": "http_request", "request_id": request_id,
                                   "route": getattr(route, "path", "unmatched"),
                                   "method": request.method, "status": response.status_code,
                                   "duration_ms": round((time.monotonic() - started) * 1000, 2)}))
    return response

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Donation-Token", "X-Idempotency-Key"],
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "provider": provider.name}


@app.get("/api/ready")
def ready() -> dict[str, str]:
    if service.repository:
        service.payment_confirmations.contains("readiness-probe")
    return {"status": "ok"}


@app.post("/api/donations/intents", response_model=DonationIntentResponse, status_code=status.HTTP_201_CREATED)
async def create_donation_intent(payload: DonationIntentRequest, x_idempotency_key: str | None = Header(None)) -> DonationIntentResponse:
    if not await run_in_threadpool(service.allow_intent):
        raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde um minuto.", headers={"Retry-After": "60"})
    return await service.create_intent(payload, x_idempotency_key)


@app.post("/api/internal/emails/process")
def process_emails(authorization: str = Header("")) -> dict[str, int]:
    verify_scheduler(authorization, settings)
    return service.process_pending_emails()


@app.get("/api/donations/options", response_model=DonationOptionsResponse)
def donation_options() -> DonationOptionsResponse:
    return DonationOptionsResponse(methods=list(provider.supported_methods))


@app.get("/api/donations/{donation_id}/status", response_model=DonationStatusResponse)
def donation_status(donation_id: str, x_donation_token: str = Header(...)) -> DonationStatusResponse:
    return service.get_status(donation_id, x_donation_token)


@app.post("/api/donations/{donation_id}/finalize", response_model=DonationStatusResponse)
def finalize_donation(
    donation_id: str,
    payload: DonationFinalizeRequest,
    x_donation_token: str = Header(...),
) -> DonationStatusResponse:
    return service.finalize_after_restart(donation_id, x_donation_token, payload)


@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request) -> JSONResponse:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 1_048_576:
            raise HTTPException(status_code=413, detail="Webhook excede o tamanho permitido.")
    headers = {key.lower(): value for key, value in request.headers.items()}
    event = await service.process_webhook(bytes(body), headers)
    return JSONResponse({"received": True, "event_id": event.event_id if event else None})


if settings.serve_frontend:
    if not settings.frontend_dir.exists():
        raise RuntimeError(f"FRONTEND_DIR não existe: {settings.frontend_dir}")
    app.mount("/", StaticFiles(directory=str(settings.frontend_dir), html=True), name="frontend")
