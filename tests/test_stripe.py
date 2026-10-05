import asyncio
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.models import DonationFinalizeRequest, DonationIntentRequest, DonorQuestionnaire, PaymentMethod
from backend.app.providers.stripe import StripePaymentProvider
from backend.app.services import PaymentService
from backend.app.storage import JsonlStore


def payload(method="card_recurring"):
    return DonationIntentRequest(
        donor=DonorQuestionnaire(name="Test Donor", email="test@example.com", cpf="52998224725"),
        program="geral", method=method, amount_cents=10000,
    )


@pytest.fixture
def integration(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path, public_base_url="http://localhost:8000", app_env="development",
        stripe_secret_key="sk_test_example", stripe_webhook_secret="whsec_test_only",
        stripe_api_version="2026-09-30.endive", stripe_live_mode=False,
    )
    requests = []
    real_client = httpx.AsyncClient

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "cs_test_checkout", "url": "https://checkout.stripe.com/c/pay/test",
            "expires_at": int(time.time()) + 86400,
        })

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    provider = StripePaymentProvider(settings)
    service = PaymentService(settings, provider)
    response = asyncio.run(service.create_intent(payload()))
    fields = parse_qs(requests[0].content.decode())
    metadata = {key[9:-1]: values[0] for key, values in fields.items() if key.startswith("metadata[")}
    return service, response, settings, metadata, requests, real_client


def event(settings, metadata, *, kind="invoice.payment_succeeded", invoice_id="in_first"):
    obj = {
        "id": invoice_id, "object": "invoice", "currency": "brl", "status": "paid",
        "amount_paid": 10000, "amount_remaining": 0,
        "parent": {"type": "subscription_details", "subscription_details": {
            "subscription": "sub_monthly", "metadata": metadata,
        }},
    }
    return {"id": "evt_first", "type": kind, "api_version": settings.stripe_api_version,
            "livemode": False, "data": {"object": obj}}


def signed(settings, data, *, timestamp=None):
    body = json.dumps(data, separators=(",", ":")).encode()
    timestamp = int(time.time()) if timestamp is None else timestamp
    signature = hmac.new(settings.stripe_webhook_secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    return body, {"stripe-signature": f"t={timestamp},v1={signature}"}


def deliver(service, settings, data):
    return asyncio.run(service.process_webhook(*signed(settings, data)))


def records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_monthly_checkout_contract_and_no_pii(integration):
    service, response, settings, metadata, requests, _ = integration
    request = requests[0]
    fields = parse_qs(request.content.decode())
    assert str(request.url) == "https://api.stripe.com/v1/checkout/sessions"
    assert fields["mode"] == ["subscription"]
    assert fields["payment_method_types[0]"] == ["card"]
    assert fields["line_items[0][price_data][recurring][interval]"] == ["month"]
    assert fields["line_items[0][price_data][currency]"] == ["brl"]
    assert fields["line_items[0][price_data][unit_amount]"] == ["10000"]
    assert fields["subscription_data[metadata][donation_id]"] == [response.donation_id]
    assert request.headers["Idempotency-Key"] == f"donation-{response.donation_id}"
    assert request.headers["Stripe-Version"] == settings.stripe_api_version
    for pii in ("Test Donor", "test@example.com", "52998224725"):
        assert pii not in request.content.decode()
    assert response.redirect_url.startswith("https://checkout.stripe.com/")
    assert service.get_status(response.donation_id, response.status_token).status == "pending"
    assert not list(settings.data_dir.glob("*.jsonl"))


@pytest.mark.parametrize("change", ["missing", "bad", "old", "future", "tampered", "v0", "live"])
def test_invalid_signatures_never_persist(integration, change):
    service, response, settings, metadata, _, _ = integration
    data = event(settings, metadata)
    if change == "live":
        data["livemode"] = True
    offset = -301 if change == "old" else 301 if change == "future" else 0
    body, headers = signed(settings, data, timestamp=int(time.time()) + offset)
    if change == "missing":
        headers = {}
    if change == "bad":
        headers["stripe-signature"] += "bad"
    if change == "tampered":
        body += b" "
    if change == "v0":
        headers["stripe-signature"] = headers["stripe-signature"].replace("v1=", "v0=")
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.process_webhook(body, headers))
    assert error.value.status_code == 401
    assert not list(settings.data_dir.glob("*.jsonl"))


def test_authorization_and_manual_paid_events_are_not_payment(integration):
    service, response, settings, metadata, _, _ = integration
    checkout = event(settings, metadata, kind="checkout.session.completed")
    checkout["data"]["object"] = {"id": "cs_test_checkout", "mode": "subscription", "payment_status": "paid", "metadata": metadata}
    deliver(service, settings, checkout)
    assert service.get_status(response.donation_id, response.status_token).status == "authorized"
    assert deliver(service, settings, event(settings, metadata, kind="invoice.paid")) is None
    failed = event(settings, metadata, kind="invoice.payment_failed")
    deliver(service, settings, failed)
    assert service.get_status(response.donation_id, response.status_token).status == "failed"
    assert not list(settings.data_dir.glob("*.jsonl"))


@pytest.mark.parametrize("field,value", [("amount_paid", 0), ("amount_paid", 9000), ("amount_paid", True), ("currency", "usd"), ("status", "open"), ("amount_remaining", 100)])
def test_invalid_invoice_amount_currency_and_status(integration, field, value):
    service, _, settings, metadata, _, _ = integration
    data = event(settings, metadata)
    data["data"]["object"][field] = value
    with pytest.raises(HTTPException) as error:
        deliver(service, settings, data)
    assert error.value.status_code == 400
    assert not list(settings.data_dir.glob("*.jsonl"))


def test_duplicate_and_renewal_after_restart(integration):
    service, response, settings, metadata, _, _ = integration
    first = event(settings, metadata)
    deliver(service, settings, first)
    deliver(service, settings, first)
    first["id"] = "evt_duplicate_object"
    deliver(service, settings, first)
    restarted = PaymentService(settings, service.provider)
    deliver(restarted, settings, first)
    renewal = event(settings, metadata, invoice_id="in_second")
    renewal["id"] = "evt_second"
    deliver(restarted, settings, renewal)
    deliver(restarted, settings, renewal)
    assert len(records(settings.data_dir / "recurring_payments.jsonl")) == 2
    assert len(records(settings.data_dir / "confirmed_donations.jsonl")) == 1
    assert len(records(settings.data_dir / "payment_confirmations.jsonl")) == 1
    assert "52998224725" not in (settings.data_dir / "recurring_payments.jsonl").read_text()
    assert restarted.get_status(response.donation_id, response.status_token).persisted
    # A different subscription must not reuse an existing contribution reference.
    renewal["data"]["object"]["parent"]["subscription_details"]["subscription"] = "sub_other"
    with pytest.raises(HTTPException):
        deliver(restarted, settings, renewal)


def test_retry_after_storage_failure(integration, monkeypatch):
    service, _, settings, metadata, _, _ = integration
    append = service.confirmed_donations.append_once
    monkeypatch.setattr(service.confirmed_donations, "append_once", lambda record: (_ for _ in ()).throw(OSError("disk unavailable")))
    with pytest.raises(OSError):
        deliver(service, settings, event(settings, metadata))
    monkeypatch.setattr(service.confirmed_donations, "append_once", append)
    deliver(service, settings, event(settings, metadata))
    assert len(records(settings.data_dir / "confirmed_donations.jsonl")) == 1
    assert len(records(settings.data_dir / "recurring_payments.jsonl")) == 1


def test_concurrent_duplicate_deliveries(integration):
    service, _, settings, metadata, _, _ = integration
    parsed = asyncio.run(service.provider.parse_webhook(*signed(settings, event(settings, metadata))))
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(service.apply_provider_event, [parsed] * 8))
    assert len(records(settings.data_dir / "recurring_payments.jsonl")) == 1
    assert len(records(settings.data_dir / "confirmed_donations.jsonl")) == 1


def test_webhook_before_browser_return_and_restart_recovery(integration):
    service, response, settings, metadata, _, _ = integration
    restarted = PaymentService(settings, service.provider)
    with pytest.raises(HTTPException) as error:
        restarted.finalize_after_restart(response.donation_id, response.status_token, DonationFinalizeRequest(donor=payload().donor))
    assert error.value.status_code == 409
    deliver(restarted, settings, event(settings, metadata))
    assert not (settings.data_dir / "confirmed_donations.jsonl").exists()
    with pytest.raises(HTTPException):
        restarted.finalize_after_restart(response.donation_id, "wrong", DonationFinalizeRequest(donor=payload().donor))
    for _ in range(2):
        restarted.finalize_after_restart(response.donation_id, response.status_token, DonationFinalizeRequest(donor=payload().donor))
    assert len(records(settings.data_dir / "confirmed_donations.jsonl")) == 1


def test_stripe_recurring_method_is_card_only(integration):
    service, _, settings, _, requests, _ = integration
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.create_intent(payload("pix_automatico")))
    assert error.value.status_code == 422
    assert len(requests) == 1


@pytest.mark.parametrize("method", ["pix", "card"])
def test_hosted_one_time_checkout(integration, method):
    service, _, settings, _, requests, _ = integration
    response = asyncio.run(service.create_intent(payload(method)))
    fields = parse_qs(requests[-1].content.decode())
    assert fields["mode"] == ["payment"]
    assert not any(key.startswith("subscription_data") for key in fields)
    metadata = {key[9:-1]: value[0] for key, value in fields.items() if key.startswith("metadata[")}
    data = event(settings, metadata, kind="checkout.session.completed")
    data["data"]["object"] = {
        "id": "cs_test_checkout", "mode": "payment", "currency": "brl",
        "payment_status": "unpaid", "amount_total": 10000, "metadata": metadata,
    }
    deliver(service, settings, data)
    assert not (settings.data_dir / "confirmed_donations.jsonl").exists()
    data["data"]["object"]["payment_status"] = "paid"
    data["type"] = "checkout.session.async_payment_succeeded"
    deliver(service, settings, data)
    assert service.get_status(response.donation_id, response.status_token).persisted


def test_local_store_rolls_back_failed_write_and_rejects_corruption(tmp_path, monkeypatch):
    store = JsonlStore(tmp_path / "test.jsonl", "id")
    import backend.app.storage as storage
    fsync = storage.os.fsync
    monkeypatch.setattr(storage.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("sync failed")))
    with pytest.raises(OSError):
        store.append_once({"id": "once"})
    monkeypatch.setattr(storage.os, "fsync", fsync)
    store.append_once({"id": "once"})
    assert len(records(store.path)) == 1
    store.path.write_text('{"invalid":', encoding="utf-8")
    with pytest.raises(ValueError):
        JsonlStore(store.path, "id")


def test_boundary_validation_rejects_fractional_cents():
    with pytest.raises(ValidationError):
        DonationIntentRequest(**{**payload().model_dump(), "amount_cents": 100.5})


@pytest.mark.parametrize("setting,value", [
    ("stripe_secret_key", "sk_live_wrong_mode"), ("stripe_webhook_secret", ""),
    ("app_env", "production"),
])
def test_unsafe_configuration_is_rejected(integration, setting, value):
    _, _, settings, _, _, _ = integration
    setattr(settings, setting, value)
    with pytest.raises(ValueError):
        StripePaymentProvider(settings)


@pytest.mark.parametrize("update", [
    {"api_version": "2024-10-28.acacia"},
    {"data": {"object": {"currency": "usd"}}},
])
def test_wrong_version_or_malformed_signed_event_is_rejected(integration, update):
    service, _, settings, metadata, _, _ = integration
    data = event(settings, metadata)
    data.update(update)
    with pytest.raises(HTTPException) as error:
        deliver(service, settings, data)
    assert error.value.status_code == 400
    assert not list(settings.data_dir.glob("*.jsonl"))


def test_multiple_v1_signatures_and_unrelated_events(integration):
    service, _, settings, metadata, _, _ = integration
    data = event(settings, metadata)
    body, headers = signed(settings, data)
    headers["stripe-signature"] += ",v1=invalid,v0=ignored"
    asyncio.run(service.process_webhook(body, headers))
    other = event(settings, {**metadata, "application": "other-application"}, invoice_id="in_other")
    assert deliver(service, settings, other) is None
    assert len(records(settings.data_dir / "recurring_payments.jsonl")) == 1


def test_api_endpoints_and_secrets_are_not_exposed(integration, monkeypatch):
    service, response, settings, metadata, _, real_client = integration
    # Import the application with isolated storage; tests must never write to backend/data.
    from backend.app import config
    monkeypatch.setattr(config.settings, "data_dir", settings.data_dir)
    monkeypatch.setattr(config.settings, "payment_provider", "mock")
    from backend.app import main
    monkeypatch.setattr(main, "provider", service.provider)
    monkeypatch.setattr(main, "service", service)

    async def check():
        async with real_client(transport=httpx.ASGITransport(app=main.app), base_url="http://testserver") as client:
            options = await client.get("/api/donations/options")
            assert options.json() == {"methods": ["pix", "card", "card_recurring"]}
            assert settings.stripe_secret_key not in options.text
            denied = await client.get(f"/api/donations/{response.donation_id}/status", headers={"X-Donation-Token": "invalid"})
            assert denied.status_code == 404
            rejected = await client.post("/api/webhooks/stripe", json=event(settings, metadata))
            assert rejected.status_code == 401
            assert not (settings.data_dir / "confirmed_donations.jsonl").exists()
            body, headers = signed(settings, event(settings, metadata))
            accepted = await client.post("/api/webhooks/stripe", content=body, headers=headers)
            assert accepted.status_code == 200
            oversized = await client.post("/api/webhooks/stripe", content=b"x" * 1_048_577)
            assert oversized.status_code == 413
            status = await client.get(f"/api/donations/{response.donation_id}/status", headers={"X-Donation-Token": response.status_token})
            assert status.json()["status"] == "paid"
            invalid = await client.post("/api/donations/intents", json={**payload().model_dump(mode="json"), "amount_cents": 1})
            assert invalid.status_code == 422
            created = await client.post("/api/donations/intents", json=payload().model_dump(mode="json"))
            assert created.status_code == 201
            assert "checkout.stripe.com" in created.json()["redirect_url"]
            assert settings.stripe_secret_key not in created.text
            assert settings.stripe_webhook_secret not in created.text

    asyncio.run(check())


def test_provider_errors_do_not_echo_sensitive_payloads(integration, monkeypatch):
    service, _, _, _, _, _ = integration

    async def fail(request):
        raise RuntimeError("sk_test_sensitive test@example.com 52998224725")

    monkeypatch.setattr(service.provider, "create_recurring_checkout", fail)
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.create_intent(payload()))
    assert error.value.status_code == 502
    assert "sk_test" not in error.value.detail
    assert "52998224725" not in error.value.detail


@pytest.mark.parametrize("key,value", [("status_token_hash", "0" * 64), ("amount_cents", "9000"), ("program", "mentoria"), ("method", "card")])
def test_metadata_must_match_the_original_donation(integration, key, value):
    service, _, settings, metadata, _, _ = integration
    with pytest.raises(HTTPException) as error:
        deliver(service, settings, event(settings, {**metadata, key: value}))
    assert error.value.status_code == 400
    assert not list(settings.data_dir.glob("*.jsonl"))


def test_late_checkout_completion_cannot_undo_payment(integration):
    service, response, settings, metadata, _, _ = integration
    deliver(service, settings, event(settings, metadata))
    data = event(settings, metadata, kind="checkout.session.completed")
    data["data"]["object"] = {"id": "cs_test_checkout", "mode": "subscription", "payment_status": "paid", "metadata": metadata}
    deliver(service, settings, data)
    assert service.get_status(response.donation_id, response.status_token).status == "paid"


@pytest.mark.parametrize("url", ["http://checkout.stripe.com/c/pay/test", "https://checkout.stripe.com.evil.test/", "https://evil.test/", "https://checkout.stripe.com:444/"])
def test_untrusted_checkout_redirect_is_rejected(integration, monkeypatch, url):
    service, _, _, _, _, real_client = integration
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "id": "cs_test_checkout", "url": url, "expires_at": int(time.time()) + 86400,
    }))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs))
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.create_intent(payload()))
    assert error.value.status_code == 502


def test_donor_storage_cannot_be_public(integration):
    _, _, settings, _, _, _ = integration
    settings.data_dir = settings.frontend_dir / "data"
    with pytest.raises(ValueError):
        PaymentService(settings, StripePaymentProvider(settings))
