# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-service-schedule-auto-cash-v1
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import pytest
import sqlalchemy as sa
from zoneinfo import ZoneInfo

from restaurant_os import models
from restaurant_os.operations import (
    ORGANIZATION_ID,
    get_open_cash_shift,
    list_public_branches,
    reconcile_branch_auto_cash_shift,
    update_branch,
)
from restaurant_os.public_storefront import resolve_storefront
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_platform_api import _seed

ADMIN_USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000006"
BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
PUBLIC_KEY = "pk_test_schedule_auto_cash"


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


def test_branch_schedule_columns_defaults(session: Any) -> None:
    row = (
        session.execute(
            sa.select(
                models.branches.c.service_schedule,
                models.branches.c.auto_cash_shift_enabled,
                models.branches.c.auto_cash_opening_cents,
            ).where(models.branches.c.id == BRANCH_ID)
        )
        .mappings()
        .one()
    )
    assert row["service_schedule"] == []
    assert row["auto_cash_shift_enabled"] is False
    assert row["auto_cash_opening_cents"] == 50000


def test_update_branch_service_schedule_and_auto_cash(session: Any) -> None:
    schedule = [
        {"day_index": 0, "day_name": "Lunes", "is_open": True, "open_time": "09:00", "close_time": "22:00"},
        {"day_index": 1, "day_name": "Martes", "is_open": True, "open_time": "09:00", "close_time": "22:00"},
        {"day_index": 2, "day_name": "Miércoles", "is_open": True, "open_time": "09:00", "close_time": "22:00"},
        {"day_index": 3, "day_name": "Jueves", "is_open": True, "open_time": "09:00", "close_time": "22:00"},
        {"day_index": 4, "day_name": "Viernes", "is_open": True, "open_time": "09:00", "close_time": "23:00"},
        {"day_index": 5, "day_name": "Sábado", "is_open": True, "open_time": "10:00", "close_time": "23:00"},
        {"day_index": 6, "day_name": "Domingo", "is_open": False, "open_time": "10:00", "close_time": "20:00"},
    ]

    update_branch(
        session,
        branch_id=BRANCH_ID,
        actor_user_id=ADMIN_USER_ID,
        service_schedule=schedule,
        auto_cash_shift_enabled=True,
        auto_cash_opening_cents=50000,
    )

    branch_row = (
        session.execute(
            sa.select(
                models.branches.c.service_schedule,
                models.branches.c.auto_cash_shift_enabled,
                models.branches.c.auto_cash_opening_cents,
            ).where(models.branches.c.id == BRANCH_ID)
        )
        .mappings()
        .one()
    )

    assert len(branch_row["service_schedule"]) == 7
    assert branch_row["auto_cash_shift_enabled"] is True
    assert branch_row["auto_cash_opening_cents"] == 50000
    assert branch_row["service_schedule"][6]["is_open"] is False

    # Check public branches list includes service_schedule
    pub_branches = list_public_branches(session, organization_id=ORGANIZATION_ID)
    target = next(b for b in pub_branches if b["id"] == BRANCH_ID)
    assert "service_schedule" in target
    assert len(target["service_schedule"]) == 7


def test_reconcile_branch_auto_cash_shift_opens_shift(session: Any) -> None:
    # Set Monday (index 0) open from 09:00 to 22:00
    schedule = [
        {"day_index": 0, "day_name": "Lunes", "is_open": True, "open_time": "09:00", "close_time": "22:00"},
        {"day_index": 1, "day_name": "Martes", "is_open": False, "open_time": "09:00", "close_time": "22:00"},
        {"day_index": 2, "day_name": "Miércoles", "is_open": False, "open_time": "09:00", "close_time": "22:00"},
        {"day_index": 3, "day_name": "Jueves", "is_open": False, "open_time": "09:00", "close_time": "22:00"},
        {"day_index": 4, "day_name": "Viernes", "is_open": False, "open_time": "09:00", "close_time": "22:00"},
        {"day_index": 5, "day_name": "Sábado", "is_open": False, "open_time": "09:00", "close_time": "22:00"},
        {"day_index": 6, "day_name": "Domingo", "is_open": False, "open_time": "09:00", "close_time": "22:00"},
    ]
    update_branch(
        session,
        branch_id=BRANCH_ID,
        actor_user_id=ADMIN_USER_ID,
        service_schedule=schedule,
        auto_cash_shift_enabled=True,
        auto_cash_opening_cents=50000,
    )

    # 2026-09-21 is a Monday. 10:30 AM local Chihuahua time
    tz = ZoneInfo("America/Chihuahua")
    monday_1030 = datetime(2026, 9, 21, 10, 30, tzinfo=tz)

    assert get_open_cash_shift(session, branch_id=BRANCH_ID) is None

    # Run reconciler
    opened_shift = reconcile_branch_auto_cash_shift(
        session,
        branch_id=BRANCH_ID,
        register_code="CAJA-01",
        now_dt=monday_1030,
    )

    assert opened_shift is not None
    assert opened_shift["status"] == "OPEN"
    assert opened_shift["opening_cash_cents"] == 50000
    assert get_open_cash_shift(session, branch_id=BRANCH_ID) is not None


def test_reconcile_branch_auto_cash_shift_closes_shift_when_past_hours(session: Any) -> None:
    # First open a shift on Monday at 10:30 AM
    schedule = [
        {"day_index": 0, "day_name": "Lunes", "is_open": True, "open_time": "09:00", "close_time": "22:00"},
    ]
    update_branch(
        session,
        branch_id=BRANCH_ID,
        actor_user_id=ADMIN_USER_ID,
        service_schedule=schedule,
        auto_cash_shift_enabled=True,
        auto_cash_opening_cents=50000,
    )

    tz = ZoneInfo("America/Chihuahua")
    monday_1030 = datetime(2026, 9, 21, 10, 30, tzinfo=tz)
    opened = reconcile_branch_auto_cash_shift(
        session, branch_id=BRANCH_ID, register_code="CAJA-01", now_dt=monday_1030
    )
    assert opened is not None
    shift_id = opened["id"]

    # Now simulate time at 22:15 (past 22:00 closing)
    monday_2215 = datetime(2026, 9, 21, 22, 15, tzinfo=tz)
    res = reconcile_branch_auto_cash_shift(
        session, branch_id=BRANCH_ID, register_code="CAJA-01", now_dt=monday_2215
    )
    assert res is None
    assert get_open_cash_shift(session, branch_id=BRANCH_ID) is None

    # Verify shift in db is OPERATIVELY_CLOSED
    closed_row = session.execute(
        sa.select(models.cash_shifts.c.status).where(models.cash_shifts.c.id == shift_id)
    ).scalar_one()
    assert closed_row == "OPERATIVELY_CLOSED"


def test_reconcile_branch_auto_cash_shift_closes_shift_when_day_is_closed(session: Any) -> None:
    # Shift was open, but Tuesday is closed
    schedule = [
        {"day_index": 0, "day_name": "Lunes", "is_open": True, "open_time": "09:00", "close_time": "22:00"},
        {"day_index": 1, "day_name": "Martes", "is_open": False, "open_time": "09:00", "close_time": "22:00"},
    ]
    update_branch(
        session,
        branch_id=BRANCH_ID,
        actor_user_id=ADMIN_USER_ID,
        service_schedule=schedule,
        auto_cash_shift_enabled=True,
        auto_cash_opening_cents=50000,
    )

    tz = ZoneInfo("America/Chihuahua")
    monday_1030 = datetime(2026, 9, 21, 10, 30, tzinfo=tz)
    reconcile_branch_auto_cash_shift(session, branch_id=BRANCH_ID, register_code="CAJA-01", now_dt=monday_1030)
    assert get_open_cash_shift(session, branch_id=BRANCH_ID) is not None

    # Next day: Tuesday (2026-09-22) 11:00 AM
    tuesday_1100 = datetime(2026, 9, 22, 11, 0, tzinfo=tz)
    res = reconcile_branch_auto_cash_shift(
        session, branch_id=BRANCH_ID, register_code="CAJA-01", now_dt=tuesday_1100
    )
    assert res is None
    assert get_open_cash_shift(session, branch_id=BRANCH_ID) is None


def test_manual_close_today_prevents_auto_reopen(session: Any) -> None:
    schedule = [
        {"day_index": 0, "day_name": "Lunes", "is_open": True, "open_time": "09:00", "close_time": "22:00"},
    ]
    update_branch(
        session,
        branch_id=BRANCH_ID,
        actor_user_id=ADMIN_USER_ID,
        service_schedule=schedule,
        auto_cash_shift_enabled=True,
        auto_cash_opening_cents=50000,
    )

    tz = ZoneInfo("America/Chihuahua")
    monday_1030 = datetime(2026, 9, 21, 10, 30, tzinfo=tz)
    opened = reconcile_branch_auto_cash_shift(
        session, branch_id=BRANCH_ID, register_code="CAJA-01", now_dt=monday_1030
    )
    assert opened is not None

    # Simulate manual closure by administrator at 14:00
    monday_1400 = datetime(2026, 9, 21, 14, 0, tzinfo=tz)
    from restaurant_os.operations import close_cash_shift_operationally
    close_cash_shift_operationally(
        session,
        cash_shift_id=opened["id"],
        idempotency_key="manual-close-test-1",
        actor_user_id=ADMIN_USER_ID,
    )
    session.commit()
    assert get_open_cash_shift(session, branch_id=BRANCH_ID) is None

    # Now reconcile runs at 14:15 during service hours: it MUST NOT reopen
    monday_1415 = datetime(2026, 9, 21, 14, 15, tzinfo=tz)
    result = reconcile_branch_auto_cash_shift(
        session, branch_id=BRANCH_ID, register_code="CAJA-01", now_dt=monday_1415
    )
    assert result is None
    assert get_open_cash_shift(session, branch_id=BRANCH_ID) is None
