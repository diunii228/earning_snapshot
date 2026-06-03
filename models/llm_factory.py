from typing import Optional

from langchain_core.language_models import BaseChatModel

from utils.setting import LLMProvider, get_settings


class LLMFactory:
    """Factory class for creating LLM instances."""

    @staticmethod
    def create(
        provider: Optional[LLMProvider] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> BaseChatModel:
        settings = get_settings()

        provider = provider or settings.get_provider()

        model_name = model_name or settings.get_model_name(provider)
        temperature = temperature if temperature is not None else settings.llm_temperature
        max_tokens = max_tokens or settings.llm_max_tokens

        api_key = settings.get_api_key(provider)

        if provider in {LLMProvider.OPENAI, LLMProvider.GOOGLE} and not api_key:
            raise ValueError(
                f"API key not found for provider '{provider.value}'."
            )

        # =============================
        # Provider dispatch
        # =============================
        if provider == LLMProvider.OPENAI:
            return LLMFactory._create_openai(
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key,
                **kwargs,
            )

        if provider == LLMProvider.ANTHROPIC:
            return LLMFactory._create_anthropic(
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key,
                **kwargs,
            )

        if provider == LLMProvider.GOOGLE:
            return LLMFactory._create_google(
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key,
                **kwargs,
            )

        if provider == LLMProvider.AZURE:
            return LLMFactory._create_azure(
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )

        raise ValueError(f"Unsupported LLM provider: {provider}")

    # =============================
    # Provider creators
    # =============================
    @staticmethod
    def _create_openai(
        model_name: str,
        temperature: float,
        max_tokens: int,
        api_key: str,
        **kwargs,
    ) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
            **kwargs,
        )

    @staticmethod
    def _create_anthropic(
        model_name: str,
        temperature: float,
        max_tokens: int,
        api_key: str,
        **kwargs,
    ) -> BaseChatModel:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
            **kwargs,
        )

    @staticmethod
    def _create_google(
        model_name: str,
        temperature: float,
        max_tokens: int,
        api_key: Optional[str],
        **kwargs,
    ) -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            max_output_tokens=max_tokens,
            google_api_key=api_key,  
            **kwargs,
        )

    @staticmethod
    def _create_azure(
        model_name: str,
        temperature: float,
        max_tokens: int,
        **kwargs,
    ) -> BaseChatModel:
        from langchain_openai import AzureChatOpenAI

        settings = get_settings()

        if not settings.azure_openai_api_key:
            raise ValueError("Azure OpenAI API key not found")
        if not settings.azure_openai_endpoint:
            raise ValueError("Azure OpenAI endpoint not found")

        return AzureChatOpenAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
            azure_deployment=settings.azure_openai_deployment_name or model_name,
            **kwargs,
        )


def get_llm(
    provider: Optional[LLMProvider] = None,
    **kwargs,
) -> BaseChatModel:
    return LLMFactory.create(provider=provider, **kwargs)
