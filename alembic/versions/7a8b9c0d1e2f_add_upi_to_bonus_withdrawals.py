"""add upi fields to bonus_withdrawals

Revision ID: 7a8b9c0d1e2f
Revises: e5c7a109bf34
Create Date: 2026-11-18

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "7a8b9c0d1e2f"
down_revision: str | Sequence[str] | None = "e5c7a109bf34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bonus_withdrawals",
        sa.Column("payout_method", sa.String(length=50), nullable=False, server_default="upi"),
    )
    op.add_column(
        "bonus_withdrawals",
        sa.Column("upi_id", sa.String(length=100), nullable=True),
    )
    op.alter_column(
        "bonus_withdrawals",
        "account_number",
        existing_type=sa.String(length=50),
        nullable=True,
    )
    op.alter_column(
        "bonus_withdrawals",
        "ifsc_code",
        existing_type=sa.String(length=20),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "bonus_withdrawals",
        "ifsc_code",
        existing_type=sa.String(length=20),
        nullable=False,
    )
    op.alter_column(
        "bonus_withdrawals",
        "account_number",
        existing_type=sa.String(length=50),
        nullable=False,
    )
    op.drop_column("bonus_withdrawals", "upi_id")
    op.drop_column("bonus_withdrawals", "payout_method")
