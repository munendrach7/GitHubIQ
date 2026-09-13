"""Application configuration loaded from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "GitHubIQ"
    environment: str = "development"
    cors_origins: str = "*"

    # Azure OpenAI (from Azure AI Foundry)
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str = "gpt-4.1"

    # Cosmos DB
    cosmos_endpoint: str = ""
    cosmos_key: str = ""
    cosmos_database: str = "githubiq"
    cosmos_container: str = "analyses"

    # GitHub
    github_token: str = ""

    # Azure Speech (text-to-speech for the video explainer). Part of the same
    # Azure AI Foundry (AIServices) account, so the key defaults to the OpenAI key.
    speech_region: str = "eastus2"
    speech_key: str = ""
    speech_voice: str = "en-US-AndrewMultilingualNeural"

    @property
    def speech_api_key(self) -> str:
        return self.speech_key or self.azure_openai_api_key

    @property
    def speech_configured(self) -> bool:
        return bool(self.speech_api_key and self.speech_region)

    # Auth & rate limiting
    auth_secret: str = "dev-insecure-secret-change-me"
    admin_username: str = "munendra"
    # SHA-256 of the admin password. Override the plaintext via ADMIN_PASSWORD env
    # (it is hashed at runtime); the plaintext is never stored in source.
    admin_password_sha256: str = (
        "08c49060d53793c85708ee5bf14727f82b1bfc6dace2249cc5bb705beacf18dc"
    )
    admin_password: str = ""  # optional plaintext override via env
    token_ttl_hours: int = 24
    # A user may generate `rate_limit_max_attempts` repo analyses per rolling
    # `rate_limit_window_hours` window. Both are configurable here / via env.
    rate_limit_window_hours: float = 4.0
    rate_limit_max_attempts: int = 1

    # Analysis limits (keep the MVP fast and cheap)
    max_files_scanned: int = 400
    max_file_bytes: int = 60_000

    @property
    def admin_password_hash(self) -> str:
        import hashlib

        if self.admin_password:
            return hashlib.sha256(self.admin_password.encode()).hexdigest()
        return self.admin_password_sha256

    @property
    def llm_configured(self) -> bool:
        return bool(self.azure_openai_endpoint and self.azure_openai_api_key)

    @property
    def cosmos_configured(self) -> bool:
        return bool(self.cosmos_endpoint and self.cosmos_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
