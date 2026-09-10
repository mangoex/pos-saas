"""Tenant-owned menu presentation; image URLs are references, never server fetches."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restaurant_os import models


def normalize_image_url(value: object) -> str | None:
    from restaurant_os.operations import BusinessError

    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise BusinessError("invalid_image_url", "La liga de imagen debe ser HTTP o HTTPS.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise BusinessError("invalid_image_url", "La liga de imagen contiene caracteres inválidos.")
    value = value.strip()
    if not value:
        return None
    if value.startswith("data:"):
        if not value.startswith("data:image/"):
            raise BusinessError("invalid_image_url", "Usa una imagen en formato JPG, PNG, WEBP o GIF válida, de hasta 2MB.")
        if len(value) > 2 * 1024 * 1024:
            raise BusinessError("invalid_image_url", "La imagen no debe exceder 2MB.")
        if not re.fullmatch(r"data:image/(?:jpeg|jpg|png|webp|gif);base64,[A-Za-z0-9+/]+={0,2}", value):
            raise BusinessError("invalid_image_url", "Usa una imagen en formato JPG, PNG, WEBP o GIF válida, de hasta 2MB.")
        return value
    try:
        url = urlsplit(value)
        valid = (
            len(value) <= 512
            and url.scheme in {"http", "https"}
            and bool(url.hostname)
            and not url.username
            and not url.password
            and "\\" not in value
            and not any(char.isspace() for char in value)
        )
        _ = url.port
        hostname = (url.hostname or "").rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            valid = False
        try:
            valid = valid and ip_address(hostname).is_global
        except ValueError:
            # Reject alternate numeric IP spellings that browsers normalize to loopback.
            if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", hostname.rsplit(".", 1)[-1]):
                valid = False
    except ValueError:
        valid = False
    if not valid:
        raise BusinessError(
            "invalid_image_url",
            "Usa una liga HTTP o HTTPS válida, de hasta 512 caracteres y sin credenciales.",
        )
    return value


def menu_home(session: Session, organization_id: str) -> dict[str, Any]:
    from restaurant_os.operations import BusinessError

    row = (
        session.execute(
            sa.select(
                models.organizations.c.menu_home_name, models.organizations.c.menu_home_image_url
            ).where(models.organizations.c.id == organization_id)
        )
        .mappings()
        .first()
    )
    if not row:
        raise BusinessError("organization_not_found", "Restaurante no encontrado.")
    return {"name": row["menu_home_name"], "image_url": row["menu_home_image_url"]}


def _owner(session: Session, actor_id: str) -> str:
    from restaurant_os.operations import AuthorizationError, _actor_user_info, require_permission

    require_permission(session, actor_id, "catalog.manage")
    actor = _actor_user_info(session, actor_id)
    if not actor or not actor.get("organization_id"):
        raise AuthorizationError("actor_not_authorized", "Actor is not authorized")
    return str(actor["organization_id"])


def read_menu_home(session: Session, actor_id: str) -> dict[str, Any]:
    return menu_home(session, _owner(session, actor_id))


def update_menu_home(
    session: Session, actor_id: str, name: object, image_url: object
) -> dict[str, Any]:
    from restaurant_os.operations import BusinessError, _audit

    organization_id = _owner(session, actor_id)
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise BusinessError(
            "invalid_menu_home_name", "El nombre debe tener entre 1 y 120 caracteres."
        )
    image = normalize_image_url(image_url)
    # Serialize before/after audit with concurrent presentation editors.
    session.execute(
        sa.select(models.organizations.c.id)
        .where(models.organizations.c.id == organization_id)
        .with_for_update()
    ).scalar_one()
    before = menu_home(session, organization_id)
    after = {"name": name.strip(), "image_url": image}
    session.execute(
        models.organizations.update()
        .where(models.organizations.c.id == organization_id)
        .values(
            menu_home_name=after["name"],
            menu_home_image_url=image,
            updated_at=datetime.now(timezone.utc),
        )
    )
    _audit(
        session,
        action="menu_home.updated",
        entity_type="organization",
        entity_id=organization_id,
        actor_user_id=actor_id,
        organization_id=organization_id,
        payload={"before": before, "after": after},
    )
    session.commit()
    return after
