from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models, operations
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from restaurant_os.operations import ORGANIZATION_ID
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
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
    row = (
        test_db.execute(
            models.public_order_keys.select().where(
                models.public_order_keys.c.branch_id == branch_id
            )
        )
        .mappings()
        .first()
    )
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


def _create_and_accept_public_intent(
    client,
    test_db,
    auth_headers,
    *,
    public_key,
    product_id,
    phone,
    name,
):
    intent_response = client.post(
        f"/api/v1/public/branches/{public_key}/order-intents",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "customer_name": name,
            "customer_phone": phone,
            "order_type": "takeout",
            "lines": [{"product_id": product_id, "quantity": 1}],
        },
    )
    assert intent_response.status_code == 201, intent_response.text
    public_reference = intent_response.json()["public_reference"]
    intent_id = test_db.scalar(
        sa.select(models.public_order_intents.c.id).where(
            models.public_order_intents.c.public_reference == public_reference
        )
    )
    accept_response = client.post(
        f"/api/v1/order-intents/{intent_id}/accept",
        headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"expected_version": 1},
    )
    assert accept_response.status_code in (200, 201), accept_response.text
    accepted_order = accept_response.json()
    customer_id = test_db.scalar(
        sa.select(models.orders.c.customer_id).where(models.orders.c.id == accepted_order["id"])
    )
    return public_reference, {**accepted_order, "customer_id": customer_id}


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

    intent_row = (
        test_db.execute(
            models.public_order_intents.select().where(
                models.public_order_intents.c.public_reference == public_ref
            )
        )
        .mappings()
        .first()
    )
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
    order_row = (
        test_db.execute(models.orders.select().where(models.orders.c.id == order_id))
        .mappings()
        .first()
    )
    assert order_row is not None
    assert order_row["customer_id"] is not None

    # 4. Validar que el cliente exista en `customers` con los datos correctos
    customer_row = (
        test_db.execute(
            models.customers.select().where(models.customers.c.id == order_row["customer_id"])
        )
        .mappings()
        .first()
    )
    assert customer_row is not None
    assert customer_row["name"] == "Carlos Beltrán"
    assert customer_row["origin_branch_id"] == branch_id

    # 5. Validar que el teléfono esté registrado en `customer_phones` normalizado
    phone_row = (
        test_db.execute(
            models.customer_phones.select().where(
                models.customer_phones.c.customer_id == customer_row["id"]
            )
        )
        .mappings()
        .first()
    )
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
    c1 = (
        test_db.execute(models.customers.select().where(models.customers.c.id == cust1_id))
        .mappings()
        .first()
    )
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
    phone_rows = list(
        test_db.execute(
            models.customer_phones.select().where(
                models.customer_phones.c.normalized_number == "+526699887766"
            )
        ).mappings()
    )
    assert len(phone_rows) == 1


def test_customer_feedback_persistence_and_average_rating(client, test_db, auth_headers):
    """
    TDD-TC-244: Guardado incondicional de feedback (1-5 estrellas)
    vinculado a customer_id y cálculo del promedio de satisfacción.
    """
    branch_id = _create_test_branch(client, auth_headers, "SUC-03", "Sucursal Tres")
    product_id = _create_test_product(test_db)
    public_key = _enable_public_orders(client, test_db, branch_id)
    first_reference, first_order = _create_and_accept_public_intent(
        client,
        test_db,
        auth_headers,
        public_key=public_key,
        product_id=product_id,
        phone="6681122334",
        name="Roberto Gomez",
    )
    second_reference, second_order = _create_and_accept_public_intent(
        client,
        test_db,
        auth_headers,
        public_key=public_key,
        product_id=product_id,
        phone="6681122334",
        name="Roberto Gomez",
    )
    cust_id = first_order["customer_id"]
    assert second_order["customer_id"] == cust_id

    for reference, rating, comment in [
        (first_reference, 5, "Todo excelente"),
        (second_reference, 3, "La salsa estaba muy picante"),
    ]:
        feedback_response = client.post(
            "/api/v1/public/feedback",
            json={
                "branch_id": branch_id,
                "rating": rating,
                "customer_phone": "6681122334",
                "order_folio": reference,
                "comment": comment,
            },
        )
        assert feedback_response.status_code == 201

    # Validar que ambos feedbacks quedaron vinculados a cust_id
    feedbacks = list(
        test_db.execute(
            models.customer_feedbacks.select().where(
                models.customer_feedbacks.c.customer_id == cust_id
            )
        ).mappings()
    )
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


def test_mobile_public_order_feedback_linked_before_and_after_acceptance(
    client, test_db, auth_headers
):
    """
    TDD-TC-246: Vinculación de feedback emitido antes de la aceptación del pedido móvil.
    El comensal califica en el modal de éxito inmediatamente al enviar el pedido
    (status PENDING_REVIEW, con folio de referencia pública REF-...). Al aceptarse,
    el feedback queda vinculado al cliente creado y se refleja en /customers.
    """
    branch_id = _create_test_branch(client, auth_headers, "SUC-FB1", "Sucursal Feedback 1")
    prod_id = _create_test_product(test_db)
    public_key = _enable_public_orders(client, test_db, branch_id)

    # 1. Comensal envía intención de pedido público
    intent_res = client.post(
        f"/api/v1/public/branches/{public_key}/order-intents",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "customer_name": "Ana Silva",
            "customer_phone": "6689998877",
            "order_type": "takeout",
            "lines": [{"product_id": prod_id, "quantity": 1}],
        },
    )
    assert intent_res.status_code == 201
    intent_data = intent_res.json()
    public_ref = intent_data["public_reference"]

    intent_row = (
        test_db.execute(
            models.public_order_intents.select().where(
                models.public_order_intents.c.public_reference == public_ref
            )
        )
        .mappings()
        .first()
    )
    assert intent_row is not None
    intent_id = intent_row["id"]

    # 2. El comensal califica antes de que el restaurante acepte el pedido.
    fb_res = client.post(
        "/api/v1/public/feedback",
        json={
            "branch_id": branch_id,
            "rating": 5,
            "customer_phone": "6689998877",
            "order_folio": public_ref,
            "comment": "Calificación positiva (App Móvil)",
        },
    )
    assert fb_res.status_code == 201

    # 3. Restaurante acepta la intención de pedido
    accept_res = client.post(
        f"/api/v1/order-intents/{intent_id}/accept",
        headers={**auth_headers, "Idempotency-Key": f"accept-fb-{uuid.uuid4()}"},
        json={"expected_version": 1},
    )
    assert accept_res.status_code in (200, 201)
    accepted_order_id = accept_res.json()["id"]

    order_row = (
        test_db.execute(models.orders.select().where(models.orders.c.id == accepted_order_id))
        .mappings()
        .first()
    )
    assert order_row is not None
    cust_id = order_row["customer_id"]
    assert cust_id is not None

    # 4. Validar que en /customers el cliente tiene rating_summary con 5.0 y 1 opinión
    custs_res = client.get("/api/v1/customers", headers=auth_headers)
    assert custs_res.status_code == 200
    cust_data = custs_res.json()
    cust_list = cust_data if isinstance(cust_data, list) else cust_data.get("items", [])
    ana = next((c for c in cust_list if c["id"] == cust_id), None)
    assert ana is not None
    assert ana["rating_summary"]["average_rating"] == 5.0
    assert ana["rating_summary"]["rating_count"] == 1
    assert len(ana["rating_summary"]["recent_feedbacks"]) == 1
    assert ana["rating_summary"]["recent_feedbacks"][0]["rating"] == 5
    assert (
        ana["rating_summary"]["recent_feedbacks"][0]["comment"]
        == "Calificación positiva (App Móvil)"
    )

    # 5. Validar que el endpoint individual de feedbacks del cliente retorna la reseña
    ind_res = client.get(f"/api/v1/customers/{cust_id}/feedbacks", headers=auth_headers)
    assert ind_res.status_code == 200
    fbs = ind_res.json()
    assert len(fbs) == 1
    assert fbs[0]["rating"] == 5
    assert fbs[0]["comment"] == "Calificación positiva (App Móvil)"


def test_feedback_upsert_and_retroactive_healing(client, test_db, auth_headers):
    """
    TDD-TC-247: Validación de upsert en comentarios privados y auto-sanación de feedbacks huérfanos.
    1. Si un comensal envía una calificación inicial y después un comentario privado
       con el mismo order_folio, se actualiza el registro sin duplicarlo.
    2. Si existía un feedback previo con customer_id NULL y teléfono normalizado, al crear
       el cliente, el feedback se auto-sana y vincula dentro de la organización.
    """
    branch_id = _create_test_branch(client, auth_headers, "SUC-FB2", "Sucursal Feedback 2")

    # A) Upsert al enviar comentario privado posterior para una referencia persistida
    product_id = _create_test_product(test_db)
    public_key = _enable_public_orders(client, test_db, branch_id)
    intent_response = client.post(
        f"/api/v1/public/branches/{public_key}/order-intents",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "customer_name": "Mario Gomez",
            "customer_phone": "6681122334",
            "order_type": "takeout",
            "lines": [{"product_id": product_id, "quantity": 1}],
        },
    )
    assert intent_response.status_code == 201, intent_response.text
    ref_order = intent_response.json()["public_reference"]
    fb1 = client.post(
        "/api/v1/public/feedback",
        json={
            "branch_id": branch_id,
            "rating": 2,
            "customer_phone": "6681122334",
            "order_folio": ref_order,
            "comment": None,
        },
    )
    assert fb1.status_code == 201

    fb2 = client.post(
        "/api/v1/public/feedback",
        json={
            "branch_id": branch_id,
            "rating": 2,
            "customer_phone": "6681122334",
            "order_folio": ref_order,
            "comment": "El pedido tardó demasiado",
        },
    )
    assert fb2.status_code == 201

    rows = list(
        test_db.execute(
            models.customer_feedbacks.select().where(
                models.customer_feedbacks.c.order_folio == ref_order
            )
        ).mappings()
    )
    # Debe existir exactamente 1 registro, no 2
    assert len(rows) == 1
    assert rows[0]["rating"] == 2
    assert rows[0]["comment"] == "El pedido tardó demasiado"

    # B) Auto-sanación de feedback huérfano histórico
    orphan_phone = "6687766554"
    orphan_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    test_db.execute(
        models.customer_feedbacks.insert().values(
            id=orphan_id,
            organization_id=ORGANIZATION_ID,
            branch_id=branch_id,
            customer_id=None,  # Huérfano
            customer_phone=orphan_phone,
            order_folio="REF-ORPHAN-1",
            rating=4,
            customer_name="Beatriz Mendoza",
            comment="Muy buen sabor",
            created_at=now,
        )
    )
    test_db.commit()

    # Ahora se crea/registra a Beatriz
    create_cust = client.post(
        "/api/v1/customers",
        headers=auth_headers,
        json={
            "branch_id": branch_id,
            "name": "Beatriz Mendoza",
            "phones": [{"number": orphan_phone, "is_primary": True}],
        },
    )
    assert create_cust.status_code in (200, 201)
    beatriz_id = create_cust.json()["id"]

    # Consultar el directorio conserva el vínculo auto-sanado con Beatriz.
    custs_res = client.get("/api/v1/customers", headers=auth_headers)
    assert custs_res.status_code == 200
    b_data = custs_res.json()
    items = b_data if isinstance(b_data, list) else b_data.get("items", [])
    beatriz = next((c for c in items if c["id"] == beatriz_id), None)
    assert beatriz is not None
    assert beatriz["rating_summary"]["average_rating"] == 4.0
    assert beatriz["rating_summary"]["rating_count"] == 1
    assert beatriz["rating_summary"]["recent_feedbacks"][0]["comment"] == "Muy buen sabor"


def test_public_feedback_requires_matching_persisted_order_identity(client, test_db, auth_headers):
    """TDD-TC-247: la frontera pública no acepta identidad elegida ni referencias ajenas."""
    branch_id = _create_test_branch(client, auth_headers, "SUC-FB-SEC", "Sucursal Feedback")
    other_branch_id = _create_test_branch(
        client, auth_headers, "SUC-FB-OTHER", "Sucursal Feedback Otra"
    )
    product_id = _create_test_product(test_db)
    public_key = _enable_public_orders(client, test_db, branch_id)
    intent_response = client.post(
        f"/api/v1/public/branches/{public_key}/order-intents",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={
            "customer_name": "Cliente Seguro",
            "customer_phone": "6671234567",
            "order_type": "takeout",
            "lines": [{"product_id": product_id, "quantity": 1}],
        },
    )
    assert intent_response.status_code == 201, intent_response.text
    public_reference = intent_response.json()["public_reference"]

    chosen_identity = client.post(
        "/api/v1/public/feedback",
        json={
            "branch_id": branch_id,
            "rating": 1,
            "customer_id": str(uuid.uuid4()),
            "customer_phone": "6671234567",
            "order_folio": public_reference,
            "comment": "No debe persistir",
        },
    )
    assert chosen_identity.status_code == 422

    wrong_phone = client.post(
        "/api/v1/public/feedback",
        json={
            "branch_id": branch_id,
            "rating": 1,
            "customer_phone": "6699999999",
            "order_folio": public_reference,
            "comment": "No debe persistir",
        },
    )
    assert wrong_phone.status_code == 404

    wrong_branch = client.post(
        "/api/v1/public/feedback",
        json={
            "branch_id": other_branch_id,
            "rating": 1,
            "customer_phone": "6671234567",
            "order_folio": public_reference,
            "comment": "No debe persistir",
        },
    )
    assert wrong_branch.status_code == 404

    persisted = test_db.scalar(
        sa.select(sa.func.count())
        .select_from(models.customer_feedbacks)
        .where(models.customer_feedbacks.c.order_folio == public_reference)
    )
    assert persisted == 0


def test_customer_rating_summary_excludes_cross_organization_feedback(test_db):
    """TDD-TC-247: una asociación histórica inválida no cruza el tenant de lectura."""
    now = datetime.now(timezone.utc)
    other_organization_id = "018f6f73-2d0a-74f0-8f1c-000000000099"
    customer_id = str(uuid.uuid4())
    test_db.execute(
        models.organizations.insert().values(
            id=other_organization_id,
            slug="other-restaurant",
            name="Otra Organización",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.customers.insert().values(
            id=customer_id,
            organization_id=other_organization_id,
            name="Cliente Otra Organización",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.customer_feedbacks.insert().values(
            id=str(uuid.uuid4()),
            organization_id=ORGANIZATION_ID,
            branch_id=operations.BRANCH_ID,
            customer_id=customer_id,
            order_folio="CROSS-ORG-1",
            rating=1,
            comment="Dato de otra organización",
            created_at=now,
        )
    )
    test_db.commit()

    summary = operations.get_customer_rating_summary(test_db, customer_id, other_organization_id)
    assert summary == {
        "average_rating": None,
        "rating_count": 0,
        "recent_feedbacks": [],
    }


def test_customer_feedback_order_reference_is_unique_per_branch(test_db):
    """TDD-TC-247: dos escritores no pueden crear dos filas para la misma referencia."""
    now = datetime.now(timezone.utc)
    first = {
        "id": str(uuid.uuid4()),
        "organization_id": ORGANIZATION_ID,
        "branch_id": operations.BRANCH_ID,
        "order_folio": "UNIQUE-FEEDBACK-1",
        "rating": 4,
        "created_at": now,
    }
    test_db.execute(models.customer_feedbacks.insert().values(**first))
    test_db.commit()

    with pytest.raises(IntegrityError):
        test_db.execute(
            models.customer_feedbacks.insert().values(
                **{**first, "id": str(uuid.uuid4()), "rating": 2}
            )
        )
        test_db.commit()
    test_db.rollback()
