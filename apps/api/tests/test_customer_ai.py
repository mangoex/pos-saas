"""Tests for Customer AI, CRM Segmentation, and Upsell Recommendations."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.customer_ai import (
    generate_churn_recovery_message,
    get_crm_segments_and_churn_risk,
    get_customer_upsell_recommendations,
)
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from restaurant_os.operations import BRANCH_ID, ORGANIZATION_ID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

UTC = timezone.utc
USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
LEGAL_ENTITY_ID = "018f6f73-2d0a-74f0-8f1c-000000000010"
BUSINESS_UNIT_ID = "018f6f73-2d0a-74f0-8f1c-000000000020"
CUSTOMER_ID = "018f6f73-2d0a-74f0-8f1c-000000000080"
PRODUCT_A_ID = "018f6f73-2d0a-74f0-8f1c-000000000091"
PRODUCT_B_ID = "018f6f73-2d0a-74f0-8f1c-000000000092"
PRODUCT_C_ID = "018f6f73-2d0a-74f0-8f1c-000000000094"
CATEGORY_ID = "018f6f73-2d0a-74f0-8f1c-000000000090"
FOOD_CATEGORY_ID = "018f6f73-2d0a-74f0-8f1c-000000000093"

app = create_app()


@pytest.fixture
def test_db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(test_db: Session) -> TestClient:
    app.dependency_overrides[get_session] = lambda: test_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_crm_data(test_db: Session) -> dict[str, str]:
    now = datetime.now(timezone.utc)

    # 1. Organization & Legal Entity & Business Unit & Branch
    test_db.execute(
        models.organizations.insert().values(
            id=ORGANIZATION_ID,
            name="Kiwi Corporativo",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.legal_entities.insert().values(
            id=LEGAL_ENTITY_ID,
            organization_id=ORGANIZATION_ID,
            name="Kiwi SA",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.business_units.insert().values(
            id=BUSINESS_UNIT_ID,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=LEGAL_ENTITY_ID,
            name="Unidad",
            code="U1",
            unit_type="branch",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.branches.insert().values(
            id=BRANCH_ID,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=LEGAL_ENTITY_ID,
            business_unit_id=BUSINESS_UNIT_ID,
            name="Sucursal Centro",
            code="CEN",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    role_id = "018f6f73-2d0a-74f0-8f1c-000000000071"
    permission_id = "018f6f73-2d0a-74f0-8f1c-000000000072"
    test_db.execute(
        models.users.insert().values(
            id=USER_ID,
            organization_id=ORGANIZATION_ID,
            email="customer-reader@kiwi.test",
            display_name="Customer reader",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.roles.insert().values(
            id=role_id,
            organization_id=ORGANIZATION_ID,
            name="Customer reader",
            scope="branch",
            created_at=now,
        )
    )
    test_db.execute(
        models.permissions.insert().values(
            id=permission_id,
            code="customers.read",
            description="Read customers",
            created_at=now,
        )
    )
    test_db.execute(
        models.user_roles.insert().values(user_id=USER_ID, role_id=role_id, branch_id=BRANCH_ID)
    )
    test_db.execute(
        models.role_permissions.insert().values(role_id=role_id, permission_id=permission_id)
    )

    # 2. Product Category & Products
    test_db.execute(
        models.product_categories.insert().values(
            id=CATEGORY_ID,
            organization_id=ORGANIZATION_ID,
            name="Bebidas",
            display_order=1,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.product_categories.insert().values(
            id=FOOD_CATEGORY_ID,
            organization_id=ORGANIZATION_ID,
            name="Alimentos",
            display_order=2,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.products.insert().values(
            id=PRODUCT_A_ID,
            organization_id=ORGANIZATION_ID,
            category_id=CATEGORY_ID,
            name="Maccha Pinku",
            sku="PROD-MP",
            station="drinks",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.products.insert().values(
            id=PRODUCT_B_ID,
            organization_id=ORGANIZATION_ID,
            category_id=FOOD_CATEGORY_ID,
            name="Baguette integral",
            sku="PROD-BI",
            station="kitchen",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.products.insert().values(
            id=PRODUCT_C_ID,
            organization_id=ORGANIZATION_ID,
            category_id=CATEGORY_ID,
            name="Jugo no disponible",
            sku="PROD-JN",
            station="drinks",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # 3. Price Versions
    test_db.execute(
        models.price_versions.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-000000000095",
            organization_id=ORGANIZATION_ID,
            product_id=PRODUCT_A_ID,
            price_cents=8500,
            valid_from=now,
            created_at=now,
        )
    )
    test_db.execute(
        models.price_versions.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-000000000096",
            organization_id=ORGANIZATION_ID,
            product_id=PRODUCT_B_ID,
            price_cents=14000,
            valid_from=now,
            created_at=now,
        )
    )
    test_db.execute(
        models.price_versions.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-000000000097",
            organization_id=ORGANIZATION_ID,
            product_id=PRODUCT_C_ID,
            price_cents=7000,
            valid_from=now,
            created_at=now,
        )
    )
    test_db.execute(
        models.branch_product_availability.insert().values(
            branch_id=BRANCH_ID, product_id=PRODUCT_C_ID, is_available=False, updated_at=now
        )
    )

    # Product C has the strongest raw co-occurrence but is unavailable in this branch.
    for order_index in range(3):
        order_id = f"018f6f73-2d0a-74f0-8f1c-{201 + order_index:012d}"
        test_db.execute(
            models.orders.insert().values(
                id=order_id,
                organization_id=ORGANIZATION_ID,
                branch_id=BRANCH_ID,
                folio=f"AI-{order_index + 1}",
                channel="UBER_EATS",
                status="delivered",
                total_cents=28000,
                created_at=now,
            )
        )
        paired_products = [
            (PRODUCT_B_ID, "Baguette integral", "kitchen", FOOD_CATEGORY_ID, "Alimentos", 14000),
            (PRODUCT_C_ID, "Jugo no disponible", "drinks", CATEGORY_ID, "Bebidas", 7000),
        ]
        if order_index < 2:
            paired_products.append(
                (PRODUCT_A_ID, "Maccha Pinku", "drinks", CATEGORY_ID, "Bebidas", 7000)
            )
        for line_index, (product_id, name, station, family_id, family_name, price) in enumerate(
            paired_products
        ):
            test_db.execute(
                models.order_lines.insert().values(
                    id=f"018f6f73-2d0a-74f0-8f1c-{211 + order_index * 3 + line_index:012d}",
                    order_id=order_id,
                    product_id=product_id,
                    product_name=name,
                    quantity=1,
                    unit_price_cents=price,
                    line_total_cents=price,
                    station=station,
                    family_id_snapshot=family_id,
                    family_name_snapshot=family_name,
                    family_snapshot_source="captured",
                    created_at=now,
                )
            )

    # 4. Customer & Phone
    test_db.execute(
        models.customers.insert().values(
            id=CUSTOMER_ID,
            organization_id=ORGANIZATION_ID,
            origin_branch_id=BRANCH_ID,
            name="Valeria Silva",
            email="valeria@example.com",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.customer_phones.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-000000000099",
            customer_id=CUSTOMER_ID,
            captured_number="5512345678",
            normalized_number="+525512345678",
            phone_type="mobile",
            is_primary=True,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    test_db.commit()
    return {
        "branch_id": BRANCH_ID,
        "customer_id": CUSTOMER_ID,
        "product_a_id": PRODUCT_A_ID,
        "product_b_id": PRODUCT_B_ID,
        "product_c_id": PRODUCT_C_ID,
    }


def test_get_customer_upsell_recommendations(
    test_db: Session, sample_crm_data: dict[str, str]
) -> None:
    recs = get_customer_upsell_recommendations(
        test_db,
        organization_id=ORGANIZATION_ID,
        customer_id=sample_crm_data["customer_id"],
        current_product_ids=[sample_crm_data["product_a_id"]],
    )
    assert isinstance(recs, list)
    assert all("confidence_score" not in recommendation for recommendation in recs)


def test_branch_scoped_cross_category_recommendations(
    test_db: Session, sample_crm_data: dict[str, str]
) -> None:
    recs = get_customer_upsell_recommendations(
        test_db,
        current_product_ids=[sample_crm_data["product_b_id"]],
        branch_id=sample_crm_data["branch_id"],
    )

    assert [rec["product_id"] for rec in recs] == [sample_crm_data["product_a_id"]]
    assert recs[0]["reason"] == "Frecuentemente pedido con tu selección (2 pedidos)"
    assert sample_crm_data["product_c_id"] not in {rec["product_id"] for rec in recs}

    reverse_recs = get_customer_upsell_recommendations(
        test_db,
        current_product_ids=[sample_crm_data["product_a_id"]],
        branch_id=sample_crm_data["branch_id"],
    )
    assert [rec["product_id"] for rec in reverse_recs] == [sample_crm_data["product_b_id"]]

    mixed_recs = get_customer_upsell_recommendations(
        test_db,
        current_product_ids=[
            sample_crm_data["product_a_id"],
            sample_crm_data["product_b_id"],
        ],
        branch_id=sample_crm_data["branch_id"],
    )
    assert mixed_recs == []


def test_public_upsell_endpoint_requires_branch_context(
    client: TestClient, sample_crm_data: dict[str, str]
) -> None:
    scoped = client.post(
        "/api/v1/public/order-upsell-recommendations",
        json={
            "branch_id": sample_crm_data["branch_id"],
            "current_product_ids": [sample_crm_data["product_b_id"]],
        },
    )
    assert scoped.status_code == 200
    assert [item["product_id"] for item in scoped.json()["recommendations"]] == [
        sample_crm_data["product_a_id"]
    ]

    missing_branch = client.post(
        "/api/v1/public/order-upsell-recommendations",
        json={"current_product_ids": [sample_crm_data["product_b_id"]]},
    )
    assert missing_branch.status_code == 200
    assert missing_branch.json() == {"recommendations": []}

    unknown_branch = client.post(
        "/api/v1/public/order-upsell-recommendations",
        json={
            "branch_id": "018f6f73-2d0a-74f0-8f1c-999999999999",
            "current_product_ids": [sample_crm_data["product_b_id"]],
        },
    )
    assert unknown_branch.status_code == 200
    assert unknown_branch.json() == {"recommendations": []}


def test_get_crm_segments_and_churn_risk(test_db: Session, sample_crm_data: dict[str, str]) -> None:
    crm_summary = get_crm_segments_and_churn_risk(
        test_db,
        organization_id=ORGANIZATION_ID,
        branch_id=sample_crm_data["branch_id"],
    )
    assert "vip_customers" in crm_summary
    assert "churn_risk_customers" in crm_summary
    assert "new_customers" in crm_summary


def test_crm_ignores_customers_and_orders_from_another_organization(
    test_db: Session, sample_crm_data: dict[str, str]
) -> None:
    now = datetime.now(timezone.utc)
    other_org_id = "018f6f73-2d0a-74f0-8f1c-000000000501"
    other_customer_id = "018f6f73-2d0a-74f0-8f1c-000000000502"
    other_branch_id = "018f6f73-2d0a-74f0-8f1c-000000000504"
    other_product_id = "018f6f73-2d0a-74f0-8f1c-000000000505"
    other_category_id = "018f6f73-2d0a-74f0-8f1c-000000000507"
    test_db.execute(
        models.organizations.insert().values(
            id=other_org_id,
            name="Another tenant",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.customers.insert().values(
            id=other_customer_id,
            organization_id=other_org_id,
            name="Other tenant customer",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.product_categories.insert().values(
            id=other_category_id,
            organization_id=other_org_id,
            name="Other category",
            display_order=1,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.products.insert().values(
            id=other_product_id,
            organization_id=other_org_id,
            category_id=other_category_id,
            name="Other tenant product",
            sku="OTHER-PRODUCT",
            station="drinks",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.price_versions.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-000000000506",
            organization_id=other_org_id,
            product_id=other_product_id,
            price_cents=1,
            valid_from=now,
            created_at=now,
        )
    )
    test_db.execute(
        models.orders.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-000000000503",
            organization_id=other_org_id,
            branch_id=other_branch_id,
            folio="OTHER-1",
            customer_id=other_customer_id,
            channel="UBER_EATS",
            status="delivered",
            total_cents=999999,
            created_at=now,
        )
    )
    test_db.commit()

    segments = get_crm_segments_and_churn_risk(test_db, organization_id=ORGANIZATION_ID)

    customer_ids = {
        customer["id"]
        for segment in ("vips", "churn_risk", "new_customers")
        for customer in segments[segment]
    }
    assert other_customer_id not in customer_ids
    assert segments["summary"]["total_customers"] == 1
    recommendations = get_customer_upsell_recommendations(
        test_db,
        organization_id=ORGANIZATION_ID,
        current_product_ids=[sample_crm_data["product_b_id"]],
    )
    recommendation_ids = {recommendation["product_id"] for recommendation in recommendations}
    assert other_product_id not in recommendation_ids


def test_customer_recommendations_rejects_another_tenant_branch(
    client: TestClient, test_db: Session, sample_crm_data: dict[str, str]
) -> None:
    now = datetime.now(timezone.utc)
    other_org_id = "018f6f73-2d0a-74f0-8f1c-000000000511"
    other_entity_id = "018f6f73-2d0a-74f0-8f1c-000000000512"
    other_unit_id = "018f6f73-2d0a-74f0-8f1c-000000000513"
    other_branch_id = "018f6f73-2d0a-74f0-8f1c-000000000514"
    test_db.execute(
        models.organizations.insert().values(
            id=other_org_id,
            name="Another tenant",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.legal_entities.insert().values(
            id=other_entity_id,
            organization_id=other_org_id,
            name="Another legal entity",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.business_units.insert().values(
            id=other_unit_id,
            organization_id=other_org_id,
            legal_entity_id=other_entity_id,
            name="Another unit",
            code="OTHER",
            unit_type="branch",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.branches.insert().values(
            id=other_branch_id,
            organization_id=other_org_id,
            legal_entity_id=other_entity_id,
            business_unit_id=other_unit_id,
            name="Another branch",
            code="OTHER",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.commit()
    token = create_session_token({"user_id": USER_ID}, get_settings().secret_key)

    response = client.post(
        "/api/v1/admin-ai/customer-recommendations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "branch_id": other_branch_id,
            "current_product_ids": [sample_crm_data["product_a_id"]],
        },
    )

    assert response.status_code == 403


def test_generate_churn_recovery_message() -> None:
    msg = generate_churn_recovery_message(
        customer_name="Valeria",
        favorite_product_name="Maccha Pinku",
        discount_code="VUELVE10",
    )
    assert "Valeria" in msg
    assert "Maccha Pinku" in msg
    assert "VUELVE10" in msg


def test_customer_ai_endpoints(client: TestClient, sample_crm_data: dict[str, str]) -> None:
    settings = get_settings()
    token = create_session_token(
        {
            "user_id": USER_ID,
            "organization_id": ORGANIZATION_ID,
            "role": "superadmin",
            "permissions": ["admin.manage", "customers.read"],
        },
        settings.secret_key,
    )
    headers = {"Authorization": f"Bearer {token}", "X-Actor-User-Id": USER_ID}

    # 1. Recommendations endpoint
    resp_recs = client.post(
        "/api/v1/admin-ai/customer-recommendations",
        headers=headers,
        json={
            "customer_id": sample_crm_data["customer_id"],
            "current_product_ids": [sample_crm_data["product_a_id"]],
        },
    )
    assert resp_recs.status_code == 200
    assert "recommendations" in resp_recs.json()

    # 2. CRM Segments endpoint
    resp_crm = client.get(
        f"/api/v1/admin-ai/customer-crm-segments?branch_id={sample_crm_data['branch_id']}",
        headers=headers,
    )
    assert resp_crm.status_code == 200
    data = resp_crm.json()
    assert "vip_customers" in data
    assert "churn_risk_customers" in data
