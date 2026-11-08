from datetime import date
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from application.shared.enums import UserRole
from common.database import Base
from common.database.mixins.int_id_pk import IntIdPkMixin
from common.database.mixins.timestamps import TimestampsMixin


class User(Base, IntIdPkMixin, TimestampsMixin):
    __table_args__ = (
        CheckConstraint("vk_user_id > 0", name="positive_vk_user_id"),
        CheckConstraint("streak_days >= 0", name="non_negative_streak"),
        CheckConstraint("max_streak_days >= streak_days", name="valid_max_streak"),
        CheckConstraint(
            "daily_total_cards_limit BETWEEN 20 AND 1000",
            name="daily_total_cards_limit",
        ),
        CheckConstraint(
            "daily_new_cards_limit BETWEEN 1 AND 250", name="daily_new_cards_limit"
        ),
        CheckConstraint("jsonb_typeof(settings) = 'object'", name="settings_object"),
        CheckConstraint(
            "fsrs_parameters IS NULL OR CASE "
            "WHEN jsonb_typeof(fsrs_parameters) = 'array' "
            "THEN jsonb_array_length(fsrs_parameters) = 21 ELSE false END",
            name="fsrs_parameters_shape",
        ),
    )

    vk_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    first_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    last_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    avatar_url: Mapped[str | None] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=UserRole.STUDENT,
        server_default=UserRole.STUDENT.value,
    )
    timezone: Mapped[str] = mapped_column(
        String(64), default="UTC", server_default="UTC"
    )
    streak_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_streak_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_streak_date: Mapped[date | None] = mapped_column(Date)

    daily_total_cards_limit: Mapped[int] = mapped_column(
        Integer, default=125, server_default="125"
    )
    daily_new_cards_limit: Mapped[int] = mapped_column(
        Integer, default=12, server_default="12"
    )

    fsrs_parameters: Mapped[list[float] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )

    settings: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB), default=dict, server_default=text("'{}'::jsonb")
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
