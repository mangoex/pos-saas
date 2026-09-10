"""Secure customer feedback order references.

Revision ID: 0086_secure_customer_feedback_reference
Revises: 0085_add_customer_feedbacks_customer_id_and_phone
Create Date: 2026-09-09 19:00:00.000000

Forward-remediation: automatically deduplicate historical feedback rows
(keeping the most recent by created_at) before installing the UNIQUE index.
The application layer already implements upsert semantics, so duplicates are
a pre-existing-data artefact, not an ongoing concern.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0086_secure_customer_feedback_reference"
down_revision: str | None = "0085_add_customer_feedbacks_customer_id_and_phone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _remediate_duplicates(conn: sa.Connection) -> int:
    """Delete duplicate feedback rows, keeping the newest per (org, branch, folio).

    Uses a dialect-portable two-step approach that works on both PostgreSQL and
    SQLite (which lacks window functions in older versions and DELETE … USING).

    Returns the number of deleted rows.
    """
    # Step 1: collect the IDs to keep (most recent per group).
    keep_rows = conn.execute(
        sa.text(
            """
            SELECT id
            FROM customer_feedbacks
            WHERE order_folio IS NOT NULL
            AND id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY organization_id, branch_id, order_folio
                               ORDER BY created_at DESC, id DESC
                           ) AS rn
                    FROM customer_feedbacks
                    WHERE order_folio IS NOT NULL
                ) ranked
                WHERE rn = 1
            )
            """
        )
    )
    keep_ids = {str(row[0]) for row in keep_rows}
    if not keep_ids:
        return 0

    # Step 2: find all IDs in duplicate groups.
    dup_group_rows = conn.execute(
        sa.text(
            """
            SELECT cf.id
            FROM customer_feedbacks cf
            INNER JOIN (
                SELECT organization_id, branch_id, order_folio
                FROM customer_feedbacks
                WHERE order_folio IS NOT NULL
                GROUP BY organization_id, branch_id, order_folio
                HAVING COUNT(*) > 1
            ) dups
            ON cf.organization_id = dups.organization_id
               AND cf.branch_id = dups.branch_id
               AND cf.order_folio = dups.order_folio
            """
        )
    )
    all_dup_ids = {str(row[0]) for row in dup_group_rows}
    delete_ids = all_dup_ids - keep_ids

    if not delete_ids:
        return 0

    # Step 3: delete in batches to avoid overly long IN clauses.
    deleted = 0
    batch = list(delete_ids)
    for i in range(0, len(batch), 500):
        chunk = batch[i : i + 500]
        placeholders = ", ".join(f":id_{j}" for j in range(len(chunk)))
        params = {f"id_{j}": cid for j, cid in enumerate(chunk)}
        result = conn.execute(
            sa.text(f"DELETE FROM customer_feedbacks WHERE id IN ({placeholders})"),
            params,
        )
        deleted += result.rowcount
    return deleted


def upgrade() -> None:
    conn = op.get_bind()

    deleted = _remediate_duplicates(conn)
    if deleted:
        import logging

        logging.getLogger("alembic.runtime.migration").info(
            "0086: auto-remediated %d duplicate customer feedback row(s) "
            "(kept most recent per order reference)",
            deleted,
        )

    op.create_index(
        "uq_customer_feedbacks_order_reference",
        "customer_feedbacks",
        ["organization_id", "branch_id", "order_folio"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_customer_feedbacks_order_reference",
        table_name="customer_feedbacks",
    )
