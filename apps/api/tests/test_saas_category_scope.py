# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-recovery-test-saas-category-scope-synthetic-v1
"""Categories share the same tenant and live-session boundary as products."""

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from restaurant_os import models
from test_saas_onboarding import _client_with_db


def test_category_update_and_catalog_reads_enforce_tenant_and_expiration():
    client = _client_with_db()
    tenants = []
    for suffix in ("a", "b"):
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": suffix,
                "owner_name": suffix,
                "email": f"category-{suffix}@example.test",
                "password": "synthetic-category-password",
                "business_type": "blank",
            },
        )
        assert response.status_code == 201, response.text
        tenants.append(response.json())
    first, other = tenants
    headers_a = {"Authorization": f"Bearer {first['token']}"}
    headers_b = {"Authorization": f"Bearer {other['token']}"}
    created = client.post("/api/v1/categories", headers=headers_a, json={"name": "Category A"})
    assert created.status_code == 200, created.text
    category_id = created.json()["id"]
    denied = client.put(
        f"/api/v1/categories/{category_id}",
        headers=headers_b,
        json={"name": "Foreign rename", "status": "archived"},
    )
    assert denied.status_code in (403, 404, 409), denied.text
    with client.app.state.test_session_factory() as session:
        category = (
            session.execute(
                sa.select(models.product_categories).where(
                    models.product_categories.c.id == category_id
                )
            )
            .mappings()
            .one()
        )
        assert category["name"] == "Category A"
        assert category["status"] == "active"
    allowed = client.put(
        f"/api/v1/categories/{category_id}", headers=headers_a, json={"name": "Own rename"}
    )
    assert allowed.status_code == 200, allowed.text
    with client.app.state.test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == first["organization"]["id"])
            .values(trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1))
        )
        session.commit()
    for path in ("/api/v1/catalog/products", "/api/v1/catalog/categories"):
        expired = client.get(path, headers=headers_a)
        assert expired.status_code == 403, expired.text
        assert "tenant_trial_expired" in expired.text
        assert client.get(path, headers=headers_b).status_code == 200


def test_category_selection_groups_values_and_assignments_reject_foreign_tenant() -> None:
    client = _client_with_db()
    tenants = []
    for suffix in ("a", "b"):
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": f"selection-{suffix}",
                "owner_name": suffix,
                "email": f"selection-{suffix}@example.test",
                "password": "synthetic-selection-password",
                "business_type": "blank",
            },
        )
        assert response.status_code == 201, response.text
        tenants.append(response.json())
    first, other = tenants
    headers_a = {"Authorization": f"Bearer {first['token']}"}
    headers_b = {"Authorization": f"Bearer {other['token']}"}

    category = client.post("/api/v1/categories", headers=headers_a, json={"name": "Bebidas"})
    assert category.status_code == 200, category.text
    category_id = category.json()["id"]
    product_a = client.post(
        "/api/v1/catalog/products",
        headers=headers_a,
        json={
            "name": "Agua A",
            "sku": "WATER-A",
            "category_name": "Bebidas",
            "station": "bar",
            "price_cents": 1000,
        },
    )
    product_b = client.post(
        "/api/v1/catalog/products",
        headers=headers_b,
        json={
            "name": "Agua B",
            "sku": "WATER-B",
            "category_name": "Bebidas",
            "station": "bar",
            "price_cents": 1000,
        },
    )
    assert product_a.status_code == 200, product_a.text
    assert product_b.status_code == 200, product_b.text
    cross_product_update = client.put(
        f"/api/v1/catalog/products/{product_a.json()['id']}",
        headers=headers_b,
        json={"name": "Mutación cruzada"},
    )
    cross_product_delete = client.delete(
        f"/api/v1/catalog/products/{product_a.json()['id']}", headers=headers_b
    )
    assert cross_product_update.status_code == 409
    assert cross_product_update.json()["detail"]["code"] == "product_not_found"
    assert cross_product_delete.status_code == 409
    assert cross_product_delete.json()["detail"]["code"] == "product_not_found"

    group = client.post(
        f"/api/v1/categories/{category_id}/selection-group",
        headers=headers_a,
        json={"code": "size", "name": "Tamaño", "status": "inactive"},
    )
    assert group.status_code == 200, group.text
    group_id = group.json()["id"]
    value = client.post(
        f"/api/v1/catalog/category-option-groups/{group_id}/values",
        headers=headers_a,
        json={"code": "small", "name": "Chico", "status": "active"},
    )
    assert value.status_code == 200, value.text
    assigned = client.put(
        f"/api/v1/catalog/category-option-groups/{group_id}/assignments/{product_a.json()['id']}",
        headers=headers_a,
        json={"option_value_id": value.json()["id"]},
    )
    assert assigned.status_code == 200, assigned.text

    foreign_responses = [
        client.get(f"/api/v1/categories/{category_id}/selection-group", headers=headers_b),
        client.get(
            f"/api/v1/catalog/category-option-groups/{group_id}/coverage", headers=headers_b
        ),
        client.post(
            f"/api/v1/catalog/category-option-groups/{group_id}/values",
            headers=headers_b,
            json={"code": "large", "name": "Grande", "status": "active"},
        ),
        client.put(
            f"/api/v1/catalog/category-option-groups/{group_id}/assignments/{product_b.json()['id']}",
            headers=headers_b,
            json={"option_value_id": value.json()["id"]},
        ),
    ]
    assert all(response.status_code in {403, 404} for response in foreign_responses)

    coverage = client.get(f"/api/v1/categories/{category_id}/selection-group", headers=headers_a)
    assert coverage.status_code == 200, coverage.text
    assert coverage.json()["products"] == [
        {
            "id": product_a.json()["id"],
            "name": "Agua A",
            "sku": "WATER-A",
            "assignment": {
                "value_id": value.json()["id"],
                "value_code": "small",
                "value_name": "Chico",
                "value_status": "active",
            },
            "incomplete": False,
        }
    ]
