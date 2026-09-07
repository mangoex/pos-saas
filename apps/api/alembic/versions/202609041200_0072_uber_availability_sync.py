"""Persist confirmed Uber Eats item availability commands."""

import sqlalchemy as sa
from alembic import op

revision = "0072_uber_availability_sync"
down_revision = "0071_saas_setup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = "channel_availability_sync_jobs"
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(table):
        # Downgrade retains external work. Re-entry must not discard it or accept a partial table.
        required = {
            "id",
            "organization_id",
            "branch_id",
            "provider",
            "external_store_id",
            "external_item_id",
            "product_id",
            "is_available",
            "desired_version",
            "status",
            "attempts",
            "next_attempt_at",
            "last_error",
            "confirmed_at",
            "lease_token",
            "lease_expires_at",
            "created_at",
            "updated_at",
        }
        columns = {column["name"] for column in inspector.get_columns(table)}
        unique_names = {
            constraint["name"] for constraint in inspector.get_unique_constraints(table)
        }
        check_names = {constraint["name"] for constraint in inspector.get_check_constraints(table)}
        if not (
            required <= columns
            and "uq_channel_availability_sync_target" in unique_names
            and "ck_channel_availability_sync_status" in check_names
        ):
            raise RuntimeError("Existing availability outbox schema does not match revision 0071")
        indexes = {index["name"] for index in inspector.get_indexes(table)}
        if "ix_channel_availability_sync_due" not in indexes:
            op.create_index(
                "ix_channel_availability_sync_due", table, ["status", "next_attempt_at"]
            )
        return
    op.create_table(
        "channel_availability_sync_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("branch_id", sa.String(36), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_store_id", sa.String(128), nullable=False),
        sa.Column("external_item_id", sa.String(128), nullable=False),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("desired_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(500)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RETRY', 'CLAIMED', 'CONFIRMED', 'FAILED')",
            name="ck_channel_availability_sync_status",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "external_store_id",
            "external_item_id",
            name="uq_channel_availability_sync_target",
        ),
    )
    op.create_index(
        "ix_channel_availability_sync_due",
        "channel_availability_sync_jobs",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    # Preserve externally requested availability state across image rollback.
    pass
