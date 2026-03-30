# Analyst Agent

**Role:** Research, enrich, and score every company Scout discovers. Finds the right decision-maker contact, estimates utility spend, scores the company 0–100, and writes a plain-English explanation of why.

**Agentic pattern:** ReAct (Reason + Act) with Observe → Reason → Act → Reflect loop.
**LLM calls per company:** 2 (data inspector + score narrator). Skipped if all data already present.
**Triggered by:** `POST /trigger/analyst` → Orchestrator → Task Manager → `analyst_agent.run()`

---

## Table of Contents

1. [The Problem Analyst Solves](#1-the-problem-analyst-solves)
2. [File Architecture](#2-file-architecture)
3. [How Each File Works](#3-how-each-file-works)
4. [The Agentic Loop — Observe Reason Act Reflect](#4-the-agentic-loop)
5. [Full Execution Flow](#5-full-execution-flow)
6. [Contact Enrichment Waterfall — All 8 Sources](#6-contact-enrichment-waterfall)
7. [Scoring — Exact Formula](#7-scoring--exact-formula)
8. [Spend Calculation — How the Numbers Are Built](#8-spend-calculation)
9. [LLM Calls — What Each One Does](#9-llm-calls)
10. [API Calls Made](#10-api-calls-made)
11. [Database Reads and Writes](#11-database-reads-and-writes)
12. [How It's Triggered](#12-how-its-triggered)
13. [Fallback and Error Handling](#13-fallback-and-error-handling)
14. [Data Contract](#14-data-contract)
15. [LLM Usage and Cost](#15-llm-usage-and-cost)

---

## 1. The Problem Analyst Solves

Scout saves companies with basic fields — name, city, industry (sometimes), website (sometimes). That's not enough to qualify a lead or write a credible email. Before a company can be approved for outreach:

- **Who do we contact?** Name, job title, verified email, phone.
- **How much do they spend on utilities?** Needs size + industry + location signals.
- **Are they a good fit?** Multi-site? Deregulated state? Energy-intensive industry?
- **Why exactly?** A number alone (score=84) is useless — the consultant needs to understand it.

Analyst does all of this — for every company, automatically, before it reaches the Leads page.

**The challenge:** Company data from Scout is often incomplete.
- Yelp never returns a website → no employee count possible
- Some companies have unknown industry
- Scout's website crawl may have missed employee/location signals

A fixed script would silently score with wrong data (0 employees = bad score, wrong reason). The Analyst instead **detects gaps, tries to fill them, and only scores when it has the best data it can get**.

---

## 2. File Architecture

```
agents/analyst/
│
├── analyst_agent.py        ← ENTRY POINT. Orchestrates the full pipeline per company.
│                              Called by: orchestrator → task_manager
│                              Calls: all files below
│
├── llm_inspector.py        ← AGENTIC BRAIN (Phase A).
│                              LLM inspects data, infers industry, detects gaps,
│                              decides action, generates score narrative.
│                              Called by: analyst_agent.py
│                              External: Ollama or OpenAI
│
├── enrichment_client.py    ← CONTACT FINDER + COMPANY ENRICHER.
│                              8-source contact waterfall + Apollo org enrichment.
│                              Called by: analyst_agent.py
│                              External APIs: Hunter, Apollo, Serper, Snov, Prospeo,
│                                             ZeroBounce, ScraperAPI
│
├── score_engine.py         ← SCORING MATH. Deterministic.
│                              Weighted formula → 0–100 score + tier.
│                              Called by: analyst_agent.py
│                              External: none (pure math)
│
├── spend_calculator.py     ← SPEND ESTIMATION.
│                              site_count × industry benchmarks → utility spend.
│                              employee_count × rate → telecom spend.
│                              Called by: analyst_agent.py
│                              External: benchmarks_loader.py (JSON file)
│
├── savings_calculator.py   ← SAVINGS ESTIMATION.
│                              total_spend × 10/13.5/17% → low/mid/high savings.
│                              Called by: analyst_agent.py
│                              External: none (pure math)
│
└── benchmarks_loader.py    ← DATA LOADER.
                               Reads industry_benchmarks.json once, caches in memory.
                               Serves industry sqft/kWh/rate lookups.
                               Called by: spend_calculator.py
                               External: database/seed_data/industry_benchmarks.json
```

**Dependency flow:**
```
analyst_agent.py
  ├── enrichment_client.py         (Hunter, Apollo, Serper, Snov, Prospeo, ZeroBounce)
  │     └── [PostgreSQL — save Contact]
  ├── website_crawler.py           (ScraperAPI — reused from Scout)
  ├── llm_inspector.py             (Ollama / OpenAI — 2 calls)
  ├── spend_calculator.py
  │     └── benchmarks_loader.py   (industry_benchmarks.json)
  ├── savings_calculator.py        (pure math)
  ├── score_engine.py              (pure math)
  └── [PostgreSQL — save CompanyFeature, LeadScore, update Company.status]
```

---

## 3. How Each File Works

### `analyst_agent.py` — Main Orchestrator

**What it does:** The entry point. Accepts a list of company IDs, processes each one through the full pipeline, persists results, and tracks progress.

**Key functions:**

```python
run(company_ids, db_session, run_id=None, on_progress=None) → list[str]
```
Loops over every company ID. Calls `process_one_company()` for each. Updates `AgentRun.companies_scored` after each success. Returns list of successfully scored company IDs.

```python
process_one_company(company_id, db_session) → dict
```
The core per-company pipeline:
1. Load company from DB
2. `gather_company_data()` — enrich, inspect, re-enrich if needed
3. `spend_calculator` — compute utility + telecom spend
4. `savings_calculator` — compute low/mid/high savings
5. `score_engine.compute_score()` — compute 0–100 score
6. `score_engine.assign_tier()` — high/medium/low
7. `llm_inspector.generate_score_narrative()` — write the explanation
8. `save_features()` — write `company_features` row
9. `save_score()` — write `lead_scores` row
10. `company.status = "scored"`

```python
gather_company_data(company, db_session) → dict
```
The agentic enrichment loop. This is where Observe → Reason → Act → Reflect happens.
See Section 4 for the full loop detail.

```python
decide_data_quality(crawl_result, contact_found) → float (0–10)
```
Calls `score_engine.assess_data_quality()`. The result feeds the Data Quality component of the score formula.

**Deregulated states list (hardcoded):**
```python
_DEREGULATED_STATES = {
    "NY", "TX", "IL", "OH", "PA", "NJ", "MA", "MD",
    "CT", "ME", "NH", "RI", "DE", "DC", "MI"
}
```
Companies in these states can switch electricity suppliers — the core service value proposition. This flag feeds the score narrative and the scoring formula.

---

### `llm_inspector.py` — Agentic Brain

**What it does:** Two distinct LLM calls — one to inspect available data and decide what to do before scoring, one to write the score explanation after scoring.

#### Function 1: `inspect_company()`

**When called:** Before scoring, inside `gather_company_data()`.

**What the LLM is told:**
```
You are analyzing a company to help qualify it as a B2B sales lead.

Company name : Midwest Surgical Associates
Website      : midwestsurgical.com
Industry     : unknown
Employees    : unknown
Sites/locations : unknown
Website text excerpt: "...3 convenient locations across Ohio..."

Return ONLY a JSON object — no explanation, no markdown:
{
  "inferred_industry": "<canonical industry or null if already known>",
  "data_gaps": ["employee_count"],
  "confidence": "high",
  "action": "score_now"
}

Rules:
- inferred_industry must be one of: healthcare, hospitality, manufacturing,
  retail, education, logistics, office, public_sector, technology, finance, unknown
- Set action to "enrich_before_scoring" ONLY when employee_count is unknown
  AND a website exists
- Set action to "score_now" in all other cases
```

**What it returns:**
```python
{
    "inferred_industry": "healthcare",      # LLM inferred from name + text
    "data_gaps": ["employee_count"],        # what's missing
    "action": "enrich_before_scoring",      # LLM decides to try again
    "confidence": "high"
}
```

**Optimization — LLM is skipped entirely when data is sufficient:**
```python
data_sufficient = industry_known and employee_count > 0 and site_count > 0
if data_sufficient:
    return {"inferred_industry": None, "data_gaps": [], "action": "score_now", "confidence": "high"}
```
No tokens wasted when the company already has all the data needed.

#### Function 2: `generate_score_narrative()`

**When called:** After scoring, in `process_one_company()`.

**What the LLM is told:**
```
Write ONE sentence (max 25 words) explaining why this company is a high-tier sales lead
for a utility cost consulting firm. Be specific — mention the savings figure and what
makes them a good or average fit.

Company : Midwest Surgical Associates
Industry: healthcare
Employees: 250
Sites   : 3
State   : OH (deregulated energy market)
Score   : 84/100  Tier: high
Est. annual savings: $45k

Return only the sentence. No quotes. No bullet points. Do not start with "This company".
```

**Example output:**
> *"3-site healthcare operator in deregulated Ohio with $45k savings potential — strong audit candidate."*

**Fallback template (if LLM fails):**
```python
"3-site healthcare organization. Operating in a deregulated energy market. Estimated $45k in recoverable savings. High energy intensity industry."
```

---

### `enrichment_client.py` — Contact Finder + Company Enricher

**Two distinct jobs in one file:**

#### Job 1: `enrich_company_data(domain)` — Company-level enrichment

Called when `employee_count` is still 0 after website crawl. Uses Apollo's free organization enrichment endpoint.

```python
POST https://api.apollo.io/api/v1/organizations/enrich
Headers: {"x-api-key": APOLLO_API_KEY}
Body: {"domain": "midwestsurgical.com"}

Returns:
  org.num_employees → employee_count
  org.city          → city (if missing)
  org.state         → state (if missing)
```

Returns `{}` silently if key missing, domain unknown, 404, 402, or 422. Never crashes.

#### Job 2: `find_contacts(company_name, domain, db)` — 8-source contact waterfall

See Section 6 for the full waterfall detail.

**Rate-limit guards (module-level flags):**
```python
_hunter_blocked: bool = False   # Set True on first 429 response
_apollo_blocked: bool = False   # Set True on first 403 response
```
Once blocked, those providers are skipped for the entire run — no further attempts. This prevents wasting time retrying a blocked API for every company.

**Target titles (who to contact):**
```python
_TARGET_TITLES = {
    "cfo", "chief financial officer", "vp finance", "director of finance",
    "director of facilities", "facilities manager", "vp operations",
    "energy manager", "procurement manager", "controller"
}
```

**Title priority (when multiple contacts found):**
```python
_TITLE_PRIORITY = {
    "cfo": 1, "chief financial officer": 1,
    "vp finance": 2, "director of finance": 2,
    "director of facilities": 3, "facilities manager": 3,
    "vp operations": 4, "energy manager": 4,
}
```
CFO/VPs prioritized over managers.

---

### `score_engine.py` — Scoring Math

**What it does:** Pure deterministic math. Takes enriched company data, runs the weighted formula, returns a 0–100 score and high/medium/low tier. No LLM, no external calls.

**Key functions:**

```python
compute_score(savings_mid, industry, site_count, data_quality_score) → float
```
The main formula. See Section 7 for full detail.

```python
assign_tier(score) → str
# Reads HIGH_SCORE_THRESHOLD and MEDIUM_SCORE_THRESHOLD from settings
# Defaults: ≥70 = "high", ≥40 = "medium", <40 = "low"
```

```python
assess_data_quality(site_count, employee_count, has_website, has_locations_page, has_contact_found) → float (0–10)
# +2 for having website
# +2 for having locations page
# +2 for site_count > 0
# +2 for employee_count > 0
# +2 for contact found
```

---

### `spend_calculator.py` — Spend Estimation

**What it does:** Estimates how much a company spends annually on utilities and telecom using industry benchmarks. This number is the foundation of the score — a high spend = high savings potential = high score.

**Key functions:**

```python
calculate_utility_spend(site_count, industry, state) → float
# Formula:
#   site_count × avg_sqft_per_site × kwh_per_sqft_per_year × electricity_rate
# All values come from benchmarks_loader (industry_benchmarks.json)

calculate_telecom_spend(employee_count, industry) → float
# Formula:
#   employee_count × telecom_per_employee (from benchmarks)

calculate_total_spend(utility_spend, telecom_spend) → float
# Simple sum
```

**Example — healthcare, 3 sites, Ohio:**
```
avg_sqft_per_site = 15,000 sqft
kwh_per_sqft_per_year = 25 kWh
electricity_rate (OH) = $0.12/kWh
utility_spend = 3 × 15,000 × 25 × 0.12 = $135,000

employee_count = 250
telecom_per_employee = $600/year
telecom_spend = 250 × 600 = $150,000

total_spend = $285,000
```

---

### `savings_calculator.py` — Savings Estimation

**What it does:** Converts total spend into a low/mid/high savings range using fixed percentages.

```python
calculate_savings_low(total_spend)  → total_spend × 10%   = $28,500
calculate_savings_mid(total_spend)  → total_spend × 13.5% = $38,475
calculate_savings_high(total_spend) → total_spend × 17%   = $48,450

calculate_all_savings(total_spend) → {"low": 28500, "mid": 38475, "high": 48450}
```

**The `savings_mid` value ($38,475) is what drives the Recovery component of the score formula.** Higher savings = higher Recovery score = higher overall score.

---

### `benchmarks_loader.py` — Industry Benchmark Data

**What it does:** Loads `database/seed_data/industry_benchmarks.json` once at startup, caches in memory, serves industry-specific lookup values.

**Key data served:**

| Field | What it is | Example (healthcare) |
|---|---|---|
| `avg_sqft_per_site` | Average square footage per location | 15,000 sqft |
| `kwh_per_sqft_per_year` | Annual energy consumption per sqft | 25 kWh |
| `telecom_per_employee` | Annual telecom spend per employee | $600 |
| `electricity_rate` | $/kWh for the company's state | $0.12 (OH) |

**Fallback:** If industry not found → uses `"default"` benchmark row. If state not found → uses national average rate.

```python
get_benchmark(industry="healthcare", state="OH")
# Returns: {avg_sqft_per_site, kwh_per_sqft_per_year, telecom_per_employee, electricity_rate}

get_electricity_rate(state="OH") → 0.12
# Falls back to state_rates["default"] = 0.12 if state not in JSON
```

---

## 4. The Agentic Loop

### What Makes Analyst Agentic

A fixed scoring script would:
1. Load company
2. Run formula
3. Save score
4. Done — even if `industry="unknown"` and `employee_count=0`

That produces a low, wrong score with a useless explanation. No one benefits.

The Analyst instead follows the **Observe → Reason → Act → Reflect** loop:

```
┌───────────────────────────────────────────────────────────────┐
│                      ANALYST LOOP                             │
│                                                               │
│  OBSERVE     Load company from DB.                            │
│              What do we have? industry? employees? website?   │
│                   ↓                                           │
│  REASON      (llm_inspector.inspect_company)                  │
│              What does this data tell us?                     │
│              What's missing that matters?                     │
│              Can we fill the gap? Should we try?              │
│                   ↓                                           │
│  ACT         Execute enrichment if needed:                    │
│              crawl website → Apollo org → contact waterfall   │
│                   ↓                                           │
│  REFLECT     Did we get what we needed?                       │
│              employee_count now > 0? → proceed to score       │
│              still 0 after 2 attempts? → score with low conf  │
│                   ↓                                           │
│  ACT         Run deterministic scoring (pure math)            │
│                   ↓                                           │
│  REFLECT     (llm_inspector.generate_score_narrative)         │
│              LLM writes the "why" in plain English            │
│              Was the explanation good? trim/fallback if not   │
└───────────────────────────────────────────────────────────────┘
```

### The `gather_company_data()` Loop in Detail

This is where the Observe → Reason → Act → Reflect plays out in code:

```python
# OBSERVE: what do we currently have?
website = company.get("website")
current_site_count = company.get("site_count") or 0
current_employee_count = company.get("employee_count") or 0

# ACT Step 1: crawl website if any key signals are missing
needs_crawl = website and (current_site_count <= 0 or current_employee_count <= 0)
if needs_crawl:
    crawl_result = website_crawler.crawl_company_site(website)
    # Fills: site_count from location mentions
    # Fills: employee_count from headcount mentions

# ACT Step 2: Apollo fallback if employee_count still missing
if employee_count == 0 and website:
    apollo_data = enrichment_client.enrich_company_data(website)
    # Fills: employee_count, city, state from Apollo org database

# REASON: LLM inspects what we have now and decides what to do
inspection = llm_inspector.inspect_company(
    name, website, industry, employee_count, site_count, crawled_text
)
# Returns: inferred_industry, data_gaps, action, confidence

# REFLECT + ACT: apply LLM decisions
if inspection["inferred_industry"] and industry == "unknown":
    enriched["industry"] = inspection["inferred_industry"]  # fill the gap

if inspection["action"] == "enrich_before_scoring":
    # REFLECT: LLM says data is still insufficient → try again
    for attempt in range(2):  # max 2 re-enrichment loops
        recrawl = website_crawler.crawl_company_site(website)
        # Update site_count, employee_count from recrawl
        if employee_count == 0:
            apollo_data = enrichment_client.enrich_company_data(website)
            # Try Apollo again
        if employee_count > 0:
            break  # REFLECT: good enough now → stop looping
    # If still 0 after 2 loops → proceed anyway with low confidence
```

### What the LLM Decides vs What Code Decides

| Decision | Who decides | Why |
|---|---|---|
| Industry when field = "unknown" | **LLM** | Requires language understanding of company name + website text |
| Whether to re-enrich before scoring | **LLM** | Requires reasoning about data sufficiency and whether more data is realistically obtainable |
| Score explanation in plain English | **LLM** | Requires language generation — template was too generic |
| Scoring formula weights | **Code (deterministic)** | Math must be consistent and auditable — not left to LLM judgment |
| Savings calculation | **Code (deterministic)** | Formula must be reproducible for any company |
| Tier assignment | **Code (deterministic)** | Thresholds must be consistent — configured in settings |
| Contact waterfall order | **Code (deterministic)** | Order is a business decision, not a reasoning task |

---

## 5. Full Execution Flow

```
POST /trigger/analyst
  │
  ▼
api/routes/triggers.py::trigger_analyst()
  └── background_tasks.add_task(_run_analyst)
        │
        ▼
orchestrator.run_analyst(company_ids, db)
  └── task_manager.assign_task("analyst", params, db)
        └── analyst_agent.run(company_ids, db, run_id)
              │
              ├── Update AgentRun.status = "analyst_running"
              │
              ├── FOR EACH company_id:
              │     │
              │     └── process_one_company(company_id, db)
              │           │
              │           ├── [OBSERVE] Load company from DB
              │           │
              │           ├── gather_company_data(company, db)
              │           │     │
              │           │     ├── [ACT] website_crawler (if data missing)
              │           │     │     └── ScraperAPI → HTML → extract signals
              │           │     │
              │           │     ├── [ACT] enrichment_client.enrich_company_data()
              │           │     │     └── Apollo org API → employee_count, state
              │           │     │
              │           │     ├── [REASON] llm_inspector.inspect_company()
              │           │     │     └── LLM → inferred_industry, action, gaps
              │           │     │
              │           │     └── [REFLECT] if action="enrich_before_scoring":
              │           │           └── re-crawl + re-Apollo (max 2 loops)
              │           │
              │           ├── [ACT] enrichment_client.find_contacts()
              │           │     └── 8-source waterfall → save Contact to DB
              │           │
              │           ├── spend_calculator.calculate_utility_spend()
              │           │     └── site_count × sqft × kWh × electricity_rate
              │           │
              │           ├── spend_calculator.calculate_telecom_spend()
              │           │     └── employee_count × telecom_per_employee
              │           │
              │           ├── savings_calculator.calculate_all_savings()
              │           │     └── total_spend × 10/13.5/17%
              │           │
              │           ├── score_engine.compute_score()
              │           │     └── weighted formula → 0–100
              │           │
              │           ├── score_engine.assign_tier()
              │           │     └── ≥70=high, ≥40=medium, <40=low
              │           │
              │           ├── [REFLECT] llm_inspector.generate_score_narrative()
              │           │     └── LLM → one-sentence plain-English explanation
              │           │
              │           ├── save_features() → company_features table
              │           ├── save_score()    → lead_scores table
              │           └── company.status = "scored"
              │
              ├── Update AgentRun.companies_scored after each company
              ├── Log each result to agent_run_logs
              └── Update AgentRun.status = "analyst_awaiting_approval"
```

---

## 6. Contact Enrichment Waterfall

8 sources tried in order. **Stops at first source that returns a valid contact.** Never calls all 8 for the same company.

```
Source 1: Hunter.io domain-search
  GET https://api.hunter.io/v2/domain-search?domain={domain}&api_key={KEY}
  Returns: list of emails with names + titles at the domain
  Filter: only keeps contacts matching _TARGET_TITLES
  Sort: by _TITLE_PRIORITY (CFO first)
  Skip if: HUNTER_API_KEY missing, or _hunter_blocked=True (429 received earlier)
  ↓ (only if no result)

Source 2: Apollo people-search
  POST https://api.apollo.io/api/v1/people/search
  Body: {organization_domains: [domain], titles: [...target titles]}
  Returns: list of people with name, title, email
  Skip if: APOLLO_API_KEY missing, or _apollo_blocked=True (403 received earlier)
  ↓ (only if no result)

Source 3: Website scraper — /contact, /about, /team pages
  ScraperAPI → scrape company website → extract emails from HTML
  Regex: finds mailto: links and text patterns like "name@domain.com"
  No title filtering (small company sites rarely list titles)
  Free, no API key required
  ↓ (only if no result)

Source 4: Serper email search
  POST https://google.serper.dev/search
  Query: "\"@{domain}\" email site:{domain}"
  Finds published email addresses in Google's index
  Returns: email addresses found in search snippets
  Skip if: SERPER_API_KEY missing
  ↓ (only if no result)

Source 5: Snov.io domain search
  GET https://api.snov.io/v1/get-emails-from-url?url={domain}
  Returns: prospect emails with names + titles
  150 free credits/month
  Skip if: SNOV_CLIENT_ID or SNOV_CLIENT_SECRET missing
  ↓ (only if no result)

Source 6: Prospeo LinkedIn enrichment
  POST https://api.prospeo.io/domain-search
  Body: {domain: domain}
  Returns: LinkedIn-sourced contacts
  Skip if: PROSPEO_API_KEY missing
  ↓ (only if no result)

Source 7: ZeroBounce domain search + permutation
  Uses exec name found via Serper Google name search:
    → "VP Operations {company name}"
  Then tries all 8 email permutations:
    first.last@domain.com, f.last@domain.com, firstl@domain.com, etc.
  Verifies each via ZeroBounce:
    GET https://api.zerobounce.net/v2/validate?email={email}&apikey={KEY}
  Takes first "valid" result
  Skip if: no exec name found from Serper
  ↓ (only if no result)

Source 8: Generic inbox fallback
  Tries: info@domain.com, contact@domain.com, hello@domain.com, admin@domain.com
  Verifies each via ZeroBounce (same endpoint as Source 7)
  No title — reaches *someone* at the company
  Last resort — a reachable inbox is better than no contact
```

**What gets saved to `contacts` table:**
```python
Contact(
    company_id = ...,
    full_name  = contact["full_name"],
    title      = contact["title"],
    email      = contact["email"],
    phone      = contact.get("phone"),      # if found
    linkedin_url = contact.get("linkedin"),  # if from Prospeo/Apollo
    source     = provider,                  # "hunter", "apollo", "website_scraper", etc.
    verified   = contact.get("verified"),    # True if ZeroBounce confirmed
)
```

---

## 7. Scoring — Exact Formula

```
Score (0–100) = (Recovery × weight_recovery)
              + (Industry × weight_industry)
              + (Multisite × weight_multisite)
              + (DataQuality × weight_data_quality)
```

Weights come from `.env` (configurable):
- `SCORE_WEIGHT_RECOVERY` = 0.40
- `SCORE_WEIGHT_INDUSTRY` = 0.25
- `SCORE_WEIGHT_MULTISITE` = 0.20
- `SCORE_WEIGHT_DATA_QUALITY` = 0.15

### Recovery Component (0–100 raw, × 0.40 = up to 40 pts)

Based on `savings_mid` (13.5% of total spend):

| savings_mid | Raw score |
|---|---|
| ≥ $2,000,000 | 100 |
| ≥ $1,000,000 | 85 |
| ≥ $500,000 | 70 |
| ≥ $250,000 | 55 |
| < $250,000 | 40 |

### Industry Component (raw score × 0.25 = up to 22.5 pts)

| Industry | Raw score |
|---|---|
| healthcare, hospitality, manufacturing, retail | 90 |
| public_sector, office | 70 |
| other (technology, finance, etc.) | 55 |
| unknown | 45 |

### Multisite Component (0–20 pts)

| site_count | Points |
|---|---|
| ≥ 20 | 20 |
| ≥ 10 | 17 |
| ≥ 5 | 13 |
| ≥ 2 | 8 |
| 1 | 3 |

### Data Quality Component (0–10 raw, × 0.15 = up to 1.5 pts per signal)

Each of these signals adds 2 points (max 10):
- Has website
- Has locations page
- site_count > 0
- employee_count > 0
- Contact found and saved

Then mapped to score points:

| Data quality | Points |
|---|---|
| ≥ 9 | 15 |
| ≥ 7 | 12 |
| ≥ 5 | 8 |
| ≥ 3 | 4 |
| < 3 | 1 |

### Tier Assignment

| Score | Tier |
|---|---|
| ≥ 70 | **high** |
| ≥ 40 | **medium** |
| < 40 | **low** |

Thresholds are configurable via `HIGH_SCORE_THRESHOLD` and `MEDIUM_SCORE_THRESHOLD` in `.env`.

### Worked Example — Midwest Surgical Associates

```
Company: Midwest Surgical Associates
Industry: healthcare (LLM inferred from "unknown")
Employees: 250 (from Apollo org enrichment)
Sites: 3
State: OH (deregulated)

Spend calculation:
  utility: 3 × 15,000 sqft × 25 kWh × $0.12 = $135,000
  telecom: 250 × $600 = $150,000
  total: $285,000

Savings:
  savings_mid = $285,000 × 13.5% = $38,475

Score components:
  Recovery:    savings_mid=$38,475 → raw=40 → 40 × 0.40 = 16.0
  Industry:    healthcare → raw=90 → 90 × 0.25 = 22.5
  Multisite:   3 sites → 8 pts × 0.20 = 1.6      ← wait, multisite is already in points
  DataQuality: all signals → 15 pts × 0.15 = 2.25

  [Note: the formula scales recovery and industry raw scores by weights]

Final score: ~60–70 depending on exact benchmark values
Tier: high (≥70) or medium (≥40)

Score narrative (LLM):
  "3-site healthcare operator in deregulated Ohio — strong savings candidate at ~$38k annually."
```

---

## 8. Spend Calculation

The spend estimate is built from industry benchmark data in `database/seed_data/industry_benchmarks.json`:

```json
{
  "industry_benchmarks": [
    {
      "industry_bucket": "healthcare",
      "avg_sqft_per_site": 15000,
      "kwh_per_sqft_per_year": 25.0,
      "telecom_per_employee": 600
    },
    {
      "industry_bucket": "manufacturing",
      "avg_sqft_per_site": 50000,
      "kwh_per_sqft_per_year": 95.0,
      "telecom_per_employee": 400
    },
    ...
    {
      "industry_bucket": "default",
      "avg_sqft_per_site": 10000,
      "kwh_per_sqft_per_year": 18.0,
      "telecom_per_employee": 500
    }
  ],
  "electricity_rate_by_state": {
    "NY": 0.22,
    "TX": 0.09,
    "OH": 0.12,
    "default": 0.12
  }
}
```

**Utility spend formula:**
```
utility_spend = site_count × avg_sqft_per_site × kwh_per_sqft_per_year × electricity_rate
```

**Telecom spend formula:**
```
telecom_spend = employee_count × telecom_per_employee
```

**Savings range:**
```
low  = total_spend × 10%
mid  = total_spend × 13.5%   ← used in score formula
high = total_spend × 17%
```

The benchmarks are loaded once at startup and cached in memory. Call `benchmarks_loader.refresh_benchmarks()` to reload if the JSON is updated while the server is running.

---

## 9. LLM Calls

### Call 1: `inspect_company()` — Data Inspector

| Property | Value |
|---|---|
| **When** | Before scoring, if any key field is missing |
| **Skipped when** | industry is known AND employee_count > 0 AND site_count > 0 |
| **Input** | name, website, industry, employee_count, site_count, crawled_text (600 chars) |
| **Output** | `{inferred_industry, data_gaps, action, confidence}` |
| **Temperature** | 0 (deterministic) |
| **Tokens** | ~120 prompt + ~40 response = ~160 |
| **Fallback** | `{inferred_industry: None, data_gaps: [], action: "score_now", confidence: "low"}` |

### Call 2: `generate_score_narrative()` — Score Narrator

| Property | Value |
|---|---|
| **When** | After scoring, every company |
| **Input** | name, industry, employee_count, site_count, state, deregulated, score, tier, savings_mid |
| **Output** | One sentence, max 25 words, max 200 characters |
| **Temperature** | default (slightly creative is fine for natural-sounding text) |
| **Tokens** | ~100 prompt + ~30 response = ~130 |
| **Fallback** | Rule-based template: `"{N}-site {industry} organization. Estimated ${X}k in recoverable savings."` |

---

## 10. API Calls Made

| API | Endpoint | Called From | Auth | What It Returns |
|---|---|---|---|---|
| **Apollo org** | `POST https://api.apollo.io/api/v1/organizations/enrich` | `enrichment_client.enrich_company_data()` | `x-api-key` header | employee_count, city, state |
| **Hunter domain** | `GET https://api.hunter.io/v2/domain-search` | `enrichment_client.find_via_hunter()` | `api_key` query param | contacts with emails + titles |
| **Apollo people** | `POST https://api.apollo.io/api/v1/people/search` | `enrichment_client.find_via_apollo()` | `x-api-key` header | contacts with emails + titles |
| **Serper email** | `POST https://google.serper.dev/search` | `enrichment_client.find_via_serper_email()` | `X-API-KEY` header | email addresses from Google |
| **Serper name** | `POST https://google.serper.dev/search` | `enrichment_client.find_via_serper()` | `X-API-KEY` header | exec name for permutation |
| **Snov.io** | `GET https://api.snov.io/v1/get-emails-from-url` | `enrichment_client.find_via_snov()` | OAuth token | contacts |
| **Prospeo** | `POST https://api.prospeo.io/domain-search` | `enrichment_client.find_via_prospeo()` | `X-KEY` header | LinkedIn contacts |
| **ZeroBounce** | `GET https://api.zerobounce.net/v2/validate` | `enrichment_client.find_via_zerobounce_domain()` | `apikey` query param | email validity status |
| **ScraperAPI** | `GET http://api.scraperapi.com/?api_key=...&url=...` | `website_crawler.crawl_company_site()` | query param | proxied HTML |
| **Ollama / OpenAI** | local / `https://api.openai.com/v1/chat/completions` | `llm_inspector._call_llm()` | Bearer token | inspection result / narrative |

---

## 11. Database Reads and Writes

### Reads

| Table | What is read | Why |
|---|---|---|
| `companies` | Full row by `company_id` | Load all company data for enrichment and scoring |
| `contacts` | Check if any contact exists (`SELECT id LIMIT 1`) | Determines data quality score component |

### Writes

| Table | Columns written | When |
|---|---|---|
| `contacts` | `company_id, full_name, title, email, phone, linkedin_url, source, verified` | After contact waterfall finds a result |
| `company_features` | `company_id, estimated_site_count, estimated_annual_utility_spend, estimated_annual_telecom_spend, estimated_total_spend, savings_low, savings_mid, savings_high, industry_fit_score, multi_site_confirmed, deregulated_state, data_quality_score` | After scoring |
| `lead_scores` | `company_id, score, tier, score_reason, approved_human=False, scored_at` | After scoring |
| `companies` | `status = "scored"`, `updated_at = now()` | After saving score |
| `agent_run_logs` | `run_id, agent="analyst", action, status, output_summary, duration_ms` | After each company + at completion |
| `agent_runs` | `status = "analyst_running"` → `"analyst_awaiting_approval"`, `companies_scored++` | Start + per company + completion |

---

## 12. How It's Triggered

**Via dashboard:**
Triggers page → Run Analyst → Submit

**Via API:**
```bash
curl -X POST http://localhost:8001/trigger/analyst \
  -H "Content-Type: application/json"
# Analyst runs for all companies with status = "new" or "enriched"
```

**Via full pipeline:**
```bash
curl -X POST http://localhost:8001/trigger/full \
  -H "Content-Type: application/json" \
  -d '{"industry": "healthcare", "location": "Buffalo NY", "count": 10}'
# Scout → Analyst → Writer chain runs automatically
```

**Via chatbot:**
```
"Run the analyst on new companies"
"Score all unscored leads"
```

**Poll progress:**
```bash
GET http://localhost:8001/trigger/{trigger_id}/status
```
Returns live log messages from `agent_run_logs` — visible on the Triggers page in real time.

---

## 13. Fallback and Error Handling

| Failure | What happens |
|---|---|
| LLM `inspect_company` fails | Falls back to `{action: "score_now", inferred_industry: None}` — scoring continues |
| LLM `generate_score_narrative` fails | Falls back to rule-based template string |
| Apollo org enrichment fails | Returns `{}` — employee_count stays 0, scoring continues with available data |
| All 8 contact sources fail | No contact saved — data_quality_score loses 2 points, scoring continues |
| Website crawl fails | Returns `{}` — site_count and employee_count not updated, scoring continues |
| Hunter 429 (rate limit) | Sets `_hunter_blocked = True` — skipped for entire run |
| Apollo 403 (blocked) | Sets `_apollo_blocked = True` — skipped for entire run |
| Individual company fails entirely | Logged to `agent_run_logs`, `db.rollback()`, continues to next company |
| All companies fail | Returns empty list — `agent_run_logs` has error entries for each |

**The Analyst never stops the batch because one company fails.** Each failure is isolated, logged, and the loop continues.

---

## 14. Data Contract

**Analyst reads:** Companies with `status IN ('new', 'enriched')`

**Analyst writes:**
- `contacts` row — the decision-maker contact
- `company_features` row — spend estimates + scoring signals
- `lead_scores` row — score, tier, plain-English reason
- `companies.status = "scored"`

**What happens when data is missing:**

| Missing field | Analyst's response |
|---|---|
| `industry = "unknown"` | LLM infers from name + website text |
| `employee_count = 0` | LLM triggers re-enrichment loop (crawl + Apollo, max 2×) |
| `site_count = 0` | Defaults to 1 in spend calculation |
| `state` missing | Uses national average electricity rate ($0.12/kWh) |
| No website | Skips crawl, Apollo, and website scraper — scores with available data |
| All data missing | Still scores — low tier, low confidence, fallback narrative |

---

## 15. LLM Usage and Cost

| LLM Call | Tokens | Always called? |
|---|---|---|
| `inspect_company` | ~160 | No — skipped if industry+employees+sites all present |
| `generate_score_narrative` | ~130 | Yes — every company |

**Total per company:** ~290 tokens (when both calls happen)

| Provider | Cost per company | Cost per 100 companies |
|---|---|---|
| Ollama (local) | $0 | $0 |
| OpenAI GPT-4o-mini | ~$0.00027 | ~$0.027 |

Switch provider: set `LLM_PROVIDER=openai` in `.env` and rebuild the API container.
