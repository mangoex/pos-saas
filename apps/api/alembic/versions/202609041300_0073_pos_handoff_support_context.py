"""Persist support authority across short-lived POS handoffs.

Revision ID: 0073_pos_handoff_support_context
Revises: 0072_uber_availability_sync
"""

import sqlalchemy as sa
from alembic import op

revision = "0073_pos_handoff_support_context"
down_revision = "0072_uber_availability_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("pos_session_handoffs")
    }
    if {"support_real_actor_user_id", "support_correlation_id"} <= columns:
        return
    with op.batch_alter_table("pos_session_handoffs") as batch:
        if "support_real_actor_user_id" not in columns:
            batch.add_column(
                sa.Column("support_real_actor_user_id", sa.String(36), nullable=True)
            )
            batch.create_foreign_key(
                "fk_pos_handoff_support_real_actor",
                "users",
                ["support_real_actor_user_id"],
                ["id"],
            )
        if "support_correlation_id" not in columns:
            batch.add_column(sa.Column("support_correlation_id", sa.String(36), nullable=True))


def downgrade() -> None:
    # Consumed and outstanding handoffs are short-lived. Retain attribution on rollback.
    pass
