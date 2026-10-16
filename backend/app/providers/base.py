from __future__ import annotations

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
    status_token_hash: str
    return_url: str

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
    redirect_url: str | None = None
    expires_at: str | None = None


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
