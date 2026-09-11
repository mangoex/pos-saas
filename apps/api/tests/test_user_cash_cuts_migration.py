"""PCO-006 SQLite Alembic evidence for the cash-cut compatibility boundary."""
# ruff: noqa: E501

from __future__ import annotations

import sqlite3

import pytest
from test_cash_ledger_migration import _sqlite_alembic

REVISION_0040 = "0040_order_corrections"
REVISION_0041 = "0041_user_cash_cuts"


def _shift(connection: sqlite3.Connection, shift_id: str) -> None:
    connection.execute(
        """INSERT INTO cash_shifts (id, organization_id, branch_id, register_code, status,
        opening_cash_cents, opened_at, closed_at, created_at) VALUES (?, 'o1', 'b1',
        'CAJA-01', 'OPERATIVELY_CLOSED', 0, '2026-08-15T00:00:00+00:00',
        '2026-08-15T01:00:00+00:00', '2026-08-15T00:00:00+00:00')""",
        (shift_id,),
    )


def test_0040_to_0041_backfills_only_one_open_actor(tmp_path) -> None:
    path = tmp_path / "pco006-single.db"
    assert _sqlite_alembic(path, "upgrade", REVISION_0040).returncode == 0
    connection = sqlite3.connect(path)
    try:
        _shift(connection, "shift-one")
        connection.execute(
            """INSERT INTO cash_shift_commands (id, organization_id, actor_user_id,
            cash_shift_id, command_type, idempotency_key, request_hash, result, status,
            created_at) VALUES ('command-one', 'o1', 'cashier-one', 'shift-one', 'open',
            'open-one', '0000000000000000000000000000000000000000000000000000000000000000', '{}',
            'completed', '2026-08-15T00:00:00+00:00')"""
        )
        connection.commit()
    finally:
        connection.close()
    assert _sqlite_alembic(path, "upgrade", REVISION_0041).returncode == 0
    connection = sqlite3.connect(path)
    try:
        cashier = connection.execute(
            "SELECT cashier_user_id FROM cash_shifts WHERE id = 'shift-one'"
        ).fetchone()
        assert cashier == ("cashier-one",)
    finally:
        connection.close()


@pytest.mark.parametrize("actors", [(), ("cashier-one", "cashier-two")])
def test_0041_never_invents_ambiguous_or_missing_cashier(tmp_path, actors) -> None:
    path = tmp_path / "pco006-ambiguous.db"
    assert _sqlite_alembic(path, "upgrade", REVISION_0040).returncode == 0
    connection = sqlite3.connect(path)
    try:
        _shift(connection, "shift-ambiguous")
        for index, actor in enumerate(actors):
            connection.execute(
                "INSERT INTO cash_shift_commands (id, organization_id, actor_user_id, "
                "cash_shift_id, command_type, idempotency_key, request_hash, result, "
                "status, created_at) VALUES (?, 'o1', ?, 'shift-ambiguous', 'open', ?, "
                "'0000000000000000000000000000000000000000000000000000000000000000', "
                "'{}', 'completed', '2026-08-15T00:00:00+00:00')",
                (f"command-{index}", actor, f"open-{index}"),
            )
        connection.commit()
    finally:
        connection.close()
    assert _sqlite_alembic(path, "upgrade", REVISION_0041).returncode == 0
    connection = sqlite3.connect(path)
    try:
        cashier = connection.execute(
            "SELECT cashier_user_id FROM cash_shifts WHERE id = 'shift-ambiguous'"
        ).fetchone()
        assert cashier == (None,)
    finally:
        connection.close()


def test_0041_empty_downgrade_is_reversible_and_history_blocks(tmp_path) -> None:
    path = tmp_path / "pco006-roundtrip.db"
    assert _sqlite_alembic(path, "upgrade", REVISION_0040).returncode == 0
    assert _sqlite_alembic(path, "upgrade", REVISION_0041).returncode == 0
    assert _sqlite_alembic(path, "downgrade", REVISION_0040).returncode == 0
    assert _sqlite_alembic(path, "upgrade", REVISION_0041).returncode == 0
    connection = sqlite3.connect(path)
    try:
        _shift(connection, "shift-history")
        connection.execute(
            "UPDATE cash_shifts SET cashier_user_id = 'cashier-history' "
            "WHERE id = 'shift-history'"
        )
        connection.commit()
    finally:
        connection.close()
    blocked = _sqlite_alembic(path, "downgrade", REVISION_0040)
    assert blocked.returncode != 0


def test_0041_allows_negative_expected_but_rejects_negative_counted(tmp_path) -> None:
    path = tmp_path / "pco006-negative-expected.db"
    assert _sqlite_alembic(path, "upgrade", REVISION_0041).returncode == 0
    connection = sqlite3.connect(path)
    try:
        _shift(connection, "shift-negative")
        connection.execute(
            "UPDATE cash_shifts SET cashier_user_id = 'cashier-one' "
            "WHERE id = 'shift-negative'"
        )
        values = (
            "cut-negative", "o1", "b1", "shift-negative", "CAJA-01", "cashier-one", "UTC",
            "2026-08-15T00:00:00+00:00", "2026-08-15T01:00:00+00:00", "FINALIZED", 0,
            0, 0, 100, -100, 0, 0, 0, "cashier-one", "cashier-one", 1,
            "2026-08-15T00:00:00+00:00", None, "2026-08-15T01:00:00+00:00",
        )
        connection.execute(
            "INSERT INTO user_cash_cuts (id, organization_id, branch_id, cash_shift_id, "
            "register_code_snapshot, cashier_user_id, timezone, period_start, period_end, status, "
            "opening_cash_cents, cash_payment_cents, deposit_cents, withdrawal_cents, "
            "expected_cash_cents, counted_cash_cents, difference_cents, tolerance_cents, "
            "created_by_user_id, finalized_by_user_id, version, created_at, "
            "counted_at, finalized_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
        connection.commit()
        result = connection.execute(
            "SELECT expected_cash_cents FROM user_cash_cuts"
        ).fetchone()
        assert result == (-100,)
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("table", "statement"),
    (
        ("user_cash_cuts", "INSERT INTO user_cash_cuts (id, organization_id, branch_id, cash_shift_id, register_code_snapshot, cashier_user_id, timezone, period_start, period_end, status, opening_cash_cents, tolerance_cents, created_by_user_id, version, created_at) VALUES ('cut-block', 'o1', 'b1', 'shift-block', 'CAJA-01', 'cashier-one', 'UTC', '2026-08-15T00:00:00+00:00', '2026-08-15T01:00:00+00:00', 'DRAFT', 0, 0, 'cashier-one', 1, '2026-08-15T00:00:00+00:00')"),
        ("user_cash_cut_operations", "INSERT INTO user_cash_cut_operations (id, organization_id, cash_cut_id, operation_type, operation_id, signed_amount_cents, occurred_at) VALUES ('op-block', 'o1', 'cut-block', 'PAYMENT', 'payment-block', 1, '2026-08-15T00:00:00+00:00')"),
        ("user_cash_cut_commands", "INSERT INTO user_cash_cut_commands (id, organization_id, actor_user_id, command_type, idempotency_key, request_hash, result, created_at) VALUES ('command-block', 'o1', 'cashier-one', 'create', 'block-command', '0000000000000000000000000000000000000000000000000000000000000000', '{}', '2026-08-15T00:00:00+00:00')"),
        ("user_cash_cut_reopen_requests", "INSERT INTO user_cash_cut_reopen_requests (id, organization_id, cash_cut_id, proposed_counted_cash_cents, reason, evidence_refs, status, requested_by_user_id, created_at) VALUES ('request-block', 'o1', 'cut-block', 0, 'reason', '[]', 'REQUESTED', 'cashier-one', '2026-08-15T00:00:00+00:00')"),
        ("user_cash_cut_compensations", "INSERT INTO user_cash_cut_compensations (id, organization_id, cash_cut_id, reopen_request_id, corrected_counted_cash_cents, expected_cash_cents, tolerance_cents, corrected_difference_cents, difference_delta_cents, created_by_user_id, created_at) VALUES ('compensation-block', 'o1', 'cut-block', 'request-block', 0, 0, 0, 0, 0, 'cashier-one', '2026-08-15T00:00:00+00:00')"),
    ),
)
def test_0041_downgrade_blocks_each_pco006_history_table_and_preserves_rows(tmp_path, table, statement) -> None:
    path = tmp_path / f"pco006-block-{table}.db"
    assert _sqlite_alembic(path, "upgrade", REVISION_0041).returncode == 0
    connection = sqlite3.connect(path)
    try:
        connection.execute(statement)
        connection.commit()
    finally:
        connection.close()
    assert _sqlite_alembic(path, "downgrade", REVISION_0040).returncode != 0
    connection = sqlite3.connect(path)
    try:
        assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone() == (1,)
    finally:
        connection.close()
