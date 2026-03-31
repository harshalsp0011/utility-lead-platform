# System Architecture

> Full pipeline: Lead Discovery → Enrichment → Scoring → Email Drafting → Human Review → Send → Follow-up → Reply Detection → Meeting Booked

---

## Platform Overview

This platform automates the full outbound sales pipeline — from discovering companies with high utility spend to booking a first meeting — with human approval checkpoints at two critical stages before any email is sent.

**Core principle:** AI does the research, writing, and scheduling. A human approves before outreach begins. No email is ever sent without explicit human sign-off.

**Three lead sources:**
- **AI-discovered:** Scout agent finds companies across multiple live data sources
- **CRM import:** Existing contacts pulled from any CRM with a contacts API *(planned)*
- **Manual add:** Sales team adds a company directly via form *(planned)*

All three paths enter the same pipeline and receive the same quality of research and outreach.

**What makes this agentic:** Each stage is not a simple function call — agents Observe available data, Reason about what to do using an LLM, Act by calling tools (APIs, DB writes, LLM calls), and Reflect on results (quality scores, retry decisions, learning loops).

---

## High-Level Pipeline

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

## Stage 1 — Lead Ingestion (Scout Agent)

**File:** `agents/scout/scout_agent.py`  
**Trigger:** Manual via Triggers page, or Airflow schedule  
**Agentic concepts:** LLM Query Planning, Tool Use, LLM Deduplication, Source Performance Learning

### How Scout Finds Companies

Scout does not use one fixed search query. The LLM generates 3–5 query variants for each run, then searches across four source types:

| Source Type | File | What it finds |
|---|---|---|
| Directory scraper | `directory_scraper.py` | Companies from configured B2B directories |
| Tavily news search | `search_client.py` | Companies in live news with utility spend signals |
| Google Maps | `google_maps_client.py` | Local businesses by industry + location |
| Yelp | `yelp_client.py` | Local businesses, particularly hospitality and retail |

### LLM Query Planning

Instead of a fixed query string, `llm_query_planner.py` takes `{industry}` + `{location}` and outputs 3–5 search variants:
```
"healthcare facilities Buffalo NY utility costs"
"hospital expansion Buffalo NY energy"
"multi-site medical group western new york"
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

**Output:** New rows in `companies` with `status='new'`, `source='scout'`

---

## Stage 2 — Enrichment & Scoring (Analyst Agent)

**Files:** `agents/analyst/analyst_agent.py`, `agents/analyst/enrichment_client.py`, `agents/analyst/score_engine.py`, `agents/analyst/spend_calculator.py`  
**Agentic concepts:** LLM Inspector, Re-enrichment Loop, Contact Waterfall, Deterministic Scoring with LLM Narration

### LLM Inspector

Before scoring, `llm_inspector.py` runs for every company:
1. **Industry inference** — if `company.industry` is blank, LLM infers from name + website
2. **Data gap detection** — checks for missing: employee_count, site_count, industry, contact
3. **Re-enrich decision** — if gaps found, triggers a second enrichment pass (max 2 loops)

Skipped entirely if: industry is known AND employee_count > 0 AND site_count > 0.

### Contact Enrichment Waterfall (8 Sources)

`enrichment_client.py` runs a waterfall stopping at the first successful contact:

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

### Score Formula (Deterministic Math — NOT LLM)

`score_engine.py` computes a 0–100 score:
```
score = (Recovery × 0.40) + (Industry × 0.25) + (Multisite × 0.20) + (DataQuality × 0.15)
```

| Component | Max | How measured |
|---|---|---|
| Recovery | 40 | Savings potential relative to industry benchmark |
| Industry | 25 | Healthcare/manufacturing/data center score highest |
| Multisite | 20 | Confirmed multi-site = 20, single site = 0 |
| DataQuality | 15 | How many key fields are populated |

**Tiers:** ≥70 = high | 40–69 = medium | 0–39 = low

### Spend Calculation

`spend_calculator.py` uses `database/seed_data/industry_benchmarks.json`:
```
total_spend  = site_count × avg_sqft × kWh_per_sqft × electricity_rate_per_state
savings_low  = total_spend × 10%
savings_mid  = total_spend × 13.5%
savings_high = total_spend × 17%
```

### LLM Score Narration

After the deterministic score is computed, the LLM writes a plain-English `score_reason` (2–3 sentences). This is what the Writer reads to personalize emails. The LLM does not set the score — only explains it.

---

## Stage 3 — Human Lead Approval (HITL Gate 1)

**Page:** `/leads`

The Leads page shows all scored companies. For each: score bar, tier badge, savings estimate, contact indicator, Approve / Reject actions.

- **Approve** → `company.status='approved'`, `lead_scores.approved_human=True`
- **Reject** → `company.status='archived'`

After scoring, the Orchestrator sends a notification email to `ALERT_EMAIL` with the lead list and a link to the Leads page.

**Auto-approval shortcut:** When contact enrichment succeeds on a high-tier lead, the system auto-approves (`approved_by="system (contact found)"`) so those leads flow directly to the Writer without a manual click.

---

## Stage 4 — Email Drafting (Writer + Critic)

**Files:** `agents/writer/writer_agent.py`, `agents/writer/critic_agent.py`  
**Agentic concepts:** Context-Aware Generation, Self-Critique Loop, Win-Rate Learning, Uncertainty Flagging

### Writing Process

```
Load context:
  company          → name, industry, city, state, website
  company_features → site_count, savings_mid, deregulated_state
  lead_scores      → score, tier, score_reason  ← key personalization input
  contacts         → full_name, title, email

Query email_win_rate → best performing angle for this industry (min 5 samples)

Writer LLM:
  System prompt: senior utility sales consultant persona
  Output: SUBJECT / ANGLE / BODY (150–180 words, plain text)
              ↓ draft v1
Critic LLM — 5 criteria × 0–2 points each (max 10):
  1. Personalization  — mentions company name or specific signal
  2. Savings figure   — contains a dollar or % estimate
  3. Clear CTA        — one specific ask (call, audit, reply)
  4. Human tone       — reads naturally, not templated
  5. Subject line     — specific to company, not generic

Score ≥ 7.0 → save draft
Score < 7.0 → rewrite with Critic feedback (max 2 rewrites)
Still < 7.0 → save with low_confidence=True
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

---

## Stage 5 — Human Email Review (HITL Gate 2)

**Page:** `/emails/review`

Every draft appears as a card with: company + contact, subject preview, Critic score badge, low confidence warning.

| Action | What happens |
|---|---|
| **Approve & Send** | Marks draft approved → triggers send |
| **Edit + Approve** | Inline edit subject/body → send edited version |
| **Reject** | Deletes draft, resets `company.status='approved'` → re-enters Writer queue |
| **Regenerate** | Fresh Writer + Critic cycle for this company |

---

## Stage 6 — Send (Outreach Agent)

**File:** `agents/outreach/email_sender.py`  
**Providers:** SendGrid (default) or Instantly (configurable via `EMAIL_PROVIDER`)

```
Human clicks "Approve & Send"
        ↓
email_sender.send_email(draft_id, db)
        ↓
Guardrail checks:
  1. contact.unsubscribed == False
  2. sent_today < EMAIL_DAILY_LIMIT (default: 50)
  3. contact.email is not empty
        ↓
Unsubscribe footer appended
        ↓
SendGrid POST → open + click tracking enabled
        ↓
INSERT outreach_events(event_type='sent')
        ↓
followup_scheduler.schedule_followups() → 3 × scheduled_followup rows
        ↓
company.status = 'contacted'
```

---

## Stage 7 — Follow-up Sequence

**Files:** `agents/outreach/followup_scheduler.py`, `agents/outreach/sequence_manager.py`

| Follow-up | Day offset | Subject line |
|---|---|---|
| #1 | Day 3 | `Re: {original subject}` |
| #2 | Day 7 | `Re: {original subject}` |
| #3 | Day 14 | `"Following up one last time"` |

**Daily job:** `get_due_followups()` → `build_followup_email()` (LLM polishes body) → `send_email()` → after #3: `mark_sequence_complete()` → `company.status='no_response'`

**Automatic cancellation:** when reply received, contact unsubscribes, or company status reaches `won` / `lost`.

---

## Stage 8 — Reply Detection & Tracking (Tracker Agent)

**Files:** `agents/tracker/webhook_listener.py`, `agents/tracker/reply_classifier.py`, `agents/tracker/status_updater.py`, `agents/tracker/alert_sender.py`

### SendGrid Webhook Receiver

`webhook_listener.py` — FastAPI on port 8002:
- Validates HMAC signature
- Normalizes event types: `open→opened`, `bounce→bounced`, `inbound→replied`
- Always returns HTTP 200 (prevents retry storms)

### Reply Classification

```
Try: LLM classify_reply_sentiment(text)
  → validates {sentiment, intent, summary, confidence}
  → if invalid → fallback

Fallback: rule_based_classify(text)
  → keyword matching:
     unsubscribe keywords  → negative / unsubscribe
     meeting/interest      → positive / wants_meeting
     info request          → positive / wants_info
     not interested        → negative / not_interested
     default               → neutral / other
```

### Event Handling

| Event | Action |
|---|---|
| `replied` | Classify → `status=replied` → cancel follow-ups → alert sales if positive |
| `unsubscribed` | `contact.unsubscribed=True` → cancel follow-ups → if no active contacts: `status=archived` |
| `bounced` | `contact.verified=False` → log event |
| `opened` | Log event only (no status change) |

---

## Orchestrator

**Files:** `agents/orchestrator/orchestrator.py`, `agents/orchestrator/task_manager.py`

```
run_full_pipeline(industry, location, count, db)
  1. task_manager.assign_task("scout")
  2. task_manager.assign_task("analyst")
     → HumanApprovalRequest + ALERT_EMAIL notification
     [HUMAN APPROVES LEADS]
  3. run_contact_enrichment(high_ids)
     → auto-approves leads where contact found
  4. task_manager.assign_task("writer")
     → HumanApprovalRequest + ALERT_EMAIL notification
     [HUMAN REVIEWS DRAFTS]
```

`task_manager.py` routes each agent call, tracks tasks in `_TASK_LOG` (in-process dict), writes to `logs/task_log.txt`, and provides two-pass retry on failure.

`pipeline_monitor.py` provides: stage funnel counts, active pipeline value rollup, 7-service health checks, and 4-condition stuck pipeline detection.

---

## Data Model Summary

### Core Tables

```
companies
  id, name, website, industry, city, state, phone
  status  ← drives pipeline stage
  source  ← 'scout' | 'crm_import' | 'manual'

contacts
  id, company_id, full_name, title, email
  source  ← 'hunter' | 'apollo' | 'scrape' | ...
  verified, unsubscribed

company_features
  company_id, site_count, employee_count
  savings_low, savings_mid, savings_high
  estimated_total_spend, deregulated_state

lead_scores
  company_id, score (0–100), tier
  score_reason  ← LLM-written plain English
  approved_human, approved_by, approved_at

email_drafts
  company_id, contact_id
  subject_line, body, template_used (angle)
  critic_score, low_confidence, rewrite_count
  approved_human, sent_at

outreach_events
  company_id, contact_id
  event_type  ← 'sent' | 'scheduled_followup' | 'followup_sent' |
                'replied' | 'opened' | 'clicked' | 'bounced' |
                'unsubscribed' | 'cancelled_followup'
  follow_up_number, next_followup_date
  reply_content, reply_sentiment

agent_runs + agent_run_logs   ← full audit trail per pipeline trigger

email_win_rate                ← reply rate per angle per industry (Writer reads)
source_performance            ← quality score per Scout source (Scout reads)
human_approval_requests       ← HITL queue for leads and email approvals
```

---

## Company Status Lifecycle

```
new
 └─ enriched           (Analyst: contact waterfall succeeded)
     └─ scored         (Analyst: score + savings computed)
         └─ approved   ← HITL Gate 1 (human approves on Leads page)
                         OR auto-approved when contact found (high-tier)
             └─ draft_created   (Writer: email draft saved)
                 └─ contacted   (Outreach: email sent)
                     ├─ replied         ← reply detected
                     │   └─ meeting_booked
                     │       ├─ won
                     │       └─ lost
                     └─ no_response     ← all 3 follow-ups sent, no reply

Any status → archived  (human rejects, or all contacts unsubscribed)
```

---

## Agent Responsibilities

| Agent | File | Trigger | Responsibility |
|---|---|---|---|
| **Scout** | `agents/scout/scout_agent.py` | Manual / Airflow | LLM query planning → multi-source search → LLM dedup → companies saved |
| **Analyst** | `agents/analyst/analyst_agent.py` | Manual / Airflow | LLM inspect → 8-source contact waterfall → deterministic score → LLM narration |
| **Writer** | `agents/writer/writer_agent.py` | Manual / Airflow | Win-rate angle selection → LLM draft → Critic score → rewrite loop → save draft |
| **Critic** | `agents/writer/critic_agent.py` | Called by Writer | Score draft 0–10 on 5 criteria, return feedback for rewrite |
| **Outreach** | `agents/outreach/outreach_agent.py` | Manual / send event | Send approved emails, schedule follow-ups, send due follow-ups |
| **Tracker** | `agents/tracker/tracker_agent.py` | SendGrid webhooks + Airflow | Classify replies, update statuses, cancel follow-ups, alert sales, daily health checks |
| **Orchestrator** | `agents/orchestrator/orchestrator.py` | API trigger | Sequence agents, manage HITL notifications, retry on failure, pipeline monitoring |
| **Chat** | `agents/chat_agent.py` | User message | LangChain ReAct — routes natural language to pipeline actions, confidence-gated routing |

---

## Key Configuration Parameters

```env
# LLM
LLM_PROVIDER=ollama              # 'ollama' or 'openai'
LLM_MODEL=llama3.2
OLLAMA_BASE_URL=http://host.docker.internal:11434

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
YELP_API_KEY=...

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
```
