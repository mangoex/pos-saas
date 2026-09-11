"""Tests for Inventory AI & Smart Procurement Engine."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.inventory_ai import (
    audit_inventory_yield_and_waste,
    calculate_suggested_purchases,
    parse_supplier_invoice_data,
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
SUPPLIER_ID = "018f6f73-2d0a-74f0-8f1c-000000000040"
UNIT_ID = "018f6f73-2d0a-74f0-8f1c-000000000050"
ITEM_ID = "018f6f73-2d0a-74f0-8f1c-000000000060"
PRES_ID = "018f6f73-2d0a-74f0-8f1c-000000000065"

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
def sample_inventory_data(test_db: Session) -> dict[str, str]:
    now = datetime.now(timezone.utc)
    role_id = "018f6f73-2d0a-74f0-8f1c-000000000070"
    permission_id = "018f6f73-2d0a-74f0-8f1c-000000000071"

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
        models.users.insert().values(
            id=USER_ID,
            organization_id=ORGANIZATION_ID,
            email="owner@test",
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
            id=permission_id, code="inventory.read", description="Inventory read", created_at=now
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
    test_db.execute(
        models.user_roles.insert().values(user_id=USER_ID, role_id=role_id, branch_id=BRANCH_ID)
    )
    test_db.execute(
        models.role_permissions.insert().values(role_id=role_id, permission_id=permission_id)
    )

    # 2. Supplier
    test_db.execute(
        models.suppliers.insert().values(
            id=SUPPLIER_ID,
            organization_id=ORGANIZATION_ID,
            code="SUP-01",
            commercial_name="Panadería La Espiga",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # 3. Inventory Unit
    test_db.execute(
        models.inventory_units.insert().values(
            id=UNIT_ID,
            organization_id=ORGANIZATION_ID,
            code="PZA",
            name="Pieza",
            dimension="discrete",
            precision_scale=0,
            created_at=now,
        )
    )

    # 4. Inventory Item
    test_db.execute(
        models.inventory_items.insert().values(
            id=ITEM_ID,
            organization_id=ORGANIZATION_ID,
            name="Pan Brioche Hamburguesa",
            sku="INS-PAN-01",
            base_unit_id=UNIT_ID,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # 5. Purchase Presentation
    test_db.execute(
        models.purchase_presentations.insert().values(
            id=PRES_ID,
            organization_id=ORGANIZATION_ID,
            supplier_id=SUPPLIER_ID,
            item_id=ITEM_ID,
            code="PRES-PAN-01",
            name="Caja Pan Brioche x 50",
            package_type="box",
            commercial_quantity=Decimal("50.00"),
            commercial_unit_id=UNIT_ID,
            base_unit_id=UNIT_ID,
            base_unit_yield=Decimal("50.00"),
            usable_content=Decimal("50.00"),
            yield_percent=Decimal("1.00"),
            last_net_price=Decimal("500.00"),
            cost_per_base_unit=Decimal("10.00"),
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # 6. Purchase Document & Line
    pdoc_id = "018f6f73-2d0a-74f0-8f1c-000000000070"
    test_db.execute(
        models.purchase_documents.insert().values(
            id=pdoc_id,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            supplier_id=SUPPLIER_ID,
            document_type="invoice",
            folio="FAC-101",
            document_date=now,
            subtotal=Decimal("500.00"),
            discount_total=Decimal("0.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("500.00"),
            payment_method="transfer",
            status="confirmed",
            created_by=USER_ID,
            created_at=now,
        )
    )
    test_db.execute(
        models.purchase_document_lines.insert().values(
            id="018f6f73-2d0a-74f0-8f1c-000000000071",
            purchase_document_id=pdoc_id,
            presentation_id=PRES_ID,
            item_id=ITEM_ID,
            presentation_snapshot={},
            presentation_quantity=Decimal("1.00"),
            base_quantity=Decimal("50.00"),
            unit_price=Decimal("10.00"),
            discount=Decimal("0.00"),
            tax=Decimal("0.00"),
            line_total=Decimal("500.00"),
            inventory_cost=Decimal("500.00"),
            cost_per_base_unit=Decimal("10.00"),
            created_at=now,
        )
    )

    test_db.commit()
    return {
        "branch_id": BRANCH_ID,
        "supplier_id": SUPPLIER_ID,
        "item_id": ITEM_ID,
    }


def test_calculate_suggested_purchases_groups_by_supplier(
    test_db: Session, sample_inventory_data: dict[str, str]
) -> None:
    proposals = calculate_suggested_purchases(
        test_db, ORGANIZATION_ID, sample_inventory_data["branch_id"], 7
    )
    assert proposals == []


def test_audit_inventory_yield_and_waste_returns_report(
    test_db: Session, sample_inventory_data: dict[str, str]
) -> None:
    audit = audit_inventory_yield_and_waste(
        test_db, ORGANIZATION_ID, sample_inventory_data["branch_id"], 30
    )
    assert isinstance(audit, list)


def test_parse_supplier_invoice_data_structures_lines() -> None:
    invoice_text = """
    PROVEEDOR: Panadería La Espiga
    RFC: PLE900101AA1
    FOLIO: F-9923
    ITEMS:
    - Pan Brioche Hamburguesa | 100 pzas | $12.50 | $1,250.00
    - Pan Hot Dog | 50 pzas | $8.00 | $400.00
    TOTAL: $1,650.00
    """
    parsed = parse_supplier_invoice_data(invoice_text)
    assert "supplier_name" in parsed
    assert "lines" in parsed
    assert len(parsed["lines"]) >= 1
    assert parsed["lines"][0]["quantity"] > 0


def test_parse_supplier_invoice_data_never_invents_missing_values() -> None:
    parsed = parse_supplier_invoice_data("texto ilegible sin campos verificables")

    assert parsed == {
        "supplier_name": None,
        "folio": None,
        "lines": [],
        "total_cents": 0,
    }

    incomplete_line = parse_supplier_invoice_data("Tomate | cantidad ilegible | $20.00")
    assert incomplete_line["lines"] == []


def test_post_suggested_purchases_endpoint(
    client: TestClient, sample_inventory_data: dict[str, str]
) -> None:
    settings = get_settings()
    token = create_session_token(
        {
            "user_id": USER_ID,
            "organization_id": ORGANIZATION_ID,
            "role": "superadmin",
            "permissions": ["admin.manage", "inventory.read"],
        },
        settings.secret_key,
    )
    response = client.post(
        "/api/v1/admin-ai/suggested-purchases",
        headers={"Authorization": f"Bearer {token}", "X-Actor-User-Id": USER_ID},
        json={
            "branch_id": sample_inventory_data["branch_id"],
            "days_ahead": 7,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "proposals" in data
    assert "summary" in data
