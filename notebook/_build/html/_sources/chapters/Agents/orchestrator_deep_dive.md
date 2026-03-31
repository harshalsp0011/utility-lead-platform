# Orchestrator Agent

## Tech Stack Used

| Tech | Purpose |
|---|---|
| **SQLAlchemy ORM** | All DB reads/writes — `AgentRun`, `Company`, `LeadScore`, `CompanyFeature`, `HumanApprovalRequest`, `EmailDraft`, `OutreachEvent` |
| **Python `requests`** | Service health probes in `pipeline_monitor.py` |
| **`database.connection.check_connection`** | PostgreSQL health check |
| **`email_notifier`** | Sends approval request emails after analyst + writer stages |
| **Plain text log file** (`logs/task_log.txt`) | Structured audit trail written by `task_manager` |
| **Lazy imports** (`from agents.X import Y` inside functions) | All agents imported at dispatch time — avoids circular imports |

---

## Agentic Concepts Used

| Concept | Tool / Tech | Where |
|---|---|---|
| Pipeline Orchestration | Sequential stage functions | `orchestrator.run_full_pipeline()` |
| Task Dispatch + Retry | In-process `_TASK_LOG` dict + `retry_failed_task()` | `task_manager.assign_task()` |
| Human-in-the-Loop | `HumanApprovalRequest` DB table + `email_notifier` | After analyst + writer stages |
| Auto-Approval | `score_row.approved_human = True` on contact found | `run_contact_enrichment()` |
| Pipeline Health Monitor | SQLAlchemy COUNT queries + `requests.get` health probes | `pipeline_monitor.py` |
| Stuck Condition Detection | Time-based thresholds on pipeline status | `detect_stuck_pipeline()` |
| Weekly Reporting | SQLAlchemy aggregations across 6 tables | `report_generator.generate_weekly_report()` |

---

## File-by-File Breakdown

### 1. `agents/orchestrator/orchestrator.py` — Pipeline Entry Point

**`run_full_pipeline(industry, location, count, db_session)` at line 54:**

```
Step 1: run_scout()              → task_manager dispatches scout_agent.run()
Step 2: run_analyst()            → task_manager dispatches analyst_agent.run()
                                   → creates HumanApprovalRequest + sends email
Step 3: run_contact_enrichment() → enrichment_client.find_contacts() per high-tier company
                                   → auto-approves lead if contact found
Step 4: run_writer()             → task_manager dispatches writer_agent.run()
                                   → creates HumanApprovalRequest + sends email
Step 5: generate_run_summary()   → combines all stage results into one dict
```

Each stage function calls `task_manager.assign_task()` — a uniform dispatch layer that handles logging and retry.

---

**`run_analyst()` at line 119** — after scoring:
- Reads latest `LeadScore` per company, counts `high/medium/low`
- Creates `HumanApprovalRequest(approval_type="leads", status="pending")` in DB
- Calls `email_notifier.send_lead_approval_request()` with full scored lead list to `ALERT_EMAIL`

**`run_contact_enrichment()` at line 221** — 3-source phone lookup per company:
```
1. enrichment_client.lookup_phone_google_places(name, city, state)
2. enrichment_client.lookup_phone_yelp(name, city, state)         ← if (1) fails
3. enrichment_client.scrape_phone_from_website(website)           ← if (2) fails
```
Then calls `enrichment_client.find_contacts()` (Hunter/Apollo). If contacts found → **auto-approves** the `LeadScore` row: `approved_human=True`, `approved_by="system (contact found)"`.

**`run_writer()` at line 330:**
- Queries `Company.status == "approved"` with no existing `EmailDraft`
- Creates `AgentRun` row (`status="writer_running"`)
- After drafts created: updates `AgentRun.status = "writer_awaiting_approval"`
- Creates `HumanApprovalRequest(approval_type="emails")` + sends `email_notifier.send_draft_approval_request()`

**`handle_agent_failure()` at line 521** — retry chain:
```
1. task_manager.assign_task()      ← first retry
2. task_manager.retry_failed_task() ← second retry (increments retry_count)
3. If both fail: log error → returns "failed_after_retry"
```

---

### 2. `agents/orchestrator/task_manager.py` — Task Dispatch + Audit Log

**`assign_task(agent_name, task_params, db_session)` at line 51:**
- Registers task in `_TASK_LOG` dict (in-process, keyed by UUID)
- Calls `_dispatch()` which lazy-imports and calls each agent's `run()` entry point
- Records `started_at`, `ended_at`, `duration_seconds`
- Calls `log_task_result()` → prints + appends to `logs/task_log.txt`
- Returns `{task_id, status, result}`

**`_dispatch()` at line 171** — agent routing table:

| Agent | Import | Call |
|---|---|---|
| `scout` | `agents.scout.scout_agent` | `scout_agent.run(industry, location, count, db_session)` |
| `analyst` | `agents.analyst.analyst_agent` | `analyst_agent.run(company_ids, db_session, on_progress)` |
| `writer` | `agents.writer.writer_agent` | `writer_agent.run(company_ids, db_session, run_id, on_progress)` |
| `outreach` | `agents.outreach.outreach_agent` | `outreach_agent.process_followup_queue(db_session)` |
| `tracker` | `agents.tracker.tracker_agent` | `tracker_agent.run_daily_checks(db_session)` |

All imports are **lazy** (inside the function) — avoids circular import issues at module load time.

**`retry_failed_task(task_id, db_session)` at line 110:**
- Max 3 retries enforced via `retry_count` in `_TASK_LOG`
- Calls `assign_task()` again with original params
- Updates original log entry status so `check_task_status()` reflects latest outcome

**`log_task_result()` at line 141** — structured log line format:
```
[2025-04-01T12:00:00Z] TASK: scout params: {...} result: {...} duration: 42s
```
Written to `logs/task_log.txt` (creates directory if missing).

---

### 3. `agents/orchestrator/pipeline_monitor.py` — Health + Status Dashboard

**`get_pipeline_counts(db_session)` at line 46:**
- SQLAlchemy query: all `Company.status` values
- Returns dict with zero-filled counts for all 11 statuses: `new → enriched → scored → approved → contacted → replied → meeting_booked → won → lost → no_response → archived`

**`get_pipeline_value(db_session)` at line 61:**
- Loops active companies (not `lost/archived/no_response`)
- For each `high` tier company: sums `savings_low/mid/high` from `CompanyFeature`
- Calculates `TB_CONTINGENCY_FEE × savings_mid` = estimated Troy & Banks revenue

**`check_agent_health()` at line 107** — probes 7 services:

| Service | Check |
|---|---|
| `postgres` | `database.connection.check_connection()` |
| `ollama` | `GET {OLLAMA_BASE_URL}` (5s timeout) |
| `api` | `GET http://localhost:8001/health` |
| `airflow` | `GET http://host.docker.internal:8080/health` |
| `sendgrid` | `SENDGRID_API_KEY` set? |
| `tavily` | `TAVILY_API_KEY` set? |
| `slack` | `ALERT_EMAIL` set? |

Returns `{status: "ok"/"warning"/"error", message: "..."}` per service.

**`detect_stuck_pipeline(db_session)` at line 125** — 4 time-based checks:

| Check | Threshold | Issue |
|---|---|---|
| Companies in `new` status | > 24 hours | "N companies found but not yet analyzed" |
| High-tier leads unapproved | > 48 hours | "N high-score leads waiting approval" |
| Approved drafts unsent | > 6 hours | "N approved emails not yet sent" |
| No emails sent today | Weekday only | "No emails sent today — check outreach agent" |

**`get_recent_activity(db_session, limit=10)` at line 188:**
- Queries `OutreachEvent` ordered by `event_at DESC`, joins Company + Contact names

---

### 4. `agents/orchestrator/report_generator.py` — Weekly Report

**`generate_weekly_report(start_date, end_date, db_session)` at line 29:**

Combines 6 sub-metrics into one report dict:

| Key | Function | What it queries |
|---|---|---|
| `companies_found` | `count_companies_found()` | `Company.date_found` in range, grouped by industry + state |
| `leads_by_tier` | `count_leads_by_tier()` | `LeadScore.scored_at` in range, grouped by tier |
| `emails` | `count_emails_sent()` | `OutreachEvent` — sent/followup_sent/opened/clicked counts + rates |
| `replies` | `count_replies_received()` | `OutreachEvent(event_type="replied")` — grouped by `reply_sentiment` |
| `pipeline_value` | `calculate_pipeline_value()` | Delegates to `pipeline_monitor.get_pipeline_value()` |
| `top_leads` | `get_top_leads(limit=10)` | Top high-tier companies by score, with savings range |

**`count_emails_sent()` at line 117** — derived metrics:
```python
open_rate_pct  = opened / total_sent × 100
click_rate_pct = clicked / total_sent × 100
```

**`count_replies_received()` at line 158:**
```python
reply_rate_pct = total_replies / sent_count × 100
```
Also counts unsubscribes separately.

---

## Human-in-the-Loop Gates

Two mandatory human checkpoints managed by the Orchestrator:

```
After Analyst:
  HumanApprovalRequest(approval_type="leads", status="pending")
  email_notifier.send_lead_approval_request()   → email to ALERT_EMAIL
  Human reviews leads on dashboard → clicks Approve
  → LeadScore.approved_human = True
  (OR auto-approved if contact found during enrichment)

After Writer:
  HumanApprovalRequest(approval_type="emails", status="pending")
  email_notifier.send_draft_approval_request()  → email to ALERT_EMAIL
  Human reviews drafts on dashboard → clicks Approve
  → EmailDraft.approved_human = True
  → Outreach agent picks up approved drafts
```

---

## Full Data Flow

```
run_full_pipeline(industry, location, count)
  │
  ├─ task_manager.assign_task("scout")
  │    └─ scout_agent.run()           → saves companies → returns company_ids
  │
  ├─ task_manager.assign_task("analyst")
  │    └─ analyst_agent.run()         → scores companies → LeadScore rows
  │    → HumanApprovalRequest(leads)  → email_notifier → ALERT_EMAIL
  │
  ├─ run_contact_enrichment(high_ids)
  │    ├─ lookup_phone (Google → Yelp → website scrape)
  │    ├─ enrichment_client.find_contacts() (Hunter/Apollo)
  │    └─ auto-approve LeadScore if contact found
  │
  ├─ task_manager.assign_task("writer")
  │    └─ writer_agent.run()          → drafts created → EmailDraft rows
  │    → HumanApprovalRequest(emails) → email_notifier → ALERT_EMAIL
  │
  └─ generate_run_summary()           → combined dict printed + returned

--- Daily Jobs (separate from pipeline) ---
task_manager.assign_task("outreach")
  └─ outreach_agent.process_followup_queue()  → send due follow-ups

task_manager.assign_task("tracker")
  └─ tracker_agent.run_daily_checks()         → resolve stuck leads

pipeline_monitor.detect_stuck_pipeline()      → surface blocking issues
report_generator.generate_weekly_report()     → weekly metrics snapshot
```
