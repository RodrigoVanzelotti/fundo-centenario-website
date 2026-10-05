from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..models import DonationProgram, PaymentMethod


@dataclass(slots=True)
class PaymentStartRequest:
    donation_id: str
    amount_cents: int
    currency: str
    method: PaymentMethod
    program: DonationProgram
    donor_name: str
    donor_email: str
    donor_cpf: str
    status_token_hash: str
    return_url: str
    webhook_url: str

    @property
    def metadata(self) -> dict[str, str]:
        return {
            "donation_id": self.donation_id,
            "status_token_hash": self.status_token_hash,
            "program": self.program.value,
            "method": self.method.value,
        }


@dataclass(slots=True)
class PaymentStartResult:
    provider_payment_id: str
    status: str = "pending"
    pix_copy_paste: str | None = None
    pix_qr_base64: str | None = None
    redirect_url: str | None = None
    expires_at: str | None = None
    mock_confirm_url: str | None = None


@dataclass(slots=True)
class ProviderWebhookEvent:
    event_id: str
    provider_payment_id: str
    donation_id: str
    status: str
    amount_cents: int | None = None
    status_token_hash: str | None = None
    program: str | None = None
    method: str | None = None
    raw_status: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    provider_subscription_id: str | None = None
    currency: str | None = None


class PaymentProvider(ABC):
    name: str
    supported_methods = (PaymentMethod.PIX, PaymentMethod.PIX_AUTOMATIC, PaymentMethod.CARD)

    async def create_recurring_checkout(self, request: PaymentStartRequest) -> PaymentStartResult:
        raise ValueError("Contribuição mensal no cartão indisponível neste provedor.")

    @abstractmethod
    async def create_pix(self, request: PaymentStartRequest) -> PaymentStartResult:
        raise NotImplementedError

    @abstractmethod
    async def create_pix_automatic(self, request: PaymentStartRequest) -> PaymentStartResult:
        raise NotImplementedError

    @abstractmethod
    async def create_card_checkout(self, request: PaymentStartRequest) -> PaymentStartResult:
        raise NotImplementedError

    @abstractmethod
    async def parse_webhook(self, body: bytes, headers: dict[str, str]) -> ProviderWebhookEvent | None:
        raise NotImplementedError
