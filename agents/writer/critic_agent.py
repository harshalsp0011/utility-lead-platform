from __future__ import annotations

"""Critic Agent for the Writer + Critic Loop (Phase C).

Purpose:
  Evaluates an email draft against a 5-criteria rubric and returns a score
  with actionable feedback. The Writer uses this feedback to rewrite if needed.

Agentic concept: Self-Critique / Reflection Loop
  A separate LLM call acts as a quality gatekeeper. The Writer sees the Critic's
  specific instruction and rewrites to address it. This is the Reflection pattern —
  generate → evaluate → improve → repeat.

Rubric (2 points each, 10 max):
  1. Personalization  — mentions company name or a specific detail (not generic)
  2. Savings figure   — contains a dollar or % savings estimate
  3. Clear CTA        — specific next step (call, free audit, reply)
  4. Human tone       — reads like a person, not a template
  5. Subject quality  — specific subject line (not "Quick question" or "Hello")

Score interpretation:
  8–10  pass — save and send to human review queue normally
  6–7   marginal pass — acceptable, minor issues
  < 6   fail — trigger rewrite (max 2 rewrites)
  < 7 after 2 rewrites → save with low_confidence = true

LLM tokens: ~400 per evaluation call. Cheap with Ollama.

Usage:
    from agents.writer.critic_agent import evaluate
    result = evaluate(subject="...", body="...", company_context={...})
    # result = {
    #   "score": 7.5,
    #   "passed": True,
    #   "feedback": "Good personalization. Add a specific savings figure.",
    #   "criteria": {
    #     "personalization": 2, "savings_figure": 1, "clear_cta": 2,
    #     "human_tone": 2, "subject_quality": 1
    #   }
    # }
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_PASS_THRESHOLD = 7.0   # score >= this is considered acceptable
_MAX_SCORE = 10.0


def _call_llm(prompt: str) -> str:
    from config.llm_config import get_llm
    from langchain_core.messages import HumanMessage
    llm = get_llm()
    response = llm.invoke([HumanMessage(content=prompt)])
    return str(response.content).strip()


_CRITIC_PROMPT = """You are a B2B email quality reviewer for a utility cost consulting firm.
Evaluate this outreach email draft against the rubric below.

== COMPANY CONTEXT ==
Company: {company_name}
Industry: {industry}
City: {city}, {state}
Sites: {site_count}
Est. annual savings: {savings_mid}
Score reason from analyst: {score_reason}
Contact: {contact_name} ({contact_title})

== EMAIL DRAFT ==
Subject: {subject}

{body}

== RUBRIC (score each 0, 1, or 2) ==
1. personalization  — mentions company name or a specific detail about them (not generic boilerplate)
2. savings_figure   — contains a specific dollar or % savings estimate (not vague "significant savings")
3. clear_cta        — has a specific next step: "free audit", "15-min call", "reply to schedule" etc.
4. human_tone       — reads like a real person wrote it, not a template or AI
5. subject_quality  — subject is specific to this company (not "Quick question" / "Hello" / "Checking in")

Return ONLY this JSON — no explanation, no markdown:
{{
  "criteria": {{
    "personalization": <0|1|2>,
    "savings_figure":  <0|1|2>,
    "clear_cta":       <0|1|2>,
    "human_tone":      <0|1|2>,
    "subject_quality": <0|1|2>
  }},
  "score": <total 0-10>,
  "passed": <true if score >= 7>,
  "feedback": "<one sentence: what is the biggest weakness and exactly how to fix it>"
}}"""


# Extended prompt for CRM path — adds context_accuracy as 6th criterion
# Agentic concept: Self-Critique with Context Alignment Check
# Max score = 12, pass threshold = 8 (same 70% bar as pipeline path)
_CRITIC_PROMPT_CRM = """You are a B2B email quality reviewer for a utility cost consulting firm.
Evaluate this outreach email draft against the rubric below.

== COMPANY CONTEXT ==
Company: {company_name}
Industry: {industry}
City: {city}, {state}
Sites: {site_count}
Est. annual savings: {savings_mid}
Contact: {contact_name} ({contact_title})

== MEETING CONTEXT (what was discussed in person) ==
{context_notes}

== EMAIL DRAFT ==
Subject: {subject}

{body}

== RUBRIC (score each 0, 1, or 2) ==
1. personalization       — mentions company name or a specific detail about them (not generic boilerplate)
2. relationship_reference — references the actual meeting or prior conversation (e.g. "when we spoke", "as you mentioned", "following up from the summit") — NOT a generic cold pitch
3. clear_cta             — has a specific next step: "free audit", "15-min call", "reply to schedule" etc.
4. human_tone            — reads like a real person wrote it, not a template or AI
5. subject_quality       — subject is specific to this company (not "Quick question" / "Hello" / "Checking in")
6. context_accuracy      — email actually reflects the meeting discussion points above (mentions pain points,
                           interests, or facts from the meeting context — not just generic utility pitch)

Note: Do NOT penalise the email for missing a savings dollar figure — savings are intentionally omitted
for CRM leads as the estimate is not yet verified. The audit offer IS the value proposition.

Return ONLY this JSON — no explanation, no markdown:
{{
  "criteria": {{
    "personalization":        <0|1|2>,
    "relationship_reference": <0|1|2>,
    "clear_cta":              <0|1|2>,
    "human_tone":             <0|1|2>,
    "subject_quality":        <0|1|2>,
    "context_accuracy":       <0|1|2>
  }},
  "score": <total 0-12>,
  "passed": <true if score >= 8>,
  "feedback": "<one sentence: what is the biggest weakness and exactly how to fix it>"
}}"""

_CRM_CRITERIA = ("personalization", "relationship_reference", "clear_cta", "human_tone", "subject_quality", "context_accuracy")
_PIPELINE_CRITERIA = ("personalization", "savings_figure", "clear_cta", "human_tone", "subject_quality")
_CRM_PASS_THRESHOLD = 8.0   # 8/12 ≈ same 70% bar as pipeline 7/10


def evaluate(
    subject: str,
    body: str,
    company_context: dict[str, Any],
    context_notes: str | None = None,
) -> dict[str, Any]:
    """Evaluate an email draft. Returns score, pass/fail, and improvement feedback.

    Args:
        subject:         Email subject line
        body:            Email body text
        company_context: Dict with keys: company_name, industry, city, state,
                         site_count, savings_mid, score_reason, contact_name,
                         contact_title. Missing keys default to empty string.
        context_notes:   Optional — formatted meeting context bullet points (CRM path only).
                         When provided, activates the 6-criterion CRM rubric (max 12, pass >= 8).
                         When None, uses the standard 5-criterion pipeline rubric (max 10, pass >= 7).

    Agentic concept:
        Standard path  — Self-Critique / Reflection (5 criteria, pipeline leads)
        CRM path       — Self-Critique + Context Alignment Check (6 criteria, CRM leads)
                         6th criterion verifies the email reflects actual meeting discussion points.

    Returns:
        {
          "score":    float,
          "passed":   bool,
          "feedback": str,
          "criteria": dict,
          "crm_mode": bool  — True if 6-criterion rubric was used
        }
    """
    def _get(key: str, default: str = "") -> str:
        val = company_context.get(key)
        return str(val).strip() if val else default

    crm_mode = bool(context_notes and context_notes.strip())

    if crm_mode:
        prompt = _CRITIC_PROMPT_CRM.format(
            company_name=_get("company_name", "the company"),
            industry=_get("industry"),
            city=_get("city"),
            state=_get("state"),
            site_count=_get("site_count", "unknown"),
            savings_mid=_get("savings_mid", "not estimated"),
            contact_name=_get("contact_name", "unknown"),
            contact_title=_get("contact_title", ""),
            context_notes=context_notes.strip(),
            subject=subject,
            body=body,
        )
        criteria_keys = _CRM_CRITERIA
        pass_threshold = _CRM_PASS_THRESHOLD
    else:
        prompt = _CRITIC_PROMPT.format(
            company_name=_get("company_name", "the company"),
            industry=_get("industry"),
            city=_get("city"),
            state=_get("state"),
            site_count=_get("site_count", "unknown"),
            savings_mid=_get("savings_mid", "not estimated"),
            score_reason=_get("score_reason", "not available"),
            contact_name=_get("contact_name", "unknown"),
            contact_title=_get("contact_title", ""),
            subject=subject,
            body=body,
        )
        criteria_keys = _PIPELINE_CRITERIA
        pass_threshold = _PASS_THRESHOLD

    try:
        raw = _call_llm(prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.splitlines() if not l.startswith("```")).strip()

        result = json.loads(raw)

        criteria = result.get("criteria", {})
        score = float(result.get("score", 0))
        # Recalculate score from criteria in case LLM arithmetic is off
        if criteria:
            score = float(sum(int(criteria.get(k, 0)) for k in criteria_keys))

        passed = score >= pass_threshold
        feedback = str(result.get("feedback", "")).strip() or "Improve specificity and personalization."

        logger.info(
            "[critic] crm_mode=%s score=%.1f/%.0f passed=%s criteria=%s feedback=%r",
            crm_mode, score, (12 if crm_mode else 10), passed, criteria, feedback[:80],
        )

        return {
            "score": score,
            "passed": passed,
            "feedback": feedback,
            "criteria": criteria,
            "crm_mode": crm_mode,
        }

    except Exception as exc:
        logger.warning("[critic] LLM evaluation failed: %s — returning neutral pass", exc)
        return {
            "score": pass_threshold,
            "passed": True,
            "feedback": "",
            "criteria": {},
            "crm_mode": crm_mode,
        }
