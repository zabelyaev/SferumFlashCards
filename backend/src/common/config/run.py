from typing import Annotated

from pydantic import BaseModel, Field


class RunConfig(BaseModel):
    host: str = "0.0.0.0"
    port: Annotated[int, Field(gt=0, le=65535)] = 8000
    workers: Annotated[int, Field(ge=1, le=64)] = 1
    backlog: Annotated[int, Field(ge=128, le=65535)] = 4096
    timeout_keep_alive: Annotated[int, Field(ge=1, le=300)] = 30
    timeout_graceful_shutdown: Annotated[int, Field(ge=1, le=300)] = 30
