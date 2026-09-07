"""Make marketplace webhook intake and external orders tenant-idempotent.

Revision ID: 0080_delivery_inbox_idempotency
Revises: 0079_purchase_tenant_idempotency
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0080_delivery_inbox_idempotency"
down_revision: str | None = "0079_purchase_tenant_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    duplicate = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT orders.organization_id, channel_orders_meta.provider,
                   channel_orders_meta.external_order_id, COUNT(*) AS duplicate_count
            FROM channel_orders_meta
            JOIN orders ON orders.id = channel_orders_meta.order_id
            GROUP BY orders.organization_id, channel_orders_meta.provider,
                     channel_orders_meta.external_order_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
            )
        )
        .mappings()
        .first()
    )
    if duplicate:
        raise RuntimeError(
            "0080 requires governed reconciliation of duplicate marketplace orders before retry: "
            f"organization={duplicate['organization_id']} provider={duplicate['provider']} "
            f"external_order_id={duplicate['external_order_id']} "
            f"count={duplicate['duplicate_count']}"
        )
    op.create_table(
        "integration_webhook_inbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="processing"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "organization_id", "provider", "event_id", name="uq_webhook_inbox_org_provider_event"
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'processed', 'error')", name="ck_webhook_inbox_status"
        ),
    )
    with op.batch_alter_table("channel_orders_meta") as batch:
        batch.add_column(sa.Column("organization_id", sa.String(36), nullable=True))
    op.execute(
        sa.text("""
        UPDATE channel_orders_meta SET organization_id = (
            SELECT orders.organization_id FROM orders WHERE orders.id = channel_orders_meta.order_id
        )
    """)
    )
    with op.batch_alter_table("channel_orders_meta") as batch:
        batch.alter_column("organization_id", existing_type=sa.String(36), nullable=False)
        batch.create_foreign_key(
            "fk_channel_orders_meta_organization",
            "organizations",
            ["organization_id"],
            ["id"],
        )
        batch.create_unique_constraint(
            "uq_channel_order_org_provider_external",
            ["organization_id", "provider", "external_order_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("channel_orders_meta") as batch:
        batch.drop_constraint("uq_channel_order_org_provider_external", type_="unique")
        batch.drop_constraint("fk_channel_orders_meta_organization", type_="foreignkey")
        batch.drop_column("organization_id")
    op.drop_table("integration_webhook_inbox")
