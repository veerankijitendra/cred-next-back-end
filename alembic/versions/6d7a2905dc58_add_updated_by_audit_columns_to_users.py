"""add updated_by audit columns to users

Revision ID: 6d7a2905dc58
Revises: c8e51b3a9021
Create Date: 2026-11-03

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6d7a2905dc58"
down_revision: str | Sequence[str] | None = "c8e51b3a9021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("updated_by_name", sa.String(length=150), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_updated_by_user_id_users",
        "users",
        "users",
        ["updated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_users_updated_by_user_id_users",
        "users",
        type_="foreignkey",
    )
    op.drop_column("users", "updated_by_name")
    op.drop_column("users", "updated_by_user_id")
