"""add revocable rotating refresh sessions

Revision ID: a7d4c81b2f90
Revises: 5a8d5cda0a4b
Create Date: 2026-10-10

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a7d4c81b2f90"
down_revision: str | Sequence[str] | None = "5a8d5cda0a4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refresh_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    op.create_index("ix_refresh_sessions_expires_at", "refresh_sessions", ["expires_at"])
    op.create_table(
        "refresh_credentials",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["refresh_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_credentials_token_hash", "refresh_credentials", ["token_hash"], unique=True)
    op.create_index("ix_refresh_credentials_session_created", "refresh_credentials", ["session_id", "created_at"])
    op.create_index("ix_refresh_credentials_expires_at", "refresh_credentials", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_refresh_credentials_expires_at", table_name="refresh_credentials")
    op.drop_index("ix_refresh_credentials_session_created", table_name="refresh_credentials")
    op.drop_index("ix_refresh_credentials_token_hash", table_name="refresh_credentials")
    op.drop_table("refresh_credentials")
    op.drop_index("ix_refresh_sessions_expires_at", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_user_id", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
