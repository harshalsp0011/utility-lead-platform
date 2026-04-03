from __future__ import annotations

"""LLM configuration helpers.

This file reads the LLM settings and returns the model client the app should
use. Other agents import `get_llm()` when they need to generate text, analyze
data, or call either Ollama or OpenAI through one shared place.
"""

from typing import Any

from config.settings import get_settings


def get_llm() -> Any:
    """Return the appropriate LLM client based on LLM_PROVIDER in .env."""
    settings = get_settings()
    provider = settings.LLM_PROVIDER.lower()

    if provider == "ollama":
            from importlib import import_module
            chat_ollama = import_module("langchain_ollama").ChatOllama

            # num_predict caps token output — critic returns small JSON (~200 tokens)
            return chat_ollama(model=settings.LLM_MODEL, base_url=settings.OLLAMA_BASE_URL, num_predict=300)

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
