"""Server-only Firestore persistence; no donor questionnaire in pending intents."""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone

from google.api_core.exceptions import Aborted, AlreadyExists
from google.api_core.retry import Retry
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from .models import ConfirmedDonationRecord, PaymentConfirmation, PendingDonation


def document_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


RPC = {"timeout": 5, "retry": Retry(deadline=10)}


def commit(client, write):
    try:
        return write(client.transaction())
    except ValueError as error:
        # The SDK wraps exhausted contention retries in ValueError. They are not bad PSP payloads.
        if isinstance(error.__cause__, Aborted):
            raise RuntimeError("Transação temporariamente indisponível; tente novamente.") from None
        raise


class FirestoreStore:
    def __init__(self, client, collection: str, id_field: str, model=None):
        self.client = client
        self.collection = client.collection(collection)
        self.id_field = id_field
        self.model = model

    def ref(self, value: str):
        return self.collection.document(document_key(value))

    def get(self, value: str):
        return self.ref(value).get(**RPC).to_dict()

    def get_model(self, value: str):
        record = self.get(value)
        return self.model.model_validate(record) if record else None

    def contains(self, value: str) -> bool:
        return self.get(value) is not None

    def append_once(self, record: dict) -> bool:
        try:
            self.ref(str(record[self.id_field])).create(record, **RPC)
            return True
        except AlreadyExists:
            return False


class FirestorePendingStore(FirestoreStore):
    def put(self, pending: PendingDonation) -> None:
        # The questionnaire is intentionally kept only by the browser until /finalize.
        record = pending.model_dump(mode="json", exclude={"donor"})
        record["expires_at"] = datetime.fromtimestamp(pending.expires_at_epoch, timezone.utc)
        self.ref(pending.donation_id).set(record, **RPC)

    def get(self, value: str):
        record = super().get(value)
        if not record or record["expires_at_epoch"] <= time.time():
            return None
        return PendingDonation.model_validate(record)

    def get_by_provider_id(self, value: str):
        if not value:
            return None
        snapshots = self.collection.where(filter=FieldFilter("provider_payment_id", "==", value)).limit(1).stream(**RPC)
        return next((self.get(item.to_dict()["donation_id"]) for item in snapshots), None)

    def update_status(self, value: str, status: str):
        self.ref(value).update({"provider_status": status}, **RPC)

    def remove(self, value: str):
        self.ref(value).delete(**RPC)


class FirestoreRepository:
    def __init__(self, settings, client=None):
        self.client = client or firestore.Client(project=settings.google_cloud_project, database=settings.firestore_database)
        prefix = settings.firestore_prefix
        self.pending = FirestorePendingStore(self.client, prefix + "pending", "donation_id")
        self.confirmations = FirestoreStore(self.client, prefix + "payment_confirmations", "donation_id", PaymentConfirmation)
        self.donors = FirestoreStore(self.client, prefix + "confirmed_donations", "donation_id", ConfirmedDonationRecord)
        self.payments = FirestoreStore(self.client, prefix + "recurring_payments", "provider_payment_id")
        self.outbox = FirestoreStore(self.client, prefix + "thank_you_outbox", "provider_payment_id")
        self.sent = FirestoreStore(self.client, prefix + "thank_you_sent", "provider_payment_id")
        self.intents = FirestoreStore(self.client, prefix + "intents", "key")
        self.limits = self.client.collection(prefix + "rate_limits")
        self.email_enabled = settings.email_enabled

    @staticmethod
    def job(record: dict) -> dict:
        return {"donation_id": record["donation_id"], "provider_payment_id": record["provider_payment_id"],
                "state": "pending", "next_attempt_at": time.time(), "attempts": 0, "lease": ""}

    def confirm(self, confirmation: PaymentConfirmation):
        record = confirmation.model_dump(mode="json")
        root_ref = self.confirmations.ref(confirmation.donation_id)
        payment_ref = self.payments.ref(confirmation.provider_payment_id)
        job_ref = self.outbox.ref(confirmation.provider_payment_id)

        @firestore.transactional
        def write(transaction):
            root = root_ref.get(transaction=transaction, **RPC).to_dict()
            payment = payment_ref.get(transaction=transaction, **RPC).to_dict() if confirmation.provider_subscription_id else None
            job = job_ref.get(transaction=transaction, **RPC).to_dict() if self.email_enabled else None
            if root:
                for key in ("amount_cents", "method", "program", "status_token_hash", "provider_subscription_id"):
                    if root.get(key) != record.get(key):
                        raise ValueError("Confirmação incompatível com o registro existente.")
                if not confirmation.provider_subscription_id and root["provider_payment_id"] != confirmation.provider_payment_id:
                    raise ValueError("Pagamento pontual incompatível.")
            if payment and any(payment.get(key) != record.get(key) for key in ("donation_id", "amount_cents", "provider_subscription_id")):
                raise ValueError("Fatura já vinculada a outra contribuição.")
            if not root:
                transaction.create(root_ref, record)
            if confirmation.provider_subscription_id and not payment:
                transaction.create(payment_ref, record)
            if self.email_enabled and not job:
                transaction.create(job_ref, self.job(record))

        commit(self.client, write)

    def finalize(self, record: ConfirmedDonationRecord, token_hash: str):
        root_ref = self.confirmations.ref(record.donation_id)
        donor_ref = self.donors.ref(record.donation_id)

        @firestore.transactional
        def write(transaction):
            root = root_ref.get(transaction=transaction, **RPC).to_dict()
            donor = donor_ref.get(transaction=transaction, **RPC).to_dict()
            if not root or root["status_token_hash"] != token_hash:
                raise ValueError("Cadastro sem confirmação autenticada.")
            if not donor:
                transaction.create(donor_ref, record.model_dump(mode="json"))

        commit(self.client, write)

    def enqueue(self, confirmation: PaymentConfirmation):
        if self.email_enabled:
            self.outbox.append_once(self.job(confirmation.model_dump(mode="json")))

    def due_jobs(self, limit: int):
        query = self.outbox.collection.where(filter=FieldFilter("state", "==", "pending"))
        query = query.where(filter=FieldFilter("next_attempt_at", "<=", time.time())).order_by("next_attempt_at").limit(limit)
        return [item.to_dict() for item in query.stream(**RPC)]

    def claim(self, payment_id: str, lease: str):
        reference = self.outbox.ref(payment_id)

        @firestore.transactional
        def write(transaction):
            job = reference.get(transaction=transaction, **RPC).to_dict()
            now = time.time()
            if not job or job["state"] != "pending" or job["next_attempt_at"] > now:
                return False
            transaction.update(reference, {"lease": lease, "next_attempt_at": now + 300, "attempts": job["attempts"] + 1})
            return True

        return commit(self.client, write)

    def finish_job(self, job: dict, lease: str, success: bool):
        reference = self.outbox.ref(job["provider_payment_id"])
        sent_ref = self.sent.ref(job["provider_payment_id"])

        @firestore.transactional
        def write(transaction):
            current = reference.get(transaction=transaction, **RPC).to_dict()
            if not current or current["state"] != "pending" or current["lease"] != lease:
                return
            if success:
                transaction.set(sent_ref, {"donation_id": job["donation_id"], "provider_payment_id": job["provider_payment_id"],
                                           "sent_at": datetime.now(timezone.utc).isoformat()})
                transaction.update(reference, {"state": "sent", "lease": ""})
            else:
                delay = min(3600, 60 * 2 ** min(current["attempts"], 6))
                transaction.update(reference, {"lease": "", "next_attempt_at": time.time() + delay})

        commit(self.client, write)

    def reserve_intent(self, key: str, proposed: dict):
        reference = self.intents.ref(key)

        @firestore.transactional
        def write(transaction):
            record = reference.get(transaction=transaction, **RPC).to_dict()
            if record:
                return record
            transaction.create(reference, proposed)
            return proposed

        return commit(self.client, write)

    def save_intent(self, key: str, response: dict):
        self.intents.ref(key).update({"response": response}, **RPC)

    def allow_intent(self, limit: int):
        # ponytail: global budget bounds PSP sessions; use a trusted per-client edge limit if traffic grows.
        now = datetime.now(timezone.utc)
        reference = self.limits.document("intents-" + str(int(time.time() // 60)))

        @firestore.transactional
        def write(transaction):
            record = reference.get(transaction=transaction, **RPC).to_dict() or {"count": 0}
            if record["count"] >= limit:
                return False
            transaction.set(reference, {"count": record["count"] + 1, "expires_at": now + timedelta(days=1)})
            return True

        return commit(self.client, write)
