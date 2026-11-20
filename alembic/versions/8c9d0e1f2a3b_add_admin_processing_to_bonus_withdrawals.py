"""add admin processing columns to bonus_withdrawals

Revision ID: 8c9d0e1f2a3b
Revises: 7a8b9c0d1e2f
Create Date: 2026-11-18

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8c9d0e1f2a3b"
down_revision: str | Sequence[str] | None = "7a8b9c0d1e2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bonus_withdrawals",
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "bonus_withdrawals",
        sa.Column(
            "processed_by_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "bonus_withdrawals",
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bonus_withdrawals",
        sa.Column("notes", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_bonus_withdrawals_processed_by_admin_id"),
        "bonus_withdrawals",
        ["processed_by_admin_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_bonus_withdrawals_processed_by_admin_id"),
        table_name="bonus_withdrawals",
    )
    op.drop_column("bonus_withdrawals", "notes")
    op.drop_column("bonus_withdrawals", "processed_at")
    op.drop_column("bonus_withdrawals", "processed_by_admin_id")
    op.drop_column("bonus_withdrawals", "rejection_reason")
