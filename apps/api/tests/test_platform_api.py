# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-platform-tests-v1
from __future__ import annotations

import hashlib
import json
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from restaurant_os.models import (
    attendance_checks,
    audit_events,
    branch_product_availability,
    branches,
    business_units,
    cash_shifts,
    delivery_assignments,
    drivers,
    employee_code_registry,
    inventory_items,
    inventory_movements,
    inventory_units,
    legal_entities,
    metadata,
    modifier_groups,
    modifier_options,
    order_create_commands,
    order_events,
    order_line_consumption_snapshots,
    orders,
    organizations,
    payments,
    permissions,
    pos_session_handoffs,
    price_versions,
    print_jobs,
    product_categories,
    products,
    recipe_components,
    recipes,
    role_permissions,
    roles,
    sales_operation_snapshots,
    user_credentials,
    user_roles,
    users,
    warehouses,
)
from restaurant_os.operations import (
    ORGANIZATION_ID,
    AuthorizationError,
    _next_folio,
    require_permission,
)
from restaurant_os.platform_data import list_catalog_products
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

UTC = timezone.utc
ADMIN_USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000006"
ADMIN_ROLE_ID = "018f6f73-2d0a-74f0-8f1c-000000000005"
BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
_REQUEST_IDEMPOTENCY_SEQUENCE = 0


def _admin_headers() -> dict[str, str]:
    global _REQUEST_IDEMPOTENCY_SEQUENCE
    _REQUEST_IDEMPOTENCY_SEQUENCE += 1
    token = create_session_token({"sub": ADMIN_USER_ID}, get_settings().secret_key)
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": f"platform-test-request-{_REQUEST_IDEMPOTENCY_SEQUENCE}",
    }


_SHIFT_OPEN_SEQUENCE = 0


def _open_shift(
    client: TestClient, opening_cash_cents: int, headers: dict[str, str] | None = None
) -> Any:
    global _SHIFT_OPEN_SEQUENCE
    _SHIFT_OPEN_SEQUENCE += 1
    return client.post(
        "/api/v1/cash-shifts/open",
        headers={
            **(headers or _admin_headers()),
            "Idempotency-Key": f"test-shift-open-{_SHIFT_OPEN_SEQUENCE}",
        },
        json={
            "branch_id": BRANCH_ID,
            "register_id": "CAJA-01",
            "opening_cash_cents": opening_cash_cents,
        },
    )


def test_bootstrap_status_reads_seeded_platform_data() -> None:
    client = _client_with_seeded_database()

    response = client.get("/api/v1/platform/bootstrap-status", headers=_admin_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["counts"]["organizations"] == 1
    assert payload["counts"]["branches"] == 1
    assert payload["counts"]["warehouses"] == 1
    assert payload["counts"]["products"] == 3
    assert payload["primary_organization"]["name"] == "Kiwi Restaurante"
    assert payload["primary_branch"]["name"] == "Sucursal Piloto"


def test_admin_creates_business_unit_and_assigns_new_branch() -> None:
    client = _client_with_seeded_database()
    legal_entity_id = "018f6f73-2d0a-74f0-8f1c-000000000002"

    unit_response = client.post(
        "/api/v1/business-units",
        headers=_admin_headers(),
        json={
            "name": "Unidad Norte",
            "code": "NORTE",
            "unit_type": "restaurant",
            "legal_entity_id": legal_entity_id,
        },
    )
    assert unit_response.status_code == 200
    business_unit = unit_response.json()
    assert business_unit["code"] == "NORTE"

    branch_response = client.post(
        "/api/v1/branches",
        headers=_admin_headers(),
        json={
            "name": "Sucursal Norte",
            "code": "SUC-NORTE",
            "business_unit_id": business_unit["id"],
        },
    )
    assert branch_response.status_code == 200
    assert branch_response.json()["business_unit_id"] == business_unit["id"]

    branches_response = client.get("/api/v1/branches", headers=_admin_headers())
    assert branches_response.status_code == 200
    north = next(row for row in branches_response.json() if row["code"] == "SUC-NORTE")
    assert north["business_unit_name"] == "Unidad Norte"
    assert north["legal_entity_name"] == "Kiwi Restaurante - Razon Social Pendiente"


def test_admin_manages_driver_catalog_without_pii_in_audit() -> None:
    client = _client_with_seeded_database()
    payload = {
        "employee_code": "REP778",
        "name": "María Hernández",
        "license_number": "LIC-MOTO-7788",
        "motorcycle_plate": "ABC-12-34",
        "branch_id": BRANCH_ID,
        "phone": "6141234567",
        "address": "Calle Reforma 120, Colonia Centro",
        "emergency_contact_name": "José Hernández",
    }

    denied = client.get("/api/v1/drivers")
    assert denied.status_code == 403


    incomplete = client.post(
        "/api/v1/drivers",
        headers=_admin_headers(),
        json={**payload, "license_number": "   "},
    )
    assert incomplete.status_code == 409
    assert incomplete.json()["detail"]["code"] == "driver_fields_required"

    invalid_branch = client.post(
        "/api/v1/drivers",
        headers=_admin_headers(),
        json={**payload, "branch_id": "missing-branch"},
    )
    assert invalid_branch.status_code == 409
    assert invalid_branch.json()["detail"]["code"] == "driver_branch_not_found"

    created_response = client.post(
        "/api/v1/drivers",
        headers=_admin_headers(),
        json=payload,
    )
    assert created_response.status_code == 200
    created = created_response.json()
    assert created["status"] == "active"

    listed = client.get("/api/v1/drivers", headers=_admin_headers())
    assert listed.status_code == 200
    driver = next(row for row in listed.json() if row["id"] == created["id"])
    assert driver["branch_name"] == "Sucursal Piloto"
    assert driver["motorcycle_plate"] == "ABC-12-34"

    updated_response = client.put(
        f"/api/v1/drivers/{created['id']}",
        headers=_admin_headers(),
        json={**payload, "phone": "6147654321"},
    )
    assert updated_response.status_code == 200
    assert updated_response.json()["phone"] == "6147654321"

    deactivated = client.delete(
        f"/api/v1/drivers/{created['id']}",
        headers=_admin_headers(),
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "inactive"

    session_factory = _test_session_factory(client)
    with session_factory() as session:
        stored = session.execute(
            drivers.select().where(drivers.c.id == created["id"])
        ).mappings().one()
        assert stored["status"] == "inactive"
        events = session.execute(
            audit_events.select()
            .where(audit_events.c.entity_id == created["id"])
            .order_by(audit_events.c.created_at)
        ).mappings().all()
        assert [event["action"] for event in events] == [
            "driver.created",
            "driver.updated",
            "driver.deactivated",
        ]
        serialized_payloads = str([event["payload"] for event in events])
        for private_value in (
            payload["phone"],
            payload["address"],
            payload["license_number"],
            payload["motorcycle_plate"],
            "6147654321",
        ):
            assert private_value not in serialized_payloads
        assert events[1]["payload"]["changed_fields"] == ["phone"]


def test_administrative_reads_and_purchase_presentations_fail_closed() -> None:
    client = _client_with_seeded_database()
    token = create_session_token(
        {"sub": "unprivileged-user"}, get_settings().secret_key
    )
    insufficient_headers = {
        "Authorization": f"Bearer {token}"
    }

    administrative_reads = (
        "/api/v1/branches",
        "/api/v1/roles",
        "/api/v1/users",
        "/api/v1/purchase-presentations",
    )
    for path in administrative_reads:
        assert client.get(path).status_code == 401
        assert client.get(path, headers=insufficient_headers).status_code == 403

    # The seeded administrator retains the existing corporate administration path.
    for path in administrative_reads:
        assert client.get(path, headers=_admin_headers()).status_code == 200

    for method, path in (
        (client.post, "/api/v1/purchase-presentations"),
        (client.put, "/api/v1/purchase-presentations/missing"),
        (client.put, "/api/v1/purchase-presentations/missing/price"),
    ):
        response = method(path, headers=insufficient_headers, json={})
        assert response.status_code == 403
    assert client.post(
        "/api/v1/roles",
        headers=insufficient_headers,
        json={"name": "No autorizado", "scope": "branch"},
    ).status_code == 403


def test_administrative_lists_exclude_foreign_organization_rows() -> None:
    client = _client_with_seeded_database()
    now = datetime(2026, 8, 24, tzinfo=UTC)
    with _test_session_factory(client)() as session:
        session.execute(organizations.insert().values(
            id="foreign-org", name="Foreign", status="active", created_at=now, updated_at=now,
        ))
        session.execute(legal_entities.insert().values(
            id="foreign-legal", organization_id="foreign-org", name="Foreign legal",
            tax_id=None, status="active", created_at=now, updated_at=now,
        ))
        session.execute(business_units.insert().values(
            id="foreign-unit", organization_id="foreign-org", legal_entity_id="foreign-legal",
            name="Foreign unit", code="FOREIGN", unit_type="restaurant", status="active",
            created_at=now, updated_at=now,
        ))
        session.execute(branches.insert().values(
            id="foreign-branch", organization_id="foreign-org", legal_entity_id="foreign-legal",
            business_unit_id="foreign-unit", name="Foreign branch", code="FOREIGN",
            timezone="UTC", status="active", created_at=now, updated_at=now,
        ))
        session.execute(branches.insert().values(
            id="foreign-branch-without-warehouse", organization_id="foreign-org",
            legal_entity_id="foreign-legal", business_unit_id="foreign-unit",
            name="Foreign branch without warehouse", code="FOREIGN-NO-WH",
            timezone="UTC", status="active", created_at=now, updated_at=now,
        ))
        session.execute(warehouses.insert().values(
            id="foreign-warehouse", organization_id="foreign-org", branch_id="foreign-branch",
            name="Foreign warehouse", status="active", created_at=now, updated_at=now,
        ))
        session.execute(roles.insert().values(
            id="foreign-role", organization_id="foreign-org", name="Foreign role",
            scope="organization", created_at=now,
        ))
        session.execute(users.insert().values(
            id="foreign-user", organization_id="foreign-org", email="foreign@example.test",
            display_name="Foreign user", status="active", created_at=now, updated_at=now,
        ))
        session.commit()

    headers = _admin_headers()
    branch_rows = client.get("/api/v1/branches", headers=headers).json()
    role_rows = client.get("/api/v1/roles", headers=headers).json()
    user_rows = client.get("/api/v1/users", headers=headers).json()
    assert "foreign-branch" not in {row["id"] for row in branch_rows}
    assert "foreign-role" not in {row["id"] for row in role_rows}
    assert "foreign-user" not in {row["id"] for row in user_rows}
    cross_organization_warehouse = client.post(
        "/api/v1/warehouses",
        headers=headers,
        json={"branch_id": "foreign-branch-without-warehouse", "name": "Invalid"},
    )
    assert cross_organization_warehouse.status_code == 409
    assert cross_organization_warehouse.json()["detail"]["code"] == "invalid_branch"


def test_supervisor_purchase_permissions_read_and_create_presentations_only() -> None:
    client = _client_with_seeded_database()
    supplier_response = client.post(
        "/api/v1/suppliers",
        headers=_admin_headers(),
        json={
            "code": "SUP-PRES",
            "commercial_name": "Proveedor Supervisor",
            "delivery_days": [],
            "payment_methods": [],
        },
    )
    assert supplier_response.status_code == 200
    supplier = supplier_response.json()
    now = datetime(2026, 8, 24, tzinfo=UTC)
    supervisor_id = "018f6f73-2d0a-74f0-8f1c-000000009971"
    supervisor_role_id = "018f6f73-2d0a-74f0-8f1c-000000009972"
    with _test_session_factory(client)() as session:
        session.execute(roles.insert().values(
            id=supervisor_role_id, organization_id=ORGANIZATION_ID,
            name="Supervisor compras", scope="branch", created_at=now,
        ))
        session.execute(users.insert().values(
            id=supervisor_id, organization_id=ORGANIZATION_ID,
            email="supervisor-purchases@example.test", display_name="Supervisor compras",
            status="active", created_at=now, updated_at=now,
        ))
        permission_ids = dict(session.execute(sa.select(
            permissions.c.code, permissions.c.id
        ).where(permissions.c.code.in_({"purchases.read", "purchases.manage"}))).all())
        session.execute(role_permissions.insert(), [
            {"role_id": supervisor_role_id, "permission_id": permission_ids["purchases.read"]},
            {"role_id": supervisor_role_id, "permission_id": permission_ids["purchases.manage"]},
        ])
        session.execute(user_roles.insert().values(
            user_id=supervisor_id, role_id=supervisor_role_id, branch_id=BRANCH_ID,
        ))
        session.commit()
    token = create_session_token({"sub": supervisor_id}, get_settings().secret_key)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/purchase-presentations", headers=headers).status_code == 200
    created = client.post(
        "/api/v1/purchase-presentations",
        headers=headers,
        json={
            "supplier_id": supplier["id"],
            "item_id": "018f6f73-2d0a-74f0-8f1c-000000000311",
            "code": "SUP-PRES-01",
            "name": "Presentación Supervisor", "commercial_quantity": "1",
            "commercial_unit_id": "018f6f73-2d0a-74f0-8f1c-000000000303",
            "base_unit_id": "018f6f73-2d0a-74f0-8f1c-000000000301",
            "base_unit_yield": "1000", "usable_content": "1000", "last_net_price": "25",
        },
    )
    assert created.status_code == 200
    assert client.put(
        f"/api/v1/purchase-presentations/{created.json()['id']}", headers=headers,
        json={"name": "No autorizado"},
    ).status_code == 403
    assert client.put(
        f"/api/v1/purchase-presentations/{created.json()['id']}/price", headers=headers,
        json={"net_price": "30"},
    ).status_code == 403


def test_attendance_codes_checks_report_and_audit_are_authoritative() -> None:
    client = _client_with_seeded_database()

    assigned = client.put(
        f"/api/v1/users/{ADMIN_USER_ID}",
        headers=_admin_headers(),
        json={"employee_code": "  emp001  "},
    )
    assert assigned.status_code == 200
    assert assigned.json()["employee_code"] == "EMP001"
    listed_users = client.get("/api/v1/users", headers=_admin_headers())
    assert listed_users.status_code == 200
    admin = next(row for row in listed_users.json() if row["id"] == ADMIN_USER_ID)
    assert admin["employee_code"] == "EMP001"

    duplicate_driver = client.post(
        "/api/v1/drivers",
        headers=_admin_headers(),
        json={
            "employee_code": "emp001",
            "name": "Clave Duplicada",
            "license_number": "LIC-DUP",
            "motorcycle_plate": "DUP-001",
            "branch_id": BRANCH_ID,
            "phone": "6140000000",
            "address": "Base Centro",
            "emergency_contact_name": "Contacto",
        },
    )
    assert duplicate_driver.status_code == 409
    assert duplicate_driver.json()["detail"]["code"] == "employee_code_already_exists"

    invalid_format = client.post(
        "/api/v1/attendance/checks",
        headers=_admin_headers(),
        json={"employee_code": "AB-123", "branch_id": BRANCH_ID},
    )
    assert invalid_format.status_code == 409
    assert invalid_format.json()["detail"]["code"] == "employee_code_invalid_format"

    invalid = client.post(
        "/api/v1/attendance/checks",
        headers=_admin_headers(),
        json={"employee_code": "ZZ9999", "branch_id": BRANCH_ID},
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "employee_code_invalid"

    first = client.post(
        "/api/v1/attendance/checks",
        headers=_admin_headers(),
        json={"employee_code": "emp001", "branch_id": BRANCH_ID},
    )
    assert first.status_code == 200
    assert first.json()["daily_sequence"] == 1
    assert first.json()["display_state"] == "single"

    single_report = client.get(
        "/api/v1/attendance/checks",
        headers=_admin_headers(),
        params={
            "employee_code": "EMP001",
            "day": first.json()["local_date"],
            "branch_id": BRANCH_ID,
        },
    )
    assert single_report.status_code == 200
    assert [row["display_state"] for row in single_report.json()] == ["single"]

    second = client.post(
        "/api/v1/attendance/checks",
        headers=_admin_headers(),
        json={"employee_code": "EMP001", "branch_id": BRANCH_ID},
    )
    assert second.status_code == 200
    assert second.json()["daily_sequence"] == 2
    assert second.json()["display_state"] == "exit"

    third = client.post(
        "/api/v1/attendance/checks",
        headers=_admin_headers(),
        json={"employee_code": "EMP001", "branch_id": BRANCH_ID},
    )
    assert third.status_code == 409
    assert third.json()["detail"]["code"] == "attendance_daily_limit_reached"

    full_report = client.get(
        "/api/v1/attendance/checks",
        headers=_admin_headers(),
        params={"employee_code": "emp001", "day": first.json()["local_date"]},
    )
    assert full_report.status_code == 200
    rows = full_report.json()
    assert [row["display_state"] for row in rows] == ["exit", "entry"]
    assert {row["branch_name"] for row in rows} == {"Sucursal Piloto"}
    assert all(row["branch_timezone"] == "America/Chihuahua" for row in rows)

    month_report = client.get(
        "/api/v1/attendance/checks",
        headers=_admin_headers(),
        params={"month": first.json()["local_date"][:7], "branch_id": BRANCH_ID},
    )
    assert month_report.status_code == 200
    assert len(month_report.json()) == 2
    conflicting_period = client.get(
        "/api/v1/attendance/checks",
        headers=_admin_headers(),
        params={"day": first.json()["local_date"], "month": first.json()["local_date"][:7]},
    )
    assert conflicting_period.status_code == 409
    assert conflicting_period.json()["detail"]["code"] == "attendance_period_conflict"

    driver = client.post(
        "/api/v1/drivers",
        headers=_admin_headers(),
        json={
            "employee_code": "DRV123",
            "name": "Repartidor Checador",
            "license_number": "LIC-CHECK",
            "motorcycle_plate": "CHK-123",
            "branch_id": BRANCH_ID,
            "phone": "6140000010",
            "address": "Base Centro",
            "emergency_contact_name": "Contacto",
        },
    )
    assert driver.status_code == 200
    driver_check = client.post(
        "/api/v1/attendance/checks",
        headers=_admin_headers(),
        json={"employee_code": "drv123", "branch_id": BRANCH_ID},
    )
    assert driver_check.status_code == 200
    assert driver_check.json()["subject_type"] == "driver"
    assert driver_check.json()["subject_id"] == driver.json()["id"]

    with _test_session_factory(client)() as session:
        registry_rows = session.execute(employee_code_registry.select()).mappings().all()
        owners = {
            row["employee_code"]: (row["subject_type"], row["subject_id"])
            for row in registry_rows
        }
        assert owners == {
            "EMP001": ("user", ADMIN_USER_ID),
            "DRV123": ("driver", driver.json()["id"]),
        }
        stored = session.execute(attendance_checks.select()).mappings().all()
        assert len(stored) == 3
        events = session.execute(
            audit_events.select()
            .where(audit_events.c.entity_type == "attendance_check")
            .order_by(audit_events.c.created_at)
        ).mappings().all()
        assert len(events) == 3
        serialized = str([event["payload"] for event in events])
        assert "EMP001" not in serialized
        assert admin["display_name"] not in serialized
        user_events = session.execute(
            audit_events.select().where(
                audit_events.c.entity_id == ADMIN_USER_ID,
                audit_events.c.action == "user.updated",
            )
        ).mappings().all()
        assert user_events[-1]["payload"]["employee_code_changed"] is True
        assert "EMP001" not in str(user_events[-1]["payload"])


def test_admin_can_add_own_employee_code_from_full_edit_form() -> None:
    client = _client_with_seeded_database()
    with _test_session_factory(client)() as session:
        original_hash = session.execute(
            user_credentials.select().where(
                user_credentials.c.user_id == ADMIN_USER_ID
            )
        ).mappings().one()["password_hash"]

    response = client.put(
        f"/api/v1/users/{ADMIN_USER_ID}",
        headers=_admin_headers(),
        json={
            "email": "admin@kiwi.local",
            "display_name": "Administrador Kiwi",
            "employee_code": "ABC123",
            "password": "",
            "role_id": ADMIN_ROLE_ID,
            "branch_id": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["employee_code"] == "ABC123"
    with _test_session_factory(client)() as session:
        assignments = session.execute(
            user_roles.select().where(user_roles.c.user_id == ADMIN_USER_ID)
        ).mappings().all()
        assert [assignment["role_id"] for assignment in assignments] == [ADMIN_ROLE_ID]
        stored_hash = session.execute(
            user_credentials.select().where(
                user_credentials.c.user_id == ADMIN_USER_ID
            )
        ).mappings().one()["password_hash"]
        assert stored_hash == original_hash


def test_permission_denial_rolls_back_pending_role_removal_before_audit() -> None:
    client = _client_with_seeded_database()
    session_factory = _test_session_factory(client)

    with session_factory() as session:
        session.execute(
            user_roles.delete().where(user_roles.c.user_id == ADMIN_USER_ID)
        )
        with pytest.raises(AuthorizationError):
            require_permission(session, ADMIN_USER_ID, "admin.manage")

    with session_factory() as session:
        assignment = session.execute(
            user_roles.select().where(
                user_roles.c.user_id == ADMIN_USER_ID,
                user_roles.c.role_id == ADMIN_ROLE_ID,
            )
        ).mappings().first()
        denial = session.execute(
            audit_events.select()
            .where(
                audit_events.c.action == "authorization.denied",
                audit_events.c.actor_user_id == ADMIN_USER_ID,
            )
            .order_by(audit_events.c.created_at.desc())
        ).mappings().first()

        assert assignment is not None
        assert denial is not None
        assert denial["payload"]["reason"] == "no_scoped_role"


def test_branch_scoped_admin_permission_cannot_manage_corporate_identity() -> None:
    client = _client_with_seeded_database()
    now = datetime(2026, 8, 30, 12, 30, tzinfo=UTC)
    user_id = "018f6f73-2d0a-74f0-8f1c-000000009951"
    role_id = "018f6f73-2d0a-74f0-8f1c-000000009952"

    with _test_session_factory(client)() as session:
        admin_permission_id = session.execute(
            sa.select(permissions.c.id).where(permissions.c.code == "admin.manage")
        ).scalar_one()
        session.execute(
            roles.insert().values(
                id=role_id,
                organization_id=ORGANIZATION_ID,
                name="Administrador limitado a sucursal",
                scope="branch",
                created_at=now,
            )
        )
        session.execute(
            users.insert().values(
                id=user_id,
                organization_id=ORGANIZATION_ID,
                email="branch-admin@example.test",
                display_name="Administrador de sucursal",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            role_permissions.insert().values(
                role_id=role_id, permission_id=admin_permission_id
            )
        )
        session.execute(
            user_roles.insert().values(
                user_id=user_id, role_id=role_id, branch_id=BRANCH_ID
            )
        )
        session.commit()

    token = create_session_token({"sub": user_id}, get_settings().secret_key)
    headers = {"Authorization": f"Bearer {token}"}
    for response in (
        client.get("/api/v1/roles", headers=headers),
        client.post(
            "/api/v1/roles",
            headers=headers,
            json={"name": "Escalación", "scope": "organization"},
        ),
    ):
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "permission_denied"

    assert client.get("/api/v1/roles", headers=_admin_headers()).status_code == 200


def test_attendance_report_respects_branch_scope() -> None:
    client = _client_with_seeded_database()
    fixture = _branch_admin_fixture(client)
    assigned = client.put(
        f"/api/v1/users/{fixture['supervisor_id']}",
        headers=_admin_headers(),
        json={"employee_code": "SUP001"},
    )
    assert assigned.status_code == 200
    supervisor_headers = _login_headers(
        client, "supervisor.norte@kiwi.local", "Temporal123+"
    )
    checked = client.post(
        "/api/v1/attendance/checks",
        headers=supervisor_headers,
        json={"employee_code": "SUP001", "branch_id": fixture["branch_id"]},
    )
    assert checked.status_code == 200
    own_report = client.get("/api/v1/attendance/checks", headers=supervisor_headers)
    assert own_report.status_code == 200
    assert {row["branch_id"] for row in own_report.json()} == {fixture["branch_id"]}
    forbidden = client.get(
        "/api/v1/attendance/checks",
        headers=supervisor_headers,
        params={"branch_id": BRANCH_ID},
    )
    assert forbidden.status_code == 403


def test_delivery_order_assigns_available_branch_driver_and_preserves_history() -> None:
    client = _client_with_seeded_database()
    driver_payload = {
        "employee_code": "DRV001",
        "name": "Daniel Repartidor",
        "license_number": "LIC-DELIVERY-1",
        "motorcycle_plate": "MOTO-101",
        "branch_id": BRANCH_ID,
        "phone": "6141112233",
        "address": "Base operativa Centro",
        "emergency_contact_name": "Contacto Daniel",
    }
    driver_response = client.post(
        "/api/v1/drivers",
        headers=_admin_headers(),
        json=driver_payload,
    )
    assert driver_response.status_code == 200
    driver = driver_response.json()

    available = client.get(
        "/api/v1/delivery/drivers/available",
        headers=_admin_headers(),
        params={"branch_id": BRANCH_ID},
    )
    assert available.status_code == 200
    assert available.json() == [
        {
            "id": driver["id"],
            "name": "Daniel Repartidor",
            "phone": "6141112233",
            "motorcycle_plate": "MOTO-101",
        }
    ]

    invalid_type = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "driver_id": driver["id"],
            "lines": [
                {
                    "product_id": "018f6f73-2d0a-74f0-8f1c-000000000111",
                    "quantity": 1,
                }
            ],
        },
    )
    assert invalid_type.status_code == 409
    assert invalid_type.json()["detail"]["code"] == "driver_assignment_delivery_only"

    customer_response = client.post(
        "/api/v1/customers",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "name": "Cliente Entrega",
            "phones": [{"number": "6691239876", "is_primary": True}],
        },
    )
    assert customer_response.status_code == 200
    customer = customer_response.json()
    address_response = client.post(
        f"/api/v1/customers/{customer['id']}/addresses",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "alias": "Casa",
            "street": "Avenida Entrega",
            "exterior_number": "25",
            "neighborhood": "Centro",
            "postal_code": "82000",
            "city": "Mazatlan",
            "municipality": "Mazatlan",
            "state": "Sinaloa",
            "is_default": True,
        },
    )
    assert address_response.status_code == 200
    address = address_response.json()
    assert (
        client.post(
            "/api/v1/cash-shifts/open",
            headers={**_admin_headers(), "Idempotency-Key": "delivery-shift-open"},
            json={"branch_id": BRANCH_ID, "register_id": "CAJA-01", "opening_cash_cents": 50000},
        ).status_code
        == 200
    )

    order_response = client.post(
        "/api/v1/orders",
        headers={**_admin_headers(), "Idempotency-Key": "delivery-order-recovery-001"},
        json={
            "branch_id": BRANCH_ID,
            "order_type": "delivery",
            "payment_method_intent": "cash",
            "customer_id": customer["id"],
            "delivery_address_id": address["id"],
            "driver_id": driver["id"],
            "lines": [
                {
                    "product_id": "018f6f73-2d0a-74f0-8f1c-000000000111",
                    "quantity": 2,
                    "notes": "Tocar puerta y preguntar por Cliente Entrega",
                }
            ],
        },
    )
    assert order_response.status_code == 200
    order = order_response.json()
    assignment = order["delivery_assignment"]
    assert assignment["driver_id"] == driver["id"]
    assert assignment["driver_name_snapshot"] == "Daniel Repartidor"
    assert assignment["customer_name_snapshot"] == "Cliente Entrega"
    assert assignment["order_total_cents"] == order["total_cents"]
    assert assignment["line_count"] == 1
    assert assignment["item_quantity"] == 2
    recovered = client.post(
        "/api/v1/orders/recover",
        headers={**_admin_headers(), "Idempotency-Key": "delivery-order-recovery-001"},
        json={},
    )
    assert recovered.status_code == 200
    assert recovered.json() == order

    detail = client.get(
        f"/api/v1/orders/{order['id']}",
        headers=_admin_headers(),
    )
    assert detail.status_code == 200
    assert detail.json()["delivery_assignment"]["id"] == assignment["id"]

    history = client.get(
        f"/api/v1/drivers/{driver['id']}/deliveries",
        headers=_admin_headers(),
    )
    assert history.status_code == 200
    assert history.json()[0]["folio"] == order["folio"]
    assert history.json()[0]["customer_name_snapshot"] == "Cliente Entrega"
    assert history.json()[0]["order_total_cents"] == order["total_cents"]

    assert (
        client.delete(
            f"/api/v1/drivers/{driver['id']}",
            headers=_admin_headers(),
        ).status_code
        == 200
    )
    unavailable = client.get(
        "/api/v1/delivery/drivers/available",
        headers=_admin_headers(),
        params={"branch_id": BRANCH_ID},
    )
    assert unavailable.status_code == 200
    assert unavailable.json() == []
    rejected = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "order_type": "delivery",
            "payment_method_intent": "cash",
            "customer_id": customer["id"],
            "delivery_address_id": address["id"],
            "driver_id": driver["id"],
            "lines": [
                {
                    "product_id": "018f6f73-2d0a-74f0-8f1c-000000000111",
                    "quantity": 1,
                }
            ],
        },
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "delivery_driver_unavailable"

    session_factory = _test_session_factory(client)
    with session_factory() as session:
        stored_assignments = session.execute(
            delivery_assignments.select()
        ).mappings().all()
        assert len(stored_assignments) == 1
        assert stored_assignments[0]["order_id"] == order["id"]
        driver_events = session.execute(
            order_events.select().where(
                order_events.c.order_id == order["id"],
                order_events.c.event_type == "DRIVER_ASSIGNED",
            )
        ).mappings().all()
        assert len(driver_events) == 1
        assignment_audit = session.execute(
            audit_events.select().where(
                audit_events.c.entity_id == assignment["id"],
                audit_events.c.action == "delivery.driver_assigned",
            )
        ).mappings().one()
        serialized_audit = str(assignment_audit["payload"])
        assert "Avenida Entrega" not in serialized_audit
        assert driver_payload["phone"] not in serialized_audit


        command_snapshot = session.execute(
            order_create_commands.select().where(order_create_commands.c.order_id == order["id"])
        ).mappings().one()["response_snapshot"]
        serialized_command = json.dumps(command_snapshot, ensure_ascii=False)
        for sensitive_value in (
            customer["id"],
            "Cliente Entrega",
            "Avenida Entrega",
            driver["id"],
            "Daniel Repartidor",
            "Tocar puerta",
        ):
            assert sensitive_value not in serialized_command
        session.execute(
            order_line_consumption_snapshots.delete().where(
                order_line_consumption_snapshots.c.order_id == order["id"]
            )
        )
        session.commit()

    incomplete_recovery = client.post(
        "/api/v1/orders/recover",
        headers={**_admin_headers(), "Idempotency-Key": "delivery-order-recovery-001"},
        json={},
    )
    assert incomplete_recovery.status_code == 409
    assert incomplete_recovery.json()["detail"]["code"] == "order_create_replay_incomplete"
def test_superadmin_can_login_and_create_active_admin_user() -> None:
    client = _client_with_seeded_database()

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "mangoex@gmail.com", "password": "superadmin-test-password"},

    )
    assert login_response.status_code == 200
    session = login_response.json()
    assert session["user"]["email"] == "mangoex@gmail.com"
    assert session["user"]["status"] == "active"
    assert session["user"]["is_superadmin"] is True
    assert "Administrador corporativo" in session["user"]["roles"]
    assert "admin.manage" in session["user"]["permissions"]
    assert "catalog.manage" in session["user"]["permissions"]
    assert session["token"]

    headers = {"Authorization": f"Bearer {session['token']}"}
    missing_code = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "sin.codigo@kiwi.local",
            "display_name": "Sin Código",
            "password": "Temporal123+",
        },
    )
    assert missing_code.status_code == 409
    assert missing_code.json()["detail"]["code"] == "employee_code_required"
    user_response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "admin.negocio@kiwi.local",
            "display_name": "Admin Negocio",
            "employee_code": "ADM001",
            "password": "Temporal123+",
        },
    )
    assert user_response.status_code == 200
    assert user_response.json()["status"] == "active"

    created_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin.negocio@kiwi.local", "password": "Temporal123+"},
    )
    assert created_login.status_code == 200
    assert created_login.json()["user"]["display_name"] == "Admin Negocio"
    assert created_login.json()["user"]["is_superadmin"] is False


def test_organizations_and_branches_are_listed() -> None:
    client = _client_with_seeded_database()

    organizations_response = client.get("/api/v1/organizations", headers=_admin_headers())
    branches_response = client.get("/api/v1/branches", headers=_admin_headers())

    assert organizations_response.status_code == 200
    assert branches_response.status_code == 200
    assert organizations_response.json()[0]["name"] == "Kiwi Restaurante"
    assert branches_response.json()[0]["warehouse_name"] == "Almacen Sucursal Piloto"


def test_catalog_products_are_listed_with_prices_and_availability() -> None:
    client = _client_with_seeded_database()

    response = client.get("/api/v1/catalog/products", headers=_admin_headers())
    categories_response = client.get("/api/v1/categories", headers=_admin_headers())

    assert response.status_code == 200
    assert categories_response.status_code == 200
    products_payload = response.json()
    categories_by_name = {
        category["name"]: category["id"] for category in categories_response.json()
    }
    assert [product["sku"] for product in products_payload] == [
        "KIWI-SODA",
        "KIWI-BURGER",
        "KIWI-FRIES",
    ]
    assert products_payload[0]["price_cents"] == 3000
    assert products_payload[0]["currency"] == "MXN"
    assert products_payload[0]["is_available"] is True
    assert all(
        product["category_id"] == categories_by_name[product["category_name"]]
        for product in products_payload
    )


def test_catalog_inherits_branch_availability_and_keeps_products_without_price_visible() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    with Session(engine) as session:
        _seed(session)
        product_id = (
            session.execute(products.select().where(products.c.sku == "KIWI-BURGER"))
            .mappings()
            .one()["id"]
        )
        session.execute(
            branch_product_availability.delete().where(
                branch_product_availability.c.branch_id == BRANCH_ID,
                branch_product_availability.c.product_id == product_id,
            )
        )
        session.commit()

        inherited = list_catalog_products(session, BRANCH_ID)
        assert any(item["id"] == product_id and item["is_available"] for item in inherited)

        session.execute(
            branch_product_availability.insert().values(
                branch_id=BRANCH_ID,
                product_id=product_id,
                is_available=False,
                updated_at=datetime.now(UTC),
            )
        )
        session.commit()
        unavailable = list_catalog_products(session, BRANCH_ID)
        assert all(item["id"] != product_id for item in unavailable)

        session.execute(price_versions.delete().where(price_versions.c.product_id == product_id))
        session.execute(
            branch_product_availability.delete().where(
                branch_product_availability.c.product_id == product_id
            )
        )
        session.commit()
        incomplete = list_catalog_products(session)
        product = next(item for item in incomplete if item["id"] == product_id)
        assert product["price_cents"] is None


def test_category_option_configuration_projects_fail_closed_by_branch() -> None:
    client = _client_with_seeded_database()
    products_response = client.get("/api/v1/catalog/products", headers=_admin_headers())
    burger = next(
        product for product in products_response.json() if product["sku"] == "KIWI-BURGER"
    )
    fries = next(
        product for product in products_response.json() if product["sku"] == "KIWI-FRIES"
    )
    category_id = burger["category_id"]

    group_response = client.post(
        f"/api/v1/categories/{category_id}/selection-group",
        headers=_admin_headers(),
        json={"code": "size", "name": "Tamaño", "status": "inactive"},
    )
    assert group_response.status_code == 200
    group_id = group_response.json()["id"]
    value_response = client.post(
        f"/api/v1/catalog/category-option-groups/{group_id}/values",
        headers=_admin_headers(),
        json={"code": "small", "name": "Chica", "display_order": 10},
    )
    assert value_response.status_code == 200
    value_id = value_response.json()["id"]
    assignment = client.put(
        f"/api/v1/catalog/category-option-groups/{group_id}/assignments/{burger['id']}",
        headers=_admin_headers(),
        json={"option_value_id": value_id},
    )
    assert assignment.status_code == 200
    incomplete_activation = client.post(
        f"/api/v1/categories/{category_id}/selection-group",
        headers=_admin_headers(),
        json={"code": "size", "name": "Tamaño", "status": "active"},
    )
    assert incomplete_activation.status_code == 409
    assert incomplete_activation.json()["detail"]["code"] == "category_option_group_incomplete"
    assignment = client.put(
        f"/api/v1/catalog/category-option-groups/{group_id}/assignments/{fries['id']}",
        headers=_admin_headers(),
        json={"option_value_id": value_id},
    )
    assert assignment.status_code == 200
    activated = client.post(
        f"/api/v1/categories/{category_id}/selection-group",
        headers=_admin_headers(),
        json={"code": "size", "name": "Tamaño", "status": "active"},
    )
    assert activated.status_code == 200
    categories = client.get(
        f"/api/v1/categories?branch_id={BRANCH_ID}", headers=_admin_headers()
    )
    configured = next(category for category in categories.json() if category["id"] == category_id)
    assert configured["selection_group"]["values"] == [
        {"id": value_id, "code": "small", "name": "Chica", "display_order": 10}
    ]
    branch_products = client.get(
        f"/api/v1/catalog/products?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).json()
    selected = [product for product in branch_products if product["category_id"] == category_id]
    assert {product["id"] for product in selected} == {burger["id"], fries["id"]}
    assert all(product["selection"]["value_id"] == value_id for product in selected)

    coverage = client.get(
        f"/api/v1/catalog/category-option-groups/{group_id}/coverage", headers=_admin_headers()
    )
    assert coverage.status_code == 200 and coverage.json()["complete"] is True
    assert {product["id"] for product in coverage.json()["products"]} == {
        burger["id"], fries["id"]
    }
    assert all(
        product["assignment"]["value_id"] == value_id
        for product in coverage.json()["products"]
    )
    session_factory = _test_session_factory(client)
    with session_factory() as session:
        assert session.execute(
            audit_events.select().where(
                audit_events.c.action == "category_option_assignment.created"
            )
        ).first() is not None


def test_category_option_rejects_inactive_values_and_allows_same_code_per_category() -> None:
    client = _client_with_seeded_database()
    catalog = client.get("/api/v1/catalog/products", headers=_admin_headers()).json()
    burger = next(product for product in catalog if product["sku"] == "KIWI-BURGER")
    soda = next(product for product in catalog if product["sku"] == "KIWI-SODA")
    first_group = client.post(
        f"/api/v1/categories/{burger['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño", "status": "inactive"},
    ).json()
    second_group = client.post(
        f"/api/v1/categories/{soda['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño", "status": "inactive"},
    )
    assert second_group.status_code == 200
    inactive = client.post(
        f"/api/v1/catalog/category-option-groups/{first_group['id']}/values",
        headers=_admin_headers(), json={"code": "small", "name": "Chica", "status": "inactive"},
    ).json()
    rejected = client.put(
        f"/api/v1/catalog/category-option-groups/{first_group['id']}/assignments/{burger['id']}",
        headers=_admin_headers(), json={"option_value_id": inactive["id"]},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "category_option_value_inactive"
    replacement = client.post(
        f"/api/v1/catalog/category-option-groups/{first_group['id']}/values",
        headers=_admin_headers(), json={"code": "large", "name": "Grande", "status": "active"},
    ).json()
    reassigned = client.put(
        f"/api/v1/catalog/category-option-groups/{first_group['id']}/assignments/{burger['id']}",
        headers=_admin_headers(), json={"option_value_id": replacement["id"]},
    )
    assert reassigned.status_code == 200
    coverage = client.get(
        f"/api/v1/catalog/category-option-groups/{first_group['id']}/coverage",
        headers=_admin_headers(),
    ).json()
    burger_coverage = next(
        product for product in coverage["products"] if product["id"] == burger["id"]
    )
    assert burger_coverage["assignment"]["value_id"] == replacement["id"]


def test_category_option_admin_reads_require_catalog_manage_not_pos_operate() -> None:
    client = _client_with_seeded_database()
    session_factory = _test_session_factory(client)
    with session_factory() as session:
        permission_id = session.execute(
            permissions.select().where(permissions.c.code == "pos.operate")
        ).scalar_one_or_none()
        if permission_id:
            session.execute(
                role_permissions.delete().where(role_permissions.c.permission_id == permission_id)
            )
            session.commit()
    assert client.get("/api/v1/categories", headers=_admin_headers()).status_code == 200
    assert client.get("/api/v1/catalog/products", headers=_admin_headers()).status_code == 200
    assert client.get(
        f"/api/v1/categories?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).status_code == 403


def test_category_option_contract_and_active_value_invariants_are_stable() -> None:
    client = _client_with_seeded_database()
    catalog = client.get("/api/v1/catalog/products", headers=_admin_headers()).json()
    burger = next(product for product in catalog if product["sku"] == "KIWI-BURGER")
    group = client.post(
        f"/api/v1/categories/{burger['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño", "status": "inactive"},
    ).json()
    value = client.post(
        f"/api/v1/catalog/category-option-groups/{group['id']}/values",
        headers=_admin_headers(), json={"code": "small", "name": "Chica", "status": "active"},
    ).json()
    assert client.put(
        f"/api/v1/catalog/category-option-groups/{group['id']}/assignments/{burger['id']}",
        headers=_admin_headers(), json={"option_value_id": value["id"]},
    ).status_code == 200
    replacement = client.post(
        f"/api/v1/catalog/category-option-groups/{group['id']}/values",
        headers=_admin_headers(), json={"code": "large", "name": "Grande", "display_order": 30},
    ).json()
    assert client.put(
        f"/api/v1/catalog/category-option-groups/{group['id']}/assignments/{burger['id']}",
        headers=_admin_headers(), json={"option_value_id": replacement["id"]},
    ).status_code == 200
    assert client.post(
        f"/api/v1/categories/{burger['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño", "status": "active"},
    ).status_code == 409  # The category has another unassigned active product.
    rejected_value = client.put(
        f"/api/v1/catalog/category-option-groups/{group['id']}/values/{value['id']}",
        headers=_admin_headers(), json={"code": "small", "name": "Chica", "status": "wat"},
    )
    assert rejected_value.status_code == 409
    assert rejected_value.json()["detail"]["code"] == "category_option_value_invalid_status"
    rejected_group = client.post(
        f"/api/v1/categories/{burger['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "INVALID SPACE", "name": "Tamaño"},
    )
    assert rejected_group.status_code == 409
    assert rejected_group.json()["detail"]["code"] == "category_option_group_invalid_code"

    category_response = client.get(
        f"/api/v1/categories?branch_id={BRANCH_ID}", headers=_admin_headers()
    )
    product_response = client.get(
        f"/api/v1/catalog/products?branch_id={BRANCH_ID}", headers=_admin_headers()
    )
    schema = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "packages/contracts/schemas/pos-catalog-projection-v1.schema.json"
        ).read_text()
    )
    projection = {"categories": category_response.json(), "products": product_response.json()}
    assert set(schema["required"]) <= projection.keys()
    category_required = schema["$defs"]["category"]["required"]
    product_required = schema["$defs"]["product"]["required"]
    assert all(set(category_required) <= item.keys() for item in projection["categories"])
    assert all(set(product_required) <= item.keys() for item in projection["products"])
    assert all(item["selection_group"] is None for item in projection["categories"])
    assert all(item["selection"] is None for item in projection["products"])


def test_category_option_archiving_assigned_value_rolls_back_without_partial_mutation() -> None:
    client = _client_with_seeded_database()
    catalog = client.get("/api/v1/catalog/products", headers=_admin_headers()).json()
    food = [product for product in catalog if product["category_name"] == "Comida"]
    group = client.post(
        f"/api/v1/categories/{food[0]['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño", "status": "inactive"},
    ).json()
    value = client.post(
        f"/api/v1/catalog/category-option-groups/{group['id']}/values",
        headers=_admin_headers(), json={"code": "small", "name": "Chica", "status": "active"},
    ).json()
    for product in food:
        assert client.put(
            f"/api/v1/catalog/category-option-groups/{group['id']}/assignments/{product['id']}",
            headers=_admin_headers(), json={"option_value_id": value["id"]},
        ).status_code == 200
    assert client.post(
        f"/api/v1/categories/{food[0]['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño", "status": "active"},
    ).status_code == 200
    archived = client.put(
        f"/api/v1/catalog/category-option-groups/{group['id']}/values/{value['id']}",
        headers=_admin_headers(), json={"code": "small", "name": "Chica", "status": "archived"},
    )
    assert archived.status_code == 409
    assert archived.json()["detail"]["code"] == "category_option_value_required_by_active_group"
    coverage = client.get(
        f"/api/v1/catalog/category-option-groups/{group['id']}/coverage", headers=_admin_headers()
    ).json()
    assert coverage["values"] == [{
        "id": value["id"],
        "code": "small",
        "name": "Chica",
        "display_order": 0,
        "status": "active",
    }]
    assert coverage["complete"] is True


def test_category_option_order_uses_concrete_product_backend_price_and_snapshot() -> None:
    client = _client_with_seeded_database()
    catalog = client.get("/api/v1/catalog/products", headers=_admin_headers()).json()
    burger = next(product for product in catalog if product["sku"] == "KIWI-BURGER")
    fries = next(product for product in catalog if product["sku"] == "KIWI-FRIES")
    group = client.post(
        f"/api/v1/categories/{burger['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño", "status": "inactive"},
    ).json()
    value = client.post(
        f"/api/v1/catalog/category-option-groups/{group['id']}/values",
        headers=_admin_headers(), json={"code": "small", "name": "Chica", "status": "active"},
    ).json()
    for product in (burger, fries):
        assert client.put(
            f"/api/v1/catalog/category-option-groups/{group['id']}/assignments/{product['id']}",
            headers=_admin_headers(), json={"option_value_id": value["id"]},
        ).status_code == 200
    assert client.post(
        f"/api/v1/categories/{burger['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño", "status": "active"},
    ).status_code == 200
    assert client.post(
        "/api/v1/cash-shifts/open",
        headers={**_admin_headers(), "Idempotency-Key": "category-shift-open"},
        json={"branch_id": BRANCH_ID, "register_id": "CAJA-01", "opening_cash_cents": 0}
    ).status_code == 200
    created = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "lines": [{
                "product_id": burger["id"], "quantity": 2,
                "unit_price_cents": 1, "price_cents": 1, "option_label": "Manipulado",
            }],
        },
    )
    assert created.status_code == 200
    detail = client.get(f"/api/v1/orders/{created.json()['id']}", headers=_admin_headers()).json()
    line = detail["lines"][0]
    assert line["product_id"] == burger["id"]
    assert line["product_name"] == burger["name"]
    assert line["unit_price_cents"] == burger["price_cents"] == 9500
    assert line["line_total_cents"] == 19000
    assert detail["total_cents"] == 19000


def test_category_option_rejects_unknown_category_cross_relations_and_missing_permission() -> None:
    client = _client_with_seeded_database()
    catalog = client.get("/api/v1/catalog/products", headers=_admin_headers()).json()
    burger = next(product for product in catalog if product["sku"] == "KIWI-BURGER")
    soda = next(product for product in catalog if product["sku"] == "KIWI-SODA")
    unknown = client.get(
        "/api/v1/categories/not-a-category/selection-group", headers=_admin_headers()
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "category_not_found"
    food_group = client.post(
        f"/api/v1/categories/{burger['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño"},
    ).json()
    drink_group = client.post(
        f"/api/v1/categories/{soda['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño"},
    ).json()
    food_value = client.post(
        f"/api/v1/catalog/category-option-groups/{food_group['id']}/values",
        headers=_admin_headers(), json={"code": "small", "name": "Chica"},
    ).json()
    drink_value = client.post(
        f"/api/v1/catalog/category-option-groups/{drink_group['id']}/values",
        headers=_admin_headers(), json={"code": "small", "name": "Chica"},
    ).json()
    mismatch = client.put(
        f"/api/v1/catalog/category-option-groups/{food_group['id']}/assignments/{burger['id']}",
        headers=_admin_headers(), json={"option_value_id": drink_value["id"]},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "category_option_value_group_mismatch"
    wrong_product = client.put(
        f"/api/v1/catalog/category-option-groups/{food_group['id']}/assignments/{soda['id']}",
        headers=_admin_headers(), json={"option_value_id": food_value["id"]},
    )
    assert wrong_product.status_code == 409
    assert wrong_product.json()["detail"]["code"] == "category_option_product_invalid"
    session_factory = _test_session_factory(client)
    with session_factory() as session:
        catalog_permission = session.execute(
            permissions.select().where(permissions.c.code == "catalog.manage")
        ).scalar_one()
        session.execute(role_permissions.delete().where(
            role_permissions.c.permission_id == catalog_permission
        ))
        session.commit()
    assert client.get(
        f"/api/v1/categories/{burger['category_id']}/selection-group", headers=_admin_headers()
    ).status_code == 403
    assert client.post(
        f"/api/v1/categories/{burger['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "other", "name": "Otro"},
    ).status_code == 403


def test_category_option_value_update_validation_rollback_and_audit_actions() -> None:
    client = _client_with_seeded_database()
    catalog = client.get("/api/v1/catalog/products", headers=_admin_headers()).json()
    burger = next(product for product in catalog if product["sku"] == "KIWI-BURGER")
    group = client.post(
        f"/api/v1/categories/{burger['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño", "status": "inactive"},
    ).json()
    value = client.post(
        f"/api/v1/catalog/category-option-groups/{group['id']}/values",
        headers=_admin_headers(), json={"code": "small", "name": "Chica", "display_order": 10},
    ).json()
    assert client.post(
        f"/api/v1/catalog/category-option-groups/{group['id']}/values",
        headers=_admin_headers(), json={"code": "small", "name": "Duplicada"},
    ).json()["detail"]["code"] == "category_option_duplicate"
    invalid_order = client.put(
        f"/api/v1/catalog/category-option-groups/{group['id']}/values/{value['id']}",
        headers=_admin_headers(),
        json={"code": "small", "name": "Chica", "display_order": "bad", "status": "active"},
    )
    assert invalid_order.status_code == 409
    assert invalid_order.json()["detail"]["code"] == "category_option_value_invalid_order"
    updated = client.put(
        f"/api/v1/catalog/category-option-groups/{group['id']}/values/{value['id']}",
        headers=_admin_headers(),
        json={
            "code": "small-new",
            "name": "Chica renovada",
            "display_order": 20,
            "status": "active",
        },
    )
    assert updated.status_code == 200
    coverage = client.get(
        f"/api/v1/catalog/category-option-groups/{group['id']}/coverage", headers=_admin_headers()
    ).json()
    assert coverage["values"] == [{
        "id": value["id"], "code": "small-new", "name": "Chica renovada",
        "display_order": 20, "status": "active",
    }]
    assert client.put(
        f"/api/v1/catalog/category-option-groups/{group['id']}/assignments/{burger['id']}",
        headers=_admin_headers(), json={"option_value_id": value["id"]},
    ).status_code == 200
    replacement = client.post(
        f"/api/v1/catalog/category-option-groups/{group['id']}/values",
        headers=_admin_headers(), json={"code": "large", "name": "Grande", "display_order": 30},
    ).json()
    assert client.put(
        f"/api/v1/catalog/category-option-groups/{group['id']}/assignments/{burger['id']}",
        headers=_admin_headers(), json={"option_value_id": replacement["id"]},
    ).status_code == 200
    assert client.post(
        f"/api/v1/categories/{burger['category_id']}/selection-group",
        headers=_admin_headers(),
        json={"code": "size", "name": "Tamaño actualizado", "status": "inactive"},
    ).status_code == 200
    session_factory = _test_session_factory(client)
    with session_factory() as session:
        actions = set(session.execute(
            audit_events.select().with_only_columns(audit_events.c.action)
        ).scalars())
    assert {
        "category_option_group.created", "category_option_group.updated",
        "category_option_value.created", "category_option_value.updated",
        "category_option_assignment.created",
        "category_option_assignment.reassigned",
    } <= actions


def test_pos_catalog_schema_validates_active_and_null_projections() -> None:
    from restaurant_os.pos_catalog_contract import validate_pos_catalog_projection

    client = _client_with_seeded_database()
    catalog = client.get("/api/v1/catalog/products", headers=_admin_headers()).json()
    food = [product for product in catalog if product["category_name"] == "Comida"]
    group = client.post(
        f"/api/v1/categories/{food[0]['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño", "status": "inactive"},
    ).json()
    value = client.post(
        f"/api/v1/catalog/category-option-groups/{group['id']}/values",
        headers=_admin_headers(), json={"code": "small", "name": "Chica", "display_order": 10},
    ).json()
    for product in food:
        assert client.put(
            f"/api/v1/catalog/category-option-groups/{group['id']}/assignments/{product['id']}",
            headers=_admin_headers(), json={"option_value_id": value["id"]},
        ).status_code == 200
    assert client.post(
        f"/api/v1/categories/{food[0]['category_id']}/selection-group",
        headers=_admin_headers(), json={"code": "size", "name": "Tamaño", "status": "active"},
    ).status_code == 200
    active = {
        "categories": client.get(
            f"/api/v1/categories?branch_id={BRANCH_ID}", headers=_admin_headers()
        ).json(),
        "products": client.get(
            f"/api/v1/catalog/products?branch_id={BRANCH_ID}", headers=_admin_headers()
        ).json(),
    }
    validate_pos_catalog_projection(active)
    assert any(item["selection_group"] is not None for item in active["categories"])
    assert any(item["selection"] is not None for item in active["products"])
    invalid_price = {**active, "products": [{**active["products"][0], "price_cents": "125"}]}
    with pytest.raises(ValueError, match="price_cents"):
        validate_pos_catalog_projection(invalid_price)
    selection_without_value_id = dict(
        next(item for item in active["products"] if item["selection"])["selection"]
    )
    del selection_without_value_id["value_id"]
    invalid_selection = {**active, "products": [{
        **next(item for item in active["products"] if item["selection"]),
        "selection": selection_without_value_id,
    }]}
    with pytest.raises(ValueError, match="value_id"):
        validate_pos_catalog_projection(invalid_selection)
    configured_category = next(item for item in active["categories"] if item["selection_group"])
    invalid_group = {**active, "categories": [{
        **configured_category,
        "selection_group": {**configured_category["selection_group"], "selection_mode": "multiple"},
    }]}
    with pytest.raises(ValueError, match="selection_mode"):
        validate_pos_catalog_projection(invalid_group)
    null_projection = {
        "categories": [item for item in active["categories"] if item["selection_group"] is None],
        "products": [item for item in active["products"] if item["selection"] is None],
    }
    validate_pos_catalog_projection(null_projection)


def test_admin_can_create_branch_and_product_catalog_entries() -> None:
    client = _client_with_seeded_database()

    branch_response = client.post(
        "/api/v1/branches",
        headers=_admin_headers(),
        json={"name": "Sucursal Norte", "code": "norte"},
    )
    assert branch_response.status_code == 200
    branch = branch_response.json()
    assert branch["name"] == "Sucursal Norte"
    assert branch["code"] == "NORTE"
    assert branch["warehouse"]["name"] == "Almacen Sucursal Norte"

    duplicate_branch = client.post(
        "/api/v1/branches",
        headers=_admin_headers(),
        json={"name": "Sucursal Norte Bis", "code": "NORTE"},
    )
    assert duplicate_branch.status_code == 409
    assert duplicate_branch.json()["detail"]["code"] == "branch_already_exists"

    product_response = client.post(
        "/api/v1/catalog/products",
        headers=_admin_headers(),
        json={
            "name": "WRAP KIWI",
            "sku": "'09001",
            "category_name": "COMIDA",
            "station": "kitchen",
            "price_cents": 8900,
        },
    )
    assert product_response.status_code == 200
    product = product_response.json()
    assert product["name"] == "WRAP KIWI"
    assert product["sku"] == "09001"
    assert product["category_name"] == "COMIDA"
    assert product["price_cents"] == 8900
    assert product["is_available"] is True

    duplicate_product = client.post(
        "/api/v1/catalog/products",
        headers=_admin_headers(),
        json={
            "name": "WRAP KIWI REPETIDO",
            "sku": "09001",
            "category_name": "COMIDA",
            "station": "kitchen",
            "price_cents": 8900,
        },
    )
    assert duplicate_product.status_code == 409
    assert duplicate_product.json()["detail"]["code"] == "product_already_exists"

    branches_response = client.get("/api/v1/branches", headers=_admin_headers())
    assert branches_response.status_code == 200
    created_branch = next(item for item in branches_response.json() if item["code"] == "NORTE")
    assert created_branch["warehouse_name"] == "Almacen Sucursal Norte"

    products_response = client.get("/api/v1/catalog/products", headers=_admin_headers())
    assert products_response.status_code == 200
    created_product = next(item for item in products_response.json() if item["sku"] == "09001")
    assert created_product["price_cents"] == 8900

    bootstrap_response = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    )
    assert bootstrap_response.status_code == 200
    assert bootstrap_response.json()["counts"]["branches"] == 2
    assert bootstrap_response.json()["counts"]["products"] == 4
    assert bootstrap_response.json()["counts"]["audit_events"] == 3


def test_warehouse_listing_is_branch_scoped_and_active_branch_cannot_lose_warehouse() -> None:
    client = _client_with_seeded_database()

    branch_response = client.post(
        "/api/v1/branches",
        headers=_admin_headers(),
        json={"name": "Sucursal Norte", "code": "NORTE"},
    )
    assert branch_response.status_code == 200
    north = branch_response.json()

    scoped = client.get(
        f"/api/v1/warehouses?branch_id={north['id']}", headers=_admin_headers()
    )
    assert scoped.status_code == 200
    assert scoped.json() == [
        {
            "id": north["warehouse"]["id"],
            "branch_id": north["id"],
            "name": "Almacen Sucursal Norte",
            "status": "active",
            "created_at": scoped.json()[0]["created_at"],
        }
    ]

    rejected = client.put(
        f"/api/v1/warehouses/{north['warehouse']['id']}",
        headers=_admin_headers(),
        json={"status": "inactive"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "active_branch_requires_warehouse"

    unchanged = client.get(
        f"/api/v1/warehouses?branch_id={north['id']}", headers=_admin_headers()
    )
    assert unchanged.status_code == 200
    assert unchanged.json()[0]["status"] == "active"

    with _test_session_factory(client)() as session:
        session.execute(
            branches.update().where(branches.c.id == north["id"]).values(status="inactive")
        )
        session.commit()

    allowed = client.put(
        f"/api/v1/warehouses/{north['warehouse']['id']}",
        headers=_admin_headers(),
        json={"status": "inactive"},
    )
    assert allowed.status_code == 200

    visible_inactive = client.get("/api/v1/warehouses", headers=_admin_headers())
    assert visible_inactive.status_code == 200
    north_warehouse = next(
        item for item in visible_inactive.json() if item["branch_id"] == north["id"]
    )
    assert north_warehouse["status"] == "inactive"


def test_warehouse_management_uses_catalog_authority_not_identity_administration() -> None:
    client = _client_with_seeded_database()
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    catalog_user_id = "018f6f73-2d0a-74f0-8f1c-000000009941"
    catalog_role_id = "018f6f73-2d0a-74f0-8f1c-000000009942"
    admin_user_id = "018f6f73-2d0a-74f0-8f1c-000000009943"
    admin_role_id = "018f6f73-2d0a-74f0-8f1c-000000009944"
    catalog_branch_id = "018f6f73-2d0a-74f0-8f1c-000000009945"
    admin_branch_id = "018f6f73-2d0a-74f0-8f1c-000000009946"

    with _test_session_factory(client)() as session:
        permission_ids = dict(
            session.execute(
                sa.select(permissions.c.code, permissions.c.id).where(
                    permissions.c.code.in_({"catalog.manage", "admin.manage"})
                )
            ).all()
        )
        session.execute(
            roles.insert(),
            [
                {
                    "id": catalog_role_id,
                    "organization_id": ORGANIZATION_ID,
                    "name": "Gestor corporativo de catálogo",
                    "scope": "organization",
                    "created_at": now,
                },
                {
                    "id": admin_role_id,
                    "organization_id": ORGANIZATION_ID,
                    "name": "Gestor de identidades",
                    "scope": "organization",
                    "created_at": now,
                },
            ],
        )
        session.execute(
            users.insert(),
            [
                {
                    "id": catalog_user_id,
                    "organization_id": ORGANIZATION_ID,
                    "email": "catalog-warehouse@example.test",
                    "display_name": "Gestor de catálogo",
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": admin_user_id,
                    "organization_id": ORGANIZATION_ID,
                    "email": "identity-admin@example.test",
                    "display_name": "Gestor de identidades",
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        session.execute(
            role_permissions.insert(),
            [
                {"role_id": catalog_role_id, "permission_id": permission_ids["catalog.manage"]},
                {"role_id": admin_role_id, "permission_id": permission_ids["admin.manage"]},
            ],
        )
        session.execute(
            user_roles.insert(),
            [
                {"user_id": catalog_user_id, "role_id": catalog_role_id, "branch_id": None},
                {"user_id": admin_user_id, "role_id": admin_role_id, "branch_id": None},
            ],
        )
        session.execute(
            branches.insert(),
            [
                {
                    "id": branch_id,
                    "organization_id": ORGANIZATION_ID,
                    "legal_entity_id": "018f6f73-2d0a-74f0-8f1c-000000000002",
                    "business_unit_id": "018f6f73-2d0a-74f0-8f1c-000000000015",
                    "name": branch_name,
                    "code": branch_code,
                    "timezone": "America/Chihuahua",
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
                for branch_id, branch_name, branch_code in (
                    (catalog_branch_id, "Sucursal Catálogo", "CAT-WH"),
                    (admin_branch_id, "Sucursal Identidades", "ADM-WH"),
                )
            ],
        )
        session.commit()

    catalog_token = create_session_token(
        {"sub": catalog_user_id}, get_settings().secret_key
    )
    identity_token = create_session_token(
        {"sub": admin_user_id}, get_settings().secret_key
    )
    catalog_headers = {"Authorization": f"Bearer {catalog_token}"}
    identity_headers = {"Authorization": f"Bearer {identity_token}"}

    assert client.get("/api/v1/warehouses", headers=catalog_headers).status_code == 200
    created = client.post(
        "/api/v1/warehouses",
        headers=catalog_headers,
        json={"branch_id": catalog_branch_id, "name": "Almacén Catálogo"},
    )
    assert created.status_code == 200
    renamed = client.put(
        f"/api/v1/warehouses/{created.json()['id']}",
        headers=catalog_headers,
        json={"name": "Almacén Catálogo Actualizado"},
    )
    assert renamed.status_code == 200

    for response in (
        client.get("/api/v1/warehouses", headers=identity_headers),
        client.post(
            "/api/v1/warehouses",
            headers=identity_headers,
            json={"branch_id": admin_branch_id, "name": "No autorizado"},
        ),
        client.put(
            f"/api/v1/warehouses/{created.json()['id']}",
            headers=identity_headers,
            json={"name": "No autorizado"},
        ),
    ):
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "permission_denied"


def test_catalog_cleanup_status_and_identity_validation() -> None:
    client = _client_with_seeded_database()

    unauthenticated = client.get("/api/v1/catalog/cleanup-status")
    assert unauthenticated.status_code == 401
    status = client.get("/api/v1/catalog/cleanup-status", headers=_admin_headers())
    assert status.status_code == 200
    assert status.json() == {
        "revision": "0027_catalog_cleanup",
        "status": "pending",
        "summary": {},

    }

    invalid_product = client.post(
        "/api/v1/catalog/products",
        headers=_admin_headers(),
        json={
            "name": "Producto legado",
            "sku": "LEGACY-1",
            "category_name": "Comida",
            "station": "kitchen",
            "price_cents": 100,
        },
    )
    assert invalid_product.status_code == 409
    assert invalid_product.json()["detail"]["code"] == "invalid_product_name"

    invalid_item = client.post(
        "/api/v1/inventory/items",
        headers=_admin_headers(),
        json={
            "name": "Insumo legado",
            "sku": "INV-LEGACY",
            "base_unit_id": "018f6f73-2d0a-74f0-8f1c-000000000303",
        },
    )
    assert invalid_item.status_code == 409
    assert invalid_item.json()["detail"]["code"] == "invalid_item_sku"

    invalid_category = client.post(
        "/api/v1/categories",
        headers=_admin_headers(),
        json={"name": "   "},
    )
    assert invalid_category.status_code == 409
    assert invalid_category.json()["detail"]["code"] == "invalid_category"


def test_admin_can_read_inventory_and_record_opening_balance() -> None:
    client = _client_with_seeded_database()

    stock_response = client.get("/api/v1/inventory/stock", headers=_admin_headers())
    assert stock_response.status_code == 200
    stock = stock_response.json()
    beef = next(item for item in stock if item["sku"] == "INV-BEEF")
    assert beef["quantity_on_hand"] == 25000
    assert beef["unit_code"] == "g"
    assert beef["branch_id"] == BRANCH_ID
    assert beef["warehouse_name"] == "Almacen Sucursal Piloto"

    recipes_response = client.get("/api/v1/recipes", headers=_admin_headers())
    assert recipes_response.status_code == 200
    burger_recipe = next(
        item for item in recipes_response.json() if item["product_sku"] == "KIWI-BURGER"
    )
    assert burger_recipe["version"] == 1
    assert any(component["item_sku"] == "INV-BEEF" for component in burger_recipe["components"])

    movement_response = client.post(
        "/api/v1/inventory/opening-balances",
        headers=_admin_headers(),
        json={
            "item_id": beef["id"],
            "quantity_base_units": 5000,
            "reason": "Conteo inicial adicional",
        },
    )
    assert movement_response.status_code == 200
    movement = movement_response.json()
    assert movement["movement_type"] == "OPENING_BALANCE"
    assert movement["quantity_delta"] == 5000
    assert movement["item_name"] == "Carne molida"

    invalid_movement = client.post(
        "/api/v1/inventory/opening-balances",
        headers=_admin_headers(),
        json={"item_id": beef["id"], "quantity_base_units": 0},
    )
    assert invalid_movement.status_code == 409
    assert invalid_movement.json()["detail"]["code"] == "invalid_inventory_quantity"

    updated_stock_response = client.get(
        "/api/v1/inventory/stock", headers=_admin_headers()
    )
    assert updated_stock_response.status_code == 200
    updated_beef = next(item for item in updated_stock_response.json() if item["sku"] == "INV-BEEF")
    assert updated_beef["quantity_on_hand"] == 30000

    kardex_response = client.get(
        f"/api/v1/inventory/kardex?item_id={beef['id']}", headers=_admin_headers()
    )
    assert kardex_response.status_code == 200
    kardex = kardex_response.json()
    assert [item["quantity_delta"] for item in kardex] == [5000, 25000]
    assert kardex[0]["reason"] == "Conteo inicial adicional"

    bootstrap_response = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    )
    assert bootstrap_response.status_code == 200
    assert bootstrap_response.json()["counts"]["inventory_items"] == 4
    assert bootstrap_response.json()["counts"]["inventory_movements"] == 5
    assert bootstrap_response.json()["counts"]["audit_events"] == 2


def test_rbac_rejects_inventory_adjustment_without_permission() -> None:
    client = _client_with_seeded_database()

    role_response = client.post(
        "/api/v1/roles", headers=_admin_headers(), json={"name": "Cajero", "scope": "branch"}
    )
    assert role_response.status_code == 200
    role = role_response.json()

    user_response = client.post(
        "/api/v1/users",
        headers=_admin_headers(),
        json={
            "email": "cajero-rbac@kiwi.local",
            "display_name": "Cajero RBAC",
            "employee_code": "RBC001",
            "password": "Temporal123+",
        },
    )
    assert user_response.status_code == 200
    user = user_response.json()

    missing_branch_response = client.post(
        f"/api/v1/users/{user['id']}/roles",
        headers=_admin_headers(),
        json={"role_id": role["id"]},
    )
    assert missing_branch_response.status_code == 409
    assert missing_branch_response.json()["detail"]["code"] == "branch_assignment_required"

    assignment_response = client.post(
        f"/api/v1/users/{user['id']}/roles",
        headers=_admin_headers(),
        json={"role_id": role["id"], "branch_id": BRANCH_ID},
    )
    assert assignment_response.status_code == 200

    stock_response = client.get("/api/v1/inventory/stock", headers=_admin_headers())
    assert stock_response.status_code == 200
    beef = next(item for item in stock_response.json() if item["sku"] == "INV-BEEF")

    denied_response = client.post(
        "/api/v1/inventory/opening-balances",
        headers={"X-Actor-User-Id": user["id"]},
        json={
            "item_id": beef["id"],
            "quantity_base_units": 1000,
            "reason": "Intento no autorizado",
        },
    )
    assert denied_response.status_code == 403
    assert denied_response.json()["detail"]["code"] == "permission_denied"

    updated_stock_response = client.get(
        "/api/v1/inventory/stock", headers=_admin_headers()
    )
    assert updated_stock_response.status_code == 200
    updated_beef = next(item for item in updated_stock_response.json() if item["sku"] == "INV-BEEF")
    assert updated_beef["quantity_on_hand"] == 25000

    admin_response = client.post(
        "/api/v1/inventory/opening-balances",
        headers=_admin_headers(),
        json={
            "item_id": beef["id"],
            "quantity_base_units": 1000,
            "reason": "Ajuste autorizado",
        },
    )
    assert admin_response.status_code == 200

    bootstrap_response = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    )
    assert bootstrap_response.status_code == 200
    assert bootstrap_response.json()["counts"]["inventory_movements"] == 5
    assert bootstrap_response.json()["counts"]["audit_events"] == 6


def test_supplier_contacts_and_purchase_presentation_do_not_change_inventory_cost() -> None:
    client = _client_with_seeded_database()
    before = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    ).json()["counts"]["inventory_movements"]

    kilogram = client.post(
        "/api/v1/inventory/units",
        headers=_admin_headers(),
        json={"code": "KG", "name": "Kilogramo", "precision_scale": 3, "dimension": "mass"},
    )
    assert kilogram.status_code == 200
    sugar = client.post(
        "/api/v1/inventory/items",
        headers=_admin_headers(),
        json={
            "name": "Azucar",
            "sku": "09101",
            "base_unit_id": kilogram.json()["id"],
            "item_type": "ingredient",
        },
    )
    assert sugar.status_code == 200
    supplier_response = client.post(
        "/api/v1/suppliers",
        headers=_admin_headers(),
        json={
            "code": "PROV-AZ",
            "commercial_name": "Azucares del Pacifico",
            "legal_name": "Azucares del Pacifico SA de CV",
            "tax_id": "APA010101AB1",
            "credit_days": 15,
            "delivery_days": ["monday", "thursday"],
            "payment_methods": ["cash", "transfer"],
        },
    )
    assert supplier_response.status_code == 200
    supplier = supplier_response.json()
    contact = client.post(
        f"/api/v1/suppliers/{supplier['id']}/contacts",
        headers=_admin_headers(),
        json={
            "name": "Ana Compras",
            "contact_type": "orders",
            "phone": "6691234567",
            "primary_for_orders": True,
        },
    )
    assert contact.status_code == 200
    terms = client.put(
        f"/api/v1/suppliers/{supplier['id']}/branches/{BRANCH_ID}",
        headers=_admin_headers(),
        json={"is_enabled": True, "lead_time_days": 2, "minimum_amount": "500.00"},
    )
    assert terms.status_code == 200

    presentation_response = client.post(
        "/api/v1/purchase-presentations",
        headers=_admin_headers(),
        json={
            "supplier_id": supplier["id"],
            "item_id": sugar.json()["id"],
            "code": "AZ-10KG",
            "name": "Bolsa azucar 10 kg",
            "package_type": "bag",
            "commercial_quantity": "1",
            "commercial_unit_id": "018f6f73-2d0a-74f0-8f1c-000000000303",
            "base_unit_id": kilogram.json()["id"],
            "base_unit_yield": "10",
            "usable_content": "10",
            "yield_percent": "1",
            "last_net_price": "280.00",
            "tax_rate": "0",
        },
    )
    assert presentation_response.status_code == 200
    presentation = presentation_response.json()
    assert float(presentation["cost_per_base_unit"]) == 28.0

    presentation_update = client.put(
        f"/api/v1/purchase-presentations/{presentation['id']}",
        headers=_admin_headers(),
        json={"name": "Bolsa azucar 10 kg actualizada"},
    )
    assert presentation_update.status_code == 200
    assert presentation_update.json()["name"] == "Bolsa azucar 10 kg actualizada"

    price_update = client.put(
        f"/api/v1/purchase-presentations/{presentation['id']}/price",
        headers=_admin_headers(),
        json={"net_price": "300.00"},
    )
    assert price_update.status_code == 200
    assert float(price_update.json()["cost_per_base_unit"]) == 30.0
    listed = client.get(
        f"/api/v1/purchase-presentations?branch_id={BRANCH_ID}", headers=_admin_headers()
    )
    assert listed.status_code == 200
    stored = next(row for row in listed.json() if row["id"] == presentation["id"])
    assert len(stored["price_history"]) == 3
    suppliers = client.get(
        f"/api/v1/suppliers?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).json()
    stored_supplier = next(row for row in suppliers if row["id"] == supplier["id"])
    assert stored_supplier["contacts"][0]["primary_for_orders"] is True
    assert stored_supplier["branch_terms"][0]["lead_time_days"] == 2
    after = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    ).json()["counts"]["inventory_movements"]
    assert after == before


def test_direct_purchase_cash_reconciliation_average_cost_idempotency_and_reversal() -> None:
    client = _client_with_seeded_database()
    kilogram = client.post(
        "/api/v1/inventory/units",
        headers=_admin_headers(),
        json={"code": "KG", "name": "Kilogramo", "precision_scale": 3, "dimension": "mass"},
    ).json()
    sugar = client.post(
        "/api/v1/inventory/items",
        headers=_admin_headers(),
        json={
            "name": "Azucar",
            "sku": "09102",
            "base_unit_id": kilogram["id"],
            "item_type": "ingredient",
        },
    ).json()
    supplier = client.post(
        "/api/v1/suppliers",
        headers=_admin_headers(),
        json={
            "code": "PROV-COST",
            "commercial_name": "Proveedor Costeo",
            "delivery_days": [],
            "payment_methods": ["cash"],
        },
    ).json()
    assert (
        client.put(
            f"/api/v1/suppliers/{supplier['id']}/branches/{BRANCH_ID}",
            headers=_admin_headers(),
            json={"is_enabled": True},
        ).status_code
        == 200
    )
    presentation = client.post(
        "/api/v1/purchase-presentations",
        headers=_admin_headers(),
        json={
            "supplier_id": supplier["id"],
            "item_id": sugar["id"],
            "code": "SUGAR-10",
            "name": "Bolsa 10 kg",
            "package_type": "bag",
            "commercial_quantity": "1",
            "commercial_unit_id": "018f6f73-2d0a-74f0-8f1c-000000000303",
            "base_unit_id": kilogram["id"],
            "base_unit_yield": "10",
            "usable_content": "10",
            "yield_percent": "1",
            "last_net_price": "200",
            "tax_rate": "0",
        },
    ).json()

    first = client.post(
        "/api/v1/purchases",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "supplier_id": supplier["id"],
            "document_type": "invoice",
            "folio": "FAC-001",
            "payment_method": "transfer",
            "paid_from_cash": False,
            "lines": [
                {
                    "presentation_id": presentation["id"],
                    "quantity": "1",
                    "unit_price": "200",
                    "discount": "0",
                    "tax": "32",
                }
            ],
        },
    )
    assert first.status_code == 200
    first_confirm = client.post(
        f"/api/v1/purchases/{first.json()['id']}/confirm",
        headers={**_admin_headers(), "Idempotency-Key": "purchase-first"},
        json={},
    )
    assert first_confirm.status_code == 200
    first_cost = client.get(
        f"/api/v1/inventory/costs?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).json()[0]
    assert float(first_cost["quantity_on_hand"]) == 10
    assert float(first_cost["average_unit_cost"]) == 20

    open_response = _open_shift(client, 100000)
    assert open_response.status_code == 200
    second = client.post(
        "/api/v1/purchases",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "supplier_id": supplier["id"],
            "document_type": "invoice",
            "folio": "FAC-002",
            "payment_method": "cash",
            "paid_from_cash": True,
            "lines": [
                {
                    "presentation_id": presentation["id"],
                    "quantity": "1",
                    "unit_price": "300",
                    "discount": "0",
                    "tax": "48",
                }
            ],
        },
    )
    assert second.status_code == 200
    assert float(second.json()["total"]) == 348
    confirmation_headers = {**_admin_headers(), "Idempotency-Key": "purchase-second"}
    second_confirm = client.post(
        f"/api/v1/purchases/{second.json()['id']}/confirm",
        headers=confirmation_headers,
        json={"register_id": "CAJA-01"},
    )
    assert second_confirm.status_code == 200
    confirmed = second_confirm.json()
    assert confirmed["status"] == "confirmed"
    assert len(confirmed["inventory_movements"]) == 1
    assert len(confirmed["cash_movements"]) == 1
    assert confirmed["cash_movements"][0]["amount_cents"] == 34800
    assert "idempotency_key" not in confirmed["cash_movements"][0]
    assert "evidence_refs" not in confirmed["cash_movements"][0]

    costs = client.get(
        f"/api/v1/inventory/costs?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).json()
    sugar_cost = next(row for row in costs if row["item_id"] == sugar["id"])
    assert float(sugar_cost["quantity_on_hand"]) == 20
    assert float(sugar_cost["average_unit_cost"]) == 25
    summary = client.get(
        f"/api/v1/cash-shifts/summary?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).json()["summary"]
    assert summary["withdrawal_cents"] == 34800
    assert summary["expected_cash_cents"] == 65200

    retry = client.post(
        f"/api/v1/purchases/{second.json()['id']}/confirm",
        headers=confirmation_headers,
        json={"register_id": "CAJA-01"},
    )
    assert retry.status_code == 200
    assert len(retry.json()["inventory_movements"]) == 1
    assert len(retry.json()["cash_movements"]) == 1

    cancellation = client.post(
        f"/api/v1/purchases/{second.json()['id']}/cancel",
        headers=_admin_headers(),
        json={"reason": "Factura capturada por error"},
    )
    assert cancellation.status_code == 200
    cancelled = cancellation.json()
    assert cancelled["status"] == "cancelled"
    assert {movement["movement_type"] for movement in cancelled["inventory_movements"]} == {
        "PURCHASE_RECEIPT",
        "PURCHASE_REVERSAL",
    }
    assert {movement["movement_type"] for movement in cancelled["cash_movements"]} == {
        "withdrawal",
        "deposit",
    }
    costs_after = client.get(
        f"/api/v1/inventory/costs?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).json()
    sugar_after = next(row for row in costs_after if row["item_id"] == sugar["id"])
    assert float(sugar_after["quantity_on_hand"]) == 10
    assert float(sugar_after["average_unit_cost"]) == 20
    summary_after = client.get(
        f"/api/v1/cash-shifts/summary?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).json()["summary"]
    assert summary_after["expected_cash_cents"] == 100000
    with _test_session_factory(client)() as session:
        session.execute(
            permissions.insert().values(
                id="018f6f73-2d0a-74f0-8f1c-000000009983",
                code="cash.movement.compensate",
                description="Compensar movimientos de caja",
                created_at=datetime(2026, 8, 12, tzinfo=UTC),
            )
        )
        session.execute(
            role_permissions.insert().values(
                role_id=ADMIN_ROLE_ID,
                permission_id="018f6f73-2d0a-74f0-8f1c-000000009983",
            )
        )
        session.commit()
    compensated_purchase = client.post(
        "/api/v1/purchases",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "supplier_id": supplier["id"],
            "document_type": "invoice",
            "folio": "FAC-003",
            "payment_method": "cash",
            "paid_from_cash": True,
            "lines": [{
                "presentation_id": presentation["id"],
                "quantity": "1",
                "unit_price": "300",
                "discount": "0",
                "tax": "48",
            }],
        },
    )
    confirmed_compensated = client.post(
        f"/api/v1/purchases/{compensated_purchase.json()['id']}/confirm",
        headers={**_admin_headers(), "Idempotency-Key": "purchase-compensated"},
        json={"register_id": "CAJA-01"},
    )
    assert confirmed_compensated.status_code == 200
    original_cash_id = confirmed_compensated.json()["cash_movements"][0]["id"]
    denied_manual_compensation = client.post(
        f"/api/v1/cash/movements/{original_cash_id}/compensations",
        headers={**_admin_headers(), "Idempotency-Key": "manual-purchase-compensation"},
        json={"reason": "Corrección previa", "evidence_refs": ["evidence://owner/purchase"]},
    )
    assert denied_manual_compensation.status_code == 403
    with _test_session_factory(client)() as session:
        session.execute(
            models.role_authority_grants.insert().values(
                role_id=ADMIN_ROLE_ID,
                authority_kind="organization_all_permissions",
                created_at=datetime(2026, 8, 12, tzinfo=UTC),
            )
        )
        session.commit()
    manual_compensation = client.post(
        f"/api/v1/cash/movements/{original_cash_id}/compensations",
        headers={**_admin_headers(), "Idempotency-Key": "manual-purchase-compensation"},
        json={"reason": "Corrección previa", "evidence_refs": ["evidence://owner/purchase"]},
    )
    assert manual_compensation.status_code == 200
    blocked_cancellation = client.post(
        f"/api/v1/purchases/{compensated_purchase.json()['id']}/cancel",
        headers=_admin_headers(),
        json={"reason": "No debe duplicar compensación"},
    )
    assert blocked_cancellation.status_code == 409
    assert blocked_cancellation.json()["detail"]["code"] == "cash_movement_already_compensated"
    assert "IntegrityError" not in blocked_cancellation.text
    persisted_compensated = next(
        purchase
        for purchase in client.get(
            f"/api/v1/purchases?branch_id={BRANCH_ID}", headers=_admin_headers()
        ).json()
        if purchase["id"] == compensated_purchase.json()["id"]
    )
    assert persisted_compensated["status"] == "confirmed"
    assert {row["movement_type"] for row in persisted_compensated["inventory_movements"]} == {
        "PURCHASE_RECEIPT"
    }
    assert len(persisted_compensated["cash_movements"]) == 1
    closed = client.post(
        f"/api/v1/cash/shifts/{open_response.json()['id']}/close-operationally",
        headers={**_admin_headers(), "Idempotency-Key": "purchase-operational-close"},
        json={},
    )
    assert closed.status_code == 200
    before_rejected = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    ).json()["counts"]
    rejected_purchase = client.post(
        "/api/v1/purchases",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "supplier_id": supplier["id"],
            "document_type": "invoice",
            "folio": "FAC-004",
            "payment_method": "cash",
            "paid_from_cash": True,
            "lines": [
                {
                    "presentation_id": presentation["id"],
                    "quantity": "1",
                    "unit_price": "300",
                    "discount": "0",
                    "tax": "48",
                }
            ],
        },
    )
    assert rejected_purchase.status_code == 200
    rejected_confirmation = client.post(
        f"/api/v1/purchases/{rejected_purchase.json()['id']}/confirm",
        headers={**_admin_headers(), "Idempotency-Key": "purchase-closed-shift"},
        json={"register_id": "CAJA-01"},
    )
    assert rejected_confirmation.status_code == 409
    assert rejected_confirmation.json()["detail"]["code"] == "cash_shift_not_open"
    stored_rejected = next(
        purchase
        for purchase in client.get(
            f"/api/v1/purchases?branch_id={BRANCH_ID}", headers=_admin_headers()
        ).json()
        if purchase["id"] == rejected_purchase.json()["id"]
    )
    assert stored_rejected["status"] == "draft"
    assert stored_rejected["inventory_movements"] == []
    assert stored_rejected["cash_movements"] == []
    after_rejected = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    ).json()["counts"]
    assert after_rejected["inventory_movements"] == before_rejected["inventory_movements"]


def test_purchase_confirmation_rejects_negative_inventory_without_partial_effects() -> None:
    client = _client_with_seeded_database()
    assert (
        _open_shift(client, 100000).status_code
        == 200
    )
    order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1000}]},
    ).json()
    task_id = order["production_tasks"][0]["id"]
    assert (
        client.post(
            f"/api/v1/kds/tasks/{task_id}/transition",
            headers=_admin_headers(),
            json={"status": "IN_PROGRESS"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/kds/tasks/{task_id}/transition",
            headers=_admin_headers(),
            json={"status": "COMPLETED"},
        ).status_code
        == 200
    )

    supplier = client.post(
        "/api/v1/suppliers",
        headers=_admin_headers(),
        json={
            "code": "PROV-NEG",
            "commercial_name": "Proveedor Negativo",
            "delivery_days": [],
            "payment_methods": [],
        },
    ).json()
    presentation = client.post(
        "/api/v1/purchase-presentations",
        headers=_admin_headers(),
        json={
            "supplier_id": supplier["id"],
            "item_id": "018f6f73-2d0a-74f0-8f1c-000000000311",
            "code": "BEEF-1KG",
            "name": "Carne 1 kg",
            "package_type": "package",
            "commercial_quantity": "1",
            "commercial_unit_id": "018f6f73-2d0a-74f0-8f1c-000000000303",
            "base_unit_id": "018f6f73-2d0a-74f0-8f1c-000000000301",
            "base_unit_yield": "1000",
            "usable_content": "1000",
            "yield_percent": "1",
            "last_net_price": "100",
            "tax_rate": "0",
        },
    ).json()
    purchase = client.post(
        "/api/v1/purchases",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "supplier_id": supplier["id"],
            "document_type": "ticket",
            "folio": "NEG-001",
            "payment_method": "cash",
            "paid_from_cash": True,
            "lines": [
                {
                    "presentation_id": presentation["id"],
                    "quantity": "1",
                    "unit_price": "100",
                    "tax": "0",
                }
            ],
        },
    ).json()
    before_movements = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    ).json()["counts"][
        "inventory_movements"
    ]
    confirmation = client.post(
        f"/api/v1/purchases/{purchase['id']}/confirm",
        headers={**_admin_headers(), "Idempotency-Key": "negative-policy"},
        json={},
    )
    assert confirmation.status_code == 409
    assert confirmation.json()["detail"]["code"] == "negative_inventory_cost_policy_required"
    purchases = client.get(
        f"/api/v1/purchases?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).json()
    stored = next(row for row in purchases if row["id"] == purchase["id"])
    assert stored["status"] == "draft"
    assert stored["inventory_movements"] == []
    assert stored["cash_movements"] == []
    assert (
        client.get("/api/v1/platform/bootstrap-status", headers=_admin_headers()).json()[
            "counts"
        ]["inventory_movements"]
        == before_movements
    )


def test_recipe_versions_standard_waste_and_historical_order_snapshot() -> None:
    client = _client_with_seeded_database()
    burger_id = "018f6f73-2d0a-74f0-8f1c-000000000111"
    beef_id = "018f6f73-2d0a-74f0-8f1c-000000000311"
    gram_id = "018f6f73-2d0a-74f0-8f1c-000000000301"
    piece_id = "018f6f73-2d0a-74f0-8f1c-000000000303"

    assert (
        _open_shift(client, 50000).status_code
        == 200
    )
    order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": burger_id, "quantity": 1}]},
    ).json()
    snapshot = order["consumption_snapshots"][0]
    original_beef = next(row for row in snapshot["components"] if row["item_id"] == beef_id)
    assert float(original_beef["gross_quantity"]) == 120

    updated = client.put(
        f"/api/v1/products/{burger_id}/recipe",
        headers={**_admin_headers(), "Idempotency-Key": "platform-recipe-v2"},
        json={
            "branch_id": "018f6f73-2d0a-74f0-8f1c-000000000003",
            "expected_active_recipe_id": None,
            "yield_quantity": "1",
            "yield_unit_id": piece_id,
            "components": [
                {

                    "item_id": beef_id,
                    "unit_id": gram_id,
                    "net_quantity": "100",
                    "waste_rate": "0.2",
                }
            ],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    component = updated.json()["components"][0]
    assert float(component["net_quantity"]) == 100
    assert float(component["gross_quantity"]) == 125
    assert float(component["waste_rate"]) == 0.2

    current = client.get(
        f"/api/v1/products/{burger_id}/recipe?branch_id=018f6f73-2d0a-74f0-8f1c-000000000003",
        headers=_admin_headers(),
    ).json()
    assert current["version"] == 2
    assert float(current["components"][0]["gross_quantity"]) == 125

    task_id = order["production_tasks"][0]["id"]
    assert (
        client.post(
            f"/api/v1/kds/tasks/{task_id}/transition",
            headers=_admin_headers(),
            json={"status": "IN_PROGRESS"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/kds/tasks/{task_id}/transition",
            headers=_admin_headers(),
            json={"status": "COMPLETED"},
        ).status_code
        == 200
    )
    movements = client.get(
        f"/api/v1/inventory/kardex?item_id={beef_id}", headers=_admin_headers()
    ).json()
    assert any(
        row["movement_type"] == "SALE_CONSUMPTION" and float(row["quantity_delta"]) == -120
        for row in movements
    )
    assert not any(
        row["movement_type"] == "SALE_CONSUMPTION" and float(row["quantity_delta"]) == -125
        for row in movements
    )


def test_production_batch_is_idempotent_and_production_recipes_reject_cycles() -> None:
    client = _client_with_seeded_database()
    gram_id = "018f6f73-2d0a-74f0-8f1c-000000000301"
    beef_id = "018f6f73-2d0a-74f0-8f1c-000000000311"

    sauce = client.post(
        "/api/v1/inventory/items",
        headers=_admin_headers(),
        json={
            "name": "Salsa elaborada",
            "sku": "09103",
            "base_unit_id": gram_id,
            "item_type": "elaborated",
        },
    ).json()
    recipe_response = client.post(
        "/api/v1/production-recipes",
        headers=_admin_headers(),
        json={
            "output_item_id": sauce["id"],
            "yield_quantity": "1000",
            "yield_unit_id": gram_id,
            "branch_id": BRANCH_ID,
            "components": [{"item_id": beef_id, "net_quantity": "500", "waste_percent": "0"}],
        },
    )
    assert recipe_response.status_code == 200
    recipe = recipe_response.json()

    batch_response = client.post(
        "/api/v1/production-batches",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "recipe_id": recipe["id"],
            "lot_code": "SALSA-001",
            "planned_quantity": "1000",
            "actual_quantity": "900",
        },
    )
    assert batch_response.status_code == 200
    batch = batch_response.json()
    headers = {**_admin_headers(), "Idempotency-Key": "production-salsa-001"}
    confirmed = client.post(
        f"/api/v1/production-batches/{batch['id']}/confirm", headers=headers, json={}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    assert sorted(
        (row["movement_type"], float(row["quantity_delta"]))
        for row in confirmed.json()["movements"]
    ) == [("PRODUCTION_INPUT", -500.0), ("PRODUCTION_OUTPUT", 900.0)]

    replay = client.post(
        f"/api/v1/production-batches/{batch['id']}/confirm", headers=headers, json={}
    )
    assert replay.status_code == 200
    assert len(replay.json()["movements"]) == 2
    conflict = client.post(
        f"/api/v1/production-batches/{batch['id']}/confirm",
        headers={**_admin_headers(), "Idempotency-Key": "different-key"},
        json={},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "production_batch_already_confirmed"

    product = client.post(
        "/api/v1/catalog/products",
        headers=_admin_headers(),
        json={
            "name": "PLATILLO CON SALSA",
            "sku": "09002",
            "category_name": "COMIDA",
            "station": "kitchen",
            "price_cents": 7500,
        },
    ).json()
    sale_recipe = client.put(
        f"/api/v1/products/{product['id']}/recipe",
        headers={**_admin_headers(), "Idempotency-Key": "platform-sauce-recipe"},
        json={
            "branch_id": "018f6f73-2d0a-74f0-8f1c-000000000003",
            "expected_active_recipe_id": None,
            "yield_quantity": "1",
            "yield_unit_id": "018f6f73-2d0a-74f0-8f1c-000000000303",
            "components": [{
                "item_id": sauce["id"],
                "unit_id": "018f6f73-2d0a-74f0-8f1c-000000000301",
                "net_quantity": "100",
                "waste_rate": "0",
            }],
        },
    )
    assert sale_recipe.status_code == 200
    assert (
        _open_shift(client, 10000).status_code
        == 200
    )
    order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": product["id"], "quantity": 1}]},
    ).json()
    task_id = order["production_tasks"][0]["id"]
    assert (
        client.post(
            f"/api/v1/kds/tasks/{task_id}/transition",
            headers=_admin_headers(),
            json={"status": "IN_PROGRESS"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/kds/tasks/{task_id}/transition",
            headers=_admin_headers(),
            json={"status": "COMPLETED"},
        ).status_code
        == 200
    )
    sauce_movements = client.get(
        f"/api/v1/inventory/kardex?item_id={sauce['id']}", headers=_admin_headers()
    ).json()
    assert any(
        row["movement_type"] == "SALE_CONSUMPTION" and float(row["quantity_delta"]) == -100
        for row in sauce_movements
    )
    beef_movements = client.get(
        f"/api/v1/inventory/kardex?item_id={beef_id}", headers=_admin_headers()
    ).json()
    assert not any(row["movement_type"] == "SALE_CONSUMPTION" for row in beef_movements)

    filling = client.post(
        "/api/v1/inventory/items",
        headers=_admin_headers(),
        json={
            "name": "Relleno elaborado",
            "sku": "09104",
            "base_unit_id": gram_id,
            "item_type": "elaborated",
        },
    ).json()
    replace_sauce_recipe = client.post(
        "/api/v1/production-recipes",
        headers=_admin_headers(),
        json={
            "output_item_id": sauce["id"],
            "yield_quantity": "100",
            "yield_unit_id": gram_id,
            "components": [{"item_id": filling["id"], "net_quantity": "50"}],
        },
    )
    assert replace_sauce_recipe.status_code == 200
    cycle = client.post(
        "/api/v1/production-recipes",
        headers=_admin_headers(),
        json={
            "output_item_id": filling["id"],
            "yield_quantity": "100",
            "yield_unit_id": gram_id,
            "components": [{"item_id": sauce["id"], "net_quantity": "50"}],
        },
    )
    assert cycle.status_code == 409
    assert cycle.json()["detail"]["code"] == "recipe_cycle_detected"


def test_modifiers_validate_groups_price_snapshot_kitchen_text_and_inventory() -> None:
    client = _client_with_seeded_database()
    burger_id = "018f6f73-2d0a-74f0-8f1c-000000000111"
    beef_id = "018f6f73-2d0a-74f0-8f1c-000000000311"
    bun_id = "018f6f73-2d0a-74f0-8f1c-000000000312"

    extras = client.post(
        f"/api/v1/products/{burger_id}/modifier-groups",
        headers=_admin_headers(),
        json={
            "name": "Extras",
            "minimum_selections": 0,
            "maximum_selections": 1,
            "station": "kitchen",
        },
    ).json()
    extra_beef = client.post(
        f"/api/v1/modifier-groups/{extras['id']}/options",
        headers=_admin_headers(),
        json={
            "name": "Carne extra",
            "effect_type": "add",
            "affected_item_id": beef_id,
            "add_quantity": "50",
            "price_delta_cents": 2000,
            "kitchen_text": "Agregar carne extra",
        },
    ).json()
    extra_beef_two = client.post(
        f"/api/v1/modifier-groups/{extras['id']}/options",
        headers=_admin_headers(),
        json={
            "name": "Doble carne extra",
            "effect_type": "add",
            "affected_item_id": beef_id,
            "add_quantity": "100",
            "price_delta_cents": 3500,
        },
    ).json()
    instructions = client.post(
        f"/api/v1/products/{burger_id}/modifier-groups",
        headers=_admin_headers(),
        json={"name": "Instrucciones", "minimum_selections": 0, "maximum_selections": 1},
    ).json()
    instruction = client.post(
        f"/api/v1/modifier-groups/{instructions['id']}/options",
        headers=_admin_headers(),
        json={"name": "Comentario libre", "effect_type": "instruction", "inventory_effect": False},
    ).json()
    removals = client.post(
        f"/api/v1/products/{burger_id}/modifier-groups",
        headers=_admin_headers(),
        json={"name": "Quitar", "minimum_selections": 0, "maximum_selections": 1},
    ).json()
    no_bun = client.post(
        f"/api/v1/modifier-groups/{removals['id']}/options",
        headers=_admin_headers(),
        json={
            "name": "Sin pan",
            "effect_type": "remove",
            "affected_item_id": bun_id,
            "remove_quantity": "0",
        },
    ).json()

    catalog = client.get(
        f"/api/v1/products/{burger_id}/modifiers?branch_id={BRANCH_ID}",
        headers=_admin_headers(),
    ).json()
    assert len(catalog) == 3
    assert (
        next(group for group in catalog if group["id"] == extras["id"])["options"][0][
            "price_delta_cents"
        ]
        == 2000
    )
    assert (
        _open_shift(client, 10000).status_code
        == 200
    )

    too_many = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "lines": [
                {
                    "product_id": burger_id,
                    "quantity": 1,
                    "modifiers": [
                        {"option_id": extra_beef["id"]},
                        {"option_id": extra_beef_two["id"]},
                    ],
                }
            ]
        },
    )
    assert too_many.status_code == 409
    assert too_many.json()["detail"]["code"] == "modifier_group_maximum_exceeded"

    order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "lines": [
                {
                    "product_id": burger_id,
                    "quantity": 2,
                    "modifiers": [
                        {"option_id": extra_beef["id"]},
                        {"option_id": instruction["id"], "text": "Cortar por la mitad"},
                    ],
                }
            ]
        },
    )
    assert order.status_code == 200
    payload = order.json()
    assert payload["total_cents"] == 23000
    assert payload["lines"][0]["modifier_total_cents"] == 4000
    snapshot = payload["consumption_snapshots"][0]
    beef = next(
        component for component in snapshot["components"] if component["item_id"] == beef_id
    )
    assert float(beef["gross_quantity"]) == 340
    assert any(
        modifier["kitchen_text"] == "Cortar por la mitad" for modifier in snapshot["modifiers"]
    )

    assert (
        client.put(
            f"/api/v1/modifier-options/{extra_beef['id']}/branches/{BRANCH_ID}",
            headers=_admin_headers(),
            json={"is_enabled": True, "price_delta_cents": 3000},
        ).status_code
        == 200
    )
    task_id = payload["production_tasks"][0]["id"]
    kds_task = next(
        task
        for task in client.get("/api/v1/kds/tasks", headers=_admin_headers()).json()
        if task["id"] == task_id
    )
    assert any(
        modifier["kitchen_text"] == "Cortar por la mitad"
        for modifier in kds_task["selected_modifiers"]
    )
    assert (
        client.post(
            f"/api/v1/kds/tasks/{task_id}/transition",
            headers=_admin_headers(),
            json={"status": "IN_PROGRESS"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/kds/tasks/{task_id}/transition",
            headers=_admin_headers(),
            json={"status": "COMPLETED"},
        ).status_code
        == 200
    )
    beef_movements = client.get(
        f"/api/v1/inventory/kardex?item_id={beef_id}", headers=_admin_headers()
    ).json()
    assert any(
        row["movement_type"] == "SALE_CONSUMPTION" and float(row["quantity_delta"]) == -340
        for row in beef_movements
    )

    without_bun = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "lines": [
                {"product_id": burger_id, "quantity": 1, "modifiers": [{"option_id": no_bun["id"]}]}
            ]
        },
    )
    assert without_bun.status_code == 200
    assert not any(
        component["item_id"] == bun_id
        for component in without_bun.json()["consumption_snapshots"][0]["components"]
    )

    required = client.post(
        f"/api/v1/products/{burger_id}/modifier-groups",
        headers=_admin_headers(),
        json={
            "name": "Cocción",
            "is_required": True,
            "minimum_selections": 1,
            "maximum_selections": 1,
        },
    )
    assert required.status_code == 200
    missing = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": burger_id, "quantity": 1}]},
    )
    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "modifier_group_minimum_not_met"


def test_modifier_catalog_updates_and_archives_without_mutating_order_history() -> None:
    client = _client_with_seeded_database()
    burger_id = "018f6f73-2d0a-74f0-8f1c-000000000111"
    beef_id = "018f6f73-2d0a-74f0-8f1c-000000000311"

    group = client.post(
        f"/api/v1/products/{burger_id}/modifier-groups",
        headers=_admin_headers(),
        json={"name": "Extras editables", "minimum_selections": 0, "maximum_selections": 1},
    ).json()
    option = client.post(
        f"/api/v1/modifier-groups/{group['id']}/options",
        headers=_admin_headers(),
        json={
            "name": "Carne extra editable",
            "effect_type": "add",
            "affected_item_id": beef_id,
            "add_quantity": "50",
            "price_delta_cents": 2000,
            "kitchen_text": "Agregar carne extra original",
        },
    ).json()
    assert _open_shift(client, 10000).status_code == 200
    historical_order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "lines": [
                {
                    "product_id": burger_id,
                    "quantity": 1,
                    "modifiers": [{"option_id": option["id"]}],
                }
            ]
        },
    )
    assert historical_order.status_code == 200
    historical_payload = historical_order.json()

    group_update = client.patch(
        f"/api/v1/modifier-groups/{group['id']}",
        headers=_admin_headers(),
        json={
            "name": "Extras premium",
            "is_required": False,
            "minimum_selections": 0,
            "maximum_selections": 2,
        },
    )
    assert group_update.status_code == 200
    assert group_update.json()["name"] == "Extras premium"
    assert group_update.json()["maximum_selections"] == 2

    option_update = client.patch(
        f"/api/v1/modifier-options/{option['id']}",
        headers=_admin_headers(),
        json={
            "name": "Carne extra premium",
            "effect_type": "add",
            "affected_item_id": beef_id,
            "add_quantity": "25",
            "remove_quantity": "0",
            "price_delta_cents": 3000,
            "kitchen_text": "Agregar carne extra premium",
        },
    )
    assert option_update.status_code == 200
    assert option_update.json()["price_delta_cents"] == 3000
    assert str(option_update.json()["add_quantity"]) == "25.000000"

    catalog = client.get(
        f"/api/v1/products/{burger_id}/modifiers?branch_id={BRANCH_ID}",
        headers=_admin_headers(),
    ).json()
    updated_group = next(item for item in catalog if item["id"] == group["id"])
    updated_option = next(item for item in updated_group["options"] if item["id"] == option["id"])
    assert updated_group["name"] == "Extras premium"
    assert updated_option["name"] == "Carne extra premium"
    assert updated_option["price_delta_cents"] == 3000

    factory = _test_session_factory(client)
    with factory() as session:
        historical_snapshot = (
            session.execute(
                order_line_consumption_snapshots.select().where(
                    order_line_consumption_snapshots.c.order_id == historical_payload["id"]
                )
            )
            .mappings()
            .one()
        )
        frozen = next(
            item for item in historical_snapshot["modifiers"] if item["option_id"] == option["id"]
        )
        assert frozen["group_name"] == "Extras editables"
        assert frozen["option_name"] == "Carne extra editable"
        assert frozen["price_delta_cents"] == 2000
        assert str(frozen["add_quantity"]) == "50.000000"

    archived_option = client.delete(
        f"/api/v1/modifier-options/{option['id']}", headers=_admin_headers()
    )
    assert archived_option.status_code == 200
    assert archived_option.json()["status"] == "archived"
    unavailable = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "lines": [
                {
                    "product_id": burger_id,
                    "quantity": 1,
                    "modifiers": [{"option_id": option["id"]}],
                }
            ]
        },
    )
    assert unavailable.status_code == 409
    assert unavailable.json()["detail"]["code"] == "modifier_option_unavailable"
    archived_name_conflict = client.post(
        f"/api/v1/modifier-groups/{group['id']}/options",
        headers=_admin_headers(),
        json={
            "name": "Carne extra premium",
            "effect_type": "add",
            "affected_item_id": beef_id,
            "add_quantity": "25",
            "price_delta_cents": 3000,
        },
    )
    assert archived_name_conflict.status_code == 409
    assert archived_name_conflict.json()["detail"]["code"] == "modifier_option_name_conflict"

    replacement = client.post(
        f"/api/v1/modifier-groups/{group['id']}/options",
        headers=_admin_headers(),
        json={
            "name": "Doble carne temporal",
            "effect_type": "add",
            "affected_item_id": beef_id,
            "add_quantity": "100",
            "price_delta_cents": 3500,
        },
    ).json()
    branch_disabled = client.put(
        f"/api/v1/modifier-options/{replacement['id']}/branches/{BRANCH_ID}",
        headers=_admin_headers(),
        json={"is_enabled": False, "price_delta_cents": 9999},
    )
    assert branch_disabled.status_code == 200
    point_of_sale_catalog = client.get(
        f"/api/v1/products/{burger_id}/modifiers?branch_id={BRANCH_ID}",
        headers=_admin_headers(),
    ).json()
    point_of_sale_group = next(item for item in point_of_sale_catalog if item["id"] == group["id"])
    assert point_of_sale_group["options"] == []
    central_catalog = client.get(
        f"/api/v1/products/{burger_id}/modifier-groups", headers=_admin_headers()
    )
    assert central_catalog.status_code == 200
    central_group = next(item for item in central_catalog.json() if item["id"] == group["id"])
    central_replacement = next(
        item for item in central_group["options"] if item["id"] == replacement["id"]
    )
    assert central_replacement["price_delta_cents"] == 3500
    assert central_replacement["catalog_price_delta_cents"] == 3500
    archived_group = client.delete(
        f"/api/v1/modifier-groups/{group['id']}", headers=_admin_headers()
    )
    assert archived_group.status_code == 200
    assert archived_group.json()["status"] == "archived"
    assert archived_group.json()["archived_option_count"] == 1
    catalog_after_group_archive = client.get(
        f"/api/v1/products/{burger_id}/modifiers?branch_id={BRANCH_ID}",
        headers=_admin_headers(),
    ).json()
    assert all(item["id"] != group["id"] for item in catalog_after_group_archive)

    with factory() as session:
        assert session.execute(
            modifier_groups.select().where(modifier_groups.c.id == group["id"])
        ).mappings().one()["status"] == "archived"
        assert session.execute(
            modifier_options.select().where(modifier_options.c.id == replacement["id"])
        ).mappings().one()["status"] == "archived"
        actions = set(
            session.execute(
                audit_events.select()
                .with_only_columns(audit_events.c.action)
                .where(
                    audit_events.c.entity_id.in_([group["id"], option["id"]]),
                    audit_events.c.action.in_(
                        [
                            "modifier_group.updated",
                            "modifier_group.archived",
                            "modifier_option.updated",
                            "modifier_option.archived",
                        ]
                    ),
                )
            ).scalars()
        )
        assert actions == {
            "modifier_group.updated",
            "modifier_group.archived",
            "modifier_option.updated",
            "modifier_option.archived",
        }
        corporate_actions = actions | {"modifier_group.created", "modifier_option.created"}
        audit_branches = set(
            session.execute(
                audit_events.select()
                .with_only_columns(audit_events.c.branch_id)
                .where(audit_events.c.action.in_(corporate_actions))
            ).scalars()
        )
        assert audit_branches == {None}


def test_modifier_option_archive_rejects_impossible_required_group() -> None:
    client = _client_with_seeded_database()
    burger_id = "018f6f73-2d0a-74f0-8f1c-000000000111"
    beef_id = "018f6f73-2d0a-74f0-8f1c-000000000311"
    group = client.post(
        f"/api/v1/products/{burger_id}/modifier-groups",
        headers=_admin_headers(),
        json={"name": "Elección obligatoria", "minimum_selections": 1, "maximum_selections": 1},
    ).json()
    option = client.post(
        f"/api/v1/modifier-groups/{group['id']}/options",
        headers=_admin_headers(),
        json={
            "name": "Única opción",
            "effect_type": "add",
            "affected_item_id": beef_id,
            "add_quantity": "25",
            "price_delta_cents": 1000,
        },
    ).json()

    impossible_update = client.patch(
        f"/api/v1/modifier-groups/{group['id']}",
        headers=_admin_headers(),
        json={"minimum_selections": 2, "maximum_selections": 2, "is_required": True},
    )
    assert impossible_update.status_code == 409
    assert impossible_update.json()["detail"]["code"] == "modifier_group_cardinality_conflict"

    response = client.delete(
        f"/api/v1/modifier-options/{option['id']}", headers=_admin_headers()
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "modifier_group_cardinality_conflict"

    canonical_note = client.post(
        f"/api/v1/products/{burger_id}/variation-notes",
        headers=_admin_headers(),
        json={"name": "Comentario administrado aparte"},
    ).json()
    protected_update = client.patch(
        f"/api/v1/modifier-options/{canonical_note['id']}",
        headers=_admin_headers(),
        json={"name": "No debe cambiar"},
    )
    protected_archive = client.delete(
        f"/api/v1/modifier-options/{canonical_note['id']}", headers=_admin_headers()
    )
    canonical_catalog = client.get(
        f"/api/v1/products/{burger_id}/modifier-groups", headers=_admin_headers()
    ).json()
    canonical_group = next(
        item
        for item in canonical_catalog
        if any(option["id"] == canonical_note["id"] for option in item["options"])
    )
    protected_create = client.post(
        f"/api/v1/modifier-groups/{canonical_group['id']}/options",
        headers=_admin_headers(),
        json={"name": "No debe agregarse", "effect_type": "instruction"},
    )
    assert protected_update.status_code == 409
    assert protected_update.json()["detail"]["code"] == "modifier_catalog_managed_elsewhere"
    assert protected_archive.status_code == 409
    assert protected_archive.json()["detail"]["code"] == "modifier_catalog_managed_elsewhere"
    assert protected_create.status_code == 409
    assert protected_create.json()["detail"]["code"] == "modifier_catalog_managed_elsewhere"

    unauthenticated_update = client.patch(
        f"/api/v1/modifier-groups/{group['id']}", json={"name": "X"}
    )
    assert unauthenticated_update.status_code == 401
    assert client.delete(f"/api/v1/modifier-options/{option['id']}").status_code == 401

    foreign_group = client.post(
        f"/api/v1/products/{burger_id}/modifier-groups",
        headers=_admin_headers(),
        json={
            "name": "Grupo de otra organización",
            "minimum_selections": 0,
            "maximum_selections": 1,
        },
    ).json()
    other_organization_id = "018f6f73-2d0a-74f0-8f1c-999999999999"
    now = datetime.now(UTC)
    factory = _test_session_factory(client)
    with factory() as session:
        session.execute(
            organizations.insert().values(
                id=other_organization_id,
                name="Otra organización",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            modifier_groups.update()
            .where(modifier_groups.c.id == foreign_group["id"])
            .values(organization_id=other_organization_id)
        )
        session.commit()
    cross_organization = client.post(
        f"/api/v1/modifier-groups/{foreign_group['id']}/options",
        headers=_admin_headers(),
        json={"name": "No autorizado", "effect_type": "instruction"},
    )
    assert cross_organization.status_code == 409
    assert cross_organization.json()["detail"]["code"] == "modifier_group_not_found"
    scoped_catalog = client.get(
        f"/api/v1/products/{burger_id}/modifier-groups", headers=_admin_headers()
    ).json()
    assert all(item["id"] != foreign_group["id"] for item in scoped_catalog)



def test_preset_variation_notes_force_invariants_snapshot_branch_scope_and_print() -> None:
    client = _client_with_seeded_database()
    burger_id = "018f6f73-2d0a-74f0-8f1c-000000000111"
    opened = _open_shift(client, 10000)
    assert opened.status_code == 200
    base_order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": burger_id, "quantity": 1}]},
    )
    assert base_order.status_code == 200
    base_total = base_order.json()["total_cents"]
    first = client.post(
        f"/api/v1/products/{burger_id}/variation-notes",
        headers=_admin_headers(),
        json={
            "name": "  Sin cebolla  ",
            "price_delta_cents": 9000,
            "inventory_effect": True,
            "add_quantity": "99",
        },
    )
    assert first.status_code == 200
    note = first.json()
    assert note["effect_type"] == "preset_instruction"
    assert note["price_delta_cents"] == 0
    assert note["inventory_effect"] is False
    assert note["affected_item_id"] is None and note["replacement_item_id"] is None
    assert str(note["add_quantity"]) == "0" and note["kitchen_text"] == "Sin cebolla"
    duplicate = client.post(
        f"/api/v1/products/{burger_id}/variation-notes",
        headers=_admin_headers(),
        json={"name": "sin CEBOLLA"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "variation_note_already_exists"
    second = client.post(
        f"/api/v1/products/{burger_id}/variation-notes",
        headers=_admin_headers(),
        json={"name": "Sin lechuga", "display_order": 2},
    )
    assert second.status_code == 200
    order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "lines": [{
                "product_id": burger_id,
                "quantity": 1,
                "modifiers": [
                    {"option_id": note["id"], "text": "texto malicioso"},
                    {"option_id": second.json()["id"]},
                ],
            }],
        },
    )
    assert order.status_code == 200
    payload = order.json()
    assert payload["total_cents"] == base_total
    assert payload["lines"][0]["modifier_total_cents"] == 0
    modifiers = payload["consumption_snapshots"][0]["modifiers"]
    assert {modifier["kitchen_text"] for modifier in modifiers} == {
        "Sin cebolla", "Sin lechuga"
    }
    assert payload["consumption_snapshots"][0]["components"] == (
        base_order.json()["consumption_snapshots"][0]["components"]
    )
    paid = client.post(
        f"/api/v1/orders/{payload['id']}/payments",
        headers=_admin_headers(),
        json={"amount_cents": payload["total_cents"], "method": "cash", "register_id": "CAJA-01"},
    )
    assert paid.status_code == 200
    kitchen = next(
        job for job in client.get("/api/v1/print-jobs", headers=_admin_headers()).json()
        if job["order_id"] == payload["id"] and job["job_type"] == "kitchen"
    )
    assert {
        modifier["kitchen_text"]
        for modifier in kitchen["payload"]["lines"][0]["selected_modifiers"]
    } == {"Sin cebolla", "Sin lechuga"}
    kds_task_id = payload["production_tasks"][0]["id"]
    kds_task = next(
        task for task in client.get("/api/v1/kds/tasks", headers=_admin_headers()).json()
        if task["id"] == kds_task_id
    )
    assert {
        modifier["kitchen_text"] for modifier in kds_task["selected_modifiers"]
    } == {"Sin cebolla", "Sin lechuga"}
    fixture = _branch_admin_fixture(client)
    supervisor_headers = _login_headers(client, "supervisor.norte@kiwi.local", "Temporal123+")
    forbidden = client.post(
        f"/api/v1/products/{burger_id}/variation-notes",
        headers=supervisor_headers,
        json={"name": "Central prohibida"},
    )
    assert forbidden.status_code == 403
    unavailable = client.put(
        f"/api/v1/branch-administration/catalog/variation-notes/{note['id']}",
        headers=supervisor_headers,
        json={"action": "unavailable"},
    )
    assert unavailable.status_code == 200
    effective_north = client.get(
        f"/api/v1/products/{burger_id}/modifiers?branch_id={fixture['branch_id']}",
        headers=supervisor_headers,
    ).json()
    north_names = {option["name"] for group in effective_north for option in group["options"]}
    assert "Sin cebolla" not in north_names
    effective_base = client.get(
        f"/api/v1/products/{burger_id}/modifiers?branch_id={BRANCH_ID}",
        headers=_admin_headers(),
    ).json()
    base_names = {option["name"] for group in effective_base for option in group["options"]}
    assert "Sin cebolla" in base_names
    inherited = client.put(
        f"/api/v1/branch-administration/catalog/variation-notes/{note['id']}",
        headers=supervisor_headers,
        json={"action": "inherit"},
    )
    assert inherited.status_code == 200
    updated = client.put(
        f"/api/v1/variation-notes/{note['id']}",
        headers=_admin_headers(),
        json={"name": "Sin cebolla especial"},
    )
    assert updated.status_code == 200
    archived = client.put(
        f"/api/v1/variation-notes/{note['id']}",
        headers=_admin_headers(),
        json={"status": "archived"},
    )
    assert archived.status_code == 200
    reactivated = client.put(
        f"/api/v1/variation-notes/{note['id']}",
        headers=_admin_headers(),
        json={"status": "active"},
    )
    assert reactivated.status_code == 200
    with _test_session_factory(client)() as session:
        events = session.execute(
            audit_events.select().where(audit_events.c.entity_id == note["id"])
        ).mappings().all()
    actions = {event["action"] for event in events}
    assert {
        "variation_note.created",
        "variation_note.updated",
        "variation_note.archived",
        "variation_note.reactivated",
        "variation_note.branch_configured",
    } <= actions
    branch_event = next(
        event for event in events
        if event["action"] == "variation_note.branch_configured"
    )
    assert branch_event["branch_id"] == fixture["branch_id"]
    assert branch_event["actor_user_id"] == fixture["supervisor_id"]


def test_variation_group_conflict_preserves_advanced_group_and_safe_group_reuses() -> None:
    client = _client_with_seeded_database()
    burger_id = "018f6f73-2d0a-74f0-8f1c-000000000111"
    conflicting_group = client.post(
        f"/api/v1/products/{burger_id}/modifier-groups",
        headers=_admin_headers(),
        json={
            "name": "Variaciones y cambios",
            "is_required": True,
            "minimum_selections": 1,
            "maximum_selections": 1,
        },
    )
    assert conflicting_group.status_code == 200
    instruction = client.post(
        f"/api/v1/modifier-groups/{conflicting_group.json()['id']}/options",
        headers=_admin_headers(),
        json={"name": "Instrucción libre", "effect_type": "instruction", "inventory_effect": False},
    )
    assert instruction.status_code == 200
    conflict = client.post(
        f"/api/v1/products/{burger_id}/variation-notes",
        headers=_admin_headers(),
        json={"name": "Sin cebolla"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "variation_group_conflict"
    with _test_session_factory(client)() as session:
        group = session.execute(
            modifier_groups.select().where(modifier_groups.c.id == conflicting_group.json()["id"])
        ).mappings().one()
        options = session.execute(
            modifier_options.select().where(modifier_options.c.group_id == group["id"])
        ).mappings().all()
    assert group["is_required"] is True
    assert group["minimum_selections"] == 1 and group["maximum_selections"] == 1
    assert [(option["name"], option["effect_type"]) for option in options] == [
        ("Instrucción libre", "instruction")
    ]

    fries_id = "018f6f73-2d0a-74f0-8f1c-000000000112"
    first = client.post(
        f"/api/v1/products/{fries_id}/variation-notes",
        headers=_admin_headers(),
        json={"name": "Sin sal"},
    )
    second = client.post(
        f"/api/v1/products/{fries_id}/variation-notes",
        headers=_admin_headers(),
        json={"name": "Bien doradas"},
    )
    assert first.status_code == 200 and second.status_code == 200
    with _test_session_factory(client)() as session:
        groups = session.execute(
            modifier_groups.select().where(
                modifier_groups.c.product_id == fries_id,
                modifier_groups.c.name == "Variaciones y cambios",
            )
        ).mappings().all()
    assert len(groups) == 1
    assert groups[0]["is_required"] is False
    assert groups[0]["minimum_selections"] == 0 and groups[0]["maximum_selections"] == 2


def test_modifier_option_instruction_with_empty_item_ids_normalises_to_null() -> None:
    """Regression: admin-web sends '' for affected/replacement_item_id on instruction options."""
    client = _client_with_seeded_database()
    burger_id = "018f6f73-2d0a-74f0-8f1c-000000000111"
    group = client.post(
        f"/api/v1/products/{burger_id}/modifier-groups",
        headers=_admin_headers(),
        json={"name": "Tipo aderezo", "minimum_selections": 1, "maximum_selections": 1},
    ).json()
    option = client.post(
        f"/api/v1/modifier-groups/{group['id']}/options",
        headers=_admin_headers(),
        json={
            "name": "Aderezo ranch",
            "effect_type": "instruction",
            "price_delta_cents": 0,
            "affected_item_id": "",
            "replacement_item_id": "",
            "remove_quantity": "0",
            "add_quantity": "0",
            "kitchen_text": "Aderezo ranch",
        },
    )
    assert option.status_code == 200, option.text
    data = option.json()
    assert data["affected_item_id"] is None
    assert data["replacement_item_id"] is None
    assert data["effect_type"] == "instruction"


def test_variation_display_order_validation_never_mutates_or_raises_server_error() -> None:
    client = _client_with_seeded_database()
    product_id = "018f6f73-2d0a-74f0-8f1c-000000000111"
    for invalid in ("abc", None, True):
        response = client.post(
            f"/api/v1/products/{product_id}/variation-notes",
            headers=_admin_headers(),
            json={"name": "Orden inválido", "display_order": invalid},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "invalid_variation_display_order"
    created = client.post(
        f"/api/v1/products/{product_id}/variation-notes",
        headers=_admin_headers(),
        json={"name": "Orden estable", "display_order": 4},
    )
    assert created.status_code == 200
    for invalid in ("abc", None, False):
        response = client.put(
            f"/api/v1/variation-notes/{created.json()['id']}",
            headers=_admin_headers(),
            json={"display_order": invalid},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "invalid_variation_display_order"
    listed = client.get(
        f"/api/v1/catalog/variation-notes?product_id={product_id}", headers=_admin_headers()
    ).json()
    assert next(note for note in listed if note["id"] == created.json()["id"])["display_order"] == 4


def test_real_waste_draft_confirmation_costing_idempotency_and_reversal() -> None:
    client = _client_with_seeded_database()
    piece_id = "018f6f73-2d0a-74f0-8f1c-000000000303"
    kilogram = client.post(
        "/api/v1/inventory/units",
        headers=_admin_headers(),
        json={
            "code": "KG-WASTE",
            "name": "Kilogramo merma",
            "precision_scale": 3,
            "dimension": "mass",
        },
    ).json()
    item = client.post(
        "/api/v1/inventory/items",
        headers=_admin_headers(),
        json={
            "name": "Pulpa para merma",
            "sku": "09105",
            "base_unit_id": kilogram["id"],
            "item_type": "ingredient",
        },
    ).json()

    supplier = client.post(
        "/api/v1/suppliers",
        headers=_admin_headers(),
        json={
            "code": "PROV-WASTE",
            "commercial_name": "Proveedor Merma",
            "delivery_days": [],
            "payment_methods": ["transfer"],
        },
    ).json()
    assert (
        client.put(
            f"/api/v1/suppliers/{supplier['id']}/branches/{BRANCH_ID}",
            headers=_admin_headers(),
            json={"is_enabled": True},
        ).status_code
        == 200
    )
    presentation = client.post(
        "/api/v1/purchase-presentations",
        headers=_admin_headers(),
        json={
            "supplier_id": supplier["id"],
            "item_id": item["id"],
            "code": "PULP-10",
            "name": "Cubeta 10 kg",
            "package_type": "bucket",
            "commercial_quantity": "1",
            "commercial_unit_id": piece_id,
            "base_unit_id": kilogram["id"],
            "base_unit_yield": "10",
            "usable_content": "10",
            "yield_percent": "1",
            "last_net_price": "250",
            "tax_rate": "0",
        },
    ).json()
    purchase = client.post(
        "/api/v1/purchases",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "supplier_id": supplier["id"],
            "document_type": "invoice",
            "folio": "WASTE-COST-001",
            "payment_method": "transfer",
            "paid_from_cash": False,
            "lines": [
                {
                    "presentation_id": presentation["id"],
                    "quantity": "1",
                    "unit_price": "250",
                    "discount": "0",
                    "tax": "0",
                }
            ],
        },
    ).json()
    assert (
        client.post(
            f"/api/v1/purchases/{purchase['id']}/confirm",
            headers={**_admin_headers(), "Idempotency-Key": "purchase-waste-cost"},
            json={},
        ).status_code
        == 200
    )

    reason = client.post(
        "/api/v1/inventory/waste-reasons",
        headers=_admin_headers(),
        json={"code": "TEST_SPILL", "name": "Derrame de prueba", "classification": "operation"},
    ).json()
    before_movements = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    ).json()["counts"][
        "inventory_movements"
    ]
    draft_response = client.post(
        "/api/v1/inventory/wastes",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "item_id": item["id"],
            "unit_id": kilogram["id"],
            "reason_id": reason["id"],
            "quantity": "2",
            "stage": "preparation",
            "notes": "Cubeta derramada",
            "evidence": ["evidence://photo/waste-001"],
        },
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["status"] == "draft"
    assert draft["movements"] == []
    assert (
        client.get("/api/v1/platform/bootstrap-status", headers=_admin_headers()).json()[
            "counts"
        ]["inventory_movements"]
        == before_movements
    )

    confirmation_headers = {**_admin_headers(), "Idempotency-Key": "waste-confirm-001"}
    confirmation = client.post(
        f"/api/v1/inventory/wastes/{draft['id']}/confirm",
        headers=confirmation_headers,
        json={},
    )
    assert confirmation.status_code == 200
    confirmed = confirmation.json()
    assert confirmed["status"] == "confirmed"
    assert float(confirmed["unit_cost"]) == 25
    assert float(confirmed["total_cost"]) == 50
    assert confirmed["created_by"] == ADMIN_USER_ID
    assert confirmed["confirmed_by"] == ADMIN_USER_ID
    assert len(confirmed["movements"]) == 1
    movement = confirmed["movements"][0]
    assert movement["movement_type"] == "WASTE_REAL"
    assert float(movement["quantity_delta"]) == -2
    assert float(movement["total_cost"]) == -50

    replay = client.post(
        f"/api/v1/inventory/wastes/{draft['id']}/confirm",
        headers=confirmation_headers,
        json={},
    )
    assert replay.status_code == 200
    assert len(replay.json()["movements"]) == 1
    costs = client.get(
        f"/api/v1/inventory/costs?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).json()
    cost = next(row for row in costs if row["item_id"] == item["id"])
    assert float(cost["quantity_on_hand"]) == 8
    assert float(cost["average_unit_cost"]) == 25

    wrong_key = client.post(
        f"/api/v1/inventory/wastes/{draft['id']}/confirm",
        headers={**_admin_headers(), "Idempotency-Key": "waste-other-key"},
        json={},
    )
    assert wrong_key.status_code == 409
    assert wrong_key.json()["detail"]["code"] == "waste_already_confirmed"

    reversal_headers = {**_admin_headers(), "Idempotency-Key": "waste-reverse-001"}
    reversal = client.post(
        f"/api/v1/inventory/wastes/{draft['id']}/reverse",
        headers=reversal_headers,
        json={"reason": "Cantidad capturada por error"},
    )
    assert reversal.status_code == 200
    reversed_waste = reversal.json()
    assert reversed_waste["status"] == "reversed"
    assert len(reversed_waste["movements"]) == 2
    reverse_movement = next(
        row for row in reversed_waste["movements"] if row["movement_type"] == "WASTE_REVERSAL"
    )
    assert float(reverse_movement["quantity_delta"]) == 2
    assert reverse_movement["reversal_of_id"] == movement["id"]
    reversal_replay = client.post(
        f"/api/v1/inventory/wastes/{draft['id']}/reverse",
        headers=reversal_headers,
        json={"reason": "Cantidad capturada por error"},
    )
    assert reversal_replay.status_code == 200
    assert len(reversal_replay.json()["movements"]) == 2
    costs_after = client.get(
        f"/api/v1/inventory/costs?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).json()
    cost_after = next(row for row in costs_after if row["item_id"] == item["id"])
    assert float(cost_after["quantity_on_hand"]) == 10
    assert float(cost_after["average_unit_cost"]) == 25

    insufficient = client.post(
        "/api/v1/inventory/wastes",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "item_id": item["id"],
            "reason_id": reason["id"],
            "quantity": "11",
            "stage": "storage",
            "evidence": [],
        },
    ).json()
    insufficient_confirmation = client.post(
        f"/api/v1/inventory/wastes/{insufficient['id']}/confirm",
        headers={**_admin_headers(), "Idempotency-Key": "waste-insufficient"},
        json={},
    )
    assert insufficient_confirmation.status_code == 409
    assert insufficient_confirmation.json()["detail"]["code"] == "insufficient_waste_inventory"
    listed = client.get(f"/api/v1/inventory/wastes?branch_id={BRANCH_ID}", headers=_admin_headers())
    assert listed.status_code == 200
    stored_insufficient = next(row for row in listed.json() if row["id"] == insufficient["id"])
    assert stored_insufficient["status"] == "draft"
    assert stored_insufficient["movements"] == []

    assert (
        client.put(
            f"/api/v1/inventory/waste-reasons/{reason['id']}",
            headers=_admin_headers(),
            json={"status": "inactive"},
        ).status_code
        == 200
    )
    inactive_reason = client.post(
        "/api/v1/inventory/wastes",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "item_id": item["id"],
            "reason_id": reason["id"],
            "quantity": "1",
            "stage": "storage",
        },
    )
    assert inactive_reason.status_code == 409
    assert inactive_reason.json()["detail"]["code"] == "active_waste_reason_not_found"


def test_inventory_transfer_partial_receipt_preserves_cost_and_idempotency() -> None:
    client = _client_with_seeded_database()
    piece_id = "018f6f73-2d0a-74f0-8f1c-000000000303"
    destination = client.post(
        "/api/v1/branches",
        headers=_admin_headers(),
        json={"name": "Sucursal Destino", "code": "DESTINO"},
    ).json()
    kilogram = client.post(
        "/api/v1/inventory/units",
        headers=_admin_headers(),
        json={
            "code": "KG-TRANSFER",
            "name": "Kilogramo traspaso",
            "precision_scale": 3,
            "dimension": "mass",
        },
    ).json()
    item = client.post(
        "/api/v1/inventory/items",
        headers=_admin_headers(),
        json={
            "name": "Pulpa transferible",
            "sku": "09106",
            "base_unit_id": kilogram["id"],
            "item_type": "ingredient",
        },
    ).json()
    supplier = client.post(
        "/api/v1/suppliers",
        headers=_admin_headers(),
        json={
            "code": "PROV-TRANSFER",
            "commercial_name": "Proveedor Traspaso",
            "delivery_days": [],
            "payment_methods": ["transfer"],
        },
    ).json()
    assert (
        client.put(
            f"/api/v1/suppliers/{supplier['id']}/branches/{BRANCH_ID}",
            headers=_admin_headers(),
            json={"is_enabled": True},
        ).status_code
        == 200
    )
    presentation = client.post(
        "/api/v1/purchase-presentations",
        headers=_admin_headers(),
        json={
            "supplier_id": supplier["id"],
            "item_id": item["id"],
            "code": "TRANSFER-10",
            "name": "Cubeta transferible 10 kg",
            "package_type": "bucket",
            "commercial_quantity": "1",
            "commercial_unit_id": piece_id,
            "base_unit_id": kilogram["id"],
            "base_unit_yield": "10",
            "usable_content": "10",
            "yield_percent": "1",
            "last_net_price": "250",
            "tax_rate": "0",
        },
    ).json()
    purchase = client.post(
        "/api/v1/purchases",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "supplier_id": supplier["id"],
            "document_type": "invoice",
            "folio": "TRANSFER-COST-001",
            "payment_method": "transfer",
            "paid_from_cash": False,
            "lines": [
                {
                    "presentation_id": presentation["id"],
                    "quantity": "1",
                    "unit_price": "250",
                    "discount": "0",
                    "tax": "0",
                }
            ],
        },
    ).json()
    assert (
        client.post(
            f"/api/v1/purchases/{purchase['id']}/confirm",
            headers={**_admin_headers(), "Idempotency-Key": "purchase-transfer-cost"},
            json={},
        ).status_code
        == 200
    )

    before_movements = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    ).json()["counts"][
        "inventory_movements"
    ]
    draft_response = client.post(
        "/api/v1/inventory/transfers",
        headers=_admin_headers(),
        json={
            "source_branch_id": BRANCH_ID,
            "destination_branch_id": destination["id"],
            "notes": "Traspaso de prueba",
            "lines": [{"item_id": item["id"], "unit_id": kilogram["id"], "quantity": "10"}],
        },
    )
    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert draft["status"] == "draft"
    assert draft["movements"] == []
    assert (
        client.get("/api/v1/platform/bootstrap-status", headers=_admin_headers()).json()[
            "counts"
        ]["inventory_movements"]
        == before_movements
    )

    send_headers = {**_admin_headers(), "Idempotency-Key": "transfer-send-001"}
    sent_response = client.post(
        f"/api/v1/inventory/transfers/{draft['id']}/send",
        headers=send_headers,
        json={},
    )
    assert sent_response.status_code == 200
    sent = sent_response.json()
    assert sent["status"] == "sent"
    line = sent["lines"][0]
    assert float(line["sent_quantity"]) == 10
    assert float(line["unit_cost"]) == 25
    assert float(line["sent_total_cost"]) == 250
    transfer_out = next(row for row in sent["movements"] if row["movement_type"] == "TRANSFER_OUT")
    assert float(transfer_out["quantity_delta"]) == -10
    assert float(transfer_out["total_cost"]) == -250
    sent_replay = client.post(
        f"/api/v1/inventory/transfers/{draft['id']}/send",
        headers=send_headers,
        json={},
    )
    assert sent_replay.status_code == 200
    assert len(sent_replay.json()["movements"]) == 1
    wrong_send_key = client.post(
        f"/api/v1/inventory/transfers/{draft['id']}/send",
        headers={**_admin_headers(), "Idempotency-Key": "transfer-send-other"},
        json={},
    )
    assert wrong_send_key.status_code == 409
    assert wrong_send_key.json()["detail"]["code"] == "transfer_already_sent"

    receive_headers = {**_admin_headers(), "Idempotency-Key": "transfer-receive-001"}
    received_response = client.post(
        f"/api/v1/inventory/transfers/{draft['id']}/receive",
        headers=receive_headers,
        json={
            "lines": [
                {
                    "line_id": line["id"],
                    "received_quantity": "9.5",
                    "condition": "damaged",
                    "difference_reason": "Envase dañado durante traslado",
                }
            ]
        },
    )
    assert received_response.status_code == 200
    received = received_response.json()
    assert received["status"] == "received_with_difference"
    received_line = received["lines"][0]
    assert float(received_line["received_quantity"]) == 9.5
    assert float(received_line["difference_quantity"]) == 0.5
    assert float(received_line["received_total_cost"]) == 237.5
    assert float(received_line["difference_cost"]) == 12.5
    transfer_in = next(
        row for row in received["movements"] if row["movement_type"] == "TRANSFER_IN"
    )
    assert float(transfer_in["quantity_delta"]) == 9.5
    assert float(transfer_in["total_cost"]) == 237.5
    assert all(row["movement_type"] != "PURCHASE_RECEIPT" for row in received["movements"])

    received_replay = client.post(
        f"/api/v1/inventory/transfers/{draft['id']}/receive",
        headers=receive_headers,
        json={
            "lines": [
                {"line_id": line["id"], "received_quantity": "9.5", "difference_reason": "retry"}
            ]
        },
    )
    assert received_replay.status_code == 200
    assert len(received_replay.json()["movements"]) == 2
    wrong_receive_key = client.post(
        f"/api/v1/inventory/transfers/{draft['id']}/receive",
        headers={**_admin_headers(), "Idempotency-Key": "transfer-receive-other"},
        json={
            "lines": [
                {"line_id": line["id"], "received_quantity": "9.5", "difference_reason": "retry"}
            ]
        },
    )
    assert wrong_receive_key.status_code == 409
    assert wrong_receive_key.json()["detail"]["code"] == "transfer_already_received"

    source_costs = client.get(
        f"/api/v1/inventory/costs?branch_id={BRANCH_ID}", headers=_admin_headers()
    ).json()
    source_cost = next(row for row in source_costs if row["item_id"] == item["id"])
    assert float(source_cost["quantity_on_hand"]) == 0
    assert float(source_cost["average_unit_cost"]) == 25
    destination_costs = client.get(
        f"/api/v1/inventory/costs?branch_id={destination['id']}",
        headers=_admin_headers(),
    ).json()
    destination_cost = next(row for row in destination_costs if row["item_id"] == item["id"])
    assert float(destination_cost["quantity_on_hand"]) == 9.5
    assert float(destination_cost["average_unit_cost"]) == 25
    destination_list = client.get(
        f"/api/v1/inventory/transfers?branch_id={destination['id']}",
        headers=_admin_headers(),
    )
    assert destination_list.status_code == 200
    assert destination_list.json()[0]["id"] == draft["id"]

    insufficient = client.post(
        "/api/v1/inventory/transfers",
        headers=_admin_headers(),
        json={
            "source_branch_id": BRANCH_ID,
            "destination_branch_id": destination["id"],
            "lines": [{"item_id": item["id"], "quantity": "1"}],
        },
    ).json()
    insufficient_send = client.post(
        f"/api/v1/inventory/transfers/{insufficient['id']}/send",
        headers={**_admin_headers(), "Idempotency-Key": "transfer-insufficient"},
        json={},
    )
    assert insufficient_send.status_code == 409
    assert insufficient_send.json()["detail"]["code"] == "insufficient_transfer_inventory"
    stored_insufficient = next(
        row
        for row in client.get(
            f"/api/v1/inventory/transfers?branch_id={BRANCH_ID}",
            headers=_admin_headers(),
        ).json()
        if row["id"] == insufficient["id"]
    )
    assert stored_insufficient["status"] == "draft"
    assert stored_insufficient["movements"] == []


def test_physical_count_blind_snapshot_preserves_intermediate_movements() -> None:
    client = _client_with_seeded_database()
    beef_id = "018f6f73-2d0a-74f0-8f1c-000000000311"
    burger_id = "018f6f73-2d0a-74f0-8f1c-000000000111"
    before_movements = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    ).json()["counts"][
        "inventory_movements"
    ]
    opened_response = client.post(
        "/api/v1/inventory/physical-counts",
        headers=_admin_headers(),
        json={"branch_id": BRANCH_ID, "item_ids": [beef_id], "notes": "Conteo selectivo de carne"},
    )
    assert opened_response.status_code == 200
    opened = opened_response.json()
    assert opened["status"] == "counting"
    assert opened["blind"] is True
    assert len(opened["lines"]) == 1
    line = opened["lines"][0]
    assert "theoretical_quantity" not in line
    assert "snapshot_difference" not in line
    assert opened["movements"] == []
    assert (
        client.get("/api/v1/platform/bootstrap-status", headers=_admin_headers()).json()[
            "counts"
        ]["inventory_movements"]
        == before_movements
    )

    duplicate = client.post(
        "/api/v1/inventory/physical-counts",
        headers=_admin_headers(),
        json={"branch_id": BRANCH_ID, "item_ids": [beef_id]},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "active_physical_count_exists"
    incomplete = client.post(
        f"/api/v1/inventory/physical-counts/{opened['id']}/submit",
        headers=_admin_headers(),
        json={},
    )
    assert incomplete.status_code == 409
    assert incomplete.json()["detail"]["code"] == "physical_count_incomplete"

    captured_response = client.put(
        f"/api/v1/inventory/physical-counts/{opened['id']}/lines/{line['id']}",
        headers=_admin_headers(),
        json={"counted_quantity": "24800", "notes": "Dos paquetes faltantes"},
    )
    assert captured_response.status_code == 200
    captured_line = captured_response.json()["lines"][0]
    assert float(captured_line["counted_quantity"]) == 24800
    assert "theoretical_quantity" not in captured_line
    submitted_response = client.post(
        f"/api/v1/inventory/physical-counts/{opened['id']}/submit",
        headers=_admin_headers(),
        json={},
    )
    assert submitted_response.status_code == 200
    submitted = submitted_response.json()
    assert submitted["status"] == "submitted"
    assert submitted["blind"] is False
    submitted_line = submitted["lines"][0]
    assert float(submitted_line["theoretical_quantity"]) == 25000
    assert float(submitted_line["snapshot_difference"]) == -200
    immutable_capture = client.put(
        f"/api/v1/inventory/physical-counts/{opened['id']}/lines/{line['id']}",
        headers=_admin_headers(),
        json={"counted_quantity": "24900"},
    )
    assert immutable_capture.status_code == 409
    assert immutable_capture.json()["detail"]["code"] == "physical_count_not_editable"

    assert (
        _open_shift(client, 10000).status_code
        == 200
    )
    order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": burger_id, "quantity": 1}]},
    ).json()
    task_id = order["production_tasks"][0]["id"]
    assert (
        client.post(
            f"/api/v1/kds/tasks/{task_id}/transition",
            headers=_admin_headers(),
            json={"status": "IN_PROGRESS"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/kds/tasks/{task_id}/transition",
            headers=_admin_headers(),
            json={"status": "COMPLETED"},
        ).status_code
        == 200
    )
    stock_before_approval = next(
        row
        for row in client.get(
            "/api/v1/inventory/stock", headers=_admin_headers()
        ).json()
        if row["id"] == beef_id
    )
    assert float(stock_before_approval["quantity_on_hand"]) == 24880

    approval_headers = {**_admin_headers(), "Idempotency-Key": "physical-count-approve-001"}
    approved_response = client.post(
        f"/api/v1/inventory/physical-counts/{opened['id']}/approve",
        headers=approval_headers,
        json={},
    )
    assert approved_response.status_code == 200
    approved = approved_response.json()
    assert approved["status"] == "approved"
    approved_line = approved["lines"][0]
    assert float(approved_line["snapshot_difference"]) == -200
    assert float(approved_line["approval_ledger_quantity"]) == 24880
    assert float(approved_line["adjustment_quantity"]) == -80
    assert len(approved["movements"]) == 1
    adjustment = approved["movements"][0]
    assert adjustment["movement_type"] == "COUNT_ADJUSTMENT"
    assert float(adjustment["quantity_delta"]) == -80

    replay = client.post(
        f"/api/v1/inventory/physical-counts/{opened['id']}/approve",
        headers=approval_headers,
        json={},
    )
    assert replay.status_code == 200
    assert len(replay.json()["movements"]) == 1
    wrong_key = client.post(
        f"/api/v1/inventory/physical-counts/{opened['id']}/approve",
        headers={**_admin_headers(), "Idempotency-Key": "physical-count-other"},
        json={},
    )
    assert wrong_key.status_code == 409
    assert wrong_key.json()["detail"]["code"] == "physical_count_already_approved"
    closed = client.post(
        f"/api/v1/inventory/physical-counts/{opened['id']}/close",
        headers=_admin_headers(),
        json={},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    final_stock = next(
        row
        for row in client.get(
            "/api/v1/inventory/stock", headers=_admin_headers()
        ).json()
        if row["id"] == beef_id
    )
    assert float(final_stock["quantity_on_hand"]) == 24800

    cancellable = client.post(
        "/api/v1/inventory/physical-counts",
        headers=_admin_headers(),
        json={"branch_id": BRANCH_ID, "item_ids": [beef_id]},
    ).json()
    cancelled = client.post(
        f"/api/v1/inventory/physical-counts/{cancellable['id']}/cancel",
        headers=_admin_headers(),
        json={"reason": "Conteo abierto por error"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["movements"] == []


def test_admin_can_create_user_role_and_assignment() -> None:
    client = _client_with_seeded_database()

    role_response = client.post(
        "/api/v1/roles", headers=_admin_headers(), json={"name": "Cajero", "scope": "branch"}
    )
    assert role_response.status_code == 200
    role = role_response.json()
    assert role["name"] == "Cajero"
    assert role["scope"] == "branch"

    duplicate_role = client.post(
        "/api/v1/roles", headers=_admin_headers(), json={"name": "Cajero", "scope": "branch"}
    )
    assert duplicate_role.status_code == 409
    assert duplicate_role.json()["detail"]["code"] == "role_already_exists"

    user_response = client.post(
        "/api/v1/users",
        headers=_admin_headers(),
        json={
            "email": "cajero@kiwi.local",
            "display_name": "Cajero Piloto",
            "employee_code": "CAJ001",
        },
    )
    assert user_response.status_code == 200
    user = user_response.json()
    assert user["email"] == "cajero@kiwi.local"
    assert user["status"] == "invited"

    missing_branch_response = client.post(
        f"/api/v1/users/{user['id']}/roles",
        headers=_admin_headers(),
        json={"role_id": role["id"]},
    )
    assert missing_branch_response.status_code == 409
    assert missing_branch_response.json()["detail"]["code"] == "branch_assignment_required"

    assignment_response = client.post(
        f"/api/v1/users/{user['id']}/roles",
        headers=_admin_headers(),
        json={"role_id": role["id"], "branch_id": BRANCH_ID},
    )
    assert assignment_response.status_code == 200
    assert assignment_response.json()["branch_id"] == "018f6f73-2d0a-74f0-8f1c-000000000003"

    users_response = client.get("/api/v1/users", headers=_admin_headers())
    assert users_response.status_code == 200
    created_user = next(item for item in users_response.json() if item["id"] == user["id"])
    assert created_user["roles"][0]["role_name"] == "Cajero"

    roles_response = client.get("/api/v1/roles", headers=_admin_headers())
    assert roles_response.status_code == 200
    assert any(item["name"] == "Cajero" for item in roles_response.json())

    bootstrap_response = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    )
    assert bootstrap_response.status_code == 200
    assert bootstrap_response.json()["counts"]["audit_events"] == 4


def test_cash_order_and_kds_flow() -> None:
    client = _client_with_seeded_database()

    current_response = client.get(
        "/api/v1/cash/shifts/current",
        headers=_admin_headers(),

        params={"branch_id": BRANCH_ID, "register_id": "CAJA-01"},
    )
    assert current_response.status_code == 200
    assert current_response.json()["cash_shift"] is None

    order_without_shift = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]},
    )
    assert order_without_shift.status_code == 409
    assert order_without_shift.json()["detail"]["code"] == "cash_shift_required"

    open_response = _open_shift(client, 50000)
    assert open_response.status_code == 200
    assert open_response.json()["status"] == "OPEN"

    duplicate_open = _open_shift(client, 50000)
    assert duplicate_open.status_code == 409
    assert duplicate_open.json()["detail"]["code"] == "cash_shift_already_open"

    order_response = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 2}]},
    )
    assert order_response.status_code == 200
    order_payload = order_response.json()
    assert order_payload["status"] == "ACCEPTED"
    assert order_payload["folio"] == "PILOTO-000001"
    assert order_payload["total_cents"] == 19000
    assert order_payload["lines"][0]["product_name"] == "Hamburguesa Kiwi"
    assert order_payload["production_tasks"][0]["status"] == "PENDING"

    reserved_stock_response = client.get(
        "/api/v1/inventory/stock", headers=_admin_headers()
    )
    assert reserved_stock_response.status_code == 200
    reserved_stock = reserved_stock_response.json()
    reserved_beef = next(item for item in reserved_stock if item["sku"] == "INV-BEEF")
    reserved_bun = next(item for item in reserved_stock if item["sku"] == "INV-BUN")
    assert reserved_beef["quantity_on_hand"] == 24760
    assert reserved_bun["quantity_on_hand"] == 118

    reservation_kardex = client.get(
        f"/api/v1/inventory/kardex?item_id={reserved_beef['id']}",
        headers=_admin_headers(),
    )
    assert reservation_kardex.status_code == 200
    assert any(
        item["movement_type"] == "SALE_RESERVATION" and item["quantity_delta"] == -240
        for item in reservation_kardex.json()
    )

    tasks_response = client.get("/api/v1/kds/tasks", headers=_admin_headers())
    assert tasks_response.status_code == 200
    task = tasks_response.json()[0]
    assert task["folio"] == "PILOTO-000001"
    assert task["status"] == "PENDING"

    started_response = client.post(
        f"/api/v1/kds/tasks/{task['id']}/transition",
        headers=_admin_headers(),
        json={"status": "IN_PROGRESS"},
    )
    assert started_response.status_code == 200
    assert started_response.json()["status"] == "IN_PROGRESS"

    completed_response = client.post(
        f"/api/v1/kds/tasks/{task['id']}/transition",
        headers=_admin_headers(),
        json={"status": "COMPLETED"},
    )
    assert completed_response.status_code == 200
    assert completed_response.json()["status"] == "COMPLETED"

    consumed_stock_response = client.get(
        "/api/v1/inventory/stock", headers=_admin_headers()
    )
    assert consumed_stock_response.status_code == 200
    consumed_beef = next(
        item for item in consumed_stock_response.json() if item["sku"] == "INV-BEEF"
    )
    assert consumed_beef["quantity_on_hand"] == 24760

    consumption_kardex = client.get(
        f"/api/v1/inventory/kardex?item_id={reserved_beef['id']}",
        headers=_admin_headers(),
    )
    assert consumption_kardex.status_code == 200
    beef_movements = consumption_kardex.json()
    assert any(
        item["movement_type"] == "RESERVATION_RELEASE" and item["quantity_delta"] == 240
        for item in beef_movements
    )
    assert any(
        item["movement_type"] == "SALE_CONSUMPTION" and item["quantity_delta"] == -240
        for item in beef_movements
    )

    invalid_transition = client.post(
        f"/api/v1/kds/tasks/{task['id']}/transition",
        headers=_admin_headers(),
        json={"status": "PENDING"},
    )
    assert invalid_transition.status_code == 409
    assert invalid_transition.json()["detail"]["code"] == "invalid_task_transition"

    close_response = client.post(
        f"/api/v1/cash/shifts/{open_response.json()['id']}/close-operationally",
        headers={**_admin_headers(), "Idempotency-Key": "kds-operational-close"},
        json={},
    )
    assert close_response.status_code == 200
    assert close_response.json()["cash_shift"]["status"] == "OPERATIVELY_CLOSED"


def test_next_folio_uses_max_existing_suffix_instead_of_row_count() -> None:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        _seed(session)
        now = datetime(2026, 7, 10, 19, 45, tzinfo=UTC)
        session.execute(
            cash_shifts.insert().values(
                id="018f6f73-2d0a-74f0-8f1c-000000000701",
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                branch_id=BRANCH_ID,
                register_code="CAJA-01",
                status="OPEN",
                opening_cash_cents=10000,
                opened_at=now,
                closed_at=None,
                created_at=now,
            )
        )
        for order_id, folio in [
            ("018f6f73-2d0a-74f0-8f1c-000000000711", "PILOTO-000001"),
            ("018f6f73-2d0a-74f0-8f1c-000000000712", "PILOTO-000010"),
        ]:
            session.execute(
                orders.insert().values(
                    id=order_id,
                    organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                    branch_id=BRANCH_ID,
                    cash_shift_id="018f6f73-2d0a-74f0-8f1c-000000000701",
                    folio=folio,
                    channel="POS",
                    status="ACCEPTED",
                    total_cents=9500,
                    currency="MXN",
                    owner_name="Cliente General",
                    order_type="dine-in",
                    created_at=now,
                    accepted_at=now,
                )
            )

        assert _next_folio(session, BRANCH_ID) == "PILOTO-000011"


def test_customer_multiple_addresses_and_delivery_order_snapshot() -> None:
    client = _client_with_seeded_database()
    branch_id = BRANCH_ID
    customer_response = client.post(
        "/api/v1/customers",
        headers=_admin_headers(),
        json={
            "branch_id": branch_id,
            "name": "Renata Cliente",
            "email": "RENATA@example.com",
            "phones": [
                {"number": "669 123 4567", "is_primary": True, "whatsapp_enabled": True},
                {"number": "+52 669 765 4321", "type": "work"},
            ],
        },
    )
    assert customer_response.status_code == 200
    customer = customer_response.json()
    assert [phone["normalized_number"] for phone in customer["phones"]] == [
        "+526691234567",
        "+526697654321",
    ]

    duplicate_response = client.post(
        "/api/v1/customers",
        headers=_admin_headers(),
        json={"branch_id": branch_id, "name": "Coincidencia", "phones": [{"number": "6691234567"}]},
    )
    assert duplicate_response.status_code == 200
    duplicate = duplicate_response.json()
    assert duplicate["id"] != customer["id"]

    exact_phone_page = client.get(
        "/api/v1/customers",
        headers=_admin_headers(),
        params={"branch_id": branch_id, "phone": "6691234567", "limit": 20},
    )
    assert exact_phone_page.status_code == 200
    exact_page = exact_phone_page.json()
    assert {row["id"] for row in exact_page["items"]} == {
        customer["id"],
        duplicate["id"],
    }
    assert {row["name"] for row in exact_page["items"]} == {
        "Renata Cliente",
        "Coincidencia",
    }

    missing_phone_page = client.get(
        "/api/v1/customers",
        headers=_admin_headers(),
        params={"branch_id": branch_id, "phone": "6690000000", "limit": 20},
    )
    assert missing_phone_page.status_code == 200
    assert missing_phone_page.json()["items"] == []

    incomplete_phone = client.get(
        "/api/v1/customers",
        headers=_admin_headers(),
        params={"branch_id": branch_id, "phone": "669123", "limit": 20},
    )
    assert incomplete_phone.status_code == 409
    assert incomplete_phone.json()["detail"]["code"] == "invalid_phone"

    addresses = []
    for alias, street, is_default in [
        ("Casa", "Calle Mango", True),
        ("Oficina", "Avenida Kiwi", False),
        ("Escuela", "Calle Naranja", False),
    ]:
        response = client.post(
            f"/api/v1/customers/{customer['id']}/addresses",
            headers=_admin_headers(),
            json={
                "branch_id": branch_id,
                "alias": alias,
                "street": street,
                "exterior_number": "10",
                "neighborhood": "Centro",
                "postal_code": "82000",
                "city": "Mazatlan",
                "municipality": "Mazatlan",
                "state": "Sinaloa",
                "is_default": is_default,
            },
        )
        assert response.status_code == 200
        addresses.append(response.json())

    inactive_response = client.post(
        f"/api/v1/customers/{customer['id']}/addresses",
        headers=_admin_headers(),
        json={
            "branch_id": branch_id,
            "alias": "Domicilio anterior",
            "street": "Calle Cerrada",
            "exterior_number": "99",
            "neighborhood": "Centro",
            "postal_code": "82000",
            "city": "Mazatlan",
            "municipality": "Mazatlan",
            "state": "Sinaloa",
        },
    )
    assert inactive_response.status_code == 200
    inactive_address = inactive_response.json()
    deactivate_response = client.put(
        f"/api/v1/customers/{customer['id']}/addresses/{inactive_address['id']}",
        headers=_admin_headers(),
        json={"branch_id": branch_id, "status": "inactive"},
    )
    assert deactivate_response.status_code == 200

    for query in ("Renata", "renata@example.com", "6691234567"):
        paginated_search = client.get(
            "/api/v1/customers",
            headers=_admin_headers(),
            params={"branch_id": branch_id, "q": query, "limit": 20},
        )
        assert paginated_search.status_code == 200
        page = paginated_search.json()
        assert customer["id"] in {row["id"] for row in page["items"]}
        selected_page_customer = next(
            row for row in page["items"] if row["id"] == customer["id"]
        )
        assert len(selected_page_customer["addresses"]) == 3
        assert all(
            address["status"] == "active"
            for address in selected_page_customer["addresses"]
        )

    shared_phone_search = client.get(
        "/api/v1/customers",
        headers=_admin_headers(),
        params={"branch_id": branch_id, "q": "6691234567", "limit": 20},
    ).json()
    assert {customer["id"], duplicate["id"]} <= {
        row["id"] for row in shared_phone_search["items"]
    }

    search = client.get(
        f"/api/v1/customers?phone=6691234567&branch_id={branch_id}", headers=_admin_headers()
    )
    assert search.status_code == 200
    assert {row["id"] for row in search.json()} == {customer["id"], duplicate["id"]}
    selected = next(row for row in search.json() if row["id"] == customer["id"])
    assert len(selected["addresses"]) == 3

    assert (
        _open_shift(client, 50000).status_code
        == 200
    )
    order_response = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "branch_id": branch_id,
            "order_type": "delivery",
            "payment_method_intent": "cash",
            "customer_id": customer["id"],
            "delivery_address_id": addresses[0]["id"],
            "lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}],
        },
    )
    assert order_response.status_code == 200
    order = order_response.json()
    assert order["customer_snapshot"]["name"] == "Renata Cliente"
    assert order["delivery_address_snapshot"]["alias"] == "Casa"
    assert order["delivery_address_snapshot"]["street"] == "Calle Mango"

    address_update = client.put(
        f"/api/v1/customers/{customer['id']}/addresses/{addresses[0]['id']}",
        headers=_admin_headers(),
        json={"branch_id": branch_id, "street": "Calle Mango Nueva", "is_default": True},
    )
    assert address_update.status_code == 200
    customer_update = client.put(
        f"/api/v1/customers/{customer['id']}",
        headers=_admin_headers(),
        json={"branch_id": branch_id, "name": "Renata Actualizada", "customer_type": "person"},
    )
    assert customer_update.status_code == 200
    tax_response = client.put(
        f"/api/v1/customers/{customer['id']}/tax-profile",
        headers=_admin_headers(),
        json={
            "branch_id": branch_id,
            "legal_name": "RENATA CLIENTE SA DE CV",
            "tax_id": "RCL010101AB1",
            "tax_regime": "601",
            "fiscal_postal_code": "82000",
            "cfdi_use": "G03",
            "billing_email": "FACTURAS@example.com",
        },
    )
    assert tax_response.status_code == 200
    assert tax_response.json()["billing_email"] == "facturas@example.com"

    historical_orders = client.get(
        f"/api/v1/orders?branch_id={branch_id}", headers=_admin_headers()
    )
    historical = next(row for row in historical_orders.json() if row["id"] == order["id"])
    assert historical["customer_snapshot"]["name"] == "Renata Cliente"
    assert historical["delivery_address_snapshot"]["street"] == "Calle Mango"
    refreshed_customers = client.get(
        f"/api/v1/customers?phone=6691234567&branch_id={branch_id}", headers=_admin_headers()
    ).json()
    refreshed = next(row for row in refreshed_customers if row["id"] == customer["id"])
    assert refreshed["name"] == "Renata Actualizada"
    assert refreshed["addresses"][0]["street"] == "Calle Mango Nueva"
    assert refreshed["tax_profile"]["tax_id"] == "RCL010101AB1"

    repeated_response = client.post(
        f"/api/v1/orders/{order['id']}/repeat",
        headers=_admin_headers(),
        json={"register_id": "CAJA-01"},
    )
    assert repeated_response.status_code == 200
    repeated = repeated_response.json()
    assert repeated["id"] != order["id"]
    assert repeated["folio"] != order["folio"]
    assert repeated["customer_snapshot"]["name"] == "Renata Actualizada"
    assert repeated["delivery_address_snapshot"]["street"] == "Calle Mango Nueva"
    final_customer = next(
        row
        for row in client.get(
            f"/api/v1/customers?phone=6691234567&branch_id={branch_id}", headers=_admin_headers()
        ).json()
        if row["id"] == customer["id"]
    )
    assert final_customer["order_summary"]["order_count"] == 2
    assert final_customer["order_summary"]["average_ticket_cents"] == order["total_cents"]
    assert (
        final_customer["order_summary"]["frequent_products"][0]["product_name"]
        == "Hamburguesa Kiwi"
    )

    mismatch = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "branch_id": branch_id,
            "order_type": "delivery",
            "payment_method_intent": "cash",
            "customer_id": duplicate["id"],
            "delivery_address_id": addresses[0]["id"],
            "lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}],
        },
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "customer_address_mismatch"


def test_order_cancellation_releases_reserved_inventory_before_production() -> None:
    client = _client_with_seeded_database()

    open_response = _open_shift(client, 50000)
    assert open_response.status_code == 200

    order_response = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]},
    )
    assert order_response.status_code == 200
    order = order_response.json()

    reserved_stock_response = client.get(
        "/api/v1/inventory/stock", headers=_admin_headers()
    )
    assert reserved_stock_response.status_code == 200
    reserved_beef = next(
        item for item in reserved_stock_response.json() if item["sku"] == "INV-BEEF"
    )
    assert reserved_beef["quantity_on_hand"] == 24880

    cancel_response = client.post(
        f"/api/v1/orders/{order['id']}/cancel",
        headers=_admin_headers(),
        json={"reason": "Cliente cancela antes de cocina"},
    )
    assert cancel_response.status_code == 200
    cancelled = cancel_response.json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["production_tasks"][0]["status"] == "CANCELLED"

    stock_response = client.get("/api/v1/inventory/stock", headers=_admin_headers())
    assert stock_response.status_code == 200
    beef = next(item for item in stock_response.json() if item["sku"] == "INV-BEEF")
    assert beef["quantity_on_hand"] == 25000

    kardex_response = client.get(
        f"/api/v1/inventory/kardex?item_id={beef['id']}", headers=_admin_headers()
    )
    assert kardex_response.status_code == 200
    beef_movements = kardex_response.json()
    assert any(
        item["movement_type"] == "SALE_RESERVATION" and item["quantity_delta"] == -120
        for item in beef_movements
    )
    assert any(
        item["movement_type"] == "RESERVATION_RELEASE" and item["quantity_delta"] == 120
        for item in beef_movements
    )

    payment_response = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=_admin_headers(),
        json={"amount_cents": 9500, "method": "cash", "register_id": "CAJA-01"},
    )
    assert payment_response.status_code == 409
    assert payment_response.json()["detail"]["code"] == "order_cancelled"

    orders_response = client.get("/api/v1/orders", headers=_admin_headers())
    assert orders_response.status_code == 200
    assert orders_response.json()[0]["status"] == "CANCELLED"

    bootstrap_response = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    )
    assert bootstrap_response.status_code == 200
    assert bootstrap_response.json()["counts"]["inventory_movements"] == 8
    assert bootstrap_response.json()["counts"]["audit_events"] == 4


def test_order_cancellation_is_rejected_while_production_is_in_progress() -> None:
    client = _client_with_seeded_database()

    open_response = _open_shift(client, 50000)
    assert open_response.status_code == 200

    order_response = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]},
    )
    assert order_response.status_code == 200
    order = order_response.json()

    task_id = order["production_tasks"][0]["id"]
    started_response = client.post(
        f"/api/v1/kds/tasks/{task_id}/transition",
        headers=_admin_headers(),
        json={"status": "IN_PROGRESS"},
    )
    assert started_response.status_code == 200

    cancel_response = client.post(
        f"/api/v1/orders/{order['id']}/cancel",
        headers=_admin_headers(),
        json={"reason": "Demasiado tarde"},
    )
    assert cancel_response.status_code == 409
    assert cancel_response.json()["detail"]["code"] == "production_in_progress"


def test_post_production_cancellation_records_waste_without_restocking() -> None:
    client = _client_with_seeded_database()

    open_response = _open_shift(client, 50000)
    assert open_response.status_code == 200

    order_response = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]},
    )
    assert order_response.status_code == 200
    order = order_response.json()
    task_id = order["production_tasks"][0]["id"]

    started_response = client.post(
        f"/api/v1/kds/tasks/{task_id}/transition",
        headers=_admin_headers(),
        json={"status": "IN_PROGRESS"},
    )
    assert started_response.status_code == 200
    completed_response = client.post(
        f"/api/v1/kds/tasks/{task_id}/transition",
        headers=_admin_headers(),
        json={"status": "COMPLETED"},
    )
    assert completed_response.status_code == 200

    missing_classification = client.post(
        f"/api/v1/orders/{order['id']}/cancel",
        headers=_admin_headers(),
        json={"reason": "Cliente cancela pedido producido"},
    )
    assert missing_classification.status_code == 409
    assert missing_classification.json()["detail"]["code"] == "cancellation_classification_required"

    cancel_response = client.post(
        f"/api/v1/orders/{order['id']}/cancel",
        headers=_admin_headers(),
        json={"reason": "Cliente cancela pedido producido", "classification": "waste"},
    )
    assert cancel_response.status_code == 200
    cancelled = cancel_response.json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["classification"] == "waste"
    assert cancelled["production_tasks"][0]["status"] == "COMPLETED"

    stock_response = client.get("/api/v1/inventory/stock", headers=_admin_headers())
    assert stock_response.status_code == 200
    beef = next(item for item in stock_response.json() if item["sku"] == "INV-BEEF")
    assert beef["quantity_on_hand"] == 24880

    kardex_response = client.get(
        f"/api/v1/inventory/kardex?item_id={beef['id']}", headers=_admin_headers()
    )
    assert kardex_response.status_code == 200
    beef_movements = kardex_response.json()
    assert any(
        item["movement_type"] == "SALE_CONSUMPTION" and item["quantity_delta"] == -120
        for item in beef_movements
    )
    assert any(
        item["movement_type"] == "WASTE" and item["quantity_delta"] == 0 for item in beef_movements
    )

    payment_response = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=_admin_headers(),
        json={"amount_cents": 9500, "method": "cash", "register_id": "CAJA-01"},
    )
    assert payment_response.status_code == 409
    assert payment_response.json()["detail"]["code"] == "order_cancelled"

    bootstrap_response = client.get(
        "/api/v1/platform/bootstrap-status", headers=_admin_headers()
    )
    assert bootstrap_response.status_code == 200
    assert bootstrap_response.json()["counts"]["inventory_movements"] == 12
    assert bootstrap_response.json()["counts"]["audit_events"] == 6


def test_post_production_cancellation_records_recovery_and_restocks() -> None:
    client = _client_with_seeded_database()

    open_response = _open_shift(client, 50000)
    assert open_response.status_code == 200

    order_response = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]},
    )
    assert order_response.status_code == 200
    order = order_response.json()
    task_id = order["production_tasks"][0]["id"]

    started_response = client.post(
        f"/api/v1/kds/tasks/{task_id}/transition",
        headers=_admin_headers(),
        json={"status": "IN_PROGRESS"},
    )
    assert started_response.status_code == 200
    completed_response = client.post(
        f"/api/v1/kds/tasks/{task_id}/transition",
        headers=_admin_headers(),
        json={"status": "COMPLETED"},
    )
    assert completed_response.status_code == 200

    cancel_response = client.post(
        f"/api/v1/orders/{order['id']}/cancel",
        headers=_admin_headers(),
        json={"reason": "Produccion recuperable", "classification": "recovery"},
    )
    assert cancel_response.status_code == 200
    cancelled = cancel_response.json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["classification"] == "recovery"

    stock_response = client.get("/api/v1/inventory/stock", headers=_admin_headers())
    assert stock_response.status_code == 200
    beef = next(item for item in stock_response.json() if item["sku"] == "INV-BEEF")
    assert beef["quantity_on_hand"] == 25000

    kardex_response = client.get(
        f"/api/v1/inventory/kardex?item_id={beef['id']}", headers=_admin_headers()
    )
    assert kardex_response.status_code == 200
    beef_movements = kardex_response.json()
    assert any(
        item["movement_type"] == "RECOVERY" and item["quantity_delta"] == 120
        for item in beef_movements
    )


def test_payment_cut_and_print_flow() -> None:
    client = _client_with_seeded_database()

    open_response = _open_shift(client, 50000)
    assert open_response.status_code == 200

    order_response = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]},
    )
    assert order_response.status_code == 200
    order = order_response.json()

    mismatch_payment = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=_admin_headers(),
        json={"amount_cents": 9400, "method": "cash", "register_id": "CAJA-01"},
    )
    assert mismatch_payment.status_code == 409
    assert mismatch_payment.json()["detail"]["code"] == "payment_total_mismatch"

    payment_response = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=_admin_headers(),
        json={"amount_cents": 9500, "method": "cash", "register_id": "CAJA-01"},
    )
    assert payment_response.status_code == 200
    payment = payment_response.json()
    assert payment["status"] == "CONFIRMED"
    assert payment["order_status"] == "ACCEPTED"
    assert [job["job_type"] for job in payment["print_jobs"]] == ["ticket", "kitchen"]

    duplicate_payment = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=_admin_headers(),
        json={"amount_cents": 9500, "method": "cash", "register_id": "CAJA-01"},
    )
    assert duplicate_payment.status_code == 409
    assert duplicate_payment.json()["detail"]["code"] == "payment_already_confirmed"

    orders_response = client.get("/api/v1/orders", headers=_admin_headers())
    assert orders_response.status_code == 200
    assert orders_response.json()[0]["status"] == "ACCEPTED"

    payments_response = client.get("/api/v1/payments", headers=_admin_headers())

    assert payments_response.status_code == 200
    assert payments_response.json()[0]["amount_cents"] == 9500

    print_jobs_response = client.get("/api/v1/print-jobs", headers=_admin_headers())
    assert print_jobs_response.status_code == 200
    print_jobs = print_jobs_response.json()
    assert len(print_jobs) == 2
    assert {job["status"] for job in print_jobs} == {"QUEUED"}
    assert {job["attempts"] for job in print_jobs} == {1}

    print_agent_token = "platform-initial-print-agent"
    with _test_session_factory(client)() as session:
        session.execute(
            models.device_credentials.insert().values(
                id="platform-initial-print-agent",
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                branch_id=BRANCH_ID,
                capability="print.agent",
                token_hash=hashlib.sha256(print_agent_token.encode()).hexdigest(),
                key_version="v1",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
                revoked_at=None,
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    pull_response = client.get(
        "/api/v1/print-attempts/pull",
        headers={"X-Device-Token": print_agent_token},
    )
    assert pull_response.status_code == 200
    assert {attempt["print_job_id"] for attempt in pull_response.json()} == {
        job["id"] for job in print_jobs
    }

    retry_response = client.post(
        f"/api/v1/print-jobs/{print_jobs[0]['id']}/retry",
        headers={**_admin_headers(), "Idempotency-Key": "platform-print-retry-001"},
    )
    assert retry_response.status_code == 409
    assert retry_response.json()["detail"]["code"] == "print_job_transition_invalid"


def test_openapi_operation_ids_are_unique() -> None:
    client = _client_with_seeded_database()
    schema = client.get("/openapi.json").json()
    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]

    assert len(operation_ids) == len(set(operation_ids))


def test_payment_confirmation_is_idempotent_for_the_complete_intention() -> None:
    client = _client_with_seeded_database()
    fixture = _branch_admin_fixture(client)
    payment_operation = client.get("/openapi.json").json()["paths"][
        "/api/v1/orders/{order_id}/payments"
    ]["post"]
    idempotency_parameter = next(
        parameter
        for parameter in payment_operation["parameters"]
        if parameter["name"] == "Idempotency-Key"
    )
    assert idempotency_parameter["required"] is True
    assert idempotency_parameter["schema"]["maxLength"] == 160
    open_response = _open_shift(client, 50000)
    assert open_response.status_code == 200
    order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]},
    ).json()
    other_order = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]},
    ).json()
    headers = {**_admin_headers(), "Idempotency-Key": "payment-confirmation-001"}
    payload = {"amount_cents": order["total_cents"], "method": "cash", "register_id": "CAJA-01"}

    bearer_headers = _login_headers(client, "mangoex@gmail.com", "superadmin-test-password")
    missing_key = client.post(
        f"/api/v1/orders/{order['id']}/payments", headers=bearer_headers, json=payload
    )
    assert missing_key.status_code == 409
    assert missing_key.json()["detail"]["code"] == "idempotency_key_required"

    first = client.post(f"/api/v1/orders/{order['id']}/payments", headers=headers, json=payload)
    replay = client.post(f"/api/v1/orders/{order['id']}/payments", headers=headers, json=payload)

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    conflict_cases = [
        (order["id"], headers, {**payload, "amount_cents": payload["amount_cents"] + 1}),
        (order["id"], headers, {**payload, "method": "credit_card"}),
        (order["id"], headers, {**payload, "register_id": "CAJA-02"}),
        (
            order["id"],
            {
                "X-Actor-User-Id": fixture["outsider_id"],
                "Idempotency-Key": headers["Idempotency-Key"],
            },
            payload,
        ),
        (other_order["id"], headers, payload),
    ]
    for conflict_order_id, conflict_headers, conflict_payload in conflict_cases:
        conflict = client.post(
            f"/api/v1/orders/{conflict_order_id}/payments",
            headers=conflict_headers,
            json=conflict_payload,
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "payment_idempotency_conflict"

    with _test_session_factory(client)() as session:
        payment_rows = session.execute(
            payments.select().where(payments.c.order_id == order["id"])
        ).all()
        assert len(payment_rows) == 1
        assert len(
            session.execute(
                sales_operation_snapshots.select().where(
                    sales_operation_snapshots.c.order_id == order["id"]
                )
            ).all()
        ) == 1
        assert len(
            session.execute(
                order_events.select().where(
                    order_events.c.order_id == order["id"],
                    order_events.c.event_type == "PAYMENT_CONFIRMED",
                )
            ).all()
        ) == 1
        job_rows = session.execute(
            print_jobs.select().where(print_jobs.c.order_id == order["id"])
        ).all()
        assert len(job_rows) == 2
        assert len(
            session.execute(
                audit_events.select().where(
                    audit_events.c.action == "payment.confirmed",
                    audit_events.c.entity_id == first.json()["id"],
                )
            ).all()
        ) == 1

    summary_response = client.get("/api/v1/cash-shifts/summary", headers=_admin_headers())
    assert summary_response.status_code == 200
    summary = summary_response.json()["summary"]
    assert summary["sales_total_cents"] == 9500
    assert summary["payment_total_cents"] == 9500
    assert summary["cash_payment_cents"] == 9500
    assert summary["expected_cash_cents"] == 59500

    close_response = client.post(
        f"/api/v1/cash/shifts/{open_response.json()['id']}/close-operationally",
        headers={**_admin_headers(), "Idempotency-Key": "payment-operational-close"},
        json={},
    )
    assert close_response.status_code == 200
    closure = close_response.json()["closure"]
    assert closure["summary_snapshot"]["expected_cash_cents"] == 59500


def test_payment_methods_preserve_cash_debit_credit_and_transfer() -> None:
    for method in ("cash", "debit_card", "credit_card", "transfer"):
        client = _client_with_seeded_database()
        open_response = _open_shift(client, 50000)
        assert open_response.status_code == 200
        order_response = client.post(
            "/api/v1/orders",
            headers=_admin_headers(),
            json={
                "lines": [
                    {
                        "product_id": "018f6f73-2d0a-74f0-8f1c-000000000111",
                        "quantity": 1,
                    }
                ]
            },
        )
        assert order_response.status_code == 200
        order = order_response.json()
        payment_response = client.post(
            f"/api/v1/orders/{order['id']}/payments",
            headers=_admin_headers(),
            json={"amount_cents": order["total_cents"], "method": method, "register_id": "CAJA-01"},
        )
        assert payment_response.status_code == 200
        assert payment_response.json()["method"] == method
        payments_response = client.get("/api/v1/payments", headers=_admin_headers())
        assert payments_response.status_code == 200
        assert payments_response.json()[0]["method"] == method


def test_takeout_order_stays_pending_until_payment_and_can_be_amended() -> None:
    client = _client_with_seeded_database()
    assert (
        _open_shift(client, 50000).status_code
        == 200
    )
    invalid = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "order_type": "takeout",
            "lines": [
                {
                    "product_id": "018f6f73-2d0a-74f0-8f1c-000000000111",
                    "quantity": 1,
                }
            ],
        },
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "payment_method_intent_required"

    legacy_alias = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "order_type": "takeaway",
            "payment_method_intent": "cash",
            "lines": [
                {
                    "product_id": "018f6f73-2d0a-74f0-8f1c-000000000111",
                    "quantity": 1,
                }
            ],
        },
    )
    assert legacy_alias.status_code == 409
    assert legacy_alias.json()["detail"]["code"] == "invalid_order_type"

    created = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "order_type": "takeout",
            "payment_method_intent": "cash",
            "lines": [
                {
                    "product_id": "018f6f73-2d0a-74f0-8f1c-000000000111",
                    "quantity": 1,
                }
            ],
        },
    )
    assert created.status_code == 200
    order = created.json()
    assert order["status"] == "ACCEPTED"
    assert order["version"] == 1
    assert order["payment_method_intent"] == "cash"

    listed = client.get("/api/v1/orders", headers=_admin_headers()).json()[0]
    assert listed["display_status"] == "PENDING_PAYMENT"
    assert listed["payment_status"] == "PENDING"
    detail = client.get(
        f"/api/v1/orders/{order['id']}", headers=_admin_headers()
    ).json()
    assert detail["editable"] is True
    assert detail["payments"] == []

    amendment_headers = {
        **_admin_headers(),
        "Idempotency-Key": "takeout-amendment-1",
    }
    amended = client.post(
        f"/api/v1/orders/{order['id']}/amendments",
        headers=amendment_headers,
        json={
            "expected_version": 1,
            "lines": [
                {
                    "product_id": "018f6f73-2d0a-74f0-8f1c-000000000112",
                    "quantity": 2,
                }
            ],
        },
    )
    assert amended.status_code == 200
    amended_payload = amended.json()
    assert amended_payload["version"] == 2
    assert amended_payload["payment_method_intent"] == "cash"
    assert amended_payload["total_cents"] == 9000
    assert amended_payload["lines"][0]["product_name"] == "Papas"
    retry = client.post(
        f"/api/v1/orders/{order['id']}/amendments",
        headers=amendment_headers,
        json={"expected_version": 1, "lines": []},
    )
    assert retry.status_code == 200
    assert retry.json()["version"] == 2

    payment = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers=_admin_headers(),
        json={"amount_cents": 9000, "method": "debit_card", "register_id": "CAJA-01"},
    )
    assert payment.status_code == 200
    assert payment.json()["method"] == "debit_card"
    paid_detail = client.get(
        f"/api/v1/orders/{order['id']}", headers=_admin_headers()
    ).json()
    assert paid_detail["payment_status"] == "CONFIRMED"
    assert paid_detail["payment_method"] == "debit_card"
    assert paid_detail["editable"] is False


def test_sensitive_pos_endpoints_require_authenticated_actor() -> None:
    client = _client_with_seeded_database()

    current_response = client.get(
        "/api/v1/cash/shifts/current",
        params={"branch_id": BRANCH_ID, "register_id": "CAJA-01"},
    )
    assert current_response.status_code == 401
    assert current_response.json()["detail"]["code"] == "actor_required"

    order_response = client.post(
        "/api/v1/orders",
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]},
    )
    assert order_response.status_code == 401
    assert order_response.json()["detail"]["code"] == "actor_required"


def test_cashier_can_operate_pos_and_admin_dashboard_reflects_payment() -> None:
    client = _client_with_seeded_database()

    role_response = client.post(
        "/api/v1/roles",
        headers=_admin_headers(),
        json={"name": "Cajero", "scope": "branch"},
    )
    assert role_response.status_code == 200
    role = role_response.json()
    assert "cash.shift.open" in role["permissions"]
    assert "orders.create" in role["permissions"]
    assert "payments.confirm" in role["permissions"]

    user_response = client.post(
        "/api/v1/users",
        headers=_admin_headers(),
        json={
            "email": "cajero-pos@kiwi.local",
            "display_name": "Cajero POS",
            "employee_code": "POS001",
            "password": "Temporal123+",
            "role_id": role["id"],
            "branch_id": BRANCH_ID,
        },
    )
    assert user_response.status_code == 200

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "cajero-pos@kiwi.local", "password": "Temporal123+"},
    )
    assert login_response.status_code == 200
    session_payload = login_response.json()
    cashier_headers = {"Authorization": f"Bearer {session_payload['token']}"}
    assert session_payload["user"]["assigned_branch_id"] == BRANCH_ID
    assert "pos.operate" in session_payload["user"]["permissions"]
    assert "dashboard.read" not in session_payload["user"]["permissions"]

    cashier_dashboard = client.get("/api/v1/dashboard/overview", headers=cashier_headers)
    assert cashier_dashboard.status_code == 403
    assert cashier_dashboard.json()["detail"]["code"] == "permission_denied"

    open_response = _open_shift(client, 10000, cashier_headers)
    assert open_response.status_code == 200

    order_response = client.post(
        "/api/v1/orders",
        headers={**cashier_headers, "Idempotency-Key": "cashier-pos-order-001"},
        json={"lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]},
    )
    assert order_response.status_code == 200
    order = order_response.json()
    assert order["total_cents"] == 9500
    recovered_order = client.post(
        "/api/v1/orders/recover",
        headers={**cashier_headers, "Idempotency-Key": "cashier-pos-order-001"},
        json={},
    )
    assert recovered_order.status_code == 200
    assert recovered_order.json() == order

    with _test_session_factory(client)() as database_session:
        orders_create_permission_id = database_session.execute(
            permissions.select().where(permissions.c.code == "orders.create")
        ).mappings().one()["id"]
        database_session.execute(
            role_permissions.delete().where(
                role_permissions.c.role_id == role["id"],
                role_permissions.c.permission_id == orders_create_permission_id,
            )
        )
        database_session.commit()
    revoked_recovery = client.post(
        "/api/v1/orders/recover",
        headers={**cashier_headers, "Idempotency-Key": "cashier-pos-order-001"},
        json={},
    )
    assert revoked_recovery.status_code == 403
    assert revoked_recovery.json()["detail"]["code"] == "permission_denied"

    payment_response = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers={**cashier_headers, "Idempotency-Key": "cashier-pos-payment-001"},
        json={"amount_cents": order["total_cents"], "method": "cash", "register_id": "CAJA-01"},
    )
    assert payment_response.status_code == 200
    assert payment_response.json()["status"] == "CONFIRMED"

    payments_response = client.get("/api/v1/payments", headers=cashier_headers)
    assert payments_response.status_code == 403
    assert payments_response.json()["detail"]["code"] == "permission_denied"

    dashboard_response = client.get("/api/v1/dashboard/overview", headers=_admin_headers())
    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["total_revenue_cents"] == 9500
    assert dashboard["total_orders"] == 1
    assert dashboard["recent_transactions"][0]["amount_cents"] == 9500


def test_cashier_cannot_operate_outside_assigned_branch() -> None:
    client = _client_with_seeded_database()

    branch_response = client.post(
        "/api/v1/branches",
        headers=_admin_headers(),
        json={"name": "Sucursal Norte", "code": "NORTE"},
    )
    assert branch_response.status_code == 200
    other_branch_id = branch_response.json()["id"]

    role_response = client.post(
        "/api/v1/roles",
        headers=_admin_headers(),
        json={"name": "Cajero", "scope": "branch"},
    )
    assert role_response.status_code == 200

    user_response = client.post(
        "/api/v1/users",
        headers=_admin_headers(),
        json={
            "email": "cajero-scope@kiwi.local",
            "display_name": "Cajero Scope",
            "employee_code": "SCP001",
            "password": "Temporal123+",
            "role_id": role_response.json()["id"],
            "branch_id": BRANCH_ID,
        },
    )
    assert user_response.status_code == 200

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "cajero-scope@kiwi.local", "password": "Temporal123+"},
    )
    assert login_response.status_code == 200
    cashier_headers = {"Authorization": f"Bearer {login_response.json()['token']}"}

    denied_response = client.post(
        "/api/v1/cash-shifts/open",
        headers={**cashier_headers, "Idempotency-Key": "denied-open-other"},
        json={"opening_cash_cents": 10000, "branch_id": other_branch_id, "register_id": "CAJA-01"},
    )
    assert denied_response.status_code == 403
    assert denied_response.json()["detail"]["code"] == "permission_denied"


def test_pos_account_uses_assigned_branch_and_can_update_own_profile() -> None:
    client = _client_with_seeded_database()

    branch_response = client.post(
        "/api/v1/branches",
        headers=_admin_headers(),
        json={"name": "Sucursal Centro", "code": "CENTRO"},
    )
    assert branch_response.status_code == 200
    branch_id = branch_response.json()["id"]

    role_response = client.post(
        "/api/v1/roles",
        headers=_admin_headers(),
        json={"name": "Cajero", "scope": "branch"},
    )
    assert role_response.status_code == 200

    user_response = client.post(
        "/api/v1/users",
        headers=_admin_headers(),
        json={
            "email": "cajero-centro@kiwi.local",
            "display_name": "Cajero Centro",
            "employee_code": "CTR001",
            "password": "Temporal123+",
            "role_id": role_response.json()["id"],
            "branch_id": branch_id,
        },
    )
    assert user_response.status_code == 200
    user_id = user_response.json()["id"]

    users_response = client.get("/api/v1/users", headers=_admin_headers())
    assert users_response.status_code == 200
    created_user = next(item for item in users_response.json() if item["id"] == user_id)
    assert created_user["roles"][0]["branch_id"] == branch_id
    assert created_user["roles"][0]["branch_name"] == "Sucursal Centro"

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "cajero-centro@kiwi.local", "password": "Temporal123+"},
    )
    assert login_response.status_code == 200
    session_payload = login_response.json()
    cashier_headers = {"Authorization": f"Bearer {session_payload['token']}"}
    assert session_payload["user"]["assigned_branch_id"] == branch_id

    open_response = client.post(
        "/api/v1/cash-shifts/open",
        headers={**cashier_headers, "Idempotency-Key": "branch-open-ok"},
        json={
            "opening_cash_cents": 10000,
            "branch_id": branch_id,
            "register_id": "CAJA-CENTRO-01",
        },
    )
    assert open_response.status_code == 200
    assert open_response.json()["branch_id"] == branch_id
    assert open_response.json()["register_code"] == "CAJA-CENTRO-01"

    order_response = client.post(
        "/api/v1/orders",
        headers={**cashier_headers, "Idempotency-Key": "branch-open-denied"},
        json={
            "branch_id": branch_id,
            "register_id": "CAJA-CENTRO-01",
            "lines": [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}],
        },
    )
    assert order_response.status_code == 200
    order = order_response.json()
    assert order["branch_id"] == branch_id
    assert order["cash_shift_id"] == open_response.json()["id"]

    payment_response = client.post(
        f"/api/v1/orders/{order['id']}/payments",
        headers={**cashier_headers, "Idempotency-Key": "branch-payment-ok"},
        json={
            "amount_cents": order["total_cents"],
            "method": "cash",
            "register_id": "CAJA-CENTRO-01",
        },
    )
    assert payment_response.status_code == 200
    assert payment_response.json()["status"] == "CONFIRMED"

    denied_response = client.post(
        "/api/v1/cash-shifts/open",
        headers={**cashier_headers, "Idempotency-Key": "branch-open-denied"},
        json={
            "opening_cash_cents": 10000,
            "branch_id": BRANCH_ID,
            "register_id": "CAJA-PILOTO-01",
        },
    )
    assert denied_response.status_code == 403
    assert denied_response.json()["detail"]["code"] == "permission_denied"

    profile_response = client.put(
        f"/api/v1/users/{user_id}",
        headers=cashier_headers,
        json={
            "display_name": "Cajero Centro Actualizado",
            "email": "cajero-centro@kiwi.local",
        },
    )
    assert profile_response.status_code == 200
    assert profile_response.json()["display_name"] == "Cajero Centro Actualizado"

    dashboard_response = client.get("/api/v1/dashboard/overview", headers=_admin_headers())
    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["total_orders"] == 1
    assert dashboard["recent_transactions"][0]["amount_cents"] == order["total_cents"]
    notifications = dashboard["recent_notifications"]
    assert notifications[0]["action"] == "cash_shift.opened"
    assert notifications[0]["actor_name"] == "Cajero Centro Actualizado"
    assert notifications[0]["register_code"] == "CAJA-CENTRO-01"


def test_legacy_caja_role_keeps_pos_permissions() -> None:
    client = _client_with_seeded_database()

    role_response = client.post(
        "/api/v1/roles",
        headers=_admin_headers(),
        json={"name": "Caja", "scope": "branch"},
    )
    assert role_response.status_code == 200
    role = role_response.json()
    assert "pos.operate" in role["permissions"]
    assert "cash.shift.open" in role["permissions"]
    assert "payments.confirm" in role["permissions"]

    user_response = client.post(
        "/api/v1/users",
        headers=_admin_headers(),
        json={
            "email": "legacy-caja@kiwi.local",
            "display_name": "Caja Legacy",
            "employee_code": "LEG001",
            "password": "Temporal123+",
            "role_id": role["id"],
            "branch_id": BRANCH_ID,
        },
    )
    assert user_response.status_code == 200

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "legacy-caja@kiwi.local", "password": "Temporal123+"},
    )
    assert login_response.status_code == 200
    session_payload = login_response.json()
    assert "Caja" in session_payload["user"]["roles"]
    assert "pos.operate" in session_payload["user"]["permissions"]
    assert session_payload["user"]["assigned_branch_id"] == BRANCH_ID

    open_response = client.post(
        "/api/v1/cash-shifts/open",
        headers={
            "Authorization": f"Bearer {session_payload['token']}",
            "Idempotency-Key": "token-open",
        },
        json={"opening_cash_cents": 10000, "branch_id": BRANCH_ID, "register_id": "CAJA-01"},
    )
    assert open_response.status_code == 200


def test_sync_command_without_domain_executor_is_rejected_without_writes() -> None:
    client = _client_with_seeded_database()
    device_token = "sync-gateway-test-token"
    with _test_session_factory(client)() as session:
        session.execute(
            models.device_credentials.insert().values(
                id="018f6f73-2d0a-74f0-8f1c-000000000401",
                organization_id=ORGANIZATION_ID,
                branch_id=BRANCH_ID,
                capability="gateway.sync",
                token_hash=hashlib.sha256(device_token.encode()).hexdigest(),
                key_version="v1",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                revoked_at=None,
                created_at=datetime.now(UTC),
            )
        )
        session.commit()
    gateway_headers = {"X-Device-Token": device_token}
    command = {
        "schema_version": "1.0",
        "command_id": "018f6f73-2d0a-74f0-8f1c-000000000301",
        "idempotency_key": "PILOTO-CAJA-01-000001",
        "organization_id": "018f6f73-2d0a-74f0-8f1c-000000000001",
        "branch_id": "018f6f73-2d0a-74f0-8f1c-000000000003",
        "source_device_id": "018f6f73-2d0a-74f0-8f1c-000000000401",
        "command_type": "local_order.closed",
        "occurred_at": "2026-07-07T18:00:00Z",
        "payload": {"folio": "PILOTO-LOCAL-000001", "total_cents": 9500},
    }

    spoofed_response = client.post(
        "/api/v1/sync/commands",
        headers=gateway_headers,
        json={**command, "source_device_id": "018f6f73-2d0a-74f0-8f1c-000000000499"},
    )
    assert spoofed_response.status_code == 403
    assert spoofed_response.json()["detail"]["code"] == "device_scope_denied"
    with _test_session_factory(client)() as session:
        assert session.execute(models.sync_commands.select()).mappings().all() == []

    rejected = client.post("/api/v1/sync/commands", headers=gateway_headers, json=command)
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "unsupported_sync_command"
    with _test_session_factory(client)() as session:
        assert session.execute(models.sync_commands.select()).mappings().all() == []
        assert session.execute(models.sync_events.select()).mappings().all() == []


def test_sync_command_rejects_invalid_payload() -> None:
    client = _client_with_seeded_database()

    response = client.post(
        "/api/v1/sync/commands",
        json={"schema_version": "1.0", "payload": {}},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "device_actor_required"


def test_order_quote_uses_creation_pricing_and_never_invents_tax() -> None:
    client = _client_with_seeded_database()
    assert _open_shift(client, 0).status_code == 200
    payload = {
        "branch_id": BRANCH_ID,
        "lines": [
            {
                "product_id": "018f6f73-2d0a-74f0-8f1c-000000000111",
                "quantity": 1,
            }
        ],
    }
    quote = client.post("/api/v1/orders/quote", headers=_admin_headers(), json=payload)
    assert quote.status_code == 200
    assert quote.json()["tax_cents"] is None
    created = client.post("/api/v1/orders", headers=_admin_headers(), json=payload)
    assert created.status_code == 200
    assert quote.json()["total_cents"] == created.json()["total_cents"]
    assert client.post("/api/v1/orders/quote", json=payload).status_code == 401


def test_supervisor_adjustment_is_calculated_in_python_and_consumed_once() -> None:
    client = _client_with_seeded_database()
    assert _open_shift(client, 0).status_code == 200
    lines = [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]
    authorization = client.post(
        "/api/v1/orders/adjustments/authorize",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "supervisor_pin": "superadmin-test-password",
            "lines": lines,
            "adjustment": {
                "type": "percent",
                "value": "10",
                "reason": "Cortesía de prueba",
            },
        },
    )
    assert authorization.status_code == 200
    authorization_payload = authorization.json()
    assert authorization_payload["quote"]["subtotal_cents"] == 9500
    assert authorization_payload["quote"]["adjustment_cents"] == 950
    assert authorization_payload["quote"]["total_cents"] == 8550

    order_payload = {
        "branch_id": BRANCH_ID,
        "lines": lines,
        "adjustment_authorization_id": authorization_payload["authorization_id"],
    }
    quoted = client.post(
        "/api/v1/orders/quote", headers=_admin_headers(), json=order_payload
    )
    assert quoted.status_code == 200
    assert quoted.json()["total_cents"] == 8550

    created = client.post("/api/v1/orders", headers=_admin_headers(), json=order_payload)
    assert created.status_code == 200
    assert created.json()["total_cents"] == 8550
    with _test_session_factory(client)() as session:
        persisted = session.execute(
            models.order_adjustment_authorizations.select()
        ).mappings().one()
        assert persisted["status"] == "CONSUMED"
        assert persisted["consumed_order_id"] == created.json()["id"]

    replay = client.post("/api/v1/orders", headers=_admin_headers(), json=order_payload)
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "order_adjustment_authorization_consumed"


def test_local_order_creation_is_idempotent_for_the_complete_intention() -> None:
    client = _client_with_seeded_database()
    fixture = _branch_admin_fixture(client)
    order_operation = client.get("/openapi.json").json()["paths"]["/api/v1/orders"]["post"]
    idempotency_parameter = next(
        parameter
        for parameter in order_operation["parameters"]
        if parameter["name"] == "Idempotency-Key"
    )
    assert idempotency_parameter["required"] is True
    _open_shift(client, 0)
    payload = {
        "branch_id": BRANCH_ID,
        "register_id": "CAJA-01",
        "owner_name": "Cliente idempotente",
        "order_type": "dine-in",
        "lines": [
            {
                "product_id": "018f6f73-2d0a-74f0-8f1c-000000000111",
                "quantity": 1,
                "notes": "Entregar a Renata en mesa privada",
            }
        ],
    }
    headers = {**_admin_headers(), "Idempotency-Key": "test-local-order-idempotency-001"}

    first = client.post("/api/v1/orders", headers=headers, json=payload)
    second = client.post("/api/v1/orders", headers=headers, json=payload)
    recovered = client.post("/api/v1/orders/recover", headers=headers, json={})

    assert first.status_code == second.status_code == recovered.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json() == second.json()
    assert first.json() == recovered.json()
    recovery_operation = client.get("/openapi.json").json()["paths"][
        "/api/v1/orders/recover"
    ]["post"]
    recovery_key_parameter = next(
        parameter
        for parameter in recovery_operation["parameters"]
        if parameter["name"] == "Idempotency-Key"
    )
    assert recovery_key_parameter["required"] is True
    with _test_session_factory(client)() as session:
        assert len(session.execute(orders.select()).mappings().all()) == 1
        command_snapshot = session.execute(
            order_create_commands.select().where(
                order_create_commands.c.order_id == first.json()["id"]
            )
        ).mappings().one()["response_snapshot"]
        assert "Cliente idempotente" not in json.dumps(command_snapshot, ensure_ascii=False)
        assert "Entregar a Renata" not in json.dumps(command_snapshot, ensure_ascii=False)
        assert "owner_name" not in command_snapshot
        assert "customer_id" not in command_snapshot
        assert "customer_snapshot" not in command_snapshot
        assert "delivery_address_snapshot" not in command_snapshot
        assert all(
            "line_notes" not in line and "selected_modifiers" not in line
            for line in command_snapshot["lines"]
        )
        assert all(
            "modifiers" not in snapshot
            for snapshot in command_snapshot["consumption_snapshots"]
        )
        assert len(
            session.execute(
                order_events.select().where(order_events.c.order_id == first.json()["id"])
            ).mappings().all()
        ) == 1

    bearer_headers = _login_headers(client, "mangoex@gmail.com", "superadmin-test-password")
    bearer_recovery = client.post(
        "/api/v1/orders/recover",
        headers={**bearer_headers, "Idempotency-Key": headers["Idempotency-Key"]},
        json={},
    )
    assert bearer_recovery.status_code == 200
    assert bearer_recovery.json() == first.json()
    missing_key = client.post("/api/v1/orders", headers=bearer_headers, json=payload)
    assert missing_key.status_code == 409
    assert missing_key.json()["detail"]["code"] == "idempotency_key_required"
    missing_recovery_key = client.post("/api/v1/orders/recover", headers=bearer_headers, json={})
    assert missing_recovery_key.status_code == 409
    assert missing_recovery_key.json()["detail"]["code"] == "idempotency_key_required"
    unknown_recovery = client.post(
        "/api/v1/orders/recover",
        headers={**bearer_headers, "Idempotency-Key": "unknown-order-key-001"},
        json={},
    )
    assert unknown_recovery.status_code == 409
    assert unknown_recovery.json()["detail"]["code"] == "order_create_not_found"
    outsider_recovery = client.post(
        "/api/v1/orders/recover",
        headers={
            "X-Actor-User-Id": fixture["outsider_id"],
            "Idempotency-Key": headers["Idempotency-Key"],
        },
        json={},
    )
    assert outsider_recovery.status_code == 409
    assert outsider_recovery.json()["detail"]["code"] == "order_create_not_found"
    invalid_recovery_payload = client.post(
        "/api/v1/orders/recover", headers=headers, json={"branch_id": BRANCH_ID}
    )
    assert invalid_recovery_payload.status_code == 409
    assert invalid_recovery_payload.json()["detail"]["code"] == "order_recovery_payload_invalid"

    conflict_cases = [
        (headers, {**payload, "owner_name": "Otra persona"}),
        (headers, {**payload, "branch_id": fixture["branch_id"]}),
        (headers, {**payload, "register_id": "CAJA-02"}),
        (headers, {**payload, "customer_id": "018f6f73-2d0a-74f0-8f1c-000000009901"}),
        (
            headers,
            {**payload, "delivery_address_id": "018f6f73-2d0a-74f0-8f1c-000000009902"},
        ),
        (headers, {**payload, "payment_method_intent": "cash"}),
        (headers, {**payload, "driver_id": "018f6f73-2d0a-74f0-8f1c-000000009903"}),
        (headers, {**payload, "lines": [{**payload["lines"][0], "quantity": 2}]}),
        (
            {
                "X-Actor-User-Id": fixture["outsider_id"],
                "Idempotency-Key": headers["Idempotency-Key"],
            },
            payload,
        ),
    ]
    for conflict_headers, conflict_payload in conflict_cases:
        conflicting = client.post(
            "/api/v1/orders", headers=conflict_headers, json=conflict_payload
        )
        assert conflicting.status_code == 409
        assert conflicting.json()["detail"]["code"] == "order_create_idempotency_conflict"
    with _test_session_factory(client)() as session:
        assert len(session.execute(orders.select()).mappings().all()) == 1


def test_order_recovery_rejects_cross_order_and_malformed_snapshot_references() -> None:
    client = _client_with_seeded_database()
    assert _open_shift(client, 0).status_code == 200
    base_payload = {
        "branch_id": BRANCH_ID,
        "register_id": "CAJA-01",
        "lines": [
            {
                "product_id": "018f6f73-2d0a-74f0-8f1c-000000000111",
                "quantity": 1,
            }
        ],
    }
    first = client.post(
        "/api/v1/orders",
        headers={**_admin_headers(), "Idempotency-Key": "recovery-owner-first-001"},
        json={**base_payload, "owner_name": "Pedido uno"},
    )
    second = client.post(
        "/api/v1/orders",
        headers={**_admin_headers(), "Idempotency-Key": "recovery-owner-second-001"},
        json={**base_payload, "owner_name": "Pedido dos"},
    )
    assert first.status_code == second.status_code == 200

    with _test_session_factory(client)() as session:
        commands = {
            row["order_id"]: row
            for row in session.execute(order_create_commands.select()).mappings()
        }
        first_snapshot = json.loads(json.dumps(commands[first.json()["id"]]["response_snapshot"]))
        second_snapshot = commands[second.json()["id"]]["response_snapshot"]
        first_snapshot["lines"] = second_snapshot["lines"]
        first_snapshot["consumption_snapshots"] = second_snapshot["consumption_snapshots"]
        session.execute(
            order_create_commands.update()
            .where(order_create_commands.c.order_id == first.json()["id"])
            .values(response_snapshot=first_snapshot)
        )
        session.commit()

    cross_order = client.post(
        "/api/v1/orders/recover",
        headers={**_admin_headers(), "Idempotency-Key": "recovery-owner-first-001"},
        json={},
    )
    assert cross_order.status_code == 409
    assert cross_order.json()["detail"]["code"] == "order_create_replay_incomplete"

    with _test_session_factory(client)() as session:
        malformed_snapshot = json.loads(
            json.dumps(commands[first.json()["id"]]["response_snapshot"])
        )
        malformed_snapshot["lines"] = [None]
        session.execute(
            order_create_commands.update()
            .where(order_create_commands.c.order_id == first.json()["id"])
            .values(response_snapshot=malformed_snapshot)
        )
        session.commit()

    malformed = client.post(
        "/api/v1/orders/recover",
        headers={**_admin_headers(), "Idempotency-Key": "recovery-owner-first-001"},
        json={},
    )
    assert malformed.status_code == 409
    assert malformed.json()["detail"]["code"] == "order_create_replay_incomplete"


def test_supervisor_adjustment_is_bound_to_original_cart() -> None:
    client = _client_with_seeded_database()
    lines = [{"product_id": "018f6f73-2d0a-74f0-8f1c-000000000111", "quantity": 1}]
    authorization = client.post(
        "/api/v1/orders/adjustments/authorize",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "supervisor_pin": "superadmin-test-password",
            "lines": lines,
            "adjustment": {
                "type": "fixed",
                "value": "10.25",
                "reason": "Ajuste fijo",
            },
        },
    ).json()
    changed_cart = client.post(
        "/api/v1/orders/quote",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "adjustment_authorization_id": authorization["authorization_id"],
            "lines": [{**lines[0], "quantity": 2}],
        },
    )
    assert changed_cart.status_code == 409
    assert changed_cart.json()["detail"]["code"] == "order_adjustment_cart_changed"


def test_kds_and_fulfillment_own_terminal_order_state() -> None:
    client = _client_with_seeded_database()
    assert _open_shift(client, 0).status_code == 200
    created = client.post(
        "/api/v1/orders",
        headers=_admin_headers(),
        json={
            "branch_id": BRANCH_ID,
            "lines": [
                {
                    "product_id": "018f6f73-2d0a-74f0-8f1c-000000000111",
                    "quantity": 1,
                }
            ],
        },
    )
    assert created.status_code == 200
    order = created.json()
    task_id = order["production_tasks"][0]["id"]
    assert client.post(
        f"/api/v1/kds/tasks/{task_id}/transition",
        headers=_admin_headers(),
        json={"status": "IN_PROGRESS"},
    ).status_code == 200
    assert client.post(
        f"/api/v1/kds/tasks/{task_id}/transition",
        headers=_admin_headers(),
        json={"status": "COMPLETED"},
    ).status_code == 200

    headers = {**_admin_headers(), "Idempotency-Key": "fulfill-deliver-test-001"}
    delivered = client.post(
        f"/api/v1/orders/{order['id']}/fulfillment/deliver", headers=headers
    )
    assert delivered.status_code == 200
    assert delivered.json()["status"] == "DELIVERED"
    assert client.post(
        f"/api/v1/orders/{order['id']}/fulfillment/deliver", headers=headers
    ).json() == delivered.json()
    closed = client.post(
        f"/api/v1/orders/{order['id']}/fulfillment/close",
        headers={**_admin_headers(), "Idempotency-Key": "fulfill-close-test-001"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"


def _client_with_seeded_database() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        _seed(session)

    app = create_app()

    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.state.test_session_factory = session_factory
    return TestClient(app)


def _test_session_factory(client: TestClient) -> Any:
    return cast(Any, client.app).state.test_session_factory


def _seed(session: Session) -> None:
    now = datetime(2026, 7, 7, 17, 30, tzinfo=UTC)
    organization_id = "018f6f73-2d0a-74f0-8f1c-000000000001"
    legal_entity_id = "018f6f73-2d0a-74f0-8f1c-000000000002"
    business_unit_id = "018f6f73-2d0a-74f0-8f1c-000000000015"
    branch_id = "018f6f73-2d0a-74f0-8f1c-000000000003"
    warehouse_id = "018f6f73-2d0a-74f0-8f1c-000000000004"
    role_id = "018f6f73-2d0a-74f0-8f1c-000000000005"
    user_id = "018f6f73-2d0a-74f0-8f1c-000000000006"
    food_category_id = "018f6f73-2d0a-74f0-8f1c-000000000101"
    drink_category_id = "018f6f73-2d0a-74f0-8f1c-000000000102"
    burger_product_id = "018f6f73-2d0a-74f0-8f1c-000000000111"
    fries_product_id = "018f6f73-2d0a-74f0-8f1c-000000000112"
    soda_product_id = "018f6f73-2d0a-74f0-8f1c-000000000113"
    unit_gram_id = "018f6f73-2d0a-74f0-8f1c-000000000301"
    unit_ml_id = "018f6f73-2d0a-74f0-8f1c-000000000302"
    unit_piece_id = "018f6f73-2d0a-74f0-8f1c-000000000303"
    beef_item_id = "018f6f73-2d0a-74f0-8f1c-000000000311"
    bun_item_id = "018f6f73-2d0a-74f0-8f1c-000000000312"
    potato_item_id = "018f6f73-2d0a-74f0-8f1c-000000000313"
    syrup_item_id = "018f6f73-2d0a-74f0-8f1c-000000000314"
    burger_recipe_id = "018f6f73-2d0a-74f0-8f1c-000000000321"
    fries_recipe_id = "018f6f73-2d0a-74f0-8f1c-000000000322"
    soda_recipe_id = "018f6f73-2d0a-74f0-8f1c-000000000323"

    session.execute(
        organizations.insert(),
        [
            {
                "id": organization_id,
                "name": "Kiwi Restaurante",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    session.execute(
        legal_entities.insert(),
        [
            {
                "id": legal_entity_id,
                "organization_id": organization_id,
                "name": "Kiwi Restaurante - Razon Social Pendiente",
                "tax_id": None,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    session.execute(
        business_units.insert(),
        [
            {
                "id": business_unit_id,
                "organization_id": organization_id,
                "legal_entity_id": legal_entity_id,
                "name": "Operaciones Kiwi",
                "code": "KIWI",
                "unit_type": "restaurant",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    session.execute(
        branches.insert(),
        [
            {
                "id": branch_id,

                "organization_id": organization_id,
                "legal_entity_id": legal_entity_id,
                "business_unit_id": business_unit_id,
                "name": "Sucursal Piloto",
                "code": "PILOTO",
                "timezone": "America/Chihuahua",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    session.execute(
        warehouses.insert(),
        [
            {
                "id": warehouse_id,
                "organization_id": organization_id,
                "branch_id": branch_id,
                "name": "Almacen Sucursal Piloto",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    session.execute(
        roles.insert(),
        [
            {
                "id": role_id,
                "organization_id": organization_id,
                "name": "Administrador corporativo",
                "scope": "organization",
                "created_at": now,
            }
        ],
    )
    session.execute(
        permissions.insert(),
        [
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000901",
                "code": "admin.manage",
                "description": "Administrar usuarios y roles",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000902",
                "code": "catalog.manage",
                "description": "Administrar catalogos",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000903",
                "code": "inventory.adjust",
                "description": "Registrar ajustes de inventario",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000904",
                "code": "orders.cancel",
                "description": "Cancelar pedidos",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000905",
                "code": "cash.shift.read",
                "description": "Consultar turnos de caja",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000906",
                "code": "cash.shift.open",
                "description": "Abrir turnos de caja",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000907",
                "code": "cash.shift.close",
                "description": "Cerrar turnos de caja",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000908",
                "code": "orders.read",
                "description": "Consultar pedidos POS",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000909",
                "code": "orders.create",
                "description": "Crear pedidos POS",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000910",
                "code": "payments.read",
                "description": "Consultar pagos",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000911",
                "code": "payments.confirm",
                "description": "Confirmar pagos POS",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000912",
                "code": "dashboard.read",
                "description": "Consultar dashboard operativo",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000913",
                "code": "pos.operate",
                "description": "Operar interfaz POS",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000914",
                "code": "production.manage",
                "description": "Gestionar produccion",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000915",
                "code": "inventory.waste",
                "description": "Registrar mermas reales",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000916",
                "code": "inventory.transfer.send",
                "description": "Enviar traspasos",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000917",
                "code": "inventory.transfer.receive",
                "description": "Recibir traspasos",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000918",
                "code": "inventory.count",
                "description": "Gestionar conteos físicos",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000919",
                "code": "cash.withdraw",
                "description": "Registrar retiros autorizados",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000920",
                "code": "inventory.read",
                "description": "Consultar inventario de sucursal",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000921",
                "code": "purchases.read",
                "description": "Consultar compras de sucursal",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000922",
                "code": "purchases.manage",
                "description": "Gestionar compras de sucursal",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000923",
                "code": "branch.admin.access",
                "description": "Entrar a administración de sucursal",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000924",
                "code": "branch.staff.read",
                "description": "Consultar personal de sucursal",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000925",
                "code": "catalog.branch.manage",
                "description": "Gestionar excepciones de catálogo por sucursal",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000926",
                "code": "orders.amend",
                "description": "Editar pedidos no pagados antes de producción",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000927",
                "code": "recipes.manage",
                "description": "Versionar recetas",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000928",
                "code": "kds.tasks.operate",
                "description": "Operar tareas KDS de la sucursal",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000929",
                "code": "print.jobs.read",
                "description": "Consultar trabajos de impresion",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000930",
                "code": "print.jobs.retry",
                "description": "Reintentar trabajos de impresion",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000931",
                "code": "orders.fulfill",
                "description": "Completar entrega y cierre de pedidos",
                "created_at": now,
            },
        ],
    )
    session.execute(
        role_permissions.insert(),
        [
            {"role_id": role_id, "permission_id": f"018f6f73-2d0a-74f0-8f1c-0000000009{suffix:02d}"}
            for suffix in range(1, 32)
        ],
    )
    session.execute(
        users.insert(),
        [
            {
                "id": user_id,
                "organization_id": organization_id,
                "email": "mangoex@gmail.com",
                "display_name": "Miguel Gonzalez",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    session.execute(
        user_credentials.insert(),
        [
            {
                "user_id": user_id,
                "password_hash": "uLG4WrRginnX-XVp2zegYbfB-chwTzI2M1h328MDiJM",
                "password_salt": "oaj3szcvziQTFhGeTZSDXA",
                "password_algorithm": "pbkdf2_sha256",
                "updated_at": now,
            }
        ],
    )
    session.execute(
        user_roles.insert(),
        [{"user_id": user_id, "role_id": role_id, "branch_id": None}],
    )
    session.execute(
        audit_events.insert(),
        [
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000007",
                "organization_id": organization_id,
                "branch_id": branch_id,
                "actor_user_id": user_id,
                "action": "platform.bootstrap_seeded",
                "entity_type": "organization",
                "entity_id": organization_id,
                "payload": {"source": "test"},
                "correlation_id": None,
                "created_at": now,
            }
        ],
    )
    session.execute(
        product_categories.insert(),
        [
            {
                "id": food_category_id,
                "organization_id": organization_id,
                "name": "Comida",
                "display_order": 10,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": drink_category_id,
                "organization_id": organization_id,
                "name": "Bebidas",
                "display_order": 20,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    session.execute(
        products.insert(),
        [
            {
                "id": burger_product_id,
                "organization_id": organization_id,
                "category_id": food_category_id,
                "name": "Hamburguesa Kiwi",
                "sku": "KIWI-BURGER",
                "description": "Producto semilla para flujo POS.",
                "station": "kitchen",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": fries_product_id,
                "organization_id": organization_id,
                "category_id": food_category_id,
                "name": "Papas",
                "sku": "KIWI-FRIES",
                "description": "Producto semilla para empaque.",
                "station": "kitchen",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": soda_product_id,
                "organization_id": organization_id,
                "category_id": drink_category_id,
                "name": "Refresco",
                "sku": "KIWI-SODA",
                "description": "Producto semilla para bebidas.",
                "station": "drinks",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    session.execute(
        price_versions.insert(),
        [
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000121",
                "organization_id": organization_id,
                "product_id": burger_product_id,
                "output_item_id": None,
                "branch_id": None,
                "recipe_type": "sale",
                "price_cents": 9500,
                "currency": "MXN",
                "valid_from": now,
                "valid_to": None,
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000122",
                "organization_id": organization_id,
                "product_id": fries_product_id,
                "price_cents": 4500,
                "currency": "MXN",
                "valid_from": now,
                "valid_to": None,
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000123",
                "organization_id": organization_id,
                "product_id": soda_product_id,
                "price_cents": 3000,
                "currency": "MXN",
                "valid_from": now,
                "valid_to": None,
                "created_at": now,
            },
        ],
    )
    session.execute(
        branch_product_availability.insert(),
        [
            {
                "branch_id": branch_id,
                "product_id": burger_product_id,
                "is_available": True,
                "updated_at": now,
            },
            {
                "branch_id": branch_id,
                "product_id": fries_product_id,
                "is_available": True,
                "updated_at": now,
            },
            {
                "branch_id": branch_id,
                "product_id": soda_product_id,
                "is_available": True,
                "updated_at": now,
            },
        ],
    )
    session.execute(
        inventory_units.insert(),
        [
            {
                "id": unit_gram_id,
                "organization_id": organization_id,
                "code": "g",
                "name": "Gramo",
                "precision_scale": 0,
                "created_at": now,
            },
            {
                "id": unit_ml_id,
                "organization_id": organization_id,
                "code": "ml",
                "name": "Mililitro",
                "precision_scale": 0,
                "created_at": now,
            },
            {
                "id": unit_piece_id,
                "organization_id": organization_id,
                "code": "pz",
                "name": "Pieza",
                "precision_scale": 0,
                "created_at": now,
            },
        ],
    )
    session.execute(
        inventory_items.insert(),
        [
            {
                "id": beef_item_id,
                "organization_id": organization_id,
                "name": "Carne molida",
                "sku": "INV-BEEF",
                "base_unit_id": unit_gram_id,
                "item_type": "ingredient",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": bun_item_id,
                "organization_id": organization_id,
                "name": "Pan brioche",
                "sku": "INV-BUN",
                "base_unit_id": unit_piece_id,
                "item_type": "ingredient",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": potato_item_id,
                "organization_id": organization_id,
                "name": "Papa blanca",
                "sku": "INV-POTATO",
                "base_unit_id": unit_gram_id,
                "item_type": "ingredient",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": syrup_item_id,
                "organization_id": organization_id,
                "name": "Jarabe refresco",
                "sku": "INV-SYRUP",
                "base_unit_id": unit_ml_id,
                "item_type": "ingredient",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    session.execute(
        recipes.insert(),
        [
            {
                "id": burger_recipe_id,
                "organization_id": organization_id,
                "product_id": burger_product_id,
                "version": 1,
                "status": "active",
                "yield_quantity": 1,
                "yield_unit_id": unit_piece_id,
                "valid_from": now,
                "valid_to": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": fries_recipe_id,
                "organization_id": organization_id,
                "product_id": fries_product_id,
                "output_item_id": None,
                "branch_id": None,
                "recipe_type": "sale",
                "version": 1,
                "status": "active",
                "yield_quantity": 1,
                "yield_unit_id": unit_piece_id,
                "valid_from": now,
                "valid_to": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": soda_recipe_id,
                "organization_id": organization_id,
                "product_id": soda_product_id,
                "output_item_id": None,
                "branch_id": None,
                "recipe_type": "sale",
                "version": 1,
                "status": "active",
                "yield_quantity": 1,
                "yield_unit_id": unit_piece_id,
                "valid_from": now,
                "valid_to": None,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    session.execute(
        recipe_components.insert(),
        [
            {
                "recipe_id": burger_recipe_id,
                "item_id": beef_item_id,
                "quantity_base_units": 120,
                "unit_id": unit_gram_id,
                "net_quantity": 120,
                "waste_rate": 0,
                "gross_quantity": 120,
                "sort_order": 0,
                "notes": None,
            },
            {
                "recipe_id": burger_recipe_id,
                "item_id": bun_item_id,
                "quantity_base_units": 1,
                "unit_id": unit_piece_id,
                "net_quantity": 1,
                "waste_rate": 0,
                "gross_quantity": 1,
                "sort_order": 1,
                "notes": None,
            },
            {
                "recipe_id": fries_recipe_id,
                "item_id": potato_item_id,
                "quantity_base_units": 180,
                "unit_id": unit_gram_id,
                "net_quantity": 180,
                "waste_rate": 0,
                "gross_quantity": 180,
                "sort_order": 0,
                "notes": None,
            },
            {
                "recipe_id": soda_recipe_id,
                "item_id": syrup_item_id,
                "quantity_base_units": 80,
                "unit_id": unit_ml_id,
                "net_quantity": 80,
                "waste_rate": 0,
                "gross_quantity": 80,
                "sort_order": 0,
                "notes": None,
            },
        ],
    )
    session.execute(
        inventory_movements.insert(),
        [
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000331",
                "organization_id": organization_id,
                "branch_id": branch_id,
                "warehouse_id": warehouse_id,
                "item_id": beef_item_id,
                "movement_type": "OPENING_BALANCE",
                "quantity_delta": 25000,
                "unit_id": unit_gram_id,
                "reason": "Saldo inicial semilla",
                "source_type": "test",
                "source_id": None,
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000332",
                "organization_id": organization_id,
                "branch_id": branch_id,
                "warehouse_id": warehouse_id,
                "item_id": bun_item_id,
                "movement_type": "OPENING_BALANCE",
                "quantity_delta": 120,
                "unit_id": unit_piece_id,
                "reason": "Saldo inicial semilla",
                "source_type": "test",
                "source_id": None,
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000333",
                "organization_id": organization_id,
                "branch_id": branch_id,
                "warehouse_id": warehouse_id,
                "item_id": potato_item_id,
                "movement_type": "OPENING_BALANCE",
                "quantity_delta": 35000,
                "unit_id": unit_gram_id,
                "reason": "Saldo inicial semilla",
                "source_type": "test",
                "source_id": None,
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000000334",
                "organization_id": organization_id,
                "branch_id": branch_id,
                "warehouse_id": warehouse_id,
                "item_id": syrup_item_id,
                "movement_type": "OPENING_BALANCE",
                "quantity_delta": 10000,
                "unit_id": unit_ml_id,
                "reason": "Saldo inicial semilla",
                "source_type": "test",
                "source_id": None,
                "created_at": now,
            },
        ],
    )
    session.commit()


def test_product_image_url_crud() -> None:
    client = _client_with_seeded_database()

    # 1. Get products and check image_url is present (should be None or string)
    get_res = client.get("/api/v1/catalog/products", headers=_admin_headers())
    assert get_res.status_code == 200
    products = get_res.json()
    assert len(products) > 0
    # The seeded products don't have image_url, so it should be None/null
    assert all("image_url" in p for p in products)

    # 2. Update a product with an image_url
    product_id = products[0]["id"]
    update_res = client.put(
        f"/api/v1/catalog/products/{product_id}",
        headers=_admin_headers(),
        json={
            "image_url": "https://example.com/test-image.png",
        },
    )
    assert update_res.status_code == 200
    assert update_res.json()["image_url"] == "https://example.com/test-image.png"

    # Verify it persists in subsequent GET request
    get_res2 = client.get("/api/v1/catalog/products", headers=_admin_headers())
    updated_product = next(p for p in get_res2.json() if p["id"] == product_id)
    assert updated_product["image_url"] == "https://example.com/test-image.png"


def test_update_user_profile() -> None:
    client = _client_with_seeded_database()

    # 1. Login to get token
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "mangoex@gmail.com", "password": "superadmin-test-password"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["token"]
    user_id = login_res.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Update display name and email
    update_res = client.put(
        f"/api/v1/users/{user_id}",
        headers=headers,
        json={
            "display_name": "Miguel G. Espino",
            "email": "mangoex@gmail.com",
        },
    )
    assert update_res.status_code == 200
    assert update_res.json()["display_name"] == "Miguel G. Espino"


def _login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_pos_session_handoff_is_single_use_and_requires_authenticated_pos_actor() -> None:
    client = _client_with_seeded_database()
    _branch_admin_fixture(client)
    cashier_headers = _login_headers(client, "cajero.norte@kiwi.local", "Temporal123+")

    assert client.post("/api/v1/auth/pos-handoffs").status_code == 401
    issued = client.post("/api/v1/auth/pos-handoffs", headers=cashier_headers)

    assert issued.status_code == 200
    issuance = issued.json()
    assert issuance["target_app"] == "pos"
    assert issuance["expires_in_seconds"] == 60
    assert len(issuance["handoff_code"]) >= 32
    assert "token" not in issuance

    with _test_session_factory(client)() as session:
        stored = session.execute(pos_session_handoffs.select()).mappings().one()
        assert stored["code_hash"] == hashlib.sha256(
            issuance["handoff_code"].encode("utf-8")
        ).hexdigest()
        assert issuance["handoff_code"] not in str(stored)

    exchanged = client.post(
        "/api/v1/auth/pos-handoffs/exchange",
        json={"handoff_code": issuance["handoff_code"]},
    )
    assert exchanged.status_code == 200
    token = exchanged.json()["token"]
    profile = client.get(
        "/api/v1/auth/session", headers={"Authorization": f"Bearer {token}"}
    )
    assert profile.status_code == 200
    assert profile.json()["user"]["email"] == "cajero.norte@kiwi.local"

    replay = client.post(
        "/api/v1/auth/pos-handoffs/exchange",
        json={"handoff_code": issuance["handoff_code"]},
    )
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "pos_handoff_used"

    altered = client.post(
        "/api/v1/auth/pos-handoffs/exchange",
        json={"handoff_code": f"{issuance['handoff_code']}x"},
    )
    assert altered.status_code == 409
    assert altered.json()["detail"]["code"] == "pos_handoff_invalid"
    padded = client.post(
        "/api/v1/auth/pos-handoffs/exchange",
        json={"handoff_code": f" {issuance['handoff_code']} "},
    )
    assert padded.status_code == 409
    assert padded.json()["detail"]["code"] == "pos_handoff_invalid"

    with _test_session_factory(client)() as session:
        handoff_audits = list(
            session.execute(
                audit_events.select()
                .where(audit_events.c.entity_id == stored["id"])
                .order_by(audit_events.c.created_at)
            ).mappings()
        )
        assert [row["action"] for row in handoff_audits] == [
            "auth.pos_handoff_issued",
            "auth.pos_handoff_consumed",
            "auth.pos_handoff_rejected",
        ]
        assert handoff_audits[-1]["payload"]["reason_code"] == "pos_handoff_used"
        assert session.execute(
            audit_events.select().where(audit_events.c.entity_id == "unresolved")
        ).first() is None
        assert issuance["handoff_code"] not in str(handoff_audits)
        assert token not in str(handoff_audits)


def test_pos_session_handoff_rejects_expired_code() -> None:
    client = _client_with_seeded_database()
    _branch_admin_fixture(client)
    cashier_headers = _login_headers(client, "cajero.norte@kiwi.local", "Temporal123+")
    issuance = client.post("/api/v1/auth/pos-handoffs", headers=cashier_headers).json()

    with _test_session_factory(client)() as session:
        session.execute(
            pos_session_handoffs.update().values(
                expires_at=datetime(2020, 1, 1, tzinfo=UTC)
            )
        )
        session.commit()

    expired = client.post(
        "/api/v1/auth/pos-handoffs/exchange",
        json={"handoff_code": issuance["handoff_code"]},
    )
    assert expired.status_code == 409
    assert expired.json()["detail"]["code"] == "pos_handoff_expired"
    with _test_session_factory(client)() as session:
        rejection = session.execute(
            audit_events.select().where(
                audit_events.c.action == "auth.pos_handoff_rejected"
            )
        ).mappings().one()
        assert rejection["payload"]["reason_code"] == "pos_handoff_expired"


def test_pos_session_handoff_rejects_inactive_user_and_audits_without_secret() -> None:
    client = _client_with_seeded_database()
    fixture = _branch_admin_fixture(client)
    cashier_headers = _login_headers(client, "cajero.norte@kiwi.local", "Temporal123+")
    issuance = client.post("/api/v1/auth/pos-handoffs", headers=cashier_headers).json()

    with _test_session_factory(client)() as session:
        session.execute(
            users.update()
            .where(users.c.id == fixture["cashier_id"])
            .values(status="inactive")
        )
        session.commit()

    rejected = client.post(
        "/api/v1/auth/pos-handoffs/exchange",
        json={"handoff_code": issuance["handoff_code"]},
    )

    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "user_inactive"
    with _test_session_factory(client)() as session:
        rejection = session.execute(
            audit_events.select().where(
                audit_events.c.action == "auth.pos_handoff_rejected"
            )
        ).mappings().one()
        assert rejection["payload"]["reason_code"] == "user_inactive"
        assert issuance["handoff_code"] not in str(rejection)


def _branch_admin_fixture(client: TestClient) -> dict[str, str]:
    branch_response = client.post(
        "/api/v1/branches",
        headers=_admin_headers(),
        json={"name": "Sucursal Norte", "code": "NORTE"},
    )
    assert branch_response.status_code == 200
    branch = branch_response.json()

    supervisor_role = client.post(
        "/api/v1/roles",

        headers=_admin_headers(),
        json={"name": "Supervisor de sucursal", "scope": "branch"},
    )
    assert supervisor_role.status_code == 200
    supervisor_permissions = set(supervisor_role.json()["permissions"])
    assert {
        "branch.admin.access",
        "branch.staff.read",
        "catalog.branch.manage",
        "production.manage",
    } <= supervisor_permissions

    cashier_role = client.post(
        "/api/v1/roles",
        headers=_admin_headers(),
        json={"name": "Cajero", "scope": "branch"},
    )
    assert cashier_role.status_code == 200
    assert "branch.admin.access" not in cashier_role.json()["permissions"]

    def create_user(
        email: str,
        display_name: str,
        employee_code: str,
        role_id: str,
        branch_id: str,
    ) -> str:
        response = client.post(
            "/api/v1/users",
            headers=_admin_headers(),
            json={
                "email": email,
                "display_name": display_name,
                "employee_code": employee_code,
                "password": "Temporal123+",
                "role_id": role_id,
                "branch_id": branch_id,
            },
        )
        assert response.status_code == 200
        return str(response.json()["id"])

    supervisor_id = create_user(
        "supervisor.norte@kiwi.local",
        "Supervisora Norte",
        "SUP001",
        supervisor_role.json()["id"],
        branch["id"],
    )
    cashier_id = create_user(
        "cajero.norte@kiwi.local",
        "Cajero Norte",
        "CAJ002",
        cashier_role.json()["id"],
        branch["id"],
    )
    outsider_id = create_user(
        "cajero.piloto@kiwi.local",
        "Cajero Piloto",
        "OUT001",
        cashier_role.json()["id"],
        BRANCH_ID,
    )
    return {
        "branch_id": branch["id"],
        "warehouse_id": branch["warehouse"]["id"],
        "supervisor_id": supervisor_id,
        "cashier_id": cashier_id,
        "outsider_id": outsider_id,
    }


def test_branch_admin_session_and_scope_guards() -> None:
    client = _client_with_seeded_database()
    fixture = _branch_admin_fixture(client)
    supervisor_headers = _login_headers(
        client, "supervisor.norte@kiwi.local", "Temporal123+"
    )

    assert client.get("/api/v1/auth/session").status_code == 401
    assert client.get(
        "/api/v1/auth/session", headers={"Authorization": "Bearer invalid"}
    ).status_code == 401
    assert client.get("/api/v1/branches").status_code == 401

    session_response = client.get("/api/v1/auth/session", headers=supervisor_headers)
    assert session_response.status_code == 200
    profile = session_response.json()
    assert profile["scope"] == {
        "level": "branch",
        "assigned_branch_id": fixture["branch_id"],
        "allowed_branch_ids": [fixture["branch_id"]],
    }
    assert profile["active_branch"]["id"] == fixture["branch_id"]
    assert profile["active_branch"]["business_unit"]["unit_type"] == "restaurant"
    assert profile["active_branch"]["warehouse"]["id"] == fixture["warehouse_id"]
    assert "branch.admin.access" in profile["permissions"]
    assert "password_hash" not in str(profile)
    assert "password_salt" not in str(profile)

    wrong_branch = client.get(
        f"/api/v1/branch-administration/context?branch_id={BRANCH_ID}",
        headers=supervisor_headers,
    )
    assert wrong_branch.status_code == 403
    assert wrong_branch.json()["detail"]["code"] == "permission_denied"

    cashier_headers = _login_headers(client, "cajero.norte@kiwi.local", "Temporal123+")
    cashier_context = client.get(
        "/api/v1/branch-administration/context", headers=cashier_headers
    )
    assert cashier_context.status_code == 403
    assert cashier_context.json()["detail"]["code"] == "permission_denied"

    delete_response = client.delete(
        f"/api/v1/users/{fixture['supervisor_id']}", headers=_admin_headers()
    )
    assert delete_response.status_code == 200
    assert client.get("/api/v1/auth/session", headers=supervisor_headers).status_code == 403


def test_branch_admin_staff_availability_and_audit_are_branch_scoped() -> None:
    client = _client_with_seeded_database()
    fixture = _branch_admin_fixture(client)
    headers = _login_headers(client, "supervisor.norte@kiwi.local", "Temporal123+")

    staff_response = client.get(
        "/api/v1/branch-administration/staff", headers=headers
    )
    assert staff_response.status_code == 200
    staff_ids = {row["id"] for row in staff_response.json()}
    assert fixture["supervisor_id"] in staff_ids
    assert fixture["cashier_id"] in staff_ids
    assert fixture["outsider_id"] not in staff_ids
    assert "password" not in str(staff_response.json()).lower()

    catalog_response = client.get(
        "/api/v1/branch-administration/catalog/products", headers=headers
    )
    assert catalog_response.status_code == 200
    product = catalog_response.json()[0]
    assert product["has_local_override"] is False
    assert product["availability_source"] == "central"
    assert product["effective_availability"] is True

    missing = client.put(
        "/api/v1/branch-administration/catalog/products/missing/availability",
        headers=headers,
        json={"action": "unavailable"},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "product_not_found"

    unavailable = client.put(
        f"/api/v1/branch-administration/catalog/products/{product['id']}/availability",
        headers=headers,
        json={"action": "unavailable"},
    )
    assert unavailable.status_code == 200
    assert unavailable.json()["effective_availability"] is False
    branch_catalog = client.get(
        "/api/v1/branch-administration/catalog/products", headers=headers
    ).json()
    changed = next(row for row in branch_catalog if row["id"] == product["id"])
    assert changed["has_local_override"] is True
    assert changed["availability_source"] == "branch_override"
    assert changed["sellable"] is False

    inherited = client.put(
        f"/api/v1/branch-administration/catalog/products/{product['id']}/availability",
        headers=headers,
        json={"action": "inherit"},
    )
    assert inherited.status_code == 200
    assert inherited.json()["has_local_override"] is False

    session_factory = _test_session_factory(client)
    with session_factory() as session:
        override = session.execute(
            branch_product_availability.select().where(
                branch_product_availability.c.branch_id == fixture["branch_id"],
                branch_product_availability.c.product_id == product["id"],
            )
        ).first()
        assert override is None
        audit_rows = session.execute(
            audit_events.select().where(
                audit_events.c.branch_id == fixture["branch_id"],
                audit_events.c.action == "branch_product_availability.updated",
            )
        ).mappings().all()
        assert len(audit_rows) == 2
        assert audit_rows[0]["payload"]["previous"] is None
        assert audit_rows[0]["payload"]["new"] is False


def test_branch_inventory_reads_do_not_leak_another_branch() -> None:
    client = _client_with_seeded_database()
    fixture = _branch_admin_fixture(client)
    headers = _login_headers(client, "supervisor.norte@kiwi.local", "Temporal123+")
    now = datetime(2026, 7, 12, 22, 0, tzinfo=UTC)
    beef_item_id = "018f6f73-2d0a-74f0-8f1c-000000000311"
    gram_unit_id = "018f6f73-2d0a-74f0-8f1c-000000000301"

    session_factory = _test_session_factory(client)
    with session_factory() as session:
        session.execute(
            inventory_movements.insert().values(
                id="018f6f73-2d0a-74f0-8f1c-000000009901",
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                branch_id=fixture["branch_id"],
                warehouse_id=fixture["warehouse_id"],
                item_id=beef_item_id,
                movement_type="OPENING_BALANCE",
                quantity_delta=7,
                unit_id=gram_unit_id,
                reason="Aislamiento BA-001",
                source_type="test",
                created_at=now,
            )
        )
        session.commit()

    stock_response = client.get("/api/v1/inventory/stock", headers=headers)
    assert stock_response.status_code == 200
    stock = stock_response.json()
    assert stock
    assert {row["branch_id"] for row in stock} == {fixture["branch_id"]}
    beef = next(row for row in stock if row["id"] == beef_item_id)
    assert beef["quantity_on_hand"] == 7

    kardex_response = client.get("/api/v1/inventory/kardex", headers=headers)
    assert kardex_response.status_code == 200
    assert {row["branch_id"] for row in kardex_response.json()} == {fixture["branch_id"]}

    forged = client.get(
        f"/api/v1/inventory/stock?branch_id={BRANCH_ID}", headers=headers
    )
    assert forged.status_code == 403


def test_branch_supervisor_cannot_mutate_central_catalog_or_identity() -> None:
    client = _client_with_seeded_database()
    fixture = _branch_admin_fixture(client)
    headers = _login_headers(client, "supervisor.norte@kiwi.local", "Temporal123+")

    product_response = client.post(
        "/api/v1/catalog/products",
        headers=headers,
        json={
            "name": "Producto no autorizado",
            "sku": "NO-AUTH",
            "category_name": "Comida",
            "station": "kitchen",
            "price_cents": 100,
        },
    )
    assert product_response.status_code == 403

    user_response = client.post(
        "/api/v1/users",
        headers=headers,
        json={"email": "forbidden@kiwi.local", "display_name": "Prohibido"},
    )
    assert user_response.status_code == 403
    assert client.get("/api/v1/branches", headers=headers).status_code == 403

    context = client.get(
        "/api/v1/branch-administration/context", headers=headers
    )
    assert context.status_code == 200
    assert context.json()["id"] == fixture["branch_id"]

    legal_entity_id = "018f6f73-2d0a-74f0-8f1c-000000000002"
    for unit_type in ("bakery", "production"):
        response = client.post(
            "/api/v1/business-units",
            headers=_admin_headers(),
            json={
                "name": f"Unidad {unit_type}",
                "code": unit_type.upper(),
                "unit_type": unit_type,
                "legal_entity_id": legal_entity_id,
            },
        )
        assert response.status_code == 200
        assert response.json()["unit_type"] == unit_type

    invalid = client.post(
        "/api/v1/business-units",
        headers=_admin_headers(),
        json={
            "name": "Unidad inválida",
            "code": "INVALID",
            "unit_type": "factory",
            "legal_entity_id": legal_entity_id,
        },
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "invalid_business_unit_type"
