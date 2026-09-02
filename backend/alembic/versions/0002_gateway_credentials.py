"""0002_gateway_credentials

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-02 09:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the singleton store for merchant-supplied gateway credentials."""
    op.create_table(
        "gateway_credentials",
        sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column("key_id", sa.Text(), nullable=False),
        sa.Column("key_secret", sa.Text(), nullable=False),
        sa.Column("webhook_secret", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_gateway_credentials_singleton"),
    )


def downgrade() -> None:
    op.drop_table("gateway_credentials")
