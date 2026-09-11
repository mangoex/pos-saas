# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-ingredient-tests-v1
# ruff: noqa: E501

"""Focused API checks for add-only ingredient extras and legacy compatibility."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    BRANCH_ID,
    list_product_modifiers,
)
from test_platform_api import (
    _admin_headers,
    _client_with_seeded_database,
    _open_shift,
    _test_session_factory,
)

BURGER_ID = "018f6f73-2d0a-74f0-8f1c-000000000111"
BEEF_ID = "018f6f73-2d0a-74f0-8f1c-000000000311"
SYRUP_ID = "018f6f73-2d0a-74f0-8f1c-000000000314"
SODA_ID = "018f6f73-2d0a-74f0-8f1c-000000000113"
BUSINESS_UNIT_ID = "018f6f73-2d0a-74f0-8f1c-000000000015"
WAREHOUSE_ID = "018f6f73-2d0a-74f0-8f1c-000000000004"
UTC = timezone.utc


def _assignment_payload() -> dict[str, object]:
    return {
        "product_ids": [BURGER_ID],
        "category_ids": [],
        "allow_add": True,
        "allow_remove": False,
        "add_quantity": "0.050000",
        "remove_quantity": "0",
        "charge_additional": False,
        "add_price_delta_cents": 0,
    }


def _canonical_extra_payload(inventory_item_id: str, **overrides: object) -> dict[str, object]:
    return {
        "inventory_item_id": inventory_item_id,
        "portion_quantity": "1.000000",
        "sale_price_cents": 0,
        "station": "kitchen",
        **overrides,
    }


def _insert_legacy_ingredient_assignment(
    client: Any,
    variation_id: str,
    *,
    prefix: str,
    variation_status: str = "active",
    portion_quantity: str = "1.000000",
    station: str | None = "kitchen",
) -> dict[str, str]:
    factory = _test_session_factory(client)
    group_id = f"{prefix}-group"
    add_option_id = f"{prefix}-add-option"
    remove_option_id = f"{prefix}-remove-option"
    assignment_id = f"{prefix}-assignment"
    now = datetime.now(timezone.utc)
    with factory() as session:
        variation = session.execute(
            sa.select(models.ingredient_variations).where(
                models.ingredient_variations.c.id == variation_id
            )
        ).mappings().one()
        session.execute(
            models.ingredient_variations.update()
            .where(models.ingredient_variations.c.id == variation_id)
            .values(
                status=variation_status,
                portion_quantity=portion_quantity,
                sale_price_cents=0,
                station=station,
                display_order=0,
                updated_at=now,
            )
        )
        session.execute(
            models.modifier_groups.insert().values(
                id=group_id,
                organization_id=variation["organization_id"],
                product_id=BURGER_ID,
                name=f"Histórico {prefix}",
                is_required=False,
                minimum_selections=0,
                maximum_selections=2,
                station=station,
                display_order=900,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.modifier_options.insert(),
            [
                {
                    "id": add_option_id,
                    "group_id": group_id,
                    "name": variation["add_label"],
                    "effect_type": "add",
                    "price_delta_cents": 0,
                    "affected_item_id": variation["inventory_item_id"],
                    "replacement_item_id": None,
                    "remove_quantity": "0",
                    "add_quantity": "1",
                    "inventory_effect": True,
                    "kitchen_text": variation["add_label"],
                    "station": station,
                    "display_order": 0,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": remove_option_id,
                    "group_id": group_id,
                    "name": variation["remove_label"],
                    "effect_type": "remove",
                    "price_delta_cents": 0,
                    "affected_item_id": variation["inventory_item_id"],
                    "replacement_item_id": None,
                    "remove_quantity": "1",
                    "add_quantity": "0",
                    "inventory_effect": True,
                    "kitchen_text": variation["remove_label"],
                    "station": station,
                    "display_order": 1,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        session.execute(
            models.ingredient_variation_products.insert().values(
                id=assignment_id,
                variation_id=variation_id,
                product_id=BURGER_ID,
                allow_add=True,
                allow_remove=True,
                add_quantity="1",
                remove_quantity="1",
                charge_additional=False,
                add_price_delta_cents=0,
                add_option_id=add_option_id,
                remove_option_id=remove_option_id,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    return {
        "assignment_id": assignment_id,
        "add_option_id": add_option_id,
        "remove_option_id": remove_option_id,
    }


def test_ingredient_variation_assignment_mutation_routes_are_read_only() -> None:
    client = _client_with_seeded_database()
    created = client.post(
        "/api/v1/catalog/ingredient-variations",
        headers=_admin_headers(),
        json=_canonical_extra_payload(BEEF_ID),
    )
    assert created.status_code == 200
    variation = created.json()
    payload = _assignment_payload()
    headers = {**_admin_headers(), "Idempotency-Key": "ingredient-variation-apply-0001"}
    url = f"/api/v1/catalog/ingredient-variations/{variation['id']}/assignments"
    responses = [
        client.post(f"{url}/preview", headers=_admin_headers(), json=payload),
        client.put(url, headers=headers, json=payload),
        client.put(f"{url}/{BURGER_ID}", headers=headers, json=payload),
        client.delete(f"{url}/{BURGER_ID}", headers=_admin_headers()),
    ]
    assert all(response.status_code == 409 for response in responses)
    assert {
        response.json()["detail"]["code"] for response in responses
    } == {"ingredient_variation_assignments_read_only"}
    factory = _test_session_factory(client)
    with factory() as session:
        assert session.execute(
            sa.select(sa.func.count())
            .select_from(models.ingredient_variation_products)
            .where(models.ingredient_variation_products.c.variation_id == variation["id"])
        ).scalar_one() == 0
        assert session.execute(
            sa.select(sa.func.count())
            .select_from(models.ingredient_variation_commands)
            .where(
                models.ingredient_variation_commands.c.idempotency_key
                == "ingredient-variation-apply-0001"
            )
        ).scalar_one() == 0


def test_explicit_surcharge_cents_are_preserved_in_runtime_and_order_total() -> None:
    client = _client_with_seeded_database()
    variation = client.post(
        "/api/v1/catalog/ingredient-variations",
        headers=_admin_headers(),
        json=_canonical_extra_payload(
            BEEF_ID,
            portion_quantity="0.050000",
            sale_price_cents=2050,
        ),
    ).json()
    available = client.get(
        "/api/v1/catalog/ingredient-extras/available", headers=_admin_headers()
    ).json()
    assert next(row for row in available if row["extra_id"] == variation["id"])["price_cents"] == 2050
    assert _open_shift(client, 10000).status_code == 200
    order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "lines": [
                {
                    "product_id": BURGER_ID,
                    "quantity": 1,
                    "ingredient_extras": [{"extra_id": variation["id"], "portions": 1}],
                }
            ]
        },
    )
    assert order.status_code == 200
    assert order.json()["lines"][0]["modifier_total_cents"] == 2050


def test_canonical_portions_reject_float_bool_and_nonfinite_values() -> None:
    client = _client_with_seeded_database()
    for invalid in (0, -1, 0.125, True, "NaN", "Infinity", "0.0000005"):
        response = client.post(
            "/api/v1/catalog/ingredient-variations",
            headers=_admin_headers(),
            json=_canonical_extra_payload(BEEF_ID, portion_quantity=invalid),
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "invalid_variation_quantity"


def test_unrelated_modifier_options_remain_visible() -> None:
    client = _client_with_seeded_database()
    factory = _test_session_factory(client)
    with factory() as session:
        now = datetime.now(timezone.utc)
        session.execute(
            models.modifier_groups.insert().values(
                id="ordinary-modifier-group",
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                product_id=BURGER_ID,
                name="Personalización ordinaria",
                is_required=False,
                minimum_selections=0,
                maximum_selections=2,
                station=None,
                display_order=800,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.modifier_options.insert(),
            [
                {
                    "id": "ordinary-add-option",
                    "group_id": "ordinary-modifier-group",
                    "name": "Agregar salsa",
                    "effect_type": "add",
                    "price_delta_cents": 0,
                    "affected_item_id": None,
                    "replacement_item_id": None,
                    "remove_quantity": "0",
                    "add_quantity": "0",
                    "inventory_effect": False,
                    "kitchen_text": "Agregar salsa",
                    "station": None,
                    "display_order": 0,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": "ordinary-remove-option",
                    "group_id": "ordinary-modifier-group",
                    "name": "Sin salsa",
                    "effect_type": "remove",
                    "price_delta_cents": 0,
                    "affected_item_id": None,
                    "replacement_item_id": None,
                    "remove_quantity": "0",
                    "add_quantity": "0",
                    "inventory_effect": False,
                    "kitchen_text": "Sin salsa",
                    "station": None,
                    "display_order": 1,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        session.commit()
    with factory() as session:
        modifiers = list_product_modifiers(
            session,
            BURGER_ID,
            organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
        )
    option_ids = {option["id"] for group in modifiers for option in group["options"]}
    assert {"ordinary-add-option", "ordinary-remove-option"} <= option_ids


def test_needs_review_legacy_options_are_hidden_and_cannot_create_orders() -> None:
    client = _client_with_seeded_database()
    variation = client.post(
        "/api/v1/catalog/ingredient-variations",
        headers=_admin_headers(),
        json=_canonical_extra_payload(BEEF_ID),
    ).json()
    legacy = _insert_legacy_ingredient_assignment(
        client,
        variation["id"],
        prefix="needs-review-legacy",
        variation_status="needs_review",
        portion_quantity="0",
        station=None,
    )
    factory = _test_session_factory(client)
    modifiers = client.get(
        f"/api/v1/products/{BURGER_ID}/modifiers", headers=_admin_headers()
    )
    assert modifiers.status_code == 200
    option_ids = {option["id"] for group in modifiers.json() for option in group["options"]}
    assert not {legacy["add_option_id"], legacy["remove_option_id"]} & option_ids
    central = client.get(
        f"/api/v1/products/{BURGER_ID}/modifier-groups", headers=_admin_headers()
    )
    assert central.status_code == 200
    central_options = {
        option["id"]: (group["id"], option)
        for group in central.json()
        for option in group["options"]
    }
    assert central_options[legacy["add_option_id"]][1]["variation_kind"] == "ingredient_extra"
    assert central_options[legacy["remove_option_id"]][1]["variation_kind"] == "ingredient_extra"
    protected_create = client.post(
        f"/api/v1/modifier-groups/{central_options[legacy['add_option_id']][0]}/options",
        headers=_admin_headers(),
        json={"name": "No contaminar", "effect_type": "instruction"},
    )
    assert protected_create.status_code == 409
    assert protected_create.json()["detail"]["code"] == "modifier_catalog_managed_elsewhere"
    with factory() as session:
        before_orders = session.execute(
            sa.select(sa.func.count()).select_from(models.orders)
        ).scalar_one()
    assert _open_shift(client, 10000).status_code == 200
    for option_id in (legacy["add_option_id"], legacy["remove_option_id"]):
        response = client.post(
            "/api/v1/orders",
            headers=_admin_headers(),
            json={
                "lines": [
                    {
                        "product_id": BURGER_ID,
                        "quantity": 1,
                        "modifiers": [{"option_id": option_id}],
                    }
                ]
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ingredient_extra_add_only"
    with factory() as session:
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.orders)
        ).scalar_one() == before_orders


def test_definition_defaults_labels_lifecycle_events_and_assignment_detail() -> None:
    client = _client_with_seeded_database()
    created = client.post(
        "/api/v1/catalog/ingredient-variations",
        headers=_admin_headers(),
        json=_canonical_extra_payload(BEEF_ID),
    )
    assert created.status_code == 200
    variation = created.json()
    assert variation["add_label"] == "Con carne molida"
    assert variation["remove_label"] == "Sin carne molida"
    listed = client.get("/api/v1/catalog/ingredient-variations", headers=_admin_headers()).json()
    assert next(row for row in listed if row["id"] == variation["id"])["unit_code"] == "g"
    duplicate = client.post(
        "/api/v1/catalog/ingredient-variations",
        headers=_admin_headers(),
        json=_canonical_extra_payload(BEEF_ID),
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "ingredient_variation_exists"
    null_label = client.post(
        "/api/v1/catalog/ingredient-variations",
        headers=_admin_headers(),
        json={"inventory_item_id": SYRUP_ID, "add_label": None},
    )
    assert null_label.status_code == 409
    assert null_label.json()["detail"]["code"] == "invalid_ingredient_variation_label"
    url = f"/api/v1/catalog/ingredient-variations/{variation['id']}"
    _insert_legacy_ingredient_assignment(
        client, variation["id"], prefix="detail-history"
    )
    updated = client.put(url, headers=_admin_headers(), json={"add_label": "Con proteína"})
    assert updated.status_code == 200
    factory = _test_session_factory(client)
    detail = client.get(url, headers=_admin_headers()).json()
    assert detail["assignments"][0]["product_sku"] == "KIWI-BURGER"
    assert detail["assignments"][0]["category_name"] == "Comida"
    assert client.put(url, headers=_admin_headers(), json={"status": "archived"}).status_code == 200
    assert client.put(url, headers=_admin_headers(), json={"status": "active"}).status_code == 200
    with factory() as session:
        actions = set(
            session.execute(
                sa.select(models.audit_events.c.action).where(
                    models.audit_events.c.entity_id == variation["id"]
                )
            ).scalars()
        )
    assert {
        "ingredient_variation.created",
        "ingredient_variation.updated",
        "ingredient_variation.archived",
        "ingredient_variation.reactivated",
    } <= actions


def test_order_comment_product_relations_remain_editable() -> None:
    client = _client_with_seeded_database()
    created = client.post(
        "/api/v1/catalog/order-comments/bulk",
        headers=_admin_headers(),
        json={"comments": "Sin picante", "product_ids": [BURGER_ID]},
    )
    assert created.status_code == 200
    comment_id = created.json()["items"][0]["id"]
    updated = client.put(
        f"/api/v1/catalog/order-comments/{comment_id}/products",
        headers=_admin_headers(),
        json={"product_ids": [SODA_ID]},
    )
    assert updated.status_code == 200
    assert [row["product_id"] for row in updated.json()["products"]] == [SODA_ID]


def test_read_only_assignment_routes_preserve_historical_fixture() -> None:
    client = _client_with_seeded_database()
    variation = client.post(
        "/api/v1/catalog/ingredient-variations",
        headers=_admin_headers(),
        json=_canonical_extra_payload(BEEF_ID),
    ).json()
    legacy = _insert_legacy_ingredient_assignment(
        client, variation["id"], prefix="preserved-history"
    )
    url = f"/api/v1/catalog/ingredient-variations/{variation['id']}/assignments"
    bulk = client.put(
        url,
        headers={**_admin_headers(), "Idempotency-Key": "preserved-history"},
        json=_assignment_payload(),
    )
    archived = client.delete(
        f"{url}/{BURGER_ID}",
        headers=_admin_headers(),
    )
    assert bulk.status_code == archived.status_code == 409
    factory = _test_session_factory(client)
    with factory() as session:
        assignment = session.execute(
            sa.select(models.ingredient_variation_products).where(
                models.ingredient_variation_products.c.id == legacy["assignment_id"]
            )
        ).mappings().one()
        assert assignment["status"] == "active"
        statuses = set(
            session.execute(
                sa.select(models.modifier_options.c.status).where(
                    models.modifier_options.c.id.in_(
                        [legacy["add_option_id"], legacy["remove_option_id"]]
                    )
                )
            ).scalars()
        )
        assert statuses == {"active"}


def test_universal_ingredient_additions_preserve_snapshot_cost_and_kitchen_history() -> None:
    client = _client_with_seeded_database()
    factory = _test_session_factory(client)
    with factory() as session:
        session.execute(
            models.inventory_cost_states.delete().where(
                models.inventory_cost_states.c.branch_id == BRANCH_ID,
                models.inventory_cost_states.c.warehouse_id == WAREHOUSE_ID,
                models.inventory_cost_states.c.item_id.in_([BEEF_ID, SYRUP_ID]),
            )
        )
        now = datetime.now(timezone.utc)
        session.execute(
            models.inventory_cost_states.insert(),
            [
                {"branch_id": BRANCH_ID, "warehouse_id": WAREHOUSE_ID, "item_id": BEEF_ID, "quantity_on_hand": 1000, "average_unit_cost": "2.5", "last_unit_cost": "2.5", "last_supplier_id": None, "last_cost_at": now, "updated_at": now},
                {"branch_id": BRANCH_ID, "warehouse_id": WAREHOUSE_ID, "item_id": SYRUP_ID, "quantity_on_hand": 1000, "average_unit_cost": "3", "last_unit_cost": "3", "last_supplier_id": None, "last_cost_at": now, "updated_at": now},
            ],
        )
        session.commit()
    beef = client.post(
        "/api/v1/catalog/ingredient-variations",
        headers=_admin_headers(),
        json=_canonical_extra_payload(
            BEEF_ID, portion_quantity="10.125000", sale_price_cents=1250
        ),
    ).json()
    syrup = client.post(
        "/api/v1/catalog/ingredient-variations",
        headers=_admin_headers(),
        json=_canonical_extra_payload(
            SYRUP_ID, portion_quantity="5.500000", station="drinks"
        ),
    ).json()
    assert _open_shift(client, 10000).status_code == 200
    burger_order = client.post("/api/v1/orders", headers=_admin_headers(), json={"lines": [{"product_id": BURGER_ID, "quantity": 2, "ingredient_extras": [{"extra_id": beef["id"], "portions": 1}]}]})
    assert burger_order.status_code == 200
    burger = burger_order.json()
    assert burger["lines"][0]["modifier_total_cents"] == 2500
    beef_component = next(component for component in burger["consumption_snapshots"][0]["components"] if component["item_id"] == BEEF_ID)
    assert float(beef_component["gross_quantity"]) == 260.25
    assert float(beef_component["unit_cost"]) == 2.5
    reservations = client.get(
        f"/api/v1/inventory/kardex?item_id={BEEF_ID}", headers=_admin_headers()
    ).json()
    assert any(
        row["movement_type"] == "SALE_RESERVATION" and float(row["quantity_delta"]) == -260.25
        for row in reservations
    )
    soda_order = client.post("/api/v1/orders", headers=_admin_headers(), json={"lines": [{"product_id": SODA_ID, "quantity": 1, "ingredient_extras": [{"extra_id": syrup["id"], "portions": 1}]}]})
    assert soda_order.status_code == 200
    soda = soda_order.json()
    assert soda["lines"][0]["modifier_total_cents"] == 0
    syrup_component = next(component for component in soda["consumption_snapshots"][0]["components"] if component["item_id"] == SYRUP_ID)
    assert float(syrup_component["gross_quantity"]) == 85.5
    assert float(syrup_component["unit_cost"]) == 3
    task_id = burger["production_tasks"][0]["id"]
    assert client.post(f"/api/v1/kds/tasks/{task_id}/transition", headers=_admin_headers(), json={"status": "IN_PROGRESS"}).status_code == 200
    assert client.post(f"/api/v1/kds/tasks/{task_id}/transition", headers=_admin_headers(), json={"status": "COMPLETED"}).status_code == 200
    consumptions = client.get(
        f"/api/v1/inventory/kardex?item_id={BEEF_ID}", headers=_admin_headers()
    ).json()
    assert any(
        row["movement_type"] == "SALE_CONSUMPTION" and float(row["quantity_delta"]) == -260.25
        for row in consumptions
    )
    assert client.post(
        f"/api/v1/orders/{burger['id']}/payments",
        headers=_admin_headers(),
        json={"amount_cents": burger["total_cents"], "method": "cash", "register_id": "CAJA-01"},
    ).status_code == 200
    assert client.put(
        f"/api/v1/catalog/ingredient-variations/{beef['id']}",
        headers=_admin_headers(),
        json={"status": "archived"},
    ).status_code == 200
    kitchen = next(job for job in client.get("/api/v1/print-jobs", headers=_admin_headers()).json() if job["order_id"] == burger["id"] and job["job_type"] == "kitchen")
    assert any(modifier["kitchen_text"] == beef["add_label"] for modifier in kitchen["payload"]["lines"][0]["selected_modifiers"])
    with factory() as session:
        actions = set(
            session.execute(
                sa.select(models.audit_events.c.action).where(
                    models.audit_events.c.action == "ingredient_variation.archived"
                )
            ).scalars()
        )
    assert "ingredient_variation.archived" in actions


def test_read_only_assignment_preview_does_not_create_command_or_audit() -> None:
    client = _client_with_seeded_database()
    variation = client.post(
        "/api/v1/catalog/ingredient-variations",
        headers=_admin_headers(),
        json=_canonical_extra_payload(BEEF_ID),
    ).json()
    url = f"/api/v1/catalog/ingredient-variations/{variation['id']}/assignments"
    preview = client.post(f"{url}/preview", headers=_admin_headers(), json=_assignment_payload())
    assert preview.status_code == 409
    assert preview.json()["detail"]["code"] == "ingredient_variation_assignments_read_only"
    factory = _test_session_factory(client)
    with factory() as session:
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.ingredient_variation_commands).where(
                models.ingredient_variation_commands.c.variation_id == variation["id"]
            )
        ).scalar_one() == 0
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.audit_events).where(
                models.audit_events.c.action.like("ingredient_variation.assignment.%"),
                models.audit_events.c.entity_id == variation["id"],
            )
        ).scalar_one() == 0


def test_branch_ingredient_overrides_are_scoped_to_supervisor_branch_and_cashier_is_denied(
) -> None:
    client = _client_with_seeded_database()
    branch = client.post(
        "/api/v1/branches",
        headers=_admin_headers(),
        json={"name": "Sucursal Norte", "code": "NORTE", "business_unit_id": BUSINESS_UNIT_ID},
    ).json()
    supervisor_role = client.post(
        "/api/v1/roles",
        headers=_admin_headers(),
        json={"name": "Supervisor de sucursal", "scope": "branch"},
    ).json()
    cashier_role = client.post(
        "/api/v1/roles",
        headers=_admin_headers(),
        json={"name": "Cajero", "scope": "branch"},
    ).json()
    supervisor = client.post(
        "/api/v1/users",
        headers=_admin_headers(),
        json={
            "email": "supervisor.norte@kiwi.test",
            "display_name": "Supervisor Norte",
            "employee_code": "SUP002",
            "password": "Temporal123+",
            "role_id": supervisor_role["id"],
            "branch_id": branch["id"],
        },
    ).json()
    cashier = client.post(
        "/api/v1/users",
        headers=_admin_headers(),
        json={
            "email": "cajero.norte@kiwi.test",
            "display_name": "Cajero Norte",
            "employee_code": "CAJ003",
            "password": "Temporal123+",
            "role_id": cashier_role["id"],
            "branch_id": branch["id"],
        },
    ).json()
    variation = client.post(
        "/api/v1/catalog/ingredient-variations",
        headers=_admin_headers(),
        json=_canonical_extra_payload(BEEF_ID),
    ).json()
    legacy = _insert_legacy_ingredient_assignment(
        client, variation["id"], prefix="branch-history"
    )
    option_id = legacy["add_option_id"]
    supervisor_headers = {"X-Actor-User-Id": supervisor["id"]}
    own_rows = client.get(
        "/api/v1/branch-administration/catalog/ingredient-variations",
        headers=supervisor_headers,
    )
    assert own_rows.status_code == 200
    assert own_rows.json()[0]["inventory_item_name"] == "Carne molida"
    assert own_rows.json()[0]["unit_code"] == "g"
    configured = client.put(
        f"/api/v1/branch-administration/catalog/ingredient-variations/{option_id}",
        headers=supervisor_headers,
        json={"action": "unavailable"},
    )
    assert configured.status_code == 200
    assert configured.json()["branch_id"] == branch["id"]
    other_branch_rows = client.get(
        "/api/v1/branch-administration/catalog/ingredient-variations",
        headers=_admin_headers(),
        params={"branch_id": "018f6f73-2d0a-74f0-8f1c-000000000003"},
    ).json()
    other_option = next(row for row in other_branch_rows if row["option_id"] == option_id)
    assert other_option["override"] is None
    forbidden_branch = client.get(
        "/api/v1/branch-administration/catalog/ingredient-variations",
        headers=supervisor_headers,
        params={"branch_id": "018f6f73-2d0a-74f0-8f1c-000000000003"},
    )
    assert forbidden_branch.status_code == 403
    cashier_rows = client.get(
        "/api/v1/branch-administration/catalog/ingredient-variations",
        headers={"X-Actor-User-Id": cashier["id"]},
    )
    assert cashier_rows.status_code == 403


def test_corporate_ingredient_variation_detail_update_and_archive_are_organization_scoped() -> None:
    client = _client_with_seeded_database()
    foreign_variation_id = "ingredient-variation-foreign-0001"
    now = datetime.now(timezone.utc)
    factory = _test_session_factory(client)
    with factory() as session:
        session.execute(
            models.ingredient_variations.insert().values(
                id=foreign_variation_id,
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000099",
                inventory_item_id=BEEF_ID,
                add_label="Con ajeno",
                remove_label="Sin ajeno",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
    detail_url = f"/api/v1/catalog/ingredient-variations/{foreign_variation_id}"
    assert client.get(detail_url, headers=_admin_headers()).status_code == 404
    assert client.put(
        detail_url, headers=_admin_headers(), json={"add_label": "Con acceso indebido"}
    ).status_code == 404
    assert client.delete(
        f"{detail_url}/assignments/{BURGER_ID}", headers=_admin_headers()
    ).status_code == 404
