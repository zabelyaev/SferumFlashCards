from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.database import Base
from common.database.mixins.int_id_pk import IntIdPkMixin

if TYPE_CHECKING:
    from application.accounts.users.database.models import User
    from application.flashcards.decks.database.models import Deck


class UserDeck(Base, IntIdPkMixin):
    __table_args__ = (UniqueConstraint("user_id", "deck_id"),)

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    deck_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("decks.id", ondelete="CASCADE"), index=True
    )
    is_favorite: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(lazy="raise")
    deck: Mapped["Deck"] = relationship(lazy="raise")
