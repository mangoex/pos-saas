# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-role-warehouse-scope-synthetic-v1
"""Role, permission, and warehouse mutations remain tenant scoped."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import (
    BusinessError,
    create_role,
    create_warehouse,
    delete_role,
    update_role,
    update_role_permissions,
    update_warehouse,
)
from restaurant_os.saas_onboarding import signup_tenant
from sqlalchemy.orm import Session
from test_saas_cash_scope import _cash_scope_api_client


def _owner_role_id(session, organization_id: str) -> str:
    return str(
        session.scalar(
            sa.select(models.roles.c.id)
            .select_from(
                models.roles.join(
                    models.role_authority_grants,
                    models.roles.c.id == models.role_authority_grants.c.role_id,
                )
            )
            .where(
                models.roles.c.organization_id == organization_id,
                models.role_authority_grants.c.authority_kind
                == "organization_all_permissions",
            )
        )
    )


def _add_branch_without_warehouse(session, tenant: dict, suffix: str) -> str:
    source = session.execute(
        sa.select(models.branches).where(models.branches.c.id == tenant["branch"]["id"])
    ).mappings().one()
    branch_id = str(uuid4())
    values = dict(source)
    values.update(
        {
            "id": branch_id,
            "name": f"Synthetic Branch {suffix}",
            "code": f"SYN-{suffix}",
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
    )
    session.execute(models.branches.insert().values(**values))
    return branch_id


def test_role_permissions_and_warehouses_reject_cross_tenant_mutations() -> None:
    client, factory = _cash_scope_api_client()
    try:
        with factory() as session:
            tenants = [
                signup_tenant(
                    session,
                    {
                        "business_name": f"RBAC Warehouse {suffix}",
                        "owner_name": f"Owner {suffix}",
                        "email": f"rbac-warehouse-{suffix.lower()}@example.test",
                        "password": f"test-only-rbac-warehouse-{suffix.lower()}",
                        "business_type": "blank",
                    },
                )
                for suffix in ("A", "B")
            ]
            organization_ids = [str(tenant["organization"]["id"]) for tenant in tenants]
            owner_role_ids = [
                _owner_role_id(session, organization_id)
                for organization_id in organization_ids
            ]
            permission_id = str(uuid4())
            session.execute(
                models.permissions.insert().values(
                    id=permission_id,
                    code="synthetic.scope.permission",
                    description="Synthetic permission for tenant-scope regression",
                    created_at=datetime.now(UTC),
                )
            )
            warehouse_ids = [
                str(
                    session.scalar(
                        sa.select(models.warehouses.c.id).where(
                            models.warehouses.c.organization_id == organization_id
                        )
                    )
                )
                for organization_id in organization_ids
            ]
            extra_branch_a = _add_branch_without_warehouse(session, tenants[0], "A")
            session.commit()

        headers = [
            {"Authorization": f"Bearer {tenant['token']}"} for tenant in tenants
        ]
        role_b_response = client.post(
            "/api/v1/roles",
            headers=headers[1],
            json={"name": "Tenant B Custom", "scope": "organization"},
        )
        assert role_b_response.status_code == 200, role_b_response.text
        role_b = role_b_response.json()

        foreign_role_update = client.put(
            f"/api/v1/roles/{role_b['id']}",
            headers=headers[0],
            json={"name": "Cross-tenant rename"},
        )
        assert foreign_role_update.status_code == 409, foreign_role_update.text
        assert foreign_role_update.json()["detail"]["code"] == "role_not_found"

        foreign_permissions = client.put(
            f"/api/v1/roles/{role_b['id']}/permissions",
            headers=headers[0],
            json={"permission_ids": [permission_id]},
        )
        assert foreign_permissions.status_code == 409, foreign_permissions.text
        assert foreign_permissions.json()["detail"]["code"] == "role_not_found"

        foreign_role_delete = client.delete(
            f"/api/v1/roles/{role_b['id']}", headers=headers[0]
        )
        assert foreign_role_delete.status_code == 409, foreign_role_delete.text
        assert foreign_role_delete.json()["detail"]["code"] == "role_not_found"

        own_permissions = client.put(
            f"/api/v1/roles/{role_b['id']}/permissions",
            headers=headers[1],
            json={"permission_ids": [permission_id]},
        )
        assert own_permissions.status_code == 200, own_permissions.text
        assert own_permissions.json()["permissions_count"] == 1

        owner_scope = client.put(
            f"/api/v1/roles/{owner_role_ids[1]}",
            headers=headers[1],
            json={"scope": "branch"},
        )
        assert owner_scope.status_code == 409, owner_scope.text
        assert owner_scope.json()["detail"]["code"] == "owner_role_scope_immutable"

        owner_permissions = client.put(
            f"/api/v1/roles/{owner_role_ids[1]}/permissions",
            headers=headers[1],
            json={"permission_ids": []},
        )
        assert owner_permissions.status_code == 409, owner_permissions.text
        assert owner_permissions.json()["detail"]["code"] == "owner_role_permissions_immutable"

        owner_delete = client.delete(
            f"/api/v1/roles/{owner_role_ids[1]}", headers=headers[1]
        )
        assert owner_delete.status_code == 409, owner_delete.text
        assert owner_delete.json()["detail"]["code"] == "owner_role_delete_forbidden"

        foreign_warehouse = client.put(
            f"/api/v1/warehouses/{warehouse_ids[1]}",
            headers=headers[0],
            json={"name": "Cross-tenant warehouse"},
        )
        assert foreign_warehouse.status_code == 409, foreign_warehouse.text
        assert foreign_warehouse.json()["detail"]["code"] == "warehouse_not_found"

        own_warehouse = client.put(
            f"/api/v1/warehouses/{warehouse_ids[0]}",
            headers=headers[0],
            json={"name": "Own Warehouse A"},
        )
        assert own_warehouse.status_code == 200, own_warehouse.text
        assert own_warehouse.json()["name"] == "Own Warehouse A"

        active_warehouse = client.put(
            f"/api/v1/warehouses/{warehouse_ids[0]}",
            headers=headers[0],
            json={"status": "inactive"},
        )
        assert active_warehouse.status_code == 409, active_warehouse.text
        assert active_warehouse.json()["detail"]["code"] == "active_branch_requires_warehouse"

        foreign_branch_create = client.post(
            "/api/v1/warehouses",
            headers=headers[1],
            json={"branch_id": extra_branch_a, "name": "Foreign Warehouse"},
        )
        assert foreign_branch_create.status_code == 409, foreign_branch_create.text
        assert foreign_branch_create.json()["detail"]["code"] == "invalid_branch"

        created = client.post(
            "/api/v1/warehouses",
            headers=headers[0],
            json={"branch_id": extra_branch_a, "name": "Second Branch Warehouse"},
        )
        assert created.status_code == 200, created.text

        duplicate = client.post(
            "/api/v1/warehouses",
            headers=headers[0],
            json={"branch_id": extra_branch_a, "name": "Duplicate Warehouse"},
        )
        assert duplicate.status_code == 409, duplicate.text
        assert duplicate.json()["detail"]["code"] == "warehouse_exists"

        with factory() as session:
            role_b_row = session.execute(
                sa.select(models.roles).where(models.roles.c.id == role_b["id"])
            ).mappings().one()
            assert role_b_row["organization_id"] == organization_ids[1]
            assert role_b_row["name"] == "Tenant B Custom"
            assert set(
                session.scalars(
                    sa.select(models.role_permissions.c.permission_id).where(
                        models.role_permissions.c.role_id == role_b["id"]
                    )
                )
            ) == {permission_id}
            owner_role_b = session.execute(
                sa.select(models.roles).where(models.roles.c.id == owner_role_ids[1])
            ).mappings().one()
            assert owner_role_b["scope"] == "organization"
            assert session.scalar(
                sa.select(sa.func.count())
                .select_from(models.role_authority_grants)
                .where(models.role_authority_grants.c.role_id == owner_role_ids[1])
            ) == 1
            assert session.scalar(
                sa.select(models.warehouses.c.name).where(
                    models.warehouses.c.id == warehouse_ids[1]
                )
            ) != "Cross-tenant warehouse"
            assert session.scalar(
                sa.select(models.warehouses.c.organization_id).where(
                    models.warehouses.c.id == created.json()["id"]
                )
            ) == organization_ids[0]
            assert session.scalar(
                sa.select(sa.func.count())
                .select_from(models.warehouses)
                .where(models.warehouses.c.branch_id == extra_branch_a)
            ) == 1
    finally:
        client.app.dependency_overrides.clear()


def test_role_and_warehouse_service_scope_in_sqlite_and_postgres(
    cash_scope_session: Session,
) -> None:
    with cash_scope_session as session:
        tenants = [
            signup_tenant(
                session,
                {
                    "business_name": f"RBAC Service {suffix}",
                    "owner_name": f"Service Owner {suffix}",
                    "email": f"rbac-service-{suffix.lower()}@example.test",
                    "password": f"test-only-rbac-service-{suffix.lower()}",
                    "business_type": "blank",
                },
            )
            for suffix in ("A", "B")
        ]
        actor_a, actor_b = (str(tenant["user"]["id"]) for tenant in tenants)
        organization_a, organization_b = (
            str(tenant["organization"]["id"]) for tenant in tenants
        )
        role_b = create_role(session, "Service Role B", "organization", actor_b)
        permission_id = str(uuid4())
        session.execute(
            models.permissions.insert().values(
                id=permission_id,
                code=f"synthetic.service.permission.{uuid4().hex}",
                description="Synthetic permission for service scope regression",
                created_at=datetime.now(UTC),
            )
        )
        session.commit()

        for mutation in (
            lambda: update_role(session, role_b["id"], name="Foreign", actor_user_id=actor_a),
            lambda: update_role_permissions(session, role_b["id"], [permission_id], actor_a),
            lambda: delete_role(session, role_b["id"], actor_a),
        ):
            with pytest.raises(BusinessError) as rejected:
                mutation()
            assert rejected.value.code == "role_not_found"

        updated_permissions = update_role_permissions(
            session, role_b["id"], [permission_id], actor_b
        )
        assert updated_permissions["permissions_count"] == 1
        owner_role_b = _owner_role_id(session, organization_b)
        with pytest.raises(BusinessError) as owner_scope:
            update_role(session, owner_role_b, scope="branch", actor_user_id=actor_b)
        assert owner_scope.value.code == "owner_role_scope_immutable"
        with pytest.raises(BusinessError) as owner_permissions:
            update_role_permissions(session, owner_role_b, [], actor_b)
        assert owner_permissions.value.code == "owner_role_permissions_immutable"
        with pytest.raises(BusinessError) as owner_delete:
            delete_role(session, owner_role_b, actor_b)
        assert owner_delete.value.code == "owner_role_delete_forbidden"

        warehouse_a, warehouse_b = (
            str(
                session.scalar(
                    sa.select(models.warehouses.c.id).where(
                        models.warehouses.c.organization_id == organization_id
                    )
                )
            )
            for organization_id in (organization_a, organization_b)
        )
        with pytest.raises(BusinessError) as foreign_warehouse:
            update_warehouse(session, warehouse_b, name="Foreign", actor_user_id=actor_a)
        assert foreign_warehouse.value.code == "warehouse_not_found"
        own_warehouse = update_warehouse(
            session, warehouse_b, name="Own Service Warehouse", actor_user_id=actor_b
        )
        assert own_warehouse["name"] == "Own Service Warehouse"
        with pytest.raises(BusinessError) as duplicate:
            create_warehouse(
                session,
                str(tenants[0]["branch"]["id"]),
                "Duplicate",
                actor_user_id=actor_a,
            )
        assert duplicate.value.code == "warehouse_exists"
        with pytest.raises(BusinessError) as foreign_branch:
            create_warehouse(
                session,
                str(tenants[1]["branch"]["id"]),
                "Foreign",
                actor_user_id=actor_a,
            )
        assert foreign_branch.value.code == "invalid_branch"
        assert session.scalar(
            sa.select(models.warehouses.c.organization_id).where(
                models.warehouses.c.id == warehouse_a
            )
        ) == organization_a
