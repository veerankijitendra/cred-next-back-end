"""add is_active and title to users table

Revision ID: c8e51b3a9021
Revises: a7d4c81b2f90
Create Date: 2026-10-28

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c8e51b3a9021"
down_revision: str | Sequence[str] | None = "a7d4c81b2f90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "users",
        sa.Column("title", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "title")
    op.drop_column("users", "is_active")

