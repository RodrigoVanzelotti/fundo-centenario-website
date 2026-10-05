from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from .security import normalize_cpf, validate_cpf


class DonationProgram(str, Enum):
    PROJECTS = "edital-projetos"
    SCHOLARSHIPS = "bolsas-permanencia"
    MENTORING = "mentoria"
    ALUMNI = "masterclasses-alumni"
    GENERAL = "geral"


PROGRAM_LABELS: dict[DonationProgram, str] = {
    DonationProgram.PROJECTS: "Edital de projetos",
    DonationProgram.SCHOLARSHIPS: "Programa de Bolsas de Permanência",
    DonationProgram.MENTORING: "Programa de Mentoria",
    DonationProgram.ALUMNI: "Masterclasses e conteúdo Alumni",
    DonationProgram.GENERAL: "Contribuição geral",
}


class PaymentMethod(str, Enum):
    PIX = "pix"
    PIX_AUTOMATIC = "pix_automatico"
    CARD = "card"
    CARD_RECURRING = "card_recurring"


class DonorQuestionnaire(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    email: EmailStr
    cpf: str
    communication_opt_in: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 3:
            raise ValueError("Informe seu nome completo.")
        return cleaned

    @field_validator("cpf")
    @classmethod
    def clean_cpf(cls, value: str) -> str:
        normalized = normalize_cpf(value)
        if not validate_cpf(normalized):
            raise ValueError("CPF inválido.")
        return normalized


class DonationIntentRequest(BaseModel):
    donor: DonorQuestionnaire
    program: DonationProgram
    method: PaymentMethod
    amount_cents: int = Field(strict=True, ge=100, le=100_000_000)


class DonationFinalizeRequest(BaseModel):
    donor: DonorQuestionnaire


class DonationOptionsResponse(BaseModel):
    methods: list[PaymentMethod]


class DonationIntentResponse(BaseModel):
    donation_id: str
    status_token: str
    method: PaymentMethod
    status: str
    amount_cents: int
    program: DonationProgram
    program_label: str
    pix_copy_paste: str | None = None
    pix_qr_base64: str | None = None
    redirect_url: str | None = None
    expires_at: str | None = None
    mock_confirm_url: str | None = None


class DonationStatusResponse(BaseModel):
    donation_id: str
    status: str
    method: PaymentMethod
    amount_cents: int
    program: DonationProgram
    program_label: str
    confirmed_at: str | None = None
    persisted: bool = False
    message: str


class PendingDonation(BaseModel):
    donation_id: str
    status_token_hash: str
    donor: DonorQuestionnaire
    program: DonationProgram
    method: PaymentMethod
    amount_cents: int
    provider_payment_id: str
    provider_status: str = "pending"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at_epoch: float


class PaymentConfirmation(BaseModel):
    donation_id: str
    provider_payment_id: str
    status_token_hash: str
    method: PaymentMethod
    program: DonationProgram
    amount_cents: int
    confirmed_at: str
    provider_event_id: str | None = None
    provider_subscription_id: str | None = None


class ConfirmedDonationRecord(BaseModel):
    donation_id: str
    provider_payment_id: str
    method: PaymentMethod
    program: DonationProgram
    program_label: str
    amount_cents: int
    currency: Literal["BRL"] = "BRL"
    donor_name: str
    donor_email: str
    donor_cpf: str
    communication_opt_in: bool
    created_at: str
    confirmed_at: str
