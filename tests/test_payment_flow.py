import asyncio
from pathlib import Path

from backend.app.config import Settings
from backend.app.models import DonationIntentRequest, DonorQuestionnaire, DonationProgram, PaymentMethod
from backend.app.providers.mock import MockPaymentProvider
from backend.app.services import PaymentService


def make_settings(tmp_path: Path) -> Settings:
    settings = Settings()
    settings.payment_provider = "mock"
    settings.data_dir = tmp_path
    settings.public_base_url = "http://testserver"
    settings.enable_mock_psp = True
    settings.pending_ttl_seconds = 3600
    return settings


def test_questionnaire_is_only_persisted_after_confirmation(tmp_path):
    settings = make_settings(tmp_path)
    provider = MockPaymentProvider(settings)
    service = PaymentService(settings, provider)

    payload = DonationIntentRequest(
        donor=DonorQuestionnaire(
            name="Maria da Silva",
            email="maria@example.com",
            cpf="52998224725",
            communication_opt_in=True,
        ),
        program=DonationProgram.PROJECTS,
        method=PaymentMethod.PIX,
        amount_cents=10000,
    )

    response = asyncio.run(service.create_intent(payload))
    confirmed_file = tmp_path / "confirmed_donations.jsonl"
    assert not confirmed_file.exists()

    pending = service.pending.get(response.donation_id)
    assert pending is not None
    entry = provider.entries[pending.provider_payment_id]
    event = provider.confirm(entry.provider_payment_id, entry.mock_key)
    service.apply_provider_event(event)

    assert confirmed_file.exists()
    contents = confirmed_file.read_text(encoding="utf-8")
    assert "Maria da Silva" in contents
    assert "52998224725" in contents

    status = service.get_status(response.donation_id, response.status_token)
    assert status.status == "paid"
    assert status.persisted is True


def test_recurring_and_card_use_hosted_redirects(tmp_path):
    settings = make_settings(tmp_path)
    provider = MockPaymentProvider(settings)
    service = PaymentService(settings, provider)

    for method in (PaymentMethod.PIX_AUTOMATIC, PaymentMethod.CARD):
        payload = DonationIntentRequest(
            donor=DonorQuestionnaire(
                name="João de Teste",
                email="joao@example.com",
                cpf="52998224725",
                communication_opt_in=False,
            ),
            program=DonationProgram.GENERAL,
            method=method,
            amount_cents=5000,
        )
        response = asyncio.run(service.create_intent(payload))
        assert response.redirect_url
        assert response.redirect_url.startswith("http://testserver/mock-psp/")
        assert not (tmp_path / "confirmed_donations.jsonl").exists()


def test_signed_webhook_rejects_invalid_signature_and_persists_once(tmp_path):
    import hashlib
    import hmac
    import json

    import pytest
    from fastapi import HTTPException
    from backend.app.providers.generic_http import GenericHttpPaymentProvider

    settings = make_settings(tmp_path)
    settings.psp_webhook_secret = "test-only-webhook-secret"
    settings.psp_base_url = "https://psp.example.com"
    service = PaymentService(settings, MockPaymentProvider(settings))
    payload = DonationIntentRequest(
        donor=DonorQuestionnaire(
            name="Test Donor", email="test@example.com", cpf="52998224725",
        ),
        program=DonationProgram.GENERAL,
        method=PaymentMethod.PIX,
        amount_cents=10000,
    )
    response = asyncio.run(service.create_intent(payload))
    assert response.pix_copy_paste
    assert service.get_status(response.donation_id, response.status_token).status == "pending"
    confirmed_file = tmp_path / "confirmed_donations.jsonl"
    assert not confirmed_file.exists()
    pending = service.pending.get(response.donation_id)
    body = json.dumps({
        "event_id": "test-event",
        "payment_id": pending.provider_payment_id,
        "status": "paid",
        "amount_cents": 10000,
        "metadata": {"donation_id": response.donation_id},
    }).encode()
    service.provider = GenericHttpPaymentProvider(settings)
    header = settings.psp_webhook_signature_header.lower()
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.process_webhook(body, {header: "invalid"}))
    assert error.value.status_code == 401
    assert not confirmed_file.exists()
    signature = hmac.new(settings.psp_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    for _ in range(2):
        asyncio.run(service.process_webhook(body, {header: signature}))
    assert len(confirmed_file.read_text(encoding="utf-8").splitlines()) == 1
    status = service.get_status(response.donation_id, response.status_token)
    assert status.status == "paid" and status.persisted
