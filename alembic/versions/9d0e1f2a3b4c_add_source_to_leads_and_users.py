"""add source column to leads and users

Revision ID: 9d0e1f2a3b4c
Revises: 8c9d0e1f2a3b
Create Date: 2026-11-25

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "9d0e1f2a3b4c"
down_revision: str | Sequence[str] | None = "8c9d0e1f2a3b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("source", sa.String(length=50), nullable=False, server_default="Browser"),
    )
    op.create_index(
        op.f("ix_leads_source"),
        "leads",
        ["source"],
        unique=False,
    )
    op.add_column(
        "users",
        sa.Column("source", sa.String(length=50), nullable=False, server_default="Browser"),
    )


def downgrade() -> None:
    op.drop_column("users", "source")
    op.drop_index(op.f("ix_leads_source"), table_name="leads")
    op.drop_column("leads", "source")
