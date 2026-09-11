# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-waste-record-scope-synthetic-v1
"""Real-waste commands remain isolated across SaaS tenants."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
import sqlalchemy as sa
from restaurant_os import models, operations
from restaurant_os.operations import (
    BusinessError,
    confirm_waste_record,
    create_waste_reason,
    create_waste_record,
    reverse_waste_record,
)
from restaurant_os.saas_onboarding import signup_tenant
from sqlalchemy.orm import Session
from test_saas_cash_scope import _cash_scope_api_client


def _seed_stock(session, tenant: dict, suffix: str) -> dict[str, str]:
    now = datetime.now(UTC)
    organization_id = str(tenant["organization"]["id"])
    branch_id = str(tenant["branch"]["id"])
    warehouse_id = str(
        session.scalar(
            sa.select(models.warehouses.c.id).where(
                models.warehouses.c.organization_id == organization_id,
                models.warehouses.c.branch_id == branch_id,
            )
        )
    )
    unit_id = str(uuid4())
    item_id = str(uuid4())
    session.execute(
        models.inventory_units.insert().values(
            id=unit_id,
            organization_id=organization_id,
            code=f"KG-{suffix}",
            name=f"Kilogram {suffix}",
            dimension="mass",
            precision_scale=3,
            created_at=now,
        )
    )
    session.execute(
        models.inventory_items.insert().values(
            id=item_id,
            organization_id=organization_id,
            name=f"Ingredient {suffix}",
            sku=f"WASTE-{suffix}",
            base_unit_id=unit_id,
            item_type="ingredient",
            category_name="Synthetic",
            catalog_scope="organization",
            source_branch_id=None,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.inventory_movements.insert().values(
            id=str(uuid4()),
            organization_id=organization_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            item_id=item_id,
            movement_type="PURCHASE_RECEIPT",
            quantity_delta=Decimal("10"),
            unit_id=unit_id,
            unit_cost=Decimal("25"),
            total_cost=Decimal("250"),
            effective_at=now,
            actor_user_id=tenant["user"]["id"],
            document_type="synthetic_fixture",
            document_id=str(uuid4()),
            reference=None,
            reason="Synthetic opening stock",
            notes=None,
            idempotency_key=f"synthetic-opening-stock-{suffix}",
            status="confirmed",
            reversal_of_id=None,
            source_type="synthetic_fixture",
            source_id=item_id,
            created_at=now,
        )
    )
    session.execute(
        models.inventory_cost_states.insert().values(
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            item_id=item_id,
            quantity_on_hand=Decimal("10"),
            average_unit_cost=Decimal("25"),
            last_unit_cost=Decimal("25"),
            last_supplier_id=None,
            last_cost_at=now,
            updated_at=now,
        )
    )
    return {
        "organization_id": organization_id,
        "branch_id": branch_id,
        "warehouse_id": warehouse_id,
        "unit_id": unit_id,
        "item_id": item_id,
    }


def _waste_payload(stock: dict[str, str], reason_id: str) -> dict[str, str | list[str]]:
    return {
        "branch_id": stock["branch_id"],
        "item_id": stock["item_id"],
        "unit_id": stock["unit_id"],
        "reason_id": reason_id,
        "quantity": "2",
        "stage": "storage",
        "evidence": [],
    }


def test_waste_record_ids_movements_cost_and_replays_are_tenant_scoped() -> None:
    client, factory = _cash_scope_api_client()
    try:
        with factory() as session:
            tenants = [
                signup_tenant(
                    session,
                    {
                        "business_name": f"Waste Records {suffix}",
                        "owner_name": f"Owner {suffix}",
                        "email": f"waste-records-{suffix.lower()}@example.test",
                        "password": "synthetic-waste-record-password",
                        "business_type": "blank",
                    },
                )
                for suffix in ("A", "B")
            ]
            stocks = [
                _seed_stock(session, tenant, suffix)
                for tenant, suffix in zip(tenants, ("A", "B"), strict=True)
            ]
            session.commit()

        headers = [{"Authorization": f"Bearer {tenant['token']}"} for tenant in tenants]
        reasons = []
        for auth, suffix in zip(headers, ("A", "B"), strict=True):
            response = client.post(
                "/api/v1/inventory/waste-reasons",
                headers=auth,
                json={
                    "code": "DAMAGED",
                    "name": f"Damaged {suffix}",
                    "classification": "operation",
                },
            )
            assert response.status_code == 200, response.text
            reasons.append(response.json())

        foreign_item = client.post(
            "/api/v1/inventory/wastes",
            headers=headers[0],
            json=_waste_payload(stocks[1], reasons[1]["id"]),
        )
        assert foreign_item.status_code == 403, foreign_item.text
        assert foreign_item.json()["detail"]["code"] == "permission_denied"

        foreign_reason_payload = _waste_payload(stocks[0], reasons[1]["id"])
        foreign_reason = client.post(
            "/api/v1/inventory/wastes", headers=headers[0], json=foreign_reason_payload
        )
        assert foreign_reason.status_code == 409, foreign_reason.text
        assert foreign_reason.json()["detail"]["code"] == "active_waste_reason_not_found"

        drafts = []
        for auth, stock, reason in zip(headers, stocks, reasons, strict=True):
            response = client.post(
                "/api/v1/inventory/wastes",
                headers=auth,
                json=_waste_payload(stock, reason["id"]),
            )
            assert response.status_code == 200, response.text
            drafts.append(response.json())

        for action in ("confirm", "reverse"):
            response = client.post(
                f"/api/v1/inventory/wastes/{drafts[1]['id']}/{action}",
                headers={**headers[0], "Idempotency-Key": f"foreign-{action}"},
                json={} if action == "confirm" else {"reason": "Foreign record"},
            )
            assert response.status_code == 409, response.text
            assert response.json()["detail"]["code"] == "waste_not_found"

        foreign_list = client.get(
            f"/api/v1/inventory/wastes?branch_id={stocks[1]['branch_id']}",
            headers=headers[0],
        )
        assert foreign_list.status_code == 403, foreign_list.text

        confirmation_headers = {
            **headers[0],
            "Idempotency-Key": "shared-waste-confirmation-key",
        }
        confirmed = client.post(
            f"/api/v1/inventory/wastes/{drafts[0]['id']}/confirm",
            headers=confirmation_headers,
            json={},
        )
        assert confirmed.status_code == 200, confirmed.text
        replay = client.post(
            f"/api/v1/inventory/wastes/{drafts[0]['id']}/confirm",
            headers=confirmation_headers,
            json={},
        )
        assert replay.status_code == 200, replay.text
        assert len(replay.json()["movements"]) == 1

        reused_confirmation_key = client.post(
            f"/api/v1/inventory/wastes/{drafts[0]['id']}/reverse",
            headers=confirmation_headers,
            json={"reason": "Synthetic key reuse"},
        )
        assert reused_confirmation_key.status_code == 409, reused_confirmation_key.text
        assert reused_confirmation_key.json()["detail"]["code"] == "idempotency_conflict"

        reversal_headers = {
            **headers[0],
            "Idempotency-Key": "shared-waste-reversal-key",
        }
        reversed_response = client.post(
            f"/api/v1/inventory/wastes/{drafts[0]['id']}/reverse",
            headers=reversal_headers,
            json={"reason": "Synthetic correction"},
        )
        assert reversed_response.status_code == 200, reversed_response.text
        reversal_replay = client.post(
            f"/api/v1/inventory/wastes/{drafts[0]['id']}/reverse",
            headers=reversal_headers,
            json={"reason": "Synthetic correction"},
        )
        assert reversal_replay.status_code == 200, reversal_replay.text
        assert len(reversal_replay.json()["movements"]) == 2

        conflicting_replay = client.post(
            f"/api/v1/inventory/wastes/{drafts[0]['id']}/reverse",
            headers=reversal_headers,
            json={"reason": "Different synthetic correction"},
        )
        assert conflicting_replay.status_code == 409, conflicting_replay.text
        assert conflicting_replay.json()["detail"]["code"] == "idempotency_conflict"

        with factory() as session:
            movements = list(
                session.execute(
                    sa.select(models.inventory_movements).where(
                        models.inventory_movements.c.source_id == drafts[0]["id"]
                    )
                ).mappings()
            )
            assert len(movements) == 2
            assert {str(row["organization_id"]) for row in movements} == {
                stocks[0]["organization_id"]
            }
            quantity = session.scalar(
                sa.select(models.inventory_cost_states.c.quantity_on_hand).where(
                    models.inventory_cost_states.c.branch_id == stocks[0]["branch_id"],
                    models.inventory_cost_states.c.warehouse_id == stocks[0]["warehouse_id"],
                    models.inventory_cost_states.c.item_id == stocks[0]["item_id"],
                )
            )
            assert quantity == Decimal("10")

        # A tenant-local idempotency key must not reserve the same key for another tenant.
        tenant_b_confirmation = client.post(
            f"/api/v1/inventory/wastes/{drafts[1]['id']}/confirm",
            headers={**headers[1], "Idempotency-Key": "shared-waste-confirmation-key"},
            json={},
        )
        assert tenant_b_confirmation.status_code == 200, tenant_b_confirmation.text
    finally:
        client.app.dependency_overrides.clear()


def test_waste_confirmation_same_key_is_scoped_in_two_sessions(
    cash_scope_session: Session,
) -> None:
    with cash_scope_session as seed:
        tenant_a = signup_tenant(
            seed,
            {
                "business_name": "Waste Lock A",
                "owner_name": "Owner A",
                "email": "waste-lock-a@example.test",
                "password": "test-only-waste-lock-a",
                "business_type": "blank",
            },
        )
        tenant_b = signup_tenant(
            seed,
            {
                "business_name": "Waste Lock B",
                "owner_name": "Owner B",
                "email": "waste-lock-b@example.test",
                "password": "test-only-waste-lock-b",
                "business_type": "blank",
            },
        )
        stock_a, stock_b = (
            _seed_stock(seed, tenant_a, "LOCK-A"),
            _seed_stock(seed, tenant_b, "LOCK-B"),
        )
        reason_a = create_waste_reason(
            seed,
            {"code": "LOCK", "name": "Lock A", "classification": "operation"},
            tenant_a["user"]["id"],
        )
        reason_b = create_waste_reason(
            seed,
            {"code": "LOCK", "name": "Lock B", "classification": "operation"},
            tenant_b["user"]["id"],
        )
        draft_a = create_waste_record(
            seed, _waste_payload(stock_a, reason_a["id"]), tenant_a["user"]["id"]
        )
        draft_b = create_waste_record(
            seed, _waste_payload(stock_b, reason_b["id"]), tenant_b["user"]["id"]
        )
        engine = seed.get_bind()

        with Session(engine) as session_a:
            result_a = confirm_waste_record(
                session_a, draft_a["id"], "same-key-two-sessions", tenant_a["user"]["id"]
            )
            assert result_a["status"] == "confirmed"
        with Session(engine) as session_b:
            result_b = confirm_waste_record(
                session_b, draft_b["id"], "same-key-two-sessions", tenant_b["user"]["id"]
            )
            assert result_b["status"] == "confirmed"
        assert (
            seed.scalar(
                sa.select(sa.func.count())
                .select_from(models.inventory_movements)
                .where(models.inventory_movements.c.idempotency_key == "same-key-two-sessions")
            )
            == 2
        )


def test_waste_confirm_and_reverse_claim_one_concurrent_winner(
    cash_scope_session: Session,
) -> None:
    with cash_scope_session as seed:
        engine = seed.get_bind()
        if engine.dialect.name != "postgresql":
            pytest.skip("PostgreSQL row-lock and CAS concurrency gate")
        tenant = signup_tenant(
            seed,
            {
                "business_name": "Waste Concurrent",
                "owner_name": "Owner Concurrent",
                "email": "waste-concurrent@example.test",
                "password": "test-only-waste-concurrent",
                "business_type": "blank",
            },
        )
        stock = _seed_stock(seed, tenant, "CONCURRENT")
        reason = create_waste_reason(
            seed,
            {"code": "CONCURRENT", "name": "Concurrent", "classification": "operation"},
            tenant["user"]["id"],
        )
        draft = create_waste_record(
            seed, _waste_payload(stock, reason["id"]), tenant["user"]["id"]
        )
        actor_id = str(tenant["user"]["id"])

        confirm_barrier = Barrier(2)

        def confirm(key: str) -> tuple[str, str]:
            with Session(engine) as session:
                confirm_barrier.wait()
                try:
                    result = confirm_waste_record(session, draft["id"], key, actor_id)
                    return "ok", str(result["confirmation_idempotency_key"])
                except BusinessError as exc:
                    return "error", exc.code

        confirm_keys = ("concurrent-confirm-a", "concurrent-confirm-b")
        with ThreadPoolExecutor(max_workers=2) as executor:
            confirm_results = list(executor.map(confirm, confirm_keys))
        assert sorted(status for status, _ in confirm_results) == ["error", "ok"]
        assert [value for status, value in confirm_results if status == "error"] == [
            "waste_already_confirmed"
        ]
        winning_confirm_key = next(value for status, value in confirm_results if status == "ok")

        seed.expire_all()
        assert (
            seed.scalar(
                sa.select(sa.func.count())
                .select_from(models.inventory_movements)
                .where(
                    models.inventory_movements.c.organization_id == stock["organization_id"],
                    models.inventory_movements.c.source_id == draft["id"],
                    models.inventory_movements.c.movement_type == "WASTE_REAL",
                )
            )
            == 1
        )
        assert seed.scalar(
            sa.select(models.inventory_cost_states.c.quantity_on_hand).where(
                models.inventory_cost_states.c.branch_id == stock["branch_id"],
                models.inventory_cost_states.c.warehouse_id == stock["warehouse_id"],
                models.inventory_cost_states.c.item_id == stock["item_id"],
            )
        ) == Decimal("8")

        with Session(engine) as replay_session:
            replay = confirm_waste_record(
                replay_session, draft["id"], winning_confirm_key, actor_id
            )
            assert replay["confirmation_idempotency_key"] == winning_confirm_key

        reverse_barrier = Barrier(2)

        def reverse(request: tuple[str, str]) -> tuple[str, str, str]:
            key, reversal_reason = request
            with Session(engine) as session:
                reverse_barrier.wait()
                try:
                    result = reverse_waste_record(
                        session, draft["id"], reversal_reason, key, actor_id
                    )
                    return "ok", str(result["reversal_idempotency_key"]), reversal_reason
                except BusinessError as exc:
                    return "error", exc.code, reversal_reason

        reverse_requests = (
            ("concurrent-reverse-a", "Synthetic reason A"),
            ("concurrent-reverse-b", "Synthetic reason B"),
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            reverse_results = list(executor.map(reverse, reverse_requests))
        assert sorted(status for status, _, _ in reverse_results) == ["error", "ok"]
        assert [value for status, value, _ in reverse_results if status == "error"] == [
            "waste_already_reversed"
        ]
        winning_reverse = next(result for result in reverse_results if result[0] == "ok")

        seed.expire_all()
        persisted = seed.execute(
            sa.select(models.waste_records).where(models.waste_records.c.id == draft["id"])
        ).mappings().one()
        assert persisted["status"] == "reversed"
        assert persisted["reversal_idempotency_key"] == winning_reverse[1]
        assert persisted["reversal_reason"] == winning_reverse[2]
        assert (
            seed.scalar(
                sa.select(sa.func.count())
                .select_from(models.inventory_movements)
                .where(
                    models.inventory_movements.c.organization_id == stock["organization_id"],
                    models.inventory_movements.c.source_id == draft["id"],
                    models.inventory_movements.c.movement_type == "WASTE_REVERSAL",
                )
            )
            == 1
        )
        assert seed.scalar(
            sa.select(models.inventory_cost_states.c.quantity_on_hand).where(
                models.inventory_cost_states.c.branch_id == stock["branch_id"],
                models.inventory_cost_states.c.warehouse_id == stock["warehouse_id"],
                models.inventory_cost_states.c.item_id == stock["item_id"],
            )
        ) == Decimal("10")


def test_two_wastes_cannot_concurrently_overdraw_the_same_stock(
    cash_scope_session: Session,
) -> None:
    with cash_scope_session as seed:
        engine = seed.get_bind()
        if engine.dialect.name != "postgresql":
            pytest.skip("PostgreSQL inventory concurrency gate")
        tenant = signup_tenant(
            seed,
            {
                "business_name": "Waste Shared Stock",
                "owner_name": "Owner Shared Stock",
                "email": "waste-shared-stock@example.test",
                "password": "test-only-waste-shared-stock",
                "business_type": "blank",
            },
        )
        stock = _seed_stock(seed, tenant, "SHARED-STOCK")
        reason = create_waste_reason(
            seed,
            {"code": "SHARED", "name": "Shared", "classification": "operation"},
            tenant["user"]["id"],
        )
        payload = _waste_payload(stock, reason["id"])
        payload["quantity"] = "6"
        drafts = [
            create_waste_record(seed, payload, tenant["user"]["id"]),
            create_waste_record(seed, payload, tenant["user"]["id"]),
        ]
        actor_id = str(tenant["user"]["id"])

        start_barrier = Barrier(2)

        def confirm(request: tuple[dict[str, object], str]) -> tuple[str, str]:
            draft, key = request
            with Session(engine) as session:
                start_barrier.wait()
                try:
                    result = confirm_waste_record(session, str(draft["id"]), key, actor_id)
                    return "ok", str(result["id"])
                except BusinessError as exc:
                    return "error", exc.code

        requests = ((drafts[0], "shared-stock-a"), (drafts[1], "shared-stock-b"))
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(confirm, requests))

        assert sorted(status for status, _ in results) == ["error", "ok"]
        assert [value for status, value in results if status == "error"] == [
            "insufficient_waste_inventory"
        ]
        seed.expire_all()
        assert (
            seed.scalar(
                sa.select(sa.func.count())
                .select_from(models.inventory_movements)
                .where(
                    models.inventory_movements.c.organization_id == stock["organization_id"],
                    models.inventory_movements.c.item_id == stock["item_id"],
                    models.inventory_movements.c.movement_type == "WASTE_REAL",
                )
            )
            == 1
        )
        assert operations._physical_inventory_quantity(
            seed, stock["branch_id"], stock["warehouse_id"], stock["item_id"]
        ) == Decimal("4")


def test_concurrent_waste_reversals_keep_cost_projection_consistent(
    cash_scope_session: Session,
) -> None:
    with cash_scope_session as seed:
        engine = seed.get_bind()
        if engine.dialect.name != "postgresql":
            pytest.skip("PostgreSQL inventory concurrency gate")
        tenant = signup_tenant(
            seed,
            {
                "business_name": "Waste Concurrent Reversal",
                "owner_name": "Owner Concurrent Reversal",
                "email": "waste-concurrent-reversal@example.test",
                "password": "test-only-waste-concurrent-reversal",
                "business_type": "blank",
            },
        )
        stock = _seed_stock(seed, tenant, "CONCURRENT-REVERSAL")
        reason = create_waste_reason(
            seed,
            {"code": "REVERSAL", "name": "Reversal", "classification": "operation"},
            tenant["user"]["id"],
        )
        drafts = [
            create_waste_record(
                seed, _waste_payload(stock, reason["id"]), tenant["user"]["id"]
            ),
            create_waste_record(
                seed, _waste_payload(stock, reason["id"]), tenant["user"]["id"]
            ),
        ]
        actor_id = str(tenant["user"]["id"])
        for index, draft in enumerate(drafts):
            confirm_waste_record(seed, draft["id"], f"reversal-setup-{index}", actor_id)

        start_barrier = Barrier(2)

        def reverse(request: tuple[dict[str, object], str]) -> dict[str, object]:
            draft, key = request
            with Session(engine) as session:
                start_barrier.wait()
                return reverse_waste_record(
                    session, str(draft["id"]), "Synthetic concurrent reversal", key, actor_id
                )

        requests = ((drafts[0], "parallel-reversal-a"), (drafts[1], "parallel-reversal-b"))
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(reverse, requests))
        assert [result["status"] for result in results] == ["reversed", "reversed"]

        seed.expire_all()
        physical_quantity = operations._physical_inventory_quantity(
            seed, stock["branch_id"], stock["warehouse_id"], stock["item_id"]
        )
        projected_quantity = seed.scalar(
            sa.select(models.inventory_cost_states.c.quantity_on_hand).where(
                models.inventory_cost_states.c.branch_id == stock["branch_id"],
                models.inventory_cost_states.c.warehouse_id == stock["warehouse_id"],
                models.inventory_cost_states.c.item_id == stock["item_id"],
            )
        )
        assert physical_quantity == Decimal("10")
        assert projected_quantity == physical_quantity
