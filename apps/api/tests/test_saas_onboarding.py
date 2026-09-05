# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-onboarding-tests-v1
from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

UTC = timezone.utc


def _client_with_db() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    # Seed base permissions so that role assignment works
    with session_factory() as session:
        _seed_base_permissions(session)

    app = create_app()

    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.state.test_session_factory = session_factory
    return TestClient(app)


def _seed_base_permissions(session: Session) -> None:
    now = datetime(2026, 7, 7, 17, 30, tzinfo=UTC)
    standard_permissions = [
        ("admin.manage", "Administración central de la plataforma"),
        ("catalog.manage", "Administración de catálogos y productos"),
        ("catalog.branch.manage", "Gestión operativa de catálogo por sucursal"),
        ("pos.operate", "Acceso y operación de terminal punto de venta"),
        ("orders.read", "Lectura de pedidos"),
        ("orders.create", "Creación de pedidos"),
        ("orders.cancel", "Cancelación de pedidos"),
        ("payments.read", "Lectura de cobros y pagos"),
        ("payments.confirm", "Confirmación de pagos"),
        ("cash.shift.read", "Lectura de turnos de caja"),
        ("cash.shift.open", "Apertura de turno de caja"),
        ("cash.shift.close", "Cierre y corte de turno de caja"),
        ("cash.withdraw", "Retiro de efectivo de caja"),
        ("dashboard.read", "Acceso a indicadores y métricas"),
        ("branch.admin.access", "Acceso al centro administrativo de sucursal"),
        ("branch.staff.read", "Lectura de personal de sucursal"),
    ]
    for code, desc in standard_permissions:
        session.execute(
            models.permissions.insert().values(
                id=f"perm-{code}",
                code=code,
                description=desc,
                created_at=now,
            )
        )
    session.commit()


def test_signup_creates_new_tenant_and_owner() -> None:
    client = _client_with_db()

    payload = {
        "business_name": "Tacos Don Pancho",
        "owner_name": "Francisco Pancho",
        "email": "pancho@tacos.com",
        "password": "Password123!",
        "phone": "+525512345678",
        "business_type": "taqueria",
    }

    response = client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 201, response.text

    data = response.json()
    assert "token" in data
    assert data["user"]["email"] == "pancho@tacos.com"
    assert data["user"]["display_name"] == "Francisco Pancho"
    assert data["user"]["status"] == "active"
    assert data["organization"]["name"] == "Tacos Don Pancho"
    assert data["organization"]["status"] == "active"
    assert data["organization"]["plan"] == "trial"
    assert data["organization"]["subscription_status"] == "active"
    assert data["organization"]["owner_email"] == "pancho@tacos.com"
    assert data["organization"]["owner_name"] == "Francisco Pancho"
    assert "tacos-don-pancho" in data["organization"]["slug"]
    assert data["organization"]["trial_ends_at"] is not None
    assert data["branch"]["name"] == "Sucursal Matriz"
    assert data["branch"]["status"] == "active"
    assert data["branch"]["slug"] == "matriz"

    # Verify ownership check passes
    from restaurant_os.operations import _is_organization_owner
    with client.app.state.test_session_factory() as session:
        is_owner = _is_organization_owner(session, data["organization"]["id"], "pancho@tacos.com")
        assert is_owner is True

    # Verify session profile with the returned token
    token = data["token"]
    session_response = client.get(
        "/api/v1/auth/session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert session_response.status_code == 200, session_response.text
    session_data = session_response.json()
    assert session_data["user"]["id"] == data["user"]["id"]
    assert session_data["active_branch"]["id"] == data["branch"]["id"]
    assert "pos.operate" in session_data["permissions"]
    assert "admin.manage" in session_data["permissions"]
    assert session_data["scope"]["level"] == "organization"


def test_signup_duplicate_email_rejected() -> None:
    client = _client_with_db()

    payload = {
        "business_name": "Tacos Don Pancho",
        "owner_name": "Francisco Pancho",
        "email": "pancho@tacos.com",
        "password": "Password123!",
        "phone": "+525512345678",
    }

    resp1 = client.post("/api/v1/auth/signup", json=payload)
    assert resp1.status_code == 201

    # Second signup with same email should fail
    resp2 = client.post("/api/v1/auth/signup", json=payload)
    assert resp2.status_code == 409
    err = resp2.json()
    code = err.get("code") or (err.get("detail") or {}).get("code")
    assert code == "email_already_registered"


def test_signup_validation_rejects_invalid_inputs() -> None:
    client = _client_with_db()

    # Short password (< 8 chars)
    resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Tacos",
            "owner_name": "Pancho",
            "email": "pancho@tacos.com",
            "password": "short",
        },
    )
    assert resp.status_code == 422

    # Blank business name
    resp2 = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "   ",
            "owner_name": "Pancho",
            "email": "pancho2@tacos.com",
            "password": "Password123!",
        },
    )
    assert resp2.status_code == 422


def test_signup_seeds_starter_catalog() -> None:
    client = _client_with_db()

    payload = {
        "business_name": "Café Central",
        "owner_name": "Lucía Méndez",
        "email": "lucia@cafecentral.com",
        "password": "Password123!",
        "phone": "+525587654321",
        "business_type": "cafeteria",
    }

    response = client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 201

    token = response.json()["token"]
    # Check that starter categories and products are available in the tenant
    cat_resp = client.get(
        "/api/v1/catalog/categories",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cat_resp.status_code == 200
    categories = cat_resp.json()
    assert len(categories) >= 1

    prod_resp = client.get(
        "/api/v1/catalog/products",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert prod_resp.status_code == 200
    products = prod_resp.json()
    assert len(products) >= 2
    # Ensure products have valid positive prices
    assert all(int(p.get("price_cents") or 0) > 0 for p in products)


def test_multi_tenant_isolation_between_two_signups() -> None:
    client = _client_with_db()

    # Tenant A
    resp_a = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Taquería El Pastor",
            "owner_name": "Pastor A",
            "email": "pastor@tenant-a.com",
            "password": "Password123!",
            "business_type": "taqueria",
        },
    )
    assert resp_a.status_code == 201
    token_a = resp_a.json()["token"]
    org_a_id = resp_a.json()["organization"]["id"]

    # Tenant B
    resp_b = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Pizzería Napoli",
            "owner_name": "Napoli B",
            "email": "napoli@tenant-b.com",
            "password": "Password123!",
            "business_type": "pizzeria",
        },
    )
    assert resp_b.status_code == 201
    token_b = resp_b.json()["token"]
    org_b_id = resp_b.json()["organization"]["id"]

    assert org_a_id != org_b_id

    # Verify session A sees Org A branch
    session_a = client.get(
        "/api/v1/auth/session", headers={"Authorization": f"Bearer {token_a}"}
    ).json()
    session_b = client.get(
        "/api/v1/auth/session", headers={"Authorization": f"Bearer {token_b}"}
    ).json()

    assert session_a["active_branch"]["id"] == resp_a.json()["branch"]["id"]
    assert session_b["active_branch"]["id"] == resp_b.json()["branch"]["id"]
    assert session_a["active_branch"]["id"] != session_b["active_branch"]["id"]


def test_public_branches_and_catalog_isolated_by_restaurant_slug() -> None:
    client = _client_with_db()

    # Tenant A: Taquería El Pastor
    resp_a = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Taquería El Pastor",
            "owner_name": "Pastor A",
            "email": "pastor@tenant-a.com",
            "password": "Password123!",
            "business_type": "taqueria",
        },
    )
    assert resp_a.status_code == 201
    slug_a = resp_a.json()["organization"]["slug"]
    branch_a_id = resp_a.json()["branch"]["id"]

    # Tenant B: Pizzería Napoli
    resp_b = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Pizzería Napoli",
            "owner_name": "Napoli B",
            "email": "napoli@tenant-b.com",
            "password": "Password123!",
            "business_type": "pizzeria",
        },
    )
    assert resp_b.status_code == 201
    slug_b = resp_b.json()["organization"]["slug"]
    branch_b_id = resp_b.json()["branch"]["id"]

    # 1. Verify /public/branches?restaurant={slug} returns only that restaurant's branches
    branches_a = client.get(f"/api/v1/public/branches?restaurant={slug_a}").json()
    assert len(branches_a) == 1
    assert branches_a[0]["id"] == branch_a_id

    branches_b = client.get(f"/api/v1/public/branches?restaurant={slug_b}").json()
    assert len(branches_b) == 1
    assert branches_b[0]["id"] == branch_b_id

    # 2. Verify /public/catalog?restaurant={slug} returns only that restaurant's catalog
    catalog_a = client.get(f"/api/v1/public/catalog?restaurant={slug_a}").json()
    assert catalog_a["branch_id"] == branch_a_id
    assert catalog_a["restaurant_slug"] == slug_a
    item_names_a = [item["name"] for item in catalog_a["items"]]

    catalog_b = client.get(f"/api/v1/public/catalog?restaurant={slug_b}").json()
    assert catalog_b["branch_id"] == branch_b_id
    assert catalog_b["restaurant_slug"] == slug_b
    item_names_b = [item["name"] for item in catalog_b["items"]]

    # Ensure no overlap and strict isolation
    assert len(item_names_a) > 0
    assert len(item_names_b) > 0
    for name_a in item_names_a:
        assert name_a not in item_names_b

    # 3. Direct route /public/restaurants/{slug}/catalog
    cat_direct_a = client.get(f"/api/v1/public/restaurants/{slug_a}/catalog").json()
    assert cat_direct_a["branch_id"] == branch_a_id

    # 4. Direct route /public/restaurants/{slug}
    info_a = client.get(f"/api/v1/public/restaurants/{slug_a}").json()
    assert info_a["slug"] == slug_a
    assert info_a["name"] == "Taquería El Pastor"
    assert len(info_a["branches"]) == 1
    assert info_a["branches"][0]["id"] == branch_a_id

    # 5. Non-existent slug returns 400 with restaurant_not_found
    info_none = client.get("/api/v1/public/restaurants/restaurante-inexistente")
    assert info_none.status_code in (400, 404)


def test_public_catalog_requires_context_when_multiple_tenants() -> None:
    client = _client_with_db()

    # Create 2 tenants so environment is multi-tenant
    client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Restaurante Uno",
            "owner_name": "Dueño Uno",
            "email": "uno@test.com",
            "password": "Password123!",
        },
    )
    client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Restaurante Dos",
            "owner_name": "Dueño Dos",
            "email": "dos@test.com",
            "password": "Password123!",
        },
    )

    # Calling /public/catalog without branch_id or restaurant must fail-closed (no leak)
    resp = client.get("/api/v1/public/catalog")
    assert resp.status_code == 400
    err = resp.json()
    code = err.get("code") or (err.get("detail") or {}).get("code")
    assert code == "restaurant_context_required"


def test_tenant_operational_endpoints_isolated_from_legacy_org() -> None:
    client = _client_with_db()

    # 1. Register new tenant
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Café Gourmet",
            "owner_name": "María Gourmet",
            "email": "maria@gourmet.com",
            "password": "Password123!",
            "phone": "+525544332211",
            "business_type": "cafeteria",
        },
    )
    assert signup_resp.status_code == 201
    data = signup_resp.json()
    token = data["token"]
    org_id = data["organization"]["id"]
    branch_id = data["branch"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Update mobile theme for this tenant
    theme_resp = client.put(
        "/api/v1/catalog/mobile-theme",
        json={"mobile_theme": "dark"},
        headers=headers,
    )
    assert theme_resp.status_code == 200
    assert theme_resp.json()["mobile_theme"] == "dark"

    # Verify theme was stored on tenant org, not Kiwi
    with client.app.state.test_session_factory() as session:
        theme_stmt = sa.select(models.organizations.c.mobile_theme).where(
            models.organizations.c.id == org_id
        )
        tenant_theme = session.execute(theme_stmt).scalar_one()
        assert tenant_theme == "dark"

    # 3. Seed template into this tenant
    seed_resp = client.post(
        "/api/v1/catalog/seed-starter-template",
        json={"template_type": "cafeteria", "branch_id": branch_id},
        headers=headers,
    )
    assert seed_resp.status_code == 200
    assert seed_resp.json().get("status") == "ok"

    # Verify products seeded belong to org_id
    with client.app.state.test_session_factory() as session:
        tenant_prods = session.execute(
            sa.select(models.products.c.id).where(models.products.c.organization_id == org_id)
        ).fetchall()
        assert len(tenant_prods) >= 1

    # 4. List invoices for this tenant (must not fail, must be isolated)
    inv_resp = client.get("/api/v1/invoicing/invoices", headers=headers)
    assert inv_resp.status_code == 200
    assert isinstance(inv_resp.json(), list)

    # 5. List cash shifts for this tenant's branch
    shift_resp = client.get(
        f"/api/v1/cash/shifts?branch_id={branch_id}",
        headers=headers,
    )
    assert shift_resp.status_code == 200
    assert "items" in shift_resp.json()
