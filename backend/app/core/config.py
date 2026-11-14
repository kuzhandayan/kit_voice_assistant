from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: str = "development"
    session_secret: str = Field(min_length=16)
    session_ttl_seconds: int = 8 * 3600
    allowed_origins: str = "http://localhost:5173"
    timezone: str = "Asia/Kolkata"

    college_api_base_url: str = "https://ht.knowvally.com"
    college_participant_key: str = Field(min_length=8)
    college_api_timeout_seconds: float = 8
    documents_refresh_seconds: int = 300

    database_url: str = "sqlite:///./kit.db"

    llm_chain: str = (
        "groq:openai/gpt-oss-120b@low,groq:openai/gpt-oss-20b@low,groq:qwen/qwen3.8-27b@none,"
        "gemini:gemini-3.5-flash@low,gemini:gemini-3.1-flash-lite@low"
    )
    groq_api_key: str = ""
    gemini_api_key: str = ""
    llm_timeout_seconds: float = 8

    groq_stt_model: str = "whisper-large-v3-turbo"
    deepgram_api_key: str = ""
    deepgram_stt_model: str = "nova-3"
    stt_timeout_seconds: float = 15

    edge_tts_voice: str = "en-IN-NeerjaNeural"
    deepgram_tts_model: str = "aura-2-thalia-en"
    tts_timeout_seconds: float = 12

    max_audio_mb: int = 5
    max_text_chars: int = 1000
    max_agent_steps: int = 6
    rate_limit_per_minute: int = 30

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
