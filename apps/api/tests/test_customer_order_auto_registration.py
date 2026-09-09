from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from restaurant_os import models, operations
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
    for perm in [
        "admin.manage",
        "catalog.manage",
        "orders.read",
        "orders.create",
        "cash.shift.open",
    ]:
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


from restaurant_os.config import get_settings


class _AvailableRateLimiter:
    def allow(self, *_args: object, **_kwargs: object) -> bool:
        return True


@pytest.fixture
def auth_headers():
    token = create_session_token(
        {"sub": USER_ID, "org_id": ORGANIZATION_ID, "role": "owner"},
        get_settings().secret_key,
    )
    return {"Authorization": f"Bearer {token}", "X-Actor-User-Id": USER_ID}


def _create_test_branch(client, auth_headers, code="SUC-CENTRO", name="Sucursal Centro"):
    res = client.post(
        "/api/v1/branches",
        headers=auth_headers,
        json={
            "code": code,
            "name": name,
            "address": "Av. Principal 123",
            "google_review_url": "https://g.page/r/CentroReview/review",
        },
    )
    assert res.status_code in (200, 201)
    return res.json()["id"]


def _create_test_product(test_db):
    now = datetime.now(timezone.utc)
    prod_id = str(uuid.uuid4())
    cat_id = str(uuid.uuid4())
    test_db.execute(
        models.product_categories.insert().values(
            id=cat_id,
            organization_id=ORGANIZATION_ID,
            name="General",
            status="active",
            display_order=1,
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.products.insert().values(
            id=prod_id,
            organization_id=ORGANIZATION_ID,
            category_id=cat_id,
            name="Hamburguesa Clásica",
            sku=f"HAMB-{prod_id[:4]}",
            station="cocina",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.price_versions.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            product_id=prod_id,
            price_cents=12000,
            currency="MXN",
            valid_from=now,
            created_at=now,
        )
    )
    test_db.commit()
    return prod_id


def _enable_public_orders(client, test_db, branch_id):
    row = test_db.execute(
        models.public_order_keys.select().where(
            models.public_order_keys.c.branch_id == branch_id
        )
    ).mappings().first()
    if row:
        public_key = row["public_key"]
    else:
        public_key = f"pk_test_{branch_id[:8]}"
        test_db.execute(
            models.public_order_keys.insert().values(
                public_key=public_key,
                organization_id=ORGANIZATION_ID,
                branch_id=branch_id,
                status="active",
            )
        )
        test_db.commit()
    client.app.state.public_order_intents_enabled = True
    client.app.state.public_order_rate_limiter = _AvailableRateLimiter()
    return public_key


def test_mobile_public_order_intent_auto_registers_customer(client, test_db, auth_headers):
    """
    TDD-TC-242: Al aceptar un pedido público con teléfono y nombre,
    se auto-registra el cliente en `customers` y `customer_phones`,
    y se vincula el `order.customer_id`.
    """
    branch_id = _create_test_branch(client, auth_headers, "SUC-01", "Sucursal Uno")
    prod_id = _create_test_product(test_db)
    public_key = _enable_public_orders(client, test_db, branch_id)

    # 1. Crear intención de pedido público móvil
    intent_res = client.post(
        f"/api/v1/public/branches/{public_key}/order-intents",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "customer_name": "Carlos Beltrán",
            "customer_phone": "6671234567",
            "order_type": "takeout",
            "lines": [{"product_id": prod_id, "quantity": 1}],
        },
    )
    assert intent_res.status_code == 201, intent_res.text
    intent_data = intent_res.json()
    public_ref = intent_data["public_reference"]

    intent_row = test_db.execute(
        models.public_order_intents.select().where(
            models.public_order_intents.c.public_reference == public_ref
        )
    ).mappings().first()
    assert intent_row is not None
    intent_id = intent_row["id"]

    # 2. Aceptar la intención como operador
    accept_res = client.post(
        f"/api/v1/order-intents/{intent_id}/accept",
        headers={**auth_headers, "Idempotency-Key": f"accept-intent-{uuid.uuid4()}"},
        json={"expected_version": 1},
    )
    assert accept_res.status_code in (200, 201), accept_res.text
    accepted_data = accept_res.json()
    order_id = accepted_data["id"]

    # 3. Validar que la orden tenga customer_id asignado
    order_row = test_db.execute(
        models.orders.select().where(models.orders.c.id == order_id)
    ).mappings().first()
    assert order_row is not None
    assert order_row["customer_id"] is not None

    # 4. Validar que el cliente exista en `customers` con los datos correctos
    customer_row = test_db.execute(
        models.customers.select().where(models.customers.c.id == order_row["customer_id"])
    ).mappings().first()
    assert customer_row is not None
    assert customer_row["name"] == "Carlos Beltrán"
    assert customer_row["origin_branch_id"] == branch_id

    # 5. Validar que el teléfono esté registrado en `customer_phones` normalizado
    phone_row = test_db.execute(
        models.customer_phones.select().where(
            models.customer_phones.c.customer_id == customer_row["id"]
        )
    ).mappings().first()
    assert phone_row is not None
    assert phone_row["normalized_number"] == "+526671234567"
    assert phone_row["is_primary"] is True


def test_pos_local_order_auto_registers_or_links_customer(client, test_db, auth_headers):
    """
    TDD-TC-243: Venta local en POS registra al cliente si no existe,
    y si se repite la venta con el mismo teléfono, se vincula al mismo cliente.
    """
    branch_id = _create_test_branch(client, auth_headers, "SUC-02", "Sucursal Dos")
    prod_id = _create_test_product(test_db)

    # Abrir turno de caja
    operations.open_cash_shift(test_db, 0, branch_id=branch_id, actor_user_id=USER_ID)
    test_db.commit()

    # 1. Crear orden POS con teléfono y nombre
    order1 = operations.create_local_order(
        session=test_db,
        lines=[{"product_id": prod_id, "quantity": 1}],
        owner_name="Mariana Rios",
        customer_phone="6699887766",
        branch_id=branch_id,
        actor_user_id=USER_ID,
    )
    test_db.commit()
    assert order1["customer_id"] is not None
    cust1_id = order1["customer_id"]

    # Verificar datos del cliente
    c1 = test_db.execute(
        models.customers.select().where(models.customers.c.id == cust1_id)
    ).mappings().first()
    assert c1["name"] == "Mariana Rios"
    assert c1["origin_branch_id"] == branch_id

    # 2. Segunda orden con el MISMO teléfono
    order2 = operations.create_local_order(
        session=test_db,
        lines=[{"product_id": prod_id, "quantity": 2}],
        owner_name="Mariana Rios",
        customer_phone="6699887766",
        branch_id=branch_id,
        actor_user_id=USER_ID,
    )
    test_db.commit()
    # Debe reutilizar el mismo customer_id sin duplicar
    assert order2["customer_id"] == cust1_id

    # Conteo de clientes con ese teléfono debe ser exactamente 1
    phone_rows = list(test_db.execute(
        models.customer_phones.select().where(
            models.customer_phones.c.normalized_number == "+526699887766"
        )
    ).mappings())
    assert len(phone_rows) == 1


def test_customer_feedback_persistence_and_average_rating(client, test_db, auth_headers):
    """
    TDD-TC-244: Guardado incondicional de feedback (1-5 estrellas)
    vinculado a customer_id y cálculo del promedio de satisfacción.
    """
    branch_id = _create_test_branch(client, auth_headers, "SUC-03", "Sucursal Tres")

    # Crear cliente manualmente
    cust_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    test_db.execute(
        models.customers.insert().values(
            id=cust_id,
            organization_id=ORGANIZATION_ID,
            name="Roberto Gomez",
            status="active",
            origin_branch_id=branch_id,
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.customer_phones.insert().values(
            id=str(uuid.uuid4()),
            customer_id=cust_id,
            captured_number="6681122334",
            normalized_number="+526681122334",
            phone_type="mobile",
            is_primary=True,
            whatsapp_enabled=True,
            is_verified=False,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.commit()

    # 1. Enviar feedback 5 estrellas con customer_id
    fb1 = client.post(
        "/api/v1/public/feedback",
        json={
            "branch_id": branch_id,
            "rating": 5,
            "customer_id": cust_id,
            "customer_name": "Roberto Gomez",
            "comment": "Todo excelente",
        },
    )
    assert fb1.status_code == 201

    # 2. Enviar feedback 3 estrellas con teléfono (debe resolver al cliente)
    fb2 = client.post(
        "/api/v1/public/feedback",
        json={
            "branch_id": branch_id,
            "rating": 3,
            "customer_phone": "6681122334",
            "customer_name": "Roberto Gomez",
            "comment": "La salsa estaba muy picante",
        },
    )
    assert fb2.status_code == 201

    # Validar que ambos feedbacks quedaron vinculados a cust_id
    feedbacks = list(test_db.execute(
        models.customer_feedbacks.select().where(
            models.customer_feedbacks.c.customer_id == cust_id
        )
    ).mappings())
    assert len(feedbacks) == 2


def test_list_customers_includes_rating_summary_and_feedbacks(client, test_db, auth_headers):
    """
    TDD-TC-245: El listado de clientes expone `rating_summary` con
    promedio y total de opiniones, y endpoint de feedbacks por cliente.
    """
    branch_id = _create_test_branch(client, auth_headers, "SUC-04", "Sucursal Cuatro")

    # Crear cliente
    cust_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    test_db.execute(
        models.customers.insert().values(
            id=cust_id,
            organization_id=ORGANIZATION_ID,
            name="Laura Pausini",
            status="active",
            origin_branch_id=branch_id,
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.customer_phones.insert().values(
            id=str(uuid.uuid4()),
            customer_id=cust_id,
            captured_number="6675554433",
            normalized_number="+526675554433",
            phone_type="mobile",
            is_primary=True,
            whatsapp_enabled=True,
            is_verified=False,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    # Registrar dos feedbacks: 4 y 2 estrellas -> promedio 3.0
    for r, c in [(4, "Buen servicio"), (2, "Llegó frío")]:
        test_db.execute(
            models.customer_feedbacks.insert().values(
                id=str(uuid.uuid4()),
                organization_id=ORGANIZATION_ID,
                branch_id=branch_id,
                customer_id=cust_id,
                customer_phone="+526675554433",
                rating=r,
                comment=c,
                created_at=now,
            )
        )
    test_db.commit()

    # Consultar listado de clientes
    res = client.get("/api/v1/customers", headers=auth_headers)
    assert res.status_code == 200
    customers_data = res.json()
    items = customers_data if isinstance(customers_data, list) else customers_data.get("items", [])
    laura = next((c for c in items if c["id"] == cust_id), None)
    assert laura is not None
    assert "rating_summary" in laura
    assert laura["rating_summary"]["average_rating"] == 3.0
    assert laura["rating_summary"]["rating_count"] == 2

    # Consultar endpoint individual de feedbacks del cliente
    fb_res = client.get(f"/api/v1/customers/{cust_id}/feedbacks", headers=auth_headers)
    assert fb_res.status_code == 200
    feedbacks = fb_res.json()
    assert len(feedbacks) == 2
