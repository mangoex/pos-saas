"""POS-SaaS Multi-Tenant Onboarding and Self-Service Provisioning Domain Service."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from restaurant_os import models
from restaurant_os.auth import (
    PASSWORD_ALGORITHM,
    create_session_token,
    generate_password_salt,
    hash_password,
)
from restaurant_os.config import get_settings
from restaurant_os.operations import (
    BusinessError,
    _assign_default_role_permissions,
    _audit,
    _id,
    _now,
)

UTC = timezone.utc


class SignUpRequest(BaseModel):
    business_name: str = Field(..., min_length=1, max_length=160)
    owner_name: str = Field(..., min_length=1, max_length=160)
    email: str = Field(..., min_length=5, max_length=180)
    password: str = Field(..., min_length=8, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    business_type: str | None = Field(default="general", max_length=32)

    @field_validator("business_name", "owner_name")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Field cannot be blank")
        return clean

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        clean = value.strip().lower()
        if "@" not in clean or "." not in clean.split("@")[-1]:
            raise ValueError("Invalid email format")
        return clean

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


def _generate_slug(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    short_suffix = uuid.uuid4().hex[:6]
    return f"{cleaned[:30]}-{short_suffix}" if cleaned else f"tenant-{short_suffix}"


def signup_tenant(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Atomically provision a new SaaS Tenant, legal entity, branch, owner and starter catalog."""
    req = SignUpRequest(**payload)
    normalized_email = req.email

    # Verify email uniqueness
    existing_user = session.execute(
        sa.select(models.users.c.id).where(models.users.c.email == normalized_email)
    ).first()
    if existing_user:
        raise BusinessError(
            "email_already_registered",
            "El correo electrónico ya se encuentra registrado en la plataforma.",
        )

    now = _now()
    org_id = _id()
    legal_entity_id = _id()
    business_unit_id = _id()
    branch_id = _id()
    warehouse_id = _id()
    admin_role_id = _id()
    supervisor_role_id = _id()
    leader_role_id = _id()
    head_cashier_role_id = _id()
    cashier_role_id = _id()
    user_id = _id()

    # 1. Organizations
    session.execute(
        models.organizations.insert().values(
            id=org_id,
            name=req.business_name,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # 2. Legal Entity
    session.execute(
        models.legal_entities.insert().values(
            id=legal_entity_id,
            organization_id=org_id,
            name=f"{req.business_name} SA de CV",
            tax_id="XAXX010101000",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # 3. Business Unit
    session.execute(
        models.business_units.insert().values(
            id=business_unit_id,
            organization_id=org_id,
            legal_entity_id=legal_entity_id,
            name=req.business_name,
            code="MATRIZ",
            unit_type="restaurant",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # 4. Branch
    session.execute(
        models.branches.insert().values(
            id=branch_id,
            organization_id=org_id,
            legal_entity_id=legal_entity_id,
            business_unit_id=business_unit_id,
            name="Sucursal Matriz",
            code="MATRIZ",
            timezone="America/Mexico_City",
            status="active",
            phone=req.phone or "",
            city="México",
            state="CDMX",
            created_at=now,
            updated_at=now,
        )
    )

    # 5. Warehouse
    session.execute(
        models.warehouses.insert().values(
            id=warehouse_id,
            organization_id=org_id,
            branch_id=branch_id,
            name="Almacén Matriz",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # 6. Canonical 5 Roles in Spanish
    canonical_roles = [
        (admin_role_id, "Administrador de Restaurante", "organization"),
        (supervisor_role_id, "Supervisor", "branch"),
        (leader_role_id, "Líder", "branch"),
        (head_cashier_role_id, "Cajero Jefe", "branch"),
        (cashier_role_id, "Cajero", "branch"),
    ]
    for r_id, r_name, r_scope in canonical_roles:
        session.execute(
            models.roles.insert().values(
                id=r_id,
                organization_id=org_id,
                name=r_name,
                scope=r_scope,
                created_at=now,
            )
        )
        _assign_default_role_permissions(session, r_id, r_name)

    # 7. Role Grants & Permissions for Administrator
    session.execute(
        models.role_authority_grants.insert().values(
            role_id=admin_role_id,
            authority_kind="organization_all_permissions",
            created_at=now,
        )
    )

    all_permissions = session.execute(sa.select(models.permissions.c.id)).scalars().all()
    for perm_id in all_permissions:
        session.execute(
            models.role_permissions.insert().values(
                role_id=admin_role_id,
                permission_id=perm_id,
            )
        )

    # 8. User (Administrator / Owner)
    session.execute(
        models.users.insert().values(
            id=user_id,
            organization_id=org_id,
            email=normalized_email,
            display_name=req.owner_name,
            employee_code=None,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )

    # 9. User Credentials
    salt = generate_password_salt()
    pw_hash = hash_password(req.password, salt)
    session.execute(
        models.user_credentials.insert().values(
            user_id=user_id,
            password_hash=pw_hash,
            password_salt=salt,
            password_algorithm=PASSWORD_ALGORITHM,
            updated_at=now,
        )
    )

    # 10. Assign Role to User
    session.execute(
        models.user_roles.insert().values(
            user_id=user_id,
            role_id=admin_role_id,
            branch_id=branch_id,
        )
    )

    # 11. FacturAPI Default Config
    slug = _generate_slug(req.business_name)
    session.execute(
        models.facturapi_config.insert().values(
            id=_id(),
            organization_id=org_id,
            is_enabled=False,
            environment="sandbox",
            api_key=None,
            organization_legal_name=f"{req.business_name} SA de CV",
            organization_rfc="XAXX010101000",
            organization_tax_system="601",
            organization_zip="06000",
            default_product_sat_key="90101501",
            default_unit_sat_key="E48",
            series="F",
            enable_self_invoicing=True,
            self_invoicing_domain=slug,
            self_invoicing_days_valid=30,
            print_qr_on_ticket=True,
            created_at=now,
            updated_at=now,
        )
    )

    # 12. Seed Starter Catalog
    _seed_starter_catalog(
        session=session,
        organization_id=org_id,
        branch_id=branch_id,
        business_type=req.business_type or "general",
        now=now,
    )

    # 13. Audit Event
    _audit(
        session,
        action="tenant.signup",
        entity_type="organization",
        entity_id=org_id,
        payload={"business_name": req.business_name, "owner_email": normalized_email},
        branch_id=branch_id,
        organization_id=org_id,
        actor_user_id=user_id,
    )

    session.commit()

    token = create_session_token(
        {"sub": user_id, "email": normalized_email, "org_id": org_id},
        get_settings().secret_key,
    )

    return {
        "token": token,
        "user": {
            "id": user_id,
            "email": normalized_email,
            "display_name": req.owner_name,
            "status": "active",
            "organization_id": org_id,
        },
        "organization": {
            "id": org_id,
            "name": req.business_name,
            "status": "active",
        },
        "branch": {
            "id": branch_id,
            "name": "Sucursal Matriz",
            "status": "active",
            "timezone": "America/Mexico_City",
        },
        "roles": ["Owner"],
    }


def _seed_starter_catalog(
    session: Session,
    organization_id: str,
    branch_id: str,
    business_type: str,
    now: datetime,
) -> None:
    btype = (business_type or "general").lower().strip()
    if btype == "blank":
        return

    templates = {
        "taqueria": [
            {
                "category": "Tacos",
                "display_order": 1,
                "products": [
                    {"name": "Taco al Pastor", "price_cents": 2500, "sku": "TAC-PAS"},
                    {"name": "Taco de Asada", "price_cents": 3200, "sku": "TAC-ASA"},
                    {"name": "Gringa al Pastor", "price_cents": 6500, "sku": "GRI-PAS"},
                ],
            },
            {
                "category": "Bebidas",
                "display_order": 2,
                "products": [
                    {"name": "Agua Fresca del Día", "price_cents": 3000, "sku": "BEB-AGU"},
                    {"name": "Refresco 600ml", "price_cents": 3500, "sku": "BEB-REF"},
                ],
            },
        ],
        "cafeteria": [
            {
                "category": "Cafetería",
                "display_order": 1,
                "products": [
                    {"name": "Café Americano 12oz", "price_cents": 4500, "sku": "CAF-AME"},
                    {"name": "Capuchino 12oz", "price_cents": 5500, "sku": "CAF-CAP"},
                    {"name": "Latte Helado 16oz", "price_cents": 6000, "sku": "CAF-LAT"},
                ],
            },
            {
                "category": "Repostería",
                "display_order": 2,
                "products": [
                    {"name": "Croissant de Mantequilla", "price_cents": 4800, "sku": "PAN-CRO"},
                    {"name": "Rebanada Pastel de Zanahoria", "price_cents": 6500, "sku": "PAN-ZAN"},
                ],
            },
        ],
        "pizzeria": [
            {
                "category": "Pizzas",
                "display_order": 1,
                "products": [
                    {"name": "Pizza Pepperoni Mediana", "price_cents": 14900, "sku": "PIZ-PEP"},
                    {"name": "Pizza Hawaiana Mediana", "price_cents": 15900, "sku": "PIZ-HAW"},
                ],
            },
            {
                "category": "Bebidas",
                "display_order": 2,
                "products": [
                    {"name": "Refresco 2L", "price_cents": 5000, "sku": "BEB-2L"},
                ],
            },
        ],
        "hamburgueseria": [
            {
                "category": "Hamburguesas",
                "display_order": 1,
                "products": [
                    {"name": "Hamburguesa Clásica", "price_cents": 11000, "sku": "HAM-CLA"},
                    {"name": "Hamburguesa Especial Tocino", "price_cents": 13500, "sku": "HAM-TOC"},
                    {"name": "Hamburguesa Doble Carne", "price_cents": 16500, "sku": "HAM-DOB"},
                ],
            },
            {
                "category": "Complementos y Bebidas",
                "display_order": 2,
                "products": [
                    {"name": "Papas a la Francesa", "price_cents": 5500, "sku": "COM-PAP"},
                    {"name": "Aros de Cebolla", "price_cents": 6000, "sku": "COM-ARO"},
                    {"name": "Refresco 600ml", "price_cents": 3500, "sku": "BEB-REF"},
                ],
            },
        ],
        "general": [
            {
                "category": "Especialidades",
                "display_order": 1,
                "products": [
                    {"name": "Platillo Especial", "price_cents": 12000, "sku": "ESP-01"},
                    {"name": "Combo del Día", "price_cents": 9500, "sku": "COM-01"},
                ],
            },
            {
                "category": "Bebidas",
                "display_order": 2,
                "products": [
                    {"name": "Bebida de la Casa", "price_cents": 3500, "sku": "BEB-01"},
                ],
            },
        ],
    }

    catalog_data = templates.get(btype, templates["general"])
    import_custom_catalog_for_org(
        session=session,
        organization_id=organization_id,
        branch_id=branch_id,
        catalog_data=catalog_data,
        now=now,
    )


def import_custom_catalog_for_org(
    session: Session,
    organization_id: str,
    branch_id: str | None,
    catalog_data: list[dict[str, Any]],
    mobile_theme: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Import a custom or AI-parsed menu catalog into an organization."""
    if now is None:
        now = _now()

    active_branches = session.execute(
        sa.select(models.branches.c.id).where(
            models.branches.c.organization_id == organization_id,
            models.branches.c.status == "active",
        )
    ).scalars().all()
    if not active_branches and branch_id:
        active_branches = [branch_id]

    created_products = 0

    for idx, cat_data in enumerate(catalog_data):
        cat_name = str(cat_data.get("category") or cat_data.get("name") or "General").strip()
        display_order = int(cat_data.get("display_order") or (idx + 1))

        # Reuse existing category if present
        cat = session.execute(
            sa.select(models.product_categories.c.id).where(
                models.product_categories.c.organization_id == organization_id,
                models.product_categories.c.name == cat_name,
            )
        ).scalars().first()

        if cat:
            cat_id = cat
        else:
            cat_id = _id()
            session.execute(
                models.product_categories.insert().values(
                    id=cat_id,
                    organization_id=organization_id,
                    name=cat_name,
                    display_order=display_order,
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )

        products = cat_data.get("products") or []
        for p_idx, prod_data in enumerate(products):
            prod_name = str(prod_data.get("name") or f"Producto {p_idx + 1}").strip()
            raw_sku = str(prod_data.get("sku") or "").strip()
            if not raw_sku:
                clean_prefix = re.sub(r'[^A-Z0-9]+', '', prod_name.upper())[:4] or "PRD"
                raw_sku = f"{clean_prefix}-{uuid.uuid4().hex[:4].upper()}"

            # Check if product with this SKU or name already exists in org
            existing_prod = session.execute(
                sa.select(models.products.c.id).where(
                    models.products.c.organization_id == organization_id,
                    sa.or_(
                        models.products.c.sku == raw_sku,
                        models.products.c.name == prod_name,
                    ),
                )
            ).scalars().first()

            if existing_prod:
                continue

            prod_id = _id()
            price_id = _id()
            price_cents = int(prod_data.get("price_cents") or 0)
            if price_cents <= 0 and prod_data.get("price") is not None:
                try:
                    price_cents = int(float(prod_data["price"]) * 100)
                except (ValueError, TypeError):
                    price_cents = 0

            desc = str(prod_data.get("description") or f"{prod_name} preparado al momento").strip()
            station = str(prod_data.get("station") or "cocina").lower().strip()
            if station not in ("cocina", "barra", "postres", "packing"):
                station = "cocina"

            session.execute(
                models.products.insert().values(
                    id=prod_id,
                    organization_id=organization_id,
                    category_id=cat_id,
                    name=prod_name,
                    sku=raw_sku,
                    description=desc,
                    station=station,
                    status="active",
                    catalog_scope="organization",
                    source_branch_id=None,
                    created_at=now,
                    updated_at=now,
                )
            )

            session.execute(
                models.price_versions.insert().values(
                    id=price_id,
                    organization_id=organization_id,
                    product_id=prod_id,
                    price_cents=price_cents,
                    currency="MXN",
                    valid_from=now,
                    valid_to=None,
                    created_at=now,
                )
            )

            for b_id in active_branches:
                session.execute(
                    models.branch_product_availability.insert().values(
                        branch_id=b_id,
                        product_id=prod_id,
                        is_available=True,
                        updated_at=now,
                    )
                )

    return {
        "status": "ok",
        "created_products": created_products,
        "mobile_theme": mobile_theme or "light",
    }


def seed_starter_catalog_for_org(
    session: Session,
    organization_id: str,
    branch_id: str | None,
    business_type: str,
) -> dict[str, Any]:
    """Seed or append a starter menu template into an existing organization."""
    now = _now()
    resolved_branch_id = branch_id
    if not resolved_branch_id:
        branch = session.execute(
            sa.select(models.branches.c.id)
            .where(models.branches.c.organization_id == organization_id)
            .order_by(models.branches.c.created_at)
        ).scalars().first()
        resolved_branch_id = branch

    _seed_starter_catalog(
        session=session,
        organization_id=organization_id,
        branch_id=resolved_branch_id or "",
        business_type=business_type,
        now=now,
    )
    session.commit()
    return {"status": "ok", "template": business_type}
