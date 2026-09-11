"""Tenant-owned public names and supervised domain lifecycle."""

from __future__ import annotations

import ipaddress
import re
import secrets
from typing import Annotated, Any, Literal, Optional
from urllib.parse import urlsplit
from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.auth import bearer_token, verify_session_token
from restaurant_os.config import get_settings
from restaurant_os.database import get_session
from restaurant_os.domain_dns import DnsUnavailable, lookup_txt
from restaurant_os.operations import _audit, _now
from restaurant_os.public_names import (
    is_reserved_public_name,
    is_wildcard_compatible_public_name,
    lock_public_name,
)
from restaurant_os.saas_setup import _actor
from restaurant_os.superadmin.service import require_superadmin

router = APIRouter(prefix="/api/v1/saas", tags=["restaurant-links"])
SessionDep = Annotated[Session, Depends(get_session)]
AuthDep = Annotated[Optional[str], Header()]


def error(status: int, code: str) -> HTTPException:
    messages = {
        "alias_reserved": "Este nombre está reservado. Elige otro.",
        "alias_invalid": "Este nombre no puede usarse como subdominio. Elige otro.",
        "alias_unavailable": "El nombre ya está ocupado. Elige otro.",
        "domain_invalid": "Escribe un dominio válido, sin https://, rutas ni puertos.",
        "domain_reserved": "Este dominio está reservado para la plataforma.",
        "domain_unavailable": "El dominio no está disponible.",
        "domain_tenant_mismatch": "Esta cuenta pertenece a otro restaurante. Usa su enlace.",
        "domain_tls_confirmation_required": "Falta configurar el enrutamiento y confirmar HTTPS.",
        "domain_active_exists": "Desactiva el dominio anterior antes de activar este.",
        "dns_mismatch": "El TXT no coincide. Revisa DNS y vuelve a verificar.",
        "dns_unavailable": "No se pudo consultar DNS. Intenta nuevamente.",
    }
    return HTTPException(
        status,
        detail={
            "code": code,
            "message": messages.get(
                code, "No se pudo completar la operación. Revisa el acceso y la configuración."
            ),
        },
    )


def platform_hosts() -> set[str]:
    return {h.strip().lower() for h in get_settings().platform_hosts.split(",") if h.strip()}


def wildcard_domain() -> str:
    return get_settings().storefront_wildcard_domain


def host_routing_enabled() -> bool:
    return bool(platform_hosts() or wildcard_domain())


def base_url() -> str:
    value = get_settings().public_base_url.rstrip("/")
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.path
        or url.query
        or url.fragment
        or url.username
        or url.password
        or url.port
    ):
        raise error(503, "public_base_url_invalid")
    return value


def normalize_hostname(value: str) -> str:
    host = value.strip().lower().rstrip(".")
    if (
        not host.isascii()
        or len(host) > 240
        or not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+",
            host,
        )
    ):
        raise error(422, "domain_invalid")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise error(422, "domain_invalid")
    wildcard = wildcard_domain()
    reserved = platform_hosts() | {str(urlsplit(base_url()).hostname)}
    if host.endswith((".local", ".localhost", ".internal", ".test", ".invalid")) or any(
        host == name or host.endswith("." + name) for name in reserved
    ) or (wildcard and (host == wildcard or host.endswith("." + wildcard))):
        raise error(422, "domain_reserved")
    return host


def domain_view(row: Any) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "id",
            "organization_id",
            "hostname",
            "status",
            "last_result",
            "verified_at",
            "created_at",
            "updated_at",
        )
    } | {
        "txt_name": "_humanio-verification." + row["hostname"],
        "txt_value": "humanio-domain=" + row["verification_token"],
        "cname_target": urlsplit(base_url()).hostname,
    }


def audit(session: Session, actor_id: str, row: Any, action: str) -> None:
    _audit(
        session,
        action="domain." + action,
        entity_type="restaurant_domain",
        entity_id=row["id"],
        organization_id=row["organization_id"],
        actor_user_id=actor_id,
        payload={
            "hostname": row["hostname"],
            "status": row["status"],
            "result": row["last_result"],
        },
    )


def links(session: Session, org_id: str) -> dict[str, Any]:
    org = (
        session.execute(sa.select(models.organizations).where(models.organizations.c.id == org_id))
        .mappings()
        .one()
    )
    domains = (
        session.execute(
            sa.select(models.restaurant_domains)
            .where(models.restaurant_domains.c.organization_id == org_id)
            .order_by(models.restaurant_domains.c.created_at)
        )
        .mappings()
        .all()
    )
    active = next((row for row in domains if row["status"] == "active"), None)
    canonical_slug = str(org["slug"])
    alias = str(org["preferred_public_slug"] or canonical_slug)
    wildcard = wildcard_domain()
    wildcard_alias: str | None = None
    if is_wildcard_compatible_public_name(alias):
        wildcard_alias = alias
    elif is_wildcard_compatible_public_name(canonical_slug):
        wildcard_alias = canonical_slug
    if active and host_routing_enabled():
        origin = "https://" + active["hostname"]
        menu = origin + f"/menu/{alias}/"
    elif wildcard and wildcard_alias:
        origin = f"https://{wildcard_alias}.{wildcard}"
        menu = origin + "/"
    else:
        origin = base_url()
        menu = origin + f"/menu/{alias}/"
    canonical_menu_url = (
        f"https://{canonical_slug}.{wildcard}/"
        if wildcard and is_wildcard_compatible_public_name(canonical_slug)
        else base_url() + f"/menu/{canonical_slug}/"
    )
    return {
        "name": org["name"],
        "canonical_slug": org["slug"],
        "preferred_slug": alias,
        "links": {
            "admin": origin + "/admin/",
            "pos": origin + "/pos/",
            "kds": origin + "/kds/",
            "menu": menu,
        },
        "canonical_menu_url": canonical_menu_url,
        "domains": [domain_view(row) for row in domains],
        "domain_routing_enabled": host_routing_enabled(),
    }


class AliasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    alias: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class DomainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hostname: str = Field(min_length=3, max_length=253)


class SuperviseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["activate", "disable", "delete"]
    tls_confirmed: bool = False


class AssignDomainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: str
    hostname: str = Field(min_length=3, max_length=253)


@router.get("/links")
def get_links(session: SessionDep, authorization: AuthDep = None) -> dict[str, Any]:
    return links(session, str(_actor(session, authorization)["organization_id"]))


@router.put("/links/alias")
def set_alias(
    payload: AliasRequest, session: SessionDep, authorization: AuthDep = None
) -> dict[str, Any]:
    actor = _actor(session, authorization)
    org_id = str(actor["organization_id"])
    session.execute(
        sa.select(models.organizations.c.id)
        .where(models.organizations.c.id == org_id)
        .with_for_update()
    ).one()
    alias = payload.alias
    lock_public_name(session, alias)
    if is_reserved_public_name(alias):
        raise error(409, "alias_reserved")
    if wildcard_domain() and not is_wildcard_compatible_public_name(alias):
        raise error(409, "alias_invalid")
    existing = (
        session.execute(
            sa.select(models.storefront_aliases).where(models.storefront_aliases.c.alias == alias)
        )
        .mappings()
        .first()
    )
    conflict = session.scalar(
        sa.select(models.organizations.c.id).where(
            models.organizations.c.slug == alias, models.organizations.c.id != org_id
        )
    )
    branch_conflict = session.scalar(
        sa.select(models.branches.c.id).where(
            sa.or_(sa.func.lower(models.branches.c.code) == alias, models.branches.c.id == alias)
        )
    )
    if conflict or branch_conflict or (existing and existing["organization_id"] != org_id):
        raise error(409, "alias_unavailable")
    now = _now()
    try:
        if not existing:
            session.execute(
                models.storefront_aliases.insert().values(
                    alias=alias, organization_id=org_id, created_at=now
                )
            )
        session.execute(
            models.organizations.update()
            .where(models.organizations.c.id == org_id)
            .values(preferred_public_slug=alias, updated_at=now)
        )
        _audit(
            session,
            action="storefront.alias_selected",
            entity_type="organization",
            entity_id=org_id,
            organization_id=org_id,
            actor_user_id=actor["id"],
            payload={"alias": alias},
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise error(409, "alias_unavailable") from exc
    return links(session, org_id)


@router.post("/domains")
def request_domain(
    payload: DomainRequest, session: SessionDep, authorization: AuthDep = None
) -> dict[str, Any]:
    actor = _actor(session, authorization)
    hostname = normalize_hostname(payload.hostname)
    row = (
        session.execute(
            sa.select(models.restaurant_domains).where(
                models.restaurant_domains.c.hostname == hostname
            )
        )
        .mappings()
        .first()
    )
    if row:
        if row["organization_id"] != actor["organization_id"]:
            raise error(409, "domain_unavailable")
        return domain_view(row)
    now = _now()
    values = {
        "id": str(uuid4()),
        "organization_id": actor["organization_id"],
        "hostname": hostname,
        "status": "pending_dns",
        "verification_token": secrets.token_urlsafe(32),
        "last_result": None,
        "verified_at": None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        session.execute(models.restaurant_domains.insert().values(**values))
        audit(session, actor["id"], values, "requested")
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise error(409, "domain_unavailable") from exc
    return domain_view(values)


def locked_domain(session: Session, domain_id: str, org_id: str | None = None) -> dict[str, Any]:
    stmt = sa.select(models.restaurant_domains).where(models.restaurant_domains.c.id == domain_id)
    if org_id:
        stmt = stmt.where(models.restaurant_domains.c.organization_id == org_id)
    row = session.execute(stmt.with_for_update()).mappings().first()
    if not row:
        raise error(404, "domain_not_found")
    return dict(row)


def verify_domain(session: Session, row: dict[str, Any], actor_id: str) -> bool:
    view = domain_view(row)
    try:
        matched = view["txt_value"] in lookup_txt(view["txt_name"])
        result = "dns_verified" if matched else "dns_mismatch"
    except DnsUnavailable:
        matched, result = False, "dns_unavailable"
    # A failed recheck must not silently turn off a live customer domain.
    status = (
        row["status"]
        if row["status"] in {"active", "disabled"}
        else ("pending_tls" if matched else "pending_dns")
    )
    row.update(
        status=status,
        last_result=result,
        verified_at=_now() if matched else None,
        updated_at=_now(),
    )
    session.execute(
        models.restaurant_domains.update()
        .where(models.restaurant_domains.c.id == row["id"])
        .values(
            status=status,
            last_result=result,
            verified_at=row["verified_at"],
            updated_at=row["updated_at"],
        )
    )
    audit(session, actor_id, row, "dns_checked")
    return matched


@router.post("/domains/{domain_id}/verify")
def verify_endpoint(
    domain_id: str, session: SessionDep, authorization: AuthDep = None
) -> dict[str, Any]:
    actor = _actor(session, authorization)
    row = locked_domain(session, domain_id, str(actor["organization_id"]))
    verify_domain(session, row, actor["id"])
    session.commit()
    return domain_view(row)


def platform_actor(session: Session, authorization: str | None) -> dict[str, Any]:
    token = bearer_token(authorization)
    claims = verify_session_token(token, get_settings().secret_key) if token else None
    return require_superadmin(session, str(claims.get("sub", "")) if claims else None)


@router.get("/domains/supervision")
def supervision_list(session: SessionDep, authorization: AuthDep = None) -> list[dict[str, Any]]:
    platform_actor(session, authorization)
    stmt = (
        sa.select(
            models.restaurant_domains,
            models.organizations.c.name.label("organization_name"),
            models.organizations.c.slug.label("organization_slug"),
            models.organizations.c.preferred_public_slug.label("organization_preferred_slug"),
        )
        .outerjoin(
            models.organizations,
            models.restaurant_domains.c.organization_id == models.organizations.c.id,
        )
        .order_by(models.restaurant_domains.c.created_at.desc())
        .limit(200)
    )
    results = []
    for row in session.execute(stmt).mappings():
        view = domain_view(row)
        view["organization_name"] = row.get("organization_name") or "Restaurante"
        view["organization_slug"] = row.get("organization_slug") or ""
        view["organization_preferred_slug"] = row.get("organization_preferred_slug") or ""
        results.append(view)
    return results


@router.get("/domains/supervision/tenants")
def supervision_tenants(session: SessionDep, authorization: AuthDep = None) -> list[dict[str, Any]]:
    platform_actor(session, authorization)
    orgs = (
        session.execute(
            sa.select(models.organizations)
            .order_by(models.organizations.c.name)
            .limit(300)
        )
        .mappings()
        .all()
    )
    all_domains = (
        session.execute(
            sa.select(models.restaurant_domains)
            .order_by(models.restaurant_domains.c.created_at.desc())
        )
        .mappings()
        .all()
    )
    domains_by_org: dict[str, list[dict[str, Any]]] = {}
    for d in all_domains:
        org_id = str(d["organization_id"])
        domains_by_org.setdefault(org_id, []).append(domain_view(d))

    wildcard = wildcard_domain()
    items = []
    for org in orgs:
        org_id = str(org["id"])
        canonical_slug = str(org["slug"] or "")
        alias = str(org["preferred_public_slug"] or canonical_slug)
        org_domains = domains_by_org.get(org_id, [])
        active_domain = next((d for d in org_domains if d["status"] == "active"), None)

        wildcard_alias: str | None = None
        if is_wildcard_compatible_public_name(alias):
            wildcard_alias = alias
        elif is_wildcard_compatible_public_name(canonical_slug):
            wildcard_alias = canonical_slug

        if active_domain and host_routing_enabled():
            menu_url = f"https://{active_domain['hostname']}/menu/{alias}/"
        elif wildcard and wildcard_alias:
            menu_url = f"https://{wildcard_alias}.{wildcard}/"
        else:
            menu_url = f"{base_url()}/menu/{alias}/"

        primary_status = (
            active_domain["status"]
            if active_domain
            else (org_domains[0]["status"] if org_domains else "none")
        )
        items.append({
            "organization_id": org_id,
            "organization_name": org["name"],
            "canonical_slug": canonical_slug,
            "preferred_slug": alias,
            "menu_url": menu_url,
            "domains": org_domains,
            "active_domain": active_domain["hostname"] if active_domain else None,
            "domain_status": primary_status,
        })
    return items


@router.post("/domains/supervision/assign")
def supervision_assign_domain(
    payload: AssignDomainRequest, session: SessionDep, authorization: AuthDep = None
) -> dict[str, Any]:
    actor = platform_actor(session, authorization)
    org = session.execute(
        sa.select(models.organizations.c.id).where(
            models.organizations.c.id == payload.organization_id
        )
    ).scalar_one_or_none()
    if not org:
        raise error(404, "organization_not_found")
    hostname = normalize_hostname(payload.hostname)
    row = (
        session.execute(
            sa.select(models.restaurant_domains).where(
                models.restaurant_domains.c.hostname == hostname
            )
        )
        .mappings()
        .first()
    )
    if row:
        if row["organization_id"] != payload.organization_id:
            raise error(409, "domain_unavailable")
        return domain_view(row)
    now = _now()
    values = {
        "id": str(uuid4()),
        "organization_id": payload.organization_id,
        "hostname": hostname,
        "status": "pending_dns",
        "verification_token": secrets.token_urlsafe(32),
        "last_result": None,
        "verified_at": None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        session.execute(models.restaurant_domains.insert().values(**values))
        audit(session, actor["id"], values, "requested_by_superadmin")
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise error(409, "domain_unavailable") from exc
    return domain_view(values)


@router.post("/domains/{domain_id}/supervise")
def supervise(
    domain_id: str, payload: SuperviseRequest, session: SessionDep, authorization: AuthDep = None
) -> dict[str, Any]:
    actor = platform_actor(session, authorization)
    row = locked_domain(session, domain_id)
    if payload.action == "delete":
        session.execute(
            models.restaurant_domains.delete().where(models.restaurant_domains.c.id == domain_id)
        )
        audit(session, actor["id"], row, "deleted")
        session.commit()
        return {"status": "deleted", "id": domain_id}
    if payload.action == "activate":
        if not payload.tls_confirmed or not platform_hosts():
            raise error(409, "domain_tls_confirmation_required")
        normalize_hostname(row["hostname"])
        if urlsplit(base_url()).hostname not in platform_hosts():
            raise error(409, "domain_tls_confirmation_required")
        # Serialize activation of different domains for the same organization.
        session.execute(
            sa.select(models.organizations.c.id)
            .where(models.organizations.c.id == row["organization_id"])
            .with_for_update()
        ).one()
        other = session.scalar(
            sa.select(models.restaurant_domains.c.id).where(
                models.restaurant_domains.c.organization_id == row["organization_id"],
                models.restaurant_domains.c.status == "active",
                models.restaurant_domains.c.id != domain_id,
            )
        )
        if other:
            raise error(409, "domain_active_exists")
        if not verify_domain(session, row, actor["id"]):
            session.commit()
            raise error(409, row["last_result"])
    row.update(status="active" if payload.action == "activate" else "disabled", updated_at=_now())
    session.execute(
        models.restaurant_domains.update()
        .where(models.restaurant_domains.c.id == domain_id)
        .values(status=row["status"], updated_at=row["updated_at"])
    )
    audit(session, actor["id"], row, payload.action)
    session.commit()
    return domain_view(row)
