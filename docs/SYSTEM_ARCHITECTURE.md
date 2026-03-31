# System Architecture — Utility Lead Intelligence Platform

> Full pipeline: Lead Discovery → Enrichment → Scoring → Email Drafting → Human Review → Send → Follow-up → Reply Detection → Meeting Booked

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [High-Level Pipeline](#2-high-level-pipeline)
3. [Stage 1 — Lead Ingestion (Scout Agent)](#3-stage-1--lead-ingestion-scout-agent)
4. [Stage 2 — Enrichment & Scoring (Analyst Agent)](#4-stage-2--enrichment--scoring-analyst-agent)
5. [Stage 3 — Human Lead Approval (HITL Gate 1)](#5-stage-3--human-lead-approval-hitl-gate-1)
6. [Stage 4 — Email Drafting (Writer + Critic)](#6-stage-4--email-drafting-writer--critic)
7. [Stage 5 — Human Email Review (HITL Gate 2)](#7-stage-5--human-email-review-hitl-gate-2)
8. [Stage 6 — Send (Outreach Agent)](#8-stage-6--send-outreach-agent)
9. [Stage 7 — Follow-up Sequence](#9-stage-7--follow-up-sequence)
10. [Stage 8 — Reply Detection & Tracking (Tracker Agent)](#10-stage-8--reply-detection--tracking-tracker-agent)
11. [Orchestrator](#11-orchestrator)
12. [CRM Integration Layer](#12-crm-integration-layer)
13. [Data Model Summary](#13-data-model-summary)
14. [Tech Stack Reference](#14-tech-stack-reference)
15. [Company Status Lifecycle](#15-company-status-lifecycle)
16. [Agent Responsibilities](#16-agent-responsibilities)
17. [Key Configuration Parameters](#17-key-configuration-parameters)

---

## 1. Platform Overview

This platform automates the full outbound sales pipeline — from discovering companies with high utility spend to booking a first meeting — with human approval checkpoints at two critical stages before any email is sent.

**Core principle:** AI does the research, writing, and scheduling. A human approves before outreach begins. No email is ever sent without explicit human sign-off.

**Three lead sources:**
- **AI-discovered:** Scout agent finds companies across multiple live data sources
- **CRM import:** Existing contacts pulled from any CRM with a contacts API *(planned)*
- **Manual add:** Sales team adds a company directly via form *(planned)*

All three paths enter the same pipeline and receive the same quality of research and outreach.

**What makes this agentic:** Each stage is not a simple function call — agents Observe available data, Reason about what to do using an LLM, Act by calling tools (APIs, DB writes, LLM calls), and Reflect on results (quality scores, retry decisions, learning loops). See `docs/AGENTIC_DESIGN.md` for the full breakdown.

---

## 2. High-Level Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│  LEAD SOURCES                                                        │
│                                                                      │
│  [Scout Agent]              [CRM Import]        [Manual Add]        │
│  Google Maps + Yelp +       Pull existing       Sales team form     │
│  Tavily + directories       CRM contacts        one-off lead        │
│  LLM query planning         (planned)           (planned)           │
└───────────────────────────────┬──────────────────────────────────────┘
                                ↓
                   companies + contacts tables
                                ↓
┌──────────────────────────────────────────────────────────────────────┐
│  ANALYST AGENT                                                       │
│  LLM inspector → 8-source contact waterfall                         │
│  Deterministic score (0–100) + tier + LLM-written score_reason      │
└───────────────────────────────┬──────────────────────────────────────┘
                                ↓
                   ⚠️  HUMAN CHECKPOINT 1 — Leads page
                       Approve or reject each scored lead
                                ↓
┌──────────────────────────────────────────────────────────────────────┐
│  WRITER + CRITIC AGENTS                                              │
│  LLM picks angle (win-rate biased) → writes personalized email      │
│  Critic scores 0–10 on 5 criteria → rewrite if <7 (max 2×)         │
└───────────────────────────────┬──────────────────────────────────────┘
                                ↓
                   ⚠️  HUMAN CHECKPOINT 2 — Email Review page
                       Edit / Approve / Reject / Regenerate
                                ↓
┌──────────────────────────────────────────────────────────────────────┐
│  OUTREACH AGENT — Send                                               │
│  SendGrid (or Instantly) → open + click tracking                    │
│  Unsubscribe guard + daily cap (50/day)                             │
└───────────────────────────────┬──────────────────────────────────────┘
                      ┌─────────┴─────────┐
                      ↓                   ↓
        ┌─────────────────────┐   ┌───────────────────────┐
        │  FOLLOW-UP SEQUENCE │   │  CRM SYNC (planned)   │
        │  Day 3 → Follow-up 1│   │  Create deal on send  │
        │  Day 7 → Follow-up 2│   │  Update stage on reply│
        │  Day 14 → Follow-up3│   └───────────────────────┘
        └──────────┬──────────┘
                   ↓
┌──────────────────────────────────────────────────────────────────────┐
│  TRACKER AGENT                                                       │
│  SendGrid webhook → reply classification (LLM + rule-based)         │
│  Cancel follow-ups → update status → alert sales on hot replies     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Stage 1 — Lead Ingestion (Scout Agent)

**File:** `agents/scout/scout_agent.py`
**Trigger:** Manual via Triggers page, or Airflow schedule
**Agentic concepts:** LLM Query Planning, Tool Use, LLM Deduplication, Source Performance Learning

### How Scout Finds Companies

Scout does not use one fixed search query. The LLM generates 3–5 query variants for each run, then searches across four source types in parallel:

| Source Type | Tools | What it finds |
|---|---|---|
| Directory scraper | `directory_scraper.py` | Companies from configured B2B directories |
| Tavily news search | `search_client.py` | Companies in live news with utility spend signals |
| Google Maps | `google_maps_client.py` | Local businesses by industry + location |
| Yelp | `yelp_client.py` | Local businesses, particularly hospitality and retail |

After all sources return results, `website_crawler.py` enriches each company with website data, then `company_extractor.py` parses structured fields from raw HTML.

### LLM Query Planning

Instead of a fixed query string, the LLM (`llm_query_planner.py`) takes `{industry}` + `{location}` and outputs 3–5 search variants designed to surface different aspects of high utility spend:
```
"healthcare facilities Buffalo NY utility costs"
"hospital expansion Buffalo NY energy"
"multi-site medical group western new york"
...
```

### Deduplication

Two-pass deduplication:
1. **Rule-based:** Exact domain match against existing `companies` rows
2. **LLM near-duplicate:** `llm_deduplicator.py` runs `SequenceMatcher(ratio > 0.75)` on company names + asks LLM to confirm ambiguous matches

### Source Performance Learning

After each run, Scout writes a quality score per source to `source_performance`:
```
quality = (% with website × 5) + (% with city × 3) + (% with phone × 2)
```
Future runs rank sources by `avg_quality_score` — high-performing sources get priority.

**Output:** New rows in `companies` table with `status='new'`, `source='scout'`

---

## 4. Stage 2 — Enrichment & Scoring (Analyst Agent)

**Files:** `agents/analyst/analyst_agent.py`, `agents/analyst/enrichment_client.py`, `agents/analyst/score_engine.py`, `agents/analyst/spend_calculator.py`
**Trigger:** Manual via Triggers page ("Run Analyst"), or Airflow schedule
**Agentic concepts:** LLM Inspector, Re-enrichment Loop, Contact Waterfall, Deterministic Scoring with LLM Narration

### LLM Inspector (Phase A)

Before scoring, `llm_inspector.py` runs for every company:
1. **Industry inference** — if `company.industry` is blank, LLM infers from name + website
2. **Data gap detection** — LLM checks for missing: employee_count, site_count, industry, contact
3. **Re-enrich decision** — if gaps found, triggers a second enrichment pass (max 2 loops total)

LLM inspector is **skipped entirely** if: industry is known AND employee_count > 0 AND site_count > 0. This keeps costs low for well-populated records.

### Contact Enrichment Waterfall (8 Sources)

For each company, `enrichment_client.py` runs a waterfall stopping at the first successful contact:

```
1. Hunter.io          → domain-based email finder
2. Apollo.io          → people search by company domain
3. Website scraper    → /contact, /about, /team page scan
4. Serper             → "CFO site:{domain}" Google result
5. Snov.io            → company domain search
6. Prospeo            → LinkedIn-backed contact lookup
7. ZeroBounce         → email verification + contact
8. Permutation        → firstname.lastname@domain pattern generation
```

**Target titles (priority order):** CFO → VP Finance → Director Facilities → VP Operations

### Spend Calculation (Deterministic)

`spend_calculator.py` uses `database/seed_data/industry_benchmarks.json`:
```
total_spend = site_count × avg_sqft × kWh_per_sqft × electricity_rate_per_state
savings_low  = total_spend × 10%
savings_mid  = total_spend × 13.5%
savings_high = total_spend × 17%
```

### Score Formula (Deterministic Math — NOT LLM)

`score_engine.py` computes a 0–100 score:
```
score = (Recovery × 0.40) + (Industry × 0.25) + (Multisite × 0.20) + (DataQuality × 0.15)
```

| Component | Max | How measured |
|---|---|---|
| Recovery | 40 | Savings potential relative to industry benchmark |
| Industry | 25 | Healthcare/manufacturing/data center score highest |
| Multisite | 20 | Confirmed multi-site = full 20, single site = 0 |
| DataQuality | 15 | How many key fields are populated |

**Score thresholds:**

| Score | Tier |
|---|---|
| 70–100 | high |
| 40–69 | medium |
| 0–39 | low |

### LLM Score Narration

After the deterministic score is computed, the LLM writes a plain-English `score_reason` (2–3 sentences explaining why this company scored this way). This is what the Writer agent reads to personalize emails. The LLM does not set the score — only explains it.

---

## 5. Stage 3 — Human Lead Approval (HITL Gate 1)

**Page:** `/leads`

The Leads page shows all scored companies. For each:
- Score (0–100) with visual bar
- Tier badge (high / medium / low)
- Savings estimate (mid-range)
- Contact found indicator
- Approve / Reject actions

**Approve** → `company.status='approved'`, `lead_scores.approved_human=True`
**Reject** → `company.status='archived'`

After scoring, the Orchestrator sends a notification email to `ALERT_EMAIL` with the lead list and a link to the Leads page. Only approved companies proceed to the Writer.

**Auto-approval shortcut:** When contact enrichment succeeds on a high-tier lead, the system auto-approves (`approved_by="system (contact found)"`) so those leads flow directly to the Writer without a manual click. Manual approval is still always available.

---

## 6. Stage 4 — Email Drafting (Writer + Critic)

**Files:** `agents/writer/writer_agent.py`, `agents/writer/critic_agent.py`, `agents/writer/llm_connector.py`
**Trigger:** Manual via Triggers page ("Generate Drafts"), or Airflow schedule
**LLM:** Ollama llama3.2 (local, free) or OpenAI gpt-4o-mini (configurable)
**Agentic concepts:** Context-Aware Generation, Self-Critique Loop, Win-Rate Learning, Uncertainty Flagging

### Writing Process

```
Load context:
  company         → name, industry, city, state, website
  company_features → site_count, savings_mid, deregulated_state
  lead_scores     → score, tier, score_reason  ← key personalization input
  contacts        → full_name, title, email (fallback: "there" if no contact)

Query email_win_rate → best performing angle for this industry (min 5 samples)

Writer LLM:
  System prompt: senior utility sales consultant persona
  Context: full company profile + contact + score_reason + angle hint
  Output: SUBJECT / ANGLE / BODY (150–180 words, plain text)

              ↓ draft v1

Critic LLM — 5 criteria × 0–2 points each (max 10):
  1. Personalization  — mentions company name or specific signal
  2. Savings figure   — contains a dollar or % estimate
  3. Clear CTA        — one specific ask (call, audit, reply)
  4. Human tone       — reads naturally, not templated
  5. Subject line     — specific to company, not generic

  Code recalculates total from criteria (does not trust LLM's own total)

Score ≥ 7.0 → save draft
Score < 7.0 → Writer rewrites with Critic feedback (max 2 rewrites)
Still < 7.0 after 2 rewrites → save with low_confidence=True

Save to email_drafts: subject_line, body, template_used (angle), critic_score,
  low_confidence, rewrite_count, contact_id, company_id, approved_human=False
Set company.status = 'draft_created'
```

### Email Angles

| Angle | Lead-in |
|---|---|
| `cost_savings` | Dollar savings estimate up front |
| `audit_offer` | Free no-commitment energy audit |
| `risk_reduction` | Utility cost volatility / budget risk |
| `multi_site_savings` | Multi-location efficiency opportunity |
| `deregulation_opportunity` | Open energy market / supplier switch |

### LLM Calls Per Email (Worst Case)

| Step | Calls | ~Tokens |
|---|---|---|
| Writer (initial) | 1 | ~600 |
| Critic (evaluation) | 1 | ~400 |
| Writer (rewrite ×2) | 0–2 | ~600 each |
| Critic (re-eval ×2) | 0–2 | ~400 each |
| **Total worst case** | **6** | **~3,800** |

With Ollama llama3.2 locally: ~15–40s per email.

---

## 7. Stage 5 — Human Email Review (HITL Gate 2)

**Page:** `/emails/review`

Every draft appears as a card with:
- Company + contact name / title / email
- Subject line preview
- Critic score badge (`8.5/10 ✓` or `5.0/10 ⚠`)
- Low confidence warning if `low_confidence=True`

**Actions:**

| Action | What happens |
|---|---|
| **Approve & Send** | Marks draft approved → triggers send |
| **Edit + Approve** | Inline edit subject/body → send edited version |
| **Reject** | Deletes draft, resets `company.status='approved'` → re-enters Writer queue |
| **Regenerate** | Fresh Writer + Critic cycle for this company |

After Writer completes, the Orchestrator sends a notification email to `ALERT_EMAIL` with the draft list and a link to the Email Review page.

---

## 8. Stage 6 — Send (Outreach Agent)

**File:** `agents/outreach/email_sender.py`
**Providers:** SendGrid (default) or Instantly (configurable via `EMAIL_PROVIDER`)

### Send Flow

```
Human clicks "Approve & Send"
        ↓
API: POST /emails/{draft_id}/approve
        ↓
email_sender.send_email(draft_id, db)
        ↓
Guardrail checks (in order):
  1. contact.unsubscribed == False
  2. sent_today < EMAIL_DAILY_LIMIT (default: 50)
  3. contact.email is not empty
        ↓
Unsubscribe footer appended to body
        ↓
SendGrid API:
  POST https://api.sendgrid.com/v3/mail/send
  from: {SENDGRID_FROM_EMAIL}
  to: contact.email
  subject: draft.subject_line
  tracking: open=true, click=true
        ↓
HTTP 202 → extracts X-Message-Id
        ↓
INSERT outreach_events(event_type='sent', message_id, follow_up_number=0)
        ↓
followup_scheduler.schedule_followups() → 3 × scheduled_followup rows
        ↓
company.status = 'contacted'
        ↓
CRM push (planned) → create Deal in CRM with stage "Contacted"
```

---

## 9. Stage 7 — Follow-up Sequence

**Files:** `agents/outreach/followup_scheduler.py`, `agents/outreach/sequence_manager.py`
**Scheduler:** Airflow DAG `daily_tracker_dag.py` (or manual trigger)

After the initial send, three `OutreachEvent` rows are created with `event_type='scheduled_followup'` and `next_followup_date`.

### Schedule

| Follow-up | Day offset | Subject line |
|---|---|---|
| #1 | Day 3 (configurable) | `Re: {original subject}` |
| #2 | Day 7 (configurable) | `Re: {original subject}` |
| #3 | Day 14 (configurable) | `"Following up one last time"` |

### Daily Job

1. `get_due_followups()` — finds `scheduled_followup` rows where `next_followup_date <= today` AND company not replied AND contact not unsubscribed
2. `sequence_manager.build_followup_email()` — loads original draft context → LLM polishes body
3. `email_sender.send_email()` — same guardrail flow as first send
4. After follow-up #3 sent with no reply → `mark_sequence_complete()` → `company.status='no_response'`

### Automatic Cancellation

Follow-ups are cancelled when:
- A reply is detected (Tracker calls `cancel_followups()`)
- Contact unsubscribes
- Company status changes to `won` or `lost`

---

## 10. Stage 8 — Reply Detection & Tracking (Tracker Agent)

**Files:** `agents/tracker/webhook_listener.py`, `agents/tracker/reply_classifier.py`, `agents/tracker/status_updater.py`, `agents/tracker/alert_sender.py`
**Trigger:** SendGrid webhooks (reactive), Airflow daily health check (scheduled)

### SendGrid Webhook Receiver

`webhook_listener.py` runs as a FastAPI app on port 8002:

```
POST /webhooks/email
  ← receives SendGrid event array
  ← validates HMAC signature
  ← normalizes event types (open→opened, bounce→bounced, inbound→replied)
  ← always returns HTTP 200 (prevents retry storms)
```

### Reply Classification

For every inbound reply, `reply_classifier.py` classifies intent:

```
Try: LLM classify_reply_sentiment(text)
  → validates structure: {sentiment, intent, summary, confidence}
  → if invalid → fallback

Fallback: rule_based_classify(text)
  → keyword matching in priority order:
     unsubscribe keywords  → negative / unsubscribe
     meeting/interest      → positive / wants_meeting
     info request          → positive / wants_info
     not interested        → negative / not_interested
     default               → neutral / other
```

### Event Handling

| Event | Action |
|---|---|
| `replied` | Classify intent → update status=replied → cancel follow-ups → alert sales if positive |
| `unsubscribed` | contact.unsubscribed=True → cancel follow-ups → if no active contacts: status=archived |
| `bounced` | contact.verified=False → log bounce event |
| `opened` | Log open event (no status change) |

### Sales Alert

On positive reply (wants_meeting / wants_info):
- `alert_sender.send_email_alert()` → sends to `ALERT_EMAIL` via SendGrid
- Alert includes: company, contact, score, savings, sentiment, 2-line LLM summary, dashboard link

### Daily Health Checks

`tracker_agent.run_daily_checks()` finds companies stale > 5 days and resolves:

| Status | Condition | Action |
|---|---|---|
| `contacted` | last sent > 14 days, no reply | `mark_sequence_complete()` → no_response |
| `scored` | no EmailDraft row | Log warning → needs Writer attention |
| `draft_created` | no approved draft | Send approval reminder to `ALERT_EMAIL` |

---

## 11. Orchestrator

**File:** `agents/orchestrator/orchestrator.py`, `agents/orchestrator/task_manager.py`

The Orchestrator sequences all agents, manages task dispatch with retry, and enforces HITL gates.

### Full Pipeline Run

```
run_full_pipeline(industry, location, count, db)
  1. task_manager.assign_task("scout", {...})
  2. task_manager.assign_task("analyst", {...})
     → HumanApprovalRequest inserted + ALERT_EMAIL notification sent
     [HUMAN APPROVES LEADS]
  3. run_contact_enrichment(high_ids)
     → auto-approves leads where contact found
  4. task_manager.assign_task("writer", {...})
     → HumanApprovalRequest inserted + ALERT_EMAIL notification sent
     [HUMAN REVIEWS DRAFTS]
```

### Task Dispatch

`task_manager.py` routes each agent call, tracks every task in `_TASK_LOG` (in-process dict), appends result to `logs/task_log.txt`, and provides two-pass retry on failure.

**Note:** Outreach does not run inside `run_full_pipeline()` — it runs separately on a schedule or manual trigger.

### Pipeline Monitor

`pipeline_monitor.py` provides:
- Stage funnel counts per status
- Active pipeline value rollup (savings_low/mid/high for high-tier active leads)
- Infrastructure health checks (Postgres, Ollama, SendGrid, Tavily, Airflow)
- Stuck pipeline detection (4 stall conditions with time thresholds)

---

## 12. CRM Integration Layer

The platform is **CRM-agnostic** — it integrates with any CRM that supports a REST API and outgoing webhooks. HubSpot is the reference implementation, but the same pattern applies to Salesforce, Pipedrive, Zoho, or any comparable CRM.

The CRM is the **sales team's view**. The platform is the **intelligence and execution layer** — discovery, scoring, drafting, sending, and scheduling all stay here.

### Data Flow

```
Platform  ────────────────────→  CRM
  company enriched + scored       Contact created
  email sent                      Deal created (stage: Contacted)
  reply received                  Deal stage updated → Replied
  meeting booked                  Deal stage updated → Meeting Booked

CRM  ────────────────────────→  Platform  (planned)
  reply detected                  POST /api/webhooks/crm/reply
  meeting booked                  POST /api/webhooks/crm/meeting
```

### Stage Mapping

| Platform Status | CRM Deal Stage |
|---|---|
| `contacted` | Contacted |
| `replied` | Replied |
| `meeting_booked` | Meeting Booked |
| `won` | Closed Won |
| `lost` / `no_response` | Closed Lost |

### CRM Import (Planned)

Pull existing contacts from CRM → map to `companies` + `contacts` tables → enter scoring pipeline with `source='crm_import'`.

---

## 13. Data Model Summary

### Core Tables

```
companies
  id, name, website, industry, city, state, phone
  site_count, employee_count, contact_found
  status        ← drives pipeline stage (see lifecycle below)
  source        ← 'scout' | 'crm_import' | 'manual'
  created_at, updated_at

contacts
  id, company_id
  full_name, title, email, linkedin_url
  source        ← 'hunter' | 'apollo' | 'scrape' | 'serper' | 'snov' | 'prospeo' | 'zerobounce' | 'permutation' | 'manual'
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
  subject_line, body, template_used (angle name)
  critic_score, low_confidence, rewrite_count
  approved_human, approved_by, approved_at
  sent_at, status

outreach_events
  id, company_id, contact_id, email_draft_id
  event_type    ← 'sent' | 'scheduled_followup' | 'followup_sent' |
                   'replied' | 'opened' | 'clicked' | 'bounced' |
                   'unsubscribed' | 'cancelled_followup'
  event_at, next_followup_date
  follow_up_number  ← 0=initial, 1/2/3=follow-ups
  sales_alerted, alerted_at, reply_content, reply_sentiment

agent_runs
  id, status, current_stage, trigger_source
  companies_found, companies_scored, companies_approved
  drafts_created, emails_sent
  error_message, started_at, completed_at, created_at

agent_run_logs
  id, agent_run_id, level, message, created_at
  ← real-time progress log per run, polled by frontend chat

email_win_rate
  id, template_id (angle), industry
  emails_sent, replies_received, reply_rate
  last_updated  ← Writer reads this to bias angle selection

source_performance
  id, source_name, run_date
  companies_found, avg_quality_score
  ← Scout reads this to rank sources by past performance

human_approval_requests
  id, approval_type ('leads' | 'emails'), status ('pending' | 'actioned')
  items_count, items_summary
  notification_email, notification_sent, notification_sent_at
  created_at
```

---

## 14. Tech Stack Reference

| Layer | Technology | Purpose |
|---|---|---|
| **Backend API** | FastAPI (Python) | REST endpoints, agent triggers, webhook receivers |
| **Database** | PostgreSQL | All persistent data |
| **ORM** | SQLAlchemy | DB access layer |
| **Agent Framework** | LangChain | Connects LLM to tools; ReAct loop for Chat agent |
| **LLM (local)** | Ollama + llama3.2 | Query planning, inspection, writing, scoring, classification |
| **LLM (cloud)** | OpenAI gpt-4o-mini | Optional swap via `LLM_PROVIDER=openai` |
| **LLM Tracing** | LangSmith | Optional — traces every Thought/Action/Observation per run |
| **Lead Discovery** | Tavily Search API | News-mode search for company signals |
| **Lead Discovery** | Google Maps API | Local business search by industry + location |
| **Lead Discovery** | Yelp Fusion API | Local business search, hospitality + retail |
| **Contact Enrichment** | Hunter.io | Domain-based email finder |
| **Contact Enrichment** | Apollo.io | People search by company domain |
| **Contact Enrichment** | Serper | Google-backed contact search |
| **Contact Enrichment** | Snov.io | Company domain contact lookup |
| **Contact Enrichment** | Prospeo | LinkedIn-backed contact lookup |
| **Contact Enrichment** | ZeroBounce | Email verification + contact |
| **Email Send** | SendGrid | Transactional email, open/click tracking, inbound parse |
| **Email Send (alt)** | Instantly | Alternative send provider via `EMAIL_PROVIDER=instantly` |
| **Scheduler** | Apache Airflow | Daily follow-up DAG, scheduled pipeline runs |
| **Frontend** | React + Tailwind CSS | Dashboard, Leads page, Email Review queue, Chat |
| **CRM** | Any CRM (e.g. HubSpot) | Reply detection via webhooks, deal sync *(planned)* |
| **Containerization** | Docker + Docker Compose | 2 containers: api (port 8001) + frontend (port 3000) |
| **Config** | `.env` + Pydantic Settings | All credentials and tunable parameters |

---

## 15. Company Status Lifecycle

```
new
 └─ enriched           (Analyst: contact waterfall succeeded)
     └─ scored         (Analyst: score + savings computed)
         └─ approved   ← HITL Gate 1 (human approves on Leads page)
                         OR auto-approved when contact found on high-tier lead
             └─ draft_created   (Writer: email draft saved)
                 └─ approved    ← HITL Gate 2 (human approves on Email Review)
                     └─ contacted   (Outreach: email sent)
                         ├─ replied         ← reply detected (SendGrid / CRM webhook)
                         │   └─ meeting_booked   ← meeting scheduled
                         │       ├─ won      (deal closed — manual)
                         │       └─ lost     (deal lost — manual)
                         └─ no_response      ← all 3 follow-ups sent, no reply

Any status → archived  (human rejects lead, or all contacts unsubscribed)
```

---

## 16. Agent Responsibilities

| Agent | File | Trigger | Responsibility |
|---|---|---|---|
| **Scout** | `agents/scout/scout_agent.py` | Manual / Airflow | LLM query planning → multi-source search → LLM dedup → companies saved |
| **Analyst** | `agents/analyst/analyst_agent.py` | Manual / Airflow | LLM inspect → 8-source contact waterfall → deterministic score → LLM narration |
| **Writer** | `agents/writer/writer_agent.py` | Manual / Airflow | Win-rate angle selection → LLM draft → Critic score → rewrite loop → save draft |
| **Critic** | `agents/writer/critic_agent.py` | Called by Writer | Score draft 0–10 on 5 criteria, return feedback for rewrite |
| **Outreach** | `agents/outreach/outreach_agent.py` | Manual / send event | Send approved emails, schedule follow-ups, send due follow-ups |
| **Tracker** | `agents/tracker/tracker_agent.py` | SendGrid webhooks + Airflow | Classify replies, update statuses, cancel follow-ups, alert sales, daily health checks |
| **Orchestrator** | `agents/orchestrator/orchestrator.py` | API trigger | Sequence agents, manage HITL notifications, retry on failure, pipeline monitoring |
| **Chat** | `agents/chat_agent.py` | User message | LangChain ReAct — routes natural language to pipeline actions, 3-tier routing, background thread |

---

## 17. Key Configuration Parameters

```env
# LLM
LLM_PROVIDER=ollama              # 'ollama' or 'openai'
LLM_MODEL=llama3.2
OLLAMA_BASE_URL=http://host.docker.internal:11434
OPENAI_API_KEY=...               # only if LLM_PROVIDER=openai

# Email Send
EMAIL_PROVIDER=sendgrid          # 'sendgrid' or 'instantly'
SENDGRID_API_KEY=...
SENDGRID_FROM_EMAIL=you@yourdomain.com
EMAIL_DAILY_LIMIT=50

# Follow-up Schedule
FOLLOWUP_DAY_1=3
FOLLOWUP_DAY_2=7
FOLLOWUP_DAY_3=14

# Lead Discovery
TAVILY_API_KEY=...
GOOGLE_MAPS_API_KEY=...

# Contact Enrichment
APOLLO_API_KEY=...
HUNTER_API_KEY=...
SERPER_API_KEY=...
SNOV_API_KEY=...
PROSPEO_API_KEY=...
ZEROBOUNCE_API_KEY=...

# Notifications
ALERT_EMAIL=sales-team@yourdomain.com

# Sender Identity
SENDER_NAME=Your Name
SENDER_TITLE=Your Title
OFFICE_LOCATION=City, State

# CRM (planned)
CRM_API_KEY=...
CRM_WEBHOOK_SECRET=...
```
