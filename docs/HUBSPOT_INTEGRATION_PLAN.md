# HubSpot CRM Integration Plan
### Utility Lead Intelligence Platform

> **Status:** Planned — not yet built
> **Principle:** Our platform stays the system of record for lead discovery and AI scoring. HubSpot is the system of record for relationship management, deals, and sales rep activity. Data flows both ways — but nothing breaks if HubSpot is offline.

---

## Why HubSpot + This Platform

Right now the platform discovers leads, enriches contacts, scores them, and sends outreach. But once a reply comes in, or a sales rep adds notes, or a follow-up is scheduled — that happens in HubSpot and we never see it. The gap means:

- Leads approved here don't appear in the CRM the sales team already uses
- Follow-up schedules set by reps in HubSpot are invisible to the Writer agent
- Our tracker only sees email open/click events — not meeting outcomes, deal stages, or CRM notes
- The Writer drafts cold outreach only — it can't write context-aware follow-ups for warm CRM contacts

The integration closes all four gaps.

---

## Integration Phases

We are building this in 3 phases, one at a time.

---

## Phase 1 — Pull: Existing CRM Accounts → Our DB + Tracking Flow

**What it does:**
Batch-fetches all existing HubSpot Contacts and Companies into our `contacts` and `companies` tables. Sets up a tracking flow so every future change in HubSpot (email opened, reply received, deal stage changed, meeting booked) is reflected in our `outreach_events` table in real time.

**Why first:**
The sales team already has live accounts in HubSpot. Before we push anything new, we need to know what already exists — so we don't create duplicates and so the Writer has full history context when drafting.

### What gets pulled

| HubSpot Object | Fields pulled | Our table |
|---|---|---|
| Company | name, domain, industry, city, state, employee count, annual revenue | `companies` |
| Contact | first_name, last_name, email, job_title, phone, linkedin_url, associated_company | `contacts` |
| Deal | deal_name, stage, amount, close_date, associated_company | `lead_scores` (tier mapping) |
| Activity (email sent, opened, replied) | type, timestamp, contact_id, body | `outreach_events` |
| Note | body, timestamp, contact_id | `outreach_events` (event_type="crm_note") |

### HubSpot Deal Stage → Our Tier Mapping

| HubSpot Deal Stage | Our `lead_score.tier` | Our `Company.status` |
|---|---|---|
| Appointment Scheduled | high | contacted |
| Qualified to Buy | high | replied |
| Presentation Scheduled | high | meeting_booked |
| Decision Maker Bought-In | high | meeting_booked |
| Contract Sent | high | meeting_booked |
| Closed Won | high | won |
| Closed Lost | low | lost |

### Tracking Flow (real-time, after initial batch sync)

HubSpot sends webhook events to `POST /webhooks/hubspot` whenever:

| HubSpot Event | What we do |
|---|---|
| `contact.propertyChange` (email → opened) | Create `OutreachEvent(event_type="email_opened")` |
| `contact.propertyChange` (email → replied) | Create `OutreachEvent(event_type="reply_received")`, update `Company.status = "replied"` |
| `deal.propertyChange` (stage changed) | Update `Company.status` per stage mapping above |
| `meeting.created` | Create `OutreachEvent(event_type="meeting_booked")`, update `Company.status` |
| `contact.creation` | If domain matches a known company in our DB, link the contact |
| `note.creation` | Create `OutreachEvent(event_type="crm_note", reply_content=note_body)` |

### New files for Phase 1

```
agents/hubspot/
  hubspot_client.py       ← HubSpot REST API wrapper (get_companies, get_contacts, get_deals, get_activities)
  hubspot_sync.py         ← batch pull + upsert logic → writes to our DB tables

api/routes/
  webhooks.py             ← POST /webhooks/hubspot — receives real-time HubSpot events

config/settings.py        ← add: HUBSPOT_ACCESS_TOKEN, HUBSPOT_PORTAL_ID
api/main.py               ← register webhooks router
```

### New trigger endpoint

```
POST /trigger/hubspot-pull
  → calls hubspot_sync.batch_pull_all()
  → pulls Companies, Contacts, Deals, Activities
  → upserts into our DB (no duplicates)
  → returns { companies_synced, contacts_synced, deals_mapped, activities_logged }
```

Also visible in the Triggers page UI as a new "HubSpot Sync" card.

### Env vars needed

```
HUBSPOT_ACCESS_TOKEN=...     # Private App token from HubSpot → Settings → Integrations → Private Apps
HUBSPOT_PORTAL_ID=...        # Your HubSpot account ID (found in any HubSpot URL)
HUBSPOT_WEBHOOK_SECRET=...   # Used to verify webhook signatures (optional but recommended)
```

### HubSpot Private App scopes required

```
crm.objects.contacts.read
crm.objects.companies.read
crm.objects.deals.read
crm.objects.notes.read
sales-email-read
timeline
```

---

## Phase 2 — Scheduled Follow-Ups: HubSpot Tasks → Writer Agent

**What it does:**
Fetches HubSpot Tasks (follow-up reminders) assigned to contacts. For each due task, the Writer agent drafts a customisable follow-up email — with full context from the CRM history (prior emails, notes, deal stage) baked into the prompt.

**Why second:**
Once Phase 1 is running, we have CRM history in our DB. The Writer can now use that history to write warm follow-ups — not cold outreach. This is the highest-value use of the Writer agent.

### How it works

```
HubSpot Tasks (due today or overdue)
  → fetched by hubspot_client.get_due_tasks()
  → each task has: contact_id, company_id, task_type, due_date, notes

For each task:
  → pull contact's full history from our outreach_events table
  → pull CRM notes from our outreach_events (event_type="crm_note")
  → pull deal stage from lead_scores
  → pass all context to Writer agent

Writer agent:
  → uses full history + deal stage + task notes as prompt context
  → generates a context-aware follow-up (not a cold email)
  → creates EmailDraft with template_used = "hubspot_followup"
  → flags it for human review in Email Review page
```

### What the Writer prompt gets (compared to cold outreach now)

| Cold outreach (current) | Follow-up (Phase 2) |
|---|---|
| Company name, industry, city | + Last email sent (date, subject) |
| Estimated utility spend | + Whether they opened it |
| Scout source signals | + Any replies or notes from rep |
| No history | + Current deal stage |
| | + Task notes (what the rep wants to say) |
| | + Days since last contact |

### New files for Phase 2

```
agents/hubspot/
  task_fetcher.py         ← get_due_tasks(), build_followup_context()

agents/writer/
  followup_writer.py      ← generates follow-up drafts using CRM context (separate from cold outreach writer)

api/routes/triggers.py    ← add POST /trigger/hubspot-followups
```

### New trigger endpoint

```
POST /trigger/hubspot-followups
  → fetches all HubSpot tasks due today
  → for each task: builds context → Writer generates draft → saves to email_drafts
  → returns { tasks_found, drafts_created }
```

Drafts appear in the Email Review page with badge "HubSpot Follow-up" and are editable before send.

---

## Phase 3 — Push: New Scout/Analyst Leads → HubSpot CRM

**What it does:**
When a lead is approved in our Leads page, automatically create or update the Company and Contact in HubSpot, and create a Deal at the correct pipeline stage.

**Why third:**
We do this last because by Phase 2 we understand the CRM structure well (fields, pipelines, deal stages). Pushing bad data early would clutter the CRM. By Phase 3 we know exactly what a good record looks like.

### What gets pushed

| Trigger | What we push | HubSpot objects created |
|---|---|---|
| Lead approved (high tier) | Company fields + primary contact | Company + Contact + Deal (stage: "Appointment Scheduled") |
| Email sent | Email record | Email Activity on Contact timeline |
| Reply received | Event record | Note on Contact timeline |
| Meeting booked | Status update | Deal stage change |

### De-duplication strategy

Before creating any record in HubSpot:
1. Search HubSpot by `domain` (for companies) or `email` (for contacts)
2. If found → `PATCH` (update) existing record
3. If not found → `POST` (create) new record

This prevents duplicates whether the contact was pulled in Phase 1 or has always lived in HubSpot.

---

## DB Provenance Columns — Already Deployed

Two columns were added to both `companies` and `contacts` to track where each record came from and when it was last synced. These are live on the AWS RDS database as of 2026-04-01.

### Migrations applied

| Migration | Table | SQL |
|---|---|---|
| `017_alter_companies_add_origin.sql` | `companies` | `ADD COLUMN data_origin VARCHAR(50), ADD COLUMN last_synced_at TIMESTAMP` |
| `018_alter_contacts_add_origin.sql` | `contacts` | `ADD COLUMN data_origin VARCHAR(50), ADD COLUMN last_synced_at TIMESTAMP` |

### Column definitions

| Column | Type | Values | Meaning |
|---|---|---|---|
| `data_origin` | `VARCHAR(50)` | `'scout'` | Company/contact discovered by Scout + Analyst agents from the internet |
| | | `'hubspot_crm'` | Record pulled from HubSpot CRM (Phase 1 batch sync or webhook) |
| | | `'manual'` | Added manually by a user via the UI |
| | | `NULL` | Legacy records created before this column existed — treat as `'scout'` |
| `last_synced_at` | `TIMESTAMP` | any datetime | Last time this record was pushed to or pulled from an external system |
| | | `NULL` | Never synced with any external system |

### How it is stamped today (pre-HubSpot)

All records saved by our agents are already stamped `data_origin='scout'` at write time:

| File | Location | Stamp |
|---|---|---|
| `agents/scout/company_extractor.py` | `save_to_database()` | `data_origin="scout"` on `Company()` |
| `agents/scout/scout_agent.py` | news scout path + main scout path | `data_origin="scout"` on both `Company()` constructors |
| `agents/analyst/enrichment_client.py` | `save_contact()` | `data_origin="scout"` on `Contact()` |

### How HubSpot Phase 1 will use it

When `hubspot_sync.py` upserts records from HubSpot:
- Set `data_origin = 'hubspot_crm'`
- Set `last_synced_at = datetime.utcnow()` at sync time

When Phase 3 pushes a record to HubSpot:
- Update `last_synced_at = datetime.utcnow()` after successful push

This lets us always know: "did this record come from us or from CRM?" and "is it in sync?"

---

## What We Are NOT Changing

The following stay exactly as they are:

- Scout, Analyst, Writer, Outreach, Tracker agents — no changes to their core logic
- Our `companies`, `contacts`, `email_drafts`, `outreach_events` DB tables — HubSpot is additive
- The approval workflow (Leads page, Email Review page) — unchanged
- SendGrid / Instantly for actual email sending — HubSpot is not the sender
- All existing triggers — new HubSpot triggers are additions, not replacements

HubSpot is a sync target and data source. It does not replace any part of our pipeline.

---

## Data Flow Summary

```
────────────────────────────────────────────────────────────
PHASE 1:  HubSpot CRM ──batch pull──▶ Our DB
          HubSpot CRM ──webhooks────▶ outreach_events (real-time)

PHASE 2:  HubSpot Tasks ──────────▶ Writer Agent
                                        ▼
                                  EmailDraft (follow-up)
                                        ▼
                              Email Review → Human Approves → SendGrid

PHASE 3:  Scout finds company
            → Analyst scores HIGH
              → Human approves
                → Our DB ──push──▶ HubSpot CRM (Company + Contact + Deal)
                  → Email sent ──▶ HubSpot Activity Timeline
                    → Reply ──────▶ HubSpot Note + Our outreach_events
────────────────────────────────────────────────────────────
```

---

## Build Checklist

### Phase 1 — Pull + Tracking

- [x] Add `data_origin` + `last_synced_at` columns to `companies` and `contacts` tables — **done 2026-04-01, migrations 017+018 applied to AWS RDS**
- [ ] Create HubSpot Private App in HubSpot account, copy access token
- [ ] Add `HUBSPOT_ACCESS_TOKEN`, `HUBSPOT_PORTAL_ID` to `.env`
- [ ] Create `agents/hubspot/hubspot_client.py` — REST wrapper
- [ ] Create `agents/hubspot/hubspot_sync.py` — batch pull + upsert
- [ ] Create `api/routes/webhooks.py` — `POST /webhooks/hubspot`
- [ ] Register webhook route in `api/main.py`
- [ ] Add `POST /trigger/hubspot-pull` to `api/routes/triggers.py`
- [ ] Add "HubSpot Sync" card to Triggers page UI
- [ ] Register webhook URL in HubSpot (Settings → Integrations → Webhooks)
- [ ] Test: run batch pull, verify companies + contacts in DB
- [ ] Test: change a deal stage in HubSpot, verify `outreach_events` row created

### Phase 2 — Follow-up Writer

- [ ] Create `agents/hubspot/task_fetcher.py`
- [ ] Create `agents/writer/followup_writer.py`
- [ ] Add `POST /trigger/hubspot-followups` endpoint
- [ ] Add "HubSpot Follow-ups" card to Triggers page UI
- [ ] Show "HubSpot Follow-up" badge on EmailDraft cards in Email Review page
- [ ] Test: create a task in HubSpot, run trigger, verify draft in Email Review

### Phase 3 — Push New Leads

- [ ] Add `push_to_hubspot()` call in `api/routes/leads.py` on approve
- [ ] Add `log_email_to_hubspot()` call in `agents/outreach/email_sender.py` after send
- [ ] Handle de-duplication (search before create)
- [ ] Add HubSpot write scopes to Private App
- [ ] Test: approve a lead, verify Company + Contact + Deal created in HubSpot
- [ ] Test: send email, verify activity appears on contact timeline

---

## Remaining Open Questions (resolve before Phase 1 build)

| Question | Why it matters |
|---|---|
| Which HubSpot pipeline ID should new deals go into? | Phase 3 needs a specific pipeline ID |
| Do you want ALL existing HubSpot contacts pulled, or only contacts with deals? | Affects DB size and sync time |
| Should follow-up drafts auto-send after approval, or require a separate send step? | Phase 2 workflow design |
| Should we expose a HubSpot section in API Lab for testing? | Useful for debugging during build |
