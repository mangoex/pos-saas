# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-audit-tests-v1
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.api import _actor_from_request
from restaurant_os.auth import create_session_token
from restaurant_os.config import Settings
from restaurant_os.domain.errors import StateTransitionError
from restaurant_os.domain.order_state_machine import OrderState, OrderStateMachine
from restaurant_os.operations import (
    BRANCH_ID,
    ORGANIZATION_ID,
    BusinessError,
    acknowledge_print_attempt,
    claim_print_attempt,
    receive_sync_command,
    retry_print_job,
)
from restaurant_os.platform_data import get_dashboard_overview
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

UTC = timezone.utc
CASH_SHIFT_ID = "audit-remediation-open-shift"


@pytest.fixture()
def session() -> Any:
    engine = sa.create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as database_session:
        now = datetime.now(UTC)
        database_session.execute(
            models.cash_shifts.insert().values(
                id=CASH_SHIFT_ID,
                organization_id=ORGANIZATION_ID,
                branch_id=BRANCH_ID,
                register_code="CAJA-01",
                status="OPEN",
                opening_cash_cents=0,
                opened_at=now,
                created_at=now,
            )
        )
        database_session.commit()
        yield database_session


def test_actor_from_request_rejects_header_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        environment="production",
        secret_key="prod-secret-for-test-only-1234567890",
    )
    monkeypatch.setattr("restaurant_os.api.get_settings", lambda: settings)

    # Header spoofing without token in production must return None
    actor = _actor_from_request("spoofed-admin-id", None)
    assert actor is None

    # Valid signed Bearer token in production must be resolved
    valid_token = create_session_token({"sub": "legit-user-id"}, settings.secret_key)
    resolved = _actor_from_request("spoofed-admin-id", f"Bearer {valid_token}")
    assert resolved == "legit-user-id"


def test_production_environment_is_normalized_before_secret_validation() -> None:
    with pytest.raises(ValueError, match="RESTAURANTOS_SECRET_KEY"):
        Settings(environment=" Production ")
    with pytest.raises(ValueError, match="at least 32"):
        Settings(environment="production", secret_key="too-short")
    assert Settings(environment="TEST").environment == "test"
    with pytest.raises(ValueError, match="RESTAURANTOS_ENVIRONMENT"):
        Settings(environment="staging-ish", secret_key="not-the-default")


def test_retry_print_job_resets_to_pending(session: Any) -> None:
    job_id = str(uuid.uuid4())
    order_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    # Insert an order for foreign key constraint
    session.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=ORGANIZATION_ID,
                branch_id=BRANCH_ID,
                cash_shift_id=CASH_SHIFT_ID,
            folio="PILOTO-999901",
            order_type="dine_in",
            channel="pos",
            status="ACCEPTED",
                total_cents=10000,
                created_at=now,
        )
    )
    session.execute(
            models.print_jobs.insert().values(
                id=job_id,
                organization_id=ORGANIZATION_ID,
                branch_id=BRANCH_ID,
                order_id=order_id,
            job_type="receipt",
            target="ticket_printer",
            status="FAILED",
            payload={"test": True},
            attempts=1,
            last_error="Printer offline",
            created_at=now,
        )
    )
    session.commit()

    retried = retry_print_job(session, job_id, "retry-audit-001", BRANCH_ID)
    assert retried["job"]["status"] == "QUEUED"
    assert retried["job"]["attempts"] == 2
    attempt = claim_print_attempt(session, retried["attempt"]["id"], "printer-device")
    assert attempt["status"] == "CLAIMED"
    completed = acknowledge_print_attempt(
        session, attempt["id"], "printer-device", "printed"
    )
    assert completed["status"] == "PRINTED"


def test_sync_command_fails_closed_without_an_atomic_domain_executor(session: Any) -> None:
    now = datetime.now(UTC).isoformat()
    envelope1 = {
        "schema_version": "1.0",
        "organization_id": ORGANIZATION_ID,
        "branch_id": BRANCH_ID,
        "source_device_id": "pos-terminal-1",
        "command_id": "cmd-001",
        "idempotency_key": "sync-idempotency-key-001",
        "command_type": "order.created",
        "occurred_at": now,
        "payload": {"order_id": "ord-1", "total_cents": 5000},
    }

    with pytest.raises(BusinessError) as exc:
        receive_sync_command(
            session, envelope1, ORGANIZATION_ID, BRANCH_ID, "pos-terminal-1"
        )
    assert exc.value.code == "unsupported_sync_command"


def test_sync_command_rejects_unsupported_command_type(session: Any) -> None:
    now = datetime.now(UTC).isoformat()
    invalid_envelope = {
        "schema_version": "1.0",
        "organization_id": ORGANIZATION_ID,
        "branch_id": BRANCH_ID,
        "source_device_id": "pos-terminal-1",
        "command_id": "cmd-bad",
        "idempotency_key": "sync-idempotency-key-invalid",
        "command_type": "arbitrary.unauthorized.command",
        "occurred_at": now,
        "payload": {"ignored": True},
    }

    with pytest.raises(BusinessError) as exc:
        receive_sync_command(
            session,
            invalid_envelope,
            ORGANIZATION_ID,
            BRANCH_ID,
            "pos-terminal-1",
        )
    assert exc.value.code == "unsupported_sync_command"


def test_order_state_machine_transitions() -> None:
    # Valid transitions
    assert OrderStateMachine.transition(
        OrderState.DRAFT, OrderState.ACCEPTED
    ) == OrderState.ACCEPTED
    assert OrderStateMachine.transition(
        OrderState.ACCEPTED, OrderState.CANCELLED
    ) == OrderState.CANCELLED
    assert OrderStateMachine.transition(
        OrderState.READY, OrderState.DELIVERED
    ) == OrderState.DELIVERED

    # Invalid transitions must raise StateTransitionError
    with pytest.raises(StateTransitionError):
        OrderStateMachine.transition(OrderState.CLOSED, OrderState.ACCEPTED)

    with pytest.raises(StateTransitionError):
        OrderStateMachine.transition(OrderState.CANCELLED, OrderState.READY)


def test_dashboard_overview_revenue_only_counts_confirmed_payments(session: Any) -> None:
    now = datetime.now(UTC)
    order_id = str(uuid.uuid4())
    session.execute(
        models.orders.insert().values(
                id=order_id,
                organization_id=ORGANIZATION_ID,
                branch_id=BRANCH_ID,
                cash_shift_id=CASH_SHIFT_ID,
                folio="PILOTO-999902",
            order_type="dine_in",
            channel="pos",
            status="ACCEPTED",
                total_cents=25000,
                created_at=now,
        )
    )
    # Payment not yet confirmed (PENDING)
    payment_id = str(uuid.uuid4())
    session.execute(
        models.payments.insert().values(
            id=payment_id,
            organization_id=ORGANIZATION_ID,
                branch_id=BRANCH_ID,
                order_id=order_id,
                cash_shift_id=CASH_SHIFT_ID,
                amount_cents=25000,
                method="CASH",
                status="PENDING",
                confirmed_at=now,
                created_at=now,
        )
    )
    session.commit()

    overview = get_dashboard_overview(session, organization_id=ORGANIZATION_ID)
    # Revenue must not include unconfirmed payments
    # (Only confirmed payments count towards total_revenue_cents)
    assert isinstance(overview["total_revenue_cents"], int)
    assert overview["total_revenue_cents"] == 0
    assert "order_types" in overview
    assert "mostrador" in overview["order_types"]
