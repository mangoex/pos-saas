# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-branch-catalog-scope-synthetic-v1
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import app
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _client_with_db() -> tuple[TestClient, sessionmaker[Session]]:
    engine = sa.create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app), factory


def _signup(client: TestClient, email: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "business_name": f"Restaurante {email}",
            "owner_name": "Dueño",
            "email": email,
            "password": "Password123!",
            "business_type": "general",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _product(client: TestClient, headers: dict[str, str], sku: str) -> str:
    response = client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "name": f"Producto {sku}",
            "sku": sku,
            "category_name": "Comida",
            "station": "kitchen",
            "price_cents": 10000,
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


def _branch_supervisor(
    client: TestClient,
    factory: sessionmaker[Session],
    owner_headers: dict[str, str],
    branch_id: str,
) -> dict[str, str]:
    role = client.post(
        "/api/v1/roles",
        headers=owner_headers,
        json={"name": "Supervisor de sucursal", "scope": "branch"},
    )
    assert role.status_code == 200, role.text
    needed = {"branch.admin.access", "branch.staff.read", "catalog.branch.manage"}
    with factory() as session:
        permission_ids = {code: str(uuid4()) for code in needed}
        session.execute(
            models.permissions.insert(),
            [
                {
                    "id": permission_id,
                    "code": code,
                    "description": code,
                    "created_at": datetime.now(timezone.utc),
                }
                for code, permission_id in permission_ids.items()
            ],
        )
        session.execute(
            models.role_permissions.insert(),
            [
                {"role_id": role.json()["id"], "permission_id": permission_id}
                for permission_id in permission_ids.values()
            ],
        )
        session.commit()
    created = client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={
            "email": "supervisor@branchscope.test",
            "display_name": "Supervisor",
            "employee_code": "SUP001",
            "password": "Password123!",
            "role_id": role.json()["id"],
            "branch_id": branch_id,
        },
    )
    assert created.status_code == 200, created.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "supervisor@branchscope.test", "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['token']}"}


def test_branch_catalog_and_staff_do_not_use_pilot_tenant_or_cross_branch_scope() -> None:
    client, factory = _client_with_db()
    tenant_a = _signup(client, "owner-a@branch-catalog.test")
    tenant_b = _signup(client, "owner-b@branch-catalog.test")
    headers_a = {"Authorization": f"Bearer {tenant_a['token']}"}
    headers_b = {"Authorization": f"Bearer {tenant_b['token']}"}
    branch_a = str(tenant_a["branch"]["id"])
    branch_b = str(tenant_b["branch"]["id"])
    product_a = _product(client, headers_a, "A-BRANCH")
    product_b = _product(client, headers_b, "B-BRANCH")

    cross_update = client.put(
        f"/api/v1/branches/{branch_b}",
        headers=headers_a,
        json={"name": "Sucursal B alterada"},
    )
    cross_delete = client.delete(f"/api/v1/branches/{branch_b}", headers=headers_a)
    assert cross_update.status_code == 409
    assert cross_update.json()["detail"]["code"] == "branch_not_found"
    assert cross_delete.status_code == 409
    assert cross_delete.json()["detail"]["code"] == "branch_not_found"
    with factory() as session:
        untouched_branch_b = session.execute(
            sa.select(models.branches.c.name, models.branches.c.status).where(
                models.branches.c.id == branch_b
            )
        ).mappings().one()
        assert untouched_branch_b["name"] == tenant_b["branch"]["name"]
        assert untouched_branch_b["status"] == "active"

    branch_a2_response = client.post(
        "/api/v1/branches", headers=headers_a, json={"name": "Sucursal A2", "code": "A2"}
    )
    assert branch_a2_response.status_code == 200, branch_a2_response.text
    branch_a2 = str(branch_a2_response.json()["id"])
    supervisor_headers = _branch_supervisor(client, factory, headers_a, branch_a)

    own_catalog = client.get(
        "/api/v1/branch-administration/catalog/products", headers=supervisor_headers
    )
    assert own_catalog.status_code == 200, own_catalog.text
    catalog_ids = {row["id"] for row in own_catalog.json()}
    assert product_a in catalog_ids
    assert product_b not in catalog_ids
    staff = client.get("/api/v1/branch-administration/staff", headers=supervisor_headers)
    assert staff.status_code == 200
    assert any(row["email"] == "supervisor@branchscope.test" for row in staff.json())

    unavailable = client.put(
        f"/api/v1/branch-administration/catalog/products/{product_a}/availability",
        headers=supervisor_headers,
        json={"action": "unavailable"},
    )
    assert unavailable.status_code == 200, unavailable.text
    assert (
        client.put(
            f"/api/v1/branch-administration/catalog/products/{product_a}/availability?branch_id={branch_a2}",
            headers=supervisor_headers,
            json={"action": "unavailable"},
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/v1/branch-administration/catalog/products/{product_a}/availability?branch_id={branch_b}",
            headers=headers_b,
            json={"action": "unavailable"},
        ).status_code
        == 404
    )

    with factory() as session:
        session.execute(
            models.products.update()
            .where(models.products.c.id == product_a)
            .values(catalog_scope="branch", source_branch_id=branch_a)
        )
        session.commit()
    assert (
        client.put(
            f"/api/v1/branch-administration/catalog/products/{product_a}/availability?branch_id={branch_a2}",
            headers=headers_a,
            json={"action": "unavailable"},
        ).status_code
        == 404
    )

    with factory() as session:
        assert (
            session.execute(
                sa.select(models.branch_product_availability.c.is_available).where(
                    models.branch_product_availability.c.branch_id == branch_a,
                    models.branch_product_availability.c.product_id == product_a,
                )
            ).scalar_one()
            is False
        )
        assert (
            session.execute(
                sa.select(models.branch_product_availability.c.product_id).where(
                    models.branch_product_availability.c.branch_id.in_([branch_a2, branch_b]),
                    models.branch_product_availability.c.product_id == product_a,
                )
            ).all()
            == []
        )
    app.dependency_overrides.clear()
