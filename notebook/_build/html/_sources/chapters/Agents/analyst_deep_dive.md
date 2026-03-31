# Analyst Agent

## Tech Stack Used

| Tech | Purpose |
|---|---|
| **LangChain** (`langchain_core.messages.HumanMessage`) | LLM calls in `llm_inspector.py` |
| **Ollama / OpenAI** | LLM provider via `LLM_PROVIDER` env var |
| **Apollo API** (`api.apollo.io`) | Company enrichment (employee count) + contact finding |
| **Hunter API** | Contact/email finding for decision-makers |
| **SQLAlchemy ORM** | All DB reads/writes — `Company`, `CompanyFeature`, `LeadScore`, `Contact`, `AgentRunLog` |
| **JSON seed file** (`industry_benchmarks.json`) | Benchmark data for spend estimation — loaded once, cached in memory |
| **Python `requests`** | HTTP calls to Apollo + Hunter APIs |

---

## File-by-File Breakdown

### 1. `agents/analyst/analyst_agent.py` — Coordinator

**Entry point:** `run(company_ids, db_session, run_id, on_progress)` at line 75

Loops over each company ID, calls `process_one_company()`, tracks progress via `on_progress` callback (used by UI for live updates), writes to `agent_run_logs` after each company.

**Full pipeline per company — `process_one_company()` at line 176:**

```
1. gather_company_data()        → enrichment loop (crawl → Apollo → LLM → re-enrich)
2. spend_calculator             → utility + telecom spend estimates
3. savings_calculator           → low/mid/high savings range
4. score_engine.compute_score() → 0–100 composite score
5. score_engine.assign_tier()   → high / medium / low
6. llm_inspector.generate_score_narrative() → 1-sentence human explanation
7. save_features()              → writes CompanyFeature row
8. save_score()                 → writes LeadScore row
9. company.status = "scored"    → updates Company row
```

---

### 2. `agents/analyst/analyst_agent.py` — `gather_company_data()` at line 279

**Agentic concept: Adaptive Re-enrichment Loop**

This is the intelligent data-gathering phase. It doesn't just crawl once — it inspects what's missing and decides whether to try again:

```
Step 1: website_crawler.crawl_company_site()    ← only if site_count or employee_count missing
Step 2: enrichment_client.enrich_company_data() ← Apollo API fallback if employee_count still 0
Step 3: llm_inspector.inspect_company()         ← LLM decides: "score_now" OR "enrich_before_scoring"
Step 4: Re-enrichment loop (max 2 attempts)     ← only if LLM says action="enrich_before_scoring"
```

**LLM is skipped entirely** if `industry` is known AND `employee_count > 0` AND `site_count > 0` — no tokens wasted when data is already complete.

---

### 3. `agents/analyst/llm_inspector.py` — Two LLM Jobs

**Agentic concept:** LLM as Data Quality Judge + Narrative Generator

**Job 1 — `inspect_company()` at line 81:**

- Sends company name, website, industry, employee count, site count, and crawled text excerpt (600 chars) to LLM via **LangChain `HumanMessage`**
- LLM returns structured JSON:

```json
{
  "inferred_industry": "healthcare",
  "data_gaps": ["employee_count"],
  "action": "enrich_before_scoring",
  "confidence": "high"
}
```

- If `inferred_industry` is returned and DB value was `"unknown"`, it overwrites it
- `action = "enrich_before_scoring"` triggers the re-enrichment loop in `gather_company_data()`
- Falls back to `{"action": "score_now", "confidence": "low"}` on any LLM failure

**Job 2 — `generate_score_narrative()` at line 183:**

- Sends score, tier, savings estimate, industry, employee count, sites, state, deregulated flag to LLM
- LLM writes a single sentence (max 25 words) explaining why this company scored the way it did
- Example output: *"5-site healthcare group in NY's deregulated market with $420k in recoverable utility savings."*
- Falls back to `_fallback_narrative()` (rule-based template) if LLM fails

Both use **LangChain `HumanMessage`** → Ollama or OpenAI via `_call_llm()` at line 38.

---

### 4. `agents/analyst/enrichment_client.py` — Apollo + Hunter

**Two jobs:**

**`enrich_company_data(domain)` at line 64 — Apollo organization enrichment:**
- `POST https://api.apollo.io/api/v1/organizations/enrich` with `{"domain": "example.com"}`
- Returns `employee_count`, `city`, `state`
- Silently returns `{}` if `APOLLO_API_KEY` missing or domain unknown

**`find_contacts(company_name, domain, db)` — Hunter + Apollo people search:**
- Targets decision-maker titles: CFO, VP Finance, Director of Facilities, Energy Manager, etc.
- Title priority ranking: CFO=1 → VP Finance=2 → Director of Facilities=3 → VP Operations=4
- Module-level flags `_hunter_blocked` / `_apollo_blocked` skip providers for the rest of the run if rate-limited

---

### 5. `agents/analyst/spend_calculator.py` — Spend Estimation

**No LLM. Pure math from benchmark data.**

```python
utility_spend = site_count × avg_sqft_per_site × kwh_per_sqft_per_year × electricity_rate
telecom_spend = employee_count × telecom_per_employee
total_spend   = utility_spend + telecom_spend
```

Key functions:

| Function | Line | Purpose |
|---|---|---|
| `calculate_utility_spend(site_count, industry, state)` | 13 | Site count × sqft × kWh × rate |
| `calculate_telecom_spend(employee_count, industry)` | 25 | Employee count × telecom benchmark |
| `calculate_total_spend(utility, telecom)` | 32 | Sums both |

All benchmark values come from `benchmarks_loader.get_benchmark(industry, state)`.

---

### 6. `agents/analyst/benchmarks_loader.py` — Benchmark Data

- Loads `database/seed_data/industry_benchmarks.json` **once** at startup, caches in `_BENCHMARKS_CACHE`
- `get_benchmark(industry, state)` at line 34 — returns `avg_sqft_per_site`, `kwh_per_sqft_per_year`, `telecom_per_employee`, `electricity_rate`
- `get_electricity_rate(state)` at line 65 — state-level $/kWh rates; defaults to `0.12` if state unknown
- `refresh_benchmarks()` at line 74 — clears cache to force reload (used in tests)

---

### 7. `agents/analyst/savings_calculator.py` — Savings Range

**Three-bracket estimate from total spend:**

| Bracket | Rate | Formula |
|---|---|---|
| Low | 10% | `total_spend × 0.10` |
| Mid | 13.5% | `total_spend × 0.135` |
| High | 17% | `total_spend × 0.17` |

`calculate_tb_revenue(savings_mid)` — multiplies `savings_mid × TB_CONTINGENCY_FEE` (default 24%) to get Troy & Banks expected revenue.

---

### 8. `agents/analyst/score_engine.py` — Composite Scoring

**`compute_score()` at line 38 — weighted 0–100 formula:**

| Component | Max Points | Driver |
|---|---|---|
| Recovery (savings_mid) | 40 pts | ≥$2M=100pts, ≥$1M=85, ≥$500k=70, ≥$250k=55, below=40 |
| Industry fit | 25 pts | healthcare/hospitality/manufacturing/retail=90, public_sector/office=70, unknown=45 |
| Multi-site | 20 pts | ≥20 sites=20, ≥10=17, ≥5=13, ≥2=8, 1 site=3 |
| Data quality | 15 pts | 0–10 score → mapped to 1/4/8/12/15 pts |

Weights are configurable via `settings.SCORE_WEIGHT_RECOVERY`, `SCORE_WEIGHT_INDUSTRY`, etc.

**`assign_tier()` at line 61:**

| Score | Tier |
|---|---|
| ≥ `HIGH_SCORE_THRESHOLD` | `high` |
| ≥ `MEDIUM_SCORE_THRESHOLD` | `medium` |
| Below | `low` |

**`assess_data_quality()` at line 106 — 0–10 quality signal:**

| Signal | Points |
|---|---|
| Has website | +2 |
| Has locations page | +2 |
| site_count > 0 | +2 |
| employee_count > 0 | +2 |
| Contact found in DB | +2 |

---

## Key Agentic Concepts Used

| Concept | Tool / Tech | Where |
|---|---|---|
| Adaptive Re-enrichment Loop | `website_crawler` + Apollo API + LLM | `gather_company_data()` — loops up to 2x |
| LLM as Data Quality Judge | LangChain + Ollama/OpenAI | `llm_inspector.inspect_company()` |
| LLM Narrative Generation | LangChain + Ollama/OpenAI | `llm_inspector.generate_score_narrative()` |
| Benchmark-driven Spend Estimation | JSON seed file + `benchmarks_loader` | `spend_calculator.py` |
| Contact Targeting by Title Priority | Apollo + Hunter APIs | `enrichment_client.find_contacts()` |
| Progress Streaming | `on_progress` callback → UI | `analyst_agent.run()` |

---

## What Gets Written to DB

| Table | Written by | Contents |
|---|---|---|
| `company_features` | `save_features()` | site_count, utility_spend, telecom_spend, savings low/mid/high, industry_fit_score, deregulated_state, data_quality_score |
| `lead_scores` | `save_score()` | score (0–100), tier, score_reason (LLM narrative), `approved_human=False` |
| `companies` | `process_one_company()` | status → `"scored"` |
| `contacts` | `enrichment_client.find_contacts()` | decision-maker emails from Hunter/Apollo |
| `agent_run_logs` | `_log_action()` | per-company action log for UI |

---

## Full Data Flow

```
run(company_ids)
  └─ for each company_id:
       process_one_company()
         │
         ├─ gather_company_data()
         │    ├─ website_crawler.crawl_company_site()    ← reuses Scout's crawler
         │    ├─ enrichment_client.enrich_company_data() ← Apollo API (employee_count)
         │    ├─ llm_inspector.inspect_company()         ← LangChain → Ollama/OpenAI
         │    └─ re-enrichment loop (max 2x) if LLM says "enrich_before_scoring"
         │
         ├─ spend_calculator.calculate_utility_spend()   ← benchmark JSON × site_count
         ├─ spend_calculator.calculate_telecom_spend()   ← benchmark JSON × employee_count
         ├─ savings_calculator.calculate_all_savings()   ← 10% / 13.5% / 17% of total_spend
         │
         ├─ score_engine.compute_score()                 ← weighted 4-component formula
         ├─ score_engine.assign_tier()                   ← high / medium / low
         │
         ├─ llm_inspector.generate_score_narrative()     ← LangChain → 1-sentence explanation
         │
         ├─ save_features()  → CompanyFeature DB row
         ├─ save_score()     → LeadScore DB row
         └─ company.status = "scored"
```
