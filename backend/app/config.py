from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+asyncpg://wa:wa@postgres:5432/wa_marketing"
    REDIS_URL: str = "redis://redis:6379/0"
    WHATSAPP_API_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WEBHOOK_VERIFY_TOKEN: str = "dev_verify_token"
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    MOCK_WHATSAPP: bool = True
    AI_HISTORY_LIMIT: int = 20
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


settings = Settings()
