# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-modifier-scope-synthetic-v1
from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import app
from restaurant_os.operations import BusinessError, _apply_order_modifiers
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _client_with_db() -> tuple[TestClient, sessionmaker[Session]]:
    engine = sa.create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app), factory


def _signup(client: TestClient, email: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": f"Restaurante {email}",
            "owner_name": "Dueño",
            "email": email,
            "password": "Password123!",
            "business_type": "general",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _product(client: TestClient, headers: dict[str, str], sku: str) -> str:
    response = client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "name": f"Producto {sku}",
            "sku": sku,
            "category_name": "Comida",
            "station": "kitchen",
            "price_cents": 10000,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_modifier_catalog_is_scoped_to_actor_and_order_branch() -> None:
    client, factory = _client_with_db()
    tenant_a = _signup(client, "owner-a@modifiers.test")
    tenant_b = _signup(client, "owner-b@modifiers.test")
    headers_a = {"Authorization": f"Bearer {tenant_a['token']}"}
    headers_b = {"Authorization": f"Bearer {tenant_b['token']}"}
    branch_a = str(tenant_a["branch"]["id"])
    branch_b = str(tenant_b["branch"]["id"])
    product_a = _product(client, headers_a, "A-MOD")
    product_b = _product(client, headers_b, "B-MOD")

    group_response = client.post(
        f"/api/v1/products/{product_a}/modifier-groups",
        headers=headers_a,
        json={"name": "Extras", "maximum_selections": 2},
    )
    assert group_response.status_code == 200, group_response.text
    group_a = group_response.json()
    option_response = client.post(
        f"/api/v1/modifier-groups/{group_a['id']}/options",
        headers=headers_a,
        json={"name": "Queso extra", "effect_type": "instruction", "price_delta_cents": 1500},
    )
    assert option_response.status_code == 200, option_response.text
    option_a = option_response.json()

    own_pos = client.get(
        f"/api/v1/products/{product_a}/modifiers?branch_id={branch_a}", headers=headers_a
    )
    assert own_pos.status_code == 200
    assert own_pos.json()[0]["options"][0]["price_delta_cents"] == 1500
    assert (
        client.get(f"/api/v1/products/{product_a}/modifier-groups", headers=headers_b).json() == []
    )
    assert (
        client.get(
            f"/api/v1/products/{product_a}/modifiers?branch_id={branch_b}", headers=headers_b
        ).json()
        == []
    )

    forbidden = [
        client.patch(
            f"/api/v1/modifier-groups/{group_a['id']}", headers=headers_b, json={"name": "B"}
        ),
        client.delete(f"/api/v1/modifier-options/{option_a['id']}", headers=headers_b),
        client.post(
            f"/api/v1/modifier-groups/{group_a['id']}/clone",
            headers=headers_b,
            json={"target_product_id": product_b},
        ),
        client.put(
            f"/api/v1/products/{product_a}/modifier-groups/reorder",
            headers=headers_b,
            json={"ordered_ids": [group_a["id"]]},
        ),
    ]
    assert all(response.status_code != 200 for response in forbidden)

    with factory() as session:
        components, snapshots, modifier_total = _apply_order_modifiers(
            session, product_a, branch_a, 1, [], [{"option_id": option_a["id"]}]
        )
        assert components == []
        assert snapshots[0]["option_id"] == option_a["id"]
        assert modifier_total == 1500
        try:
            _apply_order_modifiers(
                session, product_a, branch_b, 1, [], [{"option_id": option_a["id"]}]
            )
        except BusinessError as exc:
            assert exc.code == "modifier_option_unavailable"
        else:
            raise AssertionError("cross-tenant modifier was accepted")
        assert (
            session.execute(
                sa.select(models.modifier_groups.c.name).where(
                    models.modifier_groups.c.id == group_a["id"]
                )
            ).scalar_one()
            == "Extras"
        )
    app.dependency_overrides.clear()


def test_ingredient_extras_and_order_comments_are_tenant_scoped() -> None:
    client, factory = _client_with_db()
    tenant_a = _signup(client, "owner-a@extras.test")
    tenant_b = _signup(client, "owner-b@extras.test")
    headers_a = {"Authorization": f"Bearer {tenant_a['token']}"}
    headers_b = {"Authorization": f"Bearer {tenant_b['token']}"}
    product_a = _product(client, headers_a, "A-EXTRA")
    product_b = _product(client, headers_b, "B-EXTRA")
    extra = client.post(
        "/api/v1/catalog/ingredient-variations",
        headers=headers_a,
        json={
            "name": "Aguacate",
            "portion_quantity": "1",
            "sale_price_cents": 1200,
            "station": "kitchen",
        },
    )
    assert extra.status_code == 200, extra.text
    with factory() as session:
        components, snapshots, modifier_total = _apply_order_modifiers(
            session,
            product_a,
            str(tenant_a["branch"]["id"]),
            1,
            [],
            [{"option_id": extra.json()["id"], "selection_kind": "ingredient_extra"}],
        )
        assert components
        assert snapshots[0]["option_id"] == extra.json()["id"]
        assert modifier_total == 1200
    assert client.get("/api/v1/catalog/ingredient-variations", headers=headers_b).json() == []
    assert (
        client.put(
            f"/api/v1/catalog/ingredient-variations/{extra.json()['id']}",
            headers=headers_b,
            json={"sale_price_cents": 1},
        ).status_code
        != 200
    )
    comments = client.post(
        "/api/v1/catalog/order-comments/bulk",
        headers=headers_a,
        json={"comments": "Sin cebolla", "product_ids": [product_a]},
    )
    assert comments.status_code == 200, comments.text
    assert client.get("/api/v1/catalog/order-comments", headers=headers_b).json() == []
    assert (
        client.post(
            "/api/v1/catalog/order-comments/bulk",
            headers=headers_b,
            json={"comments": "Sin cebolla", "product_ids": [product_a]},
        ).status_code
        != 200
    )
    assert (
        client.post(
            "/api/v1/catalog/order-comments/bulk",
            headers=headers_b,
            json={"comments": "Sin hielo", "product_ids": [product_b]},
        ).status_code
        == 200
    )
    app.dependency_overrides.clear()
