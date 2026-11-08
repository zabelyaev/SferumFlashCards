from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from common.database import Base
from common.database.mixins.int_id_pk import IntIdPkMixin


class LearningCycle(Base, IntIdPkMixin):
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    card_id: Mapped[int] = mapped_column(BigInteger)
    deck_id: Mapped[int] = mapped_column(BigInteger)
    membership_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_decks.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CardReview(Base, IntIdPkMixin):
    __table_args__ = (
        UniqueConstraint("user_id", "card_id"),
        ForeignKeyConstraint(
            ["card_id", "deck_id"], ["cards.id", "cards.deck_id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["user_id", "deck_id"],
            ["user_decks.user_id", "user_decks.deck_id"],
            ondelete="CASCADE",
        ),
        Index("idx_card_reviews_due", "user_id", "due_date"),
        Index("idx_card_reviews_deck_due", "user_id", "deck_id", "due_date"),
        Index("idx_card_reviews_card", "card_id", "deck_id"),
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    card_id: Mapped[int] = mapped_column(BigInteger)
    deck_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("decks.id", ondelete="CASCADE")
    )
    cycle_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("learning_cycles.id", ondelete="RESTRICT")
    )
    fsrs_state: Mapped[dict[str, Any]] = mapped_column(JSONB)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_reviewed: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StudySession(Base, IntIdPkMixin):
    __table_args__ = (
        UniqueConstraint("id", "user_id"),
        CheckConstraint("total_cards > 0", name="positive_total_cards"),
        CheckConstraint(
            "completed_cards BETWEEN 0 AND total_cards", name="completed_cards_range"
        ),
        CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')", name="valid_status"
        ),
        CheckConstraint(
            "(status = 'active') = (finished_at IS NULL)", name="status_matches_finish"
        ),
        CheckConstraint(
            "status <> 'completed' OR completed_cards = total_cards",
            name="completed_session_cards",
        ),
        Index(
            "uq_study_active_user_deck",
            "user_id",
            "historical_deck_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("idx_study_sessions_user_started", "user_id", "started_at"),
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    deck_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("decks.id", ondelete="SET NULL"), index=True
    )
    historical_deck_id: Mapped[int] = mapped_column(BigInteger)
    membership_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("user_decks.id", ondelete="SET NULL"), index=True
    )
    study_date: Mapped[date] = mapped_column(Date)
    timezone: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active"
    )
    total_cards: Mapped[int] = mapped_column(Integer)
    completed_cards: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    daily_total_cards_limit: Mapped[int] = mapped_column(Integer)
    daily_new_cards_limit: Mapped[int] = mapped_column(Integer)
    scheduler_config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    current_card_id: Mapped[int | None] = mapped_column(BigInteger)
    answer_token: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    day_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finish_reason: Mapped[str | None] = mapped_column(String(32))


class StudySessionCard(Base, IntIdPkMixin):
    __table_args__ = (
        UniqueConstraint("session_id", "card_id"),
        UniqueConstraint("session_id", "order_index"),
        CheckConstraint("card_id > 0", name="positive_card_id"),
        CheckConstraint(
            "source_card_id IS NULL OR source_card_id = card_id",
            name="matching_source_card",
        ),
        CheckConstraint(
            "jsonb_typeof(snapshot) = 'object' AND snapshot->>'id' IS NOT NULL "
            "AND snapshot->>'id' = card_id::text",
            name="matching_snapshot",
        ),
        CheckConstraint("order_index >= 0", name="non_negative_order_index"),
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("study_sessions.id", ondelete="CASCADE")
    )
    card_id: Mapped[int] = mapped_column(BigInteger, index=True)
    source_card_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("cards.id", ondelete="SET NULL"), index=True
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    order_index: Mapped[int] = mapped_column(Integer)
    fsrs_state: Mapped[dict[str, Any]] = mapped_column(JSONB)
    cycle_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("learning_cycles.id", ondelete="SET NULL")
    )
    was_new: Mapped[bool] = mapped_column(Boolean)
    attempts_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewLog(Base, IntIdPkMixin):
    __table_args__ = (
        UniqueConstraint("user_id", "answer_token"),
        ForeignKeyConstraint(
            ["session_id", "user_id"],
            ["study_sessions.id", "study_sessions.user_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["session_id", "card_id"],
            ["study_session_cards.session_id", "study_session_cards.card_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("rating BETWEEN 1 AND 4", name="rating_range"),
        Index("idx_review_logs_user_reviewed", "user_id", "reviewed_at"),
        Index("idx_review_logs_session_card", "session_id", "card_id"),
        Index("idx_review_logs_quota", "user_id", "deck_id", "study_date", "card_id"),
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    card_id: Mapped[int] = mapped_column(BigInteger, index=True)
    deck_id: Mapped[int] = mapped_column(BigInteger)
    session_id: Mapped[int] = mapped_column(BigInteger)
    cycle_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("learning_cycles.id", ondelete="SET NULL")
    )
    study_date: Mapped[date] = mapped_column(Date)
    answer_token: Mapped[str] = mapped_column(String(128))
    rating: Mapped[int] = mapped_column(SmallInteger)
    was_new: Mapped[bool] = mapped_column(Boolean)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StudyDailyCard(Base):
    """Unique quota consumption; historical IDs survive content/library deletion."""

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    deck_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    study_date: Mapped[date] = mapped_column(Date, primary_key=True)
    card_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    was_new: Mapped[bool] = mapped_column(Boolean)


class StudyDailyUsage(Base):
    _need_s_in_tn_ = False
    __table_args__ = (
        CheckConstraint("total_used >= 0", name="non_negative_total"),
        CheckConstraint("new_used BETWEEN 0 AND total_used", name="valid_new_usage"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    deck_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    study_date: Mapped[date] = mapped_column(Date, primary_key=True)
    total_used: Mapped[int] = mapped_column(Integer)
    new_used: Mapped[int] = mapped_column(Integer)
