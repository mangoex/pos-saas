# ruff: noqa: E501

"""PCO-005B linked compensating correction behaviour (TDD-TC-101..109)."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    AuthorizationError,
    BusinessError,
    NotFoundError,
    ReportingProjectionService,
    apply_order_reopen_request,
    calculate_expected_cash,
    close_cash_shift_operationally,
    close_cash_shift_with_cut,
    create_order_reopen_request,
    decide_order_reopen_request,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from test_cash_concepts import OWNER_ID, SECOND_OWNER_ID, _seed_cash_concept_scope
from test_cash_ledger import (
    BRANCH_A,
    CASHIER_ID,
    CASHIER_ROLE_ID,
    NOW,
    ORG_ID,
    SHIFT_ID,
    _insert_shift,
    _new_session,
)
from test_order_reopen_workflow import CHIEF_ID, _actors, _order

WAREHOUSE_ID = "018f6f73-2d0a-74f0-8f1c-000000009801"
UNIT_ID = "018f6f73-2d0a-74f0-8f1c-000000009802"
ITEM_ID = "018f6f73-2d0a-74f0-8f1c-000000009803"
CATEGORY_ID = "018f6f73-2d0a-74f0-8f1c-000000009804"
PRODUCT_ID = "018f6f73-2d0a-74f0-8f1c-000000009805"
RECIPE_ID = "018f6f73-2d0a-74f0-8f1c-000000009806"


def _production_fixture(session, order_id: str, status: str, quantity: int = 2) -> tuple[str, str]:
    """Seed one historic production line plus a valid immutable consumption image."""
    session.execute(models.warehouses.insert().values(
        id=WAREHOUSE_ID, organization_id=ORG_ID, branch_id=BRANCH_A, name="Almacén PCO005",
        status="active", created_at=NOW, updated_at=NOW,
    ))
    session.execute(models.inventory_units.insert().values(
        id=UNIT_ID, organization_id=ORG_ID, code="pz", name="Pieza", precision_scale=0, created_at=NOW,
    ))
    session.execute(models.inventory_items.insert().values(
        id=ITEM_ID, organization_id=ORG_ID, name="Ingrediente PCO005", sku="PCO005-ITEM",
        base_unit_id=UNIT_ID, item_type="ingredient", status="active", created_at=NOW, updated_at=NOW,
    ))
    session.execute(models.product_categories.insert().values(
        id=CATEGORY_ID, organization_id=ORG_ID, name="Comida PCO005", display_order=1, status="active",
        created_at=NOW, updated_at=NOW,
    ))
    session.execute(models.products.insert().values(
        id=PRODUCT_ID, organization_id=ORG_ID, category_id=CATEGORY_ID, name="Producto PCO005",
        sku="PCO005-PRODUCT", description=None, station="kitchen", status="active", created_at=NOW, updated_at=NOW,
    ))
    session.execute(models.price_versions.insert().values(
        id="018f6f73-2d0a-74f0-8f1c-000000009807", organization_id=ORG_ID, product_id=PRODUCT_ID,
        price_cents=250, currency="MXN", valid_from=NOW, valid_to=None, created_at=NOW,
    ))
    session.execute(models.recipes.insert().values(
        id=RECIPE_ID, organization_id=ORG_ID, product_id=PRODUCT_ID, output_item_id=None, branch_id=None,
        recipe_type="sale", version=1, status="active", yield_quantity=1, yield_unit_id=UNIT_ID,
        valid_from=NOW, valid_to=None, created_at=NOW, updated_at=NOW,
    ))
    session.execute(models.recipe_components.insert().values(
        recipe_id=RECIPE_ID, item_id=ITEM_ID, quantity_base_units=1, unit_id=UNIT_ID, net_quantity=1,
        waste_rate=0, gross_quantity=1, sort_order=0, notes=None,
    ))
    line_id = "018f6f73-2d0a-74f0-8f1c-000000009808"
    task_id = "018f6f73-2d0a-74f0-8f1c-000000009809"
    session.execute(models.order_lines.insert().values(
        id=line_id, order_id=order_id, product_id=PRODUCT_ID, product_name="Producto PCO005", quantity=quantity,
        unit_price_cents=250, line_total_cents=250 * quantity, station="kitchen", selected_modifiers=[],
        modifier_total_cents=0, line_notes=None, status="active", revision=1, supersedes_line_id=None,
        updated_at=None, removed_at=None, family_id_snapshot=CATEGORY_ID, family_name_snapshot="Comida PCO005",
        family_snapshot_source="captured", created_at=NOW,
    ))
    session.execute(models.order_line_consumption_snapshots.insert().values(
        order_line_id=line_id, order_id=order_id, recipe_id=RECIPE_ID, recipe_version=1, branch_id=BRANCH_A,
        components=[{"item_id": ITEM_ID, "item_name": "Ingrediente PCO005", "unit_id": UNIT_ID,
                     "unit_code": "pz", "net_quantity": quantity, "gross_quantity": quantity,
                     "waste_rate": 0, "unit_cost": 0, "total_cost": 0}],
        modifiers=[], total_theoretical_cost=0, created_at=NOW,
    ))
    session.execute(models.production_tasks.insert().values(
        id=task_id, organization_id=ORG_ID, branch_id=BRANCH_A, order_id=order_id, order_line_id=line_id,
        station="kitchen", status=status, product_name="Producto PCO005", quantity=quantity, created_at=NOW,
        started_at=NOW if status != "PENDING" else None, completed_at=NOW if status == "COMPLETED" else None,
    ))
    payment_id = session.execute(sa.select(models.payments.c.id).where(models.payments.c.order_id == order_id)).scalar_one()
    session.execute(models.sales_operation_snapshots.insert().values(
        id="018f6f73-2d0a-74f0-8f1c-000000009810", organization_id=ORG_ID, branch_id=BRANCH_A,
        payment_id=payment_id, order_id=order_id, cash_shift_id=SHIFT_ID, register_code_snapshot="CAJA-01",
        folio_snapshot="PCO005-production", service_type_snapshot="takeout", currency="MXN", gross_cents=500,
        net_cents=500, discount_cents=0, courtesy_cents=0, tax_cents=0, quality_status="captured",
        confirmed_at=NOW, created_at=NOW,
    ))
    session.commit()
    return line_id, task_id


def _approved_production_request(session, order_id: str, suffix: str) -> dict[str, object]:
    request = create_order_reopen_request(
        session, order_id, {"reason": "Corrección productiva", "evidence_refs": ["ticket:prod"]},
        f"request-prod-{suffix}", CHIEF_ID,
    )
    decide_order_reopen_request(
        session, request["id"], "APPROVED", {"decision_reason": "Dueño aprueba corrección"}, f"approve-prod-{suffix}", OWNER_ID,
    )
    return request


def _plan(lines: list[dict[str, object]], dispositions: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {"expected_order_version": 1, "lines": lines, "production_dispositions": dispositions or [],
            "settlement_method": "cash", "settlement_evidence_refs": [], "register_id": "CAJA-01"}


def _approved_simple_request(session, suffix: str) -> tuple[str, dict[str, object]]:
    order_id = _order(session, int(suffix[-1]) + 10)
    payment_id = session.execute(
        sa.select(models.payments.c.id).where(models.payments.c.order_id == order_id)
    ).scalar_one()
    session.execute(models.sales_operation_snapshots.insert().values(
        id=f"018f6f73-2d0a-74f0-8f1c-{9800 + int(suffix[-1]):012d}", organization_id=ORG_ID,
        branch_id=BRANCH_A, payment_id=payment_id, order_id=order_id, cash_shift_id=SHIFT_ID,
        register_code_snapshot="CAJA-01", folio_snapshot=f"PCO005-simple-{suffix}",
        service_type_snapshot="takeout", currency="MXN", gross_cents=500, net_cents=500,
        discount_cents=0, courtesy_cents=0, tax_cents=0, quality_status="captured",
        confirmed_at=NOW, created_at=NOW,
    ))
    session.commit()
    request = _approved_production_request(session, order_id, f"simple-{suffix}")
    return order_id, request


def test_owner_applies_approved_request_as_linked_refund_correction() -> None:
    """A correction is append-only and does not rewrite the closed sale."""
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session)
        payment_id = session.execute(
            sa.select(models.payments.c.id).where(models.payments.c.order_id == order_id)
        ).scalar_one()
        session.execute(
            models.sales_operation_snapshots.insert().values(
                id="018f6f73-2d0a-74f0-8f1c-000000009991",
                organization_id=ORG_ID,
                branch_id=BRANCH_A,
                payment_id=payment_id,
                order_id=order_id,
                cash_shift_id=SHIFT_ID,
                register_code_snapshot="CAJA-01",
                folio_snapshot="PCO005-1",
                service_type_snapshot="takeout",
                currency="MXN",
                gross_cents=500,
                net_cents=500,
                discount_cents=0,
                courtesy_cents=0,
                tax_cents=0,
                quality_status="captured",
                confirmed_at=NOW,
                created_at=NOW,
            )
        )
        session.commit()
        original = dict(
            session.execute(sa.select(models.orders).where(models.orders.c.id == order_id))
            .mappings()
            .one()
        )
        request = create_order_reopen_request(
            session,
            order_id,
            {"reason": "Corrección aprobada por Dueño", "evidence_refs": ["ticket:101"]},
            "pco005b-request-101",
            CHIEF_ID,
        )
        decide_order_reopen_request(
            session,
            request["id"],
            "APPROVED",
            {"decision_reason": "Dueño autoriza corrección exacta"},
            "pco005b-approve-101",
            OWNER_ID,
        )

        result = apply_order_reopen_request(
            session,
            request["id"],
            {
                "expected_order_version": 1,
                "lines": [],
                "production_dispositions": [],
                "settlement_method": "cash",
                "settlement_evidence_refs": [],
                "register_id": "CAJA-01",
            },
            "pco005b-apply-101",
            OWNER_ID,
        )

        assert result["status"] == "APPLIED"
        assert result["settlement_delta_cents"] == -500
        assert result["payment_adjustment"]["adjustment_type"] == "REFUND"
        assert result["correction"]["request_id"] == request["id"]
        assert (
            dict(
                session.execute(sa.select(models.orders).where(models.orders.c.id == order_id))
                .mappings()
                .one()
            )
            == original
        )
        assert (
            session.execute(
                sa.select(sa.func.count()).select_from(models.order_corrections)
            ).scalar_one()
            == 1
        )
    finally:
        session.close()
        engine.dispose()


def test_pending_partial_reduction_releases_only_difference_and_creates_operational_task() -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session)
        line_id, task_id = _production_fixture(session, order_id, "PENDING")
        request = _approved_production_request(session, order_id, "pending")

        result = apply_order_reopen_request(
            session, str(request["id"]), _plan([{"source_line_id": line_id, "quantity": 1}]),
            "apply-prod-pending", OWNER_ID,
        )

        assert [(row["adjustment_type"], str(row["quantity"])) for row in result["production_adjustments"]] == [("RELEASE", "1")]
        assert session.execute(sa.select(models.production_tasks.c.status).where(models.production_tasks.c.id == task_id)).scalar_one() == "CANCELLED"
        replacement = session.execute(sa.select(models.production_tasks).where(models.production_tasks.c.order_id == order_id, models.production_tasks.c.status == "PENDING")).mappings().one()
        assert replacement["quantity"] == 1
        release_adjustment = result["production_adjustments"][0]
        correction_line_id = session.execute(
            sa.select(models.order_correction_lines.c.operational_order_line_id).where(
                models.order_correction_lines.c.source_line_id == line_id
            )
        ).scalar_one()
        assert release_adjustment["production_task_id"] == replacement["id"]
        assert replacement["order_line_id"] == correction_line_id
        release = session.execute(sa.select(models.inventory_movements.c.quantity_delta).where(models.inventory_movements.c.movement_type == "RESERVATION_RELEASE")).scalar_one()
        assert str(release) == "1.000000"
    finally:
        session.close()
        engine.dispose()


def test_pending_total_reduction_has_no_replacement_task() -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session)
        line_id, task_id = _production_fixture(session, order_id, "PENDING")
        request = _approved_production_request(session, order_id, "pending-total")

        result = apply_order_reopen_request(
            session, str(request["id"]), _plan([]), "apply-prod-pending-total", OWNER_ID
        )

        release = result["production_adjustments"][0]
        assert release["adjustment_type"] == "RELEASE"
        assert str(release["quantity"]) == "2"
        assert release["production_task_id"] is None
        assert session.execute(
            sa.select(models.production_tasks.c.status).where(models.production_tasks.c.id == task_id)
        ).scalar_one() == "CANCELLED"
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.production_tasks).where(
                models.production_tasks.c.order_id == order_id,
                models.production_tasks.c.status == "PENDING",
            )
        ).scalar_one() == 0
        assert session.execute(
            sa.select(models.order_production_adjustments.c.production_task_id).where(
                models.order_production_adjustments.c.source_line_id == line_id
            )
        ).scalar_one() is None
    finally:
        session.close()
        engine.dispose()


def test_only_affected_in_progress_task_blocks_and_leaves_no_correction() -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session)
        line_id, _ = _production_fixture(session, order_id, "IN_PROGRESS")
        request = _approved_production_request(session, order_id, "progress")

        with pytest.raises(Exception) as failure:
            apply_order_reopen_request(
                session, str(request["id"]), _plan([{"source_line_id": line_id, "quantity": 1}]),
                "apply-prod-progress", OWNER_ID,
            )
        assert getattr(failure.value, "code", None) == "production_in_progress"
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 0
    finally:
        session.close()
        engine.dispose()


def test_unchanged_in_progress_task_is_not_a_global_reopen_block() -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session)
        line_id, _ = _production_fixture(session, order_id, "IN_PROGRESS")
        request = _approved_production_request(session, order_id, "progress-unchanged")

        result = apply_order_reopen_request(
            session,
            str(request["id"]),
            _plan([{"source_line_id": line_id, "quantity": 2}]),
            "apply-prod-progress-unchanged",
            OWNER_ID,
        )

        assert result["status"] == "APPLIED"
        assert result["production_adjustments"] == []
    finally:
        session.close()
        engine.dispose()


@pytest.mark.parametrize("disposition,movement", [("waste", "WASTE"), ("recovery", "RECOVERY")])
def test_completed_reduction_requires_exact_disposition_and_records_compensation(
    disposition: str, movement: str,
) -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session)
        line_id, task_id = _production_fixture(session, order_id, "COMPLETED")
        request = _approved_production_request(session, order_id, f"completed-{disposition}")
        base_plan = _plan([{"source_line_id": line_id, "quantity": 1}])
        with pytest.raises(Exception) as missing:
            apply_order_reopen_request(session, str(request["id"]), base_plan, f"apply-prod-missing-{disposition}", OWNER_ID)
        assert getattr(missing.value, "code", None) == "production_disposition_required"

        result = apply_order_reopen_request(
            session, str(request["id"]), _plan(
                [{"source_line_id": line_id, "quantity": 1}],
                [{"source_line_id": line_id, "source_task_id": task_id, "quantity": 1, "disposition": disposition}],
            ), f"apply-prod-completed-{disposition}", OWNER_ID,
        )
        assert result["production_adjustments"][0]["adjustment_type"] == movement
        stored = session.execute(sa.select(models.inventory_movements.c.quantity_delta).where(models.inventory_movements.c.movement_type == movement)).scalar_one()
        assert str(stored) == ("0.000000" if disposition == "waste" else "1.000000")
    finally:
        session.close()
        engine.dispose()


def test_addition_uses_current_recipe_snapshot_reservation_and_pending_task() -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session)
        _production_fixture(session, order_id, "PENDING")
        request = _approved_production_request(session, order_id, "addition")

        result = apply_order_reopen_request(
            session, str(request["id"]), _plan([{"product_id": PRODUCT_ID, "quantity": 1}]),
            "apply-prod-addition", OWNER_ID,
        )

        addition = next(row for row in result["production_adjustments"] if row["adjustment_type"] == "ADDITION")
        assert addition["production_task_id"]
        assert session.execute(sa.select(models.production_tasks.c.status).where(models.production_tasks.c.id == addition["production_task_id"])).scalar_one() == "PENDING"
        assert session.execute(sa.select(models.order_line_consumption_snapshots.c.order_line_id).where(models.order_line_consumption_snapshots.c.order_line_id == session.execute(sa.select(models.production_tasks.c.order_line_id).where(models.production_tasks.c.id == addition["production_task_id"])).scalar_one())).scalar_one()
        assert session.execute(sa.select(models.inventory_movements.c.quantity_delta).where(models.inventory_movements.c.id == addition["inventory_movement_id"])).scalar_one() == -1
    finally:
        session.close()
        engine.dispose()


def test_non_cash_delta_requires_evidence_but_not_a_register_and_does_not_touch_expected_cash() -> None:
    """TDD-TC-102/112: non-cash settlement is an adjustment, never cash ledger."""
    engine, session = _new_session()
    try:
        _actors(session)
        _, request = _approved_simple_request(session, "1")
        before = calculate_expected_cash(session, SHIFT_ID)
        with pytest.raises(BusinessError) as forbidden_register:
            apply_order_reopen_request(
                session, str(request["id"]),
                {
                    "expected_order_version": 1, "lines": [], "production_dispositions": [],
                    "settlement_method": "transfer", "settlement_evidence_refs": ["settlement:bank"],
                    "register_id": "CAJA-01",
                },
                "pco005b-noncash-register-forbidden", OWNER_ID,
            )
        assert forbidden_register.value.code == "order_reopen_plan_invalid"
        result = apply_order_reopen_request(
            session, str(request["id"]),
            {
                "expected_order_version": 1, "lines": [], "production_dispositions": [],
                "settlement_method": "transfer", "settlement_evidence_refs": ["settlement:bank"],
            },
            "pco005b-noncash-no-register", OWNER_ID,
        )
        assert result["payment_adjustment"]["method"] == "transfer"
        assert result["payment_adjustment"]["cash_movement_id"] is None
        assert calculate_expected_cash(session, SHIFT_ID) == before
    finally:
        session.close()
        engine.dispose()


@pytest.mark.parametrize(
    "bad_line",
    [
        {},
        {"quantity": 1},
        {"source_line_id": "line", "product_id": PRODUCT_ID, "quantity": 1},
        {"source_line_id": "line", "quantity": 1, "unexpected": True},
    ],
)
def test_apply_rejects_non_oneof_line_shapes_and_non_string_evidence(bad_line: dict[str, object]) -> None:
    """TDD-TC-101: runtime shape is the same closed oneOf as the schema."""
    engine, session = _new_session()
    try:
        _actors(session)
        _, request = _approved_simple_request(session, "8")
        with pytest.raises(BusinessError) as invalid:
            apply_order_reopen_request(
                session, str(request["id"]),
                {
                    "expected_order_version": 1, "lines": [bad_line], "production_dispositions": [],
                    "settlement_method": "cash", "settlement_evidence_refs": [], "register_id": "CAJA-01",
                },
                "pco005b-line-oneof-invalid", OWNER_ID,
            )
        assert invalid.value.code == "order_reopen_plan_invalid"
        with pytest.raises(BusinessError) as evidence:
            apply_order_reopen_request(
                session, str(request["id"]),
                {
                    "expected_order_version": 1, "lines": [], "production_dispositions": [],
                    "settlement_method": "transfer", "settlement_evidence_refs": [123],
                },
                "pco005b-evidence-type-invalid", OWNER_ID,
            )
        assert evidence.value.code == "order_reopen_plan_invalid"
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 0
    finally:
        session.close()
        engine.dispose()


def test_cash_register_is_required_even_for_zero_delta() -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session, 19)
        _production_fixture(session, order_id, "PENDING")
        request = _approved_production_request(session, order_id, "zero-cash")
        line_id = session.execute(sa.select(models.order_lines.c.id).where(
            models.order_lines.c.order_id == order_id, models.order_lines.c.status == "active"
        )).scalar_one()
        with pytest.raises(BusinessError) as missing:
            apply_order_reopen_request(
                session, str(request["id"]),
                {"expected_order_version": 1, "lines": [{"source_line_id": line_id, "quantity": 2}],
                 "production_dispositions": [], "settlement_method": "cash", "settlement_evidence_refs": []},
                "pco005b-zero-cash-register", OWNER_ID,
            )
        assert missing.value.code == "cash_register_required"
    finally:
        session.close()
        engine.dispose()


def test_apply_rechecks_request_state_after_sqlite_write_serialization() -> None:
    """TC-107 regression: a state changed before the write reservation cannot apply."""
    engine, session = _new_session()
    try:
        _actors(session)
        _, request = _approved_simple_request(session, "9")
        # Model the competing command completing before this apply obtains its
        # SQLite write reservation.  Apply must read REJECTED inside that
        # reservation, not use an earlier in-memory APPROVED mapping.
        session.execute(models.order_reopen_requests.update().where(
            models.order_reopen_requests.c.id == request["id"]
        ).values(status="REJECTED"))
        session.commit()
        with pytest.raises(BusinessError) as changed:
            apply_order_reopen_request(session, str(request["id"]), _plan([]), "pco005b-state-changed", OWNER_ID)
        assert changed.value.code == "order_reopen_transition_invalid"
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 0
    finally:
        session.close()
        engine.dispose()


def test_addition_respects_branch_availability_without_partial_facts() -> None:
    """TDD-TC-102/105: addition resolves availability at the correction branch."""
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session, 20)
        _production_fixture(session, order_id, "PENDING")
        request = _approved_production_request(session, order_id, "addition-unavailable")
        session.execute(models.branch_product_availability.insert().values(
            branch_id=BRANCH_A, product_id=PRODUCT_ID, is_available=False, updated_at=NOW,
        ))
        session.commit()
        with pytest.raises(BusinessError) as unavailable:
            apply_order_reopen_request(
                session, str(request["id"]), _plan([{"product_id": PRODUCT_ID, "quantity": 1}]),
                "pco005b-addition-branch-unavailable", OWNER_ID,
            )
        assert unavailable.value.code == "order_reopen_plan_invalid"
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 0
        assert session.execute(sa.select(models.order_reopen_requests.c.status).where(
            models.order_reopen_requests.c.id == request["id"]
        )).scalar_one() == "APPROVED"
    finally:
        session.close()
        engine.dispose()


def test_python_derives_positive_zero_and_one_cent_deltas_with_modifier_total() -> None:
    """TDD-TC-102: amounts are integer Python facts, including modifiers."""
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session, 21)
        line_id, _ = _production_fixture(session, order_id, "PENDING")
        # Two units at 250 plus a frozen modifier of two cents per unit.
        session.execute(models.order_lines.update().where(models.order_lines.c.id == line_id).values(
            line_total_cents=504, modifier_total_cents=4,
        ))
        session.execute(models.orders.update().where(models.orders.c.id == order_id).values(total_cents=504))
        session.execute(models.payments.update().where(models.payments.c.order_id == order_id).values(amount_cents=504))
        session.commit()
        request = _approved_production_request(session, order_id, "modifier-delta")
        result = apply_order_reopen_request(
            session, str(request["id"]), _plan([{"source_line_id": line_id, "quantity": 1}]),
            "pco005b-modifier-negative", OWNER_ID,
        )
        assert result["correction"]["corrected_total_cents"] == 252
        assert result["settlement_delta_cents"] == -252
        assert result["payment_adjustment"]["amount_cents"] == 252
    finally:
        session.close()
        engine.dispose()


def test_one_cent_refund_is_exact_integer_cents() -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session, 26)
        line_id, _ = _production_fixture(session, order_id, "PENDING")
        session.execute(models.order_lines.update().where(models.order_lines.c.id == line_id).values(
            unit_price_cents=1, line_total_cents=2,
        ))
        session.execute(models.orders.update().where(models.orders.c.id == order_id).values(total_cents=2))
        session.execute(models.payments.update().where(models.payments.c.order_id == order_id).values(amount_cents=2))
        session.commit()
        request = _approved_production_request(session, order_id, "one-cent")
        result = apply_order_reopen_request(
            session, str(request["id"]), _plan([{"source_line_id": line_id, "quantity": 1}]),
            "pco005b-one-cent-refund", OWNER_ID,
        )
        assert result["settlement_delta_cents"] == -1
        assert result["payment_adjustment"]["amount_cents"] == 1
    finally:
        session.close()
        engine.dispose()


def test_positive_charge_and_zero_delta_have_exact_append_only_financial_facts() -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session, 22)
        line_id, _ = _production_fixture(session, order_id, "PENDING")
        positive_request = _approved_production_request(session, order_id, "positive")
        positive = apply_order_reopen_request(
            session, str(positive_request["id"]), _plan([
                {"source_line_id": line_id, "quantity": 2}, {"product_id": PRODUCT_ID, "quantity": 1},
            ]), "pco005b-positive-charge", OWNER_ID,
        )
        assert positive["settlement_delta_cents"] == 250
        assert positive["payment_adjustment"]["adjustment_type"] == "CHARGE"
        assert positive["payment_adjustment"]["amount_cents"] == 250
    finally:
        session.close()
        engine.dispose()


def test_zero_delta_succeeds_with_register_without_payment_adjustment_or_cash_movement() -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session, 23)
        line_id, _ = _production_fixture(session, order_id, "PENDING")
        request = _approved_production_request(session, order_id, "zero-success")
        zero = apply_order_reopen_request(
            session, str(request["id"]), _plan([{"source_line_id": line_id, "quantity": 2}]),
            "pco005b-zero-success", OWNER_ID,
        )
        assert zero["settlement_delta_cents"] == 0
        assert zero["payment_adjustment"] is None
        assert session.execute(sa.select(sa.func.count()).select_from(models.cash_movements).where(
            models.cash_movements.c.source_type == "order_correction"
        )).scalar_one() == 0
    finally:
        session.close()
        engine.dispose()


def test_fractional_historic_snapshot_uses_decimal_not_current_recipe_and_addition_captures_new_recipe() -> None:
    """TDD-TC-105: historic fraction and new addition have distinct authorities."""
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session, 24)
        line_id, _ = _production_fixture(session, order_id, "PENDING")
        session.execute(models.order_line_consumption_snapshots.update().where(
            models.order_line_consumption_snapshots.c.order_line_id == line_id
        ).values(components=[{
            "item_id": ITEM_ID, "item_name": "Ingrediente PCO005", "unit_id": UNIT_ID,
            "unit_code": "pz", "net_quantity": "3.0", "gross_quantity": "3.0",
            "waste_rate": "0", "unit_cost": "0", "total_cost": "0",
        }]))
        # The active recipe has changed, but retained history must still release 3/2 = 1.5.
        session.execute(models.recipe_components.update().where(
            models.recipe_components.c.recipe_id == RECIPE_ID
        ).values(net_quantity=Decimal("7"), gross_quantity=Decimal("7"), quantity_base_units=Decimal("7")))
        session.commit()
        request = _approved_production_request(session, order_id, "decimal-snapshot")
        result = apply_order_reopen_request(
            session, str(request["id"]), _plan([
                {"source_line_id": line_id, "quantity": 1}, {"product_id": PRODUCT_ID, "quantity": 1},
            ]), "pco005b-decimal-snapshot", OWNER_ID,
        )
        release = next(row for row in result["production_adjustments"] if row["adjustment_type"] == "RELEASE")
        assert session.execute(sa.select(models.inventory_movements.c.quantity_delta).where(
            models.inventory_movements.c.id == release["inventory_movement_id"]
        )).scalar_one() == Decimal("1.500000")
        addition = next(row for row in result["production_adjustments"] if row["adjustment_type"] == "ADDITION")
        addition_line_id = session.execute(sa.select(models.production_tasks.c.order_line_id).where(
            models.production_tasks.c.id == addition["production_task_id"]
        )).scalar_one()
        new_snapshot = session.execute(sa.select(models.order_line_consumption_snapshots.c.components).where(
            models.order_line_consumption_snapshots.c.order_line_id == addition_line_id
        )).scalar_one()
        assert Decimal(str(new_snapshot[0]["gross_quantity"])) == Decimal("7.000000")
    finally:
        session.close()
        engine.dispose()


@pytest.mark.parametrize("components", [[], [{"item_id": ITEM_ID, "gross_quantity": 1}]])
def test_invalid_historic_snapshot_fails_closed_and_rolls_back(components: list[dict[str, object]]) -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session, 25)
        line_id, _ = _production_fixture(session, order_id, "PENDING")
        session.execute(models.order_line_consumption_snapshots.update().where(
            models.order_line_consumption_snapshots.c.order_line_id == line_id
        ).values(components=components))
        session.commit()
        request = _approved_production_request(session, order_id, "invalid-snapshot")
        with pytest.raises(BusinessError) as invalid:
            apply_order_reopen_request(
                session, str(request["id"]), _plan([{"source_line_id": line_id, "quantity": 1}]),
                "pco005b-invalid-snapshot", OWNER_ID,
            )
        assert invalid.value.code == "historical_snapshot_missing"
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 0
        assert session.execute(sa.select(models.order_reopen_requests.c.status).where(
            models.order_reopen_requests.c.id == request["id"]
        )).scalar_one() == "APPROVED"
    finally:
        session.close()
        engine.dispose()


def test_history_typescript_has_no_correction_total_or_delta_formula() -> None:
    source = (Path(__file__).resolve().parents[3] / "apps/pos-web/src/features/history/History.tsx").read_text(encoding="utf-8")
    assert not re.search(r"settlement_delta_cents\s*[+\-*/]", source)
    assert not re.search(r"corrected_total_cents\s*[+\-*/]", source)


def test_apply_same_key_with_different_plan_or_request_conflicts_without_response_leak() -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        _, first_request = _approved_simple_request(session, "1")
        key = "pco005b-same-key-different-plan"
        apply_order_reopen_request(session, str(first_request["id"]), _plan([]), key, OWNER_ID)
        with pytest.raises(BusinessError) as plan_conflict:
            apply_order_reopen_request(
                session, str(first_request["id"]),
                {"expected_order_version": 1, "lines": [], "production_dispositions": [],
                 "settlement_method": "transfer", "settlement_evidence_refs": ["bank:changed"]},
                key, OWNER_ID,
            )
        assert plan_conflict.value.code == "idempotency_conflict"
        _, second_request = _approved_simple_request(session, "2")
        with pytest.raises(BusinessError) as target_conflict:
            apply_order_reopen_request(session, str(second_request["id"]), _plan([]), key, OWNER_ID)
        assert target_conflict.value.code == "idempotency_conflict"
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 1
    finally:
        session.close()
        engine.dispose()


def test_apply_version_conflict_preserves_approved_request_without_correction() -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        order_id, request = _approved_simple_request(session, "3")
        session.execute(models.orders.update().where(models.orders.c.id == order_id).values(version=2))
        session.commit()
        with pytest.raises(BusinessError) as conflict:
            apply_order_reopen_request(
                session, str(request["id"]), _plan([]), "pco005b-version-conflict", OWNER_ID,
            )
        assert conflict.value.code == "order_version_conflict"
        assert session.execute(sa.select(models.order_reopen_requests.c.status).where(
            models.order_reopen_requests.c.id == request["id"]
        )).scalar_one() == "APPROVED"
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 0
    finally:
        session.close()
        engine.dispose()


def test_sqlite_file_race_two_apply_keys_leaves_one_correction(tmp_path: Path) -> None:
    """SQLite asserts the invariant; this is not evidence of row locks."""
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'pco005b-race.db'}", connect_args={"timeout": 1}
    )
    models.metadata.create_all(engine)
    try:
        with Session(engine) as seed:
            _seed_cash_concept_scope(seed)
            _insert_shift(seed)
            _actors(seed)
            _, request = _approved_simple_request(seed, "4")
            request_id = str(request["id"])
        barrier = Barrier(2)

        def apply(key: str) -> str:
            with Session(engine) as contender:
                barrier.wait(timeout=5)
                try:
                    return apply_order_reopen_request(contender, request_id, _plan([]), key, OWNER_ID)["status"]
                except BusinessError as error:
                    return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(apply, ("pco005b-sqlite-race-a", "pco005b-sqlite-race-b")))
        assert outcomes.count("APPLIED") == 1
        with Session(engine) as verify:
            assert verify.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 1
            assert verify.execute(sa.select(sa.func.count()).select_from(models.order_payment_adjustments)).scalar_one() == 1
            assert verify.execute(sa.select(sa.func.count()).select_from(models.cash_movements).where(
                models.cash_movements.c.source_type == "order_correction"
            )).scalar_one() == 1
    finally:
        engine.dispose()


def test_cash_requires_register_and_correction_cash_movement_changes_only_current_expected_cash() -> None:
    """TDD-TC-102/103/112: a refund is a current-shift withdrawal once."""
    engine, session = _new_session()
    try:
        _actors(session)
        _, request = _approved_simple_request(session, "2")
        plan = {
            "expected_order_version": 1, "lines": [], "production_dispositions": [],
            "settlement_method": "cash", "settlement_evidence_refs": [],
        }
        with pytest.raises(BusinessError) as missing_register:
            apply_order_reopen_request(session, str(request["id"]), plan, "pco005b-cash-no-register", OWNER_ID)
        assert missing_register.value.code == "cash_register_required"
        assert calculate_expected_cash(session, SHIFT_ID)["expected_cash_cents"] == 10_500
        result = apply_order_reopen_request(
            session, str(request["id"]), {**plan, "register_id": "CAJA-01"},
            "pco005b-cash-current-shift", OWNER_ID,
        )
        assert result["settlement_delta_cents"] == -500
        assert calculate_expected_cash(session, SHIFT_ID)["expected_cash_cents"] == 10_000
        assert session.execute(sa.select(sa.func.count()).select_from(models.cash_movements)).scalar_one() == 1
    finally:
        session.close()
        engine.dispose()


def test_apply_preserves_original_payment_snapshot_and_shift_rows() -> None:
    """TDD-TC-103: correction facts are linked; sale-era facts are byte-for-byte unchanged."""
    engine, session = _new_session()
    try:
        _actors(session)
        order_id, request = _approved_simple_request(session, "6")
        payment = dict(session.execute(sa.select(models.payments).where(
            models.payments.c.order_id == order_id
        )).mappings().one())
        snapshot = dict(session.execute(sa.select(models.sales_operation_snapshots).where(
            models.sales_operation_snapshots.c.order_id == order_id
        )).mappings().one())
        shift = dict(session.execute(sa.select(models.cash_shifts).where(
            models.cash_shifts.c.id == SHIFT_ID
        )).mappings().one())
        apply_order_reopen_request(session, str(request["id"]), _plan([]), "pco005b-immutable-facts", OWNER_ID)
        assert dict(session.execute(sa.select(models.payments).where(models.payments.c.id == payment["id"])).mappings().one()) == payment
        assert dict(session.execute(sa.select(models.sales_operation_snapshots).where(models.sales_operation_snapshots.c.id == snapshot["id"])).mappings().one()) == snapshot
        assert dict(session.execute(sa.select(models.cash_shifts).where(models.cash_shifts.c.id == SHIFT_ID)).mappings().one()) == shift
        adjustment = session.execute(sa.select(models.order_payment_adjustments)).mappings().one()
        assert adjustment["original_payment_id"] == payment["id"]
        assert adjustment["cash_shift_id"] == SHIFT_ID
    finally:
        session.close()
        engine.dispose()


def test_current_period_correction_is_separate_from_original_sales_and_reconciles_cash_closure() -> None:
    """TDD-TC-112: correction reporting is current/append-only, never a rewritten sale."""
    engine, session = _new_session()
    try:
        _actors(session)
        report_permission = "018f6f73-2d0a-74f0-8f1c-000000009899"
        session.execute(models.permissions.insert().values(
            id=report_permission, code="reports.sales.read", description="reports", created_at=NOW,
        ))
        session.execute(models.role_permissions.insert().values(
            role_id=CASHIER_ROLE_ID, permission_id=report_permission,
        ))
        session.commit()
        _, request = _approved_simple_request(session, "7")
        original_period = {"from_utc": NOW - timedelta(seconds=1), "to_utc": NOW + timedelta(seconds=1), "branch_id": BRANCH_A}
        service = ReportingProjectionService(session, CASHIER_ID)
        before = service.summary(original_period)
        assert before["summary"]["net"]["known_cents"] == 500
        assert before["corrections"]["count"] == 0

        result = apply_order_reopen_request(session, str(request["id"]), _plan([]), "pco005b-report-current", OWNER_ID)
        applied_at = datetime.fromisoformat(result["correction"]["applied_at"].replace("Z", "+00:00"))
        current_period = {
            "from_utc": applied_at - timedelta(seconds=1),
            "to_utc": applied_at + timedelta(seconds=1),
            "branch_id": BRANCH_A,
        }
        historical = service.summary(original_period)
        current = service.summary(current_period)
        drill = service.drill_down({**current_period, "metric": "net"})
        assert historical["summary"]["net"]["known_cents"] == 500
        assert historical["corrections"]["count"] == 0
        assert current["summary"]["order_count"] == 0
        assert current["corrections"] == {
            "count": 1, "charge_cents": 0, "refund_cents": 500,
            "net_delta_cents": -500, "cash_adjustment_count": 1,
        }
        assert drill["items"] == []
        assert drill["corrections"][0]["correction_id"] == result["correction"]["id"]
        assert calculate_expected_cash(session, SHIFT_ID)["expected_cash_cents"] == 10_000
        closed = close_cash_shift_operationally(session, SHIFT_ID, "pco005b-close-after-correction", CASHIER_ID)
        assert closed["closure"]["summary_snapshot"]["expected_cash_cents"] == 10_000
        with pytest.raises(BusinessError) as forbidden_legacy_cut:
            close_cash_shift_with_cut(session, 10_000, actor_user_id=CASHIER_ID)
        assert forbidden_legacy_cut.value.code == "legacy_cash_cut_forbidden"
    finally:
        session.close()
        engine.dispose()


def test_apply_requires_owner_authority_even_when_a_role_has_authorize_permission() -> None:
    """TDD-TC-106: PCO-005B cannot be granted by a look-alike operational role."""
    engine, session = _new_session()
    try:
        _actors(session)
        _, request = _approved_simple_request(session, "3")
        permission_id = session.execute(sa.select(models.permissions.c.id).where(
            models.permissions.c.code == "orders.reopen.authorize"
        )).scalar_one()
        session.execute(models.role_permissions.insert().values(role_id="018f6f73-2d0a-74f0-8f1c-000000009511", permission_id=permission_id))
        session.commit()
        with pytest.raises(AuthorizationError) as denied:
            apply_order_reopen_request(session, str(request["id"]), _plan([]), "pco005b-chief-denied", CHIEF_ID)
        assert denied.value.code == "permission_denied"
        assert session.execute(sa.select(models.order_reopen_requests.c.status).where(
            models.order_reopen_requests.c.id == request["id"]
        )).scalar_one() == "APPROVED"
    finally:
        session.close()
        engine.dispose()


@pytest.mark.parametrize("profile", ["Cajero", "Cajero jefe", "Líder", "Supervisor", "Administrador"])
def test_each_non_owner_profile_is_denied_even_with_reopen_authorize_permission(profile: str) -> None:
    """TDD-TC-106: labels/permissions cannot substitute organization owner authority."""
    engine, session = _new_session()
    try:
        _actors(session)
        _, request = _approved_simple_request(session, "6")
        permission_id = session.execute(sa.select(models.permissions.c.id).where(
            models.permissions.c.code == "orders.reopen.authorize"
        )).scalar_one()
        if profile == "Cajero":
            actor_id = CASHIER_ID
            role_id = CASHIER_ROLE_ID
        elif profile == "Cajero jefe":
            actor_id = CHIEF_ID
            role_id = "018f6f73-2d0a-74f0-8f1c-000000009511"
        else:
            suffix = {"Líder": "41", "Supervisor": "42", "Administrador": "43"}[profile]
            actor_id = f"018f6f73-2d0a-74f0-8f1c-0000000099{suffix}"
            role_id = f"018f6f73-2d0a-74f0-8f1c-0000000098{suffix}"
            session.execute(models.roles.insert().values(
                id=role_id, organization_id=ORG_ID, name=profile, scope="branch", created_at=NOW,
            ))
            session.execute(models.users.insert().values(
                id=actor_id, organization_id=ORG_ID, email=f"{suffix}@example.test", display_name=profile,
                status="active", created_at=NOW, updated_at=NOW,
            ))
            session.execute(models.user_roles.insert().values(
                user_id=actor_id, role_id=role_id, branch_id=BRANCH_A,
            ))
        session.execute(models.role_permissions.insert().values(role_id=role_id, permission_id=permission_id))
        session.commit()
        with pytest.raises(AuthorizationError) as denied:
            apply_order_reopen_request(
                session, str(request["id"]), _plan([]), f"pco005b-profile-denied-{profile}", actor_id,
            )
        assert denied.value.code == "permission_denied"
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 0
    finally:
        session.close()
        engine.dispose()


def test_cross_organization_actor_is_denied_before_idempotency_replay() -> None:
    engine, session = _new_session()
    try:
        _actors(session)
        _, request = _approved_simple_request(session, "7")
        other_org = "018f6f73-2d0a-74f0-8f1c-000000009701"
        outsider = "018f6f73-2d0a-74f0-8f1c-000000009702"
        session.execute(models.organizations.insert().values(
            id=other_org, name="Otra organización", status="active", created_at=NOW, updated_at=NOW,
        ))
        session.execute(models.users.insert().values(
            id=outsider, organization_id=other_org, email="outside@example.test", display_name="Outside",
            status="active", created_at=NOW, updated_at=NOW,
        ))
        session.commit()
        with pytest.raises(NotFoundError) as denied:
            apply_order_reopen_request(session, str(request["id"]), _plan([]), "pco005b-cross-org", outsider)
        assert denied.value.code == "order_reopen_request_not_found"
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 0
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_reopen_commands).where(
            models.order_reopen_commands.c.idempotency_key == "pco005b-cross-org"
        )).scalar_one() == 0
    finally:
        session.close()
        engine.dispose()


def test_apply_replay_is_stable_for_same_owner_and_conflicts_for_different_owner() -> None:
    """TDD-TC-107: replay has stable IDs but never changes command actor."""
    engine, session = _new_session()
    try:
        _actors(session)
        _, request = _approved_simple_request(session, "4")
        plan = _plan([])
        key = "pco005b-owner-replay-stable"
        first = apply_order_reopen_request(session, str(request["id"]), plan, key, OWNER_ID)
        assert apply_order_reopen_request(session, str(request["id"]), plan, key, OWNER_ID) == first
        with pytest.raises(BusinessError) as different_actor:
            apply_order_reopen_request(session, str(request["id"]), plan, key, SECOND_OWNER_ID)
        assert different_actor.value.code == "idempotency_conflict"
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 1
    finally:
        session.close()
        engine.dispose()


@pytest.mark.parametrize("failed_step", ["correction", "cash_movement", "payment_adjustment", "order_event", "reopen_request", "command", "audit"])
def test_failure_after_sensitive_write_rolls_back_and_a_clean_retry_applies_once(
    monkeypatch: pytest.MonkeyPatch, failed_step: str,
) -> None:
    """TDD-TC-109: no partial correction survives a failed post-write hook."""
    engine, session = _new_session()
    try:
        _actors(session)
        _, request = _approved_simple_request(session, "5")

        def fail_after_correction(step: str) -> None:
            if step == failed_step:
                raise RuntimeError("injected PCO-005B failure")

        monkeypatch.setattr("restaurant_os.operations._pco005b_after_sensitive_write", fail_after_correction)
        with pytest.raises(RuntimeError, match="injected"):
            apply_order_reopen_request(session, str(request["id"]), _plan([]), "pco005b-rollback-then-retry", OWNER_ID)
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 0
        assert session.execute(sa.select(models.order_reopen_requests.c.status).where(
            models.order_reopen_requests.c.id == request["id"]
        )).scalar_one() == "APPROVED"
        monkeypatch.setattr("restaurant_os.operations._pco005b_after_sensitive_write", lambda _step: None)
        result = apply_order_reopen_request(session, str(request["id"]), _plan([]), "pco005b-rollback-then-retry", OWNER_ID)
        assert result["status"] == "APPLIED"
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 1
    finally:
        session.close()
        engine.dispose()


@pytest.mark.parametrize(
    "scenario,failed_step",
    [
        ("pending", "correction_lines"),
        ("pending", "inventory_movement"),
        ("pending", "production_task"),
        ("pending", "replacement_task"),
        ("pending", "production_adjustment"),
        ("completed", "inventory_movement"),
        ("completed", "production_adjustment"),
        ("addition", "production_task"),
        ("addition", "production_adjustment"),
    ],
)
def test_production_sensitive_write_failure_rolls_back_every_fact_and_retries(
    monkeypatch: pytest.MonkeyPatch, scenario: str, failed_step: str,
) -> None:
    """TDD-TC-109 covers PENDING, COMPLETED and ADDITION write paths."""
    engine, session = _new_session()
    try:
        _actors(session)
        order_id = _order(session, 30)
        line_id, task_id = _production_fixture(
            session, order_id, "COMPLETED" if scenario == "completed" else "PENDING"
        )
        request = _approved_production_request(session, order_id, f"rollback-{scenario}-{failed_step}")
        if scenario == "completed":
            plan = _plan(
                [{"source_line_id": line_id, "quantity": 1}],
                [{"source_line_id": line_id, "source_task_id": task_id, "quantity": 1, "disposition": "recovery"}],
            )
        elif scenario == "addition":
            # Keep the historic line unchanged so no RELEASE path runs first;
            # this isolates reservation/snapshot/task writes of ADDITION.
            plan = _plan([
                {"source_line_id": line_id, "quantity": 2},
                {"product_id": PRODUCT_ID, "quantity": 1},
            ])
        else:
            plan = _plan([{"source_line_id": line_id, "quantity": 1}])

        def operational_fingerprint() -> dict[str, list[dict[str, object]]]:
            return {
                "order_lines": [dict(row) for row in session.execute(
                    sa.select(models.order_lines).where(models.order_lines.c.order_id == order_id)
                ).mappings()],
                "consumption_snapshots": [dict(row) for row in session.execute(
                    sa.select(models.order_line_consumption_snapshots).where(
                        models.order_line_consumption_snapshots.c.order_id == order_id
                    )
                ).mappings()],
                "production_tasks": [dict(row) for row in session.execute(
                    sa.select(models.production_tasks).where(models.production_tasks.c.order_id == order_id)
                ).mappings()],
                "inventory_movements": [dict(row) for row in session.execute(
                    sa.select(models.inventory_movements).where(
                        models.inventory_movements.c.source_type == "order_correction"
                    )
                ).mappings()],
            }

        before_operational = operational_fingerprint()

        def fail_selected(step: str) -> None:
            if step == failed_step:
                raise RuntimeError(f"injected {step}")

        monkeypatch.setattr("restaurant_os.operations._pco005b_after_sensitive_write", fail_selected)
        with pytest.raises(RuntimeError, match=f"injected {failed_step}"):
            apply_order_reopen_request(
                session, str(request["id"]), plan, f"pco005b-prod-fail-{scenario}-{failed_step}", OWNER_ID,
            )
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 0
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_payment_adjustments)).scalar_one() == 0
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_production_adjustments)).scalar_one() == 0
        assert session.execute(sa.select(models.order_reopen_requests.c.status).where(
            models.order_reopen_requests.c.id == request["id"]
        )).scalar_one() == "APPROVED"
        assert operational_fingerprint() == before_operational
        monkeypatch.setattr("restaurant_os.operations._pco005b_after_sensitive_write", lambda _step: None)
        applied = apply_order_reopen_request(
            session, str(request["id"]), plan, f"pco005b-prod-fail-{scenario}-{failed_step}", OWNER_ID,
        )
        assert applied["status"] == "APPLIED"
        assert session.execute(sa.select(sa.func.count()).select_from(models.order_corrections)).scalar_one() == 1
    finally:
        session.close()
        engine.dispose()
