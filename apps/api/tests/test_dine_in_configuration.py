# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-dine-in-configuration-v1
from __future__ import annotations

from typing import Any
import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    ORGANIZATION_ID,
    BusinessError,
    create_public_order_intent,
    list_public_branches,
    update_branch,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_platform_api import _seed

ADMIN_USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000006"
BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
BURGER_ID = "018f6f73-2d0a-74f0-8f1c-000000000111"
PUBLIC_KEY = "pk_test_dine_in_config"


@pytest.fixture()
def session() -> Any:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as database_session:
        _seed(database_session)
        yield database_session


def _enable_public_key(session: Any) -> None:
    session.execute(
        models.public_order_keys.insert().values(
            public_key=PUBLIC_KEY,
            organization_id=ORGANIZATION_ID,
            branch_id=BRANCH_ID,
            status="active",
        )
    )
    session.commit()


def test_branch_dine_in_default_is_true(session: Any) -> None:
    row = (
        session.execute(
            sa.select(models.branches.c.dine_in_enabled).where(models.branches.c.id == BRANCH_ID)
        )
        .mappings()
        .one()
    )
    assert row["dine_in_enabled"] is True


def test_update_branch_dine_in_toggle(session: Any) -> None:
    # Disable dine-in
    updated = update_branch(
        session,
        BRANCH_ID,
        actor_user_id=ADMIN_USER_ID,
        dine_in_enabled=False,
    )
    assert updated["dine_in_enabled"] is False

    # Check via DB
    row = (
        session.execute(
            sa.select(models.branches.c.dine_in_enabled).where(models.branches.c.id == BRANCH_ID)
        )
        .mappings()
        .one()
    )
    assert row["dine_in_enabled"] is False

    # Check via list_public_branches
    branches = list_public_branches(session, organization_id=ORGANIZATION_ID)
    matching = next(b for b in branches if b["id"] == BRANCH_ID)
    assert matching["dine_in_enabled"] is False

    # Re-enable dine-in
    updated2 = update_branch(
        session,
        BRANCH_ID,
        actor_user_id=ADMIN_USER_ID,
        dine_in_enabled=True,
    )
    assert updated2["dine_in_enabled"] is True


def test_public_order_intent_blocks_dine_in_when_disabled(session: Any) -> None:
    _enable_public_key(session)
    update_branch(
        session,
        BRANCH_ID,
        actor_user_id=ADMIN_USER_ID,
        dine_in_enabled=False,
    )

    # Attempt dine-in order
    payload = {
        "customer_name": "Ana Lopez",
        "customer_phone": "6671234567",
        "order_type": "dine-in",
        "table_number": "5",
        "lines": [{"product_id": BURGER_ID, "quantity": 1}],
    }
    with pytest.raises(BusinessError) as exc:
        create_public_order_intent(session, PUBLIC_KEY, payload, "idemp-dine-in-001")
    assert exc.value.code == "dine_in_disabled"

    # Takeaway order should succeed even when dine-in is disabled
    takeaway_payload = {
        "customer_name": "Ana Lopez",
        "customer_phone": "6671234567",
        "order_type": "takeout",
        "lines": [{"product_id": BURGER_ID, "quantity": 1}],
        "order_notes": "📅 Recoger: Hoy a las 15:30",
    }
    result, created = create_public_order_intent(
        session, PUBLIC_KEY, takeaway_payload, "idemp-takeout-002"
    )
    assert created is True
    assert result["status"] == "PENDING_REVIEW"

    # Verify intent record in database has the pickup schedule note
    intent = (
        session.execute(
            sa.select(models.public_order_intents).where(
                models.public_order_intents.c.public_reference == result["public_reference"]
            )
        )
        .mappings()
        .one()
    )
    assert intent["order_notes"] == "📅 Recoger: Hoy a las 15:30"
