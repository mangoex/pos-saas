from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()


organizations = sa.Table(
    "organizations",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

legal_entities = sa.Table(
    "legal_entities",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("name", sa.String(180), nullable=False),
    sa.Column("tax_id", sa.String(32), nullable=True),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

business_units = sa.Table(
    "business_units",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("legal_entity_id", sa.String(36), sa.ForeignKey("legal_entities.id"), nullable=False),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("code", sa.String(32), nullable=False),
    sa.Column("unit_type", sa.String(32), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "code", name="uq_business_units_organization_code"),
)

branches = sa.Table(
    "branches",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("legal_entity_id", sa.String(36), sa.ForeignKey("legal_entities.id"), nullable=False),
    sa.Column(
        "business_unit_id", sa.String(36), sa.ForeignKey("business_units.id"), nullable=False
    ),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("code", sa.String(32), nullable=False),
    sa.Column("timezone", sa.String(64), nullable=False, server_default="America/Chihuahua"),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("street", sa.String(200), nullable=True),
    sa.Column("exterior_number", sa.String(32), nullable=True),
    sa.Column("interior_number", sa.String(32), nullable=True),
    sa.Column("neighborhood", sa.String(120), nullable=True),
    sa.Column("postal_code", sa.String(12), nullable=True),
    sa.Column("city", sa.String(100), nullable=True, server_default="Culiacán"),
    sa.Column("state", sa.String(100), nullable=True, server_default="Sinaloa"),
    sa.Column("cross_streets", sa.String(250), nullable=True),
    sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
    sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
    sa.Column("phone", sa.String(32), nullable=True),
    sa.Column("google_review_url", sa.String(500), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "code", name="uq_branches_organization_code"),
    sa.Index("uq_branches_organization_id_id", "organization_id", "id", unique=True),
)

employee_code_registry = sa.Table(
    "employee_code_registry",
    metadata,
    sa.Column(
        "organization_id",
        sa.String(36),
        sa.ForeignKey("organizations.id"),
        primary_key=True,
    ),
    sa.Column("employee_code", sa.String(6), primary_key=True),
    sa.Column("subject_type", sa.String(16), nullable=False),
    sa.Column("subject_id", sa.String(36), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "length(employee_code) = 6",
        name="ck_employee_code_registry_length",
    ),
    sa.CheckConstraint(
        "subject_type IN ('user', 'driver')",
        name="ck_employee_code_registry_subject_type",
    ),
    sa.UniqueConstraint(
        "organization_id",
        "subject_type",
        "subject_id",
        name="uq_employee_code_registry_subject",
    ),
    sa.UniqueConstraint(
        "organization_id",
        "employee_code",
        "subject_id",
        name="uq_employee_code_registry_reference",
    ),
)

drivers = sa.Table(
    "drivers",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("employee_code", sa.String(6), nullable=True),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("license_number", sa.String(80), nullable=False),
    sa.Column("motorcycle_plate", sa.String(32), nullable=False),
    sa.Column("phone", sa.String(32), nullable=False),
    sa.Column("address", sa.String(500), nullable=False),
    sa.Column("emergency_contact_name", sa.String(160), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id", "employee_code", name="uq_drivers_organization_employee_code"
    ),
    sa.CheckConstraint(
        "employee_code IS NULL OR length(employee_code) = 6",
        name="ck_drivers_employee_code_length",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "employee_code", "id"],
        [
            "employee_code_registry.organization_id",
            "employee_code_registry.employee_code",
            "employee_code_registry.subject_id",
        ],
        name="fk_drivers_employee_code_registry",
        onupdate="CASCADE",
    ),
)

warehouses = sa.Table(
    "warehouses",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column(
        "branch_id",
        sa.String(36),
        sa.ForeignKey("branches.id"),
        nullable=False,
        unique=True,
    ),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

roles = sa.Table(
    "roles",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("scope", sa.String(32), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "name", name="uq_roles_organization_name"),
)

permissions = sa.Table(
    "permissions",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("code", sa.String(120), nullable=False, unique=True),
    sa.Column("description", sa.String(240), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

users = sa.Table(
    "users",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("email", sa.String(180), nullable=False, unique=True),
    sa.Column("display_name", sa.String(160), nullable=False),
    sa.Column("employee_code", sa.String(6), nullable=True),
    sa.Column("status", sa.String(32), nullable=False, server_default="invited"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id", "employee_code", name="uq_users_organization_employee_code"
    ),
    sa.CheckConstraint(
        "employee_code IS NULL OR length(employee_code) = 6",
        name="ck_users_employee_code_length",
    ),
    sa.ForeignKeyConstraint(
        ["organization_id", "employee_code", "id"],
        [
            "employee_code_registry.organization_id",
            "employee_code_registry.employee_code",
            "employee_code_registry.subject_id",
        ],
        name="fk_users_employee_code_registry",
        onupdate="CASCADE",
    ),
)

user_credentials = sa.Table(
    "user_credentials",
    metadata,
    sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
    sa.Column("password_hash", sa.String(96), nullable=False),
    sa.Column("password_salt", sa.String(32), nullable=False),
    sa.Column("password_algorithm", sa.String(32), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

role_permissions = sa.Table(
    "role_permissions",
    metadata,
    sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id"), primary_key=True),
    sa.Column("permission_id", sa.String(36), sa.ForeignKey("permissions.id"), primary_key=True),
)

role_authority_grants = sa.Table(
    "role_authority_grants",
    metadata,
    sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id"), primary_key=True),
    sa.Column("authority_kind", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "authority_kind = 'organization_all_permissions'",
        name="ck_role_authority_grants_kind",
    ),
)

profile_transition_mappings = sa.Table(
    "profile_transition_mappings",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("legacy_role_id", sa.String(36), sa.ForeignKey("roles.id"), nullable=False),
    sa.Column("target_role_id", sa.String(36), sa.ForeignKey("roles.id"), nullable=False),
    sa.Column("target_branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("mapped_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("role_snapshot", sa.JSON(), nullable=True),
    sa.Column("provenance", sa.String(160), nullable=True),
    sa.Column("create_idempotency_key", sa.String(128), nullable=True),
    sa.Column("apply_idempotency_key", sa.String(128), nullable=True),
    sa.Column("reverse_idempotency_key", sa.String(128), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
        "status IN ('pending', 'mapped', 'reversed')",
        name="ck_profile_transition_mappings_status",
    ),
    sa.Index(
        "uq_profile_transition_mappings_open_target",
        "user_id",
        "target_role_id",
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'mapped')"),
        postgresql_where=sa.text("status IN ('pending', 'mapped')"),
    ),
    sa.UniqueConstraint(
        "organization_id",
        "create_idempotency_key",
        name="uq_profile_transition_mappings_create_key",
    ),
)

user_roles = sa.Table(
    "user_roles",
    metadata,
    sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
    sa.Column("role_id", sa.String(36), sa.ForeignKey("roles.id"), primary_key=True),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
)

audit_events = sa.Table(
    "audit_events",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("action", sa.String(120), nullable=False),
    sa.Column("entity_type", sa.String(120), nullable=False),
    sa.Column("entity_id", sa.String(36), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("correlation_id", sa.String(36), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

# Admin AI stores a reviewed, redacted configuration proposal; it never stores a
# provider transcript, credentials, or an instruction executable by the provider.
admin_ai_proposals = sa.Table(
    "admin_ai_proposals",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
    sa.Column("base_fingerprint", sa.String(64), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("reviewed_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("apply_idempotency_key", sa.String(180), nullable=True, unique=True),
    sa.Column("result", sa.JSON(), nullable=True),
    sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
        "status IN ('DRAFT', 'READY_FOR_REVIEW', 'APPLIED', 'REJECTED', 'EXPIRED')",
        name="ck_admin_ai_proposals_status",
    ),
    sa.Index("ix_admin_ai_proposals_org_status", "organization_id", "status"),
)

attendance_checks = sa.Table(
    "attendance_checks",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("subject_type", sa.String(16), nullable=False),
    sa.Column("subject_id", sa.String(36), nullable=False),
    sa.Column("employee_code_snapshot", sa.String(6), nullable=False),
    sa.Column("employee_name_snapshot", sa.String(160), nullable=False),
    sa.Column("local_date", sa.Date(), nullable=False),
    sa.Column("daily_sequence", sa.Integer(), nullable=False),
    sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.CheckConstraint(
        "subject_type IN ('user', 'driver')", name="ck_attendance_checks_subject_type"
    ),
    sa.CheckConstraint("daily_sequence IN (1, 2)", name="ck_attendance_checks_daily_sequence"),
    sa.UniqueConstraint(
        "organization_id",
        "subject_type",
        "subject_id",
        "local_date",
        "daily_sequence",
        name="uq_attendance_checks_daily_sequence",
    ),
)

product_categories = sa.Table(
    "product_categories",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "name", name="uq_product_categories_org_name"),
)

category_option_groups = sa.Table(
    "category_option_groups",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("category_id", sa.String(36), sa.ForeignKey("product_categories.id"), nullable=False),
    sa.Column("code", sa.String(64), nullable=False),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("selection_mode", sa.String(16), nullable=False, server_default="single"),
    sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("status", sa.String(32), nullable=False, server_default="inactive"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "selection_mode = 'single'", name="ck_category_option_groups_selection_mode"
    ),
    sa.CheckConstraint("is_required", name="ck_category_option_groups_required"),
    sa.CheckConstraint(
        "status IN ('active', 'inactive', 'archived')", name="ck_category_option_groups_status"
    ),
    sa.UniqueConstraint(
        "organization_id", "category_id", name="uq_category_option_groups_organization_category"
    ),
)

category_option_values = sa.Table(
    "category_option_values",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "group_id", sa.String(36), sa.ForeignKey("category_option_groups.id"), nullable=False
    ),
    sa.Column("code", sa.String(64), nullable=False),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "status IN ('active', 'inactive', 'archived')", name="ck_category_option_values_status"
    ),
    sa.UniqueConstraint("group_id", "code", name="uq_category_option_values_group_code"),
)

product_option_value_assignments = sa.Table(
    "product_option_value_assignments",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
    sa.Column(
        "group_id", sa.String(36), sa.ForeignKey("category_option_groups.id"), nullable=False
    ),
    sa.Column(
        "option_value_id",
        sa.String(36),
        sa.ForeignKey("category_option_values.id"),
        nullable=False,
    ),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "product_id", "group_id", name="uq_product_option_value_assignments_product_group"
    ),
)

products = sa.Table(
    "products",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("category_id", sa.String(36), sa.ForeignKey("product_categories.id"), nullable=False),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("sku", sa.String(64), nullable=False),
    sa.Column("description", sa.String(360), nullable=True),
    sa.Column("station", sa.String(32), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("image_url", sa.String(512), nullable=True),
    sa.Column("catalog_scope", sa.String(24), nullable=False, server_default="organization"),
    sa.Column("source_branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
    sa.Column("delivery_price_cents", sa.Integer(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "sku", name="uq_products_org_sku"),
)

modifier_groups = sa.Table(
    "modifier_groups",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("minimum_selections", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("maximum_selections", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("station", sa.String(32), nullable=True),
    sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("product_id", "name", name="uq_modifier_group_product_name"),
)

modifier_options = sa.Table(
    "modifier_options",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("group_id", sa.String(36), sa.ForeignKey("modifier_groups.id"), nullable=False),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("effect_type", sa.String(24), nullable=False),
    sa.Column("price_delta_cents", sa.Integer(), nullable=False, server_default="0"),
    sa.Column(
        "affected_item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=True
    ),
    sa.Column(
        "replacement_item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=True
    ),
    sa.Column("remove_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("add_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("inventory_effect", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("kitchen_text", sa.String(240), nullable=False),
    sa.Column("station", sa.String(32), nullable=True),
    sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("group_id", "name", name="uq_modifier_option_group_name"),
)

branch_modifier_options = sa.Table(
    "branch_modifier_options",
    metadata,
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), primary_key=True),
    sa.Column("option_id", sa.String(36), sa.ForeignKey("modifier_options.id"), primary_key=True),
    sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("price_delta_cents", sa.Integer(), nullable=True),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

ingredient_variations = sa.Table(
    "ingredient_variations",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column(
        "inventory_item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=False
    ),
    sa.Column("add_label", sa.String(120), nullable=False),
    sa.Column("remove_label", sa.String(120), nullable=False),
    sa.Column("portion_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("sale_price_cents", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("station", sa.String(32), nullable=True),
    sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id", "inventory_item_id", name="uq_ingredient_variation_org_item"
    ),
)

order_comment_presets = sa.Table(
    "order_comment_presets",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("text", sa.String(120), nullable=False),
    sa.Column("text_normalized", sa.String(120), nullable=False),
    sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id", "text_normalized", name="uq_order_comment_preset_org_normalized"
    ),
)

order_comment_products = sa.Table(
    "order_comment_products",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "comment_preset_id",
        sa.String(36),
        sa.ForeignKey("order_comment_presets.id"),
        nullable=False,
    ),
    sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("comment_preset_id", "product_id", name="uq_order_comment_product_pair"),
)

ingredient_variation_products = sa.Table(
    "ingredient_variation_products",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "variation_id", sa.String(36), sa.ForeignKey("ingredient_variations.id"), nullable=False
    ),
    sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
    sa.Column("allow_add", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("allow_remove", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("add_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("remove_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("charge_additional", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("add_price_delta_cents", sa.Integer(), nullable=False, server_default="0"),
    sa.Column(
        "add_option_id",
        sa.String(36),
        sa.ForeignKey("modifier_options.id"),
        nullable=True,
        unique=True,
    ),
    sa.Column(
        "remove_option_id",
        sa.String(36),
        sa.ForeignKey("modifier_options.id"),
        nullable=True,
        unique=True,
    ),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("variation_id", "product_id", name="uq_ingredient_variation_product"),
    sa.CheckConstraint("allow_add = 1 OR allow_remove = 1", name="ck_ingredient_variation_actions"),
    sa.CheckConstraint(
        "allow_add = 0 OR add_quantity > 0", name="ck_ingredient_variation_add_quantity"
    ),
    sa.CheckConstraint("remove_quantity >= 0", name="ck_ingredient_variation_remove_quantity"),
    sa.CheckConstraint(
        "charge_additional = 0 OR (allow_add = 1 AND add_price_delta_cents > 0)",
        name="ck_ingredient_variation_charge",
    ),
    sa.CheckConstraint(
        "charge_additional = 1 OR add_price_delta_cents = 0",
        name="ck_ingredient_variation_free_price",
    ),
)

ingredient_variation_commands = sa.Table(
    "ingredient_variation_commands",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column(
        "variation_id", sa.String(36), sa.ForeignKey("ingredient_variations.id"), nullable=False
    ),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("idempotency_key", sa.String(180), nullable=False, unique=True),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("result", sa.JSON(), nullable=True),
    sa.Column("status", sa.String(24), nullable=False, server_default="processing"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

price_versions = sa.Table(
    "price_versions",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
    sa.Column("price_cents", sa.Integer(), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False, server_default="MXN"),
    sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
    sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

branch_product_availability = sa.Table(
    "branch_product_availability",
    metadata,
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), primary_key=True),
    sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), primary_key=True),
    sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

inventory_units = sa.Table(
    "inventory_units",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("code", sa.String(24), nullable=False),
    sa.Column("name", sa.String(80), nullable=False),
    sa.Column("dimension", sa.String(24), nullable=False, server_default="discrete"),
    sa.Column("precision_scale", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "code", name="uq_inventory_units_org_code"),
)

suppliers = sa.Table(
    "suppliers",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("code", sa.String(32), nullable=False),
    sa.Column("commercial_name", sa.String(180), nullable=False),
    sa.Column("legal_name", sa.String(180), nullable=True),
    sa.Column("tax_id", sa.String(16), nullable=True),
    sa.Column("tax_regime", sa.String(12), nullable=True),
    sa.Column("fiscal_address", sa.String(500), nullable=True),
    sa.Column("fiscal_postal_code", sa.String(12), nullable=True),
    sa.Column("municipality", sa.String(100), nullable=True),
    sa.Column("state", sa.String(100), nullable=True),
    sa.Column("country", sa.String(2), nullable=False, server_default="MX"),
    sa.Column("billing_email", sa.String(180), nullable=True),
    sa.Column("phone", sa.String(32), nullable=True),
    sa.Column("supplier_type", sa.String(64), nullable=False, server_default="insumos"),
    sa.Column("credit_days", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("credit_limit", sa.Numeric(18, 2), nullable=True),
    sa.Column("currency", sa.String(3), nullable=False, server_default="MXN"),
    sa.Column("minimum_amount", sa.Numeric(18, 2), nullable=True),
    sa.Column("usual_lead_time_days", sa.Integer(), nullable=True),
    sa.Column("delivery_days", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("payment_methods", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("accounting_reference", sa.String(120), nullable=True),
    sa.Column("notes", sa.String(600), nullable=True),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "code", name="uq_suppliers_organization_code"),
)

supplier_contacts = sa.Table(
    "supplier_contacts",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("supplier_id", sa.String(36), sa.ForeignKey("suppliers.id"), nullable=False),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("position_area", sa.String(120), nullable=True),
    sa.Column("phone", sa.String(32), nullable=True),
    sa.Column("whatsapp", sa.String(32), nullable=True),
    sa.Column("email", sa.String(180), nullable=True),
    sa.Column("contact_type", sa.String(32), nullable=False),
    sa.Column("schedule", sa.String(160), nullable=True),
    sa.Column("primary_for_orders", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("primary_for_billing", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("primary_for_collection", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("notes", sa.String(400), nullable=True),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

supplier_branch_terms = sa.Table(
    "supplier_branch_terms",
    metadata,
    sa.Column("supplier_id", sa.String(36), sa.ForeignKey("suppliers.id"), primary_key=True),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), primary_key=True),
    sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("lead_time_days", sa.Integer(), nullable=True),
    sa.Column("minimum_amount", sa.Numeric(18, 2), nullable=True),
    sa.Column("notes", sa.String(400), nullable=True),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

purchase_presentations = sa.Table(
    "purchase_presentations",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("supplier_id", sa.String(36), sa.ForeignKey("suppliers.id"), nullable=False),
    sa.Column("item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=False),
    sa.Column("code", sa.String(64), nullable=False),
    sa.Column("name", sa.String(180), nullable=False),
    sa.Column("package_type", sa.String(40), nullable=False),
    sa.Column("commercial_quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column(
        "commercial_unit_id", sa.String(36), sa.ForeignKey("inventory_units.id"), nullable=False
    ),
    sa.Column("base_unit_id", sa.String(36), sa.ForeignKey("inventory_units.id"), nullable=False),
    sa.Column("base_unit_yield", sa.Numeric(18, 6), nullable=False),
    sa.Column("gross_content", sa.Numeric(18, 6), nullable=True),
    sa.Column("net_content", sa.Numeric(18, 6), nullable=True),
    sa.Column("usable_content", sa.Numeric(18, 6), nullable=False),
    sa.Column("yield_percent", sa.Numeric(9, 6), nullable=False),
    sa.Column("barcode", sa.String(64), nullable=True),
    sa.Column("tax_rate", sa.Numeric(9, 6), nullable=False, server_default="0"),
    sa.Column("last_net_price", sa.Numeric(18, 6), nullable=False),
    sa.Column("cost_per_base_unit", sa.Numeric(18, 6), nullable=False),
    sa.Column("is_preferred", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "code", name="uq_purchase_presentations_org_code"),
)

supplier_price_history = sa.Table(
    "supplier_price_history",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "presentation_id", sa.String(36), sa.ForeignKey("purchase_presentations.id"), nullable=False
    ),
    sa.Column("supplier_id", sa.String(36), sa.ForeignKey("suppliers.id"), nullable=False),
    sa.Column("net_price", sa.Numeric(18, 6), nullable=False),
    sa.Column("cost_per_base_unit", sa.Numeric(18, 6), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False, server_default="MXN"),
    sa.Column(
        "effective_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column("recorded_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

inventory_items = sa.Table(
    "inventory_items",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("sku", sa.String(64), nullable=False),
    sa.Column("base_unit_id", sa.String(36), sa.ForeignKey("inventory_units.id"), nullable=False),
    sa.Column("item_type", sa.String(32), nullable=False, server_default="ingredient"),
    sa.Column("category_name", sa.String(120), nullable=True),
    sa.Column("catalog_scope", sa.String(24), nullable=False, server_default="organization"),
    sa.Column("source_branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "sku", name="uq_inventory_items_org_sku"),
)

recipes = sa.Table(
    "recipes",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=True),
    sa.Column("output_item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=True),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
    sa.Column("recipe_type", sa.String(24), nullable=False, server_default="sale"),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("yield_quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column("yield_unit_id", sa.String(36), sa.ForeignKey("inventory_units.id"), nullable=False),
    sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
    sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("product_id", "version", name="uq_recipes_product_version"),
    sa.UniqueConstraint("output_item_id", "version", name="uq_recipes_output_item_version"),
)

recipe_components = sa.Table(
    "recipe_components",
    metadata,
    sa.Column("recipe_id", sa.String(36), sa.ForeignKey("recipes.id"), primary_key=True),
    sa.Column("item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), primary_key=True),
    sa.Column("quantity_base_units", sa.Numeric(18, 6), nullable=False),
    sa.Column("unit_id", sa.String(36), sa.ForeignKey("inventory_units.id"), nullable=False),
    sa.Column("net_quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column("waste_rate", sa.Numeric(9, 6), nullable=False, server_default="0"),
    sa.Column("gross_quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("notes", sa.String(400), nullable=True),
)

# PCO-007: the command is retained independently of the immutable recipe
# history so a replay can return the original redacted response safely.
recipe_version_commands = sa.Table(
    "recipe_version_commands",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
    sa.Column("recipe_id", sa.String(36), sa.ForeignKey("recipes.id"), nullable=False),
    sa.Column("idempotency_key", sa.String(180), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("result", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id", "idempotency_key", name="uq_recipe_version_commands_key"
    ),
    sa.CheckConstraint("trim(idempotency_key) != ''", name="ck_recipe_version_commands_key"),
    sa.CheckConstraint("length(request_hash) = 64", name="ck_recipe_version_commands_hash"),
)

recipe_cost_calculations = sa.Table(
    "recipe_cost_calculations",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("recipe_id", sa.String(36), sa.ForeignKey("recipes.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("cost_before_waste", sa.Numeric(18, 6), nullable=False),
    sa.Column("waste_cost", sa.Numeric(18, 6), nullable=False),
    sa.Column("total_cost", sa.Numeric(18, 6), nullable=False),
    sa.Column("cost_per_yield_unit", sa.Numeric(18, 6), nullable=False),
    sa.Column("breakdown", sa.JSON(), nullable=False),
    sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("calculated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
)


production_batches = sa.Table(
    "production_batches",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("warehouse_id", sa.String(36), sa.ForeignKey("warehouses.id"), nullable=False),
    sa.Column("recipe_id", sa.String(36), sa.ForeignKey("recipes.id"), nullable=False),
    sa.Column("output_item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=False),
    sa.Column("lot_code", sa.String(80), nullable=False),
    sa.Column("planned_quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column("actual_quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column("actual_waste_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("total_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("unit_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("idempotency_key", sa.String(180), nullable=True, unique=True),
    sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("confirmed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    sa.UniqueConstraint("branch_id", "lot_code", name="uq_production_batch_branch_lot"),
)

order_line_consumption_snapshots = sa.Table(
    "order_line_consumption_snapshots",
    metadata,
    sa.Column("order_line_id", sa.String(36), sa.ForeignKey("order_lines.id"), primary_key=True),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("recipe_id", sa.String(36), sa.ForeignKey("recipes.id"), nullable=False),
    sa.Column("recipe_version", sa.Integer(), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("components", sa.JSON(), nullable=False),
    sa.Column("modifiers", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("total_theoretical_cost", sa.Numeric(18, 6), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

waste_reasons = sa.Table(
    "waste_reasons",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("code", sa.String(40), nullable=False),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("classification", sa.String(40), nullable=False),
    sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "code", name="uq_waste_reason_organization_code"),
)

waste_records = sa.Table(
    "waste_records",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("warehouse_id", sa.String(36), sa.ForeignKey("warehouses.id"), nullable=False),
    sa.Column("item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=False),
    sa.Column("unit_id", sa.String(36), sa.ForeignKey("inventory_units.id"), nullable=False),
    sa.Column("reason_id", sa.String(36), sa.ForeignKey("waste_reasons.id"), nullable=False),
    sa.Column("stage", sa.String(48), nullable=False),
    sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column("unit_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("total_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("notes", sa.String(600), nullable=True),
    sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
    sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("confirmed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("reversed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("movement_id", sa.String(36), sa.ForeignKey("inventory_movements.id"), nullable=True),
    sa.Column(
        "reversal_movement_id",
        sa.String(36),
        sa.ForeignKey("inventory_movements.id"),
        nullable=True,
    ),
    sa.Column("confirmation_idempotency_key", sa.String(180), nullable=True, unique=True),
    sa.Column("reversal_idempotency_key", sa.String(180), nullable=True, unique=True),
    sa.Column("reversal_reason", sa.String(400), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
)

inventory_transfers = sa.Table(
    "inventory_transfers",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("source_branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("source_warehouse_id", sa.String(36), sa.ForeignKey("warehouses.id"), nullable=False),
    sa.Column("destination_branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column(
        "destination_warehouse_id", sa.String(36), sa.ForeignKey("warehouses.id"), nullable=False
    ),
    sa.Column("folio", sa.String(64), nullable=False),
    sa.Column("status", sa.String(40), nullable=False, server_default="draft"),
    sa.Column("notes", sa.String(600), nullable=True),
    sa.Column("cancellation_reason", sa.String(400), nullable=True),
    sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("sent_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("received_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("cancelled_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("send_idempotency_key", sa.String(180), nullable=True, unique=True),
    sa.Column("receive_idempotency_key", sa.String(180), nullable=True, unique=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    sa.UniqueConstraint("source_branch_id", "folio", name="uq_inventory_transfer_source_folio"),
)

inventory_transfer_lines = sa.Table(
    "inventory_transfer_lines",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "transfer_id", sa.String(36), sa.ForeignKey("inventory_transfers.id"), nullable=False
    ),
    sa.Column("item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=False),
    sa.Column("unit_id", sa.String(36), sa.ForeignKey("inventory_units.id"), nullable=False),
    sa.Column("requested_quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column("sent_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("received_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("difference_quantity", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("unit_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("sent_total_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("received_total_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("difference_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("difference_reason", sa.String(400), nullable=True),
    sa.Column("condition", sa.String(40), nullable=True),
    sa.Column("notes", sa.String(600), nullable=True),
    sa.Column(
        "out_movement_id", sa.String(36), sa.ForeignKey("inventory_movements.id"), nullable=True
    ),
    sa.Column(
        "in_movement_id", sa.String(36), sa.ForeignKey("inventory_movements.id"), nullable=True
    ),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("transfer_id", "item_id", name="uq_inventory_transfer_line_item"),
)

physical_count_sessions = sa.Table(
    "physical_count_sessions",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("warehouse_id", sa.String(36), sa.ForeignKey("warehouses.id"), nullable=False),
    sa.Column("folio", sa.String(64), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="counting"),
    sa.Column("scope", sa.String(32), nullable=False, server_default="all_active"),
    sa.Column("notes", sa.String(600), nullable=True),
    sa.Column("cancellation_reason", sa.String(400), nullable=True),
    sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("submitted_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("approved_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("closed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("cancelled_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("approval_idempotency_key", sa.String(180), nullable=True, unique=True),
    sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    sa.UniqueConstraint("branch_id", "folio", name="uq_physical_count_branch_folio"),
)

physical_count_lines = sa.Table(
    "physical_count_lines",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "session_id", sa.String(36), sa.ForeignKey("physical_count_sessions.id"), nullable=False
    ),
    sa.Column("item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=False),
    sa.Column("unit_id", sa.String(36), sa.ForeignKey("inventory_units.id"), nullable=False),
    sa.Column("theoretical_quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column("snapshot_unit_cost", sa.Numeric(18, 6), nullable=False),
    sa.Column("snapshot_value", sa.Numeric(18, 6), nullable=False),
    sa.Column("counted_quantity", sa.Numeric(18, 6), nullable=True),
    sa.Column("snapshot_difference", sa.Numeric(18, 6), nullable=True),
    sa.Column("approval_ledger_quantity", sa.Numeric(18, 6), nullable=True),
    sa.Column("adjustment_quantity", sa.Numeric(18, 6), nullable=True),
    sa.Column("adjustment_unit_cost", sa.Numeric(18, 6), nullable=True),
    sa.Column("adjustment_cost", sa.Numeric(18, 6), nullable=True),
    sa.Column(
        "adjustment_movement_id",
        sa.String(36),
        sa.ForeignKey("inventory_movements.id"),
        nullable=True,
    ),
    sa.Column("captured_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("notes", sa.String(600), nullable=True),
    sa.UniqueConstraint("session_id", "item_id", name="uq_physical_count_line_item"),
)

inventory_movements = sa.Table(
    "inventory_movements",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("warehouse_id", sa.String(36), sa.ForeignKey("warehouses.id"), nullable=False),
    sa.Column("item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=False),
    sa.Column("movement_type", sa.String(48), nullable=False),
    sa.Column("quantity_delta", sa.Numeric(18, 6), nullable=False),
    sa.Column("unit_id", sa.String(36), sa.ForeignKey("inventory_units.id"), nullable=False),
    sa.Column("unit_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("total_cost", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column(
        "effective_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("document_type", sa.String(48), nullable=True),
    sa.Column("document_id", sa.String(36), nullable=True),
    sa.Column("reference", sa.String(120), nullable=True),
    sa.Column("reason", sa.String(240), nullable=False),
    sa.Column("notes", sa.String(600), nullable=True),
    sa.Column("idempotency_key", sa.String(180), nullable=True, unique=True),
    sa.Column("status", sa.String(32), nullable=False, server_default="confirmed"),
    sa.Column(
        "reversal_of_id", sa.String(36), sa.ForeignKey("inventory_movements.id"), nullable=True
    ),
    sa.Column("source_type", sa.String(80), nullable=True),
    sa.Column("source_id", sa.String(36), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

cash_movement_concepts = sa.Table(
    "cash_movement_concepts",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("code", sa.String(64), nullable=False),
    sa.Column("status", sa.String(24), nullable=False, server_default="active"),
    sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('active', 'archived')", name="ck_cash_concepts_status"),
    sa.UniqueConstraint("organization_id", "code", name="uq_cash_concepts_org_code"),
)

cash_movement_concept_versions = sa.Table(
    "cash_movement_concept_versions",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "concept_id",
        sa.String(36),
        sa.ForeignKey("cash_movement_concepts.id"),
        nullable=False,
    ),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("allowed_movement_type", sa.String(16), nullable=False),
    sa.Column("requires_reference", sa.Boolean(), nullable=False),
    sa.Column("requires_evidence", sa.Boolean(), nullable=False),
    sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("version > 0", name="ck_cash_concept_versions_positive"),
    sa.CheckConstraint(
        "allowed_movement_type IN ('deposit', 'withdrawal', 'both')",
        name="ck_cash_concept_versions_type",
    ),
    sa.CheckConstraint("requires_reference", name="ck_cash_concept_versions_reference"),
    sa.CheckConstraint("requires_evidence", name="ck_cash_concept_versions_evidence"),
    sa.UniqueConstraint("concept_id", "version", name="uq_cash_concept_versions_number"),
)

cash_concept_commands = sa.Table(
    "cash_concept_commands",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column(
        "target_concept_id",
        sa.String(36),
        sa.ForeignKey("cash_movement_concepts.id"),
        nullable=False,
    ),
    sa.Column("command_type", sa.String(24), nullable=False),
    sa.Column("idempotency_key", sa.String(180), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("result", sa.JSON(), nullable=False),
    sa.Column("status", sa.String(24), nullable=False, server_default="completed"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "command_type IN ('create', 'version', 'archive')",
        name="ck_cash_concept_commands_type",
    ),
    sa.CheckConstraint("status = 'completed'", name="ck_cash_concept_commands_status"),
    sa.UniqueConstraint(
        "organization_id", "idempotency_key", name="uq_cash_concept_commands_org_key"
    ),
)

cash_movements = sa.Table(
    "cash_movements",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("cash_shift_id", sa.String(36), sa.ForeignKey("cash_shifts.id"), nullable=False),
    sa.Column("movement_type", sa.String(32), nullable=False),
    sa.Column("amount_cents", sa.Integer(), nullable=False),
    sa.Column("reason_code", sa.String(48), nullable=False),
    sa.Column("reason", sa.String(240), nullable=False),
    sa.Column("source_type", sa.String(48), nullable=True),
    sa.Column("source_id", sa.String(36), nullable=True),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("idempotency_key", sa.String(180), nullable=False, unique=True),
    sa.Column("status", sa.String(32), nullable=False, server_default="confirmed"),
    sa.Column("reversal_of_id", sa.String(36), sa.ForeignKey("cash_movements.id"), nullable=True),
    sa.Column(
        "concept_id", sa.String(36), sa.ForeignKey("cash_movement_concepts.id"), nullable=True
    ),
    sa.Column(
        "concept_version_id",
        sa.String(36),
        sa.ForeignKey("cash_movement_concept_versions.id"),
        nullable=True,
    ),
    sa.Column("concept_snapshot", sa.JSON(), nullable=True),
    sa.Column("reference", sa.String(600), nullable=True),
    sa.Column("evidence_refs", sa.JSON(), nullable=True),
    sa.Column(
        "compensates_movement_id",
        sa.String(36),
        sa.ForeignKey("cash_movements.id"),
        nullable=True,
    ),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

sa.Index(
    "uq_cash_movements_compensates_movement",
    cash_movements.c.compensates_movement_id,
    unique=True,
    sqlite_where=cash_movements.c.compensates_movement_id.is_not(None),
    postgresql_where=cash_movements.c.compensates_movement_id.is_not(None),
)

sa.Index(
    "ix_cash_movements_branch_shift_created",
    cash_movements.c.branch_id,
    cash_movements.c.cash_shift_id,
    cash_movements.c.created_at,
)

cash_movement_commands = sa.Table(
    "cash_movement_commands",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column(
        "target_movement_id", sa.String(36), sa.ForeignKey("cash_movements.id"), nullable=True
    ),
    sa.Column("command_type", sa.String(24), nullable=False),
    sa.Column("idempotency_key", sa.String(180), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("result", sa.JSON(), nullable=False),
    sa.Column("status", sa.String(24), nullable=False, server_default="completed"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "command_type IN ('create', 'compensate')", name="ck_cash_movement_commands_type"
    ),
    sa.CheckConstraint("status = 'completed'", name="ck_cash_movement_commands_status"),
    sa.UniqueConstraint(
        "organization_id", "idempotency_key", name="uq_cash_movement_commands_org_key"
    ),
)

purchase_documents = sa.Table(
    "purchase_documents",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("supplier_id", sa.String(36), sa.ForeignKey("suppliers.id"), nullable=False),
    sa.Column("document_type", sa.String(32), nullable=False),
    sa.Column("folio", sa.String(80), nullable=False),
    sa.Column("document_date", sa.DateTime(timezone=True), nullable=False),
    sa.Column("subtotal", sa.Numeric(18, 6), nullable=False),
    sa.Column("discount_total", sa.Numeric(18, 6), nullable=False),
    sa.Column("tax_total", sa.Numeric(18, 6), nullable=False),
    sa.Column("freight_total", sa.Numeric(18, 6), nullable=False, server_default="0"),
    sa.Column("total", sa.Numeric(18, 6), nullable=False),
    sa.Column("payment_method", sa.String(32), nullable=False),
    sa.Column("paid_from_cash", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("cash_movement_id", sa.String(36), sa.ForeignKey("cash_movements.id"), nullable=True),
    sa.Column("evidence_url", sa.String(600), nullable=True),
    sa.Column("notes", sa.String(600), nullable=True),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("confirmed_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("cancelled_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("confirmation_idempotency_key", sa.String(180), nullable=True, unique=True),
    sa.Column("cancellation_reason", sa.String(400), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    sa.UniqueConstraint(
        "branch_id", "supplier_id", "document_type", "folio", name="uq_purchase_document_identity"
    ),
)

# PCO-007 reporting indexes mirror migration 0042 for isolated metadata schemas.
sa.Index(
    "ix_pco007_purchase_report",
    purchase_documents.c.organization_id,
    purchase_documents.c.branch_id,
    purchase_documents.c.confirmed_at,
)
sa.Index(
    "ix_pco007_purchase_cancelled_report",
    purchase_documents.c.organization_id,
    purchase_documents.c.branch_id,
    purchase_documents.c.cancelled_at,
)
sa.Index(
    "ix_pco007_cash_report",
    cash_movements.c.organization_id,
    cash_movements.c.branch_id,
    cash_movements.c.created_at,
)
sa.Index(
    "ix_pco007_recipe_snapshot",
    order_line_consumption_snapshots.c.order_id,
    order_line_consumption_snapshots.c.recipe_id,
)

purchase_document_lines = sa.Table(
    "purchase_document_lines",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "purchase_document_id",
        sa.String(36),
        sa.ForeignKey("purchase_documents.id"),
        nullable=False,
    ),
    sa.Column(
        "presentation_id", sa.String(36), sa.ForeignKey("purchase_presentations.id"), nullable=False
    ),
    sa.Column("item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=False),
    sa.Column("presentation_snapshot", sa.JSON(), nullable=False),
    sa.Column("presentation_quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column("base_quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
    sa.Column("discount", sa.Numeric(18, 6), nullable=False),
    sa.Column("tax", sa.Numeric(18, 6), nullable=False),
    sa.Column("line_total", sa.Numeric(18, 6), nullable=False),
    sa.Column("inventory_cost", sa.Numeric(18, 6), nullable=False),
    sa.Column("cost_per_base_unit", sa.Numeric(18, 6), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

inventory_cost_states = sa.Table(
    "inventory_cost_states",
    metadata,
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), primary_key=True),
    sa.Column("warehouse_id", sa.String(36), sa.ForeignKey("warehouses.id"), primary_key=True),
    sa.Column("item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), primary_key=True),
    sa.Column("quantity_on_hand", sa.Numeric(18, 6), nullable=False),
    sa.Column("average_unit_cost", sa.Numeric(18, 6), nullable=False),
    sa.Column("last_unit_cost", sa.Numeric(18, 6), nullable=False),
    sa.Column("last_supplier_id", sa.String(36), sa.ForeignKey("suppliers.id"), nullable=True),
    sa.Column("last_cost_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

cash_shifts = sa.Table(
    "cash_shifts",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("register_code", sa.String(32), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("opening_cash_cents", sa.Integer(), nullable=False),
    # Nullable only while historical shifts await the one-authoritative-source backfill.
    sa.Column("cashier_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

sa.Index(
    "uq_cash_shifts_open_register",
    cash_shifts.c.branch_id,
    cash_shifts.c.register_code,
    unique=True,
    sqlite_where=sa.func.upper(cash_shifts.c.status).in_(("OPEN", "CLOSING")),
    postgresql_where=sa.func.upper(cash_shifts.c.status).in_(("OPEN", "CLOSING")),
)
sa.Index("ix_cash_shifts_cashier", cash_shifts.c.cashier_user_id)

customers = sa.Table(
    "customers",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("email", sa.String(180), nullable=True),
    sa.Column("customer_type", sa.String(24), nullable=False, server_default="person"),
    sa.Column("customer_segment", sa.String(48), nullable=True),
    sa.Column("notes", sa.String(600), nullable=True),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("origin_branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

customer_phones = sa.Table(
    "customer_phones",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
    sa.Column("captured_number", sa.String(32), nullable=False),
    sa.Column("normalized_number", sa.String(20), nullable=False),
    sa.Column("phone_type", sa.String(24), nullable=False, server_default="mobile"),
    sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("whatsapp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

customer_addresses = sa.Table(
    "customer_addresses",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
    sa.Column("alias", sa.String(60), nullable=False),
    sa.Column("street", sa.String(180), nullable=False),
    sa.Column("exterior_number", sa.String(32), nullable=False),
    sa.Column("interior_number", sa.String(32), nullable=True),
    sa.Column("neighborhood", sa.String(120), nullable=False),
    sa.Column("postal_code", sa.String(12), nullable=False),
    sa.Column("city", sa.String(100), nullable=False),
    sa.Column("municipality", sa.String(100), nullable=False),
    sa.Column("state", sa.String(100), nullable=False),
    sa.Column("country", sa.String(2), nullable=False, server_default="MX"),
    sa.Column("cross_streets", sa.String(240), nullable=True),
    sa.Column("references", sa.String(600), nullable=True),
    sa.Column("delivery_instructions", sa.String(600), nullable=True),
    sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
    sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
    sa.Column("delivery_zone_id", sa.String(36), nullable=True),
    sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

legacy_import_batches = sa.Table(
    "legacy_import_batches",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("source_system", sa.String(80), nullable=False),
    sa.Column("manifest_checksum", sa.String(64), nullable=False),
    sa.Column("manifest", sa.JSON(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="loading"),
    sa.Column("summary", sa.JSON(), nullable=False, server_default="{}"),
    sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id",
        "branch_id",
        "source_system",
        "manifest_checksum",
        name="uq_legacy_import_batch_manifest",
    ),
)

legacy_import_records = sa.Table(
    "legacy_import_records",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("batch_id", sa.String(36), sa.ForeignKey("legacy_import_batches.id"), nullable=False),
    sa.Column("entity_type", sa.String(32), nullable=False),
    sa.Column("source_key", sa.String(160), nullable=False),
    sa.Column("source_row", sa.Integer(), nullable=False),
    sa.Column("raw_payload", sa.JSON(), nullable=False),
    sa.Column("normalized_payload", sa.JSON(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("reason_code", sa.String(80), nullable=True),
    sa.Column("target_entity_type", sa.String(80), nullable=True),
    sa.Column("target_entity_id", sa.String(36), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "batch_id", "entity_type", "source_key", name="uq_legacy_import_record_source"
    ),
)

catalog_cleanup_runs = sa.Table(
    "catalog_cleanup_runs",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("revision", sa.String(80), nullable=False, unique=True),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("summary", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

catalog_cleanup_records = sa.Table(
    "catalog_cleanup_records",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("revision", sa.String(80), nullable=False),
    sa.Column("entity_type", sa.String(64), nullable=False),
    sa.Column("entity_id", sa.String(120), nullable=False),
    sa.Column("action", sa.String(32), nullable=False),
    sa.Column("original_payload", sa.JSON(), nullable=False),
    sa.Column("applied_payload", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "revision",
        "entity_type",
        "entity_id",
        name="uq_catalog_cleanup_record_entity",
    ),
)

customer_tax_profiles = sa.Table(
    "customer_tax_profiles",
    metadata,
    sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), primary_key=True),
    sa.Column("legal_name", sa.String(180), nullable=False),
    sa.Column("tax_id", sa.String(16), nullable=False),
    sa.Column("tax_regime", sa.String(12), nullable=False),
    sa.Column("fiscal_postal_code", sa.String(12), nullable=False),
    sa.Column("cfdi_use", sa.String(12), nullable=True),
    sa.Column("billing_email", sa.String(180), nullable=True),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

orders = sa.Table(
    "orders",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    # Only the authenticated public-intent acceptance path may create the
    # explicitly marked, no-cash-shift operational order.
    sa.Column("cash_shift_id", sa.String(36), sa.ForeignKey("cash_shifts.id"), nullable=True),
    sa.Column(
        "public_order_intent_id",
        sa.String(36),
        sa.ForeignKey("public_order_intents.id"),
        nullable=True,
        unique=True,
    ),
    sa.Column("public_order_intent_status", sa.String(24), nullable=True),
    sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=True),
    sa.Column("customer_snapshot", sa.JSON(), nullable=True),
    sa.Column("delivery_address_snapshot", sa.JSON(), nullable=True),
    sa.Column("folio", sa.String(64), nullable=False),
    sa.Column("channel", sa.String(32), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("total_cents", sa.Integer(), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False, server_default="MXN"),
    sa.Column("owner_name", sa.String(160), nullable=True),
    sa.Column("order_type", sa.String(32), nullable=False, server_default="dine-in"),
    sa.Column("payment_method_intent", sa.String(32), nullable=True),
    sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    sa.UniqueConstraint("branch_id", "folio", name="uq_orders_branch_folio"),
    sa.CheckConstraint(
        "cash_shift_id IS NOT NULL OR channel IN ('UBER_EATS', 'DIDI_FOOD', 'RAPPI') "
        "OR (channel = 'PUBLIC_INTENT' "
        "AND public_order_intent_id IS NOT NULL "
        "AND public_order_intent_status = 'ACCEPTED')",
        name="ck_orders_cash_shift_required_except_public_intent",
    ),
)

public_order_keys = sa.Table(
    "public_order_keys",
    metadata,
    sa.Column("public_key", sa.String(160), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("status", sa.String(16), nullable=False, server_default="active"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('active', 'retired')", name="ck_public_order_keys_status"),
)
sa.Index(
    "uq_public_order_keys_one_active_branch",
    public_order_keys.c.branch_id,
    unique=True,
    sqlite_where=public_order_keys.c.status == "active",
    postgresql_where=public_order_keys.c.status == "active",
)

public_order_intents = sa.Table(
    "public_order_intents",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column(
        "public_key", sa.String(160), sa.ForeignKey("public_order_keys.public_key"), nullable=False
    ),
    sa.Column("public_reference", sa.String(64), nullable=False, unique=True),
    sa.Column("correlation_id", sa.String(64), nullable=False, unique=True),
    sa.Column("status", sa.String(24), nullable=False, server_default="PENDING_REVIEW"),
    sa.Column("customer_snapshot", sa.JSON(), nullable=False),
    sa.Column("delivery_address_snapshot", sa.JSON(), nullable=True),
    sa.Column("order_type", sa.String(32), nullable=False),
    sa.Column("order_notes", sa.String(500), nullable=True),
    sa.Column("total_cents", sa.Integer(), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False, server_default="MXN"),
    sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    sa.Column(
        "accepted_order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=True, unique=True
    ),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("decision_reason", sa.String(500), nullable=True),
    sa.Column("decided_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.CheckConstraint(
        "status IN ('PENDING_REVIEW', 'ACCEPTED', 'REJECTED', 'EXPIRED')",
        name="ck_public_order_intents_status",
    ),
    sa.CheckConstraint(
        "total_cents >= 0 AND version > 0", name="ck_public_order_intents_amount_version"
    ),
)
sa.UniqueConstraint(
    public_order_intents.c.id,
    public_order_intents.c.status,
    name="uq_public_order_intent_id_status",
)
orders.append_constraint(
    sa.ForeignKeyConstraint(
        ["public_order_intent_id", "public_order_intent_status"],
        ["public_order_intents.id", "public_order_intents.status"],
        name="fk_orders_public_order_intent_accepted",
    )
)
sa.Index(
    "ix_public_order_intents_branch_status",
    public_order_intents.c.branch_id,
    public_order_intents.c.status,
)

public_order_intent_lines = sa.Table(
    "public_order_intent_lines",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("intent_id", sa.String(36), sa.ForeignKey("public_order_intents.id"), nullable=False),
    sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
    sa.Column("product_name", sa.String(160), nullable=False),
    sa.Column("quantity", sa.Integer(), nullable=False),
    sa.Column("unit_price_cents", sa.Integer(), nullable=False),
    sa.Column("line_total_cents", sa.Integer(), nullable=False),
    sa.Column("station", sa.String(32), nullable=False),
    sa.Column("selected_modifiers", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("modifier_total_cents", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("line_notes", sa.String(500), nullable=True),
    sa.Column("family_id_snapshot", sa.String(36), nullable=False),
    sa.Column("family_name_snapshot", sa.String(160), nullable=False),
    sa.Column("consumption_snapshot", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "quantity > 0 AND unit_price_cents >= 0 AND line_total_cents >= 0",
        name="ck_public_order_intent_lines_amounts",
    ),
)

public_order_intent_commands = sa.Table(
    "public_order_intent_commands",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("intent_id", sa.String(36), sa.ForeignKey("public_order_intents.id"), nullable=True),
    sa.Column("command_type", sa.String(16), nullable=False),
    sa.Column("idempotency_key", sa.String(160), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("result", sa.JSON(), nullable=False),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "command_type IN ('create', 'accept', 'reject')",
        name="ck_public_order_intent_commands_type",
    ),
    sa.UniqueConstraint(
        "organization_id",
        "command_type",
        "idempotency_key",
        name="uq_public_order_intent_commands_key",
    ),
)

order_outbox_events = sa.Table(
    "order_outbox_events",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("event_type", sa.String(80), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
)
sa.Index(
    "ix_order_outbox_events_unpublished",
    order_outbox_events.c.branch_id,
    order_outbox_events.c.published_at,
)

delivery_assignments = sa.Table(
    "delivery_assignments",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False, unique=True),
    sa.Column("driver_id", sa.String(36), sa.ForeignKey("drivers.id"), nullable=False),
    sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=True),
    sa.Column("driver_name_snapshot", sa.String(160), nullable=False),
    sa.Column("customer_name_snapshot", sa.String(160), nullable=False),
    sa.Column("delivery_address_snapshot", sa.JSON(), nullable=False),
    sa.Column("order_total_cents", sa.Integer(), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("line_count", sa.Integer(), nullable=False),
    sa.Column("item_quantity", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="ASSIGNED"),
    sa.Column("assigned_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
)

order_lines = sa.Table(
    "order_lines",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
    sa.Column("product_name", sa.String(160), nullable=False),
    sa.Column("quantity", sa.Integer(), nullable=False),
    sa.Column("unit_price_cents", sa.Integer(), nullable=False),
    sa.Column("line_total_cents", sa.Integer(), nullable=False),
    sa.Column("station", sa.String(32), nullable=False),
    sa.Column("selected_modifiers", sa.JSON(), nullable=False, server_default="[]"),
    sa.Column("modifier_total_cents", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("line_notes", sa.String(500), nullable=True),
    sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("supersedes_line_id", sa.String(36), sa.ForeignKey("order_lines.id"), nullable=True),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("family_id_snapshot", sa.String(36), nullable=False),
    sa.Column("family_name_snapshot", sa.String(160), nullable=False),
    sa.Column("family_snapshot_source", sa.String(32), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "family_snapshot_source IN ('captured', 'legacy_catalog_backfill')",
        name="ck_order_lines_family_snapshot_source",
    ),
    sa.CheckConstraint(
        "trim(family_id_snapshot) != '' AND trim(family_name_snapshot) != ''",
        name="ck_order_lines_family_snapshot_complete",
    ),
)

order_amendments = sa.Table(
    "order_amendments",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("sequence", sa.Integer(), nullable=False),
    sa.Column("expected_version", sa.Integer(), nullable=False),
    sa.Column("resulting_version", sa.Integer(), nullable=False),
    sa.Column("before_snapshot", sa.JSON(), nullable=False),
    sa.Column("after_snapshot", sa.JSON(), nullable=False),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("idempotency_key", sa.String(160), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("order_id", "sequence", name="uq_order_amendment_sequence"),
    sa.UniqueConstraint("order_id", "idempotency_key", name="uq_order_amendment_idempotency"),
)

order_events = sa.Table(
    "order_events",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("event_type", sa.String(80), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

production_tasks = sa.Table(
    "production_tasks",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("order_line_id", sa.String(36), sa.ForeignKey("order_lines.id"), nullable=False),
    sa.Column("station", sa.String(32), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("product_name", sa.String(160), nullable=False),
    sa.Column("quantity", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
)

payments = sa.Table(
    "payments",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("cash_shift_id", sa.String(36), sa.ForeignKey("cash_shifts.id"), nullable=False),
    sa.Column("method", sa.String(32), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("amount_cents", sa.Integer(), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False, server_default="MXN"),
    sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

sa.Index(
    "uq_payments_confirmed_order",
    payments.c.order_id,
    unique=True,
    sqlite_where=payments.c.status == "CONFIRMED",
    postgresql_where=payments.c.status == "CONFIRMED",
)

payment_commands = sa.Table(
    "payment_commands",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("payment_id", sa.String(36), sa.ForeignKey("payments.id"), nullable=False),
    sa.Column("idempotency_key", sa.String(160), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("response_snapshot", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_payment_command_org_key"),
    sa.CheckConstraint("length(request_hash) = 64", name="ck_payment_command_hash"),
)

sa.Index(
    "ix_payment_commands_scope_created",
    payment_commands.c.organization_id,
    payment_commands.c.branch_id,
    payment_commands.c.created_at,
)

cash_shift_closures = sa.Table(
    "cash_shift_closures",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column(
        "cash_shift_id", sa.String(36), sa.ForeignKey("cash_shifts.id"), nullable=False, unique=True
    ),
    sa.Column("register_code_snapshot", sa.String(32), nullable=False),
    sa.Column("closed_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("summary_snapshot", sa.JSON(), nullable=False),
    sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "trim(register_code_snapshot) != ''", name="ck_cash_shift_closures_register"
    ),
)

cash_shift_commands = sa.Table(
    "cash_shift_commands",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("cash_shift_id", sa.String(36), sa.ForeignKey("cash_shifts.id"), nullable=True),
    sa.Column("command_type", sa.String(16), nullable=False),
    sa.Column("idempotency_key", sa.String(180), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("result", sa.JSON(), nullable=False),
    sa.Column("status", sa.String(24), nullable=False, server_default="completed"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("command_type IN ('open', 'close')", name="ck_cash_shift_commands_type"),
    sa.CheckConstraint("status = 'completed'", name="ck_cash_shift_commands_status"),
    sa.CheckConstraint(
        "trim(idempotency_key) != ''", name="ck_cash_shift_commands_idempotency_key"
    ),
    sa.CheckConstraint("length(request_hash) = 64", name="ck_cash_shift_commands_request_hash"),
    sa.UniqueConstraint(
        "organization_id", "idempotency_key", name="uq_cash_shift_commands_org_key"
    ),
)

# PCO-006 is intentionally separate from the legacy cash_shift_cuts report.  These rows are
# append-only snapshots; corrections are represented by a linked compensation instead of updates.
user_cash_cuts = sa.Table(
    "user_cash_cuts",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("cash_shift_id", sa.String(36), sa.ForeignKey("cash_shifts.id"), nullable=False),
    sa.Column("register_code_snapshot", sa.String(32), nullable=False),
    sa.Column("cashier_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("timezone", sa.String(64), nullable=False),
    sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
    sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("opening_cash_cents", sa.Integer(), nullable=False),
    sa.Column("cash_payment_cents", sa.Integer(), nullable=True),
    sa.Column("deposit_cents", sa.Integer(), nullable=True),
    sa.Column("withdrawal_cents", sa.Integer(), nullable=True),
    sa.Column("expected_cash_cents", sa.Integer(), nullable=True),
    sa.Column("counted_cash_cents", sa.Integer(), nullable=True),
    sa.Column("difference_cents", sa.Integer(), nullable=True),
    sa.Column("tolerance_cents", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("finalized_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("counted_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
        "status IN ('DRAFT','COUNTED','FINALIZED')",
        name="ck_user_cash_cuts_status",
    ),
    sa.CheckConstraint("period_start < period_end", name="ck_user_cash_cuts_period"),
    sa.CheckConstraint("tolerance_cents = 0", name="ck_user_cash_cuts_tolerance"),
    sa.CheckConstraint(
        "opening_cash_cents >= 0 AND "
        "(cash_payment_cents IS NULL OR cash_payment_cents >= 0) AND "
        "(deposit_cents IS NULL OR deposit_cents >= 0) AND "
        "(withdrawal_cents IS NULL OR withdrawal_cents >= 0) AND "
        "(counted_cash_cents IS NULL OR counted_cash_cents >= 0) AND version > 0",
        name="ck_user_cash_cuts_amounts",
    ),
    sa.UniqueConstraint("cash_shift_id", name="uq_user_cash_cuts_shift"),
)
sa.Index(
    "ix_user_cash_cuts_org_branch_period",
    user_cash_cuts.c.organization_id,
    user_cash_cuts.c.branch_id,
    user_cash_cuts.c.period_start,
)

user_cash_cut_operations = sa.Table(
    "user_cash_cut_operations",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("cash_cut_id", sa.String(36), sa.ForeignKey("user_cash_cuts.id"), nullable=False),
    sa.Column("operation_type", sa.String(16), nullable=False),
    sa.Column("operation_id", sa.String(36), nullable=False),
    sa.Column("signed_amount_cents", sa.Integer(), nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "operation_type IN ('PAYMENT','MOVEMENT')",
        name="ck_user_cash_cut_operations_type",
    ),
    sa.UniqueConstraint(
        "organization_id",
        "operation_type",
        "operation_id",
        name="uq_user_cash_cut_operation_global",
    ),
)

user_cash_cut_commands = sa.Table(
    "user_cash_cut_commands",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("cash_cut_id", sa.String(36), sa.ForeignKey("user_cash_cuts.id"), nullable=True),
    sa.Column("command_type", sa.String(24), nullable=False),
    sa.Column("idempotency_key", sa.String(180), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("result", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_user_cash_cut_commands_key"),
    sa.CheckConstraint(
        "command_type IN ('create','count','finalize','reopen_request',"
        "'reopen_approved','reopen_rejected','reopen_compensate')",
        name="ck_user_cash_cut_commands_type",
    ),
    sa.CheckConstraint("trim(idempotency_key) != ''", name="ck_user_cash_cut_commands_key"),
    sa.CheckConstraint("length(request_hash) = 64", name="ck_user_cash_cut_commands_hash"),
)

user_cash_cut_reopen_requests = sa.Table(
    "user_cash_cut_reopen_requests",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("cash_cut_id", sa.String(36), sa.ForeignKey("user_cash_cuts.id"), nullable=False),
    sa.Column("proposed_counted_cash_cents", sa.Integer(), nullable=False),
    sa.Column("reason", sa.String(600), nullable=False),
    sa.Column("evidence_refs", sa.JSON(), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("requested_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("decided_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
        "status IN ('REQUESTED','APPROVED','REJECTED','COMPENSATED')",
        name="ck_user_cash_cut_reopen_status",
    ),
    sa.CheckConstraint("proposed_counted_cash_cents >= 0", name="ck_user_cash_cut_reopen_amount"),
)
sa.Index(
    "uq_user_cash_cut_reopen_active",
    user_cash_cut_reopen_requests.c.cash_cut_id,
    unique=True,
    sqlite_where=user_cash_cut_reopen_requests.c.status.in_(("REQUESTED", "APPROVED")),
    postgresql_where=user_cash_cut_reopen_requests.c.status.in_(("REQUESTED", "APPROVED")),
)

user_cash_cut_compensations = sa.Table(
    "user_cash_cut_compensations",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("cash_cut_id", sa.String(36), sa.ForeignKey("user_cash_cuts.id"), nullable=False),
    sa.Column(
        "reopen_request_id",
        sa.String(36),
        sa.ForeignKey("user_cash_cut_reopen_requests.id"),
        nullable=False,
        unique=True,
    ),
    sa.Column("corrected_counted_cash_cents", sa.Integer(), nullable=False),
    sa.Column("expected_cash_cents", sa.Integer(), nullable=False),
    sa.Column("tolerance_cents", sa.Integer(), nullable=False),
    sa.Column("corrected_difference_cents", sa.Integer(), nullable=False),
    sa.Column("difference_delta_cents", sa.Integer(), nullable=False),
    sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "corrected_counted_cash_cents >= 0 AND tolerance_cents >= 0",
        name="ck_user_cash_cut_compensation_amounts",
    ),
)

sales_operation_snapshots = sa.Table(
    "sales_operation_snapshots",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column(
        "payment_id", sa.String(36), sa.ForeignKey("payments.id"), nullable=False, unique=True
    ),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("cash_shift_id", sa.String(36), sa.ForeignKey("cash_shifts.id"), nullable=False),
    sa.Column("register_code_snapshot", sa.String(32), nullable=False),
    sa.Column("folio_snapshot", sa.String(64), nullable=False),
    sa.Column("service_type_snapshot", sa.String(32), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("gross_cents", sa.Integer(), nullable=False),
    sa.Column("net_cents", sa.Integer(), nullable=False),
    sa.Column("discount_cents", sa.Integer(), nullable=True),
    sa.Column("courtesy_cents", sa.Integer(), nullable=True),
    sa.Column("tax_cents", sa.Integer(), nullable=True),
    sa.Column("quality_status", sa.String(32), nullable=False),
    sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "quality_status IN ('captured', 'legacy_backfill', 'incomplete')",
        name="ck_sales_snapshot_quality",
    ),
    sa.CheckConstraint(
        "service_type_snapshot IN ('dine-in', 'takeout', 'delivery')",
        name="ck_sales_snapshot_service_type",
    ),
    sa.CheckConstraint("length(trim(currency)) = 3", name="ck_sales_snapshot_currency"),
    sa.CheckConstraint(
        "trim(register_code_snapshot) != '' AND trim(folio_snapshot) != ''",
        name="ck_sales_snapshot_identifiers",
    ),
    sa.CheckConstraint(
        "gross_cents >= 0 AND net_cents >= 0",
        name="ck_sales_snapshot_known_cents_nonnegative",
    ),
    sa.CheckConstraint(
        "(discount_cents IS NULL OR discount_cents >= 0) "
        "AND (courtesy_cents IS NULL OR courtesy_cents >= 0) "
        "AND (tax_cents IS NULL OR tax_cents >= 0)",
        name="ck_sales_snapshot_optional_cents_nonnegative",
    ),
)

sales_operation_line_snapshots = sa.Table(
    "sales_operation_line_snapshots",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "sales_operation_snapshot_id",
        sa.String(36),
        sa.ForeignKey("sales_operation_snapshots.id"),
        nullable=False,
    ),
    sa.Column("payment_id", sa.String(36), sa.ForeignKey("payments.id"), nullable=False),
    sa.Column("order_line_id", sa.String(36), sa.ForeignKey("order_lines.id"), nullable=False),
    sa.Column("product_id", sa.String(36), nullable=False),
    sa.Column("product_name_snapshot", sa.String(160), nullable=False),
    sa.Column("family_id_snapshot", sa.String(36), nullable=False),
    sa.Column("family_name_snapshot", sa.String(160), nullable=False),
    sa.Column("family_snapshot_source", sa.String(32), nullable=False),
    sa.Column("quantity", sa.Integer(), nullable=False),
    sa.Column("gross_cents", sa.Integer(), nullable=False),
    sa.Column("net_cents", sa.Integer(), nullable=True),
    sa.Column("discount_cents", sa.Integer(), nullable=True),
    sa.Column("courtesy_cents", sa.Integer(), nullable=True),
    sa.Column("tax_cents", sa.Integer(), nullable=True),
    sa.UniqueConstraint(
        "sales_operation_snapshot_id", "order_line_id", name="uq_sales_snapshot_line"
    ),
    sa.CheckConstraint(
        "family_snapshot_source IN ('captured', 'legacy_catalog_backfill')",
        name="ck_sales_line_family_source",
    ),
    sa.CheckConstraint(
        "trim(product_name_snapshot) != '' AND trim(family_name_snapshot) != ''",
        name="ck_sales_line_names",
    ),
    sa.CheckConstraint("quantity > 0 AND gross_cents >= 0", name="ck_sales_line_quantity_gross"),
    sa.CheckConstraint(
        "(net_cents IS NULL OR net_cents >= 0) "
        "AND (discount_cents IS NULL OR discount_cents >= 0) "
        "AND (courtesy_cents IS NULL OR courtesy_cents >= 0) "
        "AND (tax_cents IS NULL OR tax_cents >= 0)",
        name="ck_sales_line_optional_cents_nonnegative",
    ),
)

# PCO-005A stores a governed request separately from immutable order history.
order_reopen_requests = sa.Table(
    "order_reopen_requests",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("order_version_snapshot", sa.Integer(), nullable=False),
    sa.Column("order_status_snapshot", sa.String(32), nullable=False),
    sa.Column("before_snapshot", sa.JSON(), nullable=False),
    sa.Column("reason", sa.String(500), nullable=False),
    sa.Column("evidence_refs", sa.JSON(), nullable=False),
    sa.Column("requested_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("decided_by_user_id", sa.String(36), sa.ForeignKey("users.id")),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("decision_reason", sa.String(500)),
    sa.Column("applied_by_user_id", sa.String(36), sa.ForeignKey("users.id")),
    sa.Column("applied_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "status IN ('REQUESTED','APPROVED','REJECTED','EXPIRED','APPLIED')",
        name="ck_order_reopen_status",
    ),
    sa.CheckConstraint("order_version_snapshot > 0", name="ck_order_reopen_version"),
    sa.CheckConstraint("trim(reason) != ''", name="ck_order_reopen_reason"),
    sa.CheckConstraint(
        "length(trim(CAST(evidence_refs AS TEXT))) > 2",
        name="ck_order_reopen_evidence_nonempty",
    ),
    sa.CheckConstraint(
        "(status = 'REQUESTED' AND decided_by_user_id IS NULL AND decided_at IS NULL "
        "AND decision_reason IS NULL AND applied_by_user_id IS NULL AND applied_at IS NULL) "
        "OR (status IN ('APPROVED','REJECTED') AND decided_by_user_id IS NOT NULL "
        "AND decided_at IS NOT NULL AND trim(decision_reason) != '' "
        "AND applied_by_user_id IS NULL AND applied_at IS NULL) "
        "OR (status = 'EXPIRED' AND decided_by_user_id IS NULL AND decided_at IS NULL "
        "AND decision_reason IS NULL AND applied_by_user_id IS NULL AND applied_at IS NULL) "
        "OR (status = 'APPLIED' AND decided_by_user_id IS NOT NULL AND decided_at IS NOT NULL "
        "AND trim(decision_reason) != '' AND applied_by_user_id IS NOT NULL "
        "AND applied_at IS NOT NULL)",
        name="ck_order_reopen_state_coherence",
    ),
)
sa.Index(
    "uq_order_reopen_active",
    order_reopen_requests.c.order_id,
    unique=True,
    sqlite_where=order_reopen_requests.c.status.in_(("REQUESTED", "APPROVED")),
    postgresql_where=order_reopen_requests.c.status.in_(("REQUESTED", "APPROVED")),
)
sa.Index(
    "ix_order_reopen_org_branch_requested",
    order_reopen_requests.c.organization_id,
    order_reopen_requests.c.branch_id,
    order_reopen_requests.c.requested_at,
    order_reopen_requests.c.id,
)
sa.Index(
    "ix_order_reopen_order_created",
    order_reopen_requests.c.order_id,
    order_reopen_requests.c.created_at,
)

order_reopen_commands = sa.Table(
    "order_reopen_commands",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("request_id", sa.String(36), sa.ForeignKey("order_reopen_requests.id")),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("command_type", sa.String(16), nullable=False),
    sa.Column("idempotency_key", sa.String(160), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("status", sa.String(16), nullable=False, server_default="completed"),
    sa.Column("response_snapshot", sa.JSON(), nullable=False),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "command_type IN ('request','approve','reject','apply')",
        name="ck_order_reopen_command_type",
    ),
    sa.CheckConstraint("status = 'completed'", name="ck_order_reopen_command_status"),
    sa.UniqueConstraint(
        "organization_id", "idempotency_key", name="uq_order_reopen_command_org_key"
    ),
)

# PCO-005B: corrections are new append-only facts; protected sale rows are never updated.
order_corrections = sa.Table(
    "order_corrections",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column(
        "request_id",
        sa.String(36),
        sa.ForeignKey("order_reopen_requests.id"),
        nullable=False,
        unique=True,
    ),
    sa.Column("folio", sa.String(80), nullable=False, unique=True),
    sa.Column("captured_order_version", sa.Integer(), nullable=False),
    sa.Column("resulting_order_version", sa.Integer(), nullable=False),
    sa.Column("before_snapshot", sa.JSON(), nullable=False),
    sa.Column("after_snapshot", sa.JSON(), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("corrected_total_cents", sa.Integer(), nullable=False),
    sa.Column("settlement_delta_cents", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(16), nullable=False, server_default="APPLIED"),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "captured_order_version > 0 AND resulting_order_version >= captured_order_version",
        name="ck_order_corrections_versions",
    ),
    sa.CheckConstraint(
        "length(trim(currency)) = 3 AND currency = upper(currency)",
        name="ck_order_corrections_currency",
    ),
    sa.CheckConstraint("corrected_total_cents >= 0", name="ck_order_corrections_total"),
    sa.CheckConstraint("status = 'APPLIED'", name="ck_order_corrections_status"),
)
order_correction_lines = sa.Table(
    "order_correction_lines",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "correction_id", sa.String(36), sa.ForeignKey("order_corrections.id"), nullable=False
    ),
    sa.Column("source_line_id", sa.String(36), sa.ForeignKey("order_lines.id")),
    sa.Column("operational_order_line_id", sa.String(36), sa.ForeignKey("order_lines.id")),
    sa.Column("product_id", sa.String(36), nullable=False),
    sa.Column("product_name_snapshot", sa.String(160), nullable=False),
    sa.Column("family_name_snapshot", sa.String(160), nullable=False),
    sa.Column("unit_price_cents", sa.Integer(), nullable=False),
    sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column("modifiers_snapshot", sa.JSON(), nullable=False),
    sa.Column("line_total_cents", sa.Integer(), nullable=False),
    sa.Column("classification", sa.String(16), nullable=False),
    sa.CheckConstraint(
        "quantity > 0 AND unit_price_cents >= 0 AND line_total_cents >= 0",
        name="ck_order_correction_lines_amounts",
    ),
    sa.CheckConstraint(
        "classification IN ('RETAINED','ADDITION')", name="ck_order_correction_lines_classification"
    ),
    sa.CheckConstraint(
        "(classification = 'RETAINED' AND source_line_id IS NOT NULL) OR "
        "(classification = 'ADDITION' AND source_line_id IS NULL)",
        name="ck_order_correction_lines_source",
    ),
)
sa.Index("ix_order_correction_lines_correction", order_correction_lines.c.correction_id)
sa.Index(
    "ix_order_correction_lines_operational",
    order_correction_lines.c.operational_order_line_id,
)
order_payment_adjustments = sa.Table(
    "order_payment_adjustments",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "correction_id",
        sa.String(36),
        sa.ForeignKey("order_corrections.id"),
        nullable=False,
        unique=True,
    ),
    sa.Column("original_payment_id", sa.String(36), sa.ForeignKey("payments.id"), nullable=False),
    sa.Column("adjustment_type", sa.String(12), nullable=False),
    sa.Column("amount_cents", sa.Integer(), nullable=False),
    sa.Column("method", sa.String(32), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("cash_shift_id", sa.String(36), sa.ForeignKey("cash_shifts.id")),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("evidence_refs", sa.JSON(), nullable=False),
    sa.Column("cash_movement_id", sa.String(36), sa.ForeignKey("cash_movements.id")),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "adjustment_type IN ('CHARGE','REFUND') AND amount_cents > 0",
        name="ck_order_payment_adjustments_amount",
    ),
    sa.CheckConstraint("status = 'CONFIRMED'", name="ck_order_payment_adjustments_status"),
    sa.CheckConstraint(
        "method IN ('cash','debit_card','credit_card','transfer')",
        name="ck_order_payment_adjustments_method",
    ),
    sa.CheckConstraint(
        "length(trim(currency)) = 3 AND currency = upper(currency)",
        name="ck_order_payment_adjustments_currency",
    ),
    sa.CheckConstraint(
        "(method = 'cash' AND cash_shift_id IS NOT NULL AND cash_movement_id IS NOT NULL) "
        "OR (method != 'cash' AND cash_shift_id IS NULL AND cash_movement_id IS NULL)",
        name="ck_order_payment_adjustments_cash_link",
    ),
)
sa.Index("ix_order_payment_adjustments_correction", order_payment_adjustments.c.correction_id)
order_production_adjustments = sa.Table(
    "order_production_adjustments",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "correction_id", sa.String(36), sa.ForeignKey("order_corrections.id"), nullable=False
    ),
    sa.Column("source_line_id", sa.String(36), sa.ForeignKey("order_lines.id")),
    sa.Column("source_task_id", sa.String(36), sa.ForeignKey("production_tasks.id")),
    sa.Column("correction_line_id", sa.String(36), sa.ForeignKey("order_correction_lines.id")),
    sa.Column("adjustment_type", sa.String(16), nullable=False),
    sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
    sa.Column("inventory_movement_id", sa.String(36), sa.ForeignKey("inventory_movements.id")),
    sa.Column("production_task_id", sa.String(36), sa.ForeignKey("production_tasks.id")),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "adjustment_type IN ('RELEASE','WASTE','RECOVERY','ADDITION') AND quantity > 0",
        name="ck_order_production_adjustments_value",
    ),
    sa.CheckConstraint(
        "(adjustment_type = 'ADDITION' AND source_line_id IS NULL AND source_task_id IS NULL "
        "AND correction_line_id IS NOT NULL) OR (adjustment_type != 'ADDITION' "
        "AND source_line_id IS NOT NULL AND source_task_id IS NOT NULL)",
        name="ck_order_production_adjustments_links",
    ),
)
sa.Index("ix_order_production_adjustments_correction", order_production_adjustments.c.correction_id)
sa.Index(
    "ix_order_corrections_org_branch_applied",
    order_corrections.c.organization_id,
    order_corrections.c.branch_id,
    order_corrections.c.applied_at,
)

sa.Index(
    "ix_cash_shift_closures_org_branch_closed",
    cash_shift_closures.c.organization_id,
    cash_shift_closures.c.branch_id,
    cash_shift_closures.c.closed_at,
)
sa.Index(
    "ix_sales_snapshots_org_period_branch",
    sales_operation_snapshots.c.organization_id,
    sales_operation_snapshots.c.confirmed_at,
    sales_operation_snapshots.c.branch_id,
)
sa.Index(
    "ix_sales_snapshots_org_shift_register_service",
    sales_operation_snapshots.c.organization_id,
    sales_operation_snapshots.c.cash_shift_id,
    sales_operation_snapshots.c.register_code_snapshot,
    sales_operation_snapshots.c.service_type_snapshot,
)
sa.Index(
    "ix_sales_line_snapshots_family",
    sales_operation_line_snapshots.c.family_id_snapshot,
    sales_operation_line_snapshots.c.sales_operation_snapshot_id,
)
sa.Index("ix_sales_line_snapshots_payment", sales_operation_line_snapshots.c.payment_id)

cash_shift_cuts = sa.Table(
    "cash_shift_cuts",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column(
        "cash_shift_id",
        sa.String(36),
        sa.ForeignKey("cash_shifts.id"),
        nullable=False,
        unique=True,
    ),
    sa.Column("sales_total_cents", sa.Integer(), nullable=False),
    sa.Column("payment_total_cents", sa.Integer(), nullable=False),
    sa.Column("cash_payment_total_cents", sa.Integer(), nullable=False),
    sa.Column("opening_cash_cents", sa.Integer(), nullable=False),
    sa.Column("expected_cash_cents", sa.Integer(), nullable=False),
    sa.Column("counted_cash_cents", sa.Integer(), nullable=False),
    sa.Column("difference_cents", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

print_jobs = sa.Table(
    "print_jobs",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("job_type", sa.String(32), nullable=False),
    sa.Column("target", sa.String(64), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("last_error", sa.String(240), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
)

device_credentials = sa.Table(
    "device_credentials",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), nullable=False),
    sa.Column("capability", sa.String(64), nullable=False),
    sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
    sa.Column("key_version", sa.String(32), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("revoked_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "capability IN ('kds.operate', 'gateway.sync', 'print.agent')",
        name="ck_device_credential_capability",
    ),
    sa.CheckConstraint("length(token_hash) = 64", name="ck_device_credential_token_hash"),
    sa.ForeignKeyConstraint(
        ["organization_id", "branch_id"],
        ["branches.organization_id", "branches.id"],
        name="fk_device_credentials_organization_branch",
    ),
)

# Short-lived, single-use browser handoffs contain only a SHA-256 digest. They
# transfer an already authenticated human session between the Admin and POS
# origins without placing the bearer token in a URL.
pos_session_handoffs = sa.Table(
    "pos_session_handoffs",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("target_app", sa.String(16), nullable=False),
    sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("consumed_at", sa.DateTime(timezone=True)),
    sa.CheckConstraint("target_app = 'pos'", name="ck_pos_session_handoff_target"),
    sa.CheckConstraint("length(code_hash) = 64", name="ck_pos_session_handoff_hash"),
)

sa.Index(
    "ix_pos_session_handoffs_user_expires",
    pos_session_handoffs.c.organization_id,
    pos_session_handoffs.c.user_id,
    pos_session_handoffs.c.expires_at,
)

print_attempts = sa.Table(
    "print_attempts",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("print_job_id", sa.String(36), sa.ForeignKey("print_jobs.id"), nullable=False),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("idempotency_key", sa.String(160), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("claimed_by_device_id", sa.String(36)),
    sa.Column("claimed_at", sa.DateTime(timezone=True)),
    sa.Column("ack_hash", sa.String(64)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("acked_at", sa.DateTime(timezone=True)),
    sa.Column("failed_at", sa.DateTime(timezone=True)),
    sa.Column("error_code", sa.String(64)),
    sa.UniqueConstraint("print_job_id", "idempotency_key", name="uq_print_attempt_key"),
    sa.CheckConstraint(
        "status IN ('QUEUED', 'CLAIMED', 'PRINTED', 'FAILED')", name="ck_print_attempt_status"
    ),
    sa.CheckConstraint(
        "(status = 'QUEUED' AND claimed_by_device_id IS NULL AND claimed_at IS NULL "
        "AND ack_hash IS NULL AND acked_at IS NULL "
        "AND failed_at IS NULL AND error_code IS NULL) OR "
        "(status = 'CLAIMED' AND claimed_by_device_id IS NOT NULL AND claimed_at IS NOT NULL "
        "AND ack_hash IS NULL AND acked_at IS NULL "
        "AND failed_at IS NULL AND error_code IS NULL) OR "
        "(status = 'PRINTED' AND claimed_by_device_id IS NOT NULL AND claimed_at IS NOT NULL "
        "AND ack_hash IS NOT NULL AND acked_at IS NOT NULL "
        "AND failed_at IS NULL AND error_code IS NULL) OR "
        "(status = 'FAILED' AND claimed_by_device_id IS NOT NULL AND claimed_at IS NOT NULL "
        "AND failed_at IS NOT NULL AND error_code IS NOT NULL "
        "AND ack_hash IS NULL AND acked_at IS NULL)",
        name="ck_print_attempt_state_fields",
    ),
    sa.CheckConstraint("length(request_hash) = 64", name="ck_print_attempt_request_hash"),
    sa.CheckConstraint(
        "ack_hash IS NULL OR length(ack_hash) = 64", name="ck_print_attempt_ack_hash"
    ),
    sa.CheckConstraint(
        "error_code IS NULL OR (length(error_code) BETWEEN 1 AND 64)",
        name="ck_print_attempt_error_code",
    ),
    sa.Index(
        "ix_print_attempts_pull_scope",
        "organization_id",
        "branch_id",
        "status",
        "created_at",
        "id",
    ),
)

order_create_commands = sa.Table(
    "order_create_commands",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("idempotency_key", sa.String(160), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("response_snapshot", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id", "idempotency_key", name="uq_order_create_command_org_key"
    ),
    sa.CheckConstraint("length(request_hash) = 64", name="ck_order_create_command_hash"),
)

sa.Index(
    "ix_order_create_commands_scope_created",
    order_create_commands.c.organization_id,
    order_create_commands.c.branch_id,
    order_create_commands.c.created_at,
)

order_fulfillment_commands = sa.Table(
    "order_fulfillment_commands",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("command", sa.String(32), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("idempotency_key", sa.String(160), nullable=False),
    sa.Column("response_snapshot", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("order_id", "idempotency_key", name="uq_order_fulfillment_command_key"),
    sa.CheckConstraint(
        "command IN ('start_delivery', 'deliver', 'close')",
        name="ck_order_fulfillment_command",
    ),
    sa.Index(
        "ix_order_fulfillment_commands_scope_created",
        "organization_id",
        "branch_id",
        "created_at",
    ),
)

order_adjustment_authorizations = sa.Table(
    "order_adjustment_authorizations",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("requesting_actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("supervisor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
    sa.Column("cart_hash", sa.String(64), nullable=False),
    sa.Column("adjustment_type", sa.String(16), nullable=False),
    sa.Column("adjustment_value", sa.String(40), nullable=False),
    sa.Column("subtotal_cents", sa.Integer(), nullable=False),
    sa.Column("adjustment_cents", sa.Integer(), nullable=False),
    sa.Column("resulting_total_cents", sa.Integer(), nullable=False),
    sa.Column("reason", sa.String(240), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("consumed_order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=True),
    sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint(
        "adjustment_type IN ('percent', 'fixed', 'courtesy')",
        name="ck_order_adjustment_authorization_type",
    ),
    sa.CheckConstraint(
        "status IN ('AUTHORIZED', 'CONSUMED')",
        name="ck_order_adjustment_authorization_status",
    ),
    sa.CheckConstraint(
        "adjustment_cents >= 0",
        name="ck_order_adjustment_authorization_cents",
    ),
    sa.CheckConstraint(
        "subtotal_cents >= adjustment_cents AND "
        "resulting_total_cents = subtotal_cents - adjustment_cents",
        name="ck_order_adjustment_authorization_totals",
    ),
    sa.Index(
        "ix_order_adjustment_authorizations_scope_status",
        "organization_id",
        "branch_id",
        "status",
        "expires_at",
    ),
)

sync_commands = sa.Table(
    "sync_commands",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("source_device_id", sa.String(36), nullable=False),
    sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("command_id", sa.String(36), nullable=False),
    sa.Column("idempotency_key", sa.String(160), nullable=False),
    sa.Column("command_type", sa.String(120), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("request_hash", sa.String(64), nullable=True),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("checkpoint", sa.Integer(), nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_sync_commands_org_key"),
    sa.UniqueConstraint("organization_id", "command_id", name="uq_sync_commands_org_command"),
)

sa.Index(
    "ix_sync_commands_org_branch_checkpoint",
    sync_commands.c.organization_id,
    sync_commands.c.branch_id,
    sync_commands.c.checkpoint,
)

sync_branch_checkpoints = sa.Table(
    "sync_branch_checkpoints",
    metadata,
    sa.Column(
        "organization_id",
        sa.String(36),
        sa.ForeignKey("organizations.id"),
        primary_key=True,
    ),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), primary_key=True),
    sa.Column("last_checkpoint", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("last_checkpoint >= 0", name="ck_sync_branch_checkpoints_positive"),
)

sync_events = sa.Table(
    "sync_events",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("sync_command_id", sa.String(36), sa.ForeignKey("sync_commands.id"), nullable=False),
    sa.Column("event_type", sa.String(120), nullable=False),
    sa.Column("checkpoint", sa.Integer(), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
)

reconciliation_audit_logs = sa.Table(
    "reconciliation_audit_logs",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("date", sa.String(10), nullable=False),
    sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("audited_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    sa.Column("notes", sa.Text(), nullable=True),
    sa.Column("audited_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("branch_id", "date", name="uq_reconciliation_audit_logs_branch_date"),
)

channel_integrations = sa.Table(
    "channel_integrations",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("provider", sa.String(32), nullable=False),
    sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("environment", sa.String(24), nullable=False, server_default="sandbox"),
    sa.Column("client_id", sa.String(128), nullable=True),
    sa.Column("client_secret", sa.String(256), nullable=True),
    sa.Column("webhook_secret", sa.String(256), nullable=True),
    sa.Column("auto_accept", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("default_prep_time_minutes", sa.Integer(), nullable=False, server_default="20"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", "provider", name="uq_channel_integrations_org_provider"),
)

channel_store_mappings = sa.Table(
    "channel_store_mappings",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("provider", sa.String(32), nullable=False),
    sa.Column("external_store_id", sa.String(128), nullable=False),
    sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id",
        "provider",
        "external_store_id",
        name="uq_channel_store_mappings_org_provider_store",
    ),
    sa.UniqueConstraint("branch_id", "provider", name="uq_channel_store_mappings_branch_provider"),
)

channel_product_mappings = sa.Table(
    "channel_product_mappings",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
    sa.Column("provider", sa.String(32), nullable=False),
    sa.Column("external_item_id", sa.String(128), nullable=False),
    sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "organization_id",
        "provider",
        "external_item_id",
        name="uq_channel_product_mappings_org_provider_item",
    ),
)

integration_webhook_logs = sa.Table(
    "integration_webhook_logs",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("provider", sa.String(32), nullable=False),
    sa.Column("event_type", sa.String(64), nullable=False),
    sa.Column("event_id", sa.String(128), nullable=True),
    sa.Column("signature", sa.String(256), nullable=True),
    sa.Column("payload_raw", sa.JSON(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False, server_default="received"),
    sa.Column("error_message", sa.String(500), nullable=True),
    sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

channel_orders_meta = sa.Table(
    "channel_orders_meta",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False, unique=True),
    sa.Column("provider", sa.String(32), nullable=False),
    sa.Column("external_order_id", sa.String(128), nullable=False),
    sa.Column("display_code", sa.String(32), nullable=False),
    sa.Column("customer_name", sa.String(160), nullable=True),
    sa.Column("driver_name", sa.String(160), nullable=True),
    sa.Column("driver_phone", sa.String(32), nullable=True),
    sa.Column("external_status", sa.String(48), nullable=False, server_default="CREATED"),
    sa.Column("estimated_ready_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("raw_payload", sa.JSON(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

facturapi_config = sa.Table(
    "facturapi_config",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("environment", sa.String(24), nullable=False, server_default="sandbox"),
    sa.Column("api_key", sa.String(256), nullable=True),
    sa.Column("organization_legal_name", sa.String(200), nullable=True),
    sa.Column("organization_rfc", sa.String(13), nullable=True),
    sa.Column("organization_tax_system", sa.String(10), nullable=True),
    sa.Column("organization_zip", sa.String(10), nullable=True),
    sa.Column("default_product_sat_key", sa.String(16), nullable=False, server_default="90101501"),
    sa.Column("default_unit_sat_key", sa.String(16), nullable=False, server_default="E48"),
    sa.Column("series", sa.String(10), nullable=False, server_default="F"),
    sa.Column("enable_self_invoicing", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("self_invoicing_domain", sa.String(120), nullable=True, server_default="demo"),
    sa.Column("self_invoicing_days_valid", sa.Integer(), nullable=False, server_default="30"),
    sa.Column("print_qr_on_ticket", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("organization_id", name="uq_facturapi_config_org"),
)

cfdi_invoices = sa.Table(
    "cfdi_invoices",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=True),
    sa.Column("facturapi_invoice_id", sa.String(128), nullable=True, unique=True),
    sa.Column("facturapi_receipt_id", sa.String(128), nullable=True),
    sa.Column("uuid_sat", sa.String(64), nullable=True),
    sa.Column("folio_number", sa.String(64), nullable=False),
    sa.Column("rfc_emisor", sa.String(13), nullable=False),
    sa.Column("rfc_receptor", sa.String(13), nullable=False),
    sa.Column("nombre_receptor", sa.String(200), nullable=False),
    sa.Column("codigo_postal_receptor", sa.String(10), nullable=False),
    sa.Column("regimen_fiscal_receptor", sa.String(10), nullable=False),
    sa.Column("uso_cfdi", sa.String(10), nullable=False, server_default="G03"),
    sa.Column("forma_pago_sat", sa.String(10), nullable=False, server_default="01"),
    sa.Column("metodo_pago_sat", sa.String(10), nullable=False, server_default="PUE"),
    sa.Column("total_cents", sa.Integer(), nullable=False),
    sa.Column("currency", sa.String(3), nullable=False, server_default="MXN"),
    sa.Column("status", sa.String(32), nullable=False, server_default="issued"),
    sa.Column("verification_url", sa.String(500), nullable=True),
    sa.Column("self_invoice_url", sa.String(500), nullable=True),
    sa.Column("pdf_url", sa.String(500), nullable=True),
    sa.Column("xml_url", sa.String(500), nullable=True),
    sa.Column("cancellation_reason", sa.String(10), nullable=True),
    sa.Column("raw_sat_response", sa.JSON(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
)

customer_feedbacks = sa.Table(
    "customer_feedbacks",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
    sa.Column("order_folio", sa.String(64), nullable=True),
    sa.Column("rating", sa.Integer(), nullable=False),
    sa.Column("customer_name", sa.String(160), nullable=True),
    sa.Column("comment", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_customer_feedbacks_branch_created", "branch_id", "created_at"),
)
