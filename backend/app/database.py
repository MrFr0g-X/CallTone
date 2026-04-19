from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker


class Settings(BaseSettings):
    APP_NAME: str = "CallTone API"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api"

    DB_HOST: str = ""
    DB_PORT: int = 5432
    DB_NAME: str = "calltone_db"
    DB_USER: str = ""
    DB_PASSWORD: str = ""

    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    ALGORITHM: str = "HS256"
    FRONTEND_URL: str = "http://localhost:8080"
    CORS_ORIGINS: str = ""  # comma-separated extra origins, e.g. "http://gpu-server:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def use_sqlite(self) -> bool:
        return not self.DB_HOST

    @property
    def DATABASE_URL(self) -> str:
        if self.use_sqlite:
            db_path = Path(__file__).resolve().parent.parent / "calltone.db"
            return f"sqlite:///{db_path}"
        return (
            f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()


# ── Production SECRET_KEY guard ──────────────────────────────────────────────
# When DEBUG=false the JWT signing key MUST NOT be the dev default.
# Refusing to boot is intentional — a warning would be ignored and the
# resulting deploy would be trivially compromised (anyone can forge
# tokens against the well-known default).
_DEV_SECRET_KEY_DEFAULT = "dev-secret-key-change-in-production"
if not settings.DEBUG and settings.SECRET_KEY == _DEV_SECRET_KEY_DEFAULT:
    raise RuntimeError(
        "SECRET_KEY is the development default but DEBUG=false. "
        "Set SECRET_KEY in .env.prod via `openssl rand -hex 32` before "
        "starting the production server."
    )

connect_args = {"check_same_thread": False} if settings.use_sqlite else {}
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
)

if settings.use_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
