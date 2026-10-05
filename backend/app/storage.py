from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from .models import ConfirmedDonationRecord, PaymentConfirmation, PendingDonation


class JsonlStore:
    def __init__(self, path: Path, id_field: str):
        self.path = path
        self.id_field = id_field
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                record_id = str(record[self.id_field])
                self._index[record_id] = record
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError("Arquivo local de pagamentos corrompido; restaure-o antes de iniciar.") from exc

    def get(self, record_id: str) -> dict[str, Any] | None:
        return self._index.get(record_id)

    def contains(self, record_id: str) -> bool:
        return record_id in self._index

    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._index.values())

    def append_once(self, record: dict[str, Any]) -> bool:
        record_id = str(record[self.id_field])
        with self._lock:
            if record_id in self._index:
                return False
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0), 0o600)
            with os.fdopen(descriptor, "a+b") as handle:
                offset = handle.tell()
                try:
                    handle.write((json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
                    handle.flush()
                    os.fsync(handle.fileno())
                except OSError:
                    handle.truncate(offset)
                    handle.flush()
                    raise
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            self._index[record_id] = record
            return True


class PendingDonationStore:
    def __init__(self) -> None:
        self._records: dict[str, PendingDonation] = {}
        self._provider_index: dict[str, str] = {}
        self._lock = threading.Lock()

    def put(self, pending: PendingDonation) -> None:
        with self._lock:
            self._cleanup_locked()
            self._records[pending.donation_id] = pending
            self._provider_index[pending.provider_payment_id] = pending.donation_id

    def get(self, donation_id: str) -> PendingDonation | None:
        with self._lock:
            self._cleanup_locked()
            return self._records.get(donation_id)

    def get_by_provider_id(self, provider_payment_id: str) -> PendingDonation | None:
        with self._lock:
            self._cleanup_locked()
            donation_id = self._provider_index.get(provider_payment_id)
            return self._records.get(donation_id) if donation_id else None

    def update_status(self, donation_id: str, status: str) -> PendingDonation | None:
        with self._lock:
            pending = self._records.get(donation_id)
            if pending:
                pending.provider_status = status
            return pending

    def remove(self, donation_id: str) -> None:
        with self._lock:
            pending = self._records.pop(donation_id, None)
            if pending:
                self._provider_index.pop(pending.provider_payment_id, None)

    def _cleanup_locked(self) -> None:
        now = time.time()
        expired = [donation_id for donation_id, record in self._records.items() if record.expires_at_epoch <= now]
        for donation_id in expired:
            record = self._records.pop(donation_id, None)
            if record:
                self._provider_index.pop(record.provider_payment_id, None)


class PaymentConfirmationStore(JsonlStore):
    def __init__(self, path: Path):
        super().__init__(path, "donation_id")

    def get_model(self, donation_id: str) -> PaymentConfirmation | None:
        record = self.get(donation_id)
        return PaymentConfirmation.model_validate(record) if record else None


class ConfirmedDonationStore(JsonlStore):
    def __init__(self, path: Path):
        super().__init__(path, "donation_id")

    def get_model(self, donation_id: str) -> ConfirmedDonationRecord | None:
        record = self.get(donation_id)
        return ConfirmedDonationRecord.model_validate(record) if record else None
