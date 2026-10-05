"""add user reference id

Revision ID: 1c2c980dfb78
Revises: 39a6bf28a52b
Create Date: 2026-10-02 13:02:17.061084

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1c2c980dfb78"
down_revision: str | Sequence[str] | None = "39a6bf28a52b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # ---------------------------------------------------------
    # 1. Add the column as nullable first.
    #    Existing users do not have a reference_id yet.
    # ---------------------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "reference_id",
            sa.String(length=45),
            nullable=True,
        ),
    )

    # ---------------------------------------------------------
    # 2. Backfill existing users.
    #
    # Example:
    # user.id:
    # 550e8400-e29b-41d4-a716-446655440000
    #
    # becomes:
    # CNX-REF-550e8400e29b41d4a716446655440000
    #
    # UUID is unique, therefore the generated reference_id
    # is also unique.
    # ---------------------------------------------------------
    op.execute(
        """
        UPDATE users
        SET reference_id =
            'CNX-REF-' || REPLACE(id::text, '-', '')
        WHERE reference_id IS NULL
        """
    )

    # ---------------------------------------------------------
    # 3. Make sure every existing user was backfilled.
    # ---------------------------------------------------------
    bind = op.get_bind()

    null_count = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM users
            WHERE reference_id IS NULL
            """
        )
    ).scalar_one()

    if null_count != 0:
        raise RuntimeError(
            f"Reference ID backfill failed. "
            f"{null_count} users still have NULL reference_id."
        )

    # ---------------------------------------------------------
    # 4. Make reference_id mandatory.
    # ---------------------------------------------------------
    op.alter_column(
        "users",
        "reference_id",
        existing_type=sa.String(length=45),
        nullable=False,
    )

    # ---------------------------------------------------------
    # 5. Add UNIQUE constraint.
    # ---------------------------------------------------------
    op.create_unique_constraint(
        "uq_users_reference_id",
        "users",
        ["reference_id"],
    )

    # ---------------------------------------------------------
    # 6. Add index for fast referral lookup.
    #
    # PostgreSQL automatically creates an index for the
    # UNIQUE constraint, so a separate index is technically
    # unnecessary.
    # ---------------------------------------------------------


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_users_reference_id",
        "users",
        type_="unique",
    )

    op.drop_column(
        "users",
        "reference_id",
    )
