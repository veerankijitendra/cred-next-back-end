"""add acquisition_sources table and seed initial sources

Revision ID: ae1f2b3c4d5e
Revises: 9d0e1f2a3b4c
Create Date: 2026-11-25

"""
from collections.abc import Sequence
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "ae1f2b3c4d5e"
down_revision: str | Sequence[str] | None = "9d0e1f2a3b4c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "acquisition_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("normalized_key", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("normalized_key"),
    )
    op.create_index(op.f("ix_acquisition_sources_name"), "acquisition_sources", ["name"], unique=True)
    op.create_index(
        op.f("ix_acquisition_sources_normalized_key"),
        "acquisition_sources",
        ["normalized_key"],
        unique=True,
    )

    sources_table = sa.table(
        "acquisition_sources",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("normalized_key", sa.String()),
        sa.column("description", sa.String()),
        sa.column("is_system", sa.Boolean()),
    )

    op.bulk_insert(
        sources_table,
        [
            {
                "id": uuid4(),
                "name": "Browser",
                "normalized_key": "browser",
                "description": "Default organic website browser traffic",
                "is_system": True,
            },
            {
                "id": uuid4(),
                "name": "BrightFitness",
                "normalized_key": "brightfitness",
                "description": "BrightFitness gym partner QR campaign",
                "is_system": False,
            },
            {
                "id": uuid4(),
                "name": "V-Card",
                "normalized_key": "v-card",
                "description": "Visiting Card physical QR campaign",
                "is_system": False,
            },
            {
                "id": uuid4(),
                "name": "P-Card",
                "normalized_key": "p-card",
                "description": "Promotion Card QR campaign",
                "is_system": False,
            },
            {
                "id": uuid4(),
                "name": "SH",
                "normalized_key": "sh",
                "description": "SH partner hub QR campaign",
                "is_system": False,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_acquisition_sources_normalized_key"), table_name="acquisition_sources")
    op.drop_index(op.f("ix_acquisition_sources_name"), table_name="acquisition_sources")
    op.drop_table("acquisition_sources")
