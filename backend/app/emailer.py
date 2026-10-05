from __future__ import annotations

import hashlib
import smtplib
import ssl
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate
from html import escape
from string import Template
from urllib.parse import urlsplit

from .config import Settings
from .models import ConfirmedDonationRecord, PaymentMethod


class DonationEmailSender:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.activity_url = settings.email_activity_url or f"{settings.public_base_url}/#impacto"
        if not settings.email_enabled:
            return
        if not all((settings.smtp_host, settings.smtp_username, settings.smtp_password, settings.email_from_address)):
            raise ValueError("Configure SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD e EMAIL_FROM_ADDRESS antes de habilitar emails.")
        if settings.smtp_security not in ("starttls", "ssl") or not 1 <= settings.smtp_port <= 65535:
            raise ValueError("SMTP exige STARTTLS ou SSL e uma porta válida.")
        Address(display_name=settings.email_from_name, addr_spec=settings.email_from_address)
        if settings.email_reply_to:
            Address(addr_spec=settings.email_reply_to)
        if "\r" in settings.email_subject or "\n" in settings.email_subject:
            raise ValueError("EMAIL_SUBJECT não pode conter quebras de linha.")
        url = urlsplit(self.activity_url)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            raise ValueError("EMAIL_ACTIVITY_URL deve ser uma URL HTTP/HTTPS sem credenciais.")
        if settings.app_env == "production" and url.scheme != "https":
            raise ValueError("EMAIL_ACTIVITY_URL deve usar HTTPS em produção.")
        if not settings.email_template_path.is_file():
            raise ValueError("Template HTML de agradecimento não encontrado.")

    def message(self, donor: ConfirmedDonationRecord, amount_cents: int, payment_id: str) -> EmailMessage:
        integer, cents = divmod(amount_cents, 100)
        amount = f"R$ {integer:,}".replace(",", ".") + f",{cents:02d}"
        contribution_type = "Recorrente" if donor.method in (PaymentMethod.CARD_RECURRING, PaymentMethod.PIX_AUTOMATIC) else "Pontual"
        values = {
            "donor_name": donor.donor_name, "amount": amount, "cause": donor.program_label,
            "contribution_type": contribution_type, "thank_you_text": self.settings.email_thank_you_text,
            "activity_url": self.activity_url,
        }
        html = Template(self.settings.email_template_path.read_text(encoding="utf-8")).substitute(
            {key: escape(value, quote=True) for key, value in values.items()}
        )
        message = EmailMessage()
        message["Subject"] = self.settings.email_subject
        message["From"] = Address(display_name=self.settings.email_from_name, addr_spec=self.settings.email_from_address)
        message["To"] = Address(addr_spec=donor.donor_email)
        if self.settings.email_reply_to:
            message["Reply-To"] = Address(addr_spec=self.settings.email_reply_to)
        message["Date"] = formatdate(localtime=False)
        # A stable ID helps recipient-side deduplication; SMTP cannot guarantee exactly-once delivery.
        message["Message-ID"] = f"<donation-{hashlib.sha256(payment_id.encode()).hexdigest()}@{Address(addr_spec=self.settings.email_from_address).domain}>"
        message.set_content(
            f"Olá, {donor.donor_name}!\n\nSua contribuição foi confirmada.\n"
            f"Valor: {amount}\nCausa: {donor.program_label}\nForma: {contribution_type}\n\n"
            f"{self.settings.email_thank_you_text}\n\nConheça as atividades do Fundo: {self.activity_url}\n"
        )
        message.add_alternative(html, subtype="html")
        return message

    def send(self, donor: ConfirmedDonationRecord, amount_cents: int, payment_id: str) -> None:
        if not self.settings.email_enabled:
            return
        message = self.message(donor, amount_cents, payment_id)
        context = ssl.create_default_context()
        factory = smtplib.SMTP_SSL if self.settings.smtp_security == "ssl" else smtplib.SMTP
        kwargs = {"timeout": 10}
        if self.settings.smtp_security == "ssl":
            kwargs["context"] = context
        with factory(self.settings.smtp_host, self.settings.smtp_port, **kwargs) as client:
            if self.settings.smtp_security == "starttls":
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
            client.login(self.settings.smtp_username, self.settings.smtp_password)
            client.send_message(message, from_addr=self.settings.email_from_address, to_addrs=[donor.donor_email])
