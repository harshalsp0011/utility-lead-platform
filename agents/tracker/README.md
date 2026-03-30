# Tracker Agent

The Tracker agent is the fifth and final agent in the pipeline. It watches everything that happens after an email is sent — opens, clicks, replies, bounces, and unsubscribes — classifies reply intent using LLM + rule-based fallback, updates lead status in the database, alerts the sales team on hot replies, and runs a daily health check to catch leads that have stalled. Tracker also closes the learning loop by enabling win-rate data to flow back to the Writer agent.

---

## 1. Position in the Pipeline

```
Scout → Analyst → Writer → Outreach → Tracker
                                         ▲
                              SendGrid webhooks (opens, clicks, replies, bounces)
                              CRM webhooks (meetings booked, deals updated)
```

Tracker is the only agent that runs reactively (webhook-driven) in addition to a scheduled daily job. It never generates content — it only observes, classifies, routes, and updates state.

---

## 2. File Architecture

```
agents/tracker/
├── tracker_agent.py        # Orchestration: webhook dispatch, stuck-lead health checks
├── webhook_listener.py     # FastAPI endpoint: receive/validate/parse SendGrid webhook payloads
├── reply_classifier.py     # LLM + rule-based reply intent/sentiment classification
├── status_updater.py       # DB state transitions: replied, unsubscribed, bounced, opened
└── alert_sender.py         # Sales team email alerts via SendGrid
```

### Dependency Tree

```
tracker_agent.py
├── agents.outreach.followup_scheduler  (cancel_followups, mark_sequence_complete)
├── agents.tracker.status_updater       (update_lead_status)
└── requests                            (Slack/webhook approval reminders via ALERT_EMAIL)

webhook_listener.py
├── fastapi + uvicorn
└── agents.tracker.tracker_agent.process_event

reply_classifier.py
├── agents.tracker.llm_connector        (primary — classify_reply_sentiment, call_llm)
└── agents.writer.llm_connector         (fallback — call_openai, call_ollama)

status_updater.py
└── agents.outreach.followup_scheduler  (cancel_followups)

alert_sender.py
├── agents.outreach.email_sender        (send_via_sendgrid)
└── agents.tracker.reply_classifier     (should_alert_sales)
```

---

## 3. How Each File Works

### `tracker_agent.py` — Orchestration Layer

The central coordinator. Handles webhook event dispatch, stuck-lead detection, and daily resolution logic.

**`process_event(event)`** — placeholder webhook dispatch entrypoint.
Currently logs the event. Downstream routing (to `status_updater`, `reply_classifier`, `alert_sender`) connects here as events are processed.

**`check_stuck_leads(db)` query:**
```python
SELECT company.id
WHERE company.updated_at < (now - 5 days)
  AND company.status NOT IN {'won','lost','no_response','archived','unsubscribed'}
ORDER BY updated_at ASC
```

**`resolve_stuck_lead(company_id, db)` — decision tree:**

| Company Status | Condition | Action | Return |
|---|---|---|---|
| `contacted` | last sent > 14 days ago + no reply exists | `mark_sequence_complete()` + `update_lead_status("no_response")` | `"marked_no_response"` |
| `scored` | no `EmailDraft` row exists | Log warning | `"needs_writer_attention"` |
| `draft_created` | no `approved_human=True` draft exists | Send approval reminder via `ALERT_EMAIL` | `"reminded_approval_needed"` |
| any other | — | No action | `"no_action"` |

**`run_daily_checks(db)` return:**
```python
{
    "stuck_found": int,       # total leads stale > 5 days
    "resolved": int,          # marked_no_response + reminded_approval_needed
    "needs_attention": int    # needs_writer_attention count
}
```

**`_send_approval_reminder(company_id, company_name)` — alert format:**
```
Draft waiting human approval > 5 days
Company: {company_name}
Lead ID: {company_id}
Review: http://localhost:3000/leads/{company_id}
```
Sent via HTTP POST to `ALERT_EMAIL` webhook URL. Silently fails if `ALERT_EMAIL` is not configured.

---

### `webhook_listener.py` — SendGrid Webhook Receiver

Runs as a FastAPI app on port 8002. Receives SendGrid event arrays, validates HMAC signature, normalizes event types, extracts reply content, and dispatches to `tracker_agent.process_event()`.

**Endpoint:**
```
POST /webhooks/email
```
Always returns HTTP 200 — prevents SendGrid retry storms even on processing errors.

**Event type mapping:**

| SendGrid `event` | Internal `event_type` |
|---|---|
| `open` | `opened` |
| `click` | `clicked` |
| `bounce` | `bounced` |
| `unsubscribe` | `unsubscribed` |
| `inbound` | `replied` |
| (anything else) | passed through as-is |

**`parse_sendgrid_event(raw_payload)` — normalized event dict:**
```python
{
    "event_type": str,          # mapped internal name
    "message_id": str,          # sg_message_id OR smtp-id OR message_id
    "email": str,               # recipient email
    "timestamp": datetime,      # UTC — from Unix int, digit string, or ISO string
    "reply_content": str|None,  # populated only for "replied" events
}
```

**`validate_webhook(headers, body)` — HMAC validation:**
- Reads `X-Twilio-Email-Event-Webhook-Signature`, `X-SendGrid-Signature`, or `X-SendGrid-Event-Webhook-Signature` header
- Computes `HMAC-SHA256(SENDGRID_API_KEY, body)`
- Compares with `hmac.compare_digest()` (timing-safe)
- In Phase 1: logs warning but does NOT block processing on signature failure

**`extract_reply_content(sendgrid_inbound_event)` — reply cleaning:**
- Reads `text`, `body`, or `content` field from inbound event
- Strips quoted reply chains (lines starting with `>`)
- Stops on reply separators: `"On ... wrote:"`, `"--"`, `"---"`, or sign-off words (`Thanks`, `Best`, `Regards`)
- Collapses excess blank lines (3+ → 2)
- Strips trailing whitespace

---

### `reply_classifier.py` — Reply Intent Classification

LLM-first classification with a rule-based keyword fallback. Ensures replies always get a usable intent even if the LLM is unavailable.

**`classify_reply(reply_text)` flow:**
```
try:
    llm_result = tracker_llm_connector.classify_reply_sentiment(text)
    if valid structure → return normalized result
except:
    pass
→ fallback: rule_based_classify(text)
```

**LLM validation — `_is_valid_classification(value)` checks:**
- Is a dict with keys: `sentiment`, `intent`, `summary`, `confidence`
- `sentiment` in `{"positive", "neutral", "negative"}`
- `intent` in `{"wants_meeting", "wants_info", "not_interested", "unsubscribe", "other"}`
- `summary` is non-empty string
- `confidence` is float between 0.0 and 1.0

**Rule-based fallback — keyword matching in priority order:**

| Priority | Keywords | Sentiment | Intent | Confidence |
|---|---|---|---|---|
| 1st | `unsubscribe`, `remove me`, `stop`, `do not contact`, `opt out` | negative | unsubscribe | 0.98 |
| 2nd | `interested`, `schedule`, `call`, `meeting`, `sounds good`, `yes`, `can we` | positive | wants_meeting | 0.88 |
| 3rd | `more information`, `details`, `brochure`, `how does it work`, `what is` | positive | wants_info | 0.84 |
| 4th | `not interested`, `no thank you`, `already have`, `wrong person` | negative | not_interested | 0.90 |
| default | (none matched) | neutral | other | 0.60 |

**`generate_reply_summary(reply_text, company_name, contact_name, sentiment)` prompt:**
```
Summarize this email reply in exactly 2 lines for a sales team.
From: {contact_name} at {company_name}
Sentiment: {sentiment}
Reply: {reply_text}
Line 1: What they said
Line 2: Recommended next action
```
Tries tracker LLM connector first, then falls back to writer LLM connector. Hardcoded fallback if both fail.

**`should_alert_sales(sentiment, intent)` logic:**
```python
if sentiment == "negative": return False
if intent in {"not_interested", "unsubscribe"}: return False
if sentiment == "positive": return True
if intent in {"wants_meeting", "wants_info"}: return True
return False  # neutral/other
```

---

### `status_updater.py` — DB State Transitions

Applies all database changes after webhook events. Every function maps to one event type.

**Valid company statuses (11 states):**
```
new → enriched → scored → approved → contacted → replied
                                               → meeting_booked → won
                                               → no_response
                                               → lost
                                               → archived
                                               (unsubscribed — via contact flag)
```

**`update_lead_status(company_id, new_status, db)`:**
- Validates `new_status` against the 11-state set
- Updates `company.status` and `company.updated_at = now(UTC)`
- Returns `False` for invalid status (raises `ValueError` in class interface)

**`mark_replied(company_id, reply_content, sentiment, db)`:**
1. `update_lead_status(company_id, "replied", db)`
2. Find all prior events for company (`sent`, `followup_sent`, `opened`, `clicked`)
3. Update each: `event_type="replied"`, `reply_content=text`, `reply_sentiment=sentiment`, `event_at=now`
4. `followup_scheduler.cancel_followups(company_id, db)` — stops remaining follow-ups
5. `db_session.commit()`

**`mark_unsubscribed(contact_id, db)`:**
1. `contact.unsubscribed = True`
2. `followup_scheduler.cancel_followups(company_id, db)` for that contact's company
3. Check if any active (non-unsubscribed) contacts remain for the company
4. If none remain: `company.status = "archived"`
5. `db_session.commit()`

**`mark_bounced(contact_id, db)`:**
1. `contact.verified = False`
2. Insert `OutreachEvent(event_type="bounced", reply_content="Email bounced for contact {id} — finding alternative contact")`
3. `db_session.commit()`
4. Logs warning — triggers manual re-enrichment for alternative contact

**`mark_opened(company_id, contact_id, db)`:**
1. Insert `OutreachEvent(event_type="opened")`
2. `db_session.commit()`
3. Does NOT change `company.status`

**`mark_sales_alerted(outreach_event_id, db)`:**
1. Sets `event.sales_alerted = True`
2. Sets `event.alerted_at = now(UTC)`
3. Prevents duplicate alerts from being sent for the same event

---

### `alert_sender.py` — Sales Team Alerts

Sends email notifications to the sales team when a high-intent reply is detected. No Slack — email only via SendGrid.

**`should_alert(event_type, sentiment, intent)`:**
Only returns `True` for `event_type="replied"` AND `reply_classifier.should_alert_sales()` returns True.

**`send_email_alert(...)` — alert recipient:**
Uses `ALERT_EMAIL` setting as primary recipient. Falls back to `to_email` parameter if not configured.

**Alert subject:**
```
HOT LEAD: {company_name} replied — action needed
```

**`build_alert_message(...)` — alert body format:**
```
HOT LEAD REPLY — {company_name}
Contact: {contact_name} — {contact_title}
Score: {score}/100
Est. Savings: {savings_formatted}
Sentiment: {sentiment}
Summary: {reply_summary}
Time: {Monday March 30 2026 at 2:15 PM EDT}

Open Dashboard to respond → http://localhost:3000/leads/{company_id}
```

---

## 4. Complete Webhook Flow: Reply Event

```
SendGrid inbound email (contact replied)
    │
    ▼
POST /webhooks/email
    │
    ▼
webhook_listener.receive_webhook(request)
    │  ├── Read body bytes
    │  ├── validate_webhook(headers, body)  → HMAC check (log only, not blocking)
    │  └── parse_sendgrid_event(body)
    │           ├── Parse JSON array
    │           ├── Map "inbound" → "replied"
    │           ├── Extract message_id, email, timestamp
    │           └── extract_reply_content() → clean reply text
    │
    ▼
tracker_agent.process_event(event)
    │
    ▼
reply_classifier.classify_reply(reply_content)
    │  ├── Try: tracker_llm_connector.classify_reply_sentiment(text)
    │  └── Fallback: rule_based_classify(text)
    │          → {sentiment, intent, summary, confidence}
    │
    ▼
alert_sender.should_alert("replied", sentiment, intent)
    │  → True if positive sentiment / wants_meeting / wants_info
    │  → False if negative / unsubscribe / not_interested
    │
    ├── If True:
    │     reply_classifier.generate_reply_summary(text, company_name, contact_name, sentiment)
    │     alert_sender.send_email_alert(ALERT_EMAIL, company_name, ...)
    │     status_updater.mark_sales_alerted(event_id, db)
    │
    └── status_updater.mark_replied(company_id, reply_content, sentiment, db)
            ├── UPDATE companies SET status="replied"
            ├── UPDATE outreach_events SET event_type="replied", sentiment=...
            └── followup_scheduler.cancel_followups(company_id)
                    └── UPDATE scheduled_followup rows → "cancelled_followup"

    └── return HTTP 200
```

---

## 5. Complete Webhook Flow: Unsubscribe Event

```
SendGrid unsubscribe event
    │
    ▼
parse_sendgrid_event() → event_type="unsubscribed"
    │
    ▼
status_updater.mark_unsubscribed(contact_id, db)
    ├── contact.unsubscribed = True
    ├── followup_scheduler.cancel_followups(company_id)
    ├── Check: any active contacts remaining for company?
    └── If none: company.status = "archived"
```

---

## 6. Complete Webhook Flow: Bounce Event

```
SendGrid bounce event
    │
    ▼
parse_sendgrid_event() → event_type="bounced"
    │
    ▼
status_updater.mark_bounced(contact_id, db)
    ├── contact.verified = False
    └── INSERT outreach_events(event_type="bounced", reply_content="bounced — finding alternative")
```

---

## 7. Daily Health Check Flow

```
Scheduler triggers tracker_agent.run_daily_checks(db)
    │
    ▼
check_stuck_leads(db)
    │  SELECT companies WHERE updated_at < (now - 5 days)
    │    AND status NOT IN terminal states
    │
    ▼
For each stuck company_id:
    │
    resolve_stuck_lead(company_id, db)
    │
    ├── status == "contacted" + last sent > 14 days + no reply:
    │       followup_scheduler.mark_sequence_complete()  → status="no_response"
    │       update_lead_status("no_response")
    │
    ├── status == "scored" + no draft exists:
    │       log warning → "needs_writer_attention"
    │
    └── status == "draft_created" + no approved draft:
            _send_approval_reminder(company_id, company_name)
            POST ALERT_EMAIL with dashboard link
```

---

## 8. Agentic Mechanics

The Tracker agent uses **Observe → Reason → Act** on two distinct triggers: reactive (webhook) and scheduled (daily).

| Phase | Observe | Reason | Act |
|---|---|---|---|
| Webhook (reply) | Parse webhook payload, extract reply text | Classify intent with LLM + rule fallback; decide if sales alert needed | Update DB status, cancel follow-ups, send alert |
| Webhook (unsubscribe) | Detect unsubscribed event | Check if other active contacts remain for company | Mark contact, optionally archive company |
| Webhook (bounce) | Detect bounce event | Contact is unverified | Invalidate contact, log event |
| Daily check | Find leads stale > 5 days | Match status → stuck condition → resolution action | Cancel sequence / send reminder / flag for attention |

**LLM-first + rule-based fallback pattern:**
- Classifier tries LLM for nuanced understanding of reply intent
- If LLM fails or returns invalid structure → keyword rules provide a reliable fallback
- This ensures the system never silently drops a reply or misclassifies an unsubscribe request

**Agentic concept used:** Reactive event processing with LLM-augmented classification. The LLM acts as an Analyst tool within the event processing loop — its output is validated before use and overridable by rules. LangSmith traces all LLM calls (when enabled).

---

## 9. All DB Reads and Writes

### Reads

| Table | What | When |
|---|---|---|
| `companies` | `status`, `updated_at`, `name` | Stuck lead checks, resolve logic |
| `email_drafts` | Existence check, `approved_human` | Resolve stuck (scored/draft_created) |
| `outreach_events` | Prior sent/followup/open/click events for company | `mark_replied` |
| `contacts` | `unsubscribed`, `company_id` | `mark_unsubscribed` |
| `outreach_events` | `outreach_event_id` | `mark_sales_alerted` |

### Writes

| Table | Columns Written | When |
|---|---|---|
| `companies` | `status`, `updated_at` | `update_lead_status`, `mark_unsubscribed` (→ archived), `mark_sequence_complete` |
| `outreach_events` | `event_type="replied"`, `reply_content`, `reply_sentiment`, `event_at` | `mark_replied` |
| `outreach_events` | `event_type="cancelled_followup"` | `cancel_followups` (via scheduler) |
| `outreach_events` | `event_type="opened"`, `event_at`, `follow_up_number=0`, `sales_alerted=False` | `mark_opened` |
| `outreach_events` | `event_type="bounced"`, `event_at`, `reply_content` | `mark_bounced` |
| `outreach_events` | `sales_alerted=True`, `alerted_at` | `mark_sales_alerted` |
| `contacts` | `unsubscribed=True` | `mark_unsubscribed` |
| `contacts` | `verified=False` | `mark_bounced` |

---

## 10. Lead Lifecycle Status Map

```
new
 └─ enriched
     └─ scored
         └─ approved         ← HITL checkpoint 1 (Leads page)
             └─ [draft_created]
                 └─ approved  ← HITL checkpoint 2 (Email Review)
                     └─ contacted
                         ├─ replied
                         │   └─ meeting_booked → won
                         │                    → lost
                         └─ no_response       (sequence completed, no reply)

Any status → archived       (all contacts unsubscribed)
Any status → unsubscribed   (contact-level flag, not company status)
```

---

## 11. Reply Classification Decision Table

| Reply Text Example | Sentiment | Intent | Alert? |
|---|---|---|---|
| "Interested, can we set up a call?" | positive | wants_meeting | Yes |
| "Please send me more information" | positive | wants_info | Yes |
| "Not interested at this time" | negative | not_interested | No |
| "Please remove me from your list" | negative | unsubscribe | No |
| "I'll pass this along to our CFO" | neutral | other | No |
| (LLM unavailable) "Yes, let's connect" | positive | wants_meeting | Yes (rule-based) |

---

## 12. Configuration

| Env Var | Purpose |
|---|---|
| `SENDGRID_API_KEY` | HMAC webhook validation + alert sends |
| `SENDGRID_FROM_EMAIL` | From address for sales alert emails |
| `ALERT_EMAIL` | Sales team recipient for hot-lead alerts + approval reminders |

---

## 13. LLM Usage

| LLM Call | When | Tokens (est.) |
|---|---|---|
| `classify_reply_sentiment(text)` | Per inbound reply | ~200–400 tokens |
| `generate_reply_summary(text, ...)` | Per alert-worthy reply | ~300–500 tokens |

**LLM cost:** ~$0 (Ollama), ~$0.00025 per reply classified (GPT-4o-mini).

Both calls have full fallbacks (rule-based + hardcoded defaults). LLM failure never blocks event processing.

---

## 14. Remaining / Not Yet Built

- `tracker_agent.process_event()` full routing — currently a placeholder logger. Full routing to `status_updater` + `reply_classifier` + `alert_sender` per event type needs wiring.
- Win-rate table update — Tracker should update `email_win_rate` (angle=won) when a reply leads to a meeting or deal
- CRM webhook receiver — handle inbound CRM webhooks (meeting booked, deal stage changed) at `POST /api/webhooks/crm/reply` and `POST /api/webhooks/crm/meeting`
- Click tracking — `clicked` events parsed but no downstream action yet wired
- LangSmith trace per webhook event — not yet integrated in tracker's LLM calls
