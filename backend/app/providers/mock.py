from __future__ import annotations

import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .base import PaymentProvider, PaymentStartRequest, PaymentStartResult, ProviderWebhookEvent
from ..config import Settings
from ..models import PaymentMethod


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def _crc16_ccitt(payload: str) -> str:
    crc = 0xFFFF
    polynomial = 0x1021
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ polynomial) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _clean_ascii(value: str, max_length: int) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(normalized.upper().split())[:max_length]


def build_static_pix(key: str, merchant_name: str, merchant_city: str, amount_cents: int, txid: str) -> str:
    gui = _tlv("00", "BR.GOV.BCB.PIX")
    merchant_account = _tlv("26", gui + _tlv("01", key))
    amount = f"{amount_cents / 100:.2f}"
    additional = _tlv("62", _tlv("05", txid[:25] or "***"))
    payload = (
        _tlv("00", "01")
        + merchant_account
        + _tlv("52", "0000")
        + _tlv("53", "986")
        + _tlv("54", amount)
        + _tlv("58", "BR")
        + _tlv("59", _clean_ascii(merchant_name, 25))
        + _tlv("60", _clean_ascii(merchant_city, 15))
        + additional
        + "6304"
    )
    return payload + _crc16_ccitt(payload)


@dataclass(slots=True)
class MockEntry:
    request: PaymentStartRequest
    provider_payment_id: str
    mock_key: str


class MockPaymentProvider(PaymentProvider):
    name = "mock"
    supported_methods = tuple(PaymentMethod)

    def __init__(self, settings: Settings):
        self.settings = settings
        self.entries: dict[str, MockEntry] = {}

    def _new_entry(self, request: PaymentStartRequest) -> MockEntry:
        provider_payment_id = f"mock_{secrets.token_hex(10)}"
        entry = MockEntry(request=request, provider_payment_id=provider_payment_id, mock_key=secrets.token_urlsafe(18))
        self.entries[provider_payment_id] = entry
        return entry

    async def create_pix(self, request: PaymentStartRequest) -> PaymentStartResult:
        entry = self._new_entry(request)
        txid = request.donation_id.replace("-", "")[:25]
        payload = build_static_pix(
            self.settings.mock_pix_key,
            self.settings.mock_merchant_name,
            self.settings.mock_merchant_city,
            request.amount_cents,
            txid,
        )
        expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        return PaymentStartResult(
            provider_payment_id=entry.provider_payment_id,
            pix_copy_paste=payload,
            expires_at=expires,
            mock_confirm_url=f"/api/mock/{entry.provider_payment_id}/confirm?key={quote(entry.mock_key)}",
        )

    async def create_pix_automatic(self, request: PaymentStartRequest) -> PaymentStartResult:
        entry = self._new_entry(request)
        return PaymentStartResult(
            provider_payment_id=entry.provider_payment_id,
            status="pending_authorization",
            redirect_url=f"{self.settings.public_base_url}/mock-psp/pix-automatico/{entry.provider_payment_id}?key={quote(entry.mock_key)}",
        )

    async def create_card_checkout(self, request: PaymentStartRequest) -> PaymentStartResult:
        entry = self._new_entry(request)
        return PaymentStartResult(
            provider_payment_id=entry.provider_payment_id,
            redirect_url=f"{self.settings.public_base_url}/mock-psp/card/{entry.provider_payment_id}?key={quote(entry.mock_key)}",
        )

    async def parse_webhook(self, body: bytes, headers: dict[str, str]) -> ProviderWebhookEvent:
        raise RuntimeError("O provedor mock usa o endpoint /api/mock/* para simular confirmações.")

    async def create_recurring_checkout(self, request: PaymentStartRequest) -> PaymentStartResult:
        return await self.create_card_checkout(request)

    def confirm(self, provider_payment_id: str, key: str) -> ProviderWebhookEvent:
        entry = self.entries.get(provider_payment_id)
        if not entry or not secrets.compare_digest(entry.mock_key, key):
            raise KeyError("Pagamento mock não encontrado ou chave inválida.")
        request = entry.request
        return ProviderWebhookEvent(
            event_id=f"mock_evt_{secrets.token_hex(8)}",
            provider_payment_id=provider_payment_id,
            donation_id=request.donation_id,
            status="paid",
            amount_cents=request.amount_cents,
            status_token_hash=request.status_token_hash,
            program=request.program.value,
            method=request.method.value,
            raw_status="paid",
            payload={"mock": True},
        )

    def get_entry(self, provider_payment_id: str, key: str) -> MockEntry:
        entry = self.entries.get(provider_payment_id)
        if not entry or not secrets.compare_digest(entry.mock_key, key):
            raise KeyError("Pagamento mock não encontrado ou chave inválida.")
        return entry
