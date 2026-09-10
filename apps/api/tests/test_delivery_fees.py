# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-delivery-fees-v1
from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    ORGANIZATION_ID,
    BusinessError,
    accept_public_order_intent,
    create_local_order,
    create_public_order_intent,
    update_branch,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_platform_api import _seed

ADMIN_USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000006"
BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
BURGER_ID = "018f6f73-2d0a-74f0-8f1c-000000000111"
PUBLIC_KEY = "pk_test_delivery_fees"


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


def _configure_branch_delivery(
    session: Any,
    *,
    enabled: bool = True,
    tiers: list[dict[str, Any]] | None = None,
    free_min_cents: int | None = None,
) -> None:
    if tiers is None:
        tiers = [
            {"id": "tier_1", "name": "Zona Corta", "fee_cents": 2000, "is_default_web": True},
            {"id": "tier_2", "name": "Zona Media", "fee_cents": 3000, "is_default_web": False},
            {"id": "tier_3", "name": "Zona Lejana", "fee_cents": 4000, "is_default_web": False},
            {"id": "tier_free", "name": "Gratis", "fee_cents": 0, "is_default_web": False},
        ]
    session.execute(
        sa.update(models.branches)
        .where(models.branches.c.id == BRANCH_ID)
        .values(
            delivery_fee_enabled=enabled,
            delivery_tiers=tiers,
            free_delivery_min_cents=free_min_cents,
        )
    )
    session.commit()


def _delivery_payload(*, quantity: int = 1, delivery_fee_cents: int = 0) -> dict[str, Any]:
    return {
        "customer_name": "Juan Perez",
        "customer_phone": "5512345678",
        "order_type": "delivery",
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
        "delivery_address": {"street": "Av Insurgentes 123", "neighborhood": "Centro"},
        "delivery_fee_cents": delivery_fee_cents,
    }


def test_branch_delivery_fields_crud(session: Any) -> None:
    # Update branch delivery settings
    tiers = [
        {"id": "corta", "name": "Corta", "fee_cents": 2500, "is_default_web": False},
        {"id": "gratis", "name": "Gratis", "fee_cents": 0, "is_default_web": True},
    ]
    updated = update_branch(
        session,
        BRANCH_ID,
        actor_user_id=ADMIN_USER_ID,
        extra_payload={
            "delivery_fee_enabled": True,
            "delivery_tiers": tiers,
            "free_delivery_min_cents": 35000,
        },
    )
    assert updated["delivery_fee_enabled"] is True
    assert updated["delivery_tiers"] == tiers
    assert updated["free_delivery_min_cents"] == 35000


def test_public_order_applies_default_delivery_tier(session: Any) -> None:
    _enable_public_key(session)
    _configure_branch_delivery(session, enabled=True)

    # Burger price is 9500 ($95.00 MXN)
    # Default tier is Zona Corta ($20.00 = 2000 cents)
    intent, created = create_public_order_intent(
        session,
        PUBLIC_KEY,
        _delivery_payload(quantity=1),
        "intent-delivery-default-001",
    )
    assert created is True
    assert intent["delivery_fee_cents"] == 2000
    assert intent["total_cents"] == 9500 + 2000  # 11500


def test_public_order_applies_free_delivery_threshold(session: Any) -> None:
    _enable_public_key(session)
    # Free delivery threshold at 20000 ($200.00 MXN)
    _configure_branch_delivery(session, enabled=True, free_min_cents=20000)

    # 1 burger = 9500 (< 20000) -> delivery fee 2000 applies
    intent1, _ = create_public_order_intent(
        session,
        PUBLIC_KEY,
        _delivery_payload(quantity=1),
        "intent-delivery-threshold-001",
    )
    assert intent1["delivery_fee_cents"] == 2000
    assert intent1["total_cents"] == 9500 + 2000

    # 3 burgers = 28500 (>= 20000) -> free delivery applies!
    intent2, _ = create_public_order_intent(
        session,
        PUBLIC_KEY,
        _delivery_payload(quantity=3),
        "intent-delivery-threshold-002",
    )
    assert intent2["delivery_fee_cents"] == 0
    assert intent2["total_cents"] == 28500


def test_public_order_free_default_tier(session: Any) -> None:
    _enable_public_key(session)
    # Configure gratis as default web tier
    tiers = [
        {"id": "t1", "name": "Zona 1", "fee_cents": 2000, "is_default_web": False},
        {"id": "t_free", "name": "Sin costo web", "fee_cents": 0, "is_default_web": True},
    ]
    _configure_branch_delivery(session, enabled=True, tiers=tiers)

    intent, _ = create_public_order_intent(
        session,
        PUBLIC_KEY,
        _delivery_payload(quantity=1),
        "intent-delivery-free-default-001",
    )
    assert intent["delivery_fee_cents"] == 0
    assert intent["total_cents"] == 9500


def test_accept_public_order_preserves_delivery_fee(session: Any) -> None:
    _enable_public_key(session)
    _configure_branch_delivery(session, enabled=True)

    intent, _ = create_public_order_intent(
        session,
        PUBLIC_KEY,
        _delivery_payload(quantity=1),
        "intent-delivery-accept-001",
    )
    intent_id = session.scalar(
        sa.select(models.public_order_intents.c.id).where(
            models.public_order_intents.c.public_reference == intent["public_reference"]
        )
    )

    accepted, created = accept_public_order_intent(
        session,
        str(intent_id),
        1,
        "accept-delivery-001",
        ADMIN_USER_ID,
    )
    assert created is True
    assert accepted["total_cents"] == 11500
    assert accepted["delivery_fee_cents"] == 2000

    # Verify persisted in database
    db_order = session.execute(
        sa.select(models.orders).where(models.orders.c.id == accepted["id"])
    ).mappings().first()
    assert db_order["delivery_fee_cents"] == 2000
    assert db_order["total_cents"] == 11500


def test_create_local_order_with_delivery_fee(session: Any) -> None:
    from restaurant_os.operations import open_cash_shift

    open_cash_shift(session, 10000, branch_id=BRANCH_ID, actor_user_id=ADMIN_USER_ID)

    lines = [
        {
            "product_id": BURGER_ID,
            "quantity": 1,
            "notes": None,
            "modifiers": [],
            "comment_preset_ids": [],
            "ingredient_extras": [],
        }
    ]
    order = create_local_order(
        session,
        lines=lines,
        order_type="delivery",
        branch_id=BRANCH_ID,
        actor_user_id=ADMIN_USER_ID,
        delivery_address_id=None,
        payment_method_intent="cash",
        delivery_fee_cents=3000,
        idempotency_key="local-delivery-fee-001",
    )
    assert order["delivery_fee_cents"] == 3000
    assert order["total_cents"] == 9500 + 3000  # 12500

    # Non-delivery orders must reject non-zero delivery fee
    with pytest.raises(BusinessError) as exc_info:
        create_local_order(
            session,
            lines=lines,
            order_type="dine-in",
            branch_id=BRANCH_ID,
            actor_user_id=ADMIN_USER_ID,
            delivery_fee_cents=2000,
            idempotency_key="local-delivery-fee-invalid-001",
        )
    assert exc_info.value.code == "delivery_fee_not_allowed"
