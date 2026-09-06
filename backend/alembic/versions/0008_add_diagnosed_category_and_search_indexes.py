"""0008_add_diagnosed_category_and_search_indexes

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-06 21:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEARCHABLE_COLUMNS = (
    "payment_id",
    "customer_id",
    "invoice_id",
    "subscription_id",
    "campaign_id",
    "error_code",
    "contact_email",
    "case_id",
    "user_ref",
    "reference_id",
    "contact_phone",
    "error_source",
)


def upgrade() -> None:
    """Two analytics/search fixes bundled together since both were driven by
    the same root cause: reading a scalar out of data_json, or matching free
    text against CAST(data_json AS text), re-parses the multi-KB JSONB blob
    embedded in every case row and dominates query cost independent of the
    fix's own logic.

    1. Promote diagnosed_category from data_json-only to a real column,
       backfilled from existing data -- the analytics category breakdown
       extracted this with data_json ->> on every request.
    2. Add pg_trgm + GIN indexes on every column the free-text `q` filter and
       suggest_search_terms() match with a leading-wildcard ILIKE, which a
       btree index can't serve.
    """
    op.add_column(
        "cases",
        sa.Column(
            "diagnosed_category",
            sa.Text(),
            nullable=False,
            server_default="UNCLASSIFIED",
        ),
    )
    op.execute(
        "UPDATE cases SET diagnosed_category = "
        "COALESCE(data_json ->> 'diagnosed_category', 'UNCLASSIFIED');"
    )
    op.create_index("idx_cases_diagnosed_category", "cases", ["diagnosed_category"])

    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    for column in SEARCHABLE_COLUMNS:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_cases_{column}_trgm "
            f"ON cases USING gin ({column} gin_trgm_ops);"
        )


def downgrade() -> None:
    for column in SEARCHABLE_COLUMNS:
        op.execute(f"DROP INDEX IF EXISTS idx_cases_{column}_trgm;")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm;")
    op.drop_index("idx_cases_diagnosed_category", table_name="cases")
    op.drop_column("cases", "diagnosed_category")
