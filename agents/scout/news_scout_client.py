from __future__ import annotations

"""News-based intent scout for the Scout agent.

Purpose:
  Find companies that appear in local business news with buying signals —
  expansion, new facilities, cost-cutting, renovation — indicating they
  are actively relevant for a utility cost audit right now.

This is different from regular company discovery (Google Maps / Tavily directories):
  Regular Scout:  "find healthcare companies in Rochester"  → lists existing businesses
  News Scout:     "healthcare expansion Rochester 2024"     → finds companies IN THE NEWS
                                                              with a reason to care NOW

Agentic concept used: Intent-Based Prospecting
  Instead of cold-finding any company, we surface companies at the right moment
  in their business cycle — when the buying signal is highest.

Buying signals we look for:
  - expansion       → new location/branch/facility opening
  - new_facility    → construction, breaking ground, renovation
  - cost_pressure   → budget cuts, rising costs, expense reduction
  - energy_news     → utility bills, energy costs, power contracts
  - acquisition     → merger/acquisition (more sites under one roof)

Flow:
  1. LLM generates 3 news-specific search queries (different angle from regular queries)
  2. Tavily news search returns article snippets (not directory URLs)
  3. LLM reads each snippet → extracts company name + signal type + signal detail
  4. Returns list of company dicts with intent_signal field populated

Dependencies:
  - TAVILY_API_KEY in .env
  - SEARCH_PROVIDER=tavily in .env
  - LLM (Ollama or OpenAI) for extraction

Usage:
    from agents.scout.news_scout_client import find_companies_in_news
    results = find_companies_in_news("healthcare", "Rochester NY", max_results=10)
    # results = [
    #   { "name": "Rochester Regional Health", "city": "Rochester", "state": "NY",
    #     "industry": "healthcare", "source": "news_scout",
    #     "source_url": "https://...", "intent_signal": "expansion: opening new urgent care center" }
    # ]
"""

import json
import logging
from typing import Any

import requests

from config.settings import get_settings

logger = logging.getLogger(__name__)

_TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Signal categories the LLM should classify into
_SIGNAL_TYPES = [
    "expansion",       # new location, branch, or market entry
    "new_facility",    # construction, renovation, breaking ground
    "cost_pressure",   # budget cuts, rising costs, expense reduction
    "energy_news",     # utility bills, power contracts, energy audit
    "acquisition",     # merger or acquisition (more sites combined)
    "hiring",          # large hiring = growth = higher spend
]


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _call_llm(prompt: str) -> str:
    from config.llm_config import get_llm
    from langchain_core.messages import HumanMessage
    llm = get_llm()
    response = llm.invoke([HumanMessage(content=prompt)])
    return str(response.content).strip()


def _generate_news_queries(industry: str, location: str) -> list[str]:
    """Ask LLM to generate 3 news-signal search queries for this industry + location.

    These are intentionally different from regular company discovery queries —
    they look for events and signals, not directories.
    """
    prompt = f"""Generate 3 search queries to find {industry} companies in {location}
that appear in LOCAL BUSINESS NEWS with buying signals like expansion, new facilities,
rising costs, or renovations.

These should find NEWS ARTICLES, not company directories.

Return ONLY a JSON array of 3 query strings:
["query 1", "query 2", "query 3"]

Examples of good queries:
- "{industry} company expansion {location} 2024"
- "{industry} new facility construction {location}"
- "{location} {industry} rising utility costs budget"

Rules:
- Include year (2024 or 2025) in at least one query to get recent news
- Focus on events that signal high utility spend or active cost concern
- Include location in every query"""

    try:
        raw = _call_llm(prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.splitlines() if not l.startswith("```")).strip()
        queries = json.loads(raw)
        if isinstance(queries, list) and len(queries) >= 2:
            return [str(q).strip() for q in queries if str(q).strip()][:3]
    except Exception as exc:
        logger.warning("[news_scout] Query generation failed: %s", exc)

    # Fallback: static signal queries
    return [
        f"{industry} expansion new location {location} 2024",
        f"{industry} new facility construction {location}",
        f"{location} {industry} energy costs budget reduction",
    ]


def _extract_companies_from_snippets(
    snippets: list[dict[str, str]],
    industry: str,
    location: str,
) -> list[dict[str, Any]]:
    """Ask LLM to extract company names + signals from Tavily article snippets.

    snippets: list of { "title": "...", "content": "...", "url": "..." }
    Returns:  list of extracted company dicts with intent_signal
    """
    if not snippets:
        return []

    # Build a compact representation of all snippets for one LLM call
    snippet_lines = []
    for i, s in enumerate(snippets[:8]):  # cap at 8 snippets per LLM call
        title = s.get("title", "")[:120]
        content = s.get("content", "")[:200]
        url = s.get("url", "")
        snippet_lines.append(f"[{i+1}] Title: {title}\n    Snippet: {content}\n    URL: {url}")

    snippets_text = "\n\n".join(snippet_lines)

    prompt = f"""Below are news article snippets about {industry} businesses in {location}.

Extract any REAL companies mentioned that are relevant for utility cost consulting.
For each company found, identify the buying signal (why they need an audit now).

{snippets_text}

Return ONLY a JSON array. Each item must have:
{{
  "name": "Company Name",
  "city": "City",
  "state": "NY",
  "signal_type": "expansion|new_facility|cost_pressure|energy_news|acquisition|hiring",
  "signal_detail": "one sentence describing what the news says",
  "source_url": "the article URL"
}}

Rules:
- Only extract REAL named companies (not generic references like "a local hospital")
- Only include companies in the {location} area
- If no relevant companies found, return []
- Do not make up companies — only extract what is explicitly named in the snippets"""

    try:
        raw = _call_llm(prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.splitlines() if not l.startswith("```")).strip()

        extracted = json.loads(raw)
        if not isinstance(extracted, list):
            return []

        results = []
        for item in extracted:
            name = str(item.get("name", "")).strip()
            if not name or len(name) < 3:
                continue

            signal_type = str(item.get("signal_type", "")).strip()
            signal_detail = str(item.get("signal_detail", "")).strip()
            intent_signal = f"{signal_type}: {signal_detail}" if signal_type and signal_detail else signal_detail or signal_type

            results.append({
                "name": name,
                "city": str(item.get("city", "")).strip() or location.split()[0],
                "state": str(item.get("state", "")).strip() or "",
                "industry": industry,
                "source": "news_scout",
                "source_url": str(item.get("source_url", "")).strip(),
                "intent_signal": intent_signal,
                "website": None,  # populated later by enrichment if needed
                "phone": None,
            })

        logger.info("[news_scout] Extracted %d companies from %d snippets", len(results), len(snippets))
        return results

    except Exception as exc:
        logger.warning("[news_scout] LLM extraction failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Tavily news search
# ---------------------------------------------------------------------------

def _search_news(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Run one Tavily search in news mode. Returns article snippets."""
    settings = get_settings()
    api_key = str(settings.TAVILY_API_KEY or "").strip()
    if not api_key:
        return []

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "topic": "news",          # ← Tavily news mode: returns recent articles, not pages
        "max_results": max_results,
    }

    try:
        response = requests.post(_TAVILY_SEARCH_URL, json=payload, timeout=15)
        response.raise_for_status()
        body = response.json()
        results = body.get("results", [])
        return [
            {
                "title": str(r.get("title", "")),
                "content": str(r.get("content", "")),
                "url": str(r.get("url", "")),
            }
            for r in results
            if r.get("title") or r.get("content")
        ]
    except Exception as exc:
        logger.warning("[news_scout] Tavily news search failed for '%s': %s", query, exc)
        return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def find_companies_in_news(
    industry: str,
    location: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Find companies in local news with utility-audit buying signals.

    Agentic concept: Intent-Based Prospecting — surfaces companies at the
    right moment in their business cycle, not just any company in the area.

    Steps:
    1. LLM generates 3 news-signal search queries
    2. Tavily news search returns article snippets (topic="news")
    3. LLM extracts company names + signal type + signal detail from snippets
    4. Returns deduplicated list with intent_signal field populated

    Args:
        industry:    e.g. "healthcare", "manufacturing"
        location:    e.g. "Rochester NY"
        max_results: cap on companies to return

    Returns:
        list of company dicts, each with intent_signal field set
    """
    settings = get_settings()
    provider = str(settings.SEARCH_PROVIDER or "").strip().lower()
    api_key = str(settings.TAVILY_API_KEY or "").strip()

    if provider != "tavily" or not api_key:
        logger.info("[news_scout] Skipping — Tavily not configured")
        return []

    # Step 1: generate news-specific search queries
    queries = _generate_news_queries(industry, location)
    logger.info("[news_scout] News queries for %s/%s: %s", industry, location, queries)

    # Step 2: search Tavily in news mode — collect all snippets
    all_snippets: list[dict[str, str]] = []
    for query in queries:
        snippets = _search_news(query, max_results=5)
        all_snippets.extend(snippets)
        logger.info("[news_scout] Query '%s' → %d snippets", query, len(snippets))

    if not all_snippets:
        logger.info("[news_scout] No news snippets found for %s in %s", industry, location)
        return []

    # Step 3: LLM extracts companies + signals from snippets
    companies = _extract_companies_from_snippets(all_snippets, industry, location)

    # Step 4: basic dedup by name within this batch
    seen_names: set[str] = set()
    unique: list[dict[str, Any]] = []
    for c in companies:
        key = c["name"].lower().strip()
        if key not in seen_names:
            seen_names.add(key)
            unique.append(c)

    return unique[:max_results]
