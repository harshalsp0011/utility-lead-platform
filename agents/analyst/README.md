# Analyst Agent

Scores companies found by Scout and assigns high/medium/low lead tiers.

---

## Current Behavior (rule-based)

```
Load company from DB
  ↓
gather_company_data():
  - crawl website if site_count=0 or employee_count=0
  - Apollo org enrichment if employee_count still 0
  ↓
spend_calculator: site_count × industry benchmark → utility_spend
                  employee_count × rate → telecom_spend
  ↓
savings_calculator: total_spend × 8/15/24% → low/mid/high savings
  ↓
score_engine.compute_score():
  Score = (Recovery×0.40) + (Industry×0.25) + (Multisite×0.20) + (DataQuality×0.15)
  ↓
assign_tier(): ≥70=high, 40–69=medium, <40=low
  ↓
Save: company_features row + lead_scores row
      company.status = "scored"
```

---

## Agentic Upgrade — Phase A

Three LLM reasoning steps added to the pipeline:

### 1. LLM Data Inspector (new: `llm_inspector.py`)

Before scoring, LLM reads all available company data and decides what to do next.

```
Input:  name, website, industry, employee_count, site_count, crawled_text
Output: {
  "inferred_industry": "healthcare",    ← null if industry already known
  "data_gaps": ["employee_count"],      ← what's missing that matters
  "action": "enrich_before_scoring"     ← or "score_now"
}
```

If `action = enrich_before_scoring`:
- Runs re-enrichment (crawl → Apollo → Hunter)
- LLM re-evaluates: "enough now?" → `score_now` or `score_with_low_confidence`
- Max 2 enrichment loops

### 2. Industry Inference

Before this upgrade: `"healthcare"` → 90 pts; `"unknown"` → 45 pts penalty (exact match only).

After: LLM classifies from company name + website text:
- `"Buffalo Surgical Associates"` → `"healthcare"` ✓
- `"WNY Emergency Services"` → `"healthcare"` ✓
- `"Canal Side Hotel"` → `"hospitality"` ✓

Falls back to existing industry if already set and non-unknown.

### 3. LLM Score Narrator (replaces template string)

Before: `"1-site healthcare organization. Estimated $45k in recoverable savings."`

After: LLM generates contextual narrative:
- `"250-employee healthcare company, 3 sites in deregulated NY — strong audit candidate with ~$180k annual savings potential"`
- `"Single-site hospitality business, limited data — moderate audit fit, manual verification recommended"`

---

## Files

| File | Purpose |
|---|---|
| `analyst_agent.py` | Main entry point — orchestrates the full scoring pipeline per company |
| `llm_inspector.py` | **NEW (Phase A)** — LLM-based data inspection, industry inference, gap detection |
| `enrichment_client.py` | Apollo org enrichment (employee_count, state) + Hunter/Apollo contact finding |
| `spend_calculator.py` | Rule-based utility + telecom spend estimates from benchmarks |
| `savings_calculator.py` | Converts total spend to low/mid/high savings ranges |
| `score_engine.py` | Weighted score formula (0–100), tier assignment, data quality scoring |
| `benchmarks_loader.py` | Loads/caches `industry_benchmarks.json`, falls back to `default` |

---

## Score Formula (deterministic — not changed by agentic upgrade)

```
Score = (Recovery × 0.40) + (Industry × 0.25) + (Multisite × 0.20) + (Data Quality × 0.15)
```

| Component | What it measures | Points |
|---|---|---|
| Recovery | Savings potential (utility + telecom spend × 15%) | 0–100 scaled |
| Industry fit | Healthcare/hospitality/manufacturing = best | 45–90 |
| Multisite | More locations = more spend to recover | 3–20 |
| Data quality | Website present, employee count known, contacts found | 1–15 |

---

## Data Contract

Analyst expects companies with `status = 'new'` or `'enriched'`.
Writes: `company_features` row, `lead_scores` row (with `scored_at` timestamp), `company.status = 'scored'`.

If data is missing:
| Missing | Handled by |
|---|---|
| `industry = unknown` | Phase A: LLM infers from name/text |
| `employee_count = 0` | Phase A: LLM triggers re-enrichment loop |
| `site_count = 0` | defaults to 1 in calculations |
| `state` missing | uses national average electricity rate |
| All missing | still scores — low tier, low confidence |

---

## LLM Usage (Phase A)

- **Provider:** Ollama llama3.2 (local, free) or OpenAI GPT-4o-mini (optional)
- **Calls per company:** 2 (inspector + narrator)
- **Tokens per company:** ~180
- **Cost with Ollama:** $0
- **Cost with GPT-4o-mini:** ~$0.00027 per company
