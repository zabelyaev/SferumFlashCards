"""Allow decks without a subject or cover color.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "decks",
        "subject",
        existing_type=postgresql.ENUM(name="subject_type", create_type=False),
        existing_nullable=False,
        nullable=True,
    )
    op.alter_column(
        "decks",
        "cover_color",
        existing_type=sa.String(length=32),
        existing_nullable=False,
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:

    op.alter_column(
        "decks",
        "subject",
        existing_type=postgresql.ENUM(name="subject_type", create_type=False),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        "decks",
        "cover_color",
        existing_type=sa.String(length=32),
        existing_nullable=True,
        nullable=False,
        server_default="gradient-blue",
    )
