"""PCO-007 RED/green contract coverage (TDD-TS-082, TC-121..128)."""
# ruff: noqa: E501

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

import pytest
from restaurant_os import models
from restaurant_os.operations import (
    AuthorizationError,
    BusinessError,
    ReportingProjectionService,
    get_effective_product_recipe,
    get_recipes_workspace,
    update_product_recipe_versioned,
)
from test_cash_ledger import BRANCH_A, CASHIER_ID, CASHIER_ROLE_ID, NOW, ORG_ID, _new_session

PRODUCT_ID = "018f6f73-2d0a-74f0-8f1c-000000007701"
ITEM_ID = "018f6f73-2d0a-74f0-8f1c-000000007702"
UNIT_ID = "018f6f73-2d0a-74f0-8f1c-000000007703"


def _seed_recipe_scope(session) -> None:
    session.execute(models.permissions.insert().values(
        id="018f6f73-2d0a-74f0-8f1c-000000007704", code="recipes.manage",
        description="recipes", created_at=NOW,
    ))
    session.execute(models.role_permissions.insert().values(
        role_id=CASHIER_ROLE_ID, permission_id="018f6f73-2d0a-74f0-8f1c-000000007704",
    ))
    session.execute(models.inventory_units.insert().values(
        id=UNIT_ID, organization_id=ORG_ID, code="kg", name="Kilogramo", precision_scale=3,
        created_at=NOW,
    ))
    session.execute(models.inventory_items.insert().values(
        id=ITEM_ID, organization_id=ORG_ID, name="Insumo PCO007", sku="PCO007-I",
        base_unit_id=UNIT_ID, item_type="ingredient", status="active", created_at=NOW,
        updated_at=NOW,
    ))
    session.execute(models.product_categories.insert().values(
        id="018f6f73-2d0a-74f0-8f1c-000000007705", organization_id=ORG_ID,
        name="PCO007", display_order=1, status="active", created_at=NOW, updated_at=NOW,
    ))
    session.execute(models.products.insert().values(
        id=PRODUCT_ID, organization_id=ORG_ID,
        category_id="018f6f73-2d0a-74f0-8f1c-000000007705", name="Producto PCO007",
        sku="PCO007-P", description=None, station="kitchen", status="active", created_at=NOW,
        updated_at=NOW,
    ))
    session.commit()


def test_recipe_version_is_scoped_idempotent_and_does_not_accept_client_costs() -> None:
    engine, session = _new_session()
    try:
        _seed_recipe_scope(session)
        payload = {
            "yield_quantity": "1", "yield_unit_id": UNIT_ID,
            "components": [{"item_id": ITEM_ID, "unit_id": UNIT_ID, "net_quantity": "0.250"}],
        }
        result = update_product_recipe_versioned(
            session, PRODUCT_ID, payload, BRANCH_A, None, "pco007-recipe-1", CASHIER_ID,
        )
        replay = update_product_recipe_versioned(
            session, PRODUCT_ID, payload, BRANCH_A, None, "pco007-recipe-1", CASHIER_ID,
        )
        assert replay["id"] == result["id"]
        assert result["branch_id"] == BRANCH_A
        assert result["components"][0]["net_quantity"] == Decimal("0.250")
        effective = get_effective_product_recipe(session, PRODUCT_ID, BRANCH_A, CASHIER_ID)
        assert effective and effective["source"] == "branch"
        with pytest.raises(BusinessError, match="unsupported fields"):
            update_product_recipe_versioned(
                session, PRODUCT_ID, {**payload, "cost": "1"}, BRANCH_A, result["id"],
                "pco007-recipe-1", CASHIER_ID,
            )
    finally:
        session.close()
        engine.dispose()


def test_pco007_rejection_metrics_are_safe(caplog: pytest.LogCaptureFixture) -> None:
    engine, session = _new_session()
    try:
        _seed_recipe_scope(session)
        caplog.set_level(logging.INFO, logger="restaurant_os.operations")
        with pytest.raises(BusinessError):
            ReportingProjectionService(session, CASHIER_ID).ingredient_sales({})
        with pytest.raises(AuthorizationError):
            get_recipes_workspace(session, CASHIER_ID, None)
        payload = {"yield_quantity": "1", "yield_unit_id": UNIT_ID,
                   "components": [{"item_id": ITEM_ID, "unit_id": UNIT_ID, "net_quantity": "1"}]}
        created = update_product_recipe_versioned(session, PRODUCT_ID, payload, BRANCH_A, None, "metric-one", CASHIER_ID)
        with pytest.raises(BusinessError):
            update_product_recipe_versioned(session, PRODUCT_ID, payload, BRANCH_A, None, "metric-two", CASHIER_ID)
        with pytest.raises(BusinessError):
            update_product_recipe_versioned(session, PRODUCT_ID, {**payload, "yield_quantity": "2"}, BRANCH_A, created["id"], "metric-one", CASHIER_ID)
        records = [record for record in caplog.records if getattr(record, "metric", "").startswith("pco007")]
        assert any(record.result == "denied" for record in records)
        assert any(record.result == "conflict" for record in records)
        for record in records:
            assert hasattr(record, "duration_ms")
            assert not {"actor_user_id", "payload", "components", "email"} & set(record.__dict__)
    finally:
        session.close()
        engine.dispose()


def test_report_projections_are_decimal_and_scope_fail_closed(caplog: pytest.LogCaptureFixture) -> None:
    engine, session = _new_session()
    try:
        _seed_recipe_scope(session)
        session.execute(models.permissions.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-000000007706", code="reports.ingredient_sales.read",
            description="ingredient report", created_at=NOW,
        ))
        session.execute(models.permissions.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-000000007707", code="reports.expenses.read",
            description="expense report", created_at=NOW,
        ))
        permission_ids = (
            "018f6f73-2d0a-74f0-8f1c-000000007706",
            "018f6f73-2d0a-74f0-8f1c-000000007707",
        )
        for permission_id in permission_ids:
            session.execute(models.role_permissions.insert().values(
                role_id=CASHIER_ROLE_ID, permission_id=permission_id
            ))
        session.commit()
        service = ReportingProjectionService(session, CASHIER_ID)
        caplog.set_level(logging.INFO, logger="restaurant_os.operations")
        period = {
            "from_utc": NOW - timedelta(seconds=1), "to_utc": NOW + timedelta(seconds=1),
            "branch_id": BRANCH_A,
        }
        assert service.ingredient_sales(period)["items"] == []
        assert service.expenses(period)["items"] == []
        metrics = {getattr(record, "metric", None): record for record in caplog.records}
        assert metrics["pco007.report.ingredient_sales"].result == "success"
        assert metrics["pco007.report.ingredient_sales"].item_count == 0
        assert metrics["pco007.report.expenses"].unknown_tax_count == 0
        with pytest.raises((AuthorizationError, BusinessError)):
            service.ingredient_sales({**period, "branch_id": "foreign"})
    finally:
        session.close()
        engine.dispose()


def test_ingredient_projection_uses_frozen_line_total_once_and_marks_incomplete() -> None:
    engine, session = _new_session()
    try:
        _seed_recipe_scope(session)
        session.execute(models.permissions.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-000000007708", code="reports.ingredient_sales.read",
            description="ingredient report", created_at=NOW,
        ))
        session.execute(models.role_permissions.insert().values(
            role_id=CASHIER_ROLE_ID, permission_id="018f6f73-2d0a-74f0-8f1c-000000007708"
        ))
        fixture_rows = (("good", [{"item_id": ITEM_ID, "unit_id": UNIT_ID,
                                     "gross_quantity": "2.500", "item_name": "Insumo",
                                     "unit_code": "kg"}]), ("bad", []))
        for index, (suffix, components) in enumerate(fixture_rows, start=1):
            operation = f"018f6f73-2d0a-74f0-8f1c-0000000077{index:02d}"
            line = f"line-{suffix}"
            session.execute(models.sales_operation_snapshots.insert().values(
                id=operation, organization_id=ORG_ID, branch_id=BRANCH_A,
                payment_id=f"payment-{suffix}", order_id=f"order-{suffix}", cash_shift_id="shift",
                register_code_snapshot="CAJA-01", folio_snapshot=suffix,
                service_type_snapshot="takeout", currency="MXN", gross_cents=1, net_cents=1,
                discount_cents=0, courtesy_cents=0, tax_cents=0, quality_status="captured",
                confirmed_at=NOW, created_at=NOW,
            ))
            session.execute(models.sales_operation_line_snapshots.insert().values(
                id=f"snapshot-line-{suffix}", sales_operation_snapshot_id=operation,
                payment_id=f"payment-{suffix}", order_line_id=line, product_id=PRODUCT_ID,
                product_name_snapshot="Producto", family_id_snapshot="family",
                family_name_snapshot="Familia",
                family_snapshot_source="captured", quantity=3, gross_cents=1, net_cents=1,
                discount_cents=0, courtesy_cents=0, tax_cents=0,
            ))
            session.execute(models.order_line_consumption_snapshots.insert().values(
                order_line_id=line, order_id=f"order-{suffix}", recipe_id="recipe",
                recipe_version=1,
                branch_id=BRANCH_A, components=components, modifiers=[], total_theoretical_cost=0,
                created_at=NOW,
            ))
        session.commit()
        report = ReportingProjectionService(session, CASHIER_ID).ingredient_sales({
            "from_utc": NOW - timedelta(seconds=1), "to_utc": NOW + timedelta(seconds=1),
            "branch_id": BRANCH_A,
        })
        assert report["items"][0]["quantity"] == "2.500"
        assert report["items"][0]["known_operation_count"] == 1
        assert report["incomplete_operation_count"] == 1
    finally:
        session.close()
        engine.dispose()


def _seed_correction_projection(session, suffix: str, *, desired: int | None, addition: bool = False,
                                incomplete: bool = False) -> tuple[str, str, str]:
    """Persist a minimal original sale plus one applied correction; no workflow mocks."""
    _seed_recipe_scope(session)
    permission = f"018f6f73-2d0a-74f0-8f1c-0000000078{suffix}"
    session.execute(models.permissions.insert().values(
        id=permission, code="reports.ingredient_sales.read", description="report", created_at=NOW,
    ))
    session.execute(models.role_permissions.insert().values(role_id=CASHIER_ROLE_ID, permission_id=permission))
    order_id, line_id, operation_id = (f"order-c-{suffix}", f"line-c-{suffix}", f"operation-c-{suffix}")
    session.execute(models.orders.insert().values(
        id=order_id, organization_id=ORG_ID, branch_id=BRANCH_A, cash_shift_id="shift-c", customer_id=None,
        customer_snapshot=None, delivery_address_snapshot=None, folio=f"C-{suffix}", channel="POS", status="CLOSED",
        total_cents=1, currency="MXN", owner_name=None, order_type="takeout", payment_method_intent=None,
        version=1, created_at=NOW, accepted_at=NOW,
    ))
    session.execute(models.order_lines.insert().values(
        id=line_id, order_id=order_id, product_id=PRODUCT_ID, product_name="Producto", quantity=3,
        unit_price_cents=1, line_total_cents=3, station="kitchen", selected_modifiers=[], modifier_total_cents=0,
        line_notes=None, status="active", revision=1, supersedes_line_id=None, updated_at=None, removed_at=None,
        family_id_snapshot="family", family_name_snapshot="Familia", family_snapshot_source="captured", created_at=NOW,
    ))
    session.execute(models.sales_operation_snapshots.insert().values(
        id=operation_id, organization_id=ORG_ID, branch_id=BRANCH_A, payment_id=f"payment-c-{suffix}", order_id=order_id,
        cash_shift_id="shift-c", register_code_snapshot="CAJA-01", folio_snapshot=f"C-{suffix}",
        service_type_snapshot="takeout", currency="MXN", gross_cents=3, net_cents=3, discount_cents=0,
        courtesy_cents=0, tax_cents=0, quality_status="captured", confirmed_at=NOW, created_at=NOW,
    ))
    session.execute(models.sales_operation_line_snapshots.insert().values(
        id=f"sales-line-c-{suffix}", sales_operation_snapshot_id=operation_id, payment_id=f"payment-c-{suffix}",
        order_line_id=line_id, product_id=PRODUCT_ID, product_name_snapshot="Producto", family_id_snapshot="family",
        family_name_snapshot="Familia", family_snapshot_source="captured", quantity=3, gross_cents=3, net_cents=3,
        discount_cents=0, courtesy_cents=0, tax_cents=0,
    ))
    components = [] if incomplete else [{"item_id": ITEM_ID, "unit_id": UNIT_ID, "gross_quantity": "2.500", "unit_code": "kg"}]
    session.execute(models.order_line_consumption_snapshots.insert().values(
        order_line_id=line_id, order_id=order_id, recipe_id="recipe-c", recipe_version=1, branch_id=BRANCH_A,
        components=components, modifiers=[], total_theoretical_cost=0, created_at=NOW,
    ))
    correction_id, request_id = f"correction-{suffix}", f"request-{suffix}"
    applied = NOW + timedelta(days=1)
    session.execute(models.order_reopen_requests.insert().values(
        id=request_id, organization_id=ORG_ID, branch_id=BRANCH_A, order_id=order_id, status="APPLIED",
        order_version_snapshot=1, order_status_snapshot="CLOSED", before_snapshot={}, reason="Corrección", evidence_refs=["e"],
        requested_by_user_id=CASHIER_ID, requested_at=NOW, decided_by_user_id=CASHIER_ID, decided_at=NOW,
        decision_reason="Aprobada", applied_by_user_id=CASHIER_ID, applied_at=applied, created_at=NOW, updated_at=applied,
    ))
    session.execute(models.order_corrections.insert().values(
        id=correction_id, organization_id=ORG_ID, branch_id=BRANCH_A, order_id=order_id, request_id=request_id,
        folio=f"COR-{suffix}", captured_order_version=1, resulting_order_version=1, before_snapshot={}, after_snapshot={},
        currency="MXN", corrected_total_cents=1, settlement_delta_cents=0, status="APPLIED",
        actor_user_id=CASHIER_ID, applied_at=applied,
    ))
    if desired is not None:
        session.execute(models.order_correction_lines.insert().values(
            id=f"correction-line-{suffix}", correction_id=correction_id, source_line_id=line_id,
            operational_order_line_id=None, product_id=PRODUCT_ID, product_name_snapshot="Producto",
            family_name_snapshot="Familia", unit_price_cents=1, quantity=desired, modifiers_snapshot=[],
            line_total_cents=desired, classification="RETAINED",
        ))
    if addition:
        add_line = f"addition-{suffix}"
        session.execute(models.order_line_consumption_snapshots.insert().values(
            order_line_id=add_line, order_id=order_id, recipe_id="recipe-add", recipe_version=2, branch_id=BRANCH_A,
            components=[{"item_id": ITEM_ID, "unit_id": UNIT_ID, "gross_quantity": "1.000", "unit_code": "kg"}],
            modifiers=[], total_theoretical_cost=0, created_at=applied,
        ))
        session.execute(models.order_correction_lines.insert().values(
            id=f"addition-correction-{suffix}", correction_id=correction_id, source_line_id=None,
            operational_order_line_id=add_line, product_id=PRODUCT_ID, product_name_snapshot="Extra",
            family_name_snapshot="Familia", unit_price_cents=1, quantity=1, modifiers_snapshot=[], line_total_cents=1,
            classification="ADDITION",
        ))
    session.commit()
    return order_id, operation_id, correction_id


def test_correction_retained_delta_is_at_applied_period_and_quantized() -> None:
    engine, session = _new_session()
    try:
        _seed_correction_projection(session, "81", desired=2)
        service = ReportingProjectionService(session, CASHIER_ID)
        report = service.ingredient_sales({"from_utc": NOW + timedelta(hours=12), "to_utc": NOW + timedelta(days=2), "branch_id": BRANCH_A})
        expected = format(Decimal("2.500") * (Decimal(2) / Decimal(3) - 1), "f")
        assert report["items"][0]["quantity"] == format(Decimal(expected).quantize(Decimal("0.000001")), "f")
    finally:
        session.close()
        engine.dispose()


def test_correction_omitted_line_and_addition_reconcile_combined_period() -> None:
    engine, session = _new_session()
    try:
        _seed_correction_projection(session, "82", desired=None, addition=True)
        report = ReportingProjectionService(session, CASHIER_ID).ingredient_sales({"from_utc": NOW - timedelta(seconds=1), "to_utc": NOW + timedelta(days=2), "branch_id": BRANCH_A})
        assert report["items"][0]["quantity"] == "1.000000"
    finally:
        session.close()
        engine.dispose()


def test_incomplete_correction_is_counted_once_and_contributes_nothing() -> None:
    engine, session = _new_session()
    try:
        _seed_correction_projection(session, "83", desired=2, incomplete=True)
        service = ReportingProjectionService(session, CASHIER_ID)
        report = service.ingredient_sales({"from_utc": NOW + timedelta(hours=12), "to_utc": NOW + timedelta(days=2), "branch_id": BRANCH_A})
        assert report["items"] == [] and report["incomplete_operation_count"] == 1
    finally:
        session.close()
        engine.dispose()


def _expense_service(session):
    _seed_recipe_scope(session)
    permission = "018f6f73-2d0a-74f0-8f1c-000000007890"
    session.execute(models.permissions.insert().values(id=permission, code="reports.expenses.read", description="r", created_at=NOW))
    session.execute(models.role_permissions.insert().values(role_id=CASHIER_ROLE_ID, permission_id=permission))
    ingredient = "018f6f73-2d0a-74f0-8f1c-000000007891"
    session.execute(models.permissions.insert().values(id=ingredient, code="reports.ingredient_sales.read", description="r", created_at=NOW))
    session.execute(models.role_permissions.insert().values(role_id=CASHIER_ROLE_ID, permission_id=ingredient))
    session.commit()
    return ReportingProjectionService(session, CASHIER_ID)


def _movement(session, identifier, kind, amount, source=None, linked=None):
    session.execute(models.cash_movements.insert().values(
        id=identifier, organization_id=ORG_ID, branch_id=BRANCH_A, cash_shift_id="expense-shift",
        movement_type=kind, amount_cents=amount, reason_code="TEST", reason="test", source_type=source,
        source_id=None, actor_user_id=CASHIER_ID, idempotency_key=f"key-{identifier}", status="confirmed",
        reversal_of_id=linked, concept_id=None, concept_version_id=None, concept_snapshot=None, reference=None,
        evidence_refs=[], compensates_movement_id=None, created_at=NOW,
    ))


def test_expenses_purchase_cash_and_cancellation_are_canonical() -> None:
    engine, session = _new_session()
    try:
        service = _expense_service(session)
        session.execute(models.suppliers.insert().values(id="supplier-exp", organization_id=ORG_ID, code="EXP", commercial_name="Proveedor", country="MX", credit_days=0, currency="MXN", delivery_days=[], payment_methods=[], created_at=NOW, updated_at=NOW, status="active"))
        session.execute(models.purchase_documents.insert().values(id="purchase-exp", organization_id=ORG_ID, branch_id=BRANCH_A, supplier_id="supplier-exp", document_type="ticket", folio="EXP-1", document_date=NOW, subtotal=100, discount_total=0, tax_total=16, freight_total=0, total=116, payment_method="cash", paid_from_cash=True, cash_movement_id=None, evidence_url=None, notes=None, status="cancelled", created_by=CASHIER_ID, confirmed_by=CASHIER_ID, cancelled_by=CASHIER_ID, confirmation_idempotency_key=None, cancellation_reason="x", created_at=NOW, confirmed_at=NOW, cancelled_at=NOW + timedelta(days=1)))
        _movement(session, "purchase-withdrawal", "withdrawal", 11600, "purchase")
        session.commit()
        positive = service.expenses({"from_utc": NOW-timedelta(seconds=1), "to_utc": NOW+timedelta(seconds=1), "branch_id": BRANCH_A})
        negative = service.expenses({"from_utc": NOW+timedelta(hours=12), "to_utc": NOW+timedelta(days=2), "branch_id": BRANCH_A})
        assert positive["items"][0]["total_cents"] == 11600 and positive["items"][0]["tax_cents"] == 1600
        assert negative["items"][0]["total_cents"] == -11600
    finally:
        session.close()
        engine.dispose()


def test_expenses_manual_withdrawal_compensation_and_exclusions() -> None:
    engine, session = _new_session()
    try:
        service = _expense_service(session)
        _movement(session, "manual", "withdrawal", 100)
        _movement(session, "compensation", "deposit", 100, "compensation", "manual")
        _movement(session, "deposit", "deposit", 100)
        _movement(session, "correction", "withdrawal", 100, "order_correction")
        session.commit()
        report = service.expenses({"from_utc": NOW-timedelta(seconds=1), "to_utc": NOW+timedelta(seconds=1), "branch_id": BRANCH_A})
        assert sorted(item["total_cents"] for item in report["items"]) == [-100, 100]
        assert report["unknown_tax_source_count"] == 2
    finally:
        session.close()
        engine.dispose()


def test_report_cursor_is_stable_and_bound_to_filters() -> None:
    engine, session = _new_session()
    try:
        service = _expense_service(session)
        _movement(session, "one", "withdrawal", 1)
        _movement(session, "two", "withdrawal", 2)
        session.commit()
        raw = {"from_utc": NOW-timedelta(seconds=1), "to_utc": NOW+timedelta(seconds=1), "branch_id": BRANCH_A, "limit": 1}
        first = service.expenses(raw)
        second = service.expenses({**raw, "cursor": first["next_cursor"]})
        assert first["items"][0]["id"] != second["items"][0]["id"]
        with pytest.raises(BusinessError, match="cursor"):
            service.ingredient_sales({**raw, "cursor": first["next_cursor"]})
    finally:
        session.close()
        engine.dispose()
