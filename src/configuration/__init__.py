"""Environment-backed application configuration."""

from pydantic import AnyUrl, Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE_SETTINGS = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore",
    case_sensitive=False,
)


class Settings(BaseSettings):
    """Validated settings shared by the application composition roots."""

    model_config = ENV_FILE_SETTINGS

    database_url: PostgresDsn = PostgresDsn(
        "postgresql://motor_mitra:motor_mitra@localhost:5432/motor_mitra"
    )
    database_pool_min_size: int = Field(default=1, ge=1)
    database_pool_max_size: int = Field(default=10, ge=1)
    database_acquire_timeout_seconds: float = Field(default=2.0, gt=0)
    database_command_timeout_seconds: float = Field(default=2.0, gt=0)
    business_time_zone: str = "Asia/Kolkata"
    log_level: str = "INFO"


class LiveKitConnectionSettings(BaseSettings):
    """Credentials and identity used by the agent and browser token API."""

    model_config = ENV_FILE_SETTINGS

    livekit_url: AnyUrl
    livekit_api_key: SecretStr
    livekit_api_secret: SecretStr
    livekit_agent_name: str = Field(
        default="motor-mitra-service-desk",
        min_length=1,
        max_length=128,
    )
    browser_auth_token: SecretStr = Field(min_length=24)
    web_allowed_origin: str = "http://localhost:5173"


class VoicePipelineSettings(BaseSettings):
    """Pinned provider configuration for the Stage 1 voice pipeline."""

    model_config = ENV_FILE_SETTINGS

    deepgram_api_key: SecretStr
    deepgram_model: str = "nova-3"
    deepgram_language: str = "multi"
    groq_api_key: SecretStr
    groq_model: str = "openai/gpt-oss-20b"
    eleven_api_key: SecretStr
    eleven_voice_id: str = Field(min_length=1)
    eleven_model: str = "eleven_flash_v2_5"
    eleven_language: str = "hi"


class LangfuseSettings(BaseSettings):
    """Optional Langfuse trace-export configuration."""

    model_config = ENV_FILE_SETTINGS

    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_capture_pii: bool = True

    @property
    def is_configured(self) -> bool:
        """Return whether both Langfuse credentials are present."""
        return self.langfuse_public_key is not None and self.langfuse_secret_key is not None


def load_settings() -> Settings:
    """Load and validate application settings from the environment."""
    settings = Settings()
    if settings.database_pool_min_size > settings.database_pool_max_size:
        msg = "DATABASE_POOL_MIN_SIZE cannot exceed DATABASE_POOL_MAX_SIZE"
        raise ValueError(msg)
    return settings


def load_livekit_connection_settings() -> LiveKitConnectionSettings:
    """Load LiveKit and browser-auth settings only when that surface starts."""
    return LiveKitConnectionSettings()  # pyright: ignore[reportCallIssue]


def load_voice_pipeline_settings() -> VoicePipelineSettings:
    """Load provider settings only when the voice agent starts."""
    return VoicePipelineSettings()  # pyright: ignore[reportCallIssue]


def load_langfuse_settings() -> LangfuseSettings:
    """Load optional Langfuse tracing settings."""
    return LangfuseSettings()
