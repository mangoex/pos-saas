from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from uuid import UUID

UTC = timezone.utc
COMMAND_TYPE = "cash.movement.create.v1"
SCHEMA_VERSION = 1
logger = logging.getLogger(__name__)


class InvalidCommandEnvelope(ValueError):
    pass


class GatewayOutbox:
    """Versioned SQLite WAL outbox for the single PCO-008 cash command."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def enqueue_command(self, envelope: dict[str, Any]) -> dict[str, Any]:
        _validate_command(envelope)
        request_hash = hashlib.sha256(_canonical(envelope).encode("utf-8")).hexdigest()
        now = _now_iso()
        with self._connect() as connection:
            connection.execute("begin immediate")
            existing = connection.execute(
                "select * from local_commands where idempotency_key = ? or command_id = ?",
                (envelope["idempotency_key"], envelope["command_id"]),
            ).fetchone()
            if existing:
                if existing["request_hash"] != request_hash:
                    raise InvalidCommandEnvelope("idempotency_conflict")
                return _row_to_command(existing)
            connection.execute(
                """insert into local_commands (
                    command_id, idempotency_key, organization_id, branch_id, source_device_id,
                    actor_user_id, command_type, offline_grant, payload_json, request_hash, status,
                    occurred_at, accepted_at, created_at, next_attempt_at, attempts
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_SYNC', ?, ?, ?, ?, 0)""",
                (
                    envelope["command_id"],
                    envelope["idempotency_key"],
                    envelope["organization_id"],
                    envelope["branch_id"],
                    envelope["source_device_id"],
                    envelope["actor_user_id"],
                    envelope["command_type"],
                    envelope["offline_grant"],
                    json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":")),
                    request_hash,
                    envelope["occurred_at"],
                    envelope["accepted_at"],
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "select * from local_commands where command_id = ?", (envelope["command_id"],)
            ).fetchone()
        command = _row_to_command(row)
        _record("pco008.outbox.enqueued", command)
        return command

    def list_pending_commands(self) -> list[dict[str, Any]]:
        return self._list_dispatchable("status = 'PENDING_SYNC'")

    def claim_pending_commands(
        self, *, now: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise InvalidCommandEnvelope("invalid_claim_limit")
        claim_time = now or _now_iso()
        with self._connect() as connection:
            connection.execute("begin immediate")
            rows = connection.execute(
                """select id from local_commands
                   where status = 'PENDING_SYNC' and command_type = ?
                     and request_hash is not null and offline_grant is not null
                     and next_attempt_at <= ?
                   order by created_at, id limit ?""",
                (COMMAND_TYPE, claim_time, limit),
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            if not ids:
                return []
            connection.executemany(
                """update local_commands set status = 'SYNCING', syncing_at = ?
                   where id = ? and status = 'PENDING_SYNC'""",
                [(claim_time, command_id) for command_id in ids],
            )
            placeholders = ",".join("?" for _ in ids)
            claimed = connection.execute(
                f"""select * from local_commands where id in ({placeholders})
                    and status = 'SYNCING' and syncing_at = ? order by id""",
                (*ids, claim_time),
            ).fetchall()
        return [_row_to_command(row) for row in claimed]

    def recover_syncing(self, *, now: str | None = None) -> int:
        recovery_time = now or _now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """update local_commands
                   set status = 'PENDING_SYNC', syncing_at = null, next_attempt_at = ?
                   where status = 'SYNCING'""",
                (recovery_time,),
            )
        return int(cursor.rowcount)

    def release_transport_failure(
        self, idempotency_key: str, *, now: str | None = None
    ) -> dict[str, Any]:
        failure_time = now or _now_iso()
        with self._connect() as connection:
            row = self._require_row(connection, idempotency_key)
            if row["status"] not in {"SYNCING", "PENDING_SYNC"}:
                raise InvalidCommandEnvelope("command_state_conflict")
            attempts = int(row["attempts"]) + 1
            delay = min(60 * (2 ** min(attempts - 1, 4)), 960)
            connection.execute(
                """update local_commands
                   set status = 'PENDING_SYNC', attempts = ?, syncing_at = null,
                       next_attempt_at = ? where id = ?""",
                (attempts, _plus_seconds(failure_time, delay), row["id"]),
            )
            command = _row_to_command(self._require_row(connection, idempotency_key))
        _record("pco008.outbox.retry", command)
        return command

    def mark_conflict(self, idempotency_key: str, code: str) -> dict[str, Any]:
        safe_code = str(code).strip()[:96]
        if not safe_code:
            raise InvalidCommandEnvelope("conflict_code_required")
        with self._connect() as connection:
            row = self._require_row(connection, idempotency_key)
            connection.execute(
                """update local_commands
                   set status = 'CONFLICT', conflict_code = ?, syncing_at = null
                   where id = ?""",
                (safe_code, row["id"]),
            )
            command = _row_to_command(self._require_row(connection, idempotency_key))
        _record("pco008.outbox.conflict", command)
        return command

    def mark_confirmed(self, idempotency_key: str, checkpoint: int) -> dict[str, Any]:
        if isinstance(checkpoint, bool) or not isinstance(checkpoint, int) or checkpoint <= 0:
            raise InvalidCommandEnvelope("checkpoint must be positive")
        now = _now_iso()
        with self._connect() as connection:
            connection.execute("begin immediate")
            row = self._require_row(connection, idempotency_key)
            connection.execute(
                """update local_commands
                   set status = 'CONFIRMED', confirmed_checkpoint = ?, confirmed_at = ?,
                       syncing_at = null where id = ?""",
                (checkpoint, now, row["id"]),
            )
            connection.execute(
                """insert into sync_state (branch_id, last_checkpoint, updated_at)
                   values (?, ?, ?)
                   on conflict(branch_id) do update set
                     last_checkpoint = max(last_checkpoint, excluded.last_checkpoint),
                     updated_at = excluded.updated_at""",
                (row["branch_id"], checkpoint, now),
            )
            command = _row_to_command(self._require_row(connection, idempotency_key))
        _record("pco008.outbox.confirmed", command)
        return command

    def list_local_status(self, identity: dict[str, str]) -> list[dict[str, Any]]:
        required = {"organization_id", "branch_id", "source_device_id"}
        if set(identity) != required:
            raise InvalidCommandEnvelope("invalid_gateway_identity")
        with self._connect() as connection:
            rows = connection.execute(
                """select * from local_commands
                   where organization_id = ? and branch_id = ? and source_device_id = ?
                     and command_type = ? order by created_at, id""",
                (
                    identity["organization_id"],
                    identity["branch_id"],
                    identity["source_device_id"],
                    COMMAND_TYPE,
                ),
            ).fetchall()
        return [_redact_command(_row_to_command(row)) for row in rows]

    def get_command(self, idempotency_key: str) -> dict[str, Any]:
        with self._connect() as connection:
            return _row_to_command(self._require_row(connection, idempotency_key))

    def get_sync_state(self, branch_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "select * from sync_state where branch_id = ?", (branch_id,)
            ).fetchone()
        return (
            dict(row)
            if row
            else {"branch_id": branch_id, "last_checkpoint": 0, "updated_at": None}
        )

    def journal_mode(self) -> str:
        with self._connect() as connection:
            return str(connection.execute("pragma journal_mode").fetchone()[0]).lower()

    def downgrade_to_v0(self) -> None:
        with self._connect() as connection:
            connection.execute("begin immediate")
            if int(connection.execute("pragma user_version").fetchone()[0]) != SCHEMA_VERSION:
                raise InvalidCommandEnvelope("downgrade_not_applicable")
            if connection.execute(
                "select 1 from local_commands where command_type = ? limit 1", (COMMAND_TYPE,)
            ).fetchone():
                raise InvalidCommandEnvelope("downgrade_blocked_pco008_history")
            connection.execute("alter table local_commands rename to local_commands_v1")
            _create_v0_schema(connection)
            connection.execute(
                """insert into local_commands (
                    id, command_id, idempotency_key, organization_id, branch_id, source_device_id,
                    command_type, payload_json, status, occurred_at, created_at,
                    confirmed_checkpoint, confirmed_at
                ) select id, command_id, idempotency_key, organization_id, branch_id,
                    source_device_id, command_type, payload_json,
                    case when status = 'PENDING_SYNC' then 'PENDING' else status end,
                    occurred_at, created_at, confirmed_checkpoint, confirmed_at
                  from local_commands_v1"""
            )
            connection.execute("drop table local_commands_v1")
            connection.execute("pragma user_version = 0")

    def _list_dispatchable(self, predicate: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                f"""select * from local_commands where {predicate} and command_type = ?
                    and request_hash is not null and offline_grant is not null
                    order by created_at, id""",
                (COMMAND_TYPE,),
            ).fetchall()
        return [_row_to_command(row) for row in rows]

    @staticmethod
    def _require_row(connection: sqlite3.Connection, key: str) -> sqlite3.Row:
        row = connection.execute(
            "select * from local_commands where idempotency_key = ?", (key,)
        ).fetchone()
        if row is None:
            raise InvalidCommandEnvelope("command was not found")
        return cast(sqlite3.Row, row)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("pragma journal_mode = wal")
            connection.execute("begin immediate")
            version = int(connection.execute("pragma user_version").fetchone()[0])
            has_commands = connection.execute(
                "select 1 from sqlite_master where type = 'table' and name = 'local_commands'"
            ).fetchone()
            if version == 0 and has_commands:
                self._migrate_v0_to_v1(connection)
            elif version == 0:
                _create_v1_schema(connection)
                connection.execute(f"pragma user_version = {SCHEMA_VERSION}")
            elif version != SCHEMA_VERSION:
                raise InvalidCommandEnvelope("unsupported_sqlite_schema_version")
            _create_sync_state_schema(connection)

    @staticmethod
    def _migrate_v0_to_v1(connection: sqlite3.Connection) -> None:
        connection.execute("alter table local_commands rename to local_commands_v0")
        _create_v1_schema(connection)
        connection.execute(
            """insert into local_commands (
                id, command_id, idempotency_key, organization_id, branch_id, source_device_id,
                actor_user_id, command_type, offline_grant, payload_json, request_hash, status,
                occurred_at, accepted_at, created_at, next_attempt_at, attempts,
                syncing_at, confirmed_checkpoint, confirmed_at, conflict_code
            ) select id, command_id, idempotency_key, organization_id, branch_id, source_device_id,
                null, command_type, null, payload_json, null,
                case when status = 'PENDING' then 'PENDING_SYNC' else status end,
                occurred_at, null, created_at, created_at, 0, null,
                confirmed_checkpoint, confirmed_at, null from local_commands_v0"""
        )
        connection.execute("drop table local_commands_v0")
        connection.execute(f"pragma user_version = {SCHEMA_VERSION}")

    def _connect(self) -> sqlite3.Connection:
        _prepare_private_database_file(self.database_path)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection


def _prepare_private_database_file(path: Path) -> None:
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if path.is_symlink():
        raise InvalidCommandEnvelope("unsafe_sqlite_path")
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise InvalidCommandEnvelope("unsafe_sqlite_path") from exc
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise InvalidCommandEnvelope("unsafe_sqlite_path")
        if os.name != "nt":
            if file_stat.st_uid != os.geteuid():
                raise InvalidCommandEnvelope("unsafe_sqlite_path")
            os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


def _create_v1_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """create table local_commands (
            id integer primary key autoincrement,
            command_id text not null unique,
            idempotency_key text not null unique,
            organization_id text not null,
            branch_id text not null,
            source_device_id text not null,
            actor_user_id text,
            command_type text not null,
            offline_grant text,
            payload_json text not null,
            request_hash text,
            status text not null,
            occurred_at text not null,
            accepted_at text,
            created_at text not null,
            next_attempt_at text,
            attempts integer not null default 0,
            syncing_at text,
            confirmed_checkpoint integer,
            confirmed_at text,
            conflict_code text
        )"""
    )


def _create_v0_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """create table local_commands (
            id integer primary key autoincrement,
            command_id text not null,
            idempotency_key text not null unique,
            organization_id text not null,
            branch_id text not null,
            source_device_id text not null,
            command_type text not null,
            payload_json text not null,
            status text not null,
            occurred_at text not null,
            created_at text not null,
            confirmed_checkpoint integer,
            confirmed_at text
        )"""
    )


def _create_sync_state_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """create table if not exists sync_state (
            branch_id text primary key,
            last_checkpoint integer not null,
            updated_at text not null
        )"""
    )


def _validate_command(envelope: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "command_id",
        "idempotency_key",
        "organization_id",
        "branch_id",
        "source_device_id",
        "actor_user_id",
        "command_type",
        "occurred_at",
        "accepted_at",
        "offline_grant",
        "payload",
    }
    if set(envelope) != required:
        raise InvalidCommandEnvelope("invalid_command_envelope")
    if envelope["schema_version"] != "1.0":
        raise InvalidCommandEnvelope("unsupported_schema_version")
    if envelope["command_type"] != COMMAND_TYPE:
        raise InvalidCommandEnvelope("unsupported_command_type")
    if (
        not isinstance(envelope["idempotency_key"], str)
        or not 12 <= len(envelope["idempotency_key"]) <= 160
        or not isinstance(envelope["offline_grant"], str)
        or len(envelope["offline_grant"]) < 20
        or any(
            not _is_uuid_string(envelope[field])
            for field in (
                "command_id",
                "organization_id",
                "branch_id",
                "source_device_id",
                "actor_user_id",
            )
        )
        or not _is_timezone_datetime(envelope["occurred_at"])
        or not _is_timezone_datetime(envelope["accepted_at"])
        or not isinstance(envelope["payload"], dict)
    ):
        raise InvalidCommandEnvelope("invalid_command_envelope")
    payload = envelope["payload"]
    required_keys = {"register_id", "movement_type", "amount_cents"}
    allowed_keys = {
        "register_id",
        "movement_type",
        "amount_cents",
        "concept_id",
        "concept",
        "reason",
        "reference",
        "evidence_refs",
    }
    if not isinstance(payload, dict) or not required_keys.issubset(payload) or not set(payload).issubset(allowed_keys):
        raise InvalidCommandEnvelope("invalid_cash_payload")
    has_concept_id = payload.get("concept_id") is not None
    invalid = (
        payload["movement_type"] not in {"deposit", "withdrawal"}
        or isinstance(payload["amount_cents"], bool)
        or not isinstance(payload["amount_cents"], int)
        or payload["amount_cents"] <= 0
        or not isinstance(payload["register_id"], str)
        or not payload["register_id"].strip()
        or (has_concept_id and not _is_uuid_string(payload["concept_id"]))
        or (
            payload.get("reference") is not None
            and (
                not isinstance(payload["reference"], str)
                or not 1 <= len(payload["reference"].strip()) <= 600
            )
        )
        or (
            payload.get("evidence_refs") is not None
            and (
                not isinstance(payload["evidence_refs"], list)
                or not 1 <= len(payload["evidence_refs"]) <= 10
                or any(
                    not isinstance(item, str) or not 1 <= len(item.strip()) <= 600
                    for item in payload["evidence_refs"]
                )
            )
        )
    )
    if invalid:
        raise InvalidCommandEnvelope("invalid_cash_payload")


def _is_uuid_string(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        value,
    ):
        return False
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _is_timezone_datetime(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})",
        value,
    ):
        return False
    normalized = f"{value[:-1]}+00:00" if value.upper().endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _canonical(envelope: dict[str, Any]) -> str:
    intent = {
        field: envelope[field]
        for field in (
            "organization_id",
            "branch_id",
            "source_device_id",
            "actor_user_id",
            "command_type",
            "payload",
        )
    }
    return json.dumps(intent, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _row_to_command(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        raise InvalidCommandEnvelope("command was not found")
    return {
        "id": row["id"],
        "command_id": row["command_id"],
        "idempotency_key": row["idempotency_key"],
        "organization_id": row["organization_id"],
        "branch_id": row["branch_id"],
        "source_device_id": row["source_device_id"],
        "actor_user_id": row["actor_user_id"],
        "command_type": row["command_type"],
        "offline_grant": row["offline_grant"],
        "payload": json.loads(row["payload_json"]),
        "request_hash": row["request_hash"],
        "status": row["status"],
        "occurred_at": row["occurred_at"],
        "accepted_at": row["accepted_at"],
        "created_at": row["created_at"],
        "attempts": row["attempts"],
        "confirmed_checkpoint": row["confirmed_checkpoint"],
        "confirmed_at": row["confirmed_at"],
        "conflict_code": row["conflict_code"],
    }


def _redact_command(command: dict[str, Any]) -> dict[str, Any]:
    visible = (
        "id",
        "command_id",
        "idempotency_key",
        "status",
        "occurred_at",
        "accepted_at",
        "created_at",
        "attempts",
        "confirmed_checkpoint",
        "confirmed_at",
        "conflict_code",
    )
    return {field: command[field] for field in visible}


def _record(event: str, command: dict[str, Any]) -> None:
    safe = {
        key: command.get(key)
        for key in (
            "command_id",
            "branch_id",
            "source_device_id",
            "status",
            "attempts",
            "confirmed_checkpoint",
            "conflict_code",
        )
        if command.get(key) is not None
    }
    logger.info(event, extra={"event": event, **safe})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _plus_seconds(value: str, seconds: int) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed + timedelta(seconds=seconds)).isoformat()
