# Utility Lead Intelligence Platform

AI-assisted B2B prospecting and outreach automation for utility cost-reduction sales teams.
The platform runs a full pipeline from lead discovery to personalized email delivery — with two human approval checkpoints and no email ever sent without explicit review.

---

## Table of Contents

1. [What It Does](#1-what-it-does)
2. [Architecture](#2-architecture)
3. [Agent System](#3-agent-system)
4. [Tech Stack](#4-tech-stack)
5. [Project Status](#5-project-status)
6. [Quick Start](#6-quick-start)
7. [Configuration Reference](#7-configuration-reference)
8. [Dashboard Pages](#8-dashboard-pages)
9. [Observability & Monitoring](#9-observability--monitoring)
10. [Database Tables](#10-database-tables)
11. [API Reference](#11-api-reference)
12. [Troubleshooting](#12-troubleshooting)
13. [Documentation Index](#13-documentation-index)

---

## 1. What It Does

The platform automates the full B2B sales prospecting cycle for utility cost-reduction consultants:

```
Find companies  →  Enrich contacts  →  Score as leads
→  Draft personalized emails  →  Human review  →  Send
→  Schedule follow-ups  →  Track replies
```

**Two human checkpoints — nothing moves forward without approval:**
1. After scoring: approve or skip each lead before any email is written
2. After drafting: approve, edit, or reject each email before it is sent

**What is fully automated (no human needed):**
- Daily news scan for companies with high utility spend signals
- Contact lookup and enrichment (8-step waterfall)
- Scoring 0–100 with LLM narrative explanation
- Email drafting with AI Critic review loop (up to 2 rewrites)
- Sending via SendGrid with open/click tracking
- Follow-up scheduling (Day 3 / 7 / 14)

---

## 2. Architecture

### Full System Flow

```
┌─────────────────────────────────────────────────────────┐
│                    Browser (localhost:3000)             │
│                  React + Vite + Tailwind                │
│                                                         │
│  Leads  │  Email Review  │  Pipeline  │  Triggers  │ ...│
└─────────────────────────┬───────────────────────────────┘
                          │  HTTP (fetch)
                          ▼
┌──────────────────────────────────────────────────────────┐
│                   API Layer (localhost:8001)             │
│                    FastAPI + Uvicorn                     │
│                                                          │
│  GET /leads   GET /emails   POST /trigger   GET /pipeline│
└──────┬───────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│                       Agents                             │
│                                                          │
│  Scout Agent         Analyst Agent    Writer Agent       |
│  (news → companies)  (score + enrich) (draft + critic)   │
│                                                          │
│  Outreach Agent      Tracker Agent    Orchestrator       │
│  (send + followup)   (reply monitor)  (chain runner)     │
└──────┬──────────────────────────────────────┬────────────┘
       │                                      │
       ▼                                      ▼
┌──────────────────────┐         ┌─────────────────────────┐
│   External APIs      │         │       PostgreSQL        │
│                      │         │                         │
│  Tavily (search)     │         │  companies              │
│  Apollo (contacts)   │         │  contacts               │
│  Hunter.io (email)   │         │  lead_scores            │
│  Google Maps Places  │         │  email_drafts           │
│  Yelp Business       │         │  outreach_events        │
│  SendGrid (email)    │         │  followup_schedules     │
│  Ollama / OpenAI     │         │  agent_runs             │
└──────────────────────┘         │  email_win_rate         │
                                 └─────────────────────────┘
```

### Docker Services

```
docker-compose up
  ├── api       (port 8001)  FastAPI backend — all agents run inside this process
  └── frontend  (port 3000)  nginx serving the Vite-built React app
```

No separate agent containers. Airflow is a scheduled add-on (not required to run the platform).
Database is external PostgreSQL — not in Docker.

### Human-in-Loop Checkpoints

```
Scout finds companies from the news
        │
        ▼
Analyst enriches contacts + scores 0–100
        │
        ▼
  [HUMAN REVIEW #1]  ← Leads page: approve or skip each company
        │
        ▼
Writer drafts personalized email → Critic reviews → rewrites if needed
        │
        ▼
  [HUMAN REVIEW #2]  ← Email Review page: approve/edit/reject
        │
        ▼
SendGrid sends an email with open + click tracking
        │
        ▼
Follow-ups scheduled at Day 3 / 7 / 14 (cancelled if reply received)
```

---

## 3. Agent System

### Agentic Design Principle

```
Old (rule-based):  fixed query → fixed formula → fixed output

Agentic (current): LLM reasons about available data
                       → decides what tools to call and in what order
                       → executes tools (APIs, DB, scoring math)
                       → evaluates result quality
                       → loops if not good enough
                       → returns result
```

**LLM = decision and reasoning layer only.**
**APIs / DB / math = deterministic tools it calls.**
LLM never does math directly. LLM classifies, infers, decides, evaluates, generates text.

---

### Scout Agent — Company Discovery

Reads business news daily via Tavily and extracts companies with intent signals — new facilities opening, expansions, multi-location operations — that indicate high utility spend.

```
Tavily news search (industry + location queries)
  ↓
LLM extracts: company name, industry, city, why it's a signal
  ↓
Deduplication against existing companies in DB
  ↓
Save new companies with source = 'news_scout'
```

Sources used:
```
1. Tavily news mode   — AI-powered news search for intent signals
2. Google Maps        — Places API for local business discovery
3. Yelp               — Business Search API
4. Directory Scraper  — configured sources (Yellow Pages, local directories)
```

---

### Analyst Agent — Enrichment + Scoring

For each new company, the Analyst finds the right contact and computes a fit score.

```
Load company from DB
  ↓
Contact enrichment waterfall (8 steps):
  Hunter.io → Apollo → website scraper → Serper →
  Snov.io → Prospeo → ZeroBounce → permutation fallback
  ↓
Phone enrichment: Google Places → Yelp → website scraper
  ↓
LLM Data Inspector:
  Infers missing industry from company name
  Detects data gaps → triggers re-enrichment if needed
  ↓
score_engine.compute_score(...)   ← deterministic math
  Score = (Recovery × 0.40) + (Industry × 0.25) + (Multisite × 0.20) + (Data × 0.15)
  ↓
LLM Score Narrator:
  Generates a plain-English explanation of why this company scores this way
```

Tier: **≥70 = high**, **40–69 = medium**, **<40 = low**

---

### Writer Agent — Draft Generation + Critic Loop

```
Writer:
  Reads email_win_rate for the best-performing angle in this industry
  Reads company data + score narrative
  Generates full email: subject line + body (personalized, with savings figure, clear CTA)
  ↓
Critic (second LLM call):
  Scores draft 0–10 on: personalization, savings figure, CTA clarity, human tone, subject line
  Returns score + specific improvement instructions
  ↓
If score < 7: Writer rewrites using Critic feedback (max 2 rewrites)
If score ≥ 7: save draft → Email Review queue
If still < 7 after 2 rewrites: save with low_confidence=true → flagged in UI
```

The email angle used (e.g. `"audit_offer"`) is saved as `template_used`.
When a reply is received, Tracker updates `email_win_rate` → future Writer runs bias toward winning angles per industry.

---

### Run Tracking

Every pipeline trigger creates one `agent_runs` row:

```
agent_runs
  id, trigger_source ("dashboard" / "airflow"), status, current_stage
  companies_found, companies_scored, drafts_created, emails_sent
  started_at, completed_at, error_message
```

Every tool call appends one `agent_run_logs` row — full audit trail.

---

## 4. Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React 18 + Vite + Tailwind CSS | Dashboard UI |
| Routing | React Router v6 | Page navigation |
| API | FastAPI + Uvicorn | REST backend, agent orchestration |
| Agent framework | LangChain | LLM tool-calling and ReAct loops |
| LLM (local) | Ollama + llama3.2 | Default — runs on your machine |
| LLM (cloud) | OpenAI gpt-4o-mini | Optional — set `LLM_PROVIDER=openai` |
| ORM | SQLAlchemy | Database models and queries |
| Database | PostgreSQL | External — not in Docker |
| Search | Tavily API | Company discovery + news signals |
| Maps | Google Maps Places API | Company discovery + phone lookup |
| Business search | Yelp Business API | Company discovery + phone fallback |
| Enrichment | Apollo, Hunter.io, Prospeo, Snov.io | Contact email/title lookup waterfall |
| Verification | ZeroBounce | Email address validation |
| Email delivery | SendGrid | Outreach sending with tracking |
| Containerization | Docker + nginx | 2 containers: api + frontend |
| Scheduled runs | Airflow (add-on) | Optional — daily pipeline scheduling |

---

## 5. Project Status

### What Works End-to-End Right Now

You can run this full sequence today with no missing pieces:

```
1. Triggers page → Run Scout
   → Companies discovered from business news and saved to DB

2. Triggers page → Run Analyst
   → Contacts found, companies scored 0–100 with narrative explanation

3. Leads page → review scores → Approve high-tier leads

4. Triggers page → Run Writer
   → Personalized emails drafted, AI Critic review loop runs

5. Email Review page → read each draft → Approve & Send
   → Email sent via SendGrid, follow-ups scheduled in DB

Pipeline stages update automatically at every step.
```

### Feature Status

| Feature | Status |
|---|---|
| Scout: news-based company discovery | ✅ Done |
| Contact enrichment (8-step waterfall) | ✅ Done |
| LLM scoring + narrative explanation | ✅ Done |
| Lead approval (Leads page) | ✅ Done |
| Writer + Critic + rewrite loop | ✅ Done |
| Email approval queue (Email Review page) | ✅ Done |
| SendGrid sending with tracking | ✅ Done |
| Follow-up scheduling (Day 3/7/14) | ✅ Done (DB only) |
| Dashboard: Leads, Pipeline, Triggers, Email Review | ✅ Done |
| Follow-up actual sending via Airflow | ⚠️ Code exists, Airflow not live |
| Reply detection (webhook) | ❌ Not built |
| CRM sync (e.g., HubSpot) | ❌ Not built |
| Manual lead add form | ❌ Not built |
| CRM import (e.g., HubSpot) | ❌ Not built |
| Reply inbox page | ❌ Not built |

See `docs/BUILD_STATUS.md` for full details, priority order, and what to build next.

### Build Priority (What's Next)

```
1. Reply detection webhook        ← closes biggest gap in pipeline
2. CRM push sync                  ← CRM visibility for sales team (e.g., HubSpot)
3. Manual add + CRM import        ← unlocks existing contacts as lead source
4. Reply inbox page               ← makes replies visible in dashboard
5. Airflow live scheduling        ← makes follow-ups actually send
```

---

## 6. Quick Start

### Prerequisites

- Docker Desktop running
- Ollama installed and running locally with llama3.2 pulled (or OpenAI API key)
- PostgreSQL instance with migrations applied

```bash
# Check prerequisites
docker --version
ollama list       # should show llama3.2
```

### Setup

```bash
# 1. Clone
git clone <your-repo-url>
cd utility-lead-platform

# 2. Copy env file
cp .env.example .env
# Fill in: DATABASE_URL, TAVILY_API_KEY, HUNTER_API_KEY,
#          SENDGRID_API_KEY, SENDGRID_FROM_EMAIL, ALERT_EMAIL

# 3. Pull Ollama model (runs on your host machine)
ollama pull llama3.2

# 4. Run database migrations
psql $DATABASE_URL -f database/migrations/001_create_companies.sql
# ... run all migrations in order 001 through latest

# 5. Build and start containers
docker-compose up --build
```

### Access

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API | http://localhost:8001 |
| API docs (Swagger) | http://localhost:8001/docs |

### Useful Container Commands

```bash
# View API logs (see agent steps, errors)
docker-compose logs api -f

# Rebuild API after code changes
docker-compose build api && docker-compose up -d api

# Rebuild frontend after UI changes
docker-compose build frontend && docker-compose up -d frontend

# Stop everything
docker-compose down
```

> **Important:** Always rebuild the relevant container after code changes. Running containers do not pick up file changes automatically.

---

## 7. Configuration Reference

All config is read from `.env`. Copy `.env.example` to `.env` and fill in values.

### Required

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host:5432/dbname` |
| `LLM_PROVIDER` | `ollama` (local) or `openai` (cloud) | `ollama` |
| `LLM_MODEL` | Model name for selected provider | `llama3.2` |
| `OLLAMA_BASE_URL` | Ollama server URL (Docker uses host.docker.internal) | `http://host.docker.internal:11434` |
| `TAVILY_API_KEY` | Tavily search API key | `tvly-...` |
| `SENDGRID_API_KEY` | SendGrid email delivery key | `SG.xxx` |
| `SENDGRID_FROM_EMAIL` | Verified sender email address | `outreach@yourdomain.com` |
| `ALERT_EMAIL` | Email address for system notifications | `sales@yourdomain.com` |
| `SENDER_NAME` | Name shown in outbound email From field | `Jane Smith` |
| `SENDER_TITLE` | Title shown in email signature | `Energy Consultant` |

### Optional

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` | Required only if `LLM_PROVIDER=openai` | blank |
| `GOOGLE_MAPS_API_KEY` | Google Places — company discovery + phone lookup | blank |
| `YELP_API_KEY` | Yelp Business — company discovery + phone fallback | blank |
| `HUNTER_API_KEY` | Hunter.io — domain email search | blank |
| `APOLLO_API_KEY` | Apollo.io — contact enrichment | blank |
| `SERPER_API_KEY` | Serper.dev — Google search for email discovery | blank |
| `PROSPEO_API_KEY` | Prospeo.io — LinkedIn contact enrichment | blank |
| `ZEROBOUNCE_API_KEY` | ZeroBounce — email verification | blank |
| `SNOV_CLIENT_ID` | Snov.io client ID | blank |
| `SNOV_CLIENT_SECRET` | Snov.io client secret | blank |
| `SCRAPERAPI_KEY` | ScraperAPI — directory scraping proxy | blank |
| `HIGH_SCORE_THRESHOLD` | Minimum score for "high" tier | `70` |
| `MEDIUM_SCORE_THRESHOLD` | Minimum score for "medium" tier | `40` |
| `EMAIL_DAILY_LIMIT` | Max emails sent per day | `50` |
| `DEPLOY_ENV` | `local` disables API key auth on routes | `local` |

---

## 8. Dashboard Pages

| Page | Route | What it shows |
|---|---|---|
| **Leads** | `/leads` | All companies with search + filters — approve/reject leads |
| **Email Review** | `/emails` | Pending email drafts — approve / edit+approve / reject |
| **Triggers** | `/triggers` | Manual pipeline controls: Scout, Analyst, Enrich, Writer |
| **Pipeline** | `/pipeline` | Agent health, stage counts, recent activity feed |

---

## 9. Observability & Monitoring

### Option 1 — Docker Logs (always available)

```bash
docker-compose logs api -f
```

Shows HTTP requests, agent steps, and errors in real time.

### Option 2 — LangSmith (recommended — visual trace per run)

LangSmith shows every LLM call, which tool was chosen, arguments, token counts, and latency in a visual timeline.

**Setup:**
1. Sign up free at https://smith.langchain.com
2. Go to Settings → API Keys → Create API Key
3. Add to `.env`:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__your_key_here
LANGCHAIN_PROJECT=utility-lead-platform
```

4. Rebuild and restart the API container.

### Option 3 — Database Query (audit trail)

Every agent step is persisted in PostgreSQL:

```sql
-- Last 10 agent runs with status
SELECT id, trigger_source, status, current_stage,
       companies_found, error_message, created_at
FROM agent_runs
ORDER BY created_at DESC LIMIT 10;

-- Every step in a specific run
SELECT agent, action, status, output_summary, duration_ms
FROM agent_run_logs
WHERE run_id = '<run-id>'
ORDER BY logged_at ASC;
```

Or via API: `GET http://localhost:8001/pipeline/run/{run_id}`

---

## 10. Database Tables

All tables live in external PostgreSQL. Migrations are in `database/migrations/`.

### Core Data Tables

| Table | Purpose | Key columns |
|---|---|---|
| `companies` | Every company discovered | `id`, `name`, `industry`, `city`, `website`, `source`, `status` |
| `company_features` | Enrichment signals | `company_id`, `employee_count`, `location_count`, `utility_spend_estimate` |
| `lead_scores` | Analyst scoring output | `company_id`, `score`, `tier`, `approved_human`, `score_reason` |
| `contacts` | Decision-maker contacts | `company_id`, `name`, `email`, `title`, `phone` |
| `email_drafts` | Writer-generated drafts | `company_id`, `subject_line`, `body`, `critic_score`, `approved`, `sent_at` |
| `outreach_events` | Every email sent/opened/replied | `company_id`, `event_type`, `event_at`, `reply_sentiment` |
| `followup_schedules` | Scheduled follow-up emails | `company_id`, `send_date`, `sequence_number`, `status` |

### Run Tracking Tables

| Table | Purpose |
|---|---|
| `agent_runs` | One row per pipeline trigger — status, stage counts, timing |
| `agent_run_logs` | Step-by-step audit log per run |
| `human_approval_requests` | Human-in-loop queue for leads and email approvals |

### Learning Tables

| Table | Purpose | Who writes | Who reads |
|---|---|---|---|
| `source_performance` | Quality score per Scout source per industry | Scout (after each run) | Scout (next run) |
| `email_win_rate` | Open/reply rate per email angle per industry | Tracker (after replies) | Writer (before drafting) |

### Migration Files

```
database/migrations/
  001_create_companies.sql
  002_create_contacts.sql
  003_create_company_features.sql
  004_create_lead_scores.sql
  005_create_email_drafts.sql
  006_create_outreach_events.sql
  007_create_directory_sources.sql
  008_create_agent_runs.sql
  009_create_agent_run_logs.sql
  010_create_source_performance.sql
  011_create_email_win_rate.sql
  012_create_human_approval_requests.sql
  013_alter_companies_add_run_id.sql
  014_create_followup_schedules.sql
  015_alter_email_drafts_add_critic_fields.sql
  016_alter_companies_add_phone.sql
```

---

## 11. API Reference

Full Swagger docs at `http://localhost:8001/docs`. Key endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/leads` | Fetch leads with filters (search, status, tier, industry) |
| `PATCH` | `/leads/{id}/approve` | Approve a single lead |
| `PATCH` | `/leads/{id}/reject` | Reject a single lead |
| `GET` | `/emails/pending` | Fetch unapproved email drafts |
| `PATCH` | `/emails/{id}/approve` | Approve an email draft (triggers send) |
| `PATCH` | `/emails/{id}/edit` | Edit subject/body of a draft |
| `PATCH` | `/emails/{id}/reject` | Reject a draft (resets company to approved) |
| `POST` | `/trigger/scout` | Run Scout (background) |
| `POST` | `/trigger/analyst` | Run Analyst for all unscored companies |
| `POST` | `/trigger/writer` | Run Writer for all approved companies |
| `GET` | `/trigger/{id}/status` | Poll status of a triggered run |
| `GET` | `/pipeline/status` | Current stage counts |
| `GET` | `/pipeline/run/{run_id}` | Status and logs for one agent run |
| `GET` | `/health` | API health check |

---

## 12. Troubleshooting

### API not responding
```bash
docker-compose logs api --tail 30
docker-compose restart api
```

### Ollama not responding (LLM calls fail)
```bash
ollama serve          # start Ollama if not running
ollama list           # confirm llama3.2 is pulled
curl http://localhost:11434/api/tags
```
Inside Docker, Ollama is reached via `host.docker.internal:11434`.
Confirm `OLLAMA_BASE_URL=http://host.docker.internal:11434` in `.env`.

### Scout finds 0 companies
- Check `TAVILY_API_KEY` is set and quota is not exceeded
- Check API logs: `docker-compose logs api -f`

### Database connection error
- Confirm `DATABASE_URL` is correct in `.env`
- Test: `docker exec <api-container> python -c "from database.connection import engine; print(engine.url)"`

### Frontend blank page / 404 on refresh
Rebuild the frontend container:
```bash
docker-compose build frontend && docker-compose up -d frontend
```

### SendGrid emails not delivering
- Verify sender email is authenticated in SendGrid dashboard
- Confirm `SENDGRID_FROM_EMAIL` matches the verified sender identity
- Check SendGrid activity feed for blocked or rejected messages

### Code changes not showing
Always rebuild the relevant container after editing code:
```bash
docker-compose build api && docker-compose up -d api      # after backend changes
docker-compose build frontend && docker-compose up -d frontend  # after UI changes
```

---

## 13. Documentation Index

| Document | What it covers |
|---|---|
| `docs/BUILD_STATUS.md` | Exact status of every feature — what's done, what's wired live, what's missing, build priority order |
| `docs/HOW_IT_WORKS.md` | Plain-English guide for business stakeholders — the journey of a lead from discovery to reply |
| `docs/SYSTEM_ARCHITECTURE.md` | Full technical architecture — every agent, every API, every data flow, database schema |
| `docs/MASTER_CHECKLIST.md` | Item-by-item build checklist used during development |
| `docs/AGENTIC_TRANSFORMATION_PLAN.md` | Design plan for agentic upgrades to Scout and Analyst |
| `docs/DOCKER_DEPLOYMENT_GUIDE.md` | Full Docker setup and deployment instructions |
| `docs/DOCKER_QUICK_REFERENCE.md` | Quick reference for common Docker commands |
| `docs/AGENTIC_DESIGN.md` | Agentic reasoning patterns used across agents |
| `docs/CONTACT_ENRICHMENT_STRATEGY.md` | Contact enrichment waterfall — sources, fallbacks, quality gates |
| `docs/ENRICHMENT_API_GUIDE.md` | API-by-API guide for enrichment integrations |
| `docs/SCOUT_SOURCES_AND_SIGNALS.md` | Scout news signals and source configuration |
