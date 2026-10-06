"""Validate a trusted, reconciled JSONL backup; apply only with explicit operator flags."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.models import ConfirmedDonationRecord, DonorQuestionnaire, PaymentConfirmation


def load_source(source: Path):
    def read(name, model=None):
        path = source / (name + ".jsonl")
        if not path.exists():
            return []
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [model.model_validate(value) for value in values] if model else values

    roots = read("payment_confirmations", PaymentConfirmation)
    invoices = read("recurring_payments", PaymentConfirmation)
    donors = read("confirmed_donations", ConfirmedDonationRecord)
    sent = read("thank_you_sent")
    outbox = read("thank_you_outbox")
    by_donation = {record.donation_id: record for record in roots}
    if len(by_donation) != len(roots):
        raise ValueError("Duplicate root confirmations")
    payments = {record.provider_payment_id: record for record in roots + invoices}
    if len({record.donation_id for record in donors}) != len(donors):
        raise ValueError("Duplicate donor records")
    for payment in roots + invoices:
        root = by_donation.get(payment.donation_id)
        if not root or not payment.provider_payment_id.startswith(("cs_", "in_")):
            raise ValueError("Reconcile Stripe payments before importing; mock records are not production payments")
        if not 100 <= payment.amount_cents <= 100_000_000 or not re.fullmatch(r"[0-9a-f]{64}", payment.status_token_hash):
            raise ValueError("Invalid financial record or access-token hash")
        if payments[payment.provider_payment_id].donation_id != payment.donation_id:
            raise ValueError("Payment assigned to multiple donations")
        for field in ("method", "program", "amount_cents", "status_token_hash", "provider_subscription_id"):
            if getattr(root, field) != getattr(payment, field):
                raise ValueError("Inconsistent payment ledger")
    for donor in donors:
        root = by_donation.get(donor.donation_id)
        if not root or any(getattr(donor, field) != getattr(root, field) for field in ("provider_payment_id", "method", "program", "amount_cents")):
            raise ValueError("Donor without matching payment")
        DonorQuestionnaire(name=donor.donor_name, email=donor.donor_email, cpf=donor.donor_cpf)
    for job in sent + outbox:
        payment = payments.get(job["provider_payment_id"])
        if not payment or payment.donation_id != job["donation_id"]:
            raise ValueError("Email without matching payment")
    return roots, invoices, donors, sent, outbox


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--project")
    parser.add_argument("--database", default="(default)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirmed-source", action="store_true", help="Operator has backed up and reconciled these records with Stripe")
    parser.add_argument("--include-pending-emails", action="store_true")
    args = parser.parse_args()
    roots, invoices, donors, sent, outbox = load_source(args.source)
    print(f"Validated: {len(roots)} donations, {len(invoices)} invoices, {len(donors)} donor records, {len(sent)} sent markers.")
    if not args.apply:
        print("Dry run: no remote connection or writes.")
        return
    if not args.project or not args.confirmed_source:
        parser.error("--apply requires --project and --confirmed-source")
    from backend.app.config import Settings
    from backend.app.firestore_storage import FirestoreRepository
    settings = Settings(storage_backend="firestore", google_cloud_project=args.project,
                        firestore_database=args.database, email_enabled=False)
    repository = FirestoreRepository(settings)
    try:
        for record in roots + invoices:
            repository.confirm(record)
        confirmations = {record.donation_id: record for record in roots}
        for record in donors:
            repository.finalize(record, confirmations[record.donation_id].status_token_hash)
        for marker in sent:
            repository.sent.append_once({key: marker[key] for key in ("donation_id", "provider_payment_id", "sent_at")})
        if args.include_pending_emails:
            for job in outbox:
                if not repository.sent.contains(job["provider_payment_id"]):
                    repository.outbox.append_once(repository.job(job))
        print("Import completed. No SMTP calls were made.")
    finally:
        repository.client.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Model validation errors can include donor data; never print their message or traceback.
        print(f"Migration failed ({type(error).__name__}); inspect the source privately.", file=sys.stderr)
        raise SystemExit(1) from None
