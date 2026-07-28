from src.config import Settings


def test_config_development_defaults() -> None:
    s = Settings(ENVIRONMENT="development")
    assert s.is_production is False
    assert s.DATABASE_URL == "postgresql://postgres:postgres@localhost:5432/yaadein"
    assert s.REDIS_URL == "redis://localhost:6379/0"
    assert s.R2_ENDPOINT_URL == "http://localhost:9000"


def test_config_production_resolution() -> None:
    upstash_url = "rediss://default:gQAAAAAAASpSAAIgcDI4YTE3YzEyNjQ1YmI0ZDliODgyOTg4ZTJkZTc4NTlkNw@driven-polliwog-76370.upstash.io:6379"
    supabase_url = "postgresql://postgres.ref:secret@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
    prod_r2 = "https://12345.r2.cloudflarestorage.com"

    s = Settings(
        ENVIRONMENT="production",
        UPSTASH_REDIS_URL=upstash_url,
        SUPABASE_DATABASE_URL=supabase_url,
        PROD_R2_ENDPOINT_URL=prod_r2,
    )
    assert s.is_production is True
    assert s.DATABASE_URL == supabase_url
    assert s.REDIS_URL == upstash_url
    assert s.R2_ENDPOINT_URL == prod_r2


def test_config_explicit_url_overrides() -> None:
    override_db = "postgresql://override:override@localhost:5433/db"
    override_redis = "redis://override:6379/1"

    s = Settings(
        ENVIRONMENT="development",
        EXPLICIT_DATABASE_URL=override_db,
        EXPLICIT_REDIS_URL=override_redis,
    )
    assert s.DATABASE_URL == override_db
    assert s.REDIS_URL == override_redis


def test_supabase_credentials() -> None:
    s = Settings(
        SUPABASE_URL="https://qhakmjlyccdavjcbekxa.supabase.co",
        SUPABASE_KEY="sb_publishable_sRVKfxUSuVx0UK5vmmGwGA_D96IvGwL",
    )
    assert s.SUPABASE_URL == "https://qhakmjlyccdavjcbekxa.supabase.co"
    assert s.SUPABASE_KEY == "sb_publishable_sRVKfxUSuVx0UK5vmmGwGA_D96IvGwL"

