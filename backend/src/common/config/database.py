from pydantic import BaseModel, NonNegativeInt, PositiveInt, SecretStr
from sqlalchemy import URL


class SQLAConfig(BaseModel):
    pool_size: PositiveInt = 5
    max_overflow: NonNegativeInt = 10
    echo: bool = False
    echo_pool: bool = False

    naming_convention: dict[str, str] = {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }


class DatabaseConfig(BaseModel):
    name: str = "database"
    host: str = "localhost"
    port: PositiveInt = 5432
    user: str = "app"
    password: SecretStr

    sqla: SQLAConfig = SQLAConfig()

    @property
    def async_url(self) -> str:
        return URL.create(
            drivername="postgresql+asyncpg",
            database=self.name,
            host=self.host,
            port=self.port,
            username=self.user,
            password=self.password.get_secret_value(),
        ).render_as_string(hide_password=False)
