from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from common.config.api_prefixes import ApiPrefix
from common.config.auth import AuthConfig
from common.config.cors import CorsConfig
from common.config.database import DatabaseConfig
from common.config.documentation import DocumentationConfig
from common.config.run import RunConfig
from common.config.study import StudyConfig

PROJECT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_nested_delimiter="__",
        env_prefix="APP_CONFIG__",
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    db: DatabaseConfig
    auth: AuthConfig = Field(default_factory=AuthConfig)
    cors: CorsConfig
    documentation: DocumentationConfig = Field(default_factory=DocumentationConfig)
    api: ApiPrefix = ApiPrefix()
    run: RunConfig = RunConfig()
    study: StudyConfig = Field(default_factory=StudyConfig)


settings = Settings()  # type: ignore
