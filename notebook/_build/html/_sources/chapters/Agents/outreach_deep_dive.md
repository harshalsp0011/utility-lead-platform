# Outreach Agent

## Tech Stack Used

| Tech | Purpose |
|---|---|
| **SendGrid SDK** (`sendgrid`, `sendgrid.helpers.mail`) | Primary email delivery provider |
| **Instantly API** (`requests.post`) | Alternative email delivery via campaign API |
| **Ollama / OpenAI** (`llm_connector`) | LLM polishes follow-up email bodies |
| **SQLAlchemy ORM** | Reads `EmailDraft`, `Contact`, `Company`; writes `OutreachEvent`, `EmailDraft` |
| **Python `datetime` + `timedelta`** | Follow-up scheduling — day offsets from send date |

---

## Agentic Concepts Used

| Concept | Tool / Tech | Where |
|---|---|---|
| Automated Multi-Step Sequence | `followup_scheduler` + `OutreachEvent` table | 3-touch follow-up cadence auto-scheduled |
| Daily Rate Limiting | SQLAlchemy count query on `outreach_events` | `check_daily_limit()` — enforced before every send |
| Unsubscribe Guard | `Contact.unsubscribed` flag | Checked in `send_email()` and `get_due_followups()` |
| LLM Email Polishing | `llm_connector.call_ollama/openai()` | `_polish_followup_body()` in `sequence_manager.py` |
| Provider Abstraction | `select_provider()` → SendGrid or Instantly | Switchable via `EMAIL_PROVIDER` env var |

---

## File-by-File Breakdown

### 1. `agents/outreach/outreach_agent.py` — Coordinator

Two public entry points:

**`process_followup_queue(db_session)` at line 41** — daily scheduler job:
```
1. followup_scheduler.get_due_followups()   → find all follow-ups due today
2. for each due follow-up:
     sequence_manager.build_followup_email() → build subject + LLM-polished body
     _create_followup_draft()               → save new EmailDraft row
     email_sender.send_email()              → send via provider
     mark OutreachEvent as "followup_sent"
     if follow_up_number < 3: schedule next batch
     if follow_up_number == 3: mark_sequence_complete()
```

**`get_approved_queue(db_session)` at line 121** — returns all human-approved drafts that haven't been sent yet. Filters by `approved_human=True` and absence of a `sent` event in `outreach_events`.

**`check_daily_limit(db_session)` at line 158** — wraps `email_sender.check_daily_limit()`, adds `remaining` count to the response.

---

### 2. `agents/outreach/email_sender.py` — Email Delivery

**`send_email(draft_id, db_session)` at line 47** — full send pipeline:

```
1. Load EmailDraft from DB
2. Load Contact from DB
3. Check contact.unsubscribed → skip if true
4. check_daily_limit()        → skip if at cap
5. add_unsubscribe_footer()   → append brand footer + unsubscribe instruction
6. select_provider()          → "sendgrid" or "instantly"
7. send_via_sendgrid() or send_via_instantly()
8. log_send_event()           → write OutreachEvent row (event_type="sent")
```

**`send_via_sendgrid()` at line 119** — uses **SendGrid Python SDK**:
- `SendGridAPIClient(api_key=...)` 
- Builds `Mail` object with `From`, `To`, `PlainTextContent`, `HtmlContent` (body with `\n` → `<br>`)
- Enables open tracking + click tracking via `TrackingSettings`
- Returns `success=True` on HTTP 202, extracts `X-Message-Id` header

**`send_via_instantly()` at line 185** — uses **`requests.post`** directly:
- `POST {INSTANTLY_API_BASE_URL}/api/v1/lead/add`
- Payload: `{campaign_id, email, name, subject, body}`
- Returns `message_id` from response JSON

**`check_daily_limit(db_session)` at line 245** — SQLAlchemy `COUNT` query on `outreach_events` where `event_type="sent"` AND `event_at >= start_of_day`. Compares against `EMAIL_DAILY_LIMIT` setting.

**`add_unsubscribe_footer(body)` at line 234** — appends:
```
---
{UNSUBSCRIBE_INSTRUCTION}
{TB_BRAND_NAME} | {TB_OFFICE_LOCATION} | {TB_PHONE}
```

**`log_send_event()` at line 269** — writes one `OutreachEvent` row with `event_type="sent"` and `message_id` stored in `reply_content`.

---

### 3. `agents/outreach/followup_scheduler.py` — Follow-up Scheduling

**`schedule_followups(company_id, contact_id, draft_id, send_date, db_session)` at line 46:**

Creates **3 `OutreachEvent` rows** (`event_type="scheduled_followup"`) with dates calculated from configurable day offsets:

| Follow-up | Day offset setting | Default |
|---|---|---|
| Follow-up 1 | `FOLLOWUP_DAY_1` | Day 3 |
| Follow-up 2 | `FOLLOWUP_DAY_2` | Day 7 |
| Follow-up 3 | `FOLLOWUP_DAY_3` | Day 14 |

**`get_due_followups(db_session)` at line 83** — SQLAlchemy 3-table JOIN (`OutreachEvent` + `Company` + `Contact`):
- `event_type = "scheduled_followup"`
- `next_followup_date <= date.today()`
- `sales_alerted = False`
- `company.status != "replied"`
- `contact.unsubscribed = False`

Returns list of dicts with company name, contact email, follow-up number, next date.

**`cancel_followups(company_id, db_session)` at line 117** — sets future `scheduled_followup` events to `cancelled_followup` for a company (called when reply received).

**`mark_sequence_complete(company_id, db_session)` at line 185** — sets `company.status = "no_response"` and cancels any remaining scheduled follow-ups.

**`check_sequence_status(company_id, db_session)` at line 140** — returns:
```python
{
    "last_followup_sent": 2,
    "next_followup_date": date(2025, 4, 10),
    "sequence_complete": False,
    "reply_received": False,
}
```

---

### 4. `agents/outreach/sequence_manager.py` — Follow-up Content Builder

**`build_followup_email(original_draft_id, follow_up_number, db_session)` at line 37:**

```
1. Load original EmailDraft + Company + Contact + CompanyFeature + LeadScore from DB
2. writer_agent.build_context()             → same context dict the Writer uses
3. template_engine.load_followup_template() → load followup_day{N}.txt
4. template_engine.fill_static_fields()    → replace {{placeholders}}
5. build_followup_subject()                → "Re: {original subject}" or "Following up one last time"
6. _polish_followup_body()                 → LLM polishes the filled template
```

**`build_followup_subject()` at line 108:**

| Follow-up # | Subject |
|---|---|
| 1 or 2 | `Re: {original subject}` |
| 3 | `"Following up one last time"` |

**`_polish_followup_body()` at line 123** — sends the filled template to LLM:
- Uses `llm_connector.call_ollama()` or `call_openai()` based on `LLM_PROVIDER`
- Prompt instructs: *"Polish this follow-up. Keep it short and natural. Don't invent facts."*
- Falls back to filled template if LLM not available

---

## Follow-up Sequence Timeline

```
Day 0:  First email sent (human approved)
         → schedule_followups() creates 3 OutreachEvent rows
                ↓
Day 3:  Follow-up 1 — "Re: {subject}" — short reminder
                ↓
Day 7:  Follow-up 2 — "Re: {subject}" — add social proof or different angle
                ↓
Day 14: Follow-up 3 — "Following up one last time" — final touch
         → mark_sequence_complete() → company.status = "no_response"

At any point:
  Reply received → Tracker cancels remaining follow-ups
  Unsubscribe    → contact.unsubscribed=True → all future sends skipped
```

---

## What Gets Written to DB

| Table | Written by | Contents |
|---|---|---|
| `outreach_events` | `log_send_event()` | `event_type="sent"`, `event_at`, `message_id` in `reply_content` |
| `outreach_events` | `schedule_followups()` | 3 rows `event_type="scheduled_followup"`, `next_followup_date` |
| `outreach_events` | `cancel_followups()` | Updates rows to `event_type="cancelled_followup"` |
| `email_drafts` | `_create_followup_draft()` | New draft row per follow-up with `template_used="followup_dayN"` |
| `companies` | `mark_sequence_complete()` | `status = "no_response"` |

---

## Full Data Flow

```
--- First Email ---
get_approved_queue()              ← EmailDraft where approved_human=True, no sent event
  └─ for each draft:
       email_sender.send_email()
         ├─ check contact.unsubscribed
         ├─ check_daily_limit()
         ├─ add_unsubscribe_footer()
         ├─ send_via_sendgrid() or send_via_instantly()
         └─ log_send_event()      → OutreachEvent(event_type="sent")
       followup_scheduler.schedule_followups()  → 3 OutreachEvent rows

--- Daily Follow-up Job ---
process_followup_queue()
  └─ followup_scheduler.get_due_followups()    ← 3-table JOIN, due today
       └─ for each due follow-up:
            sequence_manager.build_followup_email()
              ├─ load original draft + company + contact from DB
              ├─ template_engine.fill_static_fields()
              └─ _polish_followup_body()        ← LLM (Ollama or OpenAI)
            _create_followup_draft()            → new EmailDraft row
            email_sender.send_email()           → send + log event
            if follow_up_number == 3:
              mark_sequence_complete()          → company.status="no_response"
```
