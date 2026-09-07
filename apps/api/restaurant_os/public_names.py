"""Serialize public alias/slug/code allocation across tenant transactions."""

import hashlib

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from restaurant_os import models


def lock_public_name(session: Session, name: str) -> None:
    if session.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(
            hashlib.sha256(("public-name:" + name.lower()).encode()).digest()[:8],
            "big",
            signed=True,
        )
        session.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def available_slug(session: Session, name: str) -> bool:
    lock_public_name(session, name)
    return not any(
        (
            session.scalar(
                sa.select(models.storefront_aliases.c.alias).where(
                    models.storefront_aliases.c.alias == name
                )
            ),
            session.scalar(
                sa.select(models.organizations.c.id).where(models.organizations.c.slug == name)
            ),
            session.scalar(
                sa.select(models.branches.c.id).where(sa.func.lower(models.branches.c.code) == name)
            ),
        )
    )


def guard_branch_code(session: Session, code: str) -> None:
    normalized = code.strip().lower()
    lock_public_name(session, normalized)
    if session.scalar(
        sa.select(models.storefront_aliases.c.alias).where(
            models.storefront_aliases.c.alias == normalized
        )
    ):
        raise HTTPException(
            409,
            detail={
                "code": "public_name_reserved",
                "message": "El código está reservado como enlace público. Elige otro.",
            },
        )
