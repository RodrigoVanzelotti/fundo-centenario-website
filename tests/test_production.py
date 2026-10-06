import asyncio
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
import time
import uuid

import pytest
from fastapi import HTTPException

from backend.app.config import Settings, _bool
from backend.app.models import DonationFinalizeRequest, DonationIntentRequest
from backend.app.providers.base import ProviderWebhookEvent
from backend.app.providers.mock import MockPaymentProvider
from backend.app.services import PaymentService


@pytest.fixture
def cloud(monkeypatch, tmp_path):
    host = os.getenv("FIRESTORE_TEST_HOST")
    if not host:
        if os.getenv("REQUIRE_FIRESTORE_TESTS") == "1":
            pytest.fail("FIRESTORE_TEST_HOST must point to the local emulator")
        pytest.skip("Run Firestore emulator tests with FIRESTORE_TEST_HOST")
    assert host.startswith(("127.0.0.1:", "localhost:")), "Tests must use a local emulator"
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", host)
    from backend.app.firestore_storage import FirestoreRepository
    settings = Settings(storage_backend="firestore", google_cloud_project="demo-fundo-centenario",
                        firestore_prefix="test_" + uuid.uuid4().hex + "_", data_dir=tmp_path,
                        public_base_url="http://testserver", email_enabled=False)
    repository = FirestoreRepository(settings)
    provider = MockPaymentProvider(settings)
    service = PaymentService(settings, provider, repository)
    payload = DonationIntentRequest(donor={"name": "Synthetic Donor", "email": "donor@example.com", "cpf": "52998224725"},
                                    method="card_recurring", program="geral", amount_cents=10000)
    response = asyncio.run(service.create_intent(payload, str(uuid.uuid4())))
    pending = service.pending.get(response.donation_id)
    event = ProviderWebhookEvent(event_id="evt_test", provider_payment_id="in_first", donation_id=response.donation_id,
                                status="paid", amount_cents=10000, currency="BRL", provider_subscription_id="sub_test",
                                status_token_hash=pending.status_token_hash, method="card_recurring", program="geral")
    yield service, repository, settings, payload, response, event
    for collection in repository.client.collections():
        if collection.id.startswith(settings.firestore_prefix):
            for document in collection.stream():
                document.reference.delete()
    repository.client.close()


def test_remote_pending_is_durable_without_pii_and_finalize_requires_payment(cloud):
    service, repository, settings, payload, response, event = cloud
    raw = repository.pending.ref(response.donation_id).get().to_dict()
    assert not any(field in str(raw) for field in (payload.donor.name, str(payload.donor.email), payload.donor.cpf))
    assert "donor" not in raw
    restarted = PaymentService(settings, service.provider)
    assert restarted.get_status(response.donation_id, response.status_token).status == "pending"
    with pytest.raises(HTTPException) as error:
        restarted.finalize_after_restart(response.donation_id, response.status_token, DonationFinalizeRequest(donor=payload.donor))
    assert error.value.status_code == 409
    restarted.apply_provider_event(event)
    assert not repository.donors.contains(response.donation_id)
    with pytest.raises(HTTPException):
        service.finalize_after_restart(response.donation_id, "wrong", DonationFinalizeRequest(donor=payload.donor))
    status = service.finalize_after_restart(response.donation_id, response.status_token, DonationFinalizeRequest(donor=payload.donor))
    assert status.persisted
    assert restarted.get_status(response.donation_id, response.status_token).persisted
    assert not list(settings.data_dir.glob("*.jsonl"))


def test_two_instances_deduplicate_invoices_and_donor(cloud):
    service, repository, settings, payload, response, event = cloud
    other = PaymentService(settings, service.provider)
    def deliver(index):
        try:
            (service if index % 2 else other).apply_provider_event(event)
        except RuntimeError:
            # PSP redelivery recovers a transient exhausted transaction without duplicate records.
            return False
        return True
    with ThreadPoolExecutor(max_workers=8) as pool:
        delivered = list(pool.map(deliver, range(16)))
    assert any(delivered)
    other.apply_provider_event(event)
    assert len(list(repository.confirmations.collection.stream())) == 1
    assert len(list(repository.payments.collection.stream())) == 1
    def finalize(index):
        try:
            (service if index % 2 else other).finalize_after_restart(
                response.donation_id, response.status_token, DonationFinalizeRequest(donor=payload.donor))
        except RuntimeError:
            return False
        return True
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert any(pool.map(finalize, range(8)))
    other.finalize_after_restart(response.donation_id, response.status_token, DonationFinalizeRequest(donor=payload.donor))
    assert len(list(repository.donors.collection.stream())) == 1
    other.apply_provider_event(replace(event, provider_payment_id="in_second", event_id="evt_second"))
    assert len(list(repository.payments.collection.stream())) == 2
    assert repository.confirmations.get(response.donation_id)["provider_payment_id"] == "in_first"


def test_concurrent_email_claims_and_recovery(cloud, monkeypatch):
    service, repository, settings, payload, response, event = cloud
    settings.email_enabled = True
    repository.email_enabled = True
    other = PaymentService(replace(settings, email_enabled=False), service.provider)
    other.settings.email_enabled = True
    other.repository.email_enabled = True
    service.apply_provider_event(event)
    job = repository.outbox.get(event.provider_payment_id)
    assert not any(field in str(job) for field in (payload.donor.name, str(payload.donor.email), payload.donor.cpf))
    # Missing donor never sends; the job survives and is scheduled for retry.
    sent = []
    monkeypatch.setattr(service.email_sender, "send", lambda *args: sent.append(args))
    assert service.process_pending_emails()["deferred"] == 1
    assert not sent
    service.finalize_after_restart(response.donation_id, response.status_token, DonationFinalizeRequest(donor=payload.donor))
    repository.outbox.ref(event.provider_payment_id).update({"next_attempt_at": 0})
    monkeypatch.setattr(other.email_sender, "send", lambda *args: sent.append(args))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda worker: worker.process_pending_emails(), [service, other]))
    assert len(sent) == 1
    assert repository.outbox.get(event.provider_payment_id)["state"] == "sent"
    assert repository.sent.contains(event.provider_payment_id)
    service.apply_provider_event(event)
    assert not repository.due_jobs(10)


def test_expired_email_lease_can_be_reclaimed(cloud):
    service, repository, settings, payload, response, event = cloud
    repository.email_enabled = True
    service.apply_provider_event(event)
    assert repository.claim(event.provider_payment_id, "first")
    assert not repository.claim(event.provider_payment_id, "second")
    repository.outbox.ref(event.provider_payment_id).update({"next_attempt_at": time.time() - 1})
    assert repository.claim(event.provider_payment_id, "second")
    repository.finish_job(repository.outbox.get(event.provider_payment_id), "first", True)
    assert not repository.sent.contains(event.provider_payment_id)


def test_idempotent_creation_after_restart_and_payload_conflict(cloud):
    service, repository, settings, payload, response, event = cloud
    key = str(uuid.uuid4())
    first = asyncio.run(service.create_intent(payload, key))
    other = PaymentService(settings, service.provider)
    second = asyncio.run(other.create_intent(payload, key))
    assert first == second
    with pytest.raises(HTTPException) as error:
        asyncio.run(other.create_intent(payload.model_copy(update={"amount_cents": 5000}), key))
    assert error.value.status_code == 409
    assert "donor" not in str(repository.intents.get(key))


def test_distributed_creation_budget(cloud):
    service, repository, settings, *_ = cloud
    other = PaymentService(settings, service.provider)
    settings.intent_limit_per_minute = other.settings.intent_limit_per_minute = 3
    assert service.allow_intent()
    assert other.allow_intent()
    assert service.allow_intent()
    assert not other.allow_intent()


def test_remote_confirmation_outbox_transaction_is_atomic(cloud, monkeypatch):
    service, repository, settings, payload, response, event = cloud
    repository.email_enabled = True
    from google.cloud.firestore_v1.transaction import Transaction
    def fail_commit(*args, **kwargs):
        raise OSError("Synthetic commit failure")
    with monkeypatch.context() as patch:
        patch.setattr(Transaction, "_commit", fail_commit)
        with pytest.raises(OSError):
            service.apply_provider_event(event)
    assert not repository.confirmations.contains(response.donation_id)
    assert not repository.payments.contains(event.provider_payment_id)
    assert not repository.outbox.contains(event.provider_payment_id)
    service.apply_provider_event(event)
    assert repository.confirmations.contains(response.donation_id)
    assert repository.outbox.contains(event.provider_payment_id)


def test_signed_stripe_webhook_remote_store_never_confirms_invalid_signature(cloud):
    from backend.app.providers.stripe import StripePaymentProvider
    service, repository, settings, payload, response, event = cloud
    settings.stripe_secret_key = "sk_test_example"
    settings.stripe_webhook_secret = "whsec_example"
    service.provider = StripePaymentProvider(settings)
    metadata = {"application": "fundo-centenario", "donation_id": response.donation_id,
                "status_token_hash": event.status_token_hash, "amount_cents": "10000", "program": "geral", "method": "card_recurring"}
    body = json.dumps({"id": "evt_remote", "type": "invoice.payment_succeeded", "livemode": False,
                       "api_version": settings.stripe_api_version, "data": {"object": {
                           "id": "in_remote", "currency": "brl", "status": "paid", "amount_paid": 10000, "amount_remaining": 0,
                           "parent": {"subscription_details": {"subscription": "sub_test", "metadata": metadata}}}}}).encode()
    with pytest.raises(HTTPException):
        asyncio.run(service.process_webhook(body, {"stripe-signature": "invalid"}))
    assert not repository.confirmations.contains(response.donation_id)
    timestamp = str(int(time.time()))
    signature = hmac.new(settings.stripe_webhook_secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    for _ in range(2):
        asyncio.run(service.process_webhook(body, {"stripe-signature": f"t={timestamp},v1={signature}"}))
    assert len(list(repository.payments.collection.stream())) == 1
    assert not repository.donors.contains(response.donation_id)


@pytest.mark.parametrize("field,value", [("storage_backend", "local"), ("payment_provider", "mock"),
                                       ("enable_mock_psp", True), ("stripe_live_mode", False),
                                       ("public_base_url", "http://example.com"), ("cors_origins", ["*"])])
def test_production_configuration_fails_closed(field, value, monkeypatch):
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    settings = Settings(app_env="production", storage_backend="firestore", google_cloud_project="example",
                        payment_provider="stripe", stripe_live_mode=True, enable_mock_psp=False,
                        public_base_url="https://example.com", cors_origins=["https://example.com"])
    settings.validate_runtime()
    setattr(settings, field, value)
    with pytest.raises(ValueError):
        settings.validate_runtime()


def test_invalid_boolean_is_not_silently_accepted(monkeypatch):
    monkeypatch.setenv("AUDIT_BOOLEAN", "maybe")
    with pytest.raises(ValueError):
        _bool("AUDIT_BOOLEAN")


def test_exhausted_transaction_is_retryable_not_a_bad_webhook():
    from backend.app.firestore_storage import commit
    from google.api_core.exceptions import Aborted
    def exhausted(transaction):
        raise ValueError("SDK exhausted retries") from Aborted("contention")
    class Client:
        def transaction(self):
            return object()
    with pytest.raises(RuntimeError):
        commit(Client(), exhausted)


def test_scheduler_requires_verified_identity_and_audience(monkeypatch):
    from backend.app import scheduler_auth
    settings = Settings(scheduler_audience="https://service.run.app", scheduler_service_account="scheduler@example.iam.gserviceaccount.com")
    seen = []
    def verify(token, request, audience):
        seen.append(audience)
        return {"email": settings.scheduler_service_account, "email_verified": True}
    monkeypatch.setattr(scheduler_auth.id_token, "verify_oauth2_token", verify)
    with pytest.raises(HTTPException):
        scheduler_auth.verify_scheduler("", settings)
    scheduler_auth.verify_scheduler("Bearer test", settings)
    assert seen == [settings.scheduler_audience]
    monkeypatch.setattr(scheduler_auth.id_token, "verify_oauth2_token", lambda *args, **kwargs: {"email": "attacker@example.com", "email_verified": True})
    with pytest.raises(HTTPException):
        scheduler_auth.verify_scheduler("Bearer invalid", settings)


def test_api_body_limits_security_headers_and_transient_failures(tmp_path, monkeypatch):
    import httpx
    from backend.app import config
    monkeypatch.setattr(config.settings, "data_dir", tmp_path)
    from backend.app import main
    settings = Settings(data_dir=tmp_path, email_enabled=False, intent_limit_per_minute=1)
    provider = MockPaymentProvider(settings)
    service = PaymentService(settings, provider)
    monkeypatch.setattr(main, "service", service)
    monkeypatch.setattr(main, "provider", provider)
    payload = {"donor": {"name": "Test Donor", "email": "test@example.com", "cpf": "52998224725"},
               "program": "geral", "method": "pix", "amount_cents": 10000}
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://testserver") as client:
            page = await client.get("/como-apoiar/")
            assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
            assert page.headers["referrer-policy"] == "no-referrer"
            assert (await client.post("/api/donations/intents", content=b"x" * 32769)).status_code == 413
            denied = await client.post("/api/internal/emails/process")
            assert denied.status_code in (401, 503)
            first = await client.post("/api/donations/intents", json=payload)
            assert first.status_code == 201
            assert first.headers["cache-control"] == "no-store"
            limited = await client.post("/api/donations/intents", json=payload)
            assert limited.status_code == 429 and limited.headers["retry-after"] == "60"
            def fail():
                raise RuntimeError("synthetic sensitive SDK details")
            monkeypatch.setattr(service, "allow_intent", fail)
            failed = await client.post("/api/donations/intents", json=payload)
            assert failed.status_code == 503
            assert "sensitive" not in failed.text
    asyncio.run(check())
