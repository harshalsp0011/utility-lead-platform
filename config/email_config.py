from __future__ import annotations

"""Email configuration helpers.

This file reads email settings and returns the email client the app should use.
Other parts of the system can import these helpers when they need to send
outreach emails or read the daily sending limit.
"""

from typing import Any

from config.settings import get_settings


def get_email_client() -> Any:
    """Return the appropriate email client based on EMAIL_PROVIDER in .env."""
    settings = get_settings()
    provider = settings.EMAIL_PROVIDER.lower()

    if provider == "sendgrid":
        if not settings.SENDGRID_API_KEY:
            raise ValueError(
                "SENDGRID_API_KEY is not set. "
                "Add it to .env or set it as an environment variable."
            )
        from sendgrid import SendGridAPIClient

        return SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)

    if provider == "instantly":
        if not settings.INSTANTLY_API_KEY:
            raise ValueError(
                "INSTANTLY_API_KEY is not set. "
                "Add it to .env or set it as an environment variable."
            )
        raise NotImplementedError(
            "EMAIL_PROVIDER 'instantly' is configured, but the Instantly client "
            "is not implemented in this workspace."
        )

    raise ValueError(
        f"Unsupported EMAIL_PROVIDER '{settings.EMAIL_PROVIDER}'. "
        "Supported values: 'sendgrid'."
    )


def get_daily_limit() -> int:
    """Return the configured daily email send limit."""
    return get_settings().EMAIL_DAILY_LIMIT
