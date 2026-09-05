"""0003_oauth_connection

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-02 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the Razorpay Partner OAuth connection and pending-state tables."""
    op.create_table(
        "oauth_connection",
        sa.Column("id", sa.Integer(), primary_key=True, server_default="1"),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("public_token", sa.Text(), nullable=True),
        sa.Column("razorpay_account_id", sa.Text(), nullable=True),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Text(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_oauth_connection_singleton"),
    )

    # Issued authorization states, single-use. Persisted rather than in-process so
    # a callback reaching another worker still verifies.
    op.create_table(
        "oauth_auth_state",
        sa.Column("state", sa.Text(), primary_key=True),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_oauth_auth_state_created_at", "oauth_auth_state", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_oauth_auth_state_created_at", table_name="oauth_auth_state")
    op.drop_table("oauth_auth_state")
    op.drop_table("oauth_connection")
