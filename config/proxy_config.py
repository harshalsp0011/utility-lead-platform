from __future__ import annotations

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