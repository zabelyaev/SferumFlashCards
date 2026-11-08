from pydantic import ConfigDict

from common.schemas.base import BaseSchema


class ReadSchema(BaseSchema):
    model_config = ConfigDict(from_attributes=True)
