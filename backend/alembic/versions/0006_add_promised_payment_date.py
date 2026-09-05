"""0006_add_promised_payment_date

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-05 23:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add promised_payment_date to cases, tracking the P2P_WAITING follow-up date."""
    op.add_column(
        "cases",
        sa.Column("promised_payment_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "cases",
        sa.Column(
            "p2p_reminder_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.create_index(
        "idx_cases_promised_payment_date", "cases", ["promised_payment_date"]
    )


def downgrade() -> None:
    op.drop_index("idx_cases_promised_payment_date", table_name="cases")
    op.drop_column("cases", "p2p_reminder_count")
    op.drop_column("cases", "promised_payment_date")
