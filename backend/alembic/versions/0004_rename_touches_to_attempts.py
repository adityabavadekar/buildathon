"""0004_rename_touches_to_attempts

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-05 16:36:29.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename cases.touches_count to attempts_count.

    The workflows table also has a touches_count column, but it is left out of
    this migration: workflows already has a distinct pre-existing
    attempts_count column (retry attempts), so renaming touches_count to the
    same name there would collide. See docs/DECISIONS.md.
    """
    op.alter_column("cases", "touches_count", new_column_name="attempts_count")


def downgrade() -> None:
    op.alter_column("cases", "attempts_count", new_column_name="touches_count")
