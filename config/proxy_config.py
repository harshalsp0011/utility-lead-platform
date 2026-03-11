from __future__ import annotations

"""Proxy configuration helpers for scraping.

This file decides which proxy URL the Scout scraper should use based on the
current settings. Other scraping code imports `get_proxy_url()` so proxy logic
stays in one place.
"""

from typing import Optional

from config.settings import get_settings


def get_proxy_url() -> Optional[str]:
    """Return the configured proxy URL for scraping, or None when disabled."""
    settings = get_settings()
    provider = settings.PROXY_PROVIDER.lower()

    if provider == "scraperapi":
        if not settings.SCRAPERAPI_KEY:
            raise ValueError(
                "SCRAPERAPI_KEY is not set. "
                "Add it to .env or set it as an environment variable."
            )
        return (
            f"http://scraperapi:{settings.SCRAPERAPI_KEY}"
            "@proxy-server.scraperapi.com:8001"
        )

    if provider == "brightdata":
        if not settings.BRIGHTDATA_KEY:
            raise ValueError(
                "BRIGHTDATA_KEY is not set. "
                "Add it to .env or set it as an environment variable."
            )
        return f"http://{settings.BRIGHTDATA_KEY}@brd.superproxy.io:22225"

    if provider == "none":
        return None

    raise ValueError(
        f"Unsupported PROXY_PROVIDER '{settings.PROXY_PROVIDER}'. "
        "Supported values: 'scraperapi', 'brightdata', 'none'."
    )