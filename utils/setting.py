from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    AZURE = "azure"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Auto-detect LLM provider based on available API keys.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===========================================
    # LLM Provider API Keys
    # ===========================================
    openai_api_key: Optional[str] = Field(default=None)
    anthropic_api_key: Optional[str] = Field(default=None)
    GOOGLE_API_KEY: Optional[str] = Field(default=None)

    # Azure OpenAI
    azure_openai_api_key: Optional[str] = Field(default=None)
    azure_openai_endpoint: Optional[str] = Field(default=None)
    azure_openai_api_version: str = Field(default="2024-02-15-preview")
    azure_openai_deployment_name: Optional[str] = Field(default=None)

    # ===========================================
    # Search Tools
    # ===========================================
    tavily_api_key: Optional[str] = Field(default=None)

    # ===========================================
    # Database (PostgreSQL)
    # ===========================================
    database_url: Optional[str] = Field(
        default=None,
        description="PostgreSQL connection string, e.g. postgresql://user:pass@localhost:5432/dbname",
    )

    # ===========================================
    # Default / Auto settings
    # ===========================================
    default_llm_provider: Optional[LLMProvider] = Field(
        default=None,
        description="Auto-detect provider if not explicitly set"
    )

    # ===========================================
    # Model names
    # ===========================================
    openai_model_name: str = Field(default="gpt-4o")
    anthropic_model_name: str = Field(default="claude-sonnet-4-20250514")
    google_model_name: str = Field(default="gemini-2.5-flash")
    azure_model_name: str = Field(default="gpt-4")

    # ===========================================
    # Generation params
    # ===========================================
    llm_max_tokens: int = Field(default=4096, ge=1)
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    # ===========================================
    # Provider resolution
    # ===========================================
    def resolve_provider(self) -> LLMProvider:
        """
        Auto-select provider based on available API keys.
        Priority order:
        Google → OpenAI → Anthropic → Azure
        """
        if self.GOOGLE_API_KEY:
            return LLMProvider.GOOGLE
        if self.openai_api_key:
            return LLMProvider.OPENAI
        if self.anthropic_api_key:
            return LLMProvider.ANTHROPIC
        if self.azure_openai_api_key:
            return LLMProvider.AZURE

        raise ValueError(
            "No LLM API key found. Please set at least one LLM API key."
        )

    # ===========================================
    # Accessors
    # ===========================================
    def get_provider(self, provider: Optional[LLMProvider] = None) -> LLMProvider:
        return provider or self.default_llm_provider or self.resolve_provider()

    def get_model_name(self, provider: Optional[LLMProvider] = None) -> str:
        provider = self.get_provider(provider)
        return {
            LLMProvider.OPENAI: self.openai_model_name,
            LLMProvider.ANTHROPIC: self.anthropic_model_name,
            LLMProvider.GOOGLE: self.google_model_name,
            LLMProvider.AZURE: self.azure_model_name,
        }[provider]

    def get_api_key(self, provider: Optional[LLMProvider] = None) -> Optional[str]:
        provider = self.get_provider(provider)
        return {
            LLMProvider.OPENAI: self.openai_api_key,
            LLMProvider.ANTHROPIC: self.anthropic_api_key,
            LLMProvider.GOOGLE: self.GOOGLE_API_KEY,
            LLMProvider.AZURE: self.azure_openai_api_key,
        }[provider]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
