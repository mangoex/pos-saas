# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-trial-and-delete-synthetic-v1
"""TDD suite for SaaS Superadmin trial days calculation and suspended tenant deletion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
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


def test_list_tenants_includes_trial_days_remaining_and_extra_days() -> None:
    client = _client_with_db()
    headers = _login_superadmin(client)
    now = datetime.now(UTC)

    # 1. Tenant con prueba activa: 10 días restantes
    resp_active_trial = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Tacos Activos",
            "owner_name": "Dueño Activo",
            "email": "activo@tacos.test",
            "password": "Password123!",
            "business_type": "taqueria",
            "plan": "trial",
            "menu_mode": "blank",
        },
    )
    assert resp_active_trial.status_code == 201
    active_id = resp_active_trial.json()["tenant"]["id"]

    # Ajustar fecha para que queden exactamente 10 días
    with client.app.state._test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == active_id)
            .values(trial_ends_at=now + timedelta(days=10))
        )
        session.commit()

    # 2. Tenant con prueba vencida: 3 días adicionales transcurridos
    resp_expired_trial = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Pizza Vencida",
            "owner_name": "Dueño Vencido",
            "email": "vencido@pizza.test",
            "password": "Password123!",
            "business_type": "pizzeria",
            "plan": "trial",
            "menu_mode": "blank",
        },
    )
    assert resp_expired_trial.status_code == 201
    expired_id = resp_expired_trial.json()["tenant"]["id"]

    with client.app.state._test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == expired_id)
            .values(trial_ends_at=now - timedelta(days=3))
        )
        session.commit()

    # Consultar lista de tenants en superadmin
    list_resp = client.get("/api/v1/superadmin/tenants", headers=headers)
    assert list_resp.status_code == 200
    tenants = {t["id"]: t for t in list_resp.json()}

    # Validar tenant activo en prueba
    t_active = tenants[active_id]
    assert t_active["is_trial"] is True
    assert t_active["trial_days_remaining"] == 10
    assert t_active["trial_extra_days"] == 0

    # Validar tenant vencido con días adicionales (flecha arriba)
    t_expired = tenants[expired_id]
    assert t_expired["is_trial"] is True
    assert t_expired["trial_days_remaining"] == 0
    assert t_expired["trial_extra_days"] >= 3


def test_delete_tenant_requires_suspended_status() -> None:
    client = _client_with_db()
    headers = _login_superadmin(client)

    # Crear tenant activo
    create_resp = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Restaurante No Borrable",
            "owner_name": "Juan Pérez",
            "email": "juan@noborrable.test",
            "password": "Password123!",
            "business_type": "general",
            "plan": "trial",
            "menu_mode": "blank",
        },
    )
    assert create_resp.status_code == 201
    tenant_id = create_resp.json()["tenant"]["id"]

    # Intentar eliminar directamente estando activo debe fallar (422)
    delete_resp = client.delete(f"/api/v1/superadmin/tenants/{tenant_id}", headers=headers)
    assert delete_resp.status_code == 422
    assert delete_resp.json()["detail"]["code"] == "tenant_must_be_suspended_to_delete"

    # Suspender el tenant
    suspend_resp = client.patch(
        f"/api/v1/superadmin/tenants/{tenant_id}/status",
        headers=headers,
        json={"status": "suspended", "reason": "Falta de pago o prueba concluida"},
    )
    assert suspend_resp.status_code == 200

    # Ahora eliminar el tenant suspendido debe tener éxito (200)
    delete_ok_resp = client.delete(f"/api/v1/superadmin/tenants/{tenant_id}", headers=headers)
    assert delete_ok_resp.status_code == 200
    assert delete_ok_resp.json()["status"] == "deleted"

    # El tenant ya no debe aparecer en la lista de tenants
    list_resp = client.get("/api/v1/superadmin/tenants", headers=headers)
    assert list_resp.status_code == 200
    ids_in_list = [t["id"] for t in list_resp.json()]
    assert tenant_id not in ids_in_list

    # Validar auditoría de la eliminación
    with client.app.state._test_session_factory() as session:
        audit_row = session.execute(
            sa.select(models.audit_events).where(
                models.audit_events.c.action == "tenant.deleted",
                models.audit_events.c.organization_id == tenant_id,
            )
        ).mappings().first()
        assert audit_row is not None


def test_organization_profile_includes_trial_extra_days() -> None:
    client = _client_with_db()
    headers = _login_superadmin(client)
    now = datetime.now(UTC)

    # Crear tenant vencido
    create_resp = client.post(
        "/api/v1/superadmin/tenants",
        headers=headers,
        json={
            "business_name": "Café Gracia",
            "owner_name": "Dueño Gracia",
            "email": "gracia@cafe.test",
            "password": "Password123!",
            "business_type": "cafeteria",
            "plan": "trial",
            "menu_mode": "blank",
        },
    )
    assert create_resp.status_code == 201
    tenant_id = create_resp.json()["tenant"]["id"]

    # Ajustar a 2 días pasados
    with client.app.state._test_session_factory() as session:
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == tenant_id)
            .values(trial_ends_at=now - timedelta(days=2))
        )
        session.commit()

    # Login como el dueño del tenant
    owner_login = client.post(
        "/api/v1/auth/login",
        json={"email": "gracia@cafe.test", "password": "Password123!"},
    )
    assert owner_login.status_code == 200
    owner_token = owner_login.json()["token"]

    # Consultar /organization/profile
    profile_resp = client.get(
        "/api/v1/organization/profile",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert profile_resp.status_code == 200
    data = profile_resp.json()
    assert data["trial_days_remaining"] == 0
    assert data["trial_extra_days"] >= 2
