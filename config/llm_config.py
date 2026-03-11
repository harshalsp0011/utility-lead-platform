from __future__ import annotations

from typing import Union

from config.settings import get_settings


def get_llm() -> Union["Ollama", "OpenAI"]:
    """Return the appropriate LLM client based on LLM_PROVIDER in .env."""
    settings = get_settings()
    provider = settings.LLM_PROVIDER.lower()

    if provider == "ollama":
        from ollama import Client as OllamaClient

        return OllamaClient(host=settings.OLLAMA_BASE_URL, model=settings.LLM_MODEL)

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Add it to .env or set it as an environment variable."
            )
        from openai import OpenAI

        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        client.model = settings.LLM_MODEL  # type: ignore[attr-defined]
        return client

    raise ValueError(
        f"Unsupported LLM_PROVIDER '{settings.LLM_PROVIDER}'. "
        "Supported values: 'ollama', 'openai'."
    )
