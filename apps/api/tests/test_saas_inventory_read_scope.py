# SEC001-SYNTHETIC-FIXTURE provenance=recovery-78cd0224d1a7
"""Inventory administration reads remain inside the authenticated restaurant."""

from restaurant_os.main import app
from restaurant_os.saas_onboarding import signup_tenant
from test_saas_cash_scope import _cash_scope_api_client


def test_inventory_units_items_stock_and_warehouses_are_tenant_scoped():
    client, factory = _cash_scope_api_client()
    try:
        with factory() as session:
            tenants = [
                signup_tenant(
                    session,
                    {
                        "business_name": f"Inventory {key}",
                        "owner_name": key,
                        "email": f"inventory-{key}@example.test",
                        "password": "synthetic-inventory-password",
                        "business_type": "blank",
                    },
                )
                for key in ("a", "b")
            ]
        created = []
        for key, tenant in zip(("A", "B"), tenants, strict=True):
            auth = {"Authorization": f"Bearer {tenant['token']}"}
            unit = client.post(
                "/api/v1/inventory/units",
                headers=auth,
                json={
                    "code": "PZA",
                    "name": f"Piece {key}",
                    "dimension": "discrete",
                },
            )
            assert unit.status_code == 200, unit.text
            item = client.post(
                "/api/v1/inventory/items",
                headers=auth,
                json={
                    "name": f"Item {key}",
                    "sku": "12345",
                    "base_unit_id": unit.json()["id"],
                    "item_type": "ingredient",
                },
            )
            assert item.status_code == 200, item.text
            created.append((unit.json(), item.json()))
        for index, tenant in enumerate(tenants):
            auth = {"Authorization": f"Bearer {tenant['token']}"}
            unit_ids = {
                row["id"] for row in client.get("/api/v1/inventory/units", headers=auth).json()
            }
            item_ids = {
                row["id"] for row in client.get("/api/v1/inventory/items", headers=auth).json()
            }
            stock_ids = {
                row["id"] for row in client.get("/api/v1/inventory/stock", headers=auth).json()
            }
            warehouses = client.get("/api/v1/warehouses", headers=auth)
            assert unit_ids == {created[index][0]["id"]}
            assert item_ids == {created[index][1]["id"]}
            assert stock_ids == {created[index][1]["id"]}
            assert warehouses.status_code == 200, warehouses.text
            assert {row["branch_id"] for row in warehouses.json()} == {tenant["branch"]["id"]}
            assert (
                client.get(
                    "/api/v1/inventory/kardex",
                    headers=auth,
                    params={"item_id": created[1 - index][1]["id"]},
                ).json()
                == []
            )
        cross_unit = client.put(
            f"/api/v1/inventory/units/{created[1][0]['id']}",
            headers={"Authorization": f"Bearer {tenants[0]['token']}"},
            json={"name": "foreign edit"},
        )
        cross_item = client.put(
            f"/api/v1/inventory/items/{created[1][1]['id']}",
            headers={"Authorization": f"Bearer {tenants[0]['token']}"},
            json={"name": "foreign edit"},
        )
        foreign_unit_reference = client.post(
            "/api/v1/inventory/items",
            headers={"Authorization": f"Bearer {tenants[0]['token']}"},
            json={
                "name": "Invalid reference",
                "sku": "67890",
                "base_unit_id": created[1][0]["id"],
                "item_type": "ingredient",
            },
        )
        assert cross_unit.status_code == 409
        assert cross_item.status_code == 409
        assert foreign_unit_reference.status_code == 409

        tenant_a_auth = {"Authorization": f"Bearer {tenants[0]['token']}"}
        own_opening = client.post(
            "/api/v1/inventory/opening-balances",
            headers=tenant_a_auth,
            json={
                "item_id": created[0][1]["id"],
                "branch_id": tenants[0]["branch"]["id"],
                "quantity_base_units": 25,
                "reason": "Apertura A",
            },
        )
        foreign_item_opening = client.post(
            "/api/v1/inventory/opening-balances",
            headers=tenant_a_auth,
            json={
                "item_id": created[1][1]["id"],
                "branch_id": tenants[0]["branch"]["id"],
                "quantity_base_units": 25,
            },
        )
        foreign_branch_opening = client.post(
            "/api/v1/inventory/opening-balances",
            headers=tenant_a_auth,
            json={
                "item_id": created[0][1]["id"],
                "branch_id": tenants[1]["branch"]["id"],
                "quantity_base_units": 25,
            },
        )
        assert own_opening.status_code == 200, own_opening.text
        assert own_opening.json()["organization_id"] == tenants[0]["organization"]["id"]
        assert own_opening.json()["branch_id"] == tenants[0]["branch"]["id"]
        assert foreign_item_opening.status_code == 409
        assert foreign_branch_opening.status_code == 403

        tenant_b_kardex = client.get(
            "/api/v1/inventory/kardex",
            headers={"Authorization": f"Bearer {tenants[1]['token']}"},
            params={"item_id": created[0][1]["id"]},
        )
        assert tenant_b_kardex.status_code == 200
        assert tenant_b_kardex.json() == []
    finally:
        app.dependency_overrides.clear()
