from __future__ import annotations

import json
import threading
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from restaurant_os import models
from restaurant_os.database import get_session
from restaurant_os.main import create_app
from restaurant_os.operations import (
    AuthorizationError,
    BusinessError,
    archive_cash_concept,
    create_cash_concept,
    create_cash_concept_version,
    list_cash_concepts,
    list_effective_cash_concepts,
)
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

UTC = timezone.utc
ORG_ID = "018f6f73-2d0a-74f0-8f1c-000000000001"
LEGAL_ID = "018f6f73-2d0a-74f0-8f1c-000000000002"
BUSINESS_UNIT_ID = "018f6f73-2d0a-74f0-8f1c-000000000015"
BRANCH_A = "018f6f73-2d0a-74f0-8f1c-000000000003"
BRANCH_B = "018f6f73-2d0a-74f0-8f1c-000000000013"
OWNER_ID = "018f6f73-2d0a-74f0-8f1c-000000000006"
SECOND_OWNER_ID = "018f6f73-2d0a-74f0-8f1c-000000000017"
CASHIER_ID = "018f6f73-2d0a-74f0-8f1c-000000000016"
OWNER_ROLE_ID = "018f6f73-2d0a-74f0-8f1c-000000001006"
CASHIER_ROLE_ID = "018f6f73-2d0a-74f0-8f1c-000000001001"


def _concept_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "code": "OPERATING_WITHDRAWAL",
        "name": "Retiro operativo",
        "allowed_movement_type": "withdrawal",
        "requires_reference": True,
        "requires_evidence": True,
        "valid_from": "2026-08-11T18:00:00Z",
        **overrides,
    }


def _version_payload(**overrides: Any) -> dict[str, Any]:
    payload = _concept_payload(**overrides)
    payload.pop("code")
    return payload


def test_owner_versions_archives_and_reads_effective_concept_without_erasing_history() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_cash_concept_scope(session)

        created = create_cash_concept(
            session,
            _concept_payload(),
            "concept-create-001",
            OWNER_ID,
        )
        replay = create_cash_concept(
            session,
            _concept_payload(),
            "concept-create-001",
            OWNER_ID,
        )
        assert replay == created
        assert created["code"] == "OPERATING_WITHDRAWAL"
        assert created["versions"][0]["version"] == 1

        with pytest.raises(BusinessError) as conflict:
            create_cash_concept(
                session,
                _concept_payload(name="Retiro distinto"),
                "concept-create-001",
                OWNER_ID,
            )
        assert conflict.value.code == "idempotency_conflict"

        versioned = create_cash_concept_version(
            session,
            created["id"],
            _version_payload(
                name="Retiro operativo actualizado",
                valid_from="2026-09-01T00:00:00Z",
            ),
            "concept-version-002",
            OWNER_ID,
        )
        assert [row["version"] for row in versioned["versions"]] == [1, 2]
        replay_version = create_cash_concept_version(
            session,
            created["id"],
            _version_payload(
                name="Retiro operativo actualizado",
                valid_from="2026-09-01T00:00:00Z",
            ),
            "concept-version-002",
            OWNER_ID,
        )
        assert replay_version == versioned

        with pytest.raises(BusinessError) as immutable_code:
            create_cash_concept_version(
                session,
                created["id"],
                _concept_payload(code="ANOTHER_CODE"),
                "concept-version-invalid-code",
                OWNER_ID,
            )
        assert immutable_code.value.code == "cash_concept_code_immutable"

        august = list_effective_cash_concepts(
            session,
            "withdrawal",
            datetime(2026, 8, 20, tzinfo=UTC),
            CASHIER_ID,
            BRANCH_A,
        )
        september = list_effective_cash_concepts(
            session,
            "withdrawal",
            datetime(2026, 9, 2, tzinfo=UTC),
            CASHIER_ID,
            BRANCH_A,
        )
        assert [(row["code"], row["version"]) for row in august] == [
            ("OPERATING_WITHDRAWAL", 1)
        ]
        assert [(row["name"], row["version"]) for row in september] == [
            ("Retiro operativo actualizado", 2)
        ]
        assert list_effective_cash_concepts(
            session,
            "deposit",
            datetime(2026, 9, 2, tzinfo=UTC),
            CASHIER_ID,
            BRANCH_A,
        ) == []

        archived = archive_cash_concept(
            session,
            created["id"],
            "concept-archive-003",
            OWNER_ID,
        )
        replay_archive = archive_cash_concept(
            session,
            created["id"],
            "concept-archive-003",
            OWNER_ID,
        )
        assert replay_archive == archived
        assert archived["status"] == "archived"
        assert len(archived["versions"]) == 2
        assert create_cash_concept_version(
            session,
            created["id"],
            _version_payload(
                name="Retiro operativo actualizado",
                valid_from="2026-09-01T00:00:00Z",
            ),
            "concept-version-002",
            OWNER_ID,
        ) == versioned
        with pytest.raises(BusinessError) as actor_conflict:
            create_cash_concept(
                session,
                _concept_payload(),
                "concept-create-001",
                SECOND_OWNER_ID,
            )
        assert actor_conflict.value.code == "idempotency_conflict"
        assert list_effective_cash_concepts(
            session,
            "withdrawal",
            datetime(2026, 9, 2, tzinfo=UTC),
            CASHIER_ID,
            BRANCH_A,
        ) == []
        history = list_cash_concepts(session, OWNER_ID)
        assert len(history) == 1
        assert len(history[0]["versions"]) == 2
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.cash_concept_commands)
        ).scalar_one() == 3
        actions = set(
            session.execute(
                models.audit_events.select()
                .with_only_columns(models.audit_events.c.action)
                .where(models.audit_events.c.entity_type == "cash_movement_concept")
            ).scalars()
        )
        assert actions == {
            "cash_concept.created",
            "cash_concept.versioned",
            "cash_concept.archived",
        }


def test_cash_concept_validation_and_persisted_permissions_fail_closed() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_cash_concept_scope(session)

        with pytest.raises(AuthorizationError) as denied:
            create_cash_concept(
                session,
                _concept_payload(),
                "cashier-cannot-create",
                CASHIER_ID,
            )
        assert denied.value.code == "permission_denied"

        invalid_payloads = [
            _concept_payload(code="texto libre"),
            _concept_payload(name=""),
            _concept_payload(allowed_movement_type="expense"),
            _concept_payload(valid_from="not-a-date"),
            _concept_payload(requires_reference=False),
            _concept_payload(requires_evidence=False),
        ]
        for index, payload in enumerate(invalid_payloads):
            with pytest.raises(BusinessError) as invalid:
                create_cash_concept(
                    session,
                    payload,
                    f"invalid-concept-{index}",
                    OWNER_ID,
                )
            assert invalid.value.code == "cash_concept_invalid"

        with pytest.raises(AuthorizationError) as wrong_branch:
            list_effective_cash_concepts(
                session,
                "withdrawal",
                datetime(2026, 8, 20, tzinfo=UTC),
                CASHIER_ID,
                BRANCH_B,
            )
        assert wrong_branch.value.code == "permission_denied"
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.cash_movement_concepts)
        ).scalar_one() == 0


def test_invalid_and_foreign_mutations_leave_history_and_success_audits_unchanged() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_cash_concept_scope(session)
        created = create_cash_concept(session, _concept_payload(), "valid-create", OWNER_ID)
        before = _cash_concept_counts(session)
        with pytest.raises(BusinessError) as immutable:
            create_cash_concept_version(
                session, created["id"], _concept_payload(), "version-with-code", OWNER_ID
            )
        assert immutable.value.code == "cash_concept_code_immutable"
        session.execute(
            models.organizations.insert().values(
                id="foreign-org",
                name="Foreign",
                status="active",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        session.execute(
            models.cash_movement_concepts.insert().values(
                id="018f6f73-2d0a-74f0-8f1c-000000009999",
                organization_id="foreign-org",
                code="FOREIGN_CONCEPT",
                status="active",
                created_by_user_id=OWNER_ID,
                created_at=datetime.now(UTC),
                archived_at=None,
            )
        )
        session.commit()
        with pytest.raises(BusinessError) as foreign:
            create_cash_concept_version(
                session,
                "018f6f73-2d0a-74f0-8f1c-000000009999",
                _version_payload(),
                "foreign-version",
                OWNER_ID,
            )
        assert foreign.value.code == "cash_concept_not_found"
        after = _cash_concept_counts(session)
        assert after == {**before, "concepts": before["concepts"] + 1}


def test_permission_denial_audits_without_committing_pending_mutation() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_cash_concept_scope(session)
        session.execute(
            models.cash_movement_concepts.insert().values(
                id="018f6f73-2d0a-74f0-8f1c-000000009998",
                organization_id=ORG_ID,
                code="PENDING_ONLY",
                status="active",
                created_by_user_id=OWNER_ID,
                created_at=datetime.now(UTC),
                archived_at=None,
            )
        )
        with pytest.raises(AuthorizationError):
            create_cash_concept(session, _concept_payload(), "denied-create", CASHIER_ID)
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.cash_movement_concepts)
        ).scalar_one() == 0
        assert session.execute(
            sa.select(sa.func.count())
            .select_from(models.audit_events)
            .where(models.audit_events.c.action == "authorization.denied")
        ).scalar_one() == 1


def test_concurrent_version_publication_is_normalized_without_partial_history(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cash-concept-concurrency.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 1},
    )
    models.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        _seed_cash_concept_scope(session)
        concept = create_cash_concept(session, _concept_payload(), "concurrency-create", OWNER_ID)

    barrier = threading.Barrier(2)
    entered = {"count": 0}
    entered_lock = threading.Lock()

    @event.listens_for(engine, "before_cursor_execute")
    def synchronize_version_inserts(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: Any,
    ) -> None:
        if "INSERT INTO cash_movement_concept_versions" not in statement:
            return
        with entered_lock:
            entered["count"] += 1
            should_wait = entered["count"] <= 2
        if should_wait:
            barrier.wait(timeout=5)

    outcomes: list[dict[str, Any] | BusinessError] = []

    def publish(key: str) -> None:
        with factory() as session:
            try:
                outcomes.append(
                    create_cash_concept_version(
                        session,
                        concept["id"],
                        _version_payload(name="Versión concurrente"),
                        key,
                        OWNER_ID,
                    )
                )
            except BusinessError as error:
                outcomes.append(error)

    first = threading.Thread(target=publish, args=("concurrency-one",))
    second = threading.Thread(target=publish, args=("concurrency-two",))
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)
    event.remove(engine, "before_cursor_execute", synchronize_version_inserts)
    assert not first.is_alive() and not second.is_alive()
    assert len(outcomes) == 2
    assert all(isinstance(outcome, (dict, BusinessError)) for outcome in outcomes)
    assert all(
        not isinstance(outcome, BusinessError) or outcome.code == "cash_concept_version_conflict"
        for outcome in outcomes
    )
    with factory() as session:
        versions = session.execute(
            sa.select(models.cash_movement_concept_versions.c.version)
            .where(models.cash_movement_concept_versions.c.concept_id == concept["id"])
            .order_by(models.cash_movement_concept_versions.c.version)
        ).scalars().all()
        assert versions == [1, 2]
        assert session.execute(
            sa.select(sa.func.count())
            .select_from(models.cash_concept_commands)
            .where(models.cash_concept_commands.c.target_concept_id == concept["id"])
        ).scalar_one() == 2


def test_cash_concept_api_exposes_only_pco_002_contracts() -> None:
    client = _cash_concept_client()
    owner_headers = {
        "X-Actor-User-Id": OWNER_ID,
        "Idempotency-Key": "api-concept-create-001",
    }
    response = client.post(
        "/api/v1/cash/concepts",
        headers=owner_headers,
        json=_concept_payload(),
    )
    assert response.status_code == 200
    concept = response.json()

    version_response = client.put(
        f"/api/v1/cash/concepts/{concept['id']}/versions",
        headers={
            "X-Actor-User-Id": OWNER_ID,
            "Idempotency-Key": "api-concept-version-002",
        },
        json=_version_payload(
            name="Retiro operativo dos",
            valid_from="2026-09-01T00:00:00Z",
        ),
    )
    assert version_response.status_code == 200
    assert len(version_response.json()["versions"]) == 2

    effective = client.get(
        "/api/v1/cash/concepts/effective",
        headers={"X-Actor-User-Id": CASHIER_ID},
        params={
            "branch_id": BRANCH_A,
            "movement_type": "withdrawal",
            "effective_at": "2026-08-20T00:00:00Z",
        },
    )
    assert effective.status_code == 200
    assert effective.json()[0]["version"] == 1

    history = client.get(
        "/api/v1/cash/concepts",
        headers={"X-Actor-User-Id": OWNER_ID},
    )
    assert history.status_code == 200
    assert len(history.json()[0]["versions"]) == 2

    missing_key = client.post(
        "/api/v1/cash/concepts",
        headers={"X-Actor-User-Id": OWNER_ID},
        json=_concept_payload(code="MISSING_KEY"),
    )
    assert missing_key.status_code == 409
    assert missing_key.json()["detail"]["code"] == "idempotency_key_required"

    # PCO-003 owns the route and rejects an incomplete command without writing.
    movement = client.post(
        "/api/v1/cash/movements",
        headers={"X-Actor-User-Id": OWNER_ID, "Idempotency-Key": "not-yet"},
        json={},
    )
    assert movement.status_code == 409
    assert movement.json()["detail"]["code"] == "cash_movement_invalid"


def test_cash_concept_contracts_describe_real_responses_and_reject_extensions() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    client = _cash_concept_client()
    response = client.post(
        "/api/v1/cash/concepts",
        headers={"X-Actor-User-Id": OWNER_ID, "Idempotency-Key": "contract-create"},
        json=_concept_payload(),
    )
    assert response.status_code == 200
    concept = response.json()
    effective = client.get(
        "/api/v1/cash/concepts/effective",
        headers={"X-Actor-User-Id": CASHIER_ID},
        params={
            "branch_id": BRANCH_A,
            "movement_type": "withdrawal",
            "effective_at": "2026-08-20T00:00:00Z",
        },
    )
    assert effective.status_code == 200
    schemas = Path(__file__).resolve().parents[3] / "packages/contracts/schemas"
    response_schema = json.loads((schemas / "cash-concept-response-v1.schema.json").read_text())
    effective_schema = json.loads((schemas / "effective-cash-concepts-v1.schema.json").read_text())
    command_schema = json.loads((schemas / "cash-concept-command-v1.schema.json").read_text())
    validator = jsonschema.Draft202012Validator
    format_checker = jsonschema.FormatChecker()

    @format_checker.checks("date-time")
    def is_timezone_aware_datetime(value: object) -> bool:
        if not isinstance(value, str):
            return True
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
        except ValueError:
            return False

    validator.check_schema(command_schema)
    validator.check_schema(response_schema)
    validator.check_schema(effective_schema)
    validator(response_schema, format_checker=format_checker).validate(concept)
    validator(effective_schema, format_checker=format_checker).validate(effective.json())
    create_validator = validator(command_schema["$defs"]["create"], format_checker=format_checker)
    version_validator = validator(command_schema["$defs"]["version"], format_checker=format_checker)
    create_validator.validate(_concept_payload())
    version_validator.validate(_version_payload())
    with pytest.raises(jsonschema.ValidationError):
        version_validator.validate(_concept_payload())
    with pytest.raises(jsonschema.ValidationError):
        create_validator.validate(_concept_payload(unexpected=True))
    with pytest.raises(jsonschema.ValidationError):
        create_validator.validate(_concept_payload(allowed_movement_type="ledger"))
    with pytest.raises(jsonschema.ValidationError):
        create_validator.validate(_concept_payload(valid_from="not-a-date"))
    with pytest.raises(jsonschema.ValidationError):
        create_validator.validate(_concept_payload(code="lowercase"))
    invalid_response = {**concept, "unexpected": True}
    with pytest.raises(jsonschema.ValidationError):
        validator(response_schema, format_checker=format_checker).validate(invalid_response)


def _cash_concept_client() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        _seed_cash_concept_scope(session)

    app = create_app()

    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.state.test_session_factory = session_factory
    return TestClient(app)


def _cash_concept_counts(session: Session) -> dict[str, int]:
    return {
        "concepts": session.execute(
            sa.select(sa.func.count()).select_from(models.cash_movement_concepts)
        ).scalar_one(),
        "versions": session.execute(
            sa.select(sa.func.count()).select_from(models.cash_movement_concept_versions)
        ).scalar_one(),
        "commands": session.execute(
            sa.select(sa.func.count()).select_from(models.cash_concept_commands)
        ).scalar_one(),
        "success_audits": session.execute(
            sa.select(sa.func.count())
            .select_from(models.audit_events)
            .where(models.audit_events.c.action.like("cash_concept.%"))
        ).scalar_one(),
    }


def _seed_cash_concept_scope(session: Session) -> None:
    now = datetime(2026, 8, 11, 17, 0, tzinfo=UTC)
    session.execute(
        models.organizations.insert().values(
            id=ORG_ID,
            name="Kiwi Restaurante",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.legal_entities.insert().values(
            id=LEGAL_ID,
            organization_id=ORG_ID,
            name="Kiwi",
            tax_id=None,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.business_units.insert().values(
            id=BUSINESS_UNIT_ID,
            organization_id=ORG_ID,
            legal_entity_id=LEGAL_ID,
            name="Restaurantes",
            code="REST",
            unit_type="restaurant",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.branches.insert(),
        [
            {
                "id": branch_id,
                "organization_id": ORG_ID,
                "legal_entity_id": LEGAL_ID,
                "business_unit_id": BUSINESS_UNIT_ID,
                "name": name,
                "code": code,
                "timezone": "America/Mazatlan",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
            for branch_id, name, code in (
                (BRANCH_A, "Centro", "CENTRO"),
                (BRANCH_B, "Norte", "NORTE"),
            )
        ],
    )
    session.execute(
        models.permissions.insert(),
        [
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000001105",
                "code": "cash.concept.read",
                "description": "Leer conceptos",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000001106",
                "code": "cash.concept.manage",
                "description": "Administrar conceptos",
                "created_at": now,
            },
        ],
    )
    session.execute(
        models.roles.insert(),
        [
            {
                "id": OWNER_ROLE_ID,
                "organization_id": ORG_ID,
                "name": "Etiqueta no autoritativa",
                "scope": "organization",
                "created_at": now,
            },
            {
                "id": CASHIER_ROLE_ID,
                "organization_id": ORG_ID,
                "name": "Cajero",
                "scope": "branch",
                "created_at": now,
            },
        ],
    )
    session.execute(
        models.role_permissions.insert(),
        [
            {
                "role_id": OWNER_ROLE_ID,
                "permission_id": "018f6f73-2d0a-74f0-8f1c-000000001105",
            },
            {
                "role_id": OWNER_ROLE_ID,
                "permission_id": "018f6f73-2d0a-74f0-8f1c-000000001106",
            },
            {
                "role_id": CASHIER_ROLE_ID,
                "permission_id": "018f6f73-2d0a-74f0-8f1c-000000001105",
            },
        ],
    )
    session.execute(
        models.users.insert(),
        [
            {
                "id": OWNER_ID,
                "organization_id": ORG_ID,
                "email": "owner@example.com",
                "display_name": "Owner",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": SECOND_OWNER_ID,
                "organization_id": ORG_ID,
                "email": "owner-two@example.com",
                "display_name": "Owner two",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": CASHIER_ID,
                "organization_id": ORG_ID,
                "email": "cashier@example.com",
                "display_name": "Cashier",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    session.execute(
        models.user_roles.insert(),
        [
            {"user_id": OWNER_ID, "role_id": OWNER_ROLE_ID, "branch_id": None},
            {"user_id": SECOND_OWNER_ID, "role_id": OWNER_ROLE_ID, "branch_id": None},
            {"user_id": CASHIER_ID, "role_id": CASHIER_ROLE_ID, "branch_id": BRANCH_A},
        ],
    )
    session.execute(
        models.role_authority_grants.insert().values(
            role_id=OWNER_ROLE_ID,
            authority_kind="organization_all_permissions",
            created_at=now,
        )
    )
    session.commit()
