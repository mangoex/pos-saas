# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-onboarding-synthetic-v1
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
    assert data["branch"]["name"] == "Sucursal Matriz"
    assert data["branch"]["status"] == "active"

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


def test_trial_is_fourteen_days_and_setup_rejects_skipping_steps() -> None:
    from datetime import timedelta

    client = _client_with_db()
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Test Trial",
            "owner_name": "Test Owner",
            "email": "trial@example.test",
            "password": "FixturePassword123!",
            "business_type": "blank",
            "plan": "pro_599",
        },
    )
    assert response.status_code == 201
    data = response.json()
    headers = {"Authorization": f"Bearer {data['token']}"}
    with client.app.state.test_session_factory() as session:
        org = (
            session.execute(
                sa.select(models.organizations).where(
                    models.organizations.c.id == data["organization"]["id"]
                )
            )
            .mappings()
            .one()
        )
        assert org["plan"] == "pro_599"
        assert org["subscription_status"] == "trialing"
        assert org["trial_ends_at"] - org["created_at"] == timedelta(days=14)
    setup = client.get("/api/v1/saas/onboarding", headers=headers)
    assert setup.status_code == 200
    assert setup.json()["step"] == "business"
    skipped = client.put(
        "/api/v1/saas/onboarding",
        headers=headers,
        json={"step": "register", "register_name": "CAJA-01"},
    )
    assert skipped.status_code == 409
    for payload, next_step in [
        (
            {
                "step": "business",
                "business_name": "Test Trial",
                "branch_name": "Matriz",
                "phone": "5551234567",
                "timezone": "America/Chihuahua",
            },
            "menu",
        ),
        ({"step": "menu", "business_type": "taqueria"}, "register"),
        ({"step": "register", "register_name": "CAJA-01"}, "complete"),
    ]:
        result = client.put("/api/v1/saas/onboarding", headers=headers, json=payload)
        assert result.status_code == 200, result.text
        assert result.json()["step"] == next_step
        replay = client.put("/api/v1/saas/onboarding", headers=headers, json=payload)
        assert replay.status_code == 200
        assert replay.json()["step"] == next_step


def test_signup_rejects_unrecognized_plan() -> None:
    client = _client_with_db()
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Test",
            "owner_name": "Owner",
            "email": "invalid@example.test",
            "password": "FixturePassword123!",
            "plan": "free_forever",
        },
    )
    assert response.status_code == 422


def test_new_branch_provisions_public_key_in_its_restaurant() -> None:
    client = _client_with_db()
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Branches",
            "owner_name": "Owner",
            "email": "branches@example.test",
            "password": "FixturePassword123!",
            "business_type": "blank",
        },
    ).json()
    headers = {"Authorization": f"Bearer {signup['token']}"}
    created = client.post(
        "/api/v1/branches", headers=headers, json={"name": "Centro", "code": "CENTRO"}
    )
    assert created.status_code == 200, created.text
    storefront = client.get(f"/api/v1/public/storefronts/{signup['organization']['slug']}")
    assert storefront.status_code == 200, storefront.text
    assert len(storefront.json()["branches"]) == 2
    assert all(branch["public_key"] for branch in storefront.json()["branches"])


def test_catalog_import_and_template_remain_in_actor_restaurant() -> None:
    client = _client_with_db()
    tenants = []
    for name in ("one", "two"):
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": name,
                "owner_name": name,
                "email": f"{name}@example.test",
                "password": "FixturePassword123!",
                "business_type": "blank",
            },
        )
        assert response.status_code == 201
        tenants.append(response.json())
    first, other = tenants
    headers = {"Authorization": f"Bearer {first['token']}"}
    foreign = client.post(
        "/api/v1/catalog/import-custom-catalog",
        headers=headers,
        json={
            "branch_id": other["branch"]["id"],
            "categories": [{"category": "Test", "products": [{"name": "X", "price_cents": 100}]}],
        },
    )
    assert foreign.status_code == 403
    imported = client.post(
        "/api/v1/catalog/import-custom-catalog",
        headers=headers,
        json={
            "branch_id": first["branch"]["id"],
            "categories": [{"category": "Test", "products": [{"name": "X", "price_cents": 100}]}],
        },
    )
    assert imported.status_code == 200, imported.text
    seeded = client.post(
        "/api/v1/catalog/seed-starter-template",
        headers=headers,
        json={"branch_id": first["branch"]["id"], "template_type": "taqueria"},
    )
    assert seeded.status_code == 200, seeded.text
    with client.app.state.test_session_factory() as session:
        product_orgs = set(session.execute(sa.select(models.products.c.organization_id)).scalars())
        assert product_orgs == {first["organization"]["id"]}


def test_mobile_theme_belongs_to_authenticated_restaurant() -> None:
    client = _client_with_db()
    tenants = []
    for name in ("themeone", "themetwo"):
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": name,
                "owner_name": name,
                "email": f"{name}@example.test",
                "password": "FixturePassword123!",
                "business_type": "blank",
            },
        )
        assert response.status_code == 201
        tenants.append(response.json())
    headers = {"Authorization": f"Bearer {tenants[0]['token']}"}
    response = client.put("/api/v1/catalog/mobile-theme", headers=headers, json={"theme": "dark"})
    assert response.status_code == 200
    with client.app.state.test_session_factory() as session:
        themes = dict(
            session.execute(
                sa.select(models.organizations.c.id, models.organizations.c.mobile_theme)
            ).all()
        )
        assert themes[tenants[0]["organization"]["id"]] == "dark"
        assert themes[tenants[1]["organization"]["id"]] != "dark"
    assert (
        client.get("/api/v1/catalog/mobile-theme", headers=headers).json()["mobile_theme"] == "dark"
    )
    assert client.get("/api/v1/catalog/mobile-theme").status_code == 401
    assert client.get("/api/v1/public/mobile-theme").status_code == 422
    public_theme = client.get(
        "/api/v1/public/mobile-theme",
        params={"identifier": tenants[0]["organization"]["slug"]},
    )
    assert public_theme.status_code == 200
    assert public_theme.json()["mobile_theme"] == "dark"


def test_import_keeps_exact_decimal_price_in_cents() -> None:
    client = _client_with_db()
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Exact Price QA",
            "owner_name": "Owner",
            "email": "price@example.test",
            "password": "synthetic-price-password",
            "business_type": "blank",
        },
    ).json()
    response = client.post(
        "/api/v1/catalog/import-custom-catalog",
        headers={"Authorization": f"Bearer {signup['token']}"},
        json={
            "branch_id": signup["branch"]["id"],
            "categories": [{"category": "QA", "products": [{"name": "Price QA", "price": "9.95"}]}],
        },
    )
    assert response.status_code == 200, response.text
    with client.app.state.test_session_factory() as session:
        assert session.scalar(sa.select(models.price_versions.c.price_cents)) == 995


def test_guided_signup_defers_template_until_explicit_menu_selection():
    client = _client_with_db()
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Guided QA",
            "owner_name": "Owner",
            "email": "guided@example.test",
            "password": "synthetic-password",
            "business_type": "restaurant",
            "defer_catalog_setup": True,
        },
    )
    assert signup.status_code == 201, signup.text
    data = signup.json()
    headers = {"Authorization": f"Bearer {data['token']}"}
    business = client.put(
        "/api/v1/saas/onboarding",
        headers=headers,
        json={
            "step": "business",
            "business_name": "Guided QA",
            "branch_name": "Main",
            "timezone": "America/Mexico_City",
        },
    )
    assert business.status_code == 200, business.text
    empty = client.put(
        "/api/v1/saas/onboarding", headers=headers, json={"step": "menu", "business_type": "blank"}
    )
    assert empty.status_code == 200, empty.text
    with client.app.state.test_session_factory() as session:
        assert (
            session.scalar(
                sa.select(sa.func.count())
                .select_from(models.products)
                .where(models.products.c.organization_id == data["organization"]["id"])
            )
            == 0
        )


def test_signup_normalizes_public_plan_names_to_canonical_plans():
    for public_plan, canonical in (("starter", "starter_349"), ("professional", "pro_599")):
        client = _client_with_db()
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "business_name": "Plan Contract",
                "owner_name": "Owner",
                "email": f"{public_plan}@example.test",
                "password": "FixturePassword123!",
                "plan": public_plan,
                "business_type": "blank",
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["organization"]["plan"] == canonical
        assert response.json()["organization"]["subscription_status"] == "trialing"
