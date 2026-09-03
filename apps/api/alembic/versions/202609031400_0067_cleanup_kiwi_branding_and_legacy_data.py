"""Purge legacy Kiwi branding strings and unreferenced legacy presentations/insumos.

Revision ID: 0067_cleanup_kiwi_branding_and_legacy_data
Revises: 0066_add_saas_organization_subscription
"""

from __future__ import annotations

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0067_cleanup_kiwi_branding_and_legacy_data"
down_revision: str | None = "0066_add_saas_organization_subscription"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Neutralize all branding strings in database entities
    conn.execute(sa.text("""
        UPDATE organizations
        SET name = 'RestaurantOS'
        WHERE LOWER(name) LIKE '%kiwi%'
    """))

    conn.execute(sa.text("""
        UPDATE business_units
        SET name = 'Operaciones', code = 'REST'
        WHERE LOWER(name) LIKE '%kiwi%' OR UPPER(code) = 'KIWI'
    """))

    conn.execute(sa.text("""
        UPDATE legal_entities
        SET name = 'Razón Social Principal'
        WHERE LOWER(name) LIKE '%kiwi%'
    """))

    conn.execute(sa.text("""
        UPDATE users
        SET display_name = 'Administrador'
        WHERE LOWER(display_name) LIKE '%kiwi%'
    """))

    conn.execute(sa.text("""
        UPDATE branches
        SET name = REPLACE(name, 'Kiwi', 'RestaurantOS')
        WHERE name LIKE '%Kiwi%'
    """))

    conn.execute(sa.text("""
        UPDATE warehouses
        SET name = REPLACE(name, 'Kiwi', 'RestaurantOS')
        WHERE name LIKE '%Kiwi%'
    """))

    # 2. Clean up legacy purchasing presentations and price history
    conn.execute(sa.text("""
        DELETE FROM supplier_price_history
        WHERE presentation_id IN (
            SELECT id FROM purchase_presentations
            WHERE code LIKE 'PRES-%' OR code LIKE 'PRES%' OR LOWER(name) LIKE '%kiwi%'
        )
    """))

    # Delete legacy purchase presentations not referenced in actual purchase transactions
    conn.execute(sa.text("""
        DELETE FROM purchase_presentations
        WHERE (code LIKE 'PRES-%' OR code LIKE 'PRES%' OR LOWER(name) LIKE '%kiwi%')
          AND id NOT IN (SELECT DISTINCT presentation_id FROM purchase_document_lines)
    """))

    # 3. Archive legacy wholesale inventory items from 0048 so they don't appear in catalogs
    conn.execute(sa.text("""
        UPDATE inventory_items
        SET status = 'archived'
        WHERE organization_id = '018f6f73-2d0a-74f0-8f1c-000000000001'
          AND sku >= '1000' AND sku <= '9999'
    """))

    conn.execute(sa.text("""
        UPDATE inventory_items
        SET name = REPLACE(name, 'KIWI', 'INSUMO')
        WHERE UPPER(name) LIKE '%KIWI%'
    """))


def downgrade() -> None:
    # Irreversible cleanup of legacy branding/sample data
    pass
