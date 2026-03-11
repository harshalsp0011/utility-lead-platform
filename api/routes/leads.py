from __future__ import annotations

"""Lead management API routes.

Purpose:
- CRUD-style endpoints for viewing, approving, and rejecting scored leads.
- GET /leads         — paginated lead list with optional filters
- GET /leads/high    — high-tier leads ordered by score
- GET /leads/{id}    — single lead details
- PATCH /leads/{id}/approve
- PATCH /leads/{id}/reject

Dependencies:
- `api.dependencies` for DB session and API key guard.
- `api.models.lead` for request/response schemas.
- SQLAlchemy text() queries against companies, company_features, lead_scores,
  contacts tables.

Usage:
- Include this router in api/main.py with prefix='/leads'.
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.dependencies import get_db, verify_api_key
from api.models.lead import (
    LeadApproveRequest,
    LeadFilterParams,
    LeadListResponse,
    LeadRejectRequest,
    LeadResponse,
)
from config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_currency(value: float) -> str:
    v = float(value or 0)
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}k"
    return f"${v:.0f}"


def _build_lead_row(row: dict[str, Any], contingency_fee: float) -> LeadResponse:
    savings_mid = float(row.get("savings_mid") or 0.0)
    return LeadResponse(
        company_id=row["company_id"],
        company_name=str(row.get("company_name") or ""),
        industry=str(row.get("industry") or ""),
        state=str(row.get("state") or ""),
        site_count=int(row.get("site_count") or 0),
        employee_count=int(row.get("employee_count") or 0),
        estimated_total_spend=float(row.get("estimated_total_spend") or 0.0),
        savings_low=float(row.get("savings_low") or 0.0),
        savings_mid=savings_mid,
        savings_high=float(row.get("savings_high") or 0.0),
        savings_low_formatted=_fmt_currency(float(row.get("savings_low") or 0.0)),
        savings_mid_formatted=_fmt_currency(savings_mid),
        savings_high_formatted=_fmt_currency(float(row.get("savings_high") or 0.0)),
        tb_revenue_estimate=round(savings_mid * contingency_fee, 2),
        score=float(row.get("score") or 0.0),
        tier=str(row.get("tier") or "low"),
        score_reason=str(row.get("score_reason") or ""),
        approved_human=bool(row.get("approved_human") or False),
        approved_by=row.get("approved_by"),
        approved_at=row.get("approved_at"),
        status=str(row.get("status") or "new"),
        contact_found=bool(row.get("contact_found") or False),
        date_scored=row.get("date_scored") or datetime.now(timezone.utc),
    )


def _query_leads(
    db: Session,
    filters: LeadFilterParams,
    forced_tier: str | None = None,
    order_by: str = "c.updated_at DESC",
) -> tuple[int, int, int, int, list[dict[str, Any]]]:
    """Run the leads query and return (total, high, medium, low, rows)."""
    conditions: list[str] = ["1=1"]
    params: dict[str, Any] = {}

    applied_tier = forced_tier or filters.tier
    if applied_tier:
        conditions.append("COALESCE(ls.tier, 'low') = :tier")
        params["tier"] = applied_tier

    if filters.industry:
        conditions.append("c.industry = :industry")
        params["industry"] = filters.industry

    if filters.state:
        conditions.append("c.state = :state")
        params["state"] = filters.state

    if filters.status:
        conditions.append("c.status = :status")
        params["status"] = filters.status

    if filters.min_score is not None:
        conditions.append("COALESCE(ls.score, 0) >= :min_score")
        params["min_score"] = filters.min_score

    if filters.max_score is not None:
        conditions.append("COALESCE(ls.score, 0) <= :max_score")
        params["max_score"] = filters.max_score

    if filters.date_from:
        conditions.append("ls.scored_at >= :date_from")
        params["date_from"] = filters.date_from

    if filters.date_to:
        conditions.append("ls.scored_at <= :date_to")
        params["date_to"] = filters.date_to

    where = " AND ".join(conditions)

    base_cte = f"""
        WITH base AS (
            SELECT
                c.id          AS company_id,
                c.name        AS company_name,
                c.industry,
                c.state,
                COALESCE(c.site_count, 0)      AS site_count,
                COALESCE(c.employee_count, 0)  AS employee_count,
                COALESCE(cf.estimated_total_spend, 0.0) AS estimated_total_spend,
                COALESCE(cf.savings_low,  0.0) AS savings_low,
                COALESCE(cf.savings_mid,  0.0) AS savings_mid,
                COALESCE(cf.savings_high, 0.0) AS savings_high,
                COALESCE(ls.score, 0.0)        AS score,
                COALESCE(ls.tier, 'low')       AS tier,
                COALESCE(ls.score_reason, '')  AS score_reason,
                COALESCE(ls.approved_human, false) AS approved_human,
                ls.approved_by,
                ls.approved_at,
                COALESCE(c.status, 'new')      AS status,
                EXISTS (
                    SELECT 1 FROM contacts ct
                    WHERE ct.company_id = c.id
                      AND ct.unsubscribed = false
                )                              AS contact_found,
                ls.scored_at                   AS date_scored,
                c.updated_at
            FROM companies c
            LEFT JOIN LATERAL (
                SELECT estimated_total_spend, savings_low, savings_mid, savings_high
                FROM company_features
                WHERE company_id = c.id
                ORDER BY computed_at DESC
                LIMIT 1
            ) cf ON true
            LEFT JOIN LATERAL (
                SELECT score, tier, score_reason, approved_human,
                       approved_by, approved_at, scored_at
                FROM lead_scores
                WHERE company_id = c.id
                ORDER BY scored_at DESC
                LIMIT 1
            ) ls ON true
            WHERE {where}
        )
    """

    count_sql = base_cte + """
        SELECT
            COUNT(*)                                          AS total_count,
            COUNT(*) FILTER (WHERE tier = 'high')            AS high_count,
            COUNT(*) FILTER (WHERE tier = 'medium')          AS medium_count,
            COUNT(*) FILTER (WHERE tier NOT IN ('high','medium')) AS low_count
        FROM base
    """
    cr = db.execute(text(count_sql), params).mappings().first() or {}
    total  = int(cr.get("total_count") or 0)
    high   = int(cr.get("high_count")  or 0)
    medium = int(cr.get("medium_count") or 0)
    low    = int(cr.get("low_count")   or 0)

    page      = max(1, filters.page)
    page_size = max(1, min(100, filters.page_size))
    offset    = (page - 1) * page_size

    data_params = {**params, "limit": page_size, "offset": offset}
    data_sql = base_cte + f"""
        SELECT * FROM base
        ORDER BY {order_by}
        LIMIT :limit OFFSET :offset
    """
    rows = db.execute(text(data_sql), data_params).mappings().all()
    return total, high, medium, low, [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Routes  (literal paths before parameterised ones)
# ---------------------------------------------------------------------------

@router.get("/high", response_model=LeadListResponse)
def list_high_leads(
    filters: LeadFilterParams = Depends(),
    db: Session = Depends(get_db),
) -> LeadListResponse:
    """Return high-tier leads ordered by score descending."""
    settings = get_settings()
    fee = float(getattr(settings, "TB_CONTINGENCY_FEE", 0.24) or 0.24)

    total, high, medium, low, rows = _query_leads(
        db, filters, forced_tier="high", order_by="score DESC"
    )
    leads = [_build_lead_row(r, fee) for r in rows]
    return LeadListResponse(
        leads=leads,
        total_count=total,
        high_count=high,
        medium_count=medium,
        low_count=low,
        page=filters.page,
        page_size=filters.page_size,
    )


@router.get("", response_model=LeadListResponse)
def list_leads(
    filters: LeadFilterParams = Depends(),
    db: Session = Depends(get_db),
) -> LeadListResponse:
    """Return paginated leads with optional filters."""
    settings = get_settings()
    fee = float(getattr(settings, "TB_CONTINGENCY_FEE", 0.24) or 0.24)

    total, high, medium, low, rows = _query_leads(
        db, filters, order_by="c.updated_at DESC"
    )
    leads = [_build_lead_row(r, fee) for r in rows]
    return LeadListResponse(
        leads=leads,
        total_count=total,
        high_count=high,
        medium_count=medium,
        low_count=low,
        page=filters.page,
        page_size=filters.page_size,
    )


@router.get("/{company_id}", response_model=LeadResponse)
def get_lead(company_id: UUID, db: Session = Depends(get_db)) -> LeadResponse:
    """Return full lead details for a single company."""
    settings = get_settings()
    fee = float(getattr(settings, "TB_CONTINGENCY_FEE", 0.24) or 0.24)

    row = db.execute(
        text(
            """
            SELECT
                c.id          AS company_id,
                c.name        AS company_name,
                c.industry,
                c.state,
                COALESCE(c.site_count, 0)               AS site_count,
                COALESCE(c.employee_count, 0)           AS employee_count,
                COALESCE(cf.estimated_total_spend, 0.0) AS estimated_total_spend,
                COALESCE(cf.savings_low,  0.0)          AS savings_low,
                COALESCE(cf.savings_mid,  0.0)          AS savings_mid,
                COALESCE(cf.savings_high, 0.0)          AS savings_high,
                COALESCE(ls.score, 0.0)                 AS score,
                COALESCE(ls.tier, 'low')                AS tier,
                COALESCE(ls.score_reason, '')           AS score_reason,
                COALESCE(ls.approved_human, false)      AS approved_human,
                ls.approved_by,
                ls.approved_at,
                COALESCE(c.status, 'new')               AS status,
                EXISTS (
                    SELECT 1 FROM contacts ct
                    WHERE ct.company_id = c.id
                      AND ct.unsubscribed = false
                )                                       AS contact_found,
                ls.scored_at                            AS date_scored
            FROM companies c
            LEFT JOIN LATERAL (
                SELECT estimated_total_spend, savings_low, savings_mid, savings_high
                FROM company_features
                WHERE company_id = c.id
                ORDER BY computed_at DESC
                LIMIT 1
            ) cf ON true
            LEFT JOIN LATERAL (
                SELECT score, tier, score_reason, approved_human,
                       approved_by, approved_at, scored_at
                FROM lead_scores
                WHERE company_id = c.id
                ORDER BY scored_at DESC
                LIMIT 1
            ) ls ON true
            WHERE c.id = :company_id
            """
        ),
        {"company_id": str(company_id)},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"Lead {company_id} not found.")

    return _build_lead_row(dict(row), fee)


@router.patch("/{company_id}/approve")
def approve_lead(
    company_id: UUID,
    body: LeadApproveRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Approve a lead: marks lead_scores and sets company status to 'approved'."""
    score_row = db.execute(
        text(
            """
            SELECT id FROM lead_scores
            WHERE company_id = :company_id
            ORDER BY scored_at DESC
            LIMIT 1
            """
        ),
        {"company_id": str(company_id)},
    ).mappings().first()

    if not score_row:
        raise HTTPException(
            status_code=404,
            detail=f"No lead score found for company {company_id}.",
        )

    db.execute(
        text(
            """
            UPDATE lead_scores
            SET approved_human = true,
                approved_by    = :approved_by,
                approved_at    = NOW()
            WHERE id = :score_id
            """
        ),
        {"approved_by": body.approved_by, "score_id": str(score_row["id"])},
    )
    db.execute(
        text(
            """
            UPDATE companies
            SET status = 'approved', updated_at = NOW()
            WHERE id = :company_id
            """
        ),
        {"company_id": str(company_id)},
    )
    db.commit()

    logger.info("Lead %s approved by %s", company_id, body.approved_by)
    return {"success": True, "message": f"Lead {company_id} approved by {body.approved_by}."}


@router.patch("/{company_id}/reject")
def reject_lead(
    company_id: UUID,
    body: LeadRejectRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reject a lead: clears approval flag and archives the company."""
    db.execute(
        text(
            """
            UPDATE lead_scores
            SET approved_human = false
            WHERE company_id = :company_id
            """
        ),
        {"company_id": str(company_id)},
    )
    db.execute(
        text(
            """
            UPDATE companies
            SET status = 'archived', updated_at = NOW()
            WHERE id = :company_id
            """
        ),
        {"company_id": str(company_id)},
    )
    db.commit()

    logger.info(
        "Lead %s rejected by %s. reason=%s",
        company_id,
        body.rejected_by,
        body.rejection_reason,
    )
    return {
        "success": True,
        "message": (
            f"Lead {company_id} rejected by {body.rejected_by}. "
            f"Reason: {body.rejection_reason or 'not provided'}."
        ),
    }
