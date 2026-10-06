from __future__ import annotations

import html
import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from .config import settings
from .models import DonationFinalizeRequest, DonationIntentRequest, DonationIntentResponse, DonationOptionsResponse, DonationStatusResponse
from .providers.generic_http import GenericHttpPaymentProvider
from .providers.mock import MockPaymentProvider
from .providers.stripe import StripePaymentProvider
from .services import PaymentService
from .scheduler_auth import verify_scheduler


def build_provider():
    if settings.payment_provider == "mock":
        return MockPaymentProvider(settings)
    if settings.payment_provider == "generic_http":
        return GenericHttpPaymentProvider(settings)
    if settings.payment_provider == "stripe":
        return StripePaymentProvider(settings)
    raise RuntimeError(f"PAYMENT_PROVIDER desconhecido: {settings.payment_provider}")


settings.validate_runtime()
provider = build_provider()
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
    docs_url="/api/docs" if settings.app_env != "production" else None,
    redoc_url=None,
    openapi_url=None if settings.app_env in {"production", "staging"} else "/openapi.json",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_security(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        limit = 1_048_576 if request.url.path.startswith("/api/webhooks/") else 32_768
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > limit:
                return JSONResponse({"detail": "Requisição excede o tamanho permitido."}, status_code=413)
        request._body = bytes(body)
    try:
        response = await call_next(request)
    except Exception as exc:
        # Never log request bodies or SDK exceptions that may contain credentials/PII.
        logging.getLogger(__name__).error("Requisição falhou (%s).", type(exc).__name__)
        response = JSONResponse({"detail": "Serviço temporariamente indisponível."}, status_code=503)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings.app_env in {"production", "staging"}:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    if "text/html" in response.headers.get("content-type", "") and not request.url.path.startswith("/mock-psp/"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
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


@app.post("/api/webhooks/{provider_name}")
async def provider_webhook(provider_name: str, request: Request) -> JSONResponse:
    if provider_name != provider.name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider não encontrado.")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 1_048_576:
            raise HTTPException(status_code=413, detail="Webhook excede o tamanho permitido.")
    headers = {key.lower(): value for key, value in request.headers.items()}
    event = await service.process_webhook(bytes(body), headers)
    return JSONResponse({"received": True, "event_id": event.event_id if event else None})


@app.post("/api/mock/{provider_payment_id}/confirm")
def mock_confirm(provider_payment_id: str, key: str) -> dict[str, str]:
    if settings.payment_provider != "mock" or not settings.enable_mock_psp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mock PSP não habilitado.")
    event, return_url = service.confirm_mock(provider_payment_id, key)
    return {"status": event.status, "donation_id": event.donation_id, "return_url": return_url}


def mock_psp_page(kind: str, provider_payment_id: str, key: str) -> HTMLResponse:
    if settings.payment_provider != "mock" or not settings.enable_mock_psp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mock PSP não habilitado.")
    try:
        entry = provider.get_entry(provider_payment_id, key)  # type: ignore[attr-defined]
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    request = entry.request
    label = "Pix Automático" if kind == "pix-automatico" else "Checkout de cartão"
    amount = f"R$ {request.amount_cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    safe_label = html.escape(label)
    safe_amount = html.escape(amount)
    safe_provider_id = html.escape(provider_payment_id)
    safe_key = html.escape(key)
    body = f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{safe_label} mock</title><style>
body{{font-family:system-ui,sans-serif;background:#f4f7f9;color:#13385c;display:grid;place-items:center;min-height:100vh;margin:0}}
main{{width:min(520px,calc(100% - 32px));background:#fff;border:1px solid #dce4ea;border-radius:20px;padding:32px;box-shadow:0 18px 60px #13385c18}}
small{{font-family:monospace;color:#6b7d8d}} button{{width:100%;padding:15px;border:0;border-radius:12px;background:#13385c;color:#fff;font-weight:700;cursor:pointer}}
.note{{background:#eef5fb;padding:14px;border-radius:12px;margin:20px 0;line-height:1.5}} h1{{margin:8px 0 10px}} p{{line-height:1.6;color:#5b6e7e}}
</style></head><body><main><small>AMBIENTE DE TESTE DO PSP</small><h1>{safe_label}</h1><p>Este painel existe apenas para testar a integração local. Em produção ele será substituído pelo ambiente hospedado do PSP.</p><div class='note'><strong>{safe_amount}</strong><br>Referência: {safe_provider_id}</div><button id='confirm'>Confirmar pagamento de teste</button><p id='status'></p></main>
<script>
const button=document.getElementById('confirm');const status=document.getElementById('status');
button.addEventListener('click',async()=>{{button.disabled=true;status.textContent='Confirmando...';try{{const r=await fetch('/api/mock/{safe_provider_id}/confirm?key={safe_key}',{{method:'POST'}});const data=await r.json();if(!r.ok)throw new Error(data.detail||'Falha');status.textContent='Pagamento confirmado. Retornando ao Fundo...';setTimeout(()=>location.assign(data.return_url),700)}}catch(e){{status.textContent=e.message;button.disabled=false}}}});
</script></body></html>"""
    return HTMLResponse(body)


@app.get("/mock-psp/card/{provider_payment_id}", response_class=HTMLResponse)
def mock_card(provider_payment_id: str, key: str) -> HTMLResponse:
    return mock_psp_page("card", provider_payment_id, key)


@app.get("/mock-psp/pix-automatico/{provider_payment_id}", response_class=HTMLResponse)
def mock_pix_automatic(provider_payment_id: str, key: str) -> HTMLResponse:
    return mock_psp_page("pix-automatico", provider_payment_id, key)


if settings.serve_frontend:
    if not settings.frontend_dir.exists():
        raise RuntimeError(f"FRONTEND_DIR não existe: {settings.frontend_dir}")
    app.mount("/", StaticFiles(directory=str(settings.frontend_dir), html=True), name="frontend")
