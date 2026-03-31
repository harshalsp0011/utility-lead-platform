# Agentic Design

> How and why this platform uses LLM-based reasoning instead of fixed automation rules.

---

## What "Agentic" Means Here

A traditional automation system executes fixed steps in a fixed order:

```
Automation:   User → fixed code → fixed query → fixed formula → result
```

An agentic system uses an LLM as a **reasoning and decision layer** on top of deterministic tools (APIs, DB queries, math):

```
Agentic:   User → LLM reasons about intent
                → decides which tools to call and in what order
                → executes tools (APIs, DB, math — deterministic)
                → evaluates result quality
                → loops if result is not good enough
                → returns result
```

**Key principle:** LLM never does math. LLM never calls APIs directly. LLM classifies, infers, decides, evaluates, and generates text. Everything else is deterministic code.

---

## Agentic Concepts Implemented

| Concept | Plain English | Where Used |
|---|---|---|
| **Tool Use** | LLM picks and calls tools based on intent | Chat Agent |
| **ReAct Loop** | Reason → Act → Observe → repeat until done | Chat Agent |
| **Confidence-Gated Routing** | LLM rates its own certainty — low confidence triggers clarification | Chat Agent |
| **Context Carry-Forward** | Multi-turn memory across chat messages | Chat Agent |
| **Dynamic Query Planning** | LLM generates search variants, not one fixed string | Scout |
| **Waterfall with Graceful Degradation** | Try provider A → B → C → fallback, never crash | Enrichment |
| **Context-Aware Generation** | LLM reads company signals, reasons before writing | Writer |
| **Self-Critique / Reflection** | Agent evaluates its own output on a rubric | Writer + Critic |
| **Iterative Refinement** | Rewrite loop — max 2 attempts with targeted feedback | Writer |
| **Uncertainty Flagging** | Agent signals when it can't reach confidence threshold | Writer |
| **Human-in-the-Loop (HITL)** | Human approval gates before irreversible actions | Leads + Emails |
| **Observable Execution** | Live counters, run tracking, completion notifications | All agents |
| **Learning from Feedback** | Historical reply rates bias future angle selection | Writer + Tracker |

---

## Full Pipeline — Where Agentic Behaviors Fire

```
Scout
  │  [Tool Use] — Chat LLM picks search_companies tool from user intent
  │  [Dynamic Query] — LLM builds 3–5 query variants + quality retry loop
  ▼
companies table

Analyst
  │  [LLM Scoring] — LLM narrates score_reason from company signals
  │  [Data Inference] — Apollo fallback when employee_count missing
  ▼
lead_scores  +  company_features

    ┌─── [HITL Gate 1] ─────────────────────────────────────────┐
    │  Human reviews leads on /leads page                       │
    │  Approve → company.status = "approved"                    │
    │  Reject → company excluded from Writer                    │
    └───────────────────────────────────────────────────────────┘

Contact Enrichment
  │  [Waterfall] — Hunter → Apollo → Scraper → Serper →
  │               Snov → Prospeo → ZeroBounce → Permutation
  │  [Skip Flags] — _hunter_blocked / _apollo_blocked skip after 429/403
  │  [Quality Gates] — placeholder filter, domain integrity check
  ▼
contacts table

Writer
  │  [Learning] — get_best_angle() reads email_win_rate
  │  [Context-Aware Generation] — LLM reasons about angle before writing
  │  [Self-Critique] — Critic LLM scores draft 0–10
  │  [Iterative Refinement] — rewrite loop (max 2)
  │  [Uncertainty Flagging] — low_confidence=True if never reaches 7/10
  │  [Observable Execution] — AgentRun.drafts_created counter
  ▼
email_drafts table

    ┌─── [HITL Gate 2] ─────────────────────────────────────────┐
    │  Human reviews drafts on /emails page                     │
    │  Approve → email sent immediately via SendGrid            │
    │  Reject → draft deleted, company reset to "approved"      │
    │  Edit+Approve → human edits, then sends                   │
    │  Regenerate → new Writer+Critic cycle                     │
    └───────────────────────────────────────────────────────────┘

Outreach
  │  Send approved first emails + 3-touch follow-up sequence (Day 3/7/14)
  │  [Guardrails] — unsubscribe block, daily send cap, no double-send
  ▼
outreach_events table

Tracker
  │  [Reply Classification] — LLM intent + rule-based fallback
  │  [Alert] — hot-lead notification to sales team on positive reply
  │  [Learning Write] — win rate updated on reply → feeds back to Writer
  ▼
email_win_rate  (feeds back to Writer on next run)
```

---

## Concept Deep Dives

### Tool Use + ReAct Loop (Chat Agent)

**Concept:** LangChain ReAct (Reason + Act) — the LLM reasons about user intent, picks a tool, observes the result, and decides whether to call another tool or respond.

**Tech:** LangChain `create_agent`, `@tool` decorator, `SystemMessage` / `HumanMessage`

**File:** `agents/chat_agent.py`

```
User: "find 10 healthcare companies in Buffalo"
  ↓
LLM reasons: "user wants to discover companies → call search_companies"
  ↓
Calls: search_companies(industry="healthcare", location="Buffalo NY", count=10)
  ↓
Observes: 10 companies saved to DB
  ↓
LLM responds: "Found 10 healthcare companies in Buffalo"
```

Three-tier routing decides how much LLM power to use:
- **Tier 1 — Conversational:** "thanks" → direct reply, no tools
- **Tier 2 — Intent parser:** simple data query → Python extracts filters, calls tool directly
- **Tier 3 — Agent loop:** complex/multi-step → full LangChain ReAct

**Why:** Tier 1 and 2 avoid unnecessary LLM calls — faster, cheaper, more reliable.

**Confidence-Gated Routing:** `_extract_intent()` makes one LLM call per message and returns a `confidence` value (0.0–1.0). If confidence < 0.65, the agent asks the user to clarify instead of guessing. This prevents wrong tool calls from ambiguous messages.

---

### Waterfall with Graceful Degradation (Contact Enrichment)

**Concept:** A sequence of providers where each failure silently falls through to the next. No single provider crashing stops the pipeline.

**Tech:** Python `try/except` per step, module-level skip flags, ordered fallback chain

**File:** `agents/analyst/enrichment_client.py`

```python
try:
    contacts = find_via_hunter(domain)
except Exception:
    pass  # fall through to Apollo

try:
    contacts = find_via_apollo(domain)
except Exception:
    pass  # fall through to scraper
# ... 8 steps total
```

**Skip flags** (`_hunter_blocked`, `_apollo_blocked`): once a provider returns 429/403, all remaining companies in the run skip that provider — no wasted API calls.

The 8-step waterfall:

| Step | Source | Notes |
|---|---|---|
| 1 | Hunter.io | Domain email search — 50 searches/month |
| 2 | Apollo.io | People search by company domain |
| 3 | Website scraper | `mailto:` + regex on /contact, /about |
| 4 | Serper | `"CFO site:{domain}"` Google result |
| 5 | Snov.io | Company domain bulk search |
| 6 | Prospeo | LinkedIn-backed two-step lookup |
| 7 | ZeroBounce | Email verification + contact |
| 8 | Permutation | `firstname.lastname@domain` patterns |

**Why:** Hunter 429 and Apollo 403 used to crash the entire enrichment run. Now they fail silently — every company gets a best-effort result from whatever provider is available.

---

### Context-Aware Generation (Writer)

**Concept:** Instead of filling template placeholders, the LLM reads company context and decides the angle, tone, and content before writing a single word.

**File:** `agents/writer/writer_agent.py` — `_WRITER_PROMPT`, `_write_draft()`

The prompt contains:
- Company name, industry, city, state, site count
- Estimated annual savings (low / mid / high from `company_features`)
- Whether the state is deregulated
- `score_reason` — the Analyst's narrative (e.g. *"3-site healthcare org in deregulated NY, ~$180k annual savings potential"*)
- Contact first name and title
- Win rate hint: which angle has the highest reply rate in this industry

The LLM outputs `REASONING:` → `ANGLE:` → `SUBJECT:` → `BODY:`:

```
REASONING: Healthcare company with 3 sites in deregulated NY — electricity cost
           is the primary lever. VP of Operations will care about budget
           predictability more than raw savings. Lead with audit offer.
ANGLE: audit_offer
SUBJECT: Free energy audit for Regional General Hospital — 3 sites, $180k opportunity
BODY: Hi Sarah, ...
```

**Why:** Template-filling produces the same email for every company. Context-aware generation produces emails that read like someone actually researched the company.

---

### Self-Critique + Iterative Refinement (Writer + Critic)

**Concept:** A second LLM call evaluates the first LLM's output on a rubric. If quality is below threshold, the writer rewrites with the specific feedback. Max 2 loops.

**Files:** `agents/writer/critic_agent.py`, `agents/writer/writer_agent.py`

```
Write draft (LLM call 1)
  ↓
Critic evaluates (LLM call 2):
  score=6, feedback="No savings figure. Subject too generic."
  ↓
Score < 7 → rewrite with feedback (LLM call 3)
  ↓
Critic re-evaluates (LLM call 4):
  score=8, passed=True → save draft
```

**Critic rubric** (5 criteria × 0–2 points = 10 max):

| Criterion | Pass condition |
|---|---|
| Personalised | Mentions company name or a specific detail |
| Specific number | Contains a dollar figure, not just "significant savings" |
| Clear CTA | One specific ask — call, audit, or reply |
| Sounds human | Reads like a person wrote it |
| Subject line | Specific to this company, not generic |

**Threshold:** ≥7 to pass. <7 → rewrite. Still <7 after 2 rewrites → `low_confidence=True`.

**Why:** Without evaluation, whatever the LLM produces on the first try gets sent. The Critic catches generic or vague drafts before a human wastes time reviewing them. In practice, ~60–70% of drafts pass on first try.

---

### Uncertainty Flagging (Writer)

**Concept:** When the agent cannot reach its own quality threshold after all retries, it explicitly signals uncertainty rather than silently passing a low-quality result.

**Tech:** `low_confidence` boolean on `EmailDraft`, warning banner in UI

**File:** `agents/writer/writer_agent.py`

```python
low_confidence = not critic_result["passed"]  # True if never passed after 2 rewrites
```

The Email Review page shows a red warning banner on `low_confidence=True` drafts so the human knows to review carefully.

**Why:** Silently saving a 5/10 draft misleads the reviewer. Flagging it says: "the AI struggled here — pay extra attention or regenerate."

---

### Human-in-the-Loop (HITL) Gates

**Concept:** The pipeline pauses at two checkpoints for human review before irreversible actions.

**Tech:** `approved_human` field on `LeadScore` and `EmailDraft`, `HumanApprovalRequest` table, SendGrid notification emails

**Gate 1 — Lead Approval** (after Analyst scores):
- Human reviews leads on `/leads` page — score bar, tier badge, savings estimate
- Approve → `company.status='approved'`, `lead_scores.approved_human=True`
- Reject → `company.status='archived'`
- Notification email sent to `ALERT_EMAIL` with scored lead list + link

**Gate 2 — Draft Approval** (after Writer generates):
- Human reviews drafts on `/emails` page — Approve & Send | Edit + Approve | Reject | Regenerate
- Approve triggers immediate send via SendGrid
- Reject → draft deleted, company resets to `approved` (re-enters Writer queue)
- Notification email sent to `ALERT_EMAIL` with draft list + Critic scores + link

**Why:** LLM output is probabilistic — it can produce confident but wrong results. A misaddressed email or incorrect facts could damage a sales relationship. Human gates ensure no external action happens without sign-off.

---

### Learning from Feedback (Writer + Tracker)

**Concept:** The system tracks which email angles generate replies and biases future generation toward what has worked.

**Tech:** `email_win_rate` table, `get_best_angle()` in Writer, Tracker updates on reply events

**Files:** `agents/writer/writer_agent.py` — `get_best_angle()`, `agents/tracker/tracker_agent.py` — `process_event()`

```
Writer picks angle "audit_offer" for Healthcare company
  ↓
email_drafts.template_used = "audit_offer"
  ↓
Prospect replies positively
  ↓
Tracker: email_win_rate (industry="Healthcare", template_id="audit_offer")
  → replies_received += 1
  → reply_rate recalculated
  ↓
Next Writer run for Healthcare:
  get_best_angle("Healthcare") returns "audit_offer"
  → win rate hint injected into prompt
  → LLM prefers this angle unless company signals suggest otherwise
```

**Cold start protection:** Minimum 5 emails sent before win rate data is trusted (`_WIN_RATE_MIN_SENT = 5`). Below this, the hint is omitted and LLM picks freely.

**The 5 trackable angles:**

| Angle | Lead with |
|---|---|
| `cost_savings` | Dollar savings estimate up front |
| `audit_offer` | Free no-commitment energy audit |
| `risk_reduction` | Utility cost volatility / budget risk |
| `multi_site_savings` | Multi-location efficiency opportunity |
| `deregulation_opportunity` | Open energy market / supplier switch |

---

### Observable Execution (All Agents)

**Concept:** Every agent run is tracked in the database with live counters so humans can see progress and diagnose failures.

**Tech:** `agent_runs` + `agent_run_logs` tables, `/pipeline/run/{run_id}` endpoint

What gets tracked per run:
- `status`: `writer_running` → `writer_awaiting_approval` (or `failed`)
- `current_stage`: updated at each step
- `companies_found`, `companies_scored`, `drafts_created`: live counters
- `error_message`: populated on failure
- `agent_run_logs`: one row per tool call with duration_ms and output_summary

**Why:** Without run tracking, the frontend can only say "running..." or "done". With `agent_runs`, the Triggers page shows "3/8 drafts created" in real time and failed runs can be diagnosed.

---

## What Is NOT Agentic (Intentionally)

Some parts deliberately stay rule-based and deterministic:

| Component | Why it stays rule-based |
|---|---|
| Score formula | `Score = (Recovery × 0.40) + ...` — LLM would hallucinate numbers |
| DB queries | SQL is deterministic and auditable — LLM-generated SQL is unpredictable |
| Email sending | No reasoning needed — if approved, send |
| Score thresholds | Business rules (≥70 = high) — not a judgment call |
| Phone lookup | Waterfall of structured API responses — no reasoning needed |

**Principle:** Use LLM where reasoning, inference, or language generation adds value. Use deterministic code where correctness and auditability matter more.

---

## Technology Stack for Agentic Features

| Feature | Library / Tool |
|---|---|
| Chat ReAct loop | LangChain `create_agent` |
| Writer + Critic LLM calls | `llm_connector.py` wrapping Ollama / OpenAI |
| LLM (default) | Ollama + `llama3.2` (local — zero cost, data stays on-machine) |
| LLM (optional) | OpenAI `gpt-4o-mini` — faster, ~$0.0015/email |
| Run tracking | SQLAlchemy + `agent_runs` table |
| HITL notifications | SendGrid (`email_notifier.py`) |
| Learning memory | PostgreSQL `email_win_rate` table |
| Waterfall state | Module-level flags (`_hunter_blocked`) — process-scoped, zero overhead |

---

## Agentic Maturity by Agent

| Agent | Agentic Capabilities |
|---|---|
| **Chat** | Full ReAct loop, tool use, confidence-gated routing, multi-turn context carry-forward |
| **Writer** | Context-aware generation, Critic self-critique loop, win-rate learning, uncertainty flagging |
| **Analyst** | LLM industry inference, data gap detection, re-enrichment loop (max 2), score narration |
| **Scout** | LLM query planning (3–5 variants), multi-source search, LLM deduplication, source quality learning |
| **Tracker** | LLM + rule-based reply classification, sales alerts, daily stuck-lead health checks |
| **Outreach** | 3-touch follow-up sequence, daily cap guardrail, unsubscribe guard, LLM follow-up polish |
| **Orchestrator** | Pipeline sequencing, task dispatch + retry, HITL gate enforcement, health monitoring |
