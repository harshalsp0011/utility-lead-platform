from __future__ import annotations

"""Context Formatter — CRM Lead Preprocessing Agent.

Agentic concept: Information Structuring / Preprocessing Agent
  The LLM reads raw meeting notes (free-text, unstructured, often stream-of-consciousness)
  and reorganizes them into clean, ordered bullet points — one fact or signal per line.
  It decides what is a real signal (multi-site, no vendor contract, open to audit) vs
  filler (pleasantries, repeated info, vague statements). This is not a regex or template.
  The LLM makes editorial judgments about what matters.

Tool:  LLM call via llm_connector (Ollama or OpenAI)
Tech:  LangChain-compatible prompt, same provider selection as writer_agent

Why this matters:
  The Writer and Critic receive formatted bullet points as `score_reason`.
  Clean, structured signals = better angle selection and more accurate context_accuracy
  scoring by the Critic. Garbage in → garbage email out.

Fallback:
  If the LLM call fails for any reason, `notes_raw` is stored as-is in both columns.
  The user sees a note that formatting failed — generation is never blocked.

Usage:
    from agents.writer.context_formatter import format_context_notes
    formatted = format_context_notes("Met John at conference, 12 locations, open to audit")
    # Returns:
    # "- Met contact (John) at industry conference\n- 12 locations\n- Open to audit"
"""

import logging

from agents.writer import llm_connector

logger = logging.getLogger(__name__)

_FORMATTER_PROMPT = """You are a sales intelligence assistant. Your job is to take raw meeting notes
and convert them into clean, structured bullet points for a sales team.

== RAW NOTES ==
{raw_notes}

== YOUR TASK ==
Extract every meaningful signal from the notes above. A signal is any fact that could
influence how a sales email is written — company size, pain points, interests, objections,
context about the meeting, or anything the prospect said about their situation.

Rules:
- One bullet point per signal
- Start each line with a dash (-)
- Be factual and concise — no padding, no opinions
- Remove filler (pleasantries, vague statements like "seemed interested")
- If a specific number is mentioned (locations, employees, dollar amount), keep it exactly
- If the prospect expressed interest in something specific, capture it clearly
- Order: company facts first, then pain points, then expressed interests/next steps

Return ONLY the bullet points — no intro, no explanation, no headers."""


def format_context_notes(raw_notes: str) -> str:
    """Format raw meeting notes into structured bullet points using LLM.

    Agentic concept: Information Structuring / Preprocessing Agent —
    LLM reasons about what signals matter and structures them for downstream use.

    Args:
        raw_notes: Free-text meeting notes as entered by the user.

    Returns:
        Formatted bullet-point string. Falls back to raw_notes if LLM fails.
    """
    if not raw_notes or not raw_notes.strip():
        return ""

    try:
        prompt = _FORMATTER_PROMPT.format(raw_notes=raw_notes.strip())
        provider = llm_connector.select_provider()
        if provider == "openai":
            result = llm_connector.call_openai(prompt)
        else:
            # 350 tokens is plenty for bullet-point meeting notes extraction
            result = llm_connector.call_ollama(prompt, max_tokens=350)

        formatted = result.strip()

        # Sanity check — if LLM returned something that looks like an explanation
        # rather than bullet points, fall back to raw
        if not formatted or not any(line.strip().startswith("-") for line in formatted.splitlines()):
            logger.warning("[context_formatter] LLM output did not contain bullet points — using raw notes")
            return raw_notes.strip()

        logger.info("[context_formatter] Formatted %d chars → %d bullet points",
                    len(raw_notes), sum(1 for l in formatted.splitlines() if l.strip().startswith("-")))
        return formatted

    except Exception:
        logger.exception("[context_formatter] LLM formatting failed — falling back to raw notes")
        return raw_notes.strip()
