# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-coupons-discounts-v1
from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    ORGANIZATION_ID,
    BusinessError,
    accept_public_order_intent,
    create_branch,
    create_public_order_intent,
    update_branch,
    validate_branch_coupon,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_platform_api import _seed

ADMIN_USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000006"
BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
BURGER_ID = "018f6f73-2d0a-74f0-8f1c-000000000111"
PUBLIC_KEY = "pk_test_coupons"


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


def _order_payload(*, quantity: int = 1, coupon_code: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "customer_name": "Maria Lopez",
        "customer_phone": "5512345678",
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
    }
    if coupon_code:
        payload["coupon_code"] = coupon_code
    return payload


def test_create_branch_has_default_coupon(session: Any) -> None:
    branch = create_branch(
        session=session,
        name="Sucursal Norte",
        code="NORTE11",
        actor_user_id=ADMIN_USER_ID,
    )
    branch_row = session.execute(
        sa.select(models.branches).where(models.branches.c.id == branch["id"])
    ).mappings().first()
    assert branch_row is not None
    assert branch_row["coupons"] == [
        {"code": "MIMENU-GRACIAS10", "discount_percentage": 10, "is_active": True, "show_in_checkout": True}
    ]


def test_update_branch_coupons(session: Any) -> None:
    new_coupons = [
        {"code": "SUMMER20", "discount_percentage": 20, "is_active": True, "show_in_checkout": True},
        {"code": "VIP50", "discount_percentage": 50, "is_active": False, "show_in_checkout": False},
    ]
    update_branch(
        session=session,
        branch_id=BRANCH_ID,
        coupons=new_coupons,
        actor_user_id=ADMIN_USER_ID,
    )
    branch_row = session.execute(
        sa.select(models.branches).where(models.branches.c.id == BRANCH_ID)
    ).mappings().first()
    assert branch_row is not None
    assert branch_row["coupons"] == [
        {"code": "SUMMER20", "discount_percentage": 20, "is_active": True, "show_in_checkout": True},
        {"code": "VIP50", "discount_percentage": 50, "is_active": False, "show_in_checkout": False},
    ]


def test_update_branch_coupons_can_be_cleared_to_empty(session: Any) -> None:
    branch = create_branch(
        session=session,
        name="Sucursal Sur",
        code="SUR22",
        actor_user_id=ADMIN_USER_ID,
    )
    update_branch(
        session=session,
        branch_id=branch["id"],
        coupons=[],
        actor_user_id=ADMIN_USER_ID,
    )
    branch_row = session.execute(
        sa.select(models.branches).where(models.branches.c.id == branch["id"])
    ).mappings().first()
    assert branch_row is not None
    assert branch_row["coupons"] == []


def test_normalize_branch_coupons_show_in_checkout_exclusivity() -> None:
    from restaurant_os.operations import _normalize_branch_coupons

    coupons = [
        {"code": "PROMO1", "discount_percentage": 10, "is_active": True, "show_in_checkout": True},
        {"code": "PROMO2", "discount_percentage": 15, "is_active": True, "show_in_checkout": True},
        {"code": "PROMO3", "discount_percentage": 20, "is_active": True, "show_in_checkout": False},
    ]
    normalized = _normalize_branch_coupons(coupons)
    checkout_coupons = [c for c in normalized if c["show_in_checkout"]]
    assert len(checkout_coupons) == 1
    assert checkout_coupons[0]["code"] == "PROMO2"

    inactive_coupon = [
        {"code": "OFFLINE", "discount_percentage": 10, "is_active": False, "show_in_checkout": True}
    ]
    normalized_inactive = _normalize_branch_coupons(inactive_coupon)
    assert normalized_inactive[0]["show_in_checkout"] is False


def test_validate_branch_coupon_success(session: Any) -> None:
    _enable_public_key(session)
    session.execute(
        sa.update(models.branches)
        .where(models.branches.c.id == BRANCH_ID)
        .values(
            coupons=[
                {"code": "MIMENU-GRACIAS10", "discount_percentage": 10, "is_active": True},
            ]
        )
    )
    session.commit()

    result = validate_branch_coupon(
        session,
        branch_key=PUBLIC_KEY,
        coupon_code="mimenu-gracias10",
        subtotal_cents=10000,
    )
    assert result["valid"] is True
    assert result["code"] == "MIMENU-GRACIAS10"
    assert result["discount_percentage"] == 10
    assert result["discount_cents"] == 1000


def test_validate_branch_coupon_inactive_or_missing(session: Any) -> None:
    _enable_public_key(session)
    session.execute(
        sa.update(models.branches)
        .where(models.branches.c.id == BRANCH_ID)
        .values(
            coupons=[
                {"code": "EXPIRED15", "discount_percentage": 15, "is_active": False},
            ]
        )
    )
    session.commit()

    with pytest.raises(BusinessError) as exc:
        validate_branch_coupon(
            session,
            branch_key=PUBLIC_KEY,
            coupon_code="EXPIRED15",
            subtotal_cents=5000,
        )
    assert exc.value.code == "coupon_invalid"

    with pytest.raises(BusinessError) as exc:
        validate_branch_coupon(
            session,
            branch_key=PUBLIC_KEY,
            coupon_code="NONEXISTENT",
            subtotal_cents=5000,
        )
    assert exc.value.code == "coupon_invalid"


def test_public_order_intent_with_coupon_applies_deterministic_discount(session: Any) -> None:
    _enable_public_key(session)
    session.execute(
        sa.update(models.branches)
        .where(models.branches.c.id == BRANCH_ID)
        .values(
            coupons=[
                {"code": "MIMENU-GRACIAS10", "discount_percentage": 10, "is_active": True},
            ]
        )
    )
    session.commit()

    payload = _order_payload(quantity=2, coupon_code="MIMENU-GRACIAS10")
    result, created = create_public_order_intent(
        session,
        public_key=PUBLIC_KEY,
        payload=payload,
        idempotency_key="idemp-coupon-test-001",
    )
    assert created is True
    assert result["coupon_code"] == "MIMENU-GRACIAS10"
    assert result["discount_cents"] == 1900
    assert result["total_cents"] == 17100

    intent_row = session.execute(
        sa.select(models.public_order_intents).where(
            models.public_order_intents.c.public_reference == result["public_reference"]
        )
    ).mappings().first()
    assert intent_row is not None
    assert intent_row["coupon_code"] == "MIMENU-GRACIAS10"
    assert intent_row["discount_cents"] == 1900
    assert intent_row["total_cents"] == 17100

    accept_result, _ = accept_public_order_intent(
        session,
        intent_id=intent_row["id"],
        expected_version=1,
        idempotency_key="idemp-accept-coupon-001",
        actor_user_id=ADMIN_USER_ID,
    )
    order_row = session.execute(
        sa.select(models.orders).where(
            models.orders.c.public_order_intent_id == intent_row["id"]
        )
    ).mappings().first()
    assert order_row is not None
    assert order_row["coupon_code"] == "MIMENU-GRACIAS10"
    assert order_row["discount_cents"] == 1900
    assert order_row["total_cents"] == 17100


def test_public_order_intent_rejects_invalid_coupon(session: Any) -> None:
    _enable_public_key(session)
    payload = _order_payload(quantity=1, coupon_code="INVALID-COUPON")
    with pytest.raises(BusinessError) as exc:
        create_public_order_intent(
            session,
            public_key=PUBLIC_KEY,
            payload=payload,
            idempotency_key="idemp-invalid-coupon-001",
        )
    assert exc.value.code == "coupon_invalid"
