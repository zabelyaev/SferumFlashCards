from pydantic import BaseModel

from common.config.api_prefixes.v1 import ApiV1Prefix


class ApiPrefix(BaseModel):
    prefix: str = "/api"
    v1: ApiV1Prefix = ApiV1Prefix()
