from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.database import Base
from common.database.mixins.int_id_pk import IntIdPkMixin
from common.database.mixins.timestamps import TimestampsMixin

if TYPE_CHECKING:
    from application.flashcards.decks.database.models import Deck


class Card(Base, IntIdPkMixin, TimestampsMixin):
    __table_args__ = (
        UniqueConstraint("id", "deck_id"),
        CheckConstraint("char_length(btrim(front)) > 0", name="non_empty_front"),
        CheckConstraint("char_length(btrim(back)) > 0", name="non_empty_back"),
        CheckConstraint("order_index >= 0", name="non_negative_order_index"),
        Index("idx_cards_deck_order", "deck_id", "order_index", "id"),
    )

    deck_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("decks.id", ondelete="CASCADE")
    )
    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)
    hint: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    deck: Mapped["Deck"] = relationship(back_populates="cards", lazy="raise")
