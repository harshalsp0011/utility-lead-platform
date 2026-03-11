from __future__ import annotations

"""Outreach agent queue handlers.

Purpose:
- Processes approved first-email queue and scheduled follow-up queue operations.

Dependencies:
- `agents.outreach.email_sender` for provider send + daily-limit checks.
- `agents.outreach.followup_scheduler` for due follow-up records and sequence status updates.
- `agents.outreach.sequence_manager` for follow-up subject/body generation.
- `sqlalchemy` session for `email_drafts`, `contacts`, `outreach_events`, and `companies`.

Usage:
- Call `process_followup_queue(db_session)` from a scheduler job.
- Call `get_approved_queue(db_session)` before first-send queue processing.
"""

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.outreach import email_sender, followup_scheduler, sequence_manager
from config.settings import get_settings


def process_followup_queue(db_session: Session) -> int:
    """Process due follow-ups and return number sent successfully."""
    due_followups = followup_scheduler.get_due_followups(db_session)
    sent_count = 0

    for followup in due_followups:
        contact_id = str(followup.get("contact_id") or "")
        company_id = str(followup.get("company_id") or "")
        original_draft_id = str(followup.get("email_draft_id") or "")
        follow_up_number = int(followup.get("follow_up_number") or 0)

        # Skip unsubscribed contacts.
        if bool(followup.get("unsubscribed")):
            continue

        # Build follow-up subject/body from templates + LLM polish.
        followup_email = sequence_manager.build_followup_email(
            original_draft_id=original_draft_id,
            follow_up_number=follow_up_number,
            db_session=db_session,
        )

        followup_draft_id = _create_followup_draft(
            original_draft_id=original_draft_id,
            company_id=company_id,
            contact_id=contact_id,
            subject=str(followup_email.get("subject") or ""),
            body=str(followup_email.get("body") or ""),
            follow_up_number=follow_up_number,
            db_session=db_session,
        )

        send_result = email_sender.send_email(followup_draft_id, db_session)
        if not bool(send_result.get("success")):
            continue

        sent_count += 1

        # Mark scheduled record as sent.
        db_session.execute(
            text(
                """
                UPDATE outreach_events
                SET event_type = 'followup_sent',
                    event_at = NOW(),
                    reply_content = :reply_content
                WHERE id = :event_id
                """
            ),
            {
                "event_id": str(followup.get("id") or ""),
                "reply_content": f"message_id:{send_result.get('message_id', '')}",
            },
        )

        if follow_up_number < 3:
            # Ensure future follow-ups exist in case they were not pre-scheduled.
            existing_future = db_session.execute(
                text(
                    """
                    SELECT 1
                    FROM outreach_events
                    WHERE company_id = :company_id
                      AND contact_id = :contact_id
                      AND event_type = 'scheduled_followup'
                      AND follow_up_number > :current_followup_number
                    LIMIT 1
                    """
                ),
                {
                    "company_id": company_id,
                    "contact_id": contact_id,
                    "current_followup_number": follow_up_number,
                },
            ).first()

            if existing_future is None:
                followup_scheduler.schedule_followups(
                    company_id=company_id,
                    contact_id=contact_id,
                    draft_id=followup_draft_id,
                    send_date=date.today(),
                    db_session=db_session,
                )
        else:
            followup_scheduler.mark_sequence_complete(company_id=company_id, db_session=db_session)

        db_session.commit()

    return sent_count


def get_approved_queue(db_session: Session) -> list[dict[str, Any]]:
    """Return approved draft rows that do not yet have a sent event."""
    rows = db_session.execute(
        text(
            """
            SELECT
                d.id,
                d.company_id,
                d.contact_id,
                d.subject_line,
                d.body,
                d.savings_estimate,
                d.template_used,
                d.created_at
            FROM email_drafts d
            LEFT JOIN outreach_events oe
                ON oe.email_draft_id = d.id
               AND oe.event_type IN ('sent', 'followup_sent')
            WHERE d.approved_human = true
              AND oe.id IS NULL
            ORDER BY d.created_at ASC
            """
        )
    ).mappings().all()

    return [dict(row) for row in rows]


def check_daily_limit(db_session: Session) -> dict[str, Any]:
    """Return daily send cap status with remaining count included."""
    base = email_sender.check_daily_limit(db_session)
    limit = int(getattr(get_settings(), "EMAIL_DAILY_LIMIT", 50) or 50)
    sent_today = int(base.get("sent_today") or 0)

    return {
        "within_limit": bool(base.get("within_limit")),
        "sent_today": sent_today,
        "remaining": max(0, limit - sent_today),
    }


def log_outreach_run(sent_count: int, skipped_count: int, followup_count: int) -> None:
    """Print a summary line block for one outreach run."""
    print(
        "Outreach run complete:\n"
        f"First emails sent: {int(sent_count)}\n"
        f"Followups sent: {int(followup_count)}\n"
        f"Skipped (limit/unsubscribed): {int(skipped_count)}"
    )


def _create_followup_draft(
    original_draft_id: str,
    company_id: str,
    contact_id: str,
    subject: str,
    body: str,
    follow_up_number: int,
    db_session: Session,
) -> str:
    row = db_session.execute(
        text(
            """
            SELECT savings_estimate
            FROM email_drafts
            WHERE id = :draft_id
            LIMIT 1
            """
        ),
        {"draft_id": original_draft_id},
    ).mappings().first()

    savings_estimate = str((row or {}).get("savings_estimate") or "")

    inserted_id = db_session.execute(
        text(
            """
            INSERT INTO email_drafts (
                company_id,
                contact_id,
                subject_line,
                body,
                savings_estimate,
                template_used,
                approved_human,
                edited_human
            )
            VALUES (
                :company_id,
                :contact_id,
                :subject_line,
                :body,
                :savings_estimate,
                :template_used,
                true,
                false
            )
            RETURNING id
            """
        ),
        {
            "company_id": company_id,
            "contact_id": contact_id,
            "subject_line": subject,
            "body": body,
            "savings_estimate": savings_estimate,
            "template_used": f"followup_day{follow_up_number}",
        },
    ).scalar_one()

    return str(inserted_id)
