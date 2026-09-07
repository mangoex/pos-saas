"""Tests for Executive AI Copilot and Business Insights Engine."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.executive_ai import (
    ExecutiveAiProviderOptions,
    generate_executive_insights,
    query_branches_comparison,
    query_sales_overview,
    query_top_products_profitability,
)
from restaurant_os.main import create_app
from restaurant_os.operations import BRANCH_ID, ORGANIZATION_ID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

UTC = timezone.utc
USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
LEGAL_ENTITY_ID = "018f6f73-2d0a-74f0-8f1c-000000000010"
BUSINESS_UNIT_ID = "018f6f73-2d0a-74f0-8f1c-000000000020"
CATEGORY_ID = "018f6f73-2d0a-74f0-8f1c-000000000030"

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
def sample_executive_data(test_db: Session) -> dict[str, str]:
    now = datetime.now(UTC)

    # 1. Organization
    org_row = (
        test_db.execute(
            models.organizations.select().where(models.organizations.c.id == ORGANIZATION_ID)
        )
        .mappings()
        .one_or_none()
    )
    if not org_row:
        test_db.execute(
            models.organizations.insert().values(
                id=ORGANIZATION_ID,
                name="Kiwi Corporativo",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )

    # 2. Legal Entity
    le_row = (
        test_db.execute(
            models.legal_entities.select().where(models.legal_entities.c.id == LEGAL_ENTITY_ID)
        )
        .mappings()
        .one_or_none()
    )
    if not le_row:
        test_db.execute(
            models.legal_entities.insert().values(
                id=LEGAL_ENTITY_ID,
                organization_id=ORGANIZATION_ID,
                name="Kiwi Operaciones SA de CV",
                tax_id="KOP200101AA1",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )

    # 3. Business Unit
    bu_row = (
        test_db.execute(
            models.business_units.select().where(models.business_units.c.id == BUSINESS_UNIT_ID)
        )
        .mappings()
        .one_or_none()
    )
    if not bu_row:
        test_db.execute(
            models.business_units.insert().values(
                id=BUSINESS_UNIT_ID,
                organization_id=ORGANIZATION_ID,
                legal_entity_id=LEGAL_ENTITY_ID,
                name="Unidad Operativa",
                code="UO-PRIN",
                unit_type="branch",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )

    # 4. Branch
    branch_row = (
        test_db.execute(models.branches.select().where(models.branches.c.id == BRANCH_ID))
        .mappings()
        .one_or_none()
    )

    if not branch_row:
        test_db.execute(
            models.branches.insert().values(
                id=BRANCH_ID,
                organization_id=ORGANIZATION_ID,
                legal_entity_id=LEGAL_ENTITY_ID,
                business_unit_id=BUSINESS_UNIT_ID,
                name="Sucursal Principal",
                code="PRIN",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )

    # 5. Product Category
    role_id = "018f6f73-2d0a-74f0-8f1c-000000000040"
    permission_id = "018f6f73-2d0a-74f0-8f1c-000000000041"
    test_db.execute(
        models.users.insert().values(
            id=USER_ID,
            organization_id=ORGANIZATION_ID,
            email="owner@kiwi.test",
            display_name="Owner",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    test_db.execute(
        models.roles.insert().values(
            id=role_id,
            organization_id=ORGANIZATION_ID,
            name="Owner",
            scope="organization",
            created_at=now,
        )
    )
    test_db.execute(
        models.permissions.insert().values(
            id=permission_id,
            code="analytics.read",
            description="Analytics",
            created_at=now,
        )
    )
    test_db.execute(
        models.user_roles.insert().values(user_id=USER_ID, role_id=role_id, branch_id=BRANCH_ID)
    )
    test_db.execute(
        models.role_permissions.insert().values(role_id=role_id, permission_id=permission_id)
    )

    # 6. Product Category
    cat_row = (
        test_db.execute(
            models.product_categories.select().where(models.product_categories.c.id == CATEGORY_ID)
        )
        .mappings()
        .one_or_none()
    )
    if not cat_row:
        test_db.execute(
            models.product_categories.insert().values(
                id=CATEGORY_ID,
                organization_id=ORGANIZATION_ID,
                name="Alimentos",
                display_order=1,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )

    # 6. Products
    prod_a_id = "018f6f73-2d0a-74f0-8f1c-000000000881"
    prod_b_id = "018f6f73-2d0a-74f0-8f1c-000000000882"

    for pid, name, sku in [
        (prod_a_id, "Hamburguesa Clásica", "HAMB-001"),
        (prod_b_id, "Té Verde Matcha", "TE-002"),
    ]:
        existing = (
            test_db.execute(models.products.select().where(models.products.c.id == pid))
            .mappings()
            .one_or_none()
        )
        if not existing:
            test_db.execute(
                models.products.insert().values(
                    id=pid,
                    organization_id=ORGANIZATION_ID,
                    category_id=CATEGORY_ID,
                    name=name,
                    sku=sku,
                    station="kitchen",
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )

    # 7. Orders & Line items
    order_1_id = "018f6f73-2d0a-74f0-8f1c-000000000891"
    order_2_id = "018f6f73-2d0a-74f0-8f1c-000000000892"

    for oid, folio, total, channel in [
        (order_1_id, "ORD-EX-001", 15000, "RAPPI"),
        (order_2_id, "ORD-EX-002", 21000, "UBER_EATS"),
    ]:
        existing = (
            test_db.execute(models.orders.select().where(models.orders.c.id == oid))
            .mappings()
            .one_or_none()
        )
        if not existing:
            test_db.execute(
                models.orders.insert().values(
                    id=oid,
                    organization_id=ORGANIZATION_ID,
                    branch_id=BRANCH_ID,
                    folio=folio,
                    channel=channel,
                    status="COMPLETED",
                    total_cents=total,
                    currency="MXN",
                    order_type="delivery",
                    version=1,
                    created_at=now,
                )
            )
            test_db.execute(
                models.order_lines.insert().values(
                    id=f"{oid}-L1",
                    order_id=oid,
                    product_id=prod_a_id,
                    product_name="Hamburguesa Clásica",
                    quantity=1,
                    unit_price_cents=15000,
                    line_total_cents=15000,
                    station="kitchen",
                    status="active",
                    family_id_snapshot=CATEGORY_ID,
                    family_name_snapshot="Alimentos",
                    family_snapshot_source="captured",
                    created_at=now,
                )
            )

            snapshot_id = f"snapshot-{oid}"
            test_db.execute(
                models.sales_operation_snapshots.insert().values(
                    id=snapshot_id,
                    organization_id=ORGANIZATION_ID,
                    branch_id=BRANCH_ID,
                    payment_id=f"payment-{oid}",
                    order_id=oid,
                    cash_shift_id=f"shift-{oid}",
                    register_code_snapshot="CAJA-01",
                    folio_snapshot=folio,
                    service_type_snapshot="delivery",
                    currency="MXN",
                    gross_cents=total,
                    net_cents=total,
                    quality_status="captured",
                    confirmed_at=now,
                    created_at=now,
                )
            )
            test_db.execute(
                models.sales_operation_line_snapshots.insert().values(
                    id=f"snapshot-line-{oid}",
                    sales_operation_snapshot_id=snapshot_id,
                    payment_id=f"payment-{oid}",
                    order_line_id=f"{oid}-L1",
                    product_id=prod_a_id,
                    product_name_snapshot="Hamburguesa Clásica",
                    family_id_snapshot=CATEGORY_ID,
                    family_name_snapshot="Alimentos",
                    family_snapshot_source="captured",
                    quantity=1,
                    gross_cents=total,
                    net_cents=total,
                )
            )

    test_db.commit()
    return {
        "branch_id": BRANCH_ID,
        "product_a": prod_a_id,
        "product_b": prod_b_id,
        "order_1": order_1_id,
        "order_2": order_2_id,
    }


def test_query_sales_overview_aggregates_channels_and_money(
    test_db: Session, sample_executive_data: dict[str, str]
) -> None:
    overview = query_sales_overview(
        test_db, ORGANIZATION_ID, branch_id=sample_executive_data["branch_id"]
    )
    assert overview["total_orders"] >= 2
    assert overview["total_sales_cents"] >= 36000
    assert "channels" in overview
    assert "RAPPI" in overview["channels"] or "UBER_EATS" in overview["channels"]


def test_query_top_products_profitability_returns_ranking(
    test_db: Session, sample_executive_data: dict[str, str]
) -> None:
    ranking = query_top_products_profitability(test_db, ORGANIZATION_ID, limit=5)
    assert isinstance(ranking, list)
    if ranking:
        item = ranking[0]
        assert "product_name" in item
        assert "units_sold" in item
        assert "revenue_cents" in item
        assert item["cost_status"] == "NOT_AVAILABLE"
        assert isinstance(item["revenue_cents"], int)


def test_query_branches_comparison_lists_active_branches(
    test_db: Session, sample_executive_data: dict[str, str]
) -> None:
    branches_comp = query_branches_comparison(
        test_db, ORGANIZATION_ID, sample_executive_data["branch_id"]
    )
    assert isinstance(branches_comp, list)
    assert len(branches_comp) >= 1
    branch_item = next(
        (b for b in branches_comp if b["branch_id"] == sample_executive_data["branch_id"]), None
    )
    assert branch_item is not None
    assert branch_item["total_orders"] >= 2


def test_generate_executive_insights_deterministic_synthesis(
    test_db: Session, sample_executive_data: dict[str, str]
) -> None:
    insights = generate_executive_insights(
        test_db,
        ORGANIZATION_ID,
        prompt="¿Cuáles son las ventas de la sucursal principal?",
        branch_id=sample_executive_data["branch_id"],
        provider_options=None,
    )
    assert "answer" in insights
    assert "data_points" in insights
    assert "sources" in insights
    assert isinstance(insights["data_points"], list)
    assert len(insights["sources"]) > 0


def test_post_executive_ai_insights_endpoint(
    client: TestClient, sample_executive_data: dict[str, str]
) -> None:
    settings = get_settings()
    token = create_session_token(
        {
            "user_id": USER_ID,
            "organization_id": ORGANIZATION_ID,
            "role": "superadmin",
            "permissions": ["admin.manage", "analytics.read"],
        },
        settings.secret_key,
    )
    response = client.post(
        "/api/v1/admin-ai/executive-insights",
        headers={"Authorization": f"Bearer {token}", "X-Actor-User-Id": USER_ID},
        json={
            "prompt": "¿Cuáles son los productos con mejor margen de ganancia?",
            "branch_id": sample_executive_data["branch_id"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "data_points" in data
    assert "sources" in data


def test_external_provider_receives_only_authorized_snapshot_context(
    test_db: Session, sample_executive_data: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_provider(_options, _prompt, sales, products, branches):
        captured.update({"sales": sales, "products": products, "branches": branches})
        return {"answer": "ok", "data_points": [], "sources": [], "suggested_actions": []}

    monkeypatch.setattr("restaurant_os.executive_ai._call_external_provider", fake_provider)
    generate_executive_insights(
        test_db,
        ORGANIZATION_ID,
        prompt="ventas",
        branch_id=sample_executive_data["branch_id"],
        provider_options=ExecutiveAiProviderOptions(
            api_key="test", model="test", base_url="https://example.invalid"
        ),
    )
    assert captured["sales"]
    assert captured["branches"] == [
        {**captured["branches"][0], "branch_id": sample_executive_data["branch_id"]}
    ]
    assert all(item["cost_status"] == "NOT_AVAILABLE" for item in captured["products"])
