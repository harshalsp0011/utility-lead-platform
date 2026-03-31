# Tracker Agent

## Tech Stack Used

| Tech | Purpose |
|---|---|
| **FastAPI** + **Uvicorn** | Webhook HTTP server — listens for SendGrid events on port 8002 |
| **SendGrid Inbound Parse** | Delivers reply/open/click/bounce/unsubscribe webhooks |
| **HMAC SHA-256** (`hashlib`, `hmac`) | Validates SendGrid webhook signatures |
| **LangChain / Ollama / OpenAI** | LLM classifies reply sentiment + generates 2-line sales summary |
| **SQLAlchemy ORM** | Reads/writes `Company`, `Contact`, `OutreachEvent` |
| **`requests`** | Sends approval reminder to Slack webhook (tracker_agent) |
| **Python `re`** | Cleans raw reply text — strips quoted chains, signatures |

---

## Agentic Concepts Used

| Concept | Tool / Tech | Where |
|---|---|---|
| Event-Driven Processing | FastAPI webhook + SendGrid Inbound | `webhook_listener.receive_webhook()` |
| LLM Reply Classification | LLM → `classify_reply_sentiment()` | `reply_classifier.classify_reply()` |
| Rule-Based Fallback | Keyword matching | `rule_based_classify()` — always runs if LLM unavailable |
| Automated Status Transitions | SQLAlchemy ORM updates | `status_updater` — replied / unsubscribed / bounced / no_response |
| Stuck Lead Health Check | Daily scheduler job | `tracker_agent.run_daily_checks()` |
| Sales Alert Routing | SendGrid email via `email_sender` | `alert_sender.send_email_alert()` |

---

## File-by-File Breakdown

### 1. `agents/tracker/webhook_listener.py` — HTTP Webhook Server

**Agentic concept: Event-Driven Processing**

`start_listener(port=8002)` at line 43 — spins up a **FastAPI** app served by **Uvicorn**:
```python
@app.post("/webhooks/email")
async def _email_webhook(request: Request) -> JSONResponse:
    return await receive_webhook(request)
```

**`receive_webhook(request)` at line 57:**
```
1. Read raw body bytes
2. validate_webhook()         → HMAC SHA-256 signature check
3. parse_sendgrid_event()     → normalize JSON payload → list of event dicts
4. for each event:
     tracker_agent.process_event(event)
5. Always return HTTP 200     → prevents SendGrid retry storms on errors
```

**`parse_sendgrid_event(raw_payload)` at line 81** — maps SendGrid event types to internal types:

| SendGrid `event` | Internal `event_type` |
|---|---|
| `open` | `opened` |
| `click` | `clicked` |
| `bounce` | `bounced` |
| `unsubscribe` | `unsubscribed` |
| `inbound` | `replied` |

For `replied` events, calls `extract_reply_content()` to pull clean reply text.

**`validate_webhook(headers, body)` at line 128** — HMAC-SHA256 check:
- Reads `X-Twilio-Email-Event-Webhook-Signature` / `X-SendGrid-Signature` header
- Computes `HMAC(SENDGRID_API_KEY, body, sha256)` and compares via `hmac.compare_digest()`
- Validation failure is logged but **does not drop the event** in phase 1

**`extract_reply_content(event)` at line 151** — cleans raw inbound email text:
- Strips quoted reply chains (lines starting with `>`)
- Stops at common separators: `"On {date} ... wrote:"`, `"--"`, `"---"`
- Collapses 3+ blank lines → 2, normalizes whitespace with `re.sub`

---

### 2. `agents/tracker/reply_classifier.py` — LLM + Rule-Based Classification

**Agentic concept: LLM-First with Rule-Based Fallback**

**`classify_reply(reply_text)` at line 23** — two-pass strategy:
```
1. Try LLM classifier (agents.tracker.llm_connector.classify_reply_sentiment)
   → validate result with _is_valid_classification()
   → normalize and return if valid
2. Fallback: rule_based_classify()  ← always works, no LLM required
```

**`rule_based_classify(reply_text)` at line 40** — keyword matching in priority order:

| Priority | Keywords | Sentiment | Intent |
|---|---|---|---|
| 1st | "unsubscribe", "remove me", "stop", "opt out" | `negative` | `unsubscribe` |
| 2nd | "interested", "schedule", "call", "sounds good", "yes" | `positive` | `wants_meeting` |
| 3rd | "more information", "send me", "details", "how does it work" | `positive` | `wants_info` |
| 4th | "not interested", "no thank you", "wrong person" | `negative` | `not_interested` |
| Default | (no match) | `neutral` | `other` |

Each result includes `confidence` (0.6–0.98).

**`generate_reply_summary(reply_text, company_name, contact_name, sentiment)` at line 126:**
- Sends reply + context to LLM: *"Summarize in 2 lines: Line 1 what they said, Line 2 recommended next action"*
- Falls back to `agents.writer.llm_connector` if tracker connector unavailable
- Falls back to static template if both LLM connectors fail

**`should_alert_sales(sentiment, intent)` at line 170:**
- Returns `True` only for positive sentiment OR `wants_meeting`/`wants_info` intent
- Returns `False` for `negative`, `not_interested`, `unsubscribe` — no noise for sales team

---

### 3. `agents/tracker/status_updater.py` — Status Transitions

All status changes flow through here. Valid statuses at line 29:
```
new → enriched → scored → approved → contacted → replied → meeting_booked → won
                                                                           → lost
                                                         → no_response
                                                         → archived
```

**`update_lead_status(company_id, new_status, db_session)` at line 52** — validates against `_VALID_STATUSES`, updates `company.status` + `company.updated_at`.

**`mark_replied(company_id, reply_content, sentiment, db_session)` at line 67:**
```
1. update_lead_status() → "replied"
2. Find all sent/followup_sent/opened/clicked events for this company
3. Set reply_content + reply_sentiment on all of them
4. Set event_type = "replied" on all
5. followup_scheduler.cancel_followups() → stop future follow-ups
```

**`mark_unsubscribed(contact_id, db_session)` at line 95:**
```
1. contact.unsubscribed = True
2. followup_scheduler.cancel_followups()
3. Check if any other active contacts remain for this company
4. If none: company.status = "archived"
```

**`mark_bounced(contact_id, db_session)` at line 128:**
- Sets `contact.verified = False`
- Writes `OutreachEvent(event_type="bounced")` with note to find alternative contact
- Does **not** change company status — bounce triggers contact re-search, not lead close

**`mark_opened(company_id, contact_id, db_session)` at line 197:**
- Writes `OutreachEvent(event_type="opened")` only — does not change lead status
- Used for engagement tracking

---

### 4. `agents/tracker/tracker_agent.py` — Daily Health Monitor

**`run_daily_checks(db_session)` at line 137:**
```
1. check_stuck_leads()     → find companies stale 5+ days in non-terminal status
2. for each stuck company:
     resolve_stuck_lead()  → decide action based on current status
3. Return summary: {stuck_found, resolved, needs_attention}
```

**`check_stuck_leads(db_session)` at line 51:**
- SQLAlchemy query: `company.updated_at < (now - 5 days)` AND `status NOT IN terminal_statuses`
- Terminal statuses: `won`, `lost`, `no_response`, `archived`, `unsubscribed`

**`resolve_stuck_lead(company_id, db_session)` at line 71** — decision tree by status:

| Status | Condition | Action |
|---|---|---|
| `contacted` | Last sent > 14 days ago, no reply | `mark_sequence_complete()` → `"no_response"` |
| `scored` | No EmailDraft row exists | Log warning → `"needs_writer_attention"` |
| `draft_created` | No approved draft after 5 days | `_send_approval_reminder()` → Slack webhook |

**`_send_approval_reminder()` at line 159** — `requests.post` to `ALERT_EMAIL` Slack webhook with company name + dashboard deep-link.

---

### 5. `agents/tracker/alert_sender.py` — Sales Alert Email

**`send_email_alert(...)` at line 27:**
- Builds subject: `"HOT LEAD: {company_name} replied — action needed"`
- Calls `build_alert_message()` → multiline body with score, savings, sentiment, LLM summary, dashboard link
- Delivers via `email_sender.send_via_sendgrid()` to `ALERT_EMAIL` setting

**`should_alert(event_type, sentiment, intent)` at line 97:**
- Only fires for `event_type="replied"` — delegates to `reply_classifier.should_alert_sales()`
- Open/click events do **not** trigger sales alerts

---

## Event → Action Routing

```
SendGrid Webhook → POST /webhooks/email
  └─ parse_sendgrid_event()    → normalize event type + extract reply text
       │
       ├─ event_type = "opened"
       │    └─ status_updater.mark_opened()     → OutreachEvent(opened)
       │
       ├─ event_type = "clicked"
       │    └─ OutreachEvent(clicked) logged only
       │
       ├─ event_type = "replied"
       │    ├─ extract_reply_content()           → strip quoted chains
       │    ├─ reply_classifier.classify_reply() → LLM → rule fallback
       │    │    → {sentiment, intent, summary, confidence}
       │    ├─ status_updater.mark_replied()     → company.status="replied"
       │    │                                      cancel_followups()
       │    ├─ reply_classifier.generate_reply_summary() → LLM 2-line summary
       │    └─ should_alert_sales() → True?
       │         └─ alert_sender.send_email_alert() → SendGrid email to sales team
       │
       ├─ event_type = "unsubscribed"
       │    └─ status_updater.mark_unsubscribed() → contact.unsubscribed=True
       │                                            cancel_followups()
       │                                            company.status="archived" if last contact
       │
       └─ event_type = "bounced"
            └─ status_updater.mark_bounced()     → contact.verified=False
                                                   OutreachEvent(bounced)
```

---

## What Gets Written to DB

| Table | Written by | Contents |
|---|---|---|
| `outreach_events` | `mark_opened()` | `event_type="opened"` |
| `outreach_events` | `mark_bounced()` | `event_type="bounced"` |
| `outreach_events` | `mark_replied()` | Updates existing events → `event_type="replied"`, `reply_content`, `reply_sentiment` |
| `outreach_events` | `cancel_followups()` | Updates `scheduled_followup` → `cancelled_followup` |
| `companies` | `update_lead_status()` | `status` field updated |
| `companies` | `mark_unsubscribed()` | `status = "archived"` if no active contacts |
| `companies` | `mark_sequence_complete()` | `status = "no_response"` |
| `contacts` | `mark_unsubscribed()` | `unsubscribed = True` |
| `contacts` | `mark_bounced()` | `verified = False` |
