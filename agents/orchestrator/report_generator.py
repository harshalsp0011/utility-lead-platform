from __future__ import annotations

"""Daily and weekly reporting helpers for orchestrator workflows.

Purpose:
- Generates summary reports for sourcing, scoring, outreach, replies, and
  current high-tier pipeline value.

Dependencies:
- `sqlalchemy` session queries across companies, lead_scores, company_features,
  and outreach_events.
- `agents.orchestrator.pipeline_monitor` for active pipeline value rollups.

Usage:
- Call `generate_weekly_report(start_date, end_date, db_session)` for full
  report payloads used by dashboards, exports, or scheduled reporting jobs.
"""

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.orchestrator import pipeline_monitor


def generate_weekly_report(
    start_date: date | datetime | str,
    end_date: date | datetime | str,
    db_session: Session,
) -> dict[str, Any]:
    """Generate a full report dictionary by combining all sub-metrics."""
    return {
        "date_range": {
            "start": _to_datetime_start(start_date).isoformat(),
            "end": _to_datetime_end(end_date).isoformat(),
        },
        "companies_found": count_companies_found(start_date, end_date, db_session),
        "leads_by_tier": count_leads_by_tier(start_date, end_date, db_session),
        "emails": count_emails_sent(start_date, end_date, db_session),
        "replies": count_replies_received(start_date, end_date, db_session),
        "pipeline_value": calculate_pipeline_value(db_session),
        "top_leads": get_top_leads(limit=10, db_session=db_session),
    }


def count_companies_found(
    start_date: date | datetime | str,
    end_date: date | datetime | str,
    db_session: Session,
) -> dict[str, Any]:
    """Return total discovered companies and grouped counts by industry/state."""
    start_dt, end_dt = _date_bounds(start_date, end_date)

    total = db_session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM companies
            WHERE date_found >= :start_dt
              AND date_found <= :end_dt
            """
        ),
        {"start_dt": start_dt, "end_dt": end_dt},
    ).scalar_one()

    industry_rows = db_session.execute(
        text(
            """
            SELECT COALESCE(industry, 'unknown') AS industry, COUNT(*) AS count
            FROM companies
            WHERE date_found >= :start_dt
              AND date_found <= :end_dt
            GROUP BY COALESCE(industry, 'unknown')
            ORDER BY COUNT(*) DESC
            """
        ),
        {"start_dt": start_dt, "end_dt": end_dt},
    ).mappings().all()

    state_rows = db_session.execute(
        text(
            """
            SELECT COALESCE(state, 'unknown') AS state, COUNT(*) AS count
            FROM companies
            WHERE date_found >= :start_dt
              AND date_found <= :end_dt
            GROUP BY COALESCE(state, 'unknown')
            ORDER BY COUNT(*) DESC
            """
        ),
        {"start_dt": start_dt, "end_dt": end_dt},
    ).mappings().all()

    return {
        "total": int(total or 0),
        "by_industry": {str(row["industry"]): int(row["count"] or 0) for row in industry_rows},
        "by_state": {str(row["state"]): int(row["count"] or 0) for row in state_rows},
    }


def count_leads_by_tier(
    start_date: date | datetime | str,
    end_date: date | datetime | str,
    db_session: Session,
) -> dict[str, int]:
    """Return scored lead counts by tier within the date range."""
    start_dt, end_dt = _date_bounds(start_date, end_date)

    rows = db_session.execute(
        text(
            """
            SELECT COALESCE(tier, 'low') AS tier, COUNT(*) AS count
            FROM lead_scores
            WHERE scored_at >= :start_dt
              AND scored_at <= :end_dt
            GROUP BY COALESCE(tier, 'low')
            """
        ),
        {"start_dt": start_dt, "end_dt": end_dt},
    ).mappings().all()

    result = {"high": 0, "medium": 0, "low": 0}
    for row in rows:
        tier = str(row.get("tier") or "low").strip().lower()
        if tier not in result:
            continue
        result[tier] = int(row.get("count") or 0)

    result["total"] = result["high"] + result["medium"] + result["low"]
    return result


def count_emails_sent(
    start_date: date | datetime | str,
    end_date: date | datetime | str,
    db_session: Session,
) -> dict[str, Any]:
    """Return send/open/click totals and derived open/click rates."""
    start_dt, end_dt = _date_bounds(start_date, end_date)

    rows = db_session.execute(
        text(
            """
            SELECT event_type, COUNT(*) AS count
            FROM outreach_events
            WHERE event_at >= :start_dt
              AND event_at <= :end_dt
              AND event_type IN ('sent', 'followup_sent', 'opened', 'clicked')
            GROUP BY event_type
            """
        ),
        {"start_dt": start_dt, "end_dt": end_dt},
    ).mappings().all()

    counts = {str(row["event_type"]): int(row["count"] or 0) for row in rows}

    first_emails = counts.get("sent", 0)
    followups = counts.get("followup_sent", 0)
    opened = counts.get("opened", 0)
    clicked = counts.get("clicked", 0)
    total_sent = first_emails + followups

    open_rate_pct = (opened / total_sent * 100.0) if total_sent > 0 else 0.0
    click_rate_pct = (clicked / total_sent * 100.0) if total_sent > 0 else 0.0

    return {
        "total_sent": total_sent,
        "first_emails": first_emails,
        "followups": followups,
        "open_rate_pct": round(open_rate_pct, 2),
        "click_rate_pct": round(click_rate_pct, 2),
    }


def count_replies_received(
    start_date: date | datetime | str,
    end_date: date | datetime | str,
    db_session: Session,
) -> dict[str, Any]:
    """Return reply sentiment totals, unsubscribe count, and reply rate."""
    start_dt, end_dt = _date_bounds(start_date, end_date)

    sentiment_rows = db_session.execute(
        text(
            """
            SELECT COALESCE(reply_sentiment, 'neutral') AS sentiment, COUNT(*) AS count
            FROM outreach_events
            WHERE event_type = 'replied'
              AND event_at >= :start_dt
              AND event_at <= :end_dt
            GROUP BY COALESCE(reply_sentiment, 'neutral')
            """
        ),
        {"start_dt": start_dt, "end_dt": end_dt},
    ).mappings().all()

    replies_total = db_session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM outreach_events
            WHERE event_type = 'replied'
              AND event_at >= :start_dt
              AND event_at <= :end_dt
            """
        ),
        {"start_dt": start_dt, "end_dt": end_dt},
    ).scalar_one()

    unsubscribes = db_session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM outreach_events
            WHERE event_type = 'unsubscribed'
              AND event_at >= :start_dt
              AND event_at <= :end_dt
            """
        ),
        {"start_dt": start_dt, "end_dt": end_dt},
    ).scalar_one()

    sent_total = db_session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM outreach_events
            WHERE event_type IN ('sent', 'followup_sent')
              AND event_at >= :start_dt
              AND event_at <= :end_dt
            """
        ),
        {"start_dt": start_dt, "end_dt": end_dt},
    ).scalar_one()

    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
    for row in sentiment_rows:
        sentiment = str(row.get("sentiment") or "neutral").strip().lower()
        if sentiment in sentiment_counts:
            sentiment_counts[sentiment] = int(row.get("count") or 0)

    total_replies = int(replies_total or 0)
    sent_count = int(sent_total or 0)
    reply_rate_pct = (total_replies / sent_count * 100.0) if sent_count > 0 else 0.0

    return {
        "total_replies": total_replies,
        "positive": sentiment_counts["positive"],
        "neutral": sentiment_counts["neutral"],
        "negative": sentiment_counts["negative"],
        "unsubscribes": int(unsubscribes or 0),
        "reply_rate_pct": round(reply_rate_pct, 2),
    }


def calculate_pipeline_value(db_session: Session) -> dict[str, Any]:
    """Return active pipeline value using pipeline_monitor rollups."""
    values = pipeline_monitor.get_pipeline_value(db_session)
    return {
        "active_high_leads": int(values.get("total_leads_high") or 0),
        "total_savings_potential_low": float(values.get("total_savings_low") or 0.0),
        "total_savings_potential_mid": float(values.get("total_savings_mid") or 0.0),
        "total_savings_potential_high": float(values.get("total_savings_high") or 0.0),
        "troy_banks_revenue_estimate": float(values.get("total_tb_revenue_est") or 0.0),
    }


def get_top_leads(limit: int, db_session: Session) -> list[dict[str, Any]]:
    """Return top high-tier active leads ordered by score descending."""
    safe_limit = max(1, int(limit))

    rows = db_session.execute(
        text(
            """
            SELECT
                c.name AS company_name,
                c.industry,
                ls.score,
                ls.tier,
                c.status,
                cf.savings_low,
                cf.savings_high
            FROM companies c
            JOIN lead_scores ls
                ON ls.company_id = c.id
            JOIN company_features cf
                ON cf.company_id = c.id
            WHERE ls.tier = 'high'
              AND COALESCE(c.status, '') NOT IN ('lost', 'archived', 'no_response')
            ORDER BY ls.score DESC
            LIMIT :limit
            """
        ),
        {"limit": safe_limit},
    ).mappings().all()

    top_leads: list[dict[str, Any]] = []
    for row in rows:
        savings_low = float(row.get("savings_low") or 0.0)
        savings_high = float(row.get("savings_high") or 0.0)

        top_leads.append(
            {
                "company_name": str(row.get("company_name") or ""),
                "industry": str(row.get("industry") or ""),
                "score": float(row.get("score") or 0.0),
                "tier": str(row.get("tier") or ""),
                "savings_formatted": f"{_fmt_currency(savings_low)} - {_fmt_currency(savings_high)}",
                "status": str(row.get("status") or ""),
            }
        )

    return top_leads


def _date_bounds(start_date: date | datetime | str, end_date: date | datetime | str) -> tuple[datetime, datetime]:
    start_dt = _to_datetime_start(start_date)
    end_dt = _to_datetime_end(end_date)
    return start_dt, end_dt


def _to_datetime_start(value: date | datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)

    parsed = datetime.fromisoformat(str(value))
    if parsed.time() == time.min:
        return datetime.combine(parsed.date(), time.min)
    return parsed


def _to_datetime_end(value: date | datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.max)

    parsed = datetime.fromisoformat(str(value))
    if parsed.time() == time.min:
        return datetime.combine(parsed.date(), time.max)
    return parsed


def _fmt_currency(value: float) -> str:
    amount = float(value)
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.0f}k"
    return f"${amount:.0f}"
