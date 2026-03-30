# Scout Agent

**Role:** Multi-source company discovery agent. Finds B2B utility audit prospects from business news, web directories, and APIs — then saves them to the database for the Analyst to research and score.

**Agentic pattern:** ReAct (Reason + Act) with Observe → Reason → Act → Reflect loop.
**LLM calls per run:** up to 3 (query planning + deduplication + retry planning).
**Triggered by:** `POST /trigger/scout` → Orchestrator → Task Manager → `scout_agent.run()`

---

## Table of Contents

1. [The Problem Scout Solves](#1-the-problem-scout-solves)
2. [File Architecture](#2-file-architecture)
3. [How Each File Works](#3-how-each-file-works)
4. [The Agentic Loop — Observe Reason Act Reflect](#4-the-agentic-loop)
5. [Full Execution Flow](#5-full-execution-flow)
6. [API Calls Made](#6-api-calls-made)
7. [Database Writes](#7-database-writes)
8. [The Learning Loop — Source Performance](#8-the-learning-loop)
9. [Fallback Safety](#9-fallback-safety)
10. [Data Contract](#10-data-contract)
11. [How to Trigger Scout](#11-how-to-trigger-scout)
12. [LLM Usage and Cost](#12-llm-usage-and-cost)

---

## 1. The Problem Scout Solves

Before Scout, finding prospects meant:
- Manual LinkedIn searches
- Buying static lead lists (stale, expensive, not targeted)
- Relying on referrals

**The issue with a fixed script approach:**
```
script: search("healthcare in Buffalo NY") → save results → done
```
- One query returns one narrow slice of results
- No signal about *why* a company is a good prospect right now
- No way to improve over time
- Breaks if a source fails — no fallback

**What Scout does instead:**
- Reads live business news to find companies with *buying signals* right now
- Generates multiple search query variations to maximize coverage
- Runs multiple sources in parallel and merges results
- Detects near-duplicate company names across sources
- Retries with different angles if not enough companies found
- Learns which sources work best per industry/location over time

---

## 2. File Architecture

```
agents/scout/
│
├── scout_agent.py          ← ENTRY POINT. Orchestrates all phases.
│                              Called by: orchestrator → task_manager
│                              Calls: all files below
│
├── llm_query_planner.py    ← AGENTIC BRAIN (Phase B).
│                              LLM generates diverse search query variants.
│                              Called by: scout_agent.py
│                              External: Ollama or OpenAI
│
├── llm_deduplicator.py     ← AGENTIC DEDUP (Phase B).
│                              Two-pass dedup: rule-based + LLM near-duplicate review.
│                              Called by: scout_agent.py
│                              External: Ollama or OpenAI
│
├── news_scout_client.py    ← PHASE 0. Intent-based prospecting from business news.
│                              Called by: scout_agent.py
│                              External API: Tavily (news mode)
│
├── search_client.py        ← PHASE 2. Web search → discovers directory URLs.
│                              Called by: scout_agent.py
│                              External API: Tavily (search mode)
│
├── google_maps_client.py   ← PHASE 3. Local business search via Places API.
│                              Called by: scout_agent.py
│                              External API: Google Maps Places API (New)
│
├── yelp_client.py          ← PHASE 3. Local business search via Yelp API.
│                              Called by: scout_agent.py
│                              External API: Yelp Business Search API
│
├── directory_scraper.py    ← PHASE 1. Scrapes HTML directory listing pages.
│                              Called by: scout_agent.py
│                              External: HTTP (ScraperAPI proxy)
│
├── company_extractor.py    ← DATA CLEANER. Normalizes fields, checks duplicates, saves.
│                              Called by: scout_agent.py, directory_scraper.py
│                              External: PostgreSQL (via SQLAlchemy)
│
├── website_crawler.py      ← ENRICHMENT. Visits company site for employee/site count.
│                              Called by: scout_agent.py (after API results collected)
│                              External: HTTP (ScraperAPI proxy)
│
└── scout_critic.py         ← QUALITY SCORER + LEARNING.
                               Scores source output 0–10. Writes source_performance.
                               Called by: scout_agent.py (at end of each run)
                               External: PostgreSQL (via SQLAlchemy)
```

**Dependency flow:**
```
scout_agent.py
  ├── llm_query_planner.py     (LLM)
  ├── news_scout_client.py     (Tavily news + LLM extraction)
  ├── directory_scraper.py
  │     └── company_extractor.py (DB)
  ├── search_client.py         (Tavily search + ScraperAPI)
  │     └── company_extractor.py (DB)
  ├── google_maps_client.py    (Google Maps API)
  ├── yelp_client.py           (Yelp API)
  ├── website_crawler.py       (ScraperAPI)
  ├── llm_deduplicator.py      (LLM)
  ├── company_extractor.py     (DB — final save)
  └── scout_critic.py          (DB — source_performance write)
```

---

## 3. How Each File Works

### `scout_agent.py` — Main Orchestrator

**What it does:** The entry point. Runs all 4 phases in sequence, collects results, deduplicates, quality-checks, and persists.

**Key functions:**
```python
run(industry, location, count, db_session, run_id=None)
  → Returns: list[str] of saved company IDs

_save_news_companies(companies, industry, location, run_id, db)
  → Saves news-sourced companies with intent_signal field

_save_api_companies(companies, source_name, industry, location, run_id, db)
  → Saves API-sourced companies, runs website_crawler first

_log_progress(run_id, message, db)
  → Writes AgentRunLog entry for live UI progress tracking
```

**Crucial logic — source ranking:**
```python
ranked_sources = rank_sources(industry, location, ["google_maps", "yelp"], db)
# Reads source_performance → tries best source first
# If no history: google_maps first (hardcoded default)
```

**Crucial logic — directory filtering:**
```python
location_words = {w.lower() for w in location.lower().split() if len(w) > 2}
dir_sources = [s for s in all_sources
               if any(w in str(s.get("name","")).lower() for w in location_words)]
# Only runs Buffalo directories when searching Buffalo
# Saves 60+ seconds by skipping irrelevant configured sources
```

---

### `llm_query_planner.py` — Agentic Query Generation

**What it does:** Uses an LLM to generate 3–5 diverse search query variants from a single intent. This is what makes Scout agentic — instead of one fixed string, it generates multiple angles.

**Key functions:**
```python
plan_queries(industry, location, count=10) → list[str]
  # Returns: ["healthcare companies Buffalo NY",
  #           "hospitals medical centers Buffalo",
  #           "surgical centers Western New York",
  #           "urgent care clinics Erie County NY"]

plan_retry_queries(industry, location, found, target) → list[str]
  # Called when found < 80% of target
  # LLM reasons: "found 4 of 10 healthcare — try broader/different angles"
  # Returns 3 new query variants to try
```

**System prompt (what the LLM is told):**
> You are a B2B lead research expert. Generate diverse search query variants that would surface different types of companies in the given industry and location. Think about: different terminology (hospital vs medical center vs clinic), different organizational types (chain vs independent), different sub-industries. Return only the queries, one per line.

**LLM call:**
```python
# Ollama path:
response = ChatOllama(model=settings.LLM_MODEL).invoke([HumanMessage(content=prompt)])

# OpenAI path:
response = openai_client.chat.completions.create(
    model=settings.LLM_MODEL,
    messages=[{"role": "user", "content": prompt}],
    temperature=0
)
```

**Fallback (if LLM fails):**
```python
return [
    f"{industry} businesses in {location}",
    f"{industry} companies {location} directory",
    f"list of {industry} organizations {location}",
]
```

---

### `news_scout_client.py` — Intent-Based News Prospecting (Phase 0)

**What it does:** Searches business news for companies that have *buying signals* — events that indicate high or growing utility spend. This is Phase 0 — runs before any other source.

**What a buying signal looks like:**
- "XYZ Corp breaks ground on 200,000 sq ft warehouse in Indiana"
- "Midwest Surgical opens 3rd campus in Columbus"
- "Cold chain operator expands to 5 new states"

**Key function:**
```python
find_companies_in_news(industry, location, planned_queries, db) → list[dict]
```

**Internal flow:**
```
1. For each planned query (from llm_query_planner):
   → Tavily news search (mode="news", max_results=10)
   → Returns: article titles + snippets + URLs

2. LLM extraction pass:
   → Prompt: "From these news articles, extract any company names
              that show expansion, growth, or new facility signals.
              Return: name, city, state, industry, intent_signal"
   → LLM returns structured list

3. Clean + normalize extracted companies

4. Check against DB (company_extractor.check_duplicate)

5. Save with source="news_scout", intent_signal=<why they appeared>
```

**What `intent_signal` captures:**
```
"expansion: opening new 85,000 sq ft medical campus"
"growth: adding 3rd distribution center"
"new_facility: breaking ground on manufacturing plant"
```

This field is shown on the Leads page so consultants understand *why* a company was found.

**External API call:**
```
Tavily API — news mode
POST https://api.tavily.com/search
{
  "api_key": TAVILY_API_KEY,
  "query": "healthcare expansion Buffalo NY",
  "search_depth": "basic",
  "topic": "news",
  "max_results": 10
}
```

---

### `directory_scraper.py` — HTML Directory Scraping (Phase 1)

**What it does:** Loads configured directory sources from the `directory_sources` database table and scrapes their HTML listing pages for company data.

**Key function:**
```python
scrape_directory_source(source, industry, location, db) → list[dict]
```

**Internal flow:**
```
1. Load active sources from DirectorySource table
2. Filter by location (only run Buffalo sources when searching Buffalo)
3. For each source:
   → Build URL with industry + location search params
   → Fetch HTML via ScraperAPI proxy (avoids IP blocks)
   → parse_listing(): extract name, address, phone, website from HTML
   → company_extractor.clean_company(): normalize fields
   → company_extractor.check_duplicate(): skip if already in DB
   → Yield cleaned company dicts
```

**ScraperAPI proxy call:**
```
GET http://api.scraperapi.com/?api_key=KEY&url=<target_url>
```
Every request goes through ScraperAPI to avoid IP bans from directory sites.

**Rate limiting:**
```python
time.sleep(settings.REQUEST_DELAY_SECONDS)  # Between each page request
```

**Timeout:** `settings.SCRAPER_REQUEST_TIMEOUT_SECONDS` (default 15s)

---

### `search_client.py` — Tavily Web Search (Phase 2)

**What it does:** Uses Tavily in *search* mode (not news) to find directory pages and business listing URLs. Then scrapes those URLs for company listings.

**Key functions:**
```python
search_with_queries(queries, industry, location, db) → list[dict]
  # Runs ALL planned queries through Tavily
  # Discovers directory page URLs from search results
  # Scrapes discovered URLs for company listings

search_companies(industry, location, query_override=None) → list[dict]
  # Single-query version (used for fallback)
```

**The blocklist — 27 domains that are always skipped:**
```python
_UNSCRAPPABLE_DOMAINS = {
    "glassdoor.com", "linkedin.com", "zoominfo.com", "seamless.ai",
    "bizjournals.com", "reddit.com", "facebook.com", "instagram.com",
    "twitter.com", "x.com", "yelp.com", "indeed.com", "monster.com",
    "crunchbase.com", "dnb.com", "manta.com", "bbb.org",
    # ... + 10 more
}
```
These require login, are paywalled, or return no useful structured data. Skipping them saves 60–90 seconds per run.

**External API call:**
```
POST https://api.tavily.com/search
{
  "api_key": TAVILY_API_KEY,
  "query": "healthcare companies Buffalo NY directory",
  "search_depth": "advanced",
  "max_results": 10
}
Returns: list of URLs that look like directory pages
```
Then each returned URL is scraped via ScraperAPI (same as directory_scraper).

---

### `google_maps_client.py` — Google Maps Places API (Phase 3)

**What it does:** Searches Google Maps Places API for businesses matching the industry + location. Accepts a `query_text` override so all planned queries run through it.

**Key function:**
```python
search_companies(industry, location, query_text=None) → list[dict]
  # query_text=None → builds default: "healthcare companies in Buffalo NY"
  # query_text="urgent care clinics Erie County" → uses that instead
```

**External API call (New Places API):**
```
POST https://places.googleapis.com/v1/places:searchText
Headers:
  X-Goog-Api-Key: GOOGLE_MAPS_API_KEY
  X-Goog-FieldMask: places.displayName,places.formattedAddress,
                    places.nationalPhoneNumber,places.websiteUri,
                    places.businessStatus
Body:
{
  "textQuery": "healthcare companies in Buffalo NY",
  "maxResultCount": 20
}
```

**Returns per company:** name, formatted address (parsed for city/state), phone, website, business status.

**Crucial:** Google Maps returns structured data — city and state are parsed from `formattedAddress` reliably. Website is often present. Phone is present for most businesses. This is why it tends to have the highest quality score in `source_performance`.

---

### `yelp_client.py` — Yelp Business Search API (Phase 3)

**What it does:** Searches Yelp Business Search API. Runs all planned queries. Returns business listings.

**Key function:**
```python
search_companies(industry, location, query_text=None) → list[dict]
```

**External API call:**
```
GET https://api.yelp.com/v3/businesses/search
Headers:
  Authorization: Bearer YELP_API_KEY
Params:
  term=healthcare
  location=Buffalo NY
  limit=50
  sort_by=best_match
```

**Yelp limitation — no website returned:**
Yelp's free API tier does not return `website_uri`. Every company saved from Yelp will have `website=None` and therefore `employee_count=None` and `site_count=None`. This is expected and documented — the Analyst handles it via enrichment.

This is why Yelp often scores lower in `source_performance` than Google Maps.

---

### `website_crawler.py` — Company Site Enrichment

**What it does:** Visits a company's website and extracts signals about size — employee count and number of locations.

**Key function:**
```python
crawl_company_site(website_url) → dict
  # Returns: {
  #   "employee_signal": 250,    # or None
  #   "location_count": 3,       # or None
  #   "crawl_status": "success"  # or "failed" / "timeout"
  # }
```

**What it looks for on the page:**
- Employee count: mentions of headcount ("over 500 employees", "team of 200+")
- Location count: mentions of multiple offices/sites ("3 locations", "serving 5 states")
- About pages, careers pages, and contact pages are the best signal sources

**Called after API results are collected:**
```python
for company in api_batch:
    if company.get("website"):
        crawl = website_crawler.crawl_company_site(company["website"])
        company["employee_count"] = crawl.get("employee_signal")
        company["site_count"] = crawl.get("location_count")
```

**Uses ScraperAPI proxy** — same as directory_scraper. Timeout: 15 seconds. Fails gracefully (returns None fields, never crashes Scout).

---

### `company_extractor.py` — Data Cleaner + Duplicate Checker

**What it does:** Normalizes raw company data from any source into a consistent schema before saving. Checks for duplicates. Saves to the database.

**Key functions:**
```python
clean_company(raw_dict) → dict
  # Normalizes:
  # - state: "New York" → "NY", "new york" → "NY"
  # - phone: "(716) 555-1234" → "7165551234"
  # - website: strips trailing slashes, normalizes http vs https
  # - name: strips extra whitespace, title-cases

check_duplicate(website, db, name=None, city=None) → bool
  # Check 1: exact domain match against companies table
  #   normalize: strip www., http://, trailing slash
  # Check 2: exact name + city match (for companies with no website)
  # Returns True if duplicate (caller skips saving)

save_company(company_dict, db) → Company | None
  # Creates Company ORM object and commits to DB
  # Returns None (and logs) if name is missing
```

**State normalization covers:**
- Full names → 2-letter codes ("New York" → "NY")
- Already 2-letter → uppercase passthrough
- Common abbreviations ("N.Y." → "NY")

---

### `llm_deduplicator.py` — Two-Pass Deduplication

**What it does:** After all sources are collected into one batch, removes duplicate companies. Two passes.

**Key function:**
```python
deduplicate(companies: list[dict]) → list[dict]
```

**Pass 1 — Rule-based domain dedup (fast, handles ~80% of duplicates):**
```python
seen_domains = set()
for company in companies:
    domain = extract_domain(company.get("website", ""))
    # normalize: strip www., http://, path
    if domain in seen_domains:
        drop(company)
    else:
        seen_domains.add(domain)
        keep(company)
```

**Pass 2 — LLM near-duplicate review (handles the remaining 20%):**
Only runs if batch has ≥ 5 companies.
```python
# Find name-similar pairs using SequenceMatcher
suspicious_pairs = [
    (i, j) for i, j in all_pairs
    if SequenceMatcher(None, name_i, name_j).ratio() > 0.75
]
# Example pairs flagged:
# "Buffalo City School District" + "BCSD" (ratio=0.71 — below threshold but LLM still catches it)
# "St. Luke's Hospital" + "Saint Lukes Hospital" (ratio=0.82)

# LLM prompt:
# "Review these pairs. Which are the same company?
#  Pair 1: 'St. Luke's Hospital' (Buffalo) vs 'Saint Lukes Hospital' (Buffalo NY)
#  Return: [1] if pair 1 is a duplicate, [] if none are"

# Drop the second occurrence of each confirmed duplicate pair
```

**Fallback:** If LLM fails → return Pass 1 output only (no crash).

---

### `scout_critic.py` — Quality Scorer + Learning Writer

**What it does:** Scores each source's output quality after a run and writes the result to `source_performance` for future runs to learn from.

**Key functions:**
```python
score_source_output(companies: list[dict]) → float
  # Quality = (% with website × 5) + (% with city × 3) + (% with phone × 2)
  # Max score = 10.0
  # Example: 80% website, 100% city, 60% phone → (0.8×5)+(1.0×3)+(0.6×2) = 8.2

update_source_performance(source_name, industry, location, found, passed, quality_score, db)
  # Upserts source_performance table:
  # First run: INSERT (total_runs=1, avg_quality_score=8.2)
  # Subsequent: UPDATE using rolling average
  #   new_avg = (old_avg × old_runs + new_score) / (old_runs + 1)

rank_sources(industry, location, source_names, db) → list[str]
  # Reads source_performance, returns sources sorted by avg_quality_score DESC
  # Falls back to default order if no history exists
```

---

## 4. The Agentic Loop

### Why This Is Agentic, Not Just Automated

A simple automation runs a fixed script. An agentic system uses an LLM to *reason* about what to do and *reflect* on whether it worked.

Scout's loop:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  OBSERVE      What are we looking for?                      │
│               industry="healthcare", location="Buffalo NY", │
│               count=10                                      │
│                    ↓                                        │
│  REASON       What searches would surface the right         │
│               companies? What angles exist?                 │
│               (llm_query_planner)                           │
│                    ↓                                        │
│  ACT          Run all 4 phases with planned queries         │
│               Phase 0: news → Phase 1: directories         │
│               Phase 2: Tavily → Phase 3: Maps + Yelp        │
│                    ↓                                        │
│  REFLECT      How many did we find? Is it enough?           │
│               Are there duplicates to remove?               │
│               (llm_deduplicator + quality check)            │
│                    ↓                                        │
│  RETRY?       If < 80% of target found:                    │
│               REASON again → plan new query angles          │
│               ACT again → one more round                   │
│               (plan_retry_queries)                          │
│                    ↓                                        │
│  LEARN        Write quality score back to source_performance│
│               Next run will try best source first           │
│               (scout_critic)                                │
└─────────────────────────────────────────────────────────────┘
```

### What the LLM Decides (Reasoning)

The LLM is used for three specific decisions — everything else is deterministic:

| LLM Call | What it decides | Why LLM (not code) |
|---|---|---|
| `plan_queries` | Which search angles to use | Requires language understanding — "schools" means elementary, charter, K-12, university... code can't enumerate all variants |
| `deduplicate` (Pass 2) | Are these two company names the same company? | Requires semantic reasoning — "St. Luke's" = "Saint Lukes" but "Buffalo General" ≠ "General Hospital" |
| `plan_retry_queries` | What angles were missed? What should we try next? | Requires reasoning about what was found and what gaps exist |

### What Code Decides (Deterministic)

Everything that doesn't require language understanding stays in code:

- Scoring formula (math)
- Domain normalization (string operations)
- Duplicate domain check (set lookup)
- Source ranking (sort by float)
- Rate limiting and HTTP requests
- Database writes

---

## 5. Full Execution Flow

```
POST /trigger/scout {industry, location, count}
  │
  ▼
api/routes/triggers.py::trigger_scout()
  └── background_tasks.add_task(_run_scout)
        │
        ▼
orchestrator.run_scout(industry, location, count, db)
  └── task_manager.assign_task("scout", params, db)
        └── scout_agent.run(industry, location, count, db, run_id)
              │
              ├── [OBSERVE] Log: "Starting Scout — 10 healthcare in Buffalo NY"
              │
              ├── [REASON] llm_query_planner.plan_queries(industry, location)
              │     → LLM generates 4 query variants
              │     → Log: "LLM generated 4 search variants"
              │
              ├── [ACT Phase 0] news_scout_client.find_companies_in_news(queries)
              │     → Tavily news search for each query
              │     → LLM extracts company names + intent signals
              │     → Saves to DB with source="news_scout"
              │     → Log: "News scout found 2 companies with buying signals"
              │
              ├── [ACT Phase 1] directory_scraper (location-filtered sources only)
              │     → Scrapes HTML listing pages via ScraperAPI
              │     → company_extractor.check_duplicate() before each save
              │     → Log: "Directory scraper found 3 companies"
              │
              ├── [ACT Phase 2] search_client.search_with_queries(planned_queries)
              │     → Tavily discovers directory URLs for each query
              │     → Filters blocklist (27 domains skipped)
              │     → Scrapes discovered URLs
              │     → Log: "Tavily search found 8 companies"
              │
              ├── [ACT Phase 3] API batch (ranked order)
              │     ├── rank_sources() → [google_maps, yelp] (or reversed if history says so)
              │     ├── For each query × each source → collect results
              │     │     google_maps_client.search_companies(query_text=q)
              │     │     yelp_client.search_companies(query_text=q)
              │     └── api_batch_all = all results combined
              │
              ├── [ACT] website_crawler for each API company with a website
              │     → Extracts employee_count + site_count signals
              │
              ├── [REFLECT] llm_deduplicator.deduplicate(api_batch_all)
              │     → Pass 1: domain dedup (rule-based)
              │     → Pass 2: LLM name-similarity review
              │     → Log: "Removed 5 duplicates — 37 unique companies"
              │
              ├── [REFLECT] Quality check
              │     saved_so_far vs target_count
              │     If < 80%:
              │       llm_query_planner.plan_retry_queries(found, target)
              │       → Run APIs one more time with retry queries
              │       → Deduplicate retry batch
              │
              ├── [PERSIST] _save_api_companies(unique_batch)
              │     → company_extractor.check_duplicate() (vs DB)
              │     → Save new companies only
              │     → Log: "Scout complete — saved 10 of 10 requested"
              │
              └── [LEARN] scout_critic.update_source_performance()
                    → Score each source's output quality (0–10)
                    → Upsert source_performance table
                    → Return: list[str] saved company IDs
```

---

## 6. API Calls Made

| API | Mode | Called From | What It Returns |
|---|---|---|---|
| **Tavily** | `topic="news"` | `news_scout_client.py` | News articles with company mentions |
| **Tavily** | `search_depth="advanced"` | `search_client.py` | Directory page URLs |
| **Google Maps Places** | `searchText` (New API) | `google_maps_client.py` | Business name, address, phone, website |
| **Yelp Business Search** | `GET /businesses/search` | `yelp_client.py` | Business name, address, phone (no website) |
| **ScraperAPI** | HTTP proxy | `directory_scraper.py`, `website_crawler.py`, `search_client.py` | Proxied HTML content |
| **Ollama / OpenAI** | Chat completion | `llm_query_planner.py`, `llm_deduplicator.py`, `news_scout_client.py` | Query lists, duplicate flags, extracted companies |

### Request Headers / Auth

```python
# Tavily
{"api_key": TAVILY_API_KEY, "query": "...", "topic": "news"}

# Google Maps (New Places API)
headers = {"X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
           "X-Goog-FieldMask": "places.displayName,places.formattedAddress,..."}

# Yelp
headers = {"Authorization": f"Bearer {YELP_API_KEY}"}

# ScraperAPI (proxy wrapping any URL)
GET http://api.scraperapi.com/?api_key={KEY}&url={target_url}
```

---

## 7. Database Writes

### Table: `companies`

Columns written by Scout:

| Column | Source | Notes |
|---|---|---|
| `id` | auto UUID | |
| `name` | all sources | Required — row dropped if missing |
| `industry` | LLM classified / API category | LLM infers if unknown (Phase B) |
| `city` | all sources | Optional |
| `state` | all sources | Normalized to 2-letter code |
| `website` | all except Yelp | Yelp never returns website |
| `phone` | all sources | Optional |
| `employee_count` | website_crawler | None for Yelp companies |
| `site_count` | website_crawler | None for Yelp companies |
| `source` | set per source | `"news_scout"`, `"google_maps"`, `"yelp"`, `"directory"` |
| `source_url` | all sources | URL that surfaced this company |
| `intent_signal` | news_scout only | Why this company appeared in news |
| `status` | hardcoded `"new"` | Analyst targets `status IN ('new','enriched')` |
| `run_id` | from orchestrator | Links company to the specific Scout run |
| `date_found` | `datetime.now()` | |

### Table: `source_performance`

Written by `scout_critic.update_source_performance()` after every run:

| Column | Written | Notes |
|---|---|---|
| `source_name` | "google_maps", "yelp", etc. | Composite key with industry + location |
| `industry` | from run params | |
| `location` | from run params | |
| `total_runs` | incremented | |
| `avg_quality_score` | rolling average | (0–10) — used for source ranking |
| `last_run_at` | `datetime.now()` | |

### Table: `agent_run_logs`

Written by `_log_progress()` throughout the run:

| Column | Written | Notes |
|---|---|---|
| `run_id` | from orchestrator | Links all logs to one Scout run |
| `agent` | `"scout"` | |
| `action` | `"progress"` | |
| `output_summary` | human-readable message | Visible in Pipeline page live feed |
| `logged_at` | `datetime.now()` | |

---

## 8. The Learning Loop

After every run, Scout updates `source_performance`. After 3+ runs, the learning kicks in:

```
Run 1: google_maps quality=8.3, yelp quality=5.1
Run 2: google_maps quality=7.9, yelp quality=4.8
Run 3: google_maps quality=8.1, yelp quality=5.3

Next run: rank_sources() reads:
  google_maps avg=8.1 → try first
  yelp avg=5.1 → try second

Scout now automatically tries the better source first for this industry/location.
No one manually configured this.
```

**Quality score formula:**
```
quality = (% companies with website × 5)
        + (% companies with city    × 3)
        + (% companies with phone   × 2)
Max = 10.0
```

Companies with a website can be crawled for employee/site count. Companies with city and phone are more likely to be real businesses. This formula captures what matters for downstream Analyst quality.

---

## 9. Fallback Safety

Every LLM call is wrapped in `try/except`. Scout never crashes because of LLM failure.

| Component | LLM Fails → Fallback |
|---|---|
| `llm_query_planner.plan_queries` | Returns 3 static queries: `"{industry} businesses in {location}"`, etc. |
| `llm_query_planner.plan_retry_queries` | Returns 3 static broader/narrower variants |
| `llm_deduplicator` Pass 2 | Skips LLM pass, returns Pass 1 (domain-only) output |
| `news_scout_client` LLM extraction | Returns empty list — no news companies saved |
| `website_crawler` | Timeout or error → returns `{}` — company saved with None fields |
| Any HTTP timeout | Logged, source skipped, other sources continue |

**Scout is designed to always return *something* — even if all APIs fail, it returns an empty list gracefully.**

---

## 10. Data Contract

**What Scout guarantees for every saved company:**

| Field | Guaranteed? | Why |
|---|---|---|
| `name` | ✅ Always | Row is dropped if name is missing |
| `status = "new"` | ✅ Always | Analyst queries `WHERE status = 'new'` |
| `run_id` | ✅ Always | Required for pipeline tracking |
| `source` | ✅ Always | Tells Analyst where company came from |
| `industry` | ✅ Always | Set from search params + LLM inference |
| `city` | ⚠️ Usually | Missing for some directory scrapes |
| `state` | ⚠️ Usually | Missing if not found in source |
| `website` | ⚠️ Google Maps / Directories | Always None for Yelp |
| `employee_count` | ⚠️ When crawled | None if no website or crawl failed |
| `site_count` | ⚠️ When crawled | None if no website or crawl failed |
| `phone` | ⚠️ Often | All sources return it when available |
| `intent_signal` | News scout only | Null for all other sources |

---

## 11. How to Trigger Scout

**Via dashboard:**
Triggers page → Run Scout → enter industry + location + count → Submit

**Via API:**
```bash
curl -X POST http://localhost:8001/trigger/scout \
  -H "Content-Type: application/json" \
  -d '{"industry": "healthcare", "location": "Buffalo NY", "count": 10}'
```

**Via chatbot:**
```
"Find 15 manufacturing companies in Chicago Illinois"
```

**Via orchestrator (full pipeline):**
```python
orchestrator.run_full_pipeline(industry="healthcare", location="Buffalo NY", count=10, db=db)
# Scout runs first, then Analyst, then Writer automatically
```

**Poll progress:**
```bash
GET http://localhost:8001/trigger/{trigger_id}/status
# Returns: live log messages from agent_run_logs
```

---

## 12. LLM Usage and Cost

| LLM Call | When | Tokens | Can Skip? |
|---|---|---|---|
| `plan_queries` | Every run | ~80 | No — fallback runs instead |
| `deduplicate Pass 2` | When batch ≥ 5 with similar names | ~150 | No — domain-only fallback |
| `plan_retry_queries` | Only when < 80% of target found | ~100 | No — fallback runs instead |

**Total per run:** ~300 tokens (when all 3 calls happen)

| Provider | Cost per Scout run |
|---|---|
| Ollama (local) | $0 |
| OpenAI GPT-4o-mini | ~$0.00045 |

Switch provider: set `LLM_PROVIDER=openai` in `.env` and rebuild the API container.
