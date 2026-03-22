from __future__ import annotations

"""Conversational agent for the Utility Lead Intelligence Platform.

How the agent works:
- User sends a natural-language message.
- A system prompt gives the agent its personality and rules.
- LangChain builds a ReAct loop: LLM reads message + tool descriptions,
  picks the right tool, calls it, reads the result, writes a reply.
- Tools are Python functions with docstrings — the LLM reads those docstrings
  to decide which tool to call and what args to pass.
- Every run is tracked in agent_runs + agent_run_logs tables.

Agent framework: LangChain AgentExecutor + create_tool_calling_agent
LLM: ChatOllama (llama3.2 local) or ChatOpenAI (gpt-4o-mini) via LLM_PROVIDER env var

Usage:
    from agents.chat_agent import run_chat
    result = run_chat("find 10 healthcare companies in Buffalo NY", db)
    # result = {"reply": "...", "data": {...}, "run_id": "..."}
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import get_settings
from database.orm_models import (
    AgentRun,
    AgentRunLog,
    Company,
    LeadScore,
    OutreachEvent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LangSmith tracing — activate at module load so every agent call is traced
# ---------------------------------------------------------------------------

def _setup_tracing() -> None:
    """Enable LangSmith tracing if LANGCHAIN_API_KEY is set in the environment.

    LangChain reads LANGCHAIN_TRACING_V2 and LANGCHAIN_API_KEY automatically,
    but we set them explicitly here so Docker env vars are always applied before
    any LangChain import initialises its internal tracer.
    """
    settings = get_settings()
    if settings.LANGCHAIN_API_KEY:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
        logger.info("LangSmith tracing enabled — project: %s", settings.LANGCHAIN_PROJECT)
    else:
        logger.info("LangSmith tracing disabled (LANGCHAIN_API_KEY not set)")

_setup_tracing()


# ---------------------------------------------------------------------------
# System prompt — personality and rules given to the LLM
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a Lead Intelligence Agent for a utility cost consulting firm.

Your job is to help the sales team find companies, view scored leads, track outreach, and run pipeline operations.

== CRITICAL TOOL USAGE RULES ==

DO NOT call any tool for these types of messages — reply conversationally only:
- Greetings: "hi", "hello", "hey", "good morning", "how are you"
- Capability questions: "what can you do", "how can you help", "what are your features"
- General questions: "tell me about yourself", "what is this", "how does this work"
- Confirmations: "ok", "got it", "thanks", "sounds good"

ONLY call a tool when the user gives an explicit data command:
- "find companies" → call search_companies
- "show leads", "show me leads", "get leads", "list leads" → call get_leads
- "who did we email", "outreach history" → call get_outreach_history
- "any replies", "who replied" → call get_replies
- "run the full pipeline", "run everything" → call run_full_pipeline
- "approve lead", "approve company", "approve these" → call approve_leads

When in doubt — do NOT call a tool. Ask the user to clarify what they need.

== get_leads ARGUMENT RULES — READ CAREFULLY ==

The get_leads tool has two optional filters: tier and industry.

TIER RULES — only set tier if the user explicitly uses these words:
- "high tier", "high-tier", "high level", "top leads", "best leads", "high scoring" → tier="high"
- "medium tier", "medium-tier", "medium level", "mid tier" → tier="medium"
- "low tier", "low-tier", "low level", "low leads", "low scoring" → tier="low"
- "show me leads", "all leads", "healthcare leads", "show me X leads" → tier="" (EMPTY — do NOT guess high)

INDUSTRY RULES:
- "show me healthcare leads" → industry="healthcare", tier=""
- "show me high-tier healthcare leads" → industry="healthcare", tier="high"
- "show me all leads" → industry="", tier=""

EXAMPLES (follow exactly):
- "show me leads" → get_leads(tier="", industry="")
- "show me healthcare leads" → get_leads(tier="", industry="healthcare")
- "show high tier leads" → get_leads(tier="high", industry="")
- "show high tier healthcare leads" → get_leads(tier="high", industry="healthcare")
- "can we find low level" → get_leads(tier="low", industry="")
- "what about medium" → get_leads(tier="medium", industry="")

== RESPONSE RULES ==

- For greetings: introduce yourself as a lead intelligence agent and list what you can do.
- For capability questions: explain you can find companies (with multi-query search), show scored leads with score reasons, check outreach history, and run the full pipeline.
- Keep all replies short and direct.
- Never make up company names, scores, or contact data.
"""


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def _build_llm() -> Any:
    """Return a LangChain chat model based on LLM_PROVIDER setting."""
    settings = get_settings()
    if settings.LLM_PROVIDER == "openai":
        from pydantic import SecretStr
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=SecretStr(settings.OPENAI_API_KEY),
            temperature=0,
        )
    from langchain_ollama import ChatOllama
    return ChatOllama(
        model=settings.LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0,
    )


# ---------------------------------------------------------------------------
# Run record helpers
# ---------------------------------------------------------------------------

def _create_run(db: Session, trigger_input: dict[str, Any], run_id: uuid.UUID | None = None) -> AgentRun:
    """Insert a new agent_runs row and return it."""
    now = datetime.now(timezone.utc)
    run = AgentRun(
        id=run_id or uuid.uuid4(),
        trigger_source="chat",
        trigger_input=trigger_input,
        status="started",
        current_stage="chat",
        started_at=now,
        created_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _log_action(
    db: Session,
    run_id: uuid.UUID,
    agent: str,
    action: str,
    status: str,
    output_summary: str = "",
    duration_ms: int | None = None,
    error_message: str | None = None,
) -> None:
    """Append one row to agent_run_logs."""
    entry = AgentRunLog(
        id=uuid.uuid4(),
        run_id=run_id,
        agent=agent,
        action=action,
        status=status,
        output_summary=output_summary,
        duration_ms=duration_ms,
        error_message=error_message,
        logged_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()


def _finish_run(db: Session, run: AgentRun, status: str = "completed") -> None:
    """Mark the run as finished."""
    run.status = status
    run.completed_at = datetime.now(timezone.utc)
    db.commit()


# ---------------------------------------------------------------------------
# Tools — the LLM reads each docstring to decide which one to call
# ---------------------------------------------------------------------------

def _make_tools(db: Session, results: dict[str, Any], run: AgentRun) -> list[Any]:
    """Create LangChain tools bound to the current DB session and run."""

    @tool
    def search_companies(industry: str, location: str, count: int = 10) -> str:
        """Find companies in a specific industry and location and store them in the database.
        Use this when the user asks to find, search, fetch, or discover companies.
        Args:
            industry: e.g. 'healthcare', 'hospitality', 'manufacturing', 'retail'
            location: e.g. 'Buffalo NY', 'New York', 'Chicago IL'
            count: how many companies to find (default 10)
        """
        import time
        from agents.scout import scout_agent

        start = time.time()
        run.current_stage = "scout"
        run.status = "scout_running"
        db.commit()

        _log_action(db, run.id, "scout", "progress", "info",
                    output_summary=f"Scout starting — finding {count} {industry} companies in {location}")

        try:
            company_ids = scout_agent.run(industry, location, count, db, run_id=str(run.id))
            duration = int((time.time() - start) * 1000)

            run.companies_found = len(company_ids)
            run.status = "scout_complete"
            db.commit()

            companies = db.execute(
                select(Company).where(Company.id.in_([uuid.UUID(cid) for cid in company_ids]))
            ).scalars().all()

            results["companies"] = [
                {
                    "company_id": str(c.id),
                    "name": c.name,
                    "industry": c.industry or "",
                    "city": c.city or "",
                    "state": c.state or "",
                    "website": c.website or "",
                    "source": c.source or "",
                    "status": c.status or "new",
                }
                for c in companies
            ]

            _log_action(
                db, run.id, "scout", "companies_found", "success",
                output_summary=f"Found {len(company_ids)} companies in {industry} / {location}",
                duration_ms=duration,
            )
            return json.dumps({"found": len(company_ids), "industry": industry, "location": location})

        except Exception as exc:
            _log_action(db, run.id, "scout", "companies_found", "failure", error_message=str(exc))
            run.status = "failed"
            run.error_message = str(exc)
            db.commit()
            return json.dumps({"error": str(exc)})

    @tool
    def get_leads(tier: str = "", industry: str = "") -> str:
        """Get scored leads from the database.
        Use when the user asks for leads, scored companies, high-tier leads, or pipeline results.
        Args:
            tier: ONLY set if user explicitly says 'high', 'medium', or 'low' tier.
                  Leave BLANK ("") for general requests like "show me leads" or "show me healthcare leads".
            industry: filter by industry name (e.g. 'healthcare', 'manufacturing') — leave blank for all
        """
        from sqlalchemy import func as _func
        query = select(Company, LeadScore).join(
            LeadScore, LeadScore.company_id == Company.id, isouter=True
        )
        if industry:
            query = query.where(_func.lower(Company.industry) == industry.strip().lower())
        if tier:
            query = query.where(LeadScore.tier == tier.strip().lower())

        rows = db.execute(query).all()

        leads = [
            {
                "company_id": str(company.id),
                "name": company.name,
                "industry": company.industry or "",
                "city": company.city or "",
                "state": company.state or "",
                "score": float(score.score or 0) if score else 0,
                "tier": score.tier or "unscored" if score else "unscored",
                "score_reason": (score.score_reason or "") if score else "",
                "approved": bool(score.approved_human) if score else False,
                "status": company.status or "new",
            }
            for company, score in rows
        ]
        leads.sort(key=lambda x: x["score"], reverse=True)
        results["leads"] = leads[:50]

        _log_action(db, run.id, "chat", "get_leads", "success",
                    output_summary=f"Returned {len(leads)} leads (tier={tier or 'all'}, industry={industry or 'all'})")
        return json.dumps({"count": len(leads), "tier_filter": tier, "industry_filter": industry})

    @tool
    def get_outreach_history() -> str:
        """Get companies that have already been sent emails.
        Use when the user asks about companies already contacted, emailed, or in outreach.
        """
        rows = db.execute(
            select(Company, OutreachEvent)
            .join(OutreachEvent, OutreachEvent.company_id == Company.id)
            .where(OutreachEvent.event_type == "sent")
            .order_by(OutreachEvent.event_at.desc())
        ).all()

        history = [
            {
                "company_id": str(company.id),
                "name": company.name,
                "industry": company.industry or "",
                "city": company.city or "",
                "emailed_at": event.event_at.isoformat() if event.event_at else "",
                "follow_up_number": event.follow_up_number or 0,
                "status": company.status or "",
            }
            for company, event in rows
        ]
        results["outreach_history"] = history

        _log_action(db, run.id, "chat", "get_outreach_history", "success",
                    output_summary=f"Returned {len(history)} outreach records")
        return json.dumps({"count": len(history)})

    @tool
    def get_replies() -> str:
        """Get email replies received from prospects.
        Use when the user asks about replies, responses, interested prospects, or hot leads.
        """
        rows = db.execute(
            select(Company, OutreachEvent)
            .join(OutreachEvent, OutreachEvent.company_id == Company.id)
            .where(OutreachEvent.event_type == "replied")
            .order_by(OutreachEvent.event_at.desc())
        ).all()

        replies = [
            {
                "company_id": str(company.id),
                "name": company.name,
                "industry": company.industry or "",
                "reply_sentiment": event.reply_sentiment or "unknown",
                "reply_snippet": (event.reply_content or "")[:200],
                "replied_at": event.event_at.isoformat() if event.event_at else "",
            }
            for company, event in rows
        ]
        results["replies"] = replies

        _log_action(db, run.id, "chat", "get_replies", "success",
                    output_summary=f"Returned {len(replies)} replies")
        return json.dumps({"count": len(replies)})

    @tool
    def run_full_pipeline(industry: str, location: str, count: int = 10) -> str:
        """Run the complete pipeline: Scout → Analyst → Writer for a given industry and location.
        Only use this when the user explicitly asks to run the full pipeline, start everything,
        or do a complete end-to-end run.
        Args:
            industry: target industry e.g. 'healthcare'
            location: target location e.g. 'Buffalo NY'
            count: number of companies to target (default 10)
        """
        import time
        from agents.orchestrator import orchestrator

        start = time.time()
        run.current_stage = "orchestrator"
        run.status = "scout_running"
        db.commit()

        try:
            summary = orchestrator.run_full_pipeline(industry, location, count, db)
            duration = int((time.time() - start) * 1000)

            run.companies_found = summary.get("companies_found", 0)
            run.companies_scored = summary.get("scored_high", 0) + summary.get("scored_medium", 0)
            run.drafts_created = summary.get("drafts_created", 0)
            run.status = "writer_awaiting_approval"
            run.current_stage = "writer"
            db.commit()

            results["pipeline_summary"] = summary
            _log_action(
                db, run.id, "orchestrator", "full_pipeline_complete", "success",
                output_summary=str(summary),
                duration_ms=duration,
            )
            return json.dumps(summary)

        except Exception as exc:
            _log_action(db, run.id, "orchestrator", "full_pipeline_complete",
                        "failure", error_message=str(exc))
            run.status = "failed"
            run.error_message = str(exc)
            db.commit()
            return json.dumps({"error": str(exc)})

    @tool
    def approve_leads(company_ids: list[str], approved_by: str = "sales_team") -> str:
        """Approve specific leads by their company IDs so Writer can draft emails for them.
        Use when the user says 'approve lead', 'approve company', 'approve these leads',
        or provides a list of company IDs/names to approve.
        Args:
            company_ids: list of company UUID strings to approve
            approved_by: name of the approver (default 'sales_team')
        """
        from datetime import datetime, timezone as tz
        now = datetime.now(tz.utc)
        approved_count = 0

        for cid_str in company_ids:
            try:
                cid = uuid.UUID(cid_str)
                score_row = db.execute(
                    select(LeadScore)
                    .where(LeadScore.company_id == cid)
                    .order_by(LeadScore.scored_at.desc())
                    .limit(1)
                ).scalar_one_or_none()

                if score_row:
                    score_row.approved_human = True
                    score_row.approved_by = approved_by
                    score_row.approved_at = now

                company = db.execute(
                    select(Company).where(Company.id == cid)
                ).scalar_one_or_none()
                if company:
                    company.status = "approved"
                    company.updated_at = now

                approved_count += 1
            except Exception as exc:
                logger.warning("Failed to approve company %s: %s", cid_str, exc)

        db.commit()
        _log_action(db, run.id, "chat", "approve_leads", "success",
                    output_summary=f"Approved {approved_count} leads via chat")

        return json.dumps({"approved": approved_count, "approved_by": approved_by})

    return [search_companies, get_leads, get_outreach_history, get_replies, run_full_pipeline, approve_leads]


# ---------------------------------------------------------------------------
# LLM Intent Extractor — replaces all keyword/regex routing
#
# One LLM call per message understands what the user wants using conversation
# history as context. No keyword lists, no regex, no manual updates needed.
# Falls back to "unknown" (agent loop) on any LLM failure.
# ---------------------------------------------------------------------------

_INTENT_PROMPT = """You are an intent classifier for a B2B lead management system.
{history_section}
Latest user message: "{message}"

Classify the user's intent. Return ONLY a JSON object — no explanation, no markdown:
{{
  "action": "<action>",
  "confidence": <0.0-1.0>,
  "tier": "<tier>",
  "industry": "<industry>",
  "location": "<location>",
  "count": <count>
}}

=== ACTION DEFINITIONS (understand WHAT each action does, not what words trigger it) ===

"get_leads"
  PURPOSE: Read and display companies that are ALREADY stored in our database with their scores.
  The data already exists. No external API calls. Instant.
  SIGNAL: User wants to see, list, count, view, review, check, filter existing pipeline data.

"search_companies"
  PURPOSE: Run an EXTERNAL discovery search (Google Maps + Tavily) to find NEW companies
  that are NOT yet in our database. Slow, costs API calls. Adds new rows.
  SIGNAL: User wants to find, discover, look for, get new, or add new companies from outside.

"get_outreach_history"
  PURPOSE: Show which companies we have already contacted/emailed (from outreach_events table).

"get_replies"
  PURPOSE: Show email replies received from prospects (interested leads).

"run_full_pipeline"
  PURPOSE: Trigger end-to-end Scout→Analyst→Writer for a specific industry and location.
  Only when user explicitly wants to run the whole automated workflow.

"approve_leads"
  PURPOSE: Mark specific leads as approved so Writer can draft emails for them.

"conversational"
  PURPOSE: Greeting, thanks, capability question, chit-chat — NO data operation needed.

"unknown"
  PURPOSE: Ambiguous, multi-step, or unrecognised request — needs free-form reasoning.

=== CONFIDENCE SCORING ===
Rate your certainty 0.0–1.0:
- 1.0 = completely certain (e.g. "find 10 healthcare companies in Buffalo")
- 0.8 = high confidence (most clear requests)
- 0.6 = some ambiguity (short/vague message, unclear intent)
- 0.4 = genuinely ambiguous (could be two different actions)
- <0.5 = you are guessing — use "unknown" instead

=== CONTEXT RULES ===
- Use conversation history to resolve follow-ups ("and low?", "what about medium?" after seeing leads → get_leads)
- Short follow-up messages inherit context from prior turns

Tier: "high", "medium", "low", or "" if not mentioned
Industry: canonical name e.g. "healthcare", "manufacturing" or "" if not mentioned
Location: e.g. "Buffalo NY" or "" if not mentioned
Count: number if mentioned, default 10"""


_CONFIDENCE_THRESHOLD = 0.65  # below this → ask user to clarify instead of guessing


def _extract_intent(message: str, history: list[dict], llm: Any) -> dict[str, Any]:
    """Use LLM to classify user intent using message + conversation history.

    Returns structured dict: {action, confidence, tier, industry, location, count}
    - confidence < _CONFIDENCE_THRESHOLD signals the caller to ask for clarification.
    - Falls back to {"action": "unknown", "confidence": 0.0} on any parsing error.

    Agentic concept: Confidence-Gated Routing — the LLM rates its own certainty.
    Low confidence triggers a disambiguation dialog instead of a wrong action.
    """
    history_lines = []
    for m in (history or [])[-6:]:  # last 6 messages = 3 turns of context
        role = "User" if m.get("role") == "user" else "Agent"
        content = str(m.get("content", ""))[:250].replace("\n", " ")
        history_lines.append(f"{role}: {content}")

    history_section = (
        "Recent conversation (use this for context):\n" + "\n".join(history_lines)
        if history_lines else ""
    )

    prompt = _INTENT_PROMPT.format(
        history_section=history_section,
        message=message,
    )

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        text = str(response.content).strip()
        if text.startswith("```"):
            text = "\n".join(l for l in text.splitlines() if not l.startswith("```")).strip()
        result = json.loads(text)

        valid_actions = {
            "get_leads", "search_companies", "get_outreach_history", "get_replies",
            "run_full_pipeline", "approve_leads", "conversational", "unknown",
        }
        if result.get("action") not in valid_actions:
            result["action"] = "unknown"

        # Normalise confidence to float 0–1
        try:
            result["confidence"] = float(result.get("confidence", 0.8))
        except (TypeError, ValueError):
            result["confidence"] = 0.8

        logger.info(
            "[chat] intent: action=%s confidence=%.2f tier=%s industry=%s location=%s count=%s",
            result.get("action"), result.get("confidence"),
            result.get("tier"), result.get("industry"),
            result.get("location"), result.get("count"),
        )
        return result

    except Exception as exc:
        logger.warning("[chat] intent extraction failed: %s — falling back to agent loop", exc)
        return {"action": "unknown", "confidence": 0.0, "tier": "", "industry": "", "location": "", "count": 10}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_chat(
    message: str,
    db: Session,
    run_id: str | None = None,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Process a natural-language message and return a reply with structured data.

    Args:
        message: User's natural-language input
        db: SQLAlchemy session
        run_id: Optional pre-generated UUID string for background polling
        history: Recent conversation messages [{role, content}] for context carry-forward

    Returns:
        {"reply": str, "data": dict, "run_id": str}
    """
    from langchain_core.messages import SystemMessage

    results: dict[str, Any] = {
        "companies": [],
        "leads": [],
        "outreach_history": [],
        "replies": [],
        "pipeline_summary": None,
    }

    history = history or []
    parsed_run_id = uuid.UUID(run_id) if run_id else None
    run = _create_run(db, {"message": message}, run_id=parsed_run_id)

    try:
        llm = _build_llm()
        tools = _make_tools(db, results, run)

        # Single LLM call: understand what the user wants using message + history
        intent = _extract_intent(message, history, llm)
        action = intent.get("action", "unknown")

        _log_action(db, run.id, "chat", "intent", "info",
                    output_summary=f"action={action} tier={intent.get('tier','')} "
                                   f"industry={intent.get('industry','')} "
                                   f"msg={message[:80]}")

        # ------------------------------------------------------------------
        # Confidence-Gated Routing
        # If the LLM isn't sure what the user wants, ask instead of guessing.
        # This prevents wrong tool calls AND hallucination from wrong routing.
        # Only non-conversational, non-unknown actions need a confidence gate —
        # those two are always safe to proceed with.
        # ------------------------------------------------------------------
        confidence = intent.get("confidence", 0.8)
        gated_actions = {"get_leads", "search_companies", "run_full_pipeline",
                         "get_outreach_history", "get_replies", "approve_leads"}
        if action in gated_actions and confidence < _CONFIDENCE_THRESHOLD:
            action_labels = {
                "get_leads": "show you scored leads from our database",
                "search_companies": "search for new companies externally",
                "get_outreach_history": "show outreach history",
                "get_replies": "show email replies",
                "run_full_pipeline": "run the full Scout→Analyst→Writer pipeline",
                "approve_leads": "approve leads for outreach",
            }
            label = action_labels.get(action, action)
            disambig_prompt = (
                f"User said: \"{message}\"\n"
                f"I think they want to: {label}, but I'm not fully certain (confidence={confidence:.0%}).\n\n"
                "Ask one short clarifying question to confirm what they need. "
                "Offer 2 clear options if helpful. Do not perform any action yet."
            )
            response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=disambig_prompt)])
            reply = response.content
            _log_action(db, run.id, "chat", "disambiguation", "info",
                        output_summary=f"Low confidence ({confidence:.0%}) on action={action} — asked user to clarify")
            _finish_run(db, run, "completed")
            return {"reply": reply, "data": results, "run_id": str(run.id)}

        if action == "conversational":
            response = llm.invoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=message),
            ])
            reply = response.content

        elif action == "get_leads":
            tier = intent.get("tier", "")
            industry = intent.get("industry", "")
            tool_result = tools[1].invoke({"tier": tier, "industry": industry})
            parsed = json.loads(tool_result)
            count = parsed.get("count", 0)
            filter_parts = [p for p in [tier, industry] if p]
            filter_desc = " + ".join(filter_parts) if filter_parts else "no filters"
            summarise_prompt = (
                f"User asked: \"{message}\"\n"
                f"Filters: {filter_desc} | Leads found: {count}\n\n"
                "Write a short 1-2 sentence reply confirming what was found. "
                "Do NOT greet. If count is 0, suggest removing filters or checking the Leads page."
            )
            response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=summarise_prompt)])
            reply = response.content

        elif action == "get_outreach_history":
            tool_result = tools[2].invoke({})
            parsed = json.loads(tool_result)
            count = parsed.get("count", 0)
            summarise_prompt = (
                f"User asked: \"{message}\"\nOutreach records found: {count}\n\n"
                "Write a short 1-2 sentence reply. Do NOT greet."
            )
            response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=summarise_prompt)])
            reply = response.content

        elif action == "get_replies":
            tool_result = tools[3].invoke({})
            parsed = json.loads(tool_result)
            count = parsed.get("count", 0)
            summarise_prompt = (
                f"User asked: \"{message}\"\nReplies found: {count}\n\n"
                "Write a short 1-2 sentence reply. Do NOT greet."
            )
            response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=summarise_prompt)])
            reply = response.content

        elif action == "search_companies":
            industry = intent.get("industry", "").strip()
            location = intent.get("location", "").strip()
            count = int(intent.get("count") or 10)

            # Observe first — ask for anything missing before running Scout
            missing = []
            if not location:
                missing.append("location (e.g. Buffalo NY, Rochester NY, Chicago IL)")
            if not industry:
                missing.append("type of companies (e.g. healthcare, schools, manufacturing)")

            if missing:
                clarify_prompt = (
                    f"User asked: \"{message}\"\n"
                    f"To search for companies I still need: {', '.join(missing)}.\n\n"
                    "Ask the user for this in one short, friendly sentence. Do not run any search yet."
                )
                response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=clarify_prompt)])
                reply = response.content
            else:
                # Call the tool directly — never use agent loop here.
                # The agent loop risks hallucinating company names (especially with llama3.2)
                # because the follow-up message might be a bare location like "Rochester in NY"
                # which gives the LLM no clear instruction to call the tool.
                tool_result = tools[0].invoke({"industry": industry, "location": location, "count": count})
                parsed = json.loads(tool_result)
                if "error" in parsed:
                    reply = (
                        f"I ran into an error searching for {industry} companies in {location}: "
                        f"{parsed['error']}"
                    )
                else:
                    found = parsed.get("found", 0)
                    summarise_prompt = (
                        f"User asked to find {industry} companies in {location}. "
                        f"Scout found {found} companies and saved them to the database.\n\n"
                        "Write a short 1-2 sentence reply confirming what was found. "
                        "Do NOT list company names — the UI shows them as cards. Do NOT greet."
                    )
                    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=summarise_prompt)])
                    reply = response.content

        elif action == "run_full_pipeline":
            industry = intent.get("industry", "").strip()
            location = intent.get("location", "").strip()
            count = int(intent.get("count") or 10)

            missing = []
            if not location:
                missing.append("location")
            if not industry:
                missing.append("industry")

            if missing:
                clarify_prompt = (
                    f"User asked: \"{message}\"\n"
                    f"To run the full pipeline I need: {', '.join(missing)}.\n\n"
                    "Ask the user for this in one short sentence."
                )
                response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=clarify_prompt)])
                reply = response.content
            else:
                # Call tool directly — same reason as search_companies above
                tool_result = tools[4].invoke({"industry": industry, "location": location, "count": count})
                parsed = json.loads(tool_result)
                if "error" in parsed:
                    reply = f"Pipeline error: {parsed['error']}"
                else:
                    summarise_prompt = (
                        f"Full pipeline completed for {industry} in {location}. Results: {parsed}\n\n"
                        "Write a short 2-3 sentence summary of what was done. Do NOT greet."
                    )
                    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=summarise_prompt)])
                    reply = response.content

        else:
            # unknown — full agent loop handles complex / multi-step requests
            agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)
            response = agent.invoke({"messages": [HumanMessage(content=message)]})
            reply = response["messages"][-1].content

        _finish_run(db, run, "completed")
        logger.info("Chat run %s completed. message=%r", run.id, message[:80])

    except Exception as exc:
        logger.exception("Chat agent failed. run_id=%s", run.id)
        _finish_run(db, run, "failed")
        reply = (
            "Sorry, I ran into an error processing your request. "
            f"Details: {exc}"
        )

    return {
        "reply": reply,
        "data": results,
        "run_id": str(run.id),
    }
