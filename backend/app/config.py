from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

if os.getenv("PYTHON_DOTENV_DISABLED") != "1":
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
        raise ValueError(f"Configuração booleana inválida: {name}.")
    return normalized in {"1", "true", "yes", "on"}


def _list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
    frontend_dir: Path = Path(os.getenv("FRONTEND_DIR", str(Path(__file__).resolve().parents[2] / "frontend"))).resolve()
    data_dir: Path = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[1] / "data"))).resolve()
    serve_frontend: bool = _bool("SERVE_FRONTEND", True)
    cors_origins: list[str] = field(default_factory=lambda: _list("CORS_ORIGINS", "http://localhost:8000"))
    storage_backend: str = os.getenv("STORAGE_BACKEND", "local")
    google_cloud_project: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    firestore_database: str = os.getenv("FIRESTORE_DATABASE", "(default)")
    firestore_prefix: str = os.getenv("FIRESTORE_PREFIX", "fundo_")
    intent_limit_per_minute: int = int(os.getenv("INTENT_LIMIT_PER_MINUTE", "60"))
    scheduler_audience: str = os.getenv("SCHEDULER_AUDIENCE", "")
    scheduler_service_account: str = os.getenv("SCHEDULER_SERVICE_ACCOUNT", "")
    email_batch_size: int = int(os.getenv("EMAIL_BATCH_SIZE", "10"))

    pending_ttl_seconds: int = int(os.getenv("PENDING_TTL_SECONDS", str(30 * 24 * 60 * 60)))
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe_api_version: str = os.getenv("STRIPE_API_VERSION", "2026-09-30.endive")

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

    def validate_runtime(self) -> None:
        if self.app_env not in {"development", "test", "staging", "production"}:
            raise ValueError("APP_ENV inválido.")
        if self.storage_backend not in {"local", "firestore"}:
            raise ValueError("STORAGE_BACKEND inválido.")
        if not 1 <= self.intent_limit_per_minute <= 10000 or not 1 <= self.email_batch_size <= 20:
            raise ValueError("Limites de requisições/email inválidos.")
        if self.storage_backend == "firestore" and not self.google_cloud_project:
            raise ValueError("Configure GOOGLE_CLOUD_PROJECT.")
        if not self.firestore_prefix or not self.firestore_prefix.replace("_", "").isalnum():
            raise ValueError("FIRESTORE_PREFIX inválido.")
        if self.app_env not in {"production", "staging"}:
            return
        url = urlsplit(self.public_base_url)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.path or url.query or url.fragment:
            raise ValueError("PUBLIC_BASE_URL deve ser uma origem HTTPS.")
        if self.storage_backend != "firestore":
            raise ValueError("Use Firestore em staging/production.")
        if os.getenv("FIRESTORE_EMULATOR_HOST") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            raise ValueError("Produção/staging deve usar a identidade do serviço, sem emulator ou arquivo de chave.")
        if any(origin != self.public_base_url for origin in self.cors_origins):
            raise ValueError("CORS_ORIGINS deve corresponder à origem pública.")
        if self.email_enabled and (not self.scheduler_service_account or urlsplit(self.scheduler_audience).scheme != "https"):
            raise ValueError("Configure a identidade e audience HTTPS do Scheduler.")


settings = Settings()
