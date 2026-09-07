"""Scope purchase confirmation idempotency by organization."""

from alembic import op
import sqlalchemy as sa

revision = "0079_purchase_tenant_idempotency"
down_revision = "0078_waste_tenant_idempotency"
branch_labels = None
depends_on = None


def _assert_downgrade_safe(bind: sa.Connection) -> None:
    duplicate = bind.execute(sa.text("""
        SELECT confirmation_idempotency_key FROM purchase_documents
        WHERE confirmation_idempotency_key IS NOT NULL
        GROUP BY confirmation_idempotency_key
        HAVING COUNT(DISTINCT organization_id) > 1
        LIMIT 1
    """)).scalar_one_or_none()
    if duplicate is not None:
        raise RuntimeError(
            "0078 downgrade blocked: tenant-scoped purchase idempotency keys overlap; "
            "global uniqueness cannot be restored without deleting history"
        )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(
            "ALTER TABLE purchase_documents DROP CONSTRAINT IF EXISTS "
            "purchase_documents_confirmation_idempotency_key_key"
        ))
        op.create_unique_constraint(
            "uq_purchase_documents_org_confirmation_idempotency",
            "purchase_documents",
            ["organization_id", "confirmation_idempotency_key"],
        )
        return
    convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table(
        "purchase_documents", recreate="always", naming_convention=convention
    ) as batch:
        batch.drop_constraint(
            "uq_purchase_documents_confirmation_idempotency_key", type_="unique"
        )
        batch.create_unique_constraint(
            "uq_purchase_documents_org_confirmation_idempotency",
            ["organization_id", "confirmation_idempotency_key"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    _assert_downgrade_safe(bind)
    if bind.dialect.name == "postgresql":
        op.drop_constraint(
            "uq_purchase_documents_org_confirmation_idempotency",
            "purchase_documents",
            type_="unique",
        )
        op.create_unique_constraint(
            "purchase_documents_confirmation_idempotency_key_key",
            "purchase_documents",
            ["confirmation_idempotency_key"],
        )
        return
    convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table(
        "purchase_documents", recreate="always", naming_convention=convention
    ) as batch:
        batch.drop_constraint(
            "uq_purchase_documents_org_confirmation_idempotency", type_="unique"
        )
        batch.create_unique_constraint(
            "uq_purchase_documents_confirmation_idempotency_key",
            ["confirmation_idempotency_key"],
        )
