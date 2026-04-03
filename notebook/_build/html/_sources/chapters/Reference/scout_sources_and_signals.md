# Scout — Sources, Signals & Intent-Based Prospecting
# Reference Document: How companies are discovered, scored by signal, and prioritised

> Last updated: 2026-03-22

---

## The Core Idea

Most lead generation tools find companies that EXIST in a location.
This platform finds companies that NEED an audit RIGHT NOW.

The difference is **buying signals** — events that tell you a company has a specific,
active reason to care about utility costs today:

| Signal | What happened | Why they need us |
|---|---|---|
| **Expansion** | Opening new location / branch | More sites = higher utility spend incoming |
| **New facility** | Breaking ground / construction | Audit before opening = lock in best rates |
| **Cost pressure** | Budget cuts / rising operating costs | Actively looking for savings |
| **Energy news** | Mentioned utility bills in public | Already thinking about energy costs |
| **Acquisition** | Merged with or acquired another company | Consolidating multiple utility accounts |
| **Hiring surge** | Large headcount growth | More space = more energy |

Companies with signals are **warm leads**. Companies without signals are **cold leads**.
Both are valuable — but signal companies get a scoring boost and priority in the queue.

---

## All Discovery Sources

Scout runs multiple sources in order. Each finds different companies.

```
┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 0 — News Scout (Tavily topic=news)              BUILT ✅      │
│                                                                      │
│  What: Tavily searched in news mode — returns recent articles        │
│  Finds: Companies mentioned in local business news with signals      │
│  LLM role: Extracts company name + signal from article snippets      │
│  Stored as: companies.intent_signal = "expansion: opening new..."    │
│  API cost: 3 calls × $0.01 = ~$0.03 per run                         │
│  Limit: Only finds companies that appeared in covered news           │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 0.5 — SerpAPI (Google full index)               PLANNED 🔲   │
│                                                                      │
│  What: Google's full search index via SerpAPI                        │
│  Finds: Companies in news + press releases + local business pages    │
│         that Tavily misses (different index, wider coverage)         │
│  Search modes used:                                                  │
│    tbm=nws  → Google News tab (recent articles, local journals)      │
│    regular  → Google general results (press releases, company pages) │
│    tbm=lcl  → Google Local (businesses Google knows about)           │
│  LLM role: Extracts company name + signal from search snippets       │
│  API cost: ~$0.001/query (10× cheaper than Tavily)                   │
│  Env var: SERP_API_KEY                                               │
│  Why better than Tavily for news: Google indexes local business      │
│    journals (Buffalo Business First, Democrat & Chronicle, etc.)     │
│    and PRNewswire/BusinessWire press releases directly               │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 1 — Configured Directory Sources                BUILT ✅      │
│                                                                      │
│  What: Pre-saved URLs in directory_sources table                     │
│  Finds: Companies listed on industry directories, chamber sites      │
│  Filter: Location-aware (only tries sources matching the city)       │
│  Currently: 78 Buffalo-specific sources in DB                        │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 2 — Tavily Directory Search                     BUILT ✅      │
│                                                                      │
│  What: Tavily in regular mode — finds directory/listing pages        │
│  Finds: Industry association member lists, "top employers" articles  │
│  LLM role: Query planner generates 4 diverse search queries          │
│  API cost: 4 calls × $0.01 = $0.04 per run                          │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 3 — Google Maps Places API                      BUILT ✅      │
│                                                                      │
│  What: Google Places Text Search API                                 │
│  Finds: Physical businesses — clinics, factories, hotels, schools    │
│  Returns: Name, address, phone, website, business type               │
│  4 queries × up to 20 results each = up to 80 raw before dedup       │
│  API cost: 4 calls × $0.017 = $0.07 per run                          │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  PHASE 3b — Yelp Business API                          BUILT ✅      │
│                                                                      │
│  What: Yelp Business Search API                                      │
│  Finds: Local businesses (especially hospitality, retail, food)      │
│  Limitation: Never returns website URL — so no crawl possible        │
│  Used as: fallback if Google Maps underperforms for this industry    │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  ENRICHMENT (Analyst phase — separate from Scout)      BUILT ✅      │
│                                                                      │
│  Apollo.io: given company domain → returns contact name/email/title  │
│  Used by: Analyst enrichment_client, not Scout                       │
│  Stored in: contacts table                                           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Total API calls per Scout run

| Source | Calls | Cost |
|---|---|---|
| Tavily news (Phase 0) | 3 | ~$0.03 |
| SerpAPI news (Phase 0.5, planned) | 3 | ~$0.003 |
| Tavily directory (Phase 2) | 4 | ~$0.04 |
| Google Maps (Phase 3) | 4 | ~$0.07 |
| **Total (current, no SerpAPI)** | **11** | **~$0.14** |
| **Total (with SerpAPI)** | **14** | **~$0.143** |

Quality retry (if < 80% target found): +4 more Google Maps calls (~$0.07 extra, once)

---

## How intent_signal flows through the pipeline

```
Scout discovers company via news/SerpAPI
         │
         ▼
companies.intent_signal = "expansion: opening 2 new clinics in Monroe County"
         │
         ▼
Analyst reads intent_signal during scoring:
  base_score = 72
  signal_bonus = +12  (expansion signal)
  final_score = 84  → tier = HIGH
         │
         ▼
Writer reads intent_signal when drafting email:
  "Company is expanding → lead with audit-before-you-open angle,
   mention multi-site savings, reference the Monroe County expansion"
         │
         ▼
Email draft references the specific signal — not a generic template
         │
         ▼
Human reviews — email feels researched, not cold
```

---

## Signal scoring bonuses (Analyst phase — planned)

| Signal type | Bonus points | Reasoning |
|---|---|---|
| `cost_pressure` | +15 | Actively looking for savings — highest intent |
| `energy_news` | +12 | Already thinking about utility costs |
| `expansion` | +12 | More sites = more utility spend |
| `new_facility` | +10 | Pre-opening audit = best timing |
| `acquisition` | +8 | Consolidating accounts = complexity |
| `hiring` | +5 | Growth signal — less direct but relevant |
| None (regular) | +0 | Base score only |

---

## Deduplication — 3 layers

Every company passes through 3 duplicate checks before being saved:

```
Layer 1: In-batch domain dedup (within one run)
  Python set() — exact domain match
  "RGH Medical" + "Rochester General" same domain → drop one

Layer 2: LLM name-similarity (within one run)
  difflib.SequenceMatcher → flags pairs with similarity > 0.75
  LLM reviews flagged pairs → confirms/rejects duplicate
  "Rochester Regional Health" vs "Rochester Regional Health System" → LLM: same company

Layer 3: DB duplicate check (against all prior runs)
  SQL query: SELECT id WHERE domain CONTAINS x OR (name=x AND city=x)
  Prevents re-saving companies from prior searches
```

---

## What each source finds (example: healthcare Rochester NY)

| Source | Example companies found |
|---|---|
| Tavily news | "Rochester Regional Health" (news: opening new site) |
| SerpAPI | "Unity Hospital" (press release: facility renovation) |
| Google Maps | "Rochester General Hospital", "Wilmot Cancer Center", "UR Medicine" |
| Tavily directory | Companies from Greater Rochester Chamber member list |
| Yelp | Smaller clinics, urgent care centers, dental practices |

Together they cover: named companies in news, large health systems, mid-size providers,
small practices — the full spectrum from warm (signal) to cold (directory) leads.

---

## SerpAPI — planned implementation

**New file:** `agents/scout/serp_client.py`

**Three search modes:**
```python
# Mode 1: Google News — recent articles
params = { "q": "healthcare expansion Rochester NY 2024", "tbm": "nws" }

# Mode 2: Google general — press releases
params = { "q": "Rochester NY hospital new facility press release" }

# Mode 3: Google Local — businesses
params = { "q": "manufacturing companies Rochester NY", "tbm": "lcl" }
```

**Flow:**
```
3 SerpAPI queries (news mode)
  → returns article titles + snippets
  → LLM extracts: company name, city, signal_type, signal_detail
  → saved with intent_signal

3 SerpAPI queries (general mode)
  → returns company pages, press releases
  → LLM extracts company names (no signal, just discovery)
  → saved without intent_signal
```

**Required env var:** `SERP_API_KEY=your_key`
**Free tier:** 100 searches/month
**Paid:** $50/month for 5,000 searches

---

## Files involved

| File | Purpose |
|---|---|
| `agents/scout/scout_agent.py` | Main orchestrator — runs all phases in order |
| `agents/scout/news_scout_client.py` | Phase 0 — Tavily news search + LLM extraction |
| `agents/scout/serp_client.py` | Phase 0.5 — SerpAPI news + press release search (PLANNED) |
| `agents/scout/search_client.py` | Phase 2 — Tavily directory search |
| `agents/scout/google_maps_client.py` | Phase 3 — Google Maps Places API |
| `agents/scout/yelp_client.py` | Phase 3b — Yelp Business API |
| `agents/scout/llm_query_planner.py` | Generates 4 diverse queries per source |
| `agents/scout/llm_deduplicator.py` | 2-pass dedup: domain exact + LLM name similarity |
| `agents/scout/company_extractor.py` | DB duplicate check before each save |
| `database/orm_models.py` | Company model — includes intent_signal field |
| `database/migrations/014_...sql` | Added intent_signal column |
