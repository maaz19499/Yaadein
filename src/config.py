from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/yaadein"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Cloudflare R2 Storage credentials
    R2_BUCKET_NAME: str = "yaadein-bucket"
    R2_ENDPOINT_URL: str = "http://localhost:9000"
    R2_ACCESS_KEY_ID: str = "minioadmin"
    R2_SECRET_ACCESS_KEY: str = "minioadmin"

    # Supabase JWT Secret
    SUPABASE_JWT_SECRET: str = (
        "dummy_supabase_jwt_secret_for_local_development_must_be_changed"
    )

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


settings = Settings()
