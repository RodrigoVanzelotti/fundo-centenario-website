import os

# Never read sender/payment credentials from a developer's .env during tests.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["APP_ENV"] = "development"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_synthetic"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_synthetic"
os.environ["EMAIL_ENABLED"] = "false"


import time
from urllib.parse import parse_qs

import httpx
import pytest


@pytest.fixture
def stripe_http(monkeypatch):
    """Exercise the Stripe adapter without network access or real credentials."""
    requests = []
    real_client = httpx.AsyncClient

    def handle(request):
        assert str(request.url) == "https://api.stripe.com/v1/checkout/sessions"
        requests.append(request)
        fields = parse_qs(request.content.decode())
        donation_id = fields["client_reference_id"][0]
        return httpx.Response(200, json={
            "id": "cs_test_" + donation_id,
            "url": "https://checkout.stripe.com/c/pay/test",
            "expires_at": int(time.time()) + 86400,
        })

    def client(**kwargs):
        kwargs.setdefault("transport", httpx.MockTransport(handle))
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return requests
