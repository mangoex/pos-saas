"""PCO-004 operational-close regression tests."""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    AuthorizationError,
    BusinessError,
    close_cash_shift_operationally,
    create_local_order,
    open_cash_shift,
    open_cash_shift_idempotently,
    pay_order,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from test_cash_ledger import BRANCH_A, CASHIER_ID, CASHIER_ROLE_ID, NOW, SHIFT_ID, _new_session
from test_pco004_contracts import _validators
from test_platform_api import (
    ADMIN_ROLE_ID,
    ADMIN_USER_ID,
    _admin_headers,
    _client_with_seeded_database,
    _open_shift,
    _seed,
)


def test_operational_close_freezes_summary_without_legacy_cut() -> None:
    engine, session = _new_session()
    try:
        result = close_cash_shift_operationally(session, SHIFT_ID, "close-001", CASHIER_ID)
        assert result["cash_shift"]["status"] == "OPERATIVELY_CLOSED"
        assert result["closure"]["summary_snapshot"]["opening_cash_cents"] == 10_000
        assert result["closure"]["summary_snapshot"]["cash_payment_cents"] == 0
        serializable = {
            "cash_shift": {key: value.isoformat() if hasattr(value, "isoformat") else value
                           for key, value in result["cash_shift"].items()},
            "closure": {key: value.isoformat() if hasattr(value, "isoformat") else value
                        for key, value in result["closure"].items()},
        }
        assert not list(
            _validators()["cash-shift-operational-close-response-v1.schema.json"].iter_errors(serializable)
        )
        assert session.execute(sa.select(models.cash_shift_cuts)).all() == []
    finally:
        session.close()
        engine.dispose()


def test_operational_close_http_response_uses_rfc3339_utc_timestamps() -> None:
    client = _client_with_seeded_database()
    opened = _open_shift(client, 0)
    assert opened.status_code == 200
    cash_shift_id = opened.json()["id"]

    response = client.post(
        f"/api/v1/cash/shifts/{cash_shift_id}/close-operationally",
        headers={**_admin_headers(), "Idempotency-Key": "http-operational-close"},
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert not list(
        _validators()["cash-shift-operational-close-response-v1.schema.json"].iter_errors(body)
    )
    assert body["cash_shift"]["opened_at"].endswith("Z")
    assert body["cash_shift"]["closed_at"].endswith("Z")
    assert body["closure"]["created_at"].endswith("Z")


def test_cash_shift_http_read_responses_are_rfc3339_and_schema_valid() -> None:
    client = _client_with_seeded_database()
    headers = {**_admin_headers(), "Idempotency-Key": "http-open-read"}
    opened = client.post(
        "/api/v1/cash/shifts/open",
        headers=headers,
        json={"branch_id": BRANCH_A, "register_id": "CAJA-01", "opening_cash_cents": 0},
    )
    assert opened.status_code == 200
    replay = client.post(
        "/api/v1/cash/shifts/open",
        headers=headers,
        json={"branch_id": BRANCH_A, "register_id": "CAJA-01", "opening_cash_cents": 0},
    )
    assert replay.status_code == 200
    assert opened.json()["opened_at"].endswith("Z")
    assert replay.json()["opened_at"].endswith("Z")

    current = client.get(
        "/api/v1/cash/shifts/current",
        headers=_admin_headers(),
        params={"branch_id": BRANCH_A, "register_id": "CAJA-01"},
    )
    listed = client.get(
        "/api/v1/cash/shifts",
        headers=_admin_headers(),
        params={"branch_id": BRANCH_A, "limit": 1},
    )
    detail = client.get(f"/api/v1/cash/shifts/{opened.json()['id']}", headers=_admin_headers())
    for response, schema_name in (
        (current, "cash-shift-current-v1.schema.json"),
        (listed, "cash-shift-list-v1.schema.json"),
        (detail, "cash-shift-detail-v1.schema.json"),
    ):
        assert response.status_code == 200
        assert not list(_validators()[schema_name].iter_errors(response.json()))
    assert current.json()["cash_shift"]["opened_at"].endswith("Z")
    assert listed.json()["items"][0]["opened_at"].endswith("Z")
    assert detail.json()["cash_shift"]["opened_at"].endswith("Z")
    invalid_cursor = client.get(
        "/api/v1/cash/shifts",
        headers=_admin_headers(),
        params={"branch_id": BRANCH_A, "cursor": "garbage"},
    )
    assert invalid_cursor.status_code == 409
    assert invalid_cursor.json()["detail"]["code"] == "cash_shift_cursor_invalid"
    invalid_cursor_id = client.get(
        "/api/v1/cash/shifts",
        headers=_admin_headers(),
        params={
            "branch_id": BRANCH_A,
            "cursor": "2026-08-12T00:00:00Z|not-a-uuid",
        },
    )
    assert invalid_cursor_id.status_code == 409
    assert invalid_cursor_id.json()["detail"]["code"] == "cash_shift_cursor_invalid"


def test_cash_shift_list_paginates_stably_without_duplicates_or_omissions() -> None:
    client = _client_with_seeded_database()
    opened_ids = []
    for suffix in ("02", "03", "04"):
        response = client.post(
            "/api/v1/cash/shifts/open",
            headers={**_admin_headers(), "Idempotency-Key": f"pagination-{suffix}"},
            json={
                "branch_id": BRANCH_A,
                "register_id": f"CAJA-{suffix}",
                "opening_cash_cents": 0,
            },
        )
        assert response.status_code == 200
        opened_ids.append(response.json()["id"])
        # One actor may hold only one open shift; pagination includes closed shifts.
        closed = client.post(
            f"/api/v1/cash/shifts/{opened_ids[-1]}/close-operationally",
            headers={**_admin_headers(), "Idempotency-Key": f"pagination-close-{suffix}"},
            json={},
        )
        assert closed.status_code == 200, closed.text

    first_page = client.get(
        "/api/v1/cash/shifts",
        headers=_admin_headers(),
        params={"branch_id": BRANCH_A, "limit": 1},
    )
    assert first_page.status_code == 200
    assert first_page.json()["next_cursor"]
    second_page = client.get(
        "/api/v1/cash/shifts",
        headers=_admin_headers(),
        params={"branch_id": BRANCH_A, "limit": 1, "cursor": first_page.json()["next_cursor"]},
    )
    third_page = client.get(
        "/api/v1/cash/shifts",
        headers=_admin_headers(),
        params={"branch_id": BRANCH_A, "limit": 1, "cursor": second_page.json()["next_cursor"]},
    )
    assert second_page.status_code == 200
    assert third_page.status_code == 200
    listed_ids = [
        first_page.json()["items"][0]["id"],
        second_page.json()["items"][0]["id"],
        third_page.json()["items"][0]["id"],
    ]
    assert set(listed_ids) == set(opened_ids)
    assert len(listed_ids) == len(set(listed_ids))
    invalid_limit = client.get(
        "/api/v1/cash/shifts",
        headers=_admin_headers(),
        params={"branch_id": BRANCH_A, "limit": 101},
    )
    assert invalid_limit.status_code == 409
    assert invalid_limit.json()["detail"]["code"] == "cash_shift_list_invalid"


def test_legacy_operational_close_alias_replays_lost_response_and_rechecks_permission() -> None:
    client = _client_with_seeded_database()
    opened = _open_shift(client, 0)
    assert opened.status_code == 200
    headers = {**_admin_headers(), "Idempotency-Key": "legacy-close-replay"}
    payload = {"branch_id": BRANCH_A, "register_id": "CAJA-01"}
    first = client.post("/api/v1/cash-shifts/close", headers=headers, json=payload)
    replay = client.post("/api/v1/cash-shifts/close", headers=headers, json=payload)
    lost_response_replay = client.post("/api/v1/cash-shifts/close", headers=headers, json=payload)
    assert first.status_code == replay.status_code == lost_response_replay.status_code == 200
    assert replay.json()["closure"]["id"] == first.json()["closure"]["id"]
    assert lost_response_replay.json() == replay.json()
    conflict = client.post(
        "/api/v1/cash-shifts/close",
        headers=headers,
        json={"branch_id": BRANCH_A, "register_id": "CAJA-02"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"
    factory = client.app.state.test_session_factory
    with factory() as session:
        permission_id = session.execute(sa.select(models.permissions.c.id).where(
            models.permissions.c.code == "cash.shift.close"
        )).scalar_one()
        session.execute(models.role_permissions.delete().where(
            models.role_permissions.c.role_id == ADMIN_ROLE_ID,
            models.role_permissions.c.permission_id == permission_id,
        ))
        session.commit()
    revoked = client.post("/api/v1/cash-shifts/close", headers=headers, json=payload)
    assert revoked.status_code == 403
    assert revoked.json()["detail"]["code"] == "permission_denied"


def test_sales_monitor_http_outputs_validate_schemas_and_utc_timestamps() -> None:
    client = _client_with_seeded_database()
    factory = client.app.state.test_session_factory
    with factory() as session:
        permission_id = "018f6f73-2d0a-74f0-8f1c-000000008071"
        session.execute(models.permissions.insert().values(
            id=permission_id,
            code="reports.sales.read",
            description="sales monitor",
            created_at=NOW,
        ))
        session.execute(models.role_permissions.insert().values(
            role_id=ADMIN_ROLE_ID,
            permission_id=permission_id,
        ))
        session.commit()
    assert _open_shift(client, 0).status_code == 200
    order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]},
    ).json()
    payment = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=_admin_headers(),
        json={"amount_cents": order["total_cents"], "method": "cash", "register_id": "CAJA-01"},
    )
    assert payment.status_code == 200
    params = {
        "from_utc": "2026-01-01T00:00:00Z",
        "to_utc": "2027-01-01T00:00:00Z",
        "branch_id": BRANCH_A,
    }
    summary = client.get("/api/v1/reports/sales-monitor", headers=_admin_headers(), params=params)
    drill = client.get(
        "/api/v1/reports/sales-monitor/drill-down",
        headers=_admin_headers(),
        params={**params, "metric": "gross"},
    )
    for response, schema_name in (
        (summary, "sales-monitor-v1.schema.json"),
        (drill, "sales-monitor-drill-down-v1.schema.json"),
    ):
        assert response.status_code == 200
        assert not list(_validators()[schema_name].iter_errors(response.json()))
    assert summary.json()["applied_filters"]["from_utc"].endswith("Z")
    assert drill.json()["items"][0]["confirmed_at"].endswith("Z")
    assert summary.json()["corrections"] == {
        "count": 0,
        "charge_cents": 0,
        "refund_cents": 0,
        "net_delta_cents": 0,
        "cash_adjustment_count": 0,
    }
    assert drill.json()["corrections"] == []
    invalid_cursor = client.get(
        "/api/v1/reports/sales-monitor/drill-down",
        headers=_admin_headers(),
        params={**params, "metric": "gross", "cursor": "garbage|garbage"},
    )
    assert invalid_cursor.status_code == 409
    assert invalid_cursor.json()["detail"]["code"] == "sales_monitor_cursor_invalid"


def test_pco004_http_boundaries_fail_closed_for_invalid_commands_and_filters() -> None:
    client = _client_with_seeded_database()
    invalid_open = client.post(
        "/api/v1/cash/shifts/open",
        headers={**_admin_headers(), "Idempotency-Key": "invalid-open"},
        json={
            "branch_id": BRANCH_A,
            "register_id": "CAJA-01",
            "opening_cash_cents": True,
            "unexpected": "forbidden",
        },
    )
    assert invalid_open.status_code == 409
    assert invalid_open.json()["detail"]["code"] == "cash_shift_open_payload_invalid"
    missing_key_headers = _admin_headers()
    missing_key_headers.pop("Idempotency-Key")
    missing_key = client.post(
        "/api/v1/cash/shifts/open",
        headers=missing_key_headers,
        json={"branch_id": BRANCH_A, "register_id": "CAJA-01", "opening_cash_cents": 0},
    )
    assert missing_key.status_code == 409
    assert missing_key.json()["detail"]["code"] == "idempotency_key_required"
    opened = _open_shift(client, 0)
    assert opened.status_code == 200
    invalid_close = client.post(
        f"/api/v1/cash/shifts/{opened.json()['id']}/close-operationally",
        headers=_admin_headers(),
        json={"counted_cash_cents": 0},
    )
    assert invalid_close.status_code == 409
    assert invalid_close.json()["detail"]["code"] == "cash_shift_close_payload_invalid"
    missing_close_key_headers = _admin_headers()
    missing_close_key_headers.pop("Idempotency-Key")
    missing_close_key = client.post(
        f"/api/v1/cash/shifts/{opened.json()['id']}/close-operationally",
        headers=missing_close_key_headers,
        json={},
    )
    assert missing_close_key.status_code == 409
    assert missing_close_key.json()["detail"]["code"] == "idempotency_key_required"

    factory = client.app.state.test_session_factory
    with factory() as session:
        permission_id = "018f6f73-2d0a-74f0-8f1c-000000008072"
        session.execute(models.permissions.insert().values(
            id=permission_id,
            code="reports.sales.read",
            description="sales monitor",
            created_at=NOW,
        ))
        session.execute(models.role_permissions.insert().values(
            role_id=ADMIN_ROLE_ID,
            permission_id=permission_id,
        ))
        session.commit()
    base = {"branch_id": BRANCH_A, "from_utc": "2026-08-12T01:00:00Z"}
    invalid_period = client.get(
        "/api/v1/reports/sales-monitor",
        headers=_admin_headers(),
        params={**base, "to_utc": "2026-08-12T01:00:00Z"},
    )
    assert invalid_period.status_code == 409
    assert invalid_period.json()["detail"]["code"] == "sales_monitor_period_invalid"
    invalid_timezone = client.get(
        "/api/v1/reports/sales-monitor",
        headers=_admin_headers(),
        params={**base, "to_utc": "2026-08-12T02:00:00"},
    )
    assert invalid_timezone.status_code == 409
    assert invalid_timezone.json()["detail"]["code"] == "sales_monitor_period_invalid"
    invalid_limit = client.get(
        "/api/v1/reports/sales-monitor/drill-down",
        headers=_admin_headers(),
        params={**base, "to_utc": "2026-08-12T02:00:00Z", "metric": "gross", "limit": 101},
    )
    assert invalid_limit.status_code == 409
    assert invalid_limit.json()["detail"]["code"] == "sales_monitor_filter_invalid"


def test_paid_sales_snapshot_is_immutable_after_catalog_changes() -> None:
    client = _client_with_seeded_database()
    factory = client.app.state.test_session_factory
    with factory() as session:
        permission_id = "018f6f73-2d0a-74f0-8f1c-000000008073"
        session.execute(models.permissions.insert().values(
            id=permission_id,
            code="reports.sales.read",
            description="sales monitor",
            created_at=NOW,
        ))
        session.execute(models.role_permissions.insert().values(
            role_id=ADMIN_ROLE_ID,
            permission_id=permission_id,
        ))
        session.commit()
    assert _open_shift(client, 0).status_code == 200
    product_id = "018f6f73-2d0a-74f0-8f1c-000000000111"
    order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": product_id, "quantity": 1}]},
    ).json()
    assert client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=_admin_headers(),
        json={"amount_cents": order["total_cents"], "method": "cash", "register_id": "CAJA-01"},
    ).status_code == 200
    with factory() as session:
        snapshot = session.execute(
            sa.select(models.sales_operation_line_snapshots).where(
                models.sales_operation_line_snapshots.c.product_id == product_id
            )
        ).mappings().one()
        original = {
            "product_name": snapshot["product_name_snapshot"],
            "family_id": snapshot["family_id_snapshot"],
            "family_name": snapshot["family_name_snapshot"],
        }
        replacement_category = session.execute(
            sa.select(models.product_categories.c.id).where(
                models.product_categories.c.id != original["family_id"]
            )
        ).scalar_one()
        session.execute(models.products.update().where(models.products.c.id == product_id).values(
            name="Catálogo cambiado", category_id=replacement_category
        ))
        session.commit()
    monitor = client.get(
        "/api/v1/reports/sales-monitor",
        headers=_admin_headers(),
        params={
            "from_utc": "2026-01-01T00:00:00Z",
            "to_utc": "2027-01-01T00:00:00Z",
            "branch_id": BRANCH_A,
        },
    )
    assert monitor.status_code == 200
    assert [item["id"] for item in monitor.json()["breakdowns"]["families"]] == [
        original["family_id"]
    ]
    with factory() as session:
        unchanged = session.execute(
            sa.select(models.sales_operation_line_snapshots).where(
                models.sales_operation_line_snapshots.c.product_id == product_id
            )
        ).mappings().one()
        assert {
            "product_name": unchanged["product_name_snapshot"],
            "family_id": unchanged["family_id_snapshot"],
            "family_name": unchanged["family_name_snapshot"],
        } == original


def test_sqlite_close_vs_payment_race_serializes_payment_and_frozen_close(tmp_path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'pco004-close-payment-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        shift = open_cash_shift(session, 0, "CAJA-01", BRANCH_A, ADMIN_USER_ID)
        order = create_local_order(
            session,
            [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}],
            branch_id=BRANCH_A,
            register_id="CAJA-01",
            actor_user_id=ADMIN_USER_ID,
        )
    barrier = Barrier(2)

    def close() -> tuple[str, object]:
        with Session(engine) as session:
            barrier.wait()
            try:
                return "ok", close_cash_shift_operationally(
                    session, shift["id"], "race-close", ADMIN_USER_ID
                )
            except BusinessError as exc:
                return "error", exc.code

    def pay() -> tuple[str, object]:
        with Session(engine) as session:
            barrier.wait()
            try:
                return "ok", pay_order(
                    session,
                    order["id"],
                    order["total_cents"],
                    "cash",
                    ADMIN_USER_ID,
                    "CAJA-01",
                )
            except BusinessError as exc:
                return "error", exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        close_result, payment_result = list(pool.map(lambda action: action(), (close, pay)))
    assert close_result[0] == "ok"
    with Session(engine) as session:
        payments = session.execute(
            sa.select(models.payments).where(models.payments.c.order_id == order["id"])
        ).mappings().all()
        snapshots = session.execute(
            sa.select(models.sales_operation_snapshots).where(
                models.sales_operation_snapshots.c.order_id == order["id"]
            )
        ).mappings().all()
        closure = session.execute(
            sa.select(models.cash_shift_closures).where(
                models.cash_shift_closures.c.cash_shift_id == shift["id"]
            )
        ).mappings().one()
        audit_actions = set(session.execute(
            sa.select(models.audit_events.c.action).where(
                models.audit_events.c.entity_id.in_([shift["id"], order["id"]])
            )
        ).scalars())
        cut_count = session.execute(
            sa.select(sa.func.count()).select_from(models.cash_shift_cuts)
        ).scalar_one()
    assert cut_count == 0
    assert "cash_shift.operationally_closed" in audit_actions
    if payment_result[0] == "ok":
        assert len(payments) == len(snapshots) == 1
        assert closure["summary_snapshot"]["confirmed_payment_count"] == 1
        assert closure["summary_snapshot"]["payment_total_cents"] == order["total_cents"]
    else:
        assert payment_result == ("error", "cash_shift_not_open")
        assert payments == []
        assert snapshots == []
        assert closure["summary_snapshot"]["confirmed_payment_count"] == 0
    engine.dispose()


def test_sqlite_concurrent_payment_replay_returns_one_complete_effect(tmp_path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'payment-idempotency-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        open_cash_shift(session, 0, "CAJA-01", BRANCH_A, ADMIN_USER_ID)
        order = create_local_order(
            session,
            [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}],
            branch_id=BRANCH_A,
            register_id="CAJA-01",
            actor_user_id=ADMIN_USER_ID,
        )
    barrier = Barrier(2)

    def pay() -> dict[str, object]:
        with Session(engine) as session:
            barrier.wait()
            return pay_order(
                session,
                order["id"],
                order["total_cents"],
                "cash",
                ADMIN_USER_ID,
                "CAJA-01",
                idempotency_key="concurrent-payment-replay-001",
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: pay(), range(2)))

    assert results[0] == results[1]
    with Session(engine) as session:
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.payments)
        ).scalar_one() == 1
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.payment_commands)
        ).scalar_one() == 1
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.sales_operation_snapshots)
        ).scalar_one() == 1
        assert session.execute(
            sa.select(sa.func.count())
            .select_from(models.order_events)
            .where(models.order_events.c.event_type == "PAYMENT_CONFIRMED")
        ).scalar_one() == 1
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.print_jobs)
        ).scalar_one() == 2
    engine.dispose()


def test_sqlite_concurrent_order_replay_returns_one_complete_effect(tmp_path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'order-idempotency-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        open_cash_shift(session, 0, "CAJA-01", BRANCH_A, ADMIN_USER_ID)
    barrier = Barrier(2)

    def create() -> dict[str, Any]:
        with Session(engine) as session:
            barrier.wait()
            return create_local_order(
                session,
                [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}],
                branch_id=BRANCH_A,
                register_id="CAJA-01",
                actor_user_id=ADMIN_USER_ID,
                idempotency_key="concurrent-order-replay-001",
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))

    assert results[0]["id"] == results[1]["id"]
    expected_reservations = sum(
        len(snapshot["components"])
        for snapshot in results[0]["consumption_snapshots"]
    )
    with Session(engine) as session:
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.orders)
        ).scalar_one() == 1
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.order_create_commands)
        ).scalar_one() == 1
        assert session.execute(
            sa.select(sa.func.count())
            .select_from(models.order_events)
            .where(models.order_events.c.event_type == "ORDER_ACCEPTED")
        ).scalar_one() == 1
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.production_tasks)
        ).scalar_one() == 1
        assert session.execute(
            sa.select(sa.func.count())
            .select_from(models.inventory_movements)
            .where(
                models.inventory_movements.c.source_type == "order",
                models.inventory_movements.c.source_id == results[0]["id"],
                models.inventory_movements.c.movement_type == "SALE_RESERVATION",
            )
        ).scalar_one() == expected_reservations
        assert session.execute(
            sa.select(sa.func.count())
            .select_from(models.audit_events)
            .where(
                models.audit_events.c.action == "order.accepted",
                models.audit_events.c.entity_id == results[0]["id"],
            )
        ).scalar_one() == 1
    engine.dispose()


def _pco004_postgres_url() -> str:
    url = os.environ.get("PCO004_TEST_POSTGRES_ROUNDTRIP_URL")
    if not url:
        pytest.skip("PCO004_TEST_POSTGRES_ROUNDTRIP_URL is required")
    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.path.startswith("/pco004_"):
        raise RuntimeError("PCO-004 race tests require a local isolated pco004_* database")
    return url


def _prepare_pco004_postgres(url: str) -> None:
    api_dir = Path(__file__).resolve().parents[1]
    env = {**os.environ, "RESTAURANTOS_DATABASE_URL": url}
    env.pop("DATABASE_URL", None)
    result = subprocess.run(
        [
            sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade",
            "head",
        ],
        cwd=api_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _truncate_pco004_database(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        preparer = connection.dialect.identifier_preparer
        tables = ", ".join(
            preparer.quote(table_name)
            for table_name in sa.inspect(connection).get_table_names()
            if table_name != "alembic_version"
        )
        if tables:
            connection.execute(sa.text(f"TRUNCATE TABLE {tables} CASCADE"))  # noqa: S608


def test_postgres_close_vs_payment_race_requires_isolated_pco004_database() -> None:
    """Run the real close/payment race only in an explicit local PCO-004 database."""
    url = _pco004_postgres_url()
    _prepare_pco004_postgres(url)
    engine = create_engine(url, pool_pre_ping=True)
    try:
        _truncate_pco004_database(engine)
        with Session(engine) as session:
            _seed(session)
            shift = open_cash_shift(session, 0, "CAJA-01", BRANCH_A, ADMIN_USER_ID)
            order = create_local_order(
                session,
                [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}],
                branch_id=BRANCH_A,
                register_id="CAJA-01",
                actor_user_id=ADMIN_USER_ID,
            )
        barrier = Barrier(2)

        def close() -> tuple[str, object]:
            with Session(engine) as session:
                barrier.wait()
                try:
                    return "ok", close_cash_shift_operationally(
                        session, shift["id"], "pg-race-close", ADMIN_USER_ID
                    )
                except BusinessError as exc:
                    return "error", exc.code

        def pay() -> tuple[str, object]:
            with Session(engine) as session:
                barrier.wait()
                try:
                    return "ok", pay_order(
                        session, order["id"], order["total_cents"], "cash", ADMIN_USER_ID, "CAJA-01"
                    )
                except BusinessError as exc:
                    return "error", exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            close_result, payment_result = list(pool.map(lambda action: action(), (close, pay)))
        assert close_result[0] == "ok"
        with Session(engine) as session:
            payments = session.execute(sa.select(models.payments).where(
                models.payments.c.order_id == order["id"]
            )).mappings().all()
            snapshots = session.execute(sa.select(models.sales_operation_snapshots).where(
                models.sales_operation_snapshots.c.order_id == order["id"]
            )).mappings().all()
            closure = session.execute(sa.select(models.cash_shift_closures).where(
                models.cash_shift_closures.c.cash_shift_id == shift["id"]
            )).mappings().one()
        if payment_result[0] == "ok":
            assert len(payments) == len(snapshots) == 1
            assert closure["summary_snapshot"]["confirmed_payment_count"] == 1
        else:
            assert payment_result == ("error", "cash_shift_not_open")
            assert payments == snapshots == []
            assert closure["summary_snapshot"]["confirmed_payment_count"] == 0
    finally:
        _truncate_pco004_database(engine)
        engine.dispose()


def test_close_replay_requires_current_permission_and_conflict_never_adds_cut() -> None:
    engine, session = _new_session()
    try:
        original = close_cash_shift_operationally(session, SHIFT_ID, "close-replay", CASHIER_ID)
        replay = close_cash_shift_operationally(session, SHIFT_ID, "close-replay", CASHIER_ID)
        assert replay["closure"]["id"] == original["closure"]["id"]
        cut_count = session.execute(
            sa.select(sa.func.count()).select_from(models.cash_shift_cuts)
        ).scalar_one()
        assert cut_count == 0
        session.execute(models.role_permissions.delete().where(
            models.role_permissions.c.role_id == CASHIER_ROLE_ID
        ))
        session.commit()
        with pytest.raises(AuthorizationError):
            close_cash_shift_operationally(session, SHIFT_ID, "close-replay", CASHIER_ID)
    finally:
        session.close()
        engine.dispose()


def test_operational_cash_shift_metrics_are_safe_and_distinguish_replay_conflict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine, session = _new_session()
    try:
        caplog.set_level("INFO", logger="restaurant_os.operations")
        close_cash_shift_operationally(session, SHIFT_ID, "metrics-close", CASHIER_ID)
        close_cash_shift_operationally(session, SHIFT_ID, "metrics-close", CASHIER_ID)
        with pytest.raises(BusinessError) as conflict:
            close_cash_shift_operationally(session, SHIFT_ID, "metrics-conflict", CASHIER_ID)
        assert conflict.value.code == "cash_shift_not_open"
        metrics = [record for record in caplog.records if hasattr(record, "metric")]
        close_results = [
            record.result
            for record in metrics
            if record.metric == "cash_shift_operational_close_total"
        ]
        assert {"success", "replay", "error"} <= set(close_results)
        assert any(
            record.metric == "cash_shift_guard_conflict_total"
            and record.error_code == "cash_shift_not_open"
            for record in metrics
        )
        rendered = "\n".join(record.getMessage() for record in metrics)
        assert "metrics-close" not in rendered
        assert "metrics-conflict" not in rendered
    finally:
        session.close()
        engine.dispose()


def test_open_and_close_validation_errors_emit_one_safe_primary_metric(
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine, session = _new_session()
    try:
        caplog.set_level("INFO", logger="restaurant_os.operations")
        with pytest.raises(BusinessError) as invalid_open:
            open_cash_shift_idempotently(session, BRANCH_A, "", 0, "open-invalid", CASHIER_ID)
        assert invalid_open.value.code == "cash_shift_open_payload_invalid"
        with pytest.raises(BusinessError) as invalid_close:
            close_cash_shift_operationally(session, SHIFT_ID, "", CASHIER_ID)
        assert invalid_close.value.code == "idempotency_key_required"
        metrics = [
            record for record in caplog.records
            if getattr(record, "metric", None) in {
                "cash_shift_open_total", "cash_shift_operational_close_total"
            }
            and getattr(record, "result", None) == "error"
        ]
        assert [(record.metric, record.error_code) for record in metrics] == [
            ("cash_shift_open_total", "cash_shift_open_payload_invalid"),
            ("cash_shift_operational_close_total", "idempotency_key_required"),
        ]
    finally:
        session.close()
        engine.dispose()


def test_open_idempotency_replays_and_normalizes_active_register_conflict() -> None:
    engine, session = _new_session()
    try:
        session.execute(models.cash_shifts.delete().where(models.cash_shifts.c.id == SHIFT_ID))
        session.execute(models.permissions.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-000000008101", code="cash.shift.open",
            description="open", created_at=NOW,
        ))
        session.execute(models.role_permissions.insert().values(
            role_id=CASHIER_ROLE_ID, permission_id="018f6f73-2d0a-74f0-8f1c-000000008101"
        ))
        session.commit()
        created = open_cash_shift_idempotently(
            session, BRANCH_A, "CAJA-01", 0, "open-same", CASHIER_ID
        )
        replay = open_cash_shift_idempotently(
            session, BRANCH_A, "CAJA-01", 0, "open-same", CASHIER_ID
        )
        assert replay["id"] == created["id"]
        with pytest.raises(BusinessError) as different_key:
            open_cash_shift_idempotently(session, BRANCH_A, "CAJA-01", 0, "open-other", CASHIER_ID)
        assert different_key.value.code == "cash_shift_already_open"
        with pytest.raises(BusinessError) as changed_payload:
            open_cash_shift_idempotently(session, BRANCH_A, "CAJA-01", 1, "open-same", CASHIER_ID)
        assert changed_payload.value.code == "idempotency_conflict"
    finally:
        session.close()
        engine.dispose()


def test_close_failure_after_closing_rolls_back_every_artifact() -> None:
    engine, session = _new_session()
    try:
        with pytest.raises(RuntimeError, match="inject"):
            close_cash_shift_operationally(
                session,
                SHIFT_ID,
                "close-rollback",
                CASHIER_ID,
                lambda stage: (_ for _ in ()).throw(RuntimeError("inject"))
                if stage == "after_closing"
                else None,
            )
        assert session.execute(sa.select(models.cash_shifts.c.status).where(
            models.cash_shifts.c.id == SHIFT_ID
        )).scalar_one() == "OPEN"
        for table in (
            models.cash_shift_closures,
            models.cash_shift_commands,
            models.cash_shift_cuts,
        ):
            assert session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one() == 0
    finally:
        session.close()
        engine.dispose()


def test_payment_snapshot_failure_rolls_back_all_payment_artifacts() -> None:
    client = _client_with_seeded_database()
    assert _open_shift(client, 0).status_code == 200
    order_response = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]},
    )
    assert order_response.status_code == 200
    order = order_response.json()
    factory = client.app.state.test_session_factory
    protected_tables = (
        models.order_events,
        models.print_jobs,
        models.sales_operation_snapshots,
        models.sales_operation_line_snapshots,
    )
    with factory() as session:
        before_counts = {
            table.name: session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
            for table in protected_tables
        }
    with factory() as session:
        with pytest.raises(RuntimeError, match="snapshot inject"):
            pay_order(
                session,
                order["id"],
                order["total_cents"],
                "cash",
                "018f6f73-2d0a-74f0-8f1c-000000000006",
                "CAJA-01",
                lambda stage: (_ for _ in ()).throw(RuntimeError("snapshot inject"))
                if stage == "after_sales_snapshot"
                else None,
            )
    with factory() as session:
        payment_count = session.execute(
            sa.select(sa.func.count()).select_from(models.payments)
        ).scalar_one()
        assert payment_count == 0
        assert session.execute(sa.select(models.orders.c.status).where(
            models.orders.c.id == order["id"]
        )).scalar_one() == "ACCEPTED"
        for table in protected_tables:
            count = session.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
            assert count == before_counts[table.name]
