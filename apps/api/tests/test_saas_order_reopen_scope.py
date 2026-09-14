# SEC001-SYNTHETIC-FIXTURE provenance=recovery-abba6cfc3d77
"""Order correction commands cannot cross SaaS tenant boundaries."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from restaurant_os import models
from restaurant_os.operations import (
    NotFoundError,
    amend_order,
    apply_order_reopen_request,
    create_order_reopen_request,
    decide_order_reopen_request,
    list_order_reopen_requests,
)
from restaurant_os.saas_onboarding import signup_tenant
from test_saas_cash_scope import _cash_scope_api_client


def test_reopen_request_read_decision_and_apply_are_tenant_scoped() -> None:
    client, factory = _cash_scope_api_client()
    try:
        with factory() as session:
            tenant_a = signup_tenant(
                session,
                {
                    "business_name": "Correcciones A",
                    "owner_name": "Owner A",
                    "email": "correcciones-a@example.test",
                    "password": "synthetic-correction-password",
                    "business_type": "blank",
                },
            )
            tenant_b = signup_tenant(
                session,
                {
                    "business_name": "Correcciones B",
                    "owner_name": "Owner B",
                    "email": "correcciones-b@example.test",
                    "password": "synthetic-correction-password",
                    "business_type": "blank",
                },
            )
            now = datetime.now(timezone.utc)
            order_id = str(uuid4())
            session.execute(
                models.orders.insert().values(
                    id=order_id,
                    organization_id=tenant_b["organization"]["id"],
                    branch_id=tenant_b["branch"]["id"],
                    cash_shift_id=None,
                    customer_id=None,
                    customer_snapshot={"name": "Cliente B"},
                    delivery_address_snapshot=None,
                    folio="B-COR-001",
                    channel="UBER_EATS",
                    status="CLOSED",
                    total_cents=500,
                    currency="MXN",
                    owner_name=None,
                    order_type="takeout",
                    payment_method_intent=None,
                    version=1,
                    created_at=now,
                    accepted_at=now,
                )
            )
            session.commit()

            orders_a = client.get(
                "/api/v1/orders",
                headers={"Authorization": f"Bearer {tenant_a['token']}"},
            )
            orders_b = client.get(
                "/api/v1/orders",
                headers={"Authorization": f"Bearer {tenant_b['token']}"},
            )
            assert orders_a.status_code == 200
            assert orders_a.json() == []
            assert orders_b.status_code == 200
            assert [row["id"] for row in orders_b.json()] == [order_id]

            with pytest.raises(NotFoundError):
                create_order_reopen_request(
                    session,
                    order_id,
                    {"reason": "Intento cruzado documentado", "evidence_refs": ["ticket:A"]},
                    "cross-request-key-a",
                    tenant_a["user"]["id"],
                )
            with pytest.raises(NotFoundError):
                amend_order(
                    session,
                    order_id,
                    [{"product_id": str(uuid4()), "quantity": 1}],
                    1,
                    "cross-amend-key-a",
                    tenant_a["user"]["id"],
                )

            request = create_order_reopen_request(
                session,
                order_id,
                {"reason": "Corrección propia documentada", "evidence_refs": ["ticket:B"]},
                "own-request-key-b",
                tenant_b["user"]["id"],
            )
            assert list_order_reopen_requests(session, {}, tenant_a["user"]["id"])["items"] == []
            assert [
                row["id"]
                for row in list_order_reopen_requests(session, {}, tenant_b["user"]["id"])[
                    "items"
                ]
            ] == [request["id"]]

            with pytest.raises(NotFoundError):
                decide_order_reopen_request(
                    session,
                    request["id"],
                    "APPROVED",
                    {"decision_reason": "Intento cruzado documentado"},
                    "cross-decision-key-a",
                    tenant_a["user"]["id"],
                )
            with pytest.raises(NotFoundError):
                apply_order_reopen_request(session, request["id"], tenant_a["user"]["id"])
    finally:
        client.close()
