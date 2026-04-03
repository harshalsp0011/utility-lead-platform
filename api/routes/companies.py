from __future__ import annotations

"""Company management API routes — CRM lead endpoints.

Purpose:
- GET  /companies/crm              — list all hubspot_crm companies with contact,
                                     context notes, and latest draft
- POST /companies/{id}/context     — save + LLM-format personal meeting context notes

Agentic concept:
  POST /companies/{id}/context triggers the Context Formatter agent — an LLM preprocessing
  step that structures raw meeting notes into clean bullet points before storage.
  This is Information Structuring / Preprocessing Agent pattern.

Dependencies:
- `api.dependencies` for DB session and API key guard.
- `api.models.email` for CRM request/response schemas.
- `agents.writer.context_formatter` for LLM formatting.
- `database.orm_models` for ORM reads/writes.

Usage:
- Include this router in api/main.py with prefix='/companies'.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependencies import get_db, verify_api_key
from api.models.email import (
    CrmCompanyListResponse,
    CrmCompanyResponse,
    CrmContactInfo,
    CrmContextSaveRequest,
    CrmContextSaveResponse,
    EmailDraftResponse,
)
from database.orm_models import Company, CompanyContextNote, Contact, EmailDraft

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _draft_to_response(draft: EmailDraft, company: Company, contact: Contact | None) -> EmailDraftResponse:
    return EmailDraftResponse(
        id=draft.id,
        company_id=draft.company_id,
        company_name=str(company.name if company else ""),
        contact_id=draft.contact_id,
        contact_name=str(contact.full_name if contact and contact.full_name else ""),
        contact_title=str(contact.title if contact and contact.title else ""),
        contact_email=str(contact.email if contact and contact.email else ""),
        subject_line=str(draft.subject_line or ""),
        body=str(draft.body or ""),
        savings_estimate=str(draft.savings_estimate or ""),
        template_used=str(draft.template_used or ""),
        created_at=draft.created_at or datetime.now(timezone.utc),
        approved_human=bool(draft.approved_human),
        approved_by=draft.approved_by,
        approved_at=draft.approved_at,
        edited_human=bool(draft.edited_human),
        critic_score=draft.critic_score,
        low_confidence=draft.low_confidence,
        rewrite_count=draft.rewrite_count,
    )


def _build_crm_company(
    company: Company,
    contact: Contact | None,
    context: CompanyContextNote | None,
    draft: EmailDraft | None,
) -> CrmCompanyResponse:
    contact_info = None
    if contact:
        contact_info = CrmContactInfo(
            id=contact.id,
            full_name=str(contact.full_name or ""),
            title=str(contact.title or ""),
            email=str(contact.email or ""),
        )

    latest_draft = None
    if draft:
        latest_draft = _draft_to_response(draft, company, contact)

    return CrmCompanyResponse(
        company_id=company.id,
        name=str(company.name or ""),
        industry=str(company.industry or ""),
        city=str(company.city or ""),
        state=str(company.state or ""),
        employee_count=company.employee_count,
        site_count=company.site_count,
        website=company.website,
        status=str(company.status or "new"),
        contact=contact_info,
        context_notes_raw=str(context.notes_raw or "") if context else None,
        context_notes_formatted=str(context.notes_formatted or "") if context else None,
        context_saved_at=context.updated_at if context else None,
        latest_draft=latest_draft,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/crm", response_model=CrmCompanyListResponse)
def list_crm_companies(db: Session = Depends(get_db)) -> CrmCompanyListResponse:
    """Return all hubspot_crm companies with their contact, context notes, and latest draft.

    Agentic concept: this endpoint feeds the CRM tab — it assembles everything the
    frontend needs to show company info, existing context, and any already-generated draft.
    """
    companies = db.execute(
        select(Company)
        .where(Company.data_origin == "hubspot_crm")
        .order_by(Company.created_at.desc())
    ).scalars().all()

    if not companies:
        return CrmCompanyListResponse(companies=[], total_count=0)

    company_ids = [c.id for c in companies]

    # Bulk load: one priority contact per company (latest created)
    contact_rows = db.execute(
        select(Contact)
        .where(
            Contact.company_id.in_(company_ids),
            Contact.unsubscribed.is_not(True),
        )
        .order_by(Contact.created_at.desc())
    ).scalars().all()
    # Keep only the first (most recent) contact per company
    contacts_by_company: dict[Any, Contact] = {}
    for c in contact_rows:
        if c.company_id not in contacts_by_company:
            contacts_by_company[c.company_id] = c

    # Bulk load: context notes (unique per company)
    context_rows = db.execute(
        select(CompanyContextNote).where(CompanyContextNote.company_id.in_(company_ids))
    ).scalars().all()
    context_by_company: dict[Any, CompanyContextNote] = {r.company_id: r for r in context_rows}

    # Bulk load: latest draft per company
    draft_rows = db.execute(
        select(EmailDraft)
        .where(EmailDraft.company_id.in_(company_ids))
        .order_by(EmailDraft.created_at.desc())
    ).scalars().all()
    drafts_by_company: dict[Any, EmailDraft] = {}
    for d in draft_rows:
        if d.company_id not in drafts_by_company:
            drafts_by_company[d.company_id] = d

    result = [
        _build_crm_company(
            company=c,
            contact=contacts_by_company.get(c.id),
            context=context_by_company.get(c.id),
            draft=drafts_by_company.get(c.id),
        )
        for c in companies
    ]

    return CrmCompanyListResponse(companies=result, total_count=len(result))


@router.post("/{company_id}/context", response_model=CrmContextSaveResponse)
def save_company_context(
    company_id: UUID,
    body: CrmContextSaveRequest,
    db: Session = Depends(get_db),
) -> CrmContextSaveResponse:
    """Save personal meeting context notes for a CRM company.

    Agentic concept: Information Structuring / Preprocessing Agent —
    Raw notes are passed through the Context Formatter LLM before storage.
    The LLM restructures free-text into clean bullet points (one signal per line).
    Both raw and formatted versions are stored. If LLM fails, raw is stored as-is.

    This endpoint can be called multiple times — it upserts (one record per company).
    """
    from agents.writer.context_formatter import format_context_notes  # noqa: PLC0415

    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found.")

    # Run LLM formatter
    raw = body.notes_raw.strip()
    formatted = format_context_notes(raw)
    formatter_used = formatted != raw and bool(formatted)

    now = datetime.now(timezone.utc)

    # Upsert — unique index on company_id means only one row per company
    existing = db.execute(
        select(CompanyContextNote).where(CompanyContextNote.company_id == company_id)
    ).scalar_one_or_none()

    if existing:
        existing.notes_raw = raw
        existing.notes_formatted = formatted
        existing.updated_at = now
        existing.created_by = body.created_by
        context = existing
    else:
        context = CompanyContextNote(
            id=uuid.uuid4(),
            company_id=company_id,
            notes_raw=raw,
            notes_formatted=formatted,
            source="manual_input",
            created_by=body.created_by,
            created_at=now,
            updated_at=now,
        )
        db.add(context)

    db.commit()

    logger.info(
        "[companies] Context saved for company_id=%s formatter_used=%s bullets=%d",
        company_id,
        formatter_used,
        sum(1 for l in formatted.splitlines() if l.strip().startswith("-")),
    )

    return CrmContextSaveResponse(
        company_id=company_id,
        notes_raw=raw,
        notes_formatted=formatted,
        updated_at=now,
        formatter_used=formatter_used,
    )
