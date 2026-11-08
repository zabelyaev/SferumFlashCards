"""Add private per-user FSRS parameters.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("fsrs_parameters", postgresql.JSONB(), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_users_fsrs_parameters_shape"),
        "users",
        "fsrs_parameters IS NULL OR CASE "
        "WHEN jsonb_typeof(fsrs_parameters) = 'array' "
        "THEN jsonb_array_length(fsrs_parameters) = 21 ELSE false END",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_fsrs_parameters_shape"), "users", type_="check")
    op.drop_column("users", "fsrs_parameters")
