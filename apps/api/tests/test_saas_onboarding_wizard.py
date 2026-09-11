# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-wizard-tests-v1
from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

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
    now = datetime(2026, 7, 7, 17, 30, tzinfo=timezone.utc)
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


def test_get_and_update_organization_profile() -> None:
    client = _client_with_db()

    signup_res = client.post(
        "/api/v1/auth/signup",
        json={
            "restaurant_name": "Café Bonito",
            "owner_name": "Mariana Lopez",
            "owner_email": "mariana@cafebonito.com",
            "password": "Password123!",
            "owner_phone": "+525512349999",
            "business_type": "cafe",
            "branch_name": "Sucursal Centro",
        },
    )
    assert signup_res.status_code == 201
    auth_data = signup_res.json()
    token = auth_data["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. GET /organization/profile
    profile_res = client.get("/api/v1/organization/profile", headers=headers)
    assert profile_res.status_code == 200
    profile = profile_res.json()

    assert profile["name"] == "Café Bonito"
    assert "caf" in profile["slug"]
    assert profile["business_type"] == "cafe"
    assert profile["owner_email"] == "mariana@cafebonito.com"
    assert profile["owner_phone"] == "+525512349999"
    assert profile["plan"] == "trial"
    assert profile["subscription_status"] == "trialing"
    assert profile["trial_days_remaining"] == 14
    assert profile["products_count"] >= 0
    assert len(profile["branches"]) >= 1
    assert profile["branches"][0]["name"] == "Sucursal Centro"
    assert profile["branches"][0]["public_key"] is not None

    # 2. PATCH /organization/profile
    patch_res = client.patch(
        "/api/v1/organization/profile",
        headers=headers,
        json={
            "name": "Café Bonito Gourmet",
            "owner_phone": "+525599887766",
            "business_type": "bakery",
            "mobile_theme": "dark",
        },
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["name"] == "Café Bonito Gourmet"
    assert updated["owner_phone"] == "+525599887766"
    assert updated["business_type"] == "bakery"
    assert updated["mobile_theme"] == "dark"

    # Verify get reflects changes
    refetch_res = client.get("/api/v1/organization/profile", headers=headers)
    assert refetch_res.status_code == 200
    assert refetch_res.json()["name"] == "Café Bonito Gourmet"
    assert refetch_res.json()["mobile_theme"] == "dark"


def test_get_organization_qr_info() -> None:
    client = _client_with_db()

    signup_res = client.post(
        "/api/v1/auth/signup",
        json={
            "restaurant_name": "Tacos El Guero",
            "owner_name": "Guillermo Guero",
            "owner_email": "guero@tacos.com",
            "password": "Password123!",
            "owner_phone": "+525544332211",
            "business_type": "taqueria",
        },
    )
    assert signup_res.status_code == 201
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    qr_res = client.get("/api/v1/organization/qr-info", headers=headers)
    assert qr_res.status_code == 200
    qr_data = qr_res.json()

    assert qr_data["restaurant_name"] == "Tacos El Guero"
    assert "tacos-el-guero" in qr_data["restaurant_slug"]
    assert qr_data["whatsapp_phone"] == "+525544332211"
    assert "tacos-el-guero" in qr_data["menu_url"]
    assert qr_data["public_key"] is not None


def test_multi_tenant_profile_isolation() -> None:
    client = _client_with_db()

    # Create Tenant 1
    t1_res = client.post(
        "/api/v1/auth/signup",
        json={
            "restaurant_name": "Pizzeria Roma",
            "owner_name": "Mario Rossi",
            "owner_email": "mario@roma.com",
            "password": "Password123!",
            "owner_phone": "+525511111111",
            "business_type": "pizzeria",
        },
    )
    assert t1_res.status_code == 201
    t1_token = t1_res.json()["token"]

    # Create Tenant 2
    t2_res = client.post(
        "/api/v1/auth/signup",
        json={
            "restaurant_name": "Sushi Tokyo",
            "owner_name": "Kenji Sato",
            "owner_email": "kenji@tokyo.com",
            "password": "Password123!",
            "owner_phone": "+525522222222",
            "business_type": "restaurant",
        },
    )
    assert t2_res.status_code == 201
    t2_token = t2_res.json()["token"]

    # Tenant 1 accesses profile
    t1_headers = {"Authorization": f"Bearer {t1_token}"}
    t1_profile = client.get("/api/v1/organization/profile", headers=t1_headers).json()
    assert t1_profile["name"] == "Pizzeria Roma"
    assert "pizzeria-roma" in t1_profile["slug"]

    # Tenant 2 accesses profile
    t2_headers = {"Authorization": f"Bearer {t2_token}"}
    t2_profile = client.get("/api/v1/organization/profile", headers=t2_headers).json()
    assert t2_profile["name"] == "Sushi Tokyo"
    assert "sushi-tokyo" in t2_profile["slug"]

    # Tenant 1 updates their profile
    client.patch(
        "/api/v1/organization/profile",
        headers=t1_headers,
        json={"name": "Pizzeria Roma Centro"},
    )

    # Tenant 2 profile remains unchanged
    t2_profile_after = client.get("/api/v1/organization/profile", headers=t2_headers).json()
    assert t2_profile_after["name"] == "Sushi Tokyo"
