from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, declared_attr

from common.config import settings
from common.utils import camel_case_to_snake_case


class Base(DeclarativeBase):
    _need_s_in_tn_ = True
    __abstract__ = True

    metadata = MetaData(
        naming_convention=settings.db.sqla.naming_convention,
    )

    @declared_attr.directive
    def __tablename__(cls) -> str:
        name = camel_case_to_snake_case(cls.__name__)
        return f"{name}s" if cls._need_s_in_tn_ else name
