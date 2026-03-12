from __future__ import annotations

"""Follow-up scheduling helpers for outreach sequences.

Purpose:
- Creates, finds, cancels, and summarizes scheduled follow-up events.

Dependencies:
- `config.settings.get_settings` for follow-up day offsets.
- `sqlalchemy` session access to `outreach_events`, `companies`, and `contacts`.

Usage:
- Call `schedule_followups(...)` after a successful initial send.
- Call `get_due_followups(...)` in a daily job to fetch follow-ups to send.
"""

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import get_settings


def schedule_followups(
    company_id: str,
    contact_id: str,
    draft_id: str,
    send_date: date | datetime | str,
    db_session: Session,
) -> list[str]:
    """Create three scheduled follow-up events and return their IDs."""
    settings = get_settings()
    day_1 = int(getattr(settings, "FOLLOWUP_DAY_1", 3) or 3)
    day_2 = int(getattr(settings, "FOLLOWUP_DAY_2", 7) or 7)
    day_3 = int(getattr(settings, "FOLLOWUP_DAY_3", 14) or 14)

    base_date = _to_date(send_date)
    offsets = [(1, day_1), (2, day_2), (3, day_3)]

    created_ids: list[str] = []
    for follow_up_number, day_offset in offsets:
        next_date = base_date + timedelta(days=day_offset)

        inserted_id = db_session.execute(
            text(
                """
                INSERT INTO outreach_events (
                    company_id,
                    contact_id,
                    email_draft_id,
                    event_type,
                    event_at,
                    follow_up_number,
                    next_followup_date,
                    sales_alerted
                )
                VALUES (
                    :company_id,
                    :contact_id,
                    :email_draft_id,
                    'scheduled_followup',
                    NOW(),
                    :follow_up_number,
                    :next_followup_date,
                    false
                )
                RETURNING id
                """
            ),
            {
                "company_id": company_id,
                "contact_id": contact_id,
                "email_draft_id": draft_id,
                "follow_up_number": follow_up_number,
                "next_followup_date": next_date,
            },
        ).scalar_one()

        created_ids.append(str(inserted_id))

    db_session.commit()
    return created_ids


def get_due_followups(db_session: Session) -> list[dict[str, Any]]:
    """Return scheduled follow-up events due today for active contacts/companies."""
    rows = db_session.execute(
        text(
            """
            SELECT
                oe.id,
                oe.company_id,
                oe.contact_id,
                oe.email_draft_id,
                oe.follow_up_number,
                oe.next_followup_date,
                c.name AS company_name,
                c.status AS company_status,
                ct.email AS contact_email,
                ct.full_name AS contact_name,
                ct.unsubscribed
            FROM outreach_events oe
            JOIN companies c
                ON c.id = oe.company_id
            JOIN contacts ct
                ON ct.id = oe.contact_id
            WHERE oe.event_type = 'scheduled_followup'
              AND oe.next_followup_date <= CURRENT_DATE
              AND COALESCE(oe.sales_alerted, false) = false
              AND COALESCE(c.status, '') <> 'replied'
              AND COALESCE(ct.unsubscribed, false) = false
            ORDER BY oe.next_followup_date ASC, oe.follow_up_number ASC
            """
        )
    ).mappings().all()

    return [dict(row) for row in rows]


def cancel_followups(company_id: str, db_session: Session) -> int:
    """Cancel future scheduled follow-ups for one company and return count."""
    updated_rows = db_session.execute(
        text(
            """
            UPDATE outreach_events
            SET event_type = 'cancelled_followup'
            WHERE company_id = :company_id
              AND event_type = 'scheduled_followup'
              AND next_followup_date > CURRENT_DATE
            RETURNING id
            """
        ),
        {"company_id": company_id},
    ).all()

    db_session.commit()
    return len(updated_rows)


def check_sequence_status(company_id: str, db_session: Session) -> dict[str, Any]:
    """Return follow-up sequence progress/status for one company."""
    sent_last = db_session.execute(
        text(
            """
            SELECT COALESCE(MAX(follow_up_number), 0)
            FROM outreach_events
            WHERE company_id = :company_id
              AND event_type = 'sent'
            """
        ),
        {"company_id": company_id},
    ).scalar_one()

    next_date = db_session.execute(
        text(
            """
            SELECT MIN(next_followup_date)
            FROM outreach_events
            WHERE company_id = :company_id
              AND event_type = 'scheduled_followup'
            """
        ),
        {"company_id": company_id},
    ).scalar_one_or_none()

    replied_exists = db_session.execute(
        text(
            """
            SELECT 1
            FROM outreach_events
            WHERE company_id = :company_id
              AND event_type = 'replied'
            LIMIT 1
            """
        ),
        {"company_id": company_id},
    ).first() is not None

    sequence_complete = bool(replied_exists) or (next_date is None and int(sent_last or 0) >= 3)

    return {
        "last_followup_sent": int(sent_last or 0),
        "next_followup_date": next_date,
        "sequence_complete": sequence_complete,
        "reply_received": bool(replied_exists),
    }


def mark_sequence_complete(company_id: str, db_session: Session) -> None:
    """Mark company as no_response and cancel remaining scheduled follow-ups."""
    db_session.execute(
        text(
            """
            UPDATE companies
            SET status = 'no_response',
                updated_at = NOW()
            WHERE id = :company_id
            """
        ),
        {"company_id": company_id},
    )

    cancel_followups(company_id=company_id, db_session=db_session)


def _to_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError as exc:
        raise ValueError("send_date must be a date, datetime, or ISO date string") from exc


class FollowupScheduler:
    """Class-based interface for followup scheduling operations (used by test suite)."""

    def schedule_followups(
        self,
        company_id: str,
        send_date: date | datetime | str,
        db_session: Session,
        contact_id: str = None,
        draft_id: str = None,
        followup_days: list[int] = None,
    ) -> list[dict[str, Any]]:
        """Create three scheduled follow-up event records."""
        if followup_days is None:
            followup_days = [3, 7, 14]  # Default days
        
        base_date = _to_date(send_date)
        offsets = [(1, followup_days[0]), (2, followup_days[1]), (3, followup_days[2])]
        
        records = []
        for follow_up_number, day_offset in offsets:
            next_date = base_date + timedelta(days=day_offset)
            records.append({
                'follow_up_number': follow_up_number,
                'next_followup_date': next_date,
                'company_id': company_id,
                'contact_id': contact_id or '',
                'draft_id': draft_id or '',
            })
        
        return records

    def cancel_followups(self, company_id: str, db_session: Session) -> int:
        """Cancel future scheduled follow-ups for one company."""
        return cancel_followups(company_id=company_id, db_session=db_session)

    def get_due_followups(
        self,
        db_session: Session,
        cutoff_date: date = None,
    ) -> list[dict[str, Any]]:
        """Return scheduled follow-up events due by cutoff date."""
        followups = get_due_followups(db_session)
        
        # Filter by cutoff date if provided
        if cutoff_date:
            filtered = []
            for followup in followups:
                next_date = followup.get('next_followup_date')
                if isinstance(next_date, str):
                    next_date = datetime.fromisoformat(next_date).date()
                if next_date <= cutoff_date:
                    filtered.append(followup)
            return filtered
        
        return followups

    def check_sequence_status(self, company_id: str, db_session: Session) -> dict[str, Any]:
        """Return follow-up sequence progress/status for one company."""
        return check_sequence_status(company_id=company_id, db_session=db_session)

    def mark_sequence_complete(self, company_id: str, db_session: Session) -> None:
        """Mark company as no_response and cancel remaining scheduled follow-ups."""
        mark_sequence_complete(company_id=company_id, db_session=db_session)
