# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-branch-payment-methods-v1
from __future__ import annotations

from typing import Any
import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from restaurant_os import models, operations, public_storefront
from test_platform_api import _seed

BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
PUBLIC_KEY = "pk_test_payment_config"


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
        database_session.execute(
            sa.update(models.organizations)
            .where(models.organizations.c.id == operations.ORGANIZATION_ID)
            .values(slug="test-org", status="active", subscription_status="active")
        )
        database_session.execute(
            models.public_order_keys.insert().values(
                public_key=PUBLIC_KEY,
                organization_id=operations.ORGANIZATION_ID,
                branch_id=BRANCH_ID,
                status="active",
            )
        )
        database_session.commit()
        yield database_session


def test_branch_payment_columns_defaults(session: Any) -> None:
    row = (
        session.execute(
            sa.select(
                models.branches.c.accepts_cash_payments,
                models.branches.c.accepts_card_payments,
                models.branches.c.bank_transfer_info,
            ).where(models.branches.c.id == BRANCH_ID)
        )
        .mappings()
        .first()
    )
    assert row is not None
    assert row["accepts_cash_payments"] is True
    assert row["accepts_card_payments"] is False
    assert row["bank_transfer_info"] == {} or isinstance(row["bank_transfer_info"], dict)


def test_update_branch_payment_methods_and_bank_info(session: Any) -> None:
    bank_info = {
        "bank_name": "BBVA México",
        "account_holder": "Restaurante Central S.A. de C.V.",
        "account_number": "0123456789",
        "clabe": "012180001234567890",
        "is_enabled": True,
    }

    updated = operations.update_branch(
        session,
        BRANCH_ID,
        actor_user_id="018f6f73-2d0a-74f0-8f1c-000000000006",
        accepts_cash_payments=True,
        accepts_card_payments=True,
        bank_transfer_info=bank_info,
    )
    session.commit()

    assert updated["accepts_cash_payments"] is True
    assert updated["accepts_card_payments"] is True
    assert updated["bank_transfer_info"]["bank_name"] == "BBVA México"
    assert updated["bank_transfer_info"]["clabe"] == "012180001234567890"

    storefront = public_storefront.resolve_storefront(session, BRANCH_ID)
    public_branch = next(b for b in storefront["branches"] if b["id"] == BRANCH_ID)
    assert "accepts_cash_payments" in public_branch
    assert "accepts_card_payments" in public_branch
    assert "bank_transfer_info" in public_branch
    assert public_branch["accepts_card_payments"] is True
    assert public_branch["bank_transfer_info"]["clabe"] == "012180001234567890"
