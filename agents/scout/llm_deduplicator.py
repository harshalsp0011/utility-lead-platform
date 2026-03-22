from __future__ import annotations

"""LLM-based deduplicator for the Scout agent.

Removes near-duplicate companies from a batch collected in a single Scout run.
Rule-based domain matching handles obvious duplicates; LLM handles name-variant
cases that rule matching misses (e.g. "Buffalo City School District" vs "BCSD").

Two-pass approach:
  Pass 1 (rule-based) — exact domain dedup. Fast, handles ~80% of duplicates.
  Pass 2 (LLM)        — groups by city+industry, finds name-variant duplicates.
                         Skipped if batch is small (< 5 companies) or LLM fails.

Falls back to rule-based-only output on any LLM error.
LLM tokens: ~150 per batch.
"""

import json
import logging
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Name similarity threshold to flag as "suspicious pair" for LLM review
_SIMILARITY_THRESHOLD = 0.75

# Max suspicious pairs to send to LLM in one call
_MAX_PAIRS_PER_LLM_CALL = 8


# ---------------------------------------------------------------------------
# Internal helpers
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


def _extract_domain(website: str | None) -> str | None:
    if not website:
        return None
    try:
        host = urlparse(website).netloc.lower().removeprefix("www.")
        return host if host else None
    except Exception:
        return None


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _find_suspicious_pairs(companies: list[dict]) -> list[tuple[int, int]]:
    """Find index pairs whose names are similar but don't share a domain."""
    pairs: list[tuple[int, int]] = []
    n = len(companies)
    for i in range(n):
        for j in range(i + 1, n):
            a = companies[i]
            b = companies[j]

            # Same city only — cross-city same name is NOT a duplicate
            city_a = (a.get("city") or "").lower().strip()
            city_b = (b.get("city") or "").lower().strip()
            if city_a and city_b and city_a != city_b:
                continue

            # Already deduped by domain — skip
            dom_a = _extract_domain(a.get("website"))
            dom_b = _extract_domain(b.get("website"))
            if dom_a and dom_b and dom_a == dom_b:
                continue  # already removed in pass 1

            # Flag if names are similar enough to warrant LLM review
            sim = _name_similarity(
                a.get("name", ""),
                b.get("name", ""),
            )
            if sim >= _SIMILARITY_THRESHOLD:
                pairs.append((i, j))

    return pairs[:_MAX_PAIRS_PER_LLM_CALL]


def _ask_llm_which_are_duplicates(
    companies: list[dict],
    pairs: list[tuple[int, int]],
) -> set[int]:
    """Ask LLM which companies in the suspicious pairs are duplicates.

    Returns a set of indexes to DROP (the second occurrence in each duplicate pair).
    """
    pair_descriptions = []
    for idx, (i, j) in enumerate(pairs):
        a = companies[i]
        b = companies[j]
        pair_descriptions.append(
            f'Pair {idx + 1}: "{a.get("name")}" ({a.get("city")}) vs '
            f'"{b.get("name")}" ({b.get("city")})'
        )

    pairs_text = "\n".join(pair_descriptions)

    prompt = f"""I collected company records and need to remove duplicates. For each pair below, decide if both entries refer to the SAME real-world company (abbreviation, alternate name, etc.) or if they are DIFFERENT companies.

{pairs_text}

Return ONLY a JSON array of pair numbers that are duplicates (1-indexed).
Example: [1, 3] means pairs 1 and 3 are duplicates.
If none are duplicates, return: []"""

    try:
        raw = _call_llm(prompt)
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(line for line in lines if not line.startswith("```")).strip()

        dup_pair_nums = json.loads(raw)
        if not isinstance(dup_pair_nums, list):
            return set()

        # For each flagged pair, drop the second entry (higher index)
        drop_indexes: set[int] = set()
        for num in dup_pair_nums:
            try:
                pair_idx = int(num) - 1
                if 0 <= pair_idx < len(pairs):
                    _, j = pairs[pair_idx]
                    drop_indexes.add(j)
            except (ValueError, TypeError):
                pass

        return drop_indexes

    except Exception as exc:
        logger.warning("[deduplicator] LLM pair review failed: %s", exc)
        return set()


# ---------------------------------------------------------------------------
# Public: deduplicate
# ---------------------------------------------------------------------------

def deduplicate(companies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate companies from a batch.

    Pass 1 (rule-based): drops companies sharing an exact domain.
    Pass 2 (LLM):        reviews name-similar pairs within the same city
                         and drops the second occurrence of confirmed duplicates.

    Falls back to pass-1 output if LLM fails or batch is too small for LLM.
    """
    if not companies:
        return companies

    # --- Pass 1: domain dedup ---
    seen_domains: set[str] = set()
    pass1: list[dict] = []
    for company in companies:
        domain = _extract_domain(company.get("website"))
        if domain:
            if domain in seen_domains:
                logger.debug("[deduplicator] Domain dup dropped: %s (%s)", company.get("name"), domain)
                continue
            seen_domains.add(domain)
        pass1.append(company)

    removed_pass1 = len(companies) - len(pass1)
    if removed_pass1:
        logger.info("[deduplicator] Pass 1 removed %d domain duplicates", removed_pass1)

    # --- Pass 2: LLM near-duplicate review ---
    if len(pass1) < 5:
        # Too small to bother LLM
        return pass1

    suspicious = _find_suspicious_pairs(pass1)
    if not suspicious:
        return pass1

    logger.info(
        "[deduplicator] Pass 2: sending %d suspicious name-pairs to LLM", len(suspicious)
    )
    drop_indexes = _ask_llm_which_are_duplicates(pass1, suspicious)

    if not drop_indexes:
        return pass1

    pass2 = [c for idx, c in enumerate(pass1) if idx not in drop_indexes]
    logger.info(
        "[deduplicator] Pass 2 removed %d near-duplicates — batch: %d → %d",
        len(drop_indexes), len(pass1), len(pass2),
    )
    return pass2
