from __future__ import annotations

import logging
import time
import threading
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status

from .config import Settings
from .emailer import DonationEmailSender
from .models import (
    ConfirmedDonationRecord,
    DonationFinalizeRequest,
    DonationIntentRequest,
    DonationIntentResponse,
    DonationProgram,
    DonationStatusResponse,
    PROGRAM_LABELS,
    PaymentConfirmation,
    PaymentMethod,
    PendingDonation,
)
from .providers.base import PaymentProvider, PaymentStartRequest, ProviderWebhookEvent
from .providers.mock import MockPaymentProvider
from .security import constant_time_equal, hash_token, new_status_token
from .qr_utils import qr_png_base64
from .storage import ConfirmedDonationStore, JsonlStore, PaymentConfirmationStore, PendingDonationStore


class PaymentService:
    def __init__(self, settings: Settings, provider: PaymentProvider):
        if settings.data_dir.resolve().is_relative_to(settings.frontend_dir.resolve()):
            raise ValueError("DATA_DIR deve permanecer fora da pasta pública do frontend.")
        self.settings = settings
        self.provider = provider
        self.pending = PendingDonationStore()
        self.payment_confirmations = PaymentConfirmationStore(settings.data_dir / "payment_confirmations.jsonl")
        self.confirmed_donations = ConfirmedDonationStore(settings.data_dir / "confirmed_donations.jsonl")
        self.recurring_payments = JsonlStore(settings.data_dir / "recurring_payments.jsonl", "provider_payment_id")
        self.email_sender = DonationEmailSender(settings)
        self.email_outbox = JsonlStore(settings.data_dir / "thank_you_outbox.jsonl", "provider_payment_id")
        self.email_sent = JsonlStore(settings.data_dir / "thank_you_sent.jsonl", "provider_payment_id")
        self._email_lock = threading.Lock()
        # ponytail: local files and one process; use database transactions before adding workers.
        self._event_lock = threading.Lock()

    async def create_intent(self, payload: DonationIntentRequest) -> DonationIntentResponse:
        if payload.method not in self.provider.supported_methods:
            raise HTTPException(status_code=422, detail="Forma de contribuição indisponível.")
        donation_id = str(uuid.uuid4())
        token = new_status_token()
        token_hash = hash_token(token)

        return_url = f"{self.settings.public_base_url}/como-apoiar/?donation_id={donation_id}"
        webhook_url = f"{self.settings.public_base_url}/api/webhooks/{self.provider.name}"
        start_request = PaymentStartRequest(
            donation_id=donation_id,
            amount_cents=payload.amount_cents,
            currency="BRL",
            method=payload.method,
            program=payload.program,
            donor_name=payload.donor.name,
            donor_email=str(payload.donor.email),
            donor_cpf=payload.donor.cpf,
            status_token_hash=token_hash,
            return_url=return_url,
            webhook_url=webhook_url,
        )

        try:
            if payload.method == PaymentMethod.PIX:
                result = await self.provider.create_pix(start_request)
            elif payload.method == PaymentMethod.PIX_AUTOMATIC:
                result = await self.provider.create_pix_automatic(start_request)
            elif payload.method == PaymentMethod.CARD_RECURRING:
                result = await self.provider.create_recurring_checkout(start_request)
            else:
                result = await self.provider.create_card_checkout(start_request)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Não foi possível iniciar o pagamento no PSP. Tente novamente mais tarde.") from exc

        if result.pix_copy_paste and not result.pix_qr_base64:
            result.pix_qr_base64 = qr_png_base64(result.pix_copy_paste)

        pending = PendingDonation(
            donation_id=donation_id,
            status_token_hash=token_hash,
            donor=payload.donor,
            program=payload.program,
            method=payload.method,
            amount_cents=payload.amount_cents,
            provider_payment_id=result.provider_payment_id,
            provider_status=result.status,
            expires_at_epoch=time.time() + self.settings.pending_ttl_seconds,
        )
        self.pending.put(pending)

        return DonationIntentResponse(
            donation_id=donation_id,
            status_token=token,
            method=payload.method,
            status=result.status,
            amount_cents=payload.amount_cents,
            program=payload.program,
            program_label=PROGRAM_LABELS[payload.program],
            pix_copy_paste=result.pix_copy_paste,
            pix_qr_base64=result.pix_qr_base64,
            redirect_url=result.redirect_url,
            expires_at=result.expires_at,
            mock_confirm_url=result.mock_confirm_url,
        )

    def _verify_access(self, donation_id: str, token: str) -> tuple[PendingDonation | None, PaymentConfirmation | None]:
        token_hash = hash_token(token)
        pending = self.pending.get(donation_id)
        if pending and constant_time_equal(token_hash, pending.status_token_hash):
            return pending, self.payment_confirmations.get_model(donation_id)

        confirmation = self.payment_confirmations.get_model(donation_id)
        if confirmation and constant_time_equal(token_hash, confirmation.status_token_hash):
            return None, confirmation

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doação não encontrada.")

    def get_status(self, donation_id: str, token: str) -> DonationStatusResponse:
        pending, confirmation = self._verify_access(donation_id, token)

        if confirmation:
            persisted = self.confirmed_donations.contains(donation_id)
            return DonationStatusResponse(
                donation_id=donation_id,
                status="paid",
                method=confirmation.method,
                amount_cents=confirmation.amount_cents,
                program=confirmation.program,
                program_label=PROGRAM_LABELS[confirmation.program],
                confirmed_at=confirmation.confirmed_at,
                persisted=persisted,
                message="Pagamento confirmado. Muito obrigado por apoiar o Fundo Centenário!",
            )

        assert pending is not None
        status_value = pending.provider_status
        if status_value == "authorized":
            message = "Autorização concluída. A contribuição será registrada quando o primeiro pagamento for confirmado."
        elif status_value == "failed":
            message = "O pagamento não foi concluído. Você pode iniciar uma nova tentativa."
        else:
            message = "Aguardando confirmação do pagamento pelo banco ou PSP."

        return DonationStatusResponse(
            donation_id=donation_id,
            status=status_value,
            method=pending.method,
            amount_cents=pending.amount_cents,
            program=pending.program,
            program_label=PROGRAM_LABELS[pending.program],
            persisted=False,
            message=message,
        )

    async def process_webhook(self, body: bytes, headers: dict[str, str]) -> ProviderWebhookEvent | None:
        try:
            event = await self.provider.parse_webhook(body, headers)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook inválido.") from exc
        if event is not None:
            try:
                self.apply_provider_event(event)
            except (ValueError, TypeError) as exc:
                raise HTTPException(status_code=400, detail="Webhook incompatível com a contribuição.") from exc
        return event

    def apply_provider_event(self, event: ProviderWebhookEvent) -> None:
        with self._event_lock:
            pending = self.pending.get(event.donation_id) or self.pending.get_by_provider_id(event.provider_payment_id)
            donation_id = event.donation_id or (pending.donation_id if pending else "")
            existing = self.payment_confirmations.get_model(donation_id)
            known = pending or existing
            if known:
                if donation_id != known.donation_id:
                    raise ValueError("Referência de pagamento incompatível.")
                if event.status_token_hash and not constant_time_equal(event.status_token_hash, known.status_token_hash):
                    raise ValueError("Token de pagamento incompatível.")
                if event.method and event.method != known.method.value:
                    raise ValueError("Método de pagamento incompatível.")
                if event.program and event.program != known.program.value:
                    raise ValueError("Programa incompatível.")
                if not event.provider_subscription_id and event.provider_payment_id != known.provider_payment_id:
                    # A completed subscription Checkout is only an enrollment status update.
                    if not existing or event.status == "paid":
                        raise ValueError("Identificador de pagamento incompatível.")
                if existing and existing.provider_subscription_id and event.provider_subscription_id:
                    if existing.provider_subscription_id != event.provider_subscription_id:
                        raise ValueError("Assinatura incompatível.")
            if event.status != "paid":
                if pending:
                    self.pending.update_status(pending.donation_id, event.status)
                return
            token_hash = event.status_token_hash or (known.status_token_hash if known else None)
            program_raw = event.program or (known.program.value if known else None)
            method_raw = event.method or (known.method.value if known else None)
            amount_cents = event.amount_cents if event.amount_cents is not None else (known.amount_cents if known else None)
            if not donation_id or not token_hash or not program_raw or not method_raw:
                raise ValueError("Confirmação sem metadata suficiente.")
            if type(amount_cents) is not int or not 100 <= amount_cents <= 100_000_000:
                raise ValueError("Valor de pagamento inválido.")
            if known and amount_cents != known.amount_cents:
                raise ValueError("Valor do pagamento incompatível.")
            if event.currency and event.currency.upper() != "BRL":
                raise ValueError("Moeda de pagamento incompatível.")
            confirmation = PaymentConfirmation(
                donation_id=donation_id, provider_payment_id=event.provider_payment_id,
                status_token_hash=token_hash, method=PaymentMethod(method_raw),
                program=DonationProgram(program_raw), amount_cents=amount_cents,
                confirmed_at=datetime.now(timezone.utc).isoformat(), provider_event_id=event.event_id,
                provider_subscription_id=event.provider_subscription_id,
            )
            # Durable object IDs deduplicate redeliveries and distinct events for the same invoice.
            # Do not mark an event processed before both writes succeed: Stripe must be able to retry.
            self.payment_confirmations.append_once(confirmation.model_dump())
            if confirmation.provider_subscription_id:
                self.recurring_payments.append_once(confirmation.model_dump())
            self._queue_thank_you(confirmation)
            if pending:
                self._persist_questionnaire(pending, existing or confirmation)

    def _persist_questionnaire(self, pending: PendingDonation, confirmation: PaymentConfirmation) -> bool:
        record = ConfirmedDonationRecord(
            donation_id=pending.donation_id,
            provider_payment_id=confirmation.provider_payment_id,
            method=confirmation.method,
            program=confirmation.program,
            program_label=PROGRAM_LABELS[confirmation.program],
            amount_cents=confirmation.amount_cents,
            donor_name=pending.donor.name,
            donor_email=str(pending.donor.email),
            donor_cpf=pending.donor.cpf,
            communication_opt_in=pending.donor.communication_opt_in,
            created_at=pending.created_at,
            confirmed_at=confirmation.confirmed_at,
        )
        written = self.confirmed_donations.append_once(record.model_dump())
        self.pending.remove(pending.donation_id)
        return written

    def _queue_thank_you(self, confirmation: PaymentConfirmation) -> None:
        if self.settings.email_enabled:
            self.email_outbox.append_once({
                "donation_id": confirmation.donation_id,
                "provider_payment_id": confirmation.provider_payment_id,
            })

    def process_pending_emails(self) -> None:
        if not self.settings.email_enabled:
            return
        # ponytail: one worker scans the local outbox; use a transactional queue when volume grows.
        with self._email_lock:
            for job in self.email_outbox.records():
                payment_id = job["provider_payment_id"]
                if self.email_sent.contains(payment_id):
                    continue
                confirmation = self.payment_confirmations.get_model(job["donation_id"])
                donor = self.confirmed_donations.get_model(job["donation_id"])
                if not confirmation or not donor:
                    continue
                payment = confirmation.model_dump() if confirmation.provider_payment_id == payment_id else self.recurring_payments.get(payment_id)
                if not payment or payment["donation_id"] != donor.donation_id:
                    continue
                try:
                    # ponytail: SMTP acceptance and the local marker are not atomic; provider idempotency closes this gap.
                    self.email_sender.send(donor, payment["amount_cents"], payment_id)
                    self.email_sent.append_once({
                        **job, "sent_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception as exc:
                    # SMTP errors can echo recipients and credentials. Log only the exception class.
                    logging.getLogger(__name__).warning("Agradecimento pendente: falha de envio ou registro (%s).", type(exc).__name__)

    def finalize_after_restart(self, donation_id: str, token: str, payload: DonationFinalizeRequest) -> DonationStatusResponse:
        confirmation = self.payment_confirmations.get_model(donation_id)
        if not confirmation:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="O pagamento ainda não foi confirmado.")
        if not constant_time_equal(hash_token(token), confirmation.status_token_hash):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doação não encontrada.")

        if not self.confirmed_donations.contains(donation_id):
            record = ConfirmedDonationRecord(
                donation_id=donation_id,
                provider_payment_id=confirmation.provider_payment_id,
                method=confirmation.method,
                program=confirmation.program,
                program_label=PROGRAM_LABELS[confirmation.program],
                amount_cents=confirmation.amount_cents,
                donor_name=payload.donor.name,
                donor_email=str(payload.donor.email),
                donor_cpf=payload.donor.cpf,
                communication_opt_in=payload.donor.communication_opt_in,
                created_at=confirmation.confirmed_at,
                confirmed_at=confirmation.confirmed_at,
            )
            self.confirmed_donations.append_once(record.model_dump())

        self._queue_thank_you(confirmation)
        return self.get_status(donation_id, token)

    def confirm_mock(self, provider_payment_id: str, key: str) -> tuple[ProviderWebhookEvent, str]:
        if not isinstance(self.provider, MockPaymentProvider):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mock PSP não habilitado.")
        try:
            entry = self.provider.get_entry(provider_payment_id, key)
            event = self.provider.confirm(provider_payment_id, key)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        self.apply_provider_event(event)
        return event, entry.request.return_url
