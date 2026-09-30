"""Tests for mark_order_ready and domain_host public order tracking."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import mark_order_ready
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionFactory()

    now = datetime.now(timezone.utc)
    org_id = str(uuid.uuid4())
    legal_entity_id = str(uuid.uuid4())
    branch_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    role_id = str(uuid.uuid4())

    session.execute(
        models.organizations.insert().values(
            id=org_id,
            name="Taqueria Test",
            slug="taqueria-test",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.legal_entities.insert().values(
            id=legal_entity_id,
            organization_id=org_id,
            name="Taqueria Test SA de CV",
            created_at=now,
            updated_at=now,
        )
    )
    bu_id = str(uuid.uuid4())
    session.execute(
        models.business_units.insert().values(
            id=bu_id,
            organization_id=org_id,
            legal_entity_id=legal_entity_id,
            name="Taqueria BU",
            code="TBU",
            unit_type="restaurant",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.branches.insert().values(
            id=branch_id,
            organization_id=org_id,
            legal_entity_id=legal_entity_id,
            business_unit_id=bu_id,
            name="Sucursal Matriz",
            code="MAT",
            slug="matriz",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.users.insert().values(
            id=user_id,
            organization_id=org_id,
            email="admin@test.com",
            display_name="Admin Test",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.roles.insert().values(
            id=role_id,
            organization_id=org_id,
            name="Admin",
            scope="organization",
            created_at=now,
        )
    )
    session.execute(
        models.user_roles.insert().values(
            user_id=user_id,
            role_id=role_id,
            branch_id=branch_id,
        )
    )
    for perm_code in ["orders.create", "orders.read"]:
        perm_id = str(uuid.uuid4())
        session.execute(
            models.permissions.insert().values(
                id=perm_id,
                code=perm_code,
                description=perm_code,
                created_at=now,
            )
        )
        session.execute(
            models.role_permissions.insert().values(
                role_id=role_id,
                permission_id=perm_id,
            )
        )
    session.commit()
    session.info["test_context"] = {
        "org_id": org_id,
        "branch_id": branch_id,
        "user_id": user_id,
    }
    yield session
    session.close()


def test_mark_order_ready_compiles_and_transitions_order(db_session):
    ctx = db_session.info["test_context"]
    now = datetime.now(timezone.utc)
    order_id = str(uuid.uuid4())
    folio = "F-001"

    # Insert an open cash shift
    shift_id = str(uuid.uuid4())
    db_session.execute(
        models.cash_shifts.insert().values(
            id=shift_id,
            organization_id=ctx["org_id"],
            branch_id=ctx["branch_id"],
            register_code="REG-01",
            status="OPEN",
            opening_cash_cents=100000,
            cashier_user_id=ctx["user_id"],
            opened_at=now,
            created_at=now,
        )
    )

    # Insert an accepted order
    db_session.execute(
        models.orders.insert().values(
            id=order_id,
            organization_id=ctx["org_id"],
            branch_id=ctx["branch_id"],
            cash_shift_id=shift_id,
            folio=folio,
            channel="POS",
            status="ACCEPTED",
            total_cents=15000,
            delivery_fee_cents=0,
            discount_cents=0,
            currency="MXN",
            created_at=now,
            accepted_at=now,
        )
    )

    # Insert a pending production task
    task_id = str(uuid.uuid4())
    line_id = str(uuid.uuid4())
    db_session.execute(
        models.production_tasks.insert().values(
            id=task_id,
            organization_id=ctx["org_id"],
            branch_id=ctx["branch_id"],
            order_id=order_id,
            order_line_id=line_id,
            station="COCINA",
            status="PENDING",
            product_name="Tacos al Pastor",
            quantity=3,
            created_at=now,
        )
    )
    db_session.commit()

    # Call mark_order_ready - must NOT throw CompileError (due to updated_at) or any DB error
    detail = mark_order_ready(db_session, order_id, actor_user_id=ctx["user_id"])

    assert detail is not None
    assert detail["status"] == "READY"

    # Verify orders table was updated to READY
    updated_order = (
        db_session.execute(sa.select(models.orders).where(models.orders.c.id == order_id))
        .mappings()
        .one()
    )
    assert updated_order["status"] == "READY"

    # Verify production task was updated to COMPLETED
    updated_task = (
        db_session.execute(
            sa.select(models.production_tasks).where(models.production_tasks.c.id == task_id)
        )
        .mappings()
        .one()
    )
    assert updated_task["status"] == "COMPLETED"
    assert updated_task["completed_at"] is not None

    # Verify order event was recorded
    event = (
        db_session.execute(
            sa.select(models.order_events).where(models.order_events.c.order_id == order_id)
        )
        .mappings()
        .first()
    )
    assert event is not None
    assert event["event_type"] == "READY"


@pytest.mark.anyio
async def test_bind_domain_host_allows_public_order_intents(db_session, monkeypatch):
    from restaurant_os.domain_host import bind_domain_host
    from starlette.requests import Request

    ctx = db_session.info["test_context"]
    org_id = ctx["org_id"]
    public_ref = "PI-TEST-123456"

    # Insert a domain for the test organization
    domain_id = str(uuid.uuid4())
    db_session.execute(
        models.restaurant_domains.insert().values(
            id=domain_id,
            organization_id=org_id,
            hostname="taqueriatest.com",
            verification_token="token123",
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    # Insert a public order key
    db_session.execute(
        models.public_order_keys.insert().values(
            public_key="pk_test_123",
            organization_id=org_id,
            branch_id=ctx["branch_id"],
            status="active",
            created_at=datetime.now(timezone.utc),
        )
    )
    # Insert a public order intent
    db_session.execute(
        models.public_order_intents.insert().values(
            id=str(uuid.uuid4()),
            organization_id=org_id,
            branch_id=ctx["branch_id"],
            public_key="pk_test_123",
            public_reference=public_ref,
            correlation_id=str(uuid.uuid4()),
            status="ACCEPTED",
            customer_snapshot={"name": "Cliente"},
            order_type="takeout",
            total_cents=10000,
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    # Mock platform_hosts to return empty set so taqueriatest.com is treated as custom domain
    monkeypatch.setattr("restaurant_os.domain_host.platform_hosts", lambda: set())

    # Build a custom-domain request for the public intent reference.
    scope = {
        "type": "http",
        "method": "GET",
        "path": f"/api/v1/public/order-intents/{public_ref}",
        "raw_path": f"/api/v1/public/order-intents/{public_ref}".encode(),
        "query_string": b"",
        "headers": [
            (b"host", b"taqueriatest.com"),
        ],
    }
    req = Request(scope)

    # Must NOT raise HTTPException 403 domain_route_unavailable
    await bind_domain_host(req, db_session)
