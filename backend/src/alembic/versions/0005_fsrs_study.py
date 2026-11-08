"""Prepare durable FSRS study state; reject legacy history rather than lose it.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM card_reviews) OR EXISTS (SELECT 1 FROM study_sessions)
         OR EXISTS (SELECT 1 FROM study_session_cards)
         OR EXISTS (SELECT 1 FROM review_logs)
         OR EXISTS (SELECT 1 FROM user_daily_activity WHERE time_spent_sec <> 0) THEN
        RAISE EXCEPTION 'Legacy study history requires an explicit data migration';
      END IF;
    END $$
    """)
    op.drop_table("review_logs")
    op.drop_table("study_session_cards")
    op.drop_table("study_sessions")
    op.drop_table("card_reviews")

    def identity() -> sa.Column:
        return sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True)

    def fk(
        name: str, target: str, ondelete: str, *, nullable: bool = False
    ) -> sa.Column:
        return sa.Column(
            name,
            sa.BigInteger(),
            sa.ForeignKey(target, ondelete=ondelete),
            nullable=nullable,
        )

    op.create_table(
        "learning_cycles",
        identity(),
        fk("user_id", "users.id", "CASCADE"),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        sa.Column("deck_id", sa.BigInteger(), nullable=False),
        fk("membership_id", "user_decks.id", "SET NULL", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_learning_cycles_user_id"), "learning_cycles", ["user_id"])
    op.create_table(
        "study_sessions",
        identity(),
        fk("user_id", "users.id", "CASCADE"),
        fk("deck_id", "decks.id", "SET NULL", nullable=True),
        sa.Column("historical_deck_id", sa.BigInteger(), nullable=False),
        fk("membership_id", "user_decks.id", "SET NULL", nullable=True),
        sa.Column("study_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("total_cards", sa.Integer(), nullable=False),
        sa.Column("completed_cards", sa.Integer(), server_default="0", nullable=False),
        sa.Column("daily_total_cards_limit", sa.Integer(), nullable=False),
        sa.Column("daily_new_cards_limit", sa.Integer(), nullable=False),
        sa.Column("scheduler_config", postgresql.JSONB(), nullable=False),
        sa.Column("current_card_id", sa.BigInteger(), nullable=True),
        sa.Column("answer_token", sa.String(128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("day_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finish_reason", sa.String(32), nullable=True),
        sa.UniqueConstraint("id", "user_id"),
        sa.CheckConstraint(
            "total_cards > 0", name=op.f("ck_study_sessions_positive_total_cards")
        ),
        sa.CheckConstraint(
            "completed_cards BETWEEN 0 AND total_cards",
            name=op.f("ck_study_sessions_completed_cards_range"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')",
            name=op.f("ck_study_sessions_valid_status"),
        ),
        sa.CheckConstraint(
            "(status = 'active') = (finished_at IS NULL)",
            name=op.f("ck_study_sessions_status_matches_finish"),
        ),
        sa.CheckConstraint(
            "status <> 'completed' OR completed_cards = total_cards",
            name=op.f("ck_study_sessions_completed_session_cards"),
        ),
    )
    op.create_index(op.f("ix_study_sessions_deck_id"), "study_sessions", ["deck_id"])
    op.create_index(
        "idx_study_sessions_user_started", "study_sessions", ["user_id", "started_at"]
    )
    op.create_index(
        "uq_study_active_user_deck",
        "study_sessions",
        ["user_id", "historical_deck_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "study_session_cards",
        identity(),
        fk("session_id", "study_sessions.id", "CASCADE"),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        fk("source_card_id", "cards.id", "SET NULL", nullable=True),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("fsrs_state", postgresql.JSONB(), nullable=False),
        fk("cycle_id", "learning_cycles.id", "SET NULL", nullable=True),
        sa.Column("was_new", sa.Boolean(), nullable=False),
        sa.Column("attempts_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "card_id"),
        sa.UniqueConstraint("session_id", "order_index"),
        sa.CheckConstraint(
            "card_id > 0", name=op.f("ck_study_session_cards_positive_card_id")
        ),
        sa.CheckConstraint(
            "source_card_id IS NULL OR source_card_id = card_id",
            name=op.f("ck_study_session_cards_matching_source_card"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(snapshot) = 'object' AND snapshot->>'id' IS NOT NULL "
            "AND snapshot->>'id' = card_id::text",
            name=op.f("ck_study_session_cards_matching_snapshot"),
        ),
        sa.CheckConstraint(
            "order_index >= 0",
            name=op.f("ck_study_session_cards_non_negative_order_index"),
        ),
    )
    op.create_index(
        op.f("ix_study_session_cards_card_id"), "study_session_cards", ["card_id"]
    )
    op.create_index(
        op.f("ix_study_session_cards_source_card_id"),
        "study_session_cards",
        ["source_card_id"],
    )
    op.create_table(
        "card_reviews",
        identity(),
        fk("user_id", "users.id", "CASCADE"),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        fk("deck_id", "decks.id", "CASCADE"),
        fk("cycle_id", "learning_cycles.id", "RESTRICT"),
        sa.Column("fsrs_state", postgresql.JSONB(), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_reviewed", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "card_id"),
        sa.ForeignKeyConstraint(
            ["card_id", "deck_id"], ["cards.id", "cards.deck_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "deck_id"],
            ["user_decks.user_id", "user_decks.deck_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_card_reviews_due", "card_reviews", ["user_id", "due_date"])
    op.create_index(
        "idx_card_reviews_deck_due", "card_reviews", ["user_id", "deck_id", "due_date"]
    )
    op.create_index("idx_card_reviews_card", "card_reviews", ["card_id", "deck_id"])
    op.create_table(
        "review_logs",
        identity(),
        fk("user_id", "users.id", "CASCADE"),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        sa.Column("deck_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        fk("cycle_id", "learning_cycles.id", "SET NULL", nullable=True),
        sa.Column("study_date", sa.Date(), nullable=False),
        sa.Column("answer_token", sa.String(128), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("was_new", sa.Boolean(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "answer_token"),
        sa.ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["study_sessions.id", "study_sessions.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "card_id"],
            ["study_session_cards.session_id", "study_session_cards.card_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "rating BETWEEN 1 AND 4", name=op.f("ck_review_logs_rating_range")
        ),
    )
    op.create_index(op.f("ix_review_logs_card_id"), "review_logs", ["card_id"])
    op.create_index(
        "idx_review_logs_user_reviewed", "review_logs", ["user_id", "reviewed_at"]
    )
    op.create_index(
        "idx_review_logs_session_card", "review_logs", ["session_id", "card_id"]
    )
    op.create_index(
        "idx_review_logs_quota",
        "review_logs",
        ["user_id", "deck_id", "study_date", "card_id"],
    )
    op.add_column(
        "user_daily_activity",
        sa.Column("completed", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.drop_constraint(
        op.f("ck_user_daily_activity_non_negative_time_spent"),
        "user_daily_activity",
        type_="check",
    )
    op.drop_column("user_daily_activity", "time_spent_sec")


def downgrade() -> None:
    raise RuntimeError("Downgrade requires an explicit policy for FSRS study history.")
