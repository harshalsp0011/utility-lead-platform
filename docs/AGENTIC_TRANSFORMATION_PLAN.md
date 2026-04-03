# Agentic Transformation Plan

> Last updated: April 2026
> Phases A, B, C (Writer+Critic), CRM Writer — complete.
> Phase D (Chat filters), Phase KB (Knowledge Base + Vector Memory) — planned.

---

## 1. Vision

Build an agentic lead-generation platform where agents **reason, decide, act, and evaluate**
— not just execute fixed automation steps.

```
Automation (what we had):
  User → fixed code → fixed query → fixed formula → result

Agentic (what we are building):
  User → LLM reasons about available data + memory
       → retrieves relevant proof points from knowledge base
       → decides which tools to call and in what order
       → executes tools (APIs, DB, math — deterministic)
       → evaluates result quality
       → loops if result is not good enough
       → returns result
```

**LLM = decision and reasoning layer only.**
**Tools = deterministic execution (APIs, DB queries, math formulas).**
**Memory = what the agent knows about past performance + company knowledge base.**

---

## 2. What "Agentic" Means Here

| Behavior | Example | Status |
|---|---|---|
| **Dynamic query planning** | "find schools" → LLM generates 5 search variants | ✅ Built |
| **Data gap detection** | Analyst notices employee_count=0 → re-enriches | ✅ Built |
| **Industry inference** | "Buffalo Surgical" → classifies as healthcare | ✅ Built |
| **Output evaluation** | Critic scores draft 0–10, triggers rewrite if low | ✅ Built (pipeline) |
| **Retry with feedback** | Writer sees Critic's reason → rewrites targeted | ✅ Built (pipeline) |
| **Human-in-loop critic** | CRM path: user gives feedback → writer rewrites | ✅ Built (CRM) |
| **Context carry-forward** | Meeting notes → LLM structures → writer uses them | ✅ Built (CRM) |
| **Win-rate learning** | Tracker updates reply rates → Writer picks best angle | ✅ Built |
| **Long-term knowledge memory** | Writer retrieves case studies + proof points per company | 🔲 Planned (Phase KB) |
| **Semantic retrieval** | Company profile embedded → similar case study found | 🔲 Planned (Phase KB) |
| **Chat dynamic filters** | "show healthcare leads in deregulated states" | 🔲 Planned (Phase D) |

**NOT agentic (stays rule-based — intentionally):**
- Math calculations (spend, savings, scores) — LLM hallucinates numbers
- DB queries — deterministic SQL
- Email sending — no reasoning needed
- Score threshold comparisons — business rules

---

## 3. Technology Stack

| Layer | Technology | Role | Status |
|---|---|---|---|
| LLM provider (default) | Ollama + llama3.2 (local) | Zero cost, runs on host Mac | ✅ Live |
| LLM provider (optional) | OpenAI GPT-4o-mini | Cloud fallback, ~$0.005/run | ✅ Live |
| LLM framework | LangChain | Tool calling, prompt management | ✅ Live |
| Embedding model | Ollama + nomic-embed-text | 768-dim vectors for semantic search | ✅ Running (planned for KB) |
| Vector store | PostgreSQL + pgvector | Same DB — no new infrastructure | 🔲 Planned (Phase KB-0) |
| API | FastAPI | Trigger endpoints, background tasks | ✅ Live |
| Database | PostgreSQL (AWS RDS) | Business data + agent memory | ✅ Live |
| Observability | LangSmith | Full LLM trace per run | ✅ Live |

**Note on LangGraph:** Considered for orchestrating state machines between agents.
Decision: not used. LLM reasoning layer achieves agentic behavior without a full graph
framework. May revisit in Phase KB if cross-agent state sharing becomes complex.

**Note on Graph DB (Neo4j etc.):** Considered for KB phase. Decision: start with pgvector.
Already have Postgres + nomic-embed-text. Semantic similarity search handles most retrieval
cases without a separate database. Add graph reasoning only if multi-hop queries are needed
(e.g. "which service performs best in deregulated manufacturing states?").

---

## 4. Agentic Architecture (Current + Planned)

```
┌─────────────────────────────────────────────────────────────────┐
│                    LLM REASONING LAYER                          │
│                                                                 │
│  Scout:     query planning · dedup · quality retry              │
│  Analyst:   industry inference · gap detection · re-enrich      │
│             score narration                                     │
│  Writer:    context-aware generation · angle selection          │
│             ↳ [PLANNED] retrieval agent: pulls relevant         │
│               case studies + proof points from knowledge base   │
│  Critic:    quality evaluation · rewrite instruction (pipeline) │
│  Human:     feedback dialog → rewrite instruction (CRM)        │
│  Chat:      dynamic filter building · context carry-forward     │
└──────────────────────────┬──────────────────────────────────────┘
                           │ decides what to call
┌──────────────────────────▼──────────────────────────────────────┐
│                TOOLS LAYER (deterministic)                      │
│                                                                 │
│  Google Maps API  ·  Yelp API  ·  Tavily search                 │
│  Apollo org enrichment  ·  Hunter contact finder                │
│  Website crawler (requests + BeautifulSoup)                     │
│  Spend calculator  ·  Score formula  ·  Savings calculator      │
│  PostgreSQL queries  ·  SendGrid email sender                   │
│  pgvector similarity search  ← [PLANNED] KB retrieval          │
└─────────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│              MEMORY LAYER                                       │
│                                                                 │
│  Short-term (per run, in-process):                              │
│    company data · enrichment results · critic feedback          │
│                                                                 │
│  Long-term (PostgreSQL):                                        │
│    source_performance  — which Scout sources work per industry  │
│    email_win_rate      — which angle wins replies per industry  │
│    agent_run_logs      — every decision + action, every run     │
│    company_context_notes — personal meeting notes (CRM)         │
│                                                                 │
│  Knowledge Base (pgvector) ← [PLANNED]:                        │
│    services · case studies · proof points · CTAs                │
│    stored as 768-dim embeddings (nomic-embed-text)              │
│    retrieved by semantic similarity to company profile          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Phase-by-Phase Plan

### Phase A — Agentic Analyst ✅ COMPLETE (2026-03-22)

**What changed:**
1. `llm_inspector.py` — LLM infers industry from company name + crawled text, detects data gaps, returns `score_now` or `enrich_before_scoring`
2. `analyst_agent.gather_company_data()` — calls inspector, runs re-enrichment loop if needed (max 2 loops)
3. `score_engine.generate_score_reason()` — replaced with LLM narrator that writes plain-English explanation

```
Load company
  ↓ LLM Inspector (~100 tokens)
    { inferred_industry: "healthcare", data_gaps: ["employee_count"], action: "enrich_before_scoring" }
  ↓ Re-enrich if needed (crawl → Apollo → re-check)
  ↓ score_engine.compute_score()  ← deterministic math
  ↓ LLM Narrator (~80 tokens)
    "250-employee healthcare company, 3 sites in deregulated NY — strong audit candidate"
```

**LLM calls:** 2 per company (~180 tokens). Skipped if all data present. Any failure → silent fallback to rule-based.

---

### Phase B — Agentic Scout ✅ COMPLETE (2026-03-22)

**What changed:**
1. `llm_query_planner.py` — generates 3–5 search query variants from user intent
2. Multi-query execution — runs ALL variants across Google Maps + Tavily
3. `llm_deduplicator.py` — rule dedup + LLM near-duplicate review (name similarity ≥ 0.75)
4. Quality retry loop — if results < 80% of target → generate 3 new queries → retry once

```
"find schools in Buffalo"
  ↓ LLM Query Planner → ["elementary schools Buffalo NY", "K-12 Erie County", ...]
  ↓ Run all queries → Google Maps + Tavily
  ↓ LLM Deduplicator → drops near-dupes
  ↓ Quality check: found 12, target 20 → retry with 3 new queries
  ↓ Save to DB
```

**LLM calls:** up to 3 per Scout run (~300 tokens). Any failure → silent fallback.

---

### Phase C — Writer + Critic Loop ✅ COMPLETE (2026-03-22)

**Pipeline path:**
1. Writer reads company data + score narrative → reasons about best angle → generates email
2. Critic scores draft 0–10 on 5 criteria → returns score + rewrite instruction
3. If score < 7: rewrite loop, max 2 rewrites, `low_confidence=true` if still failing

**CRM path (added April 2026):**
1. Context Formatter: LLM structures free-text meeting notes into bullet points
2. Writer uses formatted context as `score_reason` substitute — no pipeline data needed
3. No automatic critic loop — human IS the critic
4. Regenerate dialog: user types what to change → single rewrite call with that instruction
5. Signature hardcoded: "Best regards, Kevin Gibs / Sr. Vice President / Troy & Banks Inc."

```
Pipeline:  Write → Critic (0–10) → Rewrite if < 7 → max 2x → save
CRM:       Format notes → Write → Human reviews → Regenerate with feedback if needed
```

---

### Phase D — Chat Dynamic Filters 🔲 PLANNED

**What exists now:** Tier 2 routing uses Python string matching for `tier` and `industry`.
**What changes:** LLM builds filter combinations from natural language, including multi-filter combos Python matching misses. Context carry-forward across turns.

---

### Phase KB-0 — Knowledge Base: DB + pgvector 🔲 PLANNED

**Purpose:** Give the Writer agent long-term memory about what Troy & Banks does, what results they've achieved, and how to link to relevant proof points in emails.

**What to build:**
- Enable `pgvector` extension on PostgreSQL (one SQL command)
- New migration: `knowledge_base` table

```sql
CREATE TABLE knowledge_base (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type        VARCHAR(30) NOT NULL,    -- 'service', 'case_study', 'proof_point', 'cta_link', 'connect_link'
    title       VARCHAR(200) NOT NULL,
    industry_tags VARCHAR(200),         -- comma-separated hints: 'manufacturing,industrial'
    summary     TEXT NOT NULL,          -- what the LLM will read
    link        VARCHAR(500),           -- URL to include in email if relevant
    embedding   vector(768),            -- nomic-embed-text output
    active      BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ON knowledge_base USING ivfflat (embedding vector_cosine_ops);
```

**Example rows:**

| type | title | summary | link |
|---|---|---|---|
| service | Utility Contract Audit | We audit current utility contracts and renegotiate rates — clients average 18% savings | |
| case_study | Ohio Manufacturer - $80k Gas Savings | 8-site manufacturer in Columbus, OH. Overpaying on gas contracts for 3 years. Renegotiated → $80k/yr savings | https://troybanks.com/cases/ohio-mfg |
| case_study | Buffalo School District - 22% Electricity Reduction | 12-location school district, locked into above-market electricity contract. Switched suppliers → 22% reduction | https://troybanks.com/cases/buffalo-schools |
| proof_point | Average Client Saves 18% Year 1 | Across all clients, average first-year savings is 18% on electricity and 12% on gas | |
| cta_link | Book a Free 30-Min Audit Call | Schedule a no-commitment discovery call | https://calendly.com/kevingibs/30min |
| connect_link | Kevin Gibs LinkedIn | Connect on LinkedIn | https://linkedin.com/in/kevingibs |

---

### Phase KB-1 — Populate + Embed 🔲 PLANNED

**What to build:**
- `agents/writer/retrieval_agent.py` — `embed_text(text)` using nomic-embed-text via Ollama
- Admin script or API endpoint: `POST /knowledge-base` — add entry → auto-embed → store
- Seed script: populate ~10–15 entries from Troy & Banks materials

**Agentic concept: Information Structuring + Persistent Memory**
The knowledge base is not hardcoded in prompts — it's a live, queryable memory store. New case studies can be added at any time and the Writer immediately gains access to them without code changes.

---

### Phase KB-2 — Retrieval Agent 🔲 PLANNED

**What to build:** `agents/writer/retrieval_agent.py` — `retrieve(company_profile, top_k=3)`

```python
def retrieve(company_profile: str, top_k: int = 3) -> list[KnowledgeItem]:
    """
    1. Embed the company profile string using nomic-embed-text
    2. pgvector cosine similarity search against knowledge_base
    3. Return top_k most relevant items (type, title, summary, link)
    """
```

**Agentic concept: Tool-Using RAG Agent**
The Writer calls retrieval as a tool before writing — like asking an expert colleague
"what have we done for companies like this one?" The retrieval result is not injected
blindly — it is presented to the LLM as optional context, and the LLM decides which
items to use and how to weave them naturally into the email.

**Why vector (not SQL filter):**
A SQL filter on `industry_tags` catches exact matches only. A vector search catches
semantic similarity — a *hospital* case study may be highly relevant to a *school district*
because both have large HVAC loads and predictable utility bills. The embedding model
captures that relationship; a filter cannot.

**Why nomic-embed-text + pgvector (not a separate vector DB):**
- `nomic-embed-text` is already running in Ollama (confirmed in stack)
- pgvector runs inside the existing PostgreSQL instance — no new container
- One database connection, one schema, same backup/restore process
- Weaviate/Pinecone would be overkill for a knowledge base of < 1000 items

---

### Phase KB-3 — Wire into Writer 🔲 PLANNED

**What to build:**
- Both `process_one_company()` (pipeline) and `process_crm_company()` (CRM) call `retrieval_agent.retrieve()`
- Inject top-3 results into writer prompt as a new section:

```
== RELEVANT PROOF POINTS (weave in naturally — do not list robotically) ==
- [case_study] Ohio Manufacturer: 8 sites, cut gas by $80k/yr → https://troybanks.com/cases/ohio-mfg
- [service] We specialize in multi-site utility contract renegotiation
- [cta_link] Free 30-min audit: https://calendly.com/kevingibs/30min
```

- Writer decides which items to use — may use all, some, or none depending on company fit
- If retrieval returns nothing relevant (score below threshold) → omit section entirely, write without it

**Token cost addition:** ~100 tokens per retrieval injection (small context block)

---

### Phase KB-4 — Knowledge Base UI 🔲 PLANNED (optional)

Simple "Knowledge Base" page in the dashboard:
- List all entries (type, title, summary, link)
- Add new entry form (type + title + summary + link → auto-embed on save)
- Toggle active/inactive (deactivate without deleting)
- No editing of embeddings needed — re-embed on update automatically

Alternatively: manage via a simple CSV import script. Not required for the core feature.

---

## 6. Memory Model

### Short-term (per run, in-process)
- Company data accumulated during Scout
- Enrichment results per company
- Critic feedback per draft
- Retrieved knowledge items per email

### Long-term (PostgreSQL — current)

| Table | Tracks | Used by |
|---|---|---|
| `source_performance` | Quality score per source per industry/location | Scout — ranks sources at run start |
| `email_win_rate` | Reply rate per angle per industry | Writer — picks best angle |
| `agent_run_logs` | Every decision + action per run | Observability, debugging |
| `company_context_notes` | Personal meeting notes, LLM-structured | CRM Writer |

### Long-term (pgvector — planned)

| Table | Tracks | Used by |
|---|---|---|
| `knowledge_base` | Services, case studies, proof points, CTAs with 768-dim embeddings | Retrieval Agent → Writer |

---

## 7. Token Cost Estimate

Per full pipeline run (20 companies, 5 emails):

| Stage | Calls | Tokens | GPT-4o-mini cost |
|---|---|---|---|
| Scout query planning | 3 | ~300 | $0.00045 |
| Analyst per company ×20 | 40 | ~3,600 | $0.0054 |
| Writer + Critic per email ×5 | 20 | ~5,000 | $0.0075 |
| Retrieval injection ×5 (planned) | 5 | ~500 | $0.00075 |
| Chat per message | 1 | ~200 | $0.0003 |
| **Total (current)** | | **~9,100** | **~$0.013** |
| **Total (with KB)** | | **~9,600** | **~$0.014** |

With **Ollama (local)**: $0.00 per run.
Retrieval itself (embed + vector search) is ~5ms — no LLM call, zero cost.

---

## 8. Observability

Every LLM call logged to `agent_run_logs`:
- `agent` — which agent made the call
- `action` — what was asked (e.g. `infer_industry`, `retrieve_knowledge`, `write_draft`)
- `output_summary` — what it returned
- `duration_ms` — latency

LangSmith tracing enabled via `LANGCHAIN_TRACING_V2=true` — full visual trace per run.

---

## 9. Build Order

```
Step 1 → Phase A: Analyst LLM reasoning layer           ✅ DONE (2026-03-22)
Step 2 → Phase B: Scout agentic query planning           ✅ DONE (2026-03-22)
Step 3 → Phase C: Writer + Critic loop (pipeline)        ✅ DONE (2026-03-22)
Step 3b→ Phase C CRM: Context-aware CRM writer           ✅ DONE (2026-04-02)
         (context formatter, human-in-loop, signature)
Step 4 → Phase D: Chat dynamic filter generation         🔲 PLANNED
Step 5 → Phase KB-0: knowledge_base table + pgvector     🔲 PLANNED
Step 6 → Phase KB-1: Populate + embed entries            🔲 PLANNED
Step 7 → Phase KB-2: Retrieval agent                     🔲 PLANNED
Step 8 → Phase KB-3: Wire retrieval into Writer          🔲 PLANNED
Step 9 → Phase KB-4: Knowledge Base UI (optional)        🔲 PLANNED
```

---

## 10. Success Criteria

| Metric | Target |
|---|---|
| Industry correctly classified | > 90% of companies (vs ~60% exact match) |
| Companies scored with real employee_count | > 70% (vs ~30% today) |
| Email draft quality (Critic score, pipeline) | Average ≥ 7 after at most 1 rewrite |
| CRM email regenerate acceptance rate | > 80% accepted on first or second try |
| Scout query coverage | User intent matched by ≥ 3 query variants |
| Chat filter accuracy | Correct filters ≥ 95% |
| KB retrieval relevance (planned) | Top-1 result relevant to company ≥ 85% of runs |
| Email click-through with KB links (planned) | Measurable improvement vs baseline |
