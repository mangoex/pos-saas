# SEC001-SYNTHETIC-FIXTURE provenance=saas-crm-remediation-20260928
"""Omitted CRM branch must not turn branch permission into organizational access."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from test_saas_integration_mapping_scope import mapping_tenants as mapping_tenants
from test_saas_role_warehouse_scope import _add_branch_without_warehouse


@pytest.mark.parametrize("extra_org_role", [False, True])
def test_crm_omitted_branch_preserves_permission_scope(mapping_tenants, extra_org_role):
    client, factory, tenant_a, tenant_b = mapping_tenants
    org_id = tenant_a["organization"]["id"]
    branch_id = tenant_a["branch"]["id"]
    now = datetime.now(timezone.utc)
    actor_id, role_id = str(uuid4()), str(uuid4())
    with factory() as session:
        other_branch = _add_branch_without_warehouse(session, tenant_a, "CRM")
        session.execute(models.users.insert().values(
            id=actor_id, organization_id=org_id, email="crm-reader@example.test",
            display_name="Branch reader", status="active", created_at=now, updated_at=now,
        ))
        permission_id = session.scalar(sa.select(models.permissions.c.id).where(
            models.permissions.c.code == "customers.read",
        ))
        if permission_id is None:
            permission_id = str(uuid4())
            session.execute(models.permissions.insert().values(
                id=permission_id, code="customers.read",
                description="Customer read", created_at=now,
            ))
        session.execute(models.roles.insert().values(
            id=role_id, organization_id=org_id, name="Branch CRM", scope="branch", created_at=now,
        ))
        session.execute(models.role_permissions.insert().values(
            role_id=role_id, permission_id=permission_id,
        ))
        session.execute(models.user_roles.insert().values(
            user_id=actor_id, role_id=role_id, branch_id=branch_id,
        ))
        if extra_org_role:
            empty_role = str(uuid4())
            session.execute(models.roles.insert().values(
                id=empty_role, organization_id=org_id, name="No CRM authority",
                scope="organization", created_at=now,
            ))
            session.execute(models.user_roles.insert().values(
                user_id=actor_id, role_id=empty_role,
            ))
        customer_ids = []
        for index, (org, branch) in enumerate([
            (org_id, branch_id), (org_id, other_branch),
            (tenant_b["organization"]["id"], tenant_b["branch"]["id"]),
        ]):
            customer_id = str(uuid4())
            customer_ids.append(customer_id)
            session.execute(models.customers.insert().values(
                id=customer_id, organization_id=org, origin_branch_id=branch,
                name=f"Customer {index}", status="active", created_at=now, updated_at=now,
            ))
            session.execute(models.orders.insert().values(
                id=str(uuid4()), organization_id=org, branch_id=branch,
                customer_id=customer_id, folio=f"CRM-{index}", order_type="pickup",
                channel="UBER_EATS", status="ACCEPTED", total_cents=60000, created_at=now,
            ))
        session.commit()
    headers = {"Authorization": "Bearer " + create_session_token(
        {"sub": actor_id}, get_settings().secret_key,
    )}
    path = "/api/v1/admin-ai/customer-crm-segments"
    omitted = client.get(path, headers=headers)
    if extra_org_role:
        assert omitted.status_code == 403, omitted.text
    else:
        assert omitted.status_code == 200, omitted.text
        assert omitted.json()["summary"]["total_customers"] == 1
        assert [c["id"] for c in omitted.json()["vips"]] == [customer_ids[0]]
    own = client.get(path, headers=headers, params={"branch_id": branch_id})
    assert own.status_code == 200, own.text
    assert [c["id"] for c in own.json()["vips"]] == [customer_ids[0]]
    for branch in (other_branch, tenant_b["branch"]["id"]):
        assert client.get(path, headers=headers, params={"branch_id": branch}).status_code == 403
    owner = client.get(path, headers={"Authorization": f"Bearer {tenant_a['token']}"})
    assert owner.status_code == 200, owner.text
    assert {c["id"] for c in owner.json()["vips"]} == set(customer_ids[:2])
