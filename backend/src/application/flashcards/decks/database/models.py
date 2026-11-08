import secrets
import string
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from application.shared.enums import ExamType, Subject
from common.database import Base
from common.database.mixins.int_id_pk import IntIdPkMixin
from common.database.mixins.timestamps import TimestampsMixin

if TYPE_CHECKING:
    from application.accounts.users.database.models import User
    from application.flashcards.cards.database.models import Card


def generate_share_code() -> str:
    alphabet = string.ascii_letters + string.digits + "_-"
    return "".join(secrets.choice(alphabet) for _ in range(8))


class Deck(Base, IntIdPkMixin, TimestampsMixin):
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(title)) BETWEEN 1 AND 100", name="title_length"
        ),
        CheckConstraint("char_length(description) <= 300", name="description_length"),
        CheckConstraint("grade BETWEEN 7 AND 11", name="grade_range"),
        CheckConstraint("cards_count >= 0", name="non_negative_cards_count"),
        CheckConstraint("share_code ~ '^[A-Za-z0-9_-]{8}$'", name="share_code_format"),
        Index(
            "idx_decks_catalog", "subject", "grade", postgresql_where=text("is_public")
        ),
        Index(
            "idx_decks_official", "is_official", postgresql_where=text("is_official")
        ),
    )

    author_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(300))
    subject: Mapped[Subject | None] = mapped_column(
        Enum(
            Subject,
            name="subject_type",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=True,
    )
    grade: Mapped[int | None] = mapped_column(SmallInteger)
    exam_type: Mapped[ExamType | None] = mapped_column(
        Enum(
            ExamType,
            name="exam_type",
            values_callable=lambda enum: [item.value for item in enum],
        )
    )
    cover_color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    is_official: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    share_code: Mapped[str] = mapped_column(
        String(8), unique=True, default=generate_share_code
    )
    cards_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    author: Mapped["User | None"] = relationship(lazy="raise")
    cards: Mapped[list["Card"]] = relationship(
        back_populates="deck",
        cascade="save-update, merge, delete, delete-orphan",
        passive_deletes=True,
        lazy="raise",
        order_by="Card.order_index, Card.id",
    )
