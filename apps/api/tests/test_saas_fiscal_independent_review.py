# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-fiscal-independent-review-v1
"""Independent R3 refutations for fiscal provider confirmation boundaries."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.invoicing.service import InvoicingService
from sqlalchemy.orm import Session
from test_saas_invoicing_audit import _configure, _insert_order


class _ExpiredReceiptClient:
    is_mock = False

    def create_receipt(self, _payload: dict[str, object]) -> dict[str, object]:
        return {"id": "provider-expired-receipt", "status": "expired"}


class _ConfirmedInvoiceClient:
    is_mock = False

    def __init__(self) -> None:
        self.calls = 0

    def create_invoice(self, _payload: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        return {
            "id": "provider-invoice",
            "status": "valid",
            "uuid": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
            "folio_number": "101",
        }

    def send_email(self, *_args: object) -> dict[str, object]:
        return {}


def test_receipt_creation_requires_open_provider_status_before_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_order(session, "org-a", "branch-a", "order-a")
        _configure(session, "org-a")
        monkeypatch.setattr(service, "get_client", lambda *_args: _ExpiredReceiptClient())

        with pytest.raises(RuntimeError):
            service.create_receipt_for_order(session, "org-a", "branch-a", "order-a")

        command = session.execute(sa.select(models.fiscal_commands)).mappings().one()
        assert command["status"] == "unknown"
        assert command["provider_resource_id"] == "provider-expired-receipt"
        actions = set(session.execute(sa.select(models.audit_events.c.action)).scalars())
        assert "cfdi.receipt.confirmed" not in actions
        assert "cfdi.receipt.failed" in actions


def test_confirmed_issue_replay_requires_the_same_receptor_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    client = _ConfirmedInvoiceClient()
    with Session(engine) as session:
        _insert_order(session, "org-a", "branch-a", "order-a")
        _configure(session, "org-a")
        monkeypatch.setattr(service, "get_client", lambda *_args: client)
        service.issue_invoice(
            session,
            "org-a",
            "branch-a",
            ["order-a"],
            {"rfc": "XAXX010101000", "legal_name": "PUBLICO EN GENERAL"},
        )

        with pytest.raises(ValueError):
            service.issue_invoice(
                session,
                "org-a",
                "branch-a",
                ["order-a"],
                {"rfc": "GOMR880101ABC", "legal_name": "PERSONA PRIVADA"},
            )

        assert client.calls == 1
