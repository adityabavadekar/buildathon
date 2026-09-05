"""0007_add_jobs_timestamp_indexes

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-06 00:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Index jobs.created_at/updated_at, queried unindexed by the pipeline
    overview and timeseries aggregates polled every 3s while PipelineView is
    open. idx_jobs_due already covers (status, due_at) but not these columns.
    """
    op.create_index("idx_jobs_created", "jobs", ["created_at"])
    op.create_index("idx_jobs_updated", "jobs", ["updated_at"])


def downgrade() -> None:
    op.drop_index("idx_jobs_updated", table_name="jobs")
    op.drop_index("idx_jobs_created", table_name="jobs")
