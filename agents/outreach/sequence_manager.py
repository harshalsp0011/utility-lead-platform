from __future__ import annotations

"""Follow-up email content manager.

Purpose:
- Builds follow-up subject/body content from existing draft + templates.

Dependencies:
- Reads `email_drafts`, `companies`, `contacts`, `company_features`, and `lead_scores`.
- Uses `agents.writer.template_engine` for template loading/rendering.
- Uses `agents.writer.llm_connector` for body polishing.

Usage:
- Call `build_followup_email(original_draft_id, follow_up_number, db_session)`
  when a follow-up event becomes due.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.writer import llm_connector, template_engine, writer_agent
from config.settings import get_settings


def build_followup_email(
    original_draft_id: str,
    follow_up_number: int,
    db_session: Session,
) -> dict[str, str]:
    """Build one follow-up subject/body pair from original draft and context."""
    draft = db_session.execute(
        text(
            """
            SELECT id, company_id, contact_id, subject_line, body
            FROM email_drafts
            WHERE id = :draft_id
            LIMIT 1
            """
        ),
        {"draft_id": original_draft_id},
    ).mappings().first()

    if not draft:
        raise ValueError(f"Original draft not found: {original_draft_id}")

    company_id = str(draft.get("company_id") or "")
    contact_id = str(draft.get("contact_id") or "")

    company = db_session.execute(
        text(
            """
            SELECT id, name, industry, state, site_count
            FROM companies
            WHERE id = :company_id
            LIMIT 1
            """
        ),
        {"company_id": company_id},
    ).mappings().first()

    contact = db_session.execute(
        text(
            """
            SELECT id, full_name, email, unsubscribed
            FROM contacts
            WHERE id = :contact_id
            LIMIT 1
            """
        ),
        {"contact_id": contact_id},
    ).mappings().first()

    features = db_session.execute(
        text(
            """
            SELECT id, estimated_site_count, savings_low, savings_mid, savings_high
            FROM company_features
            WHERE company_id = :company_id
            ORDER BY computed_at DESC
            LIMIT 1
            """
        ),
        {"company_id": company_id},
    ).mappings().first()

    score = db_session.execute(
        text(
            """
            SELECT id, score, tier
            FROM lead_scores
            WHERE company_id = :company_id
            ORDER BY scored_at DESC
            LIMIT 1
            """
        ),
        {"company_id": company_id},
    ).mappings().first()

    if not company or not contact:
        raise ValueError("Company or contact not found for follow-up email generation")

    settings = get_settings()

    # Build context using the same function used by writer agent.
    context = writer_agent.build_context(
        company=company,
        features=features or {},
        score=score or {},
        contact=contact,
        settings=settings,
    )

    raw_template = get_followup_template(follow_up_number)
    filled_template = template_engine.fill_static_fields(raw_template, context)

    original_subject = str(draft.get("subject_line") or "")
    subject = build_followup_subject(original_subject, follow_up_number)

    body = _polish_followup_body(
        context=context,
        subject=subject,
        base_draft=filled_template,
        follow_up_number=follow_up_number,
    )

    return {
        "subject": subject,
        "body": body,
    }


def get_followup_template(follow_up_number: int) -> str:
    """Load raw follow-up template string for sequence position 1/2/3."""
    return template_engine.load_followup_template(follow_up_number)


def build_followup_subject(original_subject: str, follow_up_number: int) -> str:
    """Build follow-up subject line based on sequence number."""
    normalized_subject = (original_subject or "").strip()

    if follow_up_number in {1, 2}:
        if normalized_subject.lower().startswith("re:"):
            return normalized_subject
        return f"Re: {normalized_subject}" if normalized_subject else "Re: Quick follow-up"

    if follow_up_number == 3:
        return "Following up one last time"

    raise ValueError("follow_up_number must be 1, 2, or 3")


def _polish_followup_body(
    context: dict[str, Any],
    subject: str,
    base_draft: str,
    follow_up_number: int,
) -> str:
    generator = getattr(llm_connector, "generate_email_body", None)
    if callable(generator):
        polished = generator(
            context=context,
            subject=subject,
            base_draft=base_draft,
            retry_with_issues=[f"follow_up_number={follow_up_number}"],
        )
        return str(polished or "")

    prompt = (
        "Polish this follow-up email. Keep it professional, short, and natural. "
        "Preserve placeholders that are already resolved and do not invent facts.\n"
        f"Follow-up number: {follow_up_number}\n"
        f"Subject: {subject}\n"
        f"Company: {context.get('company_name', '')}\n"
        f"Draft:\n{base_draft}"
    )

    provider = llm_connector.select_provider()
    if provider == "openai":
        return llm_connector.call_openai(prompt)
    return llm_connector.call_ollama(prompt)
