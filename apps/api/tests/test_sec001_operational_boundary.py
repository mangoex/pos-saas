# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-sec001-tests-v1
from __future__ import annotations

# ruff: noqa: E501
import hashlib
import json
import subprocess
import sys
import threading
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os import operations as operational_services
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.internal_seed import apply_manifest
from restaurant_os.internal_seed_presets import kiwi_v1_manifest
from restaurant_os.main import create_app
from restaurant_os.operational_guard import OperationalRouteGuard
from restaurant_os.operations import (
    BusinessError,
    acknowledge_print_attempt,
    advance_kds_task,
    claim_print_attempt,
    fail_print_attempt,
    receive_sync_command,
    retry_print_job,
)
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def _client() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    models.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app()

    def override() -> Generator[Session, None, None]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    client = TestClient(app)
    client.app.state.sec001_session_factory = factory
    return client


def _client_session(client: TestClient) -> Session:
    return client.app.state.sec001_session_factory()


def _operational_scope(session: Session, organization_id: str, branch_id: str) -> None:
    now = datetime.now(timezone.utc)
    if not session.execute(
        models.organizations.select().where(models.organizations.c.id == organization_id)
    ).first():
        session.execute(
            models.organizations.insert().values(
                id=organization_id,
                name=f"Synthetic {organization_id}",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.legal_entities.insert().values(
                id=f"legal-{organization_id}",
                organization_id=organization_id,
                name="Synthetic legal entity",
                tax_id=None,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.business_units.insert().values(
                id=f"unit-{organization_id}",
                organization_id=organization_id,
                legal_entity_id=f"legal-{organization_id}",
                name="Synthetic unit",
                code=f"U-{organization_id}"[:32],
                unit_type="restaurant",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
    if not session.execute(
        models.branches.select().where(models.branches.c.id == branch_id)
    ).first():
        session.execute(
            models.branches.insert().values(
                id=branch_id,
                organization_id=organization_id,
                legal_entity_id=f"legal-{organization_id}",
                business_unit_id=f"unit-{organization_id}",
                name=f"Synthetic {branch_id}",
                code=f"B-{branch_id}"[:32],
                timezone="America/Mazatlan",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )


def _device_credential(
    session: Session,
    *,
    device_id: str,
    token: str,
    capability: str,
    organization_id: str,
    branch_id: str,
) -> None:
    now = datetime.now(timezone.utc)
    _operational_scope(session, organization_id, branch_id)
    session.execute(
        models.device_credentials.insert().values(
            id=device_id,
            organization_id=organization_id,
            branch_id=branch_id,
            capability=capability,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            key_version="v1",
            expires_at=now + timedelta(minutes=5),
            revoked_at=None,
            created_at=now,
        )
    )
    session.commit()


def test_tc141_operational_routes_deny_anonymous_without_side_effects() -> None:
    client = _client()
    calls = (
        ("get", "/api/v1/kds/tasks", None),
        ("post", "/api/v1/kds/tasks/missing/transition", {"status": "IN_PROGRESS"}),
        ("get", "/api/v1/print-jobs", None),
        ("post", "/api/v1/print-jobs/missing/retry", None),
        ("post", "/api/v1/sync/commands", {"invalid": True}),
        ("get", "/api/v1/sync/events", None),
        ("get", "/api/v1/sync/status", None),
    )
    for method, path, payload in calls:
        request_kwargs = {"json": payload} if payload is not None else {}
        response = getattr(client, method)(path, **request_kwargs)
        assert response.status_code in {401, 403}, path
    assert client.get("/api/v1/kds/tasks", headers={"X-Actor-User-Id": "forged"}).status_code == 401
    assert (
        client.get("/api/v1/kds/tasks", headers={"Authorization": "Bearer invalid"}).status_code
        == 401
    )
    assert client.post("/api/v1/seed_menu").status_code == 404
    assert client.post("/api/v1/seed_branches").status_code == 404


def test_tc143_kds_device_uses_persisted_branch_b_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client()
    token = "kds-branch-b-token"
    with _client_session(client) as session:
        _device_credential(
            session,
            device_id="kds-b",
            token=token,
            capability="kds.operate",
            organization_id="org-b",
            branch_id="branch-b",
        )
    observed: list[str] = []
    transitions: list[tuple[str, str]] = []

    def scoped_tasks(_session: Session, branch_id: str) -> list[dict[str, str]]:
        observed.append(branch_id)
        return [{"id": "task-b", "branch_id": branch_id}]

    def scoped_transition(
        _session: Session,
        task_id: str,
        _status: str,
        branch_id: str,
        **_actors: object,
    ) -> dict[str, str]:
        transitions.append((task_id, branch_id))
        return {"id": task_id, "branch_id": branch_id}

    monkeypatch.setattr("restaurant_os.api.list_kds_tasks", scoped_tasks)
    monkeypatch.setattr("restaurant_os.api.advance_kds_task", scoped_transition)

    response = client.get("/api/v1/kds/tasks", headers={"X-Device-Token": token})
    transition = client.post(
        "/api/v1/kds/tasks/task-from-branch-a/transition",
        headers={"X-Device-Token": token},
        json={"status": "IN_PROGRESS"},
    )

    assert response.status_code == 200
    assert response.json() == [{"id": "task-b", "branch_id": "branch-b"}]
    assert observed == ["branch-b"]
    assert transition.status_code == 200
    assert transitions == [("task-from-branch-a", "branch-b")]


def test_tc143_kds_human_requires_dedicated_permission() -> None:
    client = _client()
    now = datetime.now(timezone.utc)
    user_id = "human-orders-only"
    with _client_session(client) as session:
        session.execute(
            models.users.insert().values(
                id=user_id,
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                email="orders-only@example.test",
                display_name="Orders only",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.roles.insert().values(
                id="role-orders-only",
                organization_id="018f6f73-2d0a-74f0-8f1c-000000000001",
                name="SEC001 orders only",
                scope="branch",
                created_at=now,
            )
        )
        session.execute(
            models.permissions.insert().values(
                id="permission-orders-create",
                code="orders.create",
                description="Test orders permission",
                created_at=now,
            )
        )
        session.execute(
            models.role_permissions.insert().values(
                role_id="role-orders-only", permission_id="permission-orders-create"
            )
        )
        session.execute(
            models.user_roles.insert().values(
                user_id=user_id,
                role_id="role-orders-only",
                branch_id="018f6f73-2d0a-74f0-8f1c-000000000003",
            )
        )
        session.commit()
    token = create_session_token({"sub": user_id}, get_settings().secret_key)

    response = client.get(
        "/api/v1/kds/tasks", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "operational_route_denied"


def test_human_operational_routes_reauthorize_explicit_branch_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client()
    organization_id = "018f6f73-2d0a-74f0-8f1c-000000000001"
    user_id = "human-operational-branch-b"
    now = datetime.now(timezone.utc)
    with _client_session(client) as session:
        _operational_scope(session, organization_id, "branch-a")
        _operational_scope(session, organization_id, "branch-b")
        session.execute(
            models.users.insert().values(
                id=user_id,
                organization_id=organization_id,
                email="operational-b@example.test",
                display_name="Operational B",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            models.roles.insert().values(
                id="role-operational-b",
                organization_id=organization_id,
                name="Operational B",
                scope="branch",
                created_at=now,
            )
        )
        for index, code in enumerate(
            ("kds.tasks.operate", "print.jobs.read", "print.jobs.retry", "sync.events.read")
        ):
            permission_id = f"permission-operational-{index}"
            session.execute(
                models.permissions.insert().values(
                    id=permission_id,
                    code=code,
                    description=f"Synthetic {code}",
                    created_at=now,
                )
            )
            session.execute(
                models.role_permissions.insert().values(
                    role_id="role-operational-b",
                    permission_id=permission_id,
                )
            )
        session.execute(
            models.user_roles.insert().values(
                user_id=user_id,
                role_id="role-operational-b",
                branch_id="branch-b",
            )
        )
        session.commit()

    observed: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "restaurant_os.api.list_kds_tasks",
        lambda _session, branch_id: observed.append(("kds", branch_id)) or [],
    )
    monkeypatch.setattr(
        "restaurant_os.api.list_print_jobs",
        lambda _session, branch_id: observed.append(("print", branch_id)) or [],
    )
    monkeypatch.setattr(
        "restaurant_os.api.list_sync_events",
        lambda _session, _organization_id, branch_id, _checkpoint: (
            observed.append(("sync-events", branch_id)) or []
        ),
    )
    monkeypatch.setattr(
        "restaurant_os.api.get_sync_status",
        lambda _session, _organization_id, branch_id: (
            observed.append(("sync-status", branch_id))
            or {"branch_id": branch_id, "last_checkpoint": 0}
        ),
    )
    token = create_session_token({"sub": user_id}, get_settings().secret_key)
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/v1/kds/tasks?branch_id=branch-b", headers=headers).status_code == 200
    assert client.get("/api/v1/print-jobs?branch_id=branch-b", headers=headers).status_code == 200
    assert client.get("/api/v1/sync/events?branch_id=branch-b", headers=headers).status_code == 200
    assert client.get("/api/v1/sync/status?branch_id=branch-b", headers=headers).status_code == 200
    for path in ("kds/tasks", "print-jobs", "sync/events", "sync/status"):
        assert client.get(f"/api/v1/{path}?branch_id=branch-a", headers=headers).status_code in {
            401,
            403,
        }
    assert observed == [
        ("kds", "branch-b"),
        ("print", "branch-b"),
        ("sync-events", "branch-b"),
        ("sync-status", "branch-b"),
    ]


def _sync_envelope(
    *, organization_id: str, branch_id: str, device_id: str, idempotency_key: str
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "command_id": f"command-{device_id}",
        "idempotency_key": idempotency_key,
        "organization_id": organization_id,
        "branch_id": branch_id,
        "source_device_id": device_id,
        "command_type": "local_order.closed",
        "occurred_at": "2026-08-20T12:00:00Z",
        "payload": {"synthetic": True},
    }


def _governed_seed_manifest(organization_id: str = "org-seed") -> dict[str, object]:
    return {
        "organization_id": organization_id,
        "environment": "test",
        "operations": [
            {
                "type": "ensure_organization.v1",
                "id": organization_id,
                "name": "Kiwi Restaurante",
            },
            {
                "type": "ensure_branch_topology.v1",
                "legal_entity": {
                    "id": "legal-seed",
                    "name": "Kiwi S.A. de C.V.",
                },
                "business_unit": {
                    "id": "unit-seed",
                    "legal_entity_id": "legal-seed",
                    "name": "Operaciones Kiwi",
                    "code": "KIWI",
                    "unit_type": "restaurant",
                },
                "branches": [
                    {
                        "id": "branch-seed",
                        "legal_entity_id": "legal-seed",
                        "business_unit_id": "unit-seed",
                        "name": "Kiwi Matriz",
                        "code": "MTZ",
                        "timezone": "America/Mazatlan",
                        "warehouse": {
                            "id": "warehouse-seed",
                            "name": "Almacén Kiwi Matriz",
                        },
                    }
                ],
            },
            {
                "type": "ensure_menu_catalog.v1",
                "branch_id": "branch-seed",
                "categories": [
                    {
                        "id": "category-juice",
                        "name": "Jugos y Extractos",
                        "display_order": 1,
                    }
                ],
                "units": [
                    {
                        "id": "inventory-unit-kg",
                        "code": "KG",
                        "name": "Kilogramo",
                        "dimension": "mass",
                        "precision_scale": 3,
                    },
                    {
                        "id": "inventory-unit-portion",
                        "code": "POR",
                        "name": "Porción",
                        "dimension": "discrete",
                        "precision_scale": 0,
                    },
                ],
                "items": [
                    {
                        "id": "item-orange",
                        "name": "Naranja",
                        "sku": "INS-NAR",
                        "base_unit_id": "inventory-unit-kg",
                        "item_type": "ingredient",
                    }
                ],
                "products": [
                    {
                        "id": "product-green-juice",
                        "category_id": "category-juice",
                        "name": "Jugo Verde",
                        "sku": "JUG-VER",
                        "description": "Naranja.",
                        "station": "barra",
                        "price": {
                            "id": "price-green-juice",
                            "price_cents": 6500,
                            "currency": "MXN",
                        },
                        "recipe": {
                            "id": "recipe-green-juice",
                            "version": 1,
                            "yield_quantity": "1.000000",
                            "yield_unit_id": "inventory-unit-portion",
                            "components": [
                                {
                                    "item_id": "item-orange",
                                    "unit_id": "inventory-unit-kg",
                                    "quantity_base_units": "0.100000",
                                    "net_quantity": "0.100000",
                                    "waste_rate": "0.000000",
                                    "gross_quantity": "0.100000",
                                    "sort_order": 0,
                                }
                            ],
                        },
                    }
                ],
            },
        ],
    }


def test_tc143_unsupported_sync_command_is_fail_closed() -> None:
    session = _session()
    for organization_id, branch_id, device_id in (
        ("org-a", "branch-a", "gateway-a"),
        ("org-b", "branch-b", "gateway-b"),
        ("org-a", "branch-b", "gateway-a"),
        ("org-a", "branch-a", "gateway-b"),
    ):
        with pytest.raises(BusinessError) as exc_info:
            receive_sync_command(
                session,
                _sync_envelope(
                    organization_id=organization_id,
                    branch_id=branch_id,
                    device_id=device_id,
                    idempotency_key="shared-sync-key-0001",
                ),
                organization_id,
                branch_id,
                device_id,
            )
        assert exc_info.value.code == "unsupported_sync_command"
    assert session.execute(models.sync_commands.select()).mappings().all() == []
    assert session.execute(models.sync_events.select()).mappings().all() == []


def test_tc143_gateway_lists_only_events_from_persisted_scope() -> None:
    client = _client()
    token = "gateway-branch-b-token"
    with _client_session(client) as session:
        _device_credential(
            session,
            device_id="gateway-b",
            token=token,
            capability="gateway.sync",
            organization_id="org-b",
            branch_id="branch-b",
        )
        _device_credential(
            session,
            device_id="gateway-b-peer",
            token="gateway-branch-b-peer-token",
            capability="gateway.sync",
            organization_id="org-b",
            branch_id="branch-b",
        )
        _operational_scope(session, "org-a", "branch-a")
        now = datetime.now(timezone.utc)
        persisted = (
            ("sync-command-a", "sync-event-a", "org-a", "branch-a", "gateway-a", 1),
            ("sync-command-b1", "sync-event-b1", "org-b", "branch-b", "gateway-b", 1),
            (
                "sync-command-b2",
                "sync-event-b2",
                "org-b",
                "branch-b",
                "gateway-b-peer",
                2,
            ),
        )
        for command_id, event_id, organization_id, branch_id, device_id, checkpoint in persisted:
            session.execute(
                models.sync_commands.insert().values(
                    id=command_id,
                    organization_id=organization_id,
                    branch_id=branch_id,
                    source_device_id=device_id,
                    command_id=f"external-{command_id}",
                    idempotency_key=f"key-{command_id}",
                    command_type="synthetic.persisted",
                    payload={"synthetic": True},
                    status="CONFIRMED",
                    checkpoint=checkpoint,
                    occurred_at=now,
                    received_at=now,
                    confirmed_at=now,
                )
            )
            session.execute(
                models.sync_events.insert().values(
                    id=event_id,
                    organization_id=organization_id,
                    branch_id=branch_id,
                    sync_command_id=command_id,
                    event_type="synthetic.persisted.confirmed",
                    checkpoint=checkpoint,
                    payload={"synthetic": True},
                    occurred_at=now,
                )
            )
        session.commit()

    response = client.get("/api/v1/sync/events", headers={"X-Device-Token": token})

    assert response.status_code == 200
    assert [event["organization_id"] for event in response.json()] == ["org-b", "org-b"]


def test_tc143_sync_malformed_scope_denial_is_stable_and_has_zero_effects() -> None:
    client = _client()
    token = "gateway-safe-audit-token"
    with _client_session(client) as session:
        _device_credential(
            session,
            device_id="gateway-safe",
            token=token,
            capability="gateway.sync",
            organization_id="org-safe",
            branch_id="branch-safe",
        )

    response = client.post(
        "/api/v1/sync/commands",
        headers={"X-Device-Token": token},
        json=_sync_envelope(
            organization_id="org-safe",
            branch_id="missing-or-untrusted",
            device_id="gateway-safe",
            idempotency_key="sync-malformed-key-0001",
        ),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "device_scope_denied"
    with _client_session(client) as session:
        assert session.execute(models.sync_commands.select()).mappings().all() == []
        assert session.execute(models.sync_events.select()).mappings().all() == []
        denial = session.execute(models.audit_events.select()).mappings().one()
        assert denial["branch_id"] == "branch-safe"


def test_tc142_seed_is_not_an_http_surface() -> None:
    client = _client()
    schema = client.get("/openapi.json").json()
    assert "/api/v1/seed_menu" not in schema["paths"]
    assert "/api/v1/seed_branches" not in schema["paths"]


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    return Session(engine)


def test_tc143_device_expiry_revocation_capability_and_scope_leave_zero_effects() -> None:
    session = _session()
    now = datetime.now(timezone.utc)
    token = "device-" + "test-token"
    _operational_scope(session, "org-a", "branch-a")
    session.execute(
        models.device_credentials.insert().values(
            id="device-a",
            organization_id="org-a",
            branch_id="branch-a",
            capability="kds.operate",
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            key_version="v1",
            expires_at=now + timedelta(minutes=5),
            revoked_at=None,
            created_at=now,
        )
    )
    session.commit()
    guard = OperationalRouteGuard()
    assert (
        guard.require_device(session, token, "kds.operate", "org-a", "branch-a").user_id
        == "device-a"
    )
    before_denials = session.execute(models.device_credentials.select()).mappings().all()
    for capability, organization, branch in (
        ("print.agent", "org-a", "branch-a"),
        ("kds.operate", "org-b", "branch-a"),
        ("kds.operate", "org-a", "branch-b"),
    ):
        with pytest.raises(HTTPException):
            guard.require_device(session, token, capability, organization, branch)
    session.execute(
        models.device_credentials.update()
        .where(models.device_credentials.c.id == "device-a")
        .values(revoked_at=now)
    )
    session.commit()
    with pytest.raises(HTTPException):
        guard.require_device(session, token, "kds.operate", "org-a", "branch-a")
    with pytest.raises(HTTPException):
        guard.require_device(session, "invalid-token", "kds.operate", "org-a", "branch-a")
    session.execute(
        models.device_credentials.insert().values(
            id="device-expired",
            organization_id="org-a",
            branch_id="branch-a",
            capability="kds.operate",
            token_hash=hashlib.sha256(b"expired").hexdigest(),
            key_version="v1",
            expires_at=now - timedelta(seconds=1),
            revoked_at=None,
            created_at=now,
        )
    )
    session.commit()
    with pytest.raises(HTTPException):
        guard.require_device(session, "expired", "kds.operate", "org-a", "branch-a")
    after_denials = session.execute(models.device_credentials.select()).mappings().all()
    assert [row["id"] for row in after_denials] == [row["id"] for row in before_denials] + [
        "device-expired"
    ]
    denials = (
        session.execute(
            models.audit_events.select().where(
                models.audit_events.c.action == "operational_route.denied"
            )
        )
        .mappings()
        .all()
    )
    assert denials and all("token" not in json.dumps(row["payload"]).lower() for row in denials)


def test_tc143_device_scope_requires_branch_ownership_and_active_parents() -> None:
    session = _session()
    _operational_scope(session, "org-a", "branch-a")
    _operational_scope(session, "org-b", "branch-b")
    now = datetime.now(timezone.utc)
    mismatched_token = "mismatched-device-token"
    session.execute(
        models.device_credentials.insert().values(
            id="device-mismatched",
            organization_id="org-a",
            branch_id="branch-b",
            capability="kds.operate",
            token_hash=hashlib.sha256(mismatched_token.encode()).hexdigest(),
            key_version="v1",
            expires_at=now + timedelta(minutes=5),
            revoked_at=None,
            created_at=now,
        )
    )
    inactive_token = "inactive-device-token"
    _device_credential(
        session,
        device_id="device-inactive",
        token=inactive_token,
        capability="kds.operate",
        organization_id="org-a",
        branch_id="branch-a",
    )
    inactive_organization_token = "inactive-organization-device-token"
    _device_credential(
        session,
        device_id="device-inactive-organization",
        token=inactive_organization_token,
        capability="kds.operate",
        organization_id="org-c",
        branch_id="branch-c",
    )
    session.execute(
        models.branches.update()
        .where(models.branches.c.id == "branch-a")
        .values(status="inactive")
    )
    session.execute(
        models.organizations.update()
        .where(models.organizations.c.id == "org-c")
        .values(status="inactive")
    )
    session.commit()
    guard = OperationalRouteGuard()

    with pytest.raises(HTTPException) as mismatch:
        guard.require_device_for_capability(session, mismatched_token, "kds.operate")
    with pytest.raises(HTTPException) as inactive:
        guard.require_device_for_capability(session, inactive_token, "kds.operate")
    with pytest.raises(HTTPException) as inactive_organization:
        guard.require_device_for_capability(
            session, inactive_organization_token, "kds.operate"
        )

    assert mismatch.value.detail["code"] == "device_scope_denied"
    assert inactive.value.detail["code"] == "device_scope_denied"
    assert inactive_organization.value.detail["code"] == "device_scope_denied"


def test_tc144_print_attempts_are_idempotent_and_ack_is_the_only_completion() -> None:
    session = _session()
    now = datetime.now(timezone.utc)
    session.execute(
        models.print_jobs.insert().values(
            id="job-a",
            organization_id="org-a",
            branch_id="branch-a",
            order_id="order-a",
            job_type="ticket",
            target="printer",
            status="FAILED",
            payload={},
            attempts=0,
            last_error="offline",
            created_at=now,
            printed_at=None,
        )
    )
    session.commit()
    first = retry_print_job(session, "job-a", "retry-key-0001", "branch-a")
    replay = retry_print_job(session, "job-a", "retry-key-0001", "branch-a")
    assert first["attempt"]["status"] == "QUEUED" and replay["replayed"] is True
    with pytest.raises(BusinessError) as active_attempt:
        retry_print_job(session, "job-a", "retry-key-0002", "branch-a")
    assert active_attempt.value.code == "print_job_transition_invalid"
    claimed = claim_print_attempt(session, first["attempt"]["id"], "device-a")
    assert claimed["status"] == "CLAIMED"
    with pytest.raises(BusinessError):
        acknowledge_print_attempt(session, first["attempt"]["id"], "other-device", "ack")
    acknowledged = acknowledge_print_attempt(session, first["attempt"]["id"], "device-a", "ack")
    assert acknowledged["status"] == "PRINTED"
    assert (
        acknowledge_print_attempt(session, first["attempt"]["id"], "device-a", "ack")["status"]
        == "PRINTED"
    )
    with pytest.raises(BusinessError):
        acknowledge_print_attempt(session, first["attempt"]["id"], "device-a", "altered")
    assert retry_print_job(session, "job-a", "retry-key-0001", "branch-a")["replayed"] is True
    assert session.execute(models.print_jobs.select()).mappings().one()["status"] == "PRINTED"


def test_tc143_print_agent_pull_is_scoped_and_denies_invalid_devices() -> None:
    client = _client()
    now = datetime.now(timezone.utc)
    token = "pull-device-token"
    with _client_session(client) as session:
        _device_credential(
            session,
            device_id="agent-a",
            token=token,
            capability="print.agent",
            organization_id="org-a",
            branch_id="branch-a",
        )
        _device_credential(
            session,
            device_id="agent-b",
            token="other-agent",
            capability="print.agent",
            organization_id="org-b",
            branch_id="branch-b",
        )
        _device_credential(
            session,
            device_id="agent-expired",
            token="expired-agent",
            capability="print.agent",
            organization_id="org-a",
            branch_id="branch-a",
        )
        session.execute(
            models.device_credentials.update()
            .where(models.device_credentials.c.id == "agent-expired")
            .values(expires_at=now - timedelta(seconds=1))
        )
        for job_id, organization_id, branch_id in (("pull-a", "org-a", "branch-a"), ("pull-b", "org-b", "branch-b")):
            session.execute(models.print_jobs.insert().values(id=job_id, organization_id=organization_id, branch_id=branch_id, order_id=job_id, job_type="ticket", target="printer", status="QUEUED", payload={"safe": True}, attempts=1, last_error=None, created_at=now, printed_at=None))
            session.execute(models.print_attempts.insert().values(id=f"attempt-{job_id}", print_job_id=job_id, organization_id=organization_id, branch_id=branch_id, idempotency_key=f"key-{job_id}", request_hash="a" * 64, status="QUEUED", created_at=now))
        session.commit()
    response = client.get("/api/v1/print-attempts/pull", headers={"X-Device-Token": token})
    assert response.status_code == 200
    assert [item["attempt_id"] for item in response.json()] == ["attempt-pull-a"]
    assert client.get("/api/v1/print-attempts/pull", headers={"X-Device-Token": "expired-agent"}).status_code == 403
    with _client_session(client) as session:
        session.execute(models.device_credentials.update().where(models.device_credentials.c.id == "agent-a").values(revoked_at=now))
        session.commit()
    assert client.get("/api/v1/print-attempts/pull", headers={"X-Device-Token": token}).status_code == 403


def test_tc144_agent_failure_is_atomic_replayable_and_allows_next_retry() -> None:
    session = _session()
    now = datetime.now(timezone.utc)
    session.execute(models.print_jobs.insert().values(id="job-fail", organization_id="org-a", branch_id="branch-a", order_id="order-a", job_type="ticket", target="printer", status="FAILED", payload={}, attempts=0, last_error=None, created_at=now, printed_at=None))
    session.commit()
    attempt = retry_print_job(session, "job-fail", "retry-fail-001", "branch-a")["attempt"]
    claim_print_attempt(session, attempt["id"], "device-a")
    with pytest.raises(RuntimeError):
        fail_print_attempt(session, attempt["id"], "device-a", "OFFLINE", fail_after_update=True)
    assert session.execute(models.print_attempts.select()).mappings().one()["status"] == "CLAIMED"
    failed = fail_print_attempt(session, attempt["id"], "device-a", "OFFLINE")
    assert failed["status"] == "FAILED" and failed["error_code"] == "OFFLINE"
    assert fail_print_attempt(session, attempt["id"], "device-a", "OFFLINE")["status"] == "FAILED"
    with pytest.raises(BusinessError):
        fail_print_attempt(session, attempt["id"], "device-b", "OFFLINE")
    next_attempt = retry_print_job(session, "job-fail", "retry-fail-002", "branch-a")
    assert next_attempt["replayed"] is False


def test_tc142_internal_seed_dry_run_apply_and_replay_are_deterministic() -> None:
    session = _session()
    manifest = _governed_seed_manifest()
    assert apply_manifest(session, manifest, apply=False, actor_id="operator")["dry_run"] is True
    assert session.execute(models.organizations.select()).all() == []
    applied = apply_manifest(session, manifest, apply=True, actor_id="operator")
    replay = apply_manifest(session, manifest, apply=True, actor_id="operator")
    assert applied["replayed"] is False and replay["replayed"] is True
    assert session.execute(models.organizations.select()).mappings().one()["id"] == "org-seed"
    assert session.execute(models.legal_entities.select()).mappings().one()["id"] == "legal-seed"
    assert session.execute(models.branches.select()).mappings().one()["id"] == "branch-seed"
    assert session.execute(models.warehouses.select()).mappings().one()["id"] == "warehouse-seed"
    assert session.execute(models.product_categories.select()).mappings().one()["name"] == "Jugos y Extractos"
    assert session.execute(models.inventory_items.select()).mappings().one()["sku"] == "INS-NAR"
    assert session.execute(models.products.select()).mappings().one()["sku"] == "JUG-VER"
    assert session.execute(models.price_versions.select()).mappings().one()["price_cents"] == 6500
    assert session.execute(models.recipes.select()).mappings().one()["id"] == "recipe-green-juice"
    assert len(session.execute(models.recipe_components.select()).mappings().all()) == 1
    with pytest.raises(ValueError):
        invalid = _governed_seed_manifest()
        invalid["operations"][2]["products"][0]["category_id"] = "missing-category"
        apply_manifest(
            session,
            invalid,
            apply=True,
            actor_id="operator",
        )
    assert len(session.execute(models.organizations.select()).mappings().all()) == 1


def test_tc142_seed_validates_order_references_and_exact_numeric_types_before_write() -> None:
    session = _session()
    invalid_manifests = []
    wrong_order = _governed_seed_manifest()
    wrong_order["operations"][1], wrong_order["operations"][2] = (
        wrong_order["operations"][2],
        wrong_order["operations"][1],
    )
    invalid_manifests.append(wrong_order)
    missing_reference = _governed_seed_manifest()
    missing_reference["operations"][2]["products"][0]["recipe"]["components"][0][
        "item_id"
    ] = "missing-item"
    invalid_manifests.append(missing_reference)
    fractional_money = _governed_seed_manifest()
    fractional_money["operations"][2]["products"][0]["price"]["price_cents"] = 65.5
    invalid_manifests.append(fractional_money)

    for manifest in invalid_manifests:
        with pytest.raises(ValueError, match="seed_manifest_invalid"):
            apply_manifest(session, manifest, apply=True, actor_id="operator-sec001")

    assert session.execute(models.organizations.select()).mappings().all() == []
    assert session.execute(models.branches.select()).mappings().all() == []
    assert session.execute(models.products.select()).mappings().all() == []
    assert session.execute(models.audit_events.select()).mappings().all() == []


def test_tc142_legacy_kiwi_manifest_migrates_only_catalog_and_topology() -> None:
    session = _session()
    manifest = kiwi_v1_manifest()
    catalog = manifest["operations"][2]
    assert len(manifest["operations"][1]["branches"]) == 7
    assert len(catalog["categories"]) == 9
    assert len(catalog["units"]) == 4
    assert len(catalog["items"]) == 63
    assert len(catalog["products"]) == 30
    assert all(isinstance(product["price"]["price_cents"], int) for product in catalog["products"])
    assert all(
        isinstance(component["quantity_base_units"], str)
        for product in catalog["products"]
        for component in product["recipe"]["components"]
    )

    first = apply_manifest(session, manifest, apply=True, actor_id="operator-real-seed")
    replay = apply_manifest(session, manifest, apply=True, actor_id="operator-real-seed")
    assert first["replayed"] is False and replay["replayed"] is True
    assert session.scalar(sa.select(sa.func.count()).select_from(models.branches)) == 7
    assert session.scalar(sa.select(sa.func.count()).select_from(models.warehouses)) == 7
    assert session.scalar(sa.select(sa.func.count()).select_from(models.product_categories)) == 9
    assert session.scalar(sa.select(sa.func.count()).select_from(models.inventory_items)) == 63
    assert session.scalar(sa.select(sa.func.count()).select_from(models.products)) == 30
    assert session.scalar(sa.select(sa.func.count()).select_from(models.price_versions)) == 30
    assert session.scalar(sa.select(sa.func.count()).select_from(models.recipes)) == 30
    assert session.scalar(sa.select(sa.func.count()).select_from(models.recipe_components)) == 99
    assert session.execute(models.branches.select().where(models.branches.c.code == "BR-007")).mappings().one()["name"] == "Paseo de la Reforma"
    assert session.execute(models.products.select().where(models.products.c.sku == "COM-PRE")).mappings().one()["name"] == "Combo Premium"
    assert session.execute(models.price_versions.select().where(models.price_versions.c.id == "price-jug-ver")).mappings().one()["price_cents"] == 6500
    assert session.scalar(sa.select(sa.func.count()).select_from(models.cash_shifts)) == 0
    assert session.scalar(sa.select(sa.func.count()).select_from(models.orders)) == 0
    assert session.scalar(sa.select(sa.func.count()).select_from(models.order_lines)) == 0
    assert session.scalar(sa.select(sa.func.count()).select_from(models.payments)) == 0

    rollback_session = _session()
    with pytest.raises(RuntimeError, match="real_seed_rollback"):
        apply_manifest(
            rollback_session,
            manifest,
            apply=True,
            actor_id="operator-real-seed",
            _failure_hook=lambda: (_ for _ in ()).throw(RuntimeError("real_seed_rollback")),
        )
    assert rollback_session.scalar(sa.select(sa.func.count()).select_from(models.branches)) == 0
    assert rollback_session.scalar(sa.select(sa.func.count()).select_from(models.products)) == 0


def test_tc142_seed_audit_is_organization_level_and_failure_rolls_back() -> None:
    session = _session()
    manifest = _governed_seed_manifest("org-seed-audit")
    with pytest.raises(RuntimeError, match="injected_seed_failure"):
        apply_manifest(
            session,
            manifest,
            apply=True,
            actor_id="operator-sec001",
            _failure_hook=lambda: (_ for _ in ()).throw(RuntimeError("injected_seed_failure")),
        )
    assert session.execute(models.organizations.select()).mappings().all() == []
    assert session.execute(models.branches.select()).mappings().all() == []
    assert session.execute(models.products.select()).mappings().all() == []
    assert session.execute(models.audit_events.select()).mappings().all() == []

    apply_manifest(session, manifest, apply=True, actor_id="operator-sec001")
    audit = session.execute(models.audit_events.select()).mappings().one()
    assert audit["organization_id"] == "org-seed-audit"
    assert audit["branch_id"] is None
    assert audit["actor_user_id"] is None
    assert len(audit["entity_id"]) == 36
    assert audit["payload"]["operator_id"] == "operator-sec001"
    assert audit["payload"]["operation_types"] == [
        "ensure_organization.v1",
        "ensure_branch_topology.v1",
        "ensure_menu_catalog.v1",
    ]
    assert "Jugo Verde" not in json.dumps(audit["payload"])


def test_tc142_legacy_seed_entrypoints_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import seed_branches
    import seed_menu

    def unsafe_engine_access() -> None:
        raise AssertionError("legacy seed attempted database access")

    monkeypatch.setattr(seed_menu, "get_engine", unsafe_engine_access)
    monkeypatch.setattr(seed_branches, "get_engine", unsafe_engine_access)
    with pytest.raises(RuntimeError, match="internal_seed_required"):
        seed_menu.seed()
    with pytest.raises(RuntimeError, match="internal_seed_required"):
        seed_branches.seed()


def test_tc144_claim_race_and_injected_ack_failure_leave_no_partial_state() -> None:
    session = _session()
    now = datetime.now(timezone.utc)
    session.execute(
        models.print_jobs.insert().values(
            id="job-race",
            organization_id="org-a",
            branch_id="branch-a",
            order_id="order-a",
            job_type="ticket",
            target="printer",
            status="FAILED",
            payload={},
            attempts=0,
            last_error=None,
            created_at=now,
            printed_at=None,
        )
    )
    session.commit()
    attempt = retry_print_job(session, "job-race", "retry-race-0001", "branch-a")["attempt"]
    with pytest.raises(RuntimeError):
        claim_print_attempt(session, attempt["id"], "device-a", fail_after_update=True)
    assert session.execute(models.print_attempts.select()).mappings().one()["status"] == "QUEUED"
    claimed = claim_print_attempt(session, attempt["id"], "device-a")
    with pytest.raises(BusinessError):
        claim_print_attempt(session, attempt["id"], "device-b")
    with pytest.raises(RuntimeError):
        acknowledge_print_attempt(session, claimed["id"], "device-a", "ack", fail_after_update=True)
    assert session.execute(models.print_attempts.select()).mappings().one()["status"] == "CLAIMED"
    assert session.execute(models.print_jobs.select()).mappings().one()["status"] == "CLAIMED"


def test_tc144_claim_race_uses_two_connections_and_one_winner(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'claim-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    models.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as setup:
        now = datetime.now(timezone.utc)
        setup.execute(
            models.print_jobs.insert().values(
                id="job-concurrent",
                organization_id="org-a",
                branch_id="branch-a",
                order_id="order-a",
                job_type="ticket",
                target="printer",
                status="FAILED",
                payload={},
                attempts=0,
                last_error=None,
                created_at=now,
                printed_at=None,
            )
        )
        setup.commit()
        attempt_id = retry_print_job(setup, "job-concurrent", "retry-concurrent-1", "branch-a")[
            "attempt"
        ]["id"]
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def contender(device_id: str) -> None:
        with factory() as concurrent_session:
            barrier.wait(timeout=5)
            try:
                claim_print_attempt(concurrent_session, attempt_id, device_id)
                outcomes.append("claimed")
            except (BusinessError, OperationalError):
                outcomes.append("denied")

    threads = [
        threading.Thread(target=contender, args=(device_id,))
        for device_id in ("device-a", "device-b")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    with factory() as verify:
        attempt = verify.execute(models.print_attempts.select()).mappings().one()
        job = verify.execute(models.print_jobs.select()).mappings().one()
    assert sorted(outcomes) == ["claimed", "denied"]
    assert attempt["status"] == job["status"] == "CLAIMED"
    assert attempt["claimed_by_device_id"] in {"device-a", "device-b"}


def test_tc144_audit_records_actor_without_ack_material() -> None:
    session = _session()
    now = datetime.now(timezone.utc)
    session.execute(
        models.print_jobs.insert().values(
            id="job-audit",
            organization_id="org-a",
            branch_id="branch-a",
            order_id="order-a",
            job_type="ticket",
            target="printer",
            status="FAILED",
            payload={},
            attempts=0,
            last_error=None,
            created_at=now,
            printed_at=None,
        )
    )
    session.commit()
    attempt = retry_print_job(
        session, "job-audit", "retry-audit-001", "branch-a", actor_user_id="human-a"
    )["attempt"]
    claim_print_attempt(session, attempt["id"], "device-a")
    acknowledge_print_attempt(session, attempt["id"], "device-a", "ack-material-must-not-appear")
    events = session.execute(models.audit_events.select()).mappings().all()
    by_action = {event["action"]: event for event in events}
    assert by_action["print_job.retried"]["actor_user_id"] == "human-a"
    assert by_action["print_attempt.claimed"]["payload"]["device_id"] == "device-a"
    assert by_action["print_attempt.acknowledged"]["payload"]["device_id"] == "device-a"
    assert "ack-material-must-not-appear" not in json.dumps([event["payload"] for event in events])


def test_tc144_database_rejects_incoherent_print_attempt_state() -> None:
    session = _session()
    now = datetime.now(timezone.utc)
    session.execute(
        models.print_jobs.insert().values(
            id="job-invariant", organization_id="org-a", branch_id="branch-a", order_id="order-a",
            job_type="ticket", target="printer", status="FAILED", payload={}, attempts=0,
            last_error=None, created_at=now, printed_at=None,
        )
    )
    session.commit()
    with pytest.raises(IntegrityError):
        session.execute(
            models.print_attempts.insert().values(
                id="attempt-invariant", print_job_id="job-invariant", organization_id="org-a",
                branch_id="branch-a", idempotency_key="invariant-key-001", request_hash="a" * 64,
                status="QUEUED", claimed_by_device_id="device-a", claimed_at=now, ack_hash=None,
                created_at=now, acked_at=None,
            )
        )
        session.commit()
        session.rollback()


def test_tc144_new_print_jobs_have_initial_pullable_attempts() -> None:
    session = _session()
    now = datetime.now(timezone.utc)
    jobs = operational_services._create_print_jobs(
        session,
        {
            "id": "order-initial-print",
            "organization_id": "org-a",
            "branch_id": "branch-a",
            "folio": "SEC001-INITIAL",
            "total_cents": 1250,
        },
        {"id": "payment-initial-print"},
        now,
    )

    attempts = session.execute(models.print_attempts.select()).mappings().all()

    assert {job["status"] for job in jobs} == {"QUEUED"}
    assert {job["attempts"] for job in jobs} == {1}
    assert len(attempts) == len(jobs) == 2
    assert {attempt["print_job_id"] for attempt in attempts} == {job["id"] for job in jobs}


def test_tc144_concurrent_retries_create_one_active_attempt(
    tmp_path: Path,
) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'retry-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    models.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as setup:
        setup.execute(
            models.print_jobs.insert().values(
                id="job-retry-race",
                organization_id="org-a",
                branch_id="branch-a",
                order_id="order-a",
                job_type="ticket",
                target="printer",
                status="FAILED",
                payload={},
                attempts=1,
                last_error="OFFLINE",
                created_at=now,
                printed_at=None,
            )
        )
        setup.commit()
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def retry(key: str) -> None:
        with Session(engine) as concurrent_session:
            try:
                retry_print_job(
                    concurrent_session,
                    "job-retry-race",
                    key,
                    "branch-a",
                    _before_transition=lambda: barrier.wait(timeout=10),
                )
                outcomes.append("queued")
            except BusinessError as exc:
                outcomes.append(exc.code)

    workers = [
        threading.Thread(target=retry, args=(key,))
        for key in ("retry-race-key-0001", "retry-race-key-0002")
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=15)

    with Session(engine) as verify:
        job = verify.execute(models.print_jobs.select()).mappings().one()
        attempts = verify.execute(models.print_attempts.select()).mappings().all()
    assert outcomes.count("queued") == 1
    assert outcomes.count("print_job_transition_invalid") == 1
    assert job["status"] == "QUEUED" and job["attempts"] == 2
    assert len(attempts) == 1 and attempts[0]["status"] == "QUEUED"


def test_tc144_expired_claim_requires_explicit_scoped_recovery() -> None:
    session = _session()
    now = datetime.now(timezone.utc)
    session.execute(
        models.print_jobs.insert().values(
            id="job-expired-claim",
            organization_id="org-a",
            branch_id="branch-a",
            order_id="order-a",
            job_type="ticket",
            target="printer",
            status="CLAIMED",
            payload={},
            attempts=1,
            last_error=None,
            created_at=now - timedelta(minutes=10),
            printed_at=None,
        )
    )
    session.execute(
        models.print_attempts.insert().values(
            id="attempt-expired-claim",
            print_job_id="job-expired-claim",
            organization_id="org-a",
            branch_id="branch-a",
            idempotency_key="initial-attempt-expired",
            request_hash="a" * 64,
            status="CLAIMED",
            claimed_by_device_id="agent-dead",
            claimed_at=now - timedelta(minutes=10),
            created_at=now - timedelta(minutes=10),
        )
    )
    session.commit()

    with pytest.raises(BusinessError) as scope_error:
        operational_services.recover_expired_print_claim(
            session,
            "attempt-expired-claim",
            "org-a",
            "branch-b",
            now=now,
        )
    recovered = operational_services.recover_expired_print_claim(
        session,
        "attempt-expired-claim",
        "org-a",
        "branch-a",
        now=now,
    )

    assert scope_error.value.code == "device_scope_denied"
    assert recovered["status"] == "FAILED"
    assert recovered["error_code"] == "CLAIM_LEASE_EXPIRED"
    assert session.execute(models.print_attempts.select()).mappings().all() == [recovered]
    job = session.execute(models.print_jobs.select()).mappings().one()
    assert job["status"] == "FAILED" and job["attempts"] == 1


def test_tc144_expired_claim_http_recovery_is_device_scoped() -> None:
    client = _client()
    now = datetime.now(timezone.utc)
    with _client_session(client) as session:
        _device_credential(
            session,
            device_id="recovery-agent-a",
            token="recovery-agent-a-token",
            capability="print.agent",
            organization_id="org-a",
            branch_id="branch-a",
        )
        _device_credential(
            session,
            device_id="recovery-agent-b",
            token="recovery-agent-b-token",
            capability="print.agent",
            organization_id="org-a",
            branch_id="branch-b",
        )
        session.execute(
            models.print_jobs.insert().values(
                id="job-http-recovery",
                organization_id="org-a",
                branch_id="branch-a",
                order_id="order-http-recovery",
                job_type="ticket",
                target="printer",
                status="CLAIMED",
                payload={},
                attempts=1,
                last_error=None,
                created_at=now - timedelta(minutes=10),
                printed_at=None,
            )
        )
        session.execute(
            models.print_attempts.insert().values(
                id="attempt-http-recovery",
                print_job_id="job-http-recovery",
                organization_id="org-a",
                branch_id="branch-a",
                idempotency_key="initial-http-recovery",
                request_hash="a" * 64,
                status="CLAIMED",
                claimed_by_device_id="dead-agent",
                claimed_at=now - timedelta(minutes=10),
                created_at=now - timedelta(minutes=10),
            )
        )
        session.commit()

    denied = client.post(
        "/api/v1/print-attempts/attempt-http-recovery/recover-expired-claim",
        headers={"X-Device-Token": "recovery-agent-b-token"},
    )
    recovered = client.post(
        "/api/v1/print-attempts/attempt-http-recovery/recover-expired-claim",
        headers={"X-Device-Token": "recovery-agent-a-token"},
    )

    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "device_scope_denied"
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "FAILED"


def test_tc143_kds_audit_retains_human_or_device_actor_without_credential_material() -> None:
    session = _session()
    now = datetime.now(timezone.utc)
    _operational_scope(session, "org-a", "branch-a")
    session.execute(
        models.cash_shifts.insert().values(
            id="shift-audit",
            organization_id="org-a",
            branch_id="branch-a",
            register_code="CAJA-AUDIT",
            status="OPEN",
            opening_cash_cents=0,
            cashier_user_id=None,
            opened_at=now,
            closed_at=None,
            created_at=now,
        )
    )
    session.execute(
        models.orders.insert().values(
            id="order-a",
            organization_id="org-a",
            branch_id="branch-a",
            cash_shift_id="shift-audit",
            customer_id=None,
            customer_snapshot=None,
            delivery_address_snapshot=None,
            folio="AUDIT-1",
            channel="pos",
            status="ACCEPTED",
            total_cents=0,
            currency="MXN",
            owner_name=None,
            order_type="dine-in",
            payment_method_intent=None,
            version=1,
            created_at=now,
            accepted_at=now,
        )
    )
    session.execute(
        models.production_tasks.insert().values(
            id="task-audit",
            organization_id="org-a",
            branch_id="branch-a",
            order_id="order-a",
            order_line_id="line-a",
            station="hot",
            status="PENDING",
            product_name="Synthetic",
            quantity=1,
            created_at=now,
            started_at=None,
            completed_at=None,
        )
    )
    session.commit()
    advance_kds_task(session, "task-audit", "IN_PROGRESS", "branch-a", actor_user_id="human-a")
    event = (
        session.execute(
            models.audit_events.select().where(
                models.audit_events.c.action == "production_task.transitioned"
            )
        )
        .mappings()
        .one()
    )
    assert event["actor_user_id"] == "human-a"
    assert "token" not in json.dumps(event["payload"]).lower()


def test_tc142_cli_uses_explicit_sqlite_url_and_replays(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_governed_seed_manifest("org-cli")))
    database_url = f"sqlite:///{tmp_path / 'seed.db'}"
    engine = create_engine(database_url)
    models.metadata.create_all(engine)
    engine.dispose()
    command = [
        sys.executable,
        "-m",
        "restaurant_os.internal_seed",
        str(manifest),
        "--apply",
        "--actor",
        "operator",
        "--confirm-environment",
        "test",
        "--sqlite-url",
        database_url,
    ]
    first = subprocess.run(command, cwd=Path(__file__).parents[1], text=True, capture_output=True)
    second = subprocess.run(command, cwd=Path(__file__).parents[1], text=True, capture_output=True)
    assert first.returncode == second.returncode == 0
    assert json.loads(first.stdout)["replayed"] is False
    assert json.loads(second.stdout)["replayed"] is True
    verification_engine = create_engine(database_url)
    with Session(verification_engine) as verification_session:
        assert verification_session.execute(models.branches.select()).mappings().one()["id"] == (
            "branch-seed"
        )
        assert verification_session.execute(models.products.select()).mappings().one()["sku"] == (
            "JUG-VER"
        )
    verification_engine.dispose()


def test_tc142_cli_dry_run_refuses_unmigrated_sqlite_without_ddl(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest-unmigrated.json"
    manifest.write_text(
        json.dumps(
            {
                "organization_id": "org-unmigrated",
                "environment": "test",
                "operations": [
                    {
                        "type": "ensure_organization.v1",
                        "id": "org-unmigrated",
                        "name": "Synthetic",
                    }
                ],
            }
        )
    )
    database_path = tmp_path / "unmigrated.db"
    command = [
        sys.executable,
        "-m",
        "restaurant_os.internal_seed",
        str(manifest),
        "--actor",
        "operator",
        "--confirm-environment",
        "test",
        "--sqlite-url",
        f"sqlite:///{database_path}",
    ]

    result = subprocess.run(
        command, cwd=Path(__file__).parents[1], text=True, capture_output=True
    )

    assert result.returncode != 0
    engine = create_engine(f"sqlite:///{database_path}")
    assert sa.inspect(engine).get_table_names() == []
    engine.dispose()


def test_tc142_cli_dry_run_preserves_migrated_sqlite_bytes(tmp_path: Path) -> None:
    database_path = tmp_path / "dry-run-stable.db"
    database_url = f"sqlite:///{database_path}"
    engine = create_engine(database_url)
    models.metadata.create_all(engine)
    engine.dispose()
    manifest = tmp_path / "manifest-dry-run.json"
    manifest.write_text(json.dumps(_governed_seed_manifest("org-dry-run")))
    before = hashlib.sha256(database_path.read_bytes()).hexdigest()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "restaurant_os.internal_seed",
            str(manifest),
            "--actor",
            "operator",
            "--confirm-environment",
            "test",
            "--sqlite-url",
            database_url,
        ],
        cwd=Path(__file__).parents[1],
        text=True,
        capture_output=True,
    )

    after = hashlib.sha256(database_path.read_bytes()).hexdigest()
    assert result.returncode == 0
    assert json.loads(result.stdout)["dry_run"] is True
    assert before == after
