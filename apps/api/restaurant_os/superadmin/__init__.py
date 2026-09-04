"""Superadmin package."""

from .service import (
    create_restaurant_administrator,
    create_tenant_by_admin,
    get_saas_metrics,
    impersonate_tenant,
    list_restaurant_administrators,
    list_tenants,
    migrate_tenant_canonical_roles,
    parse_and_import_menu_ai,
    require_superadmin,
    setup_my_restaurant,
    update_tenant_details,
    update_tenant_plan,
    update_tenant_status,
)

__all__ = [
    "require_superadmin",
    "get_saas_metrics",
    "list_tenants",
    "create_tenant_by_admin",
    "update_tenant_status",
    "update_tenant_plan",
    "update_tenant_details",
    "impersonate_tenant",
    "parse_and_import_menu_ai",
    "list_restaurant_administrators",
    "create_restaurant_administrator",
    "setup_my_restaurant",
    "migrate_tenant_canonical_roles",
]
