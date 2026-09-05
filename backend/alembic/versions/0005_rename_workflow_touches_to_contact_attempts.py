"""0005_rename_workflow_touches_to_contact_attempts

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-05 22:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename workflows.touches_count to contact_attempts_count.

    0004 renamed cases.touches_count to attempts_count but deliberately left
    workflows.touches_count alone, since workflows already has a distinct
    pre-existing attempts_count column (retry attempts) that renaming to the
    same name would have collided with. contact_attempts_count disambiguates
    the customer-contact counter from the retry counter.
    """
    op.alter_column(
        "workflows", "touches_count", new_column_name="contact_attempts_count"
    )


def downgrade() -> None:
    op.alter_column(
        "workflows", "contact_attempts_count", new_column_name="touches_count"
    )
