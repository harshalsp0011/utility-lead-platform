from __future__ import annotations

"""Pipeline health and activity monitor.

Purpose:
- Provides pipeline status counts, value rollups, service health checks,
  stuck-condition detection, and recent outreach activity snapshots.

Dependencies:
- `sqlalchemy` session for queries across companies, scoring, features,
  drafts, and outreach events.
- `requests` for service health endpoint checks.
- `config.settings.get_settings` for API keys and contingency fee settings.
- `database.connection.check_connection` for PostgreSQL health probe.

Usage:
- Call these functions from dashboards, scheduled checks, or admin endpoints.
"""

from typing import Any

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import get_settings
from database.connection import check_connection

_EXPECTED_STATUSES = [
    "new",
    "enriched",
    "scored",
    "approved",
    "contacted",
    "replied",
    "meeting_booked",
    "won",
    "lost",
    "no_response",
    "archived",
]


def get_pipeline_counts(db_session: Session) -> dict[str, int]:
    """Return count of companies grouped by status with zero-filled defaults."""
    rows = db_session.execute(
        text(
            """
            SELECT COALESCE(status, 'new') AS status, COUNT(*) AS count
            FROM companies
            GROUP BY COALESCE(status, 'new')
            """
        )
    ).mappings().all()

    counts: dict[str, int] = {status: 0 for status in _EXPECTED_STATUSES}
    for row in rows:
        status = str(row.get("status") or "new").strip().lower()
        counts[status] = int(row.get("count") or 0)

    return counts


def get_pipeline_value(db_session: Session) -> dict[str, Any]:
    """Return high-tier pipeline savings totals and estimated TB revenue."""
    row = db_session.execute(
        text(
            """
            SELECT
                COUNT(DISTINCT c.id) AS total_leads_high,
                COALESCE(SUM(cf.savings_low), 0) AS total_savings_low,
                COALESCE(SUM(cf.savings_mid), 0) AS total_savings_mid,
                COALESCE(SUM(cf.savings_high), 0) AS total_savings_high
            FROM companies c
            JOIN lead_scores ls
                ON ls.company_id = c.id
            JOIN company_features cf
                ON cf.company_id = c.id
            WHERE ls.tier = 'high'
              AND COALESCE(c.status, '') NOT IN ('lost', 'archived', 'no_response')
            """
        )
    ).mappings().first()

    total_leads_high = int((row or {}).get("total_leads_high") or 0)
    total_savings_low = float((row or {}).get("total_savings_low") or 0.0)
    total_savings_mid = float((row or {}).get("total_savings_mid") or 0.0)
    total_savings_high = float((row or {}).get("total_savings_high") or 0.0)

    contingency_fee = float(getattr(get_settings(), "TB_CONTINGENCY_FEE", 0.24) or 0.24)
    total_tb_revenue_est = total_savings_mid * contingency_fee

    return {
        "total_leads_high": total_leads_high,
        "total_savings_low": total_savings_low,
        "total_savings_mid": total_savings_mid,
        "total_savings_high": total_savings_high,
        "total_tb_revenue_est": total_tb_revenue_est,
    }


def check_agent_health() -> dict[str, dict[str, str]]:
    """Return health status for core services and critical credentials."""
    settings = get_settings()

    health: dict[str, dict[str, str]] = {
        "postgres": _ok("Postgres reachable") if check_connection() else _error("Postgres connection failed"),
        "ollama": _probe_url("http://localhost:11434"),
        "api": _probe_url("http://localhost:8001/health"),
        "airflow": _probe_url("http://localhost:8080/health"),
        "sendgrid": _ok("SENDGRID_API_KEY configured") if settings.SENDGRID_API_KEY else _warning("SENDGRID_API_KEY missing"),
        "tavily": _ok("TAVILY_API_KEY configured") if settings.TAVILY_API_KEY else _warning("TAVILY_API_KEY missing"),
        "slack": _ok("SLACK_WEBHOOK_URL configured") if settings.SLACK_WEBHOOK_URL else _warning("SLACK_WEBHOOK_URL missing"),
    }

    return health


def detect_stuck_pipeline(db_session: Session) -> list[str]:
    """Return human-readable issue strings for stalled pipeline conditions."""
    issues: list[str] = []

    new_over_24h = db_session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM companies
            WHERE COALESCE(status, 'new') = 'new'
              AND created_at < (NOW() - INTERVAL '24 hours')
            """
        )
    ).scalar_one()
    new_count = int(new_over_24h or 0)
    if new_count > 0:
        issues.append(f"{new_count} companies found but not yet analyzed")

    high_waiting_approval = db_session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM lead_scores ls
            JOIN companies c
                ON c.id = ls.company_id
            WHERE COALESCE(c.status, '') = 'scored'
              AND COALESCE(ls.tier, '') = 'high'
              AND COALESCE(ls.approved_human, false) = false
              AND ls.scored_at < (NOW() - INTERVAL '48 hours')
            """
        )
    ).scalar_one()
    high_waiting_count = int(high_waiting_approval or 0)
    if high_waiting_count > 0:
        issues.append(f"{high_waiting_count} high-score leads waiting approval")

    approved_unsent = db_session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM email_drafts d
            LEFT JOIN outreach_events oe
                ON oe.email_draft_id = d.id
               AND oe.event_type IN ('sent', 'followup_sent')
            WHERE d.approved_human = true
              AND d.created_at < (NOW() - INTERVAL '6 hours')
              AND oe.id IS NULL
            """
        )
    ).scalar_one()
    approved_unsent_count = int(approved_unsent or 0)
    if approved_unsent_count > 0:
        issues.append(f"{approved_unsent_count} approved emails not yet sent")

    weekday = db_session.execute(text("SELECT EXTRACT(ISODOW FROM NOW())")).scalar_one()
    is_weekday = int(float(weekday or 0)) in {1, 2, 3, 4, 5}

    sent_today = db_session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM outreach_events
            WHERE event_type = 'sent'
              AND event_at >= date_trunc('day', NOW())
            """
        )
    ).scalar_one()

    if is_weekday and int(sent_today or 0) == 0:
        issues.append("No emails sent today — check outreach agent")

    return issues


def get_recent_activity(db_session: Session, limit: int = 10) -> list[dict[str, Any]]:
    """Return latest outreach activity events with company and contact names."""
    safe_limit = max(1, int(limit))
    rows = db_session.execute(
        text(
            """
            SELECT
                oe.event_at AS timestamp,
                c.name AS company_name,
                ct.full_name AS contact_name,
                oe.event_type
            FROM outreach_events oe
            LEFT JOIN companies c
                ON c.id = oe.company_id
            LEFT JOIN contacts ct
                ON ct.id = oe.contact_id
            ORDER BY oe.event_at DESC
            LIMIT :limit
            """
        ),
        {"limit": safe_limit},
    ).mappings().all()

    return [dict(row) for row in rows]


def _probe_url(url: str) -> dict[str, str]:
    try:
        response = requests.get(url, timeout=5)
        if response.ok:
            return _ok("reachable")
        return _error(f"HTTP {response.status_code}")
    except Exception as exc:
        return _error(str(exc))


def _ok(message: str) -> dict[str, str]:
    return {"status": "ok", "message": message}


def _warning(message: str) -> dict[str, str]:
    return {"status": "warning", "message": message}


def _error(message: str) -> dict[str, str]:
    return {"status": "error", "message": message}
