# CRM Leads Email Flow — Feature Plan

> Created: April 2026  
> Last updated: April 2026  
> Status: Phases CRM-0 through CRM-3 complete. Phase CRM-4 (polish) + Phase CRM-5 (HubSpot send) planned.

---

## What This Feature Does

Enables personalized email drafting and sending for CRM-sourced leads (`data_origin = 'hubspot_crm'`)
who bypassed the Scout → Analyst pipeline entirely.

**The scenario:** You met a prospect in person. You added them to HubSpot. You want to send a
follow-up email that references what you actually discussed — not a generic cold pitch.
This feature gives you a place to write that context, stores it, has the LLM draft the email
from it, and lets you review/send from a dedicated CRM tab.

**Key difference from pipeline leads:**
- No `company_features`, no `lead_scores` — the Analyst never ran on these companies
- No benchmark savings — you've met them; a fabricated number damages credibility
- No human approval gate — CRM = already qualified; draft is pre-approved, send is one click
- No automated critic loop — **you are the critic**; Regenerate asks what to change

---

## Agentic Design

| Step | Agent | Agentic Concept | Tool | Tech |
|---|---|---|---|---|
| Save context | Context Formatter | Information Structuring — LLM reorganizes free-text notes into ordered bullet-point signals | LLM call | `context_formatter.py`, LangChain + Ollama/OpenAI |
| Generate email | CRM Writer | Context-Aware Generation — uses meeting notes as `score_reason` substitute; no pipeline data needed | LLM call | `writer_agent.process_crm_company()` |
| Regenerate | Human-in-the-Loop Critic | Human IS the critic — feedback dialog sends your instruction as the rewrite prompt | LLM call | `_rewrite_draft()` with user feedback |
| Send | Email Provider | Current: SendGrid. Planned (CRM-5): HubSpot Engagements API | API call | `email_sender.py` → HubSpot |

---

## Context Formatter — How It Works

When you save meeting notes, the raw text passes through an LLM before storage:

```
Raw input (what you type):
  "Met John at the conference, they have offices in Buffalo and Rochester,
   CFO said they overpay on gas every winter, no energy contract currently,
   seemed very open to the idea of a free audit"

LLM output (stored as notes_formatted, used by Writer):
  - Met CFO (John) at industry conference
  - 2 locations: Buffalo and Rochester, NY
  - Self-reported overpayment on gas utilities in winter months
  - No current energy vendor contract in place
  - Expressed clear interest in a free utility audit
```

Both raw and formatted are stored (`company_context_notes` table). Raw is kept for reference.
If LLM fails → raw notes stored in both columns, generation is never blocked.

---

## Email Signature (Locked)

Every generated email ends with exactly:

```
Best regards,
Kevin Gibs
Sr. Vice President
Troy & Banks Inc.
https://troybanks.com/
```

Injected directly into writer and rewrite prompts — LLM cannot deviate from it.
Configurable via `.env`: `TB_SENDER_NAME`, `TB_SENDER_TITLE`, `TB_WEBSITE`.

---

## Send Flow (SendGrid — current and active)

```
Click "✓ Send"
  → SendConfirmDialog shows: TO email, FROM address, Subject
  → Confirm → PATCH /emails/{draft_id}/approve
  → email_sender.send_email()
      - Loads contact.email from DB
      - Checks contact.unsubscribed → blocks if true
      - Checks daily limit (50/day from .env EMAIL_DAILY_LIMIT) → blocks if reached
      - Sends via SendGrid
          FROM: UBinterns@troybanks.com  (SENDGRID_FROM_EMAIL in .env)
          TO:   contact.email
          + open tracking pixel enabled
          + click tracking enabled
      - Logs to outreach_events (event_type='sent', message_id stored)
      - Sets company.status = 'contacted'
```

---

## What SendGrid Tracks (via Webhook → Port 8002)

After send, SendGrid calls back our webhook listener at `POST /webhooks/email` (port 8002).
Every event is stored in the `outreach_events` table.

| SendGrid Event | Stored as (`event_type`) | What it means | What we do |
|---|---|---|---|
| `open` | `opened` | Recipient opened the email (pixel fired) | Logged to `outreach_events`. No status change — opens are noisy. |
| `click` | `clicked` | Recipient clicked a link in the email | Logged to `outreach_events`. Strong buying signal. |
| `inbound` (reply) | `replied` | Recipient replied to the email | `company.status → 'replied'`. Reply text stored. Sentiment saved. **All follow-ups cancelled.** |
| `bounce` | `bounced` | Email could not be delivered | `contact.verified = False`. Bounce event logged. No follow-ups sent to this contact. |
| `unsubscribe` | `unsubscribed` | Recipient clicked unsubscribe link | `contact.unsubscribed = True`. All follow-ups cancelled. If no active contacts remain → `company.status = 'archived'`. |

**Reply handling detail:**
- Reply content is extracted and cleaned (quoted chains stripped, signature lines stripped)
- Stored in `outreach_events.reply_content`
- Sentiment is stored in `outreach_events.reply_sentiment` (LLM classifies: wants_meeting / wants_info / not_interested / unsubscribe)
- Company status flips to `replied` immediately

**What SendGrid does NOT track:**
- Whether the prospect forwarded the email
- Whether they opened it on mobile vs desktop (raw pixel only)
- Replies sent from a different email address than the one we sent to

---

## Send Flow (Planned — HubSpot, Phase CRM-5, NOT BUILT)

> HubSpot integration has not been started. This section describes future intent only.
> Current send path for ALL leads (pipeline and CRM) is SendGrid.

Once HubSpot integration is live, CRM emails may be sent through HubSpot's Engagements API
so the email thread is visible on the contact timeline inside HubSpot.

**What needs to be built first:**
- HubSpot Phase 1 pull (sync contacts/companies → store `hubspot_contact_id` on DB rows)
- `send_via_hubspot()` in `email_sender.py`
- Routing: `if company.data_origin == 'hubspot_crm' → HubSpot, else → SendGrid`

---

## Decisions (Locked)

| Question | Decision |
|---|---|
| Critic loop for CRM drafts? | **Removed.** Human is the critic. Regenerate dialog asks what to change. No automated LLM quality gate. |
| Max rewrites? | **None automatic.** Each Regenerate = 1 LLM call. User decides when it's good. |
| Savings estimate for CRM? | **None.** Benchmark numbers are not verified and damage credibility with a personal contact. Audit offer is the CTA. |
| 1 draft per contact? | **Yes — upsert.** `_save_draft()` checks existing draft by `company_id + contact_id`. Updates in place on regenerate. Follow-up drafts are `outreach_events` rows, not `email_drafts`. |
| Context notes required to generate? | **Optional — warn inline but do not block generation.** |
| Context notes editable after saving? | **Yes, always.** Re-save re-runs LLM formatter and updates `notes_formatted`. |
| Approved_human on CRM drafts? | **True on creation.** CRM = pre-qualified; skips pending queue. Human still must click Send. |
| Send provider now? | **SendGrid.** `SENDGRID_FROM_EMAIL = UBinterns@troybanks.com` |
| Send provider after HubSpot integration? | **HubSpot Engagements API** for `data_origin = 'hubspot_crm'` companies. SendGrid stays for pipeline leads. |

---

## Database

### `company_context_notes` table (migration 019)

```sql
id              UUID PK
company_id      UUID FK → companies.id  ON DELETE CASCADE
notes_raw       TEXT      -- what the user typed
notes_formatted TEXT      -- LLM-structured bullet points (used by Writer)
source          VARCHAR(50) DEFAULT 'manual_input'
created_by      VARCHAR(100)
created_at      TIMESTAMP
updated_at      TIMESTAMP
-- UNIQUE INDEX on company_id (one context record per company)
```

---

## Files Changed

| Layer | File | What Changed |
|---|---|---|
| DB migration | `database/migrations/019_create_company_context_notes.sql` | New table + unique index |
| ORM | `database/orm_models.py` | Added `CompanyContextNote` model |
| Context Formatter | `agents/writer/context_formatter.py` | New file — LLM note structuring agent |
| Writer | `agents/writer/writer_agent.py` | Added `process_crm_company()`, `_sender_fields()`, `_MAX_REWRITES_CRM=1`; `_rewrite_draft()` now accepts user feedback; signature injected into both prompts |
| LLM connector | `agents/writer/llm_connector.py` | Added `max_tokens` param to `call_ollama()` for latency control |
| LLM config | `config/llm_config.py` | Added `num_predict=300` to ChatOllama (critic path) |
| Settings | `config/settings.py` | Added `TB_WEBSITE` field |
| .env | `.env` | Updated `TB_SENDER_NAME=Kevin Gibs`, `TB_SENDER_TITLE=Sr. Vice President`, added `TB_WEBSITE=https://troybanks.com/` |
| API models | `api/models/email.py` | Added `CrmGenerateRequest` (with optional `user_feedback`), `CrmContextSaveRequest/Response`, `CrmContactInfo`, `CrmCompanyResponse/ListResponse` |
| API routes | `api/routes/companies.py` | New file — `GET /companies/crm`, `POST /companies/{id}/context` |
| API routes | `api/routes/emails.py` | Added `POST /emails/crm-generate` (passes `user_feedback` through) |
| API main | `api/main.py` | Registered `companies` router at `/companies` |
| Frontend API | `dashboard/src/services/api.js` | Added `fetchCrmCompanies()`, `saveCompanyContext()`, `generateCrmEmail(companyId, createdBy, userFeedback)` |
| Frontend UI | `dashboard/src/pages/EmailReview.jsx` | Added tab switcher, `CrmLeadsTab`, `CrmCompanyCard`, `CrmDraftView`, `RegenerateDialog`, `SendConfirmDialog` |

**What was NOT changed:**
- Pipeline writer `process_one_company()` — untouched
- Tab 1 Pipeline Queue — untouched
- Critic agent (`critic_agent.py`) — unchanged for pipeline path; CRM path bypasses it entirely now
- Scout, Analyst, Orchestrator, Tracker — untouched

---

## Phase Plan

### Phase CRM-0 — DB + ORM ✅
- [x] Migration `019_create_company_context_notes.sql` written and run
- [x] `CompanyContextNote` ORM model added
- [x] Table confirmed in DB

### Phase CRM-1 — Backend: Context Endpoints + Formatter ✅
- [x] `GET /companies/crm` — bulk loads CRM companies + contacts + context + latest draft
- [x] `POST /companies/{id}/context` — saves notes, runs LLM formatter, upserts context row
- [x] `context_formatter.py` — LLM preprocessing agent, fallback to raw on failure
- [x] CRM schemas added to `api/models/email.py`
- [x] `companies` router registered in `api/main.py`

### Phase CRM-2 — CRM Writer ✅
- [x] `process_crm_company()` added to `writer_agent.py`
  - No `company_features` or `lead_scores` needed
  - No benchmark savings — audit offer is the CTA
  - `notes_formatted` used as `score_reason`
  - Draft saved with `approved_human = True`
- [x] `POST /emails/crm-generate` endpoint added
- [x] Upsert logic in `_save_draft()` — 1 draft per contact, updates in place on regenerate

### Phase CRM-3 — Frontend Tab ✅
- [x] Tab switcher — Pipeline Queue | CRM Leads
- [x] `CrmLeadsTab` — fetches on mount, count banner, one card per company
- [x] `CrmCompanyCard` — collapsed/expanded, context textarea, Save & Format, draft section
- [x] `CrmDraftView` — subject/body display, inline edit, Send/Edit/Regenerate
- [x] `RegenerateDialog` — modal asking what to change; empty = fresh write
- [x] `SendConfirmDialog` — shows TO / FROM / Subject before sending; confirm required
- [x] Loading overlay on generate (full-width banner with spinner)

### Phase CRM-3b — Optimisations + UX Fixes ✅
- [x] Removed automated critic loop from CRM path — 1 LLM call per generate (was 2–6)
- [x] `num_predict` caps on all Ollama calls: writer=650, rewrite=450, critic=300, formatter=350
- [x] `_MAX_REWRITES_CRM = 1` (separate from pipeline's 2)
- [x] `RegenerateDialog` — user types what to change; writer rewrites with that as the instruction
- [x] Hardcoded real signature injected into writer + rewrite prompts
- [x] `SendConfirmDialog` — shows exactly who the email goes to before sending
- [x] `NameError: critic_score` fixed (leftover reference after critic removal)

### Phase CRM-4 — Polish + Docs (Planned)
- [ ] No-contact edge case: show editable "To Email" field when no contact found on card
- [ ] Update `docs/BUILD_STATUS.md` — move CRM flow to Phase Completion table
- [ ] Update `agents/writer/README.md` — document `process_crm_company()` and context formatter

### Known Issues to Fix Before Phase CRM-5 (HubSpot Connect)

> These were found during SendGrid testing. Must be resolved before wiring HubSpot.

- **Double-send risk**: Clicking Send twice fast creates 2 `outreach_events` rows and sends
  the email twice. Root cause: no in-flight lock — the button disables only on the client side.
  Fix: add a DB-level check in `approve_draft` — if `outreach_events` already has a `sent`
  row for this `email_draft_id`, skip the send and return `{success:true, sent:false, already_sent:true}`.
  Frontend should show "Already sent" instead of re-sending.

- **UI shows Sent even when not actually delivered**: `isSent` was checking `approved_human && approved_at`
  but `approved_at` was never set client-side after send. Fixed (April 2026) — now reads `result.sent`
  from API response. Resend button added to sent banner in case user needs to retry.

- **SendGrid message_id not stored**: `response.headers` is `http.client.HTTPMessage`, not a dict —
  `isinstance(response.headers, dict)` was always False so `X-Message-Id` was never captured.
  Fixed (April 2026) — use `.get()` directly on the header object.

- **Emails landing in spam (SendGrid only)**: `troybanks.com` domain is not authenticated in
  SendGrid (no SPF/DKIM/DMARC records). Gmail treats unsigned emails from unverified domains as
  suspicious. Fix: SendGrid dashboard → Sender Authentication → Authenticate Domain → add the
  3 DNS records (2 DKIM CNAMEs + 1 SPF) to troybanks.com DNS.
  **This is NOT an issue with HubSpot send (Phase CRM-5)** — HubSpot uses its own authenticated
  sending infrastructure and sends from the connected rep's inbox (e.g. kevin.gibs@troybanks.com),
  which has established Gmail/Outlook trust. No manual DNS setup needed for HubSpot path.

---

### Phase CRM-5 — HubSpot Send Path (NOT STARTED — depends on HubSpot Phase 1 pull)

> HubSpot integration has not been built. All sends currently go through SendGrid.
> This phase cannot start until HubSpot Phase 1 (contact/company sync) is complete
> so that `hubspot_contact_id` and `hubspot_company_id` exist on our DB rows.

- [ ] HubSpot Phase 1 pull must be complete first (contacts + companies synced, IDs stored)
- [ ] Add `send_via_hubspot()` to `agents/outreach/email_sender.py`
      - POST to HubSpot Engagements API: `/crm/v3/objects/emails`
      - Associates with contact + company in HubSpot timeline
      - HubSpot tracks opens/clicks/replies natively from this point
- [ ] Add send routing in `email_sender.send_email()`:
      `data_origin = 'hubspot_crm'` → HubSpot, else → SendGrid
- [ ] Add `HUBSPOT_API_KEY` to `.env` and `config/settings.py`
- [ ] Update `SendConfirmDialog` — show "Sending via HubSpot" badge for CRM leads
- [ ] Live engagement fetch on CRM card (no storage needed):
      - On card expand, call `GET /engagements/v1/engagements/associated/CONTACT/{hubspot_contact_id}/paged`
      - Display inline: "Opened 2 days ago · Clicked link · No reply yet"
      - Temp fetch only — not written to our DB
      - NOTE: this only works for emails sent via HubSpot. Emails sent via SendGrid
        (before Phase CRM-5) are invisible to HubSpot and cannot be fetched this way.

---

## What Is NOT Affected

- Existing pipeline writer `process_one_company()` — untouched
- Tab 1 Pipeline Queue — untouched  
- SendGrid path for pipeline leads — untouched
- Scout, Analyst, Orchestrator, Tracker — untouched
- Follow-up scheduler (`sequence_manager.py`) — CRM follow-up gap is a known issue, tracked separately
