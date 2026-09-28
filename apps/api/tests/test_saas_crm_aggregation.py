# SEC001-SYNTHETIC-FIXTURE provenance=saas-crm-aggregation-20260928
"""CRM aggregation preserves scope, exact money and segments at bounded query count."""

from datetime import datetime, timedelta, timezone
from time import perf_counter
from uuid import uuid4

import pytest
import sqlalchemy as sa
from restaurant_os import customer_ai, models
from restaurant_os.saas_onboarding import signup_tenant
from sqlalchemy.orm import Session
from test_saas_role_warehouse_scope import _add_branch_without_warehouse

NOW = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


@pytest.fixture
def crm_data(cash_scope_session: Session, monkeypatch):
    session = cash_scope_session
    monkeypatch.setattr(customer_ai, "datetime", FixedClock)
    tenants = [
        signup_tenant(
            session,
            {
                "business_name": f"CRM {suffix}",
                "owner_name": "Synthetic owner",
                "email": f"crm-{suffix}@example.test",
                "password": "synthetic-crm-password",
                "business_type": "blank",
            },
        )
        for suffix in ("a", "b")
    ]
    other_branch = _add_branch_without_warehouse(session, tenants[0], "CRM-OTHER")
    session.commit()
    return session, tenants[0], tenants[1], other_branch


def customer(session, tenant, branch=None):
    cid = str(uuid4())
    session.execute(
        models.customers.insert().values(
            id=cid,
            organization_id=tenant["organization"]["id"],
            origin_branch_id=branch or tenant["branch"]["id"],
            name="Synthetic customer",
            status="active",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    return cid


def order(session, tenant, cid, cents, days=0, status="ACCEPTED", branch=None):
    oid = str(uuid4())
    session.execute(
        models.orders.insert().values(
            id=oid,
            organization_id=tenant["organization"]["id"],
            branch_id=branch or tenant["branch"]["id"],
            customer_id=cid,
            folio=oid,
            channel="UBER_EATS",
            status=status,
            total_cents=cents,
            order_type="pickup",
            created_at=NOW - timedelta(days=days),
        )
    )


def test_crm_aggregate_preserves_scope_money_and_time_boundaries(crm_data):
    session, a, b, other = crm_data
    ids = {
        name: customer(session, a)
        for name in (
            "empty",
            "cancelled",
            "vip_count",
            "vip_spend",
            "large",
            "new14",
            "old15",
            "risk30",
            "active29",
        )
    }
    order(session, a, ids["cancelled"], 90000, status="cancelled")
    for _ in range(3):
        order(session, a, ids["vip_count"], 101, days=30)
    order(session, a, ids["vip_spend"], 50000)
    for _ in range(2):
        order(session, a, ids["large"], 2_000_000_001)
    order(session, a, ids["new14"], 49999, days=14)
    order(session, a, ids["old15"], 100, days=15)
    order(session, a, ids["risk30"], 100, days=30)
    order(session, a, ids["active29"], 100, days=29)
    other_customer = customer(session, a, other)
    order(session, a, other_customer, 60000, branch=other)
    foreign_customer = customer(session, b)
    order(session, b, foreign_customer, 80000)
    # Existing single-column FKs permit this invalid historical association; never aggregate it.
    order(session, b, ids["vip_count"], 70000)
    order(session, a, ids["vip_count"], 200, branch=other)
    session.commit()

    scoped = customer_ai.get_crm_segments_and_churn_risk(
        session,
        a["organization"]["id"],
        a["branch"]["id"],
    )
    assert scoped["summary"] == {
        "total_customers": 9,
        "vip_count": 3,
        "churn_risk_count": 2,
        "new_count": 2,
    }
    assert [row["id"] for row in scoped["vips"]] == [
        ids["large"],
        ids["vip_spend"],
        ids["vip_count"],
    ]
    assert [row["total_spend_cents"] for row in scoped["vips"]] == [
        4_000_000_002,
        50000,
        303,
    ]
    assert {row["id"] for row in scoped["churn_risk"]} == {ids["vip_count"], ids["risk30"]}
    assert {row["id"] for row in scoped["new_customers"]} == {ids["vip_spend"], ids["new14"]}
    assert scoped["vips"] == scoped["vip_customers"]
    assert scoped["churn_risk"] == scoped["churn_risk_customers"]
    assert scoped["vips"][2]["last_order_date"] == (NOW - timedelta(days=30)).isoformat()
    assert scoped["vips"][2]["total_orders"] == 3
    aggregate = customer_ai.get_crm_segments_and_churn_risk(session, a["organization"]["id"])
    assert aggregate["summary"]["total_customers"] == 10
    assert aggregate["summary"]["vip_count"] == 4
    assert (
        next(row for row in aggregate["vips"] if row["id"] == ids["vip_count"])["total_spend_cents"]
        == 503
    )
    assert foreign_customer not in str(aggregate)


def test_crm_query_count_stays_bounded_with_customer_growth(crm_data):
    session, a, _, _ = crm_data
    connection = session.connection()
    counts = []
    elapsed = []
    for extra in (1, 200):
        for _ in range(extra):
            cid = customer(session, a)
            order(session, a, cid, 101)
        # Newly seeded disposable databases have no planner statistics yet.
        connection.exec_driver_sql("ANALYZE customers")
        connection.exec_driver_sql("ANALYZE orders")
        statements = []

        def record(
            conn, cursor, statement, parameters, context, executemany, *, captured=statements
        ):
            captured.append((statement, parameters))

        sa.event.listen(connection, "before_cursor_execute", record)
        try:
            started = perf_counter()
            result = customer_ai.get_crm_segments_and_churn_risk(
                session,
                a["organization"]["id"],
                a["branch"]["id"],
            )
            elapsed.append(perf_counter() - started)
        finally:
            sa.event.remove(connection, "before_cursor_execute", record)
        counts.append(len(statements))
        size = 1 if extra == 1 else 201
        assert result["summary"]["total_customers"] == size
        assert result["summary"]["new_count"] == size
        assert len(result["new_customers"]) == min(size, 15)
    print(f"CRM {connection.dialect.name}: customers=[1,201] queries={counts} seconds={elapsed}")
    statement, parameters = statements[-1]
    explain = (
        "EXPLAIN (ANALYZE, BUFFERS) "
        if connection.dialect.name == "postgresql"
        else ("EXPLAIN QUERY PLAN ")
    )
    plan = connection.exec_driver_sql(explain + statement, parameters).all()
    print(f"CRM query plan: {plan}")
    assert counts == [1, 1]
