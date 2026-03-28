# System Architecture — Utility Lead Platform
> Full pipeline: Lead Discovery → Enrichment → Scoring → Email Drafting → Human Review → Send → Follow-up → Meeting Booked

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [High-Level Pipeline](#2-high-level-pipeline)
3. [Stage 1 — Lead Ingestion](#3-stage-1--lead-ingestion)
4. [Stage 2 — Enrichment & Scoring (Analyst Agent)](#4-stage-2--enrichment--scoring-analyst-agent)
5. [Stage 3 — Human Lead Approval](#5-stage-3--human-lead-approval)
6. [Stage 4 — Email Drafting (Writer + Critic)](#6-stage-4--email-drafting-writer--critic)
7. [Stage 5 — Human Email Review](#7-stage-5--human-email-review)
8. [Stage 6 — Send (SendGrid)](#8-stage-6--send-sendgrid)
9. [Stage 7 — Follow-up Sequence](#9-stage-7--follow-up-sequence)
10. [Stage 8 — Reply Detection & Meeting Booking](#10-stage-8--reply-detection--meeting-booking)
11. [HubSpot Integration Layer](#11-hubspot-integration-layer)
12. [Data Model Summary](#12-data-model-summary)
13. [Tech Stack Reference](#13-tech-stack-reference)
14. [Company Status Lifecycle](#14-company-status-lifecycle)
15. [Agent Responsibilities](#15-agent-responsibilities)

---

## 1. Platform Overview

This platform automates the full outbound sales pipeline — from discovering companies with high utility spend to booking a first meeting — with a human approval checkpoint before any email is sent.

**Core principle:** AI does the research, writing, and scheduling. A human approves every outbound email. No email is ever sent without human sign-off.

**Two lead sources:**
- **AI-discovered:** Scout agent finds companies from live news signals (Tavily)
- **Imported:** Existing contacts pulled from HubSpot or added manually by the sales team

Both paths enter the same pipeline and receive the same quality of outreach.

---

## 2. High-Level Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LEAD SOURCES                                                           │
│                                                                         │
│  [Scout Agent]         [HubSpot Import]         [Manual Add]           │
│  Tavily news search    Pull existing CRM         Sales team form        │
│  → new companies       contacts/companies        → one-off lead         │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ↓
                    companies + contacts tables
                                 ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 1: ANALYST AGENT                                                 │
│  Apollo API enrichment → contact discovery                              │
│  LLM scoring → 0–100 score + tier (high/medium/low) + score_reason     │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ↓
                    ⚠️  HUMAN CHECKPOINT #1
                    Leads page — approve or reject
                                 ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 2: WRITER AGENT                                                  │
│  LLM writes personalized email using score_reason + company context     │
│  Critic LLM scores draft 0–10 on 5 criteria                            │
│  Auto-rewrite loop if score < 7 (max 2 rewrites)                       │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ↓
                    ⚠️  HUMAN CHECKPOINT #2
                    Email Review page — edit, approve, or reject
                                 ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 3: SEND                                                          │
│  SendGrid API → email sent from your-configured-sender@yourdomain.com                │
│  Open + click tracking enabled                                          │
│  Unsubscribe footer appended automatically                              │
└────────────────────────────────┬────────────────────────────────────────┘
                                 ↓
              ┌──────────────────┴──────────────────┐
              ↓                                     ↓
┌─────────────────────────┐           ┌─────────────────────────┐
│  FOLLOW-UP SEQUENCE     │           │  HUBSPOT SYNC           │
│  Airflow daily DAG      │           │  Deal created           │
│  Day 3 → Follow-up #1   │           │  Stage = "Contacted"    │
│  Day 7 → Follow-up #2   │           │  Reply detected via     │
│  Day 14 → Follow-up #3  │           │  webhook → your API     │
└─────────────────────────┘           └─────────────────────────┘
                                 ↓
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 4: REPLY + MEETING                                               │
│  Reply logged → follow-ups cancelled → status = 'replied'              │
│  HubSpot meeting link in follow-up #2                                  │
│  Meeting booked → status = 'meeting_booked'                            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Stage 1 — Lead Ingestion

### 3a. Scout Agent (AI Discovery)

**File:** `agents/scout/scout_agent.py`
**Trigger:** Manual via Triggers page, or Airflow schedule
**Tool:** Tavily Search API (news mode)
**Agentic concept:** Tool Use — LLM decides which search queries to run based on target industry signals

**What it does:**
1. Sends targeted search queries to Tavily (e.g. "hospital expanding Buffalo NY utility costs")
2. Tavily returns live news articles
3. LLM extracts: company name, industry, city, state, website, intent signal (why this company has high utility spend)
4. Deduplicates against existing companies in DB (by name + domain)
5. Saves new companies with `status = 'new'`

**Output:** New rows in `companies` table

**Intent signals the Scout looks for:**
- Building expansion / new facility
- Manufacturing scale-up
- Data center / hospital / industrial mention
- Multi-location operations
- High energy cost news coverage

---

### 3b. HubSpot Import (Existing Contacts)

**File:** `agents/ingest/hubspot_importer.py` *(planned)*
**Trigger:** Manual via Import page button
**Tool:** HubSpot Contacts API v3

**What it does:**
1. Fetches all HubSpot contacts with associated company properties
2. Maps HubSpot fields → `companies` + `contacts` schema
3. Sets `source = 'hubspot_import'` on each row
4. Skips contacts already in DB (matched by email or company domain)
5. Lands with `status = 'new'` — enters same pipeline as Scout leads

**Field mapping:**
| HubSpot Field | Platform Table | Column |
|---|---|---|
| `company` | companies | `name` |
| `domain` | companies | `website` |
| `industry` | companies | `industry` |
| `city` / `state` | companies | `city`, `state` |
| `firstname` + `lastname` | contacts | `full_name` |
| `email` | contacts | `email` |
| `jobtitle` | contacts | `title` |

---

### 3c. Manual Add

**File:** `api/routes/leads.py` → `POST /leads` *(planned)*
**Trigger:** Sales team form on Leads page

**What it does:**
- Simple form: Company name, website, industry, state, contact name, contact email, contact title
- Creates one `companies` row + one `contacts` row
- `status = 'new'`, `source = 'manual'`
- Immediately available for Analyst scoring

---

## 4. Stage 2 — Enrichment & Scoring (Analyst Agent)

**File:** `agents/analyst/analyst_agent.py`, `agents/analyst/enrichment_client.py`
**Trigger:** Manual via Triggers page ("Run Analyst"), or Airflow schedule
**Tools:** Apollo.io API, Ollama LLM (llama3.2)
**Agentic concepts:**
- **Tool Use** — calls Apollo API to discover contacts
- **Chain-of-Thought Reasoning** — LLM reasons through scoring criteria before assigning score
- **Memory** — reads company features computed in prior runs

### Enrichment (Apollo API)

For each company with `status = 'new'`:
1. Queries Apollo with company domain → returns people at that company
2. Finds the best contact match (VP Operations, Facilities Manager, CFO priority order)
3. Saves to `contacts` table: `full_name`, `title`, `email`, `linkedin_url`, `source = 'apollo'`
4. Updates `company.status = 'enriched'`

### Scoring (LLM)

For each enriched company:
1. Computes `company_features`: `site_count`, `employee_count`, `estimated_total_spend`, `savings_low/mid/high`, `deregulated_state`
2. Builds a structured prompt with all company signals
3. LLM reasons step-by-step (chain-of-thought) about:
   - Industry fit (healthcare, manufacturing, education score highest)
   - Multi-site potential (more sites = more savings)
   - Deregulated state (NY, PA, TX, IL, OH — can switch supplier)
   - Employee count proxy for utility spend
   - Intent signal strength from Scout
4. Outputs: `score` (0–100), `tier` (high/medium/low), `score_reason` (plain English explanation)
5. Saves to `lead_scores` table
6. Updates `company.status = 'scored'`

### Score Thresholds

| Score | Tier | Meaning |
|---|---|---|
| 70–100 | high | Strong fit — prioritize for outreach |
| 40–69 | medium | Possible fit — review manually |
| 0–39 | low | Weak fit — deprioritize |

---

## 5. Stage 3 — Human Lead Approval

**Page:** `/leads` (Leads Intelligence page)
**Who does this:** Sales manager / consultant

The Leads page shows all scored companies in a filterable table. For each company:

- **Score** with visual bar
- **Tier** badge (high / medium / low)
- **Status** badge
- **Savings estimate** (mid-range in dollars)
- **Contact found** indicator
- **Approve / Reject** inline actions

**Approve** → `company.status = 'approved'`, `lead_scores.approved_human = true`
**Reject** → `company.status = 'archived'`
**Bulk approve** → select all high-tier leads, approve in one click

Only approved companies proceed to the Writer. Rejected companies are archived and won't re-enter the pipeline unless manually reset.

---

## 6. Stage 4 — Email Drafting (Writer + Critic)

**Files:** `agents/writer/writer_agent.py`, `agents/writer/critic_agent.py`, `agents/writer/llm_connector.py`
**Trigger:** Manual via Triggers page ("Generate Drafts"), or Airflow schedule
**LLM:** Ollama llama3.2 (local, free) or OpenAI gpt-4o-mini (configurable)
**Agentic concepts:**
- **Context-Aware Generation** — reads `score_reason` + all company signals, reasons about best angle
- **Self-Critique / Reflection Loop** — Critic is a separate LLM call that scores the output
- **Learning from Feedback** — `email_win_rate` table biases angle selection toward what worked
- **Uncertainty Flagging** — `low_confidence=true` if draft never reaches 7/10 after rewrites
- **Graceful Degradation** — no contact? Generic draft instead of skip

### Writing Process Per Company

```
Load from DB:
  company → name, industry, city, state, website
  company_features → site_count, savings_mid, deregulated_state
  lead_scores → score, tier, score_reason  ← KEY input
  contacts → full_name, title, email

Query email_win_rate → best angle for this industry (if ≥5 data points)

Writer LLM call:
  System prompt: role as senior utility sales consultant
  Prompt includes: company profile + contact + score_reason + angle hint
  Output: SUBJECT: ... ANGLE: ... BODY: ... (150–180 words)

         ↓ draft v1

Critic LLM call — scores on 5 criteria × 2 points each:
  1. Personalization   — mentions company name or specific detail
  2. Savings figure    — contains a dollar or % estimate
  3. Clear CTA         — one specific ask (call, audit, reply)
  4. Human tone        — reads naturally, not template-like
  5. Subject line      — specific to company, not generic

Score ≥ 7 → save draft
Score < 7 → Writer rewrites with Critic feedback (max 2 rewrites)
Still < 7 after 2 rewrites → save with low_confidence = true

Save to email_drafts:
  subject_line, body, template_used (angle), critic_score,
  low_confidence, rewrite_count, contact_id, company_id
  approved_human = false (awaits human review)

Set company.status = 'draft_created'
```

### Email Angles

| Angle | Lead with |
|---|---|
| `cost_savings` | Dollar savings estimate up front |
| `audit_offer` | Free no-commitment energy audit |
| `risk_reduction` | Utility cost volatility and budget risk |
| `multi_site_savings` | Multi-location efficiency opportunity |
| `deregulation_opportunity` | Open energy market / supplier switch |

### LLM Calls Per Email (Worst Case)

| Step | Calls | ~Tokens |
|---|---|---|
| Writer (initial) | 1 | ~600 |
| Critic (evaluation) | 1 | ~400 |
| Writer (rewrite) | 0–2 | ~600 each |
| Critic (re-evaluation) | 0–2 | ~400 each |
| **Total worst case** | **6** | **~3,000** |

With Ollama llama3.2 locally: ~15–40s per email.

---

## 7. Stage 5 — Human Email Review

**Page:** `/emails/review` (Email Review Queue)
**Who does this:** Consultant who will be sending the emails

Every draft appears as a collapsed card showing:
- Company name
- Contact name / title / email
- Subject line preview
- AI critic score badge (`8.5/10 ✓` or `5.0/10 ⚠`)
- Low confidence warning if applicable
- Number of drafts if multiple contacts at same company

**Click to expand** → full email-client view (FROM / TO / SUBJECT / BODY)

**Actions:**
| Action | What happens |
|---|---|
| **Approve & Send** | Marks draft approved, triggers SendGrid send |
| **Edit + Approve** | Inline edit subject/body, then send edited version |
| **Reject** | Deletes draft, resets company to `approved` (re-enters writer queue) |
| **Regenerate** | Triggers a fresh Writer + Critic cycle for this company |
| **Bulk Approve** | Select all high-score leads, approve in one click |

**Contact filter:** Toggle between All / Named Contact / Generic to separate drafts where a real person was found vs. generic company-addressed emails.

---

## 8. Stage 6 — Send (SendGrid)

**File:** `agents/outreach/email_sender.py`
**Provider:** SendGrid (`EMAIL_PROVIDER=sendgrid`)
**From:** `your-configured-sender@yourdomain.com` (Your Company Name)

### Send Flow

```
Human clicks "Approve & Send"
        ↓
API: POST /emails/{draft_id}/approve
        ↓
email_sender.send_email(draft_id, db_session)
        ↓
Checks:
  - contact.unsubscribed == false
  - daily send count < EMAIL_DAILY_LIMIT (50/day)
  - contact.email is not empty
        ↓
Appends unsubscribe footer to body
        ↓
Calls SendGrid API:
  from: your-configured-sender@yourdomain.com
  to: contact.email (contact.full_name)
  subject: draft.subject_line
  body: plain text + HTML (line breaks → <br>)
  tracking: open_tracking=true, click_tracking=true
        ↓
SendGrid returns HTTP 202 + X-Message-Id header
        ↓
Logs OutreachEvent: event_type='sent', company_id, contact_id, draft_id, message_id
        ↓
Schedules 3 follow-up events (followup_scheduler.schedule_followups)
        ↓
Sets company.status = 'contacted'
        ↓
Pushes Contact + Deal to HubSpot (deal stage = "Contacted")  ← planned
```

### Daily Limits & Safety

- Max 50 emails/day (configurable via `EMAIL_DAILY_LIMIT`)
- Unsubscribed contacts are automatically skipped
- `SMTP_TEST_MODE=true` in `.env` logs email content but doesn't send (safe for dev)

---

## 9. Stage 7 — Follow-up Sequence

**File:** `agents/outreach/followup_scheduler.py`, `agents/outreach/sequence_manager.py`
**Scheduler:** Airflow DAG `daily_tracker_dag.py` (runs once per day)

After initial send, three follow-up rows are written to `outreach_events` with `event_type='scheduled_followup'` and a `next_followup_date`.

### Schedule

| Follow-up | Day offset | Subject |
|---|---|---|
| #1 | Day 3 | `Re: <original subject>` |
| #2 | Day 7 | `Re: <original subject>` |
| #3 | Day 14 | `"Following up one last time"` |

Day offsets configured via `.env`: `FOLLOWUP_DAY_1=3`, `FOLLOWUP_DAY_2=7`, `FOLLOWUP_DAY_3=14`

### Daily Airflow Job

Each day the DAG runs:
1. `get_due_followups()` — queries `outreach_events` where `next_followup_date <= today` AND `sales_alerted=false` AND company not already replied
2. For each due follow-up: `sequence_manager.build_followup_email()` — LLM polishes a template using original draft context (same company signals, same contact)
3. Sends via SendGrid
4. Marks `sales_alerted=true` to prevent duplicate sends
5. After follow-up #3 sent with no reply → `mark_sequence_complete()` → `company.status = 'no_response'`

### Cancellation

Follow-ups are automatically cancelled when:
- A reply is detected (`cancel_followups()` called by webhook handler)
- Contact unsubscribes
- Company status manually changed to `won` or `lost`

---

## 10. Stage 8 — Reply Detection & Meeting Booking

### Reply Detection

**Current gap:** SendGrid sends outbound email but cannot receive inbound replies. Two options:

**Option A — HubSpot Inbound (recommended)**
- Emails are sent from `your-configured-sender@yourdomain.com`
- Replies land in HubSpot inbox (connected email)
- HubSpot fires a webhook to `POST /api/webhooks/hubspot/reply`
- API handler:
  1. Matches `contact.email` to find the company
  2. Logs `OutreachEvent(event_type='replied')`
  3. Calls `cancel_followups()` — stops the sequence
  4. Sets `company.status = 'replied'`
  5. Updates HubSpot deal stage → "Replied"
  6. Sends internal Slack/email alert to sales team

**Option B — SendGrid Inbound Parse**
- Configure SendGrid Inbound Parse to POST raw email to your API
- Same handler logic as above

### Meeting Booking

Follow-up #2 (Day 7) includes a HubSpot scheduling link in the email body:
```
"Happy to jump on a quick 20-minute call — here's my calendar: [HubSpot meeting link]"
```

When contact books:
- HubSpot fires meeting booked webhook → `POST /api/webhooks/hubspot/meeting`
- API handler:
  1. Logs `OutreachEvent(event_type='meeting_booked')`
  2. Sets `company.status = 'meeting_booked'`
  3. Cancels remaining follow-ups
  4. Updates HubSpot deal stage → "Meeting Booked"

---

## 11. HubSpot Integration Layer

HubSpot acts as the **CRM face** of the platform — the sales team sees their pipeline there. The platform remains the **intelligence layer** — discovery, scoring, writing, and scheduling all stay here.

### Data Flow

```
Platform  ──────────────────→  HubSpot
  companies + contacts         Contacts + Deals
  company.status               Deal Stage
  email sent                   Activity logged

HubSpot  ──────────────────→  Platform
  reply received               POST /webhooks/hubspot/reply
  meeting booked               POST /webhooks/hubspot/meeting
  contact unsubscribed         POST /webhooks/hubspot/unsubscribe
```

### Stage Mapping

| Platform Status | HubSpot Deal Stage |
|---|---|
| `contacted` | Contacted |
| `replied` | Replied |
| `meeting_booked` | Meeting Booked |
| `won` | Closed Won |
| `lost` / `no_response` | Closed Lost |

### Import Direction

HubSpot → Platform (one-way import):
- Pull existing contacts → enter scoring pipeline
- Keeps platform as source of truth for outreach
- HubSpot is not written to during import (no duplicates created)

---

## 12. Data Model Summary

### Core Tables

```
companies
  id, name, website, industry, city, state, phone
  site_count, employee_count
  status        ← drives the pipeline stage
  source        ← 'scout' | 'hubspot_import' | 'manual'
  created_at, updated_at

contacts
  id, company_id
  full_name, title, email, linkedin_url
  source        ← 'apollo' | 'hubspot_import' | 'manual'
  verified, unsubscribed

company_features
  id, company_id, computed_at
  site_count, employee_count
  savings_low, savings_mid, savings_high
  estimated_total_spend
  deregulated_state, multi_site_confirmed
  industry_fit_score, data_quality_score

lead_scores
  id, company_id, scored_at
  score (0–100), tier (high/medium/low)
  score_reason  ← LLM-written plain English explanation
  approved_human, approved_by, approved_at

email_drafts
  id, company_id, contact_id
  subject_line, body, template_used (angle)
  critic_score, low_confidence, rewrite_count
  approved_human, approved_by, approved_at
  sent_at, status

outreach_events
  id, company_id, contact_id, email_draft_id
  event_type    ← 'sent' | 'scheduled_followup' | 'replied' |
                   'meeting_booked' | 'cancelled_followup' | 'followup_sent'
  event_at, next_followup_date
  follow_up_number (0=initial, 1/2/3=follow-ups)
  sales_alerted, reply_content, reply_sentiment

agent_runs
  id, status, current_stage, trigger_source
  companies_found, companies_scored, companies_approved
  drafts_created, emails_sent
  error_message, created_at

email_win_rate
  id, template_id (angle), industry
  emails_sent, replies_received, reply_rate
  last_updated  ← Writer reads this to bias angle selection
```

---

## 13. Tech Stack Reference

| Layer | Technology | Purpose |
|---|---|---|
| **Backend API** | FastAPI (Python) | REST endpoints, agent triggers, webhooks |
| **Database** | PostgreSQL | All persistent data |
| **ORM** | SQLAlchemy | DB access layer |
| **LLM (local)** | Ollama + llama3.2 | Scoring reasoning, email writing, critic |
| **LLM (cloud)** | OpenAI gpt-4o-mini | Optional swap via `LLM_PROVIDER=openai` |
| **Lead Discovery** | Tavily Search API | News-mode search for company signals |
| **Contact Enrichment** | Apollo.io API | Find contacts at target companies |
| **Email Send** | SendGrid API | Transactional email with open/click tracking |
| **Scheduler** | Apache Airflow | Daily follow-up DAG, scheduled pipeline runs |
| **Frontend** | React + Tailwind CSS | Dashboard, leads table, email review queue |
| **CRM** | HubSpot | Reply detection, meeting booking, sales team view |
| **Containerization** | Docker / Docker Compose | Local and production deployment |
| **Config** | `.env` file + Pydantic Settings | All credentials and tunable parameters |

---

## 14. Company Status Lifecycle

```
new
 ↓  (Analyst enriches)
enriched
 ↓  (Analyst scores)
scored
 ↓  (Human approves on Leads page)
approved
 ↓  (Writer creates email draft)
draft_created
 ↓  (Human approves on Email Review page → email sent)
contacted
 ↓
 ├──→ replied         (reply detected via HubSpot webhook)
 │       ↓
 │    meeting_booked  (HubSpot meeting webhook)
 │       ↓
 │    won             (deal closed — manual update)
 │
 └──→ no_response     (all 3 follow-ups sent, no reply)
         ↓
      lost            (manually marked, or after defined wait period)

Any stage → archived  (human rejects on Leads page)
```

---

## 15. Agent Responsibilities

| Agent | File | Trigger | What it does |
|---|---|---|---|
| **Scout** | `agents/scout/scout_agent.py` | Manual / Airflow | Tavily search → extract companies with utility spend signals |
| **Analyst** | `agents/analyst/analyst_agent.py` | Manual / Airflow | Apollo enrichment + LLM scoring for all `new`/`enriched` companies |
| **Writer** | `agents/writer/writer_agent.py` | Manual / Airflow | LLM email drafting for all `approved` companies with no draft |
| **Critic** | `agents/writer/critic_agent.py` | Called by Writer | Scores draft 0–10 on 5 criteria, returns feedback for rewrite |
| **Outreach** | `agents/outreach/outreach_agent.py` | Called after send | Schedules 3 follow-up events, sends due follow-ups |
| **Tracker** | `agents/tracker/tracker_agent.py` | Airflow daily | Detects stuck pipeline, marks sequences complete, updates win rates |
| **Orchestrator** | `agents/orchestrator/orchestrator.py` | API trigger | Coordinates agent run order, manages `AgentRun` state, live progress |

---

## Appendix — Key Configuration Parameters

```env
# LLM
LLM_PROVIDER=ollama              # 'ollama' or 'openai'
LLM_MODEL=llama3.2
OLLAMA_BASE_URL=http://192.168.65.254:11434

# Email Send
EMAIL_PROVIDER=sendgrid
SENDGRID_FROM_EMAIL=your-configured-sender@yourdomain.com
EMAIL_DAILY_LIMIT=50

# Follow-up Schedule
FOLLOWUP_DAY_1=3
FOLLOWUP_DAY_2=7
FOLLOWUP_DAY_3=14

# Enrichment
APOLLO_API_KEY=...
TAVILY_API_KEY=...

# HubSpot (planned)
HUBSPOT_API_KEY=...
HUBSPOT_PORTAL_ID=...
HUBSPOT_MEETING_LINK=...

# Brand
TB_BRAND_NAME=Your Company
TB_OFFICE_LOCATION=your-city, your-state
TB_SENDER_NAME=Your Company Name
```

---

*Last updated: 2026-03-27*
*Platform: Utility Lead Outreach Automation — Your Company Name, Buffalo NY*
