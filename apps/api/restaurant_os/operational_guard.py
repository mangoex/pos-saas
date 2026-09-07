from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, NoReturn

from fastapi import HTTPException
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.auth import verify_session_token
from restaurant_os.config import get_settings
from restaurant_os.operations import AuthorizationError, _audit, require_permission


@dataclass(frozen=True)
class OperationalActor:
    user_id: str
    organization_id: str
    branch_id: str | None
    capability: str


class OperationalRouteGuard:
    """Default-deny resolver for verified humans and persisted device credentials."""

    def require_human(
        self, session: Session, authorization: str | None, capability: str, branch_id: str | None
    ) -> OperationalActor:
        if not authorization or not authorization.startswith("Bearer "):
            self.deny(session, "operational_route_denied", capability, branch_id)
        payload = verify_session_token(
            authorization.removeprefix("Bearer ").strip(), get_settings().secret_key
        )
        user_id = str(payload.get("sub", "")) if payload else ""
        if not user_id:
            self.deny(session, "operational_route_denied", capability, branch_id)
        resolved_branch_id = self._resolve_human_branch(session, user_id, branch_id)
        try:
            # Existing RBAC permission; no role-name authority is introduced.
            require_permission(session, user_id, capability, resolved_branch_id)
        except AuthorizationError:
            self.deny(session, "operational_route_denied", capability, resolved_branch_id, user_id)
        actor = (
            session.execute(models.users.select().where(models.users.c.id == user_id))
            .mappings()
            .first()
        )
        if not actor:
            self.deny(session, "operational_route_denied", capability, resolved_branch_id, user_id)
        return OperationalActor(
            user_id=user_id,
            organization_id=actor["organization_id"],
            branch_id=resolved_branch_id,
            capability=capability,
        )

    def _resolve_human_branch(
        self,
        session: Session,
        user_id: str,
        requested_branch_id: str | None,
    ) -> str:
        actor = (
            session.execute(models.users.select().where(models.users.c.id == user_id))
            .mappings()
            .first()
        )
        if not actor or actor["status"] != "active":
            self.deny(
                session,
                "operational_route_denied",
                "branch.scope",
                requested_branch_id,
                user_id,
            )
        requested = (requested_branch_id or "").strip()
        if requested:
            active = session.execute(
                models.branches.select().where(
                    models.branches.c.id == requested,
                    models.branches.c.organization_id == actor["organization_id"],
                    models.branches.c.status == "active",
                )
            ).first()
            if not active:
                self.deny(session, "operational_route_denied", "branch.scope", requested, user_id)
            return requested

        assigned = list(
            session.execute(
                models.user_roles.select()
                .with_only_columns(models.user_roles.c.branch_id)
                .join(models.branches, models.user_roles.c.branch_id == models.branches.c.id)
                .where(
                    models.user_roles.c.user_id == user_id,
                    models.user_roles.c.branch_id.is_not(None),
                    models.branches.c.organization_id == actor["organization_id"],
                    models.branches.c.status == "active",
                )
                .distinct()
            ).scalars()
        )
        if len(assigned) == 1:
            return str(assigned[0])
        active_branches = list(
            session.execute(
                models.branches.select()
                .with_only_columns(models.branches.c.id)
                .where(
                    models.branches.c.organization_id == actor["organization_id"],
                    models.branches.c.status == "active",
                )
            ).scalars()
        )
        if len(active_branches) == 1:
            return str(active_branches[0])
        self.deny(session, "operational_route_denied", "branch.scope", None, user_id)

    def require_device(
        self,
        session: Session,
        token: str | None,
        capability: str,
        organization_id: str,
        branch_id: str,
    ) -> OperationalActor:
        if not token:
            self.deny(session, "device_actor_required", capability, branch_id)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        credential = (
            session.execute(
                models.device_credentials.select().where(
                    models.device_credentials.c.token_hash == digest
                )
            )
            .mappings()
            .first()
        )
        now = datetime.now(timezone.utc)
        expires_at = credential["expires_at"] if credential else None
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if not credential or credential["revoked_at"] or not expires_at or expires_at <= now:
            self.deny(session, "device_scope_denied", capability, branch_id)
        if not self._scope_is_active(session, credential):
            self.deny(
                session,
                "device_scope_denied",
                capability,
                None,
                device_id=credential["id"],
                organization_id=credential["organization_id"],
            )
        if (
            credential["capability"] != capability
            or credential["organization_id"] != organization_id
            or credential["branch_id"] != branch_id
        ):
            self.deny(
                session,
                "device_scope_denied",
                capability,
                branch_id,
                device_id=credential["id"],
            )
        return OperationalActor(
            user_id=credential["id"],
            organization_id=organization_id,
            branch_id=branch_id,
            capability=capability,
        )

    def require_device_for_capability(
        self, session: Session, token: str | None, capability: str
    ) -> OperationalActor:
        """Resolve a device's persisted scope; callers never supply a pull scope."""
        if not token:
            self.deny(session, "device_actor_required", capability, None)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        credential = (
            session.execute(
                models.device_credentials.select().where(
                    models.device_credentials.c.token_hash == digest
                )
            )
            .mappings()
            .first()
        )
        now = datetime.now(timezone.utc)
        expires_at = credential["expires_at"] if credential else None
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if not credential or credential["revoked_at"] or not expires_at or expires_at <= now:
            self.deny(session, "device_scope_denied", capability, None)
        if not self._scope_is_active(session, credential):
            self.deny(
                session,
                "device_scope_denied",
                capability,
                None,
                device_id=credential["id"],
                organization_id=credential["organization_id"],
            )
        if credential["capability"] != capability:
            self.deny(
                session,
                "device_scope_denied",
                capability,
                credential["branch_id"],
                device_id=credential["id"],
            )
        return OperationalActor(
            user_id=credential["id"],
            organization_id=credential["organization_id"],
            branch_id=credential["branch_id"],
            capability=capability,
        )

    @staticmethod
    def _scope_is_active(session: Session, credential: Mapping[str, Any] | RowMapping) -> bool:
        return bool(
            session.execute(
                models.branches.select()
                .join(
                    models.organizations,
                    models.branches.c.organization_id == models.organizations.c.id,
                )
                .where(
                    models.branches.c.id == credential["branch_id"],
                    models.branches.c.organization_id == credential["organization_id"],
                    models.branches.c.status == "active",
                    models.organizations.c.status == "active",
                )
                .limit(1)
            ).first()
        )

    @staticmethod
    def deny(
        session: Session,
        code: str,
        capability: str,
        branch_id: str | None,
        actor_user_id: str | None = None,
        device_id: str | None = None,
        organization_id: str = "018f6f73-2d0a-74f0-8f1c-000000000001",
    ) -> NoReturn:
        """Persist a credential-free denial before returning the stable public code."""
        _audit(
            session,
            action="operational_route.denied",
            entity_type="operational_route",
            entity_id=capability,
            payload={
                "code": code,
                "capability": capability,
                **({"actor_kind": "device", "device_id": device_id} if device_id else {}),
            },
            branch_id=branch_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )
        session.commit()
        status = 401 if code in {"operational_route_denied", "device_actor_required"} else 403
        raise HTTPException(status_code=status, detail={"code": code})
