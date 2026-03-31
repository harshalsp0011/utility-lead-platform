# Scout Agent

## Tech Stack Used

| Tech | Purpose |
|---|---|
| **LangChain** (`langchain_core.messages.HumanMessage`) | Wraps LLM calls in all 3 LLM modules |
| **Ollama / OpenAI** | LLM provider (configured via `LLM_PROVIDER` env var) |
| **Tavily API** | Web search + news search (HTTP `requests.post`) |
| **Google Places API v1** | `places:searchText` endpoint |
| **Yelp Business Search API** | Via `yelp_client.py` |
| **BeautifulSoup4** | HTML parsing in `directory_scraper.py` |
| **SQLAlchemy ORM** | All DB reads/writes (`Session`, `Company`, `SourcePerformance`, `DirectorySource`) |
| **Python `requests`** | HTTP calls to all external APIs and web pages |
| **`difflib.SequenceMatcher`** | Name similarity scoring in `llm_deduplicator.py` |
| **`functools.lru_cache`** | Memoizes Tavily search results in `search_client.py` |

---

## File-by-File Breakdown

### 1. `agents/scout/scout_agent.py` — Coordinator / Orchestrator

**Entry point:** `run(industry, location, count, db_session, run_id)` at line 75

This is a **sequential multi-source loop** — not a graph, not an async pipeline. Pure Python `for` loops with early-exit:

```python
if len(saved_ids) >= count: break
```

Writes live progress to `agent_run_logs` table via `_log_progress()` at line 38 — that's what the UI polls for the live status feed.

---

### 2. `agents/scout/llm_query_planner.py` — LLM Query Generation

**Agentic concept:** Dynamic Query Planning

- `plan_queries(industry, location)` at line 106 — sends prompt to LLM via **LangChain's `HumanMessage`**, asks for a JSON array of 4 search queries
- `plan_retry_queries(...)` at line 154 — called only if <80% of target found; sends what was already tried so LLM avoids repetition
- `_call_llm(prompt)` at line 28 — branches on `LLM_PROVIDER`: Ollama uses `llm.invoke([HumanMessage(...)])`, OpenAI uses raw `chat.completions.create()`
- Falls back to hardcoded queries `_fallback_queries()` at line 80 if LLM fails

---

### 3. `agents/scout/news_scout_client.py` — Intent-Based Lead Discovery

**Agentic concept:** Intent-Based Prospecting

- `find_companies_in_news(industry, location)` at line 254 — public entry point
- `_generate_news_queries()` at line 82 — LLM generates news-specific queries (looks for events, not directories)
- `_search_news(query)` at line 216 — calls **Tavily API** with `"topic": "news"` to get article snippets (not web pages)
- `_extract_companies_from_snippets()` at line 126 — feeds snippets to LLM via **LangChain `HumanMessage`**, LLM extracts company name + signal type (`expansion`, `new_facility`, `cost_pressure`, etc.) + detail as structured JSON
- Returns `intent_signal` field that gets stored in the `Company` DB row

---

### 4. `agents/scout/search_client.py` — Tavily Directory Discovery

- `search_with_queries(queries, location)` at line 163 — takes LLM-planned queries and searches Tavily for *directory URLs* to scrape
- `_cached_tavily_search()` at line 65 — `@lru_cache(maxsize=64)` prevents redundant Tavily calls within same process run
- Filters out **19 known-unscrappable domains** (LinkedIn, Glassdoor, ZoomInfo etc.) via `_UNSCRAPPABLE_DOMAINS` at line 34
- Discovered URLs get saved to `directory_sources` table via `directory_scraper.save_directory_sources()`

---

### 5. `agents/scout/directory_scraper.py` — HTML Scraping with Pagination

- `scrape_directory(url)` at line 30 — **pagination loop**: keeps calling `get_next_page()` until no next page
- `fetch_page(url)` at line 126 — **retry loop** (up to `MAX_RETRIES`), realistic browser headers, optional proxy via `get_proxy_url()`
- `_find_listing_elements(soup)` at line 266 — uses **BeautifulSoup4** to find `<article>`, `<div>`, `<li>` tags with CSS class/id hints like `"listing"`, `"card"`, `"member"`
- `parse_listing(tag)` at line 58 — extracts name (tries `h1-h4`, `[itemprop=name]`, `a[title]`), website (first absolute href), city/category by keyword

---

### 6. `agents/scout/google_maps_client.py` — Google Places API

- `search_companies(industry, location, limit, query_text)` at line 65
- Uses **Google Places API v1** (`places:searchText`) with `X-Goog-FieldMask` header to request only the fields we need
- `query_text` comes from LLM query planner — overrides default query string
- `_map_industry(raw_type, fallback)` at line 161 — maps Google place types (`"hospital"`, `"lodging"` etc.) to our 6-bucket industry taxonomy
- `_parse_city_state(formatted_address)` at line 170 — parses `"123 Main St, Buffalo, NY 14201, USA"` by splitting on commas

---

### 7. `agents/scout/llm_deduplicator.py` — Two-Pass Deduplication

**Agentic concept:** LLM-assisted fuzzy matching

- `deduplicate(companies)` at line 167
- **Pass 1** — exact domain matching using `_extract_domain()` at line 61. Fast, handles ~80% of duplicates
- **Pass 2** — `_find_suspicious_pairs()` at line 75 uses **`difflib.SequenceMatcher`** to find name pairs with similarity ≥ 0.75, then `_ask_llm_which_are_duplicates()` at line 107 sends up to 8 suspicious pairs to LLM in one call asking for a JSON array of which pair numbers are duplicates
- LLM call uses **LangChain `HumanMessage`** same as other modules

---

### 8. `agents/scout/scout_critic.py` — Quality Scoring + Source Learning

- `evaluate_quality(companies)` at line 45 — pure math, no LLM. Scores 0–10 based on `website` (5pts), `city` (3pts), `phone` (2pts) field presence rates
- `update_source_performance(...)` at line 72 — **upsert** to `source_performance` table: rolling average `(old_avg * old_runs + new_score) / (old_runs + 1)`
- `rank_sources(industry, location, sources, db)` at line 132 — SQLAlchemy query on `SourcePerformance` table, sorts by `avg_quality_score` descending. This is the **self-learning loop** — sources that historically perform better get tried first

---

## Execution Phases (`scout_agent.run()`)

```
1. LLM Query Planning     → 3–5 diverse search queries (not hardcoded strings)
2. Source Ranking         → order API sources by past performance from DB
3. Phase 0: News Scout    → finds companies IN THE NEWS with buying signals
4. Phase 1: Directory     → scrapes configured DB sources (Yellow Pages etc.)
5. Phase 2: Tavily        → AI-powered web search using planned queries
6. Phase 3: API Sources   → Google Maps + Yelp, one call per planned query
7. LLM Deduplication      → removes near-duplicates from the API batch
8. Quality Retry          → if <80% of target found, generates NEW queries and retries
9. Source Performance     → writes results back to DB so future runs learn
```

---

## Scout Critic Quality Rubric

After each source, the Critic scores the batch **0.0–10.0**:

| Field | Points |
|---|---|
| Website present | 5.0 |
| City present | 3.0 |
| Phone present | 2.0 |

- Score **≥ 6.0** = good quality
- Score **< 6.0** = try another source

The Critic also writes to the `source_performance` table — a rolling average per `(source, industry, location)`. Next run, `rank_sources()` reads this to put the best-performing source first.

---

## Key Agentic Concepts Used

| Concept | Tool / Tech | Where |
|---|---|---|
| Intent-Based Prospecting | `news_scout_client` | Phase 0 — finds warm leads from news |
| LLM Query Planning | Claude via `llm_query_planner` | Step 1 — diverse query generation |
| Adaptive Source Ranking | `SourcePerformance` DB table | `rank_sources()` — learns over time |
| LLM Deduplication | Claude via `llm_deduplicator` | After API batch collection |
| Quality-gated Retry | `llm_query_planner.plan_retry_queries` | If <80% target hit |
| Website Signal Enrichment | `website_crawler` | Crawls each company's site for employee/location signals |

---

## What Gets Saved

- **News companies**: name + industry minimum (LLM already classified), with `intent_signal` field
- **API companies**: name + industry + city minimum (no website required — Google Maps/Yelp are trusted sources)
- **Directory companies**: must pass `_validate_scraped()` — requires name + website + reachable site

---

## Full Data Flow

```
User request: "find 10 healthcare companies in Rochester NY"
          ↓
llm_query_planner.plan_queries()        ← LangChain → Ollama/OpenAI
          ↓ 4 diverse query strings
scout_critic.rank_sources()             ← SQLAlchemy reads source_performance
          ↓ ordered: [google_maps, yelp] or reversed if yelp historically better
news_scout_client.find_companies_in_news()
  → _generate_news_queries()            ← LangChain → Ollama/OpenAI
  → _search_news() × 3                 ← Tavily API (topic=news)
  → _extract_companies_from_snippets()  ← LangChain → Ollama/OpenAI
  → saved with intent_signal field
          ↓
directory_scraper.scrape_directory()    ← BeautifulSoup4 + requests (paginated)
  → company_extractor.extract_all_fields()
  → website_crawler.crawl_company_site()
          ↓
search_client.search_with_queries()     ← Tavily API (web mode)
  → directory_scraper.scrape_directory() per found URL
          ↓
google_maps_client.search_companies() × 4 queries  ← Google Places API v1
yelp_client.search_companies()                     ← Yelp API
          ↓
llm_deduplicator.deduplicate()
  Pass 1: domain exact match
  Pass 2: SequenceMatcher similarity → LangChain → Ollama/OpenAI
          ↓
If <80% found: llm_query_planner.plan_retry_queries() → retry loop
          ↓
scout_critic.update_source_performance() × per source  ← SQLAlchemy upsert
          ↓
return saved company IDs
```
