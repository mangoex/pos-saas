from __future__ import annotations

from datetime import datetime, timezone

import pytest
from restaurant_os import models, operations
from restaurant_os.operations import (
    AuthorizationError,
    BusinessError,
    apply_profile_transition_mapping,
    assign_user_role,
    authorize_branch_scope,
    bootstrap_initial_owners,
    create_profile_transition_mapping,
    create_role,
    delete_role,
    profile_transition_dry_run,
    require_permission,
    reverse_profile_transition_mapping,
    update_role,
    update_role_permissions,
    update_user,
)
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

UTC = timezone.utc
ORG_A = "018f6f73-2d0a-74f0-8f1c-000000000001"
ORG_B = "018f6f73-2d0a-74f0-8f1c-000000001002"
BRANCH_A = "018f6f73-2d0a-74f0-8f1c-000000001003"
BRANCH_A_OTHER = "018f6f73-2d0a-74f0-8f1c-000000001004"
BRANCH_B = "018f6f73-2d0a-74f0-8f1c-000000001005"
INITIAL_OWNER_EMAILS = ("aniacuestas@gmail.com", "mangoex@gmail.com")


def test_authorization_uses_persisted_authority_not_role_label_and_fails_closed() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    now = datetime(2026, 8, 10, tzinfo=UTC)
    with Session(engine) as session:
        _seed_scope_fixture(session, now)

        # The role labels are intentionally misleading. Runtime authority must come from persisted
        # permissions plus the persisted organization-authority grant, never these strings.
        require_permission(
            session, "018f6f73-2d0a-74f0-8f1c-000000001021", "admin.manage", BRANCH_A_OTHER
        )
        require_permission(
            session,
            "018f6f73-2d0a-74f0-8f1c-000000001021",
            "future.specialized.permission",
            BRANCH_A,
        )
        assert (
            authorize_branch_scope(
                session,
                "018f6f73-2d0a-74f0-8f1c-000000001021",
                "admin.manage",
                BRANCH_A_OTHER,
            )
            == BRANCH_A_OTHER
        )

        require_permission(session, "018f6f73-2d0a-74f0-8f1c-000000001020", "pos.operate", BRANCH_A)
        with pytest.raises(AuthorizationError, match="required permission") as branch_error:
            authorize_branch_scope(
                session,
                "018f6f73-2d0a-74f0-8f1c-000000001020",
                "pos.operate",
                BRANCH_A_OTHER,
            )
        assert branch_error.value.code == "permission_denied"

        with pytest.raises(AuthorizationError, match="requested branch") as cross_org_error:
            authorize_branch_scope(
                session,
                "018f6f73-2d0a-74f0-8f1c-000000001021",
                "admin.manage",
                BRANCH_B,
            )
        assert cross_org_error.value.code == "permission_denied"

        with pytest.raises(AuthorizationError, match="authentication") as missing_actor_error:
            require_permission(session, "", "pos.operate", BRANCH_A)
        assert missing_actor_error.value.code == "actor_required"
        denied_payloads = [
            row[0]
            for row in session.execute(
                models.audit_events.select()
                .with_only_columns(models.audit_events.c.payload)
                .where(models.audit_events.c.action == "authorization.denied")
            )
        ]
        assert {"no_scoped_role", "invalid_branch_scope", "missing_actor"} <= {
            payload["reason"] for payload in denied_payloads
        }


def test_branch_assignment_and_legacy_null_never_authorize() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))

        with pytest.raises(BusinessError) as missing_branch:
            assign_user_role(
                session,
                "018f6f73-2d0a-74f0-8f1c-000000001020",
                "018f6f73-2d0a-74f0-8f1c-000000001018",
                actor_user_id="018f6f73-2d0a-74f0-8f1c-000000001022",
            )
        assert missing_branch.value.code == "branch_assignment_required"

        session.execute(
            models.user_roles.update()
            .where(models.user_roles.c.user_id == "018f6f73-2d0a-74f0-8f1c-000000001020")
            .values(branch_id=None)
        )
        session.commit()
        with pytest.raises(AuthorizationError) as null_scope:
            require_permission(
                session,
                "018f6f73-2d0a-74f0-8f1c-000000001020",
                "pos.operate",
                BRANCH_A,
            )
        assert null_scope.value.code == "permission_denied"


def test_owner_assignment_requires_persisted_authority_and_role_updates_are_additive() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))
        owner_role_id = "018f6f73-2d0a-74f0-8f1c-000000001019"
        legacy_admin_id = "018f6f73-2d0a-74f0-8f1c-000000001022"
        cashier_id = "018f6f73-2d0a-74f0-8f1c-000000001020"

        with pytest.raises(AuthorizationError) as escalation:
            assign_user_role(session, legacy_admin_id, owner_role_id, actor_user_id=legacy_admin_id)
        assert escalation.value.code == "owner_authority_required"
        with pytest.raises(AuthorizationError) as assignment_to_another_user:
            assign_user_role(session, cashier_id, owner_role_id, actor_user_id=legacy_admin_id)
        assert assignment_to_another_user.value.code == "owner_authority_required"
        assert session.execute(
            models.user_roles.select().where(
                models.user_roles.c.user_id == legacy_admin_id,
                models.user_roles.c.role_id == owner_role_id,
            )
        ).first() is None
        denied_payloads = list(
            session.execute(
                models.audit_events.select()
                .with_only_columns(models.audit_events.c.payload)
                .where(models.audit_events.c.action == "authorization.denied")
            ).scalars()
        )
        assert any(payload["reason"] == "owner_authority_required" for payload in denied_payloads)

        session.execute(
            models.roles.update()
            .where(models.roles.c.id == owner_role_id)
            .values(name="Rol visible falso")
        )
        session.commit()
        assignment = assign_user_role(
            session,
            cashier_id,
            owner_role_id,
            actor_user_id="018f6f73-2d0a-74f0-8f1c-000000001021",
        )
        assert assignment["role_id"] == owner_role_id

        with pytest.raises(BusinessError) as cross_organization_assignment:
            assign_user_role(
                session,
                "018f6f73-2d0a-74f0-8f1c-000000001025",
                owner_role_id,
                actor_user_id="018f6f73-2d0a-74f0-8f1c-000000001021",
            )
        assert cross_organization_assignment.value.code == "role_organization_mismatch"

        session.execute(
            models.user_roles.delete().where(
                models.user_roles.c.user_id == cashier_id,
                models.user_roles.c.role_id == owner_role_id,
            )
        )
        session.execute(
            models.roles.insert().values(
                id="018f6f73-2d0a-74f0-8f1c-000000001024",
                organization_id=ORG_A,
                name="Especialidad preservada",
                scope="branch",
                created_at=datetime(2026, 8, 10, tzinfo=UTC),
            )
        )
        session.execute(
            models.user_roles.update()
            .where(models.user_roles.c.user_id == cashier_id)
            .values(branch_id=BRANCH_A)
        )
        session.execute(
            models.user_roles.insert().values(
                user_id=cashier_id,
                role_id="018f6f73-2d0a-74f0-8f1c-000000001024",
                branch_id=BRANCH_A,
            )
        )
        session.commit()
        update_user(
            session,
            cashier_id,
            role_id="018f6f73-2d0a-74f0-8f1c-000000001018",
            branch_id=BRANCH_A,
            actor_user_id=legacy_admin_id,
        )
        role_ids = set(session.execute(
            models.user_roles.select().with_only_columns(models.user_roles.c.role_id).where(
                models.user_roles.c.user_id == cashier_id
            )
        ).scalars())
        assert "018f6f73-2d0a-74f0-8f1c-000000001024" in role_ids


def test_update_user_same_role_different_branch_upserts_without_integrity_error() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))
        cashier_id = "018f6f73-2d0a-74f0-8f1c-000000001020"
        legacy_admin_id = "018f6f73-2d0a-74f0-8f1c-000000001022"
        # User already has role 018f6f73-2d0a-74f0-8f1c-000000001018 on BRANCH_A
        # Re-assigning or changing branch must upsert cleanly and not throw IntegrityError
        update_user(
            session,
            cashier_id,
            role_id="018f6f73-2d0a-74f0-8f1c-000000001018",
            branch_id=BRANCH_A_OTHER,
            actor_user_id=legacy_admin_id,
        )
        assigned_branch = session.execute(
            models.user_roles.select().with_only_columns(models.user_roles.c.branch_id).where(
                models.user_roles.c.user_id == cashier_id,
                models.user_roles.c.role_id == "018f6f73-2d0a-74f0-8f1c-000000001018",
            )
        ).scalar()
        assert assigned_branch == BRANCH_A_OTHER


def test_organization_authority_role_is_immutable_except_for_authorized_rename() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))
        authority_role_id = "018f6f73-2d0a-74f0-8f1c-000000001019"
        owner_id = "018f6f73-2d0a-74f0-8f1c-000000001021"
        legacy_admin_id = "018f6f73-2d0a-74f0-8f1c-000000001022"
        cashier_id = "018f6f73-2d0a-74f0-8f1c-000000001020"

        with pytest.raises(AuthorizationError) as legacy_scope:
            update_role(
                session,
                authority_role_id,
                scope="branch",
                actor_user_id=legacy_admin_id,
            )
        assert legacy_scope.value.code == "owner_authority_required"
        with pytest.raises(AuthorizationError) as legacy_delete:
            delete_role(session, authority_role_id, actor_user_id=legacy_admin_id)
        assert legacy_delete.value.code == "owner_authority_required"
        with pytest.raises(AuthorizationError) as legacy_permissions:
            update_role_permissions(
                session,
                authority_role_id,
                [],
                actor_user_id=legacy_admin_id,
            )
        assert legacy_permissions.value.code == "owner_authority_required"

        with pytest.raises(BusinessError) as owner_scope:
            update_role(session, authority_role_id, scope="branch", actor_user_id=owner_id)
        assert owner_scope.value.code == "owner_role_scope_immutable"
        with pytest.raises(BusinessError) as owner_delete:
            delete_role(session, authority_role_id, actor_user_id=owner_id)
        assert owner_delete.value.code == "owner_role_delete_forbidden"
        with pytest.raises(BusinessError) as owner_permissions:
            update_role_permissions(session, authority_role_id, [], actor_user_id=owner_id)
        assert owner_permissions.value.code == "owner_role_permissions_immutable"

        renamed = update_role(
            session,
            authority_role_id,
            name="Etiqueta no autoritativa",
            actor_user_id=owner_id,
        )
        assert renamed["name"] == "Etiqueta no autoritativa"
        assert session.execute(
            models.roles.select()
            .with_only_columns(models.roles.c.scope)
            .where(models.roles.c.id == authority_role_id)
        ).scalar_one() == "organization"
        require_permission(session, owner_id, "future.specialized.permission", BRANCH_A_OTHER)
        denied_reasons = {
            payload["reason"]
            for payload in session.execute(
                models.audit_events.select()
                .with_only_columns(models.audit_events.c.payload)
                .where(models.audit_events.c.action == "authorization.denied")
            ).scalars()
        }
        assert {
            "owner_authority_required",
            "owner_role_scope_immutable",
            "owner_role_delete_forbidden",
            "owner_role_permissions_immutable",
        } <= denied_reasons

        ordinary_role = create_role(
            session,
            "Alcance ordinario",
            scope="organization",
            actor_user_id=legacy_admin_id,
        )
        access_permission_id = session.execute(
            models.permissions.select()
            .with_only_columns(models.permissions.c.id)
            .where(models.permissions.c.code == "access.organization.all_branches")
        ).scalar_one()
        update_role_permissions(
            session,
            ordinary_role["id"],
            [access_permission_id],
            actor_user_id=legacy_admin_id,
        )
        assign_user_role(
            session,
            cashier_id,
            ordinary_role["id"],
            actor_user_id=legacy_admin_id,
        )
        with pytest.raises(AuthorizationError) as ordinary_access:
            require_permission(
                session,
                cashier_id,
                "future.specialized.permission",
                BRANCH_A,
            )
        assert ordinary_access.value.code == "permission_denied"
        assert session.execute(
            models.role_authority_grants.select().where(
                models.role_authority_grants.c.role_id == ordinary_role["id"]
            )
        ).first() is None


def test_initial_owner_bootstrap_is_atomic_idempotent_and_exact() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))
        authority_role_id = "018f6f73-2d0a-74f0-8f1c-000000001019"
        operational_actor_id = "018f6f73-2d0a-74f0-8f1c-000000001022"
        session.execute(
            models.user_roles.delete().where(
                models.user_roles.c.role_id == authority_role_id
            )
        )
        session.execute(
            models.users.update()
            .where(models.users.c.id == "018f6f73-2d0a-74f0-8f1c-000000001020")
            .values(email=INITIAL_OWNER_EMAILS[0])
        )
        session.execute(
            models.users.update()
            .where(models.users.c.id == "018f6f73-2d0a-74f0-8f1c-000000001021")
            .values(email=INITIAL_OWNER_EMAILS[1])
        )
        for user_id in (
            "018f6f73-2d0a-74f0-8f1c-000000001020",
            "018f6f73-2d0a-74f0-8f1c-000000001021",
        ):
            session.execute(
                models.user_roles.insert().values(
                    user_id=user_id,
                    role_id="018f6f73-2d0a-74f0-8f1c-000000001023",
                    branch_id=None,
                )
            )
        session.commit()

        result = bootstrap_initial_owners(
            session,
            organization_id=ORG_A,
            owner_emails=INITIAL_OWNER_EMAILS,
            operational_actor_user_id=operational_actor_id,
            provenance="test-approved-owner-bootstrap",
        )
        assert result["status"] == "bootstrapped"
        assert result["owner_user_ids"] == [
            "018f6f73-2d0a-74f0-8f1c-000000001020",
            "018f6f73-2d0a-74f0-8f1c-000000001021",
        ]
        assert session.execute(
            models.user_roles.select().where(
                models.user_roles.c.role_id == authority_role_id
            )
        ).fetchall().__len__() == 2
        assert session.execute(
            models.user_roles.select().where(
                models.user_roles.c.role_id == "018f6f73-2d0a-74f0-8f1c-000000001023",
                models.user_roles.c.user_id.in_(result["owner_user_ids"]),
            )
        ).fetchall().__len__() == 2

        replay = bootstrap_initial_owners(
            session,
            organization_id=ORG_A,
            owner_emails=INITIAL_OWNER_EMAILS,
            operational_actor_user_id=operational_actor_id,
            provenance="test-approved-owner-bootstrap",
        )
        assert replay["status"] == "already_bootstrapped"
        actions = set(
            session.execute(
                models.audit_events.select()
                .with_only_columns(models.audit_events.c.action)
                .where(models.audit_events.c.entity_id == authority_role_id)
            ).scalars()
        )
        assert {
            "rbac.initial_owners_bootstrapped",
            "rbac.initial_owners_bootstrap_replayed",
        } <= actions


def test_initial_owner_bootstrap_rejects_missing_or_partial_configuration_without_writes() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))
        authority_role_id = "018f6f73-2d0a-74f0-8f1c-000000001019"
        operational_actor_id = "018f6f73-2d0a-74f0-8f1c-000000001022"
        session.execute(
            models.user_roles.delete().where(
                models.user_roles.c.role_id == authority_role_id
            )
        )
        session.execute(
            models.users.update()
            .where(models.users.c.id == "018f6f73-2d0a-74f0-8f1c-000000001020")
            .values(email=INITIAL_OWNER_EMAILS[0])
        )
        session.commit()

        with pytest.raises(BusinessError) as missing_user:
            bootstrap_initial_owners(
                session,
                organization_id=ORG_A,
                owner_emails=INITIAL_OWNER_EMAILS,
                operational_actor_user_id=operational_actor_id,
                provenance="test-missing-owner",
            )
        assert missing_user.value.code == "bootstrap_owner_users_missing"
        assert session.execute(
            models.user_roles.select().where(
                models.user_roles.c.role_id == authority_role_id
            )
        ).first() is None

        session.execute(
            models.users.update()
            .where(models.users.c.id == "018f6f73-2d0a-74f0-8f1c-000000001021")
            .values(email=INITIAL_OWNER_EMAILS[1])
        )
        session.execute(
            models.user_roles.insert().values(
                user_id="018f6f73-2d0a-74f0-8f1c-000000001020",
                role_id=authority_role_id,
                branch_id=None,
            )
        )
        session.commit()
        with pytest.raises(BusinessError) as partial_assignment:
            bootstrap_initial_owners(
                session,
                organization_id=ORG_A,
                owner_emails=INITIAL_OWNER_EMAILS,
                operational_actor_user_id=operational_actor_id,
                provenance="test-partial-owner",
            )
        assert partial_assignment.value.code == "bootstrap_owner_assignment_conflict"
        assert session.execute(
            models.user_roles.select().where(
                models.user_roles.c.role_id == authority_role_id
            )
        ).fetchall().__len__() == 1

        with pytest.raises(BusinessError) as invalid_input:
            bootstrap_initial_owners(
                session,
                organization_id=ORG_A,
                owner_emails=(INITIAL_OWNER_EMAILS[0], "other@example.test"),
                operational_actor_user_id=operational_actor_id,
                provenance="test-invalid-owner-input",
            )
        assert invalid_input.value.code == "bootstrap_owner_input_invalid"


def test_profile_transition_is_additive_reversible_and_idempotent_without_pii() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))
        owner_id = "018f6f73-2d0a-74f0-8f1c-000000001021"
        subject_id = "018f6f73-2d0a-74f0-8f1c-000000001022"
        legacy_role_id = "018f6f73-2d0a-74f0-8f1c-000000001023"
        target_role_id = "018f6f73-2d0a-74f0-8f1c-000000001018"
        specialty_role_id = "018f6f73-2d0a-74f0-8f1c-000000001024"
        session.execute(
            models.roles.insert().values(
                id=specialty_role_id,
                organization_id=ORG_A,
                name="Especialidad existente",
                scope="branch",
                created_at=datetime(2026, 8, 10, tzinfo=UTC),
            )
        )
        session.execute(
            models.user_roles.insert().values(
                user_id=subject_id,
                role_id=specialty_role_id,
                branch_id=BRANCH_A,
            )
        )
        session.commit()

        dry_run = profile_transition_dry_run(
            session,
            organization_id=ORG_A,
            user_id=subject_id,
            legacy_role_id=legacy_role_id,
            target_role_id=target_role_id,
            target_branch_id=BRANCH_A,
            actor_user_id=owner_id,
        )
        assert dry_run["user_id"] == subject_id
        assert "email" not in dry_run
        assert "display_name" not in dry_run
        with pytest.raises(AuthorizationError) as cross_organization:
            profile_transition_dry_run(
                session,
                organization_id=ORG_B,
                user_id=subject_id,
                legacy_role_id=legacy_role_id,
                target_role_id=target_role_id,
                target_branch_id=BRANCH_B,
                actor_user_id=owner_id,
            )
        assert cross_organization.value.code == "actor_not_authorized"

        pending = create_profile_transition_mapping(
            session,
            organization_id=ORG_A,
            user_id=subject_id,
            legacy_role_id=legacy_role_id,
            target_role_id=target_role_id,
            target_branch_id=BRANCH_A,
            actor_user_id=owner_id,
            provenance="test-explicit-transition",
            idempotency_key="transition-create-001",
        )
        assert pending["status"] == "pending"
        assert create_profile_transition_mapping(
            session,
            organization_id=ORG_A,
            user_id=subject_id,
            legacy_role_id=legacy_role_id,
            target_role_id=target_role_id,
            target_branch_id=BRANCH_A,
            actor_user_id=owner_id,
            provenance="test-explicit-transition",
            idempotency_key="transition-create-001",
        )["id"] == pending["id"]
        with pytest.raises(BusinessError) as concurrent_pending:
            create_profile_transition_mapping(
                session,
                organization_id=ORG_A,
                user_id=subject_id,
                legacy_role_id=legacy_role_id,
                target_role_id=target_role_id,
                target_branch_id=BRANCH_A,
                actor_user_id=owner_id,
                provenance="test-concurrent-transition",
                idempotency_key="transition-create-002",
            )
        assert concurrent_pending.value.code == "profile_transition_conflict"

        mapped = apply_profile_transition_mapping(
            session,
            mapping_id=pending["id"],
            actor_user_id=owner_id,
            idempotency_key="transition-apply-001",
        )
        assert mapped["status"] == "mapped"
        assert apply_profile_transition_mapping(
            session,
            mapping_id=pending["id"],
            actor_user_id=owner_id,
            idempotency_key="transition-apply-001",
        )["status"] == "mapped"
        role_ids = set(
            session.execute(
                models.user_roles.select()
                .with_only_columns(models.user_roles.c.role_id)
                .where(models.user_roles.c.user_id == subject_id)
            ).scalars()
        )
        assert {legacy_role_id, specialty_role_id, target_role_id} <= role_ids
        later_specialty_role_id = "018f6f73-2d0a-74f0-8f1c-000000001026"
        session.execute(
            models.roles.insert().values(
                id=later_specialty_role_id,
                organization_id=ORG_A,
                name="Especialidad posterior",
                scope="branch",
                created_at=datetime(2026, 8, 10, tzinfo=UTC),
            )
        )
        session.execute(
            models.user_roles.insert().values(
                user_id=subject_id,
                role_id=later_specialty_role_id,
                branch_id=BRANCH_A,
            )
        )
        session.commit()

        reversed_mapping = reverse_profile_transition_mapping(
            session,
            mapping_id=pending["id"],
            actor_user_id=owner_id,
            idempotency_key="transition-reverse-001",
        )
        assert reversed_mapping["status"] == "reversed"
        assert reverse_profile_transition_mapping(
            session,
            mapping_id=pending["id"],
            actor_user_id=owner_id,
            idempotency_key="transition-reverse-001",
        )["status"] == "reversed"
        remaining_role_ids = set(
            session.execute(
                models.user_roles.select()
                .with_only_columns(models.user_roles.c.role_id)
                .where(models.user_roles.c.user_id == subject_id)
            ).scalars()
        )
        assert target_role_id not in remaining_role_ids
        assert {legacy_role_id, specialty_role_id, later_specialty_role_id} <= remaining_role_ids
        next_cycle = create_profile_transition_mapping(
            session,
            organization_id=ORG_A,
            user_id=subject_id,
            legacy_role_id=legacy_role_id,
            target_role_id=target_role_id,
            target_branch_id=BRANCH_A,
            actor_user_id=owner_id,
            provenance="test-explicit-transition-cycle-two",
            idempotency_key="transition-create-002",
        )
        assert next_cycle["id"] != pending["id"]
        assert next_cycle["status"] == "pending"


def test_rejection_audit_rolls_back_unrelated_pending_writes() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))
        pending_permission_id = "018f6f73-2d0a-74f0-8f1c-000000001040"
        session.execute(
            models.permissions.insert().values(
                id=pending_permission_id,
                code="pending.write.must.rollback",
                description="must not commit",
                created_at=datetime(2026, 8, 10, tzinfo=UTC),
            )
        )
        with pytest.raises(AuthorizationError) as denied_transition:
            profile_transition_dry_run(
                session,
                organization_id=ORG_A,
                user_id="018f6f73-2d0a-74f0-8f1c-000000001022",
                legacy_role_id="018f6f73-2d0a-74f0-8f1c-000000001023",
                target_role_id="018f6f73-2d0a-74f0-8f1c-000000001018",
                target_branch_id=BRANCH_A,
                actor_user_id="018f6f73-2d0a-74f0-8f1c-000000001022",
            )
        assert denied_transition.value.code == "owner_authority_required"
        assert session.execute(
            models.permissions.select().where(models.permissions.c.id == pending_permission_id)
        ).first() is None
        assert session.execute(
            models.audit_events.select().where(
                models.audit_events.c.organization_id == ORG_A,
                models.audit_events.c.action == "authorization.denied",
            )
        ).first() is not None

        session.execute(
            models.permissions.insert().values(
                id=pending_permission_id,
                code="pending.bootstrap.must.rollback",
                description="must not commit",
                created_at=datetime(2026, 8, 10, tzinfo=UTC),
            )
        )
        with pytest.raises(BusinessError) as denied_bootstrap:
            bootstrap_initial_owners(
                session,
                organization_id=ORG_A,
                owner_emails=INITIAL_OWNER_EMAILS,
                operational_actor_user_id="018f6f73-2d0a-74f0-8f1c-000000001022",
                provenance="test-rejection-rollback",
            )
        assert denied_bootstrap.value.code == "bootstrap_owner_users_missing"
        assert session.execute(
            models.permissions.select().where(models.permissions.c.id == pending_permission_id)
        ).first() is None
        assert session.execute(
            models.audit_events.select().where(
                models.audit_events.c.organization_id == ORG_A,
                models.audit_events.c.action == "rbac.initial_owner_bootstrap_rejected",
            )
        ).first() is not None


def test_profile_transition_create_race_rechecks_payload_and_audits_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))
        owner_id = "018f6f73-2d0a-74f0-8f1c-000000001021"
        subject_id = "018f6f73-2d0a-74f0-8f1c-000000001022"
        legacy_role_id = "018f6f73-2d0a-74f0-8f1c-000000001023"
        target_role_id = "018f6f73-2d0a-74f0-8f1c-000000001018"

        def exact_racing_insert(
            inner_session: Session, mapping: dict[str, object], _: str
        ) -> None:
            inner_session.execute(models.profile_transition_mappings.insert().values(**mapping))
            inner_session.commit()
            raise IntegrityError("insert", {}, RuntimeError("simulated concurrent insert"))

        monkeypatch.setattr(operations, "_insert_profile_transition_mapping", exact_racing_insert)
        replay = create_profile_transition_mapping(
            session,
            organization_id=ORG_A,
            user_id=subject_id,
            legacy_role_id=legacy_role_id,
            target_role_id=target_role_id,
            target_branch_id=BRANCH_A,
            actor_user_id=owner_id,
            provenance="test-race-exact",
            idempotency_key="race-exact",
        )
        assert replay["status"] == "pending"
        assert session.execute(
            models.audit_events.select().where(
                models.audit_events.c.entity_id == replay["id"],
                models.audit_events.c.action == "profile_transition.pending_replayed",
            )
        ).first() is not None

        session.execute(
            models.profile_transition_mappings.delete().where(
                models.profile_transition_mappings.c.id == replay["id"]
            )
        )
        session.commit()

        def changed_racing_insert(
            inner_session: Session, mapping: dict[str, object], _: str
        ) -> None:
            changed = {**mapping, "provenance": "test-race-changed"}
            inner_session.execute(models.profile_transition_mappings.insert().values(**changed))
            inner_session.commit()
            raise IntegrityError("insert", {}, RuntimeError("simulated concurrent insert"))

        monkeypatch.setattr(operations, "_insert_profile_transition_mapping", changed_racing_insert)
        with pytest.raises(BusinessError) as conflicting_replay:
            create_profile_transition_mapping(
                session,
                organization_id=ORG_A,
                user_id=subject_id,
                legacy_role_id=legacy_role_id,
                target_role_id=target_role_id,
                target_branch_id=BRANCH_A,
                actor_user_id=owner_id,
                provenance="test-race-original",
                idempotency_key="race-changed",
            )
        assert conflicting_replay.value.code == "profile_transition_idempotency_conflict"


def test_profile_transition_rejects_stale_legacy_and_reassigned_target() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))
        owner_id = "018f6f73-2d0a-74f0-8f1c-000000001021"
        subject_id = "018f6f73-2d0a-74f0-8f1c-000000001022"
        legacy_role_id = "018f6f73-2d0a-74f0-8f1c-000000001023"
        target_role_id = "018f6f73-2d0a-74f0-8f1c-000000001018"
        stale = create_profile_transition_mapping(
            session,
            organization_id=ORG_A,
            user_id=subject_id,
            legacy_role_id=legacy_role_id,
            target_role_id=target_role_id,
            target_branch_id=BRANCH_A,
            actor_user_id=owner_id,
            provenance="test-stale-legacy",
            idempotency_key="stale-legacy-create",
        )
        session.execute(
            models.user_roles.delete().where(
                models.user_roles.c.user_id == subject_id,
                models.user_roles.c.role_id == legacy_role_id,
            )
        )
        session.commit()
        with pytest.raises(BusinessError) as stale_apply:
            apply_profile_transition_mapping(
                session,
                mapping_id=stale["id"],
                actor_user_id=owner_id,
                idempotency_key="stale-legacy-apply",
            )
        assert stale_apply.value.code == "profile_transition_legacy_role_stale"
        assert session.execute(
            models.profile_transition_mappings.select()
            .with_only_columns(models.profile_transition_mappings.c.status)
            .where(models.profile_transition_mappings.c.id == stale["id"])
        ).scalar_one() == "pending"
        assert session.execute(
            models.audit_events.select().where(
                models.audit_events.c.entity_id == stale["id"],
                models.audit_events.c.action == "profile_transition.rejected",
            )
        ).first() is not None

        session.execute(
            models.user_roles.insert().values(
                user_id=subject_id,
                role_id=legacy_role_id,
                branch_id=None,
            )
        )
        session.execute(
            models.profile_transition_mappings.delete().where(
                models.profile_transition_mappings.c.id == stale["id"]
            )
        )
        session.commit()
        mapped = create_profile_transition_mapping(
            session,
            organization_id=ORG_A,
            user_id=subject_id,
            legacy_role_id=legacy_role_id,
            target_role_id=target_role_id,
            target_branch_id=BRANCH_A,
            actor_user_id=owner_id,
            provenance="test-reassigned-target",
            idempotency_key="reassigned-create",
        )
        apply_profile_transition_mapping(
            session,
            mapping_id=mapped["id"],
            actor_user_id=owner_id,
            idempotency_key="reassigned-apply",
        )
        session.execute(
            models.user_roles.delete().where(
                models.user_roles.c.user_id == subject_id,
                models.user_roles.c.role_id == target_role_id,
            )
        )
        session.execute(
            models.user_roles.insert().values(
                user_id=subject_id,
                role_id=target_role_id,
                branch_id=BRANCH_A_OTHER,
            )
        )
        session.commit()
        with pytest.raises(BusinessError) as reassigned_reverse:
            reverse_profile_transition_mapping(
                session,
                mapping_id=mapped["id"],
                actor_user_id=owner_id,
                idempotency_key="reassigned-reverse",
            )
        assert reassigned_reverse.value.code == "profile_transition_target_assignment_conflict"
        assert session.execute(
            models.profile_transition_mappings.select()
            .with_only_columns(models.profile_transition_mappings.c.status)
            .where(models.profile_transition_mappings.c.id == mapped["id"])
        ).scalar_one() == "mapped"
        assert session.execute(
            models.user_roles.select().where(
                models.user_roles.c.user_id == subject_id,
                models.user_roles.c.role_id == target_role_id,
                models.user_roles.c.branch_id == BRANCH_A_OTHER,
            )
        ).first() is not None
        assert session.execute(
            models.audit_events.select().where(
                models.audit_events.c.entity_id == mapped["id"],
                models.audit_events.c.action == "profile_transition.rejected",
            )
        ).first() is not None


def test_profile_transition_rejects_legacy_branch_drift_from_snapshot() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))
        owner_id = "018f6f73-2d0a-74f0-8f1c-000000001021"
        subject_id = "018f6f73-2d0a-74f0-8f1c-000000001022"
        legacy_role_id = "018f6f73-2d0a-74f0-8f1c-000000001023"
        target_role_id = "018f6f73-2d0a-74f0-8f1c-000000001018"
        session.execute(
            models.user_roles.delete().where(
                models.user_roles.c.user_id == subject_id,
                models.user_roles.c.role_id == legacy_role_id,
            )
        )
        session.execute(
            models.user_roles.insert().values(
                user_id=subject_id,
                role_id=legacy_role_id,
                branch_id=BRANCH_A,
            )
        )
        session.commit()
        pending = create_profile_transition_mapping(
            session,
            organization_id=ORG_A,
            user_id=subject_id,
            legacy_role_id=legacy_role_id,
            target_role_id=target_role_id,
            target_branch_id=BRANCH_A,
            actor_user_id=owner_id,
            provenance="test-legacy-branch-drift",
            idempotency_key="legacy-branch-drift-create",
        )
        session.execute(
            models.user_roles.delete().where(
                models.user_roles.c.user_id == subject_id,
                models.user_roles.c.role_id == legacy_role_id,
            )
        )
        session.execute(
            models.user_roles.insert().values(
                user_id=subject_id,
                role_id=legacy_role_id,
                branch_id=BRANCH_A_OTHER,
            )
        )
        session.commit()
        with pytest.raises(BusinessError) as stale_apply:
            apply_profile_transition_mapping(
                session,
                mapping_id=pending["id"],
                actor_user_id=owner_id,
                idempotency_key="legacy-branch-drift-apply",
            )
        assert stale_apply.value.code == "profile_transition_legacy_role_stale"
        assert session.execute(
            models.profile_transition_mappings.select()
            .with_only_columns(models.profile_transition_mappings.c.status)
            .where(models.profile_transition_mappings.c.id == pending["id"])
        ).scalar_one() == "pending"
        assert session.execute(
            models.user_roles.select().where(
                models.user_roles.c.user_id == subject_id,
                models.user_roles.c.role_id == target_role_id,
            )
        ).first() is None


def test_cross_organization_transition_actor_is_audited_without_committing_caller_write() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))
        pending_permission_id = "018f6f73-2d0a-74f0-8f1c-000000001041"
        cross_organization_actor_id = "018f6f73-2d0a-74f0-8f1c-000000001025"
        session.execute(
            models.permissions.insert().values(
                id=pending_permission_id,
                code="pending.cross-org.must.rollback",
                description="must not commit",
                created_at=datetime(2026, 8, 10, tzinfo=UTC),
            )
        )
        with pytest.raises(AuthorizationError) as denied_actor:
            profile_transition_dry_run(
                session,
                organization_id=ORG_A,
                user_id="018f6f73-2d0a-74f0-8f1c-000000001022",
                legacy_role_id="018f6f73-2d0a-74f0-8f1c-000000001023",
                target_role_id="018f6f73-2d0a-74f0-8f1c-000000001018",
                target_branch_id=BRANCH_A,
                actor_user_id=cross_organization_actor_id,
            )
        assert denied_actor.value.code == "actor_not_authorized"
        assert session.execute(
            models.permissions.select().where(models.permissions.c.id == pending_permission_id)
        ).first() is None
        event = session.execute(
            models.audit_events.select().where(
                models.audit_events.c.organization_id == ORG_A,
                models.audit_events.c.actor_user_id == cross_organization_actor_id,
                models.audit_events.c.action == "authorization.denied",
            )
        ).mappings().one()
        assert event["payload"]["reason"] == "actor_not_authorized"


def test_profile_transition_invalid_organization_fails_before_authority_or_audit() -> None:
    engine = create_engine("sqlite+pysqlite://")
    models.metadata.create_all(engine)
    with Session(engine) as session:
        session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
        _seed_scope_fixture(session, datetime(2026, 8, 10, tzinfo=UTC))
        invalid_organization_id = "018f6f73-2d0a-74f0-8f1c-000000009999"
        with pytest.raises(BusinessError) as invalid_organization:
            create_profile_transition_mapping(
                session,
                organization_id=invalid_organization_id,
                user_id="018f6f73-2d0a-74f0-8f1c-000000001022",
                legacy_role_id="018f6f73-2d0a-74f0-8f1c-000000001023",
                target_role_id="018f6f73-2d0a-74f0-8f1c-000000001018",
                target_branch_id=BRANCH_A,
                actor_user_id="018f6f73-2d0a-74f0-8f1c-000000001021",
                provenance="test-invalid-organization",
                idempotency_key="invalid-organization-create",
            )
        assert invalid_organization.value.code == "profile_transition_organization_invalid"
        assert session.execute(models.profile_transition_mappings.select()).first() is None
        assert session.execute(
            models.audit_events.select().where(
                models.audit_events.c.organization_id == invalid_organization_id
            )
        ).first() is None


def _seed_scope_fixture(session: Session, now: datetime) -> None:
    for organization_id in (ORG_A, ORG_B):
        session.execute(
            models.organizations.insert().values(
                id=organization_id,
                name=f"Organization {organization_id[-1]}",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
    for legal_entity_id, organization_id in (
        ("018f6f73-2d0a-74f0-8f1c-000000001011", ORG_A),
        ("018f6f73-2d0a-74f0-8f1c-000000001012", ORG_B),
    ):
        session.execute(
            models.legal_entities.insert().values(
                id=legal_entity_id,
                organization_id=organization_id,
                name="Legal",
                tax_id=None,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
    for unit_id, organization_id, legal_entity_id in (
        ("018f6f73-2d0a-74f0-8f1c-000000001013", ORG_A, "018f6f73-2d0a-74f0-8f1c-000000001011"),
        ("018f6f73-2d0a-74f0-8f1c-000000001014", ORG_B, "018f6f73-2d0a-74f0-8f1c-000000001012"),
    ):
        session.execute(
            models.business_units.insert().values(
                id=unit_id,
                organization_id=organization_id,
                legal_entity_id=legal_entity_id,
                name="Unit",
                code=unit_id[-2:],
                unit_type="restaurant",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
    for branch_id, organization_id, legal_entity_id, unit_id in (
        (
            BRANCH_A,
            ORG_A,
            "018f6f73-2d0a-74f0-8f1c-000000001011",
            "018f6f73-2d0a-74f0-8f1c-000000001013",
        ),
        (
            BRANCH_A_OTHER,
            ORG_A,
            "018f6f73-2d0a-74f0-8f1c-000000001011",
            "018f6f73-2d0a-74f0-8f1c-000000001013",
        ),
        (
            BRANCH_B,
            ORG_B,
            "018f6f73-2d0a-74f0-8f1c-000000001012",
            "018f6f73-2d0a-74f0-8f1c-000000001014",
        ),
    ):
        session.execute(
            models.branches.insert().values(
                id=branch_id,
                organization_id=organization_id,
                legal_entity_id=legal_entity_id,
                business_unit_id=unit_id,
                name="Branch",
                code=branch_id[-2:],
                timezone="UTC",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
    permissions = {
        "pos.operate",
        "admin.manage",
        "future.specialized.permission",
        "access.organization.all_branches",
    }
    for index, code in enumerate(sorted(permissions), start=30):
        session.execute(
            models.permissions.insert().values(
                id=f"018f6f73-2d0a-74f0-8f1c-0000000010{index:02d}",
                code=code,
                description=code,
                created_at=now,
            )
        )
    session.execute(
        models.roles.insert(),
        [
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000001018",
                "organization_id": ORG_A,
                "name": "Dueño falsificado",
                "scope": "branch",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000001019",
                "organization_id": ORG_A,
                "name": "Cajero que dice Dueño",
                "scope": "organization",
                "created_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000001023",
                "organization_id": ORG_A,
                "name": "Administrador legacy sin authority",
                "scope": "organization",
                "created_at": now,
            },
        ],
    )
    permission_ids = dict(
        session.execute(
            models.permissions.select().with_only_columns(
                models.permissions.c.code, models.permissions.c.id
            )
        ).all()
    )
    session.execute(
        models.role_permissions.insert().values(
            role_id="018f6f73-2d0a-74f0-8f1c-000000001018",
            permission_id=permission_ids["pos.operate"],
        )
    )
    session.execute(
        models.role_permissions.insert().values(
            role_id="018f6f73-2d0a-74f0-8f1c-000000001023",
            permission_id=permission_ids["admin.manage"],
        )
    )
    session.execute(
        models.role_authority_grants.insert().values(
            role_id="018f6f73-2d0a-74f0-8f1c-000000001019",
            authority_kind="organization_all_permissions",
            created_at=now,
        )
    )
    session.execute(
        models.users.insert(),
        [
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000001020",
                "organization_id": ORG_A,
                "email": "cashier@example.test",
                "display_name": "Cashier",
                "employee_code": None,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000001021",
                "organization_id": ORG_A,
                "email": "owner@example.test",
                "display_name": "Owner",
                "employee_code": None,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000001022",
                "organization_id": ORG_A,
                "email": "legacy-admin@example.test",
                "display_name": "Legacy admin",
                "employee_code": None,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "018f6f73-2d0a-74f0-8f1c-000000001025",
                "organization_id": ORG_B,
                "email": "other-organization@example.test",
                "display_name": "Other organization",
                "employee_code": None,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )
    session.execute(
        models.user_roles.insert(),
        [
            {
                "user_id": "018f6f73-2d0a-74f0-8f1c-000000001020",
                "role_id": "018f6f73-2d0a-74f0-8f1c-000000001018",
                "branch_id": BRANCH_A,
            },
            {
                "user_id": "018f6f73-2d0a-74f0-8f1c-000000001021",
                "role_id": "018f6f73-2d0a-74f0-8f1c-000000001019",
                "branch_id": None,
            },
            {
                "user_id": "018f6f73-2d0a-74f0-8f1c-000000001022",
                "role_id": "018f6f73-2d0a-74f0-8f1c-000000001023",
                "branch_id": None,
            },
        ],
    )
    session.commit()
