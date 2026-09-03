# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-onboarding-tests-v1
from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any, cast

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.config import get_settings
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
    session_a = client.get("/api/v1/auth/session", headers={"Authorization": f"Bearer {token_a}"}).json()
    session_b = client.get("/api/v1/auth/session", headers={"Authorization": f"Bearer {token_b}"}).json()

    assert session_a["active_branch"]["id"] == resp_a.json()["branch"]["id"]
    assert session_b["active_branch"]["id"] == resp_b.json()["branch"]["id"]
    assert session_a["active_branch"]["id"] != session_b["active_branch"]["id"]
