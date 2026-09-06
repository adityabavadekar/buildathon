"""0009_repair_cases_escalation_reason

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-06 20:40:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Repair databases stamped at 0001 before escalation_reason was added to
    that revision's create_table. Alembic replays a revision only once, so a
    database already stamped 0001 never grows the column and every analytics
    query referencing it fails with UndefinedColumn. IF NOT EXISTS keeps this a
    no-op on databases created after 0001 was amended, which do have it.

    Backfilled from data_json because the orchestrator wrote the reason there
    for the whole window the column was missing.
    """
    op.execute("ALTER TABLE cases ADD COLUMN IF NOT EXISTS escalation_reason TEXT;")
    op.execute(
        "UPDATE cases SET escalation_reason = data_json ->> 'escalation_reason' "
        "WHERE escalation_reason IS NULL "
        "AND data_json ->> 'escalation_reason' IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cases_escalation_reason "
        "ON cases (escalation_reason);"
    )


def downgrade() -> None:
    # No drop: the column belongs to 0001, so removing it here would leave a
    # database that 0001 alone can no longer reconstruct.
    pass
