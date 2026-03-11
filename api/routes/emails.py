from __future__ import annotations

"""Email draft management API routes.

Purpose:
- Endpoints for viewing, approving, editing, rejecting, and regenerating
  email drafts before outreach.
- GET  /emails               — paginated draft list
- GET  /emails/pending       — drafts awaiting approval (oldest first)
- GET  /emails/{id}          — single draft details
- PATCH /emails/{id}/approve
- PATCH /emails/{id}/edit
- PATCH /emails/{id}/reject
- POST  /emails/{id}/regenerate — regenerate draft via writer agent

Dependencies:
- `api.dependencies` for DB session and API key guard.
- `api.models.email` for request/response schemas.
- `agents.writer.writer_agent` for draft regeneration.

Usage:
- Include this router in api/main.py with prefix='/emails'.
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.dependencies import get_db, verify_api_key
from api.models.email import (
    EmailApproveRequest,
    EmailDraftResponse,
    EmailEditRequest,
    EmailListResponse,
    EmailRejectRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DRAFT_SELECT = """
    SELECT
        d.id,
        d.company_id,
        c.name          AS company_name,
        d.contact_id,
        COALESCE(ct.full_name, '') AS contact_name,
        COALESCE(ct.title, '')     AS contact_title,
        COALESCE(ct.email, '')     AS contact_email,
        COALESCE(d.subject_line, '') AS subject_line,
        COALESCE(d.body, '')         AS body,
        COALESCE(d.savings_estimate, '') AS savings_estimate,
        COALESCE(d.template_used, '')    AS template_used,
        d.created_at,
        COALESCE(d.approved_human, false) AS approved_human,
        d.approved_by,
        d.approved_at,
        COALESCE(d.edited_human, false)   AS edited_human
    FROM email_drafts d
    LEFT JOIN companies c ON c.id = d.company_id
    LEFT JOIN contacts  ct ON ct.id = d.contact_id
"""


def _row_to_draft(row: dict[str, Any]) -> EmailDraftResponse:
    return EmailDraftResponse(
        id=row["id"],
        company_id=row["company_id"],
        company_name=str(row.get("company_name") or ""),
        contact_id=row["contact_id"],
        contact_name=str(row.get("contact_name") or ""),
        contact_title=str(row.get("contact_title") or ""),
        contact_email=str(row.get("contact_email") or ""),
        subject_line=str(row.get("subject_line") or ""),
        body=str(row.get("body") or ""),
        savings_estimate=str(row.get("savings_estimate") or ""),
        template_used=str(row.get("template_used") or ""),
        created_at=row.get("created_at") or datetime.now(timezone.utc),
        approved_human=bool(row.get("approved_human") or False),
        approved_by=row.get("approved_by"),
        approved_at=row.get("approved_at"),
        edited_human=bool(row.get("edited_human") or False),
    )


def _count_drafts(db: Session) -> dict[str, int]:
    row = db.execute(
        text(
            """
            SELECT
                COUNT(*)                                              AS total_count,
                COUNT(*) FILTER (WHERE approved_human = false)       AS pending_approval,
                COUNT(*) FILTER (WHERE approved_human = true)        AS approved_count,
                (SELECT COUNT(*) FROM outreach_events
                 WHERE event_type IN ('sent', 'followup_sent'))       AS sent_count
            FROM email_drafts
            """
        )
    ).mappings().first() or {}
    return {
        "total_count":    int(row.get("total_count")    or 0),
        "pending_approval": int(row.get("pending_approval") or 0),
        "approved_count": int(row.get("approved_count") or 0),
        "sent_count":     int(row.get("sent_count")     or 0),
    }


# ---------------------------------------------------------------------------
# Routes  (literal paths before parameterised ones)
# ---------------------------------------------------------------------------

@router.get("/pending", response_model=EmailListResponse)
def list_pending_drafts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> EmailListResponse:
    """Return drafts awaiting approval, oldest first."""
    offset = (page - 1) * page_size
    rows = db.execute(
        text(
            _DRAFT_SELECT + """
            WHERE d.approved_human = false
            ORDER BY d.created_at ASC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"limit": page_size, "offset": offset},
    ).mappings().all()

    counts = _count_drafts(db)
    return EmailListResponse(
        drafts=[_row_to_draft(dict(r)) for r in rows],
        **counts,
    )


@router.get("", response_model=EmailListResponse)
def list_drafts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    approved_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> EmailListResponse:
    """Return all email drafts with optional approved_only filter."""
    offset = (page - 1) * page_size
    where = "WHERE d.approved_human = true" if approved_only else ""

    rows = db.execute(
        text(
            _DRAFT_SELECT + f"""
            {where}
            ORDER BY d.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"limit": page_size, "offset": offset},
    ).mappings().all()

    counts = _count_drafts(db)
    return EmailListResponse(
        drafts=[_row_to_draft(dict(r)) for r in rows],
        **counts,
    )


@router.get("/{draft_id}", response_model=EmailDraftResponse)
def get_draft(draft_id: UUID, db: Session = Depends(get_db)) -> EmailDraftResponse:
    """Return a single email draft by ID."""
    row = db.execute(
        text(_DRAFT_SELECT + " WHERE d.id = :draft_id"),
        {"draft_id": str(draft_id)},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")

    return _row_to_draft(dict(row))


@router.patch("/{draft_id}/approve")
def approve_draft(
    draft_id: UUID,
    body: EmailApproveRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Mark a draft as approved for outreach sending."""
    result = db.execute(
        text(
            """
            UPDATE email_drafts
            SET approved_human = true,
                approved_by    = :approved_by,
                approved_at    = NOW()
            WHERE id = :draft_id
            RETURNING id
            """
        ),
        {"approved_by": body.approved_by, "draft_id": str(draft_id)},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")

    db.commit()
    logger.info("Draft %s approved by %s", draft_id, body.approved_by)
    return {"success": True, "message": f"Draft {draft_id} approved by {body.approved_by}."}


@router.patch("/{draft_id}/edit")
def edit_draft(
    draft_id: UUID,
    body: EmailEditRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Apply human edits to subject line and/or body of a draft."""
    set_clauses: list[str] = ["edited_human = true"]
    params: dict[str, Any] = {"draft_id": str(draft_id)}

    if body.new_subject_line is not None:
        set_clauses.append("subject_line = :new_subject_line")
        params["new_subject_line"] = body.new_subject_line

    if body.new_body is not None:
        set_clauses.append("body = :new_body")
        params["new_body"] = body.new_body

    result = db.execute(
        text(
            f"""
            UPDATE email_drafts
            SET {', '.join(set_clauses)}
            WHERE id = :draft_id
            RETURNING id
            """
        ),
        params,
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")

    db.commit()
    logger.info("Draft %s edited by %s", draft_id, body.edited_by)
    return {"success": True, "message": f"Draft {draft_id} updated by {body.edited_by}."}


@router.patch("/{draft_id}/reject")
def reject_draft(
    draft_id: UUID,
    body: EmailRejectRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Delete a draft and log the rejection reason."""
    row = db.execute(
        text("SELECT id FROM email_drafts WHERE id = :draft_id"),
        {"draft_id": str(draft_id)},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")

    db.execute(
        text("DELETE FROM email_drafts WHERE id = :draft_id"),
        {"draft_id": str(draft_id)},
    )
    db.commit()

    logger.info(
        "Draft %s rejected by %s. reason=%s",
        draft_id,
        body.rejected_by,
        body.rejection_reason,
    )
    return {
        "success": True,
        "message": (
            f"Draft {draft_id} rejected by {body.rejected_by}. "
            f"Reason: {body.rejection_reason or 'not provided'}."
        ),
    }


@router.post("/{draft_id}/regenerate", response_model=EmailDraftResponse)
def regenerate_draft(
    draft_id: UUID,
    db: Session = Depends(get_db),
) -> EmailDraftResponse:
    """Delete the current draft and generate a fresh one via the writer agent."""
    from agents.writer import writer_agent  # noqa: PLC0415

    existing = db.execute(
        text("SELECT id, company_id FROM email_drafts WHERE id = :draft_id"),
        {"draft_id": str(draft_id)},
    ).mappings().first()

    if not existing:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")

    company_id = str(existing["company_id"])

    # Delete old draft so writer can create a fresh one.
    db.execute(
        text("DELETE FROM email_drafts WHERE id = :draft_id"),
        {"draft_id": str(draft_id)},
    )
    db.commit()

    started_at = datetime.now(timezone.utc)
    new_draft_id = writer_agent.process_one_company(
        company_id=company_id, db_session=db
    )

    if not new_draft_id:
        raise HTTPException(
            status_code=500,
            detail="Writer agent could not generate a new draft for this company.",
        )

    row = db.execute(
        text(
            _DRAFT_SELECT + """
            WHERE d.id = :new_draft_id
              AND d.created_at >= :started_at
            """
        ),
        {"new_draft_id": new_draft_id, "started_at": started_at},
    ).mappings().first()

    if not row:
        # Fallback: fetch by id alone (created_at timezone edge case)
        row = db.execute(
            text(_DRAFT_SELECT + " WHERE d.id = :new_draft_id"),
            {"new_draft_id": new_draft_id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=500, detail="Regenerated draft could not be retrieved.")

    return _row_to_draft(dict(row))
