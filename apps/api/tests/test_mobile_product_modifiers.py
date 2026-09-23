from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import get_public_catalog
from test_platform_api import (
    BRANCH_ID,
    _admin_headers,
    _client_with_seeded_database,
    _open_shift,
    _test_session_factory,
)

PRODUCT = "018f6f73-2d0a-74f0-8f1c-000000000111"
OPTIONS = [
    {"name": "Leche de avena", "price_delta_cents": 1000},
    {"name": "Sin azúcar", "price_delta_cents": 0},
]


def read(client: Any) -> dict[str, Any]:
    response = client.get(f"/api/v1/products/{PRODUCT}/simple-modifiers", headers=_admin_headers())
    assert response.status_code == 200, response.text
    return response.json()


def save(client: Any, options: Any, revision: Any, **fields: Any) -> Any:
    return client.put(
        f"/api/v1/catalog/products/{PRODUCT}",
        headers=_admin_headers(),
        json={**fields, "simple_modifiers": {"options": options, "expected_revision": revision}},
    )


def snapshot(client: Any) -> dict[str, Any]:
    with _test_session_factory(client)() as session:
        return {
            table.name: [dict(row) for row in session.execute(sa.select(table)).mappings()]
            for table in (
                models.products,
                models.price_versions,
                models.modifier_groups,
                models.modifier_options,
                models.audit_events,
            )
        }


@pytest.mark.parametrize("quantity", [1, 2])
def test_price_free_option_order_snapshot_and_history(quantity: int) -> None:
    client = _client_with_seeded_database()
    response = save(client, OPTIONS, read(client)["revision"], price_cents=4500)
    assert response.status_code == 200, response.text
    assert read(client)["options"] == OPTIONS
    with _test_session_factory(client)() as session:
        public = get_public_catalog(session, BRANCH_ID)
    public_product = next(p for p in public["items"] if p["id"] == PRODUCT)
    public_options = next(g for g in public_product["modifier_groups"] if g["name"] == "Extras")[
        "options"
    ]
    assert [(o["price_delta_cents"], o["selection_kind"]) for o in public_options] == [
        (1000, "modifier"),
        (0, "modifier"),
    ]
    groups = client.get(
        f"/api/v1/products/{PRODUCT}/modifiers?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).json()
    options = next(g for g in groups if g["name"] == "Extras")["options"]
    assert _open_shift(client, 10000).status_code == 200
    order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "lines": [
                {
                    "product_id": PRODUCT,
                    "quantity": quantity,
                    "modifiers": [{"option_id": o["id"], "price_delta_cents": 1} for o in options],
                }
            ]
        },
    )
    assert order.status_code == 200, order.text
    data = order.json()
    assert data["total_cents"] == 5500 * quantity
    assert data["lines"][0]["modifier_total_cents"] == 1000 * quantity
    assert all(m["kind"] == "modifier" for m in data["consumption_snapshots"][0]["modifiers"])
    with _test_session_factory(client)() as session:
        before = list(
            session.execute(sa.select(models.order_line_consumption_snapshots)).mappings()
        )
    assert save(client, [], read(client)["revision"]).status_code == 200
    with _test_session_factory(client)() as session:
        assert (
            list(session.execute(sa.select(models.order_line_consumption_snapshots)).mappings())
            == before
        )


@pytest.mark.parametrize(
    "options",
    [
        [{"name": "X", "price_delta_cents": -1}],
        [{"name": "X", "price_delta_cents": True}],
        [{"name": "X", "price_delta_cents": 1.5}],
        [{"name": "X", "price_delta_cents": "10"}],
        [{"name": "X", "price_delta_cents": 2147483648}],
        [{"name": " ", "price_delta_cents": 0}],
        [{"name": "X", "price_delta_cents": 0}, {"name": "x", "price_delta_cents": 2}],
        None,
    ],
)
def test_invalid_values_do_not_partially_update_product(options: Any) -> None:
    client = _client_with_seeded_database()
    revision = read(client)["revision"]
    before = snapshot(client)
    result = save(client, options, revision, name="CHANGED", price_cents=1234)
    assert result.status_code == 409, result.text
    assert result.json()["detail"]["code"] == "invalid_simple_modifiers"
    assert snapshot(client) == before


def test_empty_legacy_group_recovery_identity_and_stale_revision() -> None:
    client = _client_with_seeded_database()
    group = client.post(
        f"/api/v1/products/{PRODUCT}/modifier-groups",
        headers=_admin_headers(),
        json={"name": "Extras", "maximum_selections": 2},
    ).json()
    revision = read(client)["revision"]
    assert save(client, OPTIONS, revision).status_code == 200
    before = snapshot(client)
    assert save(client, [], revision, name="STALE").status_code == 409
    assert snapshot(client) == before
    ids = [o["id"] for o in before["modifier_options"]]
    assert save(client, [], read(client)["revision"]).status_code == 200
    assert save(client, OPTIONS, read(client)["revision"]).status_code == 200
    after = snapshot(client)
    assert [o["id"] for o in after["modifier_options"]] == ids
    assert [g["id"] for g in after["modifier_groups"]] == [group["id"]]


def test_atomic_creation_and_injected_option_failure() -> None:
    client = _client_with_seeded_database()
    payload = {
        "name": "LATTE",
        "sku": "99981",
        "category_name": "BEBIDAS",
        "station": "drinks",
        "price_cents": 4500,
        "simple_modifiers": {"options": OPTIONS, "expected_revision": None},
    }
    factory = _test_session_factory(client)
    engine = factory.kw["bind"]

    def fail_option(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        if statement.startswith("INSERT INTO modifier_options"):
            raise RuntimeError("injected option write failure")

    before = snapshot(client)
    sa.event.listen(engine, "before_cursor_execute", fail_option)
    try:
        with pytest.raises(RuntimeError, match="injected option write failure"):
            client.post("/api/v1/catalog/products", headers=_admin_headers(), json=payload)
    finally:
        sa.event.remove(engine, "before_cursor_execute", fail_option)
    assert snapshot(client) == before
    result = client.post("/api/v1/catalog/products", headers=_admin_headers(), json=payload)
    assert result.status_code == 200, result.text
    repeated = client.post("/api/v1/catalog/products", headers=_admin_headers(), json=payload)
    assert repeated.status_code == 409


def test_advanced_extras_and_other_groups_are_preserved() -> None:
    client = _client_with_seeded_database()
    client.post(
        f"/api/v1/products/{PRODUCT}/modifier-groups",
        headers=_admin_headers(),
        json={
            "name": "Extras",
            "is_required": True,
            "minimum_selections": 1,
            "maximum_selections": 1,
        },
    )
    assert read(client)["editable"] is False
    before = snapshot(client)
    result = save(client, OPTIONS, read(client)["revision"])
    assert result.status_code == 409
    assert snapshot(client) == before


def test_read_requires_permission_and_foreign_product_is_hidden() -> None:
    client = _client_with_seeded_database()
    assert client.get(f"/api/v1/products/{PRODUCT}/simple-modifiers").status_code == 401
    with _test_session_factory(client)() as session:
        session.execute(
            sa.update(models.products)
            .where(models.products.c.id == PRODUCT)
            .values(organization_id="foreign-organization")
        )
        session.commit()
    assert (
        client.get(
            f"/api/v1/products/{PRODUCT}/simple-modifiers", headers=_admin_headers()
        ).status_code
        == 409
    )
    before = snapshot(client)
    assert save(client, OPTIONS, "foreign", name="ATTACK").status_code == 409
    assert snapshot(client) == before


def test_price_only_change_invalidates_revision() -> None:
    client = _client_with_seeded_database()
    revision = read(client)["revision"]
    result = client.put(
        f"/api/v1/catalog/products/{PRODUCT}", headers=_admin_headers(), json={"price_cents": 5000}
    )
    assert result.status_code == 200
    assert read(client)["revision"] != revision
    before = snapshot(client)
    assert save(client, OPTIONS, revision, price_cents=4500).status_code == 409
    assert snapshot(client) == before


@pytest.mark.parametrize("price", [0, -1, True, 12.5, "4500", 2147483648])
def test_invalid_product_price_rolls_back_modifier_changes(price: Any) -> None:
    client = _client_with_seeded_database()
    revision = read(client)["revision"]
    before = snapshot(client)
    response = save(client, OPTIONS, revision, price_cents=price)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "invalid_price"
    assert snapshot(client) == before


def test_fresh_snapshot_contains_current_product_and_unchanged_save_keeps_price_history() -> None:
    client = _client_with_seeded_database()
    assert (
        client.put(
            f"/api/v1/catalog/products/{PRODUCT}",
            headers=_admin_headers(),
            json={"price_cents": 1299, "name": "NUEVO"},
        ).status_code
        == 200
    )
    state = read(client)
    assert state["product"]["price_cents"] == 1299
    assert state["product"]["name"] == "NUEVO"
    before = snapshot(client)["price_versions"]
    assert save(client, OPTIONS, state["revision"]).status_code == 200
    assert snapshot(client)["price_versions"] == before


@pytest.mark.parametrize("name", ["Leche, avena", "Extra\nLeche", "Leche\rAvena"])
def test_legacy_names_not_representable_as_lines_are_read_only(name: str) -> None:
    client = _client_with_seeded_database()
    assert save(client, OPTIONS, read(client)["revision"]).status_code == 200
    with _test_session_factory(client)() as session:
        session.execute(
            models.modifier_options.update()
            .values(name=name, kitchen_text=name)
            .where(models.modifier_options.c.name == OPTIONS[0]["name"])
        )
        session.commit()
    assert read(client)["editable"] is False


def test_branch_override_blocks_simple_editor_without_modification() -> None:
    client = _client_with_seeded_database()
    assert save(client, OPTIONS, read(client)["revision"]).status_code == 200
    option = snapshot(client)["modifier_options"][0]
    assert (
        client.put(
            f"/api/v1/modifier-options/{option['id']}/branches/{BRANCH_ID}",
            headers=_admin_headers(),
            json={"is_enabled": True, "price_delta_cents": 2000},
        ).status_code
        == 200
    )
    assert read(client)["editable"] is False
    before = snapshot(client)
    assert save(client, OPTIONS, read(client)["revision"], name="CHANGED").status_code == 409
    assert snapshot(client) == before


def test_other_group_is_preserved_and_successful_noop_is_audited() -> None:
    client = _client_with_seeded_database()
    group = client.post(
        f"/api/v1/products/{PRODUCT}/modifier-groups",
        headers=_admin_headers(),
        json={"name": "Termino", "maximum_selections": 1},
    ).json()
    assert save(client, OPTIONS, read(client)["revision"]).status_code == 200
    before = snapshot(client)
    assert save(client, OPTIONS, read(client)["revision"]).status_code == 200
    after = snapshot(client)
    assert after["modifier_options"] == before["modifier_options"]
    assert after["modifier_groups"] == before["modifier_groups"]
    assert next(g for g in after["modifier_groups"] if g["id"] == group["id"])["name"] == "Termino"
    assert len(after["audit_events"]) == len(before["audit_events"]) + 1
