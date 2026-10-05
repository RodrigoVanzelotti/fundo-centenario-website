from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from .base import PaymentProvider, PaymentStartRequest, PaymentStartResult, ProviderWebhookEvent
from ..config import Settings


def _get_path(data: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


class GenericHttpPaymentProvider(PaymentProvider):
    """
    Adaptador HTTP genérico.

    Ele já resolve autenticação comum, chamadas HTTPS, metadata, redirects e
    assinatura HMAC de webhook. O JSON exato de cada PSP varia. Se o seu PSP
    não aceitar o contrato normalizado abaixo, altere somente _payload() e os
    mapeamentos de resposta/webhook ou crie um novo provider baseado nesta classe.
    """

    name = "generic_http"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._oauth_token: str | None = None
        self._oauth_expires_at = 0.0
        if not settings.psp_base_url.startswith("https://"):
            raise ValueError("PSP_BASE_URL deve usar HTTPS no provider generic_http.")

    async def _auth_headers(self) -> dict[str, str]:
        mode = self.settings.psp_auth_mode
        if mode == "none":
            return {}
        if mode == "api_key":
            if not self.settings.psp_api_key:
                raise RuntimeError("PSP_API_KEY não configurada.")
            return {self.settings.psp_api_key_header: self.settings.psp_api_key}
        if mode == "bearer":
            if not self.settings.psp_bearer_token:
                raise RuntimeError("PSP_BEARER_TOKEN não configurado.")
            return {"Authorization": f"Bearer {self.settings.psp_bearer_token}"}
        if mode == "oauth_client_credentials":
            token = await self._oauth_client_credentials()
            return {"Authorization": f"Bearer {token}"}
        raise RuntimeError(f"PSP_AUTH_MODE não suportado: {mode}")

    async def _oauth_client_credentials(self) -> str:
        now = time.time()
        if self._oauth_token and self._oauth_expires_at > now + 30:
            return self._oauth_token
        if not self.settings.psp_oauth_token_url.startswith("https://"):
            raise RuntimeError("PSP_OAUTH_TOKEN_URL precisa usar HTTPS.")
        if not self.settings.psp_client_id or not self.settings.psp_client_secret:
            raise RuntimeError("PSP_CLIENT_ID/PSP_CLIENT_SECRET não configurados.")
        data = {"grant_type": "client_credentials"}
        if self.settings.psp_oauth_scope:
            data["scope"] = self.settings.psp_oauth_scope
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                self.settings.psp_oauth_token_url,
                data=data,
                auth=(self.settings.psp_client_id, self.settings.psp_client_secret),
            )
            response.raise_for_status()
            payload = response.json()
        self._oauth_token = payload["access_token"]
        self._oauth_expires_at = now + int(payload.get("expires_in", 300))
        return self._oauth_token

    def _payload(self, request: PaymentStartRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "external_reference": request.donation_id,
            "amount_cents": request.amount_cents,
            "currency": request.currency,
            "description": "Contribuição ao Fundo Centenário",
            "metadata": request.metadata,
            "return_url": request.return_url,
            "webhook_url": request.webhook_url,
        }
        if self.settings.psp_send_customer_data:
            payload["customer"] = {
                "name": request.donor_name,
                "email": request.donor_email,
                "cpf": request.donor_cpf,
            }
        return payload

    async def _post(self, path: str, request: PaymentStartRequest) -> PaymentStartResult:
        headers = {"Accept": "application/json", "Content-Type": "application/json", **(await self._auth_headers())}
        url = self.settings.psp_base_url + path
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=headers, json=self._payload(request))
            response.raise_for_status()
            data = response.json()
        return PaymentStartResult(
            provider_payment_id=str(_get_path(data, self.settings.psp_field_payment_id)),
            status=str(_get_path(data, self.settings.psp_field_status, "pending")),
            pix_copy_paste=_get_path(data, self.settings.psp_field_pix_copy_paste),
            pix_qr_base64=_get_path(data, self.settings.psp_field_pix_qr_base64),
            redirect_url=_get_path(data, self.settings.psp_field_redirect_url),
            expires_at=_get_path(data, self.settings.psp_field_expires_at),
        )

    async def create_pix(self, request: PaymentStartRequest) -> PaymentStartResult:
        return await self._post(self.settings.psp_pix_create_path, request)

    async def create_pix_automatic(self, request: PaymentStartRequest) -> PaymentStartResult:
        return await self._post(self.settings.psp_pix_automatic_create_path, request)

    async def create_card_checkout(self, request: PaymentStartRequest) -> PaymentStartResult:
        return await self._post(self.settings.psp_card_checkout_path, request)

    def _verify_hmac(self, body: bytes, headers: dict[str, str]) -> None:
        secret = self.settings.psp_webhook_secret
        if not secret:
            raise RuntimeError("PSP_WEBHOOK_SECRET não configurado.")
        header_name = self.settings.psp_webhook_signature_header.lower()
        supplied = headers.get(header_name, "")
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied.removeprefix("sha256="), expected):
            raise PermissionError("Assinatura do webhook inválida.")

    def _normalize_status(self, raw: str) -> str:
        lowered = raw.strip().lower()
        if lowered in {value.lower() for value in self.settings.psp_paid_statuses}:
            return "paid"
        if lowered in {value.lower() for value in self.settings.psp_authorized_statuses}:
            return "authorized"
        if lowered in {value.lower() for value in self.settings.psp_failed_statuses}:
            return "failed"
        return "pending"

    async def parse_webhook(self, body: bytes, headers: dict[str, str]) -> ProviderWebhookEvent:
        self._verify_hmac(body, headers)
        payload = json.loads(body.decode("utf-8"))
        raw_status = str(_get_path(payload, self.settings.psp_webhook_field_status, "pending"))
        donation_id = str(_get_path(payload, self.settings.psp_webhook_field_donation_id, ""))
        provider_payment_id = str(_get_path(payload, self.settings.psp_webhook_field_payment_id, ""))
        if not donation_id or not provider_payment_id:
            raise ValueError("Webhook sem donation_id ou payment_id. Mapeie os campos em .env ou no provider.")
        return ProviderWebhookEvent(
            event_id=str(_get_path(payload, self.settings.psp_webhook_field_event_id, provider_payment_id + ":" + raw_status)),
            provider_payment_id=provider_payment_id,
            donation_id=donation_id,
            status=self._normalize_status(raw_status),
            amount_cents=_get_path(payload, self.settings.psp_webhook_field_amount_cents),
            status_token_hash=_get_path(payload, self.settings.psp_webhook_field_token_hash),
            program=_get_path(payload, self.settings.psp_webhook_field_program),
            method=_get_path(payload, self.settings.psp_webhook_field_method),
            raw_status=raw_status,
            payload=payload,
        )
