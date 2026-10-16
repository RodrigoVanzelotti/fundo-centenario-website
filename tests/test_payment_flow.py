import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs

import pytest
from fastapi import HTTPException

from backend.app.config import Settings
from backend.app.models import DonationIntentRequest
from backend.app.providers.stripe import StripePaymentProvider
from backend.app.services import PaymentService


@pytest.mark.parametrize("method", ["pix", "card", "card_recurring"])
def test_stripe_checkout_confirms_and_persists_once(tmp_path, stripe_http, method):
    settings = Settings(data_dir=tmp_path, public_base_url="http://localhost:8000")
    service = PaymentService(settings, StripePaymentProvider(settings))
    payload = DonationIntentRequest(
        donor={"name": "Synthetic Donor", "email": "donor@example.com", "cpf": "52998224725"},
        program="geral", method=method, amount_cents=10000,
    )
    response = asyncio.run(service.create_intent(payload))
    assert response.redirect_url.startswith("https://checkout.stripe.com/")
    assert service.get_status(response.donation_id, response.status_token).status == "pending"
    assert not list(tmp_path.glob("*.jsonl"))
    fields = parse_qs(stripe_http[-1].content.decode())
    metadata = {key[9:-1]: values[0] for key, values in fields.items() if key.startswith("metadata[")}
    if method == "card_recurring":
        kind = "invoice.payment_succeeded"
        obj = {"id": "in_first", "status": "paid", "amount_paid": 10000, "amount_remaining": 0,
               "currency": "brl", "parent": {"subscription_details": {
                   "subscription": "sub_test", "metadata": metadata}}}
    else:
        kind = "checkout.session.completed"
        obj = {"id": service.pending.get(response.donation_id).provider_payment_id,
               "mode": "payment", "payment_status": "paid", "amount_total": 10000,
               "currency": "brl", "metadata": metadata}
    body = json.dumps({"id": "evt_first", "type": kind, "livemode": False,
                       "api_version": settings.stripe_api_version, "data": {"object": obj}}).encode()
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.process_webhook(body, {"stripe-signature": "invalid"}))
    assert error.value.status_code == 401
    assert not list(tmp_path.glob("*.jsonl"))
    timestamp = str(int(time.time()))
    signature = hmac.new(settings.stripe_webhook_secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    for _ in range(2):
        asyncio.run(service.process_webhook(body, {"stripe-signature": f"t={timestamp},v1={signature}"}))
    assert service.get_status(response.donation_id, response.status_token).persisted
    assert len((tmp_path / "confirmed_donations.jsonl").read_text().splitlines()) == 1
