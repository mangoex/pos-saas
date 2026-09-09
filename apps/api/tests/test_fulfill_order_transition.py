from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from restaurant_os import models
from restaurant_os.operations import fulfill_order, ORGANIZATION_ID, BRANCH_ID


@pytest.fixture
def test_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = TestingSession()

    now = datetime.now(timezone.utc)
    s.execute(
        models.organizations.insert().values(
            id=ORGANIZATION_ID,
            slug="test-org",
            name="Test Org",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    legal_id = str(uuid.uuid4())
    s.execute(
        models.legal_entities.insert().values(
            id=legal_id,
            organization_id=ORGANIZATION_ID,
            name="Test Legal SA",
            created_at=now,
            updated_at=now,
        )
    )
    bu_id = str(uuid.uuid4())
    s.execute(
        models.business_units.insert().values(
            id=bu_id,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=legal_id,
            name="Test BU",
            code="TBU",
            unit_type="restaurant",
            created_at=now,
            updated_at=now,
        )
    )
    s.execute(
        models.branches.insert().values(
            id=BRANCH_ID,
            organization_id=ORGANIZATION_ID,
            legal_entity_id=legal_id,
            business_unit_id=bu_id,
            code="SUC01",
            name="Sucursal Centro",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    user_id = str(uuid.uuid4())
    s.execute(
        models.users.insert().values(
            id=user_id,
            organization_id=ORGANIZATION_ID,
            email="admin@test.com",
            display_name="Admin User",
            status="active",
            is_superadmin=True,
            created_at=now,
            updated_at=now,
        )
    )
    s.commit()
    yield s, user_id
    s.close()


def test_fulfill_order_deliver_from_ready(test_session):
    s, user_id = test_session
    now = datetime.now(timezone.utc)
    order_id = str(uuid.uuid4())

    s.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            folio="ORD-001",
            channel="RAPPI",
            status="READY",
            total_cents=10000,
            currency="MXN",
            order_type="dine-in",
            version=1,
            created_at=now,
        )
    )

    line_id = str(uuid.uuid4())
    s.execute(
        models.order_lines.insert().values(
            id=line_id,
            order_id=order_id,
            product_id=str(uuid.uuid4()),
            product_name="Tacos al Pastor",
            quantity=2,
            unit_price_cents=5000,
            line_total_cents=10000,
            station="hot_kitchen",
            selected_modifiers=[],
            status="active",
            revision=1,
            family_id_snapshot="fam-1",
            family_name_snapshot="Tacos",
            family_snapshot_source="captured",
            created_at=now,
        )
    )

    task_id = str(uuid.uuid4())
    s.execute(
        models.production_tasks.insert().values(
            id=task_id,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            order_id=order_id,
            order_line_id=line_id,
            station="hot_kitchen",
            status="IN_PROGRESS",
            product_name="Tacos al Pastor",
            quantity=2,
            created_at=now,
            started_at=now,
            completed_at=None,
        )
    )
    s.commit()

    # Call fulfill_order with "deliver"
    result = fulfill_order(s, order_id, "deliver", f"key-{order_id}-deliver", user_id)
    assert result["status"] == "DELIVERED"

    # Verify order status in DB
    order_row = s.execute(select(models.orders).where(models.orders.c.id == order_id)).mappings().one()
    assert order_row["status"] == "DELIVERED"

    # Verify production task was completed and completed_at is set
    task_row = s.execute(select(models.production_tasks).where(models.production_tasks.c.id == task_id)).mappings().one()
    assert task_row["status"] == "COMPLETED"
    assert task_row["completed_at"] is not None


def test_fulfill_order_deliver_from_accepted_and_delivery_type(test_session):
    s, user_id = test_session
    now = datetime.now(timezone.utc)
    order_id = str(uuid.uuid4())

    s.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            folio="ORD-002",
            channel="RAPPI",
            status="ACCEPTED",
            total_cents=15000,
            currency="MXN",
            order_type="delivery",
            version=1,
            created_at=now,
        )
    )
    s.commit()

    result = fulfill_order(s, order_id, "deliver", f"key-{order_id}-deliver", user_id)
    assert result["status"] == "DELIVERED"

    # Idempotent re-call returns same response
    re_result = fulfill_order(s, order_id, "deliver", f"key-{order_id}-deliver", user_id)
    assert re_result["status"] == "DELIVERED"


def test_fulfill_order_close(test_session):
    s, user_id = test_session
    now = datetime.now(timezone.utc)
    order_id = str(uuid.uuid4())

    s.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            folio="ORD-003",
            channel="RAPPI",
            status="READY",
            total_cents=20000,
            currency="MXN",
            order_type="takeout",
            version=1,
            created_at=now,
        )
    )
    s.commit()

    result = fulfill_order(s, order_id, "close", f"key-{order_id}-close", user_id)
    assert result["status"] == "CLOSED"

    order_row = s.execute(select(models.orders).where(models.orders.c.id == order_id)).mappings().one()
    assert order_row["status"] == "CLOSED"


def test_fulfill_order_deliver_from_draft(test_session):
    s, user_id = test_session
    now = datetime.now(timezone.utc)
    order_id = str(uuid.uuid4())

    s.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            folio="ORD-004",
            channel="RAPPI",
            status="DRAFT",
            total_cents=12000,
            currency="MXN",
            order_type="dine-in",
            version=1,
            created_at=now,
        )
    )
    s.commit()

    result = fulfill_order(s, order_id, "deliver", f"key-{order_id}-deliver", user_id)
    assert result["status"] == "DELIVERED"

    order_row = s.execute(select(models.orders).where(models.orders.c.id == order_id)).mappings().one()
    assert order_row["status"] == "DELIVERED"
