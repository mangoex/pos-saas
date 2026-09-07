from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from restaurant_os import models, operations, platform_data
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    token = create_session_token(
        {"sub": USER_ID, "org_id": ORGANIZATION_ID, "role": "owner"},
        get_settings().secret_key,
    )
    return {"Authorization": f"Bearer {token}"}


def test_branch_google_review_url_crud(client, test_db, auth_headers):
    """
    TDD-TC-231: Persistencia y CRUD de google_review_url en Sucursales.
    """
    # 1. Crear sucursal con google_review_url
    bu_row = test_db.execute(models.business_units.select()).mappings().first()
    res = operations.create_branch(
        test_db,
        name="Sucursal Chapultepec",
        code="SUC-CHAP",
        actor_user_id=USER_ID,
        business_unit_id=bu_row["id"],
        google_review_url="https://g.page/r/AbCdEfGhIjK/review",
    )
    branch_id = res["id"]
    assert res["google_review_url"] == "https://g.page/r/AbCdEfGhIjK/review"

    # 2. Consultar list_branches
    branches = platform_data.list_branches(test_db, organization_id=ORGANIZATION_ID)
    branch_item = next(b for b in branches if b["id"] == branch_id)
    assert branch_item["google_review_url"] == "https://g.page/r/AbCdEfGhIjK/review"

    # 3. Actualizar google_review_url
    updated = operations.update_branch(
        test_db,
        branch_id=branch_id,
        actor_user_id=USER_ID,
        google_review_url="https://g.page/r/UpdatedURL/review",
    )
    assert updated["google_review_url"] == "https://g.page/r/UpdatedURL/review"

    # 4. Verificar endpoint público
    pub_resp = client.get("/api/v1/public/branches?identifier=test-restaurant")
    assert pub_resp.status_code == 200
    pub_data = pub_resp.json()
    pub_branch = next(b for b in pub_data if b["id"] == branch_id)
    assert pub_branch["google_review_url"] == "https://g.page/r/UpdatedURL/review"


def test_public_customer_feedback_endpoint(client, test_db, auth_headers):
    """
    TDD-TC-232: Captura de Feedback Privado de Comensales y consulta administrativa.
    """
    bu_row = test_db.execute(models.business_units.select()).mappings().first()
    b_res = operations.create_branch(
        test_db,
        name="Sucursal Centro",
        code="SUC-CEN",
        actor_user_id=USER_ID,
        business_unit_id=bu_row["id"],
        google_review_url="https://g.page/r/CentroReview/review",
    )
    branch_id = b_res["id"]

    # 1. Enviar feedback positivo (5 estrellas)
    fb1 = client.post(
        "/api/v1/public/feedback",
        json={
            "branch_id": branch_id,
            "rating": 5,
            "order_folio": "ORD-1001",
            "customer_name": "Juan Perez",
            "comment": "¡Excelente servicio y rapidez!",
        },
    )
    assert fb1.status_code == 201
    assert fb1.json()["status"] == "recorded"

    # 2. Enviar feedback negativo/privado (2 estrellas)
    fb2 = client.post(
        "/api/v1/public/feedback",
        json={
            "branch_id": branch_id,
            "rating": 2,
            "order_folio": "ORD-1002",
            "customer_name": "Maria Lopez",
            "comment": "La hamburguesa llegó un poco fría.",
        },
    )
    assert fb2.status_code == 201

    # 3. Enviar rating inválido (6 estrellas) -> Rechazo 422
    fb_invalid = client.post(
        "/api/v1/public/feedback",
        json={
            "branch_id": branch_id,
            "rating": 6,
        },
    )
    assert fb_invalid.status_code == 422

    # 4. Enviar para sucursal inexistente -> 404
    fb_404 = client.post(
        "/api/v1/public/feedback",
        json={
            "branch_id": "non-existent-branch-id",
            "rating": 4,
        },
    )
    assert fb_404.status_code == 404

    # 5. Consultar feedbacks desde el panel de administración
    admin_feedbacks = client.get("/api/v1/admin/feedbacks", headers=auth_headers)
    assert admin_feedbacks.status_code == 200
    feedbacks_list = admin_feedbacks.json()
    assert len(feedbacks_list) == 2
    assert feedbacks_list[0]["branch_name"] == "Sucursal Centro"
