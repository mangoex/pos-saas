# SEC001-SYNTHETIC-FIXTURE provenance=restaurantos-saas-test-saas-cash-scope-synthetic-v1
from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import app
from restaurant_os.operations import (
    AuthorizationError,
    BusinessError,
    ReportingProjectionService,
    UserCashCutService,
    close_cash_shift_operationally,
    compensate_cash_movement,
    create_cash_concept,
    create_cash_concept_version,
    create_cash_movement,
    create_local_order,
    list_cash_concepts,
    list_cash_movement_ledger,
    list_order_accounts,
    open_cash_shift,
    pay_order,
)
from restaurant_os.saas_onboarding import signup_tenant
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

API_DIR = Path(__file__).resolve().parents[1]


def _cash_scope_api_client() -> tuple[TestClient, sessionmaker[Session]]:
    engine = sa.create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_session() -> Generator[Session, None, None]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app), factory


@pytest.fixture(params=["sqlite", "postgres"], ids=["sqlite", "postgres"])
def cash_scope_session(request: pytest.FixtureRequest) -> Session:
    if request.param == "sqlite":
        engine = sa.create_engine(
            "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        models.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()
        return

    postgres_url = os.environ.get("SAAS_TEST_POSTGRES_URL")
    if not postgres_url:
        pytest.skip("SAAS_TEST_POSTGRES_URL is not configured")
    schema = f"saas_cash_scope_{uuid4().hex}"
    admin_engine = sa.create_engine(postgres_url)
    with admin_engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    schema_url = str(
        sa.engine.make_url(postgres_url).set(query={"options": f"-csearch_path={schema}"})
    )
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=API_DIR,
        env={**os.environ, "RESTAURANTOS_DATABASE_URL": schema_url},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert migration.returncode == 0, migration.stdout + migration.stderr
    engine = sa.create_engine(schema_url)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


def test_cash_shift_and_order_scope_to_branch_tenant_and_reject_cross_actor(
    cash_scope_session: Session,
) -> None:
    with cash_scope_session as session:
        tenant_a = signup_tenant(session, {
            "business_name": "Caja A", "owner_name": "Owner A", "email": "owner-a@example.test",
            "password": "test-only-owner-a-password", "business_type": "taqueria",
        })
        tenant_b = signup_tenant(session, {
            "business_name": "Caja B", "owner_name": "Owner B", "email": "owner-b@example.test",
            "password": "test-only-owner-b-password", "business_type": "taqueria",
        })
        org_a = tenant_a["organization"]["id"]
        branch_a = tenant_a["branch"]["id"]
        owner_a = tenant_a["user"]["id"]
        branch_b = tenant_b["branch"]["id"]
        org_b = tenant_b["organization"]["id"]
        owner_b = tenant_b["user"]["id"]
        _grant_cash_concept_management(session, owner_a)
        _grant_cash_concept_management(session, owner_b)
        product_a = session.scalar(
            sa.select(models.products.c.id).where(models.products.c.organization_id == org_a)
        )
        assert product_a

        shift = open_cash_shift(session, 0, branch_id=branch_a, actor_user_id=owner_a)
        assert shift["organization_id"] == org_a

        order = create_local_order(
            session,
            [{"product_id": product_a, "quantity": 1}],
            branch_id=branch_a,
            actor_user_id=owner_a,
        )
        assert order["organization_id"] == org_a
        assert session.scalar(
            sa.select(models.production_tasks.c.organization_id).where(
                models.production_tasks.c.order_id == order["id"]
            )
        ) == org_a
        accounts = list_order_accounts(session, {"branch_id": branch_a}, owner_a)
        assert [item["id"] for item in accounts["items"]] == [order["id"]]
        organization_accounts = list_order_accounts(session, {}, owner_a)
        assert [item["id"] for item in organization_accounts["items"]] == [order["id"]]
        assert list_order_accounts(session, {}, owner_b)["items"] == []
        payment = pay_order(
            session,
            order["id"],
            order["total_cents"],
            actor_user_id=owner_a,
            register_id="CAJA-01",
            idempotency_key="payment-owner-a",
        )
        assert payment["organization_id"] == org_a

        before = session.scalar(sa.select(sa.func.count()).select_from(models.cash_shifts))
        with pytest.raises(AuthorizationError):
            open_cash_shift(
                session, 0, register_code="CAJA-B", branch_id=branch_a, actor_user_id=owner_b
            )
        assert session.scalar(sa.select(sa.func.count()).select_from(models.cash_shifts)) == before

        with pytest.raises(AuthorizationError):
            close_cash_shift_operationally(session, shift["id"], "close-cross-tenant", owner_b)
        assert session.scalar(
            sa.select(models.cash_shifts.c.status).where(models.cash_shifts.c.id == shift["id"])
        ) == "OPEN"

        closed = close_cash_shift_operationally(session, shift["id"], "close-owner-a", owner_a)
        assert closed["cash_shift"]["organization_id"] == org_a
        assert closed["closure"]["organization_id"] == org_a
        replay = close_cash_shift_operationally(session, shift["id"], "close-owner-a", owner_a)
        assert replay["closure"]["id"] == closed["closure"]["id"]
        cut = UserCashCutService(session).create(
            {
                "branch_id": branch_a,
                "register_id": "CAJA-01",
                "cash_shift_id": shift["id"],
                "cashier_user_id": owner_a,
                "period_start": shift["opened_at"].isoformat(),
                "period_end": closed["closure"]["closed_at"].isoformat(),
            },
            "cut-a",
            owner_a,
        )
        assert cut["cash_cut"]["organization_id"] == org_a
        with pytest.raises(BusinessError) as foreign_cut:
            UserCashCutService(session).detail(cut["cash_cut"]["id"], owner_b)
        assert foreign_cut.value.code == "cash_cut_scope_invalid"

        shift_b = open_cash_shift(session, 0, branch_id=branch_b, actor_user_id=owner_b)
        closed_b = close_cash_shift_operationally(session, shift_b["id"], "close-owner-b", owner_b)
        cut_b = UserCashCutService(session).create(
            {
                "branch_id": branch_b,
                "register_id": "CAJA-01",
                "cash_shift_id": shift_b["id"],
                "cashier_user_id": owner_b,
                "period_start": shift_b["opened_at"].isoformat(),
                "period_end": closed_b["closure"]["closed_at"].isoformat(),
            },
            "cut-a",
            owner_b,
        )
        assert cut_b["cash_cut"]["organization_id"] == org_b
        assert session.scalar(
            sa.select(sa.func.count()).select_from(models.user_cash_cut_commands).where(
                models.user_cash_cut_commands.c.idempotency_key == "cut-a"
            )
        ) == 2

        counted = UserCashCutService(session).counted_cash(
            cut["cash_cut"]["id"],
            {"counted_cash_cents": 0, "version": 1},
            "cut-a-count",
            owner_a,
        )["cash_cut"]
        UserCashCutService(session).finalize(
            counted["id"], {"version": 2}, "cut-a-finalize", owner_a
        )
        reopen = UserCashCutService(session).request_reopen(
            cut["cash_cut"]["id"],
            {"counted_cash_cents": 0, "reason": "Conteo corregido", "evidence_refs": ["test"]},
            "cut-a-reopen",
            owner_a,
        )["reopen_request"]
        commands_before = session.scalar(
            sa.select(sa.func.count()).select_from(models.user_cash_cut_commands).where(
                models.user_cash_cut_commands.c.organization_id == org_b
            )
        )
        with pytest.raises(BusinessError) as foreign_decision:
            UserCashCutService(session).decide_reopen(
                reopen["id"], "APPROVED", "cut-a-decision", owner_b
            )
        assert foreign_decision.value.code == "cash_cut_scope_invalid"
        assert session.scalar(
            sa.select(models.user_cash_cut_reopen_requests.c.status).where(
                models.user_cash_cut_reopen_requests.c.id == reopen["id"]
            )
        ) == "REQUESTED"
        assert session.scalar(
            sa.select(sa.func.count()).select_from(models.user_cash_cut_commands).where(
                models.user_cash_cut_commands.c.organization_id == org_b
            )
        ) == commands_before


def test_reporting_expenses_uses_actor_tenant_not_pilot_organization(
    cash_scope_session: Session,
) -> None:
    with cash_scope_session as session:
        tenant_a = signup_tenant(session, {
            "business_name": "Reportes A", "owner_name": "Owner A",
            "email": "reports-a@example.test", "password": "test-only-reports-a",
            "business_type": "taqueria",
        })
        tenant_b = signup_tenant(session, {
            "business_name": "Reportes B", "owner_name": "Owner B",
            "email": "reports-b@example.test", "password": "test-only-reports-b",
            "business_type": "taqueria",
        })
        org_a, branch_a, owner_a = (
            tenant_a["organization"]["id"], tenant_a["branch"]["id"], tenant_a["user"]["id"]
        )
        org_b, branch_b, owner_b = (
            tenant_b["organization"]["id"], tenant_b["branch"]["id"], tenant_b["user"]["id"]
        )
        _grant_cash_concept_management(session, owner_a)
        _grant_cash_concept_management(session, owner_b)
        shift_a = open_cash_shift(session, 0, branch_id=branch_a, actor_user_id=owner_a)
        shift_b = open_cash_shift(session, 0, branch_id=branch_b, actor_user_id=owner_b)
        now = datetime.now(timezone.utc)
        for organization_id, branch_id, shift_id, owner_id, movement_id, amount in (
            (org_a, branch_a, shift_a["id"], owner_a, "report-expense-a", 111),
            (org_b, branch_b, shift_b["id"], owner_b, "report-expense-b", 222),
        ):
            session.execute(models.cash_movements.insert().values(
                id=movement_id,
                organization_id=organization_id,
                branch_id=branch_id,
                cash_shift_id=shift_id,
                movement_type="withdrawal",
                amount_cents=amount,
                reason_code="TEST",
                reason="Synthetic report expense",
                source_type="manual",
                source_id=None,
                actor_user_id=owner_id,
                idempotency_key=f"{movement_id}-key",
                status="confirmed",
                reversal_of_id=None,
                concept_id=None,
                concept_version_id=None,
                concept_snapshot=None,
                reference=None,
                evidence_refs=None,
                compensates_movement_id=None,
                created_at=now,
            ))
        session.commit()
        period_start = now.replace(microsecond=0)
        period = {
            "from_utc": period_start,
            "to_utc": period_start + timedelta(days=1),
            "branch_id": branch_a,
        }
        result_a = ReportingProjectionService(session, owner_a).expenses(period)
        result_b = ReportingProjectionService(session, owner_b).expenses(
            {**period, "branch_id": branch_b}
        )
        assert [item["id"] for item in result_a["items"]] == ["cash:report-expense-a"]
        assert [item["id"] for item in result_b["items"]] == ["cash:report-expense-b"]


def _grant_cash_concept_management(session: Session, user_id: str) -> None:
    role_id = session.scalar(
        sa.select(models.user_roles.c.role_id).where(models.user_roles.c.user_id == user_id)
    )
    assert role_id
    for code in (
        "cash.concept.manage",
        "cash.concept.read",
        "cash.movement.deposit",
        "cash.movement.withdraw",
        "cash.movement.read",
        "cash.user_cut.create",
        "cash.user_cut.read",
        "cash.user_cut.reopen.request",
        "cash.user_cut.reopen.authorize",
        "reports.expenses.read",
    ):
        permission_id = session.scalar(
            sa.select(models.permissions.c.id).where(models.permissions.c.code == code)
        )
        if not permission_id:
            permission_id = str(uuid4())
            session.execute(
                models.permissions.insert().values(
                    id=permission_id,
                    code=code,
                    description=f"Synthetic {code}",
                    created_at=datetime.now(timezone.utc),
                )
            )
        exists = session.scalar(
            sa.select(models.role_permissions.c.role_id).where(
                models.role_permissions.c.role_id == role_id,
                models.role_permissions.c.permission_id == permission_id,
            )
        )
        if not exists:
            session.execute(
                models.role_permissions.insert().values(
                    role_id=role_id, permission_id=permission_id
                )
            )
    session.commit()


def test_cash_concepts_are_isolated_by_actor_tenant_and_idempotency(
    cash_scope_session: Session,
) -> None:
    with cash_scope_session as session:
        tenant_a = signup_tenant(session, {
            "business_name": "Conceptos A", "owner_name": "Owner A",
            "email": "concepts-a@example.test", "password": "test-only-concepts-a",
            "business_type": "taqueria",
        })
        tenant_b = signup_tenant(session, {
            "business_name": "Conceptos B", "owner_name": "Owner B",
            "email": "concepts-b@example.test", "password": "test-only-concepts-b",
            "business_type": "taqueria",
        })
        owner_a, owner_b = tenant_a["user"]["id"], tenant_b["user"]["id"]
        _grant_cash_concept_management(session, owner_a)
        _grant_cash_concept_management(session, owner_b)
        payload = {
            "code": "RETIRO_CAJA",
            "name": "Retiro de caja",
            "allowed_movement_type": "withdrawal",
            "requires_reference": True,
            "requires_evidence": True,
            "valid_from": "2026-09-04T00:00:00Z",
        }

        concept_a = create_cash_concept(session, payload, "same-concept-key", owner_a)
        concept_b = create_cash_concept(session, payload, "same-concept-key", owner_b)
        assert concept_a["id"] != concept_b["id"]
        assert [item["id"] for item in list_cash_concepts(session, owner_a)] == [concept_a["id"]]
        assert [item["id"] for item in list_cash_concepts(session, owner_b)] == [concept_b["id"]]

        before_versions = session.scalar(
            sa.select(sa.func.count()).select_from(models.cash_movement_concept_versions)
        )
        with pytest.raises(BusinessError) as cross_tenant:
            create_cash_concept_version(
                session,
                concept_a["id"],
                {
                    "name": "Intento cruzado",
                    "allowed_movement_type": "withdrawal",
                    "requires_reference": True,
                    "requires_evidence": True,
                    "valid_from": "2026-09-05T00:00:00Z",
                },
                "cross-tenant-version",
                owner_b,
            )
        assert cross_tenant.value.code == "cash_concept_not_found"
        assert session.scalar(
            sa.select(sa.func.count()).select_from(models.cash_movement_concept_versions)
        ) == before_versions


def test_cash_movements_scope_concepts_commands_and_ledger_by_tenant(
    cash_scope_session: Session,
) -> None:
    with cash_scope_session as session:
        tenant_a = signup_tenant(session, {
            "business_name": "Movimientos A", "owner_name": "Owner A",
            "email": "movements-a@example.test", "password": "test-only-movements-a",
            "business_type": "taqueria",
        })
        tenant_b = signup_tenant(session, {
            "business_name": "Movimientos B", "owner_name": "Owner B",
            "email": "movements-b@example.test", "password": "test-only-movements-b",
            "business_type": "taqueria",
        })
        owner_a, owner_b = tenant_a["user"]["id"], tenant_b["user"]["id"]
        branch_a, branch_b = tenant_a["branch"]["id"], tenant_b["branch"]["id"]
        _grant_cash_concept_management(session, owner_a)
        _grant_cash_concept_management(session, owner_b)
        concept_payload = {
            "code": "RETIRO_MOVIMIENTO",
            "name": "Retiro operativo",
            "allowed_movement_type": "withdrawal",
            "requires_reference": True,
            "requires_evidence": True,
            "valid_from": "2026-09-04T00:00:00Z",
        }
        concept_a = create_cash_concept(session, concept_payload, "concept-a", owner_a)
        concept_b = create_cash_concept(session, concept_payload, "concept-b", owner_b)
        open_cash_shift(session, 0, branch_id=branch_a, actor_user_id=owner_a)
        open_cash_shift(session, 0, branch_id=branch_b, actor_user_id=owner_b)
        foreign_payload = {
            "branch_id": branch_a, "register_id": "CAJA-01", "movement_type": "withdrawal",
            "concept_id": concept_b["id"], "amount_cents": 100, "reference": "A intenta B",
            "evidence_refs": ["synthetic-evidence-a"],
        }
        with pytest.raises(BusinessError) as foreign_concept:
            create_cash_movement(session, foreign_payload, "foreign-concept", owner_a)
        assert foreign_concept.value.code == "cash_concept_invalid"
        assert session.scalar(
            sa.select(sa.func.count()).select_from(models.cash_movement_commands)
        ) == 0

        movement_a = create_cash_movement(
            session,
            {**foreign_payload, "concept_id": concept_a["id"]},
            "same-movement-key",
            owner_a,
        )
        movement_b = create_cash_movement(
            session,
            {
                **foreign_payload,
                "branch_id": branch_b,
                "concept_id": concept_b["id"],
                "reference": "B retiro propio",
            },
            "same-movement-key",
            owner_b,
        )
        assert movement_a["movement"]["organization_id"] == tenant_a["organization"]["id"]
        assert movement_b["movement"]["organization_id"] == tenant_b["organization"]["id"]
        assert session.scalar(
            sa.select(sa.func.count()).select_from(models.cash_movement_commands)
        ) == 2
        with pytest.raises(BusinessError) as foreign_compensation:
            compensate_cash_movement(
                session,
                movement_a["movement"]["id"],
                {"reason": "B intenta compensar A", "evidence_refs": ["synthetic-evidence-b"]},
                "foreign-compensation",
                owner_b,
            )
        assert foreign_compensation.value.code == "cash_movement_not_found"
        assert session.scalar(
            sa.select(sa.func.count()).select_from(models.cash_movement_commands)
        ) == 2
        ledger_a = list_cash_movement_ledger(
            session, owner_a, branch_a, None, None, None, None, None, 50, None
        )
        assert [item["id"] for item in ledger_a["items"]] == [movement_a["movement"]["id"]]


def test_reporting_expenses_api_returns_only_authenticated_tenant_money() -> None:
    client, factory = _cash_scope_api_client()
    try:
        with factory() as session:
            tenant_a = signup_tenant(session, {
                "business_name": "HTTP Reportes A", "owner_name": "Owner A",
                "email": "http-reports-a@example.test", "password": "test-only-http-reports-a",
                "business_type": "taqueria",
            })
            tenant_b = signup_tenant(session, {
                "business_name": "HTTP Reportes B", "owner_name": "Owner B",
                "email": "http-reports-b@example.test", "password": "test-only-http-reports-b",
                "business_type": "taqueria",
            })
            owner_a, owner_b = tenant_a["user"]["id"], tenant_b["user"]["id"]
            _grant_cash_concept_management(session, owner_a)
            _grant_cash_concept_management(session, owner_b)
            branch_a, branch_b = tenant_a["branch"]["id"], tenant_b["branch"]["id"]
            shift_a = open_cash_shift(session, 0, branch_id=branch_a, actor_user_id=owner_a)
            shift_b = open_cash_shift(session, 0, branch_id=branch_b, actor_user_id=owner_b)
            now = datetime.now(timezone.utc)
            for tenant, branch_id, shift, owner, movement_id, amount in (
                (tenant_a, branch_a, shift_a, owner_a, "http-report-expense-a", 101),
                (tenant_b, branch_b, shift_b, owner_b, "http-report-expense-b", 202),
            ):
                session.execute(models.cash_movements.insert().values(
                    id=movement_id,
                    organization_id=tenant["organization"]["id"],
                    branch_id=branch_id,
                    cash_shift_id=shift["id"],
                    movement_type="withdrawal",
                    amount_cents=amount,
                    reason_code="TEST",
                    reason="Synthetic report expense",
                    source_type="manual",
                    source_id=None,
                    actor_user_id=owner,
                    idempotency_key=f"{movement_id}-key",
                    status="confirmed",
                    reversal_of_id=None,
                    concept_id=None,
                    concept_version_id=None,
                    concept_snapshot=None,
                    reference=None,
                    evidence_refs=None,
                    compensates_movement_id=None,
                    created_at=now,
                ))
            session.commit()
        period_start = now.replace(microsecond=0)
        params = {
            "from_utc": period_start.isoformat(),
            "to_utc": (period_start + timedelta(days=1)).isoformat(),
            "branch_id": branch_a,
        }
        response_a = client.get(
            "/api/v1/reports/expenses",
            params=params,
            headers={"Authorization": f"Bearer {tenant_a['token']}"},
        )
        assert response_a.status_code == 200, response_a.text
        assert [item["id"] for item in response_a.json()["items"]] == ["cash:http-report-expense-a"]
        response_b = client.get(
            "/api/v1/reports/expenses",
            params={**params, "branch_id": branch_b},
            headers={"Authorization": f"Bearer {tenant_b['token']}"},
        )
        assert response_b.status_code == 200, response_b.text
        assert [item["id"] for item in response_b.json()["items"]] == ["cash:http-report-expense-b"]
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_cash_shift_open_api_rejects_other_tenant_branch_without_side_effect() -> None:
    client, factory = _cash_scope_api_client()
    try:
        with factory() as session:
            tenant_a = signup_tenant(session, {
                "business_name": "API Caja A", "owner_name": "Propietaria A",
                "email": "api-cash-a@example.test", "password": "test-password-a",
                "business_type": "taqueria",
            })
            tenant_b = signup_tenant(session, {
                "business_name": "API Caja B", "owner_name": "Propietario B",
                "email": "api-cash-b@example.test", "password": "test-password-b",
                "business_type": "taqueria",
            })
        branch_a = tenant_a["branch"]["id"]
        headers_a = {"Authorization": f"Bearer {tenant_a['token']}", "Idempotency-Key": "api-a"}
        headers_b = {"Authorization": f"Bearer {tenant_b['token']}", "Idempotency-Key": "api-b"}
        opened = client.post(
            "/api/v1/cash-shifts/open",
            headers=headers_a,
            json={"branch_id": branch_a, "register_id": "CAJA-01", "opening_cash_cents": 0},
        )
        assert opened.status_code == 200
        shift_id = opened.json()["id"]

        missing_scope = client.get("/api/v1/cash-shifts/summary", headers=headers_a)
        assert missing_scope.status_code in (400, 403, 409, 422), missing_scope.text
        assert "branch_required" in missing_scope.text, missing_scope.text
        scoped_summary = client.get(
            f"/api/v1/cash-shifts/summary?branch_id={branch_a}", headers=headers_a
        )
        assert scoped_summary.status_code == 200, scoped_summary.text
        assert scoped_summary.json()["cash_shift"]["id"] == shift_id

        history = client.get(
            f"/api/v1/cash/shifts?branch_id={branch_a}", headers=headers_a
        )
        assert history.status_code == 200
        assert [item["id"] for item in history.json()["items"]] == [shift_id]
        detail = client.get(f"/api/v1/cash/shifts/{shift_id}", headers=headers_a)
        assert detail.status_code == 200
        assert detail.json()["cash_shift"]["organization_id"] == tenant_a["organization"]["id"]

        rejected = client.post(
            "/api/v1/cash-shifts/open",
            headers=headers_b,
            json={"branch_id": branch_a, "register_id": "CAJA-B", "opening_cash_cents": 0},
        )
        assert rejected.status_code == 403
        forbidden_history = client.get(
            f"/api/v1/cash/shifts?branch_id={branch_a}", headers=headers_b
        )
        assert forbidden_history.status_code == 403
        forbidden_detail = client.get(f"/api/v1/cash/shifts/{shift_id}", headers=headers_b)
        assert forbidden_detail.status_code == 403
        with factory() as session:
            assert session.scalar(sa.select(sa.func.count()).select_from(models.cash_shifts)) == 1
    finally:
        app.dependency_overrides.clear()
