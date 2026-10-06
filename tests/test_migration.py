import json

import pytest

from tools.migrate_jsonl import load_source


def source(tmp_path):
    confirmation = {"donation_id": "synthetic", "provider_payment_id": "cs_test_payment", "status_token_hash": "a" * 64,
                    "method": "card", "program": "geral", "amount_cents": 10000, "confirmed_at": "2026-10-01T12:00:00+00:00"}
    donor = {**confirmation, "program_label": "Contribuição geral", "donor_name": "Synthetic Donor", "donor_email": "test@example.com",
             "donor_cpf": "52998224725", "communication_opt_in": False, "created_at": confirmation["confirmed_at"]}
    (tmp_path / "payment_confirmations.jsonl").write_text(json.dumps(confirmation) + "\n", encoding="utf-8")
    (tmp_path / "confirmed_donations.jsonl").write_text(json.dumps(donor) + "\n", encoding="utf-8")
    return confirmation, donor


def test_migration_validates_references_without_remote_connection(tmp_path):
    source(tmp_path)
    roots, invoices, donors, sent, outbox = load_source(tmp_path)
    assert len(roots) == len(donors) == 1
    assert not invoices and not sent and not outbox


@pytest.mark.parametrize("field,value", [("amount_cents", 5000), ("provider_payment_id", "cs_other"), ("donor_cpf", "11111111111")])
def test_migration_rejects_unconfirmed_or_invalid_donor(tmp_path, field, value):
    _, donor = source(tmp_path)
    donor[field] = value
    (tmp_path / "confirmed_donations.jsonl").write_text(json.dumps(donor), encoding="utf-8")
    with pytest.raises(ValueError):
        load_source(tmp_path)


def test_migration_rejects_mock_payments(tmp_path):
    confirmation, _ = source(tmp_path)
    confirmation["provider_payment_id"] = "mock_not_paid"
    (tmp_path / "payment_confirmations.jsonl").write_text(json.dumps(confirmation), encoding="utf-8")
    with pytest.raises(ValueError):
        load_source(tmp_path)


@pytest.mark.parametrize("field,value", [("amount_cents", -100), ("status_token_hash", "invalid")])
def test_migration_rejects_invalid_financial_record(tmp_path, field, value):
    confirmation, _ = source(tmp_path)
    confirmation[field] = value
    (tmp_path / "payment_confirmations.jsonl").write_text(json.dumps(confirmation), encoding="utf-8")
    with pytest.raises(ValueError):
        load_source(tmp_path)
