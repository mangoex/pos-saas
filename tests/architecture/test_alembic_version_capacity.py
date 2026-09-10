"""Architecture and integration tests for DB-001 (Alembic revision capacity).

These tests verify that the migration chain:

- has no revision identifier longer than 128 characters;
- has the bridge revision ``0013a_expand_version_num`` (<=32 chars) between
  ``0013_pos_cash_rbac_permissions`` and ``0014_legacy_caja_role_permissions``;
- has a single head and is linear (no branches);
- can run ``upgrade head`` and ``downgrade``/``upgrade`` round-trips on SQLite;
- issues the PostgreSQL ``ALTER TABLE alembic_version ... TYPE VARCHAR(128)``
  statement in the upgrade path and ``VARCHAR(32)`` in the downgrade path,
  while leaving SQLite untouched (no ``ALTER COLUMN``).
"""

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
import unittest.mock
from io import StringIO
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = ROOT / "apps" / "api" / "alembic" / "versions"
API_DIR = ROOT / "apps" / "api"
BRIDGE_REVISION = "0013a_expand_version_num"
PARENT_REVISION = "0013_pos_cash_rbac_permissions"
CHILD_REVISION = "0014_legacy_caja_role_permissions"
HEAD_REVISION = "0086_secure_customer_feedback_reference"
REVERSIBLE_REVISION = "0057_operational_human_scope_permissions"
REVERSIBLE_PARENT_REVISION = "0056_repair_0047_canonical_roles"
MAX_REVISION_LENGTH = 128
BRIDGE_MAX_LENGTH = 32


def _read_revisions() -> dict[str, dict[str, str | None]]:
    """Parse every migration file's revision/down_revision via AST.

    Returns ``{revision_id: {"file": filename, "down_revision": parent_or_None}}``.
    """
    revisions: dict[str, dict[str, str | None]] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name.endswith(".bak"):
            continue
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        revision_value: str | None = None
        down_value: str | None = None
        for node in module.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "revision":
                        revision_value = _ast_str(node.value)
                    if isinstance(target, ast.Name) and target.id == "down_revision":
                        down_value = _ast_str(node.value)
            # Also handle annotated assignments (revision: str = "...").
            if isinstance(node, ast.AnnAssign):
                if (
                    isinstance(node.target, ast.Name)
                    and node.target.id == "revision"
                    and node.value is not None
                ):
                    revision_value = _ast_str(node.value)
                if (
                    isinstance(node.target, ast.Name)
                    and node.target.id == "down_revision"
                    and node.value is not None
                ):
                    down_value = _ast_str(node.value)
        if revision_value is None:
            continue
        revisions[revision_value] = {"file": path.name, "down_revision": down_value}
    return revisions


def _ast_str(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


# --- Structural tests (no database) ----------------------------------------


def test_no_revision_exceeds_128_characters() -> None:
    revisions = _read_revisions()
    too_long = [rev for rev in revisions if len(rev) > MAX_REVISION_LENGTH]
    assert too_long == [], (
        f"Revision identifiers must not exceed {MAX_REVISION_LENGTH} characters; "
        f"found: {too_long}"
    )


def test_bridge_revision_fits_in_32_characters() -> None:
    assert len(BRIDGE_REVISION) <= BRIDGE_MAX_LENGTH, (
        f"Bridge revision {BRIDGE_REVISION!r} must fit in {BRIDGE_MAX_LENGTH} "
        f"characters so it can be registered before the column is widened."
    )


def test_bridge_exists_and_links_0013_to_0014() -> None:
    revisions = _read_revisions()
    assert BRIDGE_REVISION in revisions, (
        f"Bridge revision {BRIDGE_REVISION} not found in migrations"
    )
    assert revisions[BRIDGE_REVISION]["down_revision"] == PARENT_REVISION, (
        f"Bridge must descend from {PARENT_REVISION}, "
        f"got {revisions[BRIDGE_REVISION]['down_revision']!r}"
    )
    assert CHILD_REVISION in revisions, f"{CHILD_REVISION} not found in migrations"
    assert revisions[CHILD_REVISION]["down_revision"] == BRIDGE_REVISION, (
        f"{CHILD_REVISION} must descend from {BRIDGE_REVISION} (repointed), "
        f"got {revisions[CHILD_REVISION]['down_revision']!r}"
    )


def test_chain_is_linear_with_single_head() -> None:
    revisions = _read_revisions()
    # Every down_revision (except None) must reference an existing revision.
    for rev_id, meta in revisions.items():
        parent = meta["down_revision"]
        if parent is not None:
            assert parent in revisions, (
                f"Revision {rev_id} points to unknown parent {parent!r}"
            )

    # Heads = revisions that are not referenced as a down_revision by anyone.
    referenced_as_parent: set[str] = set()
    for meta in revisions.values():
        parent = meta["down_revision"]
        if parent is not None:
            referenced_as_parent.add(parent)
    heads = sorted(set(revisions) - referenced_as_parent)
    assert heads == [HEAD_REVISION], (
        f"Expected single head {HEAD_REVISION!r}, got {heads}"
    )

    # No duplicate parents => no branches.
    parents = [meta["down_revision"] for meta in revisions.values() if meta["down_revision"]]
    duplicates = {p for p in parents if parents.count(p) > 1}
    assert duplicates == set(), f"Multiple revisions share a parent (branch): {duplicates}"


# --- Operation-level tests of the bridge migration (PostgreSQL DDL) --------
# These tests execute the bridge's upgrade()/downgrade() against a captured
# `op` proxy so we can assert exactly which op.alter_column calls are made,
# and compile the complete operations with the PostgreSQL dialect to prove the
# DDL contains VARCHAR(128)/VARCHAR(32) as literals with no placeholders.

PLACEHOLDERS = [":length", "%(length)s", "$1", "?"]


def _load_bridge_module() -> Any:
    """Import the bridge migration file as an isolated module."""
    bridge_path = VERSIONS_DIR / "202607100200_0013a_expand_version_num.py"
    spec = importlib.util.spec_from_file_location("bridge_module", bridge_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingOp:
    """Minimal proxy that records op.alter_column calls and serves op.get_bind()."""

    def __init__(self, dialect_name: str, current_revision: str | None) -> None:
        self._dialect_name = dialect_name
        self._current_revision = current_revision
        self.alter_calls: list[dict[str, Any]] = []

    def get_bind(self) -> Any:
        bind = unittest.mock.MagicMock()
        bind.dialect.name = self._dialect_name
        # For the downgrade guard: SELECT version_num FROM alembic_version.
        bind.execute.return_value.scalar.return_value = self._current_revision
        return bind

    def alter_column(self, *args: Any, **kwargs: Any) -> None:
        self.alter_calls.append({"args": args, "kwargs": kwargs})


def _string_length(type_obj: Any) -> int:
    """Return the length attribute of a sa.String(N) type instance."""
    assert isinstance(type_obj, sa.String), f"Expected sa.String, got {type(type_obj)}"
    assert type_obj.length is not None, "sa.String must have an explicit length"
    return int(type_obj.length)


def _compile_alter_column_ddl(existing_type: Any, new_type: Any) -> str:
    """Compile the complete Alembic ALTER COLUMN for PostgreSQL."""
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    operations = Operations(context)
    operations.alter_column(
        "alembic_version",
        "version_num",
        existing_type=existing_type,
        type_=new_type,
    )
    return output.getvalue().strip()


def test_upgrade_calls_alter_column_32_to_128() -> None:
    """upgrade() on PostgreSQL must call op.alter_column widening 32 -> 128."""
    module = _load_bridge_module()
    fake_op = _RecordingOp("postgresql", current_revision=BRIDGE_REVISION)

    with unittest.mock.patch.object(module, "op", fake_op):
        module.upgrade()

    assert len(fake_op.alter_calls) == 1, (
        f"Expected exactly one op.alter_column in upgrade, got {len(fake_op.alter_calls)}"
    )
    call = fake_op.alter_calls[0]
    assert call["args"] == ("alembic_version", "version_num"), (
        f"Expected ('alembic_version', 'version_num'), got {call['args']}"
    )
    existing = call["kwargs"].get("existing_type")
    new_type = call["kwargs"].get("type_")
    assert _string_length(existing) == 32, f"existing_type must be String(32), got {existing}"
    assert _string_length(new_type) == 128, f"type_ must be String(128), got {new_type}"

    # Compile the complete Alembic operation and reject bound placeholders.
    ddl = _compile_alter_column_ddl(existing, new_type)
    assert ddl == (
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128);"
    )
    for ph in PLACEHOLDERS:
        assert ph not in ddl, f"Placeholder {ph!r} found in upgrade DDL: {ddl!r}"


def test_downgrade_calls_alter_column_128_to_32_when_revision_fits() -> None:
    """downgrade() on PostgreSQL must reduce 128 -> 32 when the revision fits."""
    module = _load_bridge_module()
    # Bridge revision is 24 chars, well within 32; guard must allow shrink.
    fake_op = _RecordingOp("postgresql", current_revision=BRIDGE_REVISION)

    with unittest.mock.patch.object(module, "op", fake_op):
        module.downgrade()

    assert len(fake_op.alter_calls) == 1, (
        f"Expected exactly one op.alter_column in downgrade, got {len(fake_op.alter_calls)}"
    )
    call = fake_op.alter_calls[0]
    assert call["args"] == ("alembic_version", "version_num")
    existing = call["kwargs"].get("existing_type")
    new_type = call["kwargs"].get("type_")
    assert _string_length(existing) == 128, f"existing_type must be String(128), got {existing}"
    assert _string_length(new_type) == 32, f"type_ must be String(32), got {new_type}"

    ddl = _compile_alter_column_ddl(existing, new_type)
    assert ddl == (
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32);"
    )
    for ph in PLACEHOLDERS:
        assert ph not in ddl, f"Placeholder {ph!r} found in downgrade DDL: {ddl!r}"


def test_downgrade_guard_rejects_revision_longer_than_32() -> None:
    """The downgrade guard must abort before shrinking if revision > 32 chars.

    When the current revision would not fit in VARCHAR(32), the bridge must
    raise RuntimeError and must NOT call op.alter_column at all.
    """
    module = _load_bridge_module()
    # 0015 is 37 chars; simulating a current revision that would not fit.
    long_revision = "0015_business_units_operational_roles"
    assert len(long_revision) > 32
    fake_op = _RecordingOp("postgresql", current_revision=long_revision)

    with unittest.mock.patch.object(module, "op", fake_op):
        try:
            module.downgrade()
        except RuntimeError:
            pass
        else:
            raise AssertionError(
                "downgrade() should have raised RuntimeError when current revision "
                "exceeds 32 characters"
            )

    assert fake_op.alter_calls == [], (
        "Guard must prevent op.alter_column from being called when the current "
        "revision would not fit in VARCHAR(32)"
    )


def test_sqlite_branch_does_not_call_alter_column() -> None:
    """On SQLite, neither upgrade() nor downgrade() may call op.alter_column."""
    module = _load_bridge_module()
    for method_name in ("upgrade", "downgrade"):
        fake_op = _RecordingOp("sqlite", current_revision=BRIDGE_REVISION)
        with unittest.mock.patch.object(module, "op", fake_op):
            getattr(module, method_name)()
        assert fake_op.alter_calls == [], (
            f"{method_name}() must not call op.alter_column on SQLite; "
            f"recorded calls: {fake_op.alter_calls}"
        )


def test_0014_only_header_changed_not_body() -> None:
    """Confirm 0014's upgrade()/downgrade() bodies are unchanged in spirit.

    We only assert that the CAJA_PERMISSION_CODES constant and the
    INSERT/DELETE role_permissions logic remain present, so the repoint did
    not accidentally alter the migration's business effect.
    """
    source = (
        VERSIONS_DIR / "202607100245_0014_legacy_caja_role_permissions.py"
    ).read_text(encoding="utf-8")
    assert "CAJA_PERMISSION_CODES" in source
    assert "INSERT INTO role_permissions" in source
    assert "DELETE FROM role_permissions" in source
    assert 'down_revision: str | None = "0013a_expand_version_num"' in source
    assert "Revises: 0013a_expand_version_num" in source


# --- Integration tests on SQLite -------------------------------------------


def _alembic(args: list[str], database_url: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "RESTAURANTOS_DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", *args],
        cwd=API_DIR,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_sqlite_upgrade_from_0013_reaches_head(tmp_path: Path) -> None:
    database_path = tmp_path / "db-001-upgrade.db"
    database_url = f"sqlite+pysqlite:///{database_path}"

    # Bring the DB up to 0013 first.
    result = _alembic(["upgrade", PARENT_REVISION], database_url)
    assert result.returncode == 0, result.stderr

    # Then upgrade the rest of the chain, which crosses the bridge.
    result = _alembic(["upgrade", "head"], database_url)
    assert result.returncode == 0, result.stderr

    result = _alembic(["current"], database_url)
    assert HEAD_REVISION in result.stdout, (
        f"Expected head {HEAD_REVISION} after upgrade, got: {result.stdout}"
    )


def test_sqlite_latest_forward_migration_roundtrip_without_history(tmp_path: Path) -> None:
    database_path = tmp_path / "db-001-roundtrip.db"
    database_url = f"sqlite+pysqlite:///{database_path}"

    # The operational permission migration is reversible; the following seed
    # verification and its earlier RBAC data repair are intentionally forward-only.
    result = _alembic(["upgrade", REVERSIBLE_PARENT_REVISION], database_url)
    assert result.returncode == 0, result.stderr
    assert _alembic(["upgrade", REVERSIBLE_REVISION], database_url).returncode == 0

    result = _alembic(["downgrade", REVERSIBLE_PARENT_REVISION], database_url)
    assert result.returncode == 0, result.stderr

    result = _alembic(["current"], database_url)
    assert REVERSIBLE_PARENT_REVISION in result.stdout, (
        f"Expected {REVERSIBLE_PARENT_REVISION} after downgrade, got: {result.stdout}"
    )

    # Upgrade through the forward-only seed verification and confirm its
    # immediate downgrade is blocked without touching the earlier repair.
    result = _alembic(["upgrade", "head"], database_url)
    assert result.returncode == 0, result.stderr

    result = _alembic(["current"], database_url)
    assert HEAD_REVISION in result.stdout, (
        f"Expected head {HEAD_REVISION} after re-upgrade, got: {result.stdout}"
    )
    result = _alembic(["downgrade", REVERSIBLE_REVISION], database_url)
    assert result.returncode != 0
    assert "forward-only" in result.stderr


def test_sqlite_bridge_does_not_alter_column(tmp_path: Path) -> None:
    """On SQLite the bridge must be a no-op: no ALTER COLUMN statement runs."""
    database_path = tmp_path / "db-001-sqlite-noop.db"
    database_url = f"sqlite+pysqlite:///{database_path}"

    assert _alembic(["upgrade", PARENT_REVISION], database_url).returncode == 0

    # Capture stdout/stderr when crossing the bridge on SQLite.
    result = _alembic(["upgrade", CHILD_REVISION], database_url)
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "ALTER" not in combined.upper(), (
        f"SQLite bridge must not emit ALTER; output was: {combined}"
    )
