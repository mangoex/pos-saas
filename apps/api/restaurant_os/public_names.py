"""Serialize public alias/slug/code allocation across tenant transactions."""

import hashlib
import re

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from restaurant_os import models

# These labels are routes/platform identities, never new public tenant identities.
RESERVED_PUBLIC_NAMES = frozenset(
    {
        "admin",
        "api",
        "app",
        "kds",
        "login",
        "matriz",
        "menu",
        "pos",
        "register",
        "soporte",
        "status",
        "www",
    }
)
_WILDCARD_PUBLIC_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def is_reserved_public_name(name: str) -> bool:
    return name.strip().lower() in RESERVED_PUBLIC_NAMES


def is_wildcard_compatible_public_name(name: str) -> bool:
    """Return whether an existing public identity is one safe DNS label."""
    normalized = name.strip().lower()
    return (
        name.strip() == normalized
        and bool(_WILDCARD_PUBLIC_LABEL.fullmatch(normalized))
        and not is_reserved_public_name(normalized)
    )


def lock_public_name(session: Session, name: str) -> None:
    if session.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(
            hashlib.sha256(("public-name:" + name.lower()).encode()).digest()[:8],
            "big",
            signed=True,
        )
        session.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def available_slug(session: Session, name: str) -> bool:
    normalized = name.strip().lower()
    if is_reserved_public_name(normalized):
        return False
    lock_public_name(session, normalized)
    return not any(
        (
            session.scalar(
                sa.select(models.storefront_aliases.c.alias).where(
                    models.storefront_aliases.c.alias == normalized
                )
            ),
            session.scalar(
                sa.select(models.organizations.c.id).where(
                    models.organizations.c.slug == normalized
                )
            ),
            session.scalar(
                sa.select(models.branches.c.id).where(
                    sa.func.lower(models.branches.c.code) == normalized
                )
            ),
        )
    )


def guard_branch_code(session: Session, code: str) -> None:
    normalized = code.strip().lower()
    lock_public_name(session, normalized)
    if is_reserved_public_name(normalized):
        raise HTTPException(
            409,
            detail={
                "code": "public_name_reserved",
                "message": "El código está reservado como enlace público. Elige otro.",
            },
        )
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
