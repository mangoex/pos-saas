"""Presentation changes are persisted only for the authenticated restaurant."""

import secrets

import pytest
import sqlalchemy as sa
from restaurant_os import models
from test_saas_onboarding import _client_with_db


@pytest.fixture
def tenants():
    client = _client_with_db()
    accounts = []
    for name in ("Tacos", "Sushi"):
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": name,
                "owner_name": name,
                "email": name + "@example.test",
                "password": secrets.token_urlsafe(24),
                "plan": "trial",
                "defer_catalog": True,
            },
        )
        assert response.status_code == 201, response.text
        data = response.json()
        accounts.append(({"Authorization": "Bearer " + data["token"]}, data))
    return client, accounts


def test_category_image_roundtrip_preserve_clear_and_tenant_boundary(tenants):
    client, accounts = tenants
    headers, _ = accounts[0]
    image = "https://images.example.test/tacos.jpg"
    created = client.post(
        "/api/v1/categories", headers=headers, json={"name": "Tacos", "image_url": image}
    )
    assert created.status_code == 200, created.text
    assert created.json()["image_url"] == image
    category_id = created.json()["id"]
    route = f"/api/v1/categories/{category_id}"
    assert client.put(route, headers=accounts[1][0], json={"image_url": ""}).status_code == 409
    assert client.put(route, headers=headers, json={"display_order": 2}).status_code == 200
    rows = client.get("/api/v1/categories", headers=headers).json()
    assert next(row for row in rows if row["id"] == category_id)["image_url"] == image
    for empty in (None, ""):
        assert client.put(route, headers=headers, json={"image_url": empty}).status_code == 200
        rows = client.get("/api/v1/categories", headers=headers).json()
        assert next(row for row in rows if row["id"] == category_id)["image_url"] is None
        assert client.put(route, headers=headers, json={"image_url": image}).status_code == 200


def test_menu_home_public_projection_and_audit(tenants):
    client, accounts = tenants
    headers, data = accounts[0]
    route = "/api/v1/catalog/menu-home"
    assert client.get(route, headers=headers).json() == {"name": "Todos", "image_url": None}
    home = {"name": "La carta del Güero", "image_url": "https://images.example.test/hero.jpg"}
    saved = client.put(route, headers=headers, json=home)
    assert saved.status_code == 200, saved.text
    assert saved.json() == home
    assert client.get(route, headers=accounts[1][0]).json()["name"] == "Todos"
    product = client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "name": "Taco",
            "sku": "TACO",
            "category_name": "Tacos",
            "station": "bar",
            "price_cents": 3000,
        },
    )
    assert product.status_code == 200, product.text
    category = client.get("/api/v1/categories", headers=headers).json()[0]
    image = "https://images.example.test/category.jpg"
    assert (
        client.put(
            f"/api/v1/categories/{category['id']}", headers=headers, json={"image_url": image}
        ).status_code
        == 200
    )
    with client.app.state.test_session_factory() as session:
        key = session.scalar(
            sa.select(models.public_order_keys.c.public_key).where(
                models.public_order_keys.c.organization_id == data["organization"]["id"]
            )
        )
        audit = (
            session.execute(
                sa.select(models.audit_events).where(
                    models.audit_events.c.action == "menu_home.updated"
                )
            )
            .mappings()
            .one()
        )
        assert audit["organization_id"] == data["organization"]["id"]
        assert audit["actor_user_id"] == data["user"]["id"]
    catalog = client.get(f"/api/v1/public/branches/{key}/catalog")
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()["menu_home"] == home
    assert catalog.json()["categories"][0]["image_url"] == image
    assert client.put(route, headers=headers, json={"name": "Todos", "image_url": ""}).json() == {
        "name": "Todos",
        "image_url": None,
    }


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "//example.com/a.jpg",
        "data:image/png,x",
        "https://user:password@example.com/a",
        "https://",
        12,
        "https://example.com/" + "x" * 512,
        "https://example.com/\nfoo",
    ],
)
def test_invalid_images_never_persist(tenants, url):
    client, accounts = tenants
    headers = accounts[0][0]
    before = client.get("/api/v1/categories", headers=headers).json()
    result = client.post(
        "/api/v1/categories", headers=headers, json={"name": "Invalid", "image_url": url}
    )
    assert result.status_code in (409, 422), result.text
    result = client.put(
        "/api/v1/catalog/menu-home", headers=headers, json={"name": "Invalid", "image_url": url}
    )
    assert result.status_code in (409, 422), result.text
    assert client.get("/api/v1/categories", headers=headers).json() == before
    assert client.get("/api/v1/catalog/menu-home", headers=headers).json()["name"] == "Todos"


def test_presentation_requires_active_catalog_permission(tenants):
    client, accounts = tenants
    headers, data = accounts[0]
    route = "/api/v1/catalog/menu-home"
    assert client.get(route).status_code == 401
    with client.app.state.test_session_factory() as session:
        session.execute(
            models.users.update()
            .where(models.users.c.id == data["user"]["id"])
            .values(status="inactive")
        )
        session.commit()
    assert client.get(route, headers=headers).status_code == 403
    assert client.put(route, headers=headers, json={"name": "Denied"}).status_code == 403


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "test.localhost",
        "127.0.0.1",
        "127.1",
        "0x7f000001",
        "127.0x0.0x0.0x1",
        "127.0.0x0.0x1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "[::1]",
        "[fc00::1]",
        "[fe80::1]",
    ],
)
def test_obvious_local_image_destinations_are_rejected(host):
    from restaurant_os.catalog_presentation import normalize_image_url
    from restaurant_os.operations import BusinessError

    with pytest.raises(BusinessError, match="HTTP o HTTPS"):
        normalize_image_url(f"https://{host}/image.jpg")


def test_category_image_audit_preserves_previous_values(tenants):
    client, accounts = tenants
    headers, data = accounts[0]
    created = client.post(
        "/api/v1/categories",
        headers=headers,
        json={"name": "Photo audit", "image_url": "https://example.test/a.jpg"},
    )
    category_id = created.json()["id"]
    for image in ("https://example.test/b.jpg", None):
        result = client.put(
            f"/api/v1/categories/{category_id}", headers=headers, json={"image_url": image}
        )
        assert result.status_code == 200, result.text
    with client.app.state.test_session_factory() as session:
        events = (
            session.execute(
                sa.select(models.audit_events.c.payload)
                .where(
                    models.audit_events.c.entity_id == category_id,
                    models.audit_events.c.action == "category.updated",
                )
                .order_by(models.audit_events.c.created_at)
            )
            .scalars()
            .all()
        )
    assert [(e["before"]["image_url"], e["after"]["image_url"]) for e in events] == [
        ("https://example.test/a.jpg", "https://example.test/b.jpg"),
        ("https://example.test/b.jpg", None),
    ]


def test_category_and_product_base64_image_url(tenants):
    client, accounts = tenants
    headers, data = accounts[0]
    base64_sample = (
        "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP////////////////////////"
        "//////////////////////////////////////////////////////////////wgALCAABAAEBAREA"
        "/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
    )

    # Category with Base64 image
    created = client.post(
        "/api/v1/categories",
        headers=headers,
        json={"name": "Papas Base64", "image_url": base64_sample},
    )
    assert created.status_code == 200, created.text
    assert created.json()["image_url"] == base64_sample
    cat_id = created.json()["id"]

    # Update category image with another base64
    base64_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    updated = client.put(
        f"/api/v1/categories/{cat_id}",
        headers=headers,
        json={"image_url": base64_png},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["image_url"] == base64_png

    # Test reject invalid base64 / non-image
    invalid_data = "data:text/plain;base64,aGVsbG8="
    bad = client.put(
        f"/api/v1/categories/{cat_id}",
        headers=headers,
        json={"image_url": invalid_data},
    )
    assert bad.status_code == 409
