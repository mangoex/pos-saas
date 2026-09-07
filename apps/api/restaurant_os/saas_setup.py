"""Resumable tenant-owned setup; no operational sale or payment is fabricated."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.auth import bearer_token, verify_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.operations import _audit, _now, require_permission
from restaurant_os.saas_onboarding import _seed_starter_catalog

router = APIRouter(prefix="/api/v1/saas", tags=["saas"])
STEPS = ("business", "menu", "register", "complete")


class SetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    step: Literal["business", "menu", "register"]
    business_name: str | None = Field(default=None, min_length=1, max_length=160)
    branch_name: str | None = Field(default=None, min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)
    business_type: (
        Literal["blank", "general", "taqueria", "cafeteria", "pizzeria", "hamburgueseria"] | None
    ) = None
    register_name: str | None = Field(default=None, min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_step(self) -> SetupRequest:
        if self.step == "business":
            if not self.business_name or not self.branch_name or not self.timezone:
                raise ValueError("Nombre del negocio, sucursal y zona horaria requeridos")
            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("Zona horaria inválida") from exc
        if self.step == "menu" and not self.business_type:
            raise ValueError("Selecciona una plantilla o un catálogo vacío")
        if self.step == "register" and not self.register_name:
            raise ValueError("Identificador de caja requerido")
        return self


def _actor(session: Session, authorization: str | None) -> dict[str, Any]:
    token = bearer_token(authorization)
    claims = verify_session_token(token, get_settings().secret_key) if token else None
    if not claims or not claims.get("sub"):
        raise HTTPException(401, detail={"code": "actor_required"})
    actor_id = str(claims["sub"])
    require_permission(session, actor_id, "admin.manage")
    actor = (
        session.execute(sa.select(models.users).where(models.users.c.id == actor_id))
        .mappings()
        .one()
    )
    return dict(actor)


def _status(session: Session, org_id: str) -> dict[str, Any]:
    org = (
        session.execute(sa.select(models.organizations).where(models.organizations.c.id == org_id))
        .mappings()
        .one()
    )
    branch = (
        session.execute(
            sa.select(models.branches)
            .where(
                models.branches.c.organization_id == org_id,
                models.branches.c.status == "active",
            )
            .order_by(models.branches.c.created_at, models.branches.c.id)
        )
        .mappings()
        .first()
    )
    if not branch:
        raise HTTPException(409, detail={"code": "onboarding_branch_required"})
    fields = ("id", "name", "plan", "subscription_status", "trial_ends_at", "slug")
    return {
        "organization": {**{key: org[key] for key in fields}, "public_slug": org["slug"]},
        "branch": {key: branch[key] for key in ("id", "name", "phone", "timezone")},
        "step": org["onboarding_step"],
        "register_name": org["onboarding_register_name"],
        "menu_url": f"/menu/{org['slug']}/" if org["slug"] else None,
    }


@router.get("/onboarding")
def get_setup(
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    actor = _actor(session, authorization)
    return _status(session, str(actor["organization_id"]))


@router.put("/onboarding")
def update_setup(
    payload: SetupRequest,
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    actor = _actor(session, authorization)
    org_id = str(actor["organization_id"])
    current = session.execute(
        sa.select(models.organizations.c.onboarding_step)
        .where(models.organizations.c.id == org_id)
        .with_for_update()
    ).scalar_one()
    if current not in STEPS:
        raise HTTPException(409, detail={"code": "onboarding_state_invalid"})
    if STEPS.index(payload.step) > STEPS.index(current):
        raise HTTPException(409, detail={"code": "onboarding_step_conflict"})
    if STEPS.index(payload.step) < STEPS.index(current):
        return _status(session, org_id)
    status = _status(session, org_id)
    branch_id = str(status["branch"]["id"])
    now = _now()
    values: dict[str, Any] = {"onboarding_step": STEPS[STEPS.index(current) + 1], "updated_at": now}
    if payload.step == "business":
        values["name"] = payload.business_name
        session.execute(
            models.branches.update()
            .where(
                models.branches.c.id == branch_id,
                models.branches.c.organization_id == org_id,
            )
            .values(
                name=payload.branch_name,
                phone=payload.phone,
                timezone=payload.timezone,
                updated_at=now,
            )
        )
    elif payload.step == "menu":
        _seed_starter_catalog(session, org_id, branch_id, payload.business_type or "blank", now)
        values["business_type"] = payload.business_type
    else:
        values["onboarding_register_name"] = payload.register_name
    session.execute(
        models.organizations.update().where(models.organizations.c.id == org_id).values(**values)
    )
    _audit(
        session,
        "tenant.onboarding_step",
        "organization",
        org_id,
        {"completed_step": current, "next_step": values["onboarding_step"]},
        branch_id=branch_id,
        organization_id=org_id,
        actor_user_id=str(actor["id"]),
    )
    session.commit()
    return _status(session, org_id)
