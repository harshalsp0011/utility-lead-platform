# Developer Guide — Utility Lead Intelligence Platform
### For humans and LLMs picking up this codebase

> **Read this before touching anything.** Every pattern, convention, and "gotcha" in this repo is documented here. If you follow this guide, you will not break things, duplicate things, or miss steps.

---

## Table of Contents

1. [What This Platform Does](#1-what-this-platform-does)
2. [Repository Layout](#2-repository-layout)
3. [Running Locally (Docker)](#3-running-locally-docker)
4. [Environment Variables](#4-environment-variables)
5. [Database — Tables, ORM, Migrations](#5-database--tables-orm-migrations)
6. [Backend — FastAPI Patterns](#6-backend--fastapi-patterns)
7. [Agents — Architecture & Conventions](#7-agents--architecture--conventions)
8. [Frontend — React Patterns](#8-frontend--react-patterns)
9. [External APIs Inventory](#9-external-apis-inventory)
10. [Data Provenance — source vs data_origin](#10-data-provenance--source-vs-data_origin)
11. [How to Add a New Feature (End-to-End)](#11-how-to-add-a-new-feature-end-to-end)
12. [How to Add a New Agent](#12-how-to-add-a-new-agent)
13. [How to Add a New DB Column or Table](#13-how-to-add-a-new-db-column-or-table)
14. [How to Add a New API Route](#14-how-to-add-a-new-api-route)
15. [How to Add a New Frontend Page](#15-how-to-add-a-new-frontend-page)
16. [Docker Rebuild Protocol](#16-docker-rebuild-protocol)
17. [Human-in-Loop Flows](#17-human-in-loop-flows)
18. [Key Design Decisions](#18-key-design-decisions)
19. [Common Mistakes to Avoid](#19-common-mistakes-to-avoid)
20. [Current Build State](#20-current-build-state)

---

## 1. What This Platform Does

Fully automated B2B lead discovery and outreach pipeline for an energy consulting firm (Troy & Banks, Buffalo NY).

**Pipeline flow:**

```
Scout Agent
  → finds companies from: Tavily news, Yelp, Google Maps, directory scraping
  → saves to companies table (data_origin="scout")

Analyst Agent
  → enriches each company: website crawl, Hunter/Apollo/Snov/Prospeo/Serper/ZeroBounce waterfall
  → scores 0-100 (Recovery score + Industry fit + Multi-site bonus + Data quality)
  → saves contacts (data_origin="scout"), saves lead_scores

[HUMAN APPROVAL GATE 1] — Leads page: approve / reject / skip companies

Writer Agent
  → drafts email for approved leads using LLM + template engine + critic loop
  → critic scores 0-10, rewrites up to 3 times

[HUMAN APPROVAL GATE 2] — Email Review page: approve / edit / reject drafts

Outreach Agent
  → sends via SendGrid or Instantly
  → schedules Day 3, 7, 14 follow-ups

Tracker Agent
  → monitors replies via SendGrid webhooks
  → classifies replies (positive / negative / auto-responder)
  → alerts sales team on positive replies
```

**Two deployment units (Docker containers):**
- `api` — FastAPI Python backend on port 8001
- `frontend` — React SPA served by nginx on port 3000

No separate worker containers. Agents run inline within the API process when triggers fire.

---

## 2. Repository Layout

```
utility-lead-platform/
├── api/
│   ├── main.py                  ← FastAPI app + all router registrations
│   ├── Dockerfile
│   └── routes/
│       ├── leads.py             ← Lead CRUD, approve/reject
│       ├── emails.py            ← Email draft management
│       ├── triggers.py          ← Manual pipeline triggers (POST /trigger/*)
│       ├── pipeline.py          ← Pipeline status + run history
│       ├── reports.py           ← Analytics
│       ├── approvals.py         ← Human approval request handlers
│       ├── chat.py              ← Chat agent endpoint
│       └── api_lab.py           ← Developer API testing (16 endpoints + credit checks)
│
├── api/models/
│   └── api_lab.py               ← Pydantic models for API Lab (ApiLabResult + 16 request types)
│
├── agents/
│   ├── chat_agent.py            ← Chat orchestration
│   ├── scout/                   ← Company discovery (11 files)
│   ├── analyst/                 ← Enrichment + scoring (7 files)
│   ├── writer/                  ← Email drafting + critic (5 files)
│   ├── outreach/                ← Send + scheduling (4 files)
│   ├── tracker/                 ← Reply monitoring (5 files)
│   ├── orchestrator/            ← High-level coordinator (4 files)
│   └── notifications/           ← Email notifier
│
├── database/
│   ├── orm_models.py            ← ALL SQLAlchemy ORM models (14 tables, single file)
│   ├── connection.py            ← Engine + session factory
│   └── migrations/              ← Numbered SQL files, run in order (001–018 so far)
│
├── config/
│   └── settings.py              ← All env var loading (50+ variables)
│
├── dashboard/
│   ├── Dockerfile               ← Multi-stage: Node 18 build → nginx:alpine serve
│   ├── package.json
│   └── src/
│       ├── App.jsx              ← Router + sidebar nav + all route definitions
│       ├── pages/               ← 9 page components
│       ├── components/          ← Reusable UI components
│       └── services/
│           └── api.js           ← All fetch() calls to backend (single source of truth)
│
├── docs/                        ← All planning + integration docs
├── dags/                        ← Airflow DAGs (optional scheduler, not currently live)
├── .env                         ← NOT in repo — copy from .env.example
├── .env.example
├── docker-compose.yml
└── requirements.txt
```

**Rules:**
- All Python deps → `requirements.txt` (no setup.py, no pyproject.toml)
- All env vars → `config/settings.py` (never import os.environ directly in agents)
- All ORM models → `database/orm_models.py` (never create a separate models file)
- All API fetch calls → `dashboard/src/services/api.js` (never fetch() inside a component)

---

## 3. Running Locally (Docker)

### First time setup

```bash
cp .env.example .env
# Fill in all required API keys in .env

docker-compose up --build
```

Access:
- Frontend: http://localhost:3000
- API docs: http://localhost:8001/docs
- API health: http://localhost:8001/health

### After any code change

**ALWAYS rebuild after code changes.** The containers do not auto-reload from source.

```bash
# Rebuild and restart both containers
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Delete old images to free space
docker image prune -f
```

**Only need to rebuild the specific service if you know what changed:**
```bash
docker-compose build --no-cache api    # backend only
docker-compose build --no-cache frontend  # frontend only
docker-compose up -d
```

### View logs

```bash
docker-compose logs api -f        # backend logs (live)
docker-compose logs frontend -f   # nginx logs
docker-compose ps                 # container status
```

### Run migrations against the live DB

```bash
# Run a single migration
psql "$DATABASE_URL" -f database/migrations/019_your_migration.sql

# Check a table structure
psql "$DATABASE_URL" -c "\d companies"
```

**Do not use `source .env` with psql** — the DATABASE_URL contains `&` characters that break shell parsing. Extract it directly:

```bash
DB_URL=$(grep "^DATABASE_URL=" .env | cut -d '=' -f2-)
psql "$DB_URL" -f database/migrations/019_your_migration.sql
```

---

## 4. Environment Variables

All variables are defined in `config/settings.py`. Never reference `os.environ` directly in agents or routes — always import from settings:

```python
from config.settings import settings

key = settings.HUNTER_API_KEY
```

### Variable groups

| Group | Key variables |
|---|---|
| **System** | `DEPLOY_ENV`, `LOG_LEVEL` |
| **Brand** | `TB_BRAND_NAME`, `TB_OFFICE_LOCATION`, `TB_CONTINGENCY_FEE`, `TB_SENDER_NAME` |
| **LLM** | `LLM_PROVIDER` ("ollama"/"openai"), `LLM_MODEL`, `OLLAMA_BASE_URL`, `OPENAI_API_KEY` |
| **Search** | `TAVILY_API_KEY`, `SERPER_API_KEY`, `SCRAPERAPI_KEY`, `GOOGLE_MAPS_API_KEY`, `YELP_API_KEY` |
| **Enrichment** | `HUNTER_API_KEY`, `APOLLO_API_KEY`, `PROSPEO_API_KEY`, `SNOV_CLIENT_ID`, `SNOV_CLIENT_SECRET`, `ZEROBOUNCE_API_KEY` |
| **Database** | `DATABASE_URL` |
| **Email send** | `EMAIL_PROVIDER`, `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`, `INSTANTLY_API_KEY`, `INSTANTLY_CAMPAIGN_ID` |
| **Scoring** | `SCORE_WEIGHT_RECOVERY`, `HIGH_SCORE_THRESHOLD` (70), `MEDIUM_SCORE_THRESHOLD` (40) |
| **Security** | `API_KEY` (optional — used by `verify_api_key` dependency) |
| **Observability** | `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` |

### Adding a new env var

1. Add to `.env.example` with a comment explaining the value
2. Add to `config/settings.py` with `Optional[str] = None` or a sensible default
3. Use `settings.YOUR_VAR` in code — never `os.environ`
4. Document in README.md under "Configuration"

---

## 5. Database — Tables, ORM, Migrations

### All 14 tables

| Table | ORM Class | Purpose |
|---|---|---|
| `companies` | `Company` | Every discovered company |
| `company_features` | `CompanyFeature` | Enrichment signals (spend, savings, scores) |
| `contacts` | `Contact` | Decision-maker contacts |
| `lead_scores` | `LeadScore` | Analyst score + tier per company |
| `email_drafts` | `EmailDraft` | Writer output, pending/approved/sent |
| `outreach_events` | `OutreachEvent` | Every interaction (sent, opened, replied, note) |
| `directory_sources` | `DirectorySource` | Scout source URLs (reusable) |
| `agent_runs` | `AgentRun` | One row per pipeline trigger |
| `agent_run_logs` | `AgentRunLog` | Step-by-step audit within a run |
| `source_performance` | `SourcePerformance` | Scout learning: which sources perform best |
| `email_win_rate` | `EmailWinRate` | Writer learning: which templates win |
| `human_approval_requests` | `HumanApprovalRequest` | Pending human approval queue |

### ORM conventions

All models live in **`database/orm_models.py`** — one file, never split.

Pattern used: SQLAlchemy 2.0 `DeclarativeBase` + `mapped_column` type annotations.

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, UUID

class Base(DeclarativeBase):
    pass

class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # ... all other fields
```

**Session injection:** Always use FastAPI's `Depends(get_db)` for session management. The `get_db` function is in `database/connection.py`.

```python
from database.connection import get_db
from sqlalchemy.orm import Session
from fastapi import Depends

@router.post("/something")
def my_endpoint(db: Session = Depends(get_db)):
    ...
```

### Migration protocol

Migrations are plain SQL files. **No Alembic, no ORM auto-migrate.**

Naming: `NNN_verb_table_description.sql` — next number is 019.

```sql
-- Migration 019: Add xyz to companies table
ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS xyz VARCHAR(100);
```

**Checklist when adding a column:**
1. Write migration SQL file: `database/migrations/019_*.sql`
2. Run it against live DB: `psql "$DB_URL" -f ...`
3. Add the column to the ORM class in `database/orm_models.py`
4. Stamp `data_origin` or other provenance fields in the agent that writes the record
5. Rebuild Docker containers

**Checklist when adding a table:**
1. Write migration SQL (CREATE TABLE with IF NOT EXISTS)
2. Run migration
3. Add ORM class to `database/orm_models.py`
4. Add to this document's table list above

---

## 6. Backend — FastAPI Patterns

### Router registration (api/main.py)

Every new route file must be registered in `api/main.py`:

```python
from api.routes import my_new_route
app.include_router(my_new_route.router, prefix="/my-prefix", tags=["my-tag"])
```

Current registration order:
1. chat
2. leads
3. emails
4. pipeline
5. triggers
6. reports
7. approvals
8. api_lab

### Route file boilerplate

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database.connection import get_db
from api.auth import verify_api_key   # optional — use when API_KEY is set in .env

router = APIRouter(dependencies=[Depends(verify_api_key)])  # remove dependency if public

@router.post("/something")
def do_something(request: MyRequestModel, db: Session = Depends(get_db)):
    ...
```

### Pydantic models

- Request/response models go in `api/models/` (one file per route group, e.g. `api/models/api_lab.py`)
- Always use Pydantic v2 `BaseModel`
- All optional fields: `Optional[str] = None` not `str | None = None` (consistency)

### Response envelope for API Lab

All API Lab endpoints return `ApiLabResult`:

```python
class ApiLabResult(BaseModel):
    provider: str
    endpoint: str
    duration_ms: int
    stored_in: Optional[str]
    success: bool
    data: Any
    error: Optional[str]
```

Use `_timed_call(fn, *args, **kwargs)` in `api/routes/api_lab.py` to wrap any agent function.

### Authentication

`verify_api_key` checks the `X-API-Key` header against `settings.API_KEY`. If `API_KEY` is not set in `.env`, the check passes through (development mode). Never bypass this in production.

---

## 7. Agents — Architecture & Conventions

### Agent rule: every agent must have a system prompt

No agent function calls an LLM without a system prompt. This is non-negotiable. The system prompt defines tone, role, output format, and constraints.

### Agent invocation pattern

Agents are Python modules — they are imported and called directly (no HTTP between agents):

```python
# In a trigger route:
from agents.scout.scout_agent import run_scout
result = run_scout(industry="healthcare", location="Buffalo, NY", db_session=db)
```

### LLM access pattern

All LLM calls go through `agents/writer/llm_connector.py` or equivalent per-agent LLM helper. Never call `openai` or `ollama` SDK directly in a route.

### Agent data flow

```
Scout writes → companies (data_origin="scout")
Analyst writes → contacts (data_origin="scout"), company_features, lead_scores
Writer writes → email_drafts
Outreach writes → outreach_events (event_type="sent")
Tracker writes → outreach_events (event_type="opened"/"replied")
HubSpot sync writes → companies/contacts (data_origin="hubspot_crm") [Phase 1, not yet built]
```

### Agent run logging

Every agent that runs via a trigger should:
1. Create an `AgentRun` row at start (status="running")
2. Create `AgentRunLog` rows per step
3. Update `AgentRun` at end (status="completed" or "failed")

This powers the Pipeline page.

### Enrichment waterfall (Analyst agent)

`agents/analyst/enrichment_client.py` → `find_contacts(company_name, domain, db_session)`

Order: Hunter → Apollo Org Enrich → Website crawl → Serper email search → Snov → Prospeo → ZeroBounce verify → ZeroBounce guess format

Stops early if enough verified contacts are found. Saves to `contacts` table with `data_origin="scout"`.

---

## 8. Frontend — React Patterns

### Tech stack

- React 18 + Vite
- React Router v6 (`<BrowserRouter>` + `<Routes>` + `<Route>`)
- Tailwind CSS (utility classes only, no custom CSS files)
- No Redux, no Context API for global state — component-local state only
- No axios — native `fetch()` only via `services/api.js`

### Page layout convention

Every page must use this structure to match the platform's design language:

```jsx
<div className="h-full overflow-y-auto bg-gray-50">
  <div className="p-6">
    <h1 className="text-3xl font-bold text-gray-900 mb-6">Page Title</h1>
    
    {/* Content in white cards */}
    <div className="bg-white rounded-lg shadow p-6">
      ...
    </div>
  </div>
</div>
```

**Never use:** dark backgrounds, custom colors, inline styles, or layout that differs from bg-gray-50/bg-white cards.

**Exception:** JSON output viewers (API Lab) use `bg-gray-900 text-green-400` for terminal readability. This is intentional.

### Adding a new page

1. Create `dashboard/src/pages/MyPage.jsx`
2. Import in `App.jsx`: `import MyPage from './pages/MyPage';`
3. Add route in `<Routes>`: `<Route path="/my-page" element={<MyPage />} />`
4. Add nav item in sidebar: `<NavItem to="/my-page" icon="🔣" label="My Page" />`

### API calls from frontend

All API calls go through `dashboard/src/services/api.js`. Never call fetch() inside a component.

```javascript
// In api.js — add a new function:
export const myNewCall = (body) => fetchAPI('/my-endpoint', {
  method: 'POST',
  body: JSON.stringify(body),
});

// In a component:
import { myNewCall } from '../services/api';

const result = await myNewCall({ param: value });
```

### Timeouts

- Default: 30 seconds (`REQUEST_TIMEOUT = 30000`)
- Long-running (Scout, scraping): pass `timeout: 180000` option (3 minutes)
- Chat: 180 seconds (`CHAT_TIMEOUT = 180000`)

### State patterns

For pages with cards/expandable items (like API Lab):
```javascript
// Card state keyed by ID
const [cardStates, setCardStates] = useState({});
// Section-level running state
const [sectionRunning, setSectionRunning] = useState({});
// Shared section inputs (for Run All)
const [sectionInputs, setSectionInputs] = useState({});
```

For sequential "Run All" — always use `for...of` + `await`, never `Promise.all`:
```javascript
for (const card of section.cards) {
  await runCard(card.id, sharedInputs);
}
```

---

## 9. External APIs Inventory

| Provider | Category | Used In | Key Operation | Rate/Credit Limit |
|---|---|---|---|---|
| **Tavily** | Search | Scout | Web search for companies + news | 1,000 searches/month (free) |
| **Google Maps Places** | Search | Scout | Discover businesses by type + location | $200/month free credit |
| **Yelp Fusion** | Search | Scout | Discover businesses by category + location | 500 calls/day (free) |
| **ScraperAPI** | Scraping | Scout | Scrape directory websites | 1,000 credits/month (free) |
| **Serper** | Search | Analyst | Find emails via web search | 2,500 queries/month (free) |
| **Hunter.io** | Enrichment | Analyst | Find contacts by domain | 25 searches/month (free) |
| **Apollo.io** | Enrichment | Analyst | Org enrich + people search | 50 exports/month (free) |
| **Snov.io** | Enrichment | Analyst | Find emails by domain | 50 credits/month (free) |
| **Prospeo** | Enrichment | Analyst | Find emails + mobile by domain | 75 credits/month (free) |
| **ZeroBounce** | Validation | Analyst | Verify email validity + guess format | 100 validations/month (free) |
| **OpenAI** | LLM | All agents | GPT-4 for extraction, scoring, drafting | Pay-per-token |
| **Ollama** | LLM (local) | All agents | Local LLM alternative to OpenAI | Unlimited (self-hosted) |
| **SendGrid** | Email send | Outreach | Transactional email + open/click tracking | 100 emails/day (free) |
| **Instantly** | Email send | Outreach | Cold email campaigns (warmup-safe) | Varies by plan |
| **LangSmith** | Observability | All agents | LLM call tracing + cost tracking | Free tier available |

**Key env var names:**
```
TAVILY_API_KEY, GOOGLE_MAPS_API_KEY, YELP_API_KEY, SCRAPERAPI_KEY
SERPER_API_KEY, HUNTER_API_KEY, APOLLO_API_KEY
SNOV_CLIENT_ID, SNOV_CLIENT_SECRET
PROSPEO_API_KEY, ZEROBOUNCE_API_KEY
OPENAI_API_KEY, SENDGRID_API_KEY, INSTANTLY_API_KEY
```

All credit-checking endpoints are live at `GET /api-lab/credits/{provider}` (Hunter, ZeroBounce, Snov, ScraperAPI).

---

## 10. Data Provenance — source vs data_origin

These two fields exist on `companies` and `contacts` and are often confused:

| Column | Type | Purpose | Example values |
|---|---|---|---|
| `source` | `VARCHAR(100)` | **Which specific API** found this record | `"google_maps"`, `"hunter"`, `"yelp"`, `"apollo"` |
| `data_origin` | `VARCHAR(50)` | **Which system** created it | `"scout"`, `"hubspot_crm"`, `"manual"` |

**Rule:** `source` = granular API name. `data_origin` = system-level origin tag.

**`data_origin` values:**

| Value | Meaning | Set by |
|---|---|---|
| `"scout"` | Discovered by our agents from the internet | `company_extractor.py`, `scout_agent.py`, `enrichment_client.py` |
| `"hubspot_crm"` | Pulled from HubSpot CRM | `hubspot_sync.py` (Phase 1 — not yet built) |
| `"manual"` | Added by a human via UI | Any future manual add endpoint |
| `NULL` | Legacy record before this column was added | Treat as `"scout"` |

**`last_synced_at` (TIMESTAMP):** When a record was last pushed to or pulled from an external CRM/system. `NULL` = never synced. Updated by HubSpot sync functions.

**Migration history:**
- `017_alter_companies_add_origin.sql` — added both columns to `companies` ✅ applied 2026-04-01
- `018_alter_contacts_add_origin.sql` — added both columns to `contacts` ✅ applied 2026-04-01

---

## 11. How to Add a New Feature (End-to-End)

Example: adding a "notes" field to companies.

### Step 1 — Database

```bash
# Create migration
cat > database/migrations/019_alter_companies_add_notes.sql << 'EOF'
-- Migration 019: Add notes field to companies
ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS notes TEXT;
EOF

# Run it
DB_URL=$(grep "^DATABASE_URL=" .env | cut -d '=' -f2-)
psql "$DB_URL" -f database/migrations/019_alter_companies_add_notes.sql
```

### Step 2 — ORM

In `database/orm_models.py`, find the `Company` class and add:

```python
notes: Mapped[str | None] = mapped_column(Text, nullable=True)
```

### Step 3 — Backend route

In `api/routes/leads.py` (or a new file), add the endpoint. If new file:

```python
# api/routes/notes.py
router = APIRouter()

@router.patch("/companies/{company_id}/notes")
def update_notes(company_id: str, body: NotesRequest, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    company.notes = body.notes
    db.commit()
    return {"ok": True}
```

Register in `api/main.py`:
```python
from api.routes import notes
app.include_router(notes.router, prefix="/companies", tags=["companies"])
```

### Step 4 — Frontend service

In `dashboard/src/services/api.js`:

```javascript
export const updateCompanyNotes = (id, notes) =>
  fetchAPI(`/companies/${id}/notes`, { method: 'PATCH', body: JSON.stringify({ notes }) });
```

### Step 5 — Frontend UI

In the relevant page (`LeadDetail.jsx` etc), import and call `updateCompanyNotes`.

### Step 6 — Rebuild Docker

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
docker image prune -f
```

---

## 12. How to Add a New Agent

Example: adding a `hubspot` agent.

### Directory structure

```
agents/hubspot/
  __init__.py
  hubspot_client.py     ← raw API wrapper (no DB, no business logic)
  hubspot_sync.py       ← orchestration: pull from API → write to DB
  README.md             ← required: describe what this agent does, inputs, outputs
```

### Rules

1. **System prompt required.** Any function that calls an LLM must have a clearly named system prompt string at the top of the function.
2. **Client vs sync separation.** `_client.py` files handle raw HTTP. `_sync.py` / `_agent.py` files handle DB writes and business logic.
3. **Session injection.** Never create a DB session inside an agent. Always accept `db_session: Session` as a parameter.
4. **Settings import.** `from config.settings import settings` — never `os.environ`.
5. **Logging.** Use Python `logging` module. `logger = logging.getLogger(__name__)` at the top of every file.
6. **Agent run logging.** For agents triggered via API, create `AgentRun` + `AgentRunLog` rows so the Pipeline page shows activity.

### Register in a trigger endpoint

In `api/routes/triggers.py`:

```python
@router.post("/trigger/hubspot-pull")
def trigger_hubspot_pull(db: Session = Depends(get_db)):
    from agents.hubspot.hubspot_sync import batch_pull_all
    result = batch_pull_all(db_session=db)
    return result
```

---

## 13. How to Add a New DB Column or Table

### New column checklist

- [ ] Write `NNN_alter_table_add_column.sql` in `database/migrations/`
- [ ] Run migration: `psql "$DB_URL" -f database/migrations/NNN_*.sql`
- [ ] Verify: `psql "$DB_URL" -c "\d table_name"`
- [ ] Add `mapped_column` to ORM class in `database/orm_models.py`
- [ ] If it's a provenance/audit field, stamp it in every agent that writes that table
- [ ] Rebuild Docker containers

### New table checklist

- [ ] Write `NNN_create_table_name.sql` with `CREATE TABLE IF NOT EXISTS`
- [ ] Run migration
- [ ] Add ORM class to `database/orm_models.py` (follow existing pattern)
- [ ] Add to table inventory in this document (Section 5)
- [ ] Rebuild Docker containers

### Next migration number

Current last: **018**. Next: **019**.

---

## 14. How to Add a New API Route

1. Create `api/routes/my_route.py` with a `router = APIRouter()` at top
2. Add endpoint functions with `@router.get(...)` or `@router.post(...)`
3. Add Pydantic request/response models to `api/models/` if needed
4. Register in `api/main.py`:
   ```python
   from api.routes import my_route
   app.include_router(my_route.router, prefix="/my-prefix", tags=["my-tag"])
   ```
5. Rebuild Docker containers
6. Test: `curl -X POST http://localhost:8001/my-prefix/endpoint -H "Content-Type: application/json" -d '{...}'`
7. Add frontend service function to `dashboard/src/services/api.js`

---

## 15. How to Add a New Frontend Page

1. Create `dashboard/src/pages/MyPage.jsx`
2. Use standard layout: `bg-gray-50` outer → `p-6` container → `bg-white rounded-lg shadow` cards
3. Import in `dashboard/src/App.jsx`:
   ```jsx
   import MyPage from './pages/MyPage';
   ```
4. Add route inside `<Routes>`:
   ```jsx
   <Route path="/my-page" element={<MyPage />} />
   ```
5. Add nav item in sidebar (look for the `<NavItem>` block):
   ```jsx
   <NavItem to="/my-page" icon="🔣" label="My Page" />
   ```
6. Rebuild Docker containers (frontend only if only frontend changed):
   ```bash
   docker-compose build --no-cache frontend
   docker-compose up -d
   ```

---

## 16. Docker Rebuild Protocol

**Always do this after any code change.** Containers do not hot-reload from source files.

```bash
# Full rebuild (safest — use after any change)
docker-compose down
docker-compose build --no-cache
docker-compose up -d
docker image prune -f

# Verify containers are running
docker-compose ps

# Spot-check
curl http://localhost:8001/health
```

**Targeted rebuilds (when you know what changed):**

```bash
# Only backend changed
docker-compose build --no-cache api && docker-compose up -d api

# Only frontend changed
docker-compose build --no-cache frontend && docker-compose up -d frontend
```

**Why --no-cache:** Docker layer caching can miss changes in `COPY` steps. Always use `--no-cache` for code changes.

**After migration + code change:** Run migration first (against live DB), then rebuild containers.

---

## 17. Human-in-Loop Flows

The platform has two hard approval gates. These are intentional and should never be bypassed.

### Gate 1 — Lead approval (after Analyst)

- Analyst scores companies → saves `LeadScore` rows
- `human_approval_requests` row is created (type="lead_review")
- Email notification sent to `settings.ALERT_EMAIL`
- UI: Leads page shows pending leads with approve/skip/reject buttons
- On approve → `LeadScore.approved_human = True`, status moves to "approved"
- Only approved leads proceed to Writer

### Gate 2 — Email approval (after Writer)

- Writer drafts emails → saves `EmailDraft` rows (approved_human=False)
- `human_approval_requests` row is created (type="email_review")
- UI: Email Review page shows drafts with edit/approve/reject
- On approve → `EmailDraft.approved_human = True`
- Only approved drafts proceed to Outreach for sending

### Bypassing gates (dev/test only)

Set in trigger body `{"skip_approval": true}` — only honoured in `DEPLOY_ENV=local`.

---

## 18. Key Design Decisions

| Decision | What it is | Why |
|---|---|---|
| **Single `orm_models.py`** | All 14 ORM classes in one file | Avoids circular imports; easy to see all tables at a glance |
| **No Alembic** | Manual SQL migrations | Simpler for team size; full control over SQL; migration history is readable |
| **No Slack** | Email-only alerts | Simpler; one less integration to maintain |
| **Agents inline** | Agents run inside API process | No separate workers or queues needed at current scale |
| **`source` vs `data_origin`** | Two separate provenance columns | `source` = specific API (e.g. "google_maps"); `data_origin` = system origin ("scout"/"hubspot_crm") |
| **LLM provider abstraction** | `LLM_PROVIDER` env var switches Ollama↔OpenAI | Dev can run fully local without spending on API calls |
| **Sequential Run All** | `for...of` + `await` instead of `Promise.all` | Prevents simultaneous API calls hitting rate limits |
| **Critic loop** | Writer → Critic → rewrite (up to 3x) | Improves email quality before human sees it |
| **Chat as primary interface** | Chat agent can trigger any pipeline action | Sales reps don't need to understand the pipeline UI |
| **Airflow as optional** | Scheduling via Airflow DAGs (not live) | Could run on Airflow in production; local dev uses manual triggers |

---

## 19. Common Mistakes to Avoid

### Backend

- **Do not import os.environ directly** — always use `from config.settings import settings`
- **Do not create DB sessions inside agents** — always pass `db_session` as a parameter
- **Do not call an LLM without a system prompt** — every LLM call needs one
- **Do not forget to register new routes in api/main.py** — they will 404 silently
- **Do not run migrations with `source .env`** — DATABASE_URL has `&` characters; use grep to extract it

### Database

- **Do not skip the ORM update after a migration** — the migration runs on DB, but Python code still needs the column in the ORM model
- **Do not run migrations twice** — use `ADD COLUMN IF NOT EXISTS` to make migrations idempotent
- **Do not use Alembic** — this repo uses plain SQL migrations

### Frontend

- **Do not fetch() inside components** — add the function to `services/api.js` first
- **Do not use a dark background for page layouts** — the design standard is `bg-gray-50` outer, `bg-white` cards
- **Do not add routes without nav items** — pages need to be reachable

### Docker

- **Do not forget to rebuild after code changes** — containers do not auto-reload
- **Do not skip `--no-cache`** — Docker can cache stale layers on COPY steps
- **Do not start both containers with old images** — `docker-compose down` first, then build

---

## 20. Current Build State

*Last updated: 2026-04-01*

### What is live and working

| Component | Status |
|---|---|
| Scout Agent (Tavily, Google Maps, Yelp, directory scraping) | ✅ Working |
| Analyst Agent (enrichment waterfall, scoring, savings calc) | ✅ Working |
| Writer Agent (LLM draft + critic loop) | ✅ Working |
| Outreach Agent (SendGrid send + follow-up scheduling) | ✅ Working |
| Tracker Agent (reply classification) | ✅ Working |
| All 9 Dashboard pages | ✅ Working |
| API Lab page (16 cards + credit checks) | ✅ Working |
| DB columns: `data_origin` + `last_synced_at` (companies + contacts) | ✅ Applied 2026-04-01 |
| Scout/Analyst stamping `data_origin="scout"` | ✅ In code, needs Docker rebuild |

### Needs Docker rebuild

The following code changes were made but containers have NOT been rebuilt yet:

| File changed | What changed |
|---|---|
| `database/orm_models.py` | Added `data_origin` + `last_synced_at` to `Company` and `Contact` |
| `agents/scout/company_extractor.py` | Added `data_origin="scout"` to `Company()` constructor |
| `agents/scout/scout_agent.py` | Added `data_origin="scout"` to both `Company()` constructors |
| `agents/analyst/enrichment_client.py` | Added `data_origin="scout"` to `Contact()` constructor |

### What is not yet built

| Feature | Status | Notes |
|---|---|---|
| HubSpot Phase 1 — Pull CRM → DB | 🔲 Not started | See `docs/HUBSPOT_INTEGRATION_PLAN.md` |
| HubSpot Phase 2 — Follow-up Writer | 🔲 Not started | Requires Phase 1 |
| HubSpot Phase 3 — Push leads → CRM | 🔲 Not started | Requires Phase 1 + 2 |
| SendGrid webhook listener (Tracker) | 🔲 Not started | `tracker/webhook_listener.py` exists but endpoint not registered |
| Airflow scheduled runs | 🔲 Not live | DAGs exist in `dags/` but Airflow not deployed |

### Next migration number

**019** (018 was `contacts` `data_origin` + `last_synced_at`)

### Open questions before HubSpot Phase 1

See `docs/HUBSPOT_INTEGRATION_PLAN.md` → "Remaining Open Questions" section.
