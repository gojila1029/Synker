from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    database_url: str = ""
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("supabase_jwt_secret", mode="after")
    @classmethod
    def require_jwt_secret(cls, v: str) -> str:
        if not v:
            raise ValueError("SUPABASE_JWT_SECRET must be set — an empty secret accepts any JWT")
        return v

    @field_validator("database_url", mode="after")
    @classmethod
    def require_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL must be set")
        return v


settings = Settings()
