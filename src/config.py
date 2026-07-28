from typing import Literal
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: Literal["development", "production", "dev", "prod"] = "development"

    # Explicit direct URL overrides (if DATABASE_URL, REDIS_URL, or R2_ENDPOINT_URL are passed directly)
    EXPLICIT_DATABASE_URL: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "EXPLICIT_DATABASE_URL"),
    )
    EXPLICIT_REDIS_URL: str | None = Field(
        default=None,
        validation_alias=AliasChoices("REDIS_URL", "EXPLICIT_REDIS_URL"),
    )
    EXPLICIT_R2_ENDPOINT_URL: str | None = Field(
        default=None,
        validation_alias=AliasChoices("R2_ENDPOINT_URL", "EXPLICIT_R2_ENDPOINT_URL"),
    )

    # Local Docker Defaults (Development)
    LOCAL_DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/yaadein"
    LOCAL_REDIS_URL: str = "redis://localhost:6379/0"
    LOCAL_R2_ENDPOINT_URL: str = "http://localhost:9000"

    # Production / Cloud Services
    SUPABASE_DATABASE_URL: str | None = None
    UPSTASH_REDIS_URL: str | None = None
    PROD_R2_ENDPOINT_URL: str | None = None

    # Cloudflare R2 Storage credentials
    R2_BUCKET_NAME: str = "yaadein-bucket"
    R2_ACCESS_KEY_ID: str = "minioadmin"
    R2_SECRET_ACCESS_KEY: str = "minioadmin"

    # Supabase credentials
    SUPABASE_URL: str | None = None
    SUPABASE_KEY: str | None = None

    # Supabase JWT Secret
    SUPABASE_JWT_SECRET: str = (
        "dummy_supabase_jwt_secret_for_local_development_must_be_changed"
    )
    # Supabase JWKS URL (for asymmetric RS256 verification)
    SUPABASE_JWKS_URL: str | None = None

    # AWS configuration (for Rekognition moderation)
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None

    # Customizable plan limits (max_count and max_size_bytes)
    PLAN_LIMITS: dict[str, dict[str, int | None]] = {
        "basic": {
            "max_count": 500,
            "max_size_bytes": 5 * 1024 * 1024 * 1024,  # 5 GB
        },
        "premium": {
            "max_count": None,
            "max_size_bytes": None,
        },
        "professional": {
            "max_count": None,
            "max_size_bytes": None,
        },
        "default": {
            "max_count": 500,
            "max_size_bytes": 5 * 1024 * 1024 * 1024,  # 5 GB
        },
    }

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ("production", "prod")

    @property
    def DATABASE_URL(self) -> str:
        if self.is_production:
            return (
                self.SUPABASE_DATABASE_URL
                or self.EXPLICIT_DATABASE_URL
                or self.LOCAL_DATABASE_URL
            )
        return self.EXPLICIT_DATABASE_URL or self.LOCAL_DATABASE_URL

    @property
    def REDIS_URL(self) -> str:
        if self.is_production:
            url = (
                self.UPSTASH_REDIS_URL
                or self.EXPLICIT_REDIS_URL
                or self.LOCAL_REDIS_URL
            )
        else:
            url = self.EXPLICIT_REDIS_URL or self.LOCAL_REDIS_URL

        if url.startswith("rediss://") and "ssl_cert_reqs" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}ssl_cert_reqs=CERT_NONE"
        return url

    @property
    def R2_ENDPOINT_URL(self) -> str:
        if self.is_production:
            return (
                self.PROD_R2_ENDPOINT_URL
                or self.EXPLICIT_R2_ENDPOINT_URL
                or self.LOCAL_R2_ENDPOINT_URL
            )
        return self.EXPLICIT_R2_ENDPOINT_URL or self.LOCAL_R2_ENDPOINT_URL


settings = Settings()

