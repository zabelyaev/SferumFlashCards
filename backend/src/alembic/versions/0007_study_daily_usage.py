"""Materialize unique daily quota usage and index membership history.

Revision ID: 0007
Revises: 0006

Stop old API writers before upgrading: daily usage is backfilled from review_logs,
then maintained transactionally by the new application, not by a database trigger.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_learning_cycles_membership_id"), "learning_cycles", ["membership_id"]
    )
    op.create_index(
        op.f("ix_study_sessions_membership_id"), "study_sessions", ["membership_id"]
    )
    op.create_table(
        "study_daily_cards",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("deck_id", sa.BigInteger(), nullable=False),
        sa.Column("study_date", sa.Date(), nullable=False),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        sa.Column("was_new", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_study_daily_cards_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id",
            "deck_id",
            "study_date",
            "card_id",
            name=op.f("pk_study_daily_cards"),
        ),
    )
    op.create_table(
        "study_daily_usage",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("deck_id", sa.BigInteger(), nullable=False),
        sa.Column("study_date", sa.Date(), nullable=False),
        sa.Column("total_used", sa.Integer(), nullable=False),
        sa.Column("new_used", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_study_daily_usage_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "user_id", "deck_id", "study_date", name=op.f("pk_study_daily_usage")
        ),
        sa.CheckConstraint(
            "total_used >= 0", name=op.f("ck_study_daily_usage_non_negative_total")
        ),
        sa.CheckConstraint(
            "new_used BETWEEN 0 AND total_used",
            name=op.f("ck_study_daily_usage_valid_new_usage"),
        ),
    )
    op.execute("""
        INSERT INTO study_daily_cards (user_id, deck_id, study_date, card_id, was_new)
        SELECT user_id, deck_id, study_date, card_id, bool_or(was_new)
        FROM review_logs GROUP BY user_id, deck_id, study_date, card_id
    """)
    op.execute("""
        INSERT INTO study_daily_usage
            (user_id, deck_id, study_date, total_used, new_used)
        SELECT user_id, deck_id, study_date,
            count(*), count(*) FILTER (WHERE was_new)
        FROM study_daily_cards GROUP BY user_id, deck_id, study_date
    """)


def downgrade() -> None:
    op.drop_table("study_daily_usage")
    op.drop_table("study_daily_cards")
    op.drop_index(op.f("ix_study_sessions_membership_id"), table_name="study_sessions")
    op.drop_index(
        op.f("ix_learning_cycles_membership_id"), table_name="learning_cycles"
    )
