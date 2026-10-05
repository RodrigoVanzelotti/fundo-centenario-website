from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from ..config import Settings
from ..models import DonationProgram, PaymentMethod
from .base import PaymentProvider, PaymentStartRequest, PaymentStartResult, ProviderWebhookEvent


class StripePaymentProvider(PaymentProvider):
    name = "stripe"

    def __init__(self, settings: Settings):
        self.settings = settings
        mode = "live" if settings.stripe_live_mode else "test"
        if not settings.stripe_secret_key.startswith((f"sk_{mode}_", f"rk_{mode}_")):
            raise ValueError("Configure uma chave Stripe correspondente ao STRIPE_LIVE_MODE.")
        if not settings.stripe_webhook_secret.startswith("whsec_"):
            raise ValueError("Configure STRIPE_WEBHOOK_SECRET para este endpoint.")
        if (settings.app_env == "production" or settings.stripe_live_mode) and urlsplit(settings.public_base_url).scheme != "https":
            raise ValueError("PUBLIC_BASE_URL deve usar HTTPS em produção.")
        self.supported_methods = (PaymentMethod.PIX, PaymentMethod.CARD, PaymentMethod.CARD_RECURRING)

    async def create_pix(self, request: PaymentStartRequest) -> PaymentStartResult:
        return await self._create_checkout(request, "pix", recurring=False)

    async def create_card_checkout(self, request: PaymentStartRequest) -> PaymentStartResult:
        return await self._create_checkout(request, "card", recurring=False)

    async def create_recurring_checkout(self, request: PaymentStartRequest) -> PaymentStartResult:
        return await self._create_checkout(request, "card", recurring=True)

    async def create_pix_automatic(self, request: PaymentStartRequest) -> PaymentStartResult:
        raise ValueError("Este adapter usa cartão para a contribuição mensal.")

    async def _create_checkout(self, request: PaymentStartRequest, method: str, *, recurring: bool) -> PaymentStartResult:
        metadata = {**request.metadata, "application": "fundo-centenario", "amount_cents": str(request.amount_cents)}
        data = {
            "mode": "subscription" if recurring else "payment",
            "payment_method_types[0]": method,
            "client_reference_id": request.donation_id,
            "success_url": request.return_url,
            "cancel_url": request.return_url.split("?", 1)[0] + "#contribuir",
            "locale": "pt-BR",
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": "brl",
            "line_items[0][price_data][unit_amount]": str(request.amount_cents),
            "line_items[0][price_data][product_data][name]": "Contribuição ao Fundo Centenário",
        }
        for key, value in metadata.items():
            data[f"metadata[{key}]"] = value
            if recurring:
                data[f"subscription_data[metadata][{key}]"] = value
        if recurring:
            data["line_items[0][price_data][recurring][interval]"] = "month"
            data["payment_method_collection"] = "always"
        # Donor PII stays out of URLs, metadata and API requests; Checkout collects what Stripe needs.
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                headers={
                    "Authorization": f"Bearer {self.settings.stripe_secret_key}",
                    "Stripe-Version": self.settings.stripe_api_version,
                    "Idempotency-Key": f"donation-{request.donation_id}",
                },
                data=data,
            )
            if not response.is_success:
                # Stripe errors can echo parameters or PII. Never send their body to the browser.
                raise RuntimeError("Não foi possível criar o checkout seguro.")
            checkout = response.json()
        redirect = urlsplit(checkout.get("url") or "")
        if redirect.scheme != "https" or redirect.netloc != "checkout.stripe.com":
            raise ValueError("URL de checkout inválida.")
        if not str(checkout.get("id", "")).startswith("cs_"):
            raise ValueError("Referência de checkout inválida.")
        return PaymentStartResult(
            provider_payment_id=checkout["id"],
            redirect_url=checkout["url"],
            expires_at=datetime.fromtimestamp(checkout["expires_at"], timezone.utc).isoformat(),
        )

    def _verify_signature(self, body: bytes, header: str) -> None:
        # Stripe's documented signature: HMAC-SHA256(timestamp + '.' + raw body), v1 only.
        parts = [part.strip().split("=", 1) for part in header.split(",")]
        timestamps = [pair[1] for pair in parts if len(pair) == 2 and pair[0] == "t"]
        signatures = [pair[1] for pair in parts if len(pair) == 2 and pair[0] == "v1"]
        if len(timestamps) != 1 or not timestamps[0].isdigit():
            raise PermissionError("Assinatura do webhook inválida.")
        if abs(time.time() - int(timestamps[0])) > 300:
            raise PermissionError("Assinatura do webhook expirada.")
        expected = hmac.new(
            self.settings.stripe_webhook_secret.encode(), timestamps[0].encode() + b"." + body, hashlib.sha256,
        ).hexdigest()
        if not any(hmac.compare_digest(expected, signature) for signature in signatures):
            raise PermissionError("Assinatura do webhook inválida.")

    async def parse_webhook(self, body: bytes, headers: dict[str, str]) -> ProviderWebhookEvent | None:
        self._verify_signature(body, headers.get("stripe-signature", ""))
        event = json.loads(body)
        if event.get("livemode") is not self.settings.stripe_live_mode:
            raise PermissionError("Modo do webhook incompatível com esta aplicação.")
        event_type = event.get("type")
        relevant = {
            "checkout.session.completed", "checkout.session.async_payment_succeeded",
            "checkout.session.async_payment_failed", "checkout.session.expired",
            "invoice.payment_succeeded", "invoice.payment_failed", "customer.subscription.deleted",
        }
        if event_type not in relevant or event.get("account"):
            return None
        if event.get("api_version") != self.settings.stripe_api_version:
            raise ValueError("Versão do webhook incompatível; configure a versão do endpoint Stripe.")
        obj = event["data"]["object"]
        prefix = "in_" if event_type.startswith("invoice.") else "sub_" if event_type.startswith("customer.") else "cs_"
        if not str(obj.get("id", "")).startswith(prefix) or not str(event.get("id", "")).startswith("evt_"):
            raise ValueError("Identificador de evento inválido.")
        subscription_id = None
        if event_type.startswith("invoice."):
            details = (obj.get("parent") or {}).get("subscription_details") or {}
            metadata = details.get("metadata") or {}
            subscription_id = details.get("subscription")
        else:
            metadata = obj.get("metadata") or {}
        if metadata.get("application") != "fundo-centenario":
            return None
        if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", metadata.get("donation_id", "")):
            raise ValueError("Referência de contribuição inválida.")
        if not re.fullmatch(r"[0-9a-f]{64}", metadata.get("status_token_hash", "")):
            raise ValueError("Metadata de autenticação inválida.")
        method = PaymentMethod(metadata["method"])
        program = DonationProgram(metadata["program"])
        expected_amount = int(metadata["amount_cents"])
        if not 100 <= expected_amount <= 100_000_000:
            raise ValueError("Valor de contribuição inválido.")
        status = "pending"
        amount = None
        currency = obj.get("currency")
        if event_type.startswith("invoice."):
            if method != PaymentMethod.CARD_RECURRING:
                raise ValueError("Método incompatível com uma fatura recorrente.")
            if not isinstance(subscription_id, str) or not subscription_id.startswith("sub_"):
                raise ValueError("Referência de assinatura inválida.")
            if event_type == "invoice.payment_succeeded":
                # invoice.paid also allows manual out-of-band marking; accept payment_succeeded only.
                if obj.get("status") != "paid" or obj.get("amount_remaining") != 0:
                    raise ValueError("Fatura sem pagamento confirmado.")
                amount = obj.get("amount_paid")
                status = "paid"
            else:
                status = "failed"
        elif event_type == "customer.subscription.deleted":
            subscription_id = obj["id"]
            status = "failed"
        elif obj.get("mode") == "subscription":
            if method != PaymentMethod.CARD_RECURRING:
                raise ValueError("Método incompatível com uma assinatura.")
            # Checkout completion proves enrollment, not settlement of a subscription invoice.
            status = "failed" if event_type.endswith(("failed", "expired")) else "authorized"
        elif obj.get("mode") == "payment":
            if method not in (PaymentMethod.PIX, PaymentMethod.CARD):
                raise ValueError("Método incompatível com pagamento pontual.")
            if event_type.endswith(("completed", "async_payment_succeeded")) and obj.get("payment_status") == "paid":
                amount = obj.get("amount_total")
                status = "paid"
            elif event_type.endswith(("failed", "expired")):
                status = "failed"
        else:
            raise ValueError("Modo de checkout inválido.")
        if status == "paid" and (type(amount) is not int or amount != expected_amount or currency != "brl"):
            raise ValueError("Valor ou moeda do pagamento não corresponde à contribuição.")
        return ProviderWebhookEvent(
            event_id=event["id"], provider_payment_id=obj["id"], donation_id=metadata["donation_id"],
            status=status, amount_cents=amount, status_token_hash=metadata["status_token_hash"],
            program=program.value, method=method.value, raw_status=event_type,
            provider_subscription_id=subscription_id, currency=currency,
        )
