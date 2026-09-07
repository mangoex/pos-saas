"""R3 evidence for fail-closed containment of legacy migration 0049."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[3]
API_DIR = ROOT / "apps" / "api"
POSTGRES_ENV = "SEED0058_TEST_POSTGRES_URL"
ORGANIZATION_ID = "018f6f73-2d0a-74f0-8f1c-000000000001"
PILOT_BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
CAJERO_ROLE_ID = "018f6f73-2d0a-74f0-8f1c-000000001001"
ADMIN_ROLE_ID = "018f6f73-2d0a-74f0-8f1c-000000001005"
AUDIT_ID = "018f6f73-2d0a-74f0-8f1c-000000001200"
LEGACY_USER_ID = "018f6f73-2d0a-74f0-8f1c-000000009049"
FUZZY_BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000009050"


def _alembic(database_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.pop("DATABASE_URL", None)
    environment["RESTAURANTOS_DATABASE_URL"] = f"sqlite+pysqlite:///{database_path}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *arguments],
        cwd=API_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _current(database_path: Path) -> str:
    result = _alembic(database_path, "current")
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _known_user_assignments(connection: sqlite3.Connection) -> set[tuple[str, str]]:
    return {
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            """
            SELECT user_roles.role_id, user_roles.branch_id
            FROM user_roles
            JOIN users ON users.id = user_roles.user_id
            WHERE LOWER(users.email) = 'caja01laprimavera@kiwi.com'
            """
        )
    }


def test_0058_verifies_clean_0049_seed_without_mutating_roles(tmp_path: Path) -> None:
    database_path = tmp_path / "clean-0049-seed.db"
    prepared = _alembic(database_path, "upgrade", "0057_operational_human_scope_permissions")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr

    connection = sqlite3.connect(database_path)
    try:
        before = _known_user_assignments(connection)
        assert len(before) == 1
    finally:
        connection.close()

    upgraded = _alembic(database_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr

    connection = sqlite3.connect(database_path)
    try:
        after = _known_user_assignments(connection)
        assert after == before
        event = connection.execute(
            """
            SELECT branch_id, actor_user_id, action, entity_type, entity_id,
                   payload, correlation_id
            FROM audit_events WHERE id = ?
            """,
            (AUDIT_ID,),
        ).fetchone()
        assert event is not None
        branch_id, actor_user_id, action, entity_type, entity_id, payload, correlation_id = event
        assert branch_id == next(iter(after))[1]
        assert actor_user_id is None
        assert action == "migration.0049_seed_state_verified"
        assert entity_type == "user_role_seed"
        assert entity_id
        assert correlation_id is None
        assert json.loads(payload) == {
            "assignment_snapshot": [{"branch_id": branch_id, "role_id": CAJERO_ROLE_ID}],
            "decision": "clean_seed_fingerprint_verified",
            "source_revision": "0049_seed_la_primavera_branch_and_user",
            "verification_revision": "0058_verify_0049_la_primavera_seed",
        }
    finally:
        connection.close()

    replay = _alembic(database_path, "upgrade", "head")
    assert replay.returncode == 0, replay.stdout + replay.stderr
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE id = ?", (AUDIT_ID,)
        ).fetchone() == (1,)
    finally:
        connection.close()

    downgrade = _alembic(database_path, "downgrade", "0057_operational_human_scope_permissions")
    assert downgrade.returncode != 0
    assert "forward-only" in downgrade.stderr


def test_0058_accepts_data_owner_approved_suc06_without_mutating_roles(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "approved-suc06-state.db"
    prepared = _alembic(database_path, "upgrade", "0057_operational_human_scope_permissions")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            UPDATE branches
            SET code = 'SUC06', updated_at = '2026-08-30 20:00:00+00:00'
            WHERE name = 'La Primavera'
            """
        )
        connection.execute(
            """
            UPDATE warehouses
            SET updated_at = '2026-08-30 20:01:00+00:00'
            WHERE name = 'Almacén La Primavera'
            """
        )
        connection.execute(
            """
            UPDATE users
            SET updated_at = '2026-08-30 20:02:00+00:00'
            WHERE LOWER(email) = 'caja01laprimavera@kiwi.com'
            """
        )
        connection.commit()
        before = _known_user_assignments(connection)
        assert len(before) == 1
    finally:
        connection.close()

    upgraded = _alembic(database_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr

    connection = sqlite3.connect(database_path)
    try:
        after = _known_user_assignments(connection)
        assert after == before
        payload = connection.execute(
            "SELECT payload FROM audit_events WHERE id = ?", (AUDIT_ID,)
        ).fetchone()
        assert payload is not None
        assert json.loads(payload[0])["decision"] == "approved_canonical_state_verified"
    finally:
        connection.close()


def test_0058_accepts_approved_suc06_warehouse_name_without_accent(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "approved-suc06-unaccented-warehouse.db"
    prepared = _alembic(database_path, "upgrade", "0057_operational_human_scope_permissions")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("UPDATE branches SET code = 'SUC06' WHERE name = 'La Primavera'")
        connection.execute(
            """
            UPDATE warehouses
            SET name = 'Almacen La Primavera'
            WHERE name = 'Almacén La Primavera'
            """
        )
        connection.commit()
        before = _known_user_assignments(connection)
        assert len(before) == 1
    finally:
        connection.close()

    upgraded = _alembic(database_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr

    connection = sqlite3.connect(database_path)
    try:
        assert _known_user_assignments(connection) == before
        payload = connection.execute(
            "SELECT payload FROM audit_events WHERE id = ?", (AUDIT_ID,)
        ).fetchone()
        assert payload is not None
        assert json.loads(payload[0])["decision"] == "approved_canonical_state_verified"
    finally:
        connection.close()


def test_0058_fails_closed_for_unapproved_suc06_warehouse_name(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "unapproved-suc06-warehouse.db"
    prepared = _alembic(database_path, "upgrade", "0057_operational_human_scope_permissions")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("UPDATE branches SET code = 'SUC06' WHERE name = 'La Primavera'")
        connection.execute(
            """
            UPDATE warehouses
            SET name = 'Bodega La Primavera'
            WHERE name = 'Almacén La Primavera'
            """
        )
        connection.commit()
        before = _known_user_assignments(connection)
    finally:
        connection.close()

    rejected = _alembic(database_path, "upgrade", "head")
    assert rejected.returncode != 0
    assert "pre-existing account requires manual role reconciliation" in rejected.stderr
    assert "0057_operational_human_scope_permissions" in _current(database_path)
    connection = sqlite3.connect(database_path)
    try:
        assert _known_user_assignments(connection) == before
        assert (
            connection.execute("SELECT 1 FROM audit_events WHERE id = ?", (AUDIT_ID,)).fetchone()
            is None
        )
    finally:
        connection.close()


def test_0058_does_not_extend_unaccented_warehouse_name_to_clean_seed(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "unaccented-clean-seed.db"
    prepared = _alembic(database_path, "upgrade", "0057_operational_human_scope_permissions")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            UPDATE warehouses
            SET name = 'Almacen La Primavera'
            WHERE name = 'Almacén La Primavera'
            """
        )
        connection.commit()
        before = _known_user_assignments(connection)
    finally:
        connection.close()

    rejected = _alembic(database_path, "upgrade", "head")
    assert rejected.returncode != 0
    assert "pre-existing account requires manual role reconciliation" in rejected.stderr
    assert "0057_operational_human_scope_permissions" in _current(database_path)
    connection = sqlite3.connect(database_path)
    try:
        assert _known_user_assignments(connection) == before
        assert (
            connection.execute("SELECT 1 FROM audit_events WHERE id = ?", (AUDIT_ID,)).fetchone()
            is None
        )
    finally:
        connection.close()


def test_0058_fails_closed_for_unapproved_exact_branch_code(tmp_path: Path) -> None:
    database_path = tmp_path / "unapproved-branch-code.db"
    prepared = _alembic(database_path, "upgrade", "0057_operational_human_scope_permissions")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("UPDATE branches SET code = 'SUC07' WHERE name = 'La Primavera'")
        connection.commit()
        before = _known_user_assignments(connection)
    finally:
        connection.close()

    rejected = _alembic(database_path, "upgrade", "head")
    assert rejected.returncode != 0
    assert "pre-existing account requires manual role reconciliation" in rejected.stderr
    assert "0057_operational_human_scope_permissions" in _current(database_path)
    connection = sqlite3.connect(database_path)
    try:
        assert _known_user_assignments(connection) == before
        assert (
            connection.execute("SELECT 1 FROM audit_events WHERE id = ?", (AUDIT_ID,)).fetchone()
            is None
        )
    finally:
        connection.close()


def test_0058_fails_closed_for_suc06_with_divergent_identity(tmp_path: Path) -> None:
    database_path = tmp_path / "suc06-divergent-identity.db"
    prepared = _alembic(database_path, "upgrade", "0057_operational_human_scope_permissions")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("UPDATE branches SET code = 'SUC06' WHERE name = 'La Primavera'")
        connection.execute(
            """
            UPDATE users
            SET display_name = 'Cuenta no aprobada'
            WHERE LOWER(email) = 'caja01laprimavera@kiwi.com'
            """
        )
        connection.commit()
        before = _known_user_assignments(connection)
    finally:
        connection.close()

    rejected = _alembic(database_path, "upgrade", "head")
    assert rejected.returncode != 0
    assert "pre-existing account requires manual role reconciliation" in rejected.stderr
    assert "0057_operational_human_scope_permissions" in _current(database_path)
    connection = sqlite3.connect(database_path)
    try:
        assert _known_user_assignments(connection) == before
        assert (
            connection.execute("SELECT 1 FROM audit_events WHERE id = ?", (AUDIT_ID,)).fetchone()
            is None
        )
    finally:
        connection.close()


def test_0058_fails_closed_for_suc06_with_additional_assignment(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "suc06-additional-assignment.db"
    prepared = _alembic(database_path, "upgrade", "0057_operational_human_scope_permissions")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr

    connection = sqlite3.connect(database_path)
    try:
        connection.execute("UPDATE branches SET code = 'SUC06' WHERE name = 'La Primavera'")
        user_id = connection.execute(
            "SELECT id FROM users WHERE LOWER(email) = 'caja01laprimavera@kiwi.com'"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO user_roles (user_id, role_id, branch_id) VALUES (?, ?, ?)",
            (user_id, ADMIN_ROLE_ID, PILOT_BRANCH_ID),
        )
        connection.commit()
        before = _known_user_assignments(connection)
    finally:
        connection.close()

    rejected = _alembic(database_path, "upgrade", "head")
    assert rejected.returncode != 0
    assert "current assignments require manual role reconciliation" in rejected.stderr
    assert "0057_operational_human_scope_permissions" in _current(database_path)
    connection = sqlite3.connect(database_path)
    try:
        assert _known_user_assignments(connection) == before
        assert (
            connection.execute("SELECT 1 FROM audit_events WHERE id = ?", (AUDIT_ID,)).fetchone()
            is None
        )
    finally:
        connection.close()


def test_0058_fails_closed_when_0049_replaced_preexisting_roles(tmp_path: Path) -> None:
    database_path = tmp_path / "preexisting-user.db"
    prepared = _alembic(database_path, "upgrade", "0048_sync_insumos_and_presentations")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            INSERT INTO users (
                id, organization_id, email, display_name, status, created_at, updated_at
            ) VALUES (?, ?, 'caja01laprimavera@kiwi.com', 'Cuenta existente', 'active', ?, ?)
            """,
            (
                LEGACY_USER_ID,
                ORGANIZATION_ID,
                "2026-08-20 12:00:00+00:00",
                "2026-08-20 12:00:00+00:00",
            ),
        )
        connection.executemany(
            "INSERT INTO user_roles (user_id, role_id, branch_id) VALUES (?, ?, ?)",
            [
                (LEGACY_USER_ID, CAJERO_ROLE_ID, PILOT_BRANCH_ID),
                (LEGACY_USER_ID, ADMIN_ROLE_ID, PILOT_BRANCH_ID),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    legacy_upgrade = _alembic(database_path, "upgrade", "0057_operational_human_scope_permissions")
    assert legacy_upgrade.returncode == 0, legacy_upgrade.stdout + legacy_upgrade.stderr
    connection = sqlite3.connect(database_path)
    try:
        replaced_assignments = _known_user_assignments(connection)
        primavera_branch_id = connection.execute(
            "SELECT id FROM branches WHERE name = 'La Primavera'"
        ).fetchone()[0]
        assert replaced_assignments == {(CAJERO_ROLE_ID, primavera_branch_id)}
    finally:
        connection.close()

    rejected = _alembic(database_path, "upgrade", "head")
    assert rejected.returncode != 0
    assert "pre-existing account requires manual role reconciliation" in rejected.stderr
    assert "0057_operational_human_scope_permissions" in _current(database_path)
    connection = sqlite3.connect(database_path)
    try:
        assert _known_user_assignments(connection) == replaced_assignments
        assert (
            connection.execute("SELECT 1 FROM audit_events WHERE id = ?", (AUDIT_ID,)).fetchone()
            is None
        )
    finally:
        connection.close()


def test_0058_fails_closed_for_fuzzy_branch_selected_by_0049(tmp_path: Path) -> None:
    database_path = tmp_path / "fuzzy-branch.db"
    prepared = _alembic(database_path, "upgrade", "0048_sync_insumos_and_presentations")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr

    connection = sqlite3.connect(database_path)
    try:
        legal_entity_id = connection.execute(
            "SELECT id FROM legal_entities WHERE organization_id = ? LIMIT 1",
            (ORGANIZATION_ID,),
        ).fetchone()[0]
        business_unit_id = connection.execute(
            "SELECT id FROM business_units WHERE organization_id = ? LIMIT 1",
            (ORGANIZATION_ID,),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO branches (
                id, organization_id, legal_entity_id, business_unit_id,
                name, code, timezone, status, city, state, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'Colonia Primavera Norte', 'NORTE',
                      'America/Chihuahua', 'active', 'Culiacán', 'Sinaloa', ?, ?)
            """,
            (
                FUZZY_BRANCH_ID,
                ORGANIZATION_ID,
                legal_entity_id,
                business_unit_id,
                "2026-08-20 12:00:00+00:00",
                "2026-08-20 12:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    legacy_upgrade = _alembic(database_path, "upgrade", "0057_operational_human_scope_permissions")
    assert legacy_upgrade.returncode == 0, legacy_upgrade.stdout + legacy_upgrade.stderr
    rejected = _alembic(database_path, "upgrade", "head")
    assert rejected.returncode != 0
    assert "exact La Primavera branch is missing" in rejected.stderr
    assert "0057_operational_human_scope_permissions" in _current(database_path)


def test_0058_fails_closed_for_additional_current_assignment(tmp_path: Path) -> None:
    database_path = tmp_path / "additional-assignment.db"
    prepared = _alembic(database_path, "upgrade", "0057_operational_human_scope_permissions")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    connection = sqlite3.connect(database_path)
    try:
        user_id = connection.execute(
            "SELECT id FROM users WHERE LOWER(email) = 'caja01laprimavera@kiwi.com'"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO user_roles (user_id, role_id, branch_id) VALUES (?, ?, ?)",
            (user_id, ADMIN_ROLE_ID, PILOT_BRANCH_ID),
        )
        connection.commit()
        before = _known_user_assignments(connection)
    finally:
        connection.close()

    rejected = _alembic(database_path, "upgrade", "head")
    assert rejected.returncode != 0
    assert "current assignments require manual role reconciliation" in rejected.stderr
    assert "0057_operational_human_scope_permissions" in _current(database_path)
    connection = sqlite3.connect(database_path)
    try:
        assert _known_user_assignments(connection) == before
        assert (
            connection.execute("SELECT 1 FROM audit_events WHERE id = ?", (AUDIT_ID,)).fetchone()
            is None
        )
    finally:
        connection.close()


def _postgres_url() -> str:
    url = os.environ.get(POSTGRES_ENV)
    if not url:
        pytest.skip(f"{POSTGRES_ENV} is required for opt-in PostgreSQL tests")
    parsed = urlparse(url)
    database = parsed.path.lstrip("/")
    if (
        not parsed.scheme.startswith("postgres")
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or not database.startswith("seed0058_")
    ):
        raise RuntimeError(f"{POSTGRES_ENV} must target a local isolated seed0058_* database")
    return url


def _postgres_alembic(url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.pop("DATABASE_URL", None)
    environment["RESTAURANTOS_DATABASE_URL"] = url
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *arguments],
        cwd=API_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_postgres_0058_verifies_clean_seed_and_blocks_downgrade() -> None:
    url = _postgres_url()
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
    finally:
        engine.dispose()

    prepared = _postgres_alembic(url, "upgrade", "0057_operational_human_scope_permissions")
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as connection:
            before = set(
                connection.execute(
                    sa.text(
                        """
                        SELECT user_roles.role_id, user_roles.branch_id
                        FROM user_roles JOIN users ON users.id = user_roles.user_id
                        WHERE LOWER(users.email) = 'caja01laprimavera@kiwi.com'
                        """
                    )
                ).tuples()
            )
    finally:
        engine.dispose()

    upgraded = _postgres_alembic(url, "upgrade", "0058_verify_0049_la_primavera_seed")
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as connection:
            after = set(
                connection.execute(
                    sa.text(
                        """
                        SELECT user_roles.role_id, user_roles.branch_id
                        FROM user_roles JOIN users ON users.id = user_roles.user_id
                        WHERE LOWER(users.email) = 'caja01laprimavera@kiwi.com'
                        """
                    )
                ).tuples()
            )
            assert after == before
            assert (
                connection.execute(
                    sa.text("SELECT action FROM audit_events WHERE id = :id"),
                    {"id": AUDIT_ID},
                ).scalar_one()
                == "migration.0049_seed_state_verified"
            )
    finally:
        engine.dispose()

    downgrade = _postgres_alembic(url, "downgrade", "0057_operational_human_scope_permissions")
    assert downgrade.returncode != 0
    assert "forward-only" in downgrade.stderr
