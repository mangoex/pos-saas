from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.integrations.service import ChannelIntegrationService
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _factory() -> sessionmaker[Session]:
    engine = sa.create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _seed(session: Session) -> None:
    now = datetime.now(timezone.utc)
    session.execute(
        models.organizations.insert().values(
            id="org",
            name="Org",
            status="active",
            subscription_status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.branches.insert().values(
            id="branch",
            organization_id="org",
            legal_entity_id="legal",
            business_unit_id="unit",
            name="Branch",
            code="B",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.products.insert().values(
            id="product",
            organization_id="org",
            category_id="cat",
            name="Taco",
            sku="T",
            station="kitchen",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.channel_integrations.insert().values(
            id="config",
            organization_id="org",
            provider="UBER_EATS",
            is_enabled=True,
            client_id="id",
            client_secret="secret",
            environment="sandbox",
            auto_accept=True,
            default_prep_time_minutes=20,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.channel_store_mappings.insert().values(
            id="store",
            organization_id="org",
            branch_id="branch",
            provider="UBER_EATS",
            external_store_id="store",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.channel_product_mappings.insert().values(
            id="item",
            organization_id="org",
            product_id="product",
            provider="UBER_EATS",
            external_item_id="item",
            is_active=True,
            created_at=now,
        )
    )
    session.commit()


def test_stale_uber_response_reconciles_latest_desired_availability() -> None:
    factory = _factory()
    service = ChannelIntegrationService()
    with factory() as session:
        _seed(session)
        service.enqueue_uber_availability_sync(session, "org", "product", False, "branch")
        session.commit()
        old = service.claim_due_uber_availability_sync(session)
        assert old
        service.enqueue_uber_availability_sync(session, "org", "product", True, "branch")
        session.commit()
        assert service.finish_uber_availability_sync(session, old, None) == "RECONCILE"
        job = session.execute(sa.select(models.channel_availability_sync_jobs)).mappings().one()
    assert job["status"] == "PENDING"
    assert job["is_available"] is True
    assert job["last_error"] == "uber_availability_superseded_reconcile"
