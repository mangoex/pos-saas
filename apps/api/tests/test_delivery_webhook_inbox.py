from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from restaurant_os import models
from restaurant_os.integrations.service import ChannelIntegrationService
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _session() -> sessionmaker:
    engine = sa.create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.metadata.create_all(
        engine, tables=[models.organizations, models.integration_webhook_inbox]
    )
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_webhook_claim_does_not_reopen_live_lease_and_retries_error() -> None:
    factory = _session()
    service = ChannelIntegrationService()
    payload = {"id": "evt-1", "store": {"id": "store-1"}}
    with factory() as session:
        first = service.claim_webhook(session, "org", "UBER_EATS", "evt-1", payload)
        assert first["claimed"] is True
        overlapping = service.claim_webhook(session, "org", "UBER_EATS", "evt-1", payload)
        assert overlapping == {"claimed": False, "in_progress": True, "id": first["id"]}
        assert service.finish_webhook(
            session, str(first["id"]), str(first["lease_token"]), "error", "timeout"
        )
        retry = service.claim_webhook(session, "org", "UBER_EATS", "evt-1", payload)
        assert retry["claimed"] is True
        assert retry["id"] == first["id"]


def test_webhook_claim_rejects_payload_conflict_and_replays_processed() -> None:
    factory = _session()
    service = ChannelIntegrationService()
    with factory() as session:
        claim = service.claim_webhook(session, "org", "UBER_EATS", "evt-2", {"value": 1})
        assert service.finish_webhook(
            session, str(claim["id"]), str(claim["lease_token"]), "processed"
        )
        assert service.claim_webhook(session, "org", "UBER_EATS", "evt-2", {"value": 1}) == {
            "claimed": False,
            "replay": True,
            "id": claim["id"],
        }
        try:
            service.claim_webhook(session, "org", "UBER_EATS", "evt-2", {"value": 2})
        except ValueError as exc:
            assert str(exc) == "webhook_event_payload_conflict"
        else:
            raise AssertionError("conflicting event payload was accepted")


def test_webhook_expired_lease_can_be_reclaimed() -> None:
    factory = _session()
    service = ChannelIntegrationService()
    with factory() as session:
        first = service.claim_webhook(session, "org", "UBER_EATS", "evt-3", {"value": 3})
        session.execute(
            models.integration_webhook_inbox.update()
            .where(models.integration_webhook_inbox.c.id == first["id"])
            .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        session.commit()
        retry = service.claim_webhook(session, "org", "UBER_EATS", "evt-3", {"value": 3})
        assert retry["claimed"] is True
        assert retry["lease_token"] != first["lease_token"]


def test_postgres_concurrent_claim_has_one_winner_and_stale_finish_is_rejected() -> None:
    database_url = os.environ.get("SAAS_TEST_POSTGRES_URL")
    if not database_url:
        return
    schema = "saas_delivery_inbox_" + uuid4().hex
    base = sa.create_engine(database_url)
    with base.begin() as connection:
        connection.execute(sa.schema.CreateSchema(schema))
    scoped_url = sa.engine.make_url(database_url).update_query_dict(
        {"options": f"-csearch_path={schema}"}
    )
    engine = sa.create_engine(scoped_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    models.metadata.create_all(
        engine, tables=[models.organizations, models.integration_webhook_inbox]
    )
    service = ChannelIntegrationService()
    with factory() as session:
        now = datetime.now(timezone.utc)
        session.execute(
            models.organizations.insert().values(
                id="org", name="Inbox QA", status="active", created_at=now, updated_at=now
            )
        )
        session.commit()
    barrier = threading.Barrier(2)
    results: list[dict[str, object]] = []

    def claim() -> None:
        with factory() as session:
            barrier.wait()
            results.append(service.claim_webhook(session, "org", "UBER_EATS", "event", {"v": 1}))

    try:
        threads = [threading.Thread(target=claim) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        winners = [result for result in results if result.get("claimed")]
        assert len(winners) == 1
        winner = winners[0]
        with factory() as session:
            assert service.finish_webhook(
                session, str(winner["id"]), str(winner["lease_token"]), "processed"
            )
            assert not service.finish_webhook(
                session, str(winner["id"]), str(winner["lease_token"]), "processed"
            )
            replay = service.claim_webhook(session, "org", "UBER_EATS", "event", {"v": 1})
        assert replay["replay"] is True
        assert replay["claimed"] is False
    finally:
        engine.dispose()
        with base.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        base.dispose()


def test_0080_duplicate_preflight_leaves_sqlite_schema_unchanged() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/202609062000_0080_delivery_inbox_idempotency.py"
    )
    spec = spec_from_file_location("delivery_inbox_migration", path)
    assert spec and spec.loader
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE organizations (id TEXT PRIMARY KEY)"))
        connection.execute(
            sa.text("CREATE TABLE orders (id TEXT PRIMARY KEY, organization_id TEXT NOT NULL)")
        )
        connection.execute(
            sa.text(
                "CREATE TABLE channel_orders_meta (id TEXT PRIMARY KEY, order_id TEXT, "
                "provider TEXT, external_order_id TEXT)"
            )
        )
        connection.execute(sa.text("INSERT INTO orders VALUES ('a', 'org')"))
        connection.execute(sa.text("INSERT INTO orders VALUES ('b', 'org')"))
        connection.execute(
            sa.text("INSERT INTO channel_orders_meta VALUES ('a', 'a', 'UBER_EATS', 'same')")
        )
        connection.execute(
            sa.text("INSERT INTO channel_orders_meta VALUES ('b', 'b', 'UBER_EATS', 'same')")
        )
        with Operations.context(MigrationContext.configure(connection)):
            try:
                migration.upgrade()
            except RuntimeError as exc:
                assert "0080 requires governed reconciliation" in str(exc)
            else:
                raise AssertionError("duplicate external orders were accepted")
        inspector = sa.inspect(connection)
        assert not inspector.has_table("integration_webhook_inbox")
        assert "organization_id" not in {
            column["name"] for column in inspector.get_columns("channel_orders_meta")
        }
