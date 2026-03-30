# Orchestrator Agent

The Orchestrator is the conductor of the entire pipeline. It does not run, score, or draft anything itself — instead it sequences all five agents in the correct order, manages task dispatch and retry logic, exposes pipeline health and monitoring data, and generates reporting metrics. It is the single entry point that drives a full end-to-end run from one function call.

---

## 1. Role in the System

```
                    ┌─────────────────────────────┐
                    │         Orchestrator         │
                    │    run_full_pipeline(...)     │
                    └──────────────┬──────────────┘
                                   │  task_manager.assign_task()
           ┌───────────┬───────────┼───────────┬───────────┐
           ▼           ▼           ▼           ▼           ▼
         Scout     Analyst      Writer      Outreach    Tracker
```

Unlike the other agents, the Orchestrator has no Docker container of its own — it runs inside the `api` container and is called directly from API routes and the Airflow scheduler.

---

## 2. File Architecture

```
agents/orchestrator/
├── orchestrator.py        # Pipeline entry point: run_full_pipeline, per-stage functions, failure handling
├── task_manager.py        # Task dispatch, in-process state registry, retry logic, audit log
├── pipeline_monitor.py    # Health checks, pipeline counts, value rollups, stuck detection, activity feed
└── report_generator.py    # Weekly/daily report aggregation: discovery, scoring, email, replies, pipeline value
```

### Dependency Tree

```
orchestrator.py
├── task_manager.py
│   ├── agents.scout.scout_agent.run()
│   ├── agents.analyst.analyst_agent.run()
│   ├── agents.writer.writer_agent.run()
│   ├── agents.outreach.outreach_agent.process_followup_queue()
│   └── agents.tracker.tracker_agent.run_daily_checks()
├── agents.analyst.enrichment_client  (phone lookup + contact enrichment in run_contact_enrichment)
├── agents.notifications.email_notifier  (lead + draft approval emails)
└── database.orm_models: Company, Contact, CompanyFeature, EmailDraft, LeadScore, HumanApprovalRequest, AgentRun

pipeline_monitor.py
├── database.connection.check_connection  (Postgres health probe)
└── requests  (HTTP health probes for Ollama, API, Airflow)

report_generator.py
└── agents.orchestrator.pipeline_monitor  (pipeline value rollup)
```

---

## 3. How Each File Works

### `orchestrator.py` — Pipeline Entry Point

Controls the full pipeline end-to-end and provides individual stage functions for partial or re-entrant runs.

---

#### `run_full_pipeline(industry, location, count, db_session)` — Main Entry

Executes all four discovery stages in sequence and returns a combined summary dict.

```
run_full_pipeline("healthcare", "Buffalo NY", 20, db)
    │
    ├── Step 1: run_scout(industry, location, count, db)
    │           └── Returns: {"company_ids": [str, ...]}
    │
    ├── Step 2: run_analyst(company_ids, db)
    │           └── Returns: {"scored": N, "high": N, "medium": N, "low": N, "high_ids": [...]}
    │
    ├── Step 3: run_contact_enrichment(high_ids, db)
    │           └── Returns: {"contacts_found": N}
    │
    ├── Step 4: run_writer(db)
    │           └── Returns: {"drafts_created": N, "run_id": str}
    │
    └── generate_run_summary(...) → prints table + returns summary dict
```

**Return dict:**
```python
{
    "companies_found": int,
    "scored_high": int,
    "scored_medium": int,
    "contacts_found": int,
    "drafts_created": int,
}
```

---

#### `run_scout(industry, location, count, db)` — Stage 1

Calls `task_manager.assign_task("scout", {...}, db)` → `scout_agent.run()`.

Returns `{"company_ids": [...]}`. Returns empty list if task fails.

---

#### `run_analyst(company_ids, db, on_progress=None)` — Stage 2

Calls `task_manager.assign_task("analyst", {...}, db)` → `analyst_agent.run()`.

After completion, queries latest `LeadScore` per company to count tiers. High-tier IDs returned as `high_ids`.

**HITL notification — after scoring:**
1. Creates a `HumanApprovalRequest` row:
   - `approval_type="leads"`, `status="pending"`, `items_count=total`
   - `items_summary="High: N, Medium: N, Low: N"`
2. Calls `email_notifier.send_lead_approval_request(leads, run_id, recipient_email)`
   - Sends summary email to `ALERT_EMAIL` with scored lead list
3. Updates `approval_req.notification_sent=True` + `notification_sent_at`

Returns:
```python
{"scored": int, "high": int, "medium": int, "low": int, "high_ids": [str, ...]}
```

---

#### `run_contact_enrichment(company_ids, db, on_progress=None)` — Stage 3

Directly calls `enrichment_client` — not routed through `task_manager`.

For each company in `high_ids`:

**Phone lookup waterfall (only if `company.phone` is missing):**
1. `enrichment_client.lookup_phone_google_places(name, city, state)`
2. `enrichment_client.lookup_phone_yelp(name, city, state)` (fallback)
3. `enrichment_client.scrape_phone_from_website(website)` (fallback)

**Contact enrichment:**
- `enrichment_client.find_contacts(company_name, website_domain, db_session)`
- On success: `company.contact_found=True`, `company.status="enriched"`
- **Auto-approval:** If `LeadScore.approved_human` is False, sets `approved_human=True`, `approved_by="system (contact found)"` — company becomes available for Writer without manual approval click

`on_progress(entry)` callback per company:
```python
{"idx": int, "name": str, "status": "found|not_found|failed|skipped",
 "provider": str|None, "contacts_found": int, "has_phone": bool}
```

Returns `{"contacts_found": int}`.

---

#### `run_writer(db, on_progress=None)` — Stage 4

Queries companies with `status="approved"` and no existing `EmailDraft`. This gate covers both auto-approved companies (from contact enrichment) and manually approved leads.

**AgentRun tracking:**
1. Creates `AgentRun` row: `status="writer_running"`, `current_stage="writer_running"`
2. Calls `task_manager.assign_task("writer", {"company_ids": ..., "run_id": ...}, db)`
3. On success: updates to `status="writer_awaiting_approval"`, `drafts_created=N`
4. On failure: updates to `status="failed"`, `current_stage="writer_failed"`

**HITL notification — after drafting:**
1. Creates `HumanApprovalRequest` row: `approval_type="emails"`, `status="pending"`
2. Calls `_load_draft_summaries(draft_ids, db)` to get company/contact/subject/angle/critic_score per draft
3. Calls `email_notifier.send_draft_approval_request(drafts, run_id, recipient_email)`
   - Sends email to `ALERT_EMAIL` with draft review list

Returns `{"drafts_created": int, "run_id": str}`.

---

#### `run_outreach(db)` — Stage 5

Calls `task_manager.assign_task("outreach", {}, db)` → `outreach_agent.process_followup_queue()`.

Returns `{"sent": int, "followups": int, "skipped": int}`.

---

#### `handle_agent_failure(agent_name, error, task_params, db)` — Retry Logic

Two-pass retry on any agent failure:

```
1st retry: assign_task(agent_name, task_params, db)
    → if completed: return "retried_successfully"

2nd retry: retry_failed_task(task_id, db) via task_manager
    → if completed: return "retried_successfully"

Both exhausted:
    → log error with task_id, params, exception
    → return "failed_after_retry"
```

---

### `task_manager.py` — Task Dispatch + Audit

Routes task calls to the correct agent, tracks every task in an in-process dict (`_TASK_LOG`), and appends a structured line to `logs/task_log.txt` after every dispatch.

**In-process task registry format:**
```python
_TASK_LOG[task_id] = {
    "agent_name": str,
    "params": dict,
    "status": "running" | "completed" | "failed",
    "result": dict | None,
    "started_at": datetime,
    "ended_at": datetime | None,
    "retry_count": int,
}
```

**Valid agents:**
```python
_VALID_AGENTS = {"scout", "analyst", "writer", "outreach", "tracker"}
```

**`assign_task(agent_name, params, db)` flow:**
1. Validate agent name — return `failed` immediately for unknown names
2. Register task in `_TASK_LOG` with `status="running"`
3. Call `_dispatch(agent_name, params, db)` — wraps in try/except
4. Update `_TASK_LOG` entry with status/result/ended_at/duration
5. Call `log_task_result(...)` → print + append to `logs/task_log.txt`
6. Return `{task_id, status, result}`

**`_dispatch` agent call table:**

| Agent | Entry Point Called | Params Unpacked |
|---|---|---|
| `scout` | `scout_agent.run(industry, location, count, db_session)` | `industry`, `location`, `count` |
| `analyst` | `analyst_agent.run(company_ids, db_session, on_progress)` | `company_ids`, `on_progress` |
| `writer` | `writer_agent.run(company_ids, db_session, run_id, on_progress)` | `company_ids`, `run_id`, `on_progress` |
| `outreach` | `outreach_agent.process_followup_queue(db_session)` | — |
| `tracker` | `tracker_agent.run_daily_checks(db_session)` | — |

**All agents imported lazily** (inside `_dispatch` using `from agents.X import Y`) to avoid circular imports at module load time.

**`retry_failed_task(task_id, db)` logic:**
- Reads `retry_count` from `_TASK_LOG[task_id]`
- If `retry_count >= 3`: return `{retried: False, error: "Max retries (3) exceeded"}`
- Otherwise: increment counter, call `assign_task()` again, propagate result back to original `task_id` entry

**`log_task_result` line format:**
```
[2026-03-30T14:22:01.234567+00:00] TASK: scout params: {industry: healthcare, location: Buffalo NY, count: 20} result: {company_ids: [...]} duration: 12s
```
Appended to `logs/task_log.txt`. Directory created if missing.

---

### `pipeline_monitor.py` — Health and Observability

Used by the dashboard, admin endpoints, and scheduled heartbeat checks.

**`get_pipeline_counts(db)` — Stage funnel counts:**
Returns count of companies per status, zero-filled for all 11 expected states:
```python
{"new": N, "enriched": N, "scored": N, "approved": N, "contacted": N,
 "replied": N, "meeting_booked": N, "won": N, "lost": N, "no_response": N, "archived": N}
```

**`get_pipeline_value(db)` — Active pipeline savings rollup:**
- Filters to active companies (excludes `lost`, `archived`, `no_response`)
- For each with `LeadScore.tier == "high"`: sums `savings_low/mid/high` from `CompanyFeature`
- `total_tb_revenue_est = total_savings_mid × TB_CONTINGENCY_FEE` (default: 0.24)

Returns:
```python
{
    "total_leads_high": int,
    "total_savings_low": float,
    "total_savings_mid": float,
    "total_savings_high": float,
    "total_tb_revenue_est": float,
}
```

**`check_agent_health()` — Infrastructure probe:**

| Service | Check |
|---|---|
| `postgres` | `database.connection.check_connection()` |
| `ollama` | HTTP GET `{OLLAMA_BASE_URL}` (default: `http://host.docker.internal:11434`) |
| `api` | HTTP GET `http://localhost:8001/health` |
| `airflow` | HTTP GET `http://host.docker.internal:8080/health` |
| `sendgrid` | `SENDGRID_API_KEY` present in settings |
| `tavily` | `TAVILY_API_KEY` present in settings |
| `slack` | `ALERT_EMAIL` present in settings |

Each entry returns: `{"status": "ok" | "warning" | "error", "message": str}`

**`detect_stuck_pipeline(db)` — Stall condition detection:**

Returns a list of human-readable issue strings. Checks four conditions:

| Check | Threshold | Issue String |
|---|---|---|
| Companies in `new` status | Created > 24h ago | `"N companies found but not yet analyzed"` |
| High-tier leads not approved | `scored_at` > 48h ago, `approved_human=False` | `"N high-score leads waiting approval"` |
| Approved drafts not sent | `created_at` > 6h ago, no sent event | `"N approved emails not yet sent"` |
| Weekday + 0 emails sent today | Is Monday–Friday, sent_today=0 | `"No emails sent today — check outreach agent"` |

**`get_recent_activity(db, limit=10)` — Activity feed:**
Returns last N `OutreachEvent` rows joined with company/contact names, ordered by `event_at DESC`.

---

### `report_generator.py` — Weekly/Daily Reports

Aggregates metrics across a date range for dashboards and scheduled reporting jobs.

**`generate_weekly_report(start_date, end_date, db)` — Full report:**

```python
{
    "date_range": {"start": ISO, "end": ISO},
    "companies_found": {total, by_industry: {}, by_state: {}},
    "leads_by_tier": {high, medium, low, total},
    "emails": {total_sent, first_emails, followups, open_rate_pct, click_rate_pct},
    "replies": {total_replies, positive, neutral, negative, unsubscribes, reply_rate_pct},
    "pipeline_value": {active_high_leads, savings_low, savings_mid, savings_high, revenue_estimate},
    "top_leads": [{company_name, industry, score, tier, savings_formatted, status}, ...]
}
```

**`count_emails_sent` derived metrics:**
- `open_rate_pct = opened / (sent + followup_sent) × 100`
- `click_rate_pct = clicked / (sent + followup_sent) × 100`

**`count_replies_received` derived metrics:**
- `reply_rate_pct = replied / (sent + followup_sent) × 100`
- Reply sentiment grouped from `OutreachEvent.reply_sentiment`

**`get_top_leads(limit=10, db)` — Sorted by score DESC:**
- Active companies only (excludes `lost`, `archived`, `no_response`)
- High tier only
- `savings_formatted`: formatted as `$XXk - $XXk` or `$X.XM - $X.XM`

---

## 4. Complete Pipeline Execution Flow

```
API POST /api/pipeline/run  (or Airflow DAG trigger)
    │
    ▼
orchestrator.run_full_pipeline("healthcare", "Buffalo NY", 20, db)
    │
    ├── task_manager.assign_task("scout", {industry, location, count}, db)
    │       └── scout_agent.run() → [company_ids]
    │       └── logs to task_log.txt
    │
    ├── task_manager.assign_task("analyst", {company_ids}, db)
    │       └── analyst_agent.run() → [scored_company_ids]
    │       └── orchestrator reads LeadScore rows → tier counts + high_ids
    │       └── HumanApprovalRequest(approval_type="leads") inserted
    │       └── email_notifier.send_lead_approval_request() → ALERT_EMAIL
    │       [HUMAN REVIEWS LEADS PAGE — HITL checkpoint 1]
    │
    ├── run_contact_enrichment(high_ids, db)
    │       └── enrichment_client.lookup_phone_*() per company
    │       └── enrichment_client.find_contacts() per company
    │       └── On contact found: company.status="enriched", LeadScore.approved_human=True (auto)
    │
    ├── task_manager.assign_task("writer", {company_ids, run_id}, db)
    │       └── writer_agent.run() → [draft_ids]
    │       └── AgentRun row: status="writer_awaiting_approval"
    │       └── HumanApprovalRequest(approval_type="emails") inserted
    │       └── email_notifier.send_draft_approval_request() → ALERT_EMAIL
    │       [HUMAN REVIEWS EMAIL DRAFTS — HITL checkpoint 2]
    │
    └── generate_run_summary() → print table + return summary dict
```

---

## 5. Agentic Mechanics

The Orchestrator implements the **ReAct planning loop at the pipeline level**: it reasons about what has been found at each stage (Observe → Reason → Act), gates the next stage on the output of the previous, and reacts to failures with structured retry.

| Role | What it does |
|---|---|
| Observe | Read task results: how many companies found? how many scored high? |
| Reason | Pass only high-tier IDs to contact enrichment; only `approved` companies to Writer |
| Act | Dispatch next stage via `task_manager.assign_task()` |
| Reflect | Log task result to `task_log.txt`; surface stuck conditions via `detect_stuck_pipeline()` |

**HITL as a pipeline gate:** The Orchestrator does not automatically continue through HITL checkpoints. The analyst stage creates a `HumanApprovalRequest` and sends a notification email — the human must visit the Leads page to approve. Only after `company.status="approved"` does `run_writer()` include that company in its query.

**Retry as a reliability layer:** `handle_agent_failure()` + `task_manager.retry_failed_task()` provide two automatic retry attempts before surfacing the failure to the operator. This protects against transient API timeouts, rate limits, and LLM hiccups.

**Agentic concept used:** Multi-agent orchestration with sequential chaining, HITL gates, and automatic retry/fallback. The Orchestrator is the meta-agent that plans and sequences the specialized sub-agents.

---

## 6. All DB Reads and Writes

### Reads

| Table | What | Function |
|---|---|---|
| `lead_scores` | Latest score + tier per company | `run_analyst` |
| `companies` | `status`, `name`, `website`, `phone`, `city`, `state` | `run_contact_enrichment`, `pipeline_monitor` |
| `company_features` | `savings_low/mid/high`, `computed_at` | `run_analyst`, `pipeline_monitor`, `report_generator` |
| `email_drafts` | Existence check, `approved_human`, `subject_line`, `template_used`, `critic_score` | `run_writer`, `pipeline_monitor` |
| `outreach_events` | `event_type`, `event_at`, `reply_sentiment` | `pipeline_monitor`, `report_generator` |
| `contacts` | `full_name` | `run_writer._load_draft_summaries`, `pipeline_monitor.get_recent_activity` |

### Writes

| Table | Columns Written | When |
|---|---|---|
| `human_approval_requests` | `id`, `approval_type`, `status`, `items_count`, `items_summary`, `notification_email`, `notification_sent`, `created_at` | After analyst completes (leads), after writer completes (emails) |
| `human_approval_requests` | `notification_sent=True`, `notification_sent_at` | After notification email successfully sent |
| `agent_runs` | `id`, `trigger_source`, `status`, `current_stage`, `companies_approved`, `drafts_created`, `started_at`, `created_at` | Before writer task |
| `agent_runs` | `status`, `current_stage`, `drafts_created`, `completed_at` | After writer task completes |
| `companies` | `phone`, `contact_found=True`, `status="enriched"` | After successful contact enrichment |
| `lead_scores` | `approved_human=True`, `approved_by="system (contact found)"`, `approved_at` | Auto-approval after contact found |

---

## 7. Pipeline Monitor — Stuck Condition Thresholds

| Stage | Threshold | What Triggers It |
|---|---|---|
| Discovery stall | `created_at > 24h` with status `new` | Scout ran but analyst hasn't processed yet |
| Approval stall | `scored_at > 48h`, `approved_human=False`, tier=`high` | Lead waiting human review too long |
| Send stall | Draft `created_at > 6h`, `approved_human=True`, no sent event | Approved email not dispatched |
| Outreach dead | Weekday + 0 emails sent today | Outreach agent likely down |

---

## 8. Report Generator Metric Summary

| Metric | Source Table | Grouped By |
|---|---|---|
| Companies found | `companies.date_found` | `industry`, `state` |
| Leads by tier | `lead_scores.scored_at` | `tier` (high/medium/low) |
| Emails sent | `outreach_events.event_type` | `sent`, `followup_sent`, `opened`, `clicked` |
| Reply sentiment | `outreach_events.reply_sentiment` | `positive`, `neutral`, `negative` |
| Pipeline value | `lead_scores.tier + company_features.savings_*` | High tier, active status only |
| Top leads | `lead_scores.score DESC` | Top 10, high tier, active only |

---

## 9. Container and Deployment

The Orchestrator has a `Dockerfile` but runs inside the `api` container — no separate container is deployed.

```
docker-compose up
  ├── api       (port 8001)  FastAPI + Orchestrator + all agents
  └── frontend  (port 3000)  nginx + React
```

**Airflow DAGs** (optional, scheduled) call `run_full_pipeline()` and `run_outreach()` on a schedule. The orchestrator is also triggered on-demand via the chat interface and direct API calls.

---

## 10. Configuration

| Env Var | Used In | Purpose |
|---|---|---|
| `ALERT_EMAIL` | `run_analyst`, `run_writer`, `_send_approval_reminder` | Notification recipient |
| `TB_CONTINGENCY_FEE` | `pipeline_monitor.get_pipeline_value` | Revenue estimate multiplier (default: 0.24) |
| `OLLAMA_BASE_URL` | `check_agent_health` | Health probe target for local LLM |

---

## 11. Remaining / Not Yet Built

- `_TASK_LOG` is in-process (RAM only) — does not persist across container restarts. A DB-backed task log would survive restarts and enable cross-process polling.
- `run_outreach()` is defined but not called from `run_full_pipeline()` — outreach runs separately on a schedule, not as part of the pipeline trigger.
- CRM push after each pipeline run — planned: push newly enriched companies and drafted emails to CRM API.
- `check_agent_health()` has `slack` key mapped to `ALERT_EMAIL` (legacy label) — will be renamed when settings are updated.
