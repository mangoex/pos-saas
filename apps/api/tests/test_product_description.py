import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import get_public_catalog
from test_category_presentation import tenants as tenants
from test_mobile_product_modifiers import PRODUCT, read, snapshot
from test_platform_api import (
    BRANCH_ID,
    _admin_headers,
    _client_with_seeded_database,
    _test_session_factory,
)


def test_description_roundtrip_preserves_commercial_fields():
    client = _client_with_seeded_database()
    before = snapshot(client)
    text = "Café con leche de avena.\nPreparado a tu gusto."
    response = client.put(
        f"/api/v1/catalog/products/{PRODUCT}", headers=_admin_headers(), json={"description": text}
    )
    assert response.status_code == 200, response.text
    assert read(client)["product"]["description"] == text
    after = snapshot(client)
    assert before["price_versions"] == after["price_versions"]
    assert before["modifier_options"] == after["modifier_options"]
    assert any(e["action"] == "product.updated" for e in after["audit_events"])
    response = client.put(f"/api/v1/catalog/products/{PRODUCT}", headers=_admin_headers(), json={})
    assert response.status_code == 200
    assert read(client)["product"]["description"] == text
    with _test_session_factory(client)() as session:
        catalog = get_public_catalog(session, BRANCH_ID)
    assert next(p for p in catalog["items"] if p["id"] == PRODUCT)["description"] == text
    for value in ["a" * 360, ""]:
        response = client.put(
            f"/api/v1/catalog/products/{PRODUCT}",
            headers=_admin_headers(),
            json={"description": value},
        )
        assert response.status_code == 200, response.text
        assert read(client)["product"]["description"] == value


@pytest.mark.parametrize("value", ["a" * 361, None, 123, {}, []])
def test_invalid_description_does_not_write(value):
    client = _client_with_seeded_database()
    before = snapshot(client)
    response = client.put(
        f"/api/v1/catalog/products/{PRODUCT}", headers=_admin_headers(), json={"description": value}
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "invalid_product_description"
    assert snapshot(client) == before


def test_description_create_public_http_and_tenant_scope(tenants):
    client, accounts = tenants
    headers, data = accounts[0]
    created = client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "name": "Latte",
            "sku": "LATTE",
            "category_name": "Cafe",
            "station": "bar",
            "price_cents": 4500,
            "description": "Latte frio con avena",
        },
    )
    assert created.status_code == 200, created.text
    pid = created.json()["id"]
    assert (
        client.put(
            f"/api/v1/catalog/products/{pid}", headers=accounts[1][0], json={"description": "Ajeno"}
        ).status_code
        == 409
    )
    assert client.put(
        f"/api/v1/catalog/products/{pid}", json={"description": "Anonimo"}
    ).status_code in (401, 403)
    with client.app.state.test_session_factory() as session:
        key = session.scalar(
            sa.select(models.public_order_keys.c.public_key).where(
                models.public_order_keys.c.organization_id == data["organization"]["id"]
            )
        )
    response = client.get(f"/api/v1/public/branches/{key}/catalog")
    assert response.status_code == 200, response.text
    assert (
        next(p for p in response.json()["items"] if p["id"] == pid)["description"]
        == "Latte frio con avena"
    )
