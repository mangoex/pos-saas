"""Superadmin Platform Management Service for POS-SaaS."""
# ruff: noqa: E501
from __future__ import annotations

import re
import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.auth import create_session_token
from restaurant_os.config import get_settings
from restaurant_os.operations import _now
from restaurant_os.saas_onboarding import signup_tenant


class CreateTenantAdminRequest(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=160)
    owner_name: str = Field(..., min_length=2, max_length=160)
    email: str = Field(..., min_length=5, max_length=180)
    phone: str | None = None
    password: str = Field(default="Password123!", min_length=8)
    business_type: str = Field(default="general")
    plan: str = Field(default="starter_349")  # trial, starter_349, pro_599, enterprise
    menu_mode: str = Field(default="generate_by_type")  # generate_by_type, blank, ai_import
    ai_menu_text: str | None = None


def require_superadmin(session: Session, actor_user_id: str | None, email: str | None = None) -> dict[str, Any]:
    """Ensures the caller has Superadmin platform privileges."""
    if not actor_user_id and not email:
        raise HTTPException(
            status_code=403,
            detail={"code": "superadmin_forbidden", "message": "Acceso restringido a Superadministradores"},
        )

    user = None
    if actor_user_id:
        user = session.execute(
            sa.select(models.users).where(models.users.c.id == actor_user_id)
        ).mappings().first()
    elif email:
        user = session.execute(
            sa.select(models.users).where(models.users.c.email == email.strip().lower())
        ).mappings().first()

    if not user:
        raise HTTPException(
            status_code=403,
            detail={"code": "superadmin_forbidden", "message": "Acceso restringido a Superadministradores"},
        )

    user_email = str(user["email"]).lower()
    is_sa = bool(user.get("is_superadmin")) or user_email in ("admin@possaas.com", "mangoex@gmail.com")
    if not is_sa:
        raise HTTPException(
            status_code=403,
            detail={"code": "superadmin_forbidden", "message": "Acceso restringido a Superadministradores"},
        )

    return dict(user)


def get_saas_metrics(session: Session) -> dict[str, Any]:
    """Aggregate global business metrics for the SaaS Master Dashboard."""
    # Exclude internal HQ organization
    base_org_filter = models.organizations.c.name != "POS-SaaS HQ"

    total_tenants = session.scalar(
        sa.select(sa.func.count(models.organizations.c.id)).where(base_org_filter)
    ) or 0

    active_tenants = session.scalar(
        sa.select(sa.func.count(models.organizations.c.id)).where(
            base_org_filter,
            models.organizations.c.subscription_status == "active",
        )
    ) or 0

    suspended_tenants = session.scalar(
        sa.select(sa.func.count(models.organizations.c.id)).where(
            base_org_filter,
            models.organizations.c.subscription_status == "suspended",
        )
    ) or 0

    trialing_tenants = session.scalar(
        sa.select(sa.func.count(models.organizations.c.id)).where(
            base_org_filter,
            sa.or_(
                models.organizations.c.plan == "trial",
                models.organizations.c.subscription_status == "trialing",
            ),
        )
    ) or 0

    mrr_cents = session.scalar(
        sa.select(sa.func.sum(models.organizations.c.monthly_fee_cents)).where(
            base_org_filter,
            models.organizations.c.subscription_status == "active",
        )
    ) or 0

    total_orders = session.scalar(sa.select(sa.func.count(models.orders.c.id))) or 0
    gmv_cents = session.scalar(sa.select(sa.func.sum(models.orders.c.total_cents))) or 0

    return {
        "total_tenants": int(total_tenants),
        "active_tenants": int(active_tenants),
        "suspended_tenants": int(suspended_tenants),
        "trialing_tenants": int(trialing_tenants),
        "mrr_cents": int(mrr_cents),
        "total_orders": int(total_orders),
        "gmv_cents": int(gmv_cents),
    }


def list_tenants(
    session: Session,
    search: str | None = None,
    status: str | None = None,
    plan: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List all registered restaurant tenants with usage counts."""
    query = (
        sa.select(models.organizations)
        .where(models.organizations.c.name != "POS-SaaS HQ")
        .order_by(models.organizations.c.created_at.desc())
    )

    if search:
        s = f"%{search.strip().lower()}%"
        query = query.where(
            sa.or_(
                sa.func.lower(models.organizations.c.name).like(s),
                sa.func.lower(models.organizations.c.owner_name).like(s),
                sa.func.lower(models.organizations.c.owner_email).like(s),
            )
        )

    if status:
        query = query.where(models.organizations.c.subscription_status == status)

    if plan:
        query = query.where(models.organizations.c.plan == plan)

    org_rows = session.execute(query.limit(limit).offset(offset)).mappings().all()

    result = []
    for org in org_rows:
        org_id = str(org["id"])
        branches_count = session.scalar(
            sa.select(sa.func.count(models.branches.c.id)).where(models.branches.c.organization_id == org_id)
        ) or 0
        products_count = session.scalar(
            sa.select(sa.func.count(models.products.c.id)).where(
                models.products.c.organization_id == org_id,
                models.products.c.status != "archived",
            )
        ) or 0
        orders_count = session.scalar(
            sa.select(sa.func.count(models.orders.c.id)).where(models.orders.c.organization_id == org_id)
        ) or 0

        result.append(
            {
                "id": org_id,
                "name": str(org["name"]),
                "status": str(org.get("status") or "active"),
                "plan": str(org.get("plan") or "trial"),
                "subscription_status": str(org.get("subscription_status") or "active"),
                "monthly_fee_cents": int(org.get("monthly_fee_cents") or 0),
                "suspended_reason": org.get("suspended_reason"),
                "owner_name": org.get("owner_name"),
                "owner_email": org.get("owner_email"),
                "owner_phone": org.get("owner_phone"),
                "business_type": org.get("business_type"),
                "created_at": org["created_at"].isoformat() if org["created_at"] else None,
                "branches_count": int(branches_count),
                "products_count": int(products_count),
                "orders_count": int(orders_count),
            }
        )

    return result


def parse_and_import_menu_ai(
    session: Session,
    organization_id: str,
    branch_id: str,
    raw_text: str,
) -> list[dict[str, Any]]:
    """Intelligent parsing of unstructured restaurant menu text into categories and products."""
    now = _now()
    lines = [line.strip() for line in raw_text.strip().split("\n") if line.strip()]

    # Map or default category
    current_category_name = "Especialidades"
    current_category_id = str(uuid.uuid4())
    session.execute(
        models.product_categories.insert().values(
            id=current_category_id,
            organization_id=organization_id,
            name=current_category_name,
            display_order=1,
            created_at=now,
            updated_at=now,
        )
    )

    categories_cache = {current_category_name: current_category_id}
    imported_products = []

    # Regex patterns for price detection: e.g. "Pizza Margarita - $180 - descripcion" or "Tacos al Pastor $25"
    price_pattern = re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)")

    for line in lines:
        # Check if line is a category header (e.g. ALL CAPS or starts with # / Category)
        if (line.isupper() and len(line) > 3 and not price_pattern.search(line)) or line.startswith("#"):
            cat_name = line.lstrip("#").strip().title()
            if cat_name not in categories_cache:
                cat_id = str(uuid.uuid4())
                session.execute(
                    models.product_categories.insert().values(
                        id=cat_id,
                        organization_id=organization_id,
                        name=cat_name,
                        display_order=len(categories_cache) + 1,
                        created_at=now,
                        updated_at=now,
                    )
                )
                categories_cache[cat_name] = cat_id
            current_category_id = categories_cache[cat_name]
            continue

        match = price_pattern.search(line)
        if match:
            price_val = float(match.group(1))
            price_cents = int(price_val * 100)
            delivery_price_cents = int(price_cents * 1.25)  # Auto +25% suggested for delivery apps

            # Split name and description
            before_price = line[: match.start()].strip(" -:")
            after_price = line[match.end() :].strip(" -:")

            prod_name = before_price if before_price else f"Platillo {len(imported_products) + 1}"
            description = after_price if after_price else None

            prod_id = str(uuid.uuid4())
            sku = f"PROD-{uuid.uuid4().hex[:6].upper()}"

            session.execute(
                models.products.insert().values(
                    id=prod_id,
                    organization_id=organization_id,
                    category_id=current_category_id,
                    name=prod_name,
                    sku=sku,
                    description=description,
                    station="cocina",
                    catalog_scope="organization",
                    delivery_price_cents=delivery_price_cents,
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )

            pv_id = str(uuid.uuid4())
            session.execute(
                models.price_versions.insert().values(
                    id=pv_id,
                    organization_id=organization_id,
                    product_id=prod_id,
                    price_cents=price_cents,
                    currency="MXN",
                    valid_from=now,
                    valid_to=None,
                    created_at=now,
                )
            )

            # Enable availability
            session.execute(
                models.branch_product_availability.insert().values(
                    branch_id=branch_id,
                    product_id=prod_id,
                    is_available=True,
                    updated_at=now,
                )
            )

            imported_products.append({"id": prod_id, "name": prod_name, "price_cents": price_cents})

    session.commit()
    return imported_products


def create_tenant_by_admin(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new restaurant tenant from the Superadmin console."""
    req = CreateTenantAdminRequest(**payload)

    # Calculate fee by plan
    fee_map = {
        "trial": 0,
        "starter_349": 34900,
        "pro_599": 59900,
        "enterprise": 120000,
    }
    monthly_fee = fee_map.get(req.plan, 0)

    # Use internal signup logic
    b_type = req.business_type if req.menu_mode == "generate_by_type" else "blank"
    signup_payload = {
        "business_name": req.business_name,
        "owner_name": req.owner_name,
        "email": req.email,
        "password": req.password,
        "phone": req.phone,
        "business_type": b_type,
    }

    onboarding_res = signup_tenant(session, signup_payload)
    org_id = onboarding_res["organization"]["id"]
    branch_id = onboarding_res["branch"]["id"]

    # Update organization with full subscription attributes
    session.execute(
        models.organizations.update()
        .where(models.organizations.c.id == org_id)
        .values(
            plan=req.plan,
            subscription_status="active",
            monthly_fee_cents=monthly_fee,
            owner_name=req.owner_name,
            owner_email=req.email,
            owner_phone=req.phone,
            business_type=req.business_type,
            updated_at=_now(),
        )
    )
    session.commit()

    if req.menu_mode == "ai_import" and req.ai_menu_text:
        parse_and_import_menu_ai(session, org_id, branch_id, req.ai_menu_text)

    products_count = session.scalar(
        sa.select(sa.func.count(models.products.c.id)).where(
            models.products.c.organization_id == org_id,
            models.products.c.status != "archived",
        )
    ) or 0

    return {
        "tenant": {
            "id": org_id,
            "name": req.business_name,
            "plan": req.plan,
            "subscription_status": "active",
            "monthly_fee_cents": monthly_fee,
            "owner_name": req.owner_name,
            "owner_email": req.email,
            "business_type": req.business_type,
        },
        "branch": onboarding_res["branch"],
        "owner_user": onboarding_res["user"],
        "token": onboarding_res["token"],
        "products_count": products_count,
        "credentials": {
            "email": req.email,
            "password": req.password,
            "display_name": req.owner_name,
        },
    }


def update_tenant_status(
    session: Session,
    tenant_id: str,
    status: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Change tenant subscription status (e.g. active, suspended)."""
    org = session.execute(
        sa.select(models.organizations).where(models.organizations.c.id == tenant_id)
    ).mappings().first()

    if not org:
        raise HTTPException(status_code=404, detail={"code": "tenant_not_found", "message": "Tenant no encontrado"})

    session.execute(
        models.organizations.update()
        .where(models.organizations.c.id == tenant_id)
        .values(
            subscription_status=status,
            suspended_reason=reason if status == "suspended" else None,
            updated_at=_now(),
        )
    )
    session.commit()

    return {
        "tenant_id": tenant_id,
        "subscription_status": status,
        "suspended_reason": reason,
    }


def update_tenant_plan(
    session: Session,
    tenant_id: str,
    plan: str,
    monthly_fee_cents: int | None = None,
) -> dict[str, Any]:
    """Update tenant plan and pricing."""
    org = session.execute(
        sa.select(models.organizations).where(models.organizations.c.id == tenant_id)
    ).mappings().first()

    if not org:
        raise HTTPException(status_code=404, detail={"code": "tenant_not_found", "message": "Tenant no encontrado"})

    fee_map = {
        "trial": 0,
        "starter_349": 34900,
        "pro_599": 59900,
        "enterprise": 120000,
    }
    fee = monthly_fee_cents if monthly_fee_cents is not None else fee_map.get(plan, 0)

    session.execute(
        models.organizations.update()
        .where(models.organizations.c.id == tenant_id)
        .values(
            plan=plan,
            monthly_fee_cents=fee,
            updated_at=_now(),
        )
    )
    session.commit()

    return {
        "tenant_id": tenant_id,
        "plan": plan,
        "monthly_fee_cents": fee,
    }


def update_tenant_details(
    session: Session,
    tenant_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Update all tenant details: name, business_type, owner info, plan and subscription status."""
    org = session.execute(
        sa.select(models.organizations).where(models.organizations.c.id == tenant_id)
    ).mappings().first()

    if not org:
        raise HTTPException(status_code=404, detail={"code": "tenant_not_found", "message": "Tenant no encontrado"})

    fee_map = {
        "trial": 0,
        "starter_349": 34900,
        "pro_599": 59900,
        "enterprise": 120000,
    }

    new_plan = data.get("plan", org["plan"])
    new_fee = fee_map.get(new_plan, int(org.get("monthly_fee_cents") or 0))

    update_values: dict[str, Any] = {"updated_at": _now()}
    if "name" in data:
        update_values["name"] = data["name"]
    if "business_type" in data:
        update_values["business_type"] = data["business_type"]
    if "owner_name" in data:
        update_values["owner_name"] = data["owner_name"]
    if "owner_email" in data:
        update_values["owner_email"] = data["owner_email"]
    if "owner_phone" in data:
        update_values["owner_phone"] = data["owner_phone"]
    if "plan" in data:
        update_values["plan"] = new_plan
        update_values["monthly_fee_cents"] = new_fee
    if "subscription_status" in data:
        update_values["subscription_status"] = data["subscription_status"]
        if data["subscription_status"] != "suspended":
            update_values["suspended_reason"] = None

    session.execute(
        models.organizations.update()
        .where(models.organizations.c.id == tenant_id)
        .values(**update_values)
    )

    # Sync owner user record if email or name changed
    old_email = org.get("owner_email")
    new_email = data.get("owner_email")
    new_owner_name = data.get("owner_name")
    if old_email and (new_email or new_owner_name):
        owner_user = session.execute(
            sa.select(models.users).where(
                models.users.c.organization_id == tenant_id,
                models.users.c.email == str(old_email).strip().lower(),
            )
        ).mappings().first()
        if owner_user:
            user_updates: dict[str, Any] = {"updated_at": _now()}
            if new_email:
                user_updates["email"] = new_email.strip().lower()
            if new_owner_name:
                user_updates["display_name"] = new_owner_name
            session.execute(
                models.users.update()
                .where(models.users.c.id == owner_user["id"])
                .values(**user_updates)
            )

    session.commit()

    updated_org = session.execute(
        sa.select(models.organizations).where(models.organizations.c.id == tenant_id)
    ).mappings().first()

    return {
        "id": tenant_id,
        "name": updated_org["name"],
        "business_type": updated_org.get("business_type"),
        "owner_name": updated_org.get("owner_name"),
        "owner_email": updated_org.get("owner_email"),
        "owner_phone": updated_org.get("owner_phone"),
        "plan": updated_org.get("plan"),
        "subscription_status": updated_org.get("subscription_status"),
        "monthly_fee_cents": int(updated_org.get("monthly_fee_cents") or 0),
    }


def impersonate_tenant(
    session: Session,
    tenant_id: str,
    actor_superadmin_id: str,
) -> dict[str, Any]:
    """Issues an authentication token for the tenant owner so superadmin can support them."""
    org = session.execute(
        sa.select(models.organizations).where(models.organizations.c.id == tenant_id)
    ).mappings().first()

    if not org:
        raise HTTPException(status_code=404, detail={"code": "tenant_not_found", "message": "Tenant no encontrado"})

    # Find owner user in this organization
    user = session.execute(
        sa.select(models.users)
        .where(models.users.c.organization_id == tenant_id, models.users.c.status == "active")
        .order_by(models.users.c.created_at.asc())
    ).mappings().first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail={"code": "owner_user_not_found", "message": "No se encontró usuario activo para este restaurante"},
        )

    # Find the primary branch of this tenant
    branch = session.execute(
        sa.select(models.branches.c.id, models.branches.c.name)
        .where(models.branches.c.organization_id == tenant_id, models.branches.c.status == "active")
        .order_by(models.branches.c.created_at.asc())
    ).mappings().first()

    # Collect user roles and permissions
    user_roles = session.execute(
        sa.select(models.roles.c.name)
        .select_from(
            models.user_roles.join(models.roles, models.user_roles.c.role_id == models.roles.c.id)
        )
        .where(models.user_roles.c.user_id == str(user["id"]))
    ).scalars().all()

    user_permissions = session.execute(
        sa.select(models.permissions.c.code)
        .select_from(
            models.user_roles.join(models.roles, models.user_roles.c.role_id == models.roles.c.id)
            .join(models.role_permissions, models.role_permissions.c.role_id == models.roles.c.id)
            .join(models.permissions, models.permissions.c.id == models.role_permissions.c.permission_id)
        )
        .where(models.user_roles.c.user_id == str(user["id"]))
    ).scalars().all()

    settings = get_settings()
    token = create_session_token(
        {
            "sub": str(user["id"]),
            "email": str(user["email"]),
            "impersonated_by": actor_superadmin_id,
        },
        settings.secret_key,
    )

    return {
        "token": token,
        "is_impersonating": True,
        "target_user_id": str(user["id"]),
        "target_email": str(user["email"]),
        "target_tenant_id": tenant_id,
        "target_tenant_name": str(org["name"]),
        "target_branch_id": str(branch["id"]) if branch else None,
        "target_branch_name": str(branch["name"]) if branch else None,
        "target_user": {
            "id": str(user["id"]),
            "email": str(user["email"]),
            "display_name": str(user["display_name"]),
            "organization_id": tenant_id,
            "is_superadmin": False,
            "roles": list(user_roles),
            "permissions": list(user_permissions),
            "assigned_branch_id": str(branch["id"]) if branch else None,
        },
    }
