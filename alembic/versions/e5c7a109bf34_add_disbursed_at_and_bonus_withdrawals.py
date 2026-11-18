"""add disbursed_at to leads and create bonus_withdrawals table

Revision ID: e5c7a109bf34
Revises: 6d7a2905dc58
Create Date: 2026-11-18

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e5c7a109bf34"
down_revision: str | Sequence[str] | None = "6d7a2905dc58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add disbursed_at to leads
    op.add_column(
        "leads",
        sa.Column("disbursed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. Create bonus_withdrawals table
    op.create_table(
        "bonus_withdrawals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("loan_type", sa.String(length=50), nullable=False),
        sa.Column("disbursed_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("commission_rate", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("gross_bonus", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("tds_rate", sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column("tds_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("net_bonus", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("cooling_period_end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("account_number", sa.String(length=50), nullable=False),
        sa.Column("ifsc_code", sa.String(length=20), nullable=False),
        sa.Column("account_holder_name", sa.String(length=150), nullable=False),
        sa.Column("transaction_reference", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"],
            name="fk_bonus_withdrawals_lead_id_leads",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_bonus_withdrawals_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("lead_id", name="uq_bonus_withdrawals_lead_id"),
    )
    op.create_index(
        "ix_bonus_withdrawals_lead_id",
        "bonus_withdrawals",
        ["lead_id"],
        unique=True,
    )
    op.create_index(
        "ix_bonus_withdrawals_user_id",
        "bonus_withdrawals",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bonus_withdrawals_user_id", table_name="bonus_withdrawals")
    op.drop_index("ix_bonus_withdrawals_lead_id", table_name="bonus_withdrawals")
    op.drop_table("bonus_withdrawals")
    op.drop_column("leads", "disbursed_at")
