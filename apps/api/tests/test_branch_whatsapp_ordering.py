from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from restaurant_os.operations import ORGANIZATION_ID
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

app = create_app()

USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
ROLE_ID = "018f6f73-2d0a-74f0-8f1c-000000000004"


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    now = datetime.now(timezone.utc)
    session.execute(
        models.organizations.insert().values(
            id=ORGANIZATION_ID,
            slug="test-restaurant",
            name="Kiwi Corporativo",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    legal_id = str(uuid.uuid4())
    session.execute(
        models.legal_entities.insert().values(
            id=legal_id,
            organization_id=ORGANIZATION_ID,
            name="Kiwi SA de CV",
            created_at=now,
            updated_at=now,
        )
    )
    bu_id = str(uuid.uuid4())
    session.execute(
        models.business_units.insert().values(
            id=bu_id,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=legal_id,
            name="Kiwi Natural",
            code="KN",
            unit_type="restaurant",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.users.insert().values(
            id=USER_ID,
            organization_id=ORGANIZATION_ID,
            email="admin@kiwi.com",
            display_name="Admin",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.roles.insert().values(
            id=ROLE_ID,
            organization_id=ORGANIZATION_ID,
            name="Dueño",
            scope="organization",
            created_at=now,
        )
    )
    session.execute(models.user_roles.insert().values(user_id=USER_ID, role_id=ROLE_ID))
    for perm in ["admin.manage", "catalog.manage", "orders.read", "orders.create"]:
        perm_id = str(uuid.uuid4())
        session.execute(
            models.permissions.insert().values(
                id=perm_id, code=perm, description=perm, created_at=now
            )
        )
        session.execute(
            models.role_permissions.insert().values(role_id=ROLE_ID, permission_id=perm_id)
        )

    session.commit()
    yield session
    session.close()


@pytest.fixture
def client(test_db):
    def override_get_session():
        yield test_db

    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    from restaurant_os.config import get_settings

    token = create_session_token(
        {"sub": USER_ID, "org_id": ORGANIZATION_ID, "role": "owner"},
        get_settings().secret_key,
    )
    return {"Authorization": f"Bearer {token}"}



def test_branch_whatsapp_ordering_enabled_crud(client, test_db, auth_headers):
    """Verifica que whatsapp_ordering_enabled se persista, consulte y actualice en /branches."""
    bu = test_db.execute(models.business_units.select()).mappings().first()

    # 1. Crear sucursal con whatsapp_ordering_enabled=True explícito
    res = client.post(
        "/api/v1/branches",
        headers=auth_headers,
        json={
            "name": "Sucursal Matriz",
            "code": "SUC-WHA",
            "business_unit_id": bu["id"],
            "phone": "+523312345678",
            "whatsapp_ordering_enabled": True,
        },

    ).json()

    assert "id" in res, res
    assert res["phone"] == "+523312345678"
    assert res.get("whatsapp_ordering_enabled") is True

    branch_id = res["id"]

    # 2. Consultar lista de sucursales y verificar el campo
    branches_res = client.get("/api/v1/branches", headers=auth_headers).json()
    branch_item = next(b for b in branches_res if b["id"] == branch_id)
    assert branch_item.get("whatsapp_ordering_enabled") is True

    # 3. Actualizar whatsapp_ordering_enabled a False
    updated = client.put(
        f"/api/v1/branches/{branch_id}",
        headers=auth_headers,
        json={
            "whatsapp_ordering_enabled": False,
        },
    ).json()

    assert updated.get("whatsapp_ordering_enabled") is False

    # 4. Verificar cambio persistido
    branches_res2 = client.get("/api/v1/branches", headers=auth_headers).json()
    branch_item2 = next(b for b in branches_res2 if b["id"] == branch_id)
    assert branch_item2.get("whatsapp_ordering_enabled") is False

    # 5. Verificar proyección pública en storefront
    pub_res = client.get("/api/v1/public/branches?identifier=test-restaurant")
    if pub_res.status_code == 200:
        pub_branches = pub_res.json()
        pub_branch = next(b for b in pub_branches if b["id"] == branch_id)
        assert "whatsapp_ordering_enabled" in pub_branch
        assert pub_branch["whatsapp_ordering_enabled"] is False


