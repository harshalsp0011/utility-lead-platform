from __future__ import annotations

"""LLM-based company data inspector and score narrator for the Analyst agent.

Two responsibilities:
1. inspect_company() — reads available company data and decides:
   - inferred_industry  : canonical industry if DB value is unknown/missing
   - data_gaps          : list of important missing fields
   - action             : "score_now" or "enrich_before_scoring"

2. generate_score_narrative() — writes a specific, human-readable one-sentence
   explanation of why this company scored the way it did.

Both functions have full fallback to rule-based behavior if the LLM call fails
or returns unparseable output. Scoring is never blocked by LLM failure.

LLM is skipped entirely when all key data is already present (no tokens wasted).
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Canonical industry values accepted by the rest of the system
_VALID_INDUSTRIES = {
    "healthcare", "hospitality", "manufacturing", "retail",
    "education", "logistics", "office", "public_sector",
    "technology", "finance", "unknown",
}


# ---------------------------------------------------------------------------
# Internal LLM caller (handles Ollama + OpenAI transparently)
# ---------------------------------------------------------------------------

def _call_llm(prompt: str) -> str:
    """Call the configured LLM and return raw text response."""
    from config.llm_config import get_llm
    from config.settings import get_settings

    settings = get_settings()
    provider = (settings.LLM_PROVIDER or "ollama").lower()

    llm = get_llm()

    if provider == "ollama":
        from langchain_core.messages import HumanMessage
        response = llm.invoke([HumanMessage(content=prompt)])
        return str(response.content).strip()

    if provider == "openai":
        response = llm.chat.completions.create(
            model=llm.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        return response.choices[0].message.content.strip()

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def _parse_json(text: str) -> dict[str, Any]:
    """Extract and parse JSON from LLM response (handles markdown code fences)."""
    text = text.strip()
    # Strip ```json ... ``` fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines
            if not line.startswith("```")
        ).strip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# Public: inspect_company
# ---------------------------------------------------------------------------

def inspect_company(
    name: str,
    website: str,
    industry: str,
    employee_count: int,
    site_count: int,
    crawled_text: str = "",
) -> dict[str, Any]:
    """Inspect available company data and decide how to proceed before scoring.

    Returns dict:
        inferred_industry : str   — canonical industry (or None if already known)
        data_gaps         : list  — fields that are missing and would improve scoring
        action            : str   — "score_now" or "enrich_before_scoring"
        confidence        : str   — "high" / "medium" / "low"

    Falls back to safe defaults on any error.
    """
    industry_known = (industry or "").strip().lower() not in ("", "unknown")
    data_sufficient = industry_known and employee_count > 0 and site_count > 0

    # Skip LLM entirely — all data present
    if data_sufficient:
        logger.debug("[inspector] %s — data sufficient, skipping LLM", name)
        return {
            "inferred_industry": None,
            "data_gaps": [],
            "action": "score_now",
            "confidence": "high",
        }

    prompt = f"""You are analyzing a company to help qualify it as a B2B sales lead.

Company name : {name}
Website      : {website or "none"}
Industry     : {industry or "unknown"}
Employees    : {employee_count if employee_count > 0 else "unknown"}
Sites/locations : {site_count if site_count > 0 else "unknown"}
Website text excerpt: {crawled_text[:600] if crawled_text else "not available"}

Return ONLY a JSON object — no explanation, no markdown:
{{
  "inferred_industry": "<canonical industry or null if already known>",
  "data_gaps": ["employee_count"],
  "confidence": "high",
  "action": "score_now"
}}

Rules:
- inferred_industry must be one of: healthcare, hospitality, manufacturing, retail,
  education, logistics, office, public_sector, technology, finance, unknown
- Set inferred_industry to null if industry is already set and not "unknown"
- data_gaps lists fields that are missing AND would meaningfully improve the score
- Set action to "enrich_before_scoring" ONLY when employee_count is unknown AND
  a website exists (more enrichment could realistically fill the gap)
- Set action to "score_now" in all other cases (no website, or data is good enough)
- confidence: how confident you are in the inferred_industry"""

    try:
        raw = _call_llm(prompt)
        result = _parse_json(raw)

        # Validate inferred_industry
        inferred = result.get("inferred_industry")
        if inferred and inferred.lower() not in _VALID_INDUSTRIES:
            logger.warning("[inspector] %s — unknown industry '%s', using 'unknown'", name, inferred)
            inferred = "unknown"

        action = result.get("action", "score_now")
        if action not in ("score_now", "enrich_before_scoring"):
            action = "score_now"

        logger.info(
            "[inspector] %s — industry=%s gaps=%s action=%s confidence=%s",
            name,
            inferred or industry,
            result.get("data_gaps", []),
            action,
            result.get("confidence", "?"),
        )

        return {
            "inferred_industry": inferred,
            "data_gaps": result.get("data_gaps", []),
            "action": action,
            "confidence": result.get("confidence", "medium"),
        }

    except Exception as exc:
        logger.warning("[inspector] %s — LLM inspect failed, using defaults: %s", name, exc)
        return {
            "inferred_industry": None,
            "data_gaps": [],
            "action": "score_now",
            "confidence": "low",
        }


# ---------------------------------------------------------------------------
# Public: generate_score_narrative
# ---------------------------------------------------------------------------

def generate_score_narrative(
    name: str,
    industry: str,
    employee_count: int,
    site_count: int,
    state: str,
    deregulated: bool,
    score: float,
    tier: str,
    savings_mid: float,
) -> str:
    """Generate a specific, human-readable one-sentence score explanation.

    Falls back to the rule-based template string on any LLM error.
    """
    savings_str = (
        f"${savings_mid / 1_000_000:.1f}M" if savings_mid >= 1_000_000
        else f"${savings_mid / 1_000:.0f}k"
    )
    energy_note = "deregulated energy market" if deregulated else "standard energy market"
    emp_str = f"{employee_count:,}" if employee_count > 0 else "unknown employee count"

    prompt = f"""Write ONE sentence (max 25 words) explaining why this company is a {tier}-tier sales lead
for a utility cost consulting firm. Be specific — mention the savings figure and what makes them
a good or average fit.

Company : {name}
Industry: {industry}
Employees: {emp_str}
Sites   : {site_count}
State   : {state or "unknown"} ({energy_note})
Score   : {score:.0f}/100  Tier: {tier}
Est. annual savings: {savings_str}

Return only the sentence. No quotes. No bullet points. Do not start with "This company"."""

    try:
        narrative = _call_llm(prompt)
        # Trim to first sentence if LLM returns multiple
        narrative = narrative.strip().split("\n")[0].strip('"').strip("'")
        if len(narrative) > 200:
            narrative = narrative[:200]
        logger.debug("[inspector] %s — narrative: %s", name, narrative)
        return narrative

    except Exception as exc:
        logger.warning("[inspector] %s — LLM narrative failed, using template: %s", name, exc)
        return _fallback_narrative(industry, site_count, savings_mid, deregulated)


def _fallback_narrative(
    industry: str,
    site_count: int,
    savings_mid: float,
    deregulated: bool,
) -> str:
    """Rule-based fallback — identical to old generate_score_reason."""
    industry_text = (industry or "unknown").replace("_", " ")
    savings_str = (
        f"${savings_mid / 1_000_000:.1f}M" if savings_mid >= 1_000_000
        else f"${savings_mid / 1_000:.0f}k"
    )
    parts = [f"{site_count}-site {industry_text} organization."]
    if deregulated:
        parts.append("Operating in a deregulated energy market.")
    parts.append(f"Estimated {savings_str} in recoverable savings.")
    if industry_text in {"healthcare", "hospitality", "manufacturing", "retail"}:
        parts.append("High energy intensity industry.")
    return " ".join(parts)
