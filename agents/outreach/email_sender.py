from __future__ import annotations

"""Outreach email sender.

Purpose:
- Sends one draft email through the configured provider and logs send events.

Dependencies:
- `config.settings.get_settings` for provider keys and limits.
- `sqlalchemy` session for `email_drafts`, `contacts`, and `outreach_events` queries.
- `sendgrid` SDK for SendGrid delivery and `requests` for Instantly API calls.

Usage:
- Call `send_email(draft_id, db_session)` from outreach orchestration code.
"""

import logging
from typing import Any

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import get_settings

logger = logging.getLogger(__name__)


def send_email(draft_id: str, db_session: Session) -> dict[str, Any]:
    """Send one approved draft through configured email provider."""
    draft = db_session.execute(
        text(
            """
            SELECT
                id,
                company_id,
                contact_id,
                subject_line,
                body
            FROM email_drafts
            WHERE id = :draft_id
            LIMIT 1
            """
        ),
        {"draft_id": draft_id},
    ).mappings().first()

    if not draft:
        return {"success": False, "message_id": "Draft not found"}

    contact = db_session.execute(
        text(
            """
            SELECT
                id,
                full_name,
                email,
                unsubscribed
            FROM contacts
            WHERE id = :contact_id
            LIMIT 1
            """
        ),
        {"contact_id": draft.get("contact_id")},
    ).mappings().first()

    if not contact:
        return {"success": False, "message_id": "Contact not found"}

    if bool(contact.get("unsubscribed")):
        return {"success": False, "message_id": "Skipped: contact unsubscribed"}

    daily_limit = check_daily_limit(db_session)
    if not bool(daily_limit.get("within_limit")):
        sent_today = int(daily_limit.get("sent_today") or 0)
        return {"success": False, "message_id": f"Skipped: daily limit reached ({sent_today})"}

    subject = str(draft.get("subject_line") or "")
    body = add_unsubscribe_footer(str(draft.get("body") or ""))
    to_email = str(contact.get("email") or "")
    to_name = str(contact.get("full_name") or "")

    if not to_email:
        return {"success": False, "message_id": "Contact email missing"}

    provider = select_provider()

    if provider == "sendgrid":
        settings = get_settings()
        from_email = str(settings.SENDGRID_FROM_EMAIL or "")
        result = send_via_sendgrid(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            body=body,
            from_email=from_email,
        )
    elif provider == "instantly":
        result = send_via_instantly(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            body=body,
        )
    else:
        result = {"success": False, "message_id": f"Unsupported provider: {provider}"}

    if bool(result.get("success")):
        log_send_event(
            company_id=str(draft.get("company_id") or ""),
            contact_id=str(contact.get("id") or ""),
            draft_id=str(draft.get("id") or ""),
            message_id=str(result.get("message_id") or ""),
            db_session=db_session,
        )
        db_session.commit()

    return {"success": bool(result.get("success")), "message_id": str(result.get("message_id") or "")}


def send_via_sendgrid(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    from_email: str,
) -> dict[str, Any]:
    """Send one email through SendGrid and return send result."""
    settings = get_settings()

    if not settings.SENDGRID_API_KEY:
        return {"success": False, "message_id": "SENDGRID_API_KEY is not set"}

    if not from_email:
        return {"success": False, "message_id": "SENDGRID_FROM_EMAIL is not set"}

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import (
            ClickTracking,
            From,
            HtmlContent,
            Mail,
            OpenTracking,
            PlainTextContent,
            To,
            TrackingSettings,
        )

        client = SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)

        mail = Mail(
            from_email=From(from_email),
            to_emails=To(to_email, to_name),
            subject=subject,
            plain_text_content=PlainTextContent(body),
            html_content=HtmlContent(body.replace("\n", "<br>")),
        )

        tracking = TrackingSettings()
        tracking.open_tracking = OpenTracking(enable=True)
        tracking.click_tracking = ClickTracking(enable=True, enable_text=True)
        mail.tracking_settings = tracking

        response = client.send(mail)

        if int(response.status_code) == 202:
            message_id = ""
            if isinstance(response.headers, dict):
                message_id = str(response.headers.get("X-Message-Id") or response.headers.get("x-message-id") or "")
            return {"success": True, "message_id": message_id}

        error_text = ""
        if isinstance(response.body, (bytes, bytearray)):
            error_text = response.body.decode("utf-8", errors="ignore")
        elif response.body is not None:
            error_text = str(response.body)
        return {"success": False, "message_id": f"SendGrid error {response.status_code}: {error_text}"}
    except Exception as exc:
        logger.exception("SendGrid send failed")
        return {"success": False, "message_id": f"SendGrid exception: {exc}"}


def send_via_instantly(to_email: str, to_name: str, subject: str, body: str) -> dict[str, Any]:
    """Send one email through Instantly API and return send result."""
    settings = get_settings()
    api_key = str(settings.INSTANTLY_API_KEY or "")
    campaign_id = str(getattr(settings, "INSTANTLY_CAMPAIGN_ID", "") or "")

    if not api_key:
        return {"success": False, "message_id": "INSTANTLY_API_KEY is not set"}
    if not campaign_id:
        return {"success": False, "message_id": "INSTANTLY_CAMPAIGN_ID is not set"}

    try:
        response = requests.post(
            "https://api.instantly.ai/api/v1/lead/add",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "campaign_id": campaign_id,
                "email": to_email,
                "name": to_name,
                "subject": subject,
                "body": body,
            },
            timeout=30,
        )

        payload = response.json() if response.content else {}
        if response.ok:
            message_id = str(payload.get("message_id") or payload.get("id") or "")
            return {"success": True, "message_id": message_id}

        return {"success": False, "message_id": str(payload.get("message") or response.text)}
    except Exception as exc:
        logger.exception("Instantly send failed")
        return {"success": False, "message_id": f"Instantly exception: {exc}"}


def select_provider() -> str:
    """Return configured email provider name."""
    provider = (get_settings().EMAIL_PROVIDER or "sendgrid").strip().lower()
    if provider not in {"sendgrid", "instantly"}:
        raise ValueError("EMAIL_PROVIDER must be 'sendgrid' or 'instantly'")
    return provider


def add_unsubscribe_footer(email_body: str) -> str:
    """Append standard unsubscribe footer to outgoing email body."""
    footer = (
        "\n\n---\n"
        "To unsubscribe reply with STOP.\n"
        "Troy & Banks | Buffalo, NY | (800) 499-8599"
    )
    return f"{email_body}{footer}"


def check_daily_limit(db_session: Session) -> dict[str, Any]:
    """Return whether today's sent email count is below configured daily cap."""
    sent_today = db_session.execute(
        text(
            """
            SELECT COUNT(*) AS sent_count
            FROM outreach_events
            WHERE event_type = 'sent'
              AND event_at >= date_trunc('day', NOW())
            """
        )
    ).scalar_one()

    limit = int(getattr(get_settings(), "EMAIL_DAILY_LIMIT", 50) or 50)
    sent_count = int(sent_today or 0)

    return {
        "within_limit": sent_count < limit,
        "sent_today": sent_count,
    }


def log_send_event(
    company_id: str,
    contact_id: str,
    draft_id: str,
    message_id: str,
    db_session: Session,
) -> str:
    """Insert one outreach sent event row and return event UUID."""
    inserted_id = db_session.execute(
        text(
            """
            INSERT INTO outreach_events (
                company_id,
                contact_id,
                email_draft_id,
                event_type,
                event_at,
                reply_content,
                reply_sentiment,
                follow_up_number
            )
            VALUES (
                :company_id,
                :contact_id,
                :email_draft_id,
                'sent',
                NOW(),
                :reply_content,
                NULL,
                0
            )
            RETURNING id
            """
        ),
        {
            "company_id": company_id,
            "contact_id": contact_id,
            "email_draft_id": draft_id,
            "reply_content": f"message_id:{message_id}",
        },
    ).scalar_one()

    return str(inserted_id)
