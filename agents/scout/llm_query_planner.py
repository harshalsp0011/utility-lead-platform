from __future__ import annotations

"""LLM-based search query planner for the Scout agent.

Generates diverse search query variants from user intent so Scout discovers
more companies than a single fixed query would find.

Two responsibilities:
1. plan_queries()       — given industry + location, LLM generates 3–5 varied
                          queries covering subtypes, synonyms, and regional terms.
2. plan_retry_queries() — when quality check finds too few results, LLM generates
                          3 additional queries distinct from what was already tried.

Both functions fall back to static defaults on any LLM failure.
LLM is ~80 tokens per call.
"""

import json
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal LLM caller (same pattern as llm_inspector.py)
# ---------------------------------------------------------------------------

def _call_llm(prompt: str) -> str:
    from config.llm_config import get_llm
    from config.settings import get_settings
    from langchain_core.messages import HumanMessage

    settings = get_settings()
    provider = (settings.LLM_PROVIDER or "ollama").lower()
    llm = get_llm()

    if provider == "ollama":
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


def _parse_query_list(text: str) -> list[str]:
    """Extract a list of query strings from LLM response (JSON array or line list)."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(line for line in lines if not line.startswith("```")).strip()

    # Try JSON array first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return [str(q).strip() for q in result if str(q).strip()]
    except (json.JSONDecodeError, ValueError):
        pass

    # Fall back: numbered list or bare lines
    queries = []
    for line in text.splitlines():
        line = line.strip().lstrip("0123456789.-) ").strip().strip('"').strip("'")
        if line and len(line) > 5:
            queries.append(line)
    return queries


# ---------------------------------------------------------------------------
# Fallbacks
# ---------------------------------------------------------------------------

def _fallback_queries(industry: str, location: str) -> list[str]:
    """Static fallback — identical to current hardcoded behavior."""
    return [
        f"{industry} businesses in {location}",
        f"{industry} companies directory in {location}",
        f"top {industry} employers {location}",
    ]


def _retry_fallback(industry: str, location: str, used_queries: list[str]) -> list[str]:
    """Static retry fallback — broader/narrower variants not yet tried."""
    candidates = [
        f"{industry} organizations near {location}",
        f"large {industry} companies {location}",
        f"{industry} facilities {location}",
        f"{industry} services {location}",
        f"local {industry} {location}",
    ]
    used_lower = {q.lower() for q in used_queries}
    return [q for q in candidates if q.lower() not in used_lower][:3]


# ---------------------------------------------------------------------------
# Public: plan_queries
# ---------------------------------------------------------------------------

def plan_queries(industry: str, location: str, count: int = 4) -> list[str]:
    """Generate diverse search query variants for company discovery.

    LLM reasons about what subtypes, synonyms, and regional terms would find
    the most relevant businesses — not just one fixed search string.

    Returns 3–5 query strings. Falls back to static defaults on any LLM error.
    LLM tokens: ~80.
    """
    prompt = f"""Generate {count} diverse search queries to find {industry} companies in {location} for B2B sales prospecting.

Each query must take a DIFFERENT angle: subtypes, synonyms, or specific business types within {industry}.

Return ONLY a JSON array of query strings, no explanation, no markdown:
["query 1", "query 2", "query 3", "query 4"]

Rules:
- 3 to 8 words per query
- Include the location or region in every query
- Queries must be different enough to return different businesses
- Think about all the specific kinds of {industry} businesses that exist"""

    try:
        raw = _call_llm(prompt)
        queries = _parse_query_list(raw)
        queries = [q for q in queries if len(q) > 5][:5]

        if len(queries) >= 2:
            logger.info(
                "[query_planner] Generated %d queries for %s in %s: %s",
                len(queries), industry, location, queries,
            )
            return queries

        logger.warning(
            "[query_planner] LLM returned %d usable queries — using fallback", len(queries)
        )
        return _fallback_queries(industry, location)

    except Exception as exc:
        logger.warning("[query_planner] LLM failed, using fallback: %s", exc)
        return _fallback_queries(industry, location)


# ---------------------------------------------------------------------------
# Public: plan_retry_queries
# ---------------------------------------------------------------------------

def plan_retry_queries(
    industry: str,
    location: str,
    results_found: int,
    target: int,
    used_queries: list[str],
) -> list[str]:
    """Generate 3 new queries when the quality check found too few results.

    LLM sees what was already tried and reasons about what different angles
    could uncover more companies.

    Returns 2–3 new query strings. Falls back to static variants on any LLM error.
    LLM tokens: ~100.
    """
    used_str = "\n".join(f"- {q}" for q in used_queries[:6])

    prompt = f"""I searched for {industry} companies in {location} and only found {results_found} out of {target} needed.

Queries already tried:
{used_str}

Generate 3 NEW search queries to find DIFFERENT {industry} businesses — try different subtypes, nearby areas, or terminology not already used above.

Return ONLY a JSON array of 3 query strings:
["query 1", "query 2", "query 3"]"""

    try:
        raw = _call_llm(prompt)
        queries = _parse_query_list(raw)
        queries = [q for q in queries if len(q) > 5][:3]

        if len(queries) >= 2:
            logger.info(
                "[query_planner] Retry: %d new queries for %s in %s: %s",
                len(queries), industry, location, queries,
            )
            return queries

        return _retry_fallback(industry, location, used_queries)

    except Exception as exc:
        logger.warning("[query_planner] Retry LLM failed: %s", exc)
        return _retry_fallback(industry, location, used_queries)
