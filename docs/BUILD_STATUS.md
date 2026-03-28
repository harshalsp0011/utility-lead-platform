# Build Status — What's Done, What's Not, What's Missing
> Last updated: March 2026
> Use this file to know exactly where the project stands before starting any new work.

---

## Quick Summary

| Stage | Feature | Status |
|---|---|---|
| Lead Discovery | Scout finds companies from news | ✅ Done |
| Lead Discovery | HubSpot import | ❌ Not built |
| Lead Discovery | Manual add form | ❌ Not built |
| Enrichment | Apollo contact lookup | ✅ Done |
| Scoring | LLM scoring + narrative | ✅ Done |
| Human Approval #1 | Leads page approve/reject | ✅ Done |
| Email Writing | Writer + Critic + rewrite loop | ✅ Done |
| Human Approval #2 | Email Review page | ✅ Done |
| Sending | SendGrid send on approval | ✅ Done |
| Follow-ups | Schedule 3 follow-ups after send | ✅ Done (scheduling only) |
| Follow-ups | Actually send follow-ups via Airflow | ⚠️ Code exists, not running live |
| Reply Detection | Detect when prospect replies | ❌ Not built (biggest gap) |
| Meeting Booking | Detect when meeting is booked | ❌ Not built |
| HubSpot Sync | Push deal to HubSpot after send | ❌ Not built |
| HubSpot Webhook | Receive reply/meeting events | ❌ Not built |
| Notifications | Email alerts for replies, pipeline events | ⚠️ Partially built |
| Tracker | Background reply/open monitoring | ⚠️ Code exists, not wired live |
| Airflow Schedule | Full pipeline on a cron schedule | ⚠️ DAG exists, not configured |
| Learning | Win-rate feedback loop | ⚠️ Tables exist, not active |
| Dashboard | Leads, Pipeline, Triggers, Email Review | ✅ Done |
| Dashboard | Reply inbox page | ❌ Not built |
| Dashboard | Notification center | ❌ Not built |
| Dashboard | Company timeline view | ❌ Not built |

---

## What Works End-to-End Right Now

You can run this full sequence today with no missing pieces:

```
1. Go to Triggers page → Run Scout
   → Companies discovered from news and saved

2. Go to Triggers page → Run Analyst
   → Companies enriched (contacts found) and scored 0–100

3. Go to Leads page → review scores → Approve high-tier leads

4. Go to Triggers page → Run Writer
   → Personalized emails drafted with AI Critic review

5. Go to Email Review page → read each draft → Approve & Send
   → Email sent via SendGrid, follow-ups scheduled in DB

Pipeline stages update automatically at every step.
```

---

## What Is Built But Not Yet Wired Live

These features have working code but are not actively running:

### Follow-up Sending
- **What exists:** `followup_scheduler.py`, `sequence_manager.py`, Airflow DAG `daily_tracker_dag.py`
- **What's missing:** Airflow is not running as a live scheduled service. Follow-ups are saved to the database but never actually sent.
- **To fix:** Start Airflow, configure it with the correct DB connection and schedule.

### Tracker Agent
- **What exists:** `agents/tracker/tracker_agent.py`, `status_updater.py`, reply/open event handling
- **What's missing:** Not running as a background process. No webhook endpoint to receive events from SendGrid or HubSpot.
- **To fix:** Wire Tracker to run continuously, add webhook handler endpoints.

### Email Win-Rate Learning
- **What exists:** `email_win_rate` table, Writer reads it to bias angle selection
- **What's missing:** Tracker never updates the table when a reply comes in (because reply detection doesn't exist yet). Table stays empty.
- **To fix:** Once reply detection is working, Tracker writes reply events → table fills → Writer starts learning.

### Notification Emails
- **What exists:** `email_notifier.py` sends approval-needed emails after Writer finishes
- **What's missing:** No automatic alerts for replies received, pipeline failures, or daily summaries.

---

## What Is Completely Missing (Not Built)

### Reply Detection — Most Critical Gap
When a prospect replies to an email, nothing in the system knows about it. Follow-ups keep going out even if they already responded. Status stays at "Contacted" forever.

**What needs to be built:**
- HubSpot webhook endpoint: `POST /api/webhooks/hubspot/reply`
- OR SendGrid Inbound Parse webhook: `POST /api/webhooks/sendgrid/inbound`
- Handler: match contact email → log reply event → cancel follow-ups → set status = "replied" → alert sales team

### Meeting Booking Detection
No automatic detection when a prospect books a meeting through the HubSpot calendar link.

**What needs to be built:**
- HubSpot meeting webhook: `POST /api/webhooks/hubspot/meeting`
- Handler: set status = "meeting_booked", cancel remaining follow-ups

### HubSpot Sync (Push)
After an email is sent, the company and contact are not pushed to HubSpot. The sales team has no CRM view of the pipeline.

**What needs to be built:**
- After `send_email()` succeeds → create HubSpot Contact + Deal via HubSpot API
- As status changes (replied, meeting_booked, won) → update HubSpot deal stage

### HubSpot Import (Pull)
No way to bring existing contacts from HubSpot into this platform.

**What needs to be built:**
- Import page in dashboard with "Import from HubSpot" button
- Backend: fetch HubSpot contacts → map to companies + contacts tables → enter scoring pipeline

### Manual Lead Add
No form to add a company manually.

**What needs to be built:**
- Form on Leads page: company name, website, industry, state, contact name, email, title
- Creates company + contact rows with `source = 'manual'`

### Reply Inbox (Dashboard)
No page to read and manage received replies.

**What needs to be built:**
- `src/pages/Replies.jsx` — list of all replies with company, contact, reply text, sentiment, date
- Sentiment filter (positive / neutral / negative)
- Link to company detail from each reply

### Notification Center (Dashboard)
No in-app alerts for replies, pipeline events, or approvals needed.

**What needs to be built:**
- `src/components/NotificationCenter.jsx`
- Badge count on nav when unread notifications exist
- Clicking a notification navigates to the relevant page

### Company Timeline (Dashboard)
No way to see the full history of a company in one view.

**What needs to be built:**
- Timeline section on Lead Detail page
- Events: discovered → scored → approved → emailed → opened → replied → meeting booked

---

## What's Deferred (Decided to Skip for Now)

| Feature | Why deferred |
|---|---|
| Bulk approve all emails in Email Review | Low priority — individual approval preferred for quality control |
| `human_approval_requests` batch status tracking | Complex, low value until Airflow scheduling is active |
| SerpAPI news/press release source for Scout | Enhancement — Scout works fine with current sources |
| Phase D: Chat dynamic filter generation | Chat already mostly works — small enhancement not worth doing yet |

---

## Build Priority Order (What to Do Next)

If starting work now, this is the order that makes the most sense:

```
1. Reply detection webhook        ← closes the biggest gap in the pipeline
   (HubSpot or SendGrid inbound)

2. HubSpot push sync              ← gives sales team CRM visibility immediately
   (create deal after send)

3. Manual add + HubSpot import    ← unlocks existing contacts as lead source

4. Reply inbox page               ← makes replies visible in dashboard

5. Airflow live scheduling        ← makes follow-ups actually send

6. Notification center            ← ties all alerts together in-app

7. Company timeline               ← full audit trail per company

8. Learning activation            ← auto-improves over time (needs reply data first)
```

---

## File Map — Where Key Things Live

| Feature | File(s) |
|---|---|
| Scout (find companies) | `agents/scout/scout_agent.py` |
| Analyst (score + enrich) | `agents/analyst/analyst_agent.py`, `enrichment_client.py` |
| Writer (draft emails) | `agents/writer/writer_agent.py` |
| Critic (score drafts) | `agents/writer/critic_agent.py` |
| Send email | `agents/outreach/email_sender.py` |
| Schedule follow-ups | `agents/outreach/followup_scheduler.py` |
| Build follow-up content | `agents/outreach/sequence_manager.py` |
| Tracker / reply handling | `agents/tracker/tracker_agent.py`, `status_updater.py` |
| Orchestrator | `agents/orchestrator/orchestrator.py` |
| Airflow DAGs | `dags/daily_tracker_dag.py` |
| API — leads | `api/routes/leads.py` |
| API — emails | `api/routes/emails.py` |
| API — triggers | `api/routes/triggers.py` |
| API — pipeline | `api/routes/pipeline.py` |
| Dashboard — Leads | `dashboard/src/pages/Leads.jsx` |
| Dashboard — Email Review | `dashboard/src/pages/EmailReview.jsx` |
| Dashboard — Triggers | `dashboard/src/pages/Triggers.jsx` |
| Dashboard — Pipeline | `dashboard/src/pages/Pipeline.jsx` |
| Settings / config | `config/settings.py`, `.env` |
| DB models | `database/orm_models.py` |
| DB migrations | `database/migrations/` |
