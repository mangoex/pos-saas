"""PCO-004 migration, backfill and reversibility checks."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from restaurant_os import models
from restaurant_os.operations import AuthorizationError, authorize_branch_scope
from sqlalchemy.orm import Session
from test_cash_ledger_migration import _sqlite_alembic


def test_metadata_requires_frozen_family_fields() -> None:
    assert not models.order_lines.c.family_id_snapshot.nullable
    assert not models.order_lines.c.family_name_snapshot.nullable
    assert not models.order_lines.c.family_snapshot_source.nullable
    assert not models.sales_operation_line_snapshots.c.family_id_snapshot.nullable
    assert not models.sales_operation_line_snapshots.c.family_name_snapshot.nullable
    expected_constraints = {
        "cash_shift_closures": {"ck_cash_shift_closures_register"},
        "cash_shift_commands": {
            "ck_cash_shift_commands_type",
            "ck_cash_shift_commands_status",
            "ck_cash_shift_commands_idempotency_key",
            "ck_cash_shift_commands_request_hash",
        },
        "sales_operation_snapshots": {
            "ck_sales_snapshot_quality",
            "ck_sales_snapshot_service_type",
            "ck_sales_snapshot_currency",
            "ck_sales_snapshot_identifiers",
            "ck_sales_snapshot_known_cents_nonnegative",
            "ck_sales_snapshot_optional_cents_nonnegative",
        },
        "sales_operation_line_snapshots": {
            "ck_sales_line_family_source",
            "ck_sales_line_names",
            "ck_sales_line_quantity_gross",
            "ck_sales_line_optional_cents_nonnegative",
        },
    }
    for table_name, expected in expected_constraints.items():
        actual = {
            constraint.name
            for constraint in models.metadata.tables[table_name].constraints
            if isinstance(constraint, sa.CheckConstraint)
        }
        assert expected <= actual
    expected_indexes = {
        "ix_cash_shift_closures_org_branch_closed",
        "ix_sales_snapshots_org_period_branch",
        "ix_sales_snapshots_org_shift_register_service",
        "ix_sales_line_snapshots_family",
        "ix_sales_line_snapshots_payment",
    }
    actual_indexes = {
        index.name
        for table in models.metadata.tables.values()
        for index in table.indexes
    }
    assert expected_indexes <= actual_indexes

ROOT = Path(__file__).resolve().parents[3]
API_DIR = ROOT / "apps" / "api"
REVISION_0037 = "0037_cash_movement_ledger"
REVISION_0038 = "0038_cash_shift_closures_sales_monitor"
ORG_ID = "018f6f73-2d0a-74f0-8f1c-000000000001"
BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000006"
PRODUCT_ID = "018f6f73-2d0a-74f0-8f1c-000000000111"
CATEGORY_ID = "018f6f73-2d0a-74f0-8f1c-000000000101"
SHIFT_ID = "018f6f73-2d0a-74f0-8f1c-000000009400"
ORDER_OK_ID = "018f6f73-2d0a-74f0-8f1c-000000009401"
ORDER_INCOMPLETE_ID = "018f6f73-2d0a-74f0-8f1c-000000009402"
LINE_OK_ID = "018f6f73-2d0a-74f0-8f1c-000000009403"
LINE_INCOMPLETE_ID = "018f6f73-2d0a-74f0-8f1c-000000009404"
PAYMENT_OK_ID = "018f6f73-2d0a-74f0-8f1c-000000009405"
PAYMENT_INCOMPLETE_ID = "018f6f73-2d0a-74f0-8f1c-000000009406"
AT = "2026-08-12T05:00:00+00:00"


def _insert_legacy_sales(connection: sqlite3.Connection, order_type: str = "takeout") -> None:
    connection.execute(
        """
        INSERT INTO cash_shifts (
            id, organization_id, branch_id, register_code, status,
            opening_cash_cents, opened_at, closed_at, created_at
        ) VALUES (?, ?, ?, 'LEGACY-04', 'CLOSED', 5000, ?, ?, ?)
        """,
        (SHIFT_ID, ORG_ID, BRANCH_ID, AT, AT, AT),
    )
    for order_id, folio, total_cents in (
        (ORDER_OK_ID, "PCO4-OK", 1_000),
        (ORDER_INCOMPLETE_ID, "PCO4-INCOMPLETE", 1_200),
    ):
        connection.execute(
            """
            INSERT INTO orders (
                id, organization_id, branch_id, cash_shift_id, folio, channel,
                status, total_cents, currency, created_at, accepted_at, order_type, version
            ) VALUES (?, ?, ?, ?, ?, 'pos', 'CLOSED', ?, 'MXN', ?, ?, ?, 1)
            """,
            (order_id, ORG_ID, BRANCH_ID, SHIFT_ID, folio, total_cents, AT, AT, order_type),
        )
    for line_id, order_id, line_total in (
        (LINE_OK_ID, ORDER_OK_ID, 1_000),
        (LINE_INCOMPLETE_ID, ORDER_INCOMPLETE_ID, 1_500),
    ):
        connection.execute(
            """
            INSERT INTO order_lines (
                id, order_id, product_id, product_name, quantity, unit_price_cents,
                line_total_cents, station, selected_modifiers, modifier_total_cents,
                status, revision, created_at
            ) VALUES (?, ?, ?, 'Hamburguesa histórica', 1, ?, ?, 'kitchen', '[]', 0,
                      'active', 1, ?)
            """,
            (line_id, order_id, PRODUCT_ID, line_total, line_total, AT),
        )
    for payment_id, order_id, amount in (
        (PAYMENT_OK_ID, ORDER_OK_ID, 1_000),
        (PAYMENT_INCOMPLETE_ID, ORDER_INCOMPLETE_ID, 1_200),
    ):
        connection.execute(
            """
            INSERT INTO payments (
                id, organization_id, branch_id, order_id, cash_shift_id,
                method, status, amount_cents, currency, confirmed_at, created_at
            ) VALUES (?, ?, ?, ?, ?, 'cash', 'CONFIRMED', ?, 'MXN', ?, ?)
            """,
            (payment_id, ORG_ID, BRANCH_ID, order_id, SHIFT_ID, amount, AT, AT),
        )
    connection.commit()


def _legacy_fingerprint(connection: sqlite3.Connection) -> tuple[tuple[object, ...], ...]:
    return tuple(
        connection.execute(
            """
            SELECT payment.id, payment.order_id, payment.cash_shift_id, payment.amount_cents,
                   order_row.folio, line.id, line.product_id, line.line_total_cents
            FROM payments payment
            JOIN orders order_row ON order_row.id = payment.order_id
            JOIN order_lines line ON line.order_id = order_row.id
            WHERE payment.id IN (?, ?)
            ORDER BY payment.id, line.id
            """,
            (PAYMENT_OK_ID, PAYMENT_INCOMPLETE_ID),
        ).fetchall()
    )


def test_sqlite_0038_backfills_known_and_unknown_history_and_roundtrips(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "pco004-roundtrip.db"
    baseline = _sqlite_alembic(database_path, "upgrade", REVISION_0037)
    assert baseline.returncode == 0, baseline.stderr
    connection = sqlite3.connect(database_path)
    try:
        _insert_legacy_sales(connection)
        fingerprint = _legacy_fingerprint(connection)
    finally:
        connection.close()

    upgraded = _sqlite_alembic(database_path, "upgrade", REVISION_0038)
    assert upgraded.returncode == 0, upgraded.stderr
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            REVISION_0038,
        )
        family = connection.execute(
            """
            SELECT family_id_snapshot, family_name_snapshot, family_snapshot_source
            FROM order_lines WHERE id = ?
            """,
            (LINE_OK_ID,),
        ).fetchone()
        assert family == (CATEGORY_ID, "Comida", "legacy_catalog_backfill")
        known = connection.execute(
            """
            SELECT gross_cents, net_cents, discount_cents, courtesy_cents, tax_cents,
                   quality_status, register_code_snapshot, service_type_snapshot
            FROM sales_operation_snapshots WHERE payment_id = ?
            """,
            (PAYMENT_OK_ID,),
        ).fetchone()
        assert known == (1_000, 1_000, 0, 0, 0, "legacy_backfill", "LEGACY-04", "takeout")
        incomplete = connection.execute(
            """
            SELECT gross_cents, net_cents, discount_cents, courtesy_cents, tax_cents,
                   quality_status
            FROM sales_operation_snapshots WHERE payment_id = ?
            """,
            (PAYMENT_INCOMPLETE_ID,),
        ).fetchone()
        assert incomplete == (1_500, 1_200, None, None, None, "incomplete")
        line_history = connection.execute(
            """
            SELECT family_snapshot_source, gross_cents, net_cents,
                   discount_cents, courtesy_cents, tax_cents
            FROM sales_operation_line_snapshots WHERE payment_id = ?
            """,
            (PAYMENT_INCOMPLETE_ID,),
        ).fetchone()
        assert line_history == ("legacy_catalog_backfill", 1_500, None, None, None, None)
        assert _legacy_fingerprint(connection) == fingerprint
    finally:
        connection.close()

    downgraded = _sqlite_alembic(database_path, "downgrade", REVISION_0037)
    assert downgraded.returncode == 0, downgraded.stderr
    connection = sqlite3.connect(database_path)
    try:
        assert _legacy_fingerprint(connection) == fingerprint
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='sales_operation_snapshots'"
        ).fetchone() is None
    finally:
        connection.close()
    reupgraded = _sqlite_alembic(database_path, "upgrade", REVISION_0038)
    assert reupgraded.returncode == 0, reupgraded.stderr
    connection = sqlite3.connect(database_path)
    try:
        assert _legacy_fingerprint(connection) == fingerprint
        assert connection.execute(
            "SELECT quality_status FROM sales_operation_snapshots WHERE payment_id = ?",
            (PAYMENT_INCOMPLETE_ID,),
        ).fetchone() == ("incomplete",)
    finally:
        connection.close()


def test_sqlite_0038_projects_exact_legacy_takeaway_without_rewriting_order(tmp_path: Path) -> None:
    database_path = tmp_path / "pco004-takeaway.db"
    assert _sqlite_alembic(database_path, "upgrade", REVISION_0037).returncode == 0
    connection = sqlite3.connect(database_path)
    try:
        _insert_legacy_sales(connection, order_type="takeaway")
    finally:
        connection.close()

    upgraded = _sqlite_alembic(database_path, "upgrade", REVISION_0038)
    assert upgraded.returncode == 0, upgraded.stderr
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT order_type FROM orders WHERE id = ?", (ORDER_OK_ID,)
        ).fetchone() == ("takeaway",)
        assert connection.execute(
            "SELECT service_type_snapshot FROM sales_operation_snapshots WHERE payment_id = ?",
            (PAYMENT_OK_ID,),
        ).fetchone() == ("takeout",)
    finally:
        connection.close()


def test_sqlite_0038_rejects_unknown_legacy_service_type_before_snapshot_creation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "pco004-unknown-service.db"
    assert _sqlite_alembic(database_path, "upgrade", REVISION_0037).returncode == 0
    connection = sqlite3.connect(database_path)
    try:
        _insert_legacy_sales(connection, order_type="takeaway-plus")
    finally:
        connection.close()

    upgraded = _sqlite_alembic(database_path, "upgrade", REVISION_0038)
    assert upgraded.returncode != 0
    assert "incoherent confirmed payment history" in (upgraded.stdout + upgraded.stderr)
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sales_operation_snapshots'"
        ).fetchone() is None
    finally:
        connection.close()

@pytest.mark.parametrize("case", ["empty_family", "category_cross_org", "order_cross_org"])
def test_sqlite_0038_family_preflight_fails_closed(tmp_path: Path, case: str) -> None:
    database_path = tmp_path / f"pco004-preflight-{case}.db"
    assert _sqlite_alembic(database_path, "upgrade", REVISION_0037).returncode == 0
    connection = sqlite3.connect(database_path)
    try:
        _insert_legacy_sales(connection)
        if case == "empty_family":
            connection.execute(
                "UPDATE product_categories SET name = '   ' WHERE id = ?", (CATEGORY_ID,)
            )
        else:
            other_org = "018f6f73-2d0a-74f0-8f1c-000000009499"
            connection.execute(
                """
                INSERT INTO organizations (id, name, status, created_at, updated_at)
                VALUES (?, 'Otra organización', 'active', ?, ?)
                """,
                (other_org, AT, AT),
            )
            if case == "category_cross_org":
                connection.execute(
                    "UPDATE product_categories SET organization_id = ? WHERE id = ?",
                    (other_org, CATEGORY_ID),
                )
            else:
                connection.execute(
                    "UPDATE orders SET organization_id = ? WHERE id = ?",
                    (other_org, ORDER_OK_ID),
                )
        connection.commit()
    finally:
        connection.close()
    blocked = _sqlite_alembic(database_path, "upgrade", REVISION_0038)
    assert blocked.returncode != 0
    assert "Family snapshot preflight failed" in blocked.stdout + blocked.stderr


def test_sqlite_0038_currency_mismatch_fails_preflight_without_backfill(tmp_path: Path) -> None:
    database_path = tmp_path / "pco004-currency-mismatch.db"
    assert _sqlite_alembic(database_path, "upgrade", REVISION_0037).returncode == 0
    connection = sqlite3.connect(database_path)
    try:
        _insert_legacy_sales(connection)
        connection.execute("UPDATE payments SET currency = 'USD' WHERE id = ?", (PAYMENT_OK_ID,))
        connection.commit()
    finally:
        connection.close()

    blocked = _sqlite_alembic(database_path, "upgrade", REVISION_0038)
    assert blocked.returncode != 0
    assert "Sales snapshot preflight failed" in blocked.stdout + blocked.stderr
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sales_operation_snapshots'"
        ).fetchone() is None
    finally:
        connection.close()


def test_pco004_cumulative_profile_grants_and_scopes_use_seeded_0035_data(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "pco004-cumulative-profiles.db"
    assert _sqlite_alembic(database_path, "upgrade", REVISION_0038).returncode == 0
    assert _sqlite_alembic(database_path, "upgrade", "head").returncode == 0
    engine = sa.create_engine(f"sqlite+pysqlite:///{database_path}")
    try:
        with Session(engine) as session:
            roles = {
                row["name"]: row["id"]
                for row in session.execute(
                    sa.select(models.roles.c.name, models.roles.c.id).where(
                        models.roles.c.name.in_(
                            [
                                "Cajero",
                                "Cajero jefe",
                                "Líder",
                                "Supervisor",
                                "Administrador",
                                "Dueño",
                            ]
                        )
                    )
                ).mappings()
            }
            assert set(roles) == {
                "Cajero",
                "Cajero jefe",
                "Líder",
                "Supervisor",
                "Administrador",
                "Dueño",
            }
            granted = {
                role_name: {
                    row["code"]
                    for row in session.execute(
                        sa.select(models.permissions.c.code)
                        .select_from(
                            models.role_permissions.join(
                                models.permissions,
                                models.role_permissions.c.permission_id == models.permissions.c.id,
                            )
                        )
                        .where(models.role_permissions.c.role_id == role_id)
                    ).mappings()
                }
                for role_name, role_id in roles.items()
            }
            cash_shift_permissions = {"cash.shift.read", "cash.shift.open", "cash.shift.close"}
            assert not (cash_shift_permissions & granted["Cajero"])
            for name in ("Cajero jefe", "Líder", "Supervisor", "Administrador", "Dueño"):
                assert cash_shift_permissions <= granted[name]
            for name in ("Cajero", "Cajero jefe", "Líder", "Supervisor"):
                assert "reports.sales.read" not in granted[name]
            assert "reports.sales.read" in granted["Administrador"]
            assert "reports.sales.read" in granted["Dueño"]
            owner_grant = session.execute(
                sa.select(models.role_authority_grants.c.authority_kind).where(
                    models.role_authority_grants.c.role_id == roles["Dueño"]
                )
            ).scalar_one()
            assert owner_grant == "organization_all_permissions"

            now = session.execute(sa.select(sa.func.max(models.users.c.created_at))).scalar_one()
            main_branch = BRANCH_ID
            users = {
                name: f"018f6f73-2d0a-74f0-8f1c-0000000070{index:02d}"
                for index, name in enumerate(roles, start=1)
            }
            session.execute(
                models.users.insert(),
                [
                    {
                        "id": user_id,
                        "organization_id": ORG_ID,
                        "email": f"pco004-{index}@example.test",
                        "display_name": role_name,
                        "status": "active",
                        "created_at": now,
                        "updated_at": now,
                    }
                    for index, (role_name, user_id) in enumerate(users.items(), start=1)
                ],
            )
            session.execute(
                models.user_roles.insert(),
                [
                    {
                        "user_id": users[role_name],
                        "role_id": role_id,
                        "branch_id": None if role_name == "Dueño" else main_branch,
                    }
                    for role_name, role_id in roles.items()
                ],
            )
            other_org = "018f6f73-2d0a-74f0-8f1c-000000007090"
            other_entity = "018f6f73-2d0a-74f0-8f1c-000000007091"
            other_unit = "018f6f73-2d0a-74f0-8f1c-000000007092"
            other_branch = "018f6f73-2d0a-74f0-8f1c-000000007093"
            session.execute(models.organizations.insert().values(
                id=other_org, name="Otra", status="active", created_at=now, updated_at=now
            ))
            session.execute(models.legal_entities.insert().values(
                id=other_entity, organization_id=other_org, name="Otra", tax_id=None,
                status="active", created_at=now, updated_at=now,
            ))
            session.execute(models.business_units.insert().values(
                id=other_unit, organization_id=other_org, legal_entity_id=other_entity,
                name="Otra", code="OTRA", unit_type="restaurant", status="active",
                created_at=now, updated_at=now,
            ))
            session.execute(models.branches.insert().values(
                id=other_branch, organization_id=other_org, legal_entity_id=other_entity,
                business_unit_id=other_unit, name="Otra", code="OTRA", timezone="America/Chihuahua",
                status="active", created_at=now, updated_at=now,
            ))
            session.commit()

            with pytest.raises(AuthorizationError):
                authorize_branch_scope(session, users["Cajero"], "cash.shift.read", main_branch)
            assert authorize_branch_scope(
                session, users["Cajero jefe"], "cash.shift.open", main_branch
            ) == main_branch
            assert authorize_branch_scope(
                session, users["Administrador"], "reports.sales.read", main_branch
            ) == main_branch
            assert authorize_branch_scope(
                session, users["Dueño"], "reports.sales.read"
            ) is None
            with pytest.raises(AuthorizationError):
                authorize_branch_scope(session, users["Dueño"], "reports.sales.read", other_branch)
    finally:
        engine.dispose()


def test_sqlite_0038_rejects_open_closing_duplicate_before_index_change(tmp_path: Path) -> None:
    database_path = tmp_path / "pco004-active-duplicate.db"
    assert _sqlite_alembic(database_path, "upgrade", REVISION_0037).returncode == 0
    connection = sqlite3.connect(database_path)
    try:
        for shift_id, status in (
            ("018f6f73-2d0a-74f0-8f1c-000000009410", "OPEN"),
            ("018f6f73-2d0a-74f0-8f1c-000000009411", "CLOSING"),
        ):
            connection.execute(
                """
                INSERT INTO cash_shifts (
                    id, organization_id, branch_id, register_code, status,
                    opening_cash_cents, opened_at, closed_at, created_at
                ) VALUES (?, ?, ?, 'DUPLICATE-04', ?, 0, ?, NULL, ?)
                """,
                (shift_id, ORG_ID, BRANCH_ID, status, AT, AT),
            )
        connection.commit()
    finally:
        connection.close()
    blocked = _sqlite_alembic(database_path, "upgrade", REVISION_0038)
    assert blocked.returncode != 0
    assert "duplicate active shifts" in blocked.stdout + blocked.stderr


def test_sqlite_0038_constraints_reject_invalid_quality_source_and_cents(tmp_path: Path) -> None:
    database_path = tmp_path / "pco004-constraints.db"
    assert _sqlite_alembic(database_path, "upgrade", REVISION_0038).returncode == 0
    connection = sqlite3.connect(database_path)
    try:
        table_sql = {
            table: connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()[0]
            for table in (
                "order_lines",
                "cash_shift_commands",
                "sales_operation_snapshots",
                "sales_operation_line_snapshots",
            )
        }
        assert "ck_order_lines_family_snapshot_source" in table_sql["order_lines"]
        assert "ck_cash_shift_commands_status" in table_sql["cash_shift_commands"]
        assert "ck_sales_snapshot_known_cents_nonnegative" in table_sql[
            "sales_operation_snapshots"
        ]
        assert "ck_sales_line_optional_cents_nonnegative" in table_sql[
            "sales_operation_line_snapshots"
        ]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO cash_shift_commands (
                    id, organization_id, actor_user_id, cash_shift_id, command_type,
                    idempotency_key, request_hash, result, status, created_at
                ) VALUES (?, ?, ?, NULL, 'open', 'bad-status', ?, '{}', 'pending', ?)
                """,
                ("018f6f73-2d0a-74f0-8f1c-000000009490", ORG_ID, USER_ID, "0" * 64, AT),
            )
        connection.rollback()
    finally:
        connection.close()


@pytest.mark.parametrize("history_kind", ["closure", "command", "snapshot", "line"])
def test_sqlite_0038_downgrade_blocks_each_captured_history_kind(
    tmp_path: Path, history_kind: str
) -> None:
    database_path = tmp_path / f"pco004-guard-{history_kind}.db"
    assert _sqlite_alembic(database_path, "upgrade", REVISION_0037).returncode == 0
    connection = sqlite3.connect(database_path)
    try:
        _insert_legacy_sales(connection)
    finally:
        connection.close()
    assert _sqlite_alembic(database_path, "upgrade", REVISION_0038).returncode == 0
    connection = sqlite3.connect(database_path)
    try:
        if history_kind == "closure":
            connection.execute(
                """
                INSERT INTO cash_shift_closures (
                    id, organization_id, branch_id, cash_shift_id, register_code_snapshot,
                    closed_by_user_id, summary_snapshot, closed_at, created_at
                ) VALUES (?, ?, ?, ?, 'LEGACY-04', ?, '{}', ?, ?)
                """,
                (
                    "018f6f73-2d0a-74f0-8f1c-000000009480",
                    ORG_ID,
                    BRANCH_ID,
                    SHIFT_ID,
                    USER_ID,
                    AT,
                    AT,
                ),
            )
        elif history_kind == "command":
            connection.execute(
                """
                INSERT INTO cash_shift_commands (
                    id, organization_id, actor_user_id, cash_shift_id, command_type,
                    idempotency_key, request_hash, result, status, created_at
                ) VALUES (?, ?, ?, ?, 'close', 'captured-command', ?, '{}', 'completed', ?)
                """,
                (
                    "018f6f73-2d0a-74f0-8f1c-000000009481",
                    ORG_ID,
                    USER_ID,
                    SHIFT_ID,
                    "0" * 64,
                    AT,
                ),
            )
        elif history_kind == "snapshot":
            connection.execute(
                "UPDATE sales_operation_snapshots SET quality_status = 'captured' "
                "WHERE payment_id = ?",
                (PAYMENT_OK_ID,),
            )
        else:
            connection.execute(
                "UPDATE order_lines SET family_snapshot_source = 'captured' WHERE id = ?",
                (LINE_OK_ID,),
            )
        connection.commit()
    finally:
        connection.close()
    blocked = _sqlite_alembic(database_path, "downgrade", REVISION_0037)
    assert blocked.returncode != 0
    assert "Safe downgrade blocked: PCO-004 captured history exists" in (
        blocked.stdout + blocked.stderr
    )


def _postgres_url() -> str:
    url = os.environ.get("PCO004_TEST_POSTGRES_ROUNDTRIP_URL")
    if not url:
        pytest.skip("PCO004_TEST_POSTGRES_ROUNDTRIP_URL is required")
    parsed = urlparse(url)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.path.startswith(
        "/pco004_"
    ):
        raise RuntimeError("PCO-004 migration tests require a local isolated pco004_* database")
    return url


def _postgres_alembic(url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "RESTAURANTOS_DATABASE_URL": url}
    env.pop("DATABASE_URL", None)
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *arguments],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


def test_postgres_0038_isolated_roundtrip_and_backfill() -> None:
    url = _postgres_url()
    downgraded = _postgres_alembic(url, "downgrade", REVISION_0037)
    assert downgraded.returncode == 0, downgraded.stderr
    baseline = _postgres_alembic(url, "upgrade", REVISION_0037)
    assert baseline.returncode == 0, baseline.stderr
    engine = sa.create_engine(url, pool_pre_ping=True)
    with engine.begin() as connection:
        for table in ("payments", "order_lines", "orders", "cash_shifts"):
            identifiers = {
                "payments": [PAYMENT_OK_ID, PAYMENT_INCOMPLETE_ID],
                "order_lines": [LINE_OK_ID, LINE_INCOMPLETE_ID],
                "orders": [ORDER_OK_ID, ORDER_INCOMPLETE_ID],
                "cash_shifts": [SHIFT_ID],
            }[table]
            connection.execute(
                sa.text(f"DELETE FROM {table} WHERE id IN :ids").bindparams(  # noqa: S608
                    sa.bindparam("ids", expanding=True)
                ),
                {"ids": identifiers},
            )
        connection.execute(
            sa.text(
                """
                INSERT INTO cash_shifts (
                    id, organization_id, branch_id, register_code, status,
                    opening_cash_cents, opened_at, closed_at, created_at
                ) VALUES (:id, :organization_id, :branch_id, 'LEGACY-04', 'CLOSED',
                          5000, :at, :at, :at)
                """
            ),
            {"id": SHIFT_ID, "organization_id": ORG_ID, "branch_id": BRANCH_ID, "at": AT},
        )
        for order_id, folio, total in (
            (ORDER_OK_ID, "PCO4-OK", 1_000),
            (ORDER_INCOMPLETE_ID, "PCO4-INCOMPLETE", 1_200),
        ):
            order_type = "takeaway" if order_id == ORDER_OK_ID else "takeout"
            connection.execute(
                sa.text(
                    """
                    INSERT INTO orders (
                        id, organization_id, branch_id, cash_shift_id, folio, channel,
                        status, total_cents, currency, created_at, accepted_at, order_type, version
                    ) VALUES (:id, :organization_id, :branch_id, :shift_id, :folio, 'pos',
                              'CLOSED', :total, 'MXN', :at, :at, :order_type, 1)
                    """
                ),
                {
                    "id": order_id,
                    "organization_id": ORG_ID,
                    "branch_id": BRANCH_ID,
                    "shift_id": SHIFT_ID,
                    "folio": folio,
                    "total": total,
                    "at": AT,
                    "order_type": order_type,
                },
            )
        for line_id, order_id, total in (
            (LINE_OK_ID, ORDER_OK_ID, 1_000),
            (LINE_INCOMPLETE_ID, ORDER_INCOMPLETE_ID, 1_500),
        ):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO order_lines (
                        id, order_id, product_id, product_name, quantity, unit_price_cents,
                        line_total_cents, station, selected_modifiers, modifier_total_cents,
                        status, revision, created_at
                    ) VALUES (:id, :order_id, :product_id, 'Hamburguesa histórica', 1,
                              :total, :total, 'kitchen', '[]', 0, 'active', 1, :at)
                    """
                ),
                {
                    "id": line_id,
                    "order_id": order_id,
                    "product_id": PRODUCT_ID,
                    "total": total,
                    "at": AT,
                },
            )
        for payment_id, order_id, amount in (
            (PAYMENT_OK_ID, ORDER_OK_ID, 1_000),
            (PAYMENT_INCOMPLETE_ID, ORDER_INCOMPLETE_ID, 1_200),
        ):
            connection.execute(
                sa.text(
                    """
                    INSERT INTO payments (
                        id, organization_id, branch_id, order_id, cash_shift_id,
                        method, status, amount_cents, currency, confirmed_at, created_at
                    ) VALUES (:id, :organization_id, :branch_id, :order_id, :shift_id,
                              'cash', 'CONFIRMED', :amount, 'MXN', :at, :at)
                    """
                ),
                {
                    "id": payment_id,
                    "organization_id": ORG_ID,
                    "branch_id": BRANCH_ID,
                    "order_id": order_id,
                    "shift_id": SHIFT_ID,
                    "amount": amount,
                    "at": AT,
                },
            )
    upgraded = _postgres_alembic(url, "upgrade", REVISION_0038)
    assert upgraded.returncode == 0, upgraded.stderr
    with engine.connect() as connection:
        history = connection.execute(
            sa.text(
                """
                SELECT payment_id, gross_cents, net_cents, tax_cents, quality_status,
                       service_type_snapshot
                FROM sales_operation_snapshots
                WHERE payment_id IN (:known, :incomplete)
                ORDER BY payment_id
                """
            ),
            {"known": PAYMENT_OK_ID, "incomplete": PAYMENT_INCOMPLETE_ID},
        ).all()
        assert history == [
            (PAYMENT_OK_ID, 1_000, 1_000, 0, "legacy_backfill", "takeout"),
            (PAYMENT_INCOMPLETE_ID, 1_500, 1_200, None, "incomplete", "takeout"),
        ]
        assert connection.execute(
            sa.text("SELECT order_type FROM orders WHERE id = :id"), {"id": ORDER_OK_ID}
        ).scalar_one() == "takeaway"
    roundtrip_down = _postgres_alembic(url, "downgrade", REVISION_0037)
    assert roundtrip_down.returncode == 0, roundtrip_down.stderr
    roundtrip_up = _postgres_alembic(url, "upgrade", REVISION_0038)
    assert roundtrip_up.returncode == 0, roundtrip_up.stderr
    engine.dispose()
