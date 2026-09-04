from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import secrets
import unicodedata
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as BinasciiError

# ruff: noqa: E501, E402
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import wraps
from typing import Any, Callable, NoReturn, TypedDict, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.auth import (
    PASSWORD_ALGORITHM,
    generate_password_salt,
    hash_password,
    verify_password,
)
from restaurant_os.catalog_policy import (
    canonical_category_name,
    is_numeric_sku,
    is_uppercase_name,
    normalize_inventory_sku,
    normalize_product_sku,
)
from restaurant_os.config import get_settings
from restaurant_os.domain.errors import StateTransitionError
from restaurant_os.domain.order_state_machine import OrderState, OrderStateMachine

UTC = timezone.utc

ORGANIZATION_ID = "018f6f73-2d0a-74f0-8f1c-000000000001"
BRANCH_ID = "018f6f73-2d0a-74f0-8f1c-000000000003"
ADMIN_USER_ID = "018f6f73-2d0a-74f0-8f1c-000000000006"
DEFAULT_REGISTER = "CAJA-01"
ORDER_COMMENT_GROUP_ID = "__global_order_comments__"
INGREDIENT_EXTRA_GROUP_ID = "__universal_ingredient_extras__"
MAX_INGREDIENT_EXTRA_PORTIONS = 99
EMPLOYEE_CODE_PATTERN = re.compile(r"^[A-Z0-9]{6}$")
CATEGORY_OPTION_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
CASH_CONCEPT_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
INITIAL_OWNER_EMAILS = ("aniacuestas@gmail.com", "mangoex@gmail.com")
logger = logging.getLogger(__name__)
POS_HANDOFF_TTL_SECONDS = 60


def _record_pco008_metric(
    *,
    result: str,
    organization_id: str,
    branch_id: str,
    source_device_id: str,
    checkpoint: int | None = None,
    error_code: str | None = None,
    lag_seconds: int | None = None,
) -> None:
    """Emit protocol metadata only; never cash references, evidence, or grants."""
    extra: dict[str, Any] = {
        "metric": "pco008.sync",
        "result": result,
        "organization_id": organization_id,
        "branch_id": branch_id,
        "source_device_id": source_device_id,
    }
    if checkpoint is not None:
        extra["checkpoint"] = checkpoint
    if error_code:
        extra["error_code"] = error_code
    if lag_seconds is not None:
        extra["lag_seconds"] = lag_seconds
    logger.info("pco008.sync", extra=extra)


def _record_pco004_metric(
    metric: str,
    *,
    result: str,
    branch_id: str | None = None,
    error_code: str | None = None,
    value: int | None = None,
) -> None:
    """Emit a safe structured PCO-004 metric without command contents or PII."""
    extra: dict[str, Any] = {"metric": metric, "result": result}
    if branch_id:
        extra["branch_id"] = branch_id
    if error_code:
        extra["error_code"] = error_code
    if value is not None:
        extra["value"] = value
    logger.info(metric, extra=extra)


def _record_pco007_metric(
    metric: str,
    *,
    result: str,
    branch_id: str | None = None,
    error_code: str | None = None,
    duration_ms: int | None = None,
    item_count: int | None = None,
    incomplete_count: int | None = None,
    unknown_tax_count: int | None = None,
) -> None:
    """Safe recipe telemetry: scope and result only, never command contents or identity data."""
    extra: dict[str, Any] = {"metric": metric, "result": result}
    if branch_id is not None:
        extra["branch_id"] = branch_id
    if error_code is not None:
        extra["error_code"] = error_code
    if duration_ms is not None:
        extra["duration_ms"] = duration_ms
    if item_count is not None:
        extra["item_count"] = item_count
    if incomplete_count is not None:
        extra["incomplete_count"] = incomplete_count
    if unknown_tax_count is not None:
        extra["unknown_tax_count"] = unknown_tax_count
    logger.info(metric, extra=extra)


def _pco007_observed(
    metric: str, branch_from: Callable[..., str | None]
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Observe rejected PCO-007 requests without retaining command or identity data."""

    def decorate(operation: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(operation)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            started = _now()
            branch_id = branch_from(*args, **kwargs)
            try:
                return operation(*args, **kwargs)
            except AuthorizationError as exc:
                _record_pco007_metric(
                    metric,
                    result="denied",
                    branch_id=branch_id,
                    error_code=exc.code,
                    duration_ms=int((_now() - started).total_seconds() * 1000),
                )
                raise
            except BusinessError as exc:
                result = (
                    "conflict"
                    if exc.code
                    in {
                        "idempotency_conflict",
                        "recipe_version_conflict",
                        "report_cursor_invalid",
                    }
                    else "error"
                )
                _record_pco007_metric(
                    metric,
                    result=result,
                    branch_id=branch_id,
                    error_code=exc.code,
                    duration_ms=int((_now() - started).total_seconds() * 1000),
                )
                raise
            except Exception:
                _record_pco007_metric(
                    metric,
                    result="error",
                    branch_id=branch_id,
                    error_code="unexpected_error",
                    duration_ms=int((_now() - started).total_seconds() * 1000),
                )
                raise

        return wrapped

    return decorate


def record_pco004_metric(
    metric: str,
    *,
    result: str,
    branch_id: str | None = None,
    error_code: str | None = None,
    value: int | None = None,
) -> None:
    """Public boundary hook for PCO-004 rejections rejected before a domain command exists."""
    _record_pco004_metric(
        metric, result=result, branch_id=branch_id, error_code=error_code, value=value
    )


def _record_pco006_metric(
    metric: str,
    *,
    result: str,
    action: str | None = None,
    branch_id: str | None = None,
    error_code: str | None = None,
) -> None:
    """Emit PCO-006 telemetry without monetary values or request data."""
    extra: dict[str, Any] = {"metric": metric, "result": result}
    if branch_id:
        extra["branch_id"] = branch_id
    if action:
        extra["action"] = action
    if error_code:
        extra["error_code"] = error_code
    logger.info(metric, extra=extra)


def _observe_pco006_command(action: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Record only command outcome metadata; never command payloads or monetary values."""

    def decorate(command: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(command)
        def observed(self: Any, *args: Any, **kwargs: Any) -> Any:
            self._pco006_replayed = False
            action_name = action(self, *args, **kwargs) if callable(action) else action
            try:
                result = command(self, *args, **kwargs)
            except _UserCashCutCommandReplay as replay:
                self._pco006_replayed = True
                result = replay.result
            except BusinessError as exc:
                _record_pco006_metric(
                    "cash_cut_command_total",
                    result="error",
                    action=action_name,
                    error_code=exc.code,
                )
                raise
            _record_pco006_metric(
                "cash_cut_command_total",
                result="replay" if self._pco006_replayed else "success",
                action=action_name,
                error_code=None,
            )
            return result

        return observed

    return decorate


class BusinessError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _UserCashCutCommandReplay(Exception):
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result


class AuthorizationError(BusinessError):
    pass


class NotFoundError(BusinessError):
    pass


class OperationalCloseResponse(TypedDict):
    cash_shift: dict[str, Any]
    closure: dict[str, Any]


ADMIN_PERMISSIONS = {
    "admin.manage",
    "catalog.manage",
    "inventory.adjust",
    "orders.cancel",
    "cash.shift.read",
    "cash.shift.open",
    "cash.shift.close",
    "orders.read",
    "orders.create",
    "orders.amend",
    "payments.read",
    "payments.confirm",
    "print.jobs.read",
    "print.jobs.retry",
    "orders.fulfill",
    "dashboard.read",
    "pos.operate",
}


def get_open_cash_shift(
    session: Session,
    register_code: str = DEFAULT_REGISTER,
    branch_id: str | None = None,
) -> dict[str, Any] | None:
    rows = (
        session.execute(
            sa.select(models.cash_shifts)
            .where(
                models.cash_shifts.c.organization_id == ORGANIZATION_ID,
                models.cash_shifts.c.branch_id == (branch_id or BRANCH_ID),
                models.cash_shifts.c.register_code == register_code,
                sa.func.upper(models.cash_shifts.c.status) == "OPEN",
            )
            .order_by(models.cash_shifts.c.opened_at.desc())
        )
        .mappings()
        .all()
    )
    if len(rows) > 1:
        raise BusinessError("cash_shift_ambiguous", "More than one open cash shift exists")
    return dict(rows[0]) if rows else None


def _guard_open_cash_shift(session: Session, register_code: str, branch_id: str) -> dict[str, Any]:
    shift = get_open_cash_shift(session, register_code, branch_id)
    if not shift:
        raise BusinessError("cash_shift_not_open", "An OPEN cash shift is required")
    guarded = (
        session.execute(
            sa.select(models.cash_shifts)
            .where(
                models.cash_shifts.c.id == shift["id"],
                models.cash_shifts.c.organization_id == ORGANIZATION_ID,
            )
            .with_for_update()
        )
        .mappings()
        .one()
    )
    if str(guarded["status"]).upper() != "OPEN":
        raise BusinessError("cash_shift_not_open", "Cash shift is no longer OPEN")
    return dict(guarded)


def _begin_cash_shift_serialization(session: Session) -> None:
    """Start SQLite's database write reservation before reading an OPEN shift.

    PostgreSQL uses the row lock in ``_guard_open_cash_shift``.  SQLite does not
    implement ``FOR UPDATE``, so each cash command starts an IMMEDIATE transaction
    before authorization/concept reads can observe the shift.
    """
    if session.get_bind().dialect.name != "sqlite":
        return
    if session.in_transaction():
        # SQLAlchemy starts a deferred SQLite transaction on the first read.  It
        # cannot be upgraded safely, so discard that read-only transaction before
        # taking the write reservation required by the cash guard.
        session.rollback()
    try:
        session.execute(sa.text("BEGIN IMMEDIATE"))
    except OperationalError as exc:
        raise BusinessError(
            "cash_shift_busy", "Cash shift is being updated; retry the command"
        ) from exc


def _acquire_idempotency_lock(session: Session, namespace: str, key: str) -> None:
    if session.get_bind().dialect.name == "postgresql":
        session.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"{namespace}:{ORGANIZATION_ID}:{key}"},
        )


def create_role(
    session: Session,
    name: str,
    scope: str = "branch",
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    normalized_name = name.strip()
    normalized_scope = scope.strip().lower()
    if not normalized_name:
        raise BusinessError("invalid_role_name", "Role name is required")
    if normalized_scope not in {"organization", "branch"}:
        raise BusinessError("invalid_role_scope", "Role scope must be organization or branch")

    actor_user = session.execute(sa.select(models.users).where(models.users.c.id == actor_id)).mappings().first()
    target_org = actor_user["organization_id"] if actor_user and actor_user.get("organization_id") else ORGANIZATION_ID

    existing = (
        session.execute(
            sa.select(models.roles).where(
                models.roles.c.organization_id == target_org,
                sa.func.lower(models.roles.c.name) == normalized_name.lower(),
            )
        )
        .mappings()
        .first()
    )
    if existing:
        raise BusinessError("role_already_exists", "Role already exists")

    now = _now()
    role: dict[str, Any] = {
        "id": _id(),
        "organization_id": target_org,
        "name": normalized_name,
        "scope": normalized_scope,
        "created_at": now,
    }
    session.execute(models.roles.insert().values(**role))
    permission_codes = _assign_default_role_permissions(session, role["id"], normalized_name)
    _audit(
        session,
        action="role.created",
        entity_type="role",
        entity_id=role["id"],
        payload={
            "name": normalized_name,
            "scope": normalized_scope,
            "permissions": permission_codes,
        },
        actor_user_id=actor_id,
    )
    session.commit()
    return {**role, "permissions": permission_codes}


def _normalize_employee_code(value: Any, *, allow_empty: bool = False) -> str | None:
    normalized = str(value or "").strip().upper()
    if not normalized:
        if allow_empty:
            return None
        raise BusinessError("employee_code_required", "Employee code is required")
    if not EMPLOYEE_CODE_PATTERN.fullmatch(normalized):
        raise BusinessError(
            "employee_code_invalid_format",
            "Employee code must contain exactly 6 alphanumeric characters",
        )
    return normalized


def _assign_employee_code(
    session: Session,
    employee_code: str,
    *,
    subject_type: str,
    subject_id: str,
    organization_id: str | None = None,
) -> None:
    if not organization_id:
        if subject_type == "user":
            organization_id = session.execute(
                sa.select(models.users.c.organization_id).where(models.users.c.id == subject_id)
            ).scalar_one_or_none()
        elif subject_type == "driver":
            organization_id = session.execute(
                sa.select(models.drivers.c.organization_id).where(models.drivers.c.id == subject_id)
            ).scalar_one_or_none()
    org_id = organization_id or ORGANIZATION_ID

    owner = (
        session.execute(
            sa.select(models.employee_code_registry).where(
                models.employee_code_registry.c.organization_id == org_id,
                models.employee_code_registry.c.employee_code == employee_code,
            )
        )
        .mappings()
        .first()
    )
    if owner and (owner["subject_type"] != subject_type or owner["subject_id"] != subject_id):
        raise BusinessError(
            "employee_code_already_exists",
            "Employee code is already assigned to another person",
        )
    current = (
        session.execute(
            sa.select(models.employee_code_registry).where(
                models.employee_code_registry.c.organization_id == org_id,
                models.employee_code_registry.c.subject_type == subject_type,
                models.employee_code_registry.c.subject_id == subject_id,
            )
        )
        .mappings()
        .first()
    )
    if current and current["employee_code"] == employee_code:
        return
    now = _now()
    try:
        if current:
            session.execute(
                models.employee_code_registry.update()
                .where(
                    models.employee_code_registry.c.organization_id == org_id,
                    models.employee_code_registry.c.subject_type == subject_type,
                    models.employee_code_registry.c.subject_id == subject_id,
                )
                .values(employee_code=employee_code, updated_at=now)
            )
        else:
            session.execute(
                models.employee_code_registry.insert().values(
                    organization_id=org_id,
                    employee_code=employee_code,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    created_at=now,
                    updated_at=now,
                )
            )
    except sa.exc.IntegrityError as exc:
        session.rollback()
        raise BusinessError(
            "employee_code_already_exists",
            "Employee code is already assigned to another person",
        ) from exc


def create_user(
    session: Session,
    email: str,
    display_name: str,
    actor_user_id: str | None = None,
    password: str | None = None,
    role_id: str | None = None,
    branch_id: str | None = None,
    employee_code: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    normalized_email = email.strip().lower()
    normalized_name = display_name.strip()
    if "@" not in normalized_email or "." not in normalized_email.split("@")[-1]:
        raise BusinessError("invalid_user_email", "User email is invalid")
    if not normalized_name:
        raise BusinessError("invalid_display_name", "Display name is required")

    existing = (
        session.execute(sa.select(models.users).where(models.users.c.email == normalized_email))
        .mappings()
        .first()
    )
    if existing:
        raise BusinessError("user_already_exists", "User already exists")
    normalized_employee_code = _normalize_employee_code(employee_code)
    assert normalized_employee_code is not None
    actor_user = session.execute(sa.select(models.users).where(models.users.c.id == actor_id)).mappings().first()
    target_org = actor_user["organization_id"] if actor_user and actor_user.get("organization_id") else ORGANIZATION_ID

    role_scope = None
    if role_id:
        role_scope = _validate_role_assignment_scope(session, role_id, target_org, branch_id)
        _authorize_governed_profile_assignment(session, actor_id, role_scope)

    now = _now()
    has_password = bool((password or "").strip())
    user_id = _id()
    _assign_employee_code(
        session,
        normalized_employee_code,
        subject_type="user",
        subject_id=user_id,
        organization_id=target_org,
    )
    user = {
        "id": user_id,
        "organization_id": target_org,
        "email": normalized_email,
        "display_name": normalized_name,
        "employee_code": normalized_employee_code,
        "status": "active" if has_password else "invited",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.users.insert().values(**user))
    if has_password:
        _set_user_password(session, user_id, password or "", now)

    if role_scope:
        role_assignment = {"user_id": user_id, **role_scope}
        _insert_user_role_assignment(session, role_assignment, actor_id)

    _audit(
        session,
        action="user.created",
        entity_type="user",
        entity_id=user_id,
        payload={
            "email": normalized_email,
            "display_name": normalized_name,
            "credential": "configured" if has_password else "pending",
        },
        actor_user_id=actor_id,
    )
    session.commit()
    return user


def _ensure_platform_superadmin(session: Session) -> None:
    sa_email = "admin@possaas.com"
    existing = session.execute(
        sa.select(models.users).where(models.users.c.email == sa_email)
    ).mappings().first()
    if existing:
        return

    now = _now()
    org = session.execute(
        sa.select(models.organizations).where(models.organizations.c.name == "POS-SaaS HQ")
    ).mappings().first()

    if not org:
        org_id = _id()
        session.execute(
            models.organizations.insert().values(
                id=org_id,
                name="POS-SaaS HQ",
                status="active",
                plan="enterprise",
                subscription_status="active",
                monthly_fee_cents=0,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        org_id = str(org["id"])

    user_id = _id()
    salt = generate_password_salt()
    pw_hash = hash_password("admin123", salt)
    session.execute(
        models.users.insert().values(
            id=user_id,
            organization_id=org_id,
            email=sa_email,
            display_name="Superadmin SaaS",
            status="active",
            is_superadmin=True,
            created_at=now,
            updated_at=now,
        )
    )
    session.execute(
        models.user_credentials.insert().values(
            user_id=user_id,
            password_algorithm=PASSWORD_ALGORITHM,
            password_hash=pw_hash,
            password_salt=salt,
            updated_at=now,
        )
    )
    session.commit()


def authenticate_user(session: Session, email: str, password: str) -> dict[str, Any]:
    normalized_email = email.strip().lower()
    if normalized_email == "admin@possaas.com":
        _ensure_platform_superadmin(session)

    user = (
        session.execute(sa.select(models.users).where(models.users.c.email == normalized_email))
        .mappings()
        .first()
    )
    if not user:
        raise AuthorizationError("invalid_credentials", "Email or password is invalid")
    credential = (
        session.execute(
            sa.select(models.user_credentials).where(
                models.user_credentials.c.user_id == user["id"],
                models.user_credentials.c.password_algorithm == PASSWORD_ALGORITHM,
            )
        )
        .mappings()
        .first()
    )
    if not credential or not verify_password(
        password,
        credential["password_salt"],
        credential["password_hash"],
    ):
        _record_authorization_denied(
            session,
            actor_user_id=user["id"],
            permission_code="auth.login",
            branch_id=BRANCH_ID,
            reason="invalid_credentials",
        )
        raise AuthorizationError("invalid_credentials", "Email or password is invalid")
    if user["status"] != "active":
        _record_authorization_denied(
            session,
            actor_user_id=user["id"],
            permission_code="auth.login",
            branch_id=BRANCH_ID,
            reason="inactive_user",
        )
        raise AuthorizationError("inactive_user", "User is not active")

    # Check if tenant organization is suspended (only for non-superadmin accounts)
    is_sa = bool(user.get("is_superadmin")) or normalized_email in ("admin@possaas.com", "mangoex@gmail.com")
    if not is_sa:
        org = session.execute(
            sa.select(models.organizations).where(models.organizations.c.id == user["organization_id"])
        ).mappings().first()
        if org and org.get("subscription_status") == "suspended":
            _record_authorization_denied(
                session,
                actor_user_id=user["id"],
                permission_code="auth.login",
                branch_id=BRANCH_ID,
                reason="tenant_suspended",
            )
            raise AuthorizationError("tenant_suspended", "La cuenta de este restaurante se encuentra suspendida por pago pendiente.")
    _audit(
        session,
        action="auth.login",
        entity_type="user",
        entity_id=user["id"],
        payload={"email": normalized_email},
        actor_user_id=user["id"],
    )
    session.commit()
    profile = dict(user)
    access_rows = session.execute(
        sa.select(
            models.roles.c.name.label("role_name"),
            models.roles.c.scope,
            models.user_roles.c.branch_id.label("role_branch_id"),
            models.permissions.c.code.label("permission_code"),
        )
        .select_from(
            models.user_roles.join(
                models.roles,
                models.user_roles.c.role_id == models.roles.c.id,
            )
            .outerjoin(
                models.role_permissions,
                models.roles.c.id == models.role_permissions.c.role_id,
            )
            .outerjoin(
                models.permissions,
                models.role_permissions.c.permission_id == models.permissions.c.id,
            )
        )
        .where(models.user_roles.c.user_id == user["id"])
    ).mappings()
    roles = []
    permissions = set()
    # Collect the first branch_id scoped to a branch role (for Caja users)
    assigned_branch_id: str | None = None
    for row in access_rows:
        role_name = row["role_name"]
        if role_name and role_name not in roles:
            roles.append(role_name)
        if row["permission_code"]:
            permissions.add(row["permission_code"])
        # Branch-scoped roles carry the specific branch_id the user is assigned to
        if row["role_branch_id"] and not assigned_branch_id:
            assigned_branch_id = row["role_branch_id"]
    organization_authority = session.execute(
        sa.select(models.role_authority_grants.c.role_id)
        .select_from(
            models.user_roles.join(
                models.roles, models.user_roles.c.role_id == models.roles.c.id
            ).join(
                models.role_authority_grants,
                models.roles.c.id == models.role_authority_grants.c.role_id,
            )
        )
        .where(
            models.user_roles.c.user_id == user["id"],
            models.roles.c.organization_id == user["organization_id"],
            models.roles.c.scope == "organization",
            models.role_authority_grants.c.authority_kind == "organization_all_permissions",
        )
        .limit(1)
    ).scalar_one_or_none()
    is_sa = bool(user.get("is_superadmin")) or normalized_email in ("admin@possaas.com", "mangoex@gmail.com")
    if organization_authority or is_sa:
        permissions.update(session.execute(sa.select(models.permissions.c.code)).scalars().all())
    profile["roles"] = roles
    profile["permissions"] = sorted(permissions)
    profile["is_superadmin"] = is_sa
    # Expose the branch the user is assigned to (critical for POS auto-configuration)
    profile["assigned_branch_id"] = assigned_branch_id
    return profile


def authorize_supervisor_step_up(
    session: Session,
    supervisor_code_or_password: str,
    branch_id: str,
    permission_code: str = "orders.discount.authorize",
) -> dict[str, Any]:
    """Validates supervisor PIN / employee code / password, and checks branch permission."""
    code = supervisor_code_or_password.strip()
    if not code:
        raise AuthorizationError(
            "supervisor_auth_failed", "Supervisor PIN or credential is required"
        )

    user = None
    # 1. Look up by 6-char employee code in registry
    if len(code) == 6:
        reg = (
            session.execute(
                sa.select(models.employee_code_registry).where(
                    models.employee_code_registry.c.organization_id == ORGANIZATION_ID,
                    models.employee_code_registry.c.employee_code == code.upper(),
                    models.employee_code_registry.c.subject_type == "user",
                )
            )
            .mappings()
            .first()
        )
        if reg:
            user = (
                session.execute(
                    sa.select(models.users).where(
                        models.users.c.id == reg["subject_id"],
                        models.users.c.status == "active",
                    )
                )
                .mappings()
                .first()
            )

    # 2. Look up by password or PIN hash
    if not user:
        users = (
            session.execute(
                sa.select(models.users).where(
                    models.users.c.organization_id == ORGANIZATION_ID,
                    models.users.c.status == "active",
                )
            )
            .mappings()
            .all()
        )
        for u in users:
            cred = (
                session.execute(
                    sa.select(models.user_credentials).where(
                        models.user_credentials.c.user_id == u["id"],
                        models.user_credentials.c.password_algorithm == PASSWORD_ALGORITHM,
                    )
                )
                .mappings()
                .first()
            )
            if cred and verify_password(code, cred["password_salt"], cred["password_hash"]):
                user = u
                break

    if not user:
        raise AuthorizationError("supervisor_auth_failed", "Supervisor credentials or PIN invalid")

    # 3. Check permissions in branch
    has_authority = False
    for perm in (
        permission_code,
        "branch.admin.access",
        "admin.manage",
        "access.organization.all_branches",
    ):
        try:
            authorize_branch_scope(session, user["id"], perm, branch_id)
            has_authority = True
            break
        except AuthorizationError:
            continue

    if not has_authority:
        _record_authorization_denied(
            session,
            actor_user_id=user["id"],
            permission_code=permission_code,
            branch_id=branch_id,
            reason="supervisor_authority_missing",
        )
        raise AuthorizationError(
            "supervisor_permission_denied",
            "User does not have supervisor authorization authority for this branch",
        )

    _audit(
        session,
        action="supervisor.step_up_authorized",
        entity_type="branch",
        entity_id=branch_id,
        payload={"supervisor_user_id": user["id"], "permission_code": permission_code},
        actor_user_id=user["id"],
    )
    return {
        "authorized": True,
        "supervisor_user_id": user["id"],
        "supervisor_name": str(user.get("display_name") or user.get("email") or "Supervisor"),
        "branch_id": branch_id,
    }


def create_branch(
    session: Session,
    name: str,
    code: str,
    actor_user_id: str | None = None,
    business_unit_id: str | None = None,
    street: str | None = None,
    exterior_number: str | None = None,
    interior_number: str | None = None,
    neighborhood: str | None = None,
    postal_code: str | None = None,
    city: str | None = None,
    state: str | None = None,
    cross_streets: str | None = None,
    latitude: float | Decimal | str | None = None,
    longitude: float | Decimal | str | None = None,
    phone: str | None = None,
    google_review_url: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    normalized_name = name.strip()
    normalized_code = code.strip().upper()
    if not normalized_name:
        raise BusinessError("invalid_branch_name", "Branch name is required")
    if not normalized_code:
        raise BusinessError("invalid_branch_code", "Branch code is required")

    actor_user = session.execute(sa.select(models.users).where(models.users.c.id == actor_id)).mappings().first()
    target_org = actor_user["organization_id"] if actor_user and actor_user.get("organization_id") else ORGANIZATION_ID

    existing = (
        session.execute(
            sa.select(models.branches).where(
                models.branches.c.organization_id == target_org,
                models.branches.c.code == normalized_code,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        raise BusinessError("branch_already_exists", "Branch code already exists")

    business_unit_query = sa.select(models.business_units).where(
        models.business_units.c.organization_id == target_org,
        models.business_units.c.status == "active",
    )
    if business_unit_id:
        business_unit_query = business_unit_query.where(
            models.business_units.c.id == business_unit_id
        )
    business_unit = (
        session.execute(business_unit_query.order_by(models.business_units.c.created_at).limit(1))
        .mappings()
        .first()
    )
    if not business_unit:
        raise BusinessError("business_unit_not_found", "An active business unit is required")
    legal_entity_id = str(business_unit["legal_entity_id"])
    now = _now()
    branch = {
        "id": _id(),
        "organization_id": target_org,
        "legal_entity_id": legal_entity_id,
        "business_unit_id": business_unit["id"],
        "name": normalized_name,
        "code": normalized_code,
        "timezone": "America/Chihuahua",
        "status": "active",
        "street": str(street).strip() if street else None,
        "exterior_number": str(exterior_number).strip() if exterior_number else None,
        "interior_number": str(interior_number).strip() if interior_number else None,
        "neighborhood": str(neighborhood).strip() if neighborhood else None,
        "postal_code": str(postal_code).strip() if postal_code else None,
        "city": str(city).strip() if city else "Culiacán",
        "state": str(state).strip() if state else "Sinaloa",
        "cross_streets": str(cross_streets).strip() if cross_streets else None,
        "latitude": latitude if latitude is not None else None,
        "longitude": longitude if longitude is not None else None,
        "phone": str(phone).strip() if phone else None,
        "google_review_url": str(google_review_url).strip() if google_review_url else None,
        "created_at": now,
        "updated_at": now,
    }
    warehouse = {
        "id": _id(),
        "organization_id": target_org,
        "branch_id": branch["id"],
        "name": f"Almacen {normalized_name}",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.branches.insert().values(**branch))
    session.execute(models.warehouses.insert().values(**warehouse))
    _audit(
        session,
        action="branch.created",
        entity_type="branch",
        entity_id=branch["id"],
        payload={
            "name": normalized_name,
            "code": normalized_code,
            "business_unit_id": business_unit["id"],
            "warehouse_id": warehouse["id"],
            "cross_streets": branch["cross_streets"],
            "latitude": str(branch["latitude"]) if branch["latitude"] is not None else None,
            "longitude": str(branch["longitude"]) if branch["longitude"] is not None else None,
            "google_review_url": branch["google_review_url"],
        },
        branch_id=branch["id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return {**branch, "warehouse": warehouse}


def create_business_unit(
    session: Session,
    name: str,
    code: str,
    unit_type: str,
    legal_entity_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    normalized_name = name.strip()
    normalized_code = code.strip().upper()
    normalized_type = unit_type.strip().lower()
    if not normalized_name or not normalized_code:
        raise BusinessError("invalid_business_unit", "Business unit name and code are required")
    if normalized_type not in {"restaurant", "bakery", "production", "other"}:
        raise BusinessError(
            "invalid_business_unit_type",
            "Business unit type must be restaurant, bakery, production or other",
        )
    actor_user = session.execute(sa.select(models.users).where(models.users.c.id == actor_id)).mappings().first()
    target_org = actor_user["organization_id"] if actor_user and actor_user.get("organization_id") else ORGANIZATION_ID

    legal_entity = session.execute(
        sa.select(models.legal_entities.c.id).where(
            models.legal_entities.c.id == legal_entity_id,
            models.legal_entities.c.organization_id == target_org,
            models.legal_entities.c.status == "active",
        )
    ).scalar_one_or_none()
    if not legal_entity:
        raise BusinessError("legal_entity_not_found", "An active legal entity is required")
    duplicate = session.execute(
        sa.select(models.business_units.c.id).where(
            models.business_units.c.organization_id == target_org,
            models.business_units.c.code == normalized_code,
        )
    ).scalar_one_or_none()
    if duplicate:
        raise BusinessError("business_unit_already_exists", "Business unit code already exists")
    now = _now()
    business_unit: dict[str, Any] = {
        "id": _id(),
        "organization_id": target_org,
        "legal_entity_id": legal_entity_id,
        "name": normalized_name,
        "code": normalized_code,
        "unit_type": normalized_type,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.business_units.insert().values(**business_unit))
    _audit(
        session,
        action="business_unit.created",
        entity_type="business_unit",
        entity_id=business_unit["id"],
        payload={"name": normalized_name, "code": normalized_code, "unit_type": normalized_type},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return business_unit


def create_product(
    session: Session,
    name: str,
    sku: str,
    category_name: str,
    station: str,
    price_cents: int,
    image_url: str | None = None,
    actor_user_id: str | None = None,
    delivery_price_cents: int | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    actor = session.execute(sa.select(models.users).where(models.users.c.id == actor_id)).mappings().first()
    org_id = str(actor["organization_id"]) if actor else ORGANIZATION_ID

    normalized_name = name.strip()
    normalized_sku = normalize_product_sku(sku)
    normalized_category = category_name.strip()
    normalized_station = station.strip().lower()

    if not normalized_name:
        raise BusinessError("invalid_product_name", "Product name cannot be blank")
    if not normalized_sku:
        raise BusinessError("invalid_product_sku", "Product SKU cannot be blank")

    if org_id == ORGANIZATION_ID:
        if not is_uppercase_name(normalized_name):
            raise BusinessError("invalid_product_name", "Product name must be uppercase")
        if not is_numeric_sku(normalized_sku):
            raise BusinessError("invalid_product_sku", "Product SKU must contain only digits")
        if not normalized_category or normalized_category != canonical_category_name(
            normalized_category
        ):
            raise BusinessError("invalid_category_name", "Category name must be uppercase")

    if normalized_station in {"cocina", "kitchen"}:
        station_val = "cocina" if org_id != ORGANIZATION_ID else "kitchen"
    elif normalized_station in {"barra", "drinks"}:
        station_val = "barra" if org_id != ORGANIZATION_ID else "drinks"
    else:
        station_val = "packing"

    if price_cents <= 0:
        raise BusinessError("invalid_price", "Price must be positive")
    if delivery_price_cents is not None and delivery_price_cents <= 0:
        raise BusinessError("invalid_delivery_price", "Delivery price must be positive")

    existing = (
        session.execute(
            sa.select(models.products).where(
                models.products.c.organization_id == org_id,
                models.products.c.sku == normalized_sku,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        raise BusinessError("product_already_exists", "Product SKU already exists")

    now = _now()
    category = _get_or_create_category(session, normalized_category, now, organization_id=org_id)
    product = {
        "id": _id(),
        "organization_id": org_id,
        "category_id": category["id"],
        "name": normalized_name,
        "sku": normalized_sku,
        "description": "Producto de catálogo.",
        "station": station_val,
        "status": "active",
        "image_url": image_url.strip() if (image_url and image_url.strip()) else None,
        "delivery_price_cents": delivery_price_cents,
        "created_at": now,
        "updated_at": now,
    }
    price = {
        "id": _id(),
        "organization_id": org_id,
        "product_id": product["id"],
        "price_cents": price_cents,
        "currency": "MXN",
        "valid_from": now,
        "valid_to": None,
        "created_at": now,
    }

    user_branch = session.execute(
        sa.select(models.user_roles.c.branch_id).where(models.user_roles.c.user_id == actor_id)
    ).scalar()
    if not user_branch:
        user_branch = session.execute(
            sa.select(models.branches.c.id).where(models.branches.c.organization_id == org_id)
        ).scalar()
    target_branch_id = str(user_branch) if user_branch else BRANCH_ID

    availability = {
        "branch_id": target_branch_id,
        "product_id": product["id"],
        "is_available": True,
        "updated_at": now,
    }
    session.execute(models.products.insert().values(**product))
    session.execute(models.price_versions.insert().values(**price))
    session.execute(models.branch_product_availability.insert().values(**availability))
    _audit(
        session,
        action="product.created",
        entity_type="product",
        entity_id=product["id"],
        payload={"sku": normalized_sku, "price_cents": price_cents, "delivery_price_cents": delivery_price_cents, "station": station_val},
        actor_user_id=actor_id,
    )
    session.commit()
    return {
        **product,
        "category_name": category["name"],
        "price_cents": price_cents,
        "delivery_price_cents": delivery_price_cents,
        "currency": "MXN",
        "is_available": True,
    }


def record_inventory_opening_balance(
    session: Session,
    item_id: str,
    quantity_base_units: int,
    reason: str = "Saldo inicial",
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "inventory.adjust")
    normalized_item_id = item_id.strip()
    normalized_reason = reason.strip() or "Saldo inicial"
    if quantity_base_units <= 0:
        raise BusinessError("invalid_inventory_quantity", "Inventory quantity must be positive")

    item = (
        session.execute(
            sa.select(
                models.inventory_items.c.id,
                models.inventory_items.c.name,
                models.inventory_items.c.base_unit_id,
                models.inventory_units.c.code.label("unit_code"),
            )
            .select_from(
                models.inventory_items.join(
                    models.inventory_units,
                    models.inventory_items.c.base_unit_id == models.inventory_units.c.id,
                )
            )
            .where(
                models.inventory_items.c.id == normalized_item_id,
                models.inventory_items.c.organization_id == ORGANIZATION_ID,
                models.inventory_items.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not item:
        raise BusinessError("inventory_item_not_found", "Inventory item was not found")

    warehouse_id = _branch_warehouse_id(session)
    now = _now()
    movement = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "branch_id": BRANCH_ID,
        "warehouse_id": warehouse_id,
        "item_id": item["id"],
        "movement_type": "OPENING_BALANCE",
        "quantity_delta": quantity_base_units,
        "unit_id": item["base_unit_id"],
        "reason": normalized_reason,
        "source_type": "admin",
        "source_id": None,
        "created_at": now,
    }
    session.execute(models.inventory_movements.insert().values(**movement))
    _audit(
        session,
        action="inventory.opening_balance_recorded",
        entity_type="inventory_movement",
        entity_id=movement["id"],
        payload={
            "item_id": item["id"],
            "item_name": item["name"],
            "quantity_delta": quantity_base_units,
            "unit_code": item["unit_code"],
        },
        branch_id=BRANCH_ID,
        actor_user_id=actor_id,
    )
    session.commit()
    return {**movement, "item_name": item["name"], "unit_code": item["unit_code"]}


def assign_user_role(
    session: Session,
    user_id: str,
    role_id: str,
    branch_id: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    assignment = _validate_user_role_assignment(session, user_id, role_id, branch_id)
    _authorize_governed_profile_assignment(session, actor_id, assignment)
    result = _insert_user_role_assignment(session, assignment, actor_id)
    session.commit()
    return result


def _validate_user_role_assignment(
    session: Session,
    user_id: str,
    role_id: str,
    branch_id: str | None = None,
) -> dict[str, Any]:
    user = (
        session.execute(sa.select(models.users).where(models.users.c.id == user_id))
        .mappings()
        .first()
    )
    if not user:
        raise BusinessError("user_not_found", "User was not found")
    return {
        "user_id": user_id,
        **_validate_role_assignment_scope(session, role_id, user["organization_id"], branch_id),
    }


def _validate_role_assignment_scope(
    session: Session,
    role_id: str,
    organization_id: str,
    branch_id: str | None,
) -> dict[str, Any]:
    role = (
        session.execute(sa.select(models.roles).where(models.roles.c.id == role_id))
        .mappings()
        .first()
    )
    if not role:
        raise BusinessError("role_not_found", "Role was not found")
    if organization_id != role["organization_id"]:
        raise BusinessError("role_organization_mismatch", "Role belongs to another organization")
    if role["scope"] == "branch":
        if not branch_id:
            raise BusinessError(
                "branch_assignment_required", "Branch-scoped roles require an explicit branch"
            )
        branch = session.execute(
            sa.select(models.branches.c.id).where(
                models.branches.c.id == branch_id,
                models.branches.c.organization_id == organization_id,
                models.branches.c.status == "active",
            )
        ).first()
        if not branch:
            raise BusinessError("branch_scope_denied", "Branch is outside the user's organization")
        return {"role_id": role_id, "branch_id": branch_id}
    if branch_id:
        raise BusinessError(
            "organization_role_branch_forbidden",
            "Organization-scoped roles cannot be assigned to one branch",
        )
    return {"role_id": role_id, "branch_id": None}


def _authorize_governed_profile_assignment(
    session: Session,
    actor_user_id: str,
    assignment: dict[str, Any],
) -> None:
    role_id = str(assignment["role_id"])
    is_owner_profile = session.execute(
        sa.select(models.role_authority_grants.c.role_id).where(
            models.role_authority_grants.c.role_id == role_id,
            models.role_authority_grants.c.authority_kind == "organization_all_permissions",
        )
    ).scalar_one_or_none()
    if not is_owner_profile:
        return
    organization_id = session.execute(
        sa.select(models.roles.c.organization_id).where(models.roles.c.id == role_id)
    ).scalar_one()

    # Superadmin or organization owner bypass
    actor_user = session.execute(
        sa.select(models.users).where(models.users.c.id == actor_user_id)
    ).mappings().first()
    if actor_user and actor_user.get("is_superadmin"):
        return
    org = session.execute(
        sa.select(models.organizations).where(models.organizations.c.id == organization_id)
    ).mappings().first()
    if org and actor_user and (org.get("owner_email") == actor_user.get("email")):
        return

    actor_has_owner_authority = session.execute(
        sa.select(models.user_roles.c.user_id)
        .select_from(
            models.user_roles.join(
                models.roles, models.user_roles.c.role_id == models.roles.c.id
            ).join(
                models.role_authority_grants,
                models.roles.c.id == models.role_authority_grants.c.role_id,
            )
        )
        .where(
            models.user_roles.c.user_id == actor_user_id,
            models.roles.c.organization_id == organization_id,
            models.roles.c.scope == "organization",
            models.role_authority_grants.c.authority_kind == "organization_all_permissions",
        )
        .limit(1)
    ).scalar_one_or_none()
    if actor_has_owner_authority:
        return
    _record_authorization_denied(
        session,
        actor_user_id=actor_user_id or None,
        permission_code="access.organization.all_branches",
        branch_id=None,
        reason="owner_authority_required",
    )
    raise AuthorizationError(
        "owner_authority_required",
        "Only an existing owner authority can assign this profile",
    )


def _insert_user_role_assignment(
    session: Session,
    assignment: dict[str, Any],
    actor_user_id: str | None,
) -> dict[str, Any]:
    user_id = assignment["user_id"]
    role_id = assignment["role_id"]
    normalized_branch_id = assignment["branch_id"]
    existing = (
        session.execute(
            sa.select(models.user_roles).where(
                models.user_roles.c.user_id == user_id,
                models.user_roles.c.role_id == role_id,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        if existing["branch_id"] != normalized_branch_id:
            session.execute(
                sa.update(models.user_roles)
                .where(
                    models.user_roles.c.user_id == user_id,
                    models.user_roles.c.role_id == role_id,
                )
                .values(branch_id=normalized_branch_id)
            )
            _audit(
                session,
                action="user_role.updated",
                entity_type="user",
                entity_id=user_id,
                payload={"role_id": role_id, "branch_id": normalized_branch_id},
                branch_id=normalized_branch_id or BRANCH_ID,
                actor_user_id=actor_user_id,
            )
        return dict(existing)

    session.execute(models.user_roles.insert().values(**assignment))
    _audit(
        session,
        action="user_role.assigned",
        entity_type="user",
        entity_id=user_id,
        payload={"role_id": role_id, "branch_id": normalized_branch_id},
        branch_id=normalized_branch_id or BRANCH_ID,
        actor_user_id=actor_user_id,
    )
    return assignment


def bootstrap_initial_owners(
    session: Session,
    *,
    organization_id: str,
    owner_emails: tuple[str, str] | list[str],
    operational_actor_user_id: str,
    provenance: str,
) -> dict[str, Any]:
    """Run the approved, non-HTTP initial Owner bootstrap for one organization."""
    normalized_organization_id = organization_id.strip()
    normalized_actor_id = _actor_user_id(operational_actor_user_id)
    normalized_provenance = provenance.strip()
    normalized_emails = tuple(sorted(str(email).strip().lower() for email in owner_emails))
    expected_emails = tuple(sorted(INITIAL_OWNER_EMAILS))
    if normalized_emails != expected_emails or len(set(normalized_emails)) != len(expected_emails):
        raise BusinessError(
            "bootstrap_owner_input_invalid",
            "Initial owner bootstrap requires exactly the approved configured emails",
        )
    if not normalized_provenance:
        raise BusinessError("bootstrap_provenance_required", "Bootstrap provenance is required")

    organization = session.execute(
        sa.select(models.organizations.c.id).where(
            models.organizations.c.id == normalized_organization_id,
            models.organizations.c.status == "active",
        )
    ).scalar_one_or_none()
    if not organization:
        raise BusinessError("bootstrap_organization_invalid", "Bootstrap organization is invalid")
    actor = session.execute(
        sa.select(models.users.c.id).where(
            models.users.c.id == normalized_actor_id,
            models.users.c.organization_id == normalized_organization_id,
            models.users.c.status == "active",
        )
    ).scalar_one_or_none()
    if not actor:
        raise BusinessError(
            "bootstrap_operational_actor_invalid",
            "Operational bootstrap actor must be an active organization user",
        )

    owner_role_id = _organization_authority_role_id(session, normalized_organization_id)
    if owner_role_id is None:
        _reject_bootstrap(
            session,
            normalized_organization_id,
            normalized_actor_id,
            normalized_provenance,
            "bootstrap_owner_role_ambiguous",
        )
    users = {
        row["email"].lower(): dict(row)
        for row in session.execute(
            sa.select(models.users.c.id, models.users.c.email, models.users.c.status).where(
                models.users.c.organization_id == normalized_organization_id,
                sa.func.lower(models.users.c.email).in_(normalized_emails),
            )
        ).mappings()
    }
    if set(users) != set(normalized_emails):
        _reject_bootstrap(
            session,
            normalized_organization_id,
            normalized_actor_id,
            normalized_provenance,
            "bootstrap_owner_users_missing",
        )
    if any(user["status"] != "active" for user in users.values()):
        _reject_bootstrap(
            session,
            normalized_organization_id,
            normalized_actor_id,
            normalized_provenance,
            "bootstrap_owner_users_inactive",
        )
    owner_user_ids = sorted(user["id"] for user in users.values())
    existing = _organization_authority_assignments(session, normalized_organization_id)
    expected = {(user_id, owner_role_id, None) for user_id in owner_user_ids}
    if existing:
        if existing == expected:
            _audit(
                session,
                action="rbac.initial_owners_bootstrap_replayed",
                entity_type="role_profile",
                entity_id=owner_role_id,
                payload={
                    "owner_user_ids": owner_user_ids,
                    "owner_count": len(owner_user_ids),
                    "provenance": normalized_provenance,
                },
                branch_id=None,
                organization_id=normalized_organization_id,
                actor_user_id=normalized_actor_id,
            )
            session.commit()
            return {"status": "already_bootstrapped", "owner_user_ids": owner_user_ids}
        _reject_bootstrap(
            session,
            normalized_organization_id,
            normalized_actor_id,
            normalized_provenance,
            "bootstrap_owner_assignment_conflict",
        )

    try:
        session.execute(
            models.user_roles.insert(),
            [
                {"user_id": user_id, "role_id": owner_role_id, "branch_id": None}
                for user_id in owner_user_ids
            ],
        )
        _audit(
            session,
            action="rbac.initial_owners_bootstrapped",
            entity_type="role_profile",
            entity_id=owner_role_id,
            payload={
                "owner_user_ids": owner_user_ids,
                "owner_count": len(owner_user_ids),
                "provenance": normalized_provenance,
            },
            branch_id=None,
            organization_id=normalized_organization_id,
            actor_user_id=normalized_actor_id,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        existing = _organization_authority_assignments(session, normalized_organization_id)
        if existing == expected:
            return bootstrap_initial_owners(
                session,
                organization_id=normalized_organization_id,
                owner_emails=list(normalized_emails),
                operational_actor_user_id=normalized_actor_id,
                provenance=normalized_provenance,
            )
        raise BusinessError(
            "bootstrap_owner_assignment_conflict",
            "Initial owner bootstrap conflicts with an existing assignment",
        ) from exc
    return {"status": "bootstrapped", "owner_user_ids": owner_user_ids}


def profile_transition_dry_run(
    session: Session,
    *,
    organization_id: str,
    user_id: str,
    legacy_role_id: str,
    target_role_id: str,
    target_branch_id: str | None,
    actor_user_id: str,
) -> dict[str, Any]:
    context = _validate_profile_transition_context(
        session,
        organization_id=organization_id,
        user_id=user_id,
        legacy_role_id=legacy_role_id,
        target_role_id=target_role_id,
        target_branch_id=target_branch_id,
        actor_user_id=actor_user_id,
    )
    _audit(
        session,
        action="profile_transition.dry_run",
        entity_type="profile_transition",
        entity_id=user_id,
        payload={
            "legacy_role_id": legacy_role_id,
            "target_role_id": target_role_id,
            "target_branch_id": context["target_assignment"]["branch_id"],
            "snapshot_role_count": len(context["role_snapshot"]),
        },
        branch_id=context["target_assignment"]["branch_id"],
        organization_id=organization_id,
        actor_user_id=actor_user_id,
    )
    session.commit()
    return {
        "organization_id": organization_id,
        "user_id": user_id,
        "legacy_role_id": legacy_role_id,
        "target_role_id": target_role_id,
        "target_branch_id": context["target_assignment"]["branch_id"],
        "role_snapshot": context["role_snapshot"],
    }


def create_profile_transition_mapping(
    session: Session,
    *,
    organization_id: str,
    user_id: str,
    legacy_role_id: str,
    target_role_id: str,
    target_branch_id: str | None,
    actor_user_id: str,
    provenance: str,
    idempotency_key: str,
) -> dict[str, Any]:
    normalized_key = _transition_idempotency_key(idempotency_key)
    normalized_provenance = provenance.strip()
    if not normalized_provenance:
        raise BusinessError(
            "profile_transition_provenance_required", "Transition provenance is required"
        )
    _require_active_profile_transition_organization(session, organization_id)
    _require_transition_authority(session, actor_user_id, organization_id)
    existing = (
        session.execute(
            sa.select(models.profile_transition_mappings).where(
                models.profile_transition_mappings.c.organization_id == organization_id,
                models.profile_transition_mappings.c.create_idempotency_key == normalized_key,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        mapping = dict(existing)
        return _replay_profile_transition_create(
            session,
            mapping=mapping,
            user_id=user_id,
            legacy_role_id=legacy_role_id,
            target_role_id=target_role_id,
            target_branch_id=target_branch_id,
            provenance=normalized_provenance,
            actor_user_id=actor_user_id,
        )
    context = _validate_profile_transition_context(
        session,
        organization_id=organization_id,
        user_id=user_id,
        legacy_role_id=legacy_role_id,
        target_role_id=target_role_id,
        target_branch_id=target_branch_id,
        actor_user_id=actor_user_id,
        organization_validated=True,
        authority_validated=True,
    )
    mapping = {
        "id": _id(),
        "organization_id": organization_id,
        "user_id": user_id,
        "legacy_role_id": legacy_role_id,
        "target_role_id": target_role_id,
        "target_branch_id": context["target_assignment"]["branch_id"],
        "status": "pending",
        "mapped_by_user_id": None,
        "role_snapshot": context["role_snapshot"],
        "provenance": normalized_provenance,
        "create_idempotency_key": normalized_key,
        "apply_idempotency_key": None,
        "reverse_idempotency_key": None,
        "created_at": _now(),
        "applied_at": None,
        "reversed_at": None,
    }
    try:
        _insert_profile_transition_mapping(session, mapping, actor_user_id)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        retry = (
            session.execute(
                sa.select(models.profile_transition_mappings).where(
                    models.profile_transition_mappings.c.organization_id == organization_id,
                    models.profile_transition_mappings.c.create_idempotency_key == normalized_key,
                )
            )
            .mappings()
            .first()
        )
        if retry:
            return _replay_profile_transition_create(
                session,
                mapping=dict(retry),
                user_id=user_id,
                legacy_role_id=legacy_role_id,
                target_role_id=target_role_id,
                target_branch_id=target_branch_id,
                provenance=normalized_provenance,
                actor_user_id=actor_user_id,
            )
        raise BusinessError(
            "profile_transition_conflict", "An active transition already exists"
        ) from exc
    return _profile_transition_result(mapping)


def apply_profile_transition_mapping(
    session: Session,
    *,
    mapping_id: str,
    actor_user_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    mapping = _get_profile_transition_mapping(session, mapping_id)
    _require_active_profile_transition_organization(session, mapping["organization_id"])
    _require_transition_authority(session, actor_user_id, mapping["organization_id"])
    normalized_key = _transition_idempotency_key(idempotency_key)
    if mapping["status"] == "mapped" and mapping["apply_idempotency_key"] == normalized_key:
        _audit(
            session,
            action="profile_transition.applied_replayed",
            entity_type="profile_transition",
            entity_id=mapping_id,
            payload={"user_id": mapping["user_id"], "target_role_id": mapping["target_role_id"]},
            branch_id=mapping["target_branch_id"],
            organization_id=mapping["organization_id"],
            actor_user_id=actor_user_id,
        )
        session.commit()
        return _profile_transition_result(mapping)
    if mapping["status"] != "pending":
        raise BusinessError("profile_transition_not_pending", "Transition is not pending")
    legacy_snapshot = next(
        (
            role
            for role in mapping["role_snapshot"] or []
            if role["role_id"] == mapping["legacy_role_id"]
        ),
        None,
    )
    legacy_assignment = (
        session.execute(
            sa.select(models.user_roles.c.branch_id).where(
                models.user_roles.c.user_id == mapping["user_id"],
                models.user_roles.c.role_id == mapping["legacy_role_id"],
            )
        )
        .mappings()
        .first()
    )
    if (
        not legacy_snapshot
        or not legacy_assignment
        or (legacy_assignment["branch_id"] != legacy_snapshot["branch_id"])
    ):
        _reject_profile_transition(
            session,
            mapping=mapping,
            actor_user_id=actor_user_id,
            code="profile_transition_legacy_role_stale",
        )
    assignment = _validate_role_assignment_scope(
        session,
        mapping["target_role_id"],
        mapping["organization_id"],
        mapping["target_branch_id"],
    )
    existing_target = session.execute(
        sa.select(models.user_roles.c.role_id).where(
            models.user_roles.c.user_id == mapping["user_id"],
            models.user_roles.c.role_id == assignment["role_id"],
        )
    ).scalar_one_or_none()
    if existing_target:
        raise BusinessError(
            "profile_transition_target_already_assigned", "Target role is already assigned"
        )
    now = _now()
    session.execute(models.user_roles.insert().values(user_id=mapping["user_id"], **assignment))
    session.execute(
        models.profile_transition_mappings.update()
        .where(models.profile_transition_mappings.c.id == mapping_id)
        .values(
            status="mapped",
            mapped_by_user_id=actor_user_id,
            apply_idempotency_key=normalized_key,
            applied_at=now,
        )
    )
    _audit(
        session,
        action="profile_transition.applied",
        entity_type="profile_transition",
        entity_id=mapping_id,
        payload={"user_id": mapping["user_id"], "target_role_id": mapping["target_role_id"]},
        branch_id=mapping["target_branch_id"],
        organization_id=mapping["organization_id"],
        actor_user_id=actor_user_id,
    )
    session.commit()
    return _profile_transition_result(
        {**mapping, "status": "mapped", "apply_idempotency_key": normalized_key, "applied_at": now}
    )


def reverse_profile_transition_mapping(
    session: Session,
    *,
    mapping_id: str,
    actor_user_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    mapping = _get_profile_transition_mapping(session, mapping_id)
    _require_active_profile_transition_organization(session, mapping["organization_id"])
    _require_transition_authority(session, actor_user_id, mapping["organization_id"])
    normalized_key = _transition_idempotency_key(idempotency_key)
    if mapping["status"] == "reversed" and mapping["reverse_idempotency_key"] == normalized_key:
        _audit(
            session,
            action="profile_transition.reversed_replayed",
            entity_type="profile_transition",
            entity_id=mapping_id,
            payload={"user_id": mapping["user_id"], "target_role_id": mapping["target_role_id"]},
            branch_id=mapping["target_branch_id"],
            organization_id=mapping["organization_id"],
            actor_user_id=actor_user_id,
        )
        session.commit()
        return _profile_transition_result(mapping)
    if mapping["status"] != "mapped":
        raise BusinessError("profile_transition_not_mapped", "Transition is not mapped")
    target_assignment = (
        session.execute(
            sa.select(models.user_roles.c.branch_id).where(
                models.user_roles.c.user_id == mapping["user_id"],
                models.user_roles.c.role_id == mapping["target_role_id"],
            )
        )
        .mappings()
        .first()
    )
    if not target_assignment or target_assignment["branch_id"] != mapping["target_branch_id"]:
        _reject_profile_transition(
            session,
            mapping=mapping,
            actor_user_id=actor_user_id,
            code="profile_transition_target_assignment_conflict",
        )
    snapshot = list(mapping["role_snapshot"] or [])
    snapshot_role_ids = {item["role_id"] for item in snapshot}
    current_role_ids = set(
        session.execute(
            sa.select(models.user_roles.c.role_id).where(
                models.user_roles.c.user_id == mapping["user_id"]
            )
        ).scalars()
    )
    for role in snapshot:
        if role["role_id"] not in current_role_ids:
            session.execute(
                models.user_roles.insert().values(
                    user_id=mapping["user_id"],
                    role_id=role["role_id"],
                    branch_id=role["branch_id"],
                )
            )
    if mapping["target_role_id"] not in snapshot_role_ids:
        target_branch_clause = (
            models.user_roles.c.branch_id.is_(None)
            if mapping["target_branch_id"] is None
            else models.user_roles.c.branch_id == mapping["target_branch_id"]
        )
        session.execute(
            models.user_roles.delete().where(
                models.user_roles.c.user_id == mapping["user_id"],
                models.user_roles.c.role_id == mapping["target_role_id"],
                target_branch_clause,
            )
        )
    now = _now()
    session.execute(
        models.profile_transition_mappings.update()
        .where(models.profile_transition_mappings.c.id == mapping_id)
        .values(status="reversed", reverse_idempotency_key=normalized_key, reversed_at=now)
    )
    _audit(
        session,
        action="profile_transition.reversed",
        entity_type="profile_transition",
        entity_id=mapping_id,
        payload={"user_id": mapping["user_id"], "target_role_id": mapping["target_role_id"]},
        branch_id=mapping["target_branch_id"],
        organization_id=mapping["organization_id"],
        actor_user_id=actor_user_id,
    )
    session.commit()
    return _profile_transition_result(
        {
            **mapping,
            "status": "reversed",
            "reverse_idempotency_key": normalized_key,
            "reversed_at": now,
        }
    )


def _insert_profile_transition_mapping(
    session: Session, mapping: dict[str, Any], actor_user_id: str
) -> None:
    session.execute(models.profile_transition_mappings.insert().values(**mapping))
    _audit(
        session,
        action="profile_transition.pending",
        entity_type="profile_transition",
        entity_id=mapping["id"],
        payload={
            "user_id": mapping["user_id"],
            "target_role_id": mapping["target_role_id"],
            "provenance": mapping["provenance"],
        },
        branch_id=mapping["target_branch_id"],
        organization_id=mapping["organization_id"],
        actor_user_id=actor_user_id,
    )


def _replay_profile_transition_create(
    session: Session,
    *,
    mapping: dict[str, Any],
    user_id: str,
    legacy_role_id: str,
    target_role_id: str,
    target_branch_id: str | None,
    provenance: str,
    actor_user_id: str,
) -> dict[str, Any]:
    expected = {
        "user_id": user_id,
        "legacy_role_id": legacy_role_id,
        "target_role_id": target_role_id,
        "target_branch_id": target_branch_id,
        "provenance": provenance,
    }
    if any(mapping[field] != value for field, value in expected.items()):
        raise BusinessError(
            "profile_transition_idempotency_conflict", "Transition key payload differs"
        )
    _audit(
        session,
        action="profile_transition.pending_replayed",
        entity_type="profile_transition",
        entity_id=mapping["id"],
        payload={"user_id": user_id, "target_role_id": target_role_id},
        branch_id=mapping["target_branch_id"],
        organization_id=mapping["organization_id"],
        actor_user_id=actor_user_id,
    )
    session.commit()
    return _profile_transition_result(mapping)


def _reject_profile_transition(
    session: Session,
    *,
    mapping: dict[str, Any],
    actor_user_id: str,
    code: str,
) -> NoReturn:
    session.rollback()
    _audit(
        session,
        action="profile_transition.rejected",
        entity_type="profile_transition",
        entity_id=mapping["id"],
        payload={"reason": code},
        branch_id=mapping["target_branch_id"],
        organization_id=mapping["organization_id"],
        actor_user_id=actor_user_id,
    )
    session.commit()
    raise BusinessError(code, "Profile transition was rejected")


def _organization_authority_role_id(session: Session, organization_id: str) -> str | None:
    role_ids = (
        session.execute(
            sa.select(models.roles.c.id)
            .select_from(
                models.roles.join(
                    models.role_authority_grants,
                    models.roles.c.id == models.role_authority_grants.c.role_id,
                )
            )
            .where(
                models.roles.c.organization_id == organization_id,
                models.roles.c.scope == "organization",
                models.role_authority_grants.c.authority_kind == "organization_all_permissions",
            )
        )
        .scalars()
        .all()
    )
    return role_ids[0] if len(role_ids) == 1 else None


def _organization_authority_assignments(
    session: Session, organization_id: str
) -> set[tuple[str, str, str | None]]:
    return {
        (row["user_id"], row["role_id"], row["branch_id"])
        for row in session.execute(
            sa.select(
                models.user_roles.c.user_id,
                models.user_roles.c.role_id,
                models.user_roles.c.branch_id,
            )
            .select_from(
                models.user_roles.join(
                    models.roles, models.user_roles.c.role_id == models.roles.c.id
                ).join(
                    models.role_authority_grants,
                    models.roles.c.id == models.role_authority_grants.c.role_id,
                )
            )
            .where(
                models.roles.c.organization_id == organization_id,
                models.role_authority_grants.c.authority_kind == "organization_all_permissions",
            )
        ).mappings()
    }


def _reject_bootstrap(
    session: Session,
    organization_id: str,
    actor_user_id: str,
    provenance: str,
    code: str,
) -> NoReturn:
    session.rollback()
    _audit(
        session,
        action="rbac.initial_owner_bootstrap_rejected",
        entity_type="owner_bootstrap",
        entity_id=organization_id,
        payload={"reason": code, "provenance": provenance},
        branch_id=None,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
    )
    session.commit()
    raise BusinessError(code, "Initial owner bootstrap was rejected")


def _require_transition_authority(
    session: Session, actor_user_id: str, organization_id: str
) -> None:
    actor = session.execute(
        sa.select(models.users.c.id).where(
            models.users.c.id == actor_user_id,
            models.users.c.organization_id == organization_id,
            models.users.c.status == "active",
        )
    ).scalar_one_or_none()
    if not actor:
        session.rollback()
        persisted_actor_id = session.execute(
            sa.select(models.users.c.id).where(models.users.c.id == actor_user_id)
        ).scalar_one_or_none()
        _audit(
            session,
            action="authorization.denied",
            entity_type="permission",
            entity_id="access.organization.all_branches",
            payload={
                "permission": "access.organization.all_branches",
                "reason": "actor_not_authorized",
            },
            branch_id=None,
            organization_id=organization_id,
            actor_user_id=persisted_actor_id,
        )
        session.commit()
        raise AuthorizationError("actor_not_authorized", "Transition actor is not authorized")
    has_authority = session.execute(
        sa.select(models.user_roles.c.user_id)
        .select_from(
            models.user_roles.join(
                models.roles, models.user_roles.c.role_id == models.roles.c.id
            ).join(
                models.role_authority_grants,
                models.roles.c.id == models.role_authority_grants.c.role_id,
            )
        )
        .where(
            models.user_roles.c.user_id == actor_user_id,
            models.roles.c.organization_id == organization_id,
            models.roles.c.scope == "organization",
            models.role_authority_grants.c.authority_kind == "organization_all_permissions",
        )
    ).scalar_one_or_none()
    if has_authority:
        return
    session.rollback()
    _audit(
        session,
        action="authorization.denied",
        entity_type="permission",
        entity_id="access.organization.all_branches",
        payload={
            "permission": "access.organization.all_branches",
            "reason": "owner_authority_required",
        },
        branch_id=None,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
    )
    session.commit()
    raise AuthorizationError(
        "owner_authority_required", "Transition requires organization authority"
    )


def _require_active_profile_transition_organization(session: Session, organization_id: str) -> None:
    organization = session.execute(
        sa.select(models.organizations.c.id).where(
            models.organizations.c.id == organization_id,
            models.organizations.c.status == "active",
        )
    ).scalar_one_or_none()
    if organization:
        return
    session.rollback()
    raise BusinessError(
        "profile_transition_organization_invalid", "Transition organization is invalid"
    )


def _validate_profile_transition_context(
    session: Session,
    *,
    organization_id: str,
    user_id: str,
    legacy_role_id: str,
    target_role_id: str,
    target_branch_id: str | None,
    actor_user_id: str,
    organization_validated: bool = False,
    authority_validated: bool = False,
) -> dict[str, Any]:
    if not organization_validated:
        _require_active_profile_transition_organization(session, organization_id)
    if not authority_validated:
        _require_transition_authority(session, actor_user_id, organization_id)
    user = session.execute(
        sa.select(models.users.c.id).where(
            models.users.c.id == user_id,
            models.users.c.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if not user:
        raise BusinessError("profile_transition_user_not_found", "Transition user was not found")
    if legacy_role_id == target_role_id:
        raise BusinessError("profile_transition_roles_equal", "Legacy and target roles must differ")
    legacy_role = session.execute(
        sa.select(models.roles.c.id).where(
            models.roles.c.id == legacy_role_id,
            models.roles.c.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if not legacy_role:
        raise BusinessError(
            "profile_transition_legacy_role_invalid", "Legacy role is not in the organization"
        )
    snapshot = [
        {"role_id": row["role_id"], "branch_id": row["branch_id"]}
        for row in session.execute(
            sa.select(models.user_roles.c.role_id, models.user_roles.c.branch_id)
            .where(models.user_roles.c.user_id == user_id)
            .order_by(models.user_roles.c.role_id)
        ).mappings()
    ]
    if legacy_role_id not in {item["role_id"] for item in snapshot}:
        raise BusinessError("profile_transition_legacy_role_missing", "Legacy role is not assigned")
    if target_role_id in {item["role_id"] for item in snapshot}:
        raise BusinessError(
            "profile_transition_target_already_assigned", "Target role is already assigned"
        )
    target_assignment = _validate_role_assignment_scope(
        session, target_role_id, organization_id, target_branch_id
    )
    return {"role_snapshot": snapshot, "target_assignment": target_assignment}


def _get_profile_transition_mapping(session: Session, mapping_id: str) -> dict[str, Any]:
    mapping = (
        session.execute(
            sa.select(models.profile_transition_mappings)
            .where(models.profile_transition_mappings.c.id == mapping_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not mapping:
        raise BusinessError("profile_transition_not_found", "Transition mapping was not found")
    return dict(mapping)


def _transition_idempotency_key(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 128:
        raise BusinessError(
            "profile_transition_idempotency_invalid", "Transition idempotency key is invalid"
        )
    return normalized


def _profile_transition_result(mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": mapping["id"],
        "organization_id": mapping["organization_id"],
        "user_id": mapping["user_id"],
        "legacy_role_id": mapping["legacy_role_id"],
        "target_role_id": mapping["target_role_id"],
        "target_branch_id": mapping["target_branch_id"],
        "status": mapping["status"],
    }


def open_cash_shift(
    session: Session,
    opening_cash_cents: int,
    register_code: str = DEFAULT_REGISTER,
    branch_id: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actual_branch_id = branch_id or BRANCH_ID
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "cash.shift.open", actual_branch_id)
    if get_open_cash_shift(session, register_code, branch_id=actual_branch_id):
        raise BusinessError("cash_shift_already_open", "Register already has an open shift")
    if opening_cash_cents < 0:
        raise BusinessError("invalid_opening_cash", "Opening cash cannot be negative")

    now = _now()
    shift: dict[str, Any] = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "branch_id": actual_branch_id,
        "register_code": register_code,
        "status": "OPEN",
        "opening_cash_cents": opening_cash_cents,
        "cashier_user_id": actor_id,
        "opened_at": now,
        "closed_at": None,
        "created_at": now,
    }
    session.execute(models.cash_shifts.insert().values(**shift))
    _audit(
        session,
        action="cash_shift.opened",
        entity_type="cash_shift",
        entity_id=shift["id"],
        payload={"register_code": register_code, "opening_cash_cents": opening_cash_cents},
        branch_id=shift["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return shift


def close_cash_shift(
    session: Session,
    register_code: str = DEFAULT_REGISTER,
    branch_id: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    raise BusinessError(
        "legacy_cash_cut_forbidden",
        "Use the idempotent operational-close command for cash shifts",
    )


def _cash_shift_command_hash(
    command_type: str, actor_id: str, cash_shift_id: str | None, payload: dict[str, Any]
) -> str:
    """Hash only canonical, server-authoritative cash-shift command inputs."""
    canonical = json.dumps(
        {
            "actor_user_id": actor_id,
            "cash_shift_id": cash_shift_id,
            "command_type": command_type,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def open_cash_shift_idempotently(
    session: Session,
    branch_id: str,
    register_code: str,
    opening_cash_cents: int,
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Create exactly one OPEN shift for an idempotent POS command."""
    key = ""
    request_hash = ""
    try:
        actor_id = _actor_user_id(actor_user_id)
        key = idempotency_key.strip()
        if not key or len(key) > 180:
            raise BusinessError("idempotency_key_required", "Idempotency-Key is required")
        if (
            not register_code.strip()
            or not isinstance(opening_cash_cents, int)
            or opening_cash_cents < 0
        ):
            raise BusinessError(
                "cash_shift_open_payload_invalid",
                "Register and non-negative integer opening cash are required",
            )
        _begin_cash_shift_serialization(session)
        require_permission(session, actor_id, "cash.shift.open", branch_id)
        request_hash = _cash_shift_command_hash(
            "open",
            actor_id,
            None,
            {
                "branch_id": branch_id,
                "register_id": register_code,
                "opening_cash_cents": opening_cash_cents,
            },
        )
        existing = (
            session.execute(
                sa.select(models.cash_shift_commands)
                .where(
                    models.cash_shift_commands.c.organization_id == ORGANIZATION_ID,
                    models.cash_shift_commands.c.idempotency_key == key,
                )
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if existing:
            if existing["request_hash"] != request_hash:
                raise BusinessError(
                    "idempotency_conflict", "Idempotency key has a different request"
                )
            replay = dict(
                session.execute(
                    sa.select(models.cash_shifts).where(
                        models.cash_shifts.c.id == existing["cash_shift_id"]
                    )
                )
                .mappings()
                .one()
            )
            _record_pco004_metric("cash_shift_open_total", result="replay", branch_id=branch_id)
            return replay
        if get_open_cash_shift(session, register_code, branch_id):
            raise BusinessError("cash_shift_already_open", "Register already has an open shift")
        now = _now()
        shift: dict[str, Any] = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": branch_id,
            "register_code": register_code,
            "status": "OPEN",
            "opening_cash_cents": opening_cash_cents,
            "cashier_user_id": actor_id,
            "opened_at": now,
            "closed_at": None,
            "created_at": now,
        }
        session.execute(models.cash_shifts.insert().values(**shift))
        _audit(
            session,
            action="cash_shift.opened",
            entity_type="cash_shift",
            entity_id=shift["id"],
            payload={"register_code": register_code, "opening_cash_cents": opening_cash_cents},
            branch_id=branch_id,
            actor_user_id=actor_id,
        )
        session.execute(
            models.cash_shift_commands.insert().values(
                id=_id(),
                organization_id=ORGANIZATION_ID,
                actor_user_id=actor_id,
                cash_shift_id=shift["id"],
                command_type="open",
                idempotency_key=key,
                request_hash=request_hash,
                result={"cash_shift_id": shift["id"]},
                status="completed",
                created_at=now,
            )
        )
        session.commit()
        _record_pco004_metric("cash_shift_open_total", result="success", branch_id=branch_id)
        return shift
    except BusinessError as exc:
        session.rollback()
        _record_pco004_metric(
            "cash_shift_open_total", result="error", branch_id=branch_id, error_code=exc.code
        )
        if exc.code in {"cash_shift_already_open", "idempotency_conflict"}:
            _record_pco004_metric(
                "cash_shift_guard_conflict_total",
                result="conflict",
                branch_id=branch_id,
                error_code=exc.code,
            )
        raise
    except IntegrityError as exc:
        session.rollback()
        # A concurrent writer may have won either the command-key or active-shift
        # uniqueness race.  Re-read on a clean transaction and expose a stable
        # domain outcome instead of a dialect-specific IntegrityError.
        command = (
            session.execute(
                sa.select(models.cash_shift_commands).where(
                    models.cash_shift_commands.c.organization_id == ORGANIZATION_ID,
                    models.cash_shift_commands.c.idempotency_key == key,
                )
            )
            .mappings()
            .first()
        )
        if command:
            if command["request_hash"] != request_hash:
                raise BusinessError(
                    "idempotency_conflict", "Idempotency key has a different request"
                ) from exc
            replay = dict(
                session.execute(
                    sa.select(models.cash_shifts).where(
                        models.cash_shifts.c.id == command["cash_shift_id"]
                    )
                )
                .mappings()
                .one()
            )
            _record_pco004_metric("cash_shift_open_total", result="replay", branch_id=branch_id)
            return replay
        if get_open_cash_shift(session, register_code, branch_id):
            _record_pco004_metric(
                "cash_shift_guard_conflict_total",
                result="conflict",
                branch_id=branch_id,
                error_code="cash_shift_already_open",
            )
            raise BusinessError(
                "cash_shift_already_open", "Register already has an open shift"
            ) from exc
        raise BusinessError(
            "cash_shift_busy", "Cash shift is being updated; retry the command"
        ) from exc
    except Exception:
        session.rollback()
        raise


def close_cash_shift_operationally_for_register(
    session: Session,
    branch_id: str,
    register_code: str,
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> OperationalCloseResponse:
    """Resolve the legacy close alias without losing a completed idempotent command.

    Authorization is intentionally checked before command lookup and again in the canonical
    close command.  A replay never bypasses a subsequently revoked permission.
    """
    key = ""
    try:
        actor_id = _actor_user_id(actor_user_id)
        key = idempotency_key.strip()
        if not key or len(key) > 180:
            raise BusinessError("idempotency_key_required", "Idempotency-Key is required")
        require_permission(session, actor_id, "cash.shift.close", branch_id)
        command = (
            session.execute(
                sa.select(models.cash_shift_commands).where(
                    models.cash_shift_commands.c.organization_id == ORGANIZATION_ID,
                    models.cash_shift_commands.c.idempotency_key == key,
                )
            )
            .mappings()
            .first()
        )
        if command:
            command_shift = (
                session.execute(
                    sa.select(models.cash_shifts).where(
                        models.cash_shifts.c.id == command["cash_shift_id"],
                        models.cash_shifts.c.organization_id == ORGANIZATION_ID,
                    )
                )
                .mappings()
                .first()
            )
            if not command_shift:
                raise BusinessError("idempotency_conflict", "Idempotency command target is invalid")
            expected_hash = _cash_shift_command_hash(
                "close", actor_id, str(command_shift["id"]), {}
            )
            if (
                command["request_hash"] != expected_hash
                or str(command_shift["branch_id"]) != branch_id
                or str(command_shift["register_code"]) != register_code
            ):
                raise BusinessError(
                    "idempotency_conflict", "Idempotency key has a different request"
                )
            return close_cash_shift_operationally(session, str(command_shift["id"]), key, actor_id)
        open_shift = get_open_cash_shift(session, register_code=register_code, branch_id=branch_id)
        if not open_shift:
            raise BusinessError("cash_shift_not_open", "Register does not have an open shift")
    except BusinessError as exc:
        session.rollback()
        _record_pco004_metric(
            "cash_shift_operational_close_total",
            result="error",
            branch_id=branch_id,
            error_code=exc.code,
        )
        if exc.code in {"cash_shift_not_open", "idempotency_conflict"}:
            _record_pco004_metric(
                "cash_shift_guard_conflict_total",
                result="conflict",
                branch_id=branch_id,
                error_code=exc.code,
            )
        raise
    return close_cash_shift_operationally(session, str(open_shift["id"]), key, actor_id)


def close_cash_shift_operationally(
    session: Session,
    cash_shift_id: str,
    idempotency_key: str,
    actor_user_id: str | None = None,
    _failure_hook: Callable[[str], None] | None = None,
) -> OperationalCloseResponse:
    """Freeze a shift summary atomically without creating a final cash cut."""
    authorized_branch_id: str | None = None
    try:
        actor_id = _actor_user_id(actor_user_id)
        key = idempotency_key.strip()
        if not key or len(key) > 180:
            raise BusinessError("idempotency_key_required", "Idempotency-Key is required")
        request_hash = _cash_shift_command_hash("close", actor_id, cash_shift_id, {})
        _begin_cash_shift_serialization(session)
        authorized_shift = (
            session.execute(
                sa.select(models.cash_shifts)
                .where(
                    models.cash_shifts.c.id == cash_shift_id,
                    models.cash_shifts.c.organization_id == ORGANIZATION_ID,
                )
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if not authorized_shift:
            raise NotFoundError("cash_shift_not_found", "Cash shift was not found")
        authorized_branch_id = str(authorized_shift["branch_id"])
        require_permission(session, actor_id, "cash.shift.close", authorized_branch_id)
        command: Any = (
            session.execute(
                sa.select(models.cash_shift_commands)
                .where(
                    models.cash_shift_commands.c.organization_id == ORGANIZATION_ID,
                    models.cash_shift_commands.c.idempotency_key == key,
                )
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if command:
            if command["request_hash"] != request_hash:
                raise BusinessError(
                    "idempotency_conflict", "Idempotency key has a different request"
                )
            replay_closure = (
                session.execute(
                    sa.select(models.cash_shift_closures).where(
                        models.cash_shift_closures.c.id == command["result"]["closure_id"]
                    )
                )
                .mappings()
                .one()
            )
            replay_shift = (
                session.execute(
                    sa.select(models.cash_shifts).where(models.cash_shifts.c.id == cash_shift_id)
                )
                .mappings()
                .one()
            )
            _record_pco004_metric(
                "cash_shift_operational_close_total",
                result="replay",
                branch_id=str(replay_shift["branch_id"]),
            )
            return _normalize_operational_close_output(
                OperationalCloseResponse(
                    cash_shift=dict(replay_shift),
                    closure=dict(replay_closure),
                )
            )

        shift_row: Any = (
            session.execute(
                sa.select(models.cash_shifts)
                .where(
                    models.cash_shifts.c.id == cash_shift_id,
                    models.cash_shifts.c.organization_id == ORGANIZATION_ID,
                )
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if not shift_row:
            raise NotFoundError("cash_shift_not_found", "Cash shift was not found")
        shift: dict[str, Any] = dict(shift_row)
        if str(shift["status"]).upper() != "OPEN":
            raise BusinessError("cash_shift_not_open", "Cash shift is not OPEN")

        now = _now()
        session.execute(
            models.cash_shifts.update()
            .where(models.cash_shifts.c.id == cash_shift_id)
            .values(status="CLOSING")
        )
        if _failure_hook:
            _failure_hook("after_closing")
        summary = _cash_summary_for_shift(session, shift)

        closure = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": shift["branch_id"],
            "cash_shift_id": cash_shift_id,
            "register_code_snapshot": shift["register_code"],
            "closed_by_user_id": actor_id,
            "summary_snapshot": summary,
            "closed_at": now,
            "created_at": now,
        }
        session.execute(models.cash_shift_closures.insert().values(**closure))
        session.execute(
            models.cash_shifts.update()
            .where(models.cash_shifts.c.id == cash_shift_id)
            .values(status="OPERATIVELY_CLOSED", closed_at=now)
        )
        _audit(
            session,
            action="cash_shift.operationally_closed",
            entity_type="cash_shift",
            entity_id=cash_shift_id,
            payload={"closure_id": closure["id"], "summary": summary},
            branch_id=shift["branch_id"],
            actor_user_id=actor_id,
        )
        session.execute(
            models.cash_shift_commands.insert().values(
                id=_id(),
                organization_id=ORGANIZATION_ID,
                actor_user_id=actor_id,
                cash_shift_id=cash_shift_id,
                command_type="close",
                idempotency_key=key,
                request_hash=request_hash,
                result={"closure_id": closure["id"]},
                status="completed",
                created_at=now,
            )
        )
        session.commit()
        _record_pco004_metric(
            "cash_shift_operational_close_total",
            result="success",
            branch_id=str(shift["branch_id"]),
        )
    except BusinessError as exc:
        session.rollback()
        _record_pco004_metric(
            "cash_shift_operational_close_total",
            result="error",
            branch_id=authorized_branch_id,
            error_code=exc.code,
        )
        if exc.code in {"cash_shift_not_open", "idempotency_conflict"}:
            _record_pco004_metric(
                "cash_shift_guard_conflict_total",
                result="conflict",
                branch_id=authorized_branch_id,
                error_code=exc.code,
            )
        raise
    except Exception:
        session.rollback()
        raise
    shift["status"] = "OPERATIVELY_CLOSED"
    shift["closed_at"] = now
    return _normalize_operational_close_output(
        OperationalCloseResponse(cash_shift=shift, closure=closure)
    )


def _normalize_operational_close_output(
    value: OperationalCloseResponse,
) -> OperationalCloseResponse:
    """Keep domain timestamps UTC-aware before the API renders RFC3339 strings."""
    return OperationalCloseResponse(
        cash_shift=_normalize_operational_close_record(value["cash_shift"]),
        closure=_normalize_operational_close_record(value["closure"]),
    )


def _normalize_operational_close_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, item in record.items():
        if isinstance(item, datetime):
            normalized[key] = (
                item.replace(tzinfo=UTC) if item.tzinfo is None else item.astimezone(UTC)
            )
        elif isinstance(item, dict):
            normalized[key] = _normalize_operational_close_record(item)
        elif isinstance(item, (list, tuple)):
            normalized[key] = [
                _normalize_operational_close_record(value) if isinstance(value, dict) else value
                for value in item
            ]
        else:
            normalized[key] = item
    return normalized


def close_cash_shift_with_cut(
    session: Session,
    counted_cash_cents: int,
    register_code: str = DEFAULT_REGISTER,
    branch_id: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    raise BusinessError(
        "legacy_cash_cut_forbidden",
        "Final cash cuts are forbidden; use the operational-close command",
    )


def _price_order_line(
    session: Session,
    item: dict[str, Any],
    branch_id: str,
    order_id: str,
    order_line_id: str,
    now: datetime,
) -> dict[str, Any]:
    """Use one Python catalog/modifier pricing path for quotes and orders."""
    product_id = item.get("product_id")
    quantity = int(item.get("quantity", 1))
    if quantity <= 0:
        raise BusinessError("invalid_quantity", "Quantity must be positive")
    if not isinstance(product_id, str) or not product_id:
        raise BusinessError("product_unavailable", "Product is unavailable")
    product = _get_available_product(session, product_id, branch_id)
    if not product:
        raise BusinessError("product_unavailable", f"Product {product_id} is unavailable")

    selected_modifiers = list(item.get("modifiers", []))
    comment_preset_ids = item.get("comment_preset_ids", [])
    if not isinstance(comment_preset_ids, list) or any(
        not isinstance(comment_id, str) or not comment_id.strip()
        for comment_id in comment_preset_ids
    ):
        raise BusinessError("invalid_order_comments", "comment_preset_ids must be an array of IDs")
    selected_modifiers.extend(
        {"option_id": comment_id.strip(), "selection_kind": "order_comment"}
        for comment_id in comment_preset_ids
    )

    ingredient_extras = item.get("ingredient_extras", [])
    if not isinstance(ingredient_extras, list):
        raise BusinessError("invalid_ingredient_extras", "ingredient_extras must be an array")
    for extra in ingredient_extras:
        if not isinstance(extra, dict) or not isinstance(extra.get("extra_id"), str):
            raise BusinessError(
                "invalid_ingredient_extras", "Every extra requires extra_id and portions"
            )
        selected_modifiers.append(
            {
                "option_id": extra["extra_id"].strip(),
                "portions": extra.get("portions", 1),
                "selection_kind": "ingredient_extra",
            }
        )

    snapshot = _build_order_consumption_snapshot(
        session,
        order_id=order_id,
        order_line_id=order_line_id,
        product_id=product["id"],
        ordered_quantity=quantity,
        branch_id=branch_id,
        created_at=now,
        selected_modifiers=selected_modifiers,
    )
    modifier_total_cents = int(snapshot["modifier_total_cents"])
    return {
        "product": product,
        "quantity": quantity,
        "snapshot": snapshot,
        "modifier_total_cents": modifier_total_cents,
        "line_total_cents": int(product["price_cents"]) * quantity + modifier_total_cents,
    }


def _order_cart_hash(lines: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        json.dumps(lines, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _calculate_order_adjustment(
    subtotal_cents: int,
    adjustment_type: str,
    adjustment_value: Any,
) -> tuple[str, int]:
    normalized_type = str(adjustment_type or "").strip().lower()
    if normalized_type not in {"percent", "fixed", "courtesy"}:
        raise BusinessError("invalid_order_adjustment", "Adjustment type is not supported")
    try:
        value = Decimal(str(adjustment_value if adjustment_value is not None else "0"))
    except (InvalidOperation, ValueError) as exc:
        raise BusinessError("invalid_order_adjustment", "Adjustment value is invalid") from exc
    if not value.is_finite() or value < 0:
        raise BusinessError("invalid_order_adjustment", "Adjustment value must be non-negative")
    if normalized_type == "courtesy":
        normalized_value = "100"
        adjustment_cents = subtotal_cents
    elif normalized_type == "percent":
        if value > Decimal("100"):
            raise BusinessError("invalid_order_adjustment", "Percentage cannot exceed 100")
        normalized_value = format(value.normalize(), "f")
        adjustment_cents = int(
            (Decimal(subtotal_cents) * value / Decimal("100")).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    else:
        normalized_value = format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
        adjustment_cents = int(
            (value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    return normalized_value, min(subtotal_cents, adjustment_cents)


def _load_order_adjustment_authorization(
    session: Session,
    authorization_id: str,
    lines: list[dict[str, Any]],
    branch_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    authorization = (
        session.execute(
            sa.select(models.order_adjustment_authorizations).where(
                models.order_adjustment_authorizations.c.id == authorization_id
            )
        )
        .mappings()
        .first()
    )
    if not authorization:
        raise BusinessError(
            "order_adjustment_authorization_invalid",
            "Order adjustment authorization was not found",
        )
    if (
        authorization["organization_id"] != ORGANIZATION_ID
        or authorization["branch_id"] != branch_id
        or authorization["requesting_actor_user_id"] != actor_user_id
    ):
        raise AuthorizationError(
            "order_adjustment_authorization_denied",
            "Order adjustment authorization belongs to another scope or actor",
        )
    if authorization["cart_hash"] != _order_cart_hash(lines):
        raise BusinessError(
            "order_adjustment_cart_changed",
            "Cart changed after supervisor authorization",
        )
    if authorization["status"] != "AUTHORIZED":
        raise BusinessError(
            "order_adjustment_authorization_consumed",
            "Order adjustment authorization was already consumed",
        )
    expires_at = authorization["expires_at"]
    if isinstance(expires_at, datetime):
        normalized_expiry = (
            expires_at.replace(tzinfo=UTC)
            if expires_at.tzinfo is None
            else expires_at.astimezone(UTC)
        )
        if normalized_expiry <= _now():
            raise BusinessError(
                "order_adjustment_authorization_expired",
                "Order adjustment authorization expired",
            )
    return dict(authorization)


def _order_create_command_snapshot(response: dict[str, Any]) -> dict[str, Any]:
    """Persist replay data without duplicating customer, address, or free-text snapshots."""
    snapshot = cast(dict[str, Any], _sanitize_for_json(response))
    for field in (
        "customer_id",
        "customer_snapshot",
        "delivery_address_snapshot",
        "owner_name",
    ):
        snapshot.pop(field, None)
    for line in snapshot.get("lines", []):
        if isinstance(line, dict):
            line.pop("line_notes", None)
            line.pop("selected_modifiers", None)
    for consumption_snapshot in snapshot.get("consumption_snapshots", []):
        if isinstance(consumption_snapshot, dict):
            consumption_snapshot.pop("modifiers", None)
    assignment = snapshot.get("delivery_assignment")
    if isinstance(assignment, dict):
        for field in (
            "assigned_by",
            "customer_id",
            "customer_name_snapshot",
            "delivery_address_snapshot",
            "driver_id",
            "driver_name_snapshot",
        ):
            assignment.pop(field, None)
    return snapshot


def _order_create_replay_response(session: Session, command: dict[str, Any]) -> dict[str, Any]:
    """Rehydrate immutable PII from its authoritative rows for an exact replay response."""
    sanitized_response = _sanitize_for_json(command["response_snapshot"])
    if not isinstance(sanitized_response, dict):
        raise BusinessError(
            "order_create_replay_incomplete", "The idempotent order replay is incomplete"
        )
    response = cast(dict[str, Any], sanitized_response)
    order = (
        session.execute(
            sa.select(models.orders).where(
                models.orders.c.id == command["order_id"],
                models.orders.c.organization_id == command["organization_id"],
                models.orders.c.branch_id == command["branch_id"],
            )
        )
        .mappings()
        .first()
    )
    if not order:
        raise BusinessError(
            "order_create_replay_incomplete", "The idempotent order replay is incomplete"
        )
    for field in (
        "customer_id",
        "customer_snapshot",
        "delivery_address_snapshot",
        "owner_name",
    ):
        response[field] = _sanitize_for_json(order[field])

    response_lines = response.get("lines")
    if (
        not isinstance(response_lines, list)
        or not response_lines
        or any(
            not isinstance(line, dict) or not isinstance(line.get("id"), str) or not line["id"]
            for line in response_lines
        )
    ):
        raise BusinessError(
            "order_create_replay_incomplete", "The idempotent order replay is incomplete"
        )
    line_ids = [line["id"] for line in response_lines]
    if len(set(line_ids)) != len(line_ids):
        raise BusinessError(
            "order_create_replay_incomplete", "The idempotent order replay is incomplete"
        )
    persisted_lines = {
        row["id"]: row
        for row in session.execute(
            sa.select(models.order_lines).where(
                models.order_lines.c.id.in_(line_ids),
                models.order_lines.c.order_id == command["order_id"],
            )
        ).mappings()
    }
    if len(persisted_lines) != len(line_ids):
        raise BusinessError(
            "order_create_replay_incomplete", "The idempotent order replay is incomplete"
        )
    for line in response_lines:
        line["line_notes"] = persisted_lines[line["id"]]["line_notes"]
        line["selected_modifiers"] = _sanitize_for_json(
            persisted_lines[line["id"]]["selected_modifiers"]
        )

    response_consumption_snapshots = response.get("consumption_snapshots")
    if not isinstance(response_consumption_snapshots, list) or any(
        not isinstance(snapshot, dict)
        or not isinstance(snapshot.get("order_line_id"), str)
        or not snapshot["order_line_id"]
        for snapshot in response_consumption_snapshots
    ):
        raise BusinessError(
            "order_create_replay_incomplete", "The idempotent order replay is incomplete"
        )
    consumption_line_ids = [
        snapshot["order_line_id"] for snapshot in response_consumption_snapshots
    ]
    if len(set(consumption_line_ids)) != len(consumption_line_ids) or set(
        consumption_line_ids
    ) != set(line_ids):
        raise BusinessError(
            "order_create_replay_incomplete", "The idempotent order replay is incomplete"
        )
    persisted_consumption_snapshots = {
        row["order_line_id"]: row
        for row in session.execute(
            sa.select(models.order_line_consumption_snapshots).where(
                models.order_line_consumption_snapshots.c.order_line_id.in_(consumption_line_ids),
                models.order_line_consumption_snapshots.c.order_id == command["order_id"],
                models.order_line_consumption_snapshots.c.branch_id == command["branch_id"],
            )
        ).mappings()
    }
    if len(persisted_consumption_snapshots) != len(consumption_line_ids):
        raise BusinessError(
            "order_create_replay_incomplete", "The idempotent order replay is incomplete"
        )
    for consumption_snapshot in response_consumption_snapshots:
        consumption_snapshot["modifiers"] = _sanitize_for_json(
            persisted_consumption_snapshots[consumption_snapshot["order_line_id"]]["modifiers"]
        )

    assignment = response.get("delivery_assignment")
    if assignment is not None and not isinstance(assignment, dict):
        raise BusinessError(
            "order_create_replay_incomplete", "The idempotent order replay is incomplete"
        )
    if isinstance(assignment, dict):
        if not isinstance(assignment.get("id"), str) or not assignment["id"]:
            raise BusinessError(
                "order_create_replay_incomplete", "The idempotent order replay is incomplete"
            )
        persisted_assignment = (
            session.execute(
                sa.select(models.delivery_assignments).where(
                    models.delivery_assignments.c.id == assignment["id"],
                    models.delivery_assignments.c.order_id == command["order_id"],
                )
            )
            .mappings()
            .first()
        )
        if not persisted_assignment:
            raise BusinessError(
                "order_create_replay_incomplete", "The idempotent order replay is incomplete"
            )
        for field in (
            "assigned_by",
            "customer_id",
            "customer_name_snapshot",
            "delivery_address_snapshot",
            "driver_id",
            "driver_name_snapshot",
        ):
            assignment[field] = _sanitize_for_json(persisted_assignment[field])
    return response


def recover_local_order_creation(
    session: Session,
    idempotency_key: str | None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Resolve a completed checkout after a client restart without resending its PII payload."""
    actor_id = _actor_user_id(actor_user_id)
    key = str(idempotency_key or "").strip()
    if not key:
        raise BusinessError("idempotency_key_required", "Idempotency-Key is required")
    if len(key) < 12 or len(key) > 160:
        raise BusinessError("idempotency_key_invalid", "Idempotency-Key is invalid")
    _begin_cash_shift_serialization(session)
    _acquire_idempotency_lock(session, "order-create", key)
    command = (
        session.execute(
            sa.select(models.order_create_commands).where(
                models.order_create_commands.c.organization_id == ORGANIZATION_ID,
                models.order_create_commands.c.actor_user_id == actor_id,
                models.order_create_commands.c.idempotency_key == key,
            )
        )
        .mappings()
        .first()
    )
    if not command:
        raise BusinessError(
            "order_create_not_found", "No completed order exists for this checkout key"
        )
    require_permission(session, actor_id, "orders.create", command["branch_id"])
    return _order_create_replay_response(session, dict(command))


def create_local_order(
    session: Session,
    lines: list[dict[str, Any]],
    owner_name: str | None = None,
    order_type: str = "dine-in",
    branch_id: str | None = None,
    register_id: str | None = None,
    actor_user_id: str | None = None,
    customer_id: str | None = None,
    delivery_address_id: str | None = None,
    payment_method_intent: str | None = None,
    driver_id: str | None = None,
    adjustment_authorization_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    _begin_cash_shift_serialization(session)
    if not lines:
        raise BusinessError("invalid_quantity", "Order must have at least one line")

    register_code = register_id or DEFAULT_REGISTER
    actual_branch_id = branch_id or BRANCH_ID
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "orders.create", actual_branch_id)
    normalized_payment_intent = _normalized_payment_method(payment_method_intent)
    key = str(idempotency_key or "").strip()
    if key and (len(key) < 12 or len(key) > 160):
        raise BusinessError("idempotency_key_invalid", "Idempotency-Key is invalid")
    if key:
        _acquire_idempotency_lock(session, "order-create", key)
    request_hash = hashlib.sha256(
        json.dumps(
            _sanitize_for_json(
                {
                    "actor_user_id": actor_id,
                    "branch_id": actual_branch_id,
                    "register_id": register_code,
                    "owner_name": owner_name,
                    "order_type": order_type,
                    "customer_id": customer_id,
                    "delivery_address_id": delivery_address_id,
                    "payment_method_intent": normalized_payment_intent,
                    "driver_id": str(driver_id or "").strip() or None,
                    "adjustment_authorization_id": adjustment_authorization_id,
                    "lines": lines,
                }
            ),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if key:
        existing_command = (
            session.execute(
                sa.select(models.order_create_commands).where(
                    models.order_create_commands.c.organization_id == ORGANIZATION_ID,
                    models.order_create_commands.c.idempotency_key == key,
                )
            )
            .mappings()
            .first()
        )
        if existing_command:
            if (
                existing_command["request_hash"] != request_hash
                or existing_command["branch_id"] != actual_branch_id
                or existing_command["actor_user_id"] != actor_id
            ):
                raise BusinessError(
                    "order_create_idempotency_conflict",
                    "Idempotency-Key was used for a different order intention",
                )
            return _order_create_replay_response(session, dict(existing_command))
    if order_type not in {"dine-in", "takeout", "delivery"}:
        raise BusinessError("invalid_order_type", "Order type is not supported")
    if order_type in {"takeout", "delivery"} and not normalized_payment_intent:
        raise BusinessError(
            "payment_method_intent_required",
            "Deferred orders require an intended payment method",
        )
    normalized_driver_id = str(driver_id or "").strip() or None
    if normalized_driver_id and order_type != "delivery":
        raise BusinessError(
            "driver_assignment_delivery_only",
            "A driver can only be assigned to a delivery order",
        )
    assigned_driver = None
    if normalized_driver_id:
        assigned_driver = (
            session.execute(
                sa.select(models.drivers).where(
                    models.drivers.c.id == normalized_driver_id,
                    models.drivers.c.organization_id == ORGANIZATION_ID,
                    models.drivers.c.branch_id == actual_branch_id,
                    models.drivers.c.status == "active",
                )
            )
            .mappings()
            .first()
        )
        if not assigned_driver:
            raise BusinessError(
                "delivery_driver_unavailable",
                "Driver must be active and assigned to the order branch",
            )
    shift = get_open_cash_shift(session, register_code=register_code, branch_id=actual_branch_id)
    if not shift:
        raise BusinessError("cash_shift_required", "Open cash shift is required")

    now = _now()
    order_id = _id()
    folio = _next_unique_folio(session, actual_branch_id)
    customer_snapshot, address_snapshot = _resolve_order_customer_snapshots(
        session,
        customer_id=customer_id,
        delivery_address_id=delivery_address_id,
        order_type=order_type,
    )
    if customer_snapshot:
        owner_name = str(customer_snapshot["name"])

    total_cents = 0
    order_lines_data = []
    tasks_data = []
    consumption_snapshots_data = []

    for item in lines:
        order_line_id = _id()
        priced = _price_order_line(session, item, actual_branch_id, order_id, order_line_id, now)
        product = priced["product"]
        quantity = priced["quantity"]
        consumption_snapshot = priced["snapshot"]
        modifier_total_cents = priced["modifier_total_cents"]
        line_total = priced["line_total_cents"]
        total_cents += line_total

        order_lines_data.append(
            {
                "id": order_line_id,
                "order_id": order_id,
                "product_id": product["id"],
                "product_name": product["name"],
                "quantity": quantity,
                "unit_price_cents": product["price_cents"],
                "line_total_cents": line_total,
                "station": product["station"],
                "selected_modifiers": consumption_snapshot["modifiers"],
                "modifier_total_cents": modifier_total_cents,
                "line_notes": item.get("notes"),
                "family_id_snapshot": product["category_id"],
                "family_name_snapshot": product["family_name"],
                "family_snapshot_source": "captured",
                "created_at": now,
            }
        )

        tasks_data.append(
            {
                "id": _id(),
                "organization_id": ORGANIZATION_ID,
                "branch_id": actual_branch_id,
                "order_id": order_id,
                "order_line_id": order_line_id,
                "station": product["station"],
                "status": "PENDING",
                "product_name": product["name"],
                "quantity": quantity,
                "created_at": now,
                "started_at": None,
                "completed_at": None,
            }
        )

        _record_calculated_consumption_movements(
            session,
            components=consumption_snapshot["components"],
            product_name=product["name"],
            movement_type="SALE_RESERVATION",
            sign=-1,
            reason=f"Reserva por pedido {folio}",
            source_type="order",
            source_id=order_id,
            created_at=now,
            branch_id=actual_branch_id,
        )
        consumption_snapshot.pop("modifier_total_cents")
        consumption_snapshots_data.append(consumption_snapshot)

    adjustment_authorization = None
    adjustment_cents = 0
    if adjustment_authorization_id:
        adjustment_authorization = _load_order_adjustment_authorization(
            session,
            adjustment_authorization_id,
            lines,
            actual_branch_id,
            actor_id,
        )
        adjustment_cents = int(adjustment_authorization["adjustment_cents"])
        if int(adjustment_authorization["subtotal_cents"]) != total_cents:
            raise BusinessError(
                "order_adjustment_total_mismatch",
                "Order subtotal changed after supervisor authorization",
            )
        total_cents -= adjustment_cents

    order = {
        "id": order_id,
        "organization_id": ORGANIZATION_ID,
        "branch_id": actual_branch_id,
        "cash_shift_id": shift["id"],
        "customer_id": customer_id,
        "customer_snapshot": customer_snapshot,
        "delivery_address_snapshot": address_snapshot,
        "folio": folio,
        "channel": "POS",
        "status": "ACCEPTED",
        "total_cents": total_cents,
        "currency": "MXN",
        "owner_name": owner_name,
        "order_type": order_type,
        "payment_method_intent": normalized_payment_intent,
        "version": 1,
        "created_at": now,
        "accepted_at": now,
    }

    session.execute(models.orders.insert().values(**order))
    if adjustment_authorization:
        consumed = session.execute(
            models.order_adjustment_authorizations.update()
            .where(
                models.order_adjustment_authorizations.c.id == adjustment_authorization["id"],
                models.order_adjustment_authorizations.c.status == "AUTHORIZED",
            )
            .values(status="CONSUMED", consumed_order_id=order_id, consumed_at=now)
        )
        if consumed.rowcount != 1:
            session.rollback()
            raise BusinessError(
                "order_adjustment_authorization_conflict",
                "Order adjustment authorization changed concurrently",
            )
    for line in order_lines_data:
        session.execute(models.order_lines.insert().values(**line))
    for snapshot in consumption_snapshots_data:
        session.execute(models.order_line_consumption_snapshots.insert().values(**snapshot))
    for task in tasks_data:
        session.execute(models.production_tasks.insert().values(**task))

    delivery_assignment = None
    if assigned_driver:
        delivery_assignment = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": actual_branch_id,
            "order_id": order_id,
            "driver_id": assigned_driver["id"],
            "customer_id": customer_id,
            "driver_name_snapshot": assigned_driver["name"],
            "customer_name_snapshot": str(
                (customer_snapshot or {}).get("name") or owner_name or "Cliente General"
            ),
            "delivery_address_snapshot": address_snapshot or {},
            "order_total_cents": total_cents,
            "currency": "MXN",
            "line_count": len(order_lines_data),
            "item_quantity": sum(int(line["quantity"]) for line in order_lines_data),
            "status": "ASSIGNED",
            "assigned_by": actor_id,
            "assigned_at": now,
        }
        session.execute(models.delivery_assignments.insert().values(**delivery_assignment))
        session.execute(
            models.order_events.insert().values(
                id=_id(),
                order_id=order_id,
                event_type="DRIVER_ASSIGNED",
                payload={
                    "driver_id": assigned_driver["id"],
                    "driver_name": assigned_driver["name"],
                },
                created_at=now,
            )
        )
        _audit(
            session,
            action="delivery.driver_assigned",
            entity_type="delivery_assignment",
            entity_id=delivery_assignment["id"],
            branch_id=actual_branch_id,
            actor_user_id=actor_id,
            payload={
                "order_id": order_id,
                "driver_id": assigned_driver["id"],
                "customer_id": customer_id,
                "order_total_cents": total_cents,
                "line_count": delivery_assignment["line_count"],
                "item_quantity": delivery_assignment["item_quantity"],
            },
        )

    session.execute(
        models.order_events.insert().values(
            id=_id(),
            order_id=order_id,
            event_type="ORDER_ACCEPTED",
            payload={
                "folio": folio,
                "total_cents": total_cents,
                "lines_count": len(order_lines_data),
            },
            created_at=now,
        )
    )

    _audit(
        session,
        action="order.accepted",
        entity_type="order",
        entity_id=order_id,
        payload={
            "folio": folio,
            "lines": len(order_lines_data),
            "total_cents": total_cents,
            "adjustment_authorization_id": adjustment_authorization_id,
            "adjustment_cents": adjustment_cents,
            "customer_id": customer_id,
            "delivery_address_id": delivery_address_id,
        },
        branch_id=actual_branch_id,
        actor_user_id=actor_id,
    )
    response = {
        **order,
        "lines": order_lines_data,
        "production_tasks": tasks_data,
        "consumption_snapshots": consumption_snapshots_data,
        "delivery_assignment": delivery_assignment,
    }
    stable_response = cast(dict[str, Any], _sanitize_for_json(response))
    if key:
        session.execute(
            models.order_create_commands.insert().values(
                id=_id(),
                organization_id=ORGANIZATION_ID,
                branch_id=actual_branch_id,
                actor_user_id=actor_id,
                idempotency_key=key,
                request_hash=request_hash,
                order_id=order_id,
                response_snapshot=_order_create_command_snapshot(stable_response),
                created_at=now,
            )
        )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if not key:
            raise
        concurrent = (
            session.execute(
                sa.select(models.order_create_commands).where(
                    models.order_create_commands.c.organization_id == ORGANIZATION_ID,
                    models.order_create_commands.c.idempotency_key == key,
                )
            )
            .mappings()
            .first()
        )
        if concurrent and concurrent["request_hash"] == request_hash:
            return _order_create_replay_response(session, dict(concurrent))
        raise BusinessError(
            "order_create_idempotency_conflict",
            "Idempotency-Key was used for a different order intention",
        ) from exc
    return stable_response


def quote_local_order(
    session: Session,
    lines: list[dict[str, Any]],
    branch_id: str,
    actor_user_id: str,
    adjustment_authorization_id: str | None = None,
) -> dict[str, Any]:
    """Return a non-persistent quote from the same Python pricer as creation."""
    require_permission(session, actor_user_id, "orders.create", branch_id)
    if not lines:
        raise BusinessError("invalid_quantity", "Order must have at least one line")
    quote_lines: list[dict[str, Any]] = []
    subtotal_cents = 0
    for item in lines:
        priced = _price_order_line(session, item, branch_id, "quote", _id(), _now())
        product = priced["product"]
        line_total_cents = int(priced["line_total_cents"])
        subtotal_cents += line_total_cents
        quote_lines.append(
            {
                "product_id": product["id"],
                "quantity": int(priced["quantity"]),
                "unit_price_cents": int(product["price_cents"]),
                "modifier_total_cents": int(priced["modifier_total_cents"]),
                "line_total_cents": line_total_cents,
            }
        )
    adjustment_authorization = None
    adjustment_cents = 0
    if adjustment_authorization_id:
        adjustment_authorization = _load_order_adjustment_authorization(
            session,
            adjustment_authorization_id,
            lines,
            branch_id,
            actor_user_id,
        )
        adjustment_cents = int(adjustment_authorization["adjustment_cents"])
        if int(adjustment_authorization["subtotal_cents"]) != subtotal_cents:
            raise BusinessError(
                "order_adjustment_total_mismatch",
                "Order subtotal changed after supervisor authorization",
            )
    return {
        "schema_version": "order-quote.v1",
        "branch_id": branch_id,
        "currency": "MXN",
        "lines": quote_lines,
        "subtotal_cents": subtotal_cents,
        "adjustment_cents": adjustment_cents,
        "adjustment_reason": (
            str(adjustment_authorization["reason"]) if adjustment_authorization else None
        ),
        "tax_cents": None,
        "total_cents": subtotal_cents - adjustment_cents,
    }


def authorize_order_adjustment(
    session: Session,
    lines: list[dict[str, Any]],
    branch_id: str,
    actor_user_id: str,
    supervisor_code_or_password: str,
    adjustment_type: str,
    adjustment_value: Any,
    reason: str,
) -> dict[str, Any]:
    require_permission(session, actor_user_id, "orders.create", branch_id)
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise BusinessError("order_adjustment_reason_required", "Adjustment reason is required")
    supervisor = authorize_supervisor_step_up(
        session,
        supervisor_code_or_password,
        branch_id,
        "orders.discount.authorize",
    )
    base_quote = quote_local_order(session, lines, branch_id, actor_user_id)
    normalized_value, adjustment_cents = _calculate_order_adjustment(
        int(base_quote["subtotal_cents"]), adjustment_type, adjustment_value
    )
    now = _now()
    authorization_id = _id()
    authorization = {
        "id": authorization_id,
        "organization_id": ORGANIZATION_ID,
        "branch_id": branch_id,
        "requesting_actor_user_id": actor_user_id,
        "supervisor_user_id": supervisor["supervisor_user_id"],
        "cart_hash": _order_cart_hash(lines),
        "adjustment_type": str(adjustment_type).strip().lower(),
        "adjustment_value": normalized_value,
        "subtotal_cents": int(base_quote["subtotal_cents"]),
        "adjustment_cents": adjustment_cents,
        "resulting_total_cents": int(base_quote["subtotal_cents"]) - adjustment_cents,
        "reason": normalized_reason,
        "status": "AUTHORIZED",
        "authorized_at": now,
        "expires_at": now + timedelta(minutes=2),
        "consumed_order_id": None,
        "consumed_at": None,
    }
    session.execute(models.order_adjustment_authorizations.insert().values(**authorization))
    _audit(
        session,
        action="order.adjustment_authorized",
        entity_type="order_adjustment_authorization",
        entity_id=authorization_id,
        payload={
            "requesting_actor_user_id": actor_user_id,
            "supervisor_user_id": supervisor["supervisor_user_id"],
            "adjustment_type": authorization["adjustment_type"],
            "adjustment_cents": adjustment_cents,
            "reason": normalized_reason,
        },
        branch_id=branch_id,
        actor_user_id=str(supervisor["supervisor_user_id"]),
    )
    session.commit()
    return {
        "authorization_id": authorization_id,
        "expires_at": authorization["expires_at"],
        "quote": {
            **base_quote,
            "adjustment_cents": adjustment_cents,
            "adjustment_reason": normalized_reason,
            "total_cents": int(base_quote["subtotal_cents"]) - adjustment_cents,
        },
    }


def fulfill_order(
    session: Session,
    order_id: str,
    command: str,
    idempotency_key: str | None,
    actor_user_id: str,
) -> dict[str, Any]:
    """Apply a service-specific terminal transition with stable idempotency."""
    key = str(idempotency_key or "").strip()
    if not key:
        raise BusinessError("idempotency_key_required", "Idempotency-Key is required")
    order = (
        session.execute(
            sa.select(models.orders).where(
                models.orders.c.id == order_id,
                models.orders.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not order:
        raise NotFoundError("order_not_found", "Order was not found")
    require_permission(session, actor_user_id, "orders.fulfill", order["branch_id"])
    normalized_command = command.strip().lower().replace("-", "_")
    digest = hashlib.sha256(
        json.dumps(
            {
                "actor_user_id": actor_user_id,
                "command": normalized_command,
                "order_id": order_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    existing = (
        session.execute(
            sa.select(models.order_fulfillment_commands).where(
                models.order_fulfillment_commands.c.order_id == order_id,
                models.order_fulfillment_commands.c.idempotency_key == key,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        if existing["request_hash"] != digest:
            raise BusinessError(
                "idempotency_conflict",
                "Idempotency-Key was already used for a different command",
            )
        return dict(existing["response_snapshot"])

    try:
        current = OrderState(str(order["status"]))
        order_type = str(order["order_type"])
        targets = {
            "start_delivery": OrderState.IN_DELIVERY,
            "deliver": OrderState.DELIVERED,
            "close": OrderState.CLOSED,
        }
        next_state = targets[normalized_command]
        valid_command = (
            (
                normalized_command == "start_delivery"
                and order_type == "delivery"
                and current == OrderState.READY
            )
            or (
                normalized_command == "deliver"
                and order_type in {"dine-in", "takeout"}
                and current == OrderState.READY
            )
            or (
                normalized_command == "deliver"
                and order_type == "delivery"
                and current == OrderState.IN_DELIVERY
            )
            or (
                normalized_command == "close"
                and current in {OrderState.DELIVERED, OrderState.RETURNED}
            )
        )
        if not valid_command:
            raise StateTransitionError("fulfillment command is not available")
        OrderStateMachine.transition(current, next_state)
    except (KeyError, ValueError, StateTransitionError) as exc:
        raise BusinessError(
            "order_fulfillment_transition_invalid",
            "Order fulfillment transition is invalid",
        ) from exc

    changed = session.execute(
        models.orders.update()
        .where(models.orders.c.id == order_id, models.orders.c.status == current.value)
        .values(status=next_state.value)
    )
    if changed.rowcount != 1:
        session.rollback()
        raise BusinessError("order_transition_conflict", "Order state changed concurrently")
    now = _now()
    response = {"id": order_id, "status": next_state.value, "order_type": order_type}
    session.execute(
        models.order_events.insert().values(
            id=_id(),
            order_id=order_id,
            event_type=next_state.value,
            payload={"source": "order_fulfillment", "command": normalized_command},
            created_at=now,
        )
    )
    session.execute(
        models.order_fulfillment_commands.insert().values(
            id=_id(),
            organization_id=order["organization_id"],
            branch_id=order["branch_id"],
            order_id=order_id,
            actor_user_id=actor_user_id,
            command=normalized_command,
            request_hash=digest,
            idempotency_key=key,
            response_snapshot=response,
            created_at=now,
        )
    )
    _audit(
        session,
        "order.fulfilled",
        "order",
        order_id,
        {"from": current.value, "to": next_state.value, "command": normalized_command},
        order["branch_id"],
        order["organization_id"],
        actor_user_id,
    )
    session.commit()
    return response


def list_recent_orders(session: Session, branch_id: str | None = None) -> list[dict[str, Any]]:
    actual_branch_id = branch_id or BRANCH_ID
    rows = session.execute(
        sa.select(models.orders)
        .where(models.orders.c.branch_id == actual_branch_id)
        .order_by(models.orders.c.created_at.desc())
        .limit(20)
    ).mappings()
    return [_order_payment_projection(session, dict(row)) for row in rows]


def _normalized_payment_method(method: str | None) -> str | None:
    if method is None or not str(method).strip():
        return None
    normalized = str(method).strip().lower()
    if normalized not in {"cash", "debit_card", "credit_card", "transfer"}:
        raise BusinessError("invalid_payment_method", "Payment method is not supported")
    return normalized


def _confirmed_payment(session: Session, order_id: str) -> dict[str, Any] | None:
    row = (
        session.execute(
            sa.select(models.payments)
            .where(
                models.payments.c.order_id == order_id,
                models.payments.c.status == "CONFIRMED",
            )
            .order_by(models.payments.c.created_at.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def _order_payment_projection(session: Session, order: dict[str, Any]) -> dict[str, Any]:
    payment = _confirmed_payment(session, order["id"])
    pending_deferred = order.get("order_type") in {"takeout", "delivery"} and payment is None
    return {
        **order,
        "payment_status": "CONFIRMED" if payment else "PENDING",
        "payment_method": payment["method"] if payment else None,
        "display_status": "PENDING_PAYMENT" if pending_deferred else order["status"],
        "delivery_assignment": _delivery_assignment_for_order(session, order["id"]),
    }


def _delivery_assignment_for_order(
    session: Session,
    order_id: str,
) -> dict[str, Any] | None:
    row = (
        session.execute(
            sa.select(models.delivery_assignments).where(
                models.delivery_assignments.c.order_id == order_id
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def get_order_detail(
    session: Session,
    order_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    order = (
        session.execute(sa.select(models.orders).where(models.orders.c.id == order_id))
        .mappings()
        .first()
    )
    if not order:
        intent = (
            session.execute(
                sa.select(models.public_order_intents).where(
                    models.public_order_intents.c.id == order_id
                )
            )
            .mappings()
            .first()
        )
        if not intent:
            raise NotFoundError("order_not_found", "Order was not found")
        if intent.get("accepted_order_id"):
            return get_order_detail(session, intent["accepted_order_id"], actor_user_id)
        require_permission(session, actor_id, "orders.read", intent["branch_id"])
        intent_lines = [
            dict(row)
            for row in session.execute(
                sa.select(models.public_order_intent_lines)
                .where(models.public_order_intent_lines.c.intent_id == order_id)
                .order_by(
                    models.public_order_intent_lines.c.created_at,
                    models.public_order_intent_lines.c.id,
                )
            ).mappings()
        ]
        cust = intent.get("customer_snapshot") or {}
        addr = intent.get("delivery_address_snapshot") or {}
        phone = cust.get("phone") or addr.get("phone")
        full_address = (
            addr.get("street") or addr.get("address_line1") or addr.get("formatted_address")
        )
        if full_address and addr.get("neighborhood"):
            full_address = f"{full_address}, {addr['neighborhood']}"
        delivery_notes = addr.get("notes") or intent.get("order_notes")
        return {
            "id": intent["id"],
            "organization_id": intent["organization_id"],
            "branch_id": intent["branch_id"],
            "cash_shift_id": None,
            "folio": f"WEB-{intent['public_reference'][-6:]}",
            "channel": "PUBLIC_INTENT",
            "status": "PENDING",
            "service_type": intent["order_type"],
            "order_type": intent["order_type"],
            "total_cents": intent["total_cents"],
            "currency": intent["currency"],
            "owner_name": cust.get("name"),
            "customer_label": cust.get("name") or "Cliente Web",
            "customer_phone": phone,
            "delivery_address": full_address,
            "delivery_notes": delivery_notes,
            "customer_snapshot": cust,
            "delivery_address_snapshot": addr,
            "payment_method_intent": None,
            "created_at": intent["created_at"],
            "accepted_at": intent.get("accepted_at"),
            "lines": [
                {
                    "id": line_item["id"],
                    "order_id": order_id,
                    "product_id": line_item["product_id"],
                    "product_name": line_item["product_name"],
                    "quantity": line_item["quantity"],
                    "unit_price_cents": line_item["unit_price_cents"],
                    "line_total_cents": line_item["line_total_cents"],
                    "station": line_item["station"],
                    "selected_modifiers": line_item.get("selected_modifiers") or [],
                    "modifier_total_cents": line_item.get("modifier_total_cents", 0),
                    "line_notes": line_item.get("line_notes"),
                    "status": "active",
                }
                for line_item in intent_lines
            ],
            "production_tasks": [],
            "payments": [],
            "events": [],
            "corrections": [],
            "sales_operation_snapshots": [],
            "payment_status": "PENDING",
            "editable": False,
            "is_editable": False,
            "edit_block_reason": "Pedido web pendiente de aceptación.",
            "reopen_eligible": False,
            "active_reopen_request_status": None,
            "is_public_intent": True,
            "public_reference": intent["public_reference"],
        }
    require_permission(session, actor_id, "orders.read", order["branch_id"])
    lines = [
        dict(row)
        for row in session.execute(
            sa.select(models.order_lines)
            .where(
                models.order_lines.c.order_id == order_id,
                models.order_lines.c.status == "active",
            )
            .order_by(models.order_lines.c.created_at, models.order_lines.c.id)
        ).mappings()
    ]
    tasks = [
        dict(row)
        for row in session.execute(
            sa.select(models.production_tasks)
            .where(models.production_tasks.c.order_id == order_id)
            .order_by(models.production_tasks.c.created_at, models.production_tasks.c.id)
        ).mappings()
    ]
    active_line_ids = {line["id"] for line in lines}
    current_tasks = [task for task in tasks if task["order_line_id"] in active_line_ids]
    tasks_pending = bool(current_tasks) and all(
        task["status"] == "PENDING" for task in current_tasks
    )
    payments_rows = [
        dict(row)
        for row in session.execute(
            sa.select(models.payments)
            .where(models.payments.c.order_id == order_id)
            .order_by(models.payments.c.created_at)
        ).mappings()
    ]
    events = [
        dict(row)
        for row in session.execute(
            sa.select(models.order_events)
            .where(models.order_events.c.order_id == order_id)
            .order_by(models.order_events.c.created_at, models.order_events.c.id)
        ).mappings()
    ]
    has_payment = any(payment["status"] == "CONFIRMED" for payment in payments_rows)
    has_tasks = bool(current_tasks)
    editable = (
        order["status"] in {"ACCEPTED", "PENDING"}
        and not has_payment
        and (not has_tasks or tasks_pending)
    )
    edit_block_reason = None
    if has_payment:
        edit_block_reason = "El pedido ya tiene un pago confirmado."
    elif order["status"] not in {"ACCEPTED", "PENDING"}:
        edit_block_reason = "El estado operativo ya no permite editar."
    elif has_tasks and not tasks_pending:
        edit_block_reason = "La producción ya inició; el pedido es sólo lectura."
    snapshots = [
        dict(row)
        for row in session.execute(
            sa.select(models.sales_operation_snapshots)
            .where(models.sales_operation_snapshots.c.order_id == order_id)
            .order_by(models.sales_operation_snapshots.c.confirmed_at)
        ).mappings()
    ]
    corrections = [
        {
            "id": row["id"],
            "request_id": row["request_id"],
            "folio": row["folio"],
            "corrected_total_cents": row["corrected_total_cents"],
            "settlement_delta_cents": row["settlement_delta_cents"],
            "currency": row["currency"],
            "applied_at": row["applied_at"],
        }
        for row in session.execute(
            sa.select(models.order_corrections)
            .where(models.order_corrections.c.order_id == order_id)
            .order_by(models.order_corrections.c.applied_at, models.order_corrections.c.id)
        ).mappings()
    ]
    active_reopen = session.execute(
        sa.select(models.order_reopen_requests.c.status).where(
            models.order_reopen_requests.c.order_id == order_id,
            models.order_reopen_requests.c.status.in_(("REQUESTED", "APPROVED")),
        )
    ).scalar_one_or_none()
    protected = (
        has_payment
        or order["status"] == "CLOSED"
        or any(task["status"] != "PENDING" for task in tasks)
    )
    projection = _order_payment_projection(session, dict(order))
    return {
        **projection,
        # Canonical aliases used by the account/history projection.  Legacy fields
        # remain in the detail payload for existing POS consumers.
        "customer_label": (order.get("customer_snapshot") or {}).get("name")
        or order.get("owner_name"),
        "customer_phone": (order.get("customer_snapshot") or {}).get("phone") or "",
        "delivery_address": (order.get("delivery_address_snapshot") or {}).get("address_text")
        or "",
        "delivery_notes": (order.get("delivery_address_snapshot") or {}).get("notes") or "",
        "channel": order.get("channel") or "POS",
        "service_type": order["order_type"],
        "lines": lines,
        "production_tasks": tasks,
        "payments": payments_rows,
        "events": events,
        "sales_operation_snapshots": snapshots,
        "corrections": corrections,
        "reopen_eligible": protected
        and order["status"] not in {"CANCELLED", "REJECTED", "FAILED", "RETURNED"},
        "active_reopen_request_status": active_reopen,
        "editable": editable,
        "edit_block_reason": edit_block_reason,
    }


def _pco005_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _pco005_key(value: str | None) -> str:
    key = (value or "").strip()
    if not 12 <= len(key) <= 160:
        raise BusinessError(
            "idempotency_key_invalid", "Idempotency-Key must contain 12 to 160 characters"
        )
    return key


def _pco005_request_dto(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "organization_id",
        "branch_id",
        "order_id",
        "status",
        "order_version_snapshot",
        "order_status_snapshot",
        "requested_by_user_id",
        "requested_at",
        "reason",
        "evidence_refs",
        "decided_by_user_id",
        "decided_at",
        "decision_reason",
        "created_at",
        "updated_at",
    )
    return {key: row[key] for key in keys}


def _pco005_replay(
    session: Session, key: str, command_type: str, digest: str
) -> dict[str, Any] | None:
    row = (
        session.execute(
            sa.select(models.order_reopen_commands).where(
                models.order_reopen_commands.c.organization_id == ORGANIZATION_ID,
                models.order_reopen_commands.c.idempotency_key == key,
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    if row["command_type"] != command_type or row["request_hash"] != digest:
        raise BusinessError(
            "idempotency_conflict", "Idempotency-Key was already used for a different command"
        )
    return dict(row["response_snapshot"])


def _require_order_correction_owner(session: Session, actor_user_id: str, branch_id: str) -> None:
    """Require the persisted organization-owner authority for PCO-005B apply.

    The ordinary reopen authorization permission is deliberately reusable for
    PCO-005A decisions.  Applying a financial/productive correction is more
    sensitive and therefore requires the actual organization authority grant,
    not merely a role which happens to contain that permission.
    """
    has_owner_authority = session.execute(
        sa.select(models.user_roles.c.user_id)
        .select_from(
            models.user_roles.join(
                models.roles, models.user_roles.c.role_id == models.roles.c.id
            ).join(
                models.role_authority_grants,
                models.roles.c.id == models.role_authority_grants.c.role_id,
            )
        )
        .where(
            models.user_roles.c.user_id == actor_user_id,
            models.roles.c.organization_id == ORGANIZATION_ID,
            models.roles.c.scope == "organization",
            models.role_authority_grants.c.authority_kind == "organization_all_permissions",
        )
        .limit(1)
    ).scalar_one_or_none()
    if has_owner_authority:
        return
    _record_authorization_denied(
        session,
        actor_user_id=actor_user_id,
        permission_code="orders.reopen.authorize",
        branch_id=branch_id,
        reason="owner_authority_required",
    )
    raise AuthorizationError("permission_denied", "Actor does not have the required permission")


def _require_cash_compensation_owner(session: Session, actor_user_id: str, branch_id: str) -> None:
    """Require the persisted organization-owner grant for manual cash compensation.

    `cash.movement.compensate` is necessary but insufficient: it may be present
    on an administrative profile, while PRD-FR-216 reserves the irreversible
    compensating command to an actual organization owner.
    """
    has_owner_authority = session.execute(
        sa.select(models.user_roles.c.user_id)
        .select_from(
            models.user_roles.join(
                models.roles, models.user_roles.c.role_id == models.roles.c.id
            ).join(
                models.role_authority_grants,
                models.roles.c.id == models.role_authority_grants.c.role_id,
            )
        )
        .where(
            models.user_roles.c.user_id == actor_user_id,
            models.roles.c.organization_id == ORGANIZATION_ID,
            models.roles.c.scope == "organization",
            models.role_authority_grants.c.authority_kind == "organization_all_permissions",
        )
        .limit(1)
    ).scalar_one_or_none()
    if has_owner_authority:
        return
    _record_authorization_denied(
        session,
        actor_user_id=actor_user_id,
        permission_code="cash.movement.compensate",
        branch_id=branch_id,
        reason="owner_authority_required",
    )
    raise AuthorizationError("permission_denied", "Actor does not have the required permission")


def _pco005b_after_sensitive_write(_step: str) -> None:
    """Private test seam for transaction-boundary failure injection.

    Production leaves this as a no-op.  Tests monkeypatch it to prove that a
    failure after any append-only write rolls the whole correction back.
    """
    return None


def _pco005_before_snapshot(session: Session, order: dict[str, Any]) -> dict[str, Any]:
    lines = session.execute(
        sa.select(models.order_lines)
        .where(models.order_lines.c.order_id == order["id"])
        .order_by(models.order_lines.c.id)
    ).mappings()
    payments = session.execute(
        sa.select(models.payments)
        .where(models.payments.c.order_id == order["id"])
        .order_by(models.payments.c.id)
    ).mappings()
    tasks = session.execute(
        sa.select(models.production_tasks)
        .where(models.production_tasks.c.order_id == order["id"])
        .order_by(models.production_tasks.c.id)
    ).mappings()
    snapshot_id = session.execute(
        sa.select(models.sales_operation_snapshots.c.id)
        .where(models.sales_operation_snapshots.c.order_id == order["id"])
        .order_by(models.sales_operation_snapshots.c.id)
        .limit(1)
    ).scalar_one_or_none()
    return {
        "order": {
            "version": order["version"],
            "status": order["status"],
            "total_cents": order["total_cents"],
            "currency": order["currency"],
        },
        "lines": [
            {"id": x["id"], "revision": x["revision"], "total_cents": x["line_total_cents"]}
            for x in lines
        ],
        "payments": [
            {
                "id": x["id"],
                "status": x["status"],
                "amount_cents": x["amount_cents"],
                "currency": x["currency"],
            }
            for x in payments
        ],
        "tasks": [{"id": x["id"], "status": x["status"]} for x in tasks],
        "sales_operation_snapshot_id": snapshot_id,
    }


def create_order_reopen_request(
    session: Session,
    order_id: str,
    payload: dict[str, Any],
    idempotency_key: str | None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id, key = _actor_user_id(actor_user_id), _pco005_key(idempotency_key)
    reason = str(payload.get("reason") or "").strip()
    evidence = (
        [str(value).strip() for value in payload.get("evidence_refs", [])]
        if isinstance(payload.get("evidence_refs"), list)
        else []
    )
    if (
        not 10 <= len(reason) <= 500
        or not 1 <= len(evidence) <= 10
        or any(not 1 <= len(value) <= 500 for value in evidence)
    ):
        raise BusinessError(
            "order_reopen_request_invalid", "Reason and evidence references are invalid"
        )
    order = (
        session.execute(
            sa.select(models.orders).where(models.orders.c.id == order_id).with_for_update()
        )
        .mappings()
        .first()
    )
    if not order:
        raise NotFoundError("order_not_found", "Order was not found")
    require_permission(session, actor_id, "orders.reopen.request", order["branch_id"])
    digest = _pco005_hash({"order_id": order_id, "reason": reason, "evidence_refs": evidence})
    if replay := _pco005_replay(session, key, "request", digest):
        logger.info(
            "order_reopen_request_total",
            extra={
                "metric": "order_reopen_request_total",
                "result": "replay",
                "command": "request",
                "actor_id": actor_id,
                "branch_id": order["branch_id"],
                "request_id": replay["id"],
            },
        )
        return replay
    protected = (
        order["status"] == "CLOSED"
        or session.execute(
            sa.select(models.payments.c.id)
            .where(models.payments.c.order_id == order_id, models.payments.c.status == "CONFIRMED")
            .limit(1)
        ).scalar_one_or_none()
        or session.execute(
            sa.select(models.production_tasks.c.id)
            .where(
                models.production_tasks.c.order_id == order_id,
                models.production_tasks.c.status != "PENDING",
            )
            .limit(1)
        ).scalar_one_or_none()
    )
    if order["status"] in {"CANCELLED", "REJECTED", "FAILED", "RETURNED"}:
        raise BusinessError("order_reopen_not_eligible", "Order is not eligible for reopening")
    if not protected:
        raise BusinessError(
            "order_reopen_not_required", "Order remains editable through the normal flow"
        )
    now = _now()
    request = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "branch_id": order["branch_id"],
        "order_id": order_id,
        "status": "REQUESTED",
        "order_version_snapshot": order["version"],
        "order_status_snapshot": order["status"],
        "before_snapshot": _pco005_before_snapshot(session, dict(order)),
        "reason": reason,
        "evidence_refs": evidence,
        "requested_by_user_id": actor_id,
        "requested_at": now,
        "decided_by_user_id": None,
        "decided_at": None,
        "decision_reason": None,
        "applied_by_user_id": None,
        "applied_at": None,
        "created_at": now,
        "updated_at": now,
    }
    response = _pco005_request_dto(request)
    try:
        session.execute(models.order_reopen_requests.insert().values(**request))
        session.execute(
            models.order_reopen_commands.insert().values(
                id=_id(),
                organization_id=ORGANIZATION_ID,
                request_id=request["id"],
                order_id=order_id,
                command_type="request",
                idempotency_key=key,
                request_hash=digest,
                status="completed",
                response_snapshot=_sanitize_for_json(response),
                actor_user_id=actor_id,
                created_at=now,
            )
        )
        _audit(
            session,
            action="order.reopen.requested",
            entity_type="order_reopen_request",
            entity_id=request["id"],
            payload={
                "order_id": order_id,
                "previous_status": None,
                "new_status": "REQUESTED",
                "order_version_snapshot": order["version"],
            },
            branch_id=order["branch_id"],
            actor_user_id=actor_id,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if "uq_order_reopen_active" in str(exc.orig) or "order_reopen_requests.order_id" in str(
            exc.orig
        ):
            raise BusinessError(
                "order_reopen_request_active", "An active reopen request already exists"
            ) from exc
        raise
    logger.info(
        "order_reopen_request_total",
        extra={
            "metric": "order_reopen_request_total",
            "result": "success",
            "command": "request",
            "actor_id": actor_id,
            "branch_id": order["branch_id"],
            "request_id": request["id"],
        },
    )
    return response


def list_order_accounts(
    session: Session, raw: dict[str, Any], actor_user_id: str | None = None
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    branch_id = authorize_branch_scope(session, actor_id, "orders.read", raw.get("branch_id"))
    limit = int(raw.get("limit", 50))
    if not 1 <= limit <= 100:
        raise BusinessError("order_accounts_limit_invalid", "Limit must be between 1 and 100")
    service = raw.get("service_type")
    if service and service not in {"dine-in", "takeout", "delivery"}:
        raise BusinessError("order_accounts_service_invalid", "Service type is invalid")

    def parse(name: str) -> datetime | None:
        value = raw.get(name)
        if not value:
            return None
        parsed = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        )
        if parsed.tzinfo is None:
            raise BusinessError(
                "order_accounts_datetime_invalid", "Datetimes must include a timezone"
            )
        return parsed

    start, end = parse("from_utc"), parse("to_utc")
    if (start is None) != (end is None) or (start and start >= end):
        raise BusinessError(
            "order_accounts_interval_invalid", "Interval must be valid and complete"
        )
    q = str(raw.get("q") or "").strip()
    if q and not 2 <= len(q) <= 120:
        raise BusinessError(
            "order_accounts_query_invalid", "Search must contain 2 to 120 characters"
        )
    filters = {
        "branch_id": branch_id,
        "from_utc": start.isoformat() if start else None,
        "to_utc": end.isoformat() if end else None,
        "cash_shift_id": raw.get("cash_shift_id"),
        "register_code": raw.get("register_code"),
        "service_type": service,
        "q": q.casefold() or None,
    }
    cursor_created: datetime | None = None
    cursor_id: str | None = None
    if cursor := raw.get("cursor"):
        try:
            data = json.loads(urlsafe_b64decode(str(cursor).encode()).decode())
            if data.get("h") != _pco005_hash(filters) or not isinstance(data.get("i"), str):
                raise ValueError("cursor filters")
            cursor_created = datetime.fromisoformat(data["c"])
            if cursor_created.tzinfo is None:
                raise ValueError("cursor timestamp is naive")
            cursor_id = data["i"]
        except (
            BinasciiError,
            UnicodeDecodeError,
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise BusinessError(
                "order_accounts_cursor_invalid", "Cursor does not match filters"
            ) from exc
    query = (
        sa.select(models.orders, models.cash_shifts.c.register_code)
        .outerjoin(models.cash_shifts, models.cash_shifts.c.id == models.orders.c.cash_shift_id)
        .where(models.orders.c.organization_id == ORGANIZATION_ID)
    )
    if branch_id:
        query = query.where(models.orders.c.branch_id == branch_id)
    if start:
        query = query.where(models.orders.c.created_at >= start, models.orders.c.created_at < end)
    if raw.get("cash_shift_id"):
        query = query.where(models.orders.c.cash_shift_id == raw["cash_shift_id"])
    if raw.get("register_code"):
        query = query.where(models.cash_shifts.c.register_code == raw["register_code"])
    if service:
        query = query.where(models.orders.c.order_type == service)
    if q:
        query = query.where(
            sa.or_(
                sa.func.lower(models.orders.c.folio).contains(q),
                sa.func.lower(models.orders.c.owner_name).contains(q),
                sa.func.lower(models.orders.c.customer_snapshot["name"].as_string()).contains(q),
            )
        )
    if cursor_id:
        query = query.where(
            sa.tuple_(models.orders.c.created_at, models.orders.c.id)
            < sa.tuple_(cursor_created, cursor_id)
        )
    rows = [
        dict(row)
        for row in session.execute(
            query.order_by(models.orders.c.created_at.desc(), models.orders.c.id.desc()).limit(
                limit + 1
            )
        ).mappings()
    ]
    has_more, rows = len(rows) > limit, rows[:limit]
    items = []
    if (
        branch_id
        and not cursor_id
        and not raw.get("cash_shift_id")
        and not raw.get("register_code")
    ):
        intent_query = (
            sa.select(models.public_order_intents)
            .where(
                models.public_order_intents.c.organization_id == ORGANIZATION_ID,
                models.public_order_intents.c.branch_id == branch_id,
                models.public_order_intents.c.status == "PENDING_REVIEW",
            )
            .order_by(models.public_order_intents.c.created_at.desc())
        )
        intent_rows = session.execute(intent_query).mappings().all()
        for intent in intent_rows:
            cust_name = (intent.get("customer_snapshot") or {}).get("name")
            items.append(
                {
                    "id": intent["id"],
                    "folio": f"WEB-{intent['public_reference'][-6:]}",
                    "branch_id": intent["branch_id"],
                    "cash_shift_id": None,
                    "register_code": "WEB",
                    "status": "PENDING",
                    "service_type": intent["order_type"],
                    "total_cents": intent["total_cents"],
                    "currency": intent["currency"],
                    "created_at": intent["created_at"],
                    "customer_label": f"🌐 {cust_name or 'Cliente Web'}",
                    "payment_status": "UNPAID",
                    "production_summary": {
                        "task_count": 0,
                        "started": False,
                    },
                    "reopen_eligible": False,
                    "active_reopen_request_status": None,
                    "is_public_intent": True,
                    "public_reference": intent["public_reference"],
                }
            )

    for order in rows:
        detail = get_order_detail(session, order["id"], actor_id)
        items.append(
            {
                "id": order["id"],
                "folio": order["folio"],
                "branch_id": order["branch_id"],
                "cash_shift_id": order["cash_shift_id"],
                "register_code": order["register_code"],
                "status": order["status"],
                "service_type": order["order_type"],
                "total_cents": order["total_cents"],
                "currency": order["currency"],
                "created_at": order["created_at"],
                "customer_label": (order.get("customer_snapshot") or {}).get("name")
                or order.get("owner_name"),
                "payment_status": detail["payment_status"],
                "production_summary": {
                    "task_count": len(detail["production_tasks"]),
                    "started": any(
                        task["status"] != "PENDING" for task in detail["production_tasks"]
                    ),
                },
                "reopen_eligible": detail["reopen_eligible"],
                "active_reopen_request_status": detail["active_reopen_request_status"],
            }
        )
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = urlsafe_b64encode(
            json.dumps(
                {"h": _pco005_hash(filters), "c": last["created_at"].isoformat(), "i": last["id"]}
            ).encode()
        ).decode()
    return {"items": items, "next_cursor": next_cursor}


def count_pending_orders(
    session: Session, branch_id: str | None, actor_user_id: str | None = None
) -> dict[str, int]:
    actor_id = _actor_user_id(actor_user_id)
    authorized_branch_id = authorize_branch_scope(session, actor_id, "orders.read", branch_id)
    if not authorized_branch_id:
        raise BusinessError(
            "pending_order_count_branch_required",
            "An active branch is required to count pending orders",
        )
    order_count = session.execute(
        sa.select(sa.func.count())
        .select_from(models.orders)
        .where(
            models.orders.c.organization_id == ORGANIZATION_ID,
            models.orders.c.branch_id == authorized_branch_id,
            models.orders.c.status == "PENDING",
        )
    ).scalar_one()

    intent_count = session.execute(
        sa.select(sa.func.count())
        .select_from(models.public_order_intents)
        .where(
            models.public_order_intents.c.organization_id == ORGANIZATION_ID,
            models.public_order_intents.c.branch_id == authorized_branch_id,
            models.public_order_intents.c.status == "PENDING_REVIEW",
        )
    ).scalar_one()

    return {"count": int(order_count) + int(intent_count)}


def list_order_reopen_requests(
    session: Session, raw: dict[str, Any], actor_user_id: str | None = None
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    branch_id = authorize_branch_scope(
        session, actor_id, "orders.reopen.authorize", raw.get("branch_id")
    )
    limit = int(raw.get("limit", 50))
    if not 1 <= limit <= 100:
        raise BusinessError(
            "order_reopen_requests_limit_invalid", "Limit must be between 1 and 100"
        )
    status = raw.get("status")
    if status and status not in {"REQUESTED", "APPROVED", "REJECTED", "EXPIRED", "APPLIED"}:
        raise BusinessError("order_reopen_requests_status_invalid", "Status is invalid")
    filters = {"branch_id": branch_id, "status": status}
    created: datetime | None = None
    request_id: str | None = None
    if cursor := raw.get("cursor"):
        try:
            data = json.loads(urlsafe_b64decode(str(cursor).encode()).decode())
            if data.get("h") != _pco005_hash(filters) or not isinstance(data.get("i"), str):
                raise ValueError("cursor filters")
            created = datetime.fromisoformat(data["c"])
            if created.tzinfo is None:
                raise ValueError("cursor timestamp is naive")
            request_id = data["i"]
        except (
            BinasciiError,
            UnicodeDecodeError,
            ValueError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise BusinessError(
                "order_reopen_requests_cursor_invalid", "Cursor does not match filters"
            ) from exc
    query = sa.select(models.order_reopen_requests).where(
        models.order_reopen_requests.c.organization_id == ORGANIZATION_ID
    )
    if branch_id:
        query = query.where(models.order_reopen_requests.c.branch_id == branch_id)
    if status:
        query = query.where(models.order_reopen_requests.c.status == status)
    if request_id:
        query = query.where(
            sa.tuple_(
                models.order_reopen_requests.c.requested_at, models.order_reopen_requests.c.id
            )
            < sa.tuple_(created, request_id)
        )
    rows = [
        dict(row)
        for row in session.execute(
            query.order_by(
                models.order_reopen_requests.c.requested_at.desc(),
                models.order_reopen_requests.c.id.desc(),
            ).limit(limit + 1)
        ).mappings()
    ]
    has_more, rows = len(rows) > limit, rows[:limit]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = urlsafe_b64encode(
            json.dumps(
                {"h": _pco005_hash(filters), "c": last["requested_at"].isoformat(), "i": last["id"]}
            ).encode()
        ).decode()
    return {"items": [_pco005_request_dto(row) for row in rows], "next_cursor": next_cursor}


def decide_order_reopen_request(
    session: Session,
    request_id: str,
    decision: str,
    payload: dict[str, Any],
    idempotency_key: str | None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id, key = _actor_user_id(actor_user_id), _pco005_key(idempotency_key)
    reason = str(payload.get("decision_reason") or "").strip()
    if decision not in {"APPROVED", "REJECTED"} or not 10 <= len(reason) <= 500:
        raise BusinessError("order_reopen_decision_invalid", "Decision reason is invalid")
    request = (
        session.execute(
            sa.select(models.order_reopen_requests)
            .where(models.order_reopen_requests.c.id == request_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not request:
        raise NotFoundError("order_reopen_request_not_found", "Reopen request was not found")
    require_permission(session, actor_id, "orders.reopen.authorize", request["branch_id"])
    command = "approve" if decision == "APPROVED" else "reject"
    digest = _pco005_hash(
        {"request_id": request_id, "decision": decision, "decision_reason": reason}
    )
    if replay := _pco005_replay(session, key, command, digest):
        logger.info(
            "order_reopen_decision_total",
            extra={
                "metric": "order_reopen_decision_total",
                "result": "replay",
                "command": command,
                "actor_id": actor_id,
                "branch_id": request["branch_id"],
                "request_id": request_id,
            },
        )
        return replay
    if request["status"] != "REQUESTED":
        raise BusinessError("order_reopen_transition_invalid", "Request is no longer pending")
    version = session.execute(
        sa.select(models.orders.c.version)
        .where(models.orders.c.id == request["order_id"])
        .with_for_update()
    ).scalar_one()
    if version != request["order_version_snapshot"]:
        raise BusinessError("order_version_conflict", "Order version changed")
    now = _now()
    updated = dict(request)
    updated.update(
        status=decision,
        decided_by_user_id=actor_id,
        decided_at=now,
        decision_reason=reason,
        updated_at=now,
    )
    response = _pco005_request_dto(updated)
    session.execute(
        models.order_reopen_requests.update()
        .where(models.order_reopen_requests.c.id == request_id)
        .values(
            status=decision,
            decided_by_user_id=actor_id,
            decided_at=now,
            decision_reason=reason,
            updated_at=now,
        )
    )
    session.execute(
        models.order_reopen_commands.insert().values(
            id=_id(),
            organization_id=ORGANIZATION_ID,
            request_id=request_id,
            order_id=request["order_id"],
            command_type=command,
            idempotency_key=key,
            request_hash=digest,
            status="completed",
            response_snapshot=_sanitize_for_json(response),
            actor_user_id=actor_id,
            created_at=now,
        )
    )
    _audit(
        session,
        action=f"order.reopen.{decision.lower()}",
        entity_type="order_reopen_request",
        entity_id=request_id,
        payload={
            "order_id": request["order_id"],
            "previous_status": "REQUESTED",
            "new_status": decision,
            "order_version_snapshot": version,
        },
        branch_id=request["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    logger.info(
        "order_reopen_decision_total",
        extra={
            "metric": "order_reopen_decision_total",
            "result": "success",
            "command": command,
            "actor_id": actor_id,
            "decision": decision.lower(),
            "branch_id": request["branch_id"],
            "request_id": request_id,
        },
    )
    return response


def apply_order_reopen_request(
    session: Session,
    request_id: str,
    payload: dict[str, Any] | str | None = None,
    idempotency_key: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Apply an approved reopen only by creating linked compensating facts.

    The legacy no-body call remains deliberately fail-closed for PCO-005A callers.
    """
    if not isinstance(payload, dict):
        legacy_actor = payload if isinstance(payload, str) else actor_user_id
        request = (
            session.execute(
                sa.select(models.order_reopen_requests).where(
                    models.order_reopen_requests.c.id == request_id
                )
            )
            .mappings()
            .first()
        )
        if not request:
            raise NotFoundError("order_reopen_request_not_found", "Reopen request was not found")
        require_permission(
            session, _actor_user_id(legacy_actor), "orders.reopen.authorize", request["branch_id"]
        )
        raise BusinessError(
            "order_reopen_policy_pending",
            "Compensating application requires a complete approved plan",
        )
    # SQLite's IMMEDIATE reservation must happen before *any* request/order
    # read.  Starting it after a read rolls that read back and leaves the
    # in-memory mapping stale relative to the transaction that will write.
    _begin_cash_shift_serialization(session)
    request = (
        session.execute(
            sa.select(models.order_reopen_requests)
            .where(models.order_reopen_requests.c.id == request_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not request:
        raise NotFoundError("order_reopen_request_not_found", "Reopen request was not found")
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "orders.reopen.authorize", request["branch_id"])
    _require_order_correction_owner(session, actor_id, request["branch_id"])
    key = _pco005_key(idempotency_key)
    required = {
        "expected_order_version",
        "lines",
        "production_dispositions",
        "settlement_method",
        "settlement_evidence_refs",
    }
    allowed = required | {"register_id"}
    if (
        not required.issubset(payload)
        or not set(payload).issubset(allowed)
        or not isinstance(payload["expected_order_version"], int)
        or isinstance(payload["expected_order_version"], bool)
        or not isinstance(payload["lines"], list)
        or not isinstance(payload["production_dispositions"], list)
        or not isinstance(payload["settlement_evidence_refs"], list)
    ):
        raise BusinessError("order_reopen_plan_invalid", "Correction plan has an invalid shape")
    dispositions: dict[tuple[str, str], dict[str, Any]] = {}
    for item in payload["production_dispositions"]:
        if not isinstance(item, dict) or set(item) != {
            "source_line_id",
            "source_task_id",
            "quantity",
            "disposition",
        }:
            raise BusinessError("order_reopen_plan_invalid", "Production disposition is invalid")
        try:
            quantity = Decimal(str(item["quantity"]))
        except (InvalidOperation, TypeError):
            raise BusinessError(
                "order_reopen_plan_invalid", "Production disposition quantity is invalid"
            ) from None
        key_disposition = (str(item["source_line_id"]), str(item["source_task_id"]))
        if (
            quantity <= 0
            or item["disposition"] not in {"waste", "recovery"}
            or key_disposition in dispositions
        ):
            raise BusinessError("order_reopen_plan_invalid", "Production disposition is invalid")
        dispositions[key_disposition] = {**item, "quantity": quantity}
    method = str(payload["settlement_method"]).lower()
    if not all(isinstance(item, str) for item in payload["settlement_evidence_refs"]):
        raise BusinessError(
            "order_reopen_plan_invalid", "Correction settlement evidence is invalid"
        )
    evidence = [item.strip() for item in payload["settlement_evidence_refs"]]
    if method not in {"cash", "debit_card", "credit_card", "transfer"} or any(
        not item or len(item) > 500 for item in evidence
    ):
        raise BusinessError("order_reopen_plan_invalid", "Correction settlement is invalid")
    # Actor is part of the command identity.  A valid replay must be
    # reauthorized first, but it may never transfer the original owner's
    # command result to a different owner using the same key.
    digest = _pco005_hash({"request_id": request_id, "actor_user_id": actor_id, "payload": payload})
    if replay := _pco005_replay(session, key, "apply", digest):
        return replay
    if request["status"] != "APPROVED":
        raise BusinessError("order_reopen_transition_invalid", "Request is not approved")
    order = (
        session.execute(
            sa.select(models.orders)
            .where(models.orders.c.id == request["order_id"])
            .with_for_update()
        )
        .mappings()
        .one()
    )
    if (
        payload["expected_order_version"] != request["order_version_snapshot"]
        or order["version"] != request["order_version_snapshot"]
    ):
        raise BusinessError(
            "order_version_conflict", "Order version no longer matches approved request"
        )
    payments = [
        dict(row)
        for row in session.execute(
            sa.select(models.payments).where(
                models.payments.c.order_id == order["id"], models.payments.c.status == "CONFIRMED"
            )
        ).mappings()
    ]
    if len(payments) != 1 or payments[0]["currency"] != order["currency"]:
        raise BusinessError(
            "payment_adjustment_invalid",
            "Exactly one confirmed payment with matching currency is required",
        )
    if not request["before_snapshot"].get("sales_operation_snapshot_id"):
        raise BusinessError("historical_snapshot_missing", "Historical sales snapshot is required")
    # PCO-005B permits exact retained historic lines and additions.  The snapshot
    # is the authority for retained lines; addition pricing is server-derived.
    correction_lines: list[dict[str, Any]] = []
    corrected_total = 0
    snapshot_lines = {
        str(line["id"]): line
        for line in request["before_snapshot"].get("lines", [])
        if isinstance(line, dict) and line.get("id")
    }
    historic_lines = {
        row["id"]: dict(row)
        for row in session.execute(
            sa.select(models.order_lines).where(
                models.order_lines.c.order_id == order["id"],
                models.order_lines.c.status == "active",
            )
        ).mappings()
    }
    seen_source_ids: set[str] = set()
    for item in payload["lines"]:
        if not isinstance(item, dict):
            raise BusinessError("order_reopen_plan_invalid", "Correction line is invalid")
        item_keys = set(item)
        retained = item_keys == {"source_line_id", "quantity"}
        addition = item_keys == {"product_id", "quantity"}
        if retained == addition:
            raise BusinessError(
                "order_reopen_plan_invalid", "Correction line must be one exact variant"
            )
        try:
            quantity = Decimal(str(item["quantity"]))
        except (KeyError, InvalidOperation):
            raise BusinessError(
                "order_reopen_plan_invalid", "Correction line quantity is invalid"
            ) from None
        if quantity <= 0 or quantity != quantity.to_integral_value():
            raise BusinessError(
                "order_reopen_plan_invalid", "Correction quantity must be a positive whole amount"
            )
        source_id = item.get("source_line_id") if retained else None
        if retained:
            source_id = str(source_id)
            if source_id in seen_source_ids:
                raise BusinessError("order_reopen_plan_invalid", "Historic line cannot be repeated")
            seen_source_ids.add(source_id)
            source = historic_lines.get(str(source_id))
            snapshot = snapshot_lines.get(source_id)
            if (
                not source
                or not snapshot
                or int(snapshot.get("revision", source["revision"])) != int(source["revision"])
                or int(
                    snapshot.get(
                        "total_cents", snapshot.get("line_total_cents", source["line_total_cents"])
                    )
                )
                != int(source["line_total_cents"])
            ):
                raise BusinessError(
                    "historical_snapshot_missing", "Historic correction line is unavailable"
                )
            if quantity > Decimal(str(source["quantity"])):
                raise BusinessError(
                    "order_reopen_plan_invalid", "Historic quantity cannot increase"
                )
            price = int(source["unit_price_cents"])
            source_quantity = int(source["quantity"])
            modifier_total = int(source["modifier_total_cents"])
            if (
                modifier_total % source_quantity != 0
                or int(source["line_total_cents"]) != price * source_quantity + modifier_total
            ):
                raise BusinessError(
                    "historical_snapshot_missing", "Historic line pricing is not reproducible"
                )
            row = {
                "source_line_id": source_id,
                "product_id": source["product_id"],
                "product_name_snapshot": source["product_name"],
                "family_name_snapshot": source["family_name_snapshot"],
                "unit_price_cents": price,
                "modifiers_snapshot": source["selected_modifiers"],
                "classification": "RETAINED",
            }
        else:
            product_id = item.get("product_id")
            if not isinstance(product_id, str) or not product_id.strip():
                raise BusinessError("order_reopen_plan_invalid", "Added product is invalid")
            product = _get_available_product(session, product_id, order["branch_id"])
            if not product or product["currency"] != order["currency"]:
                raise BusinessError("order_reopen_plan_invalid", "Added product is invalid")
            price = int(product["price_cents"])
            row = {
                "source_line_id": None,
                "product_id": product_id,
                "product_name_snapshot": product["name"],
                "family_name_snapshot": product["family_name"],
                "unit_price_cents": price,
                "modifiers_snapshot": [],
                "classification": "ADDITION",
            }
        line_total = (
            (price + int(source["modifier_total_cents"]) // int(source["quantity"])) * int(quantity)
            if source_id
            else price * int(quantity)
        )
        corrected_total += line_total
        correction_lines.append(
            {**row, "id": _id(), "quantity": quantity, "line_total_cents": line_total}
        )
    delta = corrected_total - int(payments[0]["amount_cents"])
    if delta and method != "cash" and not evidence:
        raise BusinessError("payment_adjustment_invalid", "Non-cash adjustment requires evidence")
    if method == "cash":
        register_id = payload.get("register_id")
        if not isinstance(register_id, str) or not register_id.strip():
            raise BusinessError("cash_register_required", "Cash adjustment requires a register_id")
    if method != "cash" and "register_id" in payload:
        raise BusinessError(
            "order_reopen_plan_invalid", "register_id only applies to cash settlement"
        )
    tasks = [
        dict(row)
        for row in session.execute(
            sa.select(models.production_tasks).where(
                models.production_tasks.c.order_id == order["id"]
            )
        ).mappings()
    ]
    now = _now()
    correction_id = _id()
    correction = {
        "id": correction_id,
        "organization_id": ORGANIZATION_ID,
        "branch_id": order["branch_id"],
        "order_id": order["id"],
        "request_id": request_id,
        "folio": f"COR-{order['folio']}-{request_id[-6:]}",
        "captured_order_version": order["version"],
        "resulting_order_version": order["version"],
        "before_snapshot": request["before_snapshot"],
        "after_snapshot": {
            "lines": [
                {
                    "source_line_id": row["source_line_id"],
                    "quantity": str(row["quantity"]),
                    "line_total_cents": row["line_total_cents"],
                }
                for row in correction_lines
            ],
            "total_cents": corrected_total,
        },
        "currency": order["currency"],
        "corrected_total_cents": corrected_total,
        "settlement_delta_cents": delta,
        "actor_user_id": actor_id,
        "applied_at": now,
    }
    try:
        session.execute(models.order_corrections.insert().values(**correction))
        _pco005b_after_sensitive_write("correction")
        if correction_lines:
            session.execute(
                models.order_correction_lines.insert(),
                [{**row, "correction_id": correction_id} for row in correction_lines],
            )
            _pco005b_after_sensitive_write("correction_lines")
        production_adjustments: list[dict[str, Any]] = []
        desired_by_source = {
            row["source_line_id"]: Decimal(str(row["quantity"]))
            for row in correction_lines
            if row["source_line_id"]
        }
        # A task is relevant only when its historic line actually changes.  A
        # line omitted from the desired image means a full reduction, not an
        # unchanged line.  This is deliberately calculated from the frozen
        # historic line rather than current recipe/catalog state.
        affected_dispositions: set[tuple[str, str]] = set()
        for task in tasks:
            source = historic_lines.get(task["order_line_id"])
            if not source:
                continue
            original_quantity = Decimal(str(source["quantity"]))
            desired = desired_by_source.get(source["id"], Decimal("0"))
            reduced = original_quantity - desired
            if reduced <= 0:
                continue
            if task["status"] == "IN_PROGRESS":
                raise BusinessError("production_in_progress", "Affected production is in progress")
            correction_line = next(
                (row for row in correction_lines if row["source_line_id"] == source["id"]),
                None,
            )
            if task["status"] == "COMPLETED":
                disposition = dispositions.get((source["id"], task["id"]))
                if not disposition or disposition["quantity"] != reduced:
                    raise BusinessError(
                        "production_disposition_required",
                        "Completed production requires an exact waste or recovery disposition",
                    )
                affected_dispositions.add((source["id"], task["id"]))
                movement_type, sign, adjustment_type = (
                    ("WASTE", 0, "WASTE")
                    if disposition["disposition"] == "waste"
                    else ("RECOVERY", 1, "RECOVERY")
                )
                movements = _record_scaled_snapshot_inventory_movements(
                    session,
                    source["id"],
                    reduced,
                    original_quantity,
                    movement_type,
                    sign,
                    "Compensación de producción completada",
                    "order_correction",
                    correction_id,
                    now,
                )
                _pco005b_after_sensitive_write("inventory_movement")
                adjustment = {
                    "id": _id(),
                    "correction_id": correction_id,
                    "source_line_id": source["id"],
                    "source_task_id": task["id"],
                    "correction_line_id": None
                    if correction_line is None
                    else correction_line["id"],
                    "adjustment_type": adjustment_type,
                    "quantity": reduced,
                    "inventory_movement_id": movements[0]["id"] if movements else None,
                    "production_task_id": None,
                    "created_at": now,
                }
                session.execute(models.order_production_adjustments.insert().values(**adjustment))
                _pco005b_after_sensitive_write("production_adjustment")
                production_adjustments.append(adjustment)
                continue
            if task["status"] != "PENDING":
                raise BusinessError(
                    "historical_snapshot_missing", "Production task status is not supported"
                )
            movements = _record_scaled_snapshot_inventory_movements(
                session,
                source["id"],
                reduced,
                original_quantity,
                "RESERVATION_RELEASE",
                1,
                "Libera reserva por corrección",
                "order_correction",
                correction_id,
                now,
            )
            _pco005b_after_sensitive_write("inventory_movement")
            session.execute(
                models.production_tasks.update()
                .where(models.production_tasks.c.id == task["id"])
                .values(status="CANCELLED", completed_at=now)
            )
            _pco005b_after_sensitive_write("production_task")
            operational_id = None
            operational_task_id = None
            if desired > 0:
                operational_id = _id()
                operational_task_id = _id()
                operational = {
                    **source,
                    "id": operational_id,
                    "quantity": int(desired),
                    "status": "correction",
                    "revision": int(source["revision"]) + 1,
                    "supersedes_line_id": source["id"],
                    "updated_at": now,
                    "removed_at": None,
                    "created_at": now,
                }
                session.execute(models.order_lines.insert().values(**operational))
                snapshot = (
                    session.execute(
                        sa.select(models.order_line_consumption_snapshots).where(
                            models.order_line_consumption_snapshots.c.order_line_id == source["id"]
                        )
                    )
                    .mappings()
                    .first()
                )
                if not snapshot:
                    raise BusinessError(
                        "historical_snapshot_missing",
                        "Order line consumption snapshot was not found",
                    )
                factor = desired / original_quantity
                components = [
                    {
                        **component,
                        "net_quantity": _quantity(Decimal(str(component["net_quantity"])) * factor),
                        "gross_quantity": _quantity(
                            Decimal(str(component["gross_quantity"])) * factor
                        ),
                        "total_cost": _cost(Decimal(str(component.get("total_cost", 0))) * factor),
                    }
                    for component in snapshot["components"]
                ]
                session.execute(
                    models.order_line_consumption_snapshots.insert().values(
                        order_line_id=operational_id,
                        order_id=order["id"],
                        recipe_id=snapshot["recipe_id"],
                        recipe_version=snapshot["recipe_version"],
                        branch_id=order["branch_id"],
                        components=_sanitize_for_json(components),
                        modifiers=snapshot["modifiers"],
                        total_theoretical_cost=_cost(
                            Decimal(str(snapshot["total_theoretical_cost"])) * factor
                        ),
                        created_at=now,
                    )
                )
                session.execute(
                    models.production_tasks.insert().values(
                        id=operational_task_id,
                        organization_id=ORGANIZATION_ID,
                        branch_id=order["branch_id"],
                        order_id=order["id"],
                        order_line_id=operational_id,
                        station=source["station"],
                        status="PENDING",
                        product_name=source["product_name"],
                        quantity=int(desired),
                        created_at=now,
                        started_at=None,
                        completed_at=None,
                    )
                )
                session.execute(
                    models.order_correction_lines.update()
                    .where(models.order_correction_lines.c.id == correction_line["id"])
                    .values(operational_order_line_id=operational_id)
                )
                _pco005b_after_sensitive_write("replacement_task")
            adjustment = {
                "id": _id(),
                "correction_id": correction_id,
                "source_line_id": source["id"],
                "source_task_id": task["id"],
                "correction_line_id": None if correction_line is None else correction_line["id"],
                "adjustment_type": "RELEASE",
                "quantity": reduced,
                "inventory_movement_id": movements[0]["id"] if movements else None,
                "production_task_id": operational_task_id,
                "created_at": now,
            }
            session.execute(models.order_production_adjustments.insert().values(**adjustment))
            _pco005b_after_sensitive_write("production_adjustment")
            production_adjustments.append(adjustment)
        if set(dispositions) != affected_dispositions:
            raise BusinessError(
                "order_reopen_plan_invalid",
                "Production dispositions do not match completed reductions",
            )

        # Additions are operational lines backed by the recipe currently active
        # at apply time.  Their reservation/task are new facts; historic lines,
        # snapshots and tasks above remain untouched.
        for correction_line in (
            row for row in correction_lines if row["classification"] == "ADDITION"
        ):
            operational_id, task_id = _id(), _id()
            product = (
                session.execute(
                    sa.select(models.products).where(
                        models.products.c.id == correction_line["product_id"]
                    )
                )
                .mappings()
                .one()
            )
            snapshot = _build_order_consumption_snapshot(
                session,
                order["id"],
                operational_id,
                correction_line["product_id"],
                int(correction_line["quantity"]),
                order["branch_id"],
                now,
            )
            session.execute(
                models.order_lines.insert().values(
                    id=operational_id,
                    order_id=order["id"],
                    product_id=correction_line["product_id"],
                    product_name=product["name"],
                    quantity=int(correction_line["quantity"]),
                    unit_price_cents=correction_line["unit_price_cents"],
                    line_total_cents=correction_line["line_total_cents"],
                    station=product["station"],
                    selected_modifiers=snapshot["modifiers"],
                    modifier_total_cents=int(snapshot["modifier_total_cents"]),
                    line_notes=None,
                    status="correction",
                    revision=1,
                    supersedes_line_id=None,
                    updated_at=now,
                    removed_at=None,
                    family_id_snapshot=product["category_id"],
                    family_name_snapshot=correction_line["family_name_snapshot"],
                    family_snapshot_source="captured",
                    created_at=now,
                )
            )
            snapshot.pop("modifier_total_cents")
            session.execute(models.order_line_consumption_snapshots.insert().values(**snapshot))
            movements = _record_calculated_consumption_movements(
                session,
                snapshot["components"],
                product["name"],
                "SALE_RESERVATION",
                -1,
                "Reserva por adición de corrección",
                "order_correction",
                correction_id,
                now,
                order["branch_id"],
            )
            _pco005b_after_sensitive_write("inventory_movement")
            session.execute(
                models.production_tasks.insert().values(
                    id=task_id,
                    organization_id=ORGANIZATION_ID,
                    branch_id=order["branch_id"],
                    order_id=order["id"],
                    order_line_id=operational_id,
                    station=product["station"],
                    status="PENDING",
                    product_name=product["name"],
                    quantity=int(correction_line["quantity"]),
                    created_at=now,
                    started_at=None,
                    completed_at=None,
                )
            )
            _pco005b_after_sensitive_write("production_task")
            session.execute(
                models.order_correction_lines.update()
                .where(models.order_correction_lines.c.id == correction_line["id"])
                .values(operational_order_line_id=operational_id)
            )
            adjustment = {
                "id": _id(),
                "correction_id": correction_id,
                "source_line_id": None,
                "source_task_id": None,
                "correction_line_id": correction_line["id"],
                "adjustment_type": "ADDITION",
                "quantity": correction_line["quantity"],
                "inventory_movement_id": movements[0]["id"] if movements else None,
                "production_task_id": task_id,
                "created_at": now,
            }
            session.execute(models.order_production_adjustments.insert().values(**adjustment))
            _pco005b_after_sensitive_write("production_adjustment")
            production_adjustments.append(adjustment)
        adjustment = None
        if delta:
            adjustment_id, shift_id, movement_id = _id(), None, None
            if method == "cash":
                register_id = str(payload.get("register_id") or "").strip()
                if not register_id:
                    raise BusinessError(
                        "cash_register_required", "Cash adjustment requires a register_id"
                    )
                shift = _guard_open_cash_shift(session, register_id, order["branch_id"])
                shift_id, movement_id = shift["id"], _id()
                session.execute(
                    models.cash_movements.insert().values(
                        id=movement_id,
                        organization_id=ORGANIZATION_ID,
                        branch_id=order["branch_id"],
                        cash_shift_id=shift_id,
                        movement_type="deposit" if delta > 0 else "withdrawal",
                        amount_cents=abs(delta),
                        reason_code="ORDER_CORRECTION",
                        reason="Ajuste compensatorio de pedido",
                        source_type="order_correction",
                        source_id=correction_id,
                        actor_user_id=actor_id,
                        idempotency_key=f"correction-{correction_id}",
                        status="confirmed",
                        reversal_of_id=None,
                        concept_id=None,
                        concept_version_id=None,
                        concept_snapshot=None,
                        reference=None,
                        evidence_refs=None,
                        compensates_movement_id=None,
                        created_at=now,
                    )
                )
                _pco005b_after_sensitive_write("cash_movement")
            adjustment = {
                "id": adjustment_id,
                "correction_id": correction_id,
                "original_payment_id": payments[0]["id"],
                "adjustment_type": "CHARGE" if delta > 0 else "REFUND",
                "amount_cents": abs(delta),
                "method": method,
                "currency": order["currency"],
                "cash_shift_id": shift_id,
                "status": "CONFIRMED",
                "evidence_refs": evidence,
                "cash_movement_id": movement_id,
                "created_at": now,
            }
            session.execute(models.order_payment_adjustments.insert().values(**adjustment))
            _pco005b_after_sensitive_write("payment_adjustment")
        session.execute(
            models.order_events.insert().values(
                id=_id(),
                order_id=order["id"],
                event_type="ORDER_CORRECTION_APPLIED",
                payload={"correction_id": correction_id, "settlement_delta_cents": delta},
                created_at=now,
            )
        )
        _pco005b_after_sensitive_write("order_event")
        session.execute(
            models.order_reopen_requests.update()
            .where(models.order_reopen_requests.c.id == request_id)
            .values(status="APPLIED", applied_by_user_id=actor_id, applied_at=now, updated_at=now)
        )
        _pco005b_after_sensitive_write("reopen_request")
        response = _sanitize_for_json(
            {
                "status": "APPLIED",
                "correction": {
                    key: correction[key]
                    for key in (
                        "id",
                        "request_id",
                        "folio",
                        "corrected_total_cents",
                        "settlement_delta_cents",
                        "currency",
                        "applied_at",
                    )
                },
                "settlement_delta_cents": delta,
                "payment_adjustment": None
                if adjustment is None
                else {
                    key: adjustment[key]
                    for key in (
                        "id",
                        "adjustment_type",
                        "amount_cents",
                        "method",
                        "currency",
                        "cash_movement_id",
                    )
                },
                "production_adjustments": [
                    {
                        key: value
                        for key, value in row.items()
                        if key
                        in {
                            "id",
                            "adjustment_type",
                            "source_line_id",
                            "source_task_id",
                            "quantity",
                            "inventory_movement_id",
                            "production_task_id",
                        }
                    }
                    for row in production_adjustments
                ],
            }
        )
        session.execute(
            models.order_reopen_commands.insert().values(
                id=_id(),
                organization_id=ORGANIZATION_ID,
                request_id=request_id,
                order_id=order["id"],
                command_type="apply",
                idempotency_key=key,
                request_hash=digest,
                status="completed",
                response_snapshot=response,
                actor_user_id=actor_id,
                created_at=now,
            )
        )
        _pco005b_after_sensitive_write("command")
        _audit(
            session,
            action="order.reopen.applied",
            entity_type="order_correction",
            entity_id=correction_id,
            payload={"request_id": request_id, "settlement_delta_cents": delta},
            branch_id=order["branch_id"],
            actor_user_id=actor_id,
        )
        _pco005b_after_sensitive_write("audit")
        session.commit()
        return response
    except Exception:
        session.rollback()
        raise


def amend_order(
    session: Session,
    order_id: str,
    lines: list[dict[str, Any]],
    expected_version: int,
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    if not idempotency_key.strip():
        raise BusinessError("idempotency_key_required", "Idempotency-Key is required")
    actor_id = _actor_user_id(actor_user_id)
    order = (
        session.execute(sa.select(models.orders).where(models.orders.c.id == order_id))
        .mappings()
        .first()
    )
    if not order:
        raise NotFoundError("order_not_found", "Order was not found")
    require_permission(session, actor_id, "orders.amend", order["branch_id"])
    existing = (
        session.execute(
            sa.select(models.order_amendments).where(
                models.order_amendments.c.order_id == order_id,
                models.order_amendments.c.idempotency_key == idempotency_key.strip(),
            )
        )
        .mappings()
        .first()
    )
    if existing:
        return get_order_detail(session, order_id, actor_id)
    if not lines:
        raise BusinessError("invalid_quantity", "Order must have at least one line")
    if int(order["version"]) != expected_version:
        raise BusinessError("order_version_conflict", "Order version changed")
    if _confirmed_payment(session, order_id):
        raise BusinessError("order_has_payment", "Paid order cannot be amended")
    if order["status"] not in {"ACCEPTED", "PENDING"}:
        raise BusinessError("order_not_editable", "Order state does not allow amendments")
    old_lines = [
        dict(row)
        for row in session.execute(
            sa.select(models.order_lines)
            .where(
                models.order_lines.c.order_id == order_id,
                models.order_lines.c.status == "active",
            )
            .order_by(models.order_lines.c.created_at, models.order_lines.c.id)
        ).mappings()
    ]
    active_line_ids = {line["id"] for line in old_lines}
    tasks = [
        dict(row)
        for row in session.execute(
            sa.select(models.production_tasks).where(models.production_tasks.c.order_id == order_id)
        ).mappings()
        if row["order_line_id"] in active_line_ids
    ]
    if not tasks or any(task["status"] != "PENDING" for task in tasks):
        raise BusinessError(
            "production_already_started",
            "Order cannot be amended after production starts",
        )
    now = _now()
    next_version = expected_version + 1
    before_snapshot = {
        "version": expected_version,
        "total_cents": int(order["total_cents"]),
        "lines": [
            {
                "id": line["id"],
                "product_id": line["product_id"],
                "quantity": line["quantity"],
                "line_total_cents": line["line_total_cents"],
            }
            for line in old_lines
        ],
    }
    for line in old_lines:
        _record_snapshot_inventory_movements(
            session,
            order_line_id=line["id"],
            product_name=line["product_name"],
            movement_type="RESERVATION_RELEASE",
            sign=1,
            reason=f"Libera reserva por enmienda {order['folio']}",
            source_type="order_amendment",
            source_id=order_id,
            created_at=now,
        )
    session.execute(
        models.order_lines.update()
        .where(
            models.order_lines.c.order_id == order_id,
            models.order_lines.c.status == "active",
        )
        .values(status="removed", updated_at=now, removed_at=now)
    )
    session.execute(
        models.production_tasks.update()
        .where(
            models.production_tasks.c.order_id == order_id,
            models.production_tasks.c.order_line_id.in_(active_line_ids),
        )
        .values(status="CANCELLED", completed_at=now)
    )

    total_cents = 0
    new_lines: list[dict[str, Any]] = []
    new_tasks: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    for index, item in enumerate(lines):
        quantity = int(item.get("quantity", 1))
        if quantity <= 0:
            raise BusinessError("invalid_quantity", "Quantity must be positive")
        product_id = item.get("product_id")
        if not isinstance(product_id, str) or not product_id:
            raise BusinessError("product_unavailable", "Product is unavailable")
        product = _get_available_product(session, product_id, order["branch_id"])
        if not product:
            raise BusinessError(
                "product_unavailable", f"Product {item.get('product_id')} is unavailable"
            )
        line_id = _id()
        selections = list(item.get("modifiers", []))
        for comment_id in item.get("comment_preset_ids", []):
            selections.append(
                {"option_id": str(comment_id).strip(), "selection_kind": "order_comment"}
            )
        for extra in item.get("ingredient_extras", []):
            selections.append(
                {
                    "option_id": str(extra.get("extra_id", "")).strip(),
                    "portions": extra.get("portions", 1),
                    "selection_kind": "ingredient_extra",
                }
            )
        snapshot = _build_order_consumption_snapshot(
            session,
            order_id=order_id,
            order_line_id=line_id,
            product_id=product["id"],
            ordered_quantity=quantity,
            branch_id=order["branch_id"],
            created_at=now,
            selected_modifiers=selections,
        )
        modifier_total = int(snapshot["modifier_total_cents"])
        line_total = int(product["price_cents"]) * quantity + modifier_total
        total_cents += line_total
        new_line = {
            "id": line_id,
            "order_id": order_id,
            "product_id": product["id"],
            "product_name": product["name"],
            "quantity": quantity,
            "unit_price_cents": product["price_cents"],
            "line_total_cents": line_total,
            "station": product["station"],
            "selected_modifiers": snapshot["modifiers"],
            "modifier_total_cents": modifier_total,
            "line_notes": item.get("notes"),
            "family_id_snapshot": product["category_id"],
            "family_name_snapshot": product["family_name"],
            "family_snapshot_source": "captured",
            "status": "active",
            "revision": next_version,
            "supersedes_line_id": old_lines[index]["id"] if index < len(old_lines) else None,
            "updated_at": now,
            "removed_at": None,
            "created_at": now,
        }
        new_lines.append(new_line)
        new_tasks.append(
            {
                "id": _id(),
                "organization_id": ORGANIZATION_ID,
                "branch_id": order["branch_id"],
                "order_id": order_id,
                "order_line_id": line_id,
                "station": product["station"],
                "status": "PENDING",
                "product_name": product["name"],
                "quantity": quantity,
                "created_at": now,
                "started_at": None,
                "completed_at": None,
            }
        )
        _record_calculated_consumption_movements(
            session,
            components=snapshot["components"],
            product_name=product["name"],
            movement_type="SALE_RESERVATION",
            sign=-1,
            reason=f"Reserva por enmienda {order['folio']}",
            source_type="order_amendment",
            source_id=order_id,
            created_at=now,
            branch_id=order["branch_id"],
        )
        snapshot.pop("modifier_total_cents")
        snapshots.append(snapshot)

    session.execute(models.order_lines.insert(), new_lines)
    session.execute(models.production_tasks.insert(), new_tasks)
    session.execute(models.order_line_consumption_snapshots.insert(), snapshots)
    session.execute(
        models.orders.update()
        .where(models.orders.c.id == order_id)
        .values(total_cents=total_cents, version=next_version)
    )
    after_snapshot = {
        "version": next_version,
        "total_cents": total_cents,
        "lines": [
            {
                "id": line["id"],
                "product_id": line["product_id"],
                "quantity": line["quantity"],
                "line_total_cents": line["line_total_cents"],
            }
            for line in new_lines
        ],
    }
    sequence = (
        session.execute(
            sa.select(sa.func.count(models.order_amendments.c.id)).where(
                models.order_amendments.c.order_id == order_id
            )
        ).scalar_one()
        + 1
    )
    session.execute(
        models.order_amendments.insert().values(
            id=_id(),
            order_id=order_id,
            sequence=sequence,
            expected_version=expected_version,
            resulting_version=next_version,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            actor_user_id=actor_id,
            idempotency_key=idempotency_key.strip(),
            created_at=now,
        )
    )
    session.execute(
        models.order_events.insert().values(
            id=_id(),
            order_id=order_id,
            event_type="ORDER_AMENDED",
            payload={
                "previous_version": expected_version,
                "version": next_version,
                "total_cents": total_cents,
            },
            created_at=now,
        )
    )
    _audit(
        session,
        action="order.amended",
        entity_type="order",
        entity_id=order_id,
        payload={
            "previous_version": expected_version,
            "version": next_version,
            "total_cents": total_cents,
        },
        branch_id=order["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_order_detail(session, order_id, actor_id)


def cancel_order(
    session: Session,
    order_id: str,
    reason: str = "Cancelacion solicitada en POS",
    classification: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    normalized_reason = reason.strip() or "Cancelacion solicitada en POS"
    normalized_classification = (classification or "").strip().lower()
    order = (
        session.execute(
            sa.select(models.orders).where(
                models.orders.c.id == order_id,
                models.orders.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not order:
        raise BusinessError("order_not_found", "Order was not found")
    require_permission(session, actor_id, "orders.cancel", order["branch_id"])
    if order["status"] == "CLOSED":
        raise BusinessError("order_already_closed", "Order is already closed")
    if order["status"] == "CANCELLED":
        raise BusinessError("order_already_cancelled", "Order is already cancelled")
    if order["status"] not in {"ACCEPTED", "IN_PRODUCTION", "READY"}:
        raise BusinessError("order_not_cancellable", "Order cannot be cancelled from this state")

    paid = session.execute(
        sa.select(models.payments.c.id).where(
            models.payments.c.order_id == order_id,
            models.payments.c.status == "CONFIRMED",
        )
    ).first()
    if paid:
        raise BusinessError("order_has_payment", "Paid order cannot be cancelled here")

    tasks = [
        dict(row)
        for row in session.execute(
            sa.select(models.production_tasks).where(models.production_tasks.c.order_id == order_id)
        ).mappings()
    ]
    pending_tasks = [task for task in tasks if task["status"] == "PENDING"]
    completed_tasks = [task for task in tasks if task["status"] == "COMPLETED"]
    if any(task["status"] == "IN_PROGRESS" for task in tasks):
        raise BusinessError(
            "production_in_progress",
            "Order cannot be cancelled while production is in progress",
        )
    if len(pending_tasks) != len(tasks) and len(completed_tasks) != len(tasks):
        raise BusinessError(
            "production_not_cancellable",
            "Order can only be cancelled before production or after completed production",
        )

    now = _now()
    release_movements: list[dict[str, Any]] = []
    compensation_movements: list[dict[str, Any]] = []
    lines = session.execute(
        sa.select(models.order_lines).where(models.order_lines.c.order_id == order_id)
    ).mappings()
    if len(pending_tasks) == len(tasks):
        cancellation_kind = "reservation_release"
        for line in lines:
            release_movements.extend(
                _record_snapshot_inventory_movements(
                    session,
                    order_line_id=line["id"],
                    product_name=line["product_name"],
                    movement_type="RESERVATION_RELEASE",
                    sign=1,
                    reason=f"Libera reserva por cancelacion {order['folio']}",
                    source_type="order_cancellation",
                    source_id=order_id,
                    created_at=now,
                )
            )
    else:
        if normalized_classification not in {"waste", "recovery"}:
            raise BusinessError(
                "cancellation_classification_required",
                "Post-production cancellation requires waste or recovery classification",
            )
        cancellation_kind = normalized_classification
        movement_type = "WASTE" if normalized_classification == "waste" else "RECOVERY"
        sign = 0 if normalized_classification == "waste" else 1
        for line in lines:
            compensation_movements.extend(
                _record_snapshot_inventory_movements(
                    session,
                    order_line_id=line["id"],
                    product_name=line["product_name"],
                    movement_type=movement_type,
                    sign=sign,
                    reason=(
                        f"Cancelacion producida {order['folio']} clasificada como {movement_type}"
                    ),
                    source_type="post_production_cancellation",
                    source_id=order_id,
                    created_at=now,
                )
            )

    session.execute(
        models.orders.update().where(models.orders.c.id == order_id).values(status="CANCELLED")
    )
    if pending_tasks:
        session.execute(
            models.production_tasks.update()
            .where(models.production_tasks.c.order_id == order_id)
            .values(status="CANCELLED", completed_at=now)
        )
    session.execute(
        models.order_events.insert().values(
            id=_id(),
            order_id=order_id,
            event_type="ORDER_CANCELLED",
            payload={
                "reason": normalized_reason,
                "kind": cancellation_kind,
                "classification": normalized_classification or None,
                "inventory_releases": len(release_movements),
                "inventory_compensations": len(compensation_movements),
            },
            created_at=now,
        )
    )
    _audit(
        session,
        action="order.cancelled",
        entity_type="order",
        entity_id=order_id,
        payload={
            "folio": order["folio"],
            "reason": normalized_reason,
            "kind": cancellation_kind,
            "classification": normalized_classification or None,
            "inventory_releases": len(release_movements),
            "inventory_compensations": len(compensation_movements),
        },
        branch_id=order["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    returned_tasks = [
        {**task, "status": "CANCELLED", "completed_at": now}
        if task["status"] == "PENDING"
        else task
        for task in tasks
    ]
    return {
        **dict(order),
        "status": "CANCELLED",
        "cancellation_kind": cancellation_kind,
        "classification": normalized_classification or None,
        "production_tasks": returned_tasks,
    }


def pay_order(
    session: Session,
    order_id: str,
    amount_cents: int,
    method: str = "cash",
    actor_user_id: str | None = None,
    register_id: str | None = None,
    _failure_hook: Callable[[str], None] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    _begin_cash_shift_serialization(session)
    method_normalized = method.lower()
    if method_normalized not in {"cash", "card", "debit_card", "credit_card", "transfer"}:
        raise BusinessError("invalid_payment_method", "Payment method is not supported")
    if amount_cents <= 0:
        raise BusinessError("invalid_payment_amount", "Payment amount must be positive")

    order = (
        session.execute(
            sa.select(models.orders).where(
                models.orders.c.id == order_id,
                models.orders.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not order:
        raise BusinessError("order_not_found", "Order was not found")
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "payments.confirm", order["branch_id"])
    if not register_id or not register_id.strip():
        raise BusinessError("register_id_required", "A collection register is required")
    register_code = register_id.strip()
    key = str(idempotency_key or "").strip()
    if key and not 12 <= len(key) <= 160:
        raise BusinessError(
            "idempotency_key_invalid", "Idempotency-Key must contain 12 to 160 characters"
        )
    request_hash = hashlib.sha256(
        json.dumps(
            {
                "organization_id": ORGANIZATION_ID,
                "actor_user_id": actor_id,
                "order_id": order_id,
                "amount_cents": amount_cents,
                "method": method_normalized,
                "register_id": register_code,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if key:
        existing_command = (
            session.execute(
                sa.select(models.payment_commands).where(
                    models.payment_commands.c.organization_id == ORGANIZATION_ID,
                    models.payment_commands.c.idempotency_key == key,
                )
            )
            .mappings()
            .first()
        )
        if existing_command:
            if existing_command["request_hash"] != request_hash:
                raise BusinessError(
                    "payment_idempotency_conflict",
                    "Idempotency-Key was used for a different payment intention",
                )
            return dict(existing_command["response_snapshot"])

    collection_shift = _guard_open_cash_shift(session, register_code, order["branch_id"])
    order = (
        session.execute(
            sa.select(models.orders)
            .where(
                models.orders.c.id == order_id,
                models.orders.c.organization_id == ORGANIZATION_ID,
            )
            .with_for_update()
        )
        .mappings()
        .one()
    )
    if key:
        locked_command = (
            session.execute(
                sa.select(models.payment_commands).where(
                    models.payment_commands.c.organization_id == ORGANIZATION_ID,
                    models.payment_commands.c.idempotency_key == key,
                )
            )
            .mappings()
            .first()
        )
        if locked_command:
            if locked_command["request_hash"] != request_hash:
                raise BusinessError(
                    "payment_idempotency_conflict",
                    "Idempotency-Key was used for a different payment intention",
                )
            return dict(locked_command["response_snapshot"])
    if order["status"] == "CLOSED":
        raise BusinessError("order_already_closed", "Order is already closed")
    if order["status"] == "CANCELLED":
        raise BusinessError("order_cancelled", "Cancelled order cannot be paid")

    existing_payment = session.execute(
        sa.select(models.payments.c.id).where(
            models.payments.c.order_id == order_id,
            models.payments.c.status == "CONFIRMED",
        )
    ).first()
    if existing_payment:
        raise BusinessError("payment_already_confirmed", "Order already has a confirmed payment")
    if amount_cents != int(order["total_cents"]):
        raise BusinessError("payment_total_mismatch", "Payment amount must match order total")

    now = _now()
    payment = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "branch_id": order["branch_id"],
        "order_id": order_id,
        "cash_shift_id": collection_shift["id"],
        "method": method_normalized,
        "status": "CONFIRMED",
        "amount_cents": amount_cents,
        "currency": order["currency"],
        "confirmed_at": now,
        "created_at": now,
    }
    session.execute(models.payments.insert().values(**payment))
    active_lines = [
        dict(row)
        for row in session.execute(
            sa.select(models.order_lines).where(
                models.order_lines.c.order_id == order_id,
                models.order_lines.c.status == "active",
            )
        ).mappings()
    ]
    gross_cents = sum(int(line["line_total_cents"]) for line in active_lines)
    if gross_cents != amount_cents or any(
        not line.get("family_snapshot_source") or not line.get("family_name_snapshot")
        for line in active_lines
    ):
        raise BusinessError(
            "historical_snapshot_missing", "Historical sales snapshot cannot be created"
        )
    sales_snapshot = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "branch_id": order["branch_id"],
        "payment_id": payment["id"],
        "order_id": order_id,
        "cash_shift_id": collection_shift["id"],
        "register_code_snapshot": collection_shift["register_code"],
        "folio_snapshot": order["folio"],
        "service_type_snapshot": order["order_type"],
        "currency": order["currency"],
        "gross_cents": gross_cents,
        "net_cents": amount_cents,
        "discount_cents": 0,
        "courtesy_cents": 0,
        "tax_cents": 0,
        "quality_status": "captured",
        "confirmed_at": now,
        "created_at": now,
    }
    session.execute(models.sales_operation_snapshots.insert().values(**sales_snapshot))
    session.execute(
        models.sales_operation_line_snapshots.insert(),
        [
            {
                "id": _id(),
                "sales_operation_snapshot_id": sales_snapshot["id"],
                "payment_id": payment["id"],
                "order_line_id": line["id"],
                "product_id": line["product_id"],
                "product_name_snapshot": line["product_name"],
                "family_id_snapshot": line["family_id_snapshot"],
                "family_name_snapshot": line["family_name_snapshot"],
                "family_snapshot_source": line["family_snapshot_source"],
                "quantity": line["quantity"],
                "gross_cents": line["line_total_cents"],
                "net_cents": line["line_total_cents"],
                "discount_cents": 0,
                "courtesy_cents": 0,
                "tax_cents": 0,
            }
            for line in active_lines
        ],
    )
    if _failure_hook:
        try:
            _failure_hook("after_sales_snapshot")
        except Exception:
            session.rollback()
            raise
    session.execute(
        models.order_events.insert().values(
            id=_id(),
            order_id=order_id,
            event_type="PAYMENT_CONFIRMED",
            payload={
                "payment_id": payment["id"],
                "method": method_normalized,
                "amount_cents": amount_cents,
            },
            created_at=now,
        )
    )
    print_jobs = _create_print_jobs(session, dict(order), payment, now)
    _audit(
        session,
        action="payment.confirmed",
        entity_type="payment",
        entity_id=payment["id"],
        payload={"order_id": order_id, "method": method_normalized, "amount_cents": amount_cents},
        branch_id=order["branch_id"],
        actor_user_id=actor_id,
    )
    response = {
        **payment,
        "order_status": order["status"],
        "print_jobs": [
            {
                "id": job["id"],
                "organization_id": job["organization_id"],
                "branch_id": job["branch_id"],
                "order_id": job["order_id"],
                "job_type": job["job_type"],
                "target": job["target"],
                "status": job["status"],
                "attempts": job["attempts"],
                "created_at": job["created_at"],
                "printed_at": job["printed_at"],
            }
            for job in print_jobs
        ],
    }
    stable_response = cast(dict[str, Any], _sanitize_for_json(response))
    if key:
        session.execute(
            models.payment_commands.insert().values(
                id=_id(),
                organization_id=ORGANIZATION_ID,
                branch_id=order["branch_id"],
                actor_user_id=actor_id,
                order_id=order_id,
                payment_id=payment["id"],
                idempotency_key=key,
                request_hash=request_hash,
                response_snapshot=stable_response,
                created_at=now,
            )
        )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if not key:
            raise
        concurrent = (
            session.execute(
                sa.select(models.payment_commands).where(
                    models.payment_commands.c.organization_id == ORGANIZATION_ID,
                    models.payment_commands.c.idempotency_key == key,
                )
            )
            .mappings()
            .first()
        )
        if concurrent and concurrent["request_hash"] == request_hash:
            return dict(concurrent["response_snapshot"])
        raise BusinessError(
            "payment_idempotency_conflict",
            "Idempotency-Key was used for a different payment intention",
        ) from exc
    return stable_response


def list_payments(session: Session, branch_id: str | None = None) -> list[dict[str, Any]]:
    query = (
        sa.select(
            models.payments.c.id,
            models.payments.c.order_id,
            models.payments.c.method,
            models.payments.c.status,
            models.payments.c.amount_cents,
            models.payments.c.currency,
            models.payments.c.confirmed_at,
            models.orders.c.folio,
        )
        .select_from(
            models.payments.join(models.orders, models.payments.c.order_id == models.orders.c.id)
        )
        .order_by(models.payments.c.created_at.desc())
        .limit(50)
    )
    if branch_id:
        query = query.where(models.payments.c.branch_id == branch_id)
    rows = session.execute(query).mappings()
    return [dict(row) for row in rows]


def get_cash_shift_summary(
    session: Session,
    register_code: str = DEFAULT_REGISTER,
    branch_id: str | None = None,
) -> dict[str, Any]:
    shift = get_open_cash_shift(session, register_code, branch_id=branch_id)
    if shift:
        return {
            "cash_shift": shift,
            "cut": None,
            "summary": _cash_summary_for_shift(session, shift),
        }

    row = (
        session.execute(
            sa.select(models.cash_shifts)
            .where(
                models.cash_shifts.c.branch_id == (branch_id or BRANCH_ID),
                models.cash_shifts.c.register_code == register_code,
            )
            .order_by(models.cash_shifts.c.opened_at.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if not row:
        return {"cash_shift": None, "cut": None, "summary": None}

    shift = dict(row)
    closure = (
        session.execute(
            sa.select(models.cash_shift_closures).where(
                models.cash_shift_closures.c.cash_shift_id == shift["id"]
            )
        )
        .mappings()
        .first()
    )
    if closure:
        return {
            "cash_shift": shift,
            "closure": dict(closure),
            "cut": None,
            "summary": dict(closure)["summary_snapshot"],
        }
    cut = (
        session.execute(
            sa.select(models.cash_shift_cuts).where(
                models.cash_shift_cuts.c.cash_shift_id == shift["id"]
            )
        )
        .mappings()
        .first()
    )
    return {
        "cash_shift": shift,
        "cut": dict(cut) if cut else None,
        "summary": _cash_summary_for_shift(session, shift),
    }


def list_print_jobs(session: Session, branch_id: str) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(
            models.print_jobs.c.id,
            models.print_jobs.c.order_id,
            models.print_jobs.c.job_type,
            models.print_jobs.c.target,
            models.print_jobs.c.status,
            models.print_jobs.c.attempts,
            models.print_jobs.c.last_error,
            models.print_jobs.c.payload,
            models.print_jobs.c.created_at,
            models.print_jobs.c.printed_at,
            models.orders.c.folio,
        )
        .select_from(
            models.print_jobs.join(
                models.orders,
                models.print_jobs.c.order_id == models.orders.c.id,
            )
        )
        .where(models.print_jobs.c.branch_id == branch_id)
        .order_by(models.print_jobs.c.created_at.desc())
        .limit(50)
    ).mappings()
    return [dict(row) for row in rows]


def retry_print_job(
    session: Session,
    job_id: str,
    idempotency_key: str,
    branch_id: str,
    *,
    actor_user_id: str | None = None,
    _before_transition: Callable[[], None] | None = None,
) -> dict[str, Any]:
    job = (
        session.execute(
            sa.select(models.print_jobs).where(
                models.print_jobs.c.id == job_id, models.print_jobs.c.branch_id == branch_id
            )
        )
        .mappings()
        .first()
    )
    if not job:
        raise BusinessError("print_job_not_found", "Print job was not found")
    if not idempotency_key:
        raise BusinessError("idempotency_key_required", "Idempotency key is required")
    # The key identifies a replay; the command hash represents the canonical command.
    request_hash = hashlib.sha256(
        json.dumps(
            {"branch_id": branch_id, "job_id": job_id, "operation": "print.retry"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    existing = (
        session.execute(
            sa.select(models.print_attempts).where(
                models.print_attempts.c.print_job_id == job_id,
                models.print_attempts.c.idempotency_key == idempotency_key,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        if existing["request_hash"] != request_hash:
            raise BusinessError("idempotency_conflict", "Print retry payload changed")
        return {"job": dict(job), "attempt": dict(existing), "replayed": True}
    if job["status"] == "PRINTED":
        raise BusinessError("print_job_already_printed", "Print job is already printed")
    if job["status"] != "FAILED":
        raise BusinessError("print_job_transition_invalid", "Only a failed job may be retried")
    attempts = int(job["attempts"]) + 1
    attempt = {
        "id": _id(),
        "print_job_id": job_id,
        "organization_id": job["organization_id"],
        "branch_id": job["branch_id"],
        "idempotency_key": idempotency_key,
        "request_hash": request_hash,
        "status": "QUEUED",
        "created_at": _now(),
    }
    if _before_transition:
        _before_transition()
    try:
        transitioned = session.execute(
            models.print_jobs.update()
            .where(
                models.print_jobs.c.id == job_id,
                models.print_jobs.c.branch_id == branch_id,
                models.print_jobs.c.status == job["status"],
                models.print_jobs.c.attempts == job["attempts"],
            )
            .values(status="QUEUED", attempts=attempts, printed_at=None, last_error=None)
        )
        if transitioned.rowcount != 1:
            raise BusinessError(
                "print_job_transition_invalid", "Print job already has an active attempt"
            )
        session.execute(models.print_attempts.insert().values(**attempt))
        _audit(
            session,
            action="print_job.retried",
            entity_type="print_job",
            entity_id=job_id,
            payload={"from": job["status"], "to": "QUEUED", "attempts": attempts},
            branch_id=job["branch_id"],
            organization_id=job["organization_id"],
            actor_user_id=actor_user_id,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    updated = (
        session.execute(sa.select(models.print_jobs).where(models.print_jobs.c.id == job_id))
        .mappings()
        .one()
    )
    return {"job": dict(updated), "attempt": attempt, "replayed": False}


def list_queued_print_attempts(
    session: Session, organization_id: str, branch_id: str
) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(
            models.print_attempts.c.id.label("attempt_id"),
            models.print_attempts.c.print_job_id,
            models.print_attempts.c.created_at,
            models.print_jobs.c.job_type,
            models.print_jobs.c.target,
            models.print_jobs.c.payload,
        )
        .select_from(
            models.print_attempts.join(
                models.print_jobs,
                models.print_attempts.c.print_job_id == models.print_jobs.c.id,
            )
        )
        .where(
            models.print_attempts.c.organization_id == organization_id,
            models.print_attempts.c.branch_id == branch_id,
            models.print_attempts.c.status == "QUEUED",
        )
        .order_by(
            models.print_attempts.c.created_at.asc(),
            models.print_attempts.c.id.asc(),
        )
    ).mappings()
    return [dict(row) for row in rows]


def claim_print_attempt(
    session: Session,
    attempt_id: str,
    device_id: str,
    *,
    fail_after_update: bool = False,
) -> dict[str, Any]:
    attempt = (
        session.execute(
            sa.select(models.print_attempts).where(models.print_attempts.c.id == attempt_id)
        )
        .mappings()
        .first()
    )
    if not attempt or attempt["status"] != "QUEUED":
        raise BusinessError("print_job_transition_invalid", "Print attempt cannot be claimed")
    try:
        claimed = session.execute(
            models.print_attempts.update()
            .where(
                models.print_attempts.c.id == attempt_id, models.print_attempts.c.status == "QUEUED"
            )
            .values(status="CLAIMED", claimed_by_device_id=device_id, claimed_at=_now())
        )
        if claimed.rowcount != 1:
            raise BusinessError("print_job_transition_invalid", "Print attempt cannot be claimed")
        if fail_after_update:
            raise RuntimeError("injected_print_claim_failure")
        session.execute(
            models.print_jobs.update()
            .where(models.print_jobs.c.id == attempt["print_job_id"])
            .values(status="CLAIMED")
        )
        _audit(
            session,
            action="print_attempt.claimed",
            entity_type="print_attempt",
            entity_id=attempt_id,
            payload={
                "from": "QUEUED",
                "to": "CLAIMED",
                "actor_kind": "device",
                "device_id": device_id,
            },
            branch_id=attempt["branch_id"],
            organization_id=attempt["organization_id"],
            actor_user_id=None,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return dict(
        session.execute(
            sa.select(models.print_attempts).where(models.print_attempts.c.id == attempt_id)
        )
        .mappings()
        .one()
    )


def acknowledge_print_attempt(
    session: Session,
    attempt_id: str,
    device_id: str,
    acknowledgement: str,
    *,
    fail_after_update: bool = False,
) -> dict[str, Any]:
    attempt = (
        session.execute(
            sa.select(models.print_attempts).where(models.print_attempts.c.id == attempt_id)
        )
        .mappings()
        .first()
    )
    ack_hash = hashlib.sha256(acknowledgement.encode()).hexdigest() if acknowledgement else ""
    if (
        attempt
        and attempt["status"] == "PRINTED"
        and attempt["claimed_by_device_id"] == device_id
        and attempt["ack_hash"] == ack_hash
    ):
        return dict(attempt)
    if (
        not attempt
        or attempt["status"] != "CLAIMED"
        or attempt["claimed_by_device_id"] != device_id
        or not acknowledgement
    ):
        raise BusinessError(
            "print_ack_required", "A valid claimed print acknowledgement is required"
        )
    now = _now()
    try:
        acknowledged = session.execute(
            models.print_attempts.update()
            .where(
                models.print_attempts.c.id == attempt_id,
                models.print_attempts.c.status == "CLAIMED",
                models.print_attempts.c.claimed_by_device_id == device_id,
            )
            .values(status="PRINTED", ack_hash=ack_hash, acked_at=now)
        )
        if acknowledged.rowcount != 1:
            raise BusinessError(
                "print_ack_required", "A valid claimed print acknowledgement is required"
            )
        if fail_after_update:
            raise RuntimeError("injected_print_ack_failure")
        session.execute(
            models.print_jobs.update()
            .where(models.print_jobs.c.id == attempt["print_job_id"])
            .values(status="PRINTED", printed_at=now)
        )
        _audit(
            session,
            action="print_attempt.acknowledged",
            entity_type="print_attempt",
            entity_id=attempt_id,
            payload={
                "from": "CLAIMED",
                "to": "PRINTED",
                "acknowledged": True,
                "actor_kind": "device",
                "device_id": device_id,
            },
            branch_id=attempt["branch_id"],
            organization_id=attempt["organization_id"],
            actor_user_id=None,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return dict(
        session.execute(
            sa.select(models.print_attempts).where(models.print_attempts.c.id == attempt_id)
        )
        .mappings()
        .one()
    )


def fail_print_attempt(
    session: Session,
    attempt_id: str,
    device_id: str,
    error_code: str,
    *,
    fail_after_update: bool = False,
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Z0-9_]{1,64}", error_code):
        raise BusinessError("print_job_transition_invalid", "Print failure code is invalid")
    attempt = (
        session.execute(
            sa.select(models.print_attempts).where(models.print_attempts.c.id == attempt_id)
        )
        .mappings()
        .first()
    )
    if (
        attempt
        and attempt["status"] == "FAILED"
        and attempt["claimed_by_device_id"] == device_id
        and attempt["error_code"] == error_code
    ):
        return dict(attempt)
    if (
        not attempt
        or attempt["status"] != "CLAIMED"
        or attempt["claimed_by_device_id"] != device_id
    ):
        raise BusinessError("print_job_transition_invalid", "Print attempt cannot be failed")
    now = _now()
    try:
        failed = session.execute(
            models.print_attempts.update()
            .where(
                models.print_attempts.c.id == attempt_id,
                models.print_attempts.c.status == "CLAIMED",
                models.print_attempts.c.claimed_by_device_id == device_id,
            )
            .values(status="FAILED", failed_at=now, error_code=error_code)
        )
        if failed.rowcount != 1:
            raise BusinessError("print_job_transition_invalid", "Print attempt cannot be failed")
        if fail_after_update:
            raise RuntimeError("injected_print_failure_failure")
        session.execute(
            models.print_jobs.update()
            .where(models.print_jobs.c.id == attempt["print_job_id"])
            .values(status="FAILED", last_error=error_code)
        )
        _audit(
            session,
            action="print_attempt.failed",
            entity_type="print_attempt",
            entity_id=attempt_id,
            payload={
                "from": "CLAIMED",
                "to": "FAILED",
                "error_code": error_code,
                "actor_kind": "device",
                "device_id": device_id,
            },
            branch_id=attempt["branch_id"],
            organization_id=attempt["organization_id"],
            actor_user_id=None,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return dict(
        session.execute(
            sa.select(models.print_attempts).where(models.print_attempts.c.id == attempt_id)
        )
        .mappings()
        .one()
    )


def recover_expired_print_claim(
    session: Session,
    attempt_id: str,
    organization_id: str,
    branch_id: str,
    *,
    now: datetime | None = None,
    lease_seconds: int = 300,
) -> dict[str, Any]:
    """Reconcile an uncertain abandoned claim to FAILED without re-enqueueing it."""
    current_time = now or _now()
    cutoff = current_time - timedelta(seconds=lease_seconds)
    attempt = (
        session.execute(
            sa.select(models.print_attempts).where(models.print_attempts.c.id == attempt_id)
        )
        .mappings()
        .first()
    )
    if (
        not attempt
        or attempt["organization_id"] != organization_id
        or attempt["branch_id"] != branch_id
    ):
        raise BusinessError("device_scope_denied", "Print attempt scope is denied")
    claimed_at = attempt["claimed_at"]
    comparable_claimed_at = (
        claimed_at.replace(tzinfo=UTC)
        if claimed_at is not None and claimed_at.tzinfo is None
        else claimed_at
    )
    if (
        attempt["status"] != "CLAIMED"
        or not comparable_claimed_at
        or comparable_claimed_at > cutoff
    ):
        raise BusinessError(
            "print_job_transition_invalid", "Print claim lease is not eligible for recovery"
        )
    try:
        recovered = session.execute(
            models.print_attempts.update()
            .where(
                models.print_attempts.c.id == attempt_id,
                models.print_attempts.c.status == "CLAIMED",
                models.print_attempts.c.claimed_at == claimed_at,
            )
            .values(
                status="FAILED",
                failed_at=current_time,
                error_code="CLAIM_LEASE_EXPIRED",
            )
        )
        if recovered.rowcount != 1:
            raise BusinessError(
                "print_job_transition_invalid", "Print claim lease is not eligible for recovery"
            )
        session.execute(
            models.print_jobs.update()
            .where(
                models.print_jobs.c.id == attempt["print_job_id"],
                models.print_jobs.c.status == "CLAIMED",
            )
            .values(status="FAILED", last_error="CLAIM_LEASE_EXPIRED")
        )
        _audit(
            session,
            action="print_attempt.lease_recovered",
            entity_type="print_attempt",
            entity_id=attempt_id,
            payload={"from": "CLAIMED", "to": "FAILED", "reason": "CLAIM_LEASE_EXPIRED"},
            branch_id=branch_id,
            organization_id=organization_id,
            actor_user_id=None,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return dict(
        session.execute(
            sa.select(models.print_attempts).where(models.print_attempts.c.id == attempt_id)
        )
        .mappings()
        .one()
    )


def receive_sync_command(
    session: Session,
    envelope: dict[str, Any],
    expected_organization_id: str | None = None,
    expected_branch_id: str | None = None,
    expected_device_id: str | None = None,
    *,
    actor_device_id: str | None = None,
    grant_verifier: Callable[[dict[str, Any]], str | None] | None = None,
) -> dict[str, Any]:
    """Atomically reconcile the sole allowlisted offline cash command."""
    _validate_sync_envelope(envelope)
    if str(envelope["command_type"]) != "cash.movement.create.v1":
        raise BusinessError(
            "unsupported_sync_command",
            f"Unsupported sync command type: {envelope['command_type']}",
        )
    _validate_pco008_sync_envelope(envelope)
    if (
        (
            expected_organization_id is not None
            and envelope["organization_id"] != expected_organization_id
        )
        or (expected_branch_id is not None and envelope["branch_id"] != expected_branch_id)
        or (expected_device_id is not None and envelope["source_device_id"] != expected_device_id)
    ):
        raise BusinessError("gateway_scope_denied", "Gateway command scope does not match")
    if actor_device_id is None:
        actor_device_id = expected_device_id
    if not actor_device_id:
        raise BusinessError("gateway_credential_required", "Gateway credential is required")
    if actor_device_id != str(envelope["source_device_id"]):
        raise BusinessError("gateway_scope_denied", "Gateway device scope does not match")

    organization_id = str(envelope["organization_id"])
    branch_id = str(envelope["branch_id"])
    source_device_id = str(envelope["source_device_id"])
    idempotency_key = str(envelope["idempotency_key"])
    request_hash = _sync_request_hash(envelope)
    _lock_sync_branch(session, organization_id, branch_id)
    existing = (
        session.execute(
            sa.select(models.sync_commands).where(
                models.sync_commands.c.organization_id == organization_id,
                sa.or_(
                    models.sync_commands.c.idempotency_key == idempotency_key,
                    models.sync_commands.c.command_id == str(envelope["command_id"]),
                ),
            )
        )
        .mappings()
        .first()
    )
    if existing:
        if existing["request_hash"] != request_hash:
            raise BusinessError("idempotency_conflict", "Sync command changed")
        if existing["status"] == "CONFLICT":
            code = _sync_conflict_code(session, str(existing["id"]))
            _record_pco008_metric(
                result="replay",
                error_code=code,
                organization_id=organization_id,
                branch_id=branch_id,
                source_device_id=source_device_id,
                checkpoint=int(existing["checkpoint"]),
            )
            return {
                "status": "CONFLICT",
                "code": code,
                "checkpoint": existing["checkpoint"],
                "replayed": True,
            }
        event = _get_sync_event_for_command(session, str(existing["id"]))
        movement_id = str(dict(event["payload"])["movement_id"])
        movement = (
            session.execute(
                sa.select(models.cash_movements).where(models.cash_movements.c.id == movement_id)
            )
            .mappings()
            .one()
        )
        _record_pco008_metric(
            result="replay",
            organization_id=organization_id,
            branch_id=branch_id,
            source_device_id=source_device_id,
            checkpoint=int(existing["checkpoint"]),
        )
        return {
            **_sync_confirmation(dict(existing), replayed=True),
            "movement": _redact_sync_movement(_serialize_cash_movement(dict(movement))),
        }
    grant_error = (grant_verifier or _validate_pco008_offline_grant)(envelope)
    if grant_error:
        return _store_sync_conflict(session, envelope, grant_error)

    now = _now()
    try:
        result = create_cash_movement(
            session,
            {"branch_id": branch_id, **dict(envelope["payload"])},
            idempotency_key,
            str(envelope["actor_user_id"]),
            commit=False,
        )
        _pco008_fault("after_cash_core")
    except BusinessError as exc:
        session.rollback()
        return _store_sync_conflict(session, envelope, exc.code)
    except Exception:
        session.rollback()
        raise

    checkpoint = _next_sync_checkpoint(session, organization_id, branch_id)
    command: dict[str, Any] = {
        "id": _id(),
        "organization_id": organization_id,
        "branch_id": branch_id,
        "source_device_id": source_device_id,
        "actor_user_id": str(envelope["actor_user_id"]),
        "command_id": str(envelope["command_id"]),
        "idempotency_key": idempotency_key,
        "command_type": str(envelope["command_type"]),
        "payload": _redacted_sync_payload(dict(envelope["payload"])),
        "request_hash": request_hash,
        "status": "CONFIRMED",
        "checkpoint": checkpoint,
        "occurred_at": _parse_datetime(str(envelope["occurred_at"])),
        "received_at": now,
        "confirmed_at": now,
    }
    event = {
        "id": _id(),
        "organization_id": organization_id,
        "branch_id": branch_id,
        "sync_command_id": command["id"],
        "event_type": "cash.movement.create.v1.confirmed",
        "checkpoint": checkpoint,
        "payload": {
            "command_id": command["command_id"],
            "command_type": command["command_type"],
            "movement_id": result["movement"]["id"],
        },
        "occurred_at": now,
    }
    try:
        session.execute(models.sync_commands.insert().values(**command))
        _pco008_fault("after_sync_command")
        session.execute(models.sync_events.insert().values(**event))
        _pco008_fault("after_sync_event")
        _audit(
            session,
            action="sync_command.confirmed",
            entity_type="sync_command",
            entity_id=command["id"],
            payload={"command_id": command["command_id"], "checkpoint": checkpoint},
            branch_id=branch_id,
            organization_id=organization_id,
            actor_user_id=str(envelope["actor_user_id"]),
        )
        _pco008_fault("after_audit")
        session.commit()
    except Exception:
        session.rollback()
        raise
    accepted_at = _parse_datetime(str(envelope["accepted_at"]))
    _record_pco008_metric(
        result="confirmed",
        organization_id=organization_id,
        branch_id=branch_id,
        source_device_id=source_device_id,
        checkpoint=checkpoint,
        lag_seconds=max(0, int((now - accepted_at).total_seconds())),
    )
    return {
        **_sync_confirmation(command, replayed=False),
        "movement": _redact_sync_movement(result["movement"]),
    }


def list_sync_events(
    session: Session,
    organization_id: str,
    branch_id: str,
    after_checkpoint: int = 0,
) -> list[dict[str, Any]]:
    query = (
        sa.select(models.sync_events)
        .select_from(
            models.sync_events.join(
                models.sync_commands,
                models.sync_events.c.sync_command_id == models.sync_commands.c.id,
            )
        )
        .where(
            models.sync_events.c.organization_id == organization_id,
            models.sync_events.c.branch_id == branch_id,
            models.sync_events.c.checkpoint > after_checkpoint,
        )
        .order_by(models.sync_events.c.checkpoint.asc())
        .limit(100)
    )
    rows = session.execute(query).mappings()
    return [dict(row) for row in rows]


def get_sync_status(
    session: Session,
    organization_id: str,
    branch_id: str,
) -> dict[str, Any]:
    command_count = int(
        session.execute(
            sa.select(sa.func.count())
            .select_from(models.sync_commands)
            .where(
                models.sync_commands.c.organization_id == organization_id,
                models.sync_commands.c.branch_id == branch_id,
            )
        ).scalar_one()
    )
    event_count = int(
        session.execute(
            sa.select(sa.func.count())
            .select_from(models.sync_events)
            .where(
                models.sync_events.c.organization_id == organization_id,
                models.sync_events.c.branch_id == branch_id,
            )
        ).scalar_one()
    )
    last_checkpoint = int(
        session.execute(
            sa.select(sa.func.coalesce(sa.func.max(models.sync_events.c.checkpoint), 0)).where(
                models.sync_events.c.organization_id == organization_id,
                models.sync_events.c.branch_id == branch_id,
            )
        ).scalar_one()
    )
    last_confirmed_at = session.execute(
        sa.select(sa.func.max(models.sync_commands.c.confirmed_at)).where(
            models.sync_commands.c.organization_id == organization_id,
            models.sync_commands.c.branch_id == branch_id,
        )
    ).scalar_one()
    return {
        "branch_id": branch_id,
        "last_checkpoint": last_checkpoint,
        "command_count": command_count,
        "event_count": event_count,
        "last_confirmed_at": last_confirmed_at,
    }


def list_kds_tasks(session: Session, branch_id: str) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(
            models.production_tasks.c.id,
            models.production_tasks.c.station,
            models.production_tasks.c.status,
            models.production_tasks.c.product_name,
            models.production_tasks.c.quantity,
            models.production_tasks.c.created_at,
            models.production_tasks.c.started_at,
            models.production_tasks.c.completed_at,
            models.orders.c.folio,
            models.orders.c.channel,
            models.orders.c.customer_snapshot,
            models.orders.c.owner_name,
            models.orders.c.order_type.label("service_type"),
            models.order_lines.c.selected_modifiers,
            models.order_lines.c.line_notes,
        )
        .select_from(
            models.production_tasks.join(
                models.orders,
                models.production_tasks.c.order_id == models.orders.c.id,
            ).join(
                models.order_lines,
                models.production_tasks.c.order_line_id == models.order_lines.c.id,
            )
        )
        .where(
            models.production_tasks.c.branch_id == branch_id,
            models.orders.c.status != "CANCELLED",
        )
        .order_by(models.production_tasks.c.created_at.desc())
        .limit(100)
    ).mappings()
    return [dict(row) for row in rows]


def advance_kds_task(
    session: Session,
    task_id: str,
    status: str,
    branch_id: str,
    *,
    actor_user_id: str | None = None,
    actor_device_id: str | None = None,
) -> dict[str, Any]:
    target = status.upper()
    task = (
        session.execute(
            sa.select(models.production_tasks).where(
                models.production_tasks.c.id == task_id,
                models.production_tasks.c.branch_id == branch_id,
            )
        )
        .mappings()
        .first()
    )
    if not task:
        raise BusinessError("task_not_found", "Production task was not found")

    current = task["status"]
    allowed = {("PENDING", "IN_PROGRESS"), ("IN_PROGRESS", "COMPLETED")}
    if (current, target) not in allowed:
        raise BusinessError("invalid_task_transition", f"Cannot move {current} to {target}")

    now = _now()
    values: dict[str, Any] = {"status": target}
    if target == "IN_PROGRESS":
        values["started_at"] = now
    if target == "COMPLETED":
        values["completed_at"] = now
    changed = session.execute(
        models.production_tasks.update()
        .where(
            models.production_tasks.c.id == task_id,
            models.production_tasks.c.status == current,
        )
        .values(**values)
    )
    if changed.rowcount != 1:
        session.rollback()
        raise BusinessError("task_transition_conflict", "Production task changed concurrently")

    if target == "COMPLETED":
        order_line = (
            session.execute(
                sa.select(models.order_lines).where(
                    models.order_lines.c.id == task["order_line_id"]
                )
            )
            .mappings()
            .one()
        )
        _record_snapshot_inventory_movements(
            session,
            order_line_id=order_line["id"],
            product_name=order_line["product_name"],
            movement_type="RESERVATION_RELEASE",
            sign=1,
            reason=f"Libera reserva por tarea {task_id}",
            source_type="production_task",
            source_id=task_id,
            created_at=now,
        )
        consumption_movements = _record_snapshot_inventory_movements(
            session,
            order_line_id=order_line["id"],
            product_name=order_line["product_name"],
            movement_type="SALE_CONSUMPTION",
            sign=-1,
            reason=f"Consumo por tarea {task_id}",
            source_type="production_task",
            source_id=task_id,
            created_at=now,
        )
    else:
        consumption_movements = []

    order = (
        session.execute(sa.select(models.orders).where(models.orders.c.id == task["order_id"]))
        .mappings()
        .one()
    )
    current_order_state = OrderState(str(order["status"]))
    next_order_state: OrderState | None = None
    if target == "IN_PROGRESS" and current_order_state == OrderState.ACCEPTED:
        OrderStateMachine.transition(current_order_state, OrderState.SENT_TO_PRODUCTION)
        OrderStateMachine.transition(OrderState.SENT_TO_PRODUCTION, OrderState.IN_PRODUCTION)
        next_order_state = OrderState.IN_PRODUCTION
    elif target == "COMPLETED":
        unfinished = session.execute(
            sa.select(sa.func.count())
            .select_from(models.production_tasks)
            .where(
                models.production_tasks.c.order_id == task["order_id"],
                models.production_tasks.c.status != "COMPLETED",
            )
        ).scalar_one()
        if int(unfinished) == 0 and current_order_state == OrderState.IN_PRODUCTION:
            OrderStateMachine.transition(current_order_state, OrderState.READY)
            next_order_state = OrderState.READY
    if next_order_state is not None:
        session.execute(
            models.orders.update()
            .where(
                models.orders.c.id == task["order_id"],
                models.orders.c.status == current_order_state.value,
            )
            .values(status=next_order_state.value)
        )
        session.execute(
            models.order_events.insert().values(
                id=_id(),
                order_id=task["order_id"],
                event_type=next_order_state.value,
                payload={"source": "kds_task", "task_id": task_id},
                created_at=now,
            )
        )
    _audit(
        session,
        action="production_task.transitioned",
        entity_type="production_task",
        entity_id=task_id,
        payload={
            "from": current,
            "to": target,
            "inventory_consumptions": len(consumption_movements),
            **({"actor_kind": "device", "device_id": actor_device_id} if actor_device_id else {}),
        },
        branch_id=task["branch_id"],
        organization_id=task["organization_id"],
        actor_user_id=actor_user_id,
    )
    session.commit()
    updated = (
        session.execute(
            sa.select(models.production_tasks).where(models.production_tasks.c.id == task_id)
        )
        .mappings()
        .one()
    )
    return dict(updated)


def _cash_summary_for_shift(session: Session, shift: dict[str, Any]) -> dict[str, int]:
    sales_total = 0
    closed_order_ids: set[str] = set()
    payment_total = 0
    confirmed_payment_count = 0
    for payment in session.execute(
        sa.select(models.payments).where(
            models.payments.c.cash_shift_id == shift["id"], models.payments.c.status == "CONFIRMED"
        )
    ).mappings():
        payment_total += int(payment["amount_cents"])
        sales_total += int(payment["amount_cents"])
        confirmed_payment_count += 1
        closed_order_ids.add(str(payment["order_id"]))
    ledger = calculate_expected_cash(session, str(shift["id"]))
    return {
        "sales_total_cents": sales_total,
        "payment_total_cents": payment_total,
        "cash_payment_cents": ledger["cash_payment_cents"],
        "opening_cash_cents": ledger["opening_cash_cents"],
        "expected_cash_cents": ledger["expected_cash_cents"],
        "deposit_cents": ledger["deposit_cents"],
        "withdrawal_cents": ledger["withdrawal_cents"],
        "excluded_movement_count": ledger.get("excluded_movement_count", 0),
        "confirmed_payment_count": confirmed_payment_count,
        "closed_order_count": len(closed_order_ids),
    }


class ReportingProjectionService:
    """Read-only PCO-004 sales projection. Python owns every financial aggregate."""

    _metrics = ("gross", "net", "tax", "discount", "courtesy")
    _services = {"dine-in", "takeout", "delivery"}

    def _pco007_period(
        self, raw: dict[str, Any], permission: str
    ) -> tuple[datetime, datetime, str | None, int]:
        start, end = raw.get("from_utc"), raw.get("to_utc")
        if (
            not isinstance(start, datetime)
            or not isinstance(end, datetime)
            or start.tzinfo is None
            or end.tzinfo is None
            or start >= end
        ):
            raise BusinessError("report_period_invalid", "A UTC semi-open period is required")
        limit = raw.get("limit", 50)
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise BusinessError("report_limit_invalid", "Report limit must be between 1 and 100")
        requested_branch = raw.get("branch_id")
        if requested_branch is None and not actor_has_organization_authority(
            self.session, self.actor_user_id
        ):
            raise AuthorizationError(
                "report_branch_required", "A branch is required for this actor"
            )
        branch_id = authorize_branch_scope(
            self.session, self.actor_user_id, permission, requested_branch
        )
        return start.astimezone(UTC), end.astimezone(UTC), branch_id, limit

    def _pco007_cursor(
        self, report: str, raw: dict[str, Any], key: str | None = None
    ) -> tuple[str, str | None]:
        digest = hashlib.sha256(
            json.dumps(
                {
                    "report": report,
                    "from": _sanitize_for_json(raw["from_utc"]),
                    "to": _sanitize_for_json(raw["to_utc"]),
                    "branch": raw.get("branch_id"),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        cursor = raw.get("cursor")
        if not cursor:
            return digest, None
        try:
            decoded = json.loads(urlsafe_b64decode(str(cursor).encode()).decode())
        except (ValueError, BinasciiError) as exc:
            raise BusinessError("report_cursor_invalid", "Report cursor is invalid") from exc
        if decoded.get("hash") != digest or not isinstance(decoded.get("key"), str):
            raise BusinessError("report_cursor_invalid", "Report cursor does not match filters")
        return digest, decoded["key"]

    @staticmethod
    def _pco007_next_cursor(digest: str, key: str | None) -> str | None:
        if key is None:
            return None
        return urlsafe_b64encode(
            json.dumps({"hash": digest, "key": key}, separators=(",", ":")).encode()
        ).decode()

    @_pco007_observed("pco007.report.ingredient_sales", lambda self, raw: raw.get("branch_id"))
    def ingredient_sales(self, raw: dict[str, Any]) -> dict[str, Any]:
        started_at = _now()
        start, end, branch_id, limit = self._pco007_period(raw, "reports.ingredient_sales.read")
        raw = {**raw, "from_utc": start, "to_utc": end, "branch_id": branch_id}
        digest, cursor_key = self._pco007_cursor("ingredient_sales", raw)
        snapshots = models.sales_operation_snapshots.outerjoin(
            models.sales_operation_line_snapshots,
            models.sales_operation_line_snapshots.c.sales_operation_snapshot_id
            == models.sales_operation_snapshots.c.id,
        ).outerjoin(
            models.order_line_consumption_snapshots,
            models.order_line_consumption_snapshots.c.order_line_id
            == models.sales_operation_line_snapshots.c.order_line_id,
        )
        query = (
            sa.select(
                models.sales_operation_snapshots.c.id.label("operation_id"),
                models.sales_operation_line_snapshots.c.quantity,
                models.order_line_consumption_snapshots.c.recipe_id,
                models.order_line_consumption_snapshots.c.recipe_version,
                models.order_line_consumption_snapshots.c.components,
            )
            .select_from(snapshots)
            .where(
                models.sales_operation_snapshots.c.organization_id == ORGANIZATION_ID,
                models.sales_operation_snapshots.c.confirmed_at >= start,
                models.sales_operation_snapshots.c.confirmed_at < end,
            )
        )
        if branch_id:
            query = query.where(models.sales_operation_snapshots.c.branch_id == branch_id)
        operations: dict[str, list[dict[str, Any]]] = {}
        for row in self.session.execute(query).mappings():
            operations.setdefault(str(row["operation_id"]), []).append(dict(row))
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        incomplete_operations: set[str] = set()

        for operation_id, rows in operations.items():
            validated: list[tuple[dict[str, Any], dict[str, Any], Decimal]] = []
            for row in rows:
                components = row["components"]
                if not isinstance(components, list) or not components:
                    incomplete_operations.add(operation_id)
                    break
                for component in components:
                    try:
                        item_id, unit_id = str(component["item_id"]), str(component["unit_id"])
                        amount = Decimal(str(component["gross_quantity"]))
                        if not item_id or not unit_id or amount <= 0:
                            raise ValueError
                    except (KeyError, ValueError, InvalidOperation):
                        incomplete_operations.add(operation_id)
                        break
                    validated.append((row, component, amount))
                if operation_id in incomplete_operations:
                    break
            if operation_id in incomplete_operations:
                continue
            for row, component, amount in validated:
                try:
                    item_id, unit_id = str(component["item_id"]), str(component["unit_id"])
                except (KeyError, ValueError, InvalidOperation):
                    continue
                entry = groups.setdefault(
                    (item_id, unit_id),
                    {
                        "item_id": item_id,
                        "unit_id": unit_id,
                        "item_name": component.get("item_name"),
                        "unit_code": component.get("unit_code"),
                        "quantity": Decimal("0"),
                        "known_operation_count": 0,
                        "recipe_sources": [],
                    },
                )
                entry["quantity"] += amount
                entry.setdefault("_operations", set()).add(operation_id)
                source = {"recipe_id": row["recipe_id"], "recipe_version": row["recipe_version"]}
                if source not in entry["recipe_sources"]:
                    entry["recipe_sources"].append(source)
        for correction_id, components, incomplete in self._ingredient_correction_deltas(
            start, end, branch_id
        ):
            if incomplete:
                incomplete_operations.add(correction_id)
                continue
            for component, amount in components:
                item_id, unit_id = str(component["item_id"]), str(component["unit_id"])
                entry = groups.setdefault(
                    (item_id, unit_id),
                    {
                        "item_id": item_id,
                        "unit_id": unit_id,
                        "item_name": component.get("item_name"),
                        "unit_code": component.get("unit_code"),
                        "quantity": Decimal("0"),
                        "known_operation_count": 0,
                        "recipe_sources": [],
                    },
                )
                entry["quantity"] += amount
                entry.setdefault("_operations", set()).add(correction_id)
                entry["recipe_sources"].append({"correction_id": correction_id, "kind": "delta"})
        all_items = [
            {
                **{key: value for key, value in entry.items() if key != "_operations"},
                "quantity": format(entry["quantity"], "f"),
                "known_operation_count": len(entry["_operations"]),
            }
            for _, entry in sorted(groups.items())
        ]
        if cursor_key:
            all_items = [
                item for item in all_items if f"{item['item_id']}|{item['unit_id']}" > cursor_key
            ]
        page = all_items[:limit]
        next_key = (
            f"{page[-1]['item_id']}|{page[-1]['unit_id']}"
            if len(all_items) > limit and page
            else None
        )
        result = {
            "items": page,
            "incomplete_operation_count": len(incomplete_operations),
            "next_cursor": self._pco007_next_cursor(digest, next_key),
        }
        _record_pco007_metric(
            "pco007.report.ingredient_sales",
            result="success",
            branch_id=branch_id,
            duration_ms=int((_now() - started_at).total_seconds() * 1000),
            item_count=len(page),
            incomplete_count=len(incomplete_operations),
        )
        return result

    def _ingredient_correction_deltas(
        self, start: datetime, end: datetime, branch_id: str | None
    ) -> list[tuple[str, list[tuple[dict[str, Any], Decimal]], bool]]:
        query = sa.select(models.order_corrections).where(
            models.order_corrections.c.organization_id == ORGANIZATION_ID,
            models.order_corrections.c.status == "APPLIED",
            models.order_corrections.c.applied_at >= start,
            models.order_corrections.c.applied_at < end,
        )
        if branch_id:
            query = query.where(models.order_corrections.c.branch_id == branch_id)
        result = []
        for correction in self.session.execute(query).mappings():
            original = (
                self.session.execute(
                    sa.select(
                        models.sales_operation_line_snapshots.c.order_line_id,
                        models.order_line_consumption_snapshots.c.components,
                        models.order_lines.c.quantity.label("original_quantity"),
                    )
                    .select_from(
                        models.sales_operation_line_snapshots.join(
                            models.sales_operation_snapshots,
                            models.sales_operation_snapshots.c.id
                            == models.sales_operation_line_snapshots.c.sales_operation_snapshot_id,
                        )
                        .outerjoin(
                            models.order_line_consumption_snapshots,
                            models.order_line_consumption_snapshots.c.order_line_id
                            == models.sales_operation_line_snapshots.c.order_line_id,
                        )
                        .outerjoin(
                            models.order_lines,
                            models.order_lines.c.id
                            == models.sales_operation_line_snapshots.c.order_line_id,
                        )
                    )
                    .where(models.sales_operation_snapshots.c.order_id == correction["order_id"])
                )
                .mappings()
                .all()
            )
            lines = [
                dict(row)
                for row in self.session.execute(
                    sa.select(models.order_correction_lines).where(
                        models.order_correction_lines.c.correction_id == correction["id"]
                    )
                ).mappings()
            ]
            desired = {
                str(line["source_line_id"]): Decimal(str(line["quantity"]))
                for line in lines
                if line["classification"] == "RETAINED"
            }
            deltas: list[tuple[dict[str, Any], Decimal]] = []
            incomplete = False
            for row in original:
                components = row["components"]
                if (
                    not isinstance(components, list)
                    or not components
                    or not row["original_quantity"]
                ):
                    incomplete = True
                    break
                factor = (
                    desired.get(str(row["order_line_id"]), Decimal("0"))
                    / Decimal(str(row["original_quantity"]))
                    - 1
                )
                for component in components:
                    try:
                        amount = _quantity(Decimal(str(component["gross_quantity"])) * factor)
                        if not str(component["item_id"]) or not str(component["unit_id"]):
                            raise ValueError
                    except (KeyError, ValueError, InvalidOperation):
                        incomplete = True
                        break
                    if amount:
                        deltas.append((component, amount))
                if incomplete:
                    break
            for line in lines:
                if line["classification"] != "ADDITION":
                    continue
                snapshot = self.session.execute(
                    sa.select(models.order_line_consumption_snapshots.c.components).where(
                        models.order_line_consumption_snapshots.c.order_line_id
                        == line["operational_order_line_id"]
                    )
                ).scalar_one_or_none()
                if not isinstance(snapshot, list):
                    incomplete = True
                    break
                for component in snapshot:
                    try:
                        amount = _quantity(Decimal(str(component["gross_quantity"])))
                        if (
                            amount <= 0
                            or not str(component["item_id"])
                            or not str(component["unit_id"])
                        ):
                            raise ValueError
                    except (KeyError, ValueError, InvalidOperation):
                        incomplete = True
                        break
                    if amount:
                        deltas.append((component, amount))
            result.append((str(correction["id"]), deltas, incomplete))
        return result

    @_pco007_observed("pco007.report.expenses", lambda self, raw: raw.get("branch_id"))
    def expenses(self, raw: dict[str, Any]) -> dict[str, Any]:
        started_at = _now()
        start, end, branch_id, limit = self._pco007_period(raw, "reports.expenses.read")
        raw = {**raw, "from_utc": start, "to_utc": end, "branch_id": branch_id}
        digest, cursor_key = self._pco007_cursor("expenses", raw)
        query = sa.select(models.purchase_documents).where(
            models.purchase_documents.c.organization_id == ORGANIZATION_ID,
            sa.or_(
                sa.and_(
                    models.purchase_documents.c.confirmed_at >= start,
                    models.purchase_documents.c.confirmed_at < end,
                ),
                sa.and_(
                    models.purchase_documents.c.cancelled_at >= start,
                    models.purchase_documents.c.cancelled_at < end,
                ),
            ),
        )
        if branch_id:
            query = query.where(models.purchase_documents.c.branch_id == branch_id)

        def cents(amount: Any) -> int:
            return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        items: list[dict[str, Any]] = []
        for row in self.session.execute(
            query.order_by(models.purchase_documents.c.confirmed_at, models.purchase_documents.c.id)
        ).mappings():
            if row["confirmed_at"] and start <= _utc_cursor_datetime(row["confirmed_at"]) < end:
                items.append(
                    {
                        "id": f"purchase:{row['id']}",
                        "source": "purchase",
                        "branch_id": row["branch_id"],
                        "occurred_at": row["confirmed_at"],
                        "subtotal_cents": cents(row["subtotal"]),
                        "discount_cents": cents(row["discount_total"]),
                        "tax_cents": cents(row["tax_total"]),
                        "total_cents": cents(row["total"]),
                        "linked_source_id": None,
                    }
                )
            if row["cancelled_at"] and start <= _utc_cursor_datetime(row["cancelled_at"]) < end:
                items.append(
                    {
                        "id": f"purchase-cancellation:{row['id']}",
                        "source": "purchase_cancellation",
                        "branch_id": row["branch_id"],
                        "occurred_at": row["cancelled_at"],
                        "subtotal_cents": -cents(row["subtotal"]),
                        "discount_cents": -cents(row["discount_total"]),
                        "tax_cents": -cents(row["tax_total"]),
                        "total_cents": -cents(row["total"]),
                        "linked_source_id": row["id"],
                    }
                )
        movements = sa.select(models.cash_movements).where(
            models.cash_movements.c.organization_id == ORGANIZATION_ID,
            models.cash_movements.c.status == "confirmed",
            models.cash_movements.c.created_at >= start,
            models.cash_movements.c.created_at < end,
        )
        if branch_id:
            movements = movements.where(models.cash_movements.c.branch_id == branch_id)
        unknown_tax = 0
        for movement in self.session.execute(movements).mappings():
            source_type = str(movement["source_type"] or "").lower()
            linked = movement["reversal_of_id"] or movement["compensates_movement_id"]
            if source_type in {"purchase", "purchase_cancellation", "order_correction"}:
                continue
            if movement["movement_type"] == "deposit" and not linked:
                continue
            if movement["movement_type"] == "withdrawal" or linked:
                signed = int(movement["amount_cents"]) * (-1 if linked else 1)
                items.append(
                    {
                        "id": f"cash:{movement['id']}",
                        "source": "cash_movement",
                        "branch_id": movement["branch_id"],
                        "occurred_at": movement["created_at"],
                        "subtotal_cents": None,
                        "discount_cents": None,
                        "tax_cents": None,
                        "total_cents": signed,
                        "linked_source_id": linked,
                    }
                )
                unknown_tax += 1
        items.sort(key=lambda item: (item["occurred_at"], item["id"]))
        if cursor_key:
            items = [
                item
                for item in items
                if f"{_sanitize_for_json(item['occurred_at'])}|{item['id']}" > cursor_key
            ]
        page = items[:limit]
        next_key = (
            f"{_sanitize_for_json(page[-1]['occurred_at'])}|{page[-1]['id']}"
            if len(items) > limit and page
            else None
        )
        result = {
            "items": page,
            "unknown_tax_source_count": unknown_tax,
            "next_cursor": self._pco007_next_cursor(digest, next_key),
        }
        _record_pco007_metric(
            "pco007.report.expenses",
            result="success",
            branch_id=branch_id,
            duration_ms=int((_now() - started_at).total_seconds() * 1000),
            item_count=len(page),
            unknown_tax_count=unknown_tax,
        )
        return result

    def __init__(self, session: Session, actor_user_id: str) -> None:
        self.session = session
        self.actor_user_id = actor_user_id

    def _filters(self, raw: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        from_utc, to_utc = raw.get("from_utc"), raw.get("to_utc")
        if not isinstance(from_utc, datetime) or not isinstance(to_utc, datetime):
            raise BusinessError("sales_monitor_period_invalid", "UTC period is required")
        if from_utc.tzinfo is None or to_utc.tzinfo is None or from_utc >= to_utc:
            raise BusinessError("sales_monitor_period_invalid", "UTC period is invalid")
        service_type = raw.get("service_type")
        if service_type is not None and service_type not in self._services:
            raise BusinessError("sales_monitor_filter_invalid", "Service type is invalid")
        branch_id = raw.get("branch_id")
        scoped_branch = authorize_branch_scope(
            self.session, self.actor_user_id, "reports.sales.read", branch_id
        )
        applied = {
            "from_utc": from_utc,
            "to_utc": to_utc,
            "branch_id": scoped_branch,
            "register_id": raw.get("register_id"),
            "cash_shift_id": raw.get("cash_shift_id"),
            "family_id": raw.get("family_id"),
            "service_type": service_type,
        }
        return applied, scoped_branch

    def _rows(self, applied: dict[str, Any]) -> list[dict[str, Any]]:
        query = sa.select(models.sales_operation_snapshots).where(
            models.sales_operation_snapshots.c.organization_id == ORGANIZATION_ID,
            models.sales_operation_snapshots.c.confirmed_at >= applied["from_utc"],
            models.sales_operation_snapshots.c.confirmed_at < applied["to_utc"],
        )
        if applied["branch_id"]:
            query = query.where(
                models.sales_operation_snapshots.c.branch_id == applied["branch_id"]
            )
        for field, column in (
            ("register_id", models.sales_operation_snapshots.c.register_code_snapshot),
            ("cash_shift_id", models.sales_operation_snapshots.c.cash_shift_id),
            ("service_type", models.sales_operation_snapshots.c.service_type_snapshot),
        ):
            if applied[field]:
                query = query.where(column == applied[field])
        rows = [dict(row) for row in self.session.execute(query).mappings()]
        if applied["family_id"]:
            permitted = {
                str(row[0])
                for row in self.session.execute(
                    sa.select(
                        models.sales_operation_line_snapshots.c.sales_operation_snapshot_id
                    ).where(
                        models.sales_operation_line_snapshots.c.family_id_snapshot
                        == applied["family_id"]
                    )
                ).all()
            }
            rows = [row for row in rows if str(row["id"]) in permitted]
        return rows

    @classmethod
    def _indicator(cls, rows: list[dict[str, Any]], metric: str) -> dict[str, int]:
        column = f"{metric}_cents"
        return {
            "known_cents": sum(int(row[column]) for row in rows if row.get(column) is not None),
            "unknown_operation_count": len(
                {str(row["id"]) for row in rows if row.get(column) is None}
            ),
        }

    @classmethod
    def _line_indicator(cls, lines: list[dict[str, Any]], metric: str) -> dict[str, int]:
        """Aggregate snapshot lines and count missing values once per operation."""
        column = f"{metric}_cents"
        return {
            "known_cents": sum(int(line[column]) for line in lines if line.get(column) is not None),
            "unknown_operation_count": len(
                {
                    str(line["sales_operation_snapshot_id"])
                    for line in lines
                    if line.get(column) is None
                }
            ),
        }

    def _lines(self, rows: list[dict[str, Any]], family_id: str | None) -> list[dict[str, Any]]:
        query = sa.select(models.sales_operation_line_snapshots).where(
            models.sales_operation_line_snapshots.c.sales_operation_snapshot_id.in_(
                [row["id"] for row in rows] or ["__none__"]
            )
        )
        if family_id:
            query = query.where(
                models.sales_operation_line_snapshots.c.family_id_snapshot == family_id
            )
        return [dict(row) for row in self.session.execute(query).mappings()]

    def _corrections(self, applied: dict[str, Any]) -> list[dict[str, Any]]:
        """Project compensating corrections separately from immutable sale snapshots.

        A correction is an adjustment made *now*, while a sales snapshot remains
        the evidence of the original confirmed sale.  It must therefore never
        be folded into the historical sale rows used by gross/net metrics.
        """
        if applied["family_id"] is not None or applied["service_type"] is not None:
            # Corrections are not attributed to a current catalog family/service;
            # doing so would fabricate historical reporting dimensions.
            return []
        query = (
            sa.select(
                models.order_corrections.c.id,
                models.order_corrections.c.order_id,
                models.order_corrections.c.folio,
                models.order_corrections.c.branch_id,
                models.order_corrections.c.applied_at,
                models.order_corrections.c.settlement_delta_cents,
                models.order_corrections.c.currency,
                models.order_payment_adjustments.c.id.label("payment_adjustment_id"),
                models.order_payment_adjustments.c.adjustment_type,
                models.order_payment_adjustments.c.method,
                models.order_payment_adjustments.c.amount_cents,
                models.order_payment_adjustments.c.cash_shift_id,
                models.cash_shifts.c.register_code.label("register_id"),
            )
            .select_from(
                models.order_corrections.outerjoin(
                    models.order_payment_adjustments,
                    models.order_payment_adjustments.c.correction_id
                    == models.order_corrections.c.id,
                ).outerjoin(
                    models.cash_shifts,
                    models.cash_shifts.c.id == models.order_payment_adjustments.c.cash_shift_id,
                )
            )
            .where(
                models.order_corrections.c.organization_id == ORGANIZATION_ID,
                models.order_corrections.c.applied_at >= applied["from_utc"],
                models.order_corrections.c.applied_at < applied["to_utc"],
            )
        )
        if applied["branch_id"]:
            query = query.where(models.order_corrections.c.branch_id == applied["branch_id"])
        if applied["cash_shift_id"]:
            query = query.where(
                models.order_payment_adjustments.c.cash_shift_id == applied["cash_shift_id"]
            )
        if applied["register_id"]:
            query = query.where(models.cash_shifts.c.register_code == applied["register_id"])
        return [dict(row) for row in self.session.execute(query).mappings()]

    @staticmethod
    def _correction_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "count": len(rows),
            "charge_cents": sum(
                int(row["amount_cents"] or 0) for row in rows if row["adjustment_type"] == "CHARGE"
            ),
            "refund_cents": sum(
                int(row["amount_cents"] or 0) for row in rows if row["adjustment_type"] == "REFUND"
            ),
            "net_delta_cents": sum(int(row["settlement_delta_cents"]) for row in rows),
            "cash_adjustment_count": sum(1 for row in rows if row["method"] == "cash"),
        }

    @staticmethod
    def _correction_drill_item(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "correction_id": row["id"],
            "order_id": row["order_id"],
            "folio": row["folio"],
            "branch_id": row["branch_id"],
            "applied_at": row["applied_at"],
            "settlement_delta_cents": row["settlement_delta_cents"],
            "currency": row["currency"],
            "payment_adjustment_id": row["payment_adjustment_id"],
            "adjustment_type": row["adjustment_type"],
            "method": row["method"],
            "amount_cents": row["amount_cents"],
            "cash_shift_id": row["cash_shift_id"],
            "register_id": row["register_id"],
        }

    def summary(self, raw: dict[str, Any]) -> dict[str, Any]:
        try:
            applied, _ = self._filters(raw)
            rows = self._rows(applied)
            lines = self._lines(rows, applied["family_id"])
            corrections = self._corrections(applied)
            uses_line_metrics = applied["family_id"] is not None
            summary: dict[str, Any] = {
                metric: (
                    self._line_indicator(lines, metric)
                    if uses_line_metrics
                    else self._indicator(rows, metric)
                )
                for metric in self._metrics
            }
            summary.update(
                {
                    "order_count": len({str(row["order_id"]) for row in rows}),
                    "line_count": len(lines),
                    "item_quantity": sum(int(line["quantity"]) for line in lines),
                    "legacy_backfilled_line_count": sum(
                        1
                        for line in lines
                        if line["family_snapshot_source"] == "legacy_catalog_backfill"
                    ),
                }
            )
            by_snapshot = {str(row["id"]): row for row in rows}

            def breakdown(
                identifier: str,
                label: str,
                selected_rows: list[dict[str, Any]],
                selected_lines: list[dict[str, Any]],
                *,
                use_line_metrics: bool,
            ) -> dict[str, Any]:
                breakdown_result: dict[str, Any] = {"id": identifier, "label": label}
                for metric in self._metrics:
                    breakdown_result[metric] = (
                        self._line_indicator(selected_lines, metric)
                        if use_line_metrics
                        else self._indicator(selected_rows, metric)
                    )
                breakdown_result.update(
                    {
                        "order_count": len({str(row["order_id"]) for row in selected_rows}),
                        "line_count": len(selected_lines),
                        "item_quantity": sum(int(line["quantity"]) for line in selected_lines),
                    }
                )
                return breakdown_result

            family_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for line in lines:
                family_groups.setdefault(
                    (str(line["family_id_snapshot"]), str(line["family_name_snapshot"])), []
                ).append(line)
            families = [
                breakdown(
                    identifier,
                    label,
                    [
                        by_snapshot[item_id]
                        for item_id in {str(line["sales_operation_snapshot_id"]) for line in group}
                    ],
                    group,
                    use_line_metrics=True,
                )
                for (identifier, label), group in family_groups.items()
            ]
            service_groups: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                service_groups.setdefault(str(row["service_type_snapshot"]), []).append(row)
            services = [
                breakdown(
                    service,
                    service,
                    group,
                    [
                        line
                        for line in lines
                        if str(line["sales_operation_snapshot_id"])
                        in {str(row["id"]) for row in group}
                    ],
                    use_line_metrics=uses_line_metrics,
                )
                for service, group in service_groups.items()
            ]
            result = {
                "applied_filters": applied,
                "summary": summary,
                "corrections": self._correction_summary(corrections),
                "breakdowns": {"families": families, "services": services},
                "facets": {
                    "cash_shifts": [
                        {"id": shift_id, "label": label}
                        for shift_id, label in dict.fromkeys(
                            (str(row["cash_shift_id"]), str(row["register_code_snapshot"]))
                            for row in rows
                        )
                    ],
                    "families": [
                        {"id": identifier, "label": label} for identifier, label in family_groups
                    ],
                    "service_types": [
                        {"id": service, "label": service} for service in service_groups
                    ],
                },
                "data_quality": {
                    "incomplete_operation_count": sum(
                        1 for row in rows if row["quality_status"] == "incomplete"
                    )
                },
            }
            _record_pco004_metric(
                "sales_monitor_request_total", result="success", branch_id=applied["branch_id"]
            )
            _record_pco004_metric(
                "sales_monitor_incomplete_operations",
                result="success",
                branch_id=applied["branch_id"],
                value=result["data_quality"]["incomplete_operation_count"],
            )
            return result
        except BusinessError as exc:
            _record_pco004_metric(
                "sales_monitor_request_total",
                result="error",
                branch_id=raw.get("branch_id") if isinstance(raw.get("branch_id"), str) else None,
                error_code=exc.code,
            )
            raise

    def drill_down(self, raw: dict[str, Any]) -> dict[str, Any]:
        branch_id = raw.get("branch_id") if isinstance(raw.get("branch_id"), str) else None
        try:
            metric = raw.get("metric")
            limit = raw.get("limit", 50)
            if metric not in self._metrics or not isinstance(limit, int) or not 1 <= limit <= 100:
                raise BusinessError(
                    "sales_monitor_filter_invalid", "Drill-down metric or limit is invalid"
                )
            applied, _ = self._filters(raw)
            branch_id = applied["branch_id"]
            corrections = self._corrections(applied)
            rows = sorted(
                self._rows(applied),
                key=lambda row: (_utc_cursor_datetime(row["confirmed_at"]), str(row["payment_id"])),
                reverse=True,
            )
            lines = self._lines(rows, applied["family_id"])
            lines_by_snapshot: dict[str, list[dict[str, Any]]] = {}
            for line in lines:
                lines_by_snapshot.setdefault(str(line["sales_operation_snapshot_id"]), []).append(
                    line
                )
            cursor = raw.get("cursor")
            if cursor:
                try:
                    cursor_at, cursor_payment = str(cursor).split("|", 1)
                    cursor_timestamp = _decode_sales_monitor_cursor_timestamp(cursor_at)
                    UUID(cursor_payment)
                except (BusinessError, ValueError) as exc:
                    raise BusinessError(
                        "sales_monitor_cursor_invalid", "Cursor is invalid"
                    ) from exc
                cursor_key = (cursor_timestamp, cursor_payment)
                rows = [
                    row
                    for row in rows
                    if (_utc_cursor_datetime(row["confirmed_at"]), str(row["payment_id"]))
                    < cursor_key
                ]
            page = rows[:limit]
            uses_line_metrics = applied["family_id"] is not None
            items = [
                {
                    "payment_id": row["payment_id"],
                    "order_id": row["order_id"],
                    "folio": row["folio_snapshot"],
                    "branch_id": row["branch_id"],
                    "cash_shift_id": row["cash_shift_id"],
                    "register_id": row["register_code_snapshot"],
                    "service_type": row["service_type_snapshot"],
                    "confirmed_at": row["confirmed_at"],
                    "quality_status": row["quality_status"],
                    "order_count": 1,
                    "line_count": len(lines_by_snapshot.get(str(row["id"]), [])),
                    "item_quantity": sum(
                        int(line["quantity"]) for line in lines_by_snapshot.get(str(row["id"]), [])
                    ),
                    **{
                        name: (
                            self._line_indicator(lines_by_snapshot.get(str(row["id"]), []), name)
                            if uses_line_metrics
                            else self._indicator([row], name)
                        )
                        for name in self._metrics
                    },
                }
                for row in page
            ]
            next_cursor = None
            if len(page) == limit:
                next_cursor = (
                    f"{_utc_cursor_timestamp(page[-1]['confirmed_at'])}|{page[-1]['payment_id']}"
                )
            result = {
                "applied_filters": applied,
                "metric": metric,
                "items": items,
                "next_cursor": next_cursor,
                # Corrections are a separately scoped append-only operation
                # stream.  They are bounded with the same public drill-down
                # limit but never share the sales-snapshot cursor.
                "corrections": [
                    self._correction_drill_item(row)
                    for row in sorted(
                        corrections,
                        key=lambda row: (_utc_cursor_datetime(row["applied_at"]), str(row["id"])),
                        reverse=True,
                    )[:limit]
                ],
            }
            _record_pco004_metric(
                "sales_monitor_request_total", result="success", branch_id=branch_id
            )
            return result
        except BusinessError as exc:
            _record_pco004_metric(
                "sales_monitor_request_total",
                result="error",
                branch_id=branch_id,
                error_code=exc.code,
            )
            raise


def _utc_cursor_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise BusinessError("sales_monitor_cursor_invalid", "Snapshot timestamp is invalid")
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _utc_cursor_timestamp(value: Any) -> str:
    return _utc_cursor_datetime(value).isoformat().replace("+00:00", "Z")


def _decode_sales_monitor_cursor_timestamp(value: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BusinessError("sales_monitor_cursor_invalid", "Cursor is invalid") from exc
    if timestamp.tzinfo is None:
        raise BusinessError("sales_monitor_cursor_invalid", "Cursor is invalid")
    return timestamp.astimezone(UTC)


def _create_print_jobs(
    session: Session,
    order: dict[str, Any],
    payment: dict[str, Any],
    created_at: datetime,
) -> list[dict[str, Any]]:
    lines = [
        dict(row)
        for row in session.execute(
            sa.select(models.order_lines).where(models.order_lines.c.order_id == order["id"])
        ).mappings()
    ]
    common_payload = {
        "folio": order["folio"],
        "total_cents": order["total_cents"],
        "payment_id": payment["id"],
        "lines": [
            {
                "product_name": line["product_name"],
                "quantity": line["quantity"],
                "line_total_cents": line["line_total_cents"],
                "station": line["station"],
                "selected_modifiers": line["selected_modifiers"],
            }
            for line in lines
        ],
    }
    jobs = [
        {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": BRANCH_ID,
            "order_id": order["id"],
            "job_type": "ticket",
            "target": "POS-CAJA-01",
            "status": "QUEUED",
            "payload": {**common_payload, "copy": "customer"},
            "attempts": 1,
            "last_error": None,
            "created_at": created_at,
            "printed_at": None,
        },
        {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": BRANCH_ID,
            "order_id": order["id"],
            "job_type": "kitchen",
            "target": "KDS-COCINA",
            "status": "QUEUED",
            "payload": {**common_payload, "copy": "kitchen"},
            "attempts": 1,
            "last_error": None,
            "created_at": created_at,
            "printed_at": None,
        },
    ]
    session.execute(models.print_jobs.insert(), jobs)
    attempts = []
    for job in jobs:
        request_hash = hashlib.sha256(
            json.dumps(
                {"branch_id": job["branch_id"], "job_id": job["id"], "operation": "print.initial"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        attempts.append(
            {
                "id": _id(),
                "print_job_id": job["id"],
                "organization_id": job["organization_id"],
                "branch_id": job["branch_id"],
                "idempotency_key": f"initial:{job['id']}",
                "request_hash": request_hash,
                "status": "QUEUED",
                "created_at": created_at,
            }
        )
    session.execute(models.print_attempts.insert(), attempts)
    for job in jobs:
        _audit(
            session,
            action="print_job.created",
            entity_type="print_job",
            entity_id=job["id"],
            payload={"order_id": order["id"], "job_type": job["job_type"], "target": job["target"]},
        )
    return jobs


def _validate_sync_envelope(envelope: dict[str, Any]) -> None:
    required = [
        "schema_version",
        "command_id",
        "idempotency_key",
        "organization_id",
        "branch_id",
        "source_device_id",
        "command_type",
        "occurred_at",
        "payload",
    ]
    missing = [field for field in required if not envelope.get(field)]
    if missing:
        raise BusinessError("invalid_sync_command", f"Missing fields: {', '.join(missing)}")
    if envelope["schema_version"] != "1.0":
        raise BusinessError("invalid_sync_schema", "Unsupported sync schema version")
    if not isinstance(envelope["payload"], dict):
        raise BusinessError("invalid_sync_payload", "Sync command payload must be an object")
    if len(str(envelope["idempotency_key"])) < 12:
        raise BusinessError("invalid_idempotency_key", "Idempotency key is too short")


def _validate_pco008_sync_envelope(envelope: dict[str, Any]) -> None:
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
        raise BusinessError("invalid_sync_payload", "Cash offline envelope is invalid")
    if (
        not isinstance(envelope["idempotency_key"], str)
        or len(envelope["idempotency_key"]) < 12
        or len(envelope["idempotency_key"]) > 160
    ):
        raise BusinessError("invalid_idempotency_key", "Idempotency key is invalid")
    invalid_envelope = (
        any(
            not _is_pco008_uuid_string(envelope[field])
            for field in (
                "command_id",
                "organization_id",
                "branch_id",
                "source_device_id",
                "actor_user_id",
            )
        )
        or envelope["organization_id"] != ORGANIZATION_ID
        or not _is_pco008_timezone_datetime(envelope["occurred_at"])
        or not _is_pco008_timezone_datetime(envelope["accepted_at"])
        or not isinstance(envelope["offline_grant"], str)
        or len(envelope["offline_grant"]) < 20
    )
    if invalid_envelope:
        raise BusinessError("invalid_sync_payload", "Cash offline envelope is invalid")
    payload = envelope["payload"]
    expected = {
        "register_id",
        "movement_type",
        "concept_id",
        "amount_cents",
        "reference",
        "evidence_refs",
    }
    if not isinstance(payload, dict) or set(payload) != expected:
        raise BusinessError("invalid_sync_payload", "Cash offline payload is invalid")
    invalid_payload = (
        not isinstance(payload["movement_type"], str)
        or payload["movement_type"] not in {"deposit", "withdrawal"}
        or isinstance(payload["amount_cents"], bool)
        or not isinstance(payload["amount_cents"], int)
        or payload["amount_cents"] <= 0
        or any(
            not isinstance(payload[field], str) or not payload[field].strip()
            for field in ("register_id", "concept_id")
        )
        or not _is_pco008_uuid_string(payload["concept_id"])
        or not isinstance(payload["reference"], str)
        or not 1 <= len(payload["reference"].strip()) <= 600
        or not isinstance(payload["evidence_refs"], list)
        or not 1 <= len(payload["evidence_refs"]) <= 10
        or any(
            not isinstance(item, str) or not 1 <= len(item.strip()) <= 600
            for item in payload["evidence_refs"]
        )
    )
    if invalid_payload:
        raise BusinessError("invalid_sync_payload", "Cash offline payload is invalid")


def _is_pco008_uuid_string(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        value,
    ):
        return False
    try:
        UUID(value)
    except (ValueError, AttributeError):
        return False
    return True


def _is_pco008_timezone_datetime(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})",
        value,
    ):
        return False
    try:
        parsed = _parse_datetime(value)
    except BusinessError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _sync_request_hash(envelope: dict[str, Any]) -> str:
    safe = {key: envelope[key] for key in envelope if key != "offline_grant"}
    return hashlib.sha256(
        json.dumps(safe, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _redacted_sync_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload[key] for key in ("register_id", "movement_type", "concept_id", "amount_cents")
    }


def _redact_sync_movement(movement: dict[str, Any]) -> dict[str, Any]:
    # The gateway only needs a stable domain acknowledgement.  Cash reference,
    # evidence, actor and snapshots remain central and never cross back to edge.
    return {key: movement[key] for key in ("id", "status")}


def _validate_pco008_offline_grant(envelope: dict[str, Any]) -> str | None:
    from restaurant_os.offline_grants import verify_offline_grant_v2

    grant = verify_offline_grant_v2(
        str(envelope["offline_grant"]), _offline_grant_keyring(), check_expiry=False
    )
    if not grant or any(
        str(grant.get(key)) != str(envelope[key])
        for key in ("actor_user_id", "organization_id", "branch_id", "source_device_id")
    ):
        return "offline_grant_invalid"
    if grant.get("capabilities") != ["cash.movement.create.v1"]:
        return "offline_grant_invalid"
    occurred_at = _parse_datetime(str(envelope["occurred_at"]))
    accepted_at = _parse_datetime(str(envelope["accepted_at"]))
    issued_at = datetime.fromtimestamp(int(grant["iat"]), UTC)
    expires_at = datetime.fromtimestamp(int(grant["exp"]), UTC)
    if not issued_at <= occurred_at <= expires_at:
        return "offline_grant_expired"
    if not issued_at <= accepted_at <= expires_at:
        return "offline_grant_expired"
    return None


def _offline_grant_signing_material() -> tuple[Any, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    settings = get_settings()
    if not settings.offline_grant_private_key or not settings.offline_grant_key_id:
        raise BusinessError(
            "offline_grant_configuration_invalid",
            "Offline grant signing configuration is unavailable",
        )
    try:
        key = serialization.load_pem_private_key(
            settings.offline_grant_private_key.encode("utf-8"), password=None
        )
    except (TypeError, ValueError) as exc:
        raise BusinessError(
            "offline_grant_configuration_invalid",
            "Offline grant signing configuration is unavailable",
        ) from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise BusinessError(
            "offline_grant_configuration_invalid",
            "Offline grant signing configuration is unavailable",
        )
    return key, settings.offline_grant_key_id


def _offline_grant_keyring() -> dict[str, Any]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    private_key, kid = _offline_grant_signing_material()
    keyring: dict[str, Any] = {kid: private_key.public_key()}
    configured = get_settings().offline_grant_public_keyring
    if configured is None:
        return keyring
    try:
        previous = json.loads(configured)
    except (TypeError, ValueError) as exc:
        raise BusinessError(
            "offline_grant_configuration_invalid",
            "Offline grant verification configuration is unavailable",
        ) from exc
    if not isinstance(previous, dict) or not previous:
        raise BusinessError(
            "offline_grant_configuration_invalid",
            "Offline grant verification configuration is unavailable",
        )
    for previous_kid, encoded_key in previous.items():
        if previous_kid == kid or not isinstance(previous_kid, str) or not previous_kid:
            raise BusinessError(
                "offline_grant_configuration_invalid",
                "Offline grant verification configuration is unavailable",
            )
        try:
            public_key = serialization.load_pem_public_key(encoded_key.encode("utf-8"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise BusinessError(
                "offline_grant_configuration_invalid",
                "Offline grant verification configuration is unavailable",
            ) from exc
        if not isinstance(public_key, Ed25519PublicKey):
            raise BusinessError(
                "offline_grant_configuration_invalid",
                "Offline grant verification configuration is unavailable",
            )
        keyring[previous_kid] = public_key
    return keyring


def issue_offline_cash_grant(
    session: Session,
    *,
    actor_user_id: str,
    organization_id: str,
    branch_id: str,
    source_device_id: str,
) -> dict[str, Any]:
    from restaurant_os.offline_grants import OFFLINE_GRANT_TTL_SECONDS, create_offline_grant_v2

    if organization_id != ORGANIZATION_ID:
        raise AuthorizationError("permission_denied", "Organization scope is invalid")
    actor_id = _actor_user_id(actor_user_id)
    for permission in ("cash.movement.withdraw", "cash.movement.deposit"):
        try:
            authorize_branch_scope(session, actor_id, permission, branch_id)
            break
        except AuthorizationError:
            session.rollback()
    else:
        raise AuthorizationError("permission_denied", "Cash movement permission is required")
    device = (
        session.execute(
            sa.select(models.device_credentials).where(
                models.device_credentials.c.id == source_device_id,
                models.device_credentials.c.organization_id == organization_id,
                models.device_credentials.c.branch_id == branch_id,
                models.device_credentials.c.capability == "gateway.sync",
                models.device_credentials.c.revoked_at.is_(None),
            )
        )
        .mappings()
        .first()
    )
    now_dt = _now()
    expires_at = device["expires_at"] if device else None
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if not device or not expires_at or expires_at <= now_dt:
        raise BusinessError("gateway_device_inactive", "Gateway device is not active")
    private_key, kid = _offline_grant_signing_material()
    now = int(now_dt.timestamp())
    grant = create_offline_grant_v2(
        {
            "actor_user_id": actor_id,
            "organization_id": organization_id,
            "branch_id": branch_id,
            "source_device_id": source_device_id,
            "capabilities": ["cash.movement.create.v1"],
        },
        private_key,
        kid=kid,
        now=now,
    )
    return {
        "offline_grant": grant,
        "expires_at": datetime.fromtimestamp(now + OFFLINE_GRANT_TTL_SECONDS, UTC).isoformat(),
    }


def _store_sync_conflict(session: Session, envelope: dict[str, Any], code: str) -> dict[str, Any]:
    now = _now()
    organization_id = str(envelope["organization_id"])
    branch_id = str(envelope["branch_id"])
    checkpoint = _next_sync_checkpoint(session, organization_id, branch_id)
    command: dict[str, Any] = {
        "id": _id(),
        "organization_id": organization_id,
        "branch_id": branch_id,
        "source_device_id": str(envelope["source_device_id"]),
        "actor_user_id": str(envelope["actor_user_id"]),
        "command_id": str(envelope["command_id"]),
        "idempotency_key": str(envelope["idempotency_key"]),
        "command_type": str(envelope["command_type"]),
        "payload": {},
        "request_hash": _sync_request_hash(envelope),
        "status": "CONFLICT",
        "checkpoint": checkpoint,
        "occurred_at": _parse_datetime(str(envelope["occurred_at"])),
        "received_at": now,
        "confirmed_at": now,
    }
    try:
        session.execute(models.sync_commands.insert().values(**command))
        _audit(
            session,
            "sync_command.conflict",
            "sync_command",
            command["id"],
            {"code": code},
            branch_id,
            organization_id,
            str(envelope["actor_user_id"]),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    _record_pco008_metric(
        result="conflict",
        error_code=code,
        organization_id=organization_id,
        branch_id=branch_id,
        source_device_id=str(envelope["source_device_id"]),
        checkpoint=checkpoint,
        lag_seconds=max(
            0,
            int((now - _parse_datetime(str(envelope["accepted_at"]))).total_seconds()),
        ),
    )
    return {"status": "CONFLICT", "code": code, "checkpoint": checkpoint}


def _sync_conflict_code(session: Session, command_id: str) -> str:
    audit = session.execute(
        sa.select(models.audit_events.c.payload)
        .where(
            models.audit_events.c.entity_type == "sync_command",
            models.audit_events.c.entity_id == command_id,
            models.audit_events.c.action == "sync_command.conflict",
        )
        .order_by(models.audit_events.c.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    code = audit.get("code") if isinstance(audit, dict) else None
    if isinstance(code, str):
        return code
    return "sync_conflict"


def _pco008_fault(_point: str) -> None:
    """Deterministic test seam for transaction-boundary regressions."""


def _lock_sync_branch(session: Session, organization_id: str, branch_id: str) -> None:
    """Serialize same-branch reconciliation before the idempotency lookup on PostgreSQL."""
    if session.get_bind().dialect.name == "sqlite":
        return
    session.execute(
        sa.select(models.branches.c.id)
        .where(
            models.branches.c.id == branch_id,
            models.branches.c.organization_id == organization_id,
        )
        .with_for_update()
    ).scalar_one_or_none()


def _next_sync_checkpoint(session: Session, organization_id: str, branch_id: str) -> int:
    now = _now()
    checkpoint = (
        session.execute(
            sa.select(models.sync_branch_checkpoints)
            .where(
                models.sync_branch_checkpoints.c.organization_id == organization_id,
                models.sync_branch_checkpoints.c.branch_id == branch_id,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if checkpoint is None:
        try:
            with session.begin_nested():
                session.execute(
                    models.sync_branch_checkpoints.insert().values(
                        organization_id=organization_id,
                        branch_id=branch_id,
                        last_checkpoint=1,
                        updated_at=now,
                    )
                )
            return 1
        except IntegrityError:
            checkpoint = (
                session.execute(
                    sa.select(models.sync_branch_checkpoints)
                    .where(
                        models.sync_branch_checkpoints.c.organization_id == organization_id,
                        models.sync_branch_checkpoints.c.branch_id == branch_id,
                    )
                    .with_for_update()
                )
                .mappings()
                .one()
            )
    value = int(checkpoint["last_checkpoint"]) + 1
    session.execute(
        models.sync_branch_checkpoints.update()
        .where(
            models.sync_branch_checkpoints.c.organization_id == organization_id,
            models.sync_branch_checkpoints.c.branch_id == branch_id,
        )
        .values(last_checkpoint=value, updated_at=now)
    )
    return value


def _get_sync_event_for_command(session: Session, command_id: str) -> dict[str, Any]:
    row = (
        session.execute(
            sa.select(models.sync_events).where(models.sync_events.c.sync_command_id == command_id)
        )
        .mappings()
        .one()
    )
    return dict(row)


def _sync_confirmation(
    command: dict[str, Any],
    replayed: bool,
) -> dict[str, Any]:
    return {
        "status": command["status"],
        "checkpoint": command["checkpoint"],
        "replayed": replayed,
    }


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BusinessError("invalid_occurred_at", "occurred_at must be a date-time") from exc


def _get_available_product(
    session: Session, product_id: str, branch_id: str = BRANCH_ID
) -> dict[str, Any] | None:
    price = (
        sa.select(
            models.price_versions.c.product_id,
            models.price_versions.c.price_cents,
            models.price_versions.c.currency,
        )
        .where(models.price_versions.c.valid_to.is_(None))
        .subquery()
    )
    row = (
        session.execute(
            sa.select(
                models.products.c.id,
                models.products.c.name,
                models.products.c.station,
                models.products.c.category_id,
                models.product_categories.c.name.label("family_name"),
                price.c.price_cents,
                price.c.currency,
            )
            .select_from(
                models.products.join(
                    models.product_categories,
                    models.products.c.category_id == models.product_categories.c.id,
                )
                .join(price, models.products.c.id == price.c.product_id)
                .outerjoin(
                    models.branch_product_availability,
                    sa.and_(
                        models.products.c.id == models.branch_product_availability.c.product_id,
                        models.branch_product_availability.c.branch_id == branch_id,
                    ),
                )
            )
            .where(
                sa.or_(
                    models.products.c.id == product_id,
                    models.products.c.sku == product_id,
                    sa.func.lower(models.products.c.name) == product_id.strip().lower(),
                ),
                models.products.c.status == "active",
                sa.func.coalesce(models.branch_product_availability.c.is_available, True).is_(True),
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


def _get_or_create_category(
    session: Session,
    category_name: str,
    created_at: datetime,
    organization_id: str | None = None,
) -> dict[str, Any]:
    org_id = organization_id or ORGANIZATION_ID
    row = (
        session.execute(
            sa.select(models.product_categories).where(
                models.product_categories.c.organization_id == org_id,
                models.product_categories.c.name == category_name,
                models.product_categories.c.status != "archived",
            )
        )
        .mappings()
        .first()
    )
    if row:
        return dict(row)

    category = {
        "id": _id(),
        "organization_id": org_id,
        "name": category_name,
        "display_order": 100,
        "status": "active",
        "created_at": created_at,
        "updated_at": created_at,
    }
    session.execute(models.product_categories.insert().values(**category))
    return category


def _record_recipe_inventory_movements(
    session: Session,
    product_id: str,
    product_name: str,
    quantity: int,
    movement_type: str,
    sign: int,
    reason: str,
    source_type: str,
    source_id: str,
    created_at: datetime,
    branch_id: str = BRANCH_ID,
) -> list[dict[str, Any]]:
    warehouse_id = _branch_warehouse_id(session, branch_id)
    components = _active_recipe_components(session, product_id, branch_id)
    movements: list[dict[str, Any]] = []
    for component in components:
        component_quantity = _quantity(
            Decimal(str(component["gross_quantity"]))
            / Decimal(str(component["yield_quantity"]))
            * quantity
        )
        movement = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": branch_id,
            "warehouse_id": warehouse_id,
            "item_id": component["item_id"],
            "movement_type": movement_type,
            "quantity_delta": sign * component_quantity,
            "unit_id": component["unit_id"],
            "unit_cost": 0,
            "total_cost": 0,
            "effective_at": created_at,
            "actor_user_id": None,
            "document_type": None,
            "document_id": None,
            "reference": None,
            "reason": reason,
            "notes": None,
            "idempotency_key": None,
            "status": "confirmed",
            "reversal_of_id": None,
            "source_type": source_type,
            "source_id": source_id,
            "created_at": created_at,
        }
        session.execute(models.inventory_movements.insert().values(**movement))
        movements.append(
            {
                **movement,
                "item_name": component["item_name"],
                "unit_code": component["unit_code"],
                "product_name": product_name,
            }
        )
    return movements


def _record_snapshot_inventory_movements(
    session: Session,
    order_line_id: str,
    product_name: str,
    movement_type: str,
    sign: int,
    reason: str,
    source_type: str,
    source_id: str,
    created_at: datetime,
) -> list[dict[str, Any]]:
    snapshot = (
        session.execute(
            sa.select(models.order_line_consumption_snapshots).where(
                models.order_line_consumption_snapshots.c.order_line_id == order_line_id
            )
        )
        .mappings()
        .first()
    )
    if not snapshot:
        raise BusinessError(
            "consumption_snapshot_not_found", "Order line consumption snapshot was not found"
        )
    warehouse_id = _branch_warehouse_id(session, snapshot["branch_id"])
    movements = []
    for component in snapshot["components"]:
        quantity = _quantity(component["gross_quantity"])
        unit_cost = _cost(component.get("unit_cost", 0))
        movement = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": snapshot["branch_id"],
            "warehouse_id": warehouse_id,
            "item_id": component["item_id"],
            "movement_type": movement_type,
            "quantity_delta": sign * quantity,
            "unit_id": component["unit_id"],
            "unit_cost": unit_cost,
            "total_cost": sign * _cost(component.get("total_cost", 0)),
            "effective_at": created_at,
            "actor_user_id": None,
            "document_type": "order",
            "document_id": snapshot["order_id"],
            "reference": order_line_id,
            "reason": reason,
            "notes": None,
            "idempotency_key": None,
            "status": "confirmed",
            "reversal_of_id": None,
            "source_type": source_type,
            "source_id": source_id,
            "created_at": created_at,
        }
        session.execute(models.inventory_movements.insert().values(**movement))
        movements.append(
            {
                **movement,
                "item_name": component["item_name"],
                "unit_code": component["unit_code"],
                "product_name": product_name,
            }
        )
    return movements


def _record_scaled_snapshot_inventory_movements(
    session: Session,
    order_line_id: str,
    affected_quantity: Decimal,
    original_line_quantity: Decimal,
    movement_type: str,
    sign: int,
    reason: str,
    source_type: str,
    source_id: str,
    created_at: datetime,
) -> list[dict[str, Any]]:
    """Record only the immutable-snapshot fraction affected by a correction."""
    if (
        original_line_quantity <= 0
        or affected_quantity <= 0
        or affected_quantity > original_line_quantity
    ):
        raise BusinessError(
            "historical_snapshot_missing", "Correction quantity is incompatible with history"
        )
    snapshot = (
        session.execute(
            sa.select(models.order_line_consumption_snapshots).where(
                models.order_line_consumption_snapshots.c.order_line_id == order_line_id
            )
        )
        .mappings()
        .first()
    )
    if not snapshot or not snapshot["components"]:
        raise BusinessError(
            "historical_snapshot_missing", "Order line consumption snapshot was not found"
        )
    factor = affected_quantity / original_line_quantity
    warehouse_id = _branch_warehouse_id(session, snapshot["branch_id"])
    movements: list[dict[str, Any]] = []
    for component in snapshot["components"]:
        try:
            quantity = _quantity(Decimal(str(component["gross_quantity"])) * factor)
            total_cost = _cost(Decimal(str(component.get("total_cost", 0))) * factor)
            unit_cost = _cost(component.get("unit_cost", 0))
            if quantity <= 0 or not component.get("unit_id") or not component.get("item_id"):
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            raise BusinessError(
                "historical_snapshot_missing", "Snapshot component is invalid"
            ) from None
        movement = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": snapshot["branch_id"],
            "warehouse_id": warehouse_id,
            "item_id": component["item_id"],
            "movement_type": movement_type,
            "quantity_delta": sign * quantity,
            "unit_id": component["unit_id"],
            "unit_cost": unit_cost,
            "total_cost": sign * total_cost,
            "effective_at": created_at,
            "actor_user_id": None,
            "document_type": "order_correction",
            "document_id": source_id,
            "reference": order_line_id,
            "reason": reason,
            "notes": None,
            "idempotency_key": None,
            "status": "confirmed",
            "reversal_of_id": None,
            "source_type": source_type,
            "source_id": source_id,
            "created_at": created_at,
        }
        session.execute(models.inventory_movements.insert().values(**movement))
        movements.append(movement)
    return movements


def _record_calculated_consumption_movements(
    session: Session,
    components: list[dict[str, Any]],
    product_name: str,
    movement_type: str,
    sign: int,
    reason: str,
    source_type: str,
    source_id: str,
    created_at: datetime,
    branch_id: str,
) -> list[dict[str, Any]]:
    warehouse_id = _branch_warehouse_id(session, branch_id)
    movements = []
    for component in components:
        quantity = _quantity(component["gross_quantity"])
        unit_cost = _cost(component.get("unit_cost", 0))
        movement = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": branch_id,
            "warehouse_id": warehouse_id,
            "item_id": component["item_id"],
            "movement_type": movement_type,
            "quantity_delta": sign * quantity,
            "unit_id": component["unit_id"],
            "unit_cost": unit_cost,
            "total_cost": sign * _cost(component.get("total_cost", 0)),
            "effective_at": created_at,
            "actor_user_id": None,
            "document_type": "order",
            "document_id": source_id,
            "reference": None,
            "reason": reason,
            "notes": None,
            "idempotency_key": None,
            "status": "confirmed",
            "reversal_of_id": None,
            "source_type": source_type,
            "source_id": source_id,
            "created_at": created_at,
        }
        session.execute(models.inventory_movements.insert().values(**movement))
        movements.append(
            {
                **movement,
                "item_name": component["item_name"],
                "unit_code": component["unit_code"],
                "product_name": product_name,
            }
        )
    return movements


def _active_recipe_components(
    session: Session,
    product_id: str,
    branch_id: str = BRANCH_ID,
) -> list[dict[str, Any]]:
    active_recipe_id = (
        sa.select(models.recipes.c.id)
        .where(
            models.recipes.c.product_id == product_id,
            models.recipes.c.status == "active",
            sa.or_(models.recipes.c.branch_id == branch_id, models.recipes.c.branch_id.is_(None)),
        )
        .order_by(models.recipes.c.branch_id.is_not(None).desc(), models.recipes.c.version.desc())
        .limit(1)
        .scalar_subquery()
    )
    rows = session.execute(
        sa.select(
            models.recipe_components.c.item_id,
            models.recipe_components.c.net_quantity,
            models.recipe_components.c.gross_quantity,
            models.recipe_components.c.waste_rate,
            models.recipe_components.c.unit_id,
            models.recipes.c.id.label("recipe_id"),
            models.recipes.c.version.label("recipe_version"),
            models.recipes.c.yield_quantity,
            models.inventory_items.c.name.label("item_name"),
            models.inventory_units.c.code.label("unit_code"),
        )
        .select_from(
            models.recipe_components.join(
                models.recipes,
                models.recipe_components.c.recipe_id == models.recipes.c.id,
            )
            .join(
                models.inventory_items,
                models.recipe_components.c.item_id == models.inventory_items.c.id,
            )
            .join(
                models.inventory_units,
                models.recipe_components.c.unit_id == models.inventory_units.c.id,
            )
        )
        .where(models.recipe_components.c.recipe_id == active_recipe_id)
        .order_by(models.inventory_items.c.name)
    ).mappings()
    return [dict(row) for row in rows]


def _ensure_product_default_recipe(
    session: Session,
    product_id: str,
    branch_id: str,
    now: datetime,
) -> list[dict[str, Any]]:
    """Ensure a lightweight SaaS Lite 1:1 direct recipe for products sold without explicit recipes."""
    prod = session.execute(
        sa.select(models.products).where(models.products.c.id == product_id)
    ).mappings().one_or_none()
    if not prod:
        return []

    org_id = prod["organization_id"]

    # 1. Resolve or create PZA unit
    unit_id = session.execute(
        sa.select(models.inventory_units.c.id).where(
            models.inventory_units.c.organization_id == org_id,
            models.inventory_units.c.code == "PZA",
        )
    ).scalar_one_or_none()
    if not unit_id:
        unit_id = session.execute(
            sa.select(models.inventory_units.c.id).where(models.inventory_units.c.code == "PZA")
        ).scalar_one_or_none()
    if not unit_id:
        unit_id = _id()
        session.execute(
            models.inventory_units.insert().values(
                id=unit_id,
                organization_id=org_id,
                code="PZA",
                name="Pieza",
                dimension="discrete",
                precision_scale=0,
                created_at=now,
            )
        )

    # 2. Resolve or create inventory item for this product
    item_id = session.execute(
        sa.select(models.inventory_items.c.id).where(
            models.inventory_items.c.organization_id == org_id,
            sa.or_(
                models.inventory_items.c.sku == prod["sku"],
                models.inventory_items.c.name == prod["name"],
            ),
        )
    ).scalar_one_or_none()
    if not item_id:
        item_id = _id()
        session.execute(
            models.inventory_items.insert().values(
                id=item_id,
                organization_id=org_id,
                name=prod["name"],
                sku=prod["sku"],
                base_unit_id=unit_id,
                item_type="product",
                catalog_scope="organization",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )

    # 3. Create default 1:1 recipe
    recipe_id = _id()
    session.execute(
        models.recipes.insert().values(
            id=recipe_id,
            organization_id=org_id,
            product_id=product_id,
            output_item_id=None,
            branch_id=None,
            recipe_type="sale",
            version=1,
            status="active",
            yield_quantity=Decimal("1"),
            yield_unit_id=unit_id,
            valid_from=now,
            valid_to=None,
            created_at=now,
            updated_at=now,
        )
    )

    # 4. Create default 1:1 recipe component
    session.execute(
        models.recipe_components.insert().values(
            recipe_id=recipe_id,
            item_id=item_id,
            quantity_base_units=Decimal("1"),
            unit_id=unit_id,
            net_quantity=Decimal("1"),
            waste_rate=Decimal("0"),
            gross_quantity=Decimal("1"),
            sort_order=1,
            notes="SaaS Lite direct sale recipe",
        )
    )
    session.flush()

    return _active_recipe_components(session, product_id, branch_id)


def _build_order_consumption_snapshot(
    session: Session,
    order_id: str,
    order_line_id: str,
    product_id: str,
    ordered_quantity: int,
    branch_id: str,
    created_at: datetime,
    selected_modifiers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    components = _active_recipe_components(session, product_id, branch_id)
    if not components:
        components = _ensure_product_default_recipe(session, product_id, branch_id, created_at)
    if not components:
        raise BusinessError("active_recipe_required", "Product requires an active recipe")
    warehouse_id = _branch_warehouse_id(session, branch_id)
    breakdown = []
    total = Decimal("0")
    for component in components:
        gross_quantity = _quantity(
            Decimal(str(component["gross_quantity"]))
            / Decimal(str(component["yield_quantity"]))
            * ordered_quantity
        )
        state = session.execute(
            sa.select(models.inventory_cost_states.c.average_unit_cost).where(
                models.inventory_cost_states.c.branch_id == branch_id,
                models.inventory_cost_states.c.warehouse_id == warehouse_id,
                models.inventory_cost_states.c.item_id == component["item_id"],
            )
        ).scalar_one_or_none()
        unit_cost = _cost(state or 0)
        component_cost = _cost(gross_quantity * unit_cost)
        total += component_cost
        breakdown.append(
            _sanitize_for_json(
                {
                    "item_id": component["item_id"],
                    "item_name": component["item_name"],
                    "unit_id": component["unit_id"],
                    "unit_code": component["unit_code"],
                    "net_quantity": _quantity(
                        Decimal(str(component["net_quantity"]))
                        / Decimal(str(component["yield_quantity"]))
                        * ordered_quantity
                    ),
                    "gross_quantity": gross_quantity,
                    "waste_rate": component["waste_rate"],
                    "unit_cost": unit_cost,
                    "total_cost": component_cost,
                }
            )
        )
    final_components, modifier_snapshots, modifier_total_cents = _apply_order_modifiers(
        session,
        product_id,
        branch_id,
        ordered_quantity,
        breakdown,
        selected_modifiers or [],
    )
    total = sum((_cost(component["total_cost"]) for component in final_components), Decimal("0"))
    return {
        "order_line_id": order_line_id,
        "order_id": order_id,
        "recipe_id": components[0]["recipe_id"],
        "recipe_version": components[0]["recipe_version"],
        "branch_id": branch_id,
        "components": final_components,
        "modifiers": modifier_snapshots,
        "total_theoretical_cost": _cost(total),
        "created_at": created_at,
        "modifier_total_cents": modifier_total_cents,
    }


def _apply_order_modifiers(
    session: Session,
    product_id: str,
    branch_id: str,
    ordered_quantity: int,
    base_components: list[dict[str, Any]],
    selected_modifiers: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    selected_option_ids = [str(selection.get("option_id", "")) for selection in selected_modifiers]
    legacy_ingredient_option = None
    if selected_option_ids:
        legacy_ingredient_option = session.execute(
            sa.select(models.ingredient_variation_products.c.id)
            .where(
                sa.or_(
                    models.ingredient_variation_products.c.add_option_id.in_(selected_option_ids),
                    models.ingredient_variation_products.c.remove_option_id.in_(
                        selected_option_ids
                    ),
                )
            )
            .limit(1)
        ).first()
    if legacy_ingredient_option is not None:
        raise BusinessError(
            "ingredient_extra_add_only",
            "Historical ingredient variation options cannot be selected in new sales",
        )
    groups = list_product_modifiers(session, product_id, branch_id)
    universal_extras = list(
        session.execute(
            sa.select(
                models.ingredient_variations,
                models.inventory_items.c.name.label("inventory_item_name"),
                models.inventory_items.c.sku.label("inventory_item_sku"),
                models.inventory_units.c.code.label("unit_code"),
            )
            .select_from(
                models.ingredient_variations.join(
                    models.inventory_items,
                    models.inventory_items.c.id == models.ingredient_variations.c.inventory_item_id,
                ).join(
                    models.inventory_units,
                    models.inventory_units.c.id == models.inventory_items.c.base_unit_id,
                )
            )
            .where(
                models.ingredient_variations.c.organization_id == ORGANIZATION_ID,
                models.ingredient_variations.c.status == "active",
                models.ingredient_variations.c.portion_quantity > 0,
                models.ingredient_variations.c.station.in_(("kitchen", "drinks", "packing")),
                models.inventory_items.c.organization_id == ORGANIZATION_ID,
                models.inventory_items.c.status == "active",
            )
            .order_by(models.ingredient_variations.c.display_order, models.inventory_items.c.name)
        ).mappings()
    )
    if universal_extras:
        groups.append(
            {
                "id": INGREDIENT_EXTRA_GROUP_ID,
                "organization_id": ORGANIZATION_ID,
                "product_id": product_id,
                "name": "Ingredientes adicionales",
                "is_required": False,
                "minimum_selections": 0,
                "maximum_selections": len(universal_extras),
                "station": None,
                "display_order": 10000,
                "status": "active",
                "options": [
                    {
                        "id": row["id"],
                        "group_id": INGREDIENT_EXTRA_GROUP_ID,
                        "name": row["add_label"],
                        "effect_type": "add",
                        "price_delta_cents": row["sale_price_cents"],
                        "affected_item_id": row["inventory_item_id"],
                        "replacement_item_id": None,
                        "remove_quantity": Decimal("0"),
                        "add_quantity": row["portion_quantity"],
                        "inventory_effect": True,
                        "kitchen_text": row["add_label"],
                        "station": row["station"],
                        "display_order": row["display_order"],
                        "status": "active",
                        "variation_kind": "ingredient_extra",
                        "variation_id": row["id"],
                        "inventory_item_name": row["inventory_item_name"],
                        "inventory_item_sku": row["inventory_item_sku"],
                        "unit_code": row["unit_code"],
                    }
                    for row in universal_extras
                ],
            }
        )
    groups_by_id = {group["id"]: group for group in groups}
    options_by_id = {
        option["id"]: (group, option) for group in groups for option in group["options"]
    }
    selections_by_group: dict[str, list[dict[str, Any]]] = {
        group_id: [] for group_id in groups_by_id
    }
    resolved = []
    seen_options = set()
    for selection in selected_modifiers:
        option_id = str(selection.get("option_id", ""))
        if option_id in seen_options:
            raise BusinessError(
                "duplicate_modifier_option", "Modifier option cannot be selected twice"
            )
        seen_options.add(option_id)
        match = options_by_id.get(option_id)
        if not match:
            if selection.get("selection_kind") == "order_comment":
                raise BusinessError(
                    "comment_preset_not_found",
                    "Comment preset is not available for this product",
                )
            if selection.get("selection_kind") == "ingredient_extra":
                raise BusinessError(
                    "ingredient_extra_not_found",
                    "Ingredient extra is not available",
                )
            raise BusinessError(
                "modifier_option_unavailable",
                "Modifier option is not available for this product and branch",
            )
        group, option = match
        selections_by_group[group["id"]].append(selection)
        resolved.append((group, option, selection))
    for group_id, group in groups_by_id.items():
        count = len(selections_by_group[group_id])
        minimum = int(group["minimum_selections"])
        maximum = int(group["maximum_selections"])
        if count < minimum:
            raise BusinessError(
                "modifier_group_minimum_not_met",
                f"Modifier group {group['name']} requires at least {minimum} selections",
            )
        if count > maximum:
            raise BusinessError(
                "modifier_group_maximum_exceeded",
                f"Modifier group {group['name']} allows at most {maximum} selections",
            )

    components = {component["item_id"]: dict(component) for component in base_components}
    warehouse_id = _branch_warehouse_id(session, branch_id)
    snapshots = []
    price_per_unit = 0
    for group, option, selection in resolved:
        effect = option["effect_type"]
        is_order_comment = option.get("variation_kind") == "order_comment"
        is_ingredient_extra = option.get("variation_kind") == "ingredient_extra"
        portions = 1
        if is_ingredient_extra:
            raw_portions = selection.get("portions", 1)
            if (
                isinstance(raw_portions, bool)
                or not isinstance(raw_portions, int)
                or not 1 <= raw_portions <= MAX_INGREDIENT_EXTRA_PORTIONS
            ):
                raise BusinessError(
                    "invalid_ingredient_extra_portions",
                    "Ingredient extra portions must be an integer between 1 and 99",
                )
            portions = raw_portions
        selection_kind = selection.get("selection_kind")
        if selection_kind == "order_comment" and not is_order_comment:
            raise BusinessError(
                "comment_preset_not_found", "Comment preset is not available for this product"
            )
        if selection_kind == "ingredient_extra" and not is_ingredient_extra:
            raise BusinessError("ingredient_extra_not_found", "Ingredient extra is not available")
        free_text = str(selection.get("text", "")).strip() or None
        if effect == "instruction" and free_text and len(free_text) > 240:
            raise BusinessError(
                "modifier_instruction_too_long", "Modifier instruction exceeds 240 characters"
            )
        if effect == "preset_instruction":
            # Preset notes are catalog-controlled instructions. The client may select
            # one, but can never replace the text or turn it into a priced/inventory
            # modifier at order time.
            free_text = None
        if is_order_comment:
            free_text = None
        if option["inventory_effect"] and effect not in {"instruction", "preset_instruction"}:
            affected_id = option["affected_item_id"]
            replacement_id = option["replacement_item_id"]
            remove_quantity = _quantity(option["remove_quantity"]) * ordered_quantity
            add_quantity = _quantity(option["add_quantity"]) * portions * ordered_quantity
            if effect == "remove" and remove_quantity == 0 and affected_id in components:
                remove_quantity = _quantity(components[affected_id]["gross_quantity"])
            if (
                effect in {"substitute", "variant"}
                and remove_quantity == 0
                and affected_id in components
            ):
                remove_quantity = _quantity(components[affected_id]["gross_quantity"])
            if affected_id and remove_quantity:
                current = components.get(affected_id)
                if not current or _quantity(current["gross_quantity"]) < remove_quantity:
                    raise BusinessError(
                        "modifier_quantity_exceeds_component",
                        "Modifier removes more inventory than the recipe contains",
                    )
                remaining = _quantity(current["gross_quantity"]) - remove_quantity
                if remaining == 0:
                    components.pop(affected_id)
                else:
                    current["gross_quantity"] = _sanitize_for_json(remaining)
                    current["net_quantity"] = _sanitize_for_json(
                        min(_quantity(current["net_quantity"]), remaining)
                    )
                    current["total_cost"] = _sanitize_for_json(
                        _cost(remaining * _cost(current["unit_cost"]))
                    )
            added_item_id = (
                replacement_id
                if effect in {"substitute", "variant"}
                else (replacement_id or affected_id)
            )
            if added_item_id and add_quantity:
                _add_modifier_component(
                    session, components, added_item_id, add_quantity, branch_id, warehouse_id
                )
        price_per_unit += (
            0 if effect == "preset_instruction" else int(option["price_delta_cents"]) * portions
        )
        snapshots.append(
            _sanitize_for_json(
                {
                    "group_id": group["id"],
                    "group_name": group["name"],
                    "option_id": option["id"],
                    "option_name": option["name"],
                    "kind": "order_comment"
                    if is_order_comment
                    else ("ingredient_extra" if is_ingredient_extra else "modifier"),
                    "effect_type": effect,
                    "comment_preset_id": option.get("comment_preset_id"),
                    "extra_id": option.get("variation_id") if is_ingredient_extra else None,
                    "portion_count": portions if is_ingredient_extra else None,
                    "portion_quantity": _quantity(option["add_quantity"])
                    if is_ingredient_extra
                    else None,
                    "sale_price_cents_per_portion": int(option["price_delta_cents"])
                    if is_ingredient_extra
                    else None,
                    "price_delta_cents": 0
                    if effect == "preset_instruction"
                    else int(option["price_delta_cents"]) * portions,
                    "kitchen_text": free_text or option["kitchen_text"],
                    "station": option["station"],
                    "affected_item_id": option["affected_item_id"],
                    "replacement_item_id": option["replacement_item_id"],
                    "remove_quantity": _quantity(option["remove_quantity"]) * ordered_quantity,
                    "add_quantity": _quantity(option["add_quantity"]) * portions * ordered_quantity,
                    "inventory_effect": False if is_order_comment else option["inventory_effect"],
                }
            )
        )
    return list(components.values()), snapshots, price_per_unit * ordered_quantity


def _add_modifier_component(
    session: Session,
    components: dict[str, dict[str, Any]],
    item_id: str,
    quantity: Decimal,
    branch_id: str,
    warehouse_id: str,
) -> None:
    if item_id in components:
        component = components[item_id]
        gross = _quantity(component["gross_quantity"]) + quantity
        component["gross_quantity"] = _sanitize_for_json(gross)
        component["net_quantity"] = _sanitize_for_json(
            _quantity(component["net_quantity"]) + quantity
        )
        component["total_cost"] = _sanitize_for_json(_cost(gross * _cost(component["unit_cost"])))
        return
    item = (
        session.execute(
            sa.select(
                models.inventory_items.c.id,
                models.inventory_items.c.name,
                models.inventory_items.c.base_unit_id,
                models.inventory_units.c.code.label("unit_code"),
            )
            .select_from(
                models.inventory_items.join(
                    models.inventory_units,
                    models.inventory_items.c.base_unit_id == models.inventory_units.c.id,
                )
            )
            .where(models.inventory_items.c.id == item_id)
        )
        .mappings()
        .first()
    )
    if not item:
        raise BusinessError("modifier_item_not_found", "Modifier inventory item was not found")
    average = session.execute(
        sa.select(models.inventory_cost_states.c.average_unit_cost).where(
            models.inventory_cost_states.c.branch_id == branch_id,
            models.inventory_cost_states.c.warehouse_id == warehouse_id,
            models.inventory_cost_states.c.item_id == item_id,
        )
    ).scalar_one_or_none()
    unit_cost = _cost(average or 0)
    components[item_id] = _sanitize_for_json(
        {
            "item_id": item_id,
            "item_name": item["name"],
            "unit_id": item["base_unit_id"],
            "unit_code": item["unit_code"],
            "net_quantity": quantity,
            "gross_quantity": quantity,
            "waste_rate": 0,
            "unit_cost": unit_cost,
            "total_cost": _cost(quantity * unit_cost),
        }
    )


def _branch_warehouse_id(session: Session, branch_id: str = BRANCH_ID) -> str:
    return str(
        session.execute(
            sa.select(models.warehouses.c.id)
            .where(
                models.warehouses.c.branch_id == branch_id,
                models.warehouses.c.status == "active",
            )
            .limit(1)
        ).scalar_one()
    )


def _actor_user_id(actor_user_id: str | None) -> str:
    return (actor_user_id or "").strip()


def require_permission(
    session: Session,
    actor_user_id: str,
    permission_code: str,
    branch_id: str | None = BRANCH_ID,
) -> None:
    if not actor_user_id:
        _record_authorization_denied(
            session,
            actor_user_id=None,
            permission_code=permission_code,
            branch_id=branch_id,
            reason="missing_actor",
        )

        raise AuthorizationError("actor_required", "Actor authentication is required")

    actor = (
        session.execute(
            sa.select(models.users).where(
                models.users.c.id == actor_user_id,
            )
        )
        .mappings()
        .first()
    )
    if not actor:
        _record_authorization_denied(
            session,
            actor_user_id=None,
            permission_code=permission_code,
            branch_id=branch_id,
            reason="actor_not_found",
        )
        raise AuthorizationError("actor_not_authorized", "Actor is not authorized")
    if actor["status"] != "active":
        _record_authorization_denied(
            session,
            actor_user_id=actor_user_id,
            permission_code=permission_code,
            branch_id=branch_id,
            reason="inactive_actor",
        )
        raise AuthorizationError("actor_not_authorized", "Actor is not authorized")

    if actor.get("is_superadmin"):
        return

    org_id = str(actor["organization_id"])
    org = session.execute(
        sa.select(models.organizations).where(models.organizations.c.id == org_id)
    ).mappings().first()
    if org and (org.get("owner_email") == actor.get("email")):
        return
    role_rows = session.execute(
        sa.select(
            models.roles.c.id.label("role_id"),
            models.roles.c.scope,
            models.user_roles.c.branch_id,
        )
        .select_from(
            models.user_roles.join(models.roles, models.user_roles.c.role_id == models.roles.c.id)
        )
        .where(
            models.user_roles.c.user_id == actor_user_id,
            models.roles.c.organization_id == org_id,
        )
    ).mappings()
    roles = [dict(row) for row in role_rows]
    organization_scope_required = permission_code == "admin.manage"
    scoped_role_ids = [
        role["role_id"]
        for role in roles
        if (
            role["scope"] == "organization"
            if organization_scope_required
            else (
                role["scope"] == "organization"
                or branch_id is None
                or (role["scope"] == "branch" and role["branch_id"] == branch_id)
            )
        )
    ]
    if not scoped_role_ids:
        _record_authorization_denied(
            session,
            actor_user_id=actor_user_id,
            permission_code=permission_code,
            branch_id=branch_id,
            reason="no_scoped_role",
        )
        raise AuthorizationError("permission_denied", "Actor does not have the required permission")

    compatible_codes = _compatible_permission_codes(permission_code)
    allowed = session.execute(
        sa.select(models.permissions.c.code)
        .select_from(
            models.role_permissions.join(
                models.permissions,
                models.role_permissions.c.permission_id == models.permissions.c.id,
            )
        )
        .where(
            models.role_permissions.c.role_id.in_(scoped_role_ids),
            models.permissions.c.code.in_(compatible_codes),
        )
        .limit(1)
    ).scalar_one_or_none()
    if allowed:
        return

    organization_authority = session.execute(
        sa.select(models.role_authority_grants.c.role_id)
        .select_from(
            models.role_authority_grants.join(
                models.roles,
                models.role_authority_grants.c.role_id == models.roles.c.id,
            )
        )
        .where(
            models.role_authority_grants.c.role_id.in_(scoped_role_ids),
            models.role_authority_grants.c.authority_kind == "organization_all_permissions",
            models.roles.c.organization_id == org_id,
            models.roles.c.scope == "organization",
        )
        .limit(1)
    ).scalar_one_or_none()
    if organization_authority:
        return

    _record_authorization_denied(
        session,
        actor_user_id=actor_user_id,
        permission_code=permission_code,
        branch_id=branch_id,
        reason="missing_permission",
    )
    raise AuthorizationError("permission_denied", "Actor does not have the required permission")


def _compatible_permission_codes(permission_code: str) -> set[str]:
    if permission_code in {"cash.withdraw", "cash.movement.withdraw"}:
        return {"cash.withdraw", "cash.movement.withdraw"}
    if permission_code == "purchases.manage":
        return {"catalog.manage", "purchases.manage", "admin.manage"}
    if permission_code == "purchases.read":
        return {"purchases.read", "purchases.manage", "catalog.manage", "admin.manage"}
    return {permission_code}


def authorize_branch_scope(
    session: Session,
    actor_user_id: str,
    permission_code: str,
    branch_id: str | None = None,
) -> str | None:
    actor_id = _actor_user_id(actor_user_id)
    if branch_id:
        active_branch = session.execute(
            sa.select(models.branches.c.id).where(
                models.branches.c.id == branch_id,
                models.branches.c.organization_id == ORGANIZATION_ID,
                models.branches.c.status == "active",
            )
        ).scalar_one_or_none()
        if not active_branch:
            _record_authorization_denied(
                session,
                actor_user_id=actor_id or None,
                permission_code=permission_code,
                branch_id=branch_id,
                reason="invalid_branch_scope",
            )
            raise AuthorizationError(
                "permission_denied", "Actor does not have access to the requested branch"
            )
        require_permission(session, actor_id, permission_code, branch_id)
        return branch_id
    if _actor_has_organization_scope(session, actor_id):
        require_permission(session, actor_id, permission_code, BRANCH_ID)
        return None
    scoped_branch_id = _actor_default_branch_id(session, actor_id)
    if not scoped_branch_id:
        require_permission(session, actor_id, permission_code, BRANCH_ID)
        return BRANCH_ID
    require_permission(session, actor_id, permission_code, scoped_branch_id)
    return scoped_branch_id


def authorize_cash_movement_scope(
    session: Session, actor_user_id: str, branch_id: str | None = None
) -> str | None:
    """Authorize the current-shift lookup for legacy or ledger capabilities.

    A POS cashier that may create a movement must be able to verify the open
    shift even when its role intentionally does not grant the ledger read view.
    Failed alternatives are rolled back so they do not leave denial audits for
    an ultimately authorized request; the final failure remains audited.
    """
    permissions = (
        "cash.shift.read",
        "cash.movement.read",
        "cash.movement.withdraw",
        "cash.movement.deposit",
    )
    for permission_code in permissions[:-1]:
        try:
            return authorize_branch_scope(session, actor_user_id, permission_code, branch_id)
        except AuthorizationError:
            session.rollback()
    return authorize_branch_scope(session, actor_user_id, permissions[-1], branch_id)


def _actor_has_organization_scope(session: Session, actor_user_id: str) -> bool:
    rows = session.execute(
        sa.select(models.roles.c.id, models.roles.c.scope)
        .select_from(
            models.user_roles.join(models.roles, models.user_roles.c.role_id == models.roles.c.id)
        )
        .where(
            models.user_roles.c.user_id == actor_user_id,
            models.roles.c.organization_id == ORGANIZATION_ID,
        )
    ).mappings()
    return any(row["scope"] == "organization" for row in rows)


def actor_has_organization_authority(session: Session, actor_user_id: str) -> bool:
    """The persisted grant, never a role label, is corporate authority."""
    return (
        session.execute(
            sa.select(models.user_roles.c.user_id)
            .select_from(
                models.user_roles.join(
                    models.roles, models.user_roles.c.role_id == models.roles.c.id
                ).join(
                    models.role_authority_grants,
                    models.role_authority_grants.c.role_id == models.roles.c.id,
                )
            )
            .where(
                models.user_roles.c.user_id == actor_user_id,
                models.roles.c.organization_id == ORGANIZATION_ID,
                models.roles.c.scope == "organization",
                models.role_authority_grants.c.authority_kind == "organization_all_permissions",
            )
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


@_pco007_observed("pco007.recipe.workspace", lambda session, actor_user_id, branch_id: branch_id)
def get_recipes_workspace(
    session: Session, actor_user_id: str, branch_id: str | None
) -> dict[str, Any]:
    """Read-only recipe editor inputs, deliberately independent from catalog APIs."""
    actor_id = _actor_user_id(actor_user_id)
    corporate_allowed = actor_has_organization_authority(session, actor_id)
    if branch_id is None:
        if not corporate_allowed:
            raise AuthorizationError(
                "recipe_branch_required", "A branch is required for this actor"
            )
        require_permission(session, actor_id, "recipes.manage", BRANCH_ID)
    else:
        authorize_branch_scope(session, actor_id, "recipes.manage", branch_id)

    branch_rows = (
        session.execute(
            sa.select(models.branches.c.id, models.branches.c.name, models.branches.c.code)
            .where(
                models.branches.c.organization_id == ORGANIZATION_ID,
                models.branches.c.status == "active",
            )
            .order_by(models.branches.c.code)
        )
        .mappings()
        .all()
    )
    if not corporate_allowed:
        assigned = set(
            session.execute(
                sa.select(models.user_roles.c.branch_id)
                .select_from(
                    models.user_roles.join(
                        models.roles, models.user_roles.c.role_id == models.roles.c.id
                    )
                    .join(
                        models.role_permissions,
                        models.role_permissions.c.role_id == models.roles.c.id,
                    )
                    .join(
                        models.permissions,
                        models.permissions.c.id == models.role_permissions.c.permission_id,
                    )
                )
                .where(
                    models.user_roles.c.user_id == actor_id,
                    models.user_roles.c.branch_id.is_not(None),
                    models.permissions.c.code == "recipes.manage",
                )
            ).scalars()
        )
        branch_rows = [row for row in branch_rows if row["id"] in assigned]

    product_scope = [models.products.c.catalog_scope == "organization"]
    item_scope = [models.inventory_items.c.catalog_scope == "organization"]
    if branch_id is not None:
        product_scope.append(models.products.c.source_branch_id == branch_id)
        item_scope.append(models.inventory_items.c.source_branch_id == branch_id)
    has_recipe_subquery = (
        sa.select(sa.literal(True))
        .where(
            models.recipes.c.product_id == models.products.c.id,
            models.recipes.c.status == "active",
            models.recipes.c.organization_id == ORGANIZATION_ID,
            models.recipes.c.branch_id.is_(None)
            if branch_id is None
            else sa.or_(
                models.recipes.c.branch_id == branch_id,
                models.recipes.c.branch_id.is_(None),
            ),
        )
        .limit(1)
        .exists()
    )

    products = (
        session.execute(
            sa.select(
                models.products.c.id,
                models.products.c.name,
                models.products.c.sku,
                has_recipe_subquery.label("has_recipe"),
            )
            .where(
                models.products.c.organization_id == ORGANIZATION_ID,
                models.products.c.status == "active",
                sa.or_(*product_scope),
            )
            .order_by(models.products.c.name, models.products.c.id)
        )
        .mappings()
        .all()
    )
    items = (
        session.execute(
            sa.select(
                models.inventory_items.c.id,
                models.inventory_items.c.name,
                models.inventory_items.c.base_unit_id,
                models.inventory_units.c.code.label("unit_code"),
                sa.func.coalesce(
                    sa.select(models.inventory_cost_states.c.last_unit_cost)
                    .where(models.inventory_cost_states.c.item_id == models.inventory_items.c.id)
                    .order_by(models.inventory_cost_states.c.updated_at.desc())
                    .limit(1)
                    .scalar_subquery(),
                    sa.select(models.purchase_presentations.c.cost_per_base_unit)
                    .where(models.purchase_presentations.c.item_id == models.inventory_items.c.id)
                    .order_by(
                        models.purchase_presentations.c.is_preferred.desc(),
                        models.purchase_presentations.c.created_at.desc(),
                    )
                    .limit(1)
                    .scalar_subquery(),
                    0,
                ).label("last_unit_cost"),
                sa.func.coalesce(
                    sa.select(models.inventory_cost_states.c.average_unit_cost)
                    .where(models.inventory_cost_states.c.item_id == models.inventory_items.c.id)
                    .order_by(models.inventory_cost_states.c.updated_at.desc())
                    .limit(1)
                    .scalar_subquery(),
                    0,
                ).label("average_unit_cost"),
            )
            .select_from(
                models.inventory_items.join(
                    models.inventory_units,
                    models.inventory_items.c.base_unit_id == models.inventory_units.c.id,
                )
            )
            .where(
                models.inventory_items.c.organization_id == ORGANIZATION_ID,
                models.inventory_items.c.status == "active",
                sa.or_(*item_scope),
            )
            .order_by(models.inventory_items.c.name, models.inventory_items.c.id)
        )
        .mappings()
        .all()
    )
    _record_pco007_metric(
        "pco007.recipe.workspace", result="success", branch_id=branch_id, duration_ms=0
    )
    return {
        "selected_branch_id": branch_id,
        "corporate_allowed": corporate_allowed,
        "scopes": {
            "branches": [dict(row) for row in branch_rows],
            "corporate_allowed": corporate_allowed,
        },
        "products": [dict(row) for row in products],
        "items": [
            {
                **dict(row),
                "unit_id": row["base_unit_id"],
                "last_unit_cost": float(row["last_unit_cost"] or 0),
                "average_unit_cost": float(row["average_unit_cost"] or 0),
            }
            for row in items
        ],
    }


def _actor_default_branch_id(session: Session, actor_user_id: str) -> str | None:
    return session.execute(
        sa.select(models.user_roles.c.branch_id)
        .select_from(
            models.user_roles.join(
                models.branches,
                models.user_roles.c.branch_id == models.branches.c.id,
            )
        )
        .where(
            models.user_roles.c.user_id == actor_user_id,
            models.user_roles.c.branch_id.is_not(None),
            models.branches.c.organization_id == ORGANIZATION_ID,
            models.branches.c.status == "active",
        )
        .order_by(models.branches.c.code)
        .limit(1)
    ).scalar_one_or_none()


def _assign_default_role_permissions(
    session: Session,
    role_id: str,
    role_name: str,
) -> list[str]:
    normalized = role_name.strip().lower()
    admin_perms = [
        "admin.manage",
        "catalog.manage",
        "catalog.branch.manage",
        "recipes.manage",
        "purchases.manage",
        "purchases.read",
        "inventory.read",
        "inventory.adjust",
        "inventory.waste",
        "inventory.transfer.send",
        "inventory.transfer.receive",
        "inventory.count",
        "orders.read",
        "orders.create",
        "orders.amend",
        "orders.cancel",
        "orders.fulfill",
        "orders.reopen.request",
        "orders.reopen.authorize",
        "cash.shift.read",
        "cash.shift.open",
        "cash.shift.close",
        "cash.concept.manage",
        "cash.concept.read",
        "cash.movement.read",
        "cash.movement.withdraw",
        "cash.movement.deposit",
        "cash.movement.compensate",
        "cash.reconciliation.perform",
        "cash.user_cut.read",
        "cash.user_cut.create",
        "cash.user_cut.reopen.request",
        "cash.user_cut.reopen.authorize",
        "dashboard.read",
        "reports.sales.read",
        "reports.expenses.read",
        "reports.ingredient_sales.read",
        "reports.waste.read",
        "branch.admin.access",
        "branch.staff.read",
        "pos.operate",
        "cash.withdraw",
        "production.manage",
        "access.organization.all_branches",
        "audit.read",
        "print.jobs.read",
        "print.jobs.retry",
        "payments.read",
        "payments.confirm",
    ]
    profile = {
        "administrador de restaurante": admin_perms,
        "dueño": admin_perms,
        "dueno": admin_perms,
        "owner": admin_perms,
        "administrador": [
            "admin.manage",
            "catalog.manage",
            "catalog.branch.manage",
            "recipes.manage",
            "purchases.manage",
            "purchases.read",
            "inventory.read",
            "inventory.adjust",
            "inventory.waste",
            "inventory.transfer.send",
            "inventory.transfer.receive",
            "inventory.count",
            "orders.read",
            "orders.create",
            "orders.amend",
            "orders.cancel",
            "orders.fulfill",
            "orders.reopen.request",
            "orders.reopen.authorize",
            "cash.shift.read",
            "cash.shift.open",
            "cash.shift.close",
            "cash.concept.manage",
            "cash.concept.read",
            "cash.movement.read",
            "cash.movement.withdraw",
            "cash.movement.deposit",
            "cash.movement.compensate",
            "cash.reconciliation.perform",
            "cash.user_cut.read",
            "cash.user_cut.create",
            "cash.user_cut.reopen.request",
            "cash.user_cut.reopen.authorize",
            "dashboard.read",
            "reports.sales.read",
            "reports.expenses.read",
            "reports.ingredient_sales.read",
            "reports.waste.read",
            "branch.admin.access",
            "branch.staff.read",
            "pos.operate",
            "cash.withdraw",
            "production.manage",
            "audit.read",
            "print.jobs.read",
            "print.jobs.retry",
            "payments.read",
            "payments.confirm",
        ],
        "administrador corporativo": [
            "admin.manage",
            "catalog.manage",
            "catalog.branch.manage",
            "recipes.manage",
            "purchases.manage",
            "purchases.read",
            "inventory.read",
            "inventory.adjust",
            "inventory.waste",
            "inventory.transfer.send",
            "inventory.transfer.receive",
            "inventory.count",
            "orders.read",
            "orders.create",
            "orders.amend",
            "orders.cancel",
            "orders.fulfill",
            "orders.reopen.request",
            "orders.reopen.authorize",
            "cash.shift.read",
            "cash.shift.open",
            "cash.shift.close",
            "cash.concept.manage",
            "cash.concept.read",
            "cash.movement.read",
            "cash.movement.withdraw",
            "cash.movement.deposit",
            "cash.movement.compensate",
            "cash.reconciliation.perform",
            "cash.user_cut.read",
            "cash.user_cut.create",
            "cash.user_cut.reopen.request",
            "cash.user_cut.reopen.authorize",
            "dashboard.read",
            "reports.sales.read",
            "reports.expenses.read",
            "reports.ingredient_sales.read",
            "reports.waste.read",
            "branch.admin.access",
            "branch.staff.read",
            "pos.operate",
            "cash.withdraw",
            "production.manage",
            "audit.read",
            "print.jobs.read",
            "print.jobs.retry",
            "payments.read",
            "payments.confirm",
        ],
        "supervisor": [
            "catalog.manage",
            "catalog.branch.manage",
            "recipes.manage",
            "purchases.manage",
            "purchases.read",
            "inventory.read",
            "inventory.waste",
            "inventory.transfer.send",
            "inventory.transfer.receive",
            "inventory.count",
            "orders.read",
            "orders.create",
            "orders.amend",
            "orders.cancel",
            "orders.fulfill",
            "orders.reopen.request",
            "orders.reopen.authorize",
            "cash.shift.read",
            "cash.shift.open",
            "cash.shift.close",
            "cash.movement.read",
            "cash.movement.withdraw",
            "cash.movement.deposit",
            "dashboard.read",
            "reports.sales.read",
            "reports.ingredient_sales.read",
            "reports.waste.read",
            "branch.admin.access",
            "branch.staff.read",
            "pos.operate",
            "cash.withdraw",
            "production.manage",
            "print.jobs.read",
            "print.jobs.retry",
            "payments.read",
            "payments.confirm",
        ],
        "supervisor de sucursal": [
            "catalog.manage",
            "catalog.branch.manage",
            "recipes.manage",
            "purchases.manage",
            "purchases.read",
            "inventory.read",
            "inventory.waste",
            "inventory.transfer.send",
            "inventory.transfer.receive",
            "inventory.count",
            "orders.read",
            "orders.create",
            "orders.amend",
            "orders.cancel",
            "orders.fulfill",
            "orders.reopen.request",
            "orders.reopen.authorize",
            "cash.shift.read",
            "cash.shift.open",
            "cash.shift.close",
            "cash.movement.read",
            "cash.movement.withdraw",
            "cash.movement.deposit",
            "dashboard.read",
            "reports.sales.read",
            "reports.ingredient_sales.read",
            "reports.waste.read",
            "branch.admin.access",
            "branch.staff.read",
            "pos.operate",
            "cash.withdraw",
            "production.manage",
            "print.jobs.read",
            "print.jobs.retry",
            "payments.read",
            "payments.confirm",
        ],
        "líder": [
            "purchases.read",
            "purchases.manage",
            "inventory.read",
            "inventory.waste",
            "inventory.transfer.receive",
            "inventory.count",
            "orders.read",
            "orders.create",
            "orders.amend",
            "orders.cancel",
            "orders.fulfill",
            "orders.reopen.request",
            "cash.shift.read",
            "cash.shift.open",
            "cash.shift.close",
            "cash.movement.read",
            "cash.movement.withdraw",
            "cash.movement.deposit",
            "cash.user_cut.read",
            "cash.user_cut.create",
            "cash.user_cut.reopen.request",
            "branch.admin.access",
            "branch.staff.read",
            "pos.operate",
            "cash.withdraw",
            "production.manage",
            "payments.read",
            "payments.confirm",
        ],
        "lider": [
            "purchases.read",
            "purchases.manage",
            "inventory.read",
            "inventory.waste",
            "inventory.transfer.receive",
            "inventory.count",
            "orders.read",
            "orders.create",
            "orders.amend",
            "orders.cancel",
            "orders.fulfill",
            "orders.reopen.request",
            "cash.shift.read",
            "cash.shift.open",
            "cash.shift.close",
            "cash.movement.read",
            "cash.movement.withdraw",
            "cash.movement.deposit",
            "cash.user_cut.read",
            "cash.user_cut.create",
            "cash.user_cut.reopen.request",
            "branch.admin.access",
            "branch.staff.read",
            "pos.operate",
            "cash.withdraw",
            "production.manage",
            "payments.read",
            "payments.confirm",
        ],
        "cajero jefe": [
            "purchases.read",
            "purchases.manage",
            "inventory.read",
            "inventory.waste",
            "inventory.transfer.receive",
            "orders.read",
            "orders.create",
            "orders.amend",
            "orders.fulfill",
            "payments.read",
            "payments.confirm",
            "cash.shift.read",
            "cash.shift.open",
            "cash.shift.close",
            "cash.movement.read",
            "cash.movement.withdraw",
            "cash.movement.deposit",
            "cash.concept.read",
            "branch.admin.access",
            "branch.staff.read",
            "pos.operate",
        ],
        "receptor de traspaso": ["inventory.read", "inventory.transfer.receive"],
        "gerente de sucursal": [
            "catalog.manage",
            "inventory.adjust",
            "orders.cancel",
            "cash.shift.read",
            "orders.read",
            "payments.read",
            "dashboard.read",
            "pos.operate",
        ],
        "cajero": [
            "cash.shift.read",
            "cash.shift.open",
            "cash.shift.close",
            "orders.read",
            "orders.create",
            "orders.amend",
            "payments.confirm",
            "pos.operate",
        ],
        "caja": [
            "cash.shift.read",
            "cash.shift.open",
            "cash.shift.close",
            "orders.read",
            "orders.create",
            "orders.amend",
            "payments.confirm",
            "pos.operate",
        ],
        "encargado de inventarios": ["inventory.adjust"],
    }.get(normalized, [])
    if not profile:
        return []

    rows = session.execute(
        sa.select(models.permissions.c.id, models.permissions.c.code).where(
            models.permissions.c.code.in_(profile)
        )
    ).mappings()
    permissions_by_code = {row["code"]: row["id"] for row in rows}
    assignments = [
        {"role_id": role_id, "permission_id": permissions_by_code[code]}
        for code in profile
        if code in permissions_by_code
    ]
    if assignments:
        session.execute(models.role_permissions.insert(), assignments)
    return [code for code in profile if code in permissions_by_code]


def _set_user_password(
    session: Session,
    user_id: str,
    password: str,
    updated_at: datetime,
) -> None:
    salt = generate_password_salt()
    credential = {
        "user_id": user_id,
        "password_hash": hash_password(password, salt),
        "password_salt": salt,
        "password_algorithm": PASSWORD_ALGORITHM,
        "updated_at": updated_at,
    }
    existing = (
        session.execute(
            sa.select(models.user_credentials.c.user_id).where(
                models.user_credentials.c.user_id == user_id,
                models.user_credentials.c.password_algorithm == PASSWORD_ALGORITHM,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        session.execute(
            models.user_credentials.update()
            .where(
                models.user_credentials.c.user_id == user_id,
                models.user_credentials.c.password_algorithm == PASSWORD_ALGORITHM,
            )
            .values(**credential)
        )
        return
    session.execute(models.user_credentials.insert().values(**credential))


def _record_authorization_denied(
    session: Session,
    actor_user_id: str | None,
    permission_code: str,
    branch_id: str | None,
    reason: str,
) -> None:
    session.rollback()
    _audit(
        session,
        action="authorization.denied",
        entity_type="permission",
        entity_id=permission_code,
        payload={"permission": permission_code, "reason": reason},
        branch_id=branch_id,
        actor_user_id=actor_user_id,
    )
    session.commit()


def _next_folio(session: Session, branch_id: str = BRANCH_ID) -> str:
    branch_code = session.execute(
        sa.select(models.branches.c.code).where(models.branches.c.id == branch_id)
    ).scalar_one_or_none()
    prefix = str(branch_code or "PILOTO").strip().upper()
    folios = session.execute(
        sa.select(models.orders.c.folio).where(
            models.orders.c.branch_id == branch_id,
            models.orders.c.folio.like(f"{prefix}-%"),
        )
    ).scalars()
    max_suffix = 0
    for folio in folios:
        suffix = str(folio).rsplit("-", 1)[-1]
        if suffix.isdigit():
            max_suffix = max(max_suffix, int(suffix))
    return f"{prefix}-{max_suffix + 1:06d}"


def _next_unique_folio(session: Session, branch_id: str = BRANCH_ID) -> str:
    folio = _next_folio(session, branch_id)
    existing = session.execute(
        sa.select(models.orders.c.id).where(
            models.orders.c.branch_id == branch_id,
            models.orders.c.folio == folio,
        )
    ).first()
    if not existing:
        return folio
    branch_code = session.execute(
        sa.select(models.branches.c.code).where(models.branches.c.id == branch_id)
    ).scalar_one_or_none()
    prefix = str(branch_code or "PILOTO").strip().upper()
    suffix = int(folio.rsplit("-", 1)[-1])
    while True:
        suffix += 1
        candidate = f"{prefix}-{suffix:06d}"
        existing = session.execute(
            sa.select(models.orders.c.id).where(
                models.orders.c.branch_id == branch_id,
                models.orders.c.folio == candidate,
            )
        ).first()
        if not existing:
            return candidate


def _sanitize_for_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: _sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_sanitize_for_json(v) for v in data]
    elif isinstance(data, datetime):
        return (data if data.tzinfo is not None else data.replace(tzinfo=UTC)).isoformat()
    elif isinstance(data, Decimal):
        return str(data)
    return data


def _audit(
    session: Session,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    branch_id: str | None = BRANCH_ID,
    organization_id: str = ORGANIZATION_ID,
    actor_user_id: str | None = ADMIN_USER_ID,
) -> None:
    session.execute(
        models.audit_events.insert().values(
            id=_id(),
            organization_id=organization_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=_sanitize_for_json(payload),
            correlation_id=None,
            created_at=_now(),
        )
    )


def _id() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def update_user(
    session: Session,
    user_id: str,
    email: str | None = None,
    display_name: str | None = None,
    actor_user_id: str | None = None,
    role_id: str | None = None,
    password: str | None = None,
    branch_id: str | None = None,
    employee_code: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    is_self_update = bool(actor_id and actor_id == user_id)
    role_change_requested = role_id is not None
    if role_change_requested or not is_self_update:
        require_permission(session, actor_id, "admin.manage")
    elif not actor_id:
        require_permission(session, actor_id, "admin.manage")

    user_row = session.execute(
        sa.select(models.users).where(
            models.users.c.id == user_id,
        )
    ).mappings().first()
    if not user_row:
        raise BusinessError("user_not_found", "User was not found")
    user_org_id = user_row["organization_id"]

    role_assignment = None
    if role_id:
        role_assignment = _validate_user_role_assignment(session, user_id, role_id, branch_id)
        _authorize_governed_profile_assignment(session, actor_id, role_assignment)

    update_data: dict[str, Any] = {}
    if email is not None:
        update_data["email"] = email.strip().lower()
    if display_name is not None:
        update_data["display_name"] = display_name.strip()
    if employee_code is not None:
        normalized_employee_code = _normalize_employee_code(employee_code)
        assert normalized_employee_code is not None
        _assign_employee_code(
            session,
            normalized_employee_code,
            subject_type="user",
            subject_id=user_id,
            organization_id=user_org_id,
        )
        update_data["employee_code"] = normalized_employee_code

    if update_data:
        update_data["updated_at"] = _now()
        session.execute(
            sa.update(models.users).where(models.users.c.id == user_id).values(**update_data)
        )

    if password is not None:
        p_val = password.strip()
        if p_val:
            _set_user_password(session, user_id, p_val, _now())
            session.execute(
                sa.update(models.users).where(models.users.c.id == user_id).values(status="active")
            )

    if role_id is not None:
        if role_assignment:
            _insert_user_role_assignment(session, role_assignment, actor_id)

    _audit(
        session,
        action="user.updated",
        entity_type="user",
        entity_id=user_id,
        payload={
            **{key: value for key, value in update_data.items() if key != "employee_code"},
            **({"employee_code_changed": True} if "employee_code" in update_data else {}),
            **({"role_assignment_mode": "additive"} if role_assignment else {}),
        },
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": user_id, **update_data}


def delete_user(
    session: Session,
    user_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    session.execute(
        sa.update(models.users)
        .where(models.users.c.id == user_id)
        .values(status="suspended", updated_at=_now())
    )
    _audit(
        session,
        action="user.deleted",
        entity_type="user",
        entity_id=user_id,
        payload={"status": "suspended"},
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": user_id, "status": "suspended"}


def update_branch(
    session: Session,
    branch_id: str,
    name: str | None = None,
    code: str | None = None,
    actor_user_id: str | None = None,
    street: str | None = None,
    exterior_number: str | None = None,
    interior_number: str | None = None,
    neighborhood: str | None = None,
    postal_code: str | None = None,
    city: str | None = None,
    state: str | None = None,
    cross_streets: str | None = None,
    latitude: float | Decimal | str | None = None,
    longitude: float | Decimal | str | None = None,
    phone: str | None = None,
    google_review_url: str | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")

    update_data: dict[str, Any] = {}
    if name is not None:
        update_data["name"] = name.strip()
    if code is not None:
        update_data["code"] = code.strip()
    if street is not None:
        update_data["street"] = str(street).strip() or None
    if exterior_number is not None:
        update_data["exterior_number"] = str(exterior_number).strip() or None
    if interior_number is not None:
        update_data["interior_number"] = str(interior_number).strip() or None
    if neighborhood is not None:
        update_data["neighborhood"] = str(neighborhood).strip() or None
    if postal_code is not None:
        update_data["postal_code"] = str(postal_code).strip() or None
    if city is not None:
        update_data["city"] = str(city).strip() or None
    if state is not None:
        update_data["state"] = str(state).strip() or None
    if cross_streets is not None:
        update_data["cross_streets"] = str(cross_streets).strip() or None
    if latitude is not None:
        update_data["latitude"] = (
            float(latitude) if latitude != "" and latitude is not None else None
        )
    if longitude is not None:
        update_data["longitude"] = (
            float(longitude) if longitude != "" and longitude is not None else None
        )
    if phone is not None:
        update_data["phone"] = str(phone).strip() or None
    if google_review_url is not None:
        update_data["google_review_url"] = str(google_review_url).strip() or None

    if extra_payload:
        for k in (
            "street",
            "exterior_number",
            "interior_number",
            "neighborhood",
            "postal_code",
            "city",
            "state",
            "cross_streets",
            "phone",
            "google_review_url",
        ):
            if k in extra_payload and k not in update_data:
                v = extra_payload[k]
                update_data[k] = str(v).strip() if v else None
        if "latitude" in extra_payload and "latitude" not in update_data:
            v_lat = extra_payload["latitude"]
            update_data["latitude"] = float(v_lat) if v_lat != "" and v_lat is not None else None
        if "longitude" in extra_payload and "longitude" not in update_data:
            v_lng = extra_payload["longitude"]
            update_data["longitude"] = float(v_lng) if v_lng != "" and v_lng is not None else None

    if update_data:
        update_data["updated_at"] = _now()
        session.execute(
            sa.update(models.branches)
            .where(models.branches.c.id == branch_id)
            .values(**update_data)
        )
        audit_payload = {
            k: (str(v) if isinstance(v, (Decimal, datetime)) else v) for k, v in update_data.items()
        }
        _audit(
            session,
            action="branch.updated",
            entity_type="branch",
            entity_id=branch_id,
            payload=audit_payload,
            actor_user_id=actor_id,
        )
        session.commit()
    return {"id": branch_id, **update_data}


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def list_public_branches(
    session: Session,
    customer_lat: float | None = None,
    customer_lng: float | None = None,
    include_public_key: bool = False,
) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(
            models.branches.c.id,
            models.branches.c.name,
            models.branches.c.code,
            models.branches.c.street,
            models.branches.c.exterior_number,
            models.branches.c.interior_number,
            models.branches.c.neighborhood,
            models.branches.c.postal_code,
            models.branches.c.city,
            models.branches.c.state,
            models.branches.c.cross_streets,
            models.branches.c.latitude,
            models.branches.c.longitude,
            models.branches.c.phone,
            models.branches.c.google_review_url,
            models.branches.c.status,
            models.public_order_keys.c.public_key,
        )
        .outerjoin(
            models.public_order_keys,
            sa.and_(
                models.public_order_keys.c.branch_id == models.branches.c.id,
                models.public_order_keys.c.organization_id == models.branches.c.organization_id,
                models.public_order_keys.c.status == "active",
            ),
        )
        .where(
            models.branches.c.organization_id == ORGANIZATION_ID,
            models.branches.c.status == "active",
        )
        .order_by(models.branches.c.name)
    ).mappings()
    org_theme = "light"
    try:
        theme_val = session.execute(
            sa.select(models.organizations.c.mobile_theme).where(
                models.organizations.c.id == ORGANIZATION_ID
            )
        ).scalar_one_or_none()
        if theme_val:
            org_theme = str(theme_val)
    except Exception:
        pass

    branches = []
    for r in rows:
        b = dict(r)
        b["mobile_theme"] = org_theme
        if include_public_key and not b.get("public_key"):
            generated_key = f"pk_{str(b['id']).replace('-', '')[:24]}"
            try:
                session.execute(
                    models.public_order_keys.insert().values(
                        public_key=generated_key,
                        organization_id=ORGANIZATION_ID,
                        branch_id=b["id"],
                        status="active",
                        created_at=_now(),
                    )
                )
                session.flush()
                b["public_key"] = generated_key
            except Exception:
                existing = session.execute(
                    sa.select(models.public_order_keys.c.public_key).where(
                        models.public_order_keys.c.branch_id == b["id"],
                        models.public_order_keys.c.status == "active",
                    )
                ).scalar_one_or_none()
                if existing:
                    b["public_key"] = existing
        elif not include_public_key:
            b.pop("public_key", None)
        lat = float(b["latitude"]) if b.get("latitude") is not None else None
        lng = float(b.get("longitude")) if b.get("longitude") is not None else None
        b["latitude"] = lat
        b["longitude"] = lng

        distance_km = None
        if (
            customer_lat is not None
            and customer_lng is not None
            and lat is not None
            and lng is not None
        ):
            distance_km = round(_haversine_distance_km(customer_lat, customer_lng, lat, lng), 2)
        b["distance_km"] = distance_km
        branches.append(b)

    if customer_lat is not None and customer_lng is not None:
        branches.sort(key=lambda x: (x["distance_km"] is None, x["distance_km"] or 0))

    return branches


def delete_branch(
    session: Session,
    branch_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    session.execute(
        sa.update(models.branches)
        .where(models.branches.c.id == branch_id)
        .values(status="inactive", updated_at=_now())
    )
    _audit(
        session,
        action="branch.deleted",
        entity_type="branch",
        entity_id=branch_id,
        payload={"status": "inactive"},
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": branch_id, "status": "inactive"}


_DRIVER_FIELDS = (
    "employee_code",
    "name",
    "license_number",
    "motorcycle_plate",
    "phone",
    "address",
    "emergency_contact_name",
)
_DRIVER_FIELD_LIMITS = {
    "employee_code": 6,
    "name": 160,
    "license_number": 80,
    "motorcycle_plate": 32,
    "phone": 32,
    "address": 500,
    "emergency_contact_name": 160,
}


def _normalized_driver_fields(values: dict[str, Any]) -> dict[str, str]:
    normalized = {field: str(values.get(field, "")).strip() for field in _DRIVER_FIELDS}
    empty_fields = [field for field, value in normalized.items() if not value]
    if empty_fields:
        raise BusinessError(
            "driver_fields_required",
            f"Driver fields are required: {', '.join(empty_fields)}",
        )
    oversized = [
        field for field, value in normalized.items() if len(value) > _DRIVER_FIELD_LIMITS[field]
    ]
    if oversized:
        raise BusinessError(
            "driver_field_too_long",
            f"Driver fields exceed their maximum length: {', '.join(oversized)}",
        )
    normalized["employee_code"] = _normalize_employee_code(normalized["employee_code"]) or ""
    return normalized


def _require_active_driver_branch(session: Session, branch_id: str) -> dict[str, Any]:
    branch = (
        session.execute(
            sa.select(models.branches).where(
                models.branches.c.id == branch_id,
                models.branches.c.organization_id == ORGANIZATION_ID,
                models.branches.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not branch:
        raise BusinessError(
            "driver_branch_not_found",
            "Driver branch must be active and belong to the organization",
        )
    return dict(branch)


def list_drivers(session: Session, actor_user_id: str | None = None) -> list[dict[str, Any]]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    rows = session.execute(
        sa.select(
            models.drivers,
            models.branches.c.name.label("branch_name"),
        )
        .join(models.branches, models.branches.c.id == models.drivers.c.branch_id)
        .where(models.drivers.c.organization_id == ORGANIZATION_ID)
        .order_by(models.drivers.c.name, models.drivers.c.id)
    ).mappings()
    return [dict(row) for row in rows]


def list_available_delivery_drivers(
    session: Session,
    branch_id: str,
    actor_user_id: str | None = None,
) -> list[dict[str, Any]]:
    actor_id = _actor_user_id(actor_user_id)
    authorized_branch_id = authorize_branch_scope(
        session,
        actor_id,
        "orders.create",
        branch_id,
    )
    rows = session.execute(
        sa.select(
            models.drivers.c.id,
            models.drivers.c.name,
            models.drivers.c.phone,
            models.drivers.c.motorcycle_plate,
        )
        .where(
            models.drivers.c.organization_id == ORGANIZATION_ID,
            models.drivers.c.branch_id == authorized_branch_id,
            models.drivers.c.status == "active",
        )
        .order_by(models.drivers.c.name, models.drivers.c.id)
    ).mappings()
    return [dict(row) for row in rows]


def list_driver_deliveries(
    session: Session,
    driver_id: str,
    actor_user_id: str | None = None,
) -> list[dict[str, Any]]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    driver_exists = session.execute(
        sa.select(models.drivers.c.id).where(
            models.drivers.c.id == driver_id,
            models.drivers.c.organization_id == ORGANIZATION_ID,
        )
    ).scalar_one_or_none()
    if not driver_exists:
        raise BusinessError("driver_not_found", "Driver was not found")
    rows = session.execute(
        sa.select(
            models.delivery_assignments,
            models.orders.c.folio,
            models.orders.c.status.label("order_status"),
            models.branches.c.name.label("branch_name"),
        )
        .join(models.orders, models.orders.c.id == models.delivery_assignments.c.order_id)
        .join(
            models.branches,
            models.branches.c.id == models.delivery_assignments.c.branch_id,
        )
        .where(
            models.delivery_assignments.c.organization_id == ORGANIZATION_ID,
            models.delivery_assignments.c.driver_id == driver_id,
        )
        .order_by(models.delivery_assignments.c.assigned_at.desc())
    ).mappings()
    return [dict(row) for row in rows]


def create_driver(
    session: Session,
    branch_id: str,
    values: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    normalized_branch_id = branch_id.strip()
    _require_active_driver_branch(session, normalized_branch_id)
    normalized = _normalized_driver_fields(values)
    now = _now()
    driver_id = _id()
    _assign_employee_code(
        session,
        normalized["employee_code"],
        subject_type="driver",
        subject_id=driver_id,
    )
    driver: dict[str, Any] = {
        "id": driver_id,
        "organization_id": ORGANIZATION_ID,
        "branch_id": normalized_branch_id,
        **normalized,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.drivers.insert().values(**driver))
    _audit(
        session,
        action="driver.created",
        entity_type="driver",
        entity_id=driver["id"],
        branch_id=normalized_branch_id,
        actor_user_id=actor_id,
        payload={"branch_id": normalized_branch_id, "fields": list(_DRIVER_FIELDS)},
    )
    session.commit()
    return driver


def update_driver(
    session: Session,
    driver_id: str,
    branch_id: str,
    values: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    existing = (
        session.execute(
            sa.select(models.drivers).where(
                models.drivers.c.id == driver_id,
                models.drivers.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not existing:
        raise BusinessError("driver_not_found", "Driver was not found")
    normalized_branch_id = branch_id.strip()
    _require_active_driver_branch(session, normalized_branch_id)
    normalized = _normalized_driver_fields(values)
    _assign_employee_code(
        session,
        normalized["employee_code"],
        subject_type="driver",
        subject_id=driver_id,
    )
    changed_fields = [field for field, value in normalized.items() if existing[field] != value]
    if existing["branch_id"] != normalized_branch_id:
        changed_fields.append("branch_id")
    update_data = {
        "branch_id": normalized_branch_id,
        **normalized,
        "updated_at": _now(),
    }
    session.execute(
        models.drivers.update().where(models.drivers.c.id == driver_id).values(**update_data)
    )
    _audit(
        session,
        action="driver.updated",
        entity_type="driver",
        entity_id=driver_id,
        branch_id=normalized_branch_id,
        actor_user_id=actor_id,
        payload={
            "branch_id": normalized_branch_id,
            "changed_fields": changed_fields,
        },
    )
    session.commit()
    return {"id": driver_id, "status": existing["status"], **update_data}


def deactivate_driver(
    session: Session,
    driver_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    existing = (
        session.execute(
            sa.select(models.drivers).where(
                models.drivers.c.id == driver_id,
                models.drivers.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not existing:
        raise BusinessError("driver_not_found", "Driver was not found")
    session.execute(
        models.drivers.update()
        .where(models.drivers.c.id == driver_id)
        .values(status="inactive", updated_at=_now())
    )
    _audit(
        session,
        action="driver.deactivated",
        entity_type="driver",
        entity_id=driver_id,
        branch_id=existing["branch_id"],
        actor_user_id=actor_id,
        payload={"branch_id": existing["branch_id"], "status": "inactive"},
    )
    session.commit()
    return {"id": driver_id, "status": "inactive"}


def _attendance_identity(session: Session, employee_code: str) -> dict[str, str]:
    owner = (
        session.execute(
            sa.select(models.employee_code_registry).where(
                models.employee_code_registry.c.organization_id == ORGANIZATION_ID,
                models.employee_code_registry.c.employee_code == employee_code,
            )
        )
        .mappings()
        .first()
    )
    if not owner:
        raise BusinessError(
            "employee_code_invalid", "Employee code does not identify an active employee"
        )
    subject_type = str(owner["subject_type"])
    subject_id = str(owner["subject_id"])
    if subject_type == "user":
        table = models.users
        name_column = models.users.c.display_name
    elif subject_type == "driver":
        table = models.drivers
        name_column = models.drivers.c.name
    else:
        raise BusinessError(
            "employee_code_invalid", "Employee code does not identify an active employee"
        )
    person = (
        session.execute(
            sa.select(
                table.c.id,
                name_column.label("employee_name"),
            ).where(
                table.c.organization_id == ORGANIZATION_ID,
                table.c.id == subject_id,
                table.c.employee_code == employee_code,
                table.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not person:
        raise BusinessError(
            "employee_code_invalid", "Employee code does not identify an active employee"
        )
    return {"subject_type": subject_type, **dict(person)}


def record_attendance_check(
    session: Session,
    employee_code: str,
    branch_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    authorized_branch_id = authorize_branch_scope(
        session, actor_id, "pos.operate", branch_id.strip()
    )
    if not authorized_branch_id:
        raise BusinessError(
            "attendance_branch_required", "An active branch is required for attendance"
        )
    branch = (
        session.execute(
            sa.select(models.branches.c.timezone).where(
                models.branches.c.id == authorized_branch_id,
                models.branches.c.organization_id == ORGANIZATION_ID,
                models.branches.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not branch:
        raise BusinessError(
            "attendance_branch_required", "An active branch is required for attendance"
        )
    normalized_code = _normalize_employee_code(employee_code)
    assert normalized_code is not None
    identity = _attendance_identity(session, normalized_code)
    checked_at = _now()
    try:
        local_date = checked_at.astimezone(ZoneInfo(str(branch["timezone"]))).date()
    except ZoneInfoNotFoundError as exc:
        raise BusinessError(
            "attendance_timezone_invalid", "Branch timezone is not configured correctly"
        ) from exc

    previous_sequences = list(
        session.execute(
            sa.select(models.attendance_checks.c.daily_sequence).where(
                models.attendance_checks.c.organization_id == ORGANIZATION_ID,
                models.attendance_checks.c.subject_type == identity["subject_type"],
                models.attendance_checks.c.subject_id == identity["id"],
                models.attendance_checks.c.local_date == local_date,
            )
        ).scalars()
    )
    if len(previous_sequences) >= 2:
        raise BusinessError(
            "attendance_daily_limit_reached",
            "Employee already registered entry and exit for this day",
        )
    daily_sequence = len(previous_sequences) + 1
    attendance: dict[str, Any] = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "branch_id": authorized_branch_id,
        "subject_type": identity["subject_type"],
        "subject_id": identity["id"],
        "employee_code_snapshot": normalized_code,
        "employee_name_snapshot": identity["employee_name"],
        "local_date": local_date,
        "daily_sequence": daily_sequence,
        "checked_at": checked_at,
        "created_by": actor_id,
    }
    session.execute(models.attendance_checks.insert().values(**attendance))
    _audit(
        session,
        action="attendance.checked",
        entity_type="attendance_check",
        entity_id=attendance["id"],
        branch_id=authorized_branch_id,
        actor_user_id=actor_id,
        payload={
            "subject_type": identity["subject_type"],
            "daily_sequence": daily_sequence,
            "local_date": local_date.isoformat(),
        },
    )
    session.commit()
    logger.info(
        "attendance_check_recorded",
        extra={
            "attendance_id": attendance["id"],
            "branch_id": authorized_branch_id,
            "subject_type": identity["subject_type"],
            "daily_sequence": daily_sequence,
        },
    )
    return {
        **attendance,
        "display_state": "single" if daily_sequence == 1 else "exit",
    }


def _attendance_period_filters(
    day: str | None,
    month: str | None,
) -> tuple[date | None, date | None, date | None]:
    normalized_day = (day or "").strip()
    normalized_month = (month or "").strip()
    if normalized_day and normalized_month:
        raise BusinessError("attendance_period_conflict", "Choose either day or month, not both")
    if normalized_day:
        try:
            parsed_day = date.fromisoformat(normalized_day)
        except ValueError as exc:
            raise BusinessError(
                "attendance_day_invalid", "Attendance day must use YYYY-MM-DD"
            ) from exc
        return parsed_day, None, None
    if normalized_month:
        try:
            month_start = datetime.strptime(normalized_month, "%Y-%m").date()
        except ValueError as exc:
            raise BusinessError(
                "attendance_month_invalid", "Attendance month must use YYYY-MM"
            ) from exc
        month_end = date(
            month_start.year + (1 if month_start.month == 12 else 0),
            1 if month_start.month == 12 else month_start.month + 1,
            1,
        )
        return None, month_start, month_end
    return None, None, None


def list_attendance_checks(
    session: Session,
    actor_user_id: str | None = None,
    *,
    employee_code: str | None = None,
    day: str | None = None,
    month: str | None = None,
    branch_id: str | None = None,
) -> list[dict[str, Any]]:
    actor_id = _actor_user_id(actor_user_id)
    authorized_branch_id = authorize_branch_scope(session, actor_id, "branch.staff.read", branch_id)
    parsed_day, month_start, month_end = _attendance_period_filters(day, month)
    normalized_code = _normalize_employee_code(employee_code, allow_empty=True)
    daily_counts = (
        sa.select(
            models.attendance_checks.c.organization_id,
            models.attendance_checks.c.subject_type,
            models.attendance_checks.c.subject_id,
            models.attendance_checks.c.local_date,
            sa.func.count(models.attendance_checks.c.id).label("daily_count"),
        )
        .group_by(
            models.attendance_checks.c.organization_id,
            models.attendance_checks.c.subject_type,
            models.attendance_checks.c.subject_id,
            models.attendance_checks.c.local_date,
        )
        .subquery()
    )
    query = (
        sa.select(
            models.attendance_checks,
            models.branches.c.name.label("branch_name"),
            models.branches.c.timezone.label("branch_timezone"),
            daily_counts.c.daily_count,
        )
        .join(models.branches, models.branches.c.id == models.attendance_checks.c.branch_id)
        .join(
            daily_counts,
            sa.and_(
                daily_counts.c.organization_id == models.attendance_checks.c.organization_id,
                daily_counts.c.subject_type == models.attendance_checks.c.subject_type,
                daily_counts.c.subject_id == models.attendance_checks.c.subject_id,
                daily_counts.c.local_date == models.attendance_checks.c.local_date,
            ),
        )
        .where(models.attendance_checks.c.organization_id == ORGANIZATION_ID)
    )
    if authorized_branch_id:
        query = query.where(models.attendance_checks.c.branch_id == authorized_branch_id)
    if normalized_code:
        query = query.where(models.attendance_checks.c.employee_code_snapshot == normalized_code)
    if parsed_day:
        query = query.where(models.attendance_checks.c.local_date == parsed_day)
    if month_start and month_end:
        query = query.where(
            models.attendance_checks.c.local_date >= month_start,
            models.attendance_checks.c.local_date < month_end,
        )
    rows = session.execute(
        query.order_by(
            models.attendance_checks.c.local_date.desc(),
            models.attendance_checks.c.checked_at.desc(),
        )
    ).mappings()
    result = []
    for row in rows:
        item = dict(row)
        checked_at_value = item.get("checked_at")
        if isinstance(checked_at_value, datetime) and checked_at_value.tzinfo is None:
            item["checked_at"] = checked_at_value.replace(tzinfo=UTC)
        daily_count = int(item.pop("daily_count"))
        item["display_state"] = (
            "single" if daily_count == 1 else "entry" if item["daily_sequence"] == 1 else "exit"
        )
        result.append(item)
    return result


def update_product(
    session: Session,
    product_id: str,
    name: str | None = None,
    sku: str | None = None,
    price_cents: int | None = None,
    image_url: str | None = None,
    category_name: str | None = None,
    station: str | None = None,
    status: str | None = None,
    actor_user_id: str | None = None,
    delivery_price_cents: int | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    actor = session.execute(sa.select(models.users).where(models.users.c.id == actor_id)).mappings().first()
    org_id = str(actor["organization_id"]) if actor else ORGANIZATION_ID

    update_data: dict[str, Any] = {}
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise BusinessError("invalid_product_name", "Product name cannot be blank")
        update_data["name"] = normalized_name
    if sku is not None:
        normalized_sku = normalize_product_sku(sku)
        if not normalized_sku:
            raise BusinessError("invalid_product_sku", "Product SKU cannot be blank")
        update_data["sku"] = normalized_sku
    if image_url is not None:
        update_data["image_url"] = image_url.strip() if image_url.strip() else None
    if station is not None:
        normalized_station = station.strip().lower()
        if normalized_station in {"cocina", "kitchen"}:
            update_data["station"] = "cocina" if org_id != ORGANIZATION_ID else "kitchen"
        elif normalized_station in {"barra", "drinks"}:
            update_data["station"] = "barra" if org_id != ORGANIZATION_ID else "drinks"
        elif normalized_station in {"packing"}:
            update_data["station"] = "packing"
        elif normalized_station in {"unassigned", ""}:
            update_data["station"] = "unassigned"
        else:
            raise BusinessError("invalid_station", "Station must be valid")
    if status is not None:
        normalized_status = status.strip().lower()
        if normalized_status not in {"active", "inactive", "needs_review"}:
            raise BusinessError("invalid_product_status", "Product status is invalid")
        if normalized_status == "active":
            current_station = update_data.get("station") or station
            if current_station is None:
                current_station = session.execute(
                    sa.select(models.products.c.station).where(models.products.c.id == product_id)
                ).scalar_one_or_none()
            if not current_station or current_station.strip().lower() in {"unassigned", ""}:
                raise BusinessError("missing_product_station", "Assign a station before activation")
        update_data["status"] = normalized_status
    if delivery_price_cents is not None:
        update_data["delivery_price_cents"] = delivery_price_cents

    now = _now()
    if category_name is not None:
        normalized_category = category_name.strip()
        if normalized_category:
            category = _get_or_create_category(session, normalized_category, now, organization_id=org_id)
            update_data["category_id"] = category["id"]
    if update_data:
        update_data["updated_at"] = now
        session.execute(
            sa.update(models.products)
            .where(models.products.c.id == product_id)
            .values(**update_data)
        )

    if price_cents is not None:
        price = {
            "id": _id(),
            "organization_id": org_id,
            "product_id": product_id,
            "price_cents": price_cents,
            "currency": "MXN",
            "valid_from": now,
            "valid_to": None,
            "created_at": now,
        }
        session.execute(
            sa.update(models.price_versions)
            .where(
                models.price_versions.c.product_id == product_id,
                models.price_versions.c.valid_to.is_(None),
            )
            .values(valid_to=now)
        )
        session.execute(models.price_versions.insert().values(**price))
        update_data["price_cents"] = price_cents

    if update_data or price_cents is not None:
        _audit(
            session,
            action="product.updated",
            entity_type="product",
            entity_id=product_id,
            payload=update_data,
            actor_user_id=actor_id,
        )
        session.commit()
    return {"id": product_id, **update_data}


def delete_product(
    session: Session,
    product_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    session.execute(
        sa.update(models.products)
        .where(models.products.c.id == product_id)
        .values(status="inactive", updated_at=_now())
    )
    _audit(
        session,
        action="product.deleted",
        entity_type="product",
        entity_id=product_id,
        payload={"status": "inactive"},
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": product_id, "status": "inactive"}


def update_role(
    session: Session,
    role_id: str,
    name: str | None = None,
    scope: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    is_organization_authority = _role_has_organization_authority_grant(session, role_id)
    if is_organization_authority:
        _authorize_governed_profile_assignment(session, actor_id, {"role_id": role_id})

    update_data = {}
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise BusinessError("invalid_role_name", "Role name cannot be empty")
        update_data["name"] = normalized_name

    if scope is not None:
        normalized_scope = scope.strip().lower()
        if normalized_scope not in {"organization", "branch"}:
            raise BusinessError("invalid_role_scope", "Role scope must be organization or branch")
        if is_organization_authority and normalized_scope != "organization":
            _reject_authority_role_mutation(
                session,
                actor_id,
                role_id,
                "owner_role_scope_immutable",
                "An organization authority role must retain organization scope",
            )
        update_data["scope"] = normalized_scope

    if update_data:
        session.execute(
            sa.update(models.roles).where(models.roles.c.id == role_id).values(**update_data)
        )
        _audit(
            session,
            action="role.updated",
            entity_type="role",
            entity_id=role_id,
            payload=update_data,
            actor_user_id=actor_id,
        )
        session.commit()

    return {"id": role_id, **update_data}


def delete_role(
    session: Session,
    role_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    if _role_has_organization_authority_grant(session, role_id):
        _authorize_governed_profile_assignment(session, actor_id, {"role_id": role_id})
        _reject_authority_role_mutation(
            session,
            actor_id,
            role_id,
            "owner_role_delete_forbidden",
            "An organization authority role cannot be deleted",
        )

    # Ensure role is not assigned to users
    in_use = session.execute(
        sa.select(models.user_roles).where(models.user_roles.c.role_id == role_id)
    ).first()
    if in_use:
        raise BusinessError("role_in_use", "Cannot delete role that is assigned to users")

    session.execute(
        sa.delete(models.role_permissions).where(models.role_permissions.c.role_id == role_id)
    )
    session.execute(sa.delete(models.roles).where(models.roles.c.id == role_id))

    _audit(
        session,
        action="role.deleted",
        entity_type="role",
        entity_id=role_id,
        payload={},
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": role_id, "status": "deleted"}


def update_role_permissions(
    session: Session,
    role_id: str,
    permission_ids: list[str],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    if _role_has_organization_authority_grant(session, role_id):
        _authorize_governed_profile_assignment(session, actor_id, {"role_id": role_id})
        _reject_authority_role_mutation(
            session,
            actor_id,
            role_id,
            "owner_role_permissions_immutable",
            "An organization authority role retains all persisted permissions",
        )

    # Validate permissions exist
    existing_perms = session.execute(
        sa.select(models.permissions.c.id).where(models.permissions.c.id.in_(permission_ids))
    ).fetchall()
    valid_ids = {row.id for row in existing_perms}

    if len(valid_ids) != len(permission_ids):
        raise BusinessError("invalid_permission", "One or more permission IDs are invalid")

    # Delete old permissions
    session.execute(
        sa.delete(models.role_permissions).where(models.role_permissions.c.role_id == role_id)
    )

    # Insert new permissions
    if valid_ids:
        session.execute(
            sa.insert(models.role_permissions),
            [{"role_id": role_id, "permission_id": pid} for pid in valid_ids],
        )

    _audit(
        session,
        action="role.permissions_updated",
        entity_type="role",
        entity_id=role_id,
        payload={"permission_ids": list(valid_ids)},
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": role_id, "permissions_count": len(valid_ids)}


def _role_has_organization_authority_grant(session: Session, role_id: str) -> bool:
    return (
        session.execute(
            sa.select(models.role_authority_grants.c.role_id)
            .select_from(
                models.role_authority_grants.join(
                    models.roles,
                    models.role_authority_grants.c.role_id == models.roles.c.id,
                )
            )
            .where(
                models.role_authority_grants.c.role_id == role_id,
                models.role_authority_grants.c.authority_kind == "organization_all_permissions",
                models.roles.c.organization_id == ORGANIZATION_ID,
            )
        ).scalar_one_or_none()
        is not None
    )


def _reject_authority_role_mutation(
    session: Session,
    actor_user_id: str,
    role_id: str,
    code: str,
    message: str,
) -> None:
    _record_authorization_denied(
        session,
        actor_user_id=actor_user_id or None,
        permission_code="admin.manage",
        branch_id=None,
        reason=code,
    )
    raise BusinessError(code, message)


def create_warehouse(
    session: Session,
    branch_id: str,
    name: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    normalized_name = name.strip()
    if not normalized_name:
        raise BusinessError("invalid_warehouse_name", "Warehouse name is required")

    # Check branch exists
    branch = session.execute(
        sa.select(models.branches).where(
            models.branches.c.id == branch_id,
            models.branches.c.organization_id == ORGANIZATION_ID,
        )
    ).first()
    if not branch:
        raise BusinessError("invalid_branch", "Branch does not exist")

    # A branch can only have one warehouse currently per model constraint unique=True
    existing = session.execute(
        sa.select(models.warehouses).where(models.warehouses.c.branch_id == branch_id)
    ).first()
    if existing:
        raise BusinessError("warehouse_exists", "Branch already has a warehouse")

    warehouse_id = str(uuid4())
    now = _now()
    session.execute(
        sa.insert(models.warehouses).values(
            id=warehouse_id,
            organization_id=ORGANIZATION_ID,
            branch_id=branch_id,
            name=normalized_name,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    _audit(
        session,
        action="warehouse.created",
        entity_type="warehouse",
        entity_id=warehouse_id,
        payload={"name": normalized_name, "branch_id": branch_id},
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": warehouse_id, "name": normalized_name, "branch_id": branch_id}


def update_warehouse(
    session: Session,
    warehouse_id: str,
    name: str | None = None,
    status: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    current = (
        session.execute(
            sa.select(
                models.warehouses.c.id,
                models.warehouses.c.branch_id,
                models.warehouses.c.status,
                models.branches.c.status.label("branch_status"),
            )
            .select_from(
                models.warehouses.join(
                    models.branches,
                    models.warehouses.c.branch_id == models.branches.c.id,
                )
            )
            .where(
                models.warehouses.c.id == warehouse_id,
                models.warehouses.c.organization_id == ORGANIZATION_ID,
                models.branches.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not current:
        raise BusinessError("warehouse_not_found", "Warehouse was not found")

    update_data: dict[str, Any] = {"updated_at": _now()}
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise BusinessError("invalid_warehouse_name", "Warehouse name cannot be empty")
        update_data["name"] = normalized_name

    if status is not None:
        if status not in {"active", "inactive"}:
            raise BusinessError("invalid_warehouse_status", "Status must be active or inactive")
        if status == "inactive" and current["branch_status"] == "active":
            raise BusinessError(
                "active_branch_requires_warehouse",
                "An active branch must retain its active warehouse",
            )
        update_data["status"] = status

    session.execute(
        sa.update(models.warehouses)
        .where(models.warehouses.c.id == warehouse_id)
        .values(**update_data)
    )

    _audit(
        session,
        action="warehouse.updated",
        entity_type="warehouse",
        entity_id=warehouse_id,
        payload=update_data,
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": warehouse_id, **update_data}


def create_inventory_unit(
    session: Session,
    code: str,
    name: str,
    precision_scale: int = 0,
    dimension: str = "discrete",
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    normalized_code = code.strip().upper()
    normalized_name = name.strip()
    normalized_dimension = dimension.strip().lower()

    if not normalized_code or not normalized_name:
        raise BusinessError("invalid_unit", "Code and name are required")
    if normalized_dimension not in {"mass", "volume", "discrete", "commercial"}:
        raise BusinessError("invalid_unit_dimension", "Unit dimension is invalid")

    existing = session.execute(
        sa.select(models.inventory_units).where(
            models.inventory_units.c.organization_id == ORGANIZATION_ID,
            models.inventory_units.c.code == normalized_code,
        )
    ).first()
    if existing:
        raise BusinessError("unit_exists", "Unit with this code already exists")

    unit_id = str(uuid4())
    session.execute(
        sa.insert(models.inventory_units).values(
            id=unit_id,
            organization_id=ORGANIZATION_ID,
            code=normalized_code,
            name=normalized_name,
            dimension=normalized_dimension,
            precision_scale=precision_scale,
            created_at=_now(),
        )
    )

    _audit(
        session,
        action="inventory_unit.created",
        entity_type="inventory_unit",
        entity_id=unit_id,
        payload={"code": normalized_code, "name": normalized_name},
        actor_user_id=actor_id,
    )
    session.commit()
    return {
        "id": unit_id,
        "code": normalized_code,
        "name": normalized_name,
        "dimension": normalized_dimension,
    }


def update_inventory_unit(
    session: Session,
    unit_id: str,
    name: str | None = None,
    precision_scale: int | None = None,
    dimension: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    update_data: dict[str, Any] = {}
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise BusinessError("invalid_unit_name", "Name cannot be empty")
        update_data["name"] = normalized_name
    if precision_scale is not None:
        update_data["precision_scale"] = precision_scale
    if dimension is not None:
        normalized_dimension = dimension.strip().lower()
        if normalized_dimension not in {"mass", "volume", "discrete", "commercial"}:
            raise BusinessError("invalid_unit_dimension", "Unit dimension is invalid")
        update_data["dimension"] = normalized_dimension

    if update_data:
        session.execute(
            sa.update(models.inventory_units)
            .where(models.inventory_units.c.id == unit_id)
            .values(**update_data)
        )
        _audit(
            session,
            action="inventory_unit.updated",
            entity_type="inventory_unit",
            entity_id=unit_id,
            payload=update_data,
            actor_user_id=actor_id,
        )
        session.commit()
    return {"id": unit_id, **update_data}


def create_inventory_item(
    session: Session,
    name: str,
    sku: str,
    base_unit_id: str,
    item_type: str = "ingredient",
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    normalized_name = name.strip()
    normalized_sku = normalize_inventory_sku(sku)

    if not normalized_name:
        raise BusinessError("invalid_item", "Name is required")
    if not is_numeric_sku(normalized_sku):
        raise BusinessError("invalid_item_sku", "Inventory SKU must contain only digits")

    existing = session.execute(
        sa.select(models.inventory_items).where(
            models.inventory_items.c.organization_id == ORGANIZATION_ID,
            models.inventory_items.c.sku == normalized_sku,
        )
    ).first()
    if existing:
        raise BusinessError("item_exists", "Item with this SKU already exists")

    item_id = str(uuid4())
    now = _now()
    session.execute(
        sa.insert(models.inventory_items).values(
            id=item_id,
            organization_id=ORGANIZATION_ID,
            name=normalized_name,
            sku=normalized_sku,
            base_unit_id=base_unit_id,
            item_type=item_type,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    _audit(
        session,
        action="inventory_item.created",
        entity_type="inventory_item",
        entity_id=item_id,
        payload={"sku": normalized_sku, "name": normalized_name},
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": item_id, "name": normalized_name, "sku": normalized_sku}


def update_inventory_item(
    session: Session,
    item_id: str,
    name: str | None = None,
    base_unit_id: str | None = None,
    item_type: str | None = None,
    status: str | None = None,
    category_name: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    update_data: dict[str, Any] = {"updated_at": _now()}
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise BusinessError("invalid_item_name", "Name cannot be empty")
        update_data["name"] = normalized_name
    if base_unit_id is not None:
        update_data["base_unit_id"] = base_unit_id
    if item_type is not None:
        update_data["item_type"] = item_type
    if status is not None:
        update_data["status"] = status
    if category_name is not None:
        update_data["category_name"] = category_name.strip()[:120] or None

    session.execute(
        sa.update(models.inventory_items)
        .where(models.inventory_items.c.id == item_id)
        .values(**update_data)
    )
    _audit(
        session,
        action="inventory_item.updated",
        entity_type="inventory_item",
        entity_id=item_id,
        payload=update_data,
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": item_id, **update_data}


def create_category(
    session: Session,
    name: str,
    display_order: int = 0,
    actor_user_id: str | None = None,
    organization_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    actor = session.execute(sa.select(models.users).where(models.users.c.id == actor_id)).mappings().first()
    org_id = organization_id or (str(actor["organization_id"]) if actor and actor.get("organization_id") else ORGANIZATION_ID)

    normalized_name = name.strip()
    if not normalized_name:
        raise BusinessError("invalid_category", "Category name cannot be blank")

    existing = session.execute(
        sa.select(models.product_categories).where(
            models.product_categories.c.organization_id == org_id,
            sa.func.lower(models.product_categories.c.name) == normalized_name.lower(),
            models.product_categories.c.status != "archived",
        )
    ).first()
    if existing:
        raise BusinessError("category_exists", "Category with this name already exists")

    cat_id = str(uuid4())
    now = _now()
    session.execute(
        sa.insert(models.product_categories).values(
            id=cat_id,
            organization_id=org_id,
            name=normalized_name,
            display_order=display_order,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    _audit(
        session,
        action="category.created",
        entity_type="category",
        entity_id=cat_id,
        payload={"name": normalized_name},
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": cat_id, "name": normalized_name, "display_order": display_order, "status": "active"}


def update_category(
    session: Session,
    category_id: str,
    name: str | None = None,
    display_order: int | None = None,
    status: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    update_data: dict[str, Any] = {"updated_at": _now()}
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise BusinessError("invalid_category_name", "Category name cannot be blank")
        update_data["name"] = normalized_name
    if display_order is not None:
        update_data["display_order"] = display_order
    if status is not None:
        update_data["status"] = status

    session.execute(
        sa.update(models.product_categories)
        .where(models.product_categories.c.id == category_id)
        .values(**update_data)
    )
    _audit(
        session,
        action="category.updated",
        entity_type="category",
        entity_id=category_id,
        payload=update_data,
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": category_id, **update_data}


def _category_option_group_row(session: Session, group_id: str) -> dict[str, Any]:
    group = (
        session.execute(
            sa.select(models.category_option_groups).where(
                models.category_option_groups.c.id == group_id,
                models.category_option_groups.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not group:
        raise NotFoundError(
            "category_option_group_not_found", "No se encontró el selector de categoría"
        )
    return dict(group)


def _normalize_category_option_code(value: Any, code: str) -> str:
    normalized = str(value or "").strip().lower()
    if not CATEGORY_OPTION_CODE_PATTERN.fullmatch(normalized):
        raise BusinessError(code, "El código debe usar minúsculas, números, guion o guion bajo")
    return normalized


def _normalize_category_option_status(value: Any, code: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in {"active", "inactive", "archived"}:
        raise BusinessError(code, "El estado no es válido")
    return normalized


def _normalize_category_option_order(value: Any, code: str) -> int:
    if isinstance(value, bool):
        raise BusinessError(code, "El orden debe ser un entero")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise BusinessError(code, "El orden debe ser un entero") from exc
    if normalized < 0 or normalized > 100000:
        raise BusinessError(code, "El orden está fuera de rango")
    return normalized


def _commit_category_option(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise BusinessError(
            "category_option_duplicate", "Ya existe una configuración u opción con ese código"
        ) from exc


def category_option_coverage(
    session: Session, category_id: str, actor_user_id: str | None = None
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    category = session.execute(
        sa.select(models.product_categories.c.id).where(
            models.product_categories.c.id == category_id,
            models.product_categories.c.organization_id == ORGANIZATION_ID,
        )
    ).scalar_one_or_none()
    if not category:
        raise NotFoundError("category_not_found", "No se encontró la categoría")
    group = (
        session.execute(
            sa.select(models.category_option_groups).where(
                models.category_option_groups.c.category_id == category_id,
                models.category_option_groups.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not group:
        return {
            "category_id": category_id,
            "group": None,
            "values": [],
            "products": [],
            "complete": True,
            "incomplete_products": [],
        }
    values = (
        session.execute(
            sa.select(models.category_option_values)
            .where(models.category_option_values.c.group_id == group["id"])
            .order_by(
                models.category_option_values.c.display_order, models.category_option_values.c.name
            )
        )
        .mappings()
        .all()
    )
    products = (
        session.execute(
            sa.select(models.products.c.id, models.products.c.name, models.products.c.sku)
            .where(
                models.products.c.organization_id == ORGANIZATION_ID,
                models.products.c.category_id == category_id,
                models.products.c.status == "active",
            )
            .order_by(models.products.c.name)
        )
        .mappings()
        .all()
    )
    assignments = (
        session.execute(
            sa.select(
                models.product_option_value_assignments.c.product_id,
                models.product_option_value_assignments.c.option_value_id,
            ).where(models.product_option_value_assignments.c.group_id == group["id"])
        )
        .mappings()
        .all()
    )
    assignment_by_product = {row["product_id"]: row["option_value_id"] for row in assignments}
    value_by_id = {row["id"]: dict(row) for row in values}
    coverage_products = []
    for product in products:
        assigned_value = value_by_id.get(assignment_by_product.get(product["id"], ""))
        assignment = (
            None
            if not assigned_value
            else {
                "value_id": assigned_value["id"],
                "value_code": assigned_value["code"],
                "value_name": assigned_value["name"],
                "value_status": assigned_value["status"],
            }
        )
        coverage_products.append(
            {
                **dict(product),
                "assignment": assignment,
                "incomplete": assignment is None or assignment["value_status"] != "active",
            }
        )
    incomplete = [product for product in coverage_products if product["incomplete"]]
    return {
        "category_id": category_id,
        "group": {
            "id": group["id"],
            "code": group["code"],
            "name": group["name"],
            "status": group["status"],
        },
        "values": [
            {
                "id": row["id"],
                "code": row["code"],
                "name": row["name"],
                "display_order": row["display_order"],
                "status": row["status"],
            }
            for row in values
        ],
        "complete": not incomplete,
        "incomplete_products": incomplete,
        "products": coverage_products,
    }


def get_category_option_group_coverage(
    session: Session, group_id: str, actor_user_id: str | None = None
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    group = _category_option_group_row(session, group_id)
    return category_option_coverage(session, group["category_id"], actor_id)


def upsert_category_option_group(
    session: Session, category_id: str, payload: dict[str, Any], actor_user_id: str | None = None
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    category = (
        session.execute(
            sa.select(models.product_categories).where(
                models.product_categories.c.id == category_id,
                models.product_categories.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not category:
        raise NotFoundError("category_not_found", "No se encontró la categoría")
    code = _normalize_category_option_code(
        payload.get("code"), "category_option_group_invalid_code"
    )
    name = str(payload.get("name", "")).strip()
    if not name or len(name) > 120:
        raise BusinessError(
            "category_option_group_invalid", "Código y nombre del selector son obligatorios"
        )
    status = _normalize_category_option_status(
        payload.get("status", "inactive"), "category_option_group_invalid_status"
    )
    if (
        payload.get("selection_mode", "single") != "single"
        or payload.get("is_required", True) is not True
    ):
        raise BusinessError(
            "category_option_group_invariant", "El selector debe ser único y obligatorio"
        )
    now = _now()
    existing = (
        session.execute(
            sa.select(models.category_option_groups).where(
                models.category_option_groups.c.organization_id == ORGANIZATION_ID,
                models.category_option_groups.c.category_id == category_id,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        group_id = existing["id"]
        if status == "active":
            coverage = category_option_coverage(session, category_id, actor_id)
            if not coverage["complete"]:
                raise BusinessError(
                    "category_option_group_incomplete",
                    "Asigna todos los productos activos antes de activar el selector",
                )
        session.execute(
            sa.update(models.category_option_groups)
            .where(models.category_option_groups.c.id == group_id)
            .values(
                code=code,
                name=name,
                display_order=_normalize_category_option_order(
                    payload.get("display_order", existing["display_order"]),
                    "category_option_group_invalid_order",
                ),
                selection_mode="single",
                is_required=True,
                status=status,
                updated_at=now,
            )
        )
        action = "category_option_group.updated"
    else:
        if status == "active":
            raise BusinessError(
                "category_option_group_incomplete",
                "Crea valores y asignaciones antes de activar el selector",
            )
        group_id = _id()
        session.execute(
            models.category_option_groups.insert().values(
                id=group_id,
                organization_id=ORGANIZATION_ID,
                category_id=category_id,
                code=code,
                name=name,
                selection_mode="single",
                is_required=True,
                display_order=_normalize_category_option_order(
                    payload.get("display_order", 0), "category_option_group_invalid_order"
                ),
                status=status,
                created_at=now,
                updated_at=now,
            )
        )
        action = "category_option_group.created"
    _audit(
        session,
        action=action,
        entity_type="category_option_group",
        entity_id=group_id,
        payload={"category_id": category_id, "status": status},
        actor_user_id=actor_id,
    )
    _commit_category_option(session)
    return {
        "id": group_id,
        "category_id": category_id,
        "code": code,
        "name": name,
        "status": status,
    }


def upsert_category_option_value(
    session: Session,
    group_id: str,
    payload: dict[str, Any],
    value_id: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    group = _category_option_group_row(session, group_id)
    code = _normalize_category_option_code(
        payload.get("code"), "category_option_value_invalid_code"
    )
    name = str(payload.get("name", "")).strip()
    status = _normalize_category_option_status(
        payload.get("status", "active"), "category_option_value_invalid_status"
    )
    if not name or len(name) > 120:
        raise BusinessError(
            "category_option_value_invalid", "Código, nombre o estado de opción no es válido"
        )
    now = _now()
    duplicate = session.execute(
        sa.select(models.category_option_values.c.id).where(
            models.category_option_values.c.group_id == group_id,
            models.category_option_values.c.code == code,
        )
    ).scalar_one_or_none()
    if duplicate and duplicate != value_id:
        raise BusinessError(
            "category_option_duplicate", "Ya existe una configuración u opción con ese código"
        )
    if value_id:
        value = (
            session.execute(
                sa.select(models.category_option_values).where(
                    models.category_option_values.c.id == value_id,
                    models.category_option_values.c.group_id == group_id,
                )
            )
            .mappings()
            .first()
        )
        if not value:
            raise NotFoundError("category_option_value_not_found", "No se encontró la opción")
        if group["status"] == "active" and status != "active":
            affected = session.execute(
                sa.select(models.products.c.id)
                .select_from(
                    models.products.join(
                        models.product_option_value_assignments,
                        models.products.c.id
                        == models.product_option_value_assignments.c.product_id,
                    )
                )
                .where(
                    models.product_option_value_assignments.c.group_id == group_id,
                    models.product_option_value_assignments.c.option_value_id == value_id,
                    models.products.c.organization_id == ORGANIZATION_ID,
                    models.products.c.status == "active",
                )
                .limit(1)
            ).scalar_one_or_none()
            if affected:
                raise BusinessError(
                    "category_option_value_required_by_active_group",
                    "No se puede desactivar una opción asignada en un selector activo",
                )
        session.execute(
            sa.update(models.category_option_values)
            .where(models.category_option_values.c.id == value_id)
            .values(
                code=code,
                name=name,
                display_order=_normalize_category_option_order(
                    payload.get("display_order", value["display_order"]),
                    "category_option_value_invalid_order",
                ),
                status=status,
                updated_at=now,
            )
        )
        action = "category_option_value.updated"
    else:
        value_id = _id()
        session.execute(
            models.category_option_values.insert().values(
                id=value_id,
                group_id=group_id,
                code=code,
                name=name,
                display_order=_normalize_category_option_order(
                    payload.get("display_order", 0), "category_option_value_invalid_order"
                ),
                status=status,
                created_at=now,
                updated_at=now,
            )
        )
        action = "category_option_value.created"
    _audit(
        session,
        action=action,
        entity_type="category_option_value",
        entity_id=value_id,
        payload={"group_id": group_id, "status": status},
        actor_user_id=actor_id,
    )
    _commit_category_option(session)
    return {"id": value_id, "group_id": group_id, "code": code, "name": name, "status": status}


def assign_product_category_option(
    session: Session,
    group_id: str,
    product_id: str,
    option_value_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    group = _category_option_group_row(session, group_id)
    product = (
        session.execute(sa.select(models.products).where(models.products.c.id == product_id))
        .mappings()
        .first()
    )
    value = (
        session.execute(
            sa.select(models.category_option_values).where(
                models.category_option_values.c.id == option_value_id
            )
        )
        .mappings()
        .first()
    )
    if (
        not product
        or product["organization_id"] != ORGANIZATION_ID
        or product["category_id"] != group["category_id"]
    ):
        raise BusinessError(
            "category_option_product_invalid",
            "El producto no pertenece a la categoría del selector",
        )
    if not value or value["group_id"] != group_id:
        raise BusinessError(
            "category_option_value_group_mismatch", "La opción no pertenece al selector"
        )
    if value["status"] != "active":
        raise BusinessError(
            "category_option_value_inactive", "La opción debe estar activa para asignar productos"
        )
    now = _now()
    existing = session.execute(
        sa.select(models.product_option_value_assignments.c.id).where(
            models.product_option_value_assignments.c.product_id == product_id,
            models.product_option_value_assignments.c.group_id == group_id,
        )
    ).scalar_one_or_none()
    if existing:
        session.execute(
            sa.update(models.product_option_value_assignments)
            .where(models.product_option_value_assignments.c.id == existing)
            .values(option_value_id=option_value_id, updated_at=now)
        )
        assignment_id, action = existing, "category_option_assignment.reassigned"
    else:
        assignment_id, action = _id(), "category_option_assignment.created"
        session.execute(
            models.product_option_value_assignments.insert().values(
                id=assignment_id,
                product_id=product_id,
                group_id=group_id,
                option_value_id=option_value_id,
                created_at=now,
                updated_at=now,
            )
        )
    _audit(
        session,
        action=action,
        entity_type="product_option_value_assignment",
        entity_id=assignment_id,
        payload={
            "group_id": group_id,
            "product_id": product_id,
            "option_value_id": option_value_id,
        },
        actor_user_id=actor_id,
    )
    _commit_category_option(session)
    return {
        "id": assignment_id,
        "product_id": product_id,
        "group_id": group_id,
        "option_value_id": option_value_id,
    }


def update_product_recipe(
    session: Session,
    product_id: str,
    components: list[dict[str, Any]],
    yield_quantity: Any = 1,
    yield_unit_id: str = "",
    branch_id: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    product = session.execute(
        sa.select(models.products.c.id).where(
            models.products.c.id == product_id,
            models.products.c.organization_id == ORGANIZATION_ID,
        )
    ).scalar_one_or_none()
    if not product:
        raise BusinessError("product_not_found", "Product was not found")
    normalized_yield = _quantity(yield_quantity)
    if normalized_yield <= 0:
        raise BusinessError("invalid_recipe_yield", "Recipe yield must be positive")
    if not yield_unit_id:
        yield_unit_id = str(
            session.execute(sa.select(models.inventory_units.c.id).limit(1)).scalar_one()
        )
    component_rows = _normalize_recipe_components(session, components)
    now = _now()
    max_version = (
        session.execute(
            sa.select(sa.func.max(models.recipes.c.version)).where(
                models.recipes.c.product_id == product_id
            )
        ).scalar()
        or 0
    )
    recipe_id = _id()
    session.execute(
        sa.update(models.recipes)
        .where(
            models.recipes.c.product_id == product_id,
            models.recipes.c.status == "active",
            models.recipes.c.branch_id.is_(branch_id)
            if branch_id is None
            else models.recipes.c.branch_id == branch_id,
        )
        .values(status="retired", valid_to=now, updated_at=now)
    )
    recipe = {
        "id": recipe_id,
        "organization_id": ORGANIZATION_ID,
        "product_id": product_id,
        "output_item_id": None,
        "branch_id": branch_id,
        "recipe_type": "sale",
        "version": int(max_version) + 1,
        "status": "active",
        "yield_quantity": normalized_yield,
        "yield_unit_id": yield_unit_id,
        "valid_from": now,
        "valid_to": None,
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.recipes.insert().values(**recipe))
    for row in component_rows:
        session.execute(models.recipe_components.insert().values(recipe_id=recipe_id, **row))
    cost = calculate_recipe_cost(session, recipe_id, branch_id or BRANCH_ID, actor_id, persist=True)
    _audit(
        session,
        action="recipe.updated",
        entity_type="product",
        entity_id=product_id,
        payload={"recipe_id": recipe_id, "version": recipe["version"], "branch_id": branch_id},
        actor_user_id=actor_id,
    )
    session.commit()
    return {**recipe, "components": component_rows, "cost": cost}


def _recipe_command_hash(
    product_id: str,
    payload: dict[str, Any],
    branch_id: str | None,
    expected_active_recipe_id: str | None,
) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "product_id": product_id,
                "branch_id": branch_id,
                "expected_active_recipe_id": expected_active_recipe_id,
                "payload": payload,
            },
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _recipe_response(recipe: dict[str, Any], components: list[dict[str, Any]]) -> dict[str, Any]:
    return {**recipe, "components": components}


def get_effective_product_recipe(
    session: Session, product_id: str, branch_id: str | None, actor_user_id: str
) -> dict[str, Any] | None:
    if branch_id is None and not actor_has_organization_authority(
        session, _actor_user_id(actor_user_id)
    ):
        raise AuthorizationError("recipe_branch_required", "A branch is required for this actor")
    scope = authorize_branch_scope(
        session, _actor_user_id(actor_user_id), "recipes.manage", branch_id
    )
    product = (
        session.execute(
            sa.select(models.products.c.catalog_scope, models.products.c.source_branch_id).where(
                models.products.c.id == product_id,
                models.products.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not product:
        raise BusinessError("product_not_found", "Product was not found")
    if product["catalog_scope"] != "organization" and (
        scope is None or product["source_branch_id"] != scope
    ):
        raise BusinessError("recipe_product_scope_invalid", "Product is outside recipe scope")
    rows = (
        session.execute(
            sa.select(models.recipes)
            .where(
                models.recipes.c.organization_id == ORGANIZATION_ID,
                models.recipes.c.product_id == product_id,
                models.recipes.c.status == "active",
                sa.or_(models.recipes.c.branch_id == scope, models.recipes.c.branch_id.is_(None)),
            )
            .order_by(sa.case((models.recipes.c.branch_id == scope, 0), else_=1))
        )
        .mappings()
        .all()
    )
    if not rows:
        return None
    recipe = dict(rows[0])
    components = [
        dict(row)
        for row in session.execute(
            sa.select(models.recipe_components)
            .where(models.recipe_components.c.recipe_id == recipe["id"])
            .order_by(models.recipe_components.c.sort_order)
        ).mappings()
    ]
    latest_cost = None
    if branch_id is not None:
        cost = (
            session.execute(
                sa.select(models.recipe_cost_calculations)
                .where(
                    models.recipe_cost_calculations.c.recipe_id == recipe["id"],
                    models.recipe_cost_calculations.c.branch_id == branch_id,
                )
                .order_by(models.recipe_cost_calculations.c.calculated_at.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if cost:
            latest_cost = {
                key: cost[key]
                for key in ("cost_before_waste", "waste_cost", "total_cost", "cost_per_yield_unit")
            }
    return {
        **_recipe_response(recipe, components),
        "source": "branch" if recipe["branch_id"] else "organization",
        "latest_cost": latest_cost,
    }


@_pco007_observed(
    "pco007.recipe.version", lambda session, product_id, payload, branch_id, *rest: branch_id
)
def update_product_recipe_versioned(
    session: Session,
    product_id: str,
    payload: dict[str, Any],
    branch_id: str | None,
    expected_active_recipe_id: str | None,
    idempotency_key: str,
    actor_user_id: str,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    if not isinstance(payload, dict) or "components" not in payload:
        raise BusinessError("recipe_payload_invalid", "Recipe payload must include components")
    unsupported_fields = set(payload) - {"yield_quantity", "yield_unit_id", "components"}
    if unsupported_fields:
        raise BusinessError("recipe_payload_invalid", "Recipe payload has unsupported fields")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise BusinessError("idempotency_key_required", "Idempotency-Key is required")

    # Resolve yield unit with fallback to PZA or first organization unit
    yield_unit_id = str(payload.get("yield_unit_id") or "")
    unit_row = None
    if yield_unit_id:
        unit_row = session.execute(
            sa.select(models.inventory_units.c.id).where(
                models.inventory_units.c.id == yield_unit_id,
                models.inventory_units.c.organization_id == ORGANIZATION_ID,
            )
        ).scalar_one_or_none()
    if not unit_row:
        pza_unit = session.execute(
            sa.select(models.inventory_units.c.id).where(
                models.inventory_units.c.organization_id == ORGANIZATION_ID,
                sa.func.upper(models.inventory_units.c.code) == "PZA",
            )
        ).scalar_one_or_none()
        if not pza_unit:
            pza_unit = (
                session.execute(
                    sa.select(models.inventory_units.c.id).where(
                        models.inventory_units.c.organization_id == ORGANIZATION_ID
                    )
                )
                .scalars()
                .first()
            )
        yield_unit_id = pza_unit or ""

    clean_payload = {
        "yield_quantity": payload.get("yield_quantity", 1),
        "yield_unit_id": yield_unit_id,
        "components": payload["components"],
    }

    if branch_id is None:
        if not actor_has_organization_authority(session, actor_id):
            require_permission(session, actor_id, "recipes.manage", BRANCH_ID)
    else:
        authorize_branch_scope(session, actor_id, "recipes.manage", branch_id)
    request_hash = _recipe_command_hash(
        product_id, clean_payload, branch_id, expected_active_recipe_id
    )
    existing = (
        session.execute(
            sa.select(models.recipe_version_commands).where(
                models.recipe_version_commands.c.organization_id == ORGANIZATION_ID,
                models.recipe_version_commands.c.idempotency_key == idempotency_key,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        if existing["request_hash"] != request_hash or existing["actor_user_id"] != actor_id:
            raise BusinessError(
                "idempotency_conflict", "Idempotency key belongs to another command"
            )
        return dict(existing["result"])
    product = (
        session.execute(
            sa.select(
                models.products.c.id,
                models.products.c.catalog_scope,
                models.products.c.source_branch_id,
            )
            .where(
                models.products.c.id == product_id,
                models.products.c.organization_id == ORGANIZATION_ID,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not product:
        raise BusinessError("product_not_found", "Product was not found")
    if product["catalog_scope"] != "organization" and (
        branch_id is None or product["source_branch_id"] != branch_id
    ):
        raise BusinessError("recipe_product_scope_invalid", "Product is outside recipe scope")
    # PostgreSQL row locking serializes writers for a product. Re-read the command after
    # acquiring that lock so a same-key waiter replays before expected-version validation.
    existing = (
        session.execute(
            sa.select(models.recipe_version_commands).where(
                models.recipe_version_commands.c.organization_id == ORGANIZATION_ID,
                models.recipe_version_commands.c.idempotency_key == idempotency_key,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        if existing["request_hash"] != request_hash or existing["actor_user_id"] != actor_id:
            raise BusinessError(
                "idempotency_conflict", "Idempotency key belongs to another command"
            )
        _record_pco007_metric(
            "pco007.recipe.version", result="replay", branch_id=branch_id, duration_ms=0
        )
        return dict(existing["result"])
    normalized_yield = _quantity(clean_payload["yield_quantity"])
    if normalized_yield <= 0:
        raise BusinessError("invalid_recipe_yield", "Recipe yield must be positive")
    if not yield_unit_id:
        raise BusinessError("recipe_yield_unit_invalid", "Recipe yield unit is invalid")
    components = _normalize_recipe_components(
        session, clean_payload["components"], branch_id=branch_id
    )
    active = (
        session.execute(
            sa.select(models.recipes)
            .where(
                models.recipes.c.product_id == product_id,
                models.recipes.c.status == "active",
                models.recipes.c.branch_id.is_(branch_id)
                if branch_id is None
                else models.recipes.c.branch_id == branch_id,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if (active["id"] if active else None) != expected_active_recipe_id:
        raise BusinessError("recipe_version_conflict", "Active recipe changed")
    now = _now()
    version = (
        int(
            session.execute(
                sa.select(sa.func.coalesce(sa.func.max(models.recipes.c.version), 0)).where(
                    models.recipes.c.product_id == product_id
                )
            ).scalar_one()
        )
        + 1
    )
    recipe = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "product_id": product_id,
        "output_item_id": None,
        "branch_id": branch_id,
        "recipe_type": "sale",
        "version": version,
        "status": "active",
        "yield_quantity": normalized_yield,
        "yield_unit_id": yield_unit_id,
        "valid_from": now,
        "valid_to": None,
        "created_at": now,
        "updated_at": now,
    }
    if active:
        session.execute(
            sa.update(models.recipes)
            .where(models.recipes.c.id == active["id"])
            .values(status="retired", valid_to=now, updated_at=now)
        )
    session.execute(models.recipes.insert().values(**recipe))
    for component in components:
        session.execute(
            models.recipe_components.insert().values(recipe_id=recipe["id"], **component)
        )
    result = _recipe_response(recipe, components)
    try:
        session.execute(
            models.recipe_version_commands.insert().values(
                id=_id(),
                organization_id=ORGANIZATION_ID,
                actor_user_id=actor_id,
                product_id=product_id,
                branch_id=branch_id,
                recipe_id=recipe["id"],
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                result=_sanitize_for_json(result),
                created_at=now,
            )
        )
        _audit(
            session,
            "recipe.versioned",
            "recipe",
            recipe["id"],
            {"product_id": product_id, "version": version, "branch_id": branch_id},
            branch_id=branch_id,
            actor_user_id=actor_id,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raced = (
            session.execute(
                sa.select(models.recipe_version_commands).where(
                    models.recipe_version_commands.c.organization_id == ORGANIZATION_ID,
                    models.recipe_version_commands.c.idempotency_key == idempotency_key,
                )
            )
            .mappings()
            .first()
        )
        if raced and raced["request_hash"] == request_hash and raced["actor_user_id"] == actor_id:
            _record_pco007_metric(
                "pco007.recipe.version", result="replay", branch_id=branch_id, duration_ms=0
            )
            return dict(raced["result"])
        if raced:
            raise BusinessError(
                "idempotency_conflict", "Idempotency key belongs to another command"
            ) from exc
        raise
    _record_pco007_metric(
        "pco007.recipe.version", result="success", branch_id=branch_id, duration_ms=0
    )
    return result


def create_modifier_group(
    session: Session,
    product_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    product = session.execute(
        sa.select(models.products.c.id)
        .where(
            models.products.c.id == product_id,
            models.products.c.organization_id == ORGANIZATION_ID,
            models.products.c.status == "active",
        )
        .with_for_update()
    ).scalar_one_or_none()
    if not product:
        raise BusinessError("product_not_found", "Product was not found")
    name = str(payload.get("name", "")).strip()
    minimum = int(payload.get("minimum_selections", 1 if payload.get("is_required") else 0))
    maximum = int(payload.get("maximum_selections", 1))
    required = bool(payload.get("is_required", minimum > 0))
    if not name or minimum < 0 or maximum < 1 or minimum > maximum or (required and minimum < 1):
        raise BusinessError(
            "invalid_modifier_group", "Modifier group name and valid minimum/maximum are required"
        )
    duplicate = session.execute(
        sa.select(models.modifier_groups.c.id).where(
            models.modifier_groups.c.product_id == product_id,
            models.modifier_groups.c.name == name,
        )
    ).scalar_one_or_none()
    if duplicate:
        raise BusinessError(
            "modifier_group_name_conflict",
            "An active or archived modifier group already uses this name",
        )
    now = _now()
    created_group: dict[str, Any] = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "product_id": product_id,
        "name": name,
        "is_required": required,
        "minimum_selections": minimum,
        "maximum_selections": maximum,
        "station": payload.get("station"),
        "display_order": int(payload.get("display_order", 0)),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.modifier_groups.insert().values(**created_group))
    _audit(
        session,
        "modifier_group.created",
        "modifier_group",
        created_group["id"],
        {"product_id": product_id, "minimum": minimum, "maximum": maximum},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return {**created_group, "options": []}


def _modifier_catalog_is_managed_elsewhere(
    session: Session,
    *,
    option_id: str | None = None,
    group_id: str | None = None,
) -> bool:
    option_filter = (
        models.modifier_options.c.id == option_id
        if option_id is not None
        else models.modifier_options.c.group_id == group_id
    )
    preset = session.execute(
        sa.select(models.modifier_options.c.id)
        .where(option_filter, models.modifier_options.c.effect_type == "preset_instruction")
        .limit(1)
    ).first()
    if preset:
        return True
    linked = session.execute(
        sa.select(models.ingredient_variation_products.c.id)
        .select_from(
            models.ingredient_variation_products.join(
                models.modifier_options,
                sa.or_(
                    models.ingredient_variation_products.c.add_option_id
                    == models.modifier_options.c.id,
                    models.ingredient_variation_products.c.remove_option_id
                    == models.modifier_options.c.id,
                ),
            )
        )
        .where(option_filter)
        .limit(1)
    ).first()
    return linked is not None


def _lock_active_modifier_option(
    session: Session,
    option_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    group_id = session.execute(
        sa.select(models.modifier_options.c.group_id)
        .select_from(
            models.modifier_options.join(
                models.modifier_groups,
                models.modifier_groups.c.id == models.modifier_options.c.group_id,
            )
        )
        .where(
            models.modifier_options.c.id == option_id,
            models.modifier_options.c.status == "active",
            models.modifier_groups.c.organization_id == ORGANIZATION_ID,
            models.modifier_groups.c.status == "active",
        )
    ).scalar_one_or_none()
    if not group_id:
        return None, None
    group = (
        session.execute(
            sa.select(models.modifier_groups)
            .where(
                models.modifier_groups.c.id == group_id,
                models.modifier_groups.c.organization_id == ORGANIZATION_ID,
                models.modifier_groups.c.status == "active",
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not group:
        return None, None
    option = (
        session.execute(
            sa.select(models.modifier_options)
            .where(
                models.modifier_options.c.id == option_id,
                models.modifier_options.c.group_id == group_id,
                models.modifier_options.c.status == "active",
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    return (dict(option), dict(group)) if option else (None, None)


def create_modifier_option(
    session: Session,
    group_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    group = (
        session.execute(
            sa.select(models.modifier_groups)
            .where(
                models.modifier_groups.c.id == group_id,
                models.modifier_groups.c.organization_id == ORGANIZATION_ID,
                models.modifier_groups.c.status == "active",
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not group:
        raise BusinessError("modifier_group_not_found", "Modifier group was not found")
    if _modifier_catalog_is_managed_elsewhere(session, group_id=group_id):
        raise BusinessError(
            "modifier_catalog_managed_elsewhere",
            "This modifier group is managed by its canonical catalog",
        )
    effect = str(payload.get("effect_type", "instruction")).lower()
    allowed = {"remove", "add", "substitute", "quantity", "variant", "instruction"}
    name = str(payload.get("name", "")).strip()
    affected = payload.get("affected_item_id") or None
    replacement = payload.get("replacement_item_id") or None
    remove_quantity = _quantity(payload.get("remove_quantity", 0))
    add_quantity = _quantity(payload.get("add_quantity", 0))
    if not name or effect not in allowed or remove_quantity < 0 or add_quantity < 0:
        raise BusinessError("invalid_modifier_option", "Modifier option fields are invalid")
    duplicate = session.execute(
        sa.select(models.modifier_options.c.id).where(
            models.modifier_options.c.group_id == group_id,
            models.modifier_options.c.name == name,
        )
    ).scalar_one_or_none()
    if duplicate:
        raise BusinessError(
            "modifier_option_name_conflict",
            "An active or archived modifier option already uses this name",
        )
    if effect in {"remove", "quantity", "substitute", "variant"} and not affected:
        raise BusinessError("modifier_affected_item_required", "Modifier requires an affected item")
    if effect in {"substitute", "variant"} and not replacement:
        raise BusinessError(
            "modifier_replacement_item_required", "Substitution requires a replacement item"
        )
    if effect == "add" and not (replacement or affected):
        raise BusinessError(
            "modifier_added_item_required", "Add modifier requires an inventory item"
        )
    item_ids = [str(item_id) for item_id in (affected, replacement) if item_id]
    if item_ids:
        found = set(
            session.execute(
                sa.select(models.inventory_items.c.id).where(
                    models.inventory_items.c.id.in_(item_ids),
                    models.inventory_items.c.organization_id == ORGANIZATION_ID,
                    models.inventory_items.c.status == "active",
                )
            ).scalars()
        )
        if found != set(item_ids):
            raise BusinessError("modifier_item_not_found", "Modifier inventory item was not found")
    now = _now()
    option = {
        "id": _id(),
        "group_id": group_id,
        "name": name,
        "effect_type": effect,
        "price_delta_cents": int(payload.get("price_delta_cents", 0)),
        "affected_item_id": affected,
        "replacement_item_id": replacement,
        "remove_quantity": remove_quantity,
        "add_quantity": add_quantity,
        "inventory_effect": bool(payload.get("inventory_effect", effect != "instruction")),
        "kitchen_text": str(payload.get("kitchen_text") or name).strip(),
        "station": payload.get("station") or group["station"],
        "display_order": int(payload.get("display_order", 0)),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.modifier_options.insert().values(**option))
    _audit(
        session,
        "modifier_option.created",
        "modifier_option",
        option["id"],
        {"group_id": group_id, "effect_type": effect},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return option


def update_modifier_group(
    session: Session,
    group_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    group = (
        session.execute(
            sa.select(models.modifier_groups)
            .where(
                models.modifier_groups.c.id == group_id,
                models.modifier_groups.c.status == "active",
                models.modifier_groups.c.organization_id == ORGANIZATION_ID,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not group:
        raise BusinessError("modifier_group_not_found", "Modifier group was not found")
    if _modifier_catalog_is_managed_elsewhere(session, group_id=group_id):
        raise BusinessError(
            "modifier_catalog_managed_elsewhere",
            "This modifier group is managed by its canonical catalog",
        )

    name = str(payload.get("name", group["name"])).strip()
    minimum = int(payload.get("minimum_selections", group["minimum_selections"]))
    maximum = int(payload.get("maximum_selections", group["maximum_selections"]))
    is_required = bool(payload.get("is_required", group["is_required"]))

    if not name or minimum < 0 or maximum < 0 or maximum < minimum:
        raise BusinessError("invalid_modifier_group", "Modifier group fields are invalid")
    if is_required and minimum == 0:
        raise BusinessError(
            "invalid_modifier_group", "Required groups must have a minimum selection > 0"
        )
    active_option_count = session.execute(
        sa.select(sa.func.count())
        .select_from(models.modifier_options)
        .where(
            models.modifier_options.c.group_id == group_id,
            models.modifier_options.c.status == "active",
        )
    ).scalar_one()
    if minimum > int(active_option_count):
        raise BusinessError(
            "modifier_group_cardinality_conflict",
            "Group minimum cannot exceed its active options",
        )
    duplicate = session.execute(
        sa.select(models.modifier_groups.c.id).where(
            models.modifier_groups.c.product_id == group["product_id"],
            models.modifier_groups.c.name == name,
            models.modifier_groups.c.id != group_id,
        )
    ).scalar_one_or_none()
    if duplicate:
        raise BusinessError(
            "modifier_group_name_conflict", "Another modifier group already uses this name"
        )

    now = _now()
    update_values = {
        "name": name,
        "is_required": is_required,
        "minimum_selections": minimum,
        "maximum_selections": maximum,
        "station": payload.get("station") or group["station"],
        "display_order": int(payload.get("display_order", group["display_order"])),
        "updated_at": now,
    }

    session.execute(
        models.modifier_groups.update()
        .where(models.modifier_groups.c.id == group_id)
        .values(**update_values)
    )

    _audit(
        session,
        "modifier_group.updated",
        "modifier_group",
        group_id,
        update_values,
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()

    groups = list_product_modifiers(session, group["product_id"])
    return next(g for g in groups if g["id"] == group_id)


def archive_modifier_group(
    session: Session,
    group_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    group = (
        session.execute(
            sa.select(models.modifier_groups)
            .where(
                models.modifier_groups.c.id == group_id,
                models.modifier_groups.c.status == "active",
                models.modifier_groups.c.organization_id == ORGANIZATION_ID,
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not group:
        raise BusinessError("modifier_group_not_found", "Modifier group was not found")
    if _modifier_catalog_is_managed_elsewhere(session, group_id=group_id):
        raise BusinessError(
            "modifier_catalog_managed_elsewhere",
            "This modifier group is managed by its canonical catalog",
        )

    now = _now()
    archived_options = session.execute(
        models.modifier_options.update()
        .where(
            models.modifier_options.c.group_id == group_id,
            models.modifier_options.c.status == "active",
        )
        .values(status="archived", updated_at=now)
    )
    session.execute(
        models.modifier_groups.update()
        .where(models.modifier_groups.c.id == group_id)
        .values(status="archived", updated_at=now)
    )

    archived_option_count = int(getattr(archived_options, "rowcount", 0) or 0)
    _audit(
        session,
        "modifier_group.archived",
        "modifier_group",
        group_id,
        {"product_id": group["product_id"], "archived_option_count": archived_option_count},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return {
        **dict(group),
        "status": "archived",
        "updated_at": now,
        "archived_option_count": archived_option_count,
    }


def update_modifier_option(
    session: Session,
    option_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    option, _group = _lock_active_modifier_option(session, option_id)
    if not option:
        raise BusinessError("modifier_option_not_found", "Modifier option was not found")
    if _modifier_catalog_is_managed_elsewhere(session, option_id=option_id):
        raise BusinessError(
            "modifier_catalog_managed_elsewhere",
            "This modifier option is managed by its canonical catalog",
        )

    effect = str(payload.get("effect_type", option["effect_type"])).lower()
    allowed = {"remove", "add", "substitute", "quantity", "variant", "instruction"}
    name = str(payload.get("name", option["name"])).strip()
    affected = payload.get("affected_item_id") or option["affected_item_id"]
    replacement = payload.get("replacement_item_id") or option["replacement_item_id"]
    remove_quantity = _quantity(payload.get("remove_quantity", option["remove_quantity"]))
    add_quantity = _quantity(payload.get("add_quantity", option["add_quantity"]))

    if not name or effect not in allowed or remove_quantity < 0 or add_quantity < 0:
        raise BusinessError("invalid_modifier_option", "Modifier option fields are invalid")
    if effect in {"remove", "quantity", "substitute", "variant"} and not affected:
        raise BusinessError("modifier_affected_item_required", "Modifier requires an affected item")
    if effect in {"substitute", "variant"} and not replacement:
        raise BusinessError(
            "modifier_replacement_item_required", "Substitution requires a replacement item"
        )
    if effect == "add" and not (replacement or affected):
        raise BusinessError(
            "modifier_added_item_required", "Add modifier requires an inventory item"
        )

    item_ids = [str(item_id) for item_id in (affected, replacement) if item_id]
    if item_ids:
        found = set(
            session.execute(
                sa.select(models.inventory_items.c.id).where(
                    models.inventory_items.c.id.in_(item_ids),
                    models.inventory_items.c.organization_id == ORGANIZATION_ID,
                    models.inventory_items.c.status == "active",
                )
            ).scalars()
        )
        if found != set(item_ids):
            raise BusinessError("modifier_item_not_found", "Modifier inventory item was not found")
    duplicate = session.execute(
        sa.select(models.modifier_options.c.id).where(
            models.modifier_options.c.group_id == option["group_id"],
            models.modifier_options.c.name == name,
            models.modifier_options.c.id != option_id,
        )
    ).scalar_one_or_none()
    if duplicate:
        raise BusinessError(
            "modifier_option_name_conflict", "Another modifier option already uses this name"
        )

    now = _now()
    update_values = {
        "name": name,
        "effect_type": effect,
        "price_delta_cents": int(payload.get("price_delta_cents", option["price_delta_cents"])),
        "affected_item_id": affected,
        "replacement_item_id": replacement,
        "remove_quantity": remove_quantity,
        "add_quantity": add_quantity,
        "inventory_effect": bool(payload.get("inventory_effect", option["inventory_effect"])),
        "kitchen_text": str(payload.get("kitchen_text") or name).strip(),
        "station": payload.get("station") or option["station"],
        "display_order": int(payload.get("display_order", option["display_order"])),
        "updated_at": now,
    }

    session.execute(
        models.modifier_options.update()
        .where(models.modifier_options.c.id == option_id)
        .values(**update_values)
    )

    _audit(
        session,
        "modifier_option.updated",
        "modifier_option",
        option_id,
        update_values,
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()

    updated_option = dict(option)
    updated_option.update(update_values)
    return updated_option


def archive_modifier_option(
    session: Session,
    option_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    group_id = session.execute(
        sa.select(models.modifier_options.c.group_id)
        .select_from(
            models.modifier_options.join(
                models.modifier_groups,
                models.modifier_groups.c.id == models.modifier_options.c.group_id,
            )
        )
        .where(
            models.modifier_options.c.id == option_id,
            models.modifier_options.c.status == "active",
            models.modifier_groups.c.organization_id == ORGANIZATION_ID,
            models.modifier_groups.c.status == "active",
        )
    ).scalar_one_or_none()
    if not group_id:
        raise BusinessError("modifier_option_not_found", "Modifier option was not found")

    group = (
        session.execute(
            sa.select(models.modifier_groups)
            .where(
                models.modifier_groups.c.id == group_id,
                models.modifier_groups.c.organization_id == ORGANIZATION_ID,
                models.modifier_groups.c.status == "active",
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    option = (
        session.execute(
            sa.select(models.modifier_options)
            .where(
                models.modifier_options.c.id == option_id,
                models.modifier_options.c.group_id == group_id,
                models.modifier_options.c.status == "active",
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not group or not option:
        raise BusinessError("modifier_option_not_found", "Modifier option was not found")
    if _modifier_catalog_is_managed_elsewhere(session, option_id=option_id):
        raise BusinessError(
            "modifier_catalog_managed_elsewhere",
            "This modifier option is managed by its canonical catalog",
        )

    remaining = session.execute(
        sa.select(sa.func.count())
        .select_from(models.modifier_options)
        .where(
            models.modifier_options.c.group_id == group_id,
            models.modifier_options.c.status == "active",
            models.modifier_options.c.id != option_id,
        )
    ).scalar_one()
    if int(remaining) < int(group["minimum_selections"]):
        raise BusinessError(
            "modifier_group_cardinality_conflict",
            "Edit the group minimum before removing this option",
        )

    now = _now()
    session.execute(
        models.modifier_options.update()
        .where(models.modifier_options.c.id == option_id)
        .values(status="archived", updated_at=now)
    )

    _audit(
        session,
        "modifier_option.archived",
        "modifier_option",
        option_id,
        {"group_id": group_id, "remaining_active_options": int(remaining)},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": option_id, "status": "archived"}


def clone_modifier_group(
    session: Session,
    source_group_id: str,
    target_product_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    source_group = (
        session.execute(
            sa.select(models.modifier_groups).where(
                models.modifier_groups.c.id == source_group_id,
                models.modifier_groups.c.status == "active",
                models.modifier_groups.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not source_group:
        raise BusinessError("modifier_group_not_found", "Source modifier group was not found")

    target_product = (
        session.execute(
            sa.select(models.products).where(
                models.products.c.id == target_product_id,
                models.products.c.organization_id == ORGANIZATION_ID,
                models.products.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not target_product:
        raise BusinessError("product_not_found", "Target product was not found")

    now = _now()
    new_group_id = _id()
    new_group = {
        "id": new_group_id,
        "organization_id": ORGANIZATION_ID,
        "product_id": target_product_id,
        "name": source_group["name"],
        "is_required": source_group["is_required"],
        "minimum_selections": source_group["minimum_selections"],
        "maximum_selections": source_group["maximum_selections"],
        "station": source_group["station"],
        "display_order": source_group["display_order"],
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.modifier_groups.insert().values(**new_group))

    source_options = (
        session.execute(
            sa.select(models.modifier_options).where(
                models.modifier_options.c.group_id == source_group_id,
                models.modifier_options.c.status == "active",
            )
        )
        .mappings()
        .all()
    )

    new_options = []
    for opt in source_options:
        new_opt = {
            "id": _id(),
            "group_id": new_group_id,
            "name": opt["name"],
            "effect_type": opt["effect_type"],
            "price_delta_cents": opt["price_delta_cents"],
            "affected_item_id": opt["affected_item_id"],
            "replacement_item_id": opt["replacement_item_id"],
            "remove_quantity": opt["remove_quantity"],
            "add_quantity": opt["add_quantity"],
            "inventory_effect": opt["inventory_effect"],
            "kitchen_text": opt["kitchen_text"],
            "station": opt["station"],
            "display_order": opt["display_order"],
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        new_options.append(new_opt)

    if new_options:
        session.execute(models.modifier_options.insert().values(new_options))

    _audit(
        session,
        "modifier_group.cloned",
        "modifier_group",
        new_group_id,
        {"source_group_id": source_group_id, "target_product_id": target_product_id},
        actor_user_id=actor_id,
    )
    session.commit()

    groups = list_product_modifiers(session, target_product_id)
    return next(g for g in groups if g["id"] == new_group_id)


def clone_all_modifier_groups(
    session: Session,
    source_product_id: str,
    target_product_id: str,
    actor_user_id: str | None = None,
) -> list[dict[str, Any]]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    source_groups = (
        session.execute(
            sa.select(models.modifier_groups).where(
                models.modifier_groups.c.product_id == source_product_id,
                models.modifier_groups.c.status == "active",
                models.modifier_groups.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .all()
    )

    target_product = (
        session.execute(
            sa.select(models.products).where(
                models.products.c.id == target_product_id,
                models.products.c.organization_id == ORGANIZATION_ID,
                models.products.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not target_product:
        raise BusinessError("product_not_found", "Target product was not found")

    now = _now()
    new_group_ids = []

    for source_group in source_groups:
        new_group_id = _id()
        new_group_ids.append(new_group_id)
        new_group = {
            "id": new_group_id,
            "organization_id": ORGANIZATION_ID,
            "product_id": target_product_id,
            "name": source_group["name"],
            "is_required": source_group["is_required"],
            "minimum_selections": source_group["minimum_selections"],
            "maximum_selections": source_group["maximum_selections"],
            "station": source_group["station"],
            "display_order": source_group["display_order"],
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        session.execute(models.modifier_groups.insert().values(**new_group))

        source_options = (
            session.execute(
                sa.select(models.modifier_options).where(
                    models.modifier_options.c.group_id == source_group["id"],
                    models.modifier_options.c.status == "active",
                )
            )
            .mappings()
            .all()
        )

        new_options = []
        for opt in source_options:
            new_opt = {
                "id": _id(),
                "group_id": new_group_id,
                "name": opt["name"],
                "effect_type": opt["effect_type"],
                "price_delta_cents": opt["price_delta_cents"],
                "affected_item_id": opt["affected_item_id"],
                "replacement_item_id": opt["replacement_item_id"],
                "remove_quantity": opt["remove_quantity"],
                "add_quantity": opt["add_quantity"],
                "inventory_effect": opt["inventory_effect"],
                "kitchen_text": opt["kitchen_text"],
                "station": opt["station"],
                "display_order": opt["display_order"],
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
            new_options.append(new_opt)

        if new_options:
            session.execute(models.modifier_options.insert().values(new_options))

        _audit(
            session,
            "modifier_group.cloned",
            "modifier_group",
            new_group_id,
            {"source_group_id": source_group["id"], "target_product_id": target_product_id},
            actor_user_id=actor_id,
        )

    session.commit()

    groups = list_product_modifiers(session, target_product_id)
    return [g for g in groups if g["id"] in new_group_ids]


def reorder_modifier_groups(
    session: Session,
    product_id: str,
    ordered_group_ids: list[str],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    if not ordered_group_ids:
        return {"status": "ok"}

    found_groups = set(
        session.execute(
            sa.select(models.modifier_groups.c.id).where(
                models.modifier_groups.c.id.in_(ordered_group_ids),
                models.modifier_groups.c.product_id == product_id,
                models.modifier_groups.c.status == "active",
                models.modifier_groups.c.organization_id == ORGANIZATION_ID,
            )
        ).scalars()
    )

    if found_groups != set(ordered_group_ids):
        raise BusinessError(
            "modifier_group_not_found",
            "Some modifier groups were not found or don't belong to the product",
        )

    now = _now()
    for idx, group_id in enumerate(ordered_group_ids):
        session.execute(
            models.modifier_groups.update()
            .where(models.modifier_groups.c.id == group_id)
            .values(display_order=idx, updated_at=now)
        )

    _audit(
        session,
        "modifier_group.reordered",
        "product",
        product_id,
        {"ordered_group_ids": ordered_group_ids},
        actor_user_id=actor_id,
    )
    session.commit()
    return {"status": "ok"}


def reorder_modifier_options(
    session: Session,
    group_id: str,
    ordered_option_ids: list[str],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")

    if not ordered_option_ids:
        return {"status": "ok"}

    # Validate group belongs to this organization
    group = session.execute(
        sa.select(models.modifier_groups.c.id).where(
            models.modifier_groups.c.id == group_id,
            models.modifier_groups.c.status == "active",
            models.modifier_groups.c.organization_id == ORGANIZATION_ID,
        )
    ).scalar_one_or_none()
    if not group:
        raise BusinessError("modifier_group_not_found", "Modifier group was not found")

    found_options = set(
        session.execute(
            sa.select(models.modifier_options.c.id).where(
                models.modifier_options.c.id.in_(ordered_option_ids),
                models.modifier_options.c.group_id == group_id,
                models.modifier_options.c.status == "active",
            )
        ).scalars()
    )

    if found_options != set(ordered_option_ids):
        raise BusinessError(
            "modifier_option_not_found",
            "Some modifier options were not found or don't belong to the group",
        )

    now = _now()
    for idx, option_id in enumerate(ordered_option_ids):
        session.execute(
            models.modifier_options.update()
            .where(models.modifier_options.c.id == option_id)
            .values(display_order=idx, updated_at=now)
        )

    _audit(
        session,
        "modifier_option.reordered",
        "modifier_group",
        group_id,
        {"ordered_option_ids": ordered_option_ids},
        actor_user_id=actor_id,
    )
    session.commit()
    return {"status": "ok"}


INGREDIENT_VARIATION_GROUP = "Cambios de ingredientes"


def _ingredient_variation_labels(
    item_name: str, add_label: Any = None, remove_label: Any = None
) -> tuple[str, str]:
    if add_label is None or remove_label is None:
        raise BusinessError(
            "invalid_ingredient_variation_label",
            "Ingredient variation labels cannot be null",
        )
    item = item_name.strip().lower()
    add = str(add_label).strip() if add_label is not None else f"Con {item}"
    remove = str(remove_label).strip() if remove_label is not None else f"Sin {item}"
    if not add or not remove or len(add) > 120 or len(remove) > 120:
        raise BusinessError(
            "invalid_ingredient_variation_label",
            "Ingredient variation labels must be between 1 and 120 characters",
        )
    return add, remove


def _canonical_extra_values(
    payload: dict[str, Any],
    current: dict[str, Any] | None = None,
    require_complete: bool = False,
) -> dict[str, Any]:
    aliases = {
        "portion_quantity": ("portion_quantity", "portion", "quantity"),
        "sale_price_cents": ("sale_price_cents", "price_cents"),
        "station": ("station",),
        "display_order": ("display_order",),
    }
    values: dict[str, Any] = {}
    supplied = set(payload).intersection({alias for names in aliases.values() for alias in names})
    if not supplied and current is None:
        if require_complete:
            raise BusinessError(
                "ingredient_extra_configuration_required",
                "Portion, price and station are required",
            )
        return values
    for field, names in aliases.items():
        raw = next((payload[name] for name in names if name in payload), None)
        if raw is None and current is not None:
            raw = current.get(field)
        if (
            raw is None
            and require_complete
            and field in {"portion_quantity", "sale_price_cents", "station"}
        ):
            raise BusinessError(
                "ingredient_extra_configuration_required", "Portion, price and station are required"
            )
        if raw is None:
            continue
        if field == "portion_quantity":
            quantity = _variation_quantity(raw)
            if quantity <= 0:
                raise BusinessError(
                    "invalid_variation_quantity", "Portion quantity must be positive"
                )
            values[field] = quantity
        elif field == "sale_price_cents":
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                raise BusinessError(
                    "invalid_variation_price", "Sale price must be a non-negative integer in cents"
                )
            values[field] = raw
        elif field == "station":
            station = str(raw).strip().lower()
            if station not in {"kitchen", "drinks", "packing"}:
                raise BusinessError(
                    "invalid_ingredient_extra_station", "Station must be kitchen, drinks or packing"
                )
            values[field] = station
        else:
            values[field] = _variation_display_order(raw)
    return values


def list_available_ingredient_extras(
    session: Session,
    actor_user_id: str,
    branch_id: str | None = None,
) -> list[dict[str, Any]]:
    # The branch is an authorization scope only.  It never filters or overrides
    # the corporate extra definition.
    authorize_branch_scope(session, actor_user_id, "pos.operate", branch_id)
    rows = session.execute(
        sa.select(
            models.ingredient_variations,
            models.inventory_items.c.name.label("inventory_item_name"),
            models.inventory_items.c.sku.label("inventory_item_sku"),
            models.inventory_units.c.code.label("unit_code"),
        )
        .select_from(
            models.ingredient_variations.join(
                models.inventory_items,
                models.inventory_items.c.id == models.ingredient_variations.c.inventory_item_id,
            ).join(
                models.inventory_units,
                models.inventory_units.c.id == models.inventory_items.c.base_unit_id,
            )
        )
        .where(
            models.ingredient_variations.c.organization_id == ORGANIZATION_ID,
            models.ingredient_variations.c.status == "active",
            models.ingredient_variations.c.portion_quantity > 0,
            models.ingredient_variations.c.station.in_(("kitchen", "drinks", "packing")),
            models.inventory_items.c.organization_id == ORGANIZATION_ID,
            models.inventory_items.c.status == "active",
        )
        .order_by(
            models.ingredient_variations.c.display_order,
            models.inventory_items.c.name,
        )
    ).mappings()
    return [
        _sanitize_for_json(
            {
                **dict(row),
                "extra_id": row["id"],
                "name": row["add_label"],
                "price_cents": row["sale_price_cents"],
            }
        )
        for row in rows
    ]


def create_ingredient_variation(
    session: Session, payload: dict[str, Any], actor_user_id: str | None = None
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    _reject_global_catalog_branch_override(payload)
    item_id = str(payload.get("inventory_item_id", "")).strip()
    custom_label = str(payload.get("name") or payload.get("add_label") or payload.get("label") or "").strip()
    item = None
    if item_id:
        item = (
            session.execute(
                sa.select(models.inventory_items.c.id, models.inventory_items.c.name).where(
                    models.inventory_items.c.id == item_id,
                    models.inventory_items.c.organization_id == ORGANIZATION_ID,
                    models.inventory_items.c.status == "active",
                )
            )
            .mappings()
            .first()
        )
    if not item and custom_label:
        clean_name = custom_label.removeprefix("Porción extra de ").removeprefix("Con ").strip()
        item_id = _id()
        sku_candidate = f"EXT-{re.sub(r'[^A-Z0-9]+', '', clean_name.upper())[:6] or 'ADD'}-{_id()[:4].upper()}"
        now = _now()
        session.execute(
            models.inventory_items.insert().values(
                id=item_id,
                organization_id=ORGANIZATION_ID,
                name=clean_name,
                sku=sku_candidate,
                unit_code="PZA",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        item = {"id": item_id, "name": clean_name}

    if not item:
        raise BusinessError(
            "ingredient_variation_item_not_found", "Ingredient inventory item was not found"
        )
    if session.execute(
        sa.select(models.ingredient_variations.c.id).where(
            models.ingredient_variations.c.organization_id == ORGANIZATION_ID,
            models.ingredient_variations.c.inventory_item_id == item_id,
        )
    ).scalar_one_or_none():
        raise BusinessError(
            "ingredient_variation_exists", "An ingredient variation already exists for this item"
        )
    add_label, remove_label = _ingredient_variation_labels(
        str(item["name"]),
        payload["add_label"] if "add_label" in payload else f"Con {item['name'].strip().lower()}",
        payload["remove_label"]
        if "remove_label" in payload
        else f"Sin {item['name'].strip().lower()}",
    )
    canonical_fields = _canonical_extra_values(payload, require_complete=True)
    now = _now()
    variation = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "inventory_item_id": item_id,
        "add_label": add_label,
        "remove_label": remove_label,
        "portion_quantity": canonical_fields.get("portion_quantity", Decimal("0")),
        "sale_price_cents": canonical_fields.get("sale_price_cents", 0),
        "station": canonical_fields.get("station"),
        "display_order": canonical_fields.get("display_order", 0),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.ingredient_variations.insert().values(**variation))
    _audit(
        session,
        "ingredient_variation.created",
        "ingredient_variation",
        variation["id"],
        {"inventory_item_id": item_id},
        actor_user_id=actor_id,
    )
    session.commit()
    return variation


def _ingredient_variation_summary_query() -> Any:
    return (
        sa.select(
            models.ingredient_variations,
            models.inventory_items.c.name.label("inventory_item_name"),
            models.inventory_items.c.sku.label("inventory_item_sku"),
            models.inventory_units.c.code.label("unit_code"),
            sa.func.count(models.ingredient_variation_products.c.id)
            .filter(models.ingredient_variation_products.c.status == "active")
            .label("related_products"),
            sa.func.count(models.ingredient_variation_products.c.id)
            .filter(
                models.ingredient_variation_products.c.status == "active",
                models.ingredient_variation_products.c.allow_add.is_(True),
            )
            .label("active_add_assignments"),
            sa.func.count(models.ingredient_variation_products.c.id)
            .filter(
                models.ingredient_variation_products.c.status == "active",
                models.ingredient_variation_products.c.allow_remove.is_(True),
            )
            .label("active_remove_assignments"),
        )
        .select_from(
            models.ingredient_variations.join(
                models.inventory_items,
                models.inventory_items.c.id == models.ingredient_variations.c.inventory_item_id,
            )
            .join(
                models.inventory_units,
                models.inventory_units.c.id == models.inventory_items.c.base_unit_id,
            )
            .outerjoin(
                models.ingredient_variation_products,
                models.ingredient_variation_products.c.variation_id
                == models.ingredient_variations.c.id,
            )
        )
        .group_by(
            models.ingredient_variations.c.id,
            models.inventory_items.c.name,
            models.inventory_items.c.sku,
            models.inventory_units.c.code,
        )
    )


def list_ingredient_variations(
    session: Session, search: str, status: str | None, actor_user_id: str | None = None
) -> list[dict[str, Any]]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    query = _ingredient_variation_summary_query().where(
        models.ingredient_variations.c.organization_id == ORGANIZATION_ID
    )
    if status in {"active", "archived", "needs_review"}:
        query = query.where(models.ingredient_variations.c.status == status)
    if search.strip():
        needle = f"%{search.strip().lower()}%"
        query = query.where(
            sa.or_(
                sa.func.lower(models.ingredient_variations.c.add_label).like(needle),
                sa.func.lower(models.ingredient_variations.c.remove_label).like(needle),
                sa.func.lower(models.inventory_items.c.name).like(needle),
                sa.func.lower(models.inventory_items.c.sku).like(needle),
            )
        )
    return [
        {
            **dict(row),
            "warnings": ["needs_review"] if row["status"] == "needs_review" else [],
        }
        for row in session.execute(query.order_by(models.inventory_items.c.name)).mappings()
    ]


def get_ingredient_variation(
    session: Session, variation_id: str, actor_user_id: str | None = None
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    variation = (
        session.execute(
            _ingredient_variation_summary_query().where(
                models.ingredient_variations.c.id == variation_id,
                models.ingredient_variations.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not variation:
        raise NotFoundError("ingredient_variation_not_found", "Ingredient variation was not found")
    rows = session.execute(
        sa.select(
            models.ingredient_variation_products,
            models.products.c.name.label("product_name"),
            models.products.c.sku.label("product_sku"),
            models.product_categories.c.name.label("category_name"),
        )
        .select_from(
            models.ingredient_variation_products.join(
                models.products,
                models.products.c.id == models.ingredient_variation_products.c.product_id,
            ).join(
                models.product_categories,
                models.product_categories.c.id == models.products.c.category_id,
            )
        )
        .where(
            models.ingredient_variation_products.c.variation_id == variation_id,
            models.products.c.organization_id == ORGANIZATION_ID,
        )
        .order_by(models.products.c.name)
    ).mappings()
    return {
        **dict(variation),
        "warnings": ["needs_review"] if variation["status"] == "needs_review" else [],
        "assignments": [dict(row) for row in rows],
    }


def update_ingredient_variation(
    session: Session, variation_id: str, payload: dict[str, Any], actor_user_id: str | None = None
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    _reject_global_catalog_branch_override(payload)
    variation = (
        session.execute(
            sa.select(models.ingredient_variations).where(
                models.ingredient_variations.c.id == variation_id,
                models.ingredient_variations.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not variation:
        raise NotFoundError("ingredient_variation_not_found", "Ingredient variation was not found")
    if "inventory_item_id" in payload:
        raise BusinessError(
            "ingredient_variation_item_immutable",
            "Create a new variation to change its inventory item",
        )
    allowed = {
        "add_label",
        "remove_label",
        "status",
        "portion_quantity",
        "portion",
        "quantity",
        "sale_price_cents",
        "price_cents",
        "station",
        "display_order",
    }
    if set(payload) - allowed or not payload:
        raise BusinessError(
            "invalid_ingredient_variation_update",
            "Only labels, status and canonical extra configuration may be updated",
        )
    values: dict[str, Any] = {"updated_at": _now()}
    if "add_label" in payload or "remove_label" in payload:
        item_name = str(
            session.execute(
                sa.select(models.inventory_items.c.name).where(
                    models.inventory_items.c.id == variation["inventory_item_id"]
                )
            ).scalar_one()
        )
        add, remove = _ingredient_variation_labels(
            item_name,
            payload.get("add_label", variation["add_label"]),
            payload.get("remove_label", variation["remove_label"]),
        )
        values.update(add_label=add, remove_label=remove)
    if "status" in payload:
        if payload["status"] not in {"active", "archived", "needs_review"}:
            raise BusinessError(
                "invalid_ingredient_variation_status",
                "Status must be active, archived or needs_review",
            )
        values["status"] = payload["status"]
    canonical_keys = {
        "portion_quantity",
        "portion",
        "quantity",
        "sale_price_cents",
        "price_cents",
        "station",
        "display_order",
    }
    if canonical_keys.intersection(payload):
        canonical = _canonical_extra_values(payload, current=dict(variation), require_complete=True)
        values.update(canonical)
        if not {"portion_quantity", "sale_price_cents", "station"} <= canonical.keys():
            raise BusinessError(
                "ingredient_extra_configuration_required",
                "Portion, price and station are required for a universal extra",
            )
    if values.get("status") == "active":
        _canonical_extra_values(
            {},
            current={**dict(variation), **values},
            require_complete=True,
        )
    session.execute(
        models.ingredient_variations.update()
        .where(models.ingredient_variations.c.id == variation_id)
        .values(**values)
    )
    assignments = list(
        session.execute(
            sa.select(models.ingredient_variation_products).where(
                models.ingredient_variation_products.c.variation_id == variation_id
            )
        ).mappings()
    )
    if "add_label" in values or "remove_label" in values:
        for assignment in assignments:
            if assignment["add_option_id"]:
                session.execute(
                    models.modifier_options.update()
                    .where(models.modifier_options.c.id == assignment["add_option_id"])
                    .values(
                        name=values.get("add_label", variation["add_label"]),
                        kitchen_text=values.get("add_label", variation["add_label"]),
                        updated_at=values["updated_at"],
                    )
                )
            if assignment["remove_option_id"]:
                session.execute(
                    models.modifier_options.update()
                    .where(models.modifier_options.c.id == assignment["remove_option_id"])
                    .values(
                        name=values.get("remove_label", variation["remove_label"]),
                        kitchen_text=values.get("remove_label", variation["remove_label"]),
                        updated_at=values["updated_at"],
                    )
                )
    if values.get("status") == "archived":
        option_ids = [
            option_id
            for assignment in assignments
            for option_id in (assignment["add_option_id"], assignment["remove_option_id"])
            if option_id
        ]
        if option_ids:
            session.execute(
                models.modifier_options.update()
                .where(models.modifier_options.c.id.in_(option_ids))
                .values(status="archived", updated_at=values["updated_at"])
            )
    if values.get("status") == "active" and variation["status"] == "archived":
        for assignment in assignments:
            if assignment["status"] == "active":
                option_ids = [assignment["add_option_id"] if assignment["allow_add"] else None]
                option_ids = [option_id for option_id in option_ids if option_id]
                if option_ids:
                    session.execute(
                        models.modifier_options.update()
                        .where(models.modifier_options.c.id.in_(option_ids))
                        .values(status="active", updated_at=values["updated_at"])
                    )
    if values.get("status") in {"active", "archived"}:
        group_ids = session.execute(
            sa.select(models.modifier_options.c.group_id).where(
                models.modifier_options.c.id.in_(
                    [
                        option_id
                        for assignment in assignments
                        for option_id in (
                            assignment["add_option_id"],
                            assignment["remove_option_id"],
                        )
                        if option_id
                    ]
                )
            )
        ).scalars()
        for group_id in set(group_ids):
            _recalculate_ingredient_group(session, group_id)
    _audit(
        session,
        "ingredient_variation.archived"
        if values.get("status") == "archived"
        else (
            "ingredient_variation.reactivated"
            if values.get("status") == "active" and variation["status"] == "archived"
            else "ingredient_variation.updated"
        ),
        "ingredient_variation",
        variation_id,
        values,
        actor_user_id=actor_id,
    )
    session.commit()
    return {**dict(variation), **values}


def _assignment_values(payload: dict[str, Any]) -> dict[str, Any]:
    allow_add, allow_remove = payload.get("allow_add"), payload.get("allow_remove")
    if not isinstance(allow_add, bool) or not isinstance(allow_remove, bool):
        raise BusinessError("invalid_variation_action", "Variation actions must be booleans")
    if allow_remove or not allow_add:
        raise BusinessError(
            "ingredient_extra_add_only",
            "Ingredient extras only support the add action for new sales",
        )
    add_quantity, remove_quantity = (
        _variation_quantity(payload.get("add_quantity", 0)),
        _variation_quantity(payload.get("remove_quantity", 0)),
    )
    charge = payload.get("charge_additional")
    if not isinstance(charge, bool):
        raise BusinessError("invalid_variation_price", "Additional charge must be boolean")
    raw_price = payload.get("add_price_delta_cents", 0)
    if isinstance(raw_price, bool) or not isinstance(raw_price, int):
        raise BusinessError("invalid_variation_price", "Additional price must be an integer")
    price = raw_price
    if add_quantity <= 0 or remove_quantity != 0:
        raise BusinessError(
            "invalid_variation_quantity",
            "Ingredient extras require a positive add quantity and zero remove quantity",
        )
    if (charge and (not allow_add or price <= 0)) or (not charge and price != 0):
        raise BusinessError(
            "invalid_variation_price", "Price must be explicit only for an added ingredient"
        )
    return {
        "allow_add": allow_add,
        "allow_remove": allow_remove,
        "add_quantity": add_quantity,
        "remove_quantity": remove_quantity,
        "charge_additional": charge,
        "add_price_delta_cents": price,
    }


def _variation_quantity(value: Any) -> Decimal:
    if isinstance(value, (bool, float)):
        raise BusinessError(
            "invalid_variation_quantity", "Quantity must use an exact decimal string"
        )
    if not isinstance(value, (Decimal, int, str)):
        raise BusinessError(
            "invalid_variation_quantity", "Quantity must use an exact decimal string"
        )
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        if not decimal_value.is_finite():
            raise InvalidOperation
        quantized = decimal_value.quantize(Decimal("0.000001"))
        if quantized != decimal_value:
            raise BusinessError(
                "invalid_variation_quantity",
                "Quantity cannot exceed six decimal places",
            )
        return quantized
    except (InvalidOperation, ValueError):
        raise BusinessError(
            "invalid_variation_quantity", "Quantity must be a finite exact decimal"
        ) from None


def _candidate_assignment_products(session: Session, payload: dict[str, Any]) -> list[str]:
    raw_product_ids, raw_category_ids = (
        payload.get("product_ids", []),
        payload.get("category_ids", []),
    )
    if not isinstance(raw_product_ids, list) or not isinstance(raw_category_ids, list):
        raise BusinessError(
            "variation_assignment_targets_required", "product_ids and category_ids must be arrays"
        )
    if any(
        not isinstance(value, str) or not value.strip()
        for value in raw_product_ids + raw_category_ids
    ):
        raise BusinessError(
            "invalid_variation_assignment_targets", "Targets must be non-empty string identifiers"
        )
    product_ids = {value.strip() for value in raw_product_ids}
    category_ids = {value.strip() for value in raw_category_ids}
    if not product_ids and not category_ids:
        raise BusinessError(
            "variation_assignment_targets_required", "At least one product or category is required"
        )
    if category_ids:
        valid_categories = set(
            session.execute(
                sa.select(models.product_categories.c.id).where(
                    models.product_categories.c.id.in_(category_ids),
                    models.product_categories.c.organization_id == ORGANIZATION_ID,
                )
            ).scalars()
        )
        if valid_categories != category_ids:
            raise BusinessError(
                "invalid_variation_assignment_targets",
                "Categories must belong to the authorized organization",
            )
        product_ids.update(
            session.execute(
                sa.select(models.products.c.id).where(
                    models.products.c.category_id.in_(category_ids),
                    models.products.c.status == "active",
                    models.products.c.organization_id == ORGANIZATION_ID,
                )
            ).scalars()
        )
    return sorted(product_ids)


def _assignment_preview(
    session: Session,
    variation: dict[str, Any],
    payload: dict[str, Any],
    branch_id: str,
) -> list[dict[str, Any]]:
    _assignment_values(payload)
    ids = _candidate_assignment_products(session, payload)
    products: list[dict[str, Any]] = (
        [
            dict(row)
            for row in session.execute(
                sa.select(models.products, models.product_categories.c.name.label("category_name"))
                .join(
                    models.product_categories,
                    models.products.c.category_id == models.product_categories.c.id,
                )
                .where(
                    models.products.c.id.in_(ids),
                    models.products.c.organization_id == ORGANIZATION_ID,
                )
            ).mappings()
        ]
        if ids
        else []
    )
    by_id = {row["id"]: row for row in products}
    preview = []
    for product_id in ids:
        product = by_id.get(product_id)
        reason = None
        if not product or product["status"] != "active":
            reason = "product_inactive_or_missing"
        else:
            recipe = _active_recipe_components(session, product_id, branch_id)
            if not recipe:
                reason = "active_recipe_required"
        preview.append(
            {
                "product_id": product_id,
                "product_name": product["name"] if product else None,
                "sku": product["sku"] if product else None,
                "category": product["category_name"] if product else None,
                "compatible": reason is None,
                "reason": reason,
            }
        )
    return preview


def preview_ingredient_variation_assignments(
    session: Session, variation_id: str, payload: dict[str, Any], actor_user_id: str | None = None
) -> list[dict[str, Any]]:
    _reject_ingredient_variation_assignment_mutation(session, variation_id, actor_user_id)


def _reject_ingredient_variation_assignment_mutation(
    session: Session, variation_id: str, actor_user_id: str | None = None
) -> NoReturn:
    get_ingredient_variation(session, variation_id, actor_user_id)
    raise BusinessError(
        "ingredient_variation_assignments_read_only",
        "Historical ingredient variation assignments are read-only",
    )


def _legacy_preview_ingredient_variation_assignments(
    session: Session, variation_id: str, payload: dict[str, Any], actor_user_id: str | None = None
) -> list[dict[str, Any]]:
    actor_id = _actor_user_id(actor_user_id)
    variation = get_ingredient_variation(session, variation_id, actor_id)
    branch_id = _ingredient_variation_branch(session, actor_id)
    try:
        preview = _assignment_preview(session, variation, payload, branch_id)
    except Exception:
        logger.exception(
            "ingredient_variation.preview.error variation_id=%s actor_id=%s branch_id=%s",
            variation_id,
            actor_id,
            branch_id,
        )
        raise
    logger.info(
        "ingredient_variation.preview variation_id=%s actor_id=%s branch_id=%s target_count=%s",
        variation_id,
        actor_id,
        branch_id,
        len(preview),
    )
    return preview


def _ingredient_variation_branch(session: Session, actor_id: str) -> str:
    """Resolve the active branch from the authenticated actor, never command input."""
    scoped_branch = authorize_branch_scope(session, actor_id, "catalog.manage")
    if scoped_branch:
        return scoped_branch
    return str(build_session_profile(session, actor_id)["active_branch"]["id"])


def _ingredient_group_is_owned(session: Session, group: dict[str, Any]) -> bool:
    """A named group is reusable only when every historical option is catalog-owned."""
    options = list(
        session.execute(
            sa.select(models.modifier_options.c.id).where(
                models.modifier_options.c.group_id == group["id"]
            )
        ).scalars()
    )
    if not options:
        return False
    linked = set(
        session.execute(
            sa.select(models.ingredient_variation_products.c.add_option_id)
            .where(models.ingredient_variation_products.c.add_option_id.in_(options))
            .union(
                sa.select(models.ingredient_variation_products.c.remove_option_id).where(
                    models.ingredient_variation_products.c.remove_option_id.in_(options)
                )
            )
        ).scalars()
    )
    return set(options) == linked


def _recalculate_ingredient_group(session: Session, group_id: str) -> None:
    """Keep the optional ingredient group hidden when it has no active options."""
    now = _now()
    active_count = session.execute(
        sa.select(sa.func.count())
        .select_from(models.modifier_options)
        .where(
            models.modifier_options.c.group_id == group_id,
            models.modifier_options.c.status == "active",
        )
    ).scalar_one()
    session.execute(
        models.modifier_groups.update()
        .where(models.modifier_groups.c.id == group_id)
        .values(
            maximum_selections=int(active_count),
            status="active" if active_count else "archived",
            updated_at=now,
        )
    )


def _ingredient_group(session: Session, product_id: str) -> dict[str, Any]:
    group_row = (
        session.execute(
            sa.select(models.modifier_groups).where(
                models.modifier_groups.c.product_id == product_id,
                models.modifier_groups.c.name == INGREDIENT_VARIATION_GROUP,
            )
        )
        .mappings()
        .first()
    )
    if group_row:
        group = dict(group_row)
        active_count = session.execute(
            sa.select(sa.func.count())
            .select_from(models.modifier_options)
            .where(
                models.modifier_options.c.group_id == group["id"],
                models.modifier_options.c.status == "active",
            )
        ).scalar_one()
        if (
            group["organization_id"] != ORGANIZATION_ID
            or group["product_id"] != product_id
            or group["is_required"]
            or group["minimum_selections"] != 0
            or group["status"] not in {"active", "archived"}
            or group["maximum_selections"] != int(active_count)
            or (group["status"] == "active") != bool(active_count)
            or not _ingredient_group_is_owned(session, group)
        ):
            raise BusinessError(
                "variation_group_conflict", "Ingredient variation group is incompatible"
            )
        return group
    now = _now()
    created_group: dict[str, Any] = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "product_id": product_id,
        "name": INGREDIENT_VARIATION_GROUP,
        "is_required": False,
        "minimum_selections": 0,
        "maximum_selections": 1,
        "station": None,
        "display_order": 999,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.modifier_groups.insert().values(**created_group))
    return created_group


def _sync_ingredient_assignment_options(
    session: Session, variation: dict[str, Any], assignment: dict[str, Any]
) -> dict[str, Any]:
    group = _ingredient_group(session, assignment["product_id"])
    now = _now()
    option_specs = (
        (
            "add",
            "add_option_id",
            variation["add_label"],
            assignment["allow_add"],
            assignment["add_quantity"],
            Decimal("0"),
            assignment["add_price_delta_cents"],
        ),
        (
            "remove",
            "remove_option_id",
            variation["remove_label"],
            assignment["allow_remove"],
            Decimal("0"),
            assignment["remove_quantity"],
            0,
        ),
    )
    updates: dict[str, Any] = {"updated_at": now}
    for effect, key, label, enabled, add_qty, remove_qty, price in option_specs:
        option_id = assignment.get(key)
        if not enabled:
            if option_id:
                session.execute(
                    models.modifier_options.update()
                    .where(models.modifier_options.c.id == option_id)
                    .values(status="archived", updated_at=now)
                )
            continue
        option = {
            "group_id": group["id"],
            "name": label,
            "effect_type": effect,
            "price_delta_cents": price,
            "affected_item_id": variation["inventory_item_id"],
            "replacement_item_id": None,
            "remove_quantity": remove_qty,
            "add_quantity": add_qty,
            "inventory_effect": True,
            "kitchen_text": label,
            "station": group["station"],
            "display_order": 0 if effect == "add" else 1,
            "status": "active",
            "updated_at": now,
        }
        if option_id:
            session.execute(
                models.modifier_options.update()
                .where(models.modifier_options.c.id == option_id)
                .values(**option)
            )
        else:
            option_id = _id()
            session.execute(
                models.modifier_options.insert().values(id=option_id, created_at=now, **option)
            )
            updates[key] = option_id
    session.execute(
        models.ingredient_variation_products.update()
        .where(models.ingredient_variation_products.c.id == assignment["id"])
        .values(**updates)
    )
    _recalculate_ingredient_group(session, group["id"])
    return {**assignment, **updates}


def apply_ingredient_variation_assignments(
    session: Session,
    variation_id: str,
    payload: dict[str, Any],
    idempotency_key: str,
    actor_user_id: str | None = None,
    assignment_update: bool = False,
) -> list[dict[str, Any]]:
    _reject_ingredient_variation_assignment_mutation(session, variation_id, actor_user_id)


def _legacy_apply_ingredient_variation_assignments(
    session: Session,
    variation_id: str,
    payload: dict[str, Any],
    idempotency_key: str,
    actor_user_id: str | None = None,
    assignment_update: bool = False,
) -> list[dict[str, Any]]:
    actor_id = _actor_user_id(actor_user_id)
    variation = get_ingredient_variation(session, variation_id, actor_id)
    if variation["status"] != "active":
        raise BusinessError(
            "ingredient_variation_archived", "Archived variation cannot be assigned"
        )
    if not idempotency_key.strip():
        raise BusinessError("idempotency_key_required", "Assignment apply requires Idempotency-Key")
    values = _assignment_values(payload)
    targets = _candidate_assignment_products(session, payload)
    branch_id = _ingredient_variation_branch(session, actor_id)
    canonical_request = json.dumps(
        {
            "variation_id": variation_id,
            "operation": "assignment_update" if assignment_update else "assignment_bulk_apply",
            "targets": targets,
            **{
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in values.items()
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    request_hash = hashlib.sha256(canonical_request.encode()).hexdigest()
    key = idempotency_key.strip()
    command = (
        session.execute(
            sa.select(models.ingredient_variation_commands).where(
                models.ingredient_variation_commands.c.idempotency_key == key
            )
        )
        .mappings()
        .first()
    )
    if command:
        if (
            command["organization_id"] != ORGANIZATION_ID
            or command["variation_id"] != variation_id
            or command["request_hash"] != request_hash
        ):
            logger.warning(
                "ingredient_variation.apply.conflict variation_id=%s actor_id=%s branch_id=%s target_count=%s idempotency_key=%s",
                variation_id,
                actor_id,
                branch_id,
                len(targets),
                key,
            )
            raise BusinessError(
                "idempotency_conflict", "Idempotency key belongs to a different request"
            )
        if command["status"] == "completed":
            logger.info(
                "ingredient_variation.apply.replay variation_id=%s actor_id=%s branch_id=%s target_count=%s idempotency_key=%s",
                variation_id,
                actor_id,
                branch_id,
                len(targets),
                key,
            )
            return list(command["result"] or [])
        logger.warning(
            "ingredient_variation.apply.conflict variation_id=%s actor_id=%s branch_id=%s target_count=%s idempotency_key=%s",
            variation_id,
            actor_id,
            branch_id,
            len(targets),
            key,
        )
        raise BusinessError("idempotency_conflict", "Idempotency request is still processing")
    preview = _assignment_preview(session, variation, payload, branch_id)
    incompatible = [row for row in preview if not row["compatible"]]
    if incompatible:
        raise BusinessError(
            "variation_assignment_incompatible", "All selected products must be compatible"
        )
    now = _now()
    rows = []
    updated_assignment_id: str | None = None
    try:
        session.execute(
            models.ingredient_variation_commands.insert().values(
                id=_id(),
                organization_id=ORGANIZATION_ID,
                variation_id=variation_id,
                actor_user_id=actor_id,
                idempotency_key=key,
                request_hash=request_hash,
                result=None,
                status="processing",
                created_at=now,
                updated_at=now,
            )
        )
        # Revalidate the effective branch recipe in the command transaction.
        preview = _assignment_preview(session, variation, payload, branch_id)
        incompatible = [row for row in preview if not row["compatible"]]
        if incompatible:
            raise BusinessError(
                "variation_assignment_incompatible",
                "All selected products must be compatible",
            )
        for product_id in [row["product_id"] for row in preview]:
            existing = (
                session.execute(
                    sa.select(models.ingredient_variation_products).where(
                        models.ingredient_variation_products.c.variation_id == variation_id,
                        models.ingredient_variation_products.c.product_id == product_id,
                    )
                )
                .mappings()
                .first()
            )
            assignment = {
                "id": existing["id"] if existing else _id(),
                "variation_id": variation_id,
                "product_id": product_id,
                **values,
                "status": "active",
                "updated_at": now,
            }
            if existing:
                updated_assignment_id = existing["id"]
                session.execute(
                    models.ingredient_variation_products.update()
                    .where(models.ingredient_variation_products.c.id == existing["id"])
                    .values(**assignment)
                )
                assignment = {**dict(existing), **assignment}
            else:
                assignment["created_at"] = now
                assignment["add_option_id"] = None
                assignment["remove_option_id"] = None
                session.execute(models.ingredient_variation_products.insert().values(**assignment))
            rows.append(_sync_ingredient_assignment_options(session, variation, assignment))
        audit_action = (
            "ingredient_variation.assignment.updated"
            if assignment_update and updated_assignment_id
            else "ingredient_variation.assignment.bulk_applied"
        )
        _audit(
            session,
            audit_action,
            "ingredient_variation_product" if updated_assignment_id else "ingredient_variation",
            updated_assignment_id or variation_id,
            {
                "products": len(rows),
                "idempotency_key": idempotency_key,
                "allow_add": values["allow_add"],
                "allow_remove": values["allow_remove"],
            },
            actor_user_id=actor_id,
        )
        session.execute(
            models.ingredient_variation_commands.update()
            .where(models.ingredient_variation_commands.c.idempotency_key == key)
            .values(result=_sanitize_for_json(rows), status="completed", updated_at=_now())
        )
        session.commit()
        logger.info(
            "ingredient_variation.apply variation_id=%s actor_id=%s branch_id=%s target_count=%s idempotency_key=%s",
            variation_id,
            actor_id,
            branch_id,
            len(rows),
            key,
        )
    except sa.exc.IntegrityError as exc:
        session.rollback()
        existing = (
            session.execute(
                sa.select(models.ingredient_variation_commands).where(
                    models.ingredient_variation_commands.c.idempotency_key == key
                )
            )
            .mappings()
            .first()
        )
        if (
            existing
            and existing["request_hash"] == request_hash
            and existing["status"] == "completed"
        ):
            logger.info(
                "ingredient_variation.apply.replay variation_id=%s actor_id=%s branch_id=%s target_count=%s idempotency_key=%s",
                variation_id,
                actor_id,
                branch_id,
                len(targets),
                key,
            )
            return list(existing["result"] or [])
        logger.warning(
            "ingredient_variation.apply.conflict variation_id=%s actor_id=%s branch_id=%s target_count=%s idempotency_key=%s",
            variation_id,
            actor_id,
            branch_id,
            len(targets),
            key,
        )
        raise BusinessError(
            "idempotency_conflict", "Idempotency key belongs to a different request"
        ) from exc
    except Exception:
        session.rollback()
        logger.exception(
            "ingredient_variation.apply.error variation_id=%s actor_id=%s branch_id=%s target_count=%s idempotency_key=%s",
            variation_id,
            actor_id,
            branch_id,
            len(targets),
            key,
        )
        raise
    return cast(list[dict[str, Any]], _sanitize_for_json(rows))


def archive_ingredient_variation_assignment(
    session: Session, variation_id: str, product_id: str, actor_user_id: str | None = None
) -> dict[str, Any]:
    _reject_ingredient_variation_assignment_mutation(session, variation_id, actor_user_id)


def _legacy_archive_ingredient_variation_assignment(
    session: Session, variation_id: str, product_id: str, actor_user_id: str | None = None
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    row = (
        session.execute(
            sa.select(models.ingredient_variation_products)
            .select_from(
                models.ingredient_variation_products.join(
                    models.ingredient_variations,
                    models.ingredient_variations.c.id
                    == models.ingredient_variation_products.c.variation_id,
                ).join(
                    models.products,
                    models.products.c.id == models.ingredient_variation_products.c.product_id,
                )
            )
            .where(
                models.ingredient_variation_products.c.variation_id == variation_id,
                models.ingredient_variation_products.c.product_id == product_id,
                models.ingredient_variations.c.organization_id == ORGANIZATION_ID,
                models.products.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise NotFoundError(
            "ingredient_variation_assignment_not_found",
            "Ingredient variation assignment was not found",
        )
    now = _now()
    session.execute(
        models.ingredient_variation_products.update()
        .where(models.ingredient_variation_products.c.id == row["id"])
        .values(status="archived", updated_at=now)
    )
    group_ids = set(
        session.execute(
            sa.select(models.modifier_options.c.group_id).where(
                models.modifier_options.c.id.in_(
                    [value for value in (row["add_option_id"], row["remove_option_id"]) if value]
                )
            )
        ).scalars()
    )
    session.execute(
        models.modifier_options.update()
        .where(
            models.modifier_options.c.id.in_(
                [value for value in (row["add_option_id"], row["remove_option_id"]) if value]
            )
        )
        .values(status="archived", updated_at=now)
    )
    for group_id in group_ids:
        _recalculate_ingredient_group(session, group_id)
    _audit(
        session,
        "ingredient_variation.assignment.archived",
        "ingredient_variation_product",
        row["id"],
        {"variation_id": variation_id, "product_id": product_id},
        actor_user_id=actor_id,
    )
    session.commit()
    return {**dict(row), "status": "archived", "updated_at": now}


def list_branch_ingredient_variations(
    session: Session, actor_user_id: str, branch_id: str | None = None
) -> list[dict[str, Any]]:
    authorized_branch = _branch_administration_target(
        session, actor_user_id, "branch.admin.access", branch_id
    )
    require_permission(session, actor_user_id, "catalog.branch.manage", authorized_branch)
    rows = session.execute(
        sa.select(
            models.ingredient_variation_products.c.variation_id,
            models.ingredient_variation_products.c.product_id,
            models.inventory_items.c.name.label("inventory_item_name"),
            models.inventory_items.c.sku.label("inventory_item_sku"),
            models.inventory_units.c.code.label("unit_code"),
            models.products.c.name.label("product_name"),
            models.modifier_options.c.id.label("option_id"),
            models.modifier_options.c.name.label("name"),
            models.modifier_options.c.effect_type,
            models.modifier_options.c.status.label("central_status"),
            models.branch_modifier_options.c.is_enabled.label("override"),
        )
        .select_from(
            models.ingredient_variation_products.join(
                models.ingredient_variations,
                models.ingredient_variations.c.id
                == models.ingredient_variation_products.c.variation_id,
            )
            .join(
                models.products,
                models.products.c.id == models.ingredient_variation_products.c.product_id,
            )
            .join(
                models.inventory_items,
                models.inventory_items.c.id == models.ingredient_variations.c.inventory_item_id,
            )
            .join(
                models.inventory_units,
                models.inventory_units.c.id == models.inventory_items.c.base_unit_id,
            )
            .join(
                models.modifier_options,
                models.modifier_options.c.id
                == models.ingredient_variation_products.c.add_option_id,
            )
            .outerjoin(
                models.branch_modifier_options,
                sa.and_(
                    models.branch_modifier_options.c.option_id == models.modifier_options.c.id,
                    models.branch_modifier_options.c.branch_id == authorized_branch,
                ),
            )
        )
        .where(
            models.ingredient_variation_products.c.status == "active",
            models.ingredient_variation_products.c.allow_add.is_(True),
            models.ingredient_variations.c.organization_id == ORGANIZATION_ID,
            models.ingredient_variations.c.status == "active",
            models.products.c.organization_id == ORGANIZATION_ID,
            models.products.c.status == "active",
            models.modifier_options.c.status == "active",
        )
    ).mappings()
    return [
        {
            **dict(row),
            "effective_enabled": row["central_status"] == "active" and row["override"] is not False,
        }
        for row in rows
    ]


def set_branch_ingredient_variation_option(
    session: Session, actor_user_id: str, option_id: str, action: str, branch_id: str | None = None
) -> dict[str, Any]:
    authorized_branch = _branch_administration_target(
        session, actor_user_id, "branch.admin.access", branch_id
    )
    require_permission(session, actor_user_id, "catalog.branch.manage", authorized_branch)
    option = (
        session.execute(
            sa.select(models.modifier_options.c.id, models.modifier_options.c.status)
            .select_from(
                models.modifier_options.join(
                    models.ingredient_variation_products,
                    models.ingredient_variation_products.c.add_option_id
                    == models.modifier_options.c.id,
                )
                .join(
                    models.ingredient_variations,
                    models.ingredient_variations.c.id
                    == models.ingredient_variation_products.c.variation_id,
                )
                .join(
                    models.products,
                    models.products.c.id == models.ingredient_variation_products.c.product_id,
                )
            )
            .where(
                models.modifier_options.c.id == option_id,
                models.modifier_options.c.status == "active",
                models.ingredient_variation_products.c.status == "active",
                models.ingredient_variation_products.c.allow_add.is_(True),
                models.ingredient_variations.c.organization_id == ORGANIZATION_ID,
                models.ingredient_variations.c.status == "active",
                models.products.c.organization_id == ORGANIZATION_ID,
                models.products.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not option:
        raise NotFoundError(
            "ingredient_variation_option_not_found", "Ingredient variation option was not found"
        )
    if not option:
        raise BusinessError(
            "ingredient_variation_option_not_found", "Option is not an ingredient variation"
        )
    if action not in {"available", "unavailable", "inherit"}:
        raise BusinessError(
            "invalid_ingredient_variation_action",
            "Action must be available, unavailable or inherit",
        )
    if action == "inherit":
        session.execute(
            models.branch_modifier_options.delete().where(
                models.branch_modifier_options.c.branch_id == authorized_branch,
                models.branch_modifier_options.c.option_id == option_id,
            )
        )
        override = None
    else:
        override = action == "available"
        values = {
            "branch_id": authorized_branch,
            "option_id": option_id,
            "is_enabled": override,
            "price_delta_cents": None,
            "updated_at": _now(),
        }
        exists = session.execute(
            sa.select(models.branch_modifier_options.c.option_id).where(
                models.branch_modifier_options.c.branch_id == authorized_branch,
                models.branch_modifier_options.c.option_id == option_id,
            )
        ).scalar_one_or_none()
        if exists:
            session.execute(
                models.branch_modifier_options.update()
                .where(
                    models.branch_modifier_options.c.branch_id == authorized_branch,
                    models.branch_modifier_options.c.option_id == option_id,
                )
                .values(**values)
            )
        else:
            session.execute(models.branch_modifier_options.insert().values(**values))
    _audit(
        session,
        "ingredient_variation.branch_configured",
        "modifier_option",
        option_id,
        {"action": action, "override": override},
        branch_id=authorized_branch,
        actor_user_id=actor_user_id,
    )
    session.commit()
    return {
        "option_id": option_id,
        "branch_id": authorized_branch,
        "override": override,
        "effective_enabled": option["status"] == "active" and override is not False,
    }


ORDER_COMMENT_MAX_LENGTH = 120


def _order_comment_text(value: Any) -> tuple[str, str]:
    if not isinstance(value, str):
        raise BusinessError("invalid_order_comment", "Comment text must be a string")
    visible = value.strip()
    if not visible:
        raise BusinessError("invalid_order_comment", "Comment text cannot be empty")
    if len(visible) > ORDER_COMMENT_MAX_LENGTH:
        raise BusinessError(
            "invalid_order_comment",
            "Comment text must be at most 120 characters",
        )
    compact = " ".join(visible.split())
    decomposed = unicodedata.normalize("NFKD", compact)
    normalized = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return visible, normalized


def _parse_order_comment_batch(raw_value: Any) -> tuple[list[dict[str, str]], list[str]]:
    if not isinstance(raw_value, str):
        raise BusinessError("invalid_order_comment", "Comments must be provided as text")
    raw_entries = [
        entry.strip() for entry in re.split(r"(?:,|\n|\s{2,})", raw_value) if entry.strip()
    ]
    if not raw_entries:
        raise BusinessError("invalid_order_comment", "At least one comment is required")
    if len(raw_entries) > 100:
        raise BusinessError(
            "order_comment_batch_too_large", "A comment command accepts at most 100 values"
        )
    unique: list[dict[str, str]] = []
    duplicate_values: list[str] = []
    seen: set[str] = set()
    for entry in raw_entries:
        visible, normalized = _order_comment_text(entry)
        if normalized in seen:
            duplicate_values.append(visible)
            continue
        seen.add(normalized)
        unique.append({"text": visible, "text_normalized": normalized})
    return unique, duplicate_values


def parse_order_comment_values(raw_value: str) -> list[str]:
    """Parse the corporate textarea using comma, newline or 2+ spaces."""
    values, _duplicates = _parse_order_comment_batch(raw_value)
    return [value["text"] for value in values]


def _reject_global_catalog_branch_override(payload: dict[str, Any]) -> None:
    if "branch_id" in payload or "override" in payload or "branch_ids" in payload:
        raise BusinessError(
            "global_catalog_branch_override",
            "Corporate comments and universal extras do not accept branch overrides",
        )


def _order_comment_product_ids(payload: dict[str, Any]) -> list[str]:
    raw_product_ids = payload.get("product_ids", [])
    if not isinstance(raw_product_ids, list) or any(
        not isinstance(value, str) or not value.strip() for value in raw_product_ids
    ):
        raise BusinessError("invalid_order_comment_products", "product_ids must be an array of IDs")
    return list(dict.fromkeys(value.strip() for value in raw_product_ids))


def _validate_order_comment_products(session: Session, product_ids: list[str]) -> list[str]:
    if not product_ids:
        raise BusinessError("order_comment_products_required", "Select at least one product")
    found = set(
        session.execute(
            sa.select(models.products.c.id).where(
                models.products.c.id.in_(product_ids),
                models.products.c.organization_id == ORGANIZATION_ID,
                models.products.c.status == "active",
            )
        ).scalars()
    )
    if found != set(product_ids):
        raise BusinessError(
            "order_comment_product_not_found",
            "Every selected product must belong to the active organization catalog",
        )
    return product_ids


def _order_comment_preview(
    session: Session, raw_value: Any, product_ids: list[str]
) -> dict[str, Any]:
    values, duplicate_values = _parse_order_comment_batch(raw_value)
    _validate_order_comment_products(session, product_ids)
    existing = {
        row["text_normalized"]: dict(row)
        for row in session.execute(
            sa.select(models.order_comment_presets).where(
                models.order_comment_presets.c.organization_id == ORGANIZATION_ID,
                models.order_comment_presets.c.text_normalized.in_(
                    [value["text_normalized"] for value in values] or ["__none__"]
                ),
            )
        ).mappings()
    }
    created = [value for value in values if value["text_normalized"] not in existing]
    existing_values = [
        {**value, "id": existing[value["text_normalized"]]["id"]}
        for value in values
        if value["text_normalized"] in existing
    ]
    return {
        "items": [
            {
                **value,
                "status": "existing" if value["text_normalized"] in existing else "created",
                "id": existing.get(value["text_normalized"], {}).get("id"),
            }
            for value in values
        ],
        "created": created,
        "existing": existing_values,
        "duplicates": duplicate_values,
        "product_ids": product_ids,
    }


def preview_order_comments_bulk(
    session: Session, payload: dict[str, Any], actor_user_id: str | None = None
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    _reject_global_catalog_branch_override(payload)
    raw_value = payload.get("comments", payload.get("text", ""))
    return _order_comment_preview(session, raw_value, _order_comment_product_ids(payload))


def _order_comment_payload(session: Session, comment_id: str, actor_id: str) -> dict[str, Any]:
    comment = (
        session.execute(
            sa.select(models.order_comment_presets).where(
                models.order_comment_presets.c.id == comment_id,
                models.order_comment_presets.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not comment:
        raise NotFoundError("order_comment_not_found", "Corporate order comment was not found")
    relations = session.execute(
        sa.select(
            models.order_comment_products.c.product_id,
            models.products.c.name.label("product_name"),
            models.products.c.sku.label("product_sku"),
        )
        .select_from(
            models.order_comment_products.join(
                models.products,
                models.products.c.id == models.order_comment_products.c.product_id,
            )
        )
        .where(
            models.order_comment_products.c.comment_preset_id == comment_id,
            models.order_comment_products.c.status == "active",
            models.products.c.organization_id == ORGANIZATION_ID,
        )
        .order_by(models.products.c.name)
    ).mappings()
    return {
        **dict(comment),
        "products": [dict(row) for row in relations],
        "product_ids": [row["product_id"] for row in relations],
    }


def list_order_comments(
    session: Session,
    status: str | None = None,
    actor_user_id: str | None = None,
) -> list[dict[str, Any]]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    query = sa.select(models.order_comment_presets).where(
        models.order_comment_presets.c.organization_id == ORGANIZATION_ID
    )
    if status in {"active", "archived"}:
        query = query.where(models.order_comment_presets.c.status == status)
    return [
        _order_comment_payload(session, row["id"], actor_id)
        for row in session.execute(
            query.order_by(
                models.order_comment_presets.c.display_order, models.order_comment_presets.c.text
            )
        ).mappings()
    ]


def bulk_order_comments(
    session: Session,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    _reject_global_catalog_branch_override(payload)
    raw_value = payload.get("comments", payload.get("text", ""))
    product_ids = _validate_order_comment_products(session, _order_comment_product_ids(payload))
    preview = _order_comment_preview(session, raw_value, product_ids)
    now = _now()
    created_ids: list[str] = []
    relation_count = 0
    for item in preview["items"]:
        existing = (
            session.execute(
                sa.select(models.order_comment_presets).where(
                    models.order_comment_presets.c.organization_id == ORGANIZATION_ID,
                    models.order_comment_presets.c.text_normalized == item["text_normalized"],
                )
            )
            .mappings()
            .first()
        )
        if existing:
            comment_id = existing["id"]
            session.execute(
                models.order_comment_presets.update()
                .where(models.order_comment_presets.c.id == comment_id)
                .values(
                    status="active",
                    updated_by=actor_id,
                    updated_at=now,
                )
            )
        else:
            comment_id = _id()
            created_ids.append(comment_id)
            session.execute(
                models.order_comment_presets.insert().values(
                    id=comment_id,
                    organization_id=ORGANIZATION_ID,
                    text=item["text"],
                    text_normalized=item["text_normalized"],
                    display_order=0,
                    status="active",
                    created_by=actor_id,
                    updated_by=actor_id,
                    created_at=now,
                    updated_at=now,
                )
            )
        for product_id in product_ids:
            relation = session.execute(
                sa.select(models.order_comment_products.c.id).where(
                    models.order_comment_products.c.comment_preset_id == comment_id,
                    models.order_comment_products.c.product_id == product_id,
                )
            ).scalar_one_or_none()
            if relation:
                session.execute(
                    models.order_comment_products.update()
                    .where(models.order_comment_products.c.id == relation)
                    .values(status="active", actor_user_id=actor_id, updated_at=now)
                )
            else:
                session.execute(
                    models.order_comment_products.insert().values(
                        id=_id(),
                        comment_preset_id=comment_id,
                        product_id=product_id,
                        status="active",
                        actor_user_id=actor_id,
                        created_at=now,
                        updated_at=now,
                    )
                )
            relation_count += 1
    _audit(
        session,
        "order_comment.bulk_applied",
        "order_comment_preset",
        created_ids[0]
        if created_ids
        else (preview["existing"][0]["id"] if preview["existing"] else _id()),
        {
            "created": len(created_ids),
            "existing": len(preview["existing"]),
            "duplicates": len(preview["duplicates"]),
            "products": len(product_ids),
            "relations": relation_count,
        },
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    persisted_ids = {
        row["text_normalized"]: row["id"]
        for row in session.execute(
            sa.select(
                models.order_comment_presets.c.id,
                models.order_comment_presets.c.text_normalized,
            ).where(
                models.order_comment_presets.c.organization_id == ORGANIZATION_ID,
                models.order_comment_presets.c.text_normalized.in_(
                    [item["text_normalized"] for item in preview["items"]] or ["__none__"]
                ),
            )
        ).mappings()
    }
    persisted_items = [
        {**item, "id": persisted_ids[item["text_normalized"]]} for item in preview["items"]
    ]
    return {
        **preview,
        "items": persisted_items,
        "existing": [
            {**item, "id": persisted_ids[item["text_normalized"]]} for item in preview["existing"]
        ],
        "created_ids": created_ids,
        "relation_count": relation_count,
    }


def update_order_comment(
    session: Session,
    comment_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    _reject_global_catalog_branch_override(payload)
    comment = (
        session.execute(
            sa.select(models.order_comment_presets).where(
                models.order_comment_presets.c.id == comment_id,
                models.order_comment_presets.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not comment:
        raise NotFoundError("order_comment_not_found", "Corporate order comment was not found")
    allowed = {"text", "status", "display_order"}
    if set(payload) - allowed or not payload:
        raise BusinessError(
            "invalid_order_comment_update", "Only text, order and status may be updated"
        )
    values: dict[str, Any] = {"updated_by": actor_id, "updated_at": _now()}
    if "text" in payload:
        visible, normalized = _order_comment_text(payload["text"])
        duplicate = session.execute(
            sa.select(models.order_comment_presets.c.id).where(
                models.order_comment_presets.c.organization_id == ORGANIZATION_ID,
                models.order_comment_presets.c.text_normalized == normalized,
                models.order_comment_presets.c.id != comment_id,
            )
        ).scalar_one_or_none()
        if duplicate:
            raise BusinessError(
                "order_comment_already_exists", "A corporate comment already has this text"
            )
        values.update(text=visible, text_normalized=normalized)
    if "display_order" in payload:
        values["display_order"] = _variation_display_order(payload["display_order"])
    if "status" in payload:
        if payload["status"] not in {"active", "archived"}:
            raise BusinessError("invalid_order_comment_status", "Status must be active or archived")
        values["status"] = payload["status"]
    session.execute(
        models.order_comment_presets.update()
        .where(models.order_comment_presets.c.id == comment_id)
        .values(**values)
    )
    _audit(
        session,
        "order_comment.updated",
        "order_comment_preset",
        comment_id,
        {key: value for key, value in values.items() if key not in {"updated_at", "updated_by"}},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return _order_comment_payload(session, comment_id, actor_id)


def replace_order_comment_products(
    session: Session,
    comment_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    _reject_global_catalog_branch_override(payload)
    _order_comment_payload(session, comment_id, actor_id)
    product_ids = _validate_order_comment_products(session, _order_comment_product_ids(payload))
    now = _now()
    existing = list(
        session.execute(
            sa.select(models.order_comment_products).where(
                models.order_comment_products.c.comment_preset_id == comment_id
            )
        ).mappings()
    )
    desired = set(product_ids)
    for relation in existing:
        session.execute(
            models.order_comment_products.update()
            .where(models.order_comment_products.c.id == relation["id"])
            .values(
                status="active" if relation["product_id"] in desired else "archived",
                actor_user_id=actor_id,
                updated_at=now,
            )
        )
    existing_products = {relation["product_id"] for relation in existing}
    for product_id in product_ids:
        if product_id in existing_products:
            continue
        session.execute(
            models.order_comment_products.insert().values(
                id=_id(),
                comment_preset_id=comment_id,
                product_id=product_id,
                status="active",
                actor_user_id=actor_id,
                created_at=now,
                updated_at=now,
            )
        )
    _audit(
        session,
        "order_comment.products_replaced",
        "order_comment_preset",
        comment_id,
        {"products": len(product_ids), "archived_relations": len(existing_products - desired)},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return _order_comment_payload(session, comment_id, actor_id)


PRESET_VARIATION_GROUP = "Variaciones y cambios"


def _normalized_variation_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name or len(name) > 120:
        raise BusinessError(
            "invalid_variation_note",
            "Variation note name is required and must be at most 120 characters",
        )
    return name


def _variation_display_order(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BusinessError(
            "invalid_variation_display_order", "Variation note display order must be an integer"
        )

    if value < -(2**31) or value > 2**31 - 1:
        raise BusinessError(
            "invalid_variation_display_order",
            "Variation note display order is outside the supported range",
        )
    return int(value)


def _is_safe_preset_variation_group(session: Session, group: dict[str, Any]) -> bool:
    if group["status"] != "active" or group["is_required"] or group["minimum_selections"] != 0:
        return False
    if group["maximum_selections"] < 1:
        return False
    effects = set(
        session.execute(
            sa.select(models.modifier_options.c.effect_type).where(
                models.modifier_options.c.group_id == group["id"]
            )
        ).scalars()
    )
    return effects <= {"preset_instruction"}


def _preset_variation_group(session: Session, product_id: str) -> dict[str, Any]:
    group_row = (
        session.execute(
            sa.select(models.modifier_groups).where(
                models.modifier_groups.c.product_id == product_id,
                sa.func.lower(sa.func.trim(models.modifier_groups.c.name))
                == PRESET_VARIATION_GROUP.lower(),
            )
        )
        .mappings()
        .first()
    )
    now = _now()
    if group_row:
        group = dict(group_row)
        if not _is_safe_preset_variation_group(session, group):
            raise BusinessError(
                "variation_group_conflict",
                "The existing Variaciones y cambios group is not safe for preset variation notes",
            )
        return group
    created_group: dict[str, Any] = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "product_id": product_id,
        "name": PRESET_VARIATION_GROUP,
        "is_required": False,
        "minimum_selections": 0,
        "maximum_selections": 1,
        "station": None,
        "display_order": 0,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.modifier_groups.insert().values(**created_group))
    return created_group


def _sync_preset_variation_group_capacity(session: Session, group_id: str) -> None:
    group = (
        session.execute(
            sa.select(models.modifier_groups).where(models.modifier_groups.c.id == group_id)
        )
        .mappings()
        .first()
    )
    if not group or not _is_safe_preset_variation_group(session, dict(group)):
        raise BusinessError(
            "variation_group_conflict", "Preset variation group is not safe to synchronize"
        )
    active_count = int(
        session.execute(
            sa.select(sa.func.count())
            .select_from(models.modifier_options)
            .where(
                models.modifier_options.c.group_id == group_id,
                models.modifier_options.c.effect_type == "preset_instruction",
                models.modifier_options.c.status == "active",
            )
        ).scalar_one()
    )
    session.execute(
        models.modifier_groups.update()
        .where(models.modifier_groups.c.id == group_id)
        .values(
            is_required=False,
            minimum_selections=0,
            maximum_selections=max(1, active_count),
            status="active",
            updated_at=_now(),
        )
    )


def create_variation_note(
    session: Session,
    product_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    product = session.execute(
        sa.select(models.products.c.id).where(
            models.products.c.id == product_id,
            models.products.c.organization_id == ORGANIZATION_ID,
        )
    ).scalar_one_or_none()
    if not product:
        raise NotFoundError("product_not_found", "Product was not found")
    name = _normalized_variation_name(payload.get("name"))
    duplicate = session.execute(
        sa.select(models.modifier_options.c.id)
        .select_from(
            models.modifier_options.join(
                models.modifier_groups,
                models.modifier_options.c.group_id == models.modifier_groups.c.id,
            )
        )
        .where(
            models.modifier_groups.c.product_id == product_id,
            models.modifier_options.c.effect_type == "preset_instruction",
            sa.func.lower(sa.func.trim(models.modifier_options.c.name)) == name.lower(),
        )
        .limit(1)
    ).scalar_one_or_none()
    if duplicate:
        raise BusinessError(
            "variation_note_already_exists",
            "A variation note with this name already exists for the product",
        )
    group = _preset_variation_group(session, product_id)
    now = _now()
    option = {
        "id": _id(),
        "group_id": group["id"],
        "name": name,
        "effect_type": "preset_instruction",
        "price_delta_cents": 0,
        "affected_item_id": None,
        "replacement_item_id": None,
        "remove_quantity": Decimal("0"),
        "add_quantity": Decimal("0"),
        "inventory_effect": False,
        "kitchen_text": name,
        "station": group["station"],
        "display_order": _variation_display_order(payload.get("display_order", 0)),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.modifier_options.insert().values(**option))
    _sync_preset_variation_group_capacity(session, group["id"])
    _audit(
        session,
        "variation_note.created",
        "modifier_option",
        option["id"],
        {"product_id": product_id, "name": name, "display_order": option["display_order"]},
        actor_user_id=actor_id,
    )
    session.commit()
    return option


def update_variation_note(
    session: Session,
    option_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    option = (
        session.execute(
            sa.select(models.modifier_options, models.modifier_groups.c.product_id)
            .select_from(
                models.modifier_options.join(
                    models.modifier_groups,
                    models.modifier_options.c.group_id == models.modifier_groups.c.id,
                )
            )
            .where(
                models.modifier_options.c.id == option_id,
                models.modifier_options.c.effect_type == "preset_instruction",
            )
        )
        .mappings()
        .first()
    )
    if not option:
        raise NotFoundError("variation_note_not_found", "Variation note was not found")
    unknown = set(payload) - {"name", "display_order", "status"}
    if unknown:
        raise BusinessError(
            "invalid_variation_note_update", "Only name, display_order and status may be updated"
        )
    values: dict[str, Any] = {"updated_at": _now()}
    if "name" in payload:
        name = _normalized_variation_name(payload["name"])
        duplicate = session.execute(
            sa.select(models.modifier_options.c.id)
            .select_from(
                models.modifier_options.join(
                    models.modifier_groups,
                    models.modifier_options.c.group_id == models.modifier_groups.c.id,
                )
            )
            .where(
                models.modifier_groups.c.product_id == option["product_id"],
                models.modifier_options.c.effect_type == "preset_instruction",
                sa.func.lower(sa.func.trim(models.modifier_options.c.name)) == name.lower(),
                models.modifier_options.c.id != option_id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if duplicate:
            raise BusinessError(
                "variation_note_already_exists",
                "A variation note with this name already exists for the product",
            )
        values.update(name=name, kitchen_text=name)
    if "display_order" in payload:
        values["display_order"] = _variation_display_order(payload["display_order"])
    if "status" in payload:
        status = str(payload["status"])
        if status not in {"active", "archived"}:
            raise BusinessError(
                "invalid_variation_note_status", "Variation note status must be active or archived"
            )
        values["status"] = status
    if len(values) == 1:
        raise BusinessError(
            "invalid_variation_note_update",
            "At least one editable variation note field is required",
        )
    session.execute(
        models.modifier_options.update()
        .where(models.modifier_options.c.id == option_id)
        .values(**values)
    )
    _sync_preset_variation_group_capacity(session, option["group_id"])
    action = (
        "variation_note.archived"
        if values.get("status") == "archived"
        else "variation_note.updated"
    )
    if values.get("status") == "active" and option["status"] == "archived":
        action = "variation_note.reactivated"
    _audit(session, action, "modifier_option", option_id, values, actor_user_id=actor_id)
    session.commit()
    return {**dict(option), **values}


def list_variation_notes(
    session: Session, product_id: str, actor_user_id: str | None = None
) -> list[dict[str, Any]]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    rows = session.execute(
        sa.select(
            models.modifier_options.c.id,
            models.modifier_options.c.name,
            models.modifier_options.c.kitchen_text,
            models.modifier_options.c.display_order,
            models.modifier_options.c.status,
            models.modifier_groups.c.product_id,
            models.products.c.name.label("product_name"),
        )
        .select_from(
            models.modifier_options.join(
                models.modifier_groups,
                models.modifier_options.c.group_id == models.modifier_groups.c.id,
            ).join(models.products, models.modifier_groups.c.product_id == models.products.c.id)
        )
        .where(
            models.modifier_groups.c.product_id == product_id,
            models.modifier_options.c.effect_type == "preset_instruction",
        )
        .order_by(models.modifier_options.c.display_order, models.modifier_options.c.name)
    ).mappings()
    return [dict(row) for row in rows]


def list_branch_variation_notes(
    session: Session, actor_user_id: str, branch_id: str | None = None
) -> list[dict[str, Any]]:
    authorized_branch = _branch_administration_target(
        session, actor_user_id, "branch.admin.access", branch_id
    )
    require_permission(session, actor_user_id, "catalog.branch.manage", authorized_branch)
    rows = session.execute(
        sa.select(
            models.products.c.id.label("product_id"),
            models.products.c.name.label("product_name"),
            models.modifier_options.c.id.label("option_id"),
            models.modifier_options.c.name.label("name"),
            models.modifier_options.c.display_order,
            models.modifier_options.c.status.label("central_status"),
            models.branch_modifier_options.c.is_enabled.label("override"),
        )
        .select_from(
            models.modifier_options.join(
                models.modifier_groups,
                models.modifier_options.c.group_id == models.modifier_groups.c.id,
            )
            .join(models.products, models.modifier_groups.c.product_id == models.products.c.id)
            .outerjoin(
                models.branch_modifier_options,
                sa.and_(
                    models.branch_modifier_options.c.option_id == models.modifier_options.c.id,
                    models.branch_modifier_options.c.branch_id == authorized_branch,
                ),
            )
        )
        .where(models.modifier_options.c.effect_type == "preset_instruction")
        .order_by(
            models.products.c.name,
            models.modifier_options.c.display_order,
            models.modifier_options.c.name,
        )
    ).mappings()
    return [
        {
            **dict(row),
            "effective_enabled": row["central_status"] == "active" and row["override"] is not False,
        }
        for row in rows
    ]


def set_branch_variation_note(
    session: Session, actor_user_id: str, option_id: str, action: str, branch_id: str | None = None
) -> dict[str, Any]:
    authorized_branch = _branch_administration_target(
        session, actor_user_id, "branch.admin.access", branch_id
    )
    require_permission(session, actor_user_id, "catalog.branch.manage", authorized_branch)
    option = (
        session.execute(
            sa.select(models.modifier_options.c.id, models.modifier_options.c.status).where(
                models.modifier_options.c.id == option_id,
                models.modifier_options.c.effect_type == "preset_instruction",
            )
        )
        .mappings()
        .first()
    )
    if not option:
        raise NotFoundError("variation_note_not_found", "Variation note was not found")
    if action not in {"available", "unavailable", "inherit"}:
        raise BusinessError(
            "invalid_variation_note_action", "Action must be available, unavailable or inherit"
        )
    existing = session.execute(
        sa.select(models.branch_modifier_options.c.is_enabled).where(
            models.branch_modifier_options.c.branch_id == authorized_branch,
            models.branch_modifier_options.c.option_id == option_id,
        )
    ).scalar_one_or_none()
    if action == "inherit":
        session.execute(
            models.branch_modifier_options.delete().where(
                models.branch_modifier_options.c.branch_id == authorized_branch,
                models.branch_modifier_options.c.option_id == option_id,
            )
        )
        override = None
    else:
        override = action == "available"
        values = {
            "branch_id": authorized_branch,
            "option_id": option_id,
            "is_enabled": override,
            "price_delta_cents": None,
            "updated_at": _now(),
        }
        if existing is None:
            session.execute(models.branch_modifier_options.insert().values(**values))
        else:
            session.execute(
                models.branch_modifier_options.update()
                .where(
                    models.branch_modifier_options.c.branch_id == authorized_branch,
                    models.branch_modifier_options.c.option_id == option_id,
                )
                .values(**values)
            )
    _audit(
        session,
        "variation_note.branch_configured",
        "modifier_option",
        option_id,
        {
            "branch_id": authorized_branch,
            "previous": existing,
            "override": override,
            "action": action,
        },
        branch_id=authorized_branch,
        actor_user_id=actor_user_id,
    )
    session.commit()
    return {
        "option_id": option_id,
        "branch_id": authorized_branch,
        "override": override,
        "effective_enabled": option["status"] == "active" and override is not False,
    }


def set_branch_modifier_option(
    session: Session,
    option_id: str,
    branch_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.branch.manage", branch_id)
    if not session.execute(
        sa.select(models.modifier_options.c.id).where(models.modifier_options.c.id == option_id)
    ).scalar_one_or_none():
        raise BusinessError("modifier_option_not_found", "Modifier option was not found")
    values = {
        "branch_id": branch_id,
        "option_id": option_id,
        "is_enabled": bool(payload.get("is_enabled", True)),
        "price_delta_cents": int(payload["price_delta_cents"])
        if payload.get("price_delta_cents") is not None
        else None,
        "updated_at": _now(),
    }
    existing = session.execute(
        sa.select(models.branch_modifier_options).where(
            models.branch_modifier_options.c.branch_id == branch_id,
            models.branch_modifier_options.c.option_id == option_id,
        )
    ).first()
    if existing:
        session.execute(
            sa.update(models.branch_modifier_options)
            .where(
                models.branch_modifier_options.c.branch_id == branch_id,
                models.branch_modifier_options.c.option_id == option_id,
            )
            .values(**values)
        )
    else:
        session.execute(models.branch_modifier_options.insert().values(**values))
    _audit(
        session,
        "modifier_option.branch_configured",
        "modifier_option",
        option_id,
        values,
        branch_id,
        actor_user_id=actor_id,
    )
    session.commit()
    return values


def list_product_modifiers(
    session: Session,
    product_id: str,
    branch_id: str | None = None,
    catalog_view: bool = False,
) -> list[dict[str, Any]]:
    actual_branch_id = branch_id or BRANCH_ID
    groups = [
        dict(row)
        for row in session.execute(
            sa.select(models.modifier_groups)
            .where(
                models.modifier_groups.c.product_id == product_id,
                models.modifier_groups.c.organization_id == ORGANIZATION_ID,
                models.modifier_groups.c.status == "active",
            )
            .order_by(models.modifier_groups.c.display_order, models.modifier_groups.c.name)
        ).mappings()
    ]
    by_id = {group["id"]: {**group, "options": []} for group in groups}
    global_comment_rows = session.execute(
        sa.select(
            models.order_comment_presets.c.id,
            models.order_comment_presets.c.text,
            models.order_comment_presets.c.display_order,
        )
        .select_from(
            models.order_comment_presets.join(
                models.order_comment_products,
                models.order_comment_products.c.comment_preset_id
                == models.order_comment_presets.c.id,
            )
        )
        .where(
            models.order_comment_presets.c.organization_id == ORGANIZATION_ID,
            models.order_comment_presets.c.status == "active",
            models.order_comment_products.c.product_id == product_id,
            models.order_comment_products.c.status == "active",
        )
        .order_by(models.order_comment_presets.c.display_order, models.order_comment_presets.c.text)
    ).mappings()
    global_comments = list(global_comment_rows)
    global_comment_names = {_order_comment_text(row["text"])[1] for row in global_comments}
    if global_comments:
        by_id[ORDER_COMMENT_GROUP_ID] = {
            "id": ORDER_COMMENT_GROUP_ID,
            "organization_id": ORGANIZATION_ID,
            "product_id": product_id,
            "name": "Comentarios del pedido",
            "is_required": False,
            "minimum_selections": 0,
            "maximum_selections": len(global_comments),
            "station": None,
            "display_order": -1000,
            "status": "active",
            "options": [
                {
                    "id": row["id"],
                    "group_id": ORDER_COMMENT_GROUP_ID,
                    "name": row["text"],
                    "effect_type": "preset_instruction",
                    "price_delta_cents": 0,
                    "affected_item_id": None,
                    "replacement_item_id": None,
                    "remove_quantity": Decimal("0"),
                    "add_quantity": Decimal("0"),
                    "inventory_effect": False,
                    "kitchen_text": row["text"],
                    "station": None,
                    "display_order": row["display_order"],
                    "status": "active",
                    "variation_kind": "order_comment",
                    "comment_preset_id": row["id"],
                }
                for row in global_comments
            ],
        }
    if not by_id:
        return [by_id[ORDER_COMMENT_GROUP_ID]] if global_comments else []
    branch_join_condition = (
        sa.false()
        if catalog_view
        else sa.and_(
            models.branch_modifier_options.c.option_id == models.modifier_options.c.id,
            models.branch_modifier_options.c.branch_id == actual_branch_id,
        )
    )
    options = session.execute(
        sa.select(
            models.modifier_options,
            models.branch_modifier_options.c.is_enabled.label("branch_enabled"),
            models.branch_modifier_options.c.price_delta_cents.label("branch_price_delta_cents"),
        )
        .select_from(
            models.modifier_options.outerjoin(
                models.branch_modifier_options,
                branch_join_condition,
            )
        )
        .where(
            models.modifier_options.c.group_id.in_(by_id.keys()),
            models.modifier_options.c.status == "active",
        )
        .order_by(models.modifier_options.c.display_order, models.modifier_options.c.name)
    ).mappings()
    option_rows = list(options)
    option_ids = [row["id"] for row in option_rows]
    legacy_ingredient_option_ids: set[str] = set()
    if option_ids:
        ingredient_rows = session.execute(
            sa.select(
                models.ingredient_variation_products.c.add_option_id,
                models.ingredient_variation_products.c.remove_option_id,
            ).where(
                sa.or_(
                    models.ingredient_variation_products.c.add_option_id.in_(option_ids),
                    models.ingredient_variation_products.c.remove_option_id.in_(option_ids),
                )
            )
        ).mappings()
        for ingredient in ingredient_rows:
            legacy_ingredient_option_ids.update(
                str(option_id)
                for option_id in (ingredient["add_option_id"], ingredient["remove_option_id"])
                if option_id
            )
    for row in option_rows:
        # POS-CAT-003 preserves historical ingredient options in the database,
        # but neither action can be offered in new sales. This deliberately
        # leaves unrelated add/remove/substitute modifier options unchanged.
        if row["id"] in legacy_ingredient_option_ids:
            if catalog_view:
                option = dict(row)
                option["catalog_price_delta_cents"] = row["price_delta_cents"]
                option["price_delta_cents"] = row["price_delta_cents"]
                option["variation_kind"] = "ingredient_extra"
                by_id[row["group_id"]]["options"].append(option)
            continue
        if (
            row["effect_type"] == "preset_instruction"
            and _order_comment_text(row["name"])[1] in global_comment_names
        ):
            continue
        if not catalog_view and row["branch_enabled"] is False:
            continue
        option = dict(row)
        option["catalog_price_delta_cents"] = row["price_delta_cents"]
        option["price_delta_cents"] = (
            0
            if row["effect_type"] == "preset_instruction"
            else (
                row["branch_price_delta_cents"]
                if row["branch_price_delta_cents"] is not None
                else row["price_delta_cents"]
            )
        )
        by_id[row["group_id"]]["options"].append(option)
    return [
        group
        for group in by_id.values()
        if group["options"]
        or group["name"] not in {PRESET_VARIATION_GROUP, "Comentarios del pedido"}
    ]


def create_production_recipe(
    session: Session,
    output_item_id: str,
    components: list[dict[str, Any]],
    yield_quantity: Any,
    yield_unit_id: str,
    branch_id: str | None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    output = (
        session.execute(
            sa.select(models.inventory_items).where(
                models.inventory_items.c.id == output_item_id,
                models.inventory_items.c.organization_id == ORGANIZATION_ID,
                models.inventory_items.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not output:
        raise BusinessError("output_item_not_found", "Production output item was not found")
    if output["item_type"] != "elaborated":
        raise BusinessError(
            "output_item_must_be_elaborated", "Production recipe output must be an elaborated item"
        )
    if yield_unit_id != output["base_unit_id"]:
        raise BusinessError(
            "production_yield_unit_mismatch", "Production yield unit must match output base unit"
        )
    normalized_yield = _quantity(yield_quantity)
    if normalized_yield <= 0:
        raise BusinessError("invalid_recipe_yield", "Recipe yield must be positive")
    component_rows = _normalize_recipe_components(session, components)
    _assert_no_production_recipe_cycle(
        session, output_item_id, [row["item_id"] for row in component_rows]
    )
    now = _now()
    max_version = (
        session.execute(
            sa.select(sa.func.max(models.recipes.c.version)).where(
                models.recipes.c.output_item_id == output_item_id
            )
        ).scalar()
        or 0
    )
    session.execute(
        sa.update(models.recipes)
        .where(
            models.recipes.c.output_item_id == output_item_id,
            models.recipes.c.status == "active",
            models.recipes.c.branch_id.is_(branch_id)
            if branch_id is None
            else models.recipes.c.branch_id == branch_id,
        )
        .values(status="retired", valid_to=now, updated_at=now)
    )
    recipe_id = _id()
    recipe: dict[str, Any] = {
        "id": recipe_id,
        "organization_id": ORGANIZATION_ID,
        "product_id": None,
        "output_item_id": output_item_id,
        "branch_id": branch_id,
        "recipe_type": "production",
        "version": int(max_version) + 1,
        "status": "active",
        "yield_quantity": normalized_yield,
        "yield_unit_id": yield_unit_id,
        "valid_from": now,
        "valid_to": None,
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.recipes.insert().values(**recipe))
    for row in component_rows:
        session.execute(models.recipe_components.insert().values(recipe_id=recipe_id, **row))
    cost = calculate_recipe_cost(session, recipe_id, branch_id or BRANCH_ID, actor_id, persist=True)
    _audit(
        session,
        "production_recipe.created",
        "recipe",
        recipe_id,
        {"output_item_id": output_item_id, "version": recipe["version"]},
        branch_id=branch_id,
        actor_user_id=actor_id,
    )
    session.commit()
    return {**recipe, "components": component_rows, "cost": cost}


def _normalize_recipe_components(
    session: Session,
    components: list[dict[str, Any]],
    branch_id: str | None = None,
) -> list[dict[str, Any]]:
    if not components:
        raise BusinessError("recipe_components_required", "Recipe requires at least one component")

    # Consolidate multiple rows of the same item_id by aggregating quantities
    aggregated: dict[str, dict[str, Any]] = {}
    for index, component in enumerate(components):
        item_id = str(component.get("item_id", "")).strip()
        if not item_id:
            continue

        net = _quantity(component.get("net_quantity", component.get("quantity", 0)))
        if "waste_percent" in component:
            waste = _quantity(component["waste_percent"]) / Decimal("100")
        else:
            raw_waste = _quantity(component.get("waste_rate", 0))
            waste = raw_waste / Decimal("100") if raw_waste >= Decimal("1") else raw_waste

        if waste < 0:
            waste = Decimal("0")
        if waste >= Decimal("1"):
            waste = Decimal("0.9999")

        if item_id in aggregated:
            existing = aggregated[item_id]
            existing["net"] += net
            existing["waste"] = max(existing["waste"], waste)
        else:
            aggregated[item_id] = {
                "item_id": item_id,
                "unit_id": component.get("unit_id"),
                "net": net,
                "waste": waste,
                "sort_order": int(component.get("sort_order", index)),
                "notes": component.get("notes"),
            }

    rows = []
    for item_id, comp_data in aggregated.items():
        item = (
            session.execute(
                sa.select(models.inventory_items).where(
                    models.inventory_items.c.id == item_id,
                    models.inventory_items.c.organization_id == ORGANIZATION_ID,
                    models.inventory_items.c.status == "active",
                )
            )
            .mappings()
            .first()
        )
        if not item:
            raise BusinessError("recipe_component_not_found", "Recipe component item was not found")
        if item["catalog_scope"] != "organization" and (
            branch_id is None or item["source_branch_id"] != branch_id
        ):
            raise BusinessError(
                "recipe_component_scope_invalid", "Component is outside recipe scope"
            )
        unit_id = str(comp_data.get("unit_id") or item["base_unit_id"])
        if unit_id != item["base_unit_id"]:
            unit_id = str(item["base_unit_id"])

        net = comp_data["net"]
        waste = comp_data["waste"]
        if net <= 0:
            continue
        gross = _quantity(net / (Decimal("1") - waste))
        rows.append(
            {
                "item_id": item_id,
                "quantity_base_units": gross,
                "unit_id": unit_id,
                "net_quantity": net,
                "waste_rate": waste,
                "gross_quantity": gross,
                "sort_order": comp_data["sort_order"],
                "notes": comp_data["notes"],
            }
        )
    if not rows:
        raise BusinessError("recipe_components_required", "Recipe requires at least one component")
    return rows


def calculate_recipe_cost(
    session: Session,
    recipe_id: str,
    branch_id: str,
    actor_user_id: str,
    persist: bool = True,
) -> dict[str, Any]:
    recipe = (
        session.execute(sa.select(models.recipes).where(models.recipes.c.id == recipe_id))
        .mappings()
        .first()
    )
    if not recipe:
        raise BusinessError("recipe_not_found", "Recipe was not found")
    warehouse_id = _branch_warehouse_id(session, branch_id)
    components = session.execute(
        sa.select(
            models.recipe_components,
            models.inventory_items.c.name.label("item_name"),
            models.inventory_units.c.code.label("unit_code"),
        )
        .select_from(
            models.recipe_components.join(
                models.inventory_items,
                models.recipe_components.c.item_id == models.inventory_items.c.id,
            ).join(
                models.inventory_units,
                models.recipe_components.c.unit_id == models.inventory_units.c.id,
            )
        )
        .where(models.recipe_components.c.recipe_id == recipe_id)
        .order_by(models.recipe_components.c.sort_order)
    ).mappings()
    before_waste = Decimal("0")
    total = Decimal("0")
    breakdown = []
    for component in components:
        average = session.execute(
            sa.select(models.inventory_cost_states.c.average_unit_cost).where(
                models.inventory_cost_states.c.branch_id == branch_id,
                models.inventory_cost_states.c.warehouse_id == warehouse_id,
                models.inventory_cost_states.c.item_id == component["item_id"],
            )
        ).scalar_one_or_none()
        unit_cost = _cost(average or 0)
        net_cost = _cost(Decimal(str(component["net_quantity"])) * unit_cost)
        gross_cost = _cost(Decimal(str(component["gross_quantity"])) * unit_cost)
        waste_cost = _cost(gross_cost - net_cost)
        before_waste += net_cost
        total += gross_cost
        breakdown.append(
            _sanitize_for_json(
                {
                    "item_id": component["item_id"],
                    "item_name": component["item_name"],
                    "unit_id": component["unit_id"],
                    "unit_code": component["unit_code"],
                    "net_quantity": component["net_quantity"],
                    "gross_quantity": component["gross_quantity"],
                    "waste_rate": component["waste_rate"],
                    "unit_cost": unit_cost,
                    "cost_before_waste": net_cost,
                    "waste_cost": waste_cost,
                    "total_cost": gross_cost,
                }
            )
        )
    before_waste = _cost(before_waste)
    total = _cost(total)
    cost = {
        "id": _id(),
        "recipe_id": recipe_id,
        "branch_id": branch_id,
        "cost_before_waste": before_waste,
        "waste_cost": _cost(total - before_waste),
        "total_cost": total,
        "cost_per_yield_unit": _cost(total / Decimal(str(recipe["yield_quantity"]))),
        "breakdown": breakdown,
        "calculated_at": _now(),
        "calculated_by": actor_user_id,
    }
    if persist:
        session.execute(models.recipe_cost_calculations.insert().values(**cost))
    return cost


def _assert_no_production_recipe_cycle(
    session: Session,
    output_item_id: str,
    candidate_components: list[str],
) -> None:
    adjacency: dict[str, set[str]] = {}
    rows = session.execute(
        sa.select(
            models.recipes.c.output_item_id,
            models.recipe_components.c.item_id,
        )
        .select_from(
            models.recipes.join(
                models.recipe_components,
                models.recipes.c.id == models.recipe_components.c.recipe_id,
            )
        )
        .where(
            models.recipes.c.recipe_type == "production",
            models.recipes.c.status == "active",
            models.recipes.c.output_item_id.is_not(None),
        )
    )
    for parent, child in rows:
        adjacency.setdefault(str(parent), set()).add(str(child))
    adjacency[output_item_id] = set(candidate_components)

    def visit(item_id: str, path: set[str]) -> None:
        if item_id in path:
            raise BusinessError("recipe_cycle_detected", "Production recipe would create a cycle")
        for child in adjacency.get(item_id, set()):
            visit(child, path | {item_id})

    visit(output_item_id, set())


def create_production_batch(
    session: Session,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    branch_id = str(payload.get("branch_id", ""))
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "production.manage", branch_id)
    recipe_id = str(payload.get("recipe_id", ""))
    recipe = (
        session.execute(
            sa.select(models.recipes).where(
                models.recipes.c.id == recipe_id,
                models.recipes.c.recipe_type == "production",
                models.recipes.c.status == "active",
                sa.or_(
                    models.recipes.c.branch_id == branch_id, models.recipes.c.branch_id.is_(None)
                ),
            )
        )
        .mappings()
        .first()
    )
    if not recipe:
        raise BusinessError(
            "active_production_recipe_not_found", "Active production recipe was not found"
        )
    planned = _quantity(payload.get("planned_quantity", recipe["yield_quantity"]))
    actual = _quantity(payload.get("actual_quantity", planned))
    actual_waste = _quantity(payload.get("actual_waste_quantity", 0))
    lot_code = str(payload.get("lot_code", "")).strip().upper()
    if not lot_code or planned <= 0 or actual <= 0 or actual_waste < 0:
        raise BusinessError(
            "invalid_production_batch", "Lot and positive planned/actual quantities are required"
        )
    now = _now()
    batch = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "branch_id": branch_id,
        "warehouse_id": _branch_warehouse_id(session, branch_id),
        "recipe_id": recipe_id,
        "output_item_id": recipe["output_item_id"],
        "lot_code": lot_code,
        "planned_quantity": planned,
        "actual_quantity": actual,
        "actual_waste_quantity": actual_waste,
        "total_cost": 0,
        "unit_cost": 0,
        "status": "draft",
        "idempotency_key": None,
        "created_by": actor_id,
        "confirmed_by": None,
        "created_at": now,
        "confirmed_at": None,
    }
    session.execute(models.production_batches.insert().values(**batch))
    _audit(
        session,
        "production_batch.created",
        "production_batch",
        batch["id"],
        {"lot_code": lot_code, "recipe_id": recipe_id},
        branch_id,
        actor_user_id=actor_id,
    )
    session.commit()
    return get_production_batch(session, batch["id"])


def confirm_production_batch(
    session: Session,
    batch_id: str,
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    key = idempotency_key.strip()
    if not key:
        raise BusinessError(
            "idempotency_key_required", "Production confirmation requires idempotency key"
        )
    batch = (
        session.execute(
            sa.select(models.production_batches).where(models.production_batches.c.id == batch_id)
        )
        .mappings()
        .first()
    )
    if not batch:
        raise BusinessError("production_batch_not_found", "Production batch was not found")
    require_permission(session, actor_id, "production.manage", batch["branch_id"])
    if batch["status"] == "confirmed":
        if batch["idempotency_key"] == key:
            return get_production_batch(session, batch_id)
        raise BusinessError(
            "production_batch_already_confirmed", "Production batch was already confirmed"
        )
    if batch["status"] != "draft":
        raise BusinessError("production_batch_not_confirmable", "Only draft batch can be confirmed")
    recipe = (
        session.execute(sa.select(models.recipes).where(models.recipes.c.id == batch["recipe_id"]))
        .mappings()
        .one()
    )
    components = [
        dict(row)
        for row in session.execute(
            sa.select(models.recipe_components)
            .where(models.recipe_components.c.recipe_id == batch["recipe_id"])
            .order_by(models.recipe_components.c.sort_order)
        ).mappings()
    ]
    scale = _quantity(
        Decimal(str(batch["planned_quantity"])) / Decimal(str(recipe["yield_quantity"]))
    )
    requirements = []
    total_cost = Decimal("0")
    for component in components:
        required = _quantity(Decimal(str(component["gross_quantity"])) * scale)
        available = _physical_inventory_quantity(
            session, batch["branch_id"], batch["warehouse_id"], component["item_id"]
        )
        if available < required:
            raise BusinessError(
                "insufficient_production_inventory",
                "Production component inventory is insufficient",
            )
        state = (
            session.execute(
                sa.select(models.inventory_cost_states).where(
                    models.inventory_cost_states.c.branch_id == batch["branch_id"],
                    models.inventory_cost_states.c.warehouse_id == batch["warehouse_id"],
                    models.inventory_cost_states.c.item_id == component["item_id"],
                )
            )
            .mappings()
            .first()
        )

        unit_cost = _cost(state["average_unit_cost"] if state else 0)
        component_cost = _cost(required * unit_cost)
        total_cost += component_cost
        requirements.append((component, required, available, unit_cost, component_cost, state))
    total_cost = _cost(total_cost)
    unit_cost = _cost(total_cost / Decimal(str(batch["actual_quantity"])))
    now = _now()
    for index, (
        component,
        required,
        available,
        input_unit_cost,
        component_cost,
        state,
    ) in enumerate(requirements):
        movement = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": batch["branch_id"],
            "warehouse_id": batch["warehouse_id"],
            "item_id": component["item_id"],
            "movement_type": "PRODUCTION_INPUT",
            "quantity_delta": -required,
            "unit_id": component["unit_id"],
            "unit_cost": input_unit_cost,
            "total_cost": -component_cost,
            "effective_at": now,
            "actor_user_id": actor_id,
            "document_type": "production_batch",
            "document_id": batch_id,
            "reference": batch["lot_code"],
            "reason": "Consumo de lote de produccion",
            "notes": None,
            "idempotency_key": f"{key}:input:{index}",
            "status": "confirmed",
            "reversal_of_id": None,
            "source_type": "production_batch",
            "source_id": batch_id,
            "created_at": now,
        }
        session.execute(models.inventory_movements.insert().values(**movement))
        if state:
            session.execute(
                sa.update(models.inventory_cost_states)
                .where(
                    models.inventory_cost_states.c.branch_id == batch["branch_id"],
                    models.inventory_cost_states.c.warehouse_id == batch["warehouse_id"],
                    models.inventory_cost_states.c.item_id == component["item_id"],
                )
                .values(quantity_on_hand=_quantity(available - required), updated_at=now)
            )
        else:
            session.execute(
                models.inventory_cost_states.insert().values(
                    branch_id=batch["branch_id"],
                    warehouse_id=batch["warehouse_id"],
                    item_id=component["item_id"],
                    quantity_on_hand=_quantity(available - required),
                    average_unit_cost=input_unit_cost,
                    last_unit_cost=input_unit_cost,
                    last_supplier_id=None,
                    last_cost_at=now,
                    updated_at=now,
                )
            )
    output_before = _physical_inventory_quantity(
        session, batch["branch_id"], batch["warehouse_id"], batch["output_item_id"]
    )
    output_state = (
        session.execute(
            sa.select(models.inventory_cost_states).where(
                models.inventory_cost_states.c.branch_id == batch["branch_id"],
                models.inventory_cost_states.c.warehouse_id == batch["warehouse_id"],
                models.inventory_cost_states.c.item_id == batch["output_item_id"],
            )
        )
        .mappings()
        .first()
    )
    output_average = _cost(output_state["average_unit_cost"] if output_state else 0)
    output_quantity = _quantity(batch["actual_quantity"])
    new_output_quantity = _quantity(output_before + output_quantity)
    new_output_average = (
        unit_cost
        if output_before == 0
        else _cost(((output_before * output_average) + total_cost) / new_output_quantity)
    )
    session.execute(
        models.inventory_movements.insert().values(
            id=_id(),
            organization_id=ORGANIZATION_ID,
            branch_id=batch["branch_id"],
            warehouse_id=batch["warehouse_id"],
            item_id=batch["output_item_id"],
            movement_type="PRODUCTION_OUTPUT",
            quantity_delta=output_quantity,
            unit_id=recipe["yield_unit_id"],
            unit_cost=unit_cost,
            total_cost=total_cost,
            effective_at=now,
            actor_user_id=actor_id,
            document_type="production_batch",
            document_id=batch_id,
            reference=batch["lot_code"],
            reason="Entrada de elaborado producido",
            notes=None,
            idempotency_key=f"{key}:output",
            status="confirmed",
            reversal_of_id=None,
            source_type="production_batch",
            source_id=batch_id,
            created_at=now,
        )
    )
    output_values = {
        "branch_id": batch["branch_id"],
        "warehouse_id": batch["warehouse_id"],
        "item_id": batch["output_item_id"],
        "quantity_on_hand": new_output_quantity,
        "average_unit_cost": new_output_average,
        "last_unit_cost": unit_cost,
        "last_supplier_id": None,
        "last_cost_at": now,
        "updated_at": now,
    }
    if output_state:
        session.execute(
            sa.update(models.inventory_cost_states)
            .where(
                models.inventory_cost_states.c.branch_id == batch["branch_id"],
                models.inventory_cost_states.c.warehouse_id == batch["warehouse_id"],
                models.inventory_cost_states.c.item_id == batch["output_item_id"],
            )
            .values(**output_values)
        )
    else:
        session.execute(models.inventory_cost_states.insert().values(**output_values))
    session.execute(
        sa.update(models.production_batches)
        .where(models.production_batches.c.id == batch_id)
        .values(
            status="confirmed",
            idempotency_key=key,
            total_cost=total_cost,
            unit_cost=unit_cost,
            confirmed_by=actor_id,
            confirmed_at=now,
        )
    )
    _audit(
        session,
        "production_batch.confirmed",
        "production_batch",
        batch_id,
        {"total_cost": str(total_cost), "unit_cost": str(unit_cost)},
        batch["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_production_batch(session, batch_id)


def get_production_batch(session: Session, batch_id: str) -> dict[str, Any]:
    batch = (
        session.execute(
            sa.select(models.production_batches).where(models.production_batches.c.id == batch_id)
        )
        .mappings()
        .first()
    )
    if not batch:
        raise BusinessError("production_batch_not_found", "Production batch was not found")
    result = dict(batch)
    result["movements"] = [
        dict(row)
        for row in session.execute(
            sa.select(models.inventory_movements)
            .where(
                models.inventory_movements.c.source_type == "production_batch",
                models.inventory_movements.c.source_id == batch_id,
            )
            .order_by(models.inventory_movements.c.created_at)
        ).mappings()
    ]
    return result


def list_production_batches(session: Session, branch_id: str | None) -> list[dict[str, Any]]:
    ids = session.execute(
        sa.select(models.production_batches.c.id)
        .where(models.production_batches.c.branch_id == branch_id)
        .order_by(models.production_batches.c.created_at.desc())
    ).scalars()
    return [get_production_batch(session, batch_id) for batch_id in ids]


def normalize_mexican_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) == 10:
        return f"+52{digits}"
    if len(digits) == 12 and digits.startswith("52"):
        return f"+{digits}"
    raise BusinessError("invalid_phone", "Mexican phone must contain 10 digits")


def create_customer(
    session: Session,
    name: str,
    email: str | None,
    phones: list[dict[str, Any]],
    branch_id: str | None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "orders.create", branch_id)
    normalized_name = name.strip()
    if not normalized_name:
        raise BusinessError("invalid_customer_name", "Customer name is required")
    now = _now()
    customer: dict[str, Any] = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "name": normalized_name,
        "email": email.strip().lower() if email and email.strip() else None,
        "customer_type": "person",
        "customer_segment": None,
        "notes": None,
        "status": "active",
        "origin_branch_id": branch_id,
        "created_at": now,
        "updated_at": now,
    }
    phone_rows: list[dict[str, Any]] = []
    for index, phone in enumerate(phones):
        captured = str(phone.get("number", "")).strip()
        phone_rows.append(
            {
                "id": _id(),
                "customer_id": customer["id"],
                "captured_number": captured,
                "normalized_number": normalize_mexican_phone(captured),
                "phone_type": str(phone.get("type", "mobile")),
                "is_primary": bool(phone.get("is_primary", index == 0)),
                "whatsapp_enabled": bool(phone.get("whatsapp_enabled", False)),
                "is_verified": False,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        )
    if sum(1 for phone in phone_rows if phone["is_primary"]) > 1:
        raise BusinessError("multiple_primary_phones", "Only one phone can be primary")
    session.execute(models.customers.insert().values(**customer))
    if phone_rows:
        session.execute(models.customer_phones.insert(), phone_rows)
    _audit(
        session,
        action="customer.created",
        entity_type="customer",
        entity_id=customer["id"],
        payload={"name": normalized_name, "phone_count": len(phone_rows)},
        branch_id=branch_id,
        actor_user_id=actor_id,
    )
    session.commit()
    return {**customer, "phones": phone_rows, "addresses": []}


def add_customer_address(
    session: Session,
    customer_id: str,
    payload: dict[str, Any],
    branch_id: str | None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "orders.create", branch_id)
    customer = session.execute(
        sa.select(models.customers.c.id).where(
            models.customers.c.id == customer_id,
            models.customers.c.organization_id == ORGANIZATION_ID,
            models.customers.c.status == "active",
            sa.or_(
                models.customers.c.origin_branch_id.is_(None),
                models.customers.c.origin_branch_id == branch_id,
            ),
        )
    ).scalar_one_or_none()
    if not customer:
        raise BusinessError("customer_not_found", "Active customer was not found")
    required = [
        "alias",
        "street",
        "exterior_number",
        "neighborhood",
        "postal_code",
        "city",
        "municipality",
        "state",
    ]
    if any(not str(payload.get(field, "")).strip() for field in required):
        raise BusinessError("invalid_customer_address", "Address required fields are missing")
    now = _now()
    is_default = bool(payload.get("is_default", False))
    if is_default:
        session.execute(
            sa.update(models.customer_addresses)
            .where(
                models.customer_addresses.c.customer_id == customer_id,
                models.customer_addresses.c.is_default.is_(True),
            )
            .values(is_default=False, updated_at=now)
        )
    address: dict[str, Any] = {
        "id": _id(),
        "customer_id": customer_id,
        "alias": str(payload["alias"]).strip(),
        "street": str(payload["street"]).strip(),
        "exterior_number": str(payload["exterior_number"]).strip(),
        "interior_number": str(payload.get("interior_number", "")).strip() or None,
        "neighborhood": str(payload["neighborhood"]).strip(),
        "postal_code": str(payload["postal_code"]).strip(),
        "city": str(payload["city"]).strip(),
        "municipality": str(payload["municipality"]).strip(),
        "state": str(payload["state"]).strip(),
        "country": str(payload.get("country", "MX")).upper(),
        "cross_streets": str(payload.get("cross_streets", "")).strip() or None,
        "references": str(payload.get("references", "")).strip() or None,
        "delivery_instructions": str(payload.get("delivery_instructions", "")).strip() or None,
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "delivery_zone_id": payload.get("delivery_zone_id"),
        "is_default": is_default,
        "status": "active",
        "last_used_at": None,
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.customer_addresses.insert().values(**address))
    _audit(
        session,
        "customer.address_added",
        "customer_address",
        address["id"],
        {"customer_id": customer_id, "alias": address["alias"]},
        branch_id,
        actor_user_id=actor_id,
    )
    session.commit()
    return address


def update_customer(
    session: Session,
    customer_id: str,
    payload: dict[str, Any],
    branch_id: str | None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "orders.create", branch_id)
    current = (
        session.execute(
            sa.select(models.customers).where(
                models.customers.c.id == customer_id,
                models.customers.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not current:
        raise BusinessError("customer_not_found", "Customer was not found")
    updates: dict[str, Any] = {"updated_at": _now()}
    if "name" in payload:
        name = str(payload["name"]).strip()
        if not name:
            raise BusinessError("invalid_customer_name", "Customer name is required")
        updates["name"] = name
    if "email" in payload:
        email = str(payload.get("email") or "").strip().lower()
        updates["email"] = email or None
    if "customer_type" in payload:
        customer_type = str(payload["customer_type"]).lower()
        if customer_type not in {"person", "company"}:
            raise BusinessError("invalid_customer_type", "Customer type must be person or company")
        updates["customer_type"] = customer_type
    for field in ("customer_segment", "notes", "status"):
        if field in payload:
            updates[field] = payload[field]
    session.execute(
        sa.update(models.customers).where(models.customers.c.id == customer_id).values(**updates)
    )
    _audit(
        session,
        "customer.updated",
        "customer",
        customer_id,
        updates,
        branch_id,
        actor_user_id=actor_id,
    )
    session.commit()
    return {**dict(current), **updates}


def update_customer_address(
    session: Session,
    customer_id: str,
    address_id: str,
    payload: dict[str, Any],
    branch_id: str | None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "orders.create", branch_id)
    current = (
        session.execute(
            sa.select(models.customer_addresses).where(
                models.customer_addresses.c.id == address_id,
                models.customer_addresses.c.customer_id == customer_id,
            )
        )
        .mappings()
        .first()
    )
    if not current:
        raise BusinessError("customer_address_not_found", "Customer address was not found")
    allowed = {
        "alias",
        "street",
        "exterior_number",
        "interior_number",
        "neighborhood",
        "postal_code",
        "city",
        "municipality",
        "state",
        "country",
        "cross_streets",
        "references",
        "delivery_instructions",
        "latitude",
        "longitude",
        "delivery_zone_id",
        "is_default",
        "status",
    }
    updates = {field: payload[field] for field in allowed if field in payload}
    for field in (
        "alias",
        "street",
        "exterior_number",
        "neighborhood",
        "postal_code",
        "city",
        "municipality",
        "state",
    ):
        value = updates.get(field, current[field])
        if not str(value or "").strip():
            raise BusinessError("invalid_customer_address", "Address required fields are missing")
    now = _now()
    updates["updated_at"] = now
    if bool(updates.get("is_default", False)):
        session.execute(
            sa.update(models.customer_addresses)
            .where(
                models.customer_addresses.c.customer_id == customer_id,
                models.customer_addresses.c.id != address_id,
                models.customer_addresses.c.is_default.is_(True),
            )
            .values(is_default=False, updated_at=now)
        )
    session.execute(
        sa.update(models.customer_addresses)
        .where(models.customer_addresses.c.id == address_id)
        .values(**updates)
    )
    _audit(
        session,
        "customer.address_updated",
        "customer_address",
        address_id,
        {"customer_id": customer_id, "changes": updates},
        branch_id,
        actor_user_id=actor_id,
    )
    session.commit()
    return {**dict(current), **updates}


def upsert_customer_tax_profile(
    session: Session,
    customer_id: str,
    payload: dict[str, Any],
    branch_id: str | None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "orders.create", branch_id)
    customer = session.execute(
        sa.select(models.customers.c.id).where(
            models.customers.c.id == customer_id,
            models.customers.c.organization_id == ORGANIZATION_ID,
        )
    ).scalar_one_or_none()
    if not customer:
        raise BusinessError("customer_not_found", "Customer was not found")
    required = ("legal_name", "tax_id", "tax_regime", "fiscal_postal_code")
    if any(not str(payload.get(field, "")).strip() for field in required):
        raise BusinessError(
            "invalid_tax_profile", "Fiscal name, RFC, regime and postal code are required"
        )
    tax_id = str(payload["tax_id"]).strip().upper()
    if len(tax_id) not in {12, 13}:
        raise BusinessError("invalid_tax_id", "RFC must contain 12 or 13 characters")
    profile = {
        "customer_id": customer_id,
        "legal_name": str(payload["legal_name"]).strip(),
        "tax_id": tax_id,
        "tax_regime": str(payload["tax_regime"]).strip(),
        "fiscal_postal_code": str(payload["fiscal_postal_code"]).strip(),
        "cfdi_use": str(payload.get("cfdi_use", "")).strip() or None,
        "billing_email": str(payload.get("billing_email", "")).strip().lower() or None,
        "updated_at": _now(),
    }
    existing = session.execute(
        sa.select(models.customer_tax_profiles.c.customer_id).where(
            models.customer_tax_profiles.c.customer_id == customer_id
        )
    ).scalar_one_or_none()
    if existing:
        session.execute(
            sa.update(models.customer_tax_profiles)
            .where(models.customer_tax_profiles.c.customer_id == customer_id)
            .values(**profile)
        )
    else:
        session.execute(models.customer_tax_profiles.insert().values(**profile))
    _audit(
        session,
        "customer.tax_profile_upserted",
        "customer",
        customer_id,
        {"tax_id": tax_id},
        branch_id,
        actor_user_id=actor_id,
    )
    session.commit()
    return profile


def list_customers(
    session: Session, phone: str | None = None, branch_id: str | None = None
) -> list[dict[str, Any]]:
    query = sa.select(models.customers).where(models.customers.c.organization_id == ORGANIZATION_ID)
    if branch_id:
        query = query.where(
            sa.or_(
                models.customers.c.origin_branch_id.is_(None),
                models.customers.c.origin_branch_id == branch_id,
            )
        )
    if phone:
        normalized = normalize_mexican_phone(phone)
        query = query.where(
            models.customers.c.id.in_(
                sa.select(models.customer_phones.c.customer_id).where(
                    models.customer_phones.c.normalized_number == normalized,
                    models.customer_phones.c.status == "active",
                )
            )
        )
    rows = session.execute(query.order_by(models.customers.c.name)).mappings()
    result = []
    for row in rows:
        customer = dict(row)
        customer["phones"] = [
            dict(item)
            for item in session.execute(
                sa.select(models.customer_phones)
                .where(models.customer_phones.c.customer_id == row["id"])
                .order_by(
                    models.customer_phones.c.is_primary.desc(), models.customer_phones.c.created_at
                )
            ).mappings()
        ]
        customer["addresses"] = [
            dict(item)
            for item in session.execute(
                sa.select(models.customer_addresses)
                .where(
                    models.customer_addresses.c.customer_id == row["id"],
                    models.customer_addresses.c.status == "active",
                )
                .order_by(
                    models.customer_addresses.c.is_default.desc(),
                    models.customer_addresses.c.created_at,
                )
            ).mappings()
        ]
        tax_profile = (
            session.execute(
                sa.select(models.customer_tax_profiles).where(
                    models.customer_tax_profiles.c.customer_id == row["id"]
                )
            )
            .mappings()
            .first()
        )
        customer["tax_profile"] = dict(tax_profile) if tax_profile else None
        customer["order_summary"] = get_customer_order_summary(session, str(row["id"]))
        result.append(customer)
    return result


def list_customers_page(
    session: Session,
    branch_id: str | None,
    query_text: str | None = None,
    phone: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    bounded_limit = min(max(limit, 1), 100)
    bounded_offset = max(offset, 0)
    criteria = [models.customers.c.organization_id == ORGANIZATION_ID]
    if branch_id:
        criteria.append(
            sa.or_(
                models.customers.c.origin_branch_id.is_(None),
                models.customers.c.origin_branch_id == branch_id,
            )
        )
    normalized_query = str(query_text or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        # Search by name, email, or phone (captured or normalized).
        phone_match_ids = sa.select(models.customer_phones.c.customer_id).where(
            sa.or_(
                models.customer_phones.c.captured_number.ilike(pattern),
                models.customer_phones.c.normalized_number.ilike(pattern),
            ),
            models.customer_phones.c.status == "active",
        )
        criteria.append(
            sa.or_(
                models.customers.c.name.ilike(pattern),
                models.customers.c.email.ilike(pattern),
                models.customers.c.id.in_(phone_match_ids),
            )
        )
    if phone:
        normalized_phone = normalize_mexican_phone(phone)
        criteria.append(
            models.customers.c.id.in_(
                sa.select(models.customer_phones.c.customer_id).where(
                    models.customer_phones.c.normalized_number == normalized_phone,
                    models.customer_phones.c.status == "active",
                )
            )
        )

    total = int(
        session.execute(
            sa.select(sa.func.count(models.customers.c.id)).where(*criteria)
        ).scalar_one()
    )
    customer_rows = list(
        session.execute(
            sa.select(models.customers)
            .where(*criteria)
            .order_by(models.customers.c.name, models.customers.c.id)
            .limit(bounded_limit)
            .offset(bounded_offset)
        ).mappings()
    )
    customer_ids = [str(row["id"]) for row in customer_rows]
    if not customer_ids:
        return {"items": [], "total": total, "limit": bounded_limit, "offset": bounded_offset}

    phones_by_customer: dict[str, list[dict[str, Any]]] = {item: [] for item in customer_ids}
    for row in session.execute(
        sa.select(models.customer_phones)
        .where(models.customer_phones.c.customer_id.in_(customer_ids))
        .order_by(models.customer_phones.c.is_primary.desc(), models.customer_phones.c.created_at)
    ).mappings():
        phones_by_customer[str(row["customer_id"])].append(dict(row))

    addresses_by_customer: dict[str, list[dict[str, Any]]] = {item: [] for item in customer_ids}
    for row in session.execute(
        sa.select(models.customer_addresses)
        .where(
            models.customer_addresses.c.customer_id.in_(customer_ids),
            models.customer_addresses.c.status == "active",
        )
        .order_by(
            models.customer_addresses.c.is_default.desc(), models.customer_addresses.c.created_at
        )
    ).mappings():
        addresses_by_customer[str(row["customer_id"])].append(dict(row))

    tax_by_customer = {
        str(row["customer_id"]): dict(row)
        for row in session.execute(
            sa.select(models.customer_tax_profiles).where(
                models.customer_tax_profiles.c.customer_id.in_(customer_ids)
            )
        ).mappings()
    }
    summaries = {
        str(row["customer_id"]): {
            "order_count": int(row["order_count"] or 0),
            "last_order_at": row["last_order_at"],
            "average_ticket_cents": (
                int(row["total_cents"] or 0) // int(row["order_count"]) if row["order_count"] else 0
            ),
            "frequent_products": [],
            "recent_orders": [],
        }
        for row in session.execute(
            sa.select(
                models.orders.c.customer_id,
                sa.func.count(models.orders.c.id).label("order_count"),
                sa.func.max(models.orders.c.created_at).label("last_order_at"),
                sa.func.coalesce(sa.func.sum(models.orders.c.total_cents), 0).label("total_cents"),
            )
            .where(
                models.orders.c.customer_id.in_(customer_ids),
                models.orders.c.status != "CANCELLED",
            )
            .group_by(models.orders.c.customer_id)
        ).mappings()
    }
    # Legacy address reference: recover the raw text from import records for
    # imported customers, without exposing raw_payload or cross-branch data.
    legacy_by_customer: dict[str, str | None] = {cid: None for cid in customer_ids}
    legacy_criteria = [
        models.legacy_import_records.c.target_entity_id.in_(customer_ids),
        models.legacy_import_records.c.entity_type == "customer",
        models.legacy_import_records.c.target_entity_type == "customer",
    ]
    if branch_id:
        legacy_criteria.append(models.legacy_import_batches.c.branch_id == branch_id)
    legacy_rows = session.execute(
        sa.select(
            models.legacy_import_records.c.target_entity_id,
            models.legacy_import_records.c.normalized_payload,
        )
        .select_from(
            models.legacy_import_records.join(
                models.legacy_import_batches,
                models.legacy_import_records.c.batch_id == models.legacy_import_batches.c.id,
            )
        )
        .where(*legacy_criteria)
    ).mappings()
    for row in legacy_rows:
        cid = str(row["target_entity_id"])
        if cid in legacy_by_customer:
            payload = row["normalized_payload"]
            reference = payload.get("legacy_address") if isinstance(payload, dict) else None
            legacy_by_customer[cid] = str(reference) if reference else None

    items = []
    for row in customer_rows:
        customer = dict(row)
        customer_id = str(row["id"])
        customer["phones"] = phones_by_customer[customer_id]
        customer["addresses"] = addresses_by_customer[customer_id]
        customer["legacy_address_reference"] = legacy_by_customer.get(customer_id)
        customer["tax_profile"] = tax_by_customer.get(customer_id)
        customer["order_summary"] = summaries.get(
            customer_id,
            {
                "order_count": 0,
                "last_order_at": None,
                "average_ticket_cents": 0,
                "frequent_products": [],
                "recent_orders": [],
            },
        )
        items.append(customer)
    return {"items": items, "total": total, "limit": bounded_limit, "offset": bounded_offset}


def get_customer_order_summary(session: Session, customer_id: str) -> dict[str, Any]:
    aggregate = (
        session.execute(
            sa.select(
                sa.func.count(models.orders.c.id).label("order_count"),
                sa.func.max(models.orders.c.created_at).label("last_order_at"),
                sa.func.coalesce(sa.func.sum(models.orders.c.total_cents), 0).label("total_cents"),
            ).where(
                models.orders.c.customer_id == customer_id,
                models.orders.c.status != "CANCELLED",
            )
        )
        .mappings()
        .one()
    )
    order_count = int(aggregate["order_count"] or 0)
    frequent = session.execute(
        sa.select(
            models.order_lines.c.product_id,
            models.order_lines.c.product_name,
            sa.func.sum(models.order_lines.c.quantity).label("quantity"),
        )
        .select_from(
            models.order_lines.join(
                models.orders, models.order_lines.c.order_id == models.orders.c.id
            )
        )
        .where(models.orders.c.customer_id == customer_id, models.orders.c.status != "CANCELLED")
        .group_by(models.order_lines.c.product_id, models.order_lines.c.product_name)
        .order_by(sa.func.sum(models.order_lines.c.quantity).desc())
        .limit(5)
    ).mappings()
    recent = session.execute(
        sa.select(
            models.orders.c.id,
            models.orders.c.folio,
            models.orders.c.order_type,
            models.orders.c.status,
            models.orders.c.total_cents,
            models.orders.c.created_at,
        )
        .where(models.orders.c.customer_id == customer_id)
        .order_by(models.orders.c.created_at.desc())
        .limit(5)
    ).mappings()
    return {
        "order_count": order_count,
        "last_order_at": aggregate["last_order_at"],
        "average_ticket_cents": int(aggregate["total_cents"] or 0) // order_count
        if order_count
        else 0,
        "frequent_products": [dict(row) for row in frequent],
        "recent_orders": [dict(row) for row in recent],
    }


def repeat_order(
    session: Session,
    order_id: str,
    register_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    original = (
        session.execute(sa.select(models.orders).where(models.orders.c.id == order_id))
        .mappings()
        .first()
    )
    if not original:
        raise BusinessError("order_not_found", "Order was not found")
    lines = [
        dict(row)
        for row in session.execute(
            sa.select(models.order_lines.c.product_id, models.order_lines.c.quantity).where(
                models.order_lines.c.order_id == order_id
            )
        ).mappings()
    ]
    address_snapshot = original["delivery_address_snapshot"] or {}
    delivery_address_id = address_snapshot.get("id") if isinstance(address_snapshot, dict) else None
    return create_local_order(
        session,
        lines,
        original["owner_name"],
        original["order_type"],
        original["branch_id"],
        register_id,
        actor_user_id,
        original["customer_id"],
        delivery_address_id,
        original["payment_method_intent"],
    )


def create_supplier(
    session: Session,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage", branch_id=None)
    code = str(payload.get("code", "")).strip().upper()
    commercial_name = str(payload.get("commercial_name", "")).strip()
    if not code or not commercial_name:
        raise BusinessError("invalid_supplier", "Supplier code and commercial name are required")
    tax_id = str(payload.get("tax_id", "")).strip().upper() or None
    duplicate_conditions = [models.suppliers.c.code == code]
    if tax_id is not None:
        duplicate_conditions.append(models.suppliers.c.tax_id == tax_id)
    duplicate = session.execute(
        sa.select(models.suppliers.c.id).where(
            models.suppliers.c.organization_id == ORGANIZATION_ID,
            sa.or_(*duplicate_conditions),
        )
    ).scalar_one_or_none()
    if duplicate:
        raise BusinessError("supplier_already_exists", "Supplier code or RFC already exists")
    now = _now()
    email_val = (
        str(payload.get("email") or payload.get("billing_email") or "").strip().lower() or None
    )
    address_val = str(payload.get("address") or payload.get("fiscal_address") or "").strip() or None
    postal_code_val = (
        str(payload.get("postal_code") or payload.get("fiscal_postal_code") or "").strip() or None
    )
    phone_val = str(payload.get("phone") or "").strip() or None
    supplier_type_val = (
        str(payload.get("supplier_type") or payload.get("type") or "insumos").strip().lower()
    )
    accounting_ref_val = (
        str(payload.get("accounting_reference") or payload.get("cuenta_contable") or "").strip()
        or None
    )
    status_val = str(payload.get("status") or payload.get("estatus") or "active").strip().lower()

    supplier: dict[str, Any] = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "code": code,
        "commercial_name": commercial_name,
        "legal_name": payload.get("legal_name"),
        "tax_id": tax_id,
        "tax_regime": payload.get("tax_regime"),
        "fiscal_address": address_val,
        "fiscal_postal_code": postal_code_val,
        "municipality": payload.get("municipality"),
        "state": payload.get("state"),
        "country": str(payload.get("country", "MX")).upper(),
        "billing_email": email_val,
        "phone": phone_val,
        "supplier_type": supplier_type_val,
        "credit_days": int(payload.get("credit_days", 0)),
        "credit_limit": payload.get("credit_limit"),
        "currency": str(payload.get("currency", "MXN")).upper(),
        "minimum_amount": payload.get("minimum_amount"),
        "usual_lead_time_days": payload.get("usual_lead_time_days"),
        "delivery_days": list(payload.get("delivery_days", [])),
        "payment_methods": list(payload.get("payment_methods", [])),
        "accounting_reference": accounting_ref_val,
        "notes": payload.get("notes"),
        "status": status_val if status_val in {"active", "inactive", "suspended"} else "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.suppliers.insert().values(**supplier))
    _audit(
        session,
        "supplier.created",
        "supplier",
        supplier["id"],
        {"code": code, "commercial_name": commercial_name, "supplier_type": supplier_type_val},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return supplier


def update_supplier(
    session: Session,
    supplier_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage", branch_id=None)
    existing = (
        session.execute(
            sa.select(models.suppliers).where(
                models.suppliers.c.id == supplier_id,
                models.suppliers.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not existing:
        raise BusinessError("supplier_not_found", "Supplier was not found")

    now = _now()
    updates: dict[str, Any] = {"updated_at": now}

    if "commercial_name" in payload:
        name = str(payload["commercial_name"]).strip()
        if not name:
            raise BusinessError("invalid_commercial_name", "Commercial name cannot be empty")
        updates["commercial_name"] = name
    if "legal_name" in payload:
        updates["legal_name"] = str(payload["legal_name"]).strip() or None
    if "tax_id" in payload:
        tax_id = str(payload["tax_id"]).strip().upper() or None
        if tax_id:
            duplicate = session.execute(
                sa.select(models.suppliers.c.id).where(
                    models.suppliers.c.organization_id == ORGANIZATION_ID,
                    models.suppliers.c.tax_id == tax_id,
                    models.suppliers.c.id != supplier_id,
                )
            ).scalar_one_or_none()
            if duplicate:
                raise BusinessError(
                    "tax_id_already_exists", "RFC is already registered to another supplier"
                )
        updates["tax_id"] = tax_id
    if "tax_regime" in payload:
        updates["tax_regime"] = str(payload["tax_regime"]).strip() or None
    if "address" in payload or "fiscal_address" in payload:
        updates["fiscal_address"] = (
            str(payload.get("address") or payload.get("fiscal_address") or "").strip() or None
        )
    if "postal_code" in payload or "fiscal_postal_code" in payload:
        updates["fiscal_postal_code"] = (
            str(payload.get("postal_code") or payload.get("fiscal_postal_code") or "").strip()
            or None
        )
    if "phone" in payload:
        updates["phone"] = str(payload["phone"]).strip() or None
    if "email" in payload or "billing_email" in payload:
        updates["billing_email"] = (
            str(payload.get("email") or payload.get("billing_email") or "").strip().lower() or None
        )
    if "supplier_type" in payload or "type" in payload:
        updates["supplier_type"] = (
            str(payload.get("supplier_type") or payload.get("type") or "insumos").strip().lower()
        )
    if "accounting_reference" in payload or "cuenta_contable" in payload:
        updates["accounting_reference"] = (
            str(payload.get("accounting_reference") or payload.get("cuenta_contable") or "").strip()
            or None
        )
    if "municipality" in payload:
        updates["municipality"] = str(payload["municipality"]).strip() or None
    if "state" in payload:
        updates["state"] = str(payload["state"]).strip() or None
    if "country" in payload:
        updates["country"] = str(payload["country"]).strip().upper() or "MX"
    if "credit_days" in payload:
        updates["credit_days"] = int(payload["credit_days"])
    if "credit_limit" in payload:
        updates["credit_limit"] = payload["credit_limit"]
    if "notes" in payload:
        updates["notes"] = str(payload["notes"]).strip() or None
    if "status" in payload or "estatus" in payload:
        st = str(payload.get("status") or payload.get("estatus") or "active").strip().lower()
        if st in {"active", "inactive", "suspended"}:
            updates["status"] = st

    session.execute(
        sa.update(models.suppliers).where(models.suppliers.c.id == supplier_id).values(**updates)
    )
    _audit(
        session,
        "supplier.updated",
        "supplier",
        supplier_id,
        updates,
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()

    updated = (
        session.execute(sa.select(models.suppliers).where(models.suppliers.c.id == supplier_id))
        .mappings()
        .first()
    )
    return dict(updated) if updated else updates


def delete_supplier(
    session: Session,
    supplier_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage", branch_id=None)
    existing = (
        session.execute(
            sa.select(models.suppliers).where(
                models.suppliers.c.id == supplier_id,
                models.suppliers.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not existing:
        raise BusinessError("supplier_not_found", "Supplier was not found")

    has_presentations = (
        session.execute(
            sa.select(models.purchase_presentations.c.id).where(
                models.purchase_presentations.c.supplier_id == supplier_id
            )
        ).first()
        is not None
    )

    has_purchases = False
    if hasattr(models, "branch_purchases"):
        has_purchases = (
            session.execute(
                sa.select(models.branch_purchases.c.id).where(
                    models.branch_purchases.c.supplier_id == supplier_id
                )
            ).first()
            is not None
        )

    if not has_presentations and not has_purchases:
        session.execute(
            sa.delete(models.supplier_contacts).where(
                models.supplier_contacts.c.supplier_id == supplier_id
            )
        )
        session.execute(
            sa.delete(models.supplier_branch_terms).where(
                models.supplier_branch_terms.c.supplier_id == supplier_id
            )
        )
        session.execute(sa.delete(models.suppliers).where(models.suppliers.c.id == supplier_id))
        _audit(
            session,
            "supplier.deleted",
            "supplier",
            supplier_id,
            {"code": existing["code"]},
            branch_id=None,
            actor_user_id=actor_id,
        )
        session.commit()
        return {"id": supplier_id, "deleted": True, "status": "deleted"}

    now = _now()
    session.execute(
        sa.update(models.suppliers)
        .where(models.suppliers.c.id == supplier_id)
        .values(status="inactive", updated_at=now)
    )
    _audit(
        session,
        "supplier.deactivated",
        "supplier",
        supplier_id,
        {"status": "inactive"},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return {"id": supplier_id, "deleted": False, "status": "inactive"}


def add_supplier_contact(
    session: Session,
    supplier_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage", branch_id=None)
    supplier = session.execute(
        sa.select(models.suppliers.c.id).where(
            models.suppliers.c.id == supplier_id,
            models.suppliers.c.organization_id == ORGANIZATION_ID,
        )
    ).scalar_one_or_none()
    if not supplier:
        raise BusinessError("supplier_not_found", "Supplier was not found")
    name = str(payload.get("name", "")).strip()
    contact_type = str(payload.get("contact_type", "orders")).lower()
    if not name or contact_type not in {"orders", "billing", "collection", "general"}:
        raise BusinessError("invalid_supplier_contact", "Contact name and valid type are required")
    now = _now()
    contact: dict[str, Any] = {
        "id": _id(),
        "supplier_id": supplier_id,
        "name": name,
        "position_area": payload.get("position_area"),
        "phone": payload.get("phone"),
        "whatsapp": payload.get("whatsapp"),
        "email": payload.get("email"),
        "contact_type": contact_type,
        "schedule": payload.get("schedule"),
        "primary_for_orders": bool(payload.get("primary_for_orders", False)),
        "primary_for_billing": bool(payload.get("primary_for_billing", False)),
        "primary_for_collection": bool(payload.get("primary_for_collection", False)),
        "notes": payload.get("notes"),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    for flag in ("primary_for_orders", "primary_for_billing", "primary_for_collection"):
        if contact[flag]:
            session.execute(
                sa.update(models.supplier_contacts)
                .where(
                    models.supplier_contacts.c.supplier_id == supplier_id,
                    getattr(models.supplier_contacts.c, flag).is_(True),
                )
                .values(**{flag: False, "updated_at": now})
            )
    session.execute(models.supplier_contacts.insert().values(**contact))
    _audit(
        session,
        "supplier.contact_added",
        "supplier_contact",
        contact["id"],
        {"supplier_id": supplier_id, "contact_type": contact_type},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return contact


def set_supplier_branch_terms(
    session: Session,
    supplier_id: str,
    branch_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage", branch_id=None)
    supplier = session.execute(
        sa.select(models.suppliers.c.id).where(models.suppliers.c.id == supplier_id)
    ).scalar_one_or_none()
    branch = session.execute(
        sa.select(models.branches.c.id).where(
            models.branches.c.id == branch_id, models.branches.c.organization_id == ORGANIZATION_ID
        )
    ).scalar_one_or_none()
    if not supplier or not branch:
        raise BusinessError("supplier_or_branch_not_found", "Supplier and branch are required")
    terms = {
        "supplier_id": supplier_id,
        "branch_id": branch_id,
        "is_enabled": bool(payload.get("is_enabled", True)),
        "lead_time_days": payload.get("lead_time_days"),
        "minimum_amount": payload.get("minimum_amount"),
        "notes": payload.get("notes"),
        "updated_at": _now(),
    }
    existing = session.execute(
        sa.select(models.supplier_branch_terms.c.supplier_id).where(
            models.supplier_branch_terms.c.supplier_id == supplier_id,
            models.supplier_branch_terms.c.branch_id == branch_id,
        )
    ).scalar_one_or_none()
    if existing:
        session.execute(
            sa.update(models.supplier_branch_terms)
            .where(
                models.supplier_branch_terms.c.supplier_id == supplier_id,
                models.supplier_branch_terms.c.branch_id == branch_id,
            )
            .values(**terms)
        )
    else:
        session.execute(models.supplier_branch_terms.insert().values(**terms))
    _audit(
        session,
        "supplier.branch_terms_set",
        "supplier",
        supplier_id,
        {"branch_id": branch_id, "is_enabled": terms["is_enabled"]},
        branch_id,
        actor_user_id=actor_id,
    )
    session.commit()
    return terms


def create_purchase_presentation(
    session: Session,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    authorize_branch_scope(session, actor_id, "purchases.manage")
    item_id = str(payload.get("item_id", ""))
    item = (
        session.execute(
            sa.select(models.inventory_items).where(
                models.inventory_items.c.id == item_id,
                models.inventory_items.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not item:
        raise BusinessError("presentation_reference_not_found", "Item is required")

    supplier_id = str(payload.get("supplier_id") or "")
    supplier = None
    if supplier_id:
        supplier = session.execute(
            sa.select(models.suppliers.c.id).where(
                models.suppliers.c.id == supplier_id,
                models.suppliers.c.organization_id == ORGANIZATION_ID,
                models.suppliers.c.status == "active",
            )
        ).scalar_one_or_none()
    if not supplier:
        supplier = session.execute(
            sa.select(models.suppliers.c.id).where(
                models.suppliers.c.organization_id == ORGANIZATION_ID,
                models.suppliers.c.status == "active",
            )
        ).scalar_one_or_none()
        if not supplier:
            # Fallback supplier
            supplier = session.execute(
                sa.select(models.suppliers.c.id).where(
                    models.suppliers.c.organization_id == ORGANIZATION_ID
                )
            ).scalar_one_or_none()
        supplier_id = supplier or ""

    base_unit_id = str(payload.get("base_unit_id") or item["base_unit_id"])
    commercial_unit_id = str(payload.get("commercial_unit_id") or base_unit_id)

    code = str(payload.get("code") or "").strip().upper()
    if not code:
        code = f"PRES-{item['sku']}-{_id()[:4].upper()}"

    name = str(payload.get("name") or "").strip()
    if not name:
        name = f"{item['name']} (Presentación)"

    usable = Decimal(str(payload.get("usable_content") or payload.get("base_unit_yield") or "1"))
    base_yield = Decimal(str(payload.get("base_unit_yield") or usable))
    net_price = Decimal(str(payload.get("last_net_price") or "0"))
    yield_percent = Decimal(str(payload.get("yield_percent") or "1"))

    if usable <= 0 or base_yield <= 0 or net_price < 0:
        raise BusinessError(
            "invalid_purchase_presentation", "Positive yield and nonnegative price are required"
        )

    cost_per_base = (net_price / usable).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    now = _now()
    presentation: dict[str, Any] = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "supplier_id": supplier_id,
        "item_id": item_id,
        "code": code,
        "name": name,
        "package_type": str(payload.get("package_type", "commercial")),
        "commercial_quantity": Decimal(str(payload.get("commercial_quantity", "1"))),
        "commercial_unit_id": commercial_unit_id,
        "base_unit_id": base_unit_id,
        "base_unit_yield": base_yield,
        "gross_content": payload.get("gross_content"),
        "net_content": payload.get("net_content"),
        "usable_content": usable,
        "yield_percent": yield_percent,
        "barcode": payload.get("barcode"),
        "tax_rate": Decimal(str(payload.get("tax_rate", "0"))),
        "last_net_price": net_price,
        "cost_per_base_unit": cost_per_base,
        "is_preferred": bool(payload.get("is_preferred", True)),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.purchase_presentations.insert().values(**presentation))
    _record_supplier_price(session, presentation, actor_id, now)
    _audit(
        session,
        "purchase_presentation.created",
        "purchase_presentation",
        presentation["id"],
        {"code": code, "supplier_id": supplier_id, "item_id": item_id},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return presentation


def update_purchase_presentation(
    session: Session,
    presentation_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "admin.manage")
    current = (
        session.execute(
            sa.select(models.purchase_presentations).where(
                models.purchase_presentations.c.id == presentation_id,
                models.purchase_presentations.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not current:
        raise BusinessError(
            "purchase_presentation_not_found", "Purchase presentation was not found"
        )

    name = str(payload.get("name") or current["name"]).strip()
    usable = Decimal(
        str(
            payload.get("usable_content")
            or payload.get("base_unit_yield")
            or current["usable_content"]
        )
    )
    base_yield = Decimal(str(payload.get("base_unit_yield") or usable))
    net_price = Decimal(
        str(
            payload.get("last_net_price")
            if "last_net_price" in payload
            else (payload.get("net_price") if "net_price" in payload else current["last_net_price"])
        )
    )
    tax_rate = Decimal(
        str(payload.get("tax_rate") if "tax_rate" in payload else current["tax_rate"])
    )

    if usable <= 0 or base_yield <= 0 or net_price < 0:
        raise BusinessError(
            "invalid_presentation", "Yield and price must be positive and nonnegative"
        )

    cost = (net_price / usable).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    now = _now()
    updated = {
        **dict(current),
        "name": name,
        "base_unit_yield": base_yield,
        "usable_content": usable,
        "last_net_price": net_price,
        "cost_per_base_unit": cost,
        "tax_rate": tax_rate,
        "updated_at": now,
    }
    session.execute(
        sa.update(models.purchase_presentations)
        .where(models.purchase_presentations.c.id == presentation_id)
        .values(
            name=name,
            base_unit_yield=base_yield,
            usable_content=usable,
            last_net_price=net_price,
            cost_per_base_unit=cost,
            tax_rate=tax_rate,
            updated_at=now,
        )
    )
    _record_supplier_price(session, updated, actor_id, now)
    _audit(
        session,
        "purchase_presentation.updated",
        "purchase_presentation",
        presentation_id,
        {"name": name, "net_price": str(net_price), "cost_per_base_unit": str(cost)},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return updated


def update_purchase_presentation_price(
    session: Session,
    presentation_id: str,
    net_price_value: Any,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    return update_purchase_presentation(
        session, presentation_id, {"last_net_price": net_price_value}, actor_user_id
    )


def _record_supplier_price(
    session: Session, presentation: dict[str, Any], actor_id: str, now: datetime
) -> None:
    session.execute(
        models.supplier_price_history.insert().values(
            id=_id(),
            presentation_id=presentation["id"],
            supplier_id=presentation["supplier_id"],
            net_price=presentation["last_net_price"],
            cost_per_base_unit=presentation["cost_per_base_unit"],
            currency="MXN",
            effective_at=now,
            recorded_by=actor_id,
            created_at=now,
        )
    )


def list_suppliers(session: Session) -> list[dict[str, Any]]:
    result = []
    rows = session.execute(
        sa.select(models.suppliers)
        .where(models.suppliers.c.organization_id == ORGANIZATION_ID)
        .order_by(models.suppliers.c.commercial_name)
    ).mappings()
    for row in rows:
        supplier = dict(row)
        supplier["contacts"] = [
            dict(item)
            for item in session.execute(
                sa.select(models.supplier_contacts).where(
                    models.supplier_contacts.c.supplier_id == row["id"]
                )
            ).mappings()
        ]
        supplier["branch_terms"] = [
            dict(item)
            for item in session.execute(
                sa.select(models.supplier_branch_terms).where(
                    models.supplier_branch_terms.c.supplier_id == row["id"]
                )
            ).mappings()
        ]
        result.append(supplier)
    return result


def list_purchase_presentations(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(
            models.purchase_presentations,
            models.suppliers.c.commercial_name.label("supplier_name"),
            models.inventory_items.c.name.label("item_name"),
            models.inventory_units.c.code.label("base_unit_code"),
        )
        .select_from(
            models.purchase_presentations.join(
                models.suppliers,
                models.purchase_presentations.c.supplier_id == models.suppliers.c.id,
            )
            .join(
                models.inventory_items,
                models.purchase_presentations.c.item_id == models.inventory_items.c.id,
            )
            .join(
                models.inventory_units,
                models.purchase_presentations.c.base_unit_id == models.inventory_units.c.id,
            )
        )
        .where(models.purchase_presentations.c.organization_id == ORGANIZATION_ID)
        .order_by(models.purchase_presentations.c.name)
    ).mappings()
    result = []
    for row in rows:
        presentation = dict(row)
        presentation["price_history"] = [
            dict(item)
            for item in session.execute(
                sa.select(models.supplier_price_history)
                .where(models.supplier_price_history.c.presentation_id == row["id"])
                .order_by(models.supplier_price_history.c.effective_at)
            ).mappings()
        ]
        result.append(presentation)
    return result


def create_purchase_document(
    session: Session,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    branch_id = str(payload.get("branch_id", ""))
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "purchases.manage", branch_id)
    supplier_id = str(payload.get("supplier_id", "")).strip()
    supplier = None
    if supplier_id:
        supplier = (
            session.execute(
                sa.select(models.suppliers).where(
                    models.suppliers.c.id == supplier_id,
                    models.suppliers.c.organization_id == ORGANIZATION_ID,
                    models.suppliers.c.status == "active",
                )
            )
            .mappings()
            .first()
        )
    if not supplier:
        # Default or provision general supplier
        supplier = (
            session.execute(
                sa.select(models.suppliers).where(
                    models.suppliers.c.organization_id == ORGANIZATION_ID,
                    models.suppliers.c.status == "active",
                ).order_by(models.suppliers.c.created_at)
            )
            .mappings()
            .first()
        )
        if not supplier:
            sup_id = _id()
            now_dt = _now()
            session.execute(
                models.suppliers.insert().values(
                    id=sup_id,
                    organization_id=ORGANIZATION_ID,
                    code="SUP-GEN",
                    commercial_name="Proveedor General",
                    legal_name="Proveedor General",
                    credit_days=0,
                    status="active",
                    created_at=now_dt,
                    updated_at=now_dt,
                )
            )
            supplier = session.execute(
                sa.select(models.suppliers).where(models.suppliers.c.id == sup_id)
            ).mappings().first()
        supplier_id = supplier["id"]

    branch = session.execute(
        sa.select(models.branches.c.id).where(
            models.branches.c.id == branch_id,
            models.branches.c.organization_id == ORGANIZATION_ID,
            models.branches.c.status == "active",
        )
    ).scalar_one_or_none()
    if not branch:
        raise BusinessError(
            "purchase_supplier_or_branch_not_found", "Active branch is required"
        )
    terms = (
        session.execute(
            sa.select(models.supplier_branch_terms).where(
                models.supplier_branch_terms.c.supplier_id == supplier_id,
                models.supplier_branch_terms.c.branch_id == branch_id,
            )
        )
        .mappings()
        .first()
    )
    if terms and not terms["is_enabled"]:
        raise BusinessError(
            "supplier_not_enabled_for_branch", "Supplier is disabled for this branch"
        )
    document_type = str(payload.get("document_type", "receipt")).strip().lower()
    if document_type not in {"invoice", "receipt", "ticket", "note"}:
        raise BusinessError("invalid_purchase_document_type", "Purchase document type is invalid")
    now = _now()
    folio = str(payload.get("folio", "")).strip()
    if not folio:
        folio = f"COMP-{now.strftime('%Y%m%d')}-{uuid4().hex[:4].upper()}"
    freight = _money(payload.get("freight_total", "0"))
    if freight != 0:
        raise BusinessError(
            "freight_cost_policy_required", "Freight allocation policy is not approved"
        )
    raw_lines = list(payload.get("lines", []))
    if not raw_lines:
        raise BusinessError("purchase_lines_required", "Purchase requires at least one line")
    document_id = _id()
    lines: list[dict[str, Any]] = []
    subtotal = Decimal("0")
    discount_total = Decimal("0")
    tax_total = Decimal("0")
    for raw in raw_lines:
        presentation = None
        pres_id = str(raw.get("presentation_id", "")).strip()
        if pres_id:
            presentation = (
                session.execute(
                    sa.select(models.purchase_presentations).where(
                        models.purchase_presentations.c.id == pres_id,
                        models.purchase_presentations.c.status == "active",
                    )
                )
                .mappings()
                .first()
            )

        quantity = _quantity(raw.get("quantity", "0"))
        unit_price = _money(raw.get("unit_price", "0"))
        discount = _money(raw.get("discount", "0"))
        tax = _money(raw.get("tax", "0"))

        if not presentation:
            concept = str(
                raw.get("concept")
                or raw.get("description")
                or raw.get("name")
                or raw.get("item_name")
                or "Gasto General"
            ).strip()

            # Find or create inventory item
            item = session.execute(
                sa.select(models.inventory_items).where(
                    models.inventory_items.c.organization_id == ORGANIZATION_ID,
                    sa.func.lower(models.inventory_items.c.name) == concept.lower(),
                )
            ).mappings().first()

            if not item:
                unit = session.execute(
                    sa.select(models.inventory_units.c.id).where(
                        models.inventory_units.c.code == "PZA"
                    )
                ).scalar_one_or_none()
                if not unit:
                    unit = session.execute(sa.select(models.inventory_units.c.id)).scalars().first()
                item_id = _id()
                clean_prefix = re.sub(r'[^A-Z0-9]+', '', concept.upper())[:6] or "INS"
                sku = f"{clean_prefix}-{uuid4().hex[:4].upper()}"
                session.execute(
                    models.inventory_items.insert().values(
                        id=item_id,
                        organization_id=ORGANIZATION_ID,
                        name=concept,
                        sku=sku,
                        base_unit_id=unit,
                        item_type="ingredient",
                        status="active",
                        created_at=now,
                        updated_at=now,
                    )
                )
                item = session.execute(
                    sa.select(models.inventory_items).where(models.inventory_items.c.id == item_id)
                ).mappings().first()

            pres_id = _id()
            pres_code = f"P-{uuid4().hex[:6].upper()}"
            session.execute(
                models.purchase_presentations.insert().values(
                    id=pres_id,
                    organization_id=ORGANIZATION_ID,
                    supplier_id=supplier_id,
                    item_id=item["id"],
                    code=pres_code,
                    name=concept,
                    package_type="direct",
                    commercial_quantity=Decimal("1.0"),
                    commercial_unit_id=unit,
                    base_unit_id=unit,
                    base_unit_yield=Decimal("1.0"),
                    gross_content=Decimal("1.0"),
                    net_content=Decimal("1.0"),
                    usable_content=Decimal("1.0"),
                    yield_percent=Decimal("100.0"),
                    barcode=None,
                    tax_rate=Decimal("0"),
                    last_net_price=unit_price,
                    cost_per_base_unit=unit_price,
                    is_preferred=True,
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            presentation = session.execute(
                sa.select(models.purchase_presentations).where(
                    models.purchase_presentations.c.id == pres_id
                )
            ).mappings().first()
        else:
            if unit_price <= 0 and presentation.get("last_net_price"):
                unit_price = _money(presentation["last_net_price"])

        line_subtotal = _money(quantity * unit_price)
        if quantity <= 0 or unit_price < 0 or discount < 0 or discount > line_subtotal or tax < 0:
            raise BusinessError(
                "invalid_purchase_line", "Purchase line quantities and amounts are invalid"
            )
        base_quantity = _quantity(quantity * Decimal(str(presentation["base_unit_yield"])))
        inventory_cost = _money(line_subtotal - discount)
        cost_per_base = _cost(inventory_cost / base_quantity)
        line = {
            "id": _id(),
            "purchase_document_id": document_id,
            "presentation_id": presentation["id"],
            "item_id": presentation["item_id"],
            "presentation_snapshot": _sanitize_for_json(dict(presentation)),
            "presentation_quantity": quantity,
            "base_quantity": base_quantity,
            "unit_price": unit_price,
            "discount": discount,
            "tax": tax,
            "line_total": _money(inventory_cost + tax),
            "inventory_cost": inventory_cost,
            "cost_per_base_unit": cost_per_base,
            "created_at": now,
        }
        lines.append(line)
        subtotal += line_subtotal
        discount_total += discount
        tax_total += tax
    total = _money(subtotal - discount_total + tax_total)
    paid_from_cash = bool(payload.get("paid_from_cash", False))
    payment_method = str(
        payload.get("payment_method", "cash" if paid_from_cash else "other")
    ).lower()
    if paid_from_cash and payment_method != "cash":
        raise BusinessError(
            "cash_purchase_payment_mismatch", "Purchase paid from cash must use cash payment method"
        )
    document_date = _parse_document_date(payload.get("document_date"), now)
    purchase = {
        "id": document_id,
        "organization_id": ORGANIZATION_ID,
        "branch_id": branch_id,
        "supplier_id": supplier_id,
        "document_type": document_type,
        "folio": folio,
        "document_date": document_date,
        "subtotal": _money(subtotal),
        "discount_total": _money(discount_total),
        "tax_total": _money(tax_total),
        "freight_total": freight,
        "total": total,
        "payment_method": payment_method,
        "paid_from_cash": paid_from_cash,
        "cash_movement_id": None,
        "evidence_url": payload.get("evidence_url"),
        "notes": payload.get("notes"),
        "status": "draft",
        "created_by": actor_id,
        "confirmed_by": None,
        "cancelled_by": None,
        "confirmation_idempotency_key": None,
        "cancellation_reason": None,
        "created_at": now,
        "confirmed_at": None,
        "cancelled_at": None,
    }
    session.execute(models.purchase_documents.insert().values(**purchase))
    session.execute(models.purchase_document_lines.insert(), lines)
    _audit(
        session,
        "purchase.created",
        "purchase_document",
        document_id,
        {"folio": folio, "supplier_id": supplier_id, "total": str(total)},
        branch_id,
        actor_user_id=actor_id,
    )
    session.commit()
    return {**purchase, "lines": lines}


def confirm_purchase_document(
    session: Session,
    purchase_id: str,
    idempotency_key: str,
    register_id: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    _begin_cash_shift_serialization(session)
    actor_id = _actor_user_id(actor_user_id)
    key = idempotency_key.strip()
    if not key:
        raise BusinessError("idempotency_key_required", "Confirmation idempotency key is required")
    purchase = (
        session.execute(
            sa.select(models.purchase_documents).where(
                models.purchase_documents.c.id == purchase_id
            )
        )
        .mappings()
        .first()
    )
    if not purchase:
        raise BusinessError("purchase_not_found", "Purchase document was not found")
    require_permission(session, actor_id, "purchases.manage", purchase["branch_id"])
    if purchase["status"] == "confirmed":
        if purchase["confirmation_idempotency_key"] == key:
            return get_purchase_document(session, purchase_id)
        raise BusinessError("purchase_already_confirmed", "Purchase was already confirmed")
    if purchase["status"] != "draft":
        raise BusinessError("purchase_not_confirmable", "Only draft purchases can be confirmed")
    duplicate = session.execute(
        sa.select(models.purchase_documents.c.id).where(
            models.purchase_documents.c.confirmation_idempotency_key == key,
            models.purchase_documents.c.id != purchase_id,
        )
    ).scalar_one_or_none()
    if duplicate:
        raise BusinessError(
            "idempotency_key_conflict", "Idempotency key belongs to another purchase"
        )
    lines = [
        dict(row)
        for row in session.execute(
            sa.select(models.purchase_document_lines).where(
                models.purchase_document_lines.c.purchase_document_id == purchase_id
            )
        ).mappings()
    ]
    warehouse_id = _branch_warehouse_id(session, purchase["branch_id"])
    # Validate every line before producing any externalized effect.
    for line in lines:
        physical = _physical_inventory_quantity(
            session, purchase["branch_id"], warehouse_id, line["item_id"]
        )
        if physical < 0:
            raise BusinessError(
                "negative_inventory_cost_policy_required",
                "Cannot confirm receipt while physical inventory is negative",
            )
    now = _now()
    cash_movement = None
    if purchase["paid_from_cash"]:
        require_permission(session, actor_id, "cash.movement.withdraw", purchase["branch_id"])
        register_code = (register_id or "").strip()
        if not register_code:
            raise BusinessError("cash_movement_invalid", "Cash purchase register_id is required")
        shift = _guard_open_cash_shift(session, register_code, purchase["branch_id"])
        amount_cents = int(
            (_money(purchase["total"]) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        cash_movement = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": purchase["branch_id"],
            "cash_shift_id": shift["id"],
            "movement_type": "withdrawal",
            "amount_cents": amount_cents,
            "reason_code": "SUPPLY_PURCHASE",
            "reason": "Compra de insumos",
            "source_type": "PURCHASE",
            "source_id": purchase_id,
            "actor_user_id": actor_id,
            "idempotency_key": f"{key}:cash",
            "status": "confirmed",
            "reversal_of_id": None,
            "created_at": now,
            "concept_id": None,
            "concept_version_id": None,
            "concept_snapshot": None,
            "reference": purchase["folio"],
            "evidence_refs": [],
            "compensates_movement_id": None,
        }
        session.execute(models.cash_movements.insert().values(**cash_movement))
    movements = []
    cost_states = []
    for index, line in enumerate(lines):
        current_quantity = _physical_inventory_quantity(
            session, purchase["branch_id"], warehouse_id, line["item_id"]
        )
        state = (
            session.execute(
                sa.select(models.inventory_cost_states).where(
                    models.inventory_cost_states.c.branch_id == purchase["branch_id"],
                    models.inventory_cost_states.c.warehouse_id == warehouse_id,
                    models.inventory_cost_states.c.item_id == line["item_id"],
                )
            )
            .mappings()
            .first()
        )
        current_average = _cost(state["average_unit_cost"]) if state else Decimal("0")
        entry_quantity = _quantity(line["base_quantity"])
        entry_cost = _money(line["inventory_cost"])
        new_quantity = _quantity(current_quantity + entry_quantity)
        new_average = (
            _cost(entry_cost / entry_quantity)
            if current_quantity == 0
            else _cost(((current_quantity * current_average) + entry_cost) / new_quantity)
        )
        movement = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": purchase["branch_id"],
            "warehouse_id": warehouse_id,
            "item_id": line["item_id"],
            "movement_type": "PURCHASE_RECEIPT",
            "quantity_delta": entry_quantity,
            "unit_id": line["presentation_snapshot"]["base_unit_id"],
            "unit_cost": line["cost_per_base_unit"],
            "total_cost": entry_cost,
            "effective_at": purchase["document_date"],
            "actor_user_id": actor_id,
            "document_type": purchase["document_type"],
            "document_id": purchase_id,
            "reference": purchase["folio"],
            "reason": "Recepcion de compra directa",
            "notes": purchase["notes"],
            "idempotency_key": f"{key}:inventory:{index}",
            "status": "confirmed",
            "reversal_of_id": None,
            "source_type": "purchase",
            "source_id": purchase_id,
            "created_at": now,
        }
        session.execute(models.inventory_movements.insert().values(**movement))
        state_values = {
            "branch_id": purchase["branch_id"],
            "warehouse_id": warehouse_id,
            "item_id": line["item_id"],
            "quantity_on_hand": new_quantity,
            "average_unit_cost": new_average,
            "last_unit_cost": line["cost_per_base_unit"],
            "last_supplier_id": purchase["supplier_id"],
            "last_cost_at": now,
            "updated_at": now,
        }
        if state:
            session.execute(
                sa.update(models.inventory_cost_states)
                .where(
                    models.inventory_cost_states.c.branch_id == purchase["branch_id"],
                    models.inventory_cost_states.c.warehouse_id == warehouse_id,
                    models.inventory_cost_states.c.item_id == line["item_id"],
                )
                .values(**state_values)
            )
        else:
            session.execute(models.inventory_cost_states.insert().values(**state_values))
        session.execute(
            sa.update(models.purchase_presentations)
            .where(models.purchase_presentations.c.id == line["presentation_id"])
            .values(last_net_price=line["unit_price"], updated_at=now)
        )
        presentation_for_history = {
            "id": line["presentation_id"],
            "supplier_id": purchase["supplier_id"],
            "last_net_price": line["unit_price"],
            "cost_per_base_unit": _cost(
                _money(line["unit_price"])
                / Decimal(str(line["presentation_snapshot"]["usable_content"]))
            ),
        }
        _record_supplier_price(session, presentation_for_history, actor_id, now)
        movements.append(movement)
        cost_states.append(state_values)
    session.execute(
        sa.update(models.purchase_documents)
        .where(models.purchase_documents.c.id == purchase_id)
        .values(
            status="confirmed",
            confirmed_by=actor_id,
            confirmed_at=now,
            cash_movement_id=cash_movement["id"] if cash_movement else None,
            confirmation_idempotency_key=key,
        )
    )
    _audit(
        session,
        "purchase.confirmed",
        "purchase_document",
        purchase_id,
        {
            "movement_ids": [item["id"] for item in movements],
            "cash_movement_id": cash_movement["id"] if cash_movement else None,
        },
        purchase["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_purchase_document(session, purchase_id)


def cancel_purchase_document(
    session: Session,
    purchase_id: str,
    reason: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    _begin_cash_shift_serialization(session)
    actor_id = _actor_user_id(actor_user_id)
    purchase = (
        session.execute(
            sa.select(models.purchase_documents).where(
                models.purchase_documents.c.id == purchase_id
            )
        )
        .mappings()
        .first()
    )
    if not purchase:
        raise BusinessError("purchase_not_found", "Purchase document was not found")
    require_permission(session, actor_id, "purchases.manage", purchase["branch_id"])
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise BusinessError(
            "purchase_cancellation_reason_required", "Cancellation reason is required"
        )
    if purchase["status"] == "cancelled":
        return get_purchase_document(session, purchase_id)
    if purchase["status"] == "draft":
        now = _now()
        session.execute(
            sa.update(models.purchase_documents)
            .where(models.purchase_documents.c.id == purchase_id)
            .values(
                status="cancelled",
                cancelled_by=actor_id,
                cancelled_at=now,
                cancellation_reason=normalized_reason,
            )
        )
        _audit(
            session,
            "purchase.cancelled",
            "purchase_document",
            purchase_id,
            {"reason": normalized_reason, "draft": True},
            purchase["branch_id"],
            actor_user_id=actor_id,
        )
        session.commit()
        return get_purchase_document(session, purchase_id)
    if purchase["status"] != "confirmed":
        raise BusinessError("purchase_not_cancellable", "Purchase cannot be cancelled")
    original_cash: dict[str, Any] | None = None
    if purchase["cash_movement_id"]:
        original_cash = dict(
            session.execute(
                sa.select(models.cash_movements).where(
                    models.cash_movements.c.id == purchase["cash_movement_id"]
                )
            )
            .mappings()
            .one()
        )
        register_code = session.execute(
            sa.select(models.cash_shifts.c.register_code).where(
                models.cash_shifts.c.id == original_cash["cash_shift_id"]
            )
        ).scalar_one()
        open_shift = _guard_open_cash_shift(session, register_code, purchase["branch_id"])
        if not open_shift or open_shift["id"] != original_cash["cash_shift_id"]:
            session.rollback()
            raise BusinessError("cash_shift_not_open", "Original cash shift is not OPEN")
        already_compensated = session.execute(
            sa.select(models.cash_movements.c.id).where(
                sa.or_(
                    models.cash_movements.c.reversal_of_id == original_cash["id"],
                    models.cash_movements.c.compensates_movement_id == original_cash["id"],
                )
            )
        ).scalar_one_or_none()
        if already_compensated:
            raise BusinessError(
                "cash_movement_already_compensated",
                "Cash purchase was already compensated",
            )
    receipts = [
        dict(row)
        for row in session.execute(
            sa.select(models.inventory_movements).where(
                models.inventory_movements.c.source_type == "purchase",
                models.inventory_movements.c.source_id == purchase_id,
                models.inventory_movements.c.movement_type == "PURCHASE_RECEIPT",
            )
        ).mappings()
    ]
    warehouse_id = _branch_warehouse_id(session, purchase["branch_id"])
    for receipt in receipts:
        physical = _physical_inventory_quantity(
            session, purchase["branch_id"], warehouse_id, receipt["item_id"]
        )
        if physical - _quantity(receipt["quantity_delta"]) < 0:
            raise BusinessError(
                "purchase_reversal_insufficient_stock",
                "Received stock was already consumed or transferred",
            )
    now = _now()
    for index, receipt in enumerate(receipts):
        current_quantity = _physical_inventory_quantity(
            session, purchase["branch_id"], warehouse_id, receipt["item_id"]
        )
        state = (
            session.execute(
                sa.select(models.inventory_cost_states).where(
                    models.inventory_cost_states.c.branch_id == purchase["branch_id"],
                    models.inventory_cost_states.c.warehouse_id == warehouse_id,
                    models.inventory_cost_states.c.item_id == receipt["item_id"],
                )
            )
            .mappings()
            .first()
        )
        current_average = _cost(state["average_unit_cost"]) if state else Decimal("0")
        removed_quantity = _quantity(receipt["quantity_delta"])
        new_quantity = _quantity(current_quantity - removed_quantity)
        if new_quantity == 0:
            remaining_value = Decimal("0")
        else:
            remaining_value = _money(
                (current_quantity * current_average) - _money(receipt["total_cost"])
            )
            if Decimal("-0.01") <= remaining_value <= Decimal("0"):
                remaining_value = Decimal("0")
            elif remaining_value < Decimal("-0.01"):
                raise BusinessError(
                    "purchase_reversal_cost_conflict",
                    "Purchase reversal would create negative inventory value",
                )
        new_average = Decimal("0") if new_quantity == 0 else _cost(remaining_value / new_quantity)
        reversal = {
            **{
                key: receipt[key]
                for key in ("organization_id", "branch_id", "warehouse_id", "item_id", "unit_id")
            },
            "id": _id(),
            "movement_type": "PURCHASE_REVERSAL",
            "quantity_delta": -removed_quantity,
            "unit_cost": receipt["unit_cost"],
            "total_cost": -_money(receipt["total_cost"]),
            "effective_at": now,
            "actor_user_id": actor_id,
            "document_type": purchase["document_type"],
            "document_id": purchase_id,
            "reference": purchase["folio"],
            "reason": normalized_reason,
            "notes": None,
            "idempotency_key": f"purchase-cancel:{purchase_id}:inventory:{index}",
            "status": "confirmed",
            "reversal_of_id": receipt["id"],
            "source_type": "purchase_cancellation",
            "source_id": purchase_id,
            "created_at": now,
        }
        session.execute(models.inventory_movements.insert().values(**reversal))
        session.execute(
            sa.update(models.inventory_cost_states)
            .where(
                models.inventory_cost_states.c.branch_id == purchase["branch_id"],
                models.inventory_cost_states.c.warehouse_id == warehouse_id,
                models.inventory_cost_states.c.item_id == receipt["item_id"],
            )
            .values(quantity_on_hand=new_quantity, average_unit_cost=new_average, updated_at=now)
        )
    if original_cash:
        session.execute(
            models.cash_movements.insert().values(
                id=_id(),
                organization_id=ORGANIZATION_ID,
                branch_id=purchase["branch_id"],
                cash_shift_id=original_cash["cash_shift_id"],
                movement_type="deposit",
                amount_cents=original_cash["amount_cents"],
                reason_code="PURCHASE_CANCELLATION",
                reason=normalized_reason,
                source_type="PURCHASE_CANCELLATION",
                source_id=purchase_id,
                actor_user_id=actor_id,
                idempotency_key=f"purchase-cancel:{purchase_id}:cash",
                status="confirmed",
                reversal_of_id=original_cash["id"],
                created_at=now,
                concept_id=None,
                concept_version_id=None,
                concept_snapshot=None,
                reference=purchase["folio"],
                evidence_refs=[],
                compensates_movement_id=original_cash["id"],
            )
        )
    session.execute(
        sa.update(models.purchase_documents)
        .where(models.purchase_documents.c.id == purchase_id)
        .values(
            status="cancelled",
            cancelled_by=actor_id,
            cancelled_at=now,
            cancellation_reason=normalized_reason,
        )
    )
    _audit(
        session,
        "purchase.cancelled",
        "purchase_document",
        purchase_id,
        {"reason": normalized_reason, "receipt_count": len(receipts)},
        purchase["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_purchase_document(session, purchase_id)


def get_purchase_document(session: Session, purchase_id: str) -> dict[str, Any]:
    purchase = (
        session.execute(
            sa.select(models.purchase_documents).where(
                models.purchase_documents.c.id == purchase_id
            )
        )
        .mappings()
        .first()
    )
    if not purchase:
        raise BusinessError("purchase_not_found", "Purchase document was not found")
    result = dict(purchase)
    result["lines"] = [
        dict(row)
        for row in session.execute(
            sa.select(models.purchase_document_lines).where(
                models.purchase_document_lines.c.purchase_document_id == purchase_id
            )
        ).mappings()
    ]
    result["inventory_movements"] = [
        dict(row)
        for row in session.execute(
            sa.select(models.inventory_movements)
            .where(
                sa.or_(
                    sa.and_(
                        models.inventory_movements.c.source_type == "purchase",
                        models.inventory_movements.c.source_id == purchase_id,
                    ),
                    sa.and_(
                        models.inventory_movements.c.source_type == "purchase_cancellation",
                        models.inventory_movements.c.source_id == purchase_id,
                    ),
                )
            )
            .order_by(models.inventory_movements.c.created_at)
        ).mappings()
    ]
    result["cash_movements"] = [
        _serialize_cash_movement(dict(row))
        for row in session.execute(
            sa.select(models.cash_movements)
            .where(models.cash_movements.c.source_id == purchase_id)
            .order_by(models.cash_movements.c.created_at)
        ).mappings()
    ]
    return result


def list_purchase_documents(session: Session, branch_id: str | None) -> list[dict[str, Any]]:
    ids = session.execute(
        sa.select(models.purchase_documents.c.id)
        .where(models.purchase_documents.c.branch_id == branch_id)
        .order_by(models.purchase_documents.c.created_at.desc())
    ).scalars()
    return [get_purchase_document(session, purchase_id) for purchase_id in ids]


def _cash_concept_key(idempotency_key: str) -> str:
    key = idempotency_key.strip()
    if not key:
        raise BusinessError(
            "idempotency_key_required", "Cash concept mutation requires Idempotency-Key"
        )
    if len(key) > 180:
        raise BusinessError("cash_concept_invalid", "Idempotency-Key is too long")
    return key


def _cash_concept_values(payload: dict[str, Any], *, include_code: bool) -> dict[str, Any]:
    code = str(payload.get("code", "")).strip().upper()
    if include_code and not CASH_CONCEPT_CODE_PATTERN.fullmatch(code):
        raise BusinessError(
            "cash_concept_invalid",
            "Cash concept code must use uppercase letters, numbers or underscores",
        )
    name = str(payload.get("name", "")).strip()
    if not name or len(name) > 160:
        raise BusinessError("cash_concept_invalid", "Cash concept name is required")
    movement_type = str(payload.get("allowed_movement_type", "")).strip().lower()
    if movement_type not in {"deposit", "withdrawal", "both"}:
        raise BusinessError(
            "cash_concept_invalid",
            "Cash concept type must be deposit, withdrawal or both",
        )
    if payload.get("requires_reference") is not True:
        raise BusinessError("cash_concept_invalid", "Manual cash reference is required")
    if payload.get("requires_evidence") is not True:
        raise BusinessError("cash_concept_invalid", "Manual cash evidence is required")
    raw_valid_from = payload.get("valid_from")
    try:
        if isinstance(raw_valid_from, datetime):
            valid_from = raw_valid_from
        else:
            valid_from = datetime.fromisoformat(str(raw_valid_from).replace("Z", "+00:00"))
        if valid_from.tzinfo is None:
            raise ValueError("timezone required")
        valid_from = valid_from.astimezone(UTC)
    except (TypeError, ValueError) as exc:
        raise BusinessError(
            "cash_concept_invalid", "Cash concept valid_from must be an ISO-8601 UTC timestamp"
        ) from exc
    values: dict[str, Any] = {
        "name": name,
        "allowed_movement_type": movement_type,
        "requires_reference": True,
        "requires_evidence": True,
        "valid_from": valid_from,
    }
    if include_code:
        values["code"] = code
    return values


def _cash_concept_request_hash(
    command_type: str,
    concept_id: str | None,
    actor_user_id: str,
    values: dict[str, Any],
) -> str:
    canonical = json.dumps(
        {
            "command_type": command_type,
            "concept_id": concept_id,
            "actor_user_id": actor_user_id,
            "values": _sanitize_for_json(values),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _log_cash_concept(
    action: str,
    result: str,
    actor_user_id: str,
    concept_id: str | None,
) -> None:
    logger.info(
        "cash_concept_command",
        extra={
            "action": action,
            "result": result,
            "actor_user_id": actor_user_id,
            "organization_id": ORGANIZATION_ID,
            "concept_id": concept_id,
            "correlation_id": None,
        },
    )


def _cash_concept_replay(
    session: Session,
    key: str,
    command_type: str,
    request_hash: str,
) -> dict[str, Any] | None:
    command = (
        session.execute(
            sa.select(models.cash_concept_commands).where(
                models.cash_concept_commands.c.organization_id == ORGANIZATION_ID,
                models.cash_concept_commands.c.idempotency_key == key,
            )
        )
        .mappings()
        .first()
    )
    if not command:
        return None
    if (
        command["command_type"] != command_type
        or command["request_hash"] != request_hash
        or command["status"] != "completed"
    ):
        raise BusinessError(
            "idempotency_conflict", "Idempotency key belongs to a different request"
        )
    return dict(command["result"])


def _cash_concept_detail(session: Session, concept_id: str) -> dict[str, Any]:
    concept = (
        session.execute(
            sa.select(models.cash_movement_concepts).where(
                models.cash_movement_concepts.c.id == concept_id,
                models.cash_movement_concepts.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not concept:
        raise BusinessError("cash_concept_not_found", "Cash concept was not found")

    versions = [
        dict(row)
        for row in session.execute(
            sa.select(models.cash_movement_concept_versions)
            .where(models.cash_movement_concept_versions.c.concept_id == concept_id)
            .order_by(models.cash_movement_concept_versions.c.version)
        ).mappings()
    ]
    return cast(dict[str, Any], _sanitize_for_json({**dict(concept), "versions": versions}))


def _store_cash_concept_command(
    session: Session,
    *,
    key: str,
    command_type: str,
    request_hash: str,
    concept_id: str,
    actor_user_id: str,
    result: dict[str, Any],
    created_at: datetime,
) -> None:
    session.execute(
        models.cash_concept_commands.insert().values(
            id=_id(),
            organization_id=ORGANIZATION_ID,
            actor_user_id=actor_user_id,
            target_concept_id=concept_id,
            command_type=command_type,
            idempotency_key=key,
            request_hash=request_hash,
            result=result,
            status="completed",
            created_at=created_at,
        )
    )


def create_cash_concept(
    session: Session,
    payload: dict[str, Any],
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "cash.concept.manage")
    key = _cash_concept_key(idempotency_key)
    values = _cash_concept_values(payload, include_code=True)
    request_hash = _cash_concept_request_hash("create", None, actor_id, values)
    replay = _cash_concept_replay(session, key, "create", request_hash)
    if replay is not None:
        return replay
    existing_code = session.execute(
        sa.select(models.cash_movement_concepts.c.id).where(
            models.cash_movement_concepts.c.organization_id == ORGANIZATION_ID,
            models.cash_movement_concepts.c.code == values["code"],
        )
    ).scalar_one_or_none()
    if existing_code:
        raise BusinessError("cash_concept_code_conflict", "Cash concept code already exists")

    now = _now()
    concept_id = _id()
    try:
        session.execute(
            models.cash_movement_concepts.insert().values(
                id=concept_id,
                organization_id=ORGANIZATION_ID,
                code=values["code"],
                status="active",
                created_by_user_id=actor_id,
                created_at=now,
                archived_at=None,
            )
        )
        session.execute(
            models.cash_movement_concept_versions.insert().values(
                id=_id(),
                concept_id=concept_id,
                version=1,
                name=values["name"],
                allowed_movement_type=values["allowed_movement_type"],
                requires_reference=True,
                requires_evidence=True,
                valid_from=values["valid_from"],
                created_by_user_id=actor_id,
                created_at=now,
            )
        )
        result = _cash_concept_detail(session, concept_id)
        _store_cash_concept_command(
            session,
            key=key,
            command_type="create",
            request_hash=request_hash,
            concept_id=concept_id,
            actor_user_id=actor_id,
            result=result,
            created_at=now,
        )
        _audit(
            session,
            "cash_concept.created",
            "cash_movement_concept",
            concept_id,
            {"code": values["code"], "version": 1},
            branch_id=None,
            actor_user_id=actor_id,
        )
        _log_cash_concept("create", "success", actor_id, concept_id)
        session.commit()
        return result
    except IntegrityError as exc:
        session.rollback()
        replay = _cash_concept_replay(session, key, "create", request_hash)
        if replay is not None:
            return replay
        raise BusinessError(
            "cash_concept_code_conflict", "Cash concept code already exists"
        ) from exc
    except Exception:
        session.rollback()
        raise


def create_cash_concept_version(
    session: Session,
    concept_id: str,
    payload: dict[str, Any],
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "cash.concept.manage")
    if "code" in payload:
        raise BusinessError("cash_concept_code_immutable", "Cash concept code is immutable")
    key = _cash_concept_key(idempotency_key)
    values = _cash_concept_values(payload, include_code=False)
    request_hash = _cash_concept_request_hash("version", concept_id, actor_id, values)
    replay = _cash_concept_replay(session, key, "version", request_hash)
    if replay is not None:
        return replay
    concept = (
        session.execute(
            sa.select(models.cash_movement_concepts).where(
                models.cash_movement_concepts.c.id == concept_id,
                models.cash_movement_concepts.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not concept:
        raise BusinessError("cash_concept_not_found", "Cash concept was not found")
    if concept["status"] != "active":
        raise BusinessError("cash_concept_invalid", "Archived cash concept cannot be versioned")
    next_version = (
        int(
            session.execute(
                sa.select(sa.func.max(models.cash_movement_concept_versions.c.version)).where(
                    models.cash_movement_concept_versions.c.concept_id == concept_id
                )
            ).scalar_one()
        )
        + 1
    )
    now = _now()
    try:
        session.execute(
            models.cash_movement_concept_versions.insert().values(
                id=_id(),
                concept_id=concept_id,
                version=next_version,
                name=values["name"],
                allowed_movement_type=values["allowed_movement_type"],
                requires_reference=True,
                requires_evidence=True,
                valid_from=values["valid_from"],
                created_by_user_id=actor_id,
                created_at=now,
            )
        )
        result = _cash_concept_detail(session, concept_id)
        _store_cash_concept_command(
            session,
            key=key,
            command_type="version",
            request_hash=request_hash,
            concept_id=concept_id,
            actor_user_id=actor_id,
            result=result,
            created_at=now,
        )
        _audit(
            session,
            "cash_concept.versioned",
            "cash_movement_concept",
            concept_id,
            {"code": concept["code"], "version": next_version},
            branch_id=None,
            actor_user_id=actor_id,
        )
        _log_cash_concept("version", "success", actor_id, concept_id)
        session.commit()
        return result
    except (IntegrityError, OperationalError) as exc:
        session.rollback()
        replay = _cash_concept_replay(session, key, "version", request_hash)
        if replay is not None:
            return replay
        raise BusinessError(
            "cash_concept_version_conflict", "Cash concept version changed concurrently"
        ) from exc
    except Exception:
        session.rollback()
        raise


def archive_cash_concept(
    session: Session,
    concept_id: str,
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "cash.concept.manage")
    key = _cash_concept_key(idempotency_key)
    request_hash = _cash_concept_request_hash("archive", concept_id, actor_id, {})
    replay = _cash_concept_replay(session, key, "archive", request_hash)
    if replay is not None:
        return replay
    concept = (
        session.execute(
            sa.select(models.cash_movement_concepts).where(
                models.cash_movement_concepts.c.id == concept_id,
                models.cash_movement_concepts.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not concept:
        raise BusinessError("cash_concept_not_found", "Cash concept was not found")
    if concept["status"] != "active":
        raise BusinessError("cash_concept_invalid", "Cash concept is already archived")
    now = _now()
    try:
        session.execute(
            models.cash_movement_concepts.update()
            .where(models.cash_movement_concepts.c.id == concept_id)
            .values(status="archived", archived_at=now)
        )
        result = _cash_concept_detail(session, concept_id)
        _store_cash_concept_command(
            session,
            key=key,
            command_type="archive",
            request_hash=request_hash,
            concept_id=concept_id,
            actor_user_id=actor_id,
            result=result,
            created_at=now,
        )
        _audit(
            session,
            "cash_concept.archived",
            "cash_movement_concept",
            concept_id,
            {"code": concept["code"]},
            branch_id=None,
            actor_user_id=actor_id,
        )
        _log_cash_concept("archive", "success", actor_id, concept_id)
        session.commit()
        return result
    except IntegrityError as exc:
        session.rollback()
        replay = _cash_concept_replay(session, key, "archive", request_hash)
        if replay is not None:
            return replay
        raise BusinessError(
            "idempotency_conflict", "Idempotency key belongs to a different request"
        ) from exc
    except Exception:
        session.rollback()
        raise


def list_cash_concepts(session: Session, actor_user_id: str | None = None) -> list[dict[str, Any]]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "cash.concept.manage")
    concept_ids = session.execute(
        sa.select(models.cash_movement_concepts.c.id)
        .where(models.cash_movement_concepts.c.organization_id == ORGANIZATION_ID)
        .order_by(models.cash_movement_concepts.c.code)
    ).scalars()
    return [_cash_concept_detail(session, str(concept_id)) for concept_id in concept_ids]


def list_effective_cash_concepts(
    session: Session,
    movement_type: str,
    effective_at: datetime,
    actor_user_id: str | None = None,
    branch_id: str | None = None,
) -> list[dict[str, Any]]:
    actor_id = _actor_user_id(actor_user_id)
    authorize_branch_scope(session, actor_id, "cash.concept.read", branch_id)
    normalized_type = movement_type.strip().lower()
    if normalized_type not in {"deposit", "withdrawal"}:
        raise BusinessError(
            "cash_concept_invalid", "Effective cash concept type must be deposit or withdrawal"
        )
    if effective_at.tzinfo is None:
        raise BusinessError("cash_concept_invalid", "Effective date must include timezone")
    effective_utc = effective_at.astimezone(UTC)
    rows = session.execute(
        sa.select(
            models.cash_movement_concepts.c.id.label("concept_id"),
            models.cash_movement_concepts.c.code,
            models.cash_movement_concept_versions,
        )
        .select_from(
            models.cash_movement_concepts.join(
                models.cash_movement_concept_versions,
                models.cash_movement_concepts.c.id
                == models.cash_movement_concept_versions.c.concept_id,
            )
        )
        .where(
            models.cash_movement_concepts.c.organization_id == ORGANIZATION_ID,
            models.cash_movement_concepts.c.status == "active",
            models.cash_movement_concept_versions.c.valid_from <= effective_utc,
            models.cash_movement_concept_versions.c.allowed_movement_type.in_(
                [normalized_type, "both"]
            ),
        )
        .order_by(
            models.cash_movement_concepts.c.code,
            models.cash_movement_concept_versions.c.version.desc(),
        )
    ).mappings()
    effective: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        concept_id = str(row["concept_id"])
        if concept_id in seen:
            continue
        seen.add(concept_id)
        effective.append(
            cast(
                dict[str, Any],
                _sanitize_for_json(
                    {
                        "concept_id": concept_id,
                        "version_id": row["id"],
                        "code": row["code"],
                        "version": row["version"],
                        "name": row["name"],
                        "allowed_movement_type": row["allowed_movement_type"],
                        "requires_reference": row["requires_reference"],
                        "requires_evidence": row["requires_evidence"],
                        "valid_from": row["valid_from"],
                    }
                ),
            )
        )
    _log_cash_concept("effective_read", "success", actor_id, None)
    return effective


def _cash_movement_command_key(idempotency_key: str) -> str:
    key = idempotency_key.strip()
    if not key:
        raise BusinessError("idempotency_key_required", "Idempotency-Key is required")
    if len(key) > 180:
        raise BusinessError("cash_movement_invalid", "Idempotency-Key is too long")
    return key


def _cash_movement_request_hash(
    command_type: str, actor_user_id: str, payload: dict[str, Any]
) -> str:
    canonical = json.dumps(
        {"command_type": command_type, "actor_user_id": actor_user_id, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_cash_amount(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BusinessError("cash_movement_invalid", "amount_cents must be a positive integer")
    return value


def _validate_cash_evidence(value: object) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 10:
        raise BusinessError("cash_evidence_required", "One to ten evidence references are required")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise BusinessError("cash_evidence_required", "Evidence references must be strings")
        normalized = item.strip()
        if not normalized or len(normalized) > 600:
            raise BusinessError(
                "cash_evidence_required", "Evidence references must be 1..600 characters"
            )
        result.append(normalized)
    return result


def _cash_movement_replay(session: Session, key: str, request_hash: str) -> dict[str, Any] | None:
    command = (
        session.execute(
            sa.select(models.cash_movement_commands).where(
                models.cash_movement_commands.c.organization_id == ORGANIZATION_ID,
                models.cash_movement_commands.c.idempotency_key == key,
            )
        )
        .mappings()
        .first()
    )
    if not command:
        return None
    if command["request_hash"] != request_hash:
        raise BusinessError(
            "idempotency_conflict", "Idempotency-Key belongs to a different request"
        )
    stored = cast(dict[str, Any], command["result"])
    movement = cast(dict[str, Any], stored["movement"])
    return {
        "movement": movement,
        "summary_at_commit": cast(dict[str, int], stored["summary_at_commit"]),
        "current_summary": calculate_expected_cash(session, str(movement["cash_shift_id"])),
    }


def _serialize_cash_movement(
    row: dict[str, Any],
    *,
    compensation_state: str | None = None,
    compensated_by_movement_id: str | None = None,
) -> dict[str, Any]:
    result = dict(row)
    result.pop("idempotency_key", None)
    result.pop("evidence_refs", None)
    result.pop("_cash_shift_status", None)
    source_type = result.get("source_type")
    legacy_sources = {
        "purchase": "PURCHASE",
        "purchase_cancellation": "PURCHASE_CANCELLATION",
        "compensation": "COMPENSATION",
    }
    if isinstance(source_type, str):
        result["source_type"] = legacy_sources.get(source_type.lower(), source_type)
    if compensation_state is not None:
        result["compensation_state"] = compensation_state
        result["compensated_by_movement_id"] = compensated_by_movement_id
    return cast(dict[str, Any], _sanitize_for_json(result))


def calculate_expected_cash(session: Session, cash_shift_id: str) -> dict[str, int]:
    shift = (
        session.execute(
            sa.select(models.cash_shifts).where(models.cash_shifts.c.id == cash_shift_id)
        )
        .mappings()
        .first()
    )
    if not shift:
        raise BusinessError("cash_shift_not_open", "Cash shift was not found")
    cash_payment_cents = 0
    for payment in session.execute(
        sa.select(models.payments).where(models.payments.c.cash_shift_id == cash_shift_id)
    ).mappings():
        if payment["status"] != "CONFIRMED":
            continue
        if str(payment["method"]).lower() == "cash":
            cash_payment_cents += int(payment["amount_cents"])
    deposits = 0
    withdrawals = 0
    excluded_movement_count = 0
    for movement in session.execute(
        sa.select(models.cash_movements).where(
            models.cash_movements.c.cash_shift_id == cash_shift_id
        )
    ).mappings():
        if movement["status"] != "confirmed":
            excluded_movement_count += 1
            continue
        movement_type = str(movement["movement_type"]).lower()
        if movement_type in {"deposit", "cash_reversal"}:
            deposits += int(movement["amount_cents"])
        elif movement_type == "withdrawal":
            withdrawals += int(movement["amount_cents"])
        else:
            raise BusinessError(
                "cash_ledger_unknown_type", "Confirmed cash movement type is unknown"
            )
    opening = int(shift["opening_cash_cents"])
    return {
        "opening_cash_cents": opening,
        "cash_payment_cents": cash_payment_cents,
        "deposit_cents": deposits,
        "withdrawal_cents": withdrawals,
        "excluded_movement_count": excluded_movement_count,
        "expected_cash_cents": opening + cash_payment_cents + deposits - withdrawals,
    }


def _effective_cash_concept_snapshot(
    session: Session, concept_id: str, movement_type: str, actor_id: str, branch_id: str
) -> dict[str, Any]:
    effective = list_effective_cash_concepts(session, movement_type, _now(), actor_id, branch_id)
    snapshot = next((item for item in effective if item["concept_id"] == concept_id), None)
    if not snapshot:
        raise BusinessError(
            "cash_concept_invalid", "Cash concept is not effective for this movement"
        )
    return snapshot


def create_cash_movement(
    session: Session,
    payload: dict[str, Any],
    idempotency_key: str,
    actor_user_id: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    _begin_cash_shift_serialization(session)
    actor_id = _actor_user_id(actor_user_id)
    key = _cash_movement_command_key(idempotency_key)
    request_hash = _cash_movement_request_hash("create", actor_id, payload)
    replay = _cash_movement_replay(session, key, request_hash)
    if replay is not None:
        return replay
    expected_fields = {
        "branch_id",
        "register_id",
        "movement_type",
        "concept_id",
        "amount_cents",
        "reference",
        "evidence_refs",
    }
    if set(payload) != expected_fields:
        raise BusinessError("cash_movement_invalid", "Cash movement fields are invalid")
    branch_id = str(payload["branch_id"]).strip()
    register_id = str(payload["register_id"]).strip()
    movement_type = str(payload["movement_type"]).strip().lower()
    concept_id = str(payload["concept_id"]).strip()
    if (
        not branch_id
        or not register_id
        or movement_type not in {"deposit", "withdrawal"}
        or not concept_id
    ):
        raise BusinessError(
            "cash_movement_invalid", "Cash movement branch, register, type and concept are required"
        )
    permission = "cash.movement.deposit" if movement_type == "deposit" else "cash.movement.withdraw"
    authorize_branch_scope(session, actor_id, permission, branch_id)
    amount_cents = _validate_cash_amount(payload["amount_cents"])
    reference = str(payload["reference"]).strip()
    if not reference or len(reference) > 600:
        raise BusinessError("cash_reference_required", "Cash movement reference is required")
    evidence_refs = _validate_cash_evidence(payload["evidence_refs"])
    shift = _guard_open_cash_shift(session, register_id, branch_id)
    snapshot = _effective_cash_concept_snapshot(
        session, concept_id, movement_type, actor_id, branch_id
    )
    now = _now()
    movement = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "branch_id": branch_id,
        "cash_shift_id": shift["id"],
        "movement_type": movement_type,
        "amount_cents": amount_cents,
        "reason_code": "MANUAL_DEPOSIT" if movement_type == "deposit" else "MANUAL_WITHDRAWAL",
        "reason": str(snapshot["name"]),
        "source_type": "manual",
        "source_id": None,
        "actor_user_id": actor_id,
        "idempotency_key": hashlib.sha256(
            (f"cash-movement:{ORGANIZATION_ID}:{key}").encode()
        ).hexdigest(),
        "status": "confirmed",
        "reversal_of_id": None,
        "concept_id": concept_id,
        "concept_version_id": snapshot["version_id"],
        "concept_snapshot": snapshot,
        "reference": reference,
        "evidence_refs": evidence_refs,
        "compensates_movement_id": None,
        "created_at": now,
    }
    try:
        session.execute(models.cash_movements.insert().values(**movement))
        summary_at_commit = calculate_expected_cash(session, str(shift["id"]))
        result = {
            "movement": _serialize_cash_movement(movement),
            "summary_at_commit": summary_at_commit,
        }
        session.execute(
            models.cash_movement_commands.insert().values(
                id=_id(),
                organization_id=ORGANIZATION_ID,
                actor_user_id=actor_id,
                target_movement_id=movement["id"],
                command_type="create",
                idempotency_key=key,
                request_hash=request_hash,
                result=result,
                status="completed",
                created_at=now,
            )
        )
        _audit(
            session,
            "cash_movement.created",
            "cash_movement",
            movement["id"],
            {
                "movement_type": movement_type,
                "amount_cents": amount_cents,
                "result": "confirmed",
            },
            branch_id,
            actor_user_id=actor_id,
        )
        if commit:
            session.commit()
        return {**result, "current_summary": summary_at_commit}
    except IntegrityError as exc:
        if not commit:
            raise BusinessError(
                "idempotency_conflict", "Cash movement changed concurrently"
            ) from exc
        session.rollback()
        replay = _cash_movement_replay(session, key, request_hash)
        if replay is not None:
            return replay
        raise BusinessError("idempotency_conflict", "Cash movement changed concurrently") from exc
    except Exception:
        if commit:
            session.rollback()
        raise


def compensate_cash_movement(
    session: Session,
    movement_id: str,
    payload: dict[str, Any],
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    _begin_cash_shift_serialization(session)
    actor_id = _actor_user_id(actor_user_id)
    key = _cash_movement_command_key(idempotency_key)
    request_hash = _cash_movement_request_hash(
        "compensate", actor_id, {"movement_id": movement_id, **payload}
    )
    replay = _cash_movement_replay(session, key, request_hash)
    if replay is not None:
        return replay
    if set(payload) != {"reason", "evidence_refs"}:
        raise BusinessError("cash_compensation_invalid", "Compensation fields are invalid")
    original = (
        session.execute(
            sa.select(models.cash_movements).where(
                models.cash_movements.c.id == movement_id,
                models.cash_movements.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not original:
        raise BusinessError("cash_movement_not_found", "Cash movement was not found")
    authorize_branch_scope(session, actor_id, "cash.movement.compensate", original["branch_id"])
    _require_cash_compensation_owner(session, actor_id, str(original["branch_id"]))
    if (
        original["status"] != "confirmed"
        or original["movement_type"] not in {"deposit", "withdrawal"}
        or original["reversal_of_id"] is not None
        or original["compensates_movement_id"] is not None
    ):
        raise BusinessError("cash_compensation_invalid", "Cash movement cannot be compensated")
    if session.execute(
        sa.select(models.cash_movements.c.id).where(
            sa.or_(
                models.cash_movements.c.reversal_of_id == movement_id,
                models.cash_movements.c.compensates_movement_id == movement_id,
            )
        )
    ).scalar_one_or_none():
        raise BusinessError(
            "cash_movement_already_compensated", "Cash movement was already compensated"
        )
    reason = str(payload["reason"]).strip()
    if not reason or len(reason) > 600:
        raise BusinessError("cash_compensation_invalid", "Compensation reason is required")
    evidence_refs = _validate_cash_evidence(payload["evidence_refs"])
    register_code = session.execute(
        sa.select(models.cash_shifts.c.register_code).where(
            models.cash_shifts.c.id == original["cash_shift_id"]
        )
    ).scalar_one()
    shift = _guard_open_cash_shift(session, register_code, original["branch_id"])
    if shift["id"] != original["cash_shift_id"]:
        raise BusinessError("cash_shift_not_open", "Original cash shift is not OPEN")
    movement_type = "deposit" if original["movement_type"] == "withdrawal" else "withdrawal"
    now = _now()
    movement = {
        "id": _id(),
        "organization_id": original["organization_id"],
        "branch_id": original["branch_id"],
        "cash_shift_id": original["cash_shift_id"],
        "movement_type": movement_type,
        "amount_cents": int(original["amount_cents"]),
        "reason_code": "MANUAL_DEPOSIT" if movement_type == "deposit" else "MANUAL_WITHDRAWAL",
        "reason": reason,
        "source_type": "COMPENSATION",
        "source_id": None,
        "actor_user_id": actor_id,
        "idempotency_key": hashlib.sha256(
            (f"cash-compensation:{ORGANIZATION_ID}:{key}").encode()
        ).hexdigest(),
        "status": "confirmed",
        "reversal_of_id": movement_id,
        "concept_id": original["concept_id"],
        "concept_version_id": original["concept_version_id"],
        "concept_snapshot": original["concept_snapshot"],
        "reference": None,
        "evidence_refs": evidence_refs,
        "compensates_movement_id": movement_id,
        "created_at": now,
    }
    try:
        session.execute(models.cash_movements.insert().values(**movement))
        summary_at_commit = calculate_expected_cash(session, str(original["cash_shift_id"]))
        result = {
            "movement": _serialize_cash_movement(movement),
            "summary_at_commit": summary_at_commit,
        }
        session.execute(
            models.cash_movement_commands.insert().values(
                id=_id(),
                organization_id=ORGANIZATION_ID,
                actor_user_id=actor_id,
                target_movement_id=movement_id,
                command_type="compensate",
                idempotency_key=key,
                request_hash=request_hash,
                result=result,
                status="completed",
                created_at=now,
            )
        )
        _audit(
            session,
            "cash_movement.compensated",
            "cash_movement",
            movement["id"],
            {
                "original_id": movement_id,
                "amount_cents": movement["amount_cents"],
                "result": "confirmed",
            },
            original["branch_id"],
            actor_user_id=actor_id,
        )
        session.commit()
        return {**result, "current_summary": summary_at_commit}
    except IntegrityError as exc:
        session.rollback()
        replay = _cash_movement_replay(session, key, request_hash)
        if replay is not None:
            return replay
        raise BusinessError(
            "cash_movement_already_compensated", "Cash movement was already compensated"
        ) from exc
    except Exception:
        session.rollback()
        raise


def list_cash_movement_ledger(
    session: Session,
    actor_user_id: str,
    branch_id: str,
    register_id: str | None,
    cash_shift_id: str | None,
    movement_type: str | None,
    from_utc: datetime | None,
    to_utc: datetime | None,
    limit: int,
    cursor: str | None,
) -> dict[str, Any]:
    authorized_branch = authorize_branch_scope(
        session, actor_user_id, "cash.movement.read", branch_id
    )
    if not 1 <= limit <= 100:
        raise BusinessError("cash_movement_invalid", "limit must be 1..100")
    query = (
        sa.select(
            models.cash_movements,
            models.cash_shifts.c.status.label("_cash_shift_status"),
        )
        .select_from(
            models.cash_movements.join(
                models.cash_shifts,
                models.cash_movements.c.cash_shift_id == models.cash_shifts.c.id,
            )
        )
        .where(models.cash_movements.c.branch_id == authorized_branch)
    )
    if cash_shift_id:
        query = query.where(models.cash_movements.c.cash_shift_id == cash_shift_id)
    if movement_type:
        if movement_type not in {"deposit", "withdrawal"}:
            raise BusinessError("cash_movement_invalid", "movement_type is invalid")
        query = query.where(models.cash_movements.c.movement_type == movement_type)
    if from_utc:
        if from_utc.tzinfo is None:
            raise BusinessError("cash_movement_invalid", "from_utc must include timezone")
        query = query.where(models.cash_movements.c.created_at >= from_utc.astimezone(UTC))
    if to_utc:
        if to_utc.tzinfo is None:
            raise BusinessError("cash_movement_invalid", "to_utc must include timezone")
        query = query.where(models.cash_movements.c.created_at <= to_utc.astimezone(UTC))
    if from_utc and to_utc and from_utc.astimezone(UTC) > to_utc.astimezone(UTC):
        raise BusinessError("cash_movement_invalid", "from_utc must not be after to_utc")
    if register_id:
        query = query.where(models.cash_shifts.c.register_code == register_id)
    if cursor:
        try:
            cursor_time_raw, cursor_id = cursor.rsplit("|", 1)

            cursor_time = datetime.fromisoformat(cursor_time_raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BusinessError("cash_movement_invalid", "cursor is invalid") from exc
        query = query.where(
            sa.or_(
                models.cash_movements.c.created_at < cursor_time,
                sa.and_(
                    models.cash_movements.c.created_at == cursor_time,
                    models.cash_movements.c.id < cursor_id,
                ),
            )
        )
    rows = [
        dict(row)
        for row in session.execute(
            query.order_by(
                models.cash_movements.c.created_at.desc(), models.cash_movements.c.id.desc()
            ).limit(limit + 1)
        ).mappings()
    ]
    next_cursor = None
    if len(rows) > limit:
        next_row = rows[limit - 1]
        next_cursor = _sanitize_for_json(next_row["created_at"]) + "|" + str(next_row["id"])
    page_rows = rows[:limit]
    page_ids = {str(row["id"]) for row in page_rows}
    incoming_compensations: dict[str, str] = {}
    if page_ids:
        linked_rows = session.execute(
            sa.select(
                models.cash_movements.c.id,
                models.cash_movements.c.reversal_of_id,
                models.cash_movements.c.compensates_movement_id,
            )
            .where(
                models.cash_movements.c.organization_id == ORGANIZATION_ID,
                sa.or_(
                    models.cash_movements.c.reversal_of_id.in_(page_ids),
                    models.cash_movements.c.compensates_movement_id.in_(page_ids),
                ),
            )
            .order_by(models.cash_movements.c.created_at.desc(), models.cash_movements.c.id.desc())
        ).mappings()
        for linked in linked_rows:
            for original_id in {linked["reversal_of_id"], linked["compensates_movement_id"]}:
                if original_id in page_ids and original_id != linked["id"]:
                    incoming_compensations.setdefault(str(original_id), str(linked["id"]))

    def compensation_projection(row: dict[str, Any]) -> tuple[str, str | None]:
        if row["reversal_of_id"] is not None or row["compensates_movement_id"] is not None:
            return "compensation", None
        compensated_by = incoming_compensations.get(str(row["id"]))
        if compensated_by:
            return "compensated", compensated_by
        if (
            str(row["status"]).lower() == "confirmed"
            and str(row["movement_type"]).lower() in {"deposit", "withdrawal"}
            and str(row["_cash_shift_status"]).upper() == "OPEN"
        ):
            return "eligible", None
        return "ineligible", None

    items = []
    for row in page_rows:
        compensation_state, compensated_by_movement_id = compensation_projection(row)
        items.append(
            _serialize_cash_movement(
                row,
                compensation_state=compensation_state,
                compensated_by_movement_id=compensated_by_movement_id,
            )
        )
    return {"items": items, "next_cursor": next_cursor}


def list_cash_movements(session: Session, branch_id: str | None) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(models.cash_movements)
        .where(models.cash_movements.c.branch_id == branch_id)
        .order_by(models.cash_movements.c.created_at.desc())
    ).mappings()
    return [_serialize_cash_movement(dict(row)) for row in rows]


class UserCashCutService:
    """PCO-006 aggregate.  Financial values and associations are computed only here."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _key(value: str) -> str:
        key = value.strip()
        if not key or len(key) > 180:
            raise BusinessError("idempotency_key_required", "Idempotency-Key is required")
        return key

    @staticmethod
    def _time(value: object) -> datetime:
        if not isinstance(value, str):
            raise BusinessError("cash_cut_period_invalid", "UTC period is required")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BusinessError("cash_cut_period_invalid", "UTC period is invalid") from exc
        if parsed.tzinfo is None:
            raise BusinessError("cash_cut_period_invalid", "UTC period is required")
        return parsed.astimezone(UTC)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def _hash(self, command: str, actor: str, target: str | None, payload: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(
                {"command": command, "actor": actor, "target": target, "payload": payload},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def _replay(self, key: str, digest: str) -> dict[str, Any] | None:
        command = (
            self.session.execute(
                sa.select(models.user_cash_cut_commands)
                .where(
                    models.user_cash_cut_commands.c.organization_id == ORGANIZATION_ID,
                    models.user_cash_cut_commands.c.idempotency_key == key,
                )
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if not command:
            return None
        if command["request_hash"] != digest:
            raise BusinessError(
                "idempotency_conflict", "Idempotency-Key belongs to a different request"
            )
        self._pco006_replayed = True
        return cast(dict[str, Any], command["result"])

    def _store(
        self,
        command: str,
        key: str,
        digest: str,
        actor: str,
        cut_id: str | None,
        result: dict[str, Any],
        now: datetime,
    ) -> None:
        try:
            self.session.execute(
                models.user_cash_cut_commands.insert().values(
                    id=_id(),
                    organization_id=ORGANIZATION_ID,
                    actor_user_id=actor,
                    cash_cut_id=cut_id,
                    command_type=command,
                    idempotency_key=key,
                    request_hash=digest,
                    result=_sanitize_for_json(result),
                    created_at=now,
                )
            )
        except IntegrityError as exc:
            self.session.rollback()
            persisted = (
                self.session.execute(
                    sa.select(models.user_cash_cut_commands).where(
                        models.user_cash_cut_commands.c.organization_id == ORGANIZATION_ID,
                        models.user_cash_cut_commands.c.idempotency_key == key,
                    )
                )
                .mappings()
                .first()
            )
            if not persisted:
                raise exc
            if persisted["request_hash"] != digest:
                raise BusinessError(
                    "idempotency_conflict", "Idempotency-Key belongs to a different request"
                ) from exc
            raise _UserCashCutCommandReplay(cast(dict[str, Any], persisted["result"])) from exc

    def _cut(self, cut_id: str, *, lock: bool = True) -> dict[str, Any]:
        query = sa.select(models.user_cash_cuts).where(
            models.user_cash_cuts.c.id == cut_id,
            models.user_cash_cuts.c.organization_id == ORGANIZATION_ID,
        )
        if lock:
            query = query.with_for_update()
        row = self.session.execute(query).mappings().first()
        if not row:
            raise BusinessError("cash_cut_scope_invalid", "Cash cut was not found")
        return dict(row)

    @staticmethod
    def _public(cut: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], _sanitize_for_json(dict(cut)))

    @_observe_pco006_command("create")
    def create(
        self, payload: dict[str, Any], idempotency_key: str, actor_user_id: str
    ) -> dict[str, Any]:
        required = {
            "branch_id",
            "register_id",
            "cash_shift_id",
            "cashier_user_id",
            "period_start",
            "period_end",
        }
        if set(payload) != required or any(
            not isinstance(payload[field], str) or not payload[field].strip() for field in required
        ):
            raise BusinessError("cash_cut_scope_invalid", "Cash cut scope is invalid")
        shift_row = (
            self.session.execute(
                sa.select(models.cash_shifts)
                .where(
                    models.cash_shifts.c.id == payload["cash_shift_id"],
                    models.cash_shifts.c.organization_id == ORGANIZATION_ID,
                )
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if not shift_row:
            raise BusinessError("cash_cut_scope_invalid", "Cash shift is invalid")
        shift = dict(shift_row)
        actor = _actor_user_id(actor_user_id)
        authorize_branch_scope(self.session, actor, "cash.user_cut.create", str(shift["branch_id"]))
        key = self._key(idempotency_key)
        digest = self._hash("create", actor, None, payload)
        replay = self._replay(key, digest)
        if replay is not None:
            return replay
        if not shift.get("cashier_user_id"):
            raise BusinessError("cash_cut_cashier_unknown", "Cash shift cashier is unknown")
        closure = (
            self.session.execute(
                sa.select(models.cash_shift_closures).where(
                    models.cash_shift_closures.c.cash_shift_id == shift["id"]
                )
            )
            .mappings()
            .first()
        )
        start, end = self._time(payload["period_start"]), self._time(payload["period_end"])
        if (
            str(shift["status"]).upper() != "OPERATIVELY_CLOSED"
            or not closure
            or str(payload["branch_id"]) != str(shift["branch_id"])
            or str(payload["register_id"]) != str(shift["register_code"])
            or str(payload["cashier_user_id"]) != str(shift["cashier_user_id"])
            or start != self._utc(shift["opened_at"])
            or end != self._utc(closure["closed_at"])
        ):
            raise BusinessError("cash_cut_period_invalid", "Cash cut scope does not match shift")
        branch = (
            self.session.execute(
                sa.select(models.branches).where(models.branches.c.id == shift["branch_id"])
            )
            .mappings()
            .one()
        )
        try:
            ZoneInfo(str(branch["timezone"]))
        except ZoneInfoNotFoundError as exc:
            raise BusinessError(
                "cash_cut_scope_invalid", "Cash cut branch timezone is invalid"
            ) from exc
        now = _now()
        cut = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "branch_id": shift["branch_id"],
            "cash_shift_id": shift["id"],
            "register_code_snapshot": shift["register_code"],
            "cashier_user_id": shift["cashier_user_id"],
            "timezone": branch["timezone"],
            "period_start": start,
            "period_end": end,
            "status": "DRAFT",
            "opening_cash_cents": shift["opening_cash_cents"],
            "cash_payment_cents": None,
            "deposit_cents": None,
            "withdrawal_cents": None,
            "expected_cash_cents": None,
            "counted_cash_cents": None,
            "difference_cents": None,
            "tolerance_cents": 0,
            "created_by_user_id": actor,
            "finalized_by_user_id": None,
            "version": 1,
            "created_at": now,
            "counted_at": None,
            "finalized_at": None,
        }
        try:
            self.session.execute(models.user_cash_cuts.insert().values(**cut))
            result = {"cash_cut": self._public(cut)}
            self._store("create", key, digest, actor, cut["id"], result, now)
            _audit(
                self.session,
                "cash_user_cut.created",
                "user_cash_cut",
                cut["id"],
                {"result": "created"},
                str(cut["branch_id"]),
                actor_user_id=actor,
            )
            self.session.commit()
            return result
        except IntegrityError as exc:
            self.session.rollback()
            raise BusinessError(
                "cash_cut_already_exists", "A cash cut already exists for this cash shift"
            ) from exc
        except Exception:
            self.session.rollback()
            raise

    def _require_owner(self, actor_user_id: str, branch_id: str, permission: str) -> None:
        """PCO-006 permits the same Owner to request and decide; no four-eyes rule exists."""
        authorize_branch_scope(self.session, actor_user_id, permission, branch_id)
        owner = self.session.execute(
            sa.select(models.roles.c.id)
            .select_from(
                models.user_roles.join(
                    models.roles, models.user_roles.c.role_id == models.roles.c.id
                ).join(
                    models.role_authority_grants,
                    models.role_authority_grants.c.role_id == models.roles.c.id,
                )
            )
            .where(
                models.user_roles.c.user_id == actor_user_id,
                models.roles.c.organization_id == ORGANIZATION_ID,
                models.role_authority_grants.c.authority_kind == "organization_all_permissions",
                sa.or_(
                    models.roles.c.scope == "organization",
                    models.user_roles.c.branch_id == branch_id,
                ),
            )
            .limit(1)
        ).scalar_one_or_none()
        if not owner:
            raise AuthorizationError(
                "permission_denied", "Only an Owner may reopen a user cash cut"
            )

    @_observe_pco006_command("reopen_request")
    def request_reopen(
        self, cut_id: str, payload: dict[str, Any], idempotency_key: str, actor_user_id: str
    ) -> dict[str, Any]:
        if (
            set(payload) != {"counted_cash_cents", "reason", "evidence_refs"}
            or isinstance(payload["counted_cash_cents"], bool)
            or not isinstance(payload["counted_cash_cents"], int)
            or payload["counted_cash_cents"] < 0
            or not isinstance(payload["reason"], str)
            or not 1 <= len(payload["reason"].strip()) <= 600
            or not isinstance(payload["evidence_refs"], list)
            or not 1 <= len(payload["evidence_refs"]) <= 10
            or any(
                not isinstance(reference, str) or not 1 <= len(reference.strip()) <= 600
                for reference in payload["evidence_refs"]
            )
        ):
            raise BusinessError("cash_cut_scope_invalid", "Reopen payload is invalid")
        cut, actor = self._cut(cut_id), _actor_user_id(actor_user_id)
        self._require_owner(actor, str(cut["branch_id"]), "cash.user_cut.reopen.request")
        key = self._key(idempotency_key)
        digest = self._hash("reopen_request", actor, cut_id, payload)
        replay = self._replay(key, digest)
        if replay is not None:
            return replay
        if cut["status"] != "FINALIZED":
            raise BusinessError(
                "cash_cut_reopen_transition_invalid", "Only finalized cuts may reopen"
            )
        existing = self.session.execute(
            sa.select(models.user_cash_cut_reopen_requests.c.id).where(
                models.user_cash_cut_reopen_requests.c.cash_cut_id == cut_id,
                models.user_cash_cut_reopen_requests.c.status.in_(("REQUESTED", "APPROVED")),
            )
        ).scalar_one_or_none()
        if existing:
            raise BusinessError(
                "cash_cut_reopen_active", "Cash cut already has an active reopen request"
            )
        now = _now()
        request = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "cash_cut_id": cut_id,
            "proposed_counted_cash_cents": payload["counted_cash_cents"],
            "reason": payload["reason"].strip(),
            "evidence_refs": [reference.strip() for reference in payload["evidence_refs"]],
            "status": "REQUESTED",
            "requested_by_user_id": actor,
            "decided_by_user_id": None,
            "created_at": now,
            "decided_at": None,
        }
        try:
            self.session.execute(models.user_cash_cut_reopen_requests.insert().values(**request))
            result = {
                "reopen_request": {
                    "id": request["id"],
                    "cash_cut_id": cut_id,
                    "status": "REQUESTED",
                }
            }
            self._store("reopen_request", key, digest, actor, cut_id, result, now)
            _audit(
                self.session,
                "cash_user_cut.reopen_requested",
                "user_cash_cut",
                cut_id,
                {"result": "requested"},
                str(cut["branch_id"]),
                actor_user_id=actor,
            )
            self.session.commit()
            return result
        except IntegrityError as exc:
            self.session.rollback()
            raise BusinessError(
                "cash_cut_reopen_active", "Cash cut already has an active reopen request"
            ) from exc
        except Exception:
            self.session.rollback()
            raise

    @_observe_pco006_command(
        lambda _self, _request_id, decision, *_args: f"reopen_{decision.lower()}"
    )
    def decide_reopen(
        self, request_id: str, decision: str, idempotency_key: str, actor_user_id: str
    ) -> dict[str, Any]:
        normalized = decision.strip().upper()
        if normalized not in {"APPROVED", "REJECTED"}:
            raise BusinessError("cash_cut_reopen_transition_invalid", "Reopen decision is invalid")
        request_row = (
            self.session.execute(
                sa.select(models.user_cash_cut_reopen_requests)
                .where(
                    models.user_cash_cut_reopen_requests.c.id == request_id,
                    models.user_cash_cut_reopen_requests.c.organization_id == ORGANIZATION_ID,
                )
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if not request_row:
            raise BusinessError("cash_cut_scope_invalid", "Reopen request was not found")
        request, cut, actor = (
            dict(request_row),
            self._cut(str(request_row["cash_cut_id"])),
            _actor_user_id(actor_user_id),
        )
        self._require_owner(actor, str(cut["branch_id"]), "cash.user_cut.reopen.authorize")
        key = self._key(idempotency_key)
        digest = self._hash("reopen_" + normalized.lower(), actor, request_id, {})
        replay = self._replay(key, digest)
        if replay is not None:
            return replay
        if request["status"] != "REQUESTED":
            raise BusinessError("cash_cut_reopen_transition_invalid", "Reopen request is terminal")
        now = _now()
        try:
            self.session.execute(
                models.user_cash_cut_reopen_requests.update()
                .where(models.user_cash_cut_reopen_requests.c.id == request_id)
                .values(status=normalized, decided_by_user_id=actor, decided_at=now)
            )
            result = {
                "reopen_request": {"id": request_id, "cash_cut_id": cut["id"], "status": normalized}
            }
            self._store("reopen_" + normalized.lower(), key, digest, actor, cut["id"], result, now)
            _audit(
                self.session,
                "cash_user_cut.reopen_decided",
                "user_cash_cut",
                cut["id"],
                {"result": normalized.lower()},
                str(cut["branch_id"]),
                actor_user_id=actor,
            )
            self.session.commit()
            return result
        except Exception:
            self.session.rollback()
            raise

    @_observe_pco006_command("reopen_compensate")
    def compensate_reopen(
        self, request_id: str, idempotency_key: str, actor_user_id: str
    ) -> dict[str, Any]:
        request_row = (
            self.session.execute(
                sa.select(models.user_cash_cut_reopen_requests)
                .where(
                    models.user_cash_cut_reopen_requests.c.id == request_id,
                    models.user_cash_cut_reopen_requests.c.organization_id == ORGANIZATION_ID,
                )
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if not request_row:
            raise BusinessError("cash_cut_scope_invalid", "Reopen request was not found")
        request, cut, actor = (
            dict(request_row),
            self._cut(str(request_row["cash_cut_id"])),
            _actor_user_id(actor_user_id),
        )
        self._require_owner(actor, str(cut["branch_id"]), "cash.user_cut.reopen.authorize")
        key = self._key(idempotency_key)
        digest = self._hash("reopen_compensate", actor, request_id, {})
        replay = self._replay(key, digest)
        if replay is not None:
            return replay
        if request["status"] != "APPROVED":
            raise BusinessError(
                "cash_cut_reopen_transition_invalid", "Reopen request is not approved"
            )
        corrected = int(request["proposed_counted_cash_cents"])
        expected = int(cut["expected_cash_cents"])
        corrected_difference = corrected - expected
        now = _now()
        compensation = {
            "id": _id(),
            "organization_id": ORGANIZATION_ID,
            "cash_cut_id": cut["id"],
            "reopen_request_id": request_id,
            "corrected_counted_cash_cents": corrected,
            "expected_cash_cents": expected,
            "tolerance_cents": int(cut["tolerance_cents"]),
            "corrected_difference_cents": corrected_difference,
            "difference_delta_cents": corrected_difference - int(cut["difference_cents"]),
            "created_by_user_id": actor,
            "created_at": now,
        }
        try:
            self.session.execute(models.user_cash_cut_compensations.insert().values(**compensation))
            self.session.execute(
                models.user_cash_cut_reopen_requests.update()
                .where(models.user_cash_cut_reopen_requests.c.id == request_id)
                .values(status="COMPENSATED", decided_by_user_id=actor, decided_at=now)
            )
            result = {"compensation": cast(dict[str, Any], _sanitize_for_json(compensation))}
            self._store("reopen_compensate", key, digest, actor, cut["id"], result, now)
            _audit(
                self.session,
                "cash_user_cut.compensated",
                "user_cash_cut",
                cut["id"],
                {"result": "compensated"},
                str(cut["branch_id"]),
                actor_user_id=actor,
            )
            self.session.commit()
            return result
        except Exception:
            self.session.rollback()
            raise

    def list(self, filters: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
        allowed = {
            "branch_id",
            "register_id",
            "cashier_user_id",
            "cash_shift_id",
            "status",
            "from_utc",
            "to_utc",
            "limit",
            "cursor",
        }
        if set(filters) - allowed:
            raise BusinessError("cash_cut_scope_invalid", "Cash cut filters are invalid")
        branch_id = str(filters.get("branch_id") or "").strip()
        if not branch_id:
            raise BusinessError("cash_cut_scope_invalid", "branch_id is required")
        actor = _actor_user_id(actor_user_id)
        authorize_branch_scope(self.session, actor, "cash.user_cut.read", branch_id)
        limit = filters.get("limit", 50)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise BusinessError("cash_cut_scope_invalid", "limit must be 1..100")
        cursor_filters = {
            key: value for key, value in filters.items() if key not in {"cursor", "limit"}
        }
        filter_hash = hashlib.sha256(
            json.dumps(cursor_filters, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        query = sa.select(models.user_cash_cuts).where(
            models.user_cash_cuts.c.organization_id == ORGANIZATION_ID,
            models.user_cash_cuts.c.branch_id == branch_id,
        )
        for field, column in (
            ("register_id", models.user_cash_cuts.c.register_code_snapshot),
            ("cashier_user_id", models.user_cash_cuts.c.cashier_user_id),
            ("cash_shift_id", models.user_cash_cuts.c.cash_shift_id),
            ("status", models.user_cash_cuts.c.status),
        ):
            if filters.get(field):
                if field == "status" and filters[field] not in {"DRAFT", "COUNTED", "FINALIZED"}:
                    raise BusinessError("cash_cut_scope_invalid", "Cash cut status is invalid")
                query = query.where(column == filters[field])
        if filters.get("from_utc") is not None:
            query = query.where(
                models.user_cash_cuts.c.period_start >= self._time(filters["from_utc"])
            )
        if filters.get("to_utc") is not None:
            query = query.where(models.user_cash_cuts.c.period_end <= self._time(filters["to_utc"]))
        if filters.get("from_utc") is not None and filters.get("to_utc") is not None:
            if self._time(filters["from_utc"]) >= self._time(filters["to_utc"]):
                raise BusinessError("cash_cut_scope_invalid", "Cash cut range is invalid")
        if filters.get("cursor"):
            try:
                decoded = urlsafe_b64decode(str(filters["cursor"]).encode()).decode()
                cursor = json.loads(decoded)
                if cursor["hash"] != filter_hash:
                    raise ValueError("filter mismatch")
                cursor_time = self._time(cursor["period_start"])
                cursor_id = str(cursor["id"])
            except (BinasciiError, UnicodeDecodeError, KeyError, ValueError, TypeError) as exc:
                raise BusinessError("cash_cut_scope_invalid", "Cash cut cursor is invalid") from exc
            query = query.where(
                sa.or_(
                    models.user_cash_cuts.c.period_start < cursor_time,
                    sa.and_(
                        models.user_cash_cuts.c.period_start == cursor_time,
                        models.user_cash_cuts.c.id < cursor_id,
                    ),
                )
            )
        rows = [
            dict(row)
            for row in self.session.execute(
                query.order_by(
                    models.user_cash_cuts.c.period_start.desc(), models.user_cash_cuts.c.id.desc()
                ).limit(limit + 1)
            ).mappings()
        ]
        next_cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            next_cursor = urlsafe_b64encode(
                json.dumps(
                    {
                        "hash": filter_hash,
                        "period_start": _sanitize_for_json(last["period_start"]),
                        "id": str(last["id"]),
                    },
                    separators=(",", ":"),
                ).encode()
            ).decode()
        return {"items": [self._public(row) for row in rows[:limit]], "next_cursor": next_cursor}

    def detail(self, cut_id: str, actor_user_id: str) -> dict[str, Any]:
        cut = self._cut(cut_id, lock=False)
        actor = _actor_user_id(actor_user_id)
        authorize_branch_scope(self.session, actor, "cash.user_cut.read", str(cut["branch_id"]))
        operations = [
            cast(dict[str, Any], _sanitize_for_json(dict(row)))
            for row in self.session.execute(
                sa.select(models.user_cash_cut_operations)
                .where(models.user_cash_cut_operations.c.cash_cut_id == cut_id)
                .order_by(
                    models.user_cash_cut_operations.c.occurred_at,
                    models.user_cash_cut_operations.c.id,
                )
            ).mappings()
        ]
        reopen = (
            self.session.execute(
                sa.select(
                    models.user_cash_cut_reopen_requests.c.id,
                    models.user_cash_cut_reopen_requests.c.status,
                )
                .where(models.user_cash_cut_reopen_requests.c.cash_cut_id == cut_id)
                .order_by(models.user_cash_cut_reopen_requests.c.created_at.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        return {
            "cash_cut": self._public(cut),
            "operations": operations,
            "reopen": dict(reopen) if reopen else None,
        }

    @_observe_pco006_command("count")
    def counted_cash(
        self, cut_id: str, payload: dict[str, Any], idempotency_key: str, actor_user_id: str
    ) -> dict[str, Any]:
        if (
            set(payload) != {"counted_cash_cents", "version"}
            or isinstance(payload["counted_cash_cents"], bool)
            or not isinstance(payload["counted_cash_cents"], int)
            or payload["counted_cash_cents"] < 0
            or isinstance(payload["version"], bool)
            or not isinstance(payload["version"], int)
        ):
            raise BusinessError("cash_cut_scope_invalid", "Counted cash payload is invalid")
        cut, actor = self._cut(cut_id), _actor_user_id(actor_user_id)
        authorize_branch_scope(self.session, actor, "cash.user_cut.create", str(cut["branch_id"]))
        key, digest, now = (
            self._key(idempotency_key),
            self._hash("count", actor, cut_id, payload),
            _now(),
        )
        replay = self._replay(key, digest)
        if replay is not None:
            return replay
        if cut["status"] != "DRAFT":
            raise BusinessError("cash_cut_transition_invalid", "Cash cut cannot be counted")
        if payload["version"] != int(cut["version"]):
            raise BusinessError("cash_cut_version_conflict", "Cash cut version is stale")
        try:
            self.session.execute(
                models.user_cash_cuts.update()
                .where(models.user_cash_cuts.c.id == cut_id)
                .values(
                    status="COUNTED",
                    counted_cash_cents=payload["counted_cash_cents"],
                    counted_at=now,
                    version=int(cut["version"]) + 1,
                )
            )
            cut.update(
                status="COUNTED",
                counted_cash_cents=payload["counted_cash_cents"],
                counted_at=now,
                version=int(cut["version"]) + 1,
            )
            result = {"cash_cut": self._public(cut)}
            self._store("count", key, digest, actor, cut_id, result, now)
            _audit(
                self.session,
                "cash_user_cut.counted",
                "user_cash_cut",
                cut_id,
                {"result": "counted"},
                str(cut["branch_id"]),
                actor_user_id=actor,
            )
            self.session.commit()
            return result
        except Exception:
            self.session.rollback()
            raise

    @_observe_pco006_command("finalize")
    def finalize(
        self, cut_id: str, payload: dict[str, Any], idempotency_key: str, actor_user_id: str
    ) -> dict[str, Any]:
        if (
            set(payload) != {"version"}
            or isinstance(payload["version"], bool)
            or not isinstance(payload["version"], int)
        ):
            raise BusinessError("cash_cut_scope_invalid", "Finalize payload is invalid")
        cut, actor = self._cut(cut_id), _actor_user_id(actor_user_id)
        authorize_branch_scope(self.session, actor, "cash.user_cut.create", str(cut["branch_id"]))
        key, digest = self._key(idempotency_key), self._hash("finalize", actor, cut_id, payload)
        replay = self._replay(key, digest)
        if replay is not None:
            return replay
        if cut["status"] != "COUNTED":
            raise BusinessError("cash_cut_transition_invalid", "Cash cut must be COUNTED")
        if payload["version"] != int(cut["version"]):
            raise BusinessError("cash_cut_version_conflict", "Cash cut version is stale")
        shift = (
            self.session.execute(
                sa.select(models.cash_shifts)
                .where(models.cash_shifts.c.id == cut["cash_shift_id"])
                .with_for_update()
            )
            .mappings()
            .one()
        )
        closure = (
            self.session.execute(
                sa.select(models.cash_shift_closures)
                .where(models.cash_shift_closures.c.cash_shift_id == cut["cash_shift_id"])
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if (
            str(shift["status"]).upper() != "OPERATIVELY_CLOSED"
            or not closure
            or cut["branch_id"] != shift["branch_id"]
            or cut["register_code_snapshot"] != shift["register_code"]
            or cut["cashier_user_id"] != shift["cashier_user_id"]
            or self._utc(cut["period_start"]) != self._utc(shift["opened_at"])
            or self._utc(cut["period_end"]) != self._utc(closure["closed_at"])
        ):
            raise BusinessError(
                "cash_cut_shift_not_closed", "Cash shift is not operationally closed"
            )
        summary = calculate_expected_cash(self.session, cut["cash_shift_id"])
        now = _now()
        expected = summary["expected_cash_cents"]
        difference = int(cut["counted_cash_cents"]) - expected
        operations: list[dict[str, Any]] = []
        for payment in self.session.execute(
            sa.select(models.payments).where(
                models.payments.c.cash_shift_id == cut["cash_shift_id"],
                models.payments.c.status == "CONFIRMED",
                sa.func.lower(models.payments.c.method) == "cash",
            )
        ).mappings():
            confirmed_at = payment["confirmed_at"]
            if not isinstance(confirmed_at, datetime):
                raise BusinessError(
                    "cash_cut_operation_conflict", "Confirmed payment timestamp is invalid"
                )
            confirmed_at = self._utc(confirmed_at)
            if not (self._utc(cut["period_start"]) <= confirmed_at < self._utc(cut["period_end"])):
                raise BusinessError("cash_cut_operation_conflict", "Payment is outside cut period")
            operations.append(
                {
                    "operation_type": "PAYMENT",
                    "operation_id": payment["id"],
                    "signed_amount_cents": int(payment["amount_cents"]),
                    "occurred_at": confirmed_at,
                }
            )
        for movement in self.session.execute(
            sa.select(models.cash_movements).where(
                models.cash_movements.c.cash_shift_id == cut["cash_shift_id"],
                models.cash_movements.c.status == "confirmed",
            )
        ).mappings():
            kind = str(movement["movement_type"]).lower()
            if kind not in {"deposit", "withdrawal", "cash_reversal"}:
                raise BusinessError("cash_cut_operation_conflict", "Unknown confirmed movement")
            occurred_at = movement["created_at"]
            if not isinstance(occurred_at, datetime):
                raise BusinessError(
                    "cash_cut_operation_conflict", "Confirmed movement timestamp is invalid"
                )
            occurred_at = self._utc(occurred_at)
            if not (self._utc(cut["period_start"]) <= occurred_at < self._utc(cut["period_end"])):
                raise BusinessError("cash_cut_operation_conflict", "Movement is outside cut period")
            operations.append(
                {
                    "operation_type": "MOVEMENT",
                    "operation_id": movement["id"],
                    "signed_amount_cents": int(movement["amount_cents"])
                    * (-1 if kind == "withdrawal" else 1),
                    "occurred_at": occurred_at,
                }
            )
        try:
            for operation in operations:
                self.session.execute(
                    models.user_cash_cut_operations.insert().values(
                        id=_id(),
                        organization_id=ORGANIZATION_ID,
                        cash_cut_id=cut_id,
                        **operation,
                    )
                )
            self.session.execute(
                models.user_cash_cuts.update()
                .where(models.user_cash_cuts.c.id == cut_id)
                .values(
                    status="FINALIZED",
                    cash_payment_cents=summary["cash_payment_cents"],
                    deposit_cents=summary["deposit_cents"],
                    withdrawal_cents=summary["withdrawal_cents"],
                    expected_cash_cents=expected,
                    difference_cents=difference,
                    finalized_by_user_id=actor,
                    finalized_at=now,
                    version=int(cut["version"]) + 1,
                )
            )
            cut.update(
                status="FINALIZED",
                opening_cash_cents=summary["opening_cash_cents"],
                cash_payment_cents=summary["cash_payment_cents"],
                deposit_cents=summary["deposit_cents"],
                withdrawal_cents=summary["withdrawal_cents"],
                expected_cash_cents=expected,
                difference_cents=difference,
                finalized_by_user_id=actor,
                finalized_at=now,
                version=int(cut["version"]) + 1,
            )
            result = {"cash_cut": self._public(cut)}
            self._store("finalize", key, digest, actor, cut_id, result, now)
            _audit(
                self.session,
                "cash_user_cut.finalized",
                "user_cash_cut",
                cut_id,
                {"result": "finalized"},
                str(cut["branch_id"]),
                actor_user_id=actor,
            )
            self.session.commit()
            _record_pco006_metric(
                "cash_cut_difference_cents",
                result="recorded",
                branch_id=str(cut["branch_id"]),
            )
            return result
        except IntegrityError as exc:
            self.session.rollback()
            raise BusinessError(
                "cash_cut_operation_conflict",
                "Operation is already associated with a cash cut",
            ) from exc
        except Exception:
            self.session.rollback()
            raise


def list_inventory_cost_states(session: Session, branch_id: str | None) -> list[dict[str, Any]]:
    rows = session.execute(
        sa.select(
            models.inventory_cost_states,
            models.inventory_items.c.name.label("item_name"),
            models.inventory_items.c.sku.label("item_sku"),
            models.inventory_units.c.code.label("unit_code"),
        )
        .select_from(
            models.inventory_cost_states.join(
                models.inventory_items,
                models.inventory_cost_states.c.item_id == models.inventory_items.c.id,
            ).join(
                models.inventory_units,
                models.inventory_items.c.base_unit_id == models.inventory_units.c.id,
            )
        )
        .where(models.inventory_cost_states.c.branch_id == branch_id)
    ).mappings()
    return [dict(row) for row in rows]


def create_waste_reason(
    session: Session,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    code = str(payload.get("code", "")).strip().upper().replace(" ", "_")
    name = str(payload.get("name", "")).strip()
    classification = str(payload.get("classification", "other")).strip().lower()
    if not code or not name or not classification:
        raise BusinessError(
            "invalid_waste_reason", "Waste reason code, name and classification are required"
        )
    now = _now()
    reason: dict[str, Any] = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "code": code,
        "name": name,
        "classification": classification,
        "display_order": int(payload.get("display_order", 0)),
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    session.execute(models.waste_reasons.insert().values(**reason))
    _audit(
        session,
        "waste_reason.created",
        "waste_reason",
        reason["id"],
        {"code": code, "classification": classification},
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return reason


def update_waste_reason(
    session: Session,
    reason_id: str,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "catalog.manage")
    existing = (
        session.execute(
            sa.select(models.waste_reasons).where(
                models.waste_reasons.c.id == reason_id,
                models.waste_reasons.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not existing:
        raise BusinessError("waste_reason_not_found", "Waste reason was not found")
    values: dict[str, Any] = {"updated_at": _now()}
    for field in ("name", "classification", "status"):
        if field in payload:
            value = str(payload[field]).strip()
            if not value:
                raise BusinessError("invalid_waste_reason", "Waste reason fields cannot be empty")
            values[field] = value.lower() if field in {"classification", "status"} else value
    if "display_order" in payload:
        values["display_order"] = int(payload["display_order"])
    session.execute(
        sa.update(models.waste_reasons)
        .where(models.waste_reasons.c.id == reason_id)
        .values(**values)
    )
    _audit(
        session,
        "waste_reason.updated",
        "waste_reason",
        reason_id,
        values,
        branch_id=None,
        actor_user_id=actor_id,
    )
    session.commit()
    return {**dict(existing), **values}


def list_waste_reasons(session: Session, include_inactive: bool = False) -> list[dict[str, Any]]:
    query = sa.select(models.waste_reasons).where(
        models.waste_reasons.c.organization_id == ORGANIZATION_ID
    )
    if not include_inactive:
        query = query.where(models.waste_reasons.c.status == "active")
    rows = session.execute(
        query.order_by(models.waste_reasons.c.display_order, models.waste_reasons.c.name)
    ).mappings()
    return [dict(row) for row in rows]


def create_waste_record(
    session: Session,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    branch_id = str(payload.get("branch_id", ""))
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "inventory.waste", branch_id)
    item_id = str(payload.get("item_id", ""))
    item = (
        session.execute(
            sa.select(models.inventory_items).where(
                models.inventory_items.c.id == item_id,
                models.inventory_items.c.organization_id == ORGANIZATION_ID,
                models.inventory_items.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not item:
        raise BusinessError("waste_item_not_found", "Waste inventory item was not found")
    unit_id = str(payload.get("unit_id") or item["base_unit_id"])
    if unit_id != item["base_unit_id"]:
        raise BusinessError("waste_unit_mismatch", "Waste unit must match item base unit")
    reason_id = str(payload.get("reason_id", ""))
    reason = (
        session.execute(
            sa.select(models.waste_reasons).where(
                models.waste_reasons.c.id == reason_id,
                models.waste_reasons.c.organization_id == ORGANIZATION_ID,
                models.waste_reasons.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not reason:
        raise BusinessError("active_waste_reason_not_found", "Active waste reason was not found")
    quantity = _quantity(payload.get("quantity", 0))
    stage = str(payload.get("stage", "")).strip().lower()
    evidence = payload.get("evidence", [])
    notes = str(payload.get("notes", "")).strip() or None
    if quantity <= 0 or not stage:
        raise BusinessError("invalid_waste_record", "Positive quantity and stage are required")
    if (
        not isinstance(evidence, list)
        or len(evidence) > 10
        or any(
            not isinstance(value, str) or not value.strip() or len(value) > 1000
            for value in evidence
        )
    ):
        raise BusinessError(
            "invalid_waste_evidence", "Waste evidence must be a list of at most ten references"
        )
    if notes and len(notes) > 600:
        raise BusinessError("invalid_waste_notes", "Waste notes exceed 600 characters")
    now = _now()
    record: dict[str, Any] = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "branch_id": branch_id,
        "warehouse_id": _branch_warehouse_id(session, branch_id),
        "item_id": item_id,
        "unit_id": unit_id,
        "reason_id": reason_id,
        "stage": stage,
        "quantity": quantity,
        "unit_cost": 0,
        "total_cost": 0,
        "effective_at": _parse_document_date(payload.get("effective_at"), now),
        "evidence": [value.strip() for value in evidence],
        "notes": notes,
        "status": "draft",
        "created_by": actor_id,
        "confirmed_by": None,
        "reversed_by": None,
        "movement_id": None,
        "reversal_movement_id": None,
        "confirmation_idempotency_key": None,
        "reversal_idempotency_key": None,
        "reversal_reason": None,
        "created_at": now,
        "confirmed_at": None,
        "reversed_at": None,
    }
    session.execute(models.waste_records.insert().values(**record))
    _audit(
        session,
        "waste.created",
        "waste",
        record["id"],
        {"item_id": item_id, "quantity": str(quantity), "reason_id": reason_id, "stage": stage},
        branch_id,
        actor_user_id=actor_id,
    )

    session.commit()
    return get_waste_record(session, record["id"])


def confirm_waste_record(
    session: Session,
    waste_id: str,
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    key = idempotency_key.strip()
    if not key:
        raise BusinessError(
            "idempotency_key_required", "Waste confirmation requires idempotency key"
        )
    record = (
        session.execute(
            sa.select(models.waste_records).where(models.waste_records.c.id == waste_id)
        )
        .mappings()
        .first()
    )
    if not record:
        raise BusinessError("waste_not_found", "Waste record was not found")
    require_permission(session, actor_id, "inventory.waste", record["branch_id"])
    if record["status"] in {"confirmed", "reversed"}:
        if record["confirmation_idempotency_key"] == key:
            return get_waste_record(session, waste_id)
        raise BusinessError("waste_already_confirmed", "Waste record was already confirmed")
    if record["status"] != "draft":
        raise BusinessError("waste_not_confirmable", "Only draft waste can be confirmed")
    quantity = _quantity(record["quantity"])
    available = _physical_inventory_quantity(
        session, record["branch_id"], record["warehouse_id"], record["item_id"]
    )
    if available < quantity:
        raise BusinessError(
            "insufficient_waste_inventory", "Waste quantity exceeds physical inventory"
        )
    state = (
        session.execute(
            sa.select(models.inventory_cost_states).where(
                models.inventory_cost_states.c.branch_id == record["branch_id"],
                models.inventory_cost_states.c.warehouse_id == record["warehouse_id"],
                models.inventory_cost_states.c.item_id == record["item_id"],
            )
        )
        .mappings()
        .first()
    )
    unit_cost = _cost(state["average_unit_cost"] if state else 0)
    total_cost = _cost(quantity * unit_cost)
    now = _now()
    movement_id = _id()
    session.execute(
        models.inventory_movements.insert().values(
            id=movement_id,
            organization_id=ORGANIZATION_ID,
            branch_id=record["branch_id"],
            warehouse_id=record["warehouse_id"],
            item_id=record["item_id"],
            movement_type="WASTE_REAL",
            quantity_delta=-quantity,
            unit_id=record["unit_id"],
            unit_cost=unit_cost,
            total_cost=-total_cost,
            effective_at=record["effective_at"],
            actor_user_id=actor_id,
            document_type="waste",
            document_id=waste_id,
            reference=None,
            reason=f"Merma real: {record['reason_id']}",
            notes=record["notes"],
            idempotency_key=key,
            status="confirmed",
            reversal_of_id=None,
            source_type="waste",
            source_id=waste_id,
            created_at=now,
        )
    )
    _set_inventory_cost_quantity(
        session,
        record["branch_id"],
        record["warehouse_id"],
        record["item_id"],
        _quantity(available - quantity),
        unit_cost,
        now,
    )
    session.execute(
        sa.update(models.waste_records)
        .where(models.waste_records.c.id == waste_id)
        .values(
            status="confirmed",
            unit_cost=unit_cost,
            total_cost=total_cost,
            confirmed_by=actor_id,
            movement_id=movement_id,
            confirmation_idempotency_key=key,
            confirmed_at=now,
        )
    )
    _audit(
        session,
        "waste.confirmed",
        "waste",
        waste_id,
        {"movement_id": movement_id, "quantity": str(quantity), "total_cost": str(total_cost)},
        record["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_waste_record(session, waste_id)


def reverse_waste_record(
    session: Session,
    waste_id: str,
    reason: str,
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    key = idempotency_key.strip()
    normalized_reason = reason.strip()
    if not key:
        raise BusinessError("idempotency_key_required", "Waste reversal requires idempotency key")
    if not normalized_reason:
        raise BusinessError("waste_reversal_reason_required", "Waste reversal reason is required")
    record = (
        session.execute(
            sa.select(models.waste_records).where(models.waste_records.c.id == waste_id)
        )
        .mappings()
        .first()
    )
    if not record:
        raise BusinessError("waste_not_found", "Waste record was not found")
    require_permission(session, actor_id, "inventory.waste", record["branch_id"])
    if record["status"] == "reversed":
        if record["reversal_idempotency_key"] == key:
            return get_waste_record(session, waste_id)
        raise BusinessError("waste_already_reversed", "Waste record was already reversed")
    if record["status"] != "confirmed" or not record["movement_id"]:
        raise BusinessError("waste_not_reversible", "Only confirmed waste can be reversed")
    now = _now()
    quantity = _quantity(record["quantity"])
    unit_cost = _cost(record["unit_cost"])
    total_cost = _cost(record["total_cost"])
    reversal_id = _id()
    session.execute(
        models.inventory_movements.insert().values(
            id=reversal_id,
            organization_id=ORGANIZATION_ID,
            branch_id=record["branch_id"],
            warehouse_id=record["warehouse_id"],
            item_id=record["item_id"],
            movement_type="WASTE_REVERSAL",
            quantity_delta=quantity,
            unit_id=record["unit_id"],
            unit_cost=unit_cost,
            total_cost=total_cost,
            effective_at=now,
            actor_user_id=actor_id,
            document_type="waste",
            document_id=waste_id,
            reference=record["movement_id"],
            reason=normalized_reason,
            notes=None,
            idempotency_key=key,
            status="confirmed",
            reversal_of_id=record["movement_id"],
            source_type="waste_reversal",
            source_id=waste_id,
            created_at=now,
        )
    )
    available = _physical_inventory_quantity(
        session, record["branch_id"], record["warehouse_id"], record["item_id"]
    )
    _set_inventory_cost_quantity(
        session,
        record["branch_id"],
        record["warehouse_id"],
        record["item_id"],
        available,
        unit_cost,
        now,
    )
    session.execute(
        sa.update(models.waste_records)
        .where(models.waste_records.c.id == waste_id)
        .values(
            status="reversed",
            reversed_by=actor_id,
            reversal_movement_id=reversal_id,
            reversal_idempotency_key=key,
            reversal_reason=normalized_reason,
            reversed_at=now,
        )
    )
    _audit(
        session,
        "waste.reversed",
        "waste",
        waste_id,
        {
            "movement_id": reversal_id,
            "reversal_of_id": record["movement_id"],
            "reason": normalized_reason,
        },
        record["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_waste_record(session, waste_id)


def _set_inventory_cost_quantity(
    session: Session,
    branch_id: str,
    warehouse_id: str,
    item_id: str,
    quantity: Decimal,
    unit_cost: Decimal,
    now: datetime,
) -> None:
    existing = (
        session.execute(
            sa.select(models.inventory_cost_states).where(
                models.inventory_cost_states.c.branch_id == branch_id,
                models.inventory_cost_states.c.warehouse_id == warehouse_id,
                models.inventory_cost_states.c.item_id == item_id,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        session.execute(
            sa.update(models.inventory_cost_states)
            .where(
                models.inventory_cost_states.c.branch_id == branch_id,
                models.inventory_cost_states.c.warehouse_id == warehouse_id,
                models.inventory_cost_states.c.item_id == item_id,
            )
            .values(quantity_on_hand=quantity, updated_at=now)
        )
    else:
        session.execute(
            models.inventory_cost_states.insert().values(
                branch_id=branch_id,
                warehouse_id=warehouse_id,
                item_id=item_id,
                quantity_on_hand=quantity,
                average_unit_cost=unit_cost,
                last_unit_cost=unit_cost,
                last_supplier_id=None,
                last_cost_at=now,
                updated_at=now,
            )
        )


def get_waste_record(session: Session, waste_id: str) -> dict[str, Any]:
    record = (
        session.execute(
            sa.select(
                models.waste_records,
                models.inventory_items.c.name.label("item_name"),
                models.inventory_items.c.sku.label("item_sku"),
                models.inventory_units.c.code.label("unit_code"),
                models.waste_reasons.c.code.label("reason_code"),
                models.waste_reasons.c.name.label("reason_name"),
                models.waste_reasons.c.classification.label("reason_classification"),
            )
            .select_from(
                models.waste_records.join(
                    models.inventory_items,
                    models.waste_records.c.item_id == models.inventory_items.c.id,
                )
                .join(
                    models.inventory_units,
                    models.waste_records.c.unit_id == models.inventory_units.c.id,
                )
                .join(
                    models.waste_reasons,
                    models.waste_records.c.reason_id == models.waste_reasons.c.id,
                )
            )
            .where(models.waste_records.c.id == waste_id)
        )
        .mappings()
        .first()
    )
    if not record:
        raise BusinessError("waste_not_found", "Waste record was not found")
    result = dict(record)
    movement_ids = [
        value for value in (record["movement_id"], record["reversal_movement_id"]) if value
    ]
    result["movements"] = (
        [
            dict(row)
            for row in session.execute(
                sa.select(models.inventory_movements)
                .where(models.inventory_movements.c.id.in_(movement_ids))
                .order_by(models.inventory_movements.c.created_at)
            ).mappings()
        ]
        if movement_ids
        else []
    )
    return result


def list_waste_records(session: Session, branch_id: str | None) -> list[dict[str, Any]]:
    ids = session.execute(
        sa.select(models.waste_records.c.id)
        .where(models.waste_records.c.branch_id == branch_id)
        .order_by(models.waste_records.c.created_at.desc())
    ).scalars()
    return [get_waste_record(session, waste_id) for waste_id in ids]


def create_inventory_transfer(
    session: Session,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    source_branch_id = str(payload.get("source_branch_id", ""))
    destination_branch_id = str(payload.get("destination_branch_id", ""))
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "inventory.transfer.send", source_branch_id)
    if (
        not source_branch_id
        or not destination_branch_id
        or source_branch_id == destination_branch_id
    ):
        raise BusinessError(
            "invalid_transfer_branches",
            "Transfer source and destination must be different branches",
        )
    branch_rows = [
        dict(row)
        for row in session.execute(
            sa.select(models.branches.c.id, models.branches.c.code).where(
                models.branches.c.id.in_([source_branch_id, destination_branch_id]),
                models.branches.c.organization_id == ORGANIZATION_ID,
                models.branches.c.status == "active",
            )
        ).mappings()
    ]
    if {row["id"] for row in branch_rows} != {source_branch_id, destination_branch_id}:
        raise BusinessError("transfer_branch_not_found", "Active transfer branches were not found")
    requested_lines = list(payload.get("lines", []))
    if not requested_lines:
        raise BusinessError("transfer_lines_required", "Transfer requires at least one line")
    seen = set()
    now = _now()
    line_rows = []
    for line in requested_lines:
        item_id = str(line.get("item_id", ""))
        if not item_id or item_id in seen:
            raise BusinessError(
                "duplicate_transfer_item", "Transfer item cannot be empty or duplicated"
            )
        seen.add(item_id)
        item = (
            session.execute(
                sa.select(models.inventory_items).where(
                    models.inventory_items.c.id == item_id,
                    models.inventory_items.c.organization_id == ORGANIZATION_ID,
                    models.inventory_items.c.status == "active",
                )
            )
            .mappings()
            .first()
        )
        if not item:
            raise BusinessError("transfer_item_not_found", "Transfer item was not found")
        unit_id = str(line.get("unit_id") or item["base_unit_id"])
        quantity = _quantity(line.get("quantity", 0))
        if unit_id != item["base_unit_id"] or quantity <= 0:
            raise BusinessError(
                "invalid_transfer_line", "Transfer quantity must be positive in item base unit"
            )
        line_rows.append(
            {
                "id": _id(),
                "item_id": item_id,
                "unit_id": unit_id,
                "requested_quantity": quantity,
                "sent_quantity": 0,
                "received_quantity": 0,
                "difference_quantity": 0,
                "unit_cost": 0,
                "sent_total_cost": 0,
                "received_total_cost": 0,
                "difference_cost": 0,
                "difference_reason": None,
                "condition": None,
                "notes": str(line.get("notes", "")).strip() or None,
                "out_movement_id": None,
                "in_movement_id": None,
                "created_at": now,
            }
        )
    source_code = next(row["code"] for row in branch_rows if row["id"] == source_branch_id)
    transfer_id = _id()
    transfer = {
        "id": transfer_id,
        "organization_id": ORGANIZATION_ID,
        "source_branch_id": source_branch_id,
        "source_warehouse_id": _branch_warehouse_id(session, source_branch_id),
        "destination_branch_id": destination_branch_id,
        "destination_warehouse_id": _branch_warehouse_id(session, destination_branch_id),
        "folio": f"TRF-{source_code}-{uuid4().hex[:8].upper()}",
        "status": "draft",
        "notes": str(payload.get("notes", "")).strip() or None,
        "cancellation_reason": None,
        "created_by": actor_id,
        "sent_by": None,
        "received_by": None,
        "cancelled_by": None,
        "send_idempotency_key": None,
        "receive_idempotency_key": None,
        "created_at": now,
        "sent_at": None,
        "received_at": None,
        "cancelled_at": None,
    }
    session.execute(models.inventory_transfers.insert().values(**transfer))
    session.execute(
        models.inventory_transfer_lines.insert(),
        [{**line, "transfer_id": transfer_id} for line in line_rows],
    )
    _audit(
        session,
        "inventory_transfer.created",
        "inventory_transfer",
        transfer_id,
        {"destination_branch_id": destination_branch_id, "line_count": len(line_rows)},
        source_branch_id,
        actor_user_id=actor_id,
    )
    session.commit()
    return get_inventory_transfer(session, transfer_id)


def send_inventory_transfer(
    session: Session,
    transfer_id: str,
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    key = idempotency_key.strip()
    if not key:
        raise BusinessError("idempotency_key_required", "Transfer send requires idempotency key")
    transfer = (
        session.execute(
            sa.select(models.inventory_transfers).where(
                models.inventory_transfers.c.id == transfer_id
            )
        )
        .mappings()
        .first()
    )
    if not transfer:
        raise BusinessError("transfer_not_found", "Inventory transfer was not found")
    require_permission(session, actor_id, "inventory.transfer.send", transfer["source_branch_id"])
    if transfer["status"] in {"sent", "received", "received_with_difference"}:
        if transfer["send_idempotency_key"] == key:
            return get_inventory_transfer(session, transfer_id)
        raise BusinessError("transfer_already_sent", "Inventory transfer was already sent")
    if transfer["status"] != "draft":
        raise BusinessError("transfer_not_sendable", "Only draft transfer can be sent")
    lines = [
        dict(row)
        for row in session.execute(
            sa.select(models.inventory_transfer_lines).where(
                models.inventory_transfer_lines.c.transfer_id == transfer_id
            )
        ).mappings()
    ]
    requirements = []
    for line in lines:
        quantity = _quantity(line["requested_quantity"])
        available = _physical_inventory_quantity(
            session, transfer["source_branch_id"], transfer["source_warehouse_id"], line["item_id"]
        )
        if available < quantity:
            raise BusinessError(
                "insufficient_transfer_inventory", "Transfer item exceeds physical inventory"
            )
        state = (
            session.execute(
                sa.select(models.inventory_cost_states).where(
                    models.inventory_cost_states.c.branch_id == transfer["source_branch_id"],
                    models.inventory_cost_states.c.warehouse_id == transfer["source_warehouse_id"],
                    models.inventory_cost_states.c.item_id == line["item_id"],
                )
            )
            .mappings()
            .first()
        )
        unit_cost = _cost(state["average_unit_cost"] if state else 0)
        requirements.append((line, quantity, available, unit_cost, _cost(quantity * unit_cost)))
    now = _now()
    for index, (line, quantity, available, unit_cost, total_cost) in enumerate(requirements):
        movement_id = _id()
        session.execute(
            models.inventory_movements.insert().values(
                id=movement_id,
                organization_id=ORGANIZATION_ID,
                branch_id=transfer["source_branch_id"],
                warehouse_id=transfer["source_warehouse_id"],
                item_id=line["item_id"],
                movement_type="TRANSFER_OUT",
                quantity_delta=-quantity,
                unit_id=line["unit_id"],
                unit_cost=unit_cost,
                total_cost=-total_cost,
                effective_at=now,
                actor_user_id=actor_id,
                document_type="inventory_transfer",
                document_id=transfer_id,
                reference=transfer["folio"],
                reason="Envío de traspaso",
                notes=line["notes"],
                idempotency_key=f"{key}:out:{index}",
                status="confirmed",
                reversal_of_id=None,
                source_type="inventory_transfer",
                source_id=transfer_id,
                created_at=now,
            )
        )
        _set_inventory_cost_quantity(
            session,
            transfer["source_branch_id"],
            transfer["source_warehouse_id"],
            line["item_id"],
            _quantity(available - quantity),
            unit_cost,
            now,
        )
        session.execute(
            sa.update(models.inventory_transfer_lines)
            .where(models.inventory_transfer_lines.c.id == line["id"])
            .values(
                sent_quantity=quantity,
                unit_cost=unit_cost,
                sent_total_cost=total_cost,
                out_movement_id=movement_id,
            )
        )
    session.execute(
        sa.update(models.inventory_transfers)
        .where(models.inventory_transfers.c.id == transfer_id)
        .values(status="sent", sent_by=actor_id, send_idempotency_key=key, sent_at=now)
    )
    _audit(
        session,
        "inventory_transfer.sent",
        "inventory_transfer",
        transfer_id,
        {"folio": transfer["folio"], "line_count": len(lines)},
        transfer["source_branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_inventory_transfer(session, transfer_id)


def receive_inventory_transfer(
    session: Session,
    transfer_id: str,
    received_lines: list[dict[str, Any]],
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    key = idempotency_key.strip()
    if not key:
        raise BusinessError("idempotency_key_required", "Transfer receipt requires idempotency key")
    transfer = (
        session.execute(
            sa.select(models.inventory_transfers).where(
                models.inventory_transfers.c.id == transfer_id
            )
        )
        .mappings()
        .first()
    )
    if not transfer:
        raise BusinessError("transfer_not_found", "Inventory transfer was not found")
    require_permission(
        session, actor_id, "inventory.transfer.receive", transfer["destination_branch_id"]
    )
    if transfer["status"] in {"received", "received_with_difference"}:
        if transfer["receive_idempotency_key"] == key:
            return get_inventory_transfer(session, transfer_id)
        raise BusinessError("transfer_already_received", "Inventory transfer was already received")
    if transfer["status"] != "sent":
        raise BusinessError("transfer_not_receivable", "Only sent transfer can be received")
    stored_lines = [
        dict(row)
        for row in session.execute(
            sa.select(models.inventory_transfer_lines).where(
                models.inventory_transfer_lines.c.transfer_id == transfer_id
            )
        ).mappings()
    ]
    received_by_id = {str(line.get("line_id", "")): line for line in received_lines}
    if set(received_by_id) != {line["id"] for line in stored_lines}:
        raise BusinessError(
            "transfer_receipt_lines_mismatch",
            "Receipt must provide every transfer line exactly once",
        )
    resolutions = []
    has_difference = False
    for line in stored_lines:
        receipt = received_by_id[line["id"]]
        sent = _quantity(line["sent_quantity"])
        received = _quantity(receipt.get("received_quantity", 0))
        if received < 0 or received > sent:
            raise BusinessError(
                "invalid_transfer_received_quantity",
                "Received quantity must be between zero and sent quantity",
            )
        difference = _quantity(sent - received)
        difference_reason = str(receipt.get("difference_reason", "")).strip() or None
        condition = str(receipt.get("condition", "good")).strip().lower()
        if difference > 0 and not difference_reason:
            raise BusinessError(
                "transfer_difference_reason_required", "Transfer difference requires a reason"
            )
        has_difference = has_difference or difference > 0
        destination_quantity = _physical_inventory_quantity(
            session,
            transfer["destination_branch_id"],
            transfer["destination_warehouse_id"],
            line["item_id"],
        )
        if destination_quantity < 0:
            raise BusinessError(
                "negative_inventory_cost_policy_required",
                "Destination has negative physical inventory",
            )
        destination_state_row = (
            session.execute(
                sa.select(models.inventory_cost_states).where(
                    models.inventory_cost_states.c.branch_id == transfer["destination_branch_id"],
                    models.inventory_cost_states.c.warehouse_id
                    == transfer["destination_warehouse_id"],
                    models.inventory_cost_states.c.item_id == line["item_id"],
                )
            )
            .mappings()
            .first()
        )
        destination_state = dict(destination_state_row) if destination_state_row else None
        resolutions.append(
            (
                line,
                received,
                difference,
                difference_reason,
                condition,
                destination_quantity,
                destination_state,
                _cost(received * _cost(line["unit_cost"])),
                _cost(difference * _cost(line["unit_cost"])),
            )
        )
    now = _now()
    for index, (
        line,
        received,
        difference,
        difference_reason,
        condition,
        destination_quantity,
        destination_state,
        received_cost,
        difference_cost,
    ) in enumerate(resolutions):
        movement_id = None
        if received > 0:
            movement_id = _id()
            session.execute(
                models.inventory_movements.insert().values(
                    id=movement_id,
                    organization_id=ORGANIZATION_ID,
                    branch_id=transfer["destination_branch_id"],
                    warehouse_id=transfer["destination_warehouse_id"],
                    item_id=line["item_id"],
                    movement_type="TRANSFER_IN",
                    quantity_delta=received,
                    unit_id=line["unit_id"],
                    unit_cost=line["unit_cost"],
                    total_cost=received_cost,
                    effective_at=now,
                    actor_user_id=actor_id,
                    document_type="inventory_transfer",
                    document_id=transfer_id,
                    reference=transfer["folio"],
                    reason="Recepción de traspaso",
                    notes=difference_reason,
                    idempotency_key=f"{key}:in:{index}",
                    status="confirmed",
                    reversal_of_id=None,
                    source_type="inventory_transfer",
                    source_id=transfer_id,
                    created_at=now,
                )
            )
            _apply_transfer_destination_cost(
                session,
                transfer["destination_branch_id"],
                transfer["destination_warehouse_id"],
                line["item_id"],
                destination_quantity,
                destination_state,
                received,
                _cost(line["unit_cost"]),
                received_cost,
                now,
            )
        session.execute(
            sa.update(models.inventory_transfer_lines)
            .where(models.inventory_transfer_lines.c.id == line["id"])
            .values(
                received_quantity=received,
                difference_quantity=difference,
                received_total_cost=received_cost,
                difference_cost=difference_cost,
                difference_reason=difference_reason,
                condition=condition,
                notes=str(received_by_id[line["id"]].get("notes", "")).strip() or line["notes"],
                in_movement_id=movement_id,
            )
        )
    final_status = "received_with_difference" if has_difference else "received"
    session.execute(
        sa.update(models.inventory_transfers)
        .where(models.inventory_transfers.c.id == transfer_id)
        .values(
            status=final_status,
            received_by=actor_id,
            receive_idempotency_key=key,
            received_at=now,
        )
    )
    _audit(
        session,
        "inventory_transfer.received",
        "inventory_transfer",
        transfer_id,
        {"status": final_status, "folio": transfer["folio"]},
        transfer["destination_branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_inventory_transfer(session, transfer_id)


def _apply_transfer_destination_cost(
    session: Session,
    branch_id: str,
    warehouse_id: str,
    item_id: str,
    current_quantity: Decimal,
    current_state: dict[str, Any] | None,
    received_quantity: Decimal,
    received_unit_cost: Decimal,
    received_cost: Decimal,
    now: datetime,
) -> None:
    current_average = _cost(current_state["average_unit_cost"] if current_state else 0)
    new_quantity = _quantity(current_quantity + received_quantity)
    new_average = (
        received_unit_cost
        if current_quantity == 0
        else _cost(((current_quantity * current_average) + received_cost) / new_quantity)
    )
    values = {
        "quantity_on_hand": new_quantity,
        "average_unit_cost": new_average,
        "last_unit_cost": received_unit_cost,
        "last_supplier_id": None,
        "last_cost_at": now,
        "updated_at": now,
    }
    if current_state:
        session.execute(
            sa.update(models.inventory_cost_states)
            .where(
                models.inventory_cost_states.c.branch_id == branch_id,
                models.inventory_cost_states.c.warehouse_id == warehouse_id,
                models.inventory_cost_states.c.item_id == item_id,
            )
            .values(**values)
        )
    else:
        session.execute(
            models.inventory_cost_states.insert().values(
                branch_id=branch_id, warehouse_id=warehouse_id, item_id=item_id, **values
            )
        )


def cancel_inventory_transfer(
    session: Session,
    transfer_id: str,
    reason: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    normalized_reason = reason.strip()
    transfer = (
        session.execute(
            sa.select(models.inventory_transfers).where(
                models.inventory_transfers.c.id == transfer_id
            )
        )
        .mappings()
        .first()
    )
    if not transfer:
        raise BusinessError("transfer_not_found", "Inventory transfer was not found")
    require_permission(session, actor_id, "inventory.transfer.send", transfer["source_branch_id"])
    if transfer["status"] != "draft":
        raise BusinessError("transfer_not_cancellable", "Only draft transfer can be cancelled")
    if not normalized_reason:
        raise BusinessError(
            "transfer_cancellation_reason_required", "Transfer cancellation reason is required"
        )
    now = _now()
    session.execute(
        sa.update(models.inventory_transfers)
        .where(models.inventory_transfers.c.id == transfer_id)
        .values(
            status="cancelled",
            cancellation_reason=normalized_reason,
            cancelled_by=actor_id,
            cancelled_at=now,
        )
    )
    _audit(
        session,
        "inventory_transfer.cancelled",
        "inventory_transfer",
        transfer_id,
        {"reason": normalized_reason},
        transfer["source_branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_inventory_transfer(session, transfer_id)


def get_inventory_transfer(session: Session, transfer_id: str) -> dict[str, Any]:
    transfer = (
        session.execute(
            sa.select(
                models.inventory_transfers,
                models.branches.c.name.label("source_branch_name"),
            )
            .select_from(
                models.inventory_transfers.join(
                    models.branches,
                    models.inventory_transfers.c.source_branch_id == models.branches.c.id,
                )
            )
            .where(models.inventory_transfers.c.id == transfer_id)
        )
        .mappings()
        .first()
    )
    if not transfer:
        raise BusinessError("transfer_not_found", "Inventory transfer was not found")
    destination_name = session.execute(
        sa.select(models.branches.c.name).where(
            models.branches.c.id == transfer["destination_branch_id"]
        )
    ).scalar_one()
    result = {**dict(transfer), "destination_branch_name": destination_name}
    result["lines"] = [
        dict(row)
        for row in session.execute(
            sa.select(
                models.inventory_transfer_lines,
                models.inventory_items.c.name.label("item_name"),
                models.inventory_items.c.sku.label("item_sku"),
                models.inventory_units.c.code.label("unit_code"),
            )
            .select_from(
                models.inventory_transfer_lines.join(
                    models.inventory_items,
                    models.inventory_transfer_lines.c.item_id == models.inventory_items.c.id,
                ).join(
                    models.inventory_units,
                    models.inventory_transfer_lines.c.unit_id == models.inventory_units.c.id,
                )
            )
            .where(models.inventory_transfer_lines.c.transfer_id == transfer_id)
            .order_by(models.inventory_items.c.name)
        ).mappings()
    ]
    movement_ids = [
        movement_id
        for line in result["lines"]
        for movement_id in (line["out_movement_id"], line["in_movement_id"])
        if movement_id
    ]
    result["movements"] = (
        [
            dict(row)
            for row in session.execute(
                sa.select(models.inventory_movements)
                .where(models.inventory_movements.c.id.in_(movement_ids))
                .order_by(models.inventory_movements.c.created_at)
            ).mappings()
        ]
        if movement_ids
        else []
    )
    return result


def list_inventory_transfers(session: Session, branch_id: str | None) -> list[dict[str, Any]]:
    ids = session.execute(
        sa.select(models.inventory_transfers.c.id)
        .where(
            sa.or_(
                models.inventory_transfers.c.source_branch_id == branch_id,
                models.inventory_transfers.c.destination_branch_id == branch_id,
            )
        )
        .order_by(models.inventory_transfers.c.created_at.desc())
    ).scalars()
    return [get_inventory_transfer(session, transfer_id) for transfer_id in ids]


def create_physical_count_session(
    session: Session,
    payload: dict[str, Any],
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    branch_id = str(payload.get("branch_id", ""))
    actor_id = _actor_user_id(actor_user_id)
    require_permission(session, actor_id, "inventory.count", branch_id)
    active = session.execute(
        sa.select(models.physical_count_sessions.c.id).where(
            models.physical_count_sessions.c.branch_id == branch_id,
            models.physical_count_sessions.c.status.in_(["counting", "submitted", "approved"]),
        )
    ).scalar_one_or_none()
    if active:
        raise BusinessError(
            "active_physical_count_exists", "Branch already has an active physical count"
        )
    requested_ids = [str(item_id) for item_id in payload.get("item_ids", []) if item_id]
    if len(requested_ids) != len(set(requested_ids)):
        raise BusinessError("duplicate_count_item", "Physical count item cannot be duplicated")
    item_query = sa.select(models.inventory_items).where(
        models.inventory_items.c.organization_id == ORGANIZATION_ID,
        models.inventory_items.c.status == "active",
    )
    if requested_ids:
        item_query = item_query.where(models.inventory_items.c.id.in_(requested_ids))
    items = [
        dict(row)
        for row in session.execute(item_query.order_by(models.inventory_items.c.name)).mappings()
    ]
    if not items or (requested_ids and {item["id"] for item in items} != set(requested_ids)):
        raise BusinessError(
            "physical_count_items_not_found", "Active physical count items were not found"
        )
    warehouse_id = _branch_warehouse_id(session, branch_id)
    now = _now()
    count_id = _id()
    branch_code = session.execute(
        sa.select(models.branches.c.code).where(
            models.branches.c.id == branch_id,
            models.branches.c.organization_id == ORGANIZATION_ID,
            models.branches.c.status == "active",
        )
    ).scalar_one_or_none()
    if not branch_code:
        raise BusinessError("count_branch_not_found", "Active count branch was not found")
    count = {
        "id": count_id,
        "organization_id": ORGANIZATION_ID,
        "branch_id": branch_id,
        "warehouse_id": warehouse_id,
        "folio": f"CNT-{branch_code}-{uuid4().hex[:8].upper()}",
        "status": "counting",
        "scope": "selected" if requested_ids else "all_active",
        "notes": str(payload.get("notes", "")).strip() or None,
        "cancellation_reason": None,
        "created_by": actor_id,
        "submitted_by": None,
        "approved_by": None,
        "closed_by": None,
        "cancelled_by": None,
        "approval_idempotency_key": None,
        "snapshot_at": now,
        "created_at": now,
        "submitted_at": None,
        "approved_at": None,
        "closed_at": None,
        "cancelled_at": None,
    }
    lines = []
    for item in items:
        theoretical = _physical_inventory_quantity(session, branch_id, warehouse_id, item["id"])
        average = session.execute(
            sa.select(models.inventory_cost_states.c.average_unit_cost).where(
                models.inventory_cost_states.c.branch_id == branch_id,
                models.inventory_cost_states.c.warehouse_id == warehouse_id,
                models.inventory_cost_states.c.item_id == item["id"],
            )
        ).scalar_one_or_none()
        unit_cost = _cost(average or 0)
        lines.append(
            {
                "id": _id(),
                "session_id": count_id,
                "item_id": item["id"],
                "unit_id": item["base_unit_id"],
                "theoretical_quantity": theoretical,
                "snapshot_unit_cost": unit_cost,
                "snapshot_value": _cost(theoretical * unit_cost),
                "counted_quantity": None,
                "snapshot_difference": None,
                "approval_ledger_quantity": None,
                "adjustment_quantity": None,
                "adjustment_unit_cost": None,
                "adjustment_cost": None,
                "adjustment_movement_id": None,
                "captured_by": None,
                "captured_at": None,
                "notes": None,
            }
        )
    session.execute(models.physical_count_sessions.insert().values(**count))
    session.execute(models.physical_count_lines.insert(), lines)
    _audit(
        session,
        "physical_count.created",
        "physical_count",
        count_id,
        {"folio": count["folio"], "scope": count["scope"], "line_count": len(lines)},
        branch_id,
        actor_user_id=actor_id,
    )
    session.commit()
    return get_physical_count_session(session, count_id)


def capture_physical_count_line(
    session: Session,
    count_id: str,
    line_id: str,
    quantity: Any,
    notes: str | None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    count = (
        session.execute(
            sa.select(models.physical_count_sessions).where(
                models.physical_count_sessions.c.id == count_id
            )
        )
        .mappings()
        .first()
    )
    if not count:
        raise BusinessError("physical_count_not_found", "Physical count was not found")
    require_permission(session, actor_id, "inventory.count", count["branch_id"])
    if count["status"] != "counting":
        raise BusinessError("physical_count_not_editable", "Only counting session can be captured")
    line = session.execute(
        sa.select(models.physical_count_lines.c.id).where(
            models.physical_count_lines.c.id == line_id,
            models.physical_count_lines.c.session_id == count_id,
        )
    ).scalar_one_or_none()
    if not line:
        raise BusinessError("physical_count_line_not_found", "Physical count line was not found")
    counted = _quantity(quantity)
    normalized_notes = str(notes or "").strip() or None
    if counted < 0:
        raise BusinessError("invalid_counted_quantity", "Counted quantity cannot be negative")
    if normalized_notes and len(normalized_notes) > 600:
        raise BusinessError("invalid_count_notes", "Count line notes exceed 600 characters")
    now = _now()
    session.execute(
        sa.update(models.physical_count_lines)
        .where(models.physical_count_lines.c.id == line_id)
        .values(
            counted_quantity=counted,
            captured_by=actor_id,
            captured_at=now,
            notes=normalized_notes,
        )
    )
    _audit(
        session,
        "physical_count.line_captured",
        "physical_count",
        count_id,
        {"line_id": line_id, "counted_quantity": str(counted)},
        count["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_physical_count_session(session, count_id)


def submit_physical_count_session(
    session: Session,
    count_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    count = (
        session.execute(
            sa.select(models.physical_count_sessions).where(
                models.physical_count_sessions.c.id == count_id
            )
        )
        .mappings()
        .first()
    )
    if not count:
        raise BusinessError("physical_count_not_found", "Physical count was not found")
    require_permission(session, actor_id, "inventory.count", count["branch_id"])
    if count["status"] != "counting":
        raise BusinessError(
            "physical_count_not_submittable", "Only counting session can be submitted"
        )
    lines = [
        dict(row)
        for row in session.execute(
            sa.select(models.physical_count_lines).where(
                models.physical_count_lines.c.session_id == count_id
            )
        ).mappings()
    ]
    if any(line["counted_quantity"] is None for line in lines):
        raise BusinessError(
            "physical_count_incomplete", "Every physical count line must be captured"
        )
    for line in lines:
        difference = _quantity(
            Decimal(str(line["counted_quantity"])) - Decimal(str(line["theoretical_quantity"]))
        )
        session.execute(
            sa.update(models.physical_count_lines)
            .where(models.physical_count_lines.c.id == line["id"])
            .values(snapshot_difference=difference)
        )
    now = _now()
    session.execute(
        sa.update(models.physical_count_sessions)
        .where(models.physical_count_sessions.c.id == count_id)
        .values(status="submitted", submitted_by=actor_id, submitted_at=now)
    )
    _audit(
        session,
        "physical_count.submitted",
        "physical_count",
        count_id,
        {"line_count": len(lines)},
        count["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_physical_count_session(session, count_id)


def approve_physical_count_session(
    session: Session,
    count_id: str,
    idempotency_key: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    key = idempotency_key.strip()
    if not key:
        raise BusinessError(
            "idempotency_key_required", "Physical count approval requires idempotency key"
        )
    count = (
        session.execute(
            sa.select(models.physical_count_sessions).where(
                models.physical_count_sessions.c.id == count_id
            )
        )
        .mappings()
        .first()
    )
    if not count:
        raise BusinessError("physical_count_not_found", "Physical count was not found")
    require_permission(session, actor_id, "inventory.count", count["branch_id"])
    if count["status"] in {"approved", "closed"}:
        if count["approval_idempotency_key"] == key:
            return get_physical_count_session(session, count_id)
        raise BusinessError(
            "physical_count_already_approved", "Physical count was already approved"
        )
    if count["status"] != "submitted":
        raise BusinessError(
            "physical_count_not_approvable", "Only submitted physical count can be approved"
        )
    lines = [
        dict(row)
        for row in session.execute(
            sa.select(models.physical_count_lines).where(
                models.physical_count_lines.c.session_id == count_id
            )
        ).mappings()
    ]
    resolutions = []
    for line in lines:
        ledger_quantity = _physical_inventory_quantity(
            session, count["branch_id"], count["warehouse_id"], line["item_id"]
        )
        adjustment = _quantity(Decimal(str(line["counted_quantity"])) - ledger_quantity)
        average = session.execute(
            sa.select(models.inventory_cost_states.c.average_unit_cost).where(
                models.inventory_cost_states.c.branch_id == count["branch_id"],
                models.inventory_cost_states.c.warehouse_id == count["warehouse_id"],
                models.inventory_cost_states.c.item_id == line["item_id"],
            )
        ).scalar_one_or_none()
        unit_cost = _cost(average or line["snapshot_unit_cost"] or 0)
        resolutions.append(
            (line, ledger_quantity, adjustment, unit_cost, _cost(adjustment * unit_cost))
        )
    now = _now()
    for index, (line, ledger_quantity, adjustment, unit_cost, adjustment_cost) in enumerate(
        resolutions
    ):
        movement_id = None
        if adjustment != 0:
            movement_id = _id()
            session.execute(
                models.inventory_movements.insert().values(
                    id=movement_id,
                    organization_id=ORGANIZATION_ID,
                    branch_id=count["branch_id"],
                    warehouse_id=count["warehouse_id"],
                    item_id=line["item_id"],
                    movement_type="COUNT_ADJUSTMENT",
                    quantity_delta=adjustment,
                    unit_id=line["unit_id"],
                    unit_cost=unit_cost,
                    total_cost=adjustment_cost,
                    effective_at=now,
                    actor_user_id=actor_id,
                    document_type="physical_count",
                    document_id=count_id,
                    reference=count["folio"],
                    reason="Conciliación de conteo físico",
                    notes=line["notes"],
                    idempotency_key=f"{key}:line:{index}",
                    status="confirmed",
                    reversal_of_id=None,
                    source_type="physical_count",
                    source_id=count_id,
                    created_at=now,
                )
            )
        _set_inventory_cost_quantity(
            session,
            count["branch_id"],
            count["warehouse_id"],
            line["item_id"],
            _quantity(line["counted_quantity"]),
            unit_cost,
            now,
        )
        session.execute(
            sa.update(models.physical_count_lines)
            .where(models.physical_count_lines.c.id == line["id"])
            .values(
                approval_ledger_quantity=ledger_quantity,
                adjustment_quantity=adjustment,
                adjustment_unit_cost=unit_cost,
                adjustment_cost=adjustment_cost,
                adjustment_movement_id=movement_id,
            )
        )
    session.execute(
        sa.update(models.physical_count_sessions)
        .where(models.physical_count_sessions.c.id == count_id)
        .values(
            status="approved",
            approved_by=actor_id,
            approval_idempotency_key=key,
            approved_at=now,
        )
    )
    _audit(
        session,
        "physical_count.approved",
        "physical_count",
        count_id,
        {"adjustment_count": sum(1 for _, _, adjustment, _, _ in resolutions if adjustment != 0)},
        count["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_physical_count_session(session, count_id)


def close_physical_count_session(
    session: Session,
    count_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    count = (
        session.execute(
            sa.select(models.physical_count_sessions).where(
                models.physical_count_sessions.c.id == count_id
            )
        )
        .mappings()
        .first()
    )
    if not count:
        raise BusinessError("physical_count_not_found", "Physical count was not found")
    require_permission(session, actor_id, "inventory.count", count["branch_id"])
    if count["status"] == "closed":
        return get_physical_count_session(session, count_id)
    if count["status"] != "approved":
        raise BusinessError(
            "physical_count_not_closable", "Only approved physical count can be closed"
        )
    now = _now()
    session.execute(
        sa.update(models.physical_count_sessions)
        .where(models.physical_count_sessions.c.id == count_id)
        .values(status="closed", closed_by=actor_id, closed_at=now)
    )
    _audit(
        session,
        "physical_count.closed",
        "physical_count",
        count_id,
        {"folio": count["folio"]},
        count["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_physical_count_session(session, count_id)


def cancel_physical_count_session(
    session: Session,
    count_id: str,
    reason: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    normalized_reason = reason.strip()
    count = (
        session.execute(
            sa.select(models.physical_count_sessions).where(
                models.physical_count_sessions.c.id == count_id
            )
        )
        .mappings()
        .first()
    )
    if not count:
        raise BusinessError("physical_count_not_found", "Physical count was not found")
    require_permission(session, actor_id, "inventory.count", count["branch_id"])
    if count["status"] != "counting":
        raise BusinessError(
            "physical_count_not_cancellable", "Only counting session can be cancelled"
        )
    if not normalized_reason:
        raise BusinessError(
            "physical_count_cancellation_reason_required", "Count cancellation reason is required"
        )
    now = _now()
    session.execute(
        sa.update(models.physical_count_sessions)
        .where(models.physical_count_sessions.c.id == count_id)
        .values(
            status="cancelled",
            cancellation_reason=normalized_reason,
            cancelled_by=actor_id,
            cancelled_at=now,
        )
    )
    _audit(
        session,
        "physical_count.cancelled",
        "physical_count",
        count_id,
        {"reason": normalized_reason},
        count["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_physical_count_session(session, count_id)


def get_physical_count_session(session: Session, count_id: str) -> dict[str, Any]:
    count = (
        session.execute(
            sa.select(
                models.physical_count_sessions,
                models.branches.c.name.label("branch_name"),
            )
            .select_from(
                models.physical_count_sessions.join(
                    models.branches,
                    models.physical_count_sessions.c.branch_id == models.branches.c.id,
                )
            )
            .where(models.physical_count_sessions.c.id == count_id)
        )
        .mappings()
        .first()
    )
    if not count:
        raise BusinessError("physical_count_not_found", "Physical count was not found")
    blind = count["status"] == "counting"
    lines = []
    for row in session.execute(
        sa.select(
            models.physical_count_lines,
            models.inventory_items.c.name.label("item_name"),
            models.inventory_items.c.sku.label("item_sku"),
            models.inventory_units.c.code.label("unit_code"),
        )
        .select_from(
            models.physical_count_lines.join(
                models.inventory_items,
                models.physical_count_lines.c.item_id == models.inventory_items.c.id,
            ).join(
                models.inventory_units,
                models.physical_count_lines.c.unit_id == models.inventory_units.c.id,
            )
        )
        .where(models.physical_count_lines.c.session_id == count_id)
        .order_by(models.inventory_items.c.name)
    ).mappings():
        line = dict(row)
        if blind:
            for field in (
                "theoretical_quantity",
                "snapshot_unit_cost",
                "snapshot_value",
                "snapshot_difference",
                "approval_ledger_quantity",
                "adjustment_quantity",
                "adjustment_unit_cost",
                "adjustment_cost",
            ):
                line.pop(field, None)
        lines.append(line)
    movement_ids = [
        line["adjustment_movement_id"] for line in lines if line.get("adjustment_movement_id")
    ]
    result = {**dict(count), "blind": blind, "lines": lines}
    result["movements"] = (
        [
            dict(row)
            for row in session.execute(
                sa.select(models.inventory_movements)
                .where(models.inventory_movements.c.id.in_(movement_ids))
                .order_by(models.inventory_movements.c.created_at)
            ).mappings()
        ]
        if movement_ids
        else []
    )
    return result


def list_physical_count_sessions(session: Session, branch_id: str | None) -> list[dict[str, Any]]:
    ids = session.execute(
        sa.select(models.physical_count_sessions.c.id)
        .where(models.physical_count_sessions.c.branch_id == branch_id)
        .order_by(models.physical_count_sessions.c.created_at.desc())
    ).scalars()
    return [get_physical_count_session(session, count_id) for count_id in ids]


def _physical_inventory_quantity(
    session: Session, branch_id: str, warehouse_id: str, item_id: str
) -> Decimal:
    value = session.execute(
        sa.select(
            sa.func.coalesce(sa.func.sum(models.inventory_movements.c.quantity_delta), 0)
        ).where(
            models.inventory_movements.c.branch_id == branch_id,
            models.inventory_movements.c.warehouse_id == warehouse_id,
            models.inventory_movements.c.item_id == item_id,
            models.inventory_movements.c.movement_type.notin_(
                ["SALE_RESERVATION", "RESERVATION_RELEASE"]
            ),
        )
    ).scalar_one()
    return _quantity(value)


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _quantity(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _cost(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _parse_document_date(value: Any, fallback: datetime) -> datetime:
    if value is None or value == "":
        return fallback
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _resolve_order_customer_snapshots(
    session: Session,
    customer_id: str | None,
    delivery_address_id: str | None,
    order_type: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not customer_id:
        if delivery_address_id:
            raise BusinessError("customer_required", "Address cannot be used without a customer")
        return None, None
    customer = (
        session.execute(
            sa.select(models.customers).where(
                models.customers.c.id == customer_id,
                models.customers.c.organization_id == ORGANIZATION_ID,
                models.customers.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not customer:
        raise BusinessError("customer_not_found", "Active customer was not found")
    phones = [
        dict(row)
        for row in session.execute(
            sa.select(models.customer_phones).where(
                models.customer_phones.c.customer_id == customer_id,
                models.customer_phones.c.status == "active",
            )
        ).mappings()
    ]
    customer_snapshot = _sanitize_for_json(
        {
            "id": customer["id"],
            "name": customer["name"],
            "email": customer["email"],
            "phones": phones,
        }
    )
    address_snapshot = None
    if delivery_address_id:
        address = (
            session.execute(
                sa.select(models.customer_addresses).where(
                    models.customer_addresses.c.id == delivery_address_id,
                    models.customer_addresses.c.customer_id == customer_id,
                    models.customer_addresses.c.status == "active",
                )
            )
            .mappings()
            .first()
        )
        if not address:
            raise BusinessError("customer_address_mismatch", "Address does not belong to customer")
        address_snapshot = _sanitize_for_json(dict(address))
    if order_type.lower() == "delivery" and not address_snapshot:
        raise BusinessError(
            "delivery_address_required", "Delivery order requires a customer address"
        )
    return customer_snapshot, address_snapshot


# ---------------------------------------------------------------------------
# Branch administration (BA-001)
# ---------------------------------------------------------------------------


def build_session_profile(
    session: Session, actor_id: str, branch_id: str | None = None
) -> dict[str, Any]:
    """Build the authenticated session profile from the database.

    Loads the actor's roles, permissions, scope and active branch from
    PostgreSQL. Does NOT rely on client-supplied role/permission state.
    Never exposes credentials.
    """
    actor = _actor_user_id(actor_id)
    user = (
        session.execute(
            sa.select(models.users).where(
                models.users.c.id == actor,
            )
        )
        .mappings()
        .first()
    )
    if not user:
        raise AuthorizationError("actor_required", "Actor authentication is required")
    if user["status"] != "active":
        raise AuthorizationError("user_inactive", "User is not active")

    org_id = str(user["organization_id"])
    role_rows = list(
        session.execute(
            sa.select(
                models.roles.c.id,
                models.roles.c.name,
                models.roles.c.scope,
                models.user_roles.c.branch_id,
            )
            .select_from(
                models.user_roles.join(
                    models.roles, models.user_roles.c.role_id == models.roles.c.id
                )
            )
            .where(
                models.user_roles.c.user_id == actor,
                models.roles.c.organization_id == org_id,
            )
            .order_by(models.roles.c.name, models.user_roles.c.branch_id)
        ).mappings()
    )
    if not role_rows:
        raise AuthorizationError("actor_not_authorized", "Actor is not authorized")

    roles_list = [
        {
            "id": row["id"],
            "name": row["name"],
            "scope": row["scope"],
            "branch_id": row["branch_id"],
        }
        for row in role_rows
    ]
    has_org_scope = any(row["scope"] == "organization" for row in role_rows)
    if has_org_scope:
        allowed_branch_ids = _active_organization_branch_ids(session, org_id)
    else:
        assigned_ids = {str(row["branch_id"]) for row in role_rows if row["branch_id"]}
        allowed_branch_ids = [
            branch for branch in _active_organization_branch_ids(session, org_id) if branch in assigned_ids
        ]
    if not allowed_branch_ids:
        raise AuthorizationError("actor_not_authorized", "Actor has no active branch scope")

    active_branch = _resolve_active_branch(
        session,
        requested_branch_id=branch_id,
        allowed_branch_ids=allowed_branch_ids,
        organization_id=org_id,
    )
    active_branch_id = str(active_branch["id"])
    effective_role_ids = {
        str(row["id"])
        for row in role_rows
        if row["scope"] == "organization" or row["branch_id"] == active_branch_id
    }

    permission_rows = session.execute(
        sa.select(models.permissions.c.code)
        .select_from(
            models.role_permissions.join(
                models.permissions,
                models.role_permissions.c.permission_id == models.permissions.c.id,
            )
        )
        .where(models.role_permissions.c.role_id.in_(effective_role_ids))
    ).mappings()
    permissions = sorted({row["code"] for row in permission_rows})
    assigned_branch_id = None if has_org_scope else active_branch_id

    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
            "status": user["status"],
        },
        "roles": [{**r, "branch_id": r["branch_id"] or None} for r in roles_list],
        "permissions": permissions,
        "scope": {
            "level": "organization" if has_org_scope else "branch",
            "assigned_branch_id": assigned_branch_id,
            "allowed_branch_ids": allowed_branch_ids,
        },
        "active_branch": active_branch,
    }


def create_pos_session_handoff(session: Session, actor_id: str) -> dict[str, Any]:
    profile = build_session_profile(session, actor_id)
    if "pos.operate" not in profile["permissions"]:
        raise AuthorizationError("permission_denied", "Actor does not have permission pos.operate")

    code = secrets.token_urlsafe(32)
    now = _now()
    handoff = {
        "id": _id(),
        "organization_id": ORGANIZATION_ID,
        "user_id": actor_id,
        "target_app": "pos",
        "code_hash": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "created_at": now,
        "expires_at": now + timedelta(seconds=POS_HANDOFF_TTL_SECONDS),
        "consumed_at": None,
    }
    session.execute(models.pos_session_handoffs.insert().values(**handoff))
    _audit(
        session,
        action="auth.pos_handoff_issued",
        entity_type="pos_session_handoff",
        entity_id=str(handoff["id"]),
        payload={"target_app": "pos", "expires_in_seconds": POS_HANDOFF_TTL_SECONDS},
        branch_id=profile["active_branch"]["id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return {
        "handoff_code": code,
        "target_app": "pos",
        "expires_in_seconds": POS_HANDOFF_TTL_SECONDS,
    }


def consume_pos_session_handoff(session: Session, code: str) -> dict[str, str]:
    normalized_code = str(code or "")
    if len(normalized_code) < 32 or len(normalized_code) > 256:
        raise BusinessError("pos_handoff_invalid", "POS session handoff is invalid")
    code_hash = hashlib.sha256(normalized_code.encode("utf-8")).hexdigest()
    handoff = (
        session.execute(
            sa.select(models.pos_session_handoffs)
            .where(models.pos_session_handoffs.c.code_hash == code_hash)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not handoff:
        raise BusinessError("pos_handoff_invalid", "POS session handoff is invalid")
    if handoff["consumed_at"] is not None:
        _audit_pos_handoff_rejection(session, handoff, "pos_handoff_used")
        raise BusinessError("pos_handoff_used", "POS session handoff was already used")

    now = _now()
    expires_at = handoff["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < now:
        _audit_pos_handoff_rejection(session, handoff, "pos_handoff_expired")
        raise BusinessError("pos_handoff_expired", "POS session handoff expired")

    try:
        profile = build_session_profile(session, str(handoff["user_id"]))
    except (AuthorizationError, BusinessError) as exc:
        _audit_pos_handoff_rejection(session, handoff, exc.code)
        raise
    if "pos.operate" not in profile["permissions"]:
        _audit_pos_handoff_rejection(session, handoff, "permission_denied")
        raise AuthorizationError("permission_denied", "Actor does not have permission pos.operate")
    consumed = session.execute(
        sa.update(models.pos_session_handoffs)
        .where(
            models.pos_session_handoffs.c.id == handoff["id"],
            models.pos_session_handoffs.c.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    if getattr(consumed, "rowcount", 0) != 1:
        session.rollback()
        _audit_pos_handoff_rejection(session, handoff, "pos_handoff_used")
        raise BusinessError("pos_handoff_used", "POS session handoff was already used")
    _audit(
        session,
        action="auth.pos_handoff_consumed",
        entity_type="pos_session_handoff",
        entity_id=str(handoff["id"]),
        payload={"target_app": "pos"},
        branch_id=profile["active_branch"]["id"],
        actor_user_id=str(handoff["user_id"]),
    )
    session.commit()
    return {
        "user_id": str(profile["user"]["id"]),
        "email": str(profile["user"]["email"]),
    }


def _audit_pos_handoff_rejection(session: Session, handoff: Any | None, reason_code: str) -> None:
    _audit(
        session,
        action="auth.pos_handoff_rejected",
        entity_type="pos_session_handoff",
        entity_id=str(handoff["id"]) if handoff is not None else "unresolved",
        payload={"target_app": "pos", "reason_code": reason_code},
        branch_id=None,
        actor_user_id=None,
    )
    session.commit()


def _resolve_active_branch(
    session: Session,
    requested_branch_id: str | None,
    allowed_branch_ids: list[str],
    organization_id: str | None = None,
) -> dict[str, Any]:
    """Resolve the active branch for a session profile."""
    if requested_branch_id and requested_branch_id not in allowed_branch_ids:
        raise AuthorizationError(
            "permission_denied", "Actor does not have access to the requested branch"
        )
    target_id = requested_branch_id or allowed_branch_ids[0]
    detail = _branch_detail(session, target_id, organization_id=organization_id)
    if not detail:
        raise AuthorizationError(
            "permission_denied", "Actor does not have access to the requested branch"
        )
    return detail


def _active_organization_branch_ids(session: Session, organization_id: str | None = None) -> list[str]:
    org_id = organization_id or ORGANIZATION_ID
    return [
        str(branch_id)
        for branch_id in session.execute(
            sa.select(models.branches.c.id)
            .where(
                models.branches.c.organization_id == org_id,
                models.branches.c.status == "active",
            )
            .order_by(models.branches.c.code)
        ).scalars()
    ]


def _branch_detail(session: Session, branch_id: str, organization_id: str | None = None) -> dict[str, Any] | None:
    org_id = organization_id
    if not org_id:
        org_id = session.execute(
            sa.select(models.branches.c.organization_id).where(models.branches.c.id == branch_id)
        ).scalar()
    if not org_id:
        org_id = ORGANIZATION_ID

    row = (
        session.execute(
            sa.select(
                models.branches.c.id,
                models.branches.c.name,
                models.branches.c.code,
                models.branches.c.timezone,
                models.branches.c.status,
                models.business_units.c.id.label("bu_id"),
                models.business_units.c.name.label("bu_name"),
                models.business_units.c.code.label("bu_code"),
                models.business_units.c.unit_type.label("bu_unit_type"),
                models.legal_entities.c.id.label("le_id"),
                models.legal_entities.c.name.label("le_name"),
                models.warehouses.c.id.label("wh_id"),
                models.warehouses.c.name.label("wh_name"),
            )
            .select_from(
                models.branches.join(
                    models.business_units,
                    models.branches.c.business_unit_id == models.business_units.c.id,
                )
                .join(
                    models.legal_entities,
                    models.branches.c.legal_entity_id == models.legal_entities.c.id,
                )
                .outerjoin(
                    models.warehouses,
                    models.warehouses.c.branch_id == models.branches.c.id,
                )
            )
            .where(
                models.branches.c.id == branch_id,
                models.branches.c.organization_id == org_id,
                models.branches.c.status == "active",
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "code": row["code"],
        "timezone": row["timezone"],
        "status": row["status"],
        "business_unit": {
            "id": row["bu_id"],
            "name": row["bu_name"],
            "code": row["bu_code"],
            "unit_type": row["bu_unit_type"],
        },
        "legal_entity": {"id": row["le_id"], "name": row["le_name"]},
        "warehouse": {"id": row["wh_id"], "name": row["wh_name"]} if row["wh_id"] else None,
    }


def get_branch_context(
    session: Session, actor_id: str, branch_id: str | None = None
) -> dict[str, Any]:
    """Return branch context (branch + business_unit + legal_entity + warehouse).

    A Supervisor is always fixed to their assigned branch; a corporate admin
    may select any active authorized branch.
    """
    authorized_branch = _branch_administration_target(
        session, actor_id, "branch.admin.access", branch_id
    )
    detail = _branch_detail(session, authorized_branch)
    if detail is None:
        raise AuthorizationError("permission_denied", "Branch is not authorized")
    return detail


def _branch_administration_target(
    session: Session,
    actor_id: str,
    permission_code: str,
    branch_id: str | None,
) -> str:
    authorized_branch = authorize_branch_scope(session, actor_id, permission_code, branch_id)
    if authorized_branch:
        return authorized_branch
    profile = build_session_profile(session, actor_id, branch_id)
    return str(profile["active_branch"]["id"])


def list_branch_staff(
    session: Session, actor_id: str, branch_id: str | None = None
) -> list[dict[str, Any]]:
    """List users assigned to the authorized branch. Read-only, no credentials."""
    authorized_branch = _branch_administration_target(
        session, actor_id, "branch.staff.read", branch_id
    )
    rows = session.execute(
        sa.select(
            models.users.c.id,
            models.users.c.email,
            models.users.c.display_name,
            models.users.c.status,
            models.roles.c.name.label("role_name"),
            models.roles.c.scope.label("role_scope"),
            models.user_roles.c.branch_id,
        )
        .select_from(
            models.user_roles.join(
                models.users, models.user_roles.c.user_id == models.users.c.id
            ).join(models.roles, models.user_roles.c.role_id == models.roles.c.id)
        )
        .where(
            models.user_roles.c.branch_id == authorized_branch,
            models.users.c.organization_id == ORGANIZATION_ID,
            models.roles.c.organization_id == ORGANIZATION_ID,
        )
        .order_by(models.users.c.display_name)
    ).mappings()
    by_user: dict[str, dict[str, Any]] = {}
    for row in rows:
        uid = row["id"]
        if uid not in by_user:
            by_user[uid] = {
                "id": uid,
                "email": row["email"],
                "display_name": row["display_name"],
                "status": row["status"],
                "roles": [],
            }
        by_user[uid]["roles"].append(
            {"name": row["role_name"], "scope": row["role_scope"], "branch_id": row["branch_id"]}
        )
    return list(by_user.values())


def list_branch_admin_catalog_products(
    session: Session, actor_id: str, branch_id: str | None = None
) -> list[dict[str, Any]]:
    """List central products with effective availability for the branch.

    Products without a price appear as ``sellable: false``. Absence of a local
    override means ``has_local_override: False`` (inherits central availability).
    """
    authorized_branch = _branch_administration_target(
        session, actor_id, "branch.admin.access", branch_id
    )

    rows = session.execute(
        sa.select(
            models.products.c.id,
            models.products.c.name,
            models.products.c.sku,
            models.products.c.status,
            models.products.c.station,
            models.products.c.catalog_scope,
            models.products.c.source_branch_id,
            models.product_categories.c.name.label("category_name"),
            models.price_versions.c.price_cents,
            models.branch_product_availability.c.is_available,
        )
        .select_from(
            models.products.join(
                models.product_categories,
                models.products.c.category_id == models.product_categories.c.id,
            )
            .outerjoin(
                models.price_versions,
                sa.and_(
                    models.price_versions.c.product_id == models.products.c.id,
                    models.price_versions.c.valid_to.is_(None),
                ),
            )
            .outerjoin(
                models.branch_product_availability,
                sa.and_(
                    models.branch_product_availability.c.product_id == models.products.c.id,
                    models.branch_product_availability.c.branch_id == authorized_branch,
                ),
            )
        )
        .where(
            models.products.c.organization_id == ORGANIZATION_ID,
            models.products.c.status != "archived",
        )
        .where(
            sa.or_(
                models.products.c.catalog_scope == "organization",
                models.products.c.source_branch_id == authorized_branch,
            )
        )
        .order_by(models.products.c.name)
    ).mappings()
    result = []
    for row in rows:
        has_override = row["is_available"] is not None
        central_active = row["status"] == "active"
        effective = central_active and (row["is_available"] if has_override else True)
        has_price = row["price_cents"] is not None and row["price_cents"] > 0
        result.append(
            {
                "id": row["id"],
                "name": row["name"],
                "sku": row["sku"],
                "status": row["status"],
                "station": row["station"],
                "category": row["category_name"],
                "category_name": row["category_name"],
                "price_cents": row["price_cents"],
                "sellable": central_active and effective and has_price,
                "effective_availability": effective,
                "has_local_override": has_override,
                "availability_source": "branch_override" if has_override else "central",
                "catalog_scope": row.get("catalog_scope", "organization"),
                "source_branch_id": row.get("source_branch_id"),
            }
        )
    return result


def set_branch_product_availability(
    session: Session,
    actor_id: str,
    product_id: str,
    action: str,
    branch_id: str | None = None,
) -> dict[str, Any]:
    """Set per-branch product availability (available / unavailable / inherit).

    ``inherit`` removes the local override so the central availability applies.
    Only modifies ``branch_product_availability``; never touches products,
    categories or price_versions. Records an audit event with old/new values.
    """
    authorized_branch = _branch_administration_target(
        session, actor_id, "catalog.branch.manage", branch_id
    )
    if action not in ("available", "unavailable", "inherit"):
        raise BusinessError(
            "invalid_availability_action",
            "Action must be available, unavailable or inherit",
        )

    product = (
        session.execute(
            sa.select(
                models.products.c.id,
                models.products.c.name,
                models.products.c.status,
            ).where(
                models.products.c.id == product_id,
                models.products.c.organization_id == ORGANIZATION_ID,
            )
        )
        .mappings()
        .first()
    )
    if not product:
        raise NotFoundError("product_not_found", "Product not found")

    existing = (
        session.execute(
            sa.select(models.branch_product_availability).where(
                models.branch_product_availability.c.branch_id == authorized_branch,
                models.branch_product_availability.c.product_id == product_id,
            )
        )
        .mappings()
        .first()
    )
    previous_value = existing["is_available"] if existing else None

    now = _now()
    if action == "inherit":
        if existing:
            session.execute(
                models.branch_product_availability.delete().where(
                    models.branch_product_availability.c.branch_id == authorized_branch,
                    models.branch_product_availability.c.product_id == product_id,
                )
            )
        new_value = None
    else:
        new_value = action == "available"
        if existing:
            session.execute(
                models.branch_product_availability.update()
                .where(
                    models.branch_product_availability.c.branch_id == authorized_branch,
                    models.branch_product_availability.c.product_id == product_id,
                )
                .values(is_available=new_value, updated_at=now)
            )
        else:
            session.execute(
                models.branch_product_availability.insert().values(
                    branch_id=authorized_branch,
                    product_id=product_id,
                    is_available=new_value,
                    updated_at=now,
                )
            )

    _audit(
        session,
        action="branch_product_availability.updated",
        entity_type="product",
        entity_id=product_id,
        payload={
            "branch_id": authorized_branch,
            "product_name": product["name"],
            "previous": previous_value,
            "new": new_value,
            "requested_action": action,
        },
        branch_id=authorized_branch,
        actor_user_id=_actor_user_id(actor_id),
    )
    session.commit()
    central_active = product["status"] == "active"
    effective_availability = central_active and (new_value if new_value is not None else True)
    return {
        "product_id": product_id,
        "branch_id": authorized_branch,
        "effective_availability": effective_availability,
        "has_local_override": action != "inherit",
        "availability_source": "central" if action == "inherit" else "branch_override",
        "previous": previous_value,
    }


def get_public_catalog(session: Session, branch_id: str | None = None) -> dict[str, Any]:
    from restaurant_os.platform_data import _project_pos_catalog

    active_branch_id = branch_id
    if active_branch_id is None:
        # Legacy catalog keeps its historical default selection while the key route is exact.
        active_branch_id = (
            session.scalar(
                sa.select(models.cash_shifts.c.branch_id)
                .where(
                    models.cash_shifts.c.organization_id == ORGANIZATION_ID,
                    sa.func.upper(models.cash_shifts.c.status) == "OPEN",
                )
                .order_by(models.cash_shifts.c.opened_at.desc())
                .limit(1)
            )
            or session.scalar(
                sa.select(models.cash_shifts.c.branch_id)
                .where(models.cash_shifts.c.organization_id == ORGANIZATION_ID)
                .order_by(models.cash_shifts.c.opened_at.desc())
                .limit(1)
            )
            or session.scalar(
                sa.select(models.branches.c.id)
                .where(models.branches.c.organization_id == ORGANIZATION_ID)
                .order_by(models.branches.c.created_at.desc())
                .limit(1)
            )
            or BRANCH_ID
        )

    branch_name = (
        session.scalar(
            sa.select(models.branches.c.name).where(models.branches.c.id == active_branch_id)
        )
        or "Kiwi Restaurante"
    )

    categories, products = _project_pos_catalog(session, active_branch_id)

    items = []
    for p in products:
        price_cents = p.get("price_cents")
        if not isinstance(price_cents, int):
            continue
        modifier_groups = []
        for group in list_product_modifiers(session, str(p["id"]), active_branch_id):
            options = [
                {
                    "id": str(option["id"]),
                    "name": str(option["name"]),
                    "price_delta_cents": int(option.get("price_delta_cents") or 0),
                    "selection_kind": str(option.get("variation_kind") or "modifier"),
                }
                for option in group.get("options", [])
                if option.get("status") == "active"
            ]
            if options:
                modifier_groups.append(
                    {
                        "id": str(group["id"]),
                        "name": str(group["name"]),
                        "is_required": bool(group.get("is_required")),
                        "minimum_selections": int(group.get("minimum_selections") or 0),
                        "maximum_selections": int(group.get("maximum_selections") or 0),
                        "options": options,
                    }
                )
        items.append(
            {
                "id": p["id"],
                "name": p["name"],
                "sku": p.get("sku") or p["id"],
                "category_name": p.get("category_name") or "General",
                "category_id": p.get("category_id"),
                "price_cents": price_cents,
                "description": p.get("description") or "",
                "image_url": p.get("image_url") or "",
                "station": p.get("station") or "barra",
                "is_available": p.get("is_available", True),
                "modifier_groups": modifier_groups,
            }
        )

    return {
        "branch_id": active_branch_id,
        "branch_name": branch_name,
        "categories": categories,
        "items": items,
    }


def _public_intent_response(intent: dict[str, Any]) -> dict[str, Any]:
    return {
        "public_reference": intent["public_reference"],
        "status": intent["status"],
        "version": int(intent["version"]),
        "total_cents": int(intent["total_cents"]),
    }


def _recover_public_order_command(
    session: Session,
    organization_id: str,
    command_type: str,
    idempotency_key: str,
    request_hash: str,
) -> tuple[dict[str, Any], bool] | None:
    """Recover the committed winner after a unique-command or CAS race."""
    session.rollback()
    prior = (
        session.execute(
            sa.select(models.public_order_intent_commands).where(
                models.public_order_intent_commands.c.organization_id == organization_id,
                models.public_order_intent_commands.c.command_type == command_type,
                models.public_order_intent_commands.c.idempotency_key == idempotency_key,
            )
        )
        .mappings()
        .first()
    )
    if not prior:
        return None
    if prior["request_hash"] != request_hash:
        raise BusinessError("idempotency_conflict", "Idempotency key was used with another request")
    return dict(prior["result"]), False


def create_public_order_intent(
    session: Session,
    public_key: str,
    payload: dict[str, Any],
    idempotency_key: str,
) -> tuple[dict[str, Any], bool]:
    """Persist a public request only; it must never create cash or production state."""
    key = str(idempotency_key or "").strip()
    if not 12 <= len(key) <= 160:
        raise BusinessError("public_order_schema_invalid", "Idempotency-Key is invalid")
    configured = (
        session.execute(
            sa.select(models.public_order_keys, models.branches.c.organization_id)
            .join(models.branches, models.branches.c.id == models.public_order_keys.c.branch_id)
            .where(
                models.public_order_keys.c.public_key == public_key,
                models.public_order_keys.c.status == "active",
                models.branches.c.status == "active",
                models.public_order_keys.c.organization_id == models.branches.c.organization_id,
            )
        )
        .mappings()
        .first()
    )
    if not configured:
        raise BusinessError("public_order_unavailable", "Public ordering is unavailable")
    branch_id = str(configured["branch_id"])
    organization_id = str(configured["organization_id"])
    raw_phone = re.sub(r"[^\d+]", "", str(payload.get("customer_phone") or "").strip())
    if not raw_phone.startswith("+"):
        raw_phone = raw_phone.lstrip("0")
    normalized = {
        "customer_name": str(payload["customer_name"]).strip(),
        "customer_phone": raw_phone,
        "order_type": str(payload["order_type"]).strip(),
        "lines": payload["lines"],
        "order_notes": str(payload.get("order_notes") or "").strip() or None,
        "delivery_address": payload.get("delivery_address"),
    }
    digest = hashlib.sha256(
        json.dumps(
            {"contract": 1, "branch": branch_id, "payload": normalized},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    prior = (
        session.execute(
            sa.select(models.public_order_intent_commands).where(
                models.public_order_intent_commands.c.organization_id == organization_id,
                models.public_order_intent_commands.c.command_type == "create",
                models.public_order_intent_commands.c.idempotency_key == key,
            )
        )
        .mappings()
        .first()
    )
    if prior:
        if prior["request_hash"] != digest:
            raise BusinessError(
                "idempotency_conflict", "Idempotency key was used with another request"
            )
        return dict(prior["result"]), False
    if normalized["order_type"] not in {"dine-in", "takeout", "delivery"}:
        raise BusinessError("public_order_schema_invalid", "Order type is invalid")
    if not normalized["customer_name"] or len(normalized["customer_name"]) > 160:
        raise BusinessError("public_order_schema_invalid", "Customer name is invalid")
    if not re.fullmatch(r"\+?[1-9]\d{7,14}", normalized["customer_phone"]):
        raise BusinessError("public_order_schema_invalid", "Customer phone is invalid")
    if not isinstance(normalized["lines"], list) or not 1 <= len(normalized["lines"]) <= 50:
        raise BusinessError("public_order_schema_invalid", "Order lines are invalid")
    now, intent_id = _now(), _id()
    total_cents = 0
    snapshots: list[dict[str, Any]] = []
    for item in normalized["lines"]:
        if not isinstance(item, dict) or set(item) - {
            "product_id",
            "quantity",
            "notes",
            "modifiers",
            "comment_preset_ids",
            "ingredient_extras",
        }:
            raise BusinessError("public_order_schema_invalid", "Order line is invalid")
        if not isinstance(item.get("quantity"), int) or not 1 <= item["quantity"] <= 99:
            raise BusinessError("public_order_schema_invalid", "Order quantity is invalid")
        line_id = _id()
        priced = _price_order_line(session, item, branch_id, intent_id, line_id, now)
        snapshot = dict(priced["snapshot"])
        modifier_total = int(snapshot.pop("modifier_total_cents"))
        snapshot = _sanitize_for_json(snapshot)
        total_cents += int(priced["line_total_cents"])
        snapshots.append(
            {
                "id": line_id,
                "intent_id": intent_id,
                "product_id": priced["product"]["id"],
                "product_name": priced["product"]["name"],
                "quantity": int(priced["quantity"]),
                "unit_price_cents": int(priced["product"]["price_cents"]),
                "line_total_cents": int(priced["line_total_cents"]),
                "station": priced["product"]["station"],
                "selected_modifiers": snapshot["modifiers"],
                "modifier_total_cents": modifier_total,
                "line_notes": item.get("notes"),
                "family_id_snapshot": priced["product"]["category_id"],
                "family_name_snapshot": priced["product"]["family_name"],
                "consumption_snapshot": snapshot,
                "created_at": now,
            }
        )
    result = {
        "public_reference": f"PI-{intent_id.replace('-', '').upper()}",
        "status": "PENDING_REVIEW",
        "version": 1,
        "total_cents": total_cents,
    }
    session.execute(
        models.public_order_intents.insert().values(
            id=intent_id,
            organization_id=organization_id,
            branch_id=branch_id,
            public_key=public_key,
            public_reference=result["public_reference"],
            correlation_id=_id(),
            status="PENDING_REVIEW",
            customer_snapshot={
                "name": normalized["customer_name"],
                "phone": normalized["customer_phone"],
            },
            delivery_address_snapshot=normalized["delivery_address"],
            order_type=normalized["order_type"],
            order_notes=normalized["order_notes"],
            total_cents=total_cents,
            currency="MXN",
            version=1,
            created_at=now,
        )
    )
    for row in snapshots:
        session.execute(models.public_order_intent_lines.insert().values(**row))
    try:
        session.execute(
            models.public_order_intent_commands.insert().values(
                id=_id(),
                organization_id=organization_id,
                intent_id=intent_id,
                command_type="create",
                idempotency_key=key,
                request_hash=digest,
                result=result,
                actor_user_id=None,
                created_at=now,
            )
        )
    except IntegrityError:
        recovered = _recover_public_order_command(session, organization_id, "create", key, digest)
        if recovered:
            return recovered
        raise
    _audit(
        session,
        "public_order_intent.captured",
        "public_order_intent",
        intent_id,
        {"status": "PENDING_REVIEW", "line_count": len(snapshots), "total_cents": total_cents},
        branch_id,
        organization_id,
        None,
    )
    session.commit()
    return result, True


def get_public_order_intent(session: Session, public_reference: str) -> dict[str, Any]:
    intent = (
        session.execute(
            sa.select(models.public_order_intents).where(
                models.public_order_intents.c.public_reference == public_reference
            )
        )
        .mappings()
        .first()
    )
    if not intent:
        raise NotFoundError("public_order_not_found", "Public order intent was not found")
    return _public_intent_response(dict(intent))


def _revalidate_public_intent_operationally(session: Session, intent: dict[str, Any]) -> None:
    """Fail closed before acceptance without repricing the captured contract."""
    key_is_active = session.execute(
        sa.select(models.public_order_keys.c.public_key)
        .join(models.branches, models.branches.c.id == models.public_order_keys.c.branch_id)
        .where(
            models.public_order_keys.c.public_key == intent["public_key"],
            models.public_order_keys.c.status == "active",
            models.public_order_keys.c.branch_id == intent["branch_id"],
            models.public_order_keys.c.organization_id == intent["organization_id"],
            models.branches.c.status == "active",
        )
    ).scalar_one_or_none()
    if not key_is_active:
        raise BusinessError(
            "public_order_transition_invalid", "Public order intent is no longer operational"
        )
    product_ids = session.scalars(
        sa.select(models.public_order_intent_lines.c.product_id).where(
            models.public_order_intent_lines.c.intent_id == intent["id"]
        )
    ).all()
    for product_id in product_ids:
        if not _get_available_product(session, str(product_id), str(intent["branch_id"])):
            raise BusinessError(
                "public_order_transition_invalid", "Public order intent is no longer operational"
            )


class OrderAcceptanceService:
    """Shared domain primitives for every channel that activates an order."""

    @staticmethod
    def ensure_production_task(
        session: Session,
        *,
        organization_id: str,
        branch_id: str,
        order_id: str,
        line: dict[str, Any],
        created_at: datetime,
    ) -> None:
        existing = session.execute(
            sa.select(models.production_tasks.c.id).where(
                models.production_tasks.c.order_id == order_id,
                models.production_tasks.c.order_line_id == line["id"],
            )
        ).scalar_one_or_none()
        if existing:
            return
        session.execute(
            models.production_tasks.insert().values(
                id=_id(),
                organization_id=organization_id,
                branch_id=branch_id,
                order_id=order_id,
                order_line_id=line["id"],
                station=line["station"],
                status="PENDING",
                product_name=line["product_name"],
                quantity=int(line["quantity"]),
                created_at=created_at,
                started_at=None,
                completed_at=None,
            )
        )

    @staticmethod
    def reserve_captured_snapshot(
        session: Session,
        *,
        order: dict[str, Any],
        line: dict[str, Any],
        snapshot: dict[str, Any],
        created_at: datetime,
        source_type: str,
    ) -> None:
        existing = session.execute(
            sa.select(models.order_line_consumption_snapshots.c.order_line_id).where(
                models.order_line_consumption_snapshots.c.order_line_id == line["id"]
            )
        ).scalar_one_or_none()
        if existing:
            return
        session.execute(
            models.order_line_consumption_snapshots.insert().values(
                order_line_id=line["id"],
                order_id=order["id"],
                recipe_id=snapshot["recipe_id"],
                recipe_version=snapshot["recipe_version"],
                branch_id=order["branch_id"],
                components=snapshot["components"],
                modifiers=snapshot.get("modifiers", []),
                total_theoretical_cost=Decimal(str(snapshot["total_theoretical_cost"])),
                created_at=created_at,
            )
        )
        _record_calculated_consumption_movements(
            session,
            components=snapshot["components"],
            product_name=line["product_name"],
            movement_type="SALE_RESERVATION",
            sign=-1,
            reason=f"Reserva por pedido {order['folio']}",
            source_type=source_type,
            source_id=order["id"],
            created_at=created_at,
            branch_id=order["branch_id"],
        )


def accept_public_order_intent(
    session: Session,
    intent_id: str,
    expected_version: int,
    idempotency_key: str,
    actor_user_id: str,
) -> tuple[dict[str, Any], bool]:
    key = str(idempotency_key or "").strip()
    if not 12 <= len(key) <= 160:
        raise BusinessError("public_order_schema_invalid", "Idempotency-Key is invalid")
    intent = (
        session.execute(
            sa.select(models.public_order_intents).where(
                models.public_order_intents.c.id == intent_id
            )
        )
        .mappings()
        .first()
    )
    if not intent:
        raise NotFoundError("public_order_not_found", "Public order intent was not found")
    require_permission(session, actor_user_id, "orders.create", intent["branch_id"])
    digest = hashlib.sha256(f"{intent_id}:{expected_version}".encode()).hexdigest()
    prior = (
        session.execute(
            sa.select(models.public_order_intent_commands).where(
                models.public_order_intent_commands.c.organization_id == intent["organization_id"],
                models.public_order_intent_commands.c.command_type == "accept",
                models.public_order_intent_commands.c.idempotency_key == key,
            )
        )
        .mappings()
        .first()
    )
    if prior:
        if prior["request_hash"] != digest:
            raise BusinessError(
                "idempotency_conflict", "Idempotency key was used with another request"
            )
        return dict(prior["result"]), False
    if intent["status"] != "PENDING_REVIEW" or int(intent["version"]) != expected_version:
        raise BusinessError(
            "public_order_transition_invalid", "Public order intent cannot be accepted"
        )
    _revalidate_public_intent_operationally(session, dict(intent))
    now, order_id = _now(), _id()
    folio = _next_unique_folio(session, intent["branch_id"])
    changed = cast(
        Any,
        session.execute(
            models.public_order_intents.update()
            .where(
                models.public_order_intents.c.id == intent_id,
                models.public_order_intents.c.status == "PENDING_REVIEW",
                models.public_order_intents.c.version == expected_version,
            )
            .values(
                status="ACCEPTED",
                accepted_at=now,
                decided_at=now,
                decided_by_user_id=actor_user_id,
                version=expected_version + 1,
            )
        ),
    )
    if changed.rowcount != 1:
        recovered = _recover_public_order_command(
            session, str(intent["organization_id"]), "accept", key, digest
        )
        if recovered:
            return recovered
        raise BusinessError("public_order_transition_invalid", "Public order intent changed")
    order = {
        "id": order_id,
        "organization_id": intent["organization_id"],
        "branch_id": intent["branch_id"],
        "cash_shift_id": None,
        "public_order_intent_id": intent_id,
        "public_order_intent_status": "ACCEPTED",
        "customer_id": None,
        "customer_snapshot": intent["customer_snapshot"],
        "delivery_address_snapshot": intent["delivery_address_snapshot"],
        "folio": folio,
        "channel": "PUBLIC_INTENT",
        "status": "ACCEPTED",
        "total_cents": int(intent["total_cents"]),
        "currency": "MXN",
        "owner_name": (intent["customer_snapshot"] or {}).get("name"),
        "order_type": intent["order_type"],
        "payment_method_intent": None,
        "version": 1,
        "created_at": now,
        "accepted_at": now,
    }
    session.execute(models.orders.insert().values(**order))
    session.execute(
        models.public_order_intents.update()
        .where(
            models.public_order_intents.c.id == intent_id,
            models.public_order_intents.c.accepted_order_id.is_(None),
        )
        .values(accepted_order_id=order_id)
    )
    lines = (
        session.execute(
            sa.select(models.public_order_intent_lines).where(
                models.public_order_intent_lines.c.intent_id == intent_id
            )
        )
        .mappings()
        .all()
    )
    for source in lines:
        line_id = _id()
        session.execute(
            models.order_lines.insert().values(
                id=line_id,
                order_id=order_id,
                product_id=source["product_id"],
                product_name=source["product_name"],
                quantity=source["quantity"],
                unit_price_cents=source["unit_price_cents"],
                line_total_cents=source["line_total_cents"],
                station=source["station"],
                selected_modifiers=source["selected_modifiers"],
                modifier_total_cents=source["modifier_total_cents"],
                line_notes=source["line_notes"],
                status="active",
                revision=1,
                updated_at=now,
                removed_at=None,
                family_id_snapshot=source["family_id_snapshot"],
                family_name_snapshot=source["family_name_snapshot"],
                family_snapshot_source="captured",
                created_at=now,
            )
        )
        snapshot = source["consumption_snapshot"]
        materialized_line = {**dict(source), "id": line_id}
        OrderAcceptanceService.ensure_production_task(
            session,
            organization_id=str(intent["organization_id"]),
            branch_id=str(intent["branch_id"]),
            order_id=order_id,
            line=materialized_line,
            created_at=now,
        )
        OrderAcceptanceService.reserve_captured_snapshot(
            session,
            order=order,
            line=materialized_line,
            snapshot=dict(snapshot),
            created_at=now,
            source_type="order",
        )
    session.execute(
        models.order_events.insert().values(
            id=_id(),
            order_id=order_id,
            event_type="ORDER_ACCEPTED",
            payload={
                "folio": folio,
                "total_cents": int(intent["total_cents"]),
                "lines_count": len(lines),
                "source": "public_order_intent",
            },
            created_at=now,
        )
    )
    _audit(
        session,
        "order.accepted",
        "order",
        order_id,
        {"folio": folio, "total_cents": int(intent["total_cents"]), "lines_count": len(lines)},
        intent["branch_id"],
        intent["organization_id"],
        actor_user_id,
    )
    session.execute(
        models.order_outbox_events.insert().values(
            id=_id(),
            organization_id=intent["organization_id"],
            branch_id=intent["branch_id"],
            order_id=order_id,
            event_type="order.accepted",
            payload={"source": "public_order_intent"},
            created_at=now,
            published_at=None,
        )
    )
    result = {
        "id": order_id,
        "folio": folio,
        "cash_shift_id": None,
        "status": "ACCEPTED",
        "total_cents": int(intent["total_cents"]),
    }
    try:
        session.execute(
            models.public_order_intent_commands.insert().values(
                id=_id(),
                organization_id=intent["organization_id"],
                intent_id=intent_id,
                command_type="accept",
                idempotency_key=key,
                request_hash=digest,
                result=result,
                actor_user_id=actor_user_id,
                created_at=now,
            )
        )
    except IntegrityError:
        recovered = _recover_public_order_command(
            session, str(intent["organization_id"]), "accept", key, digest
        )
        if recovered:
            return recovered
        raise
    _audit(
        session,
        "public_order_intent.accepted",
        "public_order_intent",
        intent_id,
        {"order_id": order_id, "status": "ACCEPTED"},
        intent["branch_id"],
        intent["organization_id"],
        actor_user_id,
    )
    session.commit()
    return result, True


def reject_public_order_intent(
    session: Session,
    intent_id: str,
    expected_version: int,
    reason: str,
    idempotency_key: str,
    actor_user_id: str,
) -> tuple[dict[str, Any], bool]:
    """Reject a pending intent without creating any operational order effects."""
    key = str(idempotency_key or "").strip()
    normalized_reason = str(reason or "").strip()
    if not 12 <= len(key) <= 160 or not 10 <= len(normalized_reason) <= 500:
        raise BusinessError("public_order_schema_invalid", "Public order rejection is invalid")
    intent = (
        session.execute(
            sa.select(models.public_order_intents).where(
                models.public_order_intents.c.id == intent_id
            )
        )
        .mappings()
        .first()
    )
    if not intent:
        raise NotFoundError("public_order_not_found", "Public order intent was not found")

    # Authorization precedes replay recovery so revoked actors cannot replay a prior decision.
    require_permission(session, actor_user_id, "orders.create", intent["branch_id"])
    digest = hashlib.sha256(
        json.dumps(
            {
                "contract": 1,
                "intent_id": intent_id,
                "expected_version": expected_version,
                "reason": normalized_reason,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    prior = (
        session.execute(
            sa.select(models.public_order_intent_commands).where(
                models.public_order_intent_commands.c.organization_id == intent["organization_id"],
                models.public_order_intent_commands.c.command_type == "reject",
                models.public_order_intent_commands.c.idempotency_key == key,
            )
        )
        .mappings()
        .first()
    )
    if prior:
        if prior["request_hash"] != digest:
            raise BusinessError(
                "idempotency_conflict", "Idempotency key was used with another request"
            )
        return dict(prior["result"]), False
    if intent["status"] != "PENDING_REVIEW" or int(intent["version"]) != expected_version:
        raise BusinessError(
            "public_order_transition_invalid", "Public order intent cannot be rejected"
        )

    now = _now()
    changed = cast(
        Any,
        session.execute(
            models.public_order_intents.update()
            .where(
                models.public_order_intents.c.id == intent_id,
                models.public_order_intents.c.status == "PENDING_REVIEW",
                models.public_order_intents.c.version == expected_version,
            )
            .values(
                status="REJECTED",
                version=expected_version + 1,
                decided_at=now,
                decision_reason=normalized_reason,
                decided_by_user_id=actor_user_id,
            )
        ),
    )
    if changed.rowcount != 1:
        recovered = _recover_public_order_command(
            session, str(intent["organization_id"]), "reject", key, digest
        )
        if recovered:
            return recovered
        raise BusinessError("public_order_transition_invalid", "Public order intent changed")

    result = {
        "public_reference": str(intent["public_reference"]),
        "status": "REJECTED",
        "version": expected_version + 1,
    }
    try:
        session.execute(
            models.public_order_intent_commands.insert().values(
                id=_id(),
                organization_id=intent["organization_id"],
                intent_id=intent_id,
                command_type="reject",
                idempotency_key=key,
                request_hash=digest,
                result=result,
                actor_user_id=actor_user_id,
                created_at=now,
            )
        )
    except IntegrityError:
        recovered = _recover_public_order_command(
            session, str(intent["organization_id"]), "reject", key, digest
        )
        if recovered:
            return recovered
        raise
    _audit(
        session,
        "public_order_intent.rejected",
        "public_order_intent",
        intent_id,
        {"status": "REJECTED", "reason": normalized_reason},
        intent["branch_id"],
        intent["organization_id"],
        actor_user_id,
    )
    session.commit()
    return result, True


def accept_pending_order(
    session: Session,
    order_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    actor_id = _actor_user_id(actor_user_id)
    order = (
        session.execute(sa.select(models.orders).where(models.orders.c.id == order_id))
        .mappings()
        .first()
    )
    if not order:
        raise NotFoundError("order_not_found", "Order was not found")
    require_permission(session, actor_id, "orders.create", order["branch_id"])
    if order["status"] != "PENDING":
        return get_order_detail(session, order_id, actor_id)

    now = _now()
    session.execute(
        models.orders.update()
        .where(models.orders.c.id == order_id)
        .values(
            status="ACCEPTED",
            accepted_at=now,
        )
    )
    lines = (
        session.execute(
            sa.select(models.order_lines).where(
                models.order_lines.c.order_id == order_id,
                models.order_lines.c.status == "active",
            )
        )
        .mappings()
        .all()
    )

    for line in lines:
        OrderAcceptanceService.ensure_production_task(
            session,
            organization_id=str(order["organization_id"]),
            branch_id=str(order["branch_id"]),
            order_id=order_id,
            line=dict(line),
            created_at=now,
        )

        # Build recipe consumption snapshot and record inventory reservation
        components = _active_recipe_components(session, line["product_id"], order["branch_id"])
        if components:
            existing_snapshot = session.execute(
                sa.select(models.order_line_consumption_snapshots.c.order_line_id).where(
                    models.order_line_consumption_snapshots.c.order_line_id == line["id"]
                )
            ).first()
            if not existing_snapshot:
                warehouse_id = _branch_warehouse_id(session, order["branch_id"])
                breakdown = []
                total_recipe_cost = Decimal("0")
                ordered_quantity = int(line.get("quantity", 1))
                for component in components:
                    gross_quantity = _quantity(
                        Decimal(str(component["gross_quantity"]))
                        / Decimal(str(component["yield_quantity"]))
                        * ordered_quantity
                    )
                    state = session.execute(
                        sa.select(models.inventory_cost_states.c.average_unit_cost).where(
                            models.inventory_cost_states.c.branch_id == order["branch_id"],
                            models.inventory_cost_states.c.warehouse_id == warehouse_id,
                            models.inventory_cost_states.c.item_id == component["item_id"],
                        )
                    ).scalar_one_or_none()
                    unit_cost = _cost(state or 0)
                    component_cost = _cost(gross_quantity * unit_cost)
                    total_recipe_cost += component_cost
                    breakdown.append(
                        _sanitize_for_json(
                            {
                                "item_id": component["item_id"],
                                "item_name": component["item_name"],
                                "unit_id": component["unit_id"],
                                "unit_code": component["unit_code"],
                                "net_quantity": _quantity(
                                    Decimal(str(component["net_quantity"]))
                                    / Decimal(str(component["yield_quantity"]))
                                    * ordered_quantity
                                ),
                                "gross_quantity": gross_quantity,
                                "waste_rate": component["waste_rate"],
                                "unit_cost": unit_cost,
                                "total_cost": component_cost,
                            }
                        )
                    )
                session.execute(
                    models.order_line_consumption_snapshots.insert().values(
                        order_line_id=line["id"],
                        order_id=order_id,
                        recipe_id=components[0]["recipe_id"],
                        recipe_version=components[0]["recipe_version"],
                        branch_id=order["branch_id"],
                        components=breakdown,
                        modifiers=[],
                        total_theoretical_cost=_cost(total_recipe_cost),
                        created_at=now,
                    )
                )
                _record_calculated_consumption_movements(
                    session,
                    components=breakdown,
                    product_name=line["product_name"],
                    movement_type="SALE_RESERVATION",
                    sign=-1,
                    reason=f"Reserva por aceptación de pedido {order['folio']}",
                    source_type="order_acceptance",
                    source_id=order_id,
                    created_at=now,
                    branch_id=order["branch_id"],
                )

    _audit(
        session,
        action="order.accepted",
        entity_type="order",
        entity_id=order_id,
        payload={"order_id": order_id, "previous_status": "PENDING", "new_status": "ACCEPTED"},
        branch_id=order["branch_id"],
        actor_user_id=actor_id,
    )
    session.commit()
    return get_order_detail(session, order_id, actor_id)
