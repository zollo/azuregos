"""Application settings, loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    env: str = Field(default="development", alias="AZUREGOS_ENV")
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    # Database
    postgres_user: str = Field(default="azuregos", alias="POSTGRES_USER")
    postgres_password: str = Field(default="azuregos", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="azuregos", alias="POSTGRES_DB")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")

    # Redis / Celery
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Auth
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")

    # Bootstrap admin
    bootstrap_admin_email: str = Field(
        default="admin@azuregos.local", alias="BOOTSTRAP_ADMIN_EMAIL"
    )
    bootstrap_admin_password: str = Field(default="admin", alias="BOOTSTRAP_ADMIN_PASSWORD")

    # OIDC
    oidc_enabled: bool = Field(default=False, alias="OIDC_ENABLED")
    oidc_client_id: str = Field(default="", alias="OIDC_CLIENT_ID")
    oidc_client_secret: str = Field(default="", alias="OIDC_CLIENT_SECRET")
    oidc_discovery_url: str = Field(default="", alias="OIDC_DISCOVERY_URL")
    oidc_redirect_uri: str = Field(default="", alias="OIDC_REDIRECT_URI")

    # SAML
    saml_enabled: bool = Field(default=False, alias="SAML_ENABLED")
    saml_metadata_url: str = Field(default="", alias="SAML_METADATA_URL")
    saml_sp_entity_id: str = Field(default="azuregos", alias="SAML_SP_ENTITY_ID")
    saml_acs_url: str = Field(default="", alias="SAML_ACS_URL")

    # Azure DevOps
    ado_org_url: str = Field(default="", alias="ADO_ORG_URL")
    ado_pat: str = Field(default="", alias="ADO_PAT")
    ado_default_project: str = Field(default="", alias="ADO_DEFAULT_PROJECT")
    ado_retry_interval_seconds: int = Field(default=60, alias="ADO_RETRY_INTERVAL_SECONDS")
    ado_max_retry_attempts: int = Field(default=20, alias="ADO_MAX_RETRY_ATTEMPTS")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL used by the app."""
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """Sync URL used by Alembic migrations."""
        return self.database_url.replace("+asyncpg", "+psycopg2")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
