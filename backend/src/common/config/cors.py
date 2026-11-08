from pydantic import BaseModel, Field


class CorsConfig(BaseModel):
    origins: list[str] = Field(default_factory=lambda: ["*"])
