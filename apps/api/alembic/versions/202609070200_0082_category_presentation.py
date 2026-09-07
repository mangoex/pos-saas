"""Add optional category photographs and a restaurant-owned menu cover."""

import sqlalchemy as sa
from alembic import op

revision = "0082_category_presentation"
down_revision = "0081_restaurant_domains"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("product_categories", sa.Column("image_url", sa.String(512), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("menu_home_name", sa.String(120), nullable=False, server_default="Todos"),
    )
    op.add_column("organizations", sa.Column("menu_home_image_url", sa.String(512), nullable=True))


def downgrade():
    bind = op.get_bind()
    customized = bind.scalar(
        sa.text(
            "SELECT COUNT(*) FROM organizations WHERE menu_home_name <> 'Todos' "
            "OR menu_home_image_url IS NOT NULL"
        )
    ) or bind.scalar(sa.text("SELECT COUNT(*) FROM product_categories WHERE image_url IS NOT NULL"))
    if customized:
        raise RuntimeError("Export and preserve menu presentation before schema rollback")
    op.drop_column("organizations", "menu_home_image_url")
    op.drop_column("organizations", "menu_home_name")
    op.drop_column("product_categories", "image_url")
