# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-invoicing-audit-synthetic-v1
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.invoicing.service import InvoicingService
from sqlalchemy.orm import Session


def _insert_order(session: Session, organization_id: str, branch_id: str, order_id: str) -> None:
    session.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=organization_id,
            branch_id=branch_id,
            folio=f"AUDIT-{order_id}",
            order_type="dine_in",
            channel="UBER_EATS",
            status="completed",
            total_cents=12000,
            currency="MXN",
            payment_method_intent="cash",
            version=1,
            created_at=datetime.now(timezone.utc),
        )
    )


class _ConfirmedClient:
    is_mock = False

    def create_invoice(self, _payload: dict[str, object]) -> dict[str, object]:
        return {
            "id": "provider-invoice-id",
            "status": "valid",
            "uuid": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
            "folio_number": "101",
        }

    def send_email(self, *_args: object) -> dict[str, object]:
        return {}


def test_confirmed_issuance_audits_real_support_actor_without_fiscal_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_order(session, "org-a", "branch-a", "order-a")
        service.save_config(
            session,
            "org-a",
            {"is_enabled": True, "environment": "sandbox", "api_key": "sk_test_live_fake"},
        )
        session.info["support_audit_context"] = {
            "target_organization_id": "org-a",
            "real_actor_user_id": "support-admin",
            "effective_actor_user_id": "tenant-owner",
            "correlation_id": "4f35055f-e4ae-46e5-8dd3-4f01011a3590",
        }
        monkeypatch.setattr(service, "get_client", lambda *_args: _ConfirmedClient())

        service.issue_invoice(
            session,
            "org-a",
            "branch-a",
            ["order-a"],
            {"rfc": "GOMR880101ABC", "legal_name": "PERSONA PRIVADA", "email": "private@test"},
            actor_user_id="tenant-owner",
        )

        event = (
            session.execute(
                sa.select(models.audit_events).where(
                    models.audit_events.c.action == "cfdi.issue.confirmed"
                )
            )
            .mappings()
            .one()
        )
        assert event["organization_id"] == "org-a"
        assert event["actor_user_id"] == "support-admin"
        assert event["correlation_id"] == "4f35055f-e4ae-46e5-8dd3-4f01011a3590"
        assert event["payload"] == {
            "outcome": "confirmed",
            "provider_confirmation": "confirmed",
            "order_count": 1,
            "effective_actor_user_id": "tenant-owner",
        }


class _ReceiptClient:
    is_mock = False

    def create_receipt(self, _payload: dict[str, object]) -> dict[str, object]:
        return {
            "id": "provider-receipt-id",
            "status": "open",
            "self_invoice_url": "https://provider.invalid/r",
        }


class _CountingReceiptClient(_ReceiptClient):
    def __init__(self) -> None:
        self.calls = 0

    def create_receipt(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        return super().create_receipt(payload)


class _CancellationClient:
    is_mock = False

    def cancel_invoice(self, *_args: object) -> dict[str, object]:
        return {"status": "cancelled"}


class _CountingCancellationClient(_CancellationClient):
    def __init__(self) -> None:
        self.calls = 0

    def cancel_invoice(self, *args: object) -> dict[str, object]:
        self.calls += 1
        return super().cancel_invoice(*args)


class _FailingClient:
    is_mock = False

    def create_invoice(self, _payload: dict[str, object]) -> dict[str, object]:
        raise TimeoutError("provider response was not received")

    def create_receipt(self, _payload: dict[str, object]) -> dict[str, object]:
        raise TimeoutError("provider response was not received")


def _configure(session: Session, organization_id: str) -> None:
    InvoicingService().save_config(
        session,
        organization_id,
        {"is_enabled": True, "environment": "sandbox", "api_key": "sk_test_live_fake"},
    )


def test_receipt_and_cancel_audit_only_after_fake_provider_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_order(session, "org-a", "branch-a", "order-a")
        _configure(session, "org-a")
        monkeypatch.setattr(service, "get_client", lambda *_args: _ReceiptClient())
        service.create_receipt_for_order(
            session, "org-a", "branch-a", "order-a", actor_user_id="owner-a"
        )
        receipt_event = session.execute(
            sa.select(models.audit_events.c.payload).where(
                models.audit_events.c.action == "cfdi.receipt.confirmed"
            )
        ).scalar_one()
        assert receipt_event["provider_confirmation"] == "confirmed"

        monkeypatch.setattr(service, "get_client", lambda *_args: _ConfirmedClient())
        issued = service.issue_invoice(
            session, "org-a", "branch-a", ["order-a"], {}, actor_user_id="owner-a"
        )
        monkeypatch.setattr(service, "get_client", lambda *_args: _CancellationClient())
        service.cancel_invoice(session, "org-a", issued["id"], actor_user_id="owner-a")
        assert session.execute(
            sa.select(models.audit_events.c.id).where(
                models.audit_events.c.action == "cfdi.cancel.confirmed"
            )
        ).one()


def test_simulation_and_provider_failure_are_explicitly_audited_without_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_order(session, "org-a", "branch-a", "order-a")
        service.save_config(
            session,
            "org-a",
            {"is_enabled": True, "environment": "sandbox", "api_key": "sk_test_mock_explicit"},
        )
        simulated = service.issue_invoice(
            session, "org-a", "branch-a", ["order-a"], {}, actor_user_id="owner-a"
        )
        assert simulated["status"] == "simulated"
        simulation_event = session.execute(
            sa.select(models.audit_events.c.payload).where(
                models.audit_events.c.action == "cfdi.issue.simulated"
            )
        ).scalar_one()
        assert simulation_event["provider_confirmation"] == "not_requested"
        assert session.execute(sa.select(models.cfdi_invoices.c.id)).all() == []

        _configure(session, "org-a")
        monkeypatch.setattr(service, "get_client", lambda *_args: _FailingClient())
        with pytest.raises(TimeoutError):
            service.issue_invoice(session, "org-a", "branch-a", ["order-a"], {})
        failed_event = session.execute(
            sa.select(models.audit_events.c.payload).where(
                models.audit_events.c.action == "cfdi.issue.failed"
            )
        ).scalar_one()
        assert failed_event["provider_confirmation"] == "unknown"
        assert session.execute(sa.select(models.cfdi_invoices.c.id)).all() == []


class _FailingCancellationClient:
    is_mock = False

    def cancel_invoice(self, *_args: object) -> dict[str, object]:
        raise TimeoutError("provider response was not received")


def _insert_issued_invoice(session: Session, invoice_id: str) -> None:
    session.execute(
        models.cfdi_invoices.insert().values(
            id=invoice_id,
            organization_id="org-a",
            branch_id="branch-a",
            order_id=None,
            facturapi_invoice_id="provider-id",
            folio_number="F-1",
            rfc_emisor="AAA010101AAA",
            rfc_receptor="XAXX010101000",
            nombre_receptor="PUBLICO EN GENERAL",
            codigo_postal_receptor="00000",
            regimen_fiscal_receptor="616",
            uso_cfdi="S01",
            forma_pago_sat="01",
            metodo_pago_sat="PUE",
            total_cents=12000,
            currency="MXN",
            status="issued",
            created_at=datetime.now(timezone.utc),
        )
    )
    session.commit()


def test_receipt_and_cancel_simulation_or_error_never_report_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_order(session, "org-a", "branch-a", "order-a")
        _insert_issued_invoice(session, "invoice-a")
        service.save_config(
            session,
            "org-a",
            {"is_enabled": True, "environment": "sandbox", "api_key": "sk_test_mock_explicit"},
        )
        assert (
            service.create_receipt_for_order(session, "org-a", "branch-a", "order-a")["status"]
            == "simulated"
        )
        assert service.cancel_invoice(session, "org-a", "invoice-a")["status"] == "simulated"
        actions = set(session.execute(sa.select(models.audit_events.c.action)).scalars())
        assert {"cfdi.receipt.simulated", "cfdi.cancel.simulated"} <= actions

        _configure(session, "org-a")
        monkeypatch.setattr(service, "get_client", lambda *_args: _FailingClient())
        with pytest.raises(TimeoutError):
            service.create_receipt_for_order(session, "org-a", "branch-a", "order-a")
        monkeypatch.setattr(service, "get_client", lambda *_args: _FailingCancellationClient())
        with pytest.raises(TimeoutError):
            service.cancel_invoice(session, "org-a", "invoice-a")
        failed = dict(
            session.execute(
                sa.select(models.audit_events.c.action, models.audit_events.c.payload).where(
                    models.audit_events.c.action.in_(["cfdi.receipt.failed", "cfdi.cancel.failed"])
                )
            ).all()
        )
        assert all(payload["provider_confirmation"] == "unknown" for payload in failed.values())
        assert (
            session.execute(
                sa.select(models.cfdi_invoices.c.status).where(
                    models.cfdi_invoices.c.id == "invoice-a"
                )
            ).scalar_one()
            == "issued"
        )


class _CountingConfirmedClient(_ConfirmedClient):
    def __init__(self) -> None:
        self.calls = 0

    def create_invoice(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls += 1
        return super().create_invoice(payload)


def test_issue_commit_failure_becomes_unknown_and_retry_does_not_reemit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_order(session, "org-a", "branch-a", "order-a")
        _configure(session, "org-a")
        client = _CountingConfirmedClient()
        monkeypatch.setattr(service, "get_client", lambda *_args: client)
        original_commit = session.commit
        fail_once = True

        def fail_after_provider_confirmation() -> None:
            nonlocal fail_once
            if client.calls == 1 and fail_once:
                fail_once = False
                raise RuntimeError("injected commit failure")
            original_commit()

        monkeypatch.setattr(session, "commit", fail_after_provider_confirmation)
        with pytest.raises(RuntimeError, match="injected commit failure"):
            service.issue_invoice(session, "org-a", "branch-a", ["order-a"], {})
        monkeypatch.setattr(session, "commit", original_commit)

        command = session.execute(sa.select(models.fiscal_commands)).mappings().one()
        assert command["status"] == "unknown"
        assert command["provider_resource_id"] == "provider-invoice-id"
        assert session.execute(sa.select(models.cfdi_invoices.c.id)).all() == []
        with pytest.raises(ValueError, match="reconciliación"):
            service.issue_invoice(session, "org-a", "branch-a", ["order-a"], {"rfc": "NEW"})
        assert client.calls == 1


class _ReconciliationClient:
    is_mock = False

    def __init__(self) -> None:
        self.lookup_calls = 0

    def get_invoice(self, _invoice_id: str) -> dict[str, object]:
        self.lookup_calls += 1
        return {
            "id": "provider-invoice-id",
            "status": "valid",
            "uuid": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
        }


def test_inflight_or_unknown_issue_requires_explicit_reconciliation_before_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_order(session, "org-a", "branch-a", "order-a")
        _configure(session, "org-a")
        command = service._prepare_issue_command(
            session,
            organization_id="org-a",
            branch_id="branch-a",
            order_ids=["order-a"],
            receptor={},
            invoice_draft={},
            actor_user_id="owner-a",
        )
        client = _CountingConfirmedClient()
        monkeypatch.setattr(service, "get_client", lambda *_args: client)
        with pytest.raises(ValueError, match="reconciliación"):
            service.issue_invoice(session, "org-a", "branch-a", ["order-a"], {})
        assert client.calls == 0
        session.execute(
            models.fiscal_commands.update()
            .where(models.fiscal_commands.c.id == command["id"])
            .values(status="unknown", provider_resource_id=None)
        )
        session.commit()
        pending = service.reconcile_issue_command(session, "org-a", command["id"])
        assert pending == {
            "status": "unknown",
            "provider_resource_known": False,
            "reconciliation_required": True,
        }


def test_reconciliation_queries_known_resource_without_marking_unknown_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_order(session, "org-a", "branch-a", "order-a")
        command = service._prepare_issue_command(
            session,
            organization_id="org-a",
            branch_id="branch-a",
            order_ids=["order-a"],
            receptor={},
            invoice_draft={
                "rfc_emisor": "AAA010101AAA",
                "rfc_receptor": "XAXX010101000",
                "nombre_receptor": "PUBLICO EN GENERAL",
                "codigo_postal_receptor": "00000",
                "regimen_fiscal_receptor": "616",
                "uso_cfdi": "S01",
                "forma_pago_sat": "01",
                "metodo_pago_sat": "PUE",
                "total_cents": 12000,
                "series": "F",
            },
            actor_user_id="owner-a",
        )
        session.execute(
            models.fiscal_commands.update()
            .where(models.fiscal_commands.c.id == command["id"])
            .values(status="unknown", provider_resource_id="provider-invoice-id")
        )
        session.commit()
        client = _ReconciliationClient()
        monkeypatch.setattr(service, "get_client", lambda *_args: client)
        result = service.reconcile_issue_command(session, "org-a", command["id"])
        assert result["status"] == "confirmed"
        assert result["reconciliation_required"] is False
        assert client.lookup_calls == 1
        assert (
            session.execute(
                sa.select(models.fiscal_commands.c.status).where(
                    models.fiscal_commands.c.id == command["id"]
                )
            ).scalar_one()
            == "confirmed"
        )


def test_confirmed_claim_returns_exact_replay_but_blocks_overlapping_orders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        for order_id in ("order-a", "order-b", "order-c"):
            _insert_order(session, "org-a", "branch-a", order_id)
        _configure(session, "org-a")
        client = _CountingConfirmedClient()
        monkeypatch.setattr(service, "get_client", lambda *_args: client)
        confirmed = service.issue_invoice(session, "org-a", "branch-a", ["order-a", "order-b"], {})
        replay = service.issue_invoice(session, "org-a", "branch-a", ["order-b", "order-a"], {})
        assert replay["id"] == confirmed["id"]
        assert client.calls == 1
        with pytest.raises(ValueError, match="ya fueron facturados"):
            service.issue_invoice(session, "org-a", "branch-a", ["order-b", "order-c"], {})
        assert client.calls == 1


class _ResourceReconciliationClient:
    is_mock = False

    def __init__(self, *, receipt_status: str = "open", cancel_status: str = "cancelled") -> None:
        self.receipt_status = receipt_status
        self.cancel_status = cancel_status
        self.receipt_lookups = 0
        self.invoice_lookups = 0

    def get_receipt(self, receipt_id: str) -> dict[str, object]:
        self.receipt_lookups += 1
        return {"id": receipt_id, "status": self.receipt_status}

    def get_invoice(self, invoice_id: str) -> dict[str, object]:
        self.invoice_lookups += 1
        return {"id": invoice_id, "status": self.cancel_status}


class _TimeoutResourceReconciliationClient:
    is_mock = False

    def get_receipt(self, _receipt_id: str) -> dict[str, object]:
        raise TimeoutError("provider lookup timed out")


def test_receipt_commit_failure_stays_unknown_until_provider_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_order(session, "org-a", "branch-a", "order-a")
        _configure(session, "org-a")
        client = _CountingReceiptClient()
        monkeypatch.setattr(service, "get_client", lambda *_args: client)
        original_commit = session.commit
        fail_once = True

        def fail_after_receipt_confirmation() -> None:
            nonlocal fail_once
            if client.calls == 1 and fail_once:
                fail_once = False
                raise RuntimeError("injected receipt commit failure")
            original_commit()

        monkeypatch.setattr(session, "commit", fail_after_receipt_confirmation)
        with pytest.raises(RuntimeError, match="injected receipt commit failure"):
            service.create_receipt_for_order(session, "org-a", "branch-a", "order-a")
        monkeypatch.setattr(session, "commit", original_commit)

        command = session.execute(sa.select(models.fiscal_commands)).mappings().one()
        assert command["status"] == "unknown"
        assert command["provider_resource_id"] == "provider-receipt-id"
        with pytest.raises(ValueError, match="reconciliación"):
            service.create_receipt_for_order(session, "org-a", "branch-a", "order-a")
        assert client.calls == 1

        reconciler = _ResourceReconciliationClient()
        monkeypatch.setattr(service, "get_client", lambda *_args: reconciler)
        result = service.reconcile_resource_command(session, "org-a", command["id"])
        assert result == {"status": "confirmed", "reconciliation_required": False}
        assert reconciler.receipt_lookups == 1
        replay = service.create_receipt_for_order(session, "org-a", "branch-a", "order-a")
        assert replay["status"] == "open"
        assert reconciler.receipt_lookups == 1


def test_cancel_commit_failure_reconciles_before_a_retry_can_return_confirmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        _insert_issued_invoice(session, "invoice-a")
        _configure(session, "org-a")
        client = _CountingCancellationClient()
        monkeypatch.setattr(service, "get_client", lambda *_args: client)
        original_commit = session.commit
        fail_once = True

        def fail_after_cancel_confirmation() -> None:
            nonlocal fail_once
            if client.calls == 1 and fail_once:
                fail_once = False
                raise RuntimeError("injected cancellation commit failure")
            original_commit()

        monkeypatch.setattr(session, "commit", fail_after_cancel_confirmation)
        with pytest.raises(RuntimeError, match="injected cancellation commit failure"):
            service.cancel_invoice(session, "org-a", "invoice-a", motive="01")
        monkeypatch.setattr(session, "commit", original_commit)

        command = session.execute(sa.select(models.fiscal_commands)).mappings().one()
        assert command["status"] == "unknown"
        assert command["provider_resource_id"] == "provider-id"
        assert service.get_invoice_detail(session, "org-a", "invoice-a")["status"] == "issued"
        with pytest.raises(ValueError, match="reconciliación"):
            service.cancel_invoice(session, "org-a", "invoice-a", motive="01")
        assert client.calls == 1

        reconciler = _ResourceReconciliationClient()
        monkeypatch.setattr(service, "get_client", lambda *_args: reconciler)
        result = service.reconcile_resource_command(session, "org-a", command["id"])
        assert result["status"] == "confirmed"
        assert reconciler.invoice_lookups == 1
        replay = service.cancel_invoice(session, "org-a", "invoice-a", motive="01")
        assert replay["status"] == "cancelled"
        assert reconciler.invoice_lookups == 1


def test_unknown_resource_command_without_provider_id_or_confirming_status_is_not_reemitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        command = service._prepare_resource_command(
            session,
            organization_id="org-a",
            branch_id="branch-a",
            operation="receipt",
            target_id="order-a",
            snapshot={},
            actor_user_id="owner-a",
        )
        session.execute(
            models.fiscal_commands.update()
            .where(models.fiscal_commands.c.id == command["id"])
            .values(status="unknown", provider_resource_id=None)
        )
        session.commit()
        assert service.reconcile_resource_command(session, "org-a", command["id"]) == {
            "status": "unknown",
            "provider_resource_known": False,
            "reconciliation_required": True,
        }

        session.execute(
            models.fiscal_commands.update()
            .where(models.fiscal_commands.c.id == command["id"])
            .values(provider_resource_id="provider-receipt-id")
        )
        session.commit()
        reconciler = _ResourceReconciliationClient(receipt_status="expired")
        monkeypatch.setattr(service, "get_client", lambda *_args: reconciler)
        result = service.reconcile_resource_command(session, "org-a", command["id"])
        assert result["status"] == "unknown"
        assert result["reconciliation_required"] is True
        assert reconciler.receipt_lookups == 1
        assert (
            session.execute(
                sa.select(models.fiscal_commands.c.status).where(
                    models.fiscal_commands.c.id == command["id"]
                )
            ).scalar_one()
            == "unknown"
        )


def test_reconciliation_timeout_keeps_receipt_unknown_without_a_second_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = sa.create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    service = InvoicingService()
    with Session(engine) as session:
        command = service._prepare_resource_command(
            session,
            organization_id="org-a",
            branch_id="branch-a",
            operation="receipt",
            target_id="order-a",
            snapshot={},
            actor_user_id="owner-a",
        )
        session.execute(
            models.fiscal_commands.update()
            .where(models.fiscal_commands.c.id == command["id"])
            .values(status="unknown", provider_resource_id="provider-receipt-id")
        )
        session.commit()
        monkeypatch.setattr(
            service, "get_client", lambda *_args: _TimeoutResourceReconciliationClient()
        )
        with pytest.raises(TimeoutError, match="lookup timed out"):
            service.reconcile_resource_command(session, "org-a", command["id"])
        assert (
            session.execute(
                sa.select(models.fiscal_commands.c.status).where(
                    models.fiscal_commands.c.id == command["id"]
                )
            ).scalar_one()
            == "unknown"
        )
