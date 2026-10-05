from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    frontend_dir: Path = Path(os.getenv("FRONTEND_DIR", str(Path(__file__).resolve().parents[2] / "frontend"))).resolve()
    data_dir: Path = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[1] / "data"))).resolve()
    serve_frontend: bool = _bool("SERVE_FRONTEND", True)
    cors_origins: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:8000"))

    payment_provider: str = os.getenv("PAYMENT_PROVIDER", "mock").strip().lower()
    pending_ttl_seconds: int = int(os.getenv("PENDING_TTL_SECONDS", str(30 * 24 * 60 * 60)))
    enable_mock_psp: bool = _bool("ENABLE_MOCK_PSP", True)
    mock_pix_key: str = os.getenv("MOCK_PIX_KEY", "doacoes@fundocentenario.org.br")
    mock_merchant_name: str = os.getenv("MOCK_MERCHANT_NAME", "FUNDO CENTENARIO")
    mock_merchant_city: str = os.getenv("MOCK_MERCHANT_CITY", "PORTO ALEGRE")

    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe_api_version: str = os.getenv("STRIPE_API_VERSION", "2026-09-30.endive")
    stripe_live_mode: bool = _bool("STRIPE_LIVE_MODE", False)

    email_enabled: bool = _bool("EMAIL_ENABLED", False)
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_security: str = os.getenv("SMTP_SECURITY", "starttls").lower()
    email_from_address: str = os.getenv("EMAIL_FROM_ADDRESS", "")
    email_from_name: str = os.getenv("EMAIL_FROM_NAME", "Fundo Centenário")
    email_reply_to: str = os.getenv("EMAIL_REPLY_TO", "")
    email_subject: str = os.getenv("EMAIL_SUBJECT", "Obrigado por apoiar o Fundo Centenário")
    email_template_path: Path = Path(os.getenv("EMAIL_TEMPLATE_PATH") or str(Path(__file__).resolve().parents[1] / "templates" / "donation_thank_you.html"))
    email_activity_url: str = os.getenv("EMAIL_ACTIVITY_URL", "")
    email_thank_you_text: str = os.getenv("EMAIL_THANK_YOU_TEXT", "Seu apoio transforma recursos em oportunidades para estudantes e projetos da Escola de Engenharia. Conheça as atividades do Fundo e acompanhe as histórias que a sua contribuição ajuda a construir.")

    psp_base_url: str = os.getenv("PSP_BASE_URL", "").rstrip("/")
    psp_pix_create_path: str = os.getenv("PSP_PIX_CREATE_PATH", "/pix/payments")
    psp_pix_automatic_create_path: str = os.getenv("PSP_PIX_AUTOMATIC_CREATE_PATH", "/pix/automatic/authorizations")
    psp_card_checkout_path: str = os.getenv("PSP_CARD_CHECKOUT_PATH", "/checkout/sessions")
    psp_status_path_template: str = os.getenv("PSP_STATUS_PATH_TEMPLATE", "/payments/{provider_payment_id}")

    psp_auth_mode: str = os.getenv("PSP_AUTH_MODE", "none").strip().lower()
    psp_api_key: str = os.getenv("PSP_API_KEY", "")
    psp_api_key_header: str = os.getenv("PSP_API_KEY_HEADER", "X-API-Key")
    psp_bearer_token: str = os.getenv("PSP_BEARER_TOKEN", "")
    psp_oauth_token_url: str = os.getenv("PSP_OAUTH_TOKEN_URL", "")
    psp_client_id: str = os.getenv("PSP_CLIENT_ID", "")
    psp_client_secret: str = os.getenv("PSP_CLIENT_SECRET", "")
    psp_oauth_scope: str = os.getenv("PSP_OAUTH_SCOPE", "")
    psp_send_customer_data: bool = _bool("PSP_SEND_CUSTOMER_DATA", False)

    psp_webhook_secret: str = os.getenv("PSP_WEBHOOK_SECRET", "")
    psp_webhook_signature_header: str = os.getenv("PSP_WEBHOOK_SIGNATURE_HEADER", "X-Webhook-Signature")

    psp_field_payment_id: str = os.getenv("PSP_FIELD_PAYMENT_ID", "id")
    psp_field_status: str = os.getenv("PSP_FIELD_STATUS", "status")
    psp_field_pix_copy_paste: str = os.getenv("PSP_FIELD_PIX_COPY_PASTE", "pix.copy_paste")
    psp_field_pix_qr_base64: str = os.getenv("PSP_FIELD_PIX_QR_BASE64", "pix.qr_base64")
    psp_field_redirect_url: str = os.getenv("PSP_FIELD_REDIRECT_URL", "redirect_url")
    psp_field_expires_at: str = os.getenv("PSP_FIELD_EXPIRES_AT", "expires_at")

    psp_webhook_field_event_id: str = os.getenv("PSP_WEBHOOK_FIELD_EVENT_ID", "event_id")
    psp_webhook_field_payment_id: str = os.getenv("PSP_WEBHOOK_FIELD_PAYMENT_ID", "payment_id")
    psp_webhook_field_donation_id: str = os.getenv("PSP_WEBHOOK_FIELD_DONATION_ID", "metadata.donation_id")
    psp_webhook_field_status: str = os.getenv("PSP_WEBHOOK_FIELD_STATUS", "status")
    psp_webhook_field_amount_cents: str = os.getenv("PSP_WEBHOOK_FIELD_AMOUNT_CENTS", "amount_cents")
    psp_webhook_field_token_hash: str = os.getenv("PSP_WEBHOOK_FIELD_TOKEN_HASH", "metadata.status_token_hash")
    psp_webhook_field_program: str = os.getenv("PSP_WEBHOOK_FIELD_PROGRAM", "metadata.program")
    psp_webhook_field_method: str = os.getenv("PSP_WEBHOOK_FIELD_METHOD", "metadata.method")

    psp_paid_statuses: list[str] = field(default_factory=lambda: _list("PSP_PAID_STATUSES", "paid,confirmed,approved,completed"))
    psp_authorized_statuses: list[str] = field(default_factory=lambda: _list("PSP_AUTHORIZED_STATUSES", "authorized,active"))
    psp_failed_statuses: list[str] = field(default_factory=lambda: _list("PSP_FAILED_STATUSES", "failed,rejected,cancelled,canceled,expired"))


settings = Settings()
