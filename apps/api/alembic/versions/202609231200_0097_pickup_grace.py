"""Optional branch pickup grace notice; existing branches remain unconfigured."""

from alembic import op
import sqlalchemy as sa

revision = "0097_pickup_grace"
down_revision = "0096_branch_color_palette"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("branches") as batch:
        batch.add_column(sa.Column("pickup_grace_minutes", sa.Integer(), nullable=True))
        batch.create_check_constraint(
            "ck_branches_pickup_grace_minutes",
            "pickup_grace_minutes IS NULL OR (pickup_grace_minutes >= 1 AND pickup_grace_minutes <= 2147483647)",
        )


def downgrade() -> None:
    with op.batch_alter_table("branches") as batch:
        batch.drop_constraint("ck_branches_pickup_grace_minutes", type_="check")
        batch.drop_column("pickup_grace_minutes")
