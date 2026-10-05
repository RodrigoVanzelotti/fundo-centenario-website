import asyncio
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.parser import BytesParser
from email.policy import default
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.app.config import Settings
from backend.app.emailer import DonationEmailSender
from backend.app.models import DonationFinalizeRequest, DonationIntentRequest, DonorQuestionnaire
from backend.app.providers.mock import MockPaymentProvider
from backend.app.services import PaymentService


@pytest.fixture
def email_flow(tmp_path, monkeypatch):
    settings = Settings(
        data_dir=tmp_path, public_base_url="https://fund.example.org", app_env="development",
        email_enabled=True, smtp_host="smtp.example.org", smtp_port=587,
        smtp_username="sender", smtp_password="test-only-password", smtp_security="starttls",
        email_from_address="fundo@example.org", email_from_name="Fundo Centenário",
        email_reply_to="equipe@example.org", email_subject="Obrigado pelo apoio",
        email_activity_url="https://fund.example.org/#impacto",
        email_template_path=Path("backend/templates/donation_thank_you.html"),
        email_thank_you_text="Descubra as iniciativas que seu apoio ajuda a realizar.",
    )
    calls, messages = [], []

    class SMTP:
        def __init__(self, host, port, **kwargs):
            calls.append(("connect", host, port, kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            calls.append(("ehlo",))

        def starttls(self, *, context):
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
            calls.append(("tls",))

        def login(self, username, password):
            calls.append(("login",))
            assert username == settings.smtp_username and password == settings.smtp_password

        def send_message(self, message, **kwargs):
            calls.append(("send",))
            messages.append((message, kwargs))

    monkeypatch.setattr(smtplib, "SMTP", SMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", SMTP)
    service = PaymentService(settings, MockPaymentProvider(settings))
    request = DonationIntentRequest(
        donor=DonorQuestionnaire(name="Maria <b>Silva</b> & Família", email="maria@example.org", cpf="52998224725"),
        program="mentoria", method="pix", amount_cents=123456,
    )
    response = asyncio.run(service.create_intent(request))
    pending = service.pending.get(response.donation_id)
    entry = service.provider.entries[pending.provider_payment_id]
    event = service.provider.confirm(entry.provider_payment_id, entry.mock_key)
    return service, settings, response, request, event, calls, messages


def test_email_only_after_paid_with_all_template_fields(email_flow):
    service, settings, response, request, event, calls, messages = email_flow
    service.process_pending_emails()
    assert not messages and not calls
    event.status = "authorized"
    service.apply_provider_event(event)
    service.process_pending_emails()
    assert not messages
    assert not service.email_outbox.path.exists()
    event.status = "failed"
    service.apply_provider_event(event)
    service.process_pending_emails()
    assert not messages
    event.status = "paid"
    service.apply_provider_event(event)
    assert not messages  # SMTP does not run in the webhook or under the payment lock.
    service.process_pending_emails()
    assert len(messages) == 1
    message, envelope = messages[0]
    assert envelope == {"from_addr": "fundo@example.org", "to_addrs": ["maria@example.org"]}
    assert message["Reply-To"] == "equipe@example.org"
    assert message["Subject"] == settings.email_subject
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "Maria &lt;b&gt;Silva&lt;/b&gt; &amp; Família" in html
    assert "R$ 1.234,56" in html
    assert "Programa de Mentoria" in html and "Pontual" in html
    assert settings.email_thank_you_text in html
    assert settings.email_activity_url in html
    assert "52998224725" not in message.as_string()
    assert calls.index(("tls",)) < calls.index(("login",)) < calls.index(("send",))
    parsed = BytesParser(policy=default).parsebytes(message.as_bytes())
    assert parsed.get_body(preferencelist=("plain",))
    assert parsed.get_body(preferencelist=("html",))
    for path in (service.email_outbox.path, service.email_sent.path):
        text = path.read_text(encoding="utf-8")
        assert "maria@example.org" not in text and "52998224725" not in text


def test_duplicate_restart_and_concurrent_workers_do_not_resend(email_flow):
    service, settings, _, _, event, _, messages = email_flow
    service.apply_provider_event(event)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: service.process_pending_emails(), range(4)))
    assert len(messages) == 1
    service.apply_provider_event(event)
    restarted = PaymentService(settings, MockPaymentProvider(settings))
    restarted.process_pending_emails()
    assert len(messages) == 1


def test_smtp_failure_preserves_payment_and_retries_without_pii_in_logs(email_flow, monkeypatch, caplog):
    service, _, response, _, event, _, messages = email_flow
    service.apply_provider_event(event)
    send = service.email_sender.send

    def fail(*args):
        raise smtplib.SMTPAuthenticationError(535, b"test-only-password maria@example.org 52998224725")

    monkeypatch.setattr(service.email_sender, "send", fail)
    service.process_pending_emails()
    assert not service.email_sent.path.exists() and not messages
    assert service.get_status(response.donation_id, response.status_token).persisted
    assert "SMTPAuthenticationError" in caplog.text
    for secret in ("test-only-password", "maria@example.org", "52998224725"):
        assert secret not in caplog.text
    monkeypatch.setattr(service.email_sender, "send", send)
    service.process_pending_emails()
    assert len(messages) == 1


def test_restart_recovery_queues_only_after_confirmed_donor_is_recovered(email_flow):
    service, settings, response, request, event, _, messages = email_flow
    restarted = PaymentService(settings, MockPaymentProvider(settings))
    with pytest.raises(HTTPException) as error:
        restarted.finalize_after_restart(response.donation_id, response.status_token, DonationFinalizeRequest(donor=request.donor))
    assert error.value.status_code == 409
    assert not restarted.email_outbox.path.exists()
    restarted.apply_provider_event(event)
    restarted.process_pending_emails()
    assert not messages  # A paid invoice alone supplies no donor name or recipient.
    restarted.finalize_after_restart(response.donation_id, response.status_token, DonationFinalizeRequest(donor=request.donor))
    restarted.process_pending_emails()
    restarted.finalize_after_restart(response.donation_id, response.status_token, DonationFinalizeRequest(donor=request.donor))
    restarted.process_pending_emails()
    assert len(messages) == 1


def test_monthly_invoice_has_recurring_label_and_one_email_per_invoice(email_flow):
    service, _, _, _, event, _, messages = email_flow
    pending = service.pending.get(event.donation_id)
    from backend.app.models import PaymentMethod
    pending.method = PaymentMethod.CARD_RECURRING
    event.method = "card_recurring"
    event.provider_subscription_id = "sub_monthly"
    event.provider_payment_id = "in_first"
    service.apply_provider_event(event)
    service.process_pending_emails()
    event.provider_payment_id = "in_second"
    event.event_id = "evt_second"
    service.apply_provider_event(event)
    service.apply_provider_event(event)
    service.process_pending_emails()
    assert len(messages) == 2
    assert all("Recorrente" in message.get_body(preferencelist=("html",)).get_content() for message, _ in messages)
    assert messages[0][0]["Message-ID"] != messages[1][0]["Message-ID"]


def test_disabled_sender_does_not_queue_or_connect(email_flow):
    service, settings, _, _, event, calls, messages = email_flow
    settings.email_enabled = False
    service.apply_provider_event(event)
    service.process_pending_emails()
    assert not messages and not calls
    assert not service.email_outbox.path.exists()


def test_ssl_sender_verifies_certificate_and_skips_starttls(email_flow):
    service, settings, _, _, event, calls, messages = email_flow
    settings.smtp_security = "ssl"
    settings.smtp_port = 465
    service.apply_provider_event(event)
    service.process_pending_emails()
    assert len(messages) == 1
    assert ("tls",) not in calls
    context = calls[0][3]["context"]
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.parametrize("key,value", [
    ("smtp_security", "none"), ("smtp_password", ""), ("smtp_port", 0),
    ("email_activity_url", "javascript:alert(1)"), ("email_subject", "Hello\nBcc: victim@example.org"),
])
def test_invalid_sender_configuration_is_rejected(email_flow, key, value):
    _, settings, _, _, _, _, _ = email_flow
    setattr(settings, key, value)
    with pytest.raises(ValueError):
        DonationEmailSender(settings)


def test_custom_template_can_be_configured(email_flow, tmp_path):
    service, settings, _, _, event, _, messages = email_flow
    template = tmp_path / "custom.html"
    template.write_text("<p>${donor_name}: ${amount}, ${cause}, ${contribution_type}</p><p>${thank_you_text}</p>", encoding="utf-8")
    settings.email_template_path = template
    service.apply_provider_event(event)
    service.process_pending_emails()
    assert "Maria &lt;b&gt;Silva&lt;/b&gt;" in messages[0][0].get_body(preferencelist=("html",)).get_content()


def test_lifespan_runs_the_email_worker_without_smtp_in_the_webhook(email_flow, monkeypatch):
    service, settings, _, _, event, _, messages = email_flow
    service.apply_provider_event(event)
    from backend.app import config
    monkeypatch.setattr(config.settings, "data_dir", settings.data_dir)
    monkeypatch.setattr(config.settings, "payment_provider", "mock")
    monkeypatch.setattr(config.settings, "email_enabled", False)
    from backend.app import main
    monkeypatch.setattr(main, "service", service)
    monkeypatch.setattr(main.settings, "email_enabled", True)

    async def check():
        async with main.app.router.lifespan_context(main.app):
            async with asyncio.timeout(3):
                while not messages:
                    await asyncio.sleep(0.01)
        assert len(messages) == 1

    asyncio.run(check())


def test_worker_does_not_trust_an_outbox_job_without_payment_confirmation(email_flow):
    service, _, _, _, event, calls, messages = email_flow
    service.email_outbox.append_once({"donation_id": event.donation_id, "provider_payment_id": event.provider_payment_id})
    service.process_pending_emails()
    assert not calls and not messages


def test_marker_failure_preserves_job_and_reuses_message_id(email_flow, monkeypatch):
    service, _, _, _, event, _, messages = email_flow
    service.apply_provider_event(event)
    append = service.email_sent.append_once

    def fail(record):
        raise OSError("disk unavailable")

    monkeypatch.setattr(service.email_sent, "append_once", fail)
    service.process_pending_emails()
    monkeypatch.setattr(service.email_sent, "append_once", append)
    service.process_pending_emails()
    assert len(messages) == 2  # SMTP and the disk marker cannot commit atomically.
    assert messages[0][0]["Message-ID"] == messages[1][0]["Message-ID"]
