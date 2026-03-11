from __future__ import annotations

"""Reporting API routes.

Purpose:
- Endpoints for weekly performance reports, top-lead rankings, and pipeline
  funnel analysis.
- GET /reports/weekly     — weekly summary report
- GET /reports/top-leads  — ranked list of top leads
- GET /reports/funnel     — funnel drop-off at each pipeline stage

Dependencies:
- `api.dependencies` for DB session and API key guard.
- `api.models.report` for response schemas.
- `agents.orchestrator.report_generator` and `pipeline_monitor` for data.

Usage:
- Include this router in api/main.py with prefix='/reports'.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.dependencies import get_db, verify_api_key
from api.models.report import TopLeadItem, TopLeadsResponse, WeeklyReportResponse
from agents.orchestrator import pipeline_monitor, report_generator

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _fmt_currency(value: float) -> str:
    v = float(value or 0)
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}k"
    return f"${v:.0f}"


@router.get("/weekly", response_model=WeeklyReportResponse)
def weekly_report(
    start_date: date = Query(default=None),
    end_date: date = Query(default=None),
    db: Session = Depends(get_db),
) -> WeeklyReportResponse:
    """Return an aggregated weekly report for the given date range."""
    today = date.today()
    if end_date is None:
        end_date = today
    if start_date is None:
        start_date = today - timedelta(days=7)

    data = report_generator.generate_weekly_report(start_date, end_date, db)

    companies = data.get("companies_found", {})
    leads = data.get("leads_by_tier", {})
    emails = data.get("emails", {})
    replies = data.get("replies", {})
    pv = data.get("pipeline_value", {})

    # Outcome counts require a direct query as they track status transitions.
    outcome_row = db.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'meeting_booked') AS meetings_booked,
                COUNT(*) FILTER (WHERE status = 'won')            AS deals_won,
                COUNT(*) FILTER (WHERE status = 'lost')           AS deals_lost
            FROM companies
            WHERE updated_at >= :start_dt AND updated_at <= :end_dt
            """
        ),
        {
            "start_dt": datetime.combine(start_date, datetime.min.time()),
            "end_dt": datetime.combine(end_date, datetime.max.time()),
        },
    ).mappings().first() or {}

    mid = float(pv.get("total_savings_mid") or 0.0)

    return WeeklyReportResponse(
        period_start=start_date,
        period_end=end_date,
        companies_found=int(companies.get("total") or 0),
        companies_by_industry=companies.get("by_industry") or {},
        companies_by_state=companies.get("by_state") or {},
        leads_high=int(leads.get("high") or 0),
        leads_medium=int(leads.get("medium") or 0),
        leads_low=int(leads.get("low") or 0),
        emails_sent=int(emails.get("total_sent") or 0),
        first_emails_sent=int(emails.get("first_emails") or 0),
        followups_sent=int(emails.get("followups") or 0),
        open_rate_pct=float(emails.get("open_rate_pct") or 0.0),
        click_rate_pct=float(emails.get("click_rate_pct") or 0.0),
        replies_total=int(replies.get("total_replies") or 0),
        replies_positive=int(replies.get("positive") or 0),
        replies_neutral=int(replies.get("neutral") or 0),
        replies_negative=int(replies.get("negative") or 0),
        reply_rate_pct=float(replies.get("reply_rate_pct") or 0.0),
        meetings_booked=int(outcome_row.get("meetings_booked") or 0),
        deals_won=int(outcome_row.get("deals_won") or 0),
        deals_lost=int(outcome_row.get("deals_lost") or 0),
        pipeline_value_mid=mid,
        pipeline_value_formatted=_fmt_currency(mid),
        troy_banks_revenue_estimate=float(pv.get("total_tb_revenue_est") or 0.0),
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/top-leads", response_model=TopLeadsResponse)
def top_leads(
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> TopLeadsResponse:
    """Return top high-tier active leads ranked by score, with all required fields."""
    rows = db.execute(
        text(
            """
            SELECT
                c.id        AS company_id,
                c.name      AS company_name,
                c.industry,
                c.state,
                COALESCE(ls.score, 0.0) AS score,
                COALESCE(ls.tier, 'low') AS tier,
                COALESCE(cf.savings_low,  0.0) AS savings_low,
                COALESCE(cf.savings_high, 0.0) AS savings_high,
                COALESCE(c.status, 'new') AS status,
                EXISTS (
                    SELECT 1 FROM contacts ct
                    WHERE ct.company_id = c.id
                      AND ct.unsubscribed = false
                ) AS contact_found
            FROM companies c
            LEFT JOIN LATERAL (
                SELECT score, tier
                FROM lead_scores
                WHERE company_id = c.id
                ORDER BY scored_at DESC
                LIMIT 1
            ) ls ON true
            LEFT JOIN LATERAL (
                SELECT savings_low, savings_high
                FROM company_features
                WHERE company_id = c.id
                ORDER BY computed_at DESC
                LIMIT 1
            ) cf ON true
            WHERE COALESCE(ls.tier, '') = 'high'
              AND COALESCE(c.status, '') NOT IN ('lost', 'archived', 'no_response')
            ORDER BY ls.score DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()

    items = [
        TopLeadItem(
            company_id=UUID(str(r["company_id"])),
            company_name=str(r.get("company_name") or ""),
            industry=str(r.get("industry") or ""),
            state=str(r.get("state") or ""),
            score=float(r.get("score") or 0.0),
            tier=str(r.get("tier") or "low"),
            savings_formatted=(
                f"{_fmt_currency(float(r.get('savings_low') or 0))} - "
                f"{_fmt_currency(float(r.get('savings_high') or 0))}"
            ),
            status=str(r.get("status") or "new"),
            contact_found=bool(r.get("contact_found") or False),
        )
        for r in rows
    ]
    return TopLeadsResponse(leads=items, total_count=len(items))


@router.get("/funnel")
def funnel_report(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Return pipeline funnel with stage counts and drop-off rates."""
    counts = pipeline_monitor.get_pipeline_counts(db)

    stages = [
        "new", "enriched", "scored", "approved",
        "contacted", "replied", "meeting_booked", "won",
    ]

    total_top = sum(counts.get(s, 0) for s in stages)

    funnel: list[dict[str, Any]] = []
    for i, stage in enumerate(stages):
        stage_count = counts.get(stage, 0)
        pct_of_total = round(stage_count / total_top * 100, 1) if total_top else 0.0

        # Drop-off from previous stage:
        if i == 0:
            drop_off_pct = 0.0
        else:
            prev_count = counts.get(stages[i - 1], 0)
            if prev_count > 0:
                drop_off_pct = round((1 - stage_count / prev_count) * 100, 1)
            else:
                drop_off_pct = 0.0

        funnel.append({
            "stage": stage,
            "count": stage_count,
            "pct_of_total": pct_of_total,
            "drop_off_from_prev_pct": drop_off_pct,
        })

    return {
        "total_companies": total_top,
        "lost": counts.get("lost", 0),
        "no_response": counts.get("no_response", 0),
        "archived": counts.get("archived", 0),
        "funnel": funnel,
    }
