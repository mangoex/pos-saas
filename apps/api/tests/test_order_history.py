from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    AuthorizationError,
    BusinessError,
    list_order_accounts,
    open_cash_shift,
)
from restaurant_os.saas_onboarding import signup_tenant
from sqlalchemy.orm import Session
from test_saas_cash_scope import cash_scope_session as cash_scope_session

NOW = datetime(2026, 9, 30, 18, tzinfo=timezone.utc)


def tenant(session: Session, name: str) -> dict:
    return signup_tenant(
        session,
        {
            "business_name": name,
            "owner_name": name,
            "email": f"{uuid4().hex}@example.test",
            "password": uuid4().hex,
            "business_type": "taqueria",
        },
    )


def intent(
    session: Session,
    owner: dict,
    *,
    status: str = "PENDING_REVIEW",
    name: str = "History",
    service: str = "takeout",
) -> str:
    intent_id = str(uuid4())
    session.execute(
        models.public_order_intents.insert().values(
            id=intent_id,
            organization_id=owner["organization"]["id"],
            branch_id=owner["branch"]["id"],
            public_key=session.scalar(
                sa.select(models.public_order_keys.c.public_key).where(
                    models.public_order_keys.c.branch_id == owner["branch"]["id"]
                )
            ),
            public_reference=f"PI-{uuid4().hex}",
            correlation_id=str(uuid4()),
            status=status,
            customer_snapshot={"name": name},
            order_type=service,
            total_cents=10000,
            created_at=NOW - timedelta(hours=25),
        )
    )
    session.commit()
    return intent_id


def test_history_filters_cursor_and_tenant_authority(cash_scope_session: Session) -> None:
    session = cash_scope_session
    a, b = tenant(session, "History A"), tenant(session, "History B")
    own = [
        intent(session, a, name="Search marker"),
        intent(session, a, status="REJECTED", name="Other", service="delivery"),
    ]
    foreign = intent(session, b)
    filters = {"branch_id": a["branch"]["id"], "limit": 1}
    actor = a["user"]["id"]
    page = list_order_accounts(session, filters, actor)
    assert len(page["items"]) == 1 and page["next_cursor"]
    second = list_order_accounts(session, {**filters, "cursor": page["next_cursor"]}, actor)
    assert {item["id"] for item in page["items"] + second["items"]} == set(own)
    assert second["next_cursor"] is None
    assert foreign not in {item["id"] for item in page["items"] + second["items"]}
    own_item = next(item for item in page["items"] + second["items"] if item["id"] == own[0])
    found = list_order_accounts(session, {**filters, "q": own_item["folio"]}, actor)
    assert [item["id"] for item in found["items"]] == [own[0]]
    with pytest.raises(AuthorizationError):
        list_order_accounts(session, {**filters, "cursor": page["next_cursor"]}, b["user"]["id"])
    with pytest.raises(BusinessError, match="Cursor"):
        list_order_accounts(
            session, {**filters, "q": "Other", "cursor": page["next_cursor"]}, actor
        )
    for extra, expected in [
        ({"q": "Search marker"}, {own[0]}),
        ({"q": "SEARCH MARKER"}, {own[0]}),
        ({"service_type": "delivery"}, {own[1]}),
        ({"from_utc": NOW - timedelta(hours=26), "to_utc": NOW}, set(own)),
        ({"cash_shift_id": str(uuid4())}, set()),
    ]:
        data = list_order_accounts(session, {**filters, "limit": 100, **extra}, actor)
        assert {item["id"] for item in data["items"]} == expected


def test_mixed_history_cursor_preserves_same_timestamp_and_id(cash_scope_session: Session) -> None:
    session = cash_scope_session
    owner = tenant(session, "Mixed history")
    intent_id = intent(session, owner)
    shift = open_cash_shift(
        session, 0, branch_id=owner["branch"]["id"], actor_user_id=owner["user"]["id"]
    )
    session.execute(
        models.orders.insert().values(
            id=intent_id,
            organization_id=owner["organization"]["id"],
            branch_id=owner["branch"]["id"],
            cash_shift_id=shift["id"],
            folio="HISTORY-001",
            channel="POS",
            status="PENDING",
            order_type="takeout",
            total_cents=10000,
            currency="MXN",
            created_at=NOW - timedelta(hours=25),
        )
    )
    session.commit()
    filters = {"branch_id": owner["branch"]["id"], "limit": 1}
    page = list_order_accounts(session, filters, owner["user"]["id"])
    assert len(page["items"]) == 1 and not page["items"][0].get("is_public_intent")
    assert page["next_cursor"]
    second = list_order_accounts(
        session, {**filters, "cursor": page["next_cursor"]}, owner["user"]["id"]
    )
    assert len(second["items"]) == 1 and second["items"][0]["is_public_intent"]
    assert second["next_cursor"] is None
