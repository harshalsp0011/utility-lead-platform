# Scout Agent

Discovers companies from multiple sources and saves them to the database for Analyst to score.

---

## Agentic Flow — Phase B ✅ COMPLETE (2026-03-22)

**Before Phase B (rule-based):** one fixed query per source: `"{industry} in {location}"`

**After Phase B (agentic):**

```
scout_agent.run(industry, location, count)
  ↓
Step 1 — LLM Query Planner (~80 tokens):
  Input:  industry, location, target_count
  Output: ["elementary schools Buffalo NY", "private schools Western New York",
           "K-12 school districts Erie County", "charter schools Buffalo NY"]
  Fallback: ["healthcare businesses in Buffalo NY", "healthcare companies directory...", ...]
  ↓
Step 2 — Directory sources (unchanged)
  configured DB sources scraped first, deduplicated vs DB
  ↓
Step 3 — Tavily: runs ALL planned queries (not 3 hardcoded strings)
  each query → Tavily finds directory URLs → scraped for company listings
  ↓
Step 4 — Google Maps: runs ALL planned queries via query_text param
  each query sends a distinct textQuery to Places API → collects all results
  ↓
Step 5 — LLM Deduplicator (~150 tokens):
  Pass 1 (rule-based): exact domain match within batch
  Pass 2 (LLM): name-similar pairs (similarity > 0.75) reviewed by LLM
  "Buffalo City School District" + "BCSD" → same company, drops duplicate
  ↓
Step 6 — Quality check:
  if saved < 80% of target → plan_retry_queries() → 3 new LLM queries → retry once
  ↓
Step 7 — Save to DB, update source_performance
```

**What this enables:**
- User says "find schools" → agent searches elementary, private, charter, university, K-12 district — not just "schools"
- Multiple query variants return overlapping results → deduplicator merges them
- If still not enough: agent detects the gap and retries with different queries automatically

**LLM calls per Scout run:** up to 3 (~300 tokens)
- 1 for query planning (always)
- 1 for deduplication (when API batch has ≥ 5 companies with similar names)
- 1 for retry planning (only when < 80% of target found)

---

## Files

| File | Purpose |
|---|---|
| `scout_agent.py` | Main entry point — orchestrates all sources, query planning, dedup, quality check |
| `llm_query_planner.py` | **NEW (Phase B)** — generates multi-variant search queries from intent |
| `llm_deduplicator.py` | **NEW (Phase B)** — removes near-duplicate companies (domain + LLM name review) |
| `directory_scraper.py` | Scrapes HTML directory listing pages |
| `company_extractor.py` | Cleans fields, normalizes state/phone, checks duplicates, saves |
| `website_crawler.py` | Visits company website, extracts employee_count + site_count |
| `search_client.py` | Tavily API — now accepts custom query list via `search_with_queries()` |
| `google_maps_client.py` | Google Maps Places API — now accepts `query_text` override param |
| `yelp_client.py` | Yelp Business Search API integration |
| `scout_critic.py` | Quality scorer — rates each source's output 0–10 |

---

## Fallback Safety

Every LLM call is wrapped in `try/except`. If the LLM fails:
- Query planner falls back to 3 static queries: `"{industry} businesses in {location}"`, etc.
- Deduplicator falls back to domain-only dedup (no LLM near-duplicate check)
- Retry query planner falls back to 3 static broader/narrower variants

**Scout never blocks or crashes because of LLM failure.**

---

## Files

| File | Purpose |
|---|---|
| `scout_agent.py` | Main entry point — orchestrates all sources, saves companies |
| `llm_query_planner.py` | **NEW (Phase B)** — generates multi-variant search queries |
| `llm_deduplicator.py` | **NEW (Phase B)** — merges near-duplicate company results |
| `directory_scraper.py` | Scrapes HTML directory listing pages |
| `company_extractor.py` | Cleans fields, normalizes state/phone, checks duplicates, saves |
| `website_crawler.py` | Visits company website, extracts employee_count + site_count |
| `search_client.py` | Tavily API calls for dynamic URL discovery |
| `google_maps_client.py` | Google Maps Places API integration |
| `yelp_client.py` | Yelp Business Search API integration |
| `scout_critic.py` | Quality scorer — rates each source's output 0–10 |

---

## Data Contract

**What Scout saves per company (same for ALL sources):**

| Field | Google Maps | Yelp | Directory/Tavily | Notes |
|---|---|---|---|---|
| `name` | ✅ | ✅ | ✅ | Required — dropped if missing |
| `industry` | ✅ mapped | ✅ mapped | ✅ classified | Phase B: LLM infers if unknown |
| `city` | ✅ | ✅ | ✅ | Optional |
| `state` | ✅ 2-letter | ✅ 2-letter | ✅ extracted | Used for electricity rate |
| `website` | ✅ | ❌ Yelp never returns | ✅ | Yelp limitation — by design |
| `employee_count` | ✅ crawled | ❌ no website | ✅ crawled | Yelp always NULL → Analyst handles |
| `site_count` | ✅ crawled | ❌ no website | ✅ crawled | Yelp always NULL → Analyst handles |
| `phone` | ✅ optional | ✅ optional | ✅ optional | Optional |
| `status` | `'new'` | `'new'` | `'new'` | Analyst targets new/enriched |

---

## Source Ranking (learning)

At run start, Scout reads `source_performance` table and tries the best source first:
```sql
SELECT source_name, avg_quality_score
FROM source_performance
WHERE industry = :industry AND location = :location
ORDER BY avg_quality_score DESC
```

After each run, writes back quality score (website present=5pts, city=3pts, phone=2pts).
After 3+ runs, Scout automatically tries the highest-performing source first.

---

## LLM Usage (Phase B)

- **Provider:** Ollama llama3.2 (local, free) or OpenAI GPT-4o-mini
- **Calls per Scout run:** 3 (query planner + deduplicator + quality check)
- **Tokens per run:** ~300
- **Cost with Ollama:** $0
- **Cost with GPT-4o-mini:** ~$0.00045 per run

---

## Blocklist

27 domains that require login or are paywalled are skipped immediately:
glassdoor, linkedin, zoominfo, seamless.ai, and others.
Defined in `search_client.py` as `_UNSCRAPPABLE_DOMAINS`.
This saves 60–90 seconds per run by not attempting sites that always fail.
