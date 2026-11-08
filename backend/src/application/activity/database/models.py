from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from common.database import Base
from common.database.mixins.int_id_pk import IntIdPkMixin

if TYPE_CHECKING:
    from application.accounts.users.database.models import User


class UserDailyActivity(Base, IntIdPkMixin):
    _need_s_in_tn_ = False

    __table_args__ = (
        UniqueConstraint("user_id", "activity_date"),
        CheckConstraint("cards_reviewed >= 0", name="non_negative_cards_reviewed"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE")
    )
    activity_date: Mapped[date] = mapped_column(Date)
    cards_reviewed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    user: Mapped["User"] = relationship(lazy="raise")
