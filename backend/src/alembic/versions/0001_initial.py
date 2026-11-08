"""Create the presentation MVP schema with VK users and durable study history.

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM(
    "student", "teacher", "admin", name="user_role", create_type=False
)
subject_type = postgresql.ENUM(
    "physics",
    "algebra",
    "geometry",
    "chemistry",
    "biology",
    "history",
    "russian",
    "informatics",
    "english",
    "other",
    name="subject_type",
    create_type=False,
)
exam_type = postgresql.ENUM("oge", "ege", name="exam_type", create_type=False)
card_review_state = postgresql.ENUM(
    "new",
    "learning",
    "review",
    "relearning",
    name="card_review_state",
    create_type=False,
)
study_session_status = postgresql.ENUM(
    "active", "completed", "abandoned", name="study_session_status", create_type=False
)
enum_types = (
    user_role,
    subject_type,
    exam_type,
    card_review_state,
    study_session_status,
)

user_checks = (
    ("positive_vk_user_id", "vk_user_id > 0"),
    ("non_negative_streak", "streak_days >= 0"),
    ("valid_max_streak", "max_streak_days >= streak_days"),
    ("daily_cards_limit", "daily_cards_limit BETWEEN 5 AND 50"),
    ("settings_object", "jsonb_typeof(settings) = 'object'"),
)


def _id() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True)


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def _updated_at() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def _check(table: str, name: str, expression: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(expression, name=op.f(f"ck_{table}_{name}"))


def upgrade() -> None:
    for enum in enum_types:
        enum.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "users",
        _id(),
        sa.Column("vk_user_id", sa.BigInteger(), nullable=False),
        sa.Column("first_name", sa.String(100), server_default="", nullable=False),
        sa.Column("last_name", sa.String(100), server_default="", nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("role", user_role, server_default="student", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("timezone", sa.String(64), server_default="UTC", nullable=False),
        sa.Column("streak_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_streak_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_streak_date", sa.Date(), nullable=True),
        sa.Column(
            "daily_cards_limit", sa.Integer(), server_default="20", nullable=False
        ),
        sa.Column(
            "settings",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        _created_at(),
        _updated_at(),
        sa.UniqueConstraint("vk_user_id", name=op.f("uq_users_vk_user_id")),
    )
    for name, expression in user_checks:
        op.create_check_constraint(op.f(f"ck_users_{name}"), "users", expression)

    op.create_table(
        "decks",
        _id(),
        sa.Column("author_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("subject", subject_type, nullable=False),
        sa.Column("grade", sa.SmallInteger(), nullable=True),
        sa.Column("exam_type", exam_type, nullable=True),
        sa.Column(
            "cover_color", sa.String(32), server_default="gradient-blue", nullable=False
        ),
        sa.Column("is_public", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_official", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("share_code", sa.String(8), nullable=False),
        sa.Column("cards_count", sa.Integer(), server_default="0", nullable=False),
        _created_at(),
        _updated_at(),
        _check("decks", "title_length", "char_length(btrim(title)) BETWEEN 1 AND 100"),
        _check("decks", "description_length", "char_length(description) <= 300"),
        _check("decks", "grade_range", "grade BETWEEN 7 AND 11"),
        _check("decks", "non_negative_cards_count", "cards_count >= 0"),
        _check("decks", "share_code_format", "share_code ~ '^[A-Za-z0-9_-]{8}$'"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("share_code", name=op.f("uq_decks_share_code")),
    )
    op.create_index("ix_decks_author_id", "decks", ["author_id"])
    op.create_index(
        "idx_decks_catalog",
        "decks",
        ["subject", "grade"],
        postgresql_where=sa.text("is_public"),
    )
    op.create_index(
        "idx_decks_official",
        "decks",
        ["is_official"],
        postgresql_where=sa.text("is_official"),
    )

    op.create_table(
        "cards",
        _id(),
        sa.Column("deck_id", sa.BigInteger(), nullable=False),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("hint", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), server_default="0", nullable=False),
        _created_at(),
        _updated_at(),
        _check("cards", "non_empty_front", "char_length(btrim(front)) > 0"),
        _check("cards", "non_empty_back", "char_length(btrim(back)) > 0"),
        _check("cards", "non_negative_order_index", "order_index >= 0"),
        sa.ForeignKeyConstraint(["deck_id"], ["decks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "deck_id", name=op.f("uq_cards_id_deck_id")),
    )
    op.create_index("idx_cards_deck_order", "cards", ["deck_id", "order_index", "id"])

    op.create_table(
        "user_decks",
        _id(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("deck_id", sa.BigInteger(), nullable=False),
        sa.Column("is_favorite", sa.Boolean(), server_default="false", nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deck_id"], ["decks.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "deck_id", name=op.f("uq_user_decks_user_id_deck_id")
        ),
    )
    op.create_index("ix_user_decks_deck_id", "user_decks", ["deck_id"])

    op.create_table(
        "card_reviews",
        _id(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        sa.Column("deck_id", sa.BigInteger(), nullable=False),
        sa.Column("state", card_review_state, server_default="new", nullable=False),
        sa.Column("repetitions", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "ease_factor", sa.Numeric(4, 2), server_default="2.50", nullable=False
        ),
        sa.Column("interval_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lapses", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "due_date",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_reviewed", sa.DateTime(timezone=True), nullable=True),
        _check("card_reviews", "non_negative_repetitions", "repetitions >= 0"),
        _check("card_reviews", "minimum_ease_factor", "ease_factor >= 1.30"),
        _check("card_reviews", "non_negative_interval", "interval_days >= 0"),
        _check("card_reviews", "non_negative_lapses", "lapses >= 0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deck_id"], ["decks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["card_id", "deck_id"], ["cards.id", "cards.deck_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "deck_id"],
            ["user_decks.user_id", "user_decks.deck_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "user_id", "card_id", name=op.f("uq_card_reviews_user_id_card_id")
        ),
    )
    op.create_index("idx_card_reviews_due", "card_reviews", ["user_id", "due_date"])
    op.create_index(
        "idx_card_reviews_deck_due", "card_reviews", ["user_id", "deck_id", "due_date"]
    )
    op.create_index("idx_card_reviews_card", "card_reviews", ["card_id", "deck_id"])

    op.create_table(
        "study_sessions",
        _id(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("deck_id", sa.BigInteger(), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column(
            "status", study_session_status, server_default="active", nullable=False
        ),
        sa.Column("total_cards", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_cards", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reviewed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("correct_answers", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _check("study_sessions", "non_negative_total_cards", "total_cards >= 0"),
        _check(
            "study_sessions",
            "completed_cards_range",
            "completed_cards BETWEEN 0 AND total_cards",
        ),
        _check(
            "study_sessions",
            "reviewed_count_range",
            "reviewed_count >= completed_cards",
        ),
        _check(
            "study_sessions",
            "correct_answers_range",
            "correct_answers BETWEEN 0 AND reviewed_count",
        ),
        _check("study_sessions", "non_negative_duration", "duration_ms >= 0"),
        _check(
            "study_sessions",
            "status_matches_finish",
            "(status = 'active') = (finished_at IS NULL)",
        ),
        _check("study_sessions", "finish_after_start", "finished_at >= started_at"),
        _check(
            "study_sessions",
            "completed_session_cards",
            "status <> 'completed' OR "
            "(total_cards > 0 AND completed_cards = total_cards)",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deck_id"], ["decks.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("id", "user_id", name=op.f("uq_study_sessions_id_user_id")),
    )
    op.create_index(
        "idx_study_sessions_user_started", "study_sessions", ["user_id", "started_at"]
    )
    op.create_index("ix_study_sessions_deck_id", "study_sessions", ["deck_id"])

    op.create_table(
        "study_session_cards",
        _id(),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        sa.Column("source_card_id", sa.BigInteger(), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("initial_state", card_review_state, nullable=False),
        sa.Column("attempts_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_rating", sa.SmallInteger(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _check("study_session_cards", "positive_card_id", "card_id > 0"),
        _check(
            "study_session_cards",
            "matching_source_card",
            "source_card_id IS NULL OR source_card_id = card_id",
        ),
        _check(
            "study_session_cards",
            "matching_snapshot",
            "jsonb_typeof(snapshot) = 'object' "
            "AND snapshot->>'id' IS NOT NULL "
            "AND snapshot->>'id' = card_id::text",
        ),
        _check("study_session_cards", "non_negative_order_index", "order_index >= 0"),
        _check("study_session_cards", "non_negative_attempts", "attempts_count >= 0"),
        _check(
            "study_session_cards", "last_rating_range", "last_rating BETWEEN 1 AND 4"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["study_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["source_card_id"], ["cards.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "session_id",
            "card_id",
            name=op.f("uq_study_session_cards_session_id_card_id"),
        ),
        sa.UniqueConstraint(
            "session_id",
            "order_index",
            name=op.f("uq_study_session_cards_session_id_order_index"),
        ),
    )
    op.create_index(
        "ix_study_session_cards_card_id", "study_session_cards", ["card_id"]
    )
    op.create_index(
        "ix_study_session_cards_source_card_id",
        "study_session_cards",
        ["source_card_id"],
    )

    op.create_table(
        "review_logs",
        _id(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("was_new", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        _check("review_logs", "rating_range", "rating BETWEEN 1 AND 4"),
        _check("review_logs", "non_negative_duration", "duration_ms >= 0"),
        _check(
            "review_logs",
            "idempotency_key_length",
            "char_length(idempotency_key) BETWEEN 1 AND 128",
        ),
        _check("review_logs", "request_hash_format", "request_hash ~ '^[a-f0-9]{64}$'"),
        _check("review_logs", "result_object", "jsonb_typeof(result) = 'object'"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
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
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name=op.f("uq_review_logs_user_id_idempotency_key"),
        ),
    )
    op.create_index(
        "idx_review_logs_user_reviewed", "review_logs", ["user_id", "reviewed_at"]
    )
    op.create_index(
        "idx_review_logs_session_card", "review_logs", ["session_id", "card_id"]
    )
    op.create_index("ix_review_logs_card_id", "review_logs", ["card_id"])

    op.create_table(
        "user_daily_activity",
        _id(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("cards_reviewed", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "time_spent_sec", sa.BigInteger(), server_default="0", nullable=False
        ),
        _check(
            "user_daily_activity", "non_negative_cards_reviewed", "cards_reviewed >= 0"
        ),
        _check("user_daily_activity", "non_negative_time_spent", "time_spent_sec >= 0"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id",
            "activity_date",
            name=op.f("uq_user_daily_activity_user_id_activity_date"),
        ),
    )
    op.create_index(
        "idx_user_activity_recent", "user_daily_activity", ["user_id", "activity_date"]
    )


def downgrade() -> None:
    for table in (
        "review_logs",
        "study_session_cards",
        "card_reviews",
        "user_decks",
        "study_sessions",
        "cards",
        "user_daily_activity",
        "decks",
        "users",
    ):
        op.drop_table(table)

    for enum in reversed(enum_types):
        enum.drop(op.get_bind(), checkfirst=False)
