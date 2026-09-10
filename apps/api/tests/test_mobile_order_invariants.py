# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-mobile-invariants-v1
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    BusinessError,
    accept_public_order_intent,
    create_public_order_intent,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_platform_api import _seed

ADMIN_USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000006"
BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
BURGER_ID = "018f6f73-2d0a-74f0-8f1c-000000000111"
BEEF_ID = "018f6f73-2d0a-74f0-8f1c-000000000311"
PUBLIC_KEY = "pk_test_mobile_invariants"


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
            organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
            branch_id=BRANCH_ID,
            status="active",
        )
    )
    session.commit()


def _payload(*, phone: str, quantity: int = 1, name: str = "Cliente Web") -> dict[str, Any]:
    return {
        "customer_name": name,
        "customer_phone": phone,
        "order_type": "takeout",
        "lines": [
            {
                "product_id": BURGER_ID,
                "quantity": quantity,
                "notes": None,
                "modifiers": [],
                "comment_preset_ids": [],
                "ingredient_extras": [],
            }
        ],
        "order_notes": None,
        "delivery_address": None,
    }


def test_public_order_validates_customer_phone(session: Any) -> None:
    _enable_public_key(session)
    with pytest.raises(BusinessError) as exc_info:
        create_public_order_intent(
            session,
            PUBLIC_KEY,
            _payload(phone="12345", name="Juan Perez"),
            "mobile-phone-invalid-001",
        )
    assert exc_info.value.code == "public_order_schema_invalid"

    intent, created = create_public_order_intent(
        session,
        PUBLIC_KEY,
        _payload(phone="5512345678", name="Juan Perez"),
        "mobile-phone-valid-001",
    )
    assert created is True
    assert intent["status"] == "PENDING_REVIEW"
    assert intent["total_cents"] == 9500
    assert session.scalar(sa.select(sa.func.count()).select_from(models.orders)) == 0


def test_public_order_does_not_create_ghost_open_shift(session: Any) -> None:
    _enable_public_key(session)
    initial_open_shifts = session.execute(
        sa.select(models.cash_shifts).where(
            models.cash_shifts.c.branch_id == BRANCH_ID,
            models.cash_shifts.c.status == "OPEN",
        )
    ).all()
    assert len(initial_open_shifts) == 0

    intent, created = create_public_order_intent(
        session,
        PUBLIC_KEY,
        _payload(phone="5588776655", quantity=2),
        "mobile-no-shift-001",
    )

    open_shifts_after = session.execute(
        sa.select(models.cash_shifts).where(
            models.cash_shifts.c.branch_id == BRANCH_ID,
            models.cash_shifts.c.status == "OPEN",
        )
    ).all()
    assert created is True
    assert len(open_shifts_after) == 0
    assert intent["total_cents"] == 19000
    assert session.scalar(sa.select(sa.func.count()).select_from(models.orders)) == 0


def test_accept_public_intent_reserves_inventory_and_creates_tasks(session: Any) -> None:
    _enable_public_key(session)
    captured, _ = create_public_order_intent(
        session,
        PUBLIC_KEY,
        _payload(phone="5544332211", quantity=2, name="Maria Gomez"),
        "mobile-accept-create-001",
    )
    intent_id = session.scalar(
        sa.select(models.public_order_intents.c.id).where(
            models.public_order_intents.c.public_reference == captured["public_reference"]
        )
    )
    assert intent_id

    pre_reservations = session.execute(
        sa.select(models.inventory_movements).where(
            models.inventory_movements.c.movement_type == "SALE_RESERVATION",
        )
    ).all()
    assert len(pre_reservations) == 0

    accepted, created = accept_public_order_intent(
        session,
        str(intent_id),
        1,
        "mobile-accept-command-001",
        ADMIN_USER_ID,
    )
    assert created is True
    assert accepted["status"] == "ACCEPTED"
    assert accepted["cash_shift_id"] is None
    order_id = accepted["id"]

    tasks = session.execute(
        sa.select(models.production_tasks).where(models.production_tasks.c.order_id == order_id)
    ).mappings().all()
    assert len(tasks) == 1
    assert tasks[0]["status"] == "PENDING"
    assert tasks[0]["quantity"] == 2

    reservations = session.execute(
        sa.select(models.inventory_movements).where(
            models.inventory_movements.c.document_id == order_id,
            models.inventory_movements.c.movement_type == "SALE_RESERVATION",
        )
    ).mappings().all()
    assert len(reservations) >= 1
    assert any(
        res["item_id"] == BEEF_ID
        and Decimal(str(res["quantity_delta"])) == Decimal("-240.000000")
        for res in reservations
    )


def test_public_order_auto_heals_missing_branch_warehouse(session: Any) -> None:
    _enable_public_key(session)
    # Delete existing warehouses for this branch to simulate a branch without configured warehouse
    session.execute(
        sa.delete(models.warehouses).where(models.warehouses.c.branch_id == BRANCH_ID)
    )
    session.commit()

    # Verify no warehouses exist
    wh_count = session.scalar(
        sa.select(sa.func.count()).where(models.warehouses.c.branch_id == BRANCH_ID)
    )
    assert wh_count == 0

    # Submit order intent - must auto-heal instead of throwing NoResultFound / database_unavailable
    intent, created = create_public_order_intent(
        session,
        PUBLIC_KEY,
        _payload(phone="5577665544", quantity=1, name="Auto Heal"),
        "mobile-auto-heal-warehouse-001",
    )
    assert created is True
    assert intent["status"] == "PENDING_REVIEW"

    # Verify warehouse was auto-created
    wh = session.execute(
        sa.select(models.warehouses).where(
            models.warehouses.c.branch_id == BRANCH_ID,
            models.warehouses.c.status == "active",
        )
    ).mappings().first()
    assert wh is not None
    assert "Almacen" in wh["name"]
