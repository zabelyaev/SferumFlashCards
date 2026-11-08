"""Replace the user study limit with separate total and new limits.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "daily_total_cards_limit",
            sa.Integer(),
            nullable=False,
            server_default="125",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "daily_new_cards_limit", sa.Integer(), nullable=False, server_default="12"
        ),
    )
    op.create_check_constraint(
        op.f("ck_users_daily_total_cards_limit"),
        "users",
        "daily_total_cards_limit BETWEEN 20 AND 1000",
    )
    op.create_check_constraint(
        op.f("ck_users_daily_new_cards_limit"),
        "users",
        "daily_new_cards_limit BETWEEN 1 AND 250",
    )
    op.drop_constraint(op.f("ck_users_daily_cards_limit"), "users", type_="check")
    op.drop_column("users", "daily_cards_limit")


def downgrade() -> None:

    raise RuntimeError(
        "Downgrade requires an explicit policy for the two study limits."
    )
