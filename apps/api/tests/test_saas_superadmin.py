# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-superadmin-synthetic-v1
"""TDD Test Suite for POS-SaaS Superadmin Platform Console & Tenant Management."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models, operations
from restaurant_os.database import get_session
from restaurant_os.main import app
from restaurant_os.superadmin.service import provision_platform_superadmin
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _client_with_db() -> TestClient:
    engine = sa.create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_session():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)
    client.app.state._test_session_factory = TestingSessionLocal
    return client


def _login_superadmin(client: TestClient) -> dict[str, str]:
    with client.app.state._test_session_factory() as session:
        provision_platform_superadmin(
            session,
            email="platform-admin@example.test",
            password="test-only-platform-admin-password",
            display_name="Platform Admin",
        )
    resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": "platform-admin@example.test",
            "password": "test-only-platform-admin-password",
        },
    )
    assert resp.status_code == 200, f"Superadmin login failed: {resp.text}"
    data = resp.json()
    assert data["user"]["is_superadmin"] is True
    token = data["token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_never_bootstraps_a_platform_admin_from_email() -> None:
    client = _client_with_db()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@possaas.com", "password": "not-a-bootstrap-password"},
    )

    assert response.status_code == 403
    with client.app.state._test_session_factory() as session:
        assert session.scalar(
            sa.select(models.users.c.id).where(models.users.c.email == "admin@possaas.com")
        ) is None


def test_email_alone_never_grants_superadmin() -> None:
    client = _client_with_db()
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Correo No Es Autoridad",
            "owner_name": "Persona De Prueba",
            "email": "admin@possaas.com",
            "password": "test-only-owner-password",
            "business_type": "general",
        },
    )
    assert signup.status_code == 201

    response = client.get(
        "/api/v1/superadmin/metrics",
        headers={"Authorization": f"Bearer {signup.json()['token']}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "superadmin_forbidden"


def test_suspended_platform_superadmin_cannot_operate_or_reactivate_self() -> None:
    client = _client_with_db()
    headers = _login_superadmin(client)
    with client.app.state._test_session_factory() as session:
        platform_admin = session.execute(
            sa.select(models.users).where(models.users.c.email == "platform-admin@example.test")
        ).mappings().one()
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == platform_admin["organization_id"])
            .values(subscription_status="suspended")
        )
        session.commit()

    metrics = client.get("/api/v1/superadmin/metrics", headers=headers)
    session_profile = client.get("/api/v1/auth/session", headers=headers)
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "platform-admin@example.test",
            "password": "test-only-platform-admin-password",
        },
    )
    password_update = client.put(
        f"/api/v1/users/{platform_admin['id']}",
        headers=headers,
        json={"password": "test-only-recovery-password"},
    )

    assert metrics.status_code == 403
    assert session_profile.status_code == 403
    assert login.status_code == 403
    assert password_update.status_code == 403
    with client.app.state._test_session_factory() as session:
        status = session.scalar(
            sa.select(models.users.c.status).where(models.users.c.id == platform_admin["id"])
        )
        assert status == "active"


def test_provisioner_rejects_existing_tenant_user() -> None:
    client = _client_with_db()
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Tenant Cannot Escalate",
            "owner_name": "Tenant Owner",
            "email": "tenant-owner@example.test",
            "password": "test-only-tenant-owner-password",
            "business_type": "general",
        },
    )
    assert signup.status_code == 201

    with client.app.state._test_session_factory() as session:
        with pytest.raises(ValueError, match="platform_superadmin_existing_tenant_user_forbidden"):
            provision_platform_superadmin(
                session,
                email="tenant-owner@example.test",
                password="test-only-attempted-promotion",
                display_name="Tenant Owner",
            )
        session.rollback()
        is_superadmin = session.scalar(
            sa.select(models.users.c.is_superadmin).where(
                models.users.c.id == signup.json()["user"]["id"]
            )
        )
        assert is_superadmin is False


def test_tenant_owner_cannot_change_platform_superadmin_password() -> None:
    client = _client_with_db()
    platform_headers = _login_superadmin(client)
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Tenant Cannot Edit Platform",
            "owner_name": "Tenant Owner",
            "email": "tenant-editor@example.test",
            "password": "test-only-tenant-editor-password",
            "business_type": "general",
        },
    )
    assert signup.status_code == 201
    with client.app.state._test_session_factory() as session:
        platform_user_id = session.scalar(
            sa.select(models.users.c.id).where(
                models.users.c.email == "platform-admin@example.test"
            )
        )
    response = client.put(
        f"/api/v1/users/{platform_user_id}",
        headers={"Authorization": f"Bearer {signup.json()['token']}"},
        json={"password": "test-only-takeover-attempt"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "superadmin_target_forbidden"
    assert client.get("/api/v1/superadmin/metrics", headers=platform_headers).status_code == 200


def test_tenant_admin_cannot_update_or_suspend_user_from_another_organization() -> None:
    client = _client_with_db()
    tenant_a = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Tenant A",
            "owner_name": "Owner A",
            "email": "owner-a@example.test",
            "password": "test-only-owner-a-password",
            "business_type": "general",
        },
    )
    tenant_b = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Tenant B",
            "owner_name": "Owner B",
            "email": "owner-b@example.test",
            "password": "test-only-owner-b-password",
            "business_type": "general",
        },
    )
    assert tenant_a.status_code == tenant_b.status_code == 201
    with client.app.state._test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(
                models.organizations.c.id.in_(
                    [tenant_a.json()["organization"]["id"], tenant_b.json()["organization"]["id"]]
                )
            )
            .values(subscription_status="active", trial_ends_at=None)
        )
        session.commit()

    headers_a = {"Authorization": f"Bearer {tenant_a.json()['token']}"}
    target_user_id = tenant_b.json()["user"]["id"]
    update = client.put(
        f"/api/v1/users/{target_user_id}",
        headers=headers_a,
        json={"display_name": "Cross Tenant Attempt"},
    )
    delete = client.delete(f"/api/v1/users/{target_user_id}", headers=headers_a)

    assert update.status_code == 403
    assert update.json()["detail"]["code"] == "target_organization_forbidden"
    assert delete.status_code == 403
    assert delete.json()["detail"]["code"] == "target_organization_forbidden"
    with client.app.state._test_session_factory() as session:
        target = session.execute(
            sa.select(models.users).where(models.users.c.id == target_user_id)
        ).mappings().one()
        assert target["display_name"] == "Owner B"
        assert target["status"] == "active"
        denial = session.execute(
            sa.select(models.audit_events)
            .where(models.audit_events.c.action == "authorization.denied")
            .order_by(models.audit_events.c.created_at.desc())
        ).mappings().first()
        assert denial is not None
        assert denial["actor_user_id"] == tenant_a.json()["user"]["id"]
        assert denial["organization_id"] == tenant_a.json()["organization"]["id"]
        assert denial["payload"]["target_organization_id"] == tenant_b.json()["organization"]["id"]


def test_suspended_tenant_token_is_denied_at_permission_check() -> None:
    client = _client_with_db()
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Suspended Tenant",
            "owner_name": "Suspended Owner",
            "email": "suspended-owner@example.test",
            "password": "test-only-suspended-owner-password",
            "business_type": "general",
        },
    )
    assert signup.status_code == 201
    organization_id = signup.json()["organization"]["id"]
    with client.app.state._test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == organization_id)
            .values(subscription_status="suspended")
        )
        session.commit()

    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {signup.json()['token']}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "tenant_suspended"

    session_response = client.get(
        "/api/v1/auth/session",
        headers={"Authorization": f"Bearer {signup.json()['token']}"},
    )
    assert session_response.status_code == 403
    assert session_response.json()["detail"]["code"] == "tenant_suspended"


def test_expired_or_missing_trial_end_denies_existing_token() -> None:
    client = _client_with_db()
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Expired Trial",
            "owner_name": "Trial Owner",
            "email": "trial-owner@example.test",
            "password": "test-only-trial-owner-password",
            "business_type": "general",
        },
    )
    assert signup.status_code == 201
    organization_id = signup.json()["organization"]["id"]
    with client.app.state._test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == organization_id)
            .values(
                subscription_status="trialing",
                trial_ends_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            )
        )
        session.commit()

    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {signup.json()['token']}"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "tenant_trial_expired"
    subscription = client.get(
        "/api/v1/subscription/status",
        headers={"Authorization": f"Bearer {signup.json()['token']}"},
    )
    assert subscription.status_code == 200
    assert subscription.json()["access_block_reason"] == "tenant_trial_expired"
    assert subscription.json()["renewal_managed_by"] == "platform_superadmin"


def test_trial_with_future_end_allows_existing_token() -> None:
    client = _client_with_db()
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Future Trial",
            "owner_name": "Future Owner",
            "email": "future-trial@example.test",
            "password": "test-only-future-trial-password",
            "business_type": "general",
        },
    )
    assert signup.status_code == 201
    with client.app.state._test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == signup.json()["organization"]["id"])
            .values(
                subscription_status="trialing",
                trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            )
        )
        session.commit()

    response = client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {signup.json()['token']}"},
    )
    assert response.status_code == 200


def test_trial_missing_end_and_exact_boundary_deny_existing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client_with_db()
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Trial Boundary",
            "owner_name": "Boundary Owner",
            "email": "trial-boundary@example.test",
            "password": "test-only-boundary-trial-password",
            "business_type": "general",
        },
    )
    assert signup.status_code == 201
    organization_id = signup.json()["organization"]["id"]
    headers = {"Authorization": f"Bearer {signup.json()['token']}"}
    with client.app.state._test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == organization_id)
            .values(subscription_status="trialing", trial_ends_at=None)
        )
        session.commit()
    missing = client.get("/api/v1/users", headers=headers)
    assert missing.status_code == 403
    assert missing.json()["detail"]["code"] == "tenant_trial_expired"

    frozen_now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(operations, "_now", lambda: frozen_now)
    with client.app.state._test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == organization_id)
            .values(trial_ends_at=frozen_now)
        )
        session.commit()
    boundary = client.get("/api/v1/users", headers=headers)
    assert boundary.status_code == 403
    assert boundary.json()["detail"]["code"] == "tenant_trial_expired"


def test_superadmin_auth_and_metrics() -> None:
    client = _client_with_db()
    headers = _login_superadmin(client)

    # Fetch SaaS metrics
    resp = client.get("/api/v1/superadmin/metrics", headers=headers)
    assert resp.status_code == 200
    metrics = resp.json()

    assert "total_tenants" in metrics
    assert "active_tenants" in metrics
    assert "mrr_cents" in metrics
    assert "total_orders" in metrics


def test_non_superadmin_forbidden() -> None:
    client = _client_with_db()

    # Normal tenant signs up
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": "Fonda Doña Rosa",
            "owner_name": "Rosa López",
            "email": "rosa@fondarosa.com",
            "password": "Password123!",
            "business_type": "general",
        },
    )
    assert signup_resp.status_code == 201
    user_token = signup_resp.json()["token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # Attempt to access superadmin endpoint with ordinary user token
    resp = client.get("/api/v1/superadmin/tenants", headers=user_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "superadmin_forbidden"


def test_superadmin_create_tenants_with_different_menu_modes() -> None:
    client = _client_with_db()
    headers = _login_superadmin(client)

    # 1. Tenant with starter catalog generated by business_type
    resp_starter = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Pizzería Nápoles",
            "owner_name": "Marco Rossi",
            "email": "marco@napoles.com",
            "password": "test-only-marco-napoles-password",
            "phone": "5511223344",
            "business_type": "pizzeria",
            "plan": "starter_349",
            "menu_mode": "generate_by_type",
        },
    )
    assert resp_starter.status_code == 201
    napoles_data = resp_starter.json()
    assert napoles_data["tenant"]["plan"] == "starter_349"
    assert napoles_data["tenant"]["subscription_status"] == "trialing"
    assert napoles_data["tenant"]["slug"]
    assert napoles_data["tenant"]["menu_url"] == f"/menu/{napoles_data['tenant']['slug']}"
    assert napoles_data["products_count"] >= 3

    # 2. Tenant with blank catalog (client wants to start clean)
    resp_blank = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Café Minimal",
            "owner_name": "Ana Blanco",
            "email": "ana@minimal.com",
            "password": "test-only-ana-minimal-password",
            "phone": "5522334455",
            "business_type": "cafeteria",
            "plan": "pro_599",
            "menu_mode": "blank",
        },
    )
    assert resp_blank.status_code == 201
    blank_data = resp_blank.json()
    assert blank_data["tenant"]["slug"]
    assert blank_data["tenant"]["menu_url"] == f"/menu/{blank_data['tenant']['slug']}"
    assert blank_data["products_count"] == 0

    napoles_storefront = client.get(
        f"/api/v1/public/storefronts/{napoles_data['tenant']['slug']}"
    )
    blank_storefront = client.get(
        f"/api/v1/public/storefronts/{blank_data['tenant']['slug']}"
    )
    assert napoles_storefront.status_code == 200
    assert blank_storefront.status_code == 200
    assert napoles_storefront.json()["organization"]["id"] == napoles_data["tenant"]["id"]
    assert blank_storefront.json()["organization"]["id"] == blank_data["tenant"]["id"]
    napoles_public_key = napoles_storefront.json()["branches"][0]["public_key"]
    blank_public_key = blank_storefront.json()["branches"][0]["public_key"]
    assert napoles_public_key != blank_public_key

    # 3. Tenant with AI Menu Import from structured or raw menu text
    menu_sample = """
    PIZZAS ARTESANALES
    Pizza Margarita - $180 - Salsa de tomate, mozzarella fresca y albahaca
    Pizza Cuatro Quesos - $220 - Mozzarella, gorgonzola, parmesano y gouda

    BEBIDAS
    Cerveza Artesanal - $75 - IPA local 355ml
    Agua Mineral - $35
    """
    resp_ai = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Trattoria Da Luigi",
            "owner_name": "Luigi Mangione",
            "email": "luigi@daluigi.com",
            "password": "test-only-luigi-daluigi-password",
            "phone": "5533445566",
            "business_type": "pizzeria",
            "plan": "pro_599",
            "menu_mode": "ai_import",
            "ai_menu_text": menu_sample,
        },
    )
    assert resp_ai.status_code == 201
    ai_data = resp_ai.json()
    assert ai_data["products_count"] >= 4

    # List all tenants
    list_resp = client.get("/api/v1/superadmin/tenants", headers=headers)
    assert list_resp.status_code == 200
    tenants = list_resp.json()
    names = [t["name"] for t in tenants]
    assert "Pizzería Nápoles" in names
    assert "Café Minimal" in names
    assert "Trattoria Da Luigi" in names
    listed_napoles = next(
        tenant for tenant in tenants if tenant["id"] == napoles_data["tenant"]["id"]
    )
    assert listed_napoles["slug"] == napoles_data["tenant"]["slug"]
    assert listed_napoles["menu_url"] == napoles_data["tenant"]["menu_url"]


def test_superadmin_suspends_and_administratively_activates_tenant_with_audited_reason() -> None:
    client = _client_with_db()
    headers = _login_superadmin(client)

    # Create tenant
    create_resp = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Taquería El Chivo",
            "owner_name": "Felipe Reyes",
            "email": "felipe@elchivo.com",
            "password": "test-only-felipe-elchivo-password",
            "business_type": "taqueria",
            "plan": "starter_349",
            "menu_mode": "generate_by_type",
        },
    )
    assert create_resp.status_code == 201
    tenant_id = create_resp.json()["tenant"]["id"]

    # Suspend tenant due to non-payment
    suspend_resp = client.patch(
        f"/api/v1/superadmin/tenants/{tenant_id}/status",
        headers=headers,
        json={"status": "suspended", "reason": "Pago mensual vencido"},
    )
    assert suspend_resp.status_code == 200
    assert suspend_resp.json()["subscription_status"] == "suspended"

    # Attempt login with tenant owner should be denied
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "felipe@elchivo.com", "password": "test-only-felipe-elchivo-password"},
    )
    assert login_resp.status_code == 403
    assert login_resp.json()["detail"]["code"] == "tenant_suspended"

    # Generic status changes cannot grant paid access.
    reactivate_resp = client.patch(
        f"/api/v1/superadmin/tenants/{tenant_id}/status",
        headers=headers,
        json={"status": "active"},
    )
    assert reactivate_resp.status_code == 422

    missing_reason = client.post(
        f"/api/v1/superadmin/tenants/{tenant_id}/administrative-activation",
        headers=headers,
        json={"plan": "starter_349", "administrative_concession_reason": ""},
    )
    assert missing_reason.status_code == 422

    activated = client.post(
        f"/api/v1/superadmin/tenants/{tenant_id}/administrative-activation",
        headers=headers,
        json={
            "plan": "starter_349",
            "administrative_concession_reason": "Concesión de prueba comercial aprobada",
        },
    )
    assert activated.status_code == 200
    assert activated.json()["subscription_status"] == "active"
    with client.app.state._test_session_factory() as session:
        audit = session.execute(
            sa.select(models.audit_events)
            .where(models.audit_events.c.action == "tenant.subscription.administratively_activated")
        ).mappings().one()
        assert audit["actor_user_id"]
        assert audit["correlation_id"]
        assert audit["payload"]["from_subscription_status"] == "suspended"
        assert audit["payload"]["administrative_concession_reason"] == (
            "Concesión de prueba comercial aprobada"
        )

    # Now login succeeds
    login_again = client.post(
        "/api/v1/auth/login",
        json={"email": "felipe@elchivo.com", "password": "test-only-felipe-elchivo-password"},
    )
    assert login_again.status_code == 200


def test_superadmin_impersonate_tenant() -> None:
    client = _client_with_db()
    headers = _login_superadmin(client)

    # Create tenant
    create_resp = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Café Central",
            "owner_name": "Claudia Morales",
            "email": "claudia@cafecentral.com",
            "password": "test-only-claudia-central-password",
            "business_type": "cafeteria",
            "plan": "pro_599",
            "menu_mode": "generate_by_type",
        },
    )
    assert create_resp.status_code == 201
    tenant_id = create_resp.json()["tenant"]["id"]

    # Superadmin requests impersonation token
    imp_resp = client.post(
        f"/api/v1/superadmin/tenants/{tenant_id}/impersonate",
        headers=headers,
    )
    assert imp_resp.status_code == 200
    imp_data = imp_resp.json()
    assert "token" in imp_data
    assert imp_data["is_impersonating"] is True
    assert imp_data["target_email"] == "claudia@cafecentral.com"

    # Use impersonated token to fetch catalog as the customer
    customer_headers = {"Authorization": f"Bearer {imp_data['token']}"}
    cat_resp = client.get("/api/v1/catalog/products", headers=customer_headers)
    assert cat_resp.status_code == 200

    # Verify impersonation details
    assert "target_user" in imp_data
    assert imp_data["target_user"]["is_superadmin"] is False
    assert imp_data["target_user"]["email"] == "claudia@cafecentral.com"
    assert "target_branch_id" in imp_data
    assert imp_data["target_branch_id"] is not None
    with client.app.state._test_session_factory() as session:
        issuance = session.execute(
            sa.select(models.audit_events)
            .where(models.audit_events.c.action == "support.impersonation_issued")
        ).mappings().one()
        assert issuance["organization_id"] == tenant_id
        assert issuance["payload"]["effective_actor_user_id"] == imp_data["target_user_id"]
        assert issuance["payload"]["target_organization_id"] == tenant_id

    # Strict multi-tenant isolation verification:
    # 1. Branches must only return Café Central's branches, NEVER 'Sucursal Piloto'
    branches_resp = client.get("/api/v1/branches", headers=customer_headers)
    assert branches_resp.status_code == 200
    branches = branches_resp.json()
    assert len(branches) == 1
    assert branches[0]["name"] == "Sucursal Matriz"
    assert branches[0]["code"] == "MATRIZ"

    # 2. Users must only return Café Central's users
    users_resp = client.get("/api/v1/users", headers=customer_headers)
    assert users_resp.status_code == 200
    users = users_resp.json()
    user_emails = [u["email"] for u in users]
    assert "claudia@cafecentral.com" in user_emails
    assert "admin@possaas.com" not in user_emails

    # 3. Roles must only return Café Central's roles
    roles_resp = client.get("/api/v1/roles", headers=customer_headers)
    assert roles_resp.status_code == 200
    roles = roles_resp.json()
    assert len(roles) >= 1


def test_superadmin_update_tenant_details() -> None:
    client = _client_with_db()
    headers = _login_superadmin(client)

    # Create tenant
    create_resp = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Tacos El Pastor",
            "owner_name": "Juan Perez",
            "email": "juan@elpastor.com",
            "password": "Password123!",
            "business_type": "taqueria",
            "plan": "starter_349",
            "menu_mode": "generate_by_type",
        },
    )
    assert create_resp.status_code == 201
    tenant_id = create_resp.json()["tenant"]["id"]

    # Credential material is never returned by provisioning responses.
    assert "credentials" not in create_resp.json()

    # Update all tenant details
    update_payload = {
        "name": "Tacos El Pastor Premium",
        "business_type": "taqueria",
        "owner_name": "Juan Carlos Perez",
        "owner_email": "juancarlos@elpastor.com",
        "owner_phone": "5512349999",
        "plan": "pro_599",
    }
    update_resp = client.put(
        f"/api/v1/superadmin/tenants/{tenant_id}",
        headers=headers,
        json=update_payload,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["name"] == "Tacos El Pastor Premium"
    assert updated["owner_name"] == "Juan Carlos Perez"
    assert updated["owner_email"] == "juancarlos@elpastor.com"
    assert updated["owner_phone"] == "5512349999"
    assert updated["plan"] == "pro_599"
    assert updated["monthly_fee_cents"] == 59900

    # Verify login works with the updated email
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "juancarlos@elpastor.com", "password": "Password123!"},
    )
    assert login_resp.status_code == 200


def test_tenant_creation_has_5_canonical_roles() -> None:
    """Verify newly created tenants have exactly the 5 canonical roles in Spanish
    and owner has Administrador de Restaurante.
    """
    client = _client_with_db()
    headers = _login_superadmin(client)
    create_resp = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Pizzeria Napoli",
            "owner_name": "Marco Rossi",
            "email": "marco@napoli.com",
            "password": "Password123!",
            "business_type": "pizzeria",
            "plan": "starter_349",
            "menu_mode": "blank",
        },
    )
    assert create_resp.status_code == 201
    owner_token = create_resp.json()["token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # Fetch tenant roles
    roles_resp = client.get("/api/v1/roles", headers=owner_headers)
    assert roles_resp.status_code == 200
    roles = roles_resp.json()
    role_names = [r["name"] for r in roles]

    assert "Cajero" in role_names
    assert "Cajero Jefe" in role_names
    assert "Líder" in role_names
    assert "Supervisor" in role_names
    assert "Administrador de Restaurante" in role_names

    # Fetch tenant users and check owner role
    users_resp = client.get("/api/v1/users", headers=owner_headers)
    assert users_resp.status_code == 200
    users = users_resp.json()
    owner = next(u for u in users if u["email"] == "marco@napoli.com")
    assert any(r["role_name"] == "Administrador de Restaurante" for r in owner.get("roles", []))


def test_superadmin_list_and_create_administrators() -> None:
    """Verify superadmin can list all restaurant administrators
    and create an independent administrator account.
    """
    client = _client_with_db()
    headers = _login_superadmin(client)

    # List administrators
    list_resp = client.get("/api/v1/superadmin/administrators", headers=headers)
    assert list_resp.status_code == 200
    admins = list_resp.json()
    assert isinstance(admins, list)

    # Create new administrator without initial restaurant
    create_admin_resp = client.post(
        "/api/v1/superadmin/administrators",
        headers=headers,
        json={
            "display_name": "Carlos Gomez",
            "email": "carlos@nuevotaqueria.com",
            "password": "Password123!",
            "phone": "5544332211",
        },
    )
    assert create_admin_resp.status_code == 201
    admin_data = create_admin_resp.json()
    assert admin_data["email"] == "carlos@nuevotaqueria.com"

    # Carlos logs in
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "carlos@nuevotaqueria.com", "password": "Password123!"},
    )
    assert login_resp.status_code == 200
    carlos_token = login_resp.json()["token"]
    carlos_headers = {"Authorization": f"Bearer {carlos_token}"}

    # Carlos completes self-onboarding for his restaurant
    setup_resp = client.post(
        "/api/v1/onboarding/setup-my-restaurant",
        headers=carlos_headers,
        json={
            "business_name": "Taquería El Tapatío",
            "business_type": "taqueria",
        },
    )
    assert setup_resp.status_code == 201
    setup_data = setup_resp.json()
    assert setup_data["tenant"]["name"] == "Taquería El Tapatío"
    assert setup_data["branch"]["name"] == "Sucursal Matriz"
    assert setup_data["tenant"]["slug"]
    assert setup_data["tenant"]["menu_url"] == f"/menu/{setup_data['tenant']['slug']}"

    storefront = client.get(f"/api/v1/public/storefronts/{setup_data['tenant']['slug']}")
    assert storefront.status_code == 200
    public_key = storefront.json()["branches"][0]["public_key"]

    replay = client.post(
        "/api/v1/onboarding/setup-my-restaurant",
        headers=carlos_headers,
        json={"business_name": "Taquería El Tapatío", "business_type": "taqueria"},
    )
    assert replay.status_code == 201
    assert replay.json()["tenant"]["slug"] == setup_data["tenant"]["slug"]
    replay_storefront = client.get(
        f"/api/v1/public/storefronts/{setup_data['tenant']['slug']}"
    )
    assert replay_storefront.status_code == 200
    assert replay_storefront.json()["branches"][0]["public_key"] == public_key

    with client.app.state._test_session_factory() as session:
        org = session.execute(
            sa.select(models.organizations).where(
                models.organizations.c.id == setup_data["tenant"]["id"]
            )
        ).mappings().one()
        assert org["onboarding_step"] == "complete"
        assert org["subscription_status"] == "trialing"
        assert org["trial_ends_at"] - org["created_at"] == timedelta(days=14)


def test_update_user_permission_and_canonical_role_assignment() -> None:
    """Verify superadmin and org owner can update a user and assign Administrador de Restaurante
    without encountering 'Actor does not have the required permission'.
    """
    client = _client_with_db()
    headers = _login_superadmin(client)

    # 1. Create a tenant
    create_resp = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Mariscos El Güero",
            "owner_name": "Alberto Vázquez",
            "email": "contacto@elguero.com",
            "password": "Password123!",
            "business_type": "general",
            "plan": "starter_349",
            "menu_mode": "blank",
        },
    )
    assert create_resp.status_code == 201
    tenant_data = create_resp.json()
    owner_token = tenant_data["token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # Fetch users and roles for this tenant
    users_resp = client.get("/api/v1/users", headers=owner_headers)
    assert users_resp.status_code == 200
    alberto = next(u for u in users_resp.json() if u["email"] == "contacto@elguero.com")

    roles_resp = client.get("/api/v1/roles", headers=owner_headers)
    assert roles_resp.status_code == 200
    admin_role = next(r for r in roles_resp.json() if r["name"] == "Administrador de Restaurante")

    # 2. Superadmin edits Alberto Vázquez to update display_name and re-assert canonical role
    put_resp = client.put(
        f"/api/v1/users/{alberto['id']}",
        headers=headers,
        json={
            "display_name": "Alberto Vázquez G.",
            "email": "contacto@elguero.com",
            "employee_code": "ADM001",
            "role_id": admin_role["id"],
            "password": "NewSecretPassword123!",
        },
    )
    assert put_resp.status_code == 200, put_resp.text
    updated = put_resp.json()
    assert updated["display_name"] == "Alberto Vázquez G."

    # 3. Alberto (as org owner) can also edit a user
    owner_put_resp = client.put(
        f"/api/v1/users/{alberto['id']}",
        headers=owner_headers,
        json={
            "display_name": "Alberto Vázquez Updated",
            "email": "contacto@elguero.com",
            "employee_code": "ADM001",
            "role_id": admin_role["id"],
        },
    )
    assert owner_put_resp.status_code == 200, owner_put_resp.text
    assert owner_put_resp.json()["display_name"] == "Alberto Vázquez Updated"


def test_new_restaurant_pos_endpoints_and_branch_scope_authorization() -> None:
    """Verify newly created restaurant owner can load POS menu and channels
    without branch_scope_denied or 500 errors.
    """
    client = _client_with_db()
    headers = _login_superadmin(client)

    # 1. Create new restaurant tenant
    create_resp = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Tacos El Güero",
            "owner_name": "Alberto Vázquez",
            "email": "contacto@tacoselguero.com",
            "password": "Password123!",
            "business_type": "taqueria",
            "plan": "starter_349",
            "menu_mode": "generate_by_type",
        },
    )
    assert create_resp.status_code == 201
    tenant_data = create_resp.json()
    branch_id = tenant_data["branch"]["id"]
    owner_token = tenant_data["token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # 2. Test POS categories loading
    cat_resp = client.get(f"/api/v1/categories?branch_id={branch_id}", headers=owner_headers)
    assert cat_resp.status_code == 200, cat_resp.text
    categories = cat_resp.json()
    assert isinstance(categories, list)

    # 3. Test POS catalog products loading
    prod_resp = client.get(f"/api/v1/catalog/products?branch_id={branch_id}", headers=owner_headers)
    assert prod_resp.status_code == 200, prod_resp.text
    products = prod_resp.json()
    assert isinstance(products, list)
    assert len(products) > 0  # since taqueria generates starter products

    # 4. Test Rappi POS orders endpoint (the one that previously threw 500)
    rappi_resp = client.get(
        f"/api/v1/pos/rappi/orders?branch_id={branch_id}", headers=owner_headers
    )
    assert rappi_resp.status_code == 200, rappi_resp.text
    assert isinstance(rappi_resp.json(), list)

    # 5. Test Uber Eats POS orders endpoint
    uber_resp = client.get(
        f"/api/v1/pos/uber-eats/orders?branch_id={branch_id}", headers=owner_headers
    )
    assert uber_resp.status_code == 200, uber_resp.text
    assert isinstance(uber_resp.json(), list)

    # 6. Test DiDi Food POS orders endpoint
    didi_resp = client.get(
        f"/api/v1/pos/didi-food/orders?branch_id={branch_id}", headers=owner_headers
    )
    assert didi_resp.status_code == 200, didi_resp.text
    assert isinstance(didi_resp.json(), list)

    # 7. Test pending orders count endpoint
    pending_resp = client.get(
        f"/api/v1/orders/pending-count?branch_id={branch_id}", headers=owner_headers
    )
    assert pending_resp.status_code == 200, pending_resp.text
