# Outreach Agent

The Outreach agent is the fourth agent in the pipeline. It takes human-approved email drafts and delivers them through a configured email provider, then manages a three-touch follow-up sequence — automatically spacing and sending follow-ups over days 3, 7, and 14 after the initial send. When a full sequence completes without a reply, Outreach marks the lead `no_response` and closes the loop.

---

## 1. Position in the Pipeline

```
Scout → Analyst → Writer → [HUMAN APPROVAL] → Outreach → Tracker
```

Outreach sits after the second HITL checkpoint (Email Review). It never sends anything that has not been approved by a human. It does not score, enrich, or draft — it only delivers and schedules.

---

## 2. File Architecture

```
agents/outreach/
├── outreach_agent.py       # Orchestration: queue management, daily limit check, run logging
├── email_sender.py         # Provider abstraction: SendGrid + Instantly, daily limit guard, event logging
├── followup_scheduler.py   # Follow-up scheduling: create/fetch/cancel OutreachEvent rows
└── sequence_manager.py     # Follow-up content: template load, subject build, LLM polish
```

### Dependency Tree

```
outreach_agent.py
├── email_sender.py
│   ├── sendgrid SDK
│   ├── requests (Instantly API)
│   └── database.orm_models: EmailDraft, Contact, OutreachEvent
├── followup_scheduler.py
│   └── database.orm_models: OutreachEvent, Company, Contact
└── sequence_manager.py
    ├── agents.writer.template_engine    (loads follow-up templates)
    ├── agents.writer.llm_connector      (polishes follow-up body)
    └── agents.writer.writer_agent       (build_context for follow-up email)
```

---

## 3. How Each File Works

### `outreach_agent.py` — Orchestration Layer

The top-level coordinator. Called by the API routes and the scheduler. Never touches the email provider directly — delegates everything to the other three modules.

Key functions:

| Function | Purpose |
|---|---|
| `get_approved_queue(db)` | Returns all approved drafts that have no sent event yet |
| `process_followup_queue(db)` | Fetches due follow-ups, builds content, sends, updates DB |
| `check_daily_limit(db)` | Wraps `email_sender.check_daily_limit` + adds `remaining` field |
| `log_outreach_run(sent, skipped, followup)` | Prints a summary block after a run |
| `_create_followup_draft(...)` | Creates a new `EmailDraft` row for each follow-up email |

`get_approved_queue` logic:
```python
select EmailDraft where approved_human=True
  AND no OutreachEvent(email_draft_id=draft.id, event_type IN ['sent','followup_sent'])
ORDER BY created_at ASC
```

`process_followup_queue` loop:
1. Get due follow-ups from `followup_scheduler.get_due_followups()`
2. Skip if contact is unsubscribed
3. Build email body via `sequence_manager.build_followup_email()`
4. Create a new `EmailDraft` row via `_create_followup_draft()`
5. Send via `email_sender.send_email()`
6. Update the `OutreachEvent` row to `event_type=followup_sent`
7. If `follow_up_number < 3`: schedule the next follow-up batch if none exist
8. If `follow_up_number == 3`: call `mark_sequence_complete()` → status=`no_response`
9. `db_session.commit()`

---

### `email_sender.py` — Provider Abstraction

Handles all actual email delivery. Supports two providers, enforces two hard guardrails (unsubscribe check + daily limit), appends the unsubscribe footer, and logs every send as an `OutreachEvent`.

**Provider selection:**
```python
EMAIL_PROVIDER = "sendgrid"   # or "instantly"
```
Selected at runtime from settings. Raises `ValueError` for unsupported values.

**Constants:**
```python
PROVIDER_SENDGRID = "sendgrid"
PROVIDER_INSTANTLY = "instantly"
EVENT_TYPE_SENT = "sent"
ENABLE_SENDGRID_OPEN_TRACKING = True
ENABLE_SENDGRID_CLICK_TRACKING = True
ENABLE_SENDGRID_TEXT_CLICK_TRACKING = True
```

**`send_email(draft_id, db)` flow — hard guardrails in order:**
1. Load `EmailDraft` — fail if not found
2. Load `Contact` — fail if not found
3. Check `contact.unsubscribed` → skip if True
4. Check `check_daily_limit()` → skip if at cap
5. Append unsubscribe footer to body
6. Dispatch to `send_via_sendgrid()` or `send_via_instantly()`
7. On success: call `log_send_event()` + `db_session.commit()`

**`check_daily_limit(db)` logic:**
```python
sent_today = COUNT(OutreachEvent) WHERE event_type="sent" AND event_at >= today_UTC_midnight
within_limit = sent_today < EMAIL_DAILY_LIMIT   # default 50
```

**`add_unsubscribe_footer(body)` output:**
```
{email body}

---
{UNSUBSCRIBE_INSTRUCTION}
{SENDER_NAME} | {OFFICE_LOCATION} | {PHONE}
```

---

### `email_sender.py` — SendGrid API Call

```
POST https://api.sendgrid.com/v3/mail/send
Authorization: Bearer {SENDGRID_API_KEY}
Content-Type: application/json

{
  "from": { "email": "{SENDGRID_FROM_EMAIL}" },
  "to":   [ { "email": "{to_email}", "name": "{to_name}" } ],
  "subject": "{subject}",
  "content": [
    { "type": "text/plain", "value": "{body}" },
    { "type": "text/html",  "value": "{body with <br> newlines}" }
  ],
  "tracking_settings": {
    "open_tracking": { "enable": true },
    "click_tracking": { "enable": true, "enable_text": true }
  }
}
```

**Success:** HTTP 202, extracts `X-Message-Id` header as `message_id`.

---

### `email_sender.py` — Instantly API Call

```
POST {INSTANTLY_API_BASE_URL}/api/v1/lead/add
Authorization: Bearer {INSTANTLY_API_KEY}
Content-Type: application/json

{
  "campaign_id": "{INSTANTLY_CAMPAIGN_ID}",
  "email": "{to_email}",
  "name":  "{to_name}",
  "subject": "{subject}",
  "body": "{body}"
}
```

**Success:** HTTP 200/2xx, extracts `message_id` or `id` from response JSON.

---

### `email_sender.py` — `log_send_event` DB Write

Inserts one `OutreachEvent` row per sent email:

| Column | Value |
|---|---|
| `company_id` | from draft |
| `contact_id` | from contact |
| `email_draft_id` | the draft that was sent |
| `event_type` | `"sent"` |
| `event_at` | `datetime.now(UTC)` |
| `reply_content` | `"message_id:{provider_message_id}"` |
| `reply_sentiment` | `None` |
| `follow_up_number` | `0` |

---

### `followup_scheduler.py` — Follow-Up Scheduling

Manages three scheduled `OutreachEvent` rows per lead after a successful first send.

**`schedule_followups(company_id, contact_id, draft_id, send_date, db)` — DB write:**

Creates 3 `OutreachEvent` rows:

| follow_up_number | next_followup_date |
|---|---|
| 1 | `send_date + FOLLOWUP_DAY_1` (default: 3 days) |
| 2 | `send_date + FOLLOWUP_DAY_2` (default: 7 days) |
| 3 | `send_date + FOLLOWUP_DAY_3` (default: 14 days) |

Each row: `event_type="scheduled_followup"`, `sales_alerted=False`.

**`get_due_followups(db)` query:**
```sql
SELECT outreach_events, companies, contacts
JOIN companies ON companies.id = outreach_events.company_id
JOIN contacts ON contacts.id = outreach_events.contact_id
WHERE outreach_events.event_type = 'scheduled_followup'
  AND outreach_events.next_followup_date <= today
  AND outreach_events.sales_alerted = False
  AND companies.status != 'replied'
  AND contacts.unsubscribed = False
ORDER BY next_followup_date ASC, follow_up_number ASC
```

**`cancel_followups(company_id, db)`:**
Sets all future `scheduled_followup` rows for a company to `event_type="cancelled_followup"`.

**`mark_sequence_complete(company_id, db)`:**
- Sets `company.status = "no_response"`
- Calls `cancel_followups()` to clean up any remaining scheduled rows

**`check_sequence_status(company_id, db)` return:**
```python
{
    "last_followup_sent": int,       # max follow_up_number from sent events
    "next_followup_date": date|None, # next scheduled date
    "sequence_complete": bool,       # True if replied OR (no scheduled AND sent >= 3)
    "reply_received": bool
}
```

---

### `sequence_manager.py` — Follow-Up Content Builder

Builds the subject line and body for each follow-up. Uses the original draft context and Writer agent templates + LLM polish.

**`build_followup_email(original_draft_id, follow_up_number, db)` flow:**
1. Load original `EmailDraft` → get `company_id`, `contact_id`
2. Load `Company`, `Contact`, `CompanyFeature`, `LeadScore`
3. Call `writer_agent.build_context(company, features, score, contact, settings)` — same context dict used by Writer
4. Load raw template: `template_engine.load_followup_template(follow_up_number)`
5. Fill static fields: `template_engine.fill_static_fields(template, context)`
6. Build subject via `build_followup_subject(original_subject, follow_up_number)`
7. LLM-polish body via `_polish_followup_body(context, subject, base_draft, follow_up_number)`

**`build_followup_subject` rules:**

| follow_up_number | Subject |
|---|---|
| 1 | `Re: {original_subject}` (or original if already starts with "Re:") |
| 2 | `Re: {original_subject}` |
| 3 | `"Following up one last time"` |

**`_polish_followup_body` prompt (fallback path when `generate_email_body` unavailable):**
```
Polish this follow-up email. Keep it professional, short, and natural.
Preserve placeholders that are already resolved and do not invent facts.
Follow-up number: {follow_up_number}
Subject: {subject}
Company: {company_name}
Draft:
{base_draft}
```

---

## 4. Complete Send Flow: First Email

```
API POST /api/outreach/send-approved
    │
    ▼
outreach_agent.get_approved_queue(db)
    │  SELECT email_drafts WHERE approved_human=True
    │  AND no sent event exists
    │
    ▼
For each draft in queue:
    │
    ├── email_sender.send_email(draft_id, db)
    │       ├── Load EmailDraft
    │       ├── Load Contact
    │       ├── GUARD: contact.unsubscribed? → skip
    │       ├── GUARD: daily limit reached? → skip
    │       ├── Append unsubscribe footer
    │       ├── send_via_sendgrid() or send_via_instantly()
    │       │       └── HTTP POST to provider
    │       └── log_send_event() → INSERT outreach_events(event_type="sent")
    │
    └── followup_scheduler.schedule_followups(company_id, contact_id, draft_id, today, db)
            └── INSERT 3 × outreach_events(event_type="scheduled_followup")
                    follow_up 1: today + 3 days
                    follow_up 2: today + 7 days
                    follow_up 3: today + 14 days
```

---

## 5. Complete Follow-Up Flow: Scheduled Send

```
Scheduler triggers process_followup_queue(db) daily
    │
    ▼
followup_scheduler.get_due_followups(db)
    │  SELECT scheduled_followup rows WHERE next_followup_date <= today
    │  AND company.status != 'replied' AND contact.unsubscribed = False
    │
    ▼
For each due follow-up:
    │
    ├── GUARD: contact.unsubscribed? → skip
    │
    ├── sequence_manager.build_followup_email(original_draft_id, follow_up_number, db)
    │       ├── Load original draft + company + contact + features + score
    │       ├── Build writer_agent context dict
    │       ├── Load template (followup_day1/2/3)
    │       ├── Fill static fields
    │       ├── Build subject line (Re: / Re: / "Following up one last time")
    │       └── LLM-polish body
    │
    ├── outreach_agent._create_followup_draft(...)
    │       └── INSERT email_drafts(approved_human=True, template="followup_day{N}")
    │
    ├── email_sender.send_email(followup_draft_id, db)
    │       └── Same provider dispatch + guardrail flow as first email
    │
    ├── UPDATE outreach_events SET event_type="followup_sent" for the scheduled row
    │
    ├── If follow_up_number < 3:
    │       └── Ensure next scheduled rows exist (re-schedule if missing)
    │
    └── If follow_up_number == 3:
            └── followup_scheduler.mark_sequence_complete()
                    ├── UPDATE companies SET status="no_response"
                    └── Cancel any remaining scheduled_followup rows
```

---

## 6. Agentic Mechanics

The Outreach agent uses **tool-calling + sequential action** rather than an LLM reasoning loop. Its "intelligence" is procedural: it checks guardrails in order, picks the right provider, sequences the follow-up schedule, and delegates body generation to the Writer's LLM connector.

| Decision | Made by |
|---|---|
| Which emails to send | Code: SQL query on `approved_human=True` + no sent event |
| Should this contact be skipped | Code: `unsubscribed` flag check |
| Is daily limit reached | Code: COUNT query on today's sent events |
| Which provider to use | Config: `EMAIL_PROVIDER` env var |
| Follow-up days spacing | Config: `FOLLOWUP_DAY_1/2/3` env vars |
| Follow-up subject line | Code: deterministic rules by sequence number |
| Follow-up body text | LLM: Writer's `generate_email_body()` / Ollama / OpenAI polishing |
| When sequence is complete | Code: `follow_up_number == 3` → `mark_sequence_complete()` |

**Agentic concept used:** Sequential tool-chaining with guardrail gates. Each step is a discrete tool call (load, check, send, log, schedule), and each gate is a hard stop that cannot be overridden by LLM output.

**LangChain:** Not used in Outreach. The agent is deterministic Python orchestration.

---

## 7. All DB Reads and Writes

### Reads

| Table | What | When |
|---|---|---|
| `email_drafts` | `approved_human=True`, check for sent events | `get_approved_queue` |
| `outreach_events` | Count today's sent events | `check_daily_limit` |
| `contacts` | `unsubscribed`, `email`, `full_name` | `send_email` |
| `outreach_events` | Due scheduled_followup rows | `get_due_followups` |
| `companies` | `status` | `get_due_followups`, `resolve_stuck_lead` |
| `company_features` | Features for follow-up context | `sequence_manager.build_followup_email` |
| `lead_scores` | Score for follow-up context | `sequence_manager.build_followup_email` |

### Writes

| Table | Columns Written | When |
|---|---|---|
| `outreach_events` | `company_id`, `contact_id`, `email_draft_id`, `event_type="sent"`, `event_at`, `reply_content="message_id:{id}"`, `follow_up_number=0` | After successful first send |
| `outreach_events` | `company_id`, `contact_id`, `email_draft_id`, `event_type="scheduled_followup"`, `follow_up_number=1/2/3`, `next_followup_date`, `sales_alerted=False` | After successful first send (×3) |
| `outreach_events` | `event_type="followup_sent"`, `event_at=now`, `reply_content="message_id:{id}"` | After successful follow-up send |
| `outreach_events` | `event_type="cancelled_followup"` | When sequence cancelled/complete |
| `email_drafts` | `id`, `company_id`, `contact_id`, `subject_line`, `body`, `savings_estimate`, `template_used="followup_dayN"`, `approved_human=True` | New row per follow-up sent |
| `companies` | `status="no_response"`, `updated_at` | After 3rd follow-up sent |

---

## 8. Follow-Up Sequence Timeline

```
Day 0   → First email sent (human-approved draft)
           └── schedule_followups() creates 3 OutreachEvent rows

Day 3   → Follow-up 1: "Re: {original subject}"
           └── Short check-in / different angle

Day 7   → Follow-up 2: "Re: {original subject}"
           └── Value reinforcement / new data point

Day 14  → Follow-up 3: "Following up one last time"
           └── Final touch / low-pressure close

Day 14+ → mark_sequence_complete()
           └── company.status = "no_response"
           └── All remaining scheduled rows cancelled
```

If the lead replies at any point, Tracker fires `cancel_followups()` — the entire scheduled sequence is stopped.

---

## 9. Guardrails Summary

| Guardrail | Enforced In | Effect |
|---|---|---|
| Unsubscribe block | `email_sender.send_email` | Skip send, no event logged |
| Daily send cap | `email_sender.check_daily_limit` | Skip send, returns remaining count |
| No draft = no send | `outreach_agent.get_approved_queue` | Only approved drafts enter queue |
| No send without approval | `EmailDraft.approved_human=True` | Hard DB filter |
| No double-send | Sent event existence check | Draft with existing sent event skipped |
| Reply stops follow-ups | Tracker → `cancel_followups()` | Sequence immediately cancelled |
| Unsubscribe stops follow-ups | `get_due_followups` filter | Contact excluded from due query |

---

## 10. Configuration

| Env Var | Default | Purpose |
|---|---|---|
| `EMAIL_PROVIDER` | `sendgrid` | `"sendgrid"` or `"instantly"` |
| `EMAIL_DAILY_LIMIT` | `50` | Max emails per day |
| `SENDGRID_API_KEY` | — | SendGrid auth |
| `SENDGRID_FROM_EMAIL` | — | Sender address |
| `INSTANTLY_API_KEY` | — | Instantly auth |
| `INSTANTLY_CAMPAIGN_ID` | — | Instantly campaign to add leads to |
| `INSTANTLY_API_BASE_URL` | — | Instantly API base URL |
| `INSTANTLY_REQUEST_TIMEOUT_SECONDS` | — | Request timeout |
| `FOLLOWUP_DAY_1` | `3` | Days after send for follow-up 1 |
| `FOLLOWUP_DAY_2` | `7` | Days after send for follow-up 2 |
| `FOLLOWUP_DAY_3` | `14` | Days after send for follow-up 3 |
| `UNSUBSCRIBE_INSTRUCTION` | — | Footer unsubscribe text |

---

## 11. LLM Usage

The Outreach agent uses the LLM only for follow-up body polishing. It delegates to the Writer agent's `llm_connector`.

| LLM Call | When | Tokens (est.) |
|---|---|---|
| `generate_email_body()` or fallback polish | Per follow-up email | ~400–800 tokens |

**LLM cost:** ~$0 (Ollama), ~$0.00035 per follow-up (GPT-4o-mini).

No LLM is used for guardrail decisions, scheduling logic, or provider selection.

---

## 12. Remaining / Not Yet Built

- Win-rate table updates after send — tracked in `email_win_rate`, updated by Tracker not Outreach
- CRM push after send — planned: push contact + sent event to CRM API after successful send
- Instantly webhook tracking (opens/clicks via Instantly's platform rather than SendGrid)
