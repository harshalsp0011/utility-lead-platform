# Writer Agent

## Tech Stack Used

| Tech | Purpose |
|---|---|
| **LangChain** (`langchain_core.messages.HumanMessage`) | LLM calls in `critic_agent.py` |
| **Ollama** (`ollama.Client`) | Local LLM via `llm_connector.call_ollama()` |
| **OpenAI** (`openai.OpenAI`) | Cloud LLM via `llm_connector.call_openai()` |
| **SQLAlchemy ORM** | Reads `Company`, `CompanyFeature`, `LeadScore`, `Contact`, `EmailWinRate`; writes `EmailDraft` |
| **Python `re`** | Regex checks in `tone_validator.py` (spam words, caps, savings claims) |
| **Plain text templates** | `data/templates/email_*.txt` — industry-specific fallback templates |

---

## Agentic Concepts Used

| Concept | Tool / Tech | Where |
|---|---|---|
| Context-Aware Generation | LLM reads `score_reason` from Analyst before writing | `_write_draft()` — `_WRITER_PROMPT` |
| Self-Critique / Reflection Loop | Critic LLM evaluates → Writer rewrites | `while not critic_result["passed"]` loop |
| Learning from Feedback | `EmailWinRate` DB table — best angle per industry | `get_best_angle()` |
| Uncertainty Flagging | `low_confidence=True` when never passes after 2 rewrites | `_save_draft()` field |
| Graceful Degradation | No contact → generic draft, not a skip | `contact_name = "there"` fallback |

---

## File-by-File Breakdown

### 1. `agents/writer/writer_agent.py` — Coordinator + Writer LLM

**Entry point:** `run(company_ids, db_session, run_id, on_progress)` at line 323

Loops over companies, calls `process_one_company()`, emits `on_progress` callbacks for live UI updates, increments `agent_runs.drafts_created` after each success.

**Full pipeline per company — `process_one_company()` at line 382:**

```
1. Load company + features + score from DB
2. Load priority contact (CFO/VP/Facilities) — graceful fallback if none
3. get_best_angle()        → query EmailWinRate for top-performing angle hint
4. Build writer_context    → all company signals + analyst score_reason + angle hint
5. _write_draft()          → Writer LLM generates subject + body + angle
6. critic_agent.evaluate() → Critic LLM scores 0–10 on 5 criteria
7. while score < 7 and rewrites < 2:
     _rewrite_draft()       → Writer LLM rewrites using Critic's feedback
     critic_agent.evaluate() → re-score
8. _save_draft()           → EmailDraft DB row (with critic_score, low_confidence, rewrite_count)
9. company.status = "draft_created"
```

---

### 2. Writer LLM — `_write_draft()` at line 210

**Agentic concept: Context-Aware Generation**

The Writer LLM does **not** fill a template. It reads the full company profile including the Analyst's `score_reason` field, **reasons first** (2–3 sentences) about the best angle, picks an angle, then writes the email.

**`_WRITER_PROMPT`** (line 144) gives the LLM:
- Company name, industry, city, state, site count
- Savings low/mid/high estimates
- Deregulated state flag
- Analyst's `score_reason` — the WHY this company is a good lead
- Contact name + title
- Win rate angle hint (if enough history exists)
- 5 available angles to choose from

**Output format the LLM must return:**
```
REASONING: <2–3 sentence reasoning>
ANGLE: <one of 5 angle names>
SUBJECT: <specific subject line>
BODY:
<email body 100–160 words>
```

Parsed by `_parse_writer_output()` at line 265 — handles two LLM output formats (with and without explicit `BODY:` marker). `_strip_llm_explanation()` at line 253 removes any self-commentary the LLM appends after the email.

---

### 3. `agents/writer/critic_agent.py` — Critic LLM

**Agentic concept: Self-Critique / Reflection Pattern**

A **separate LLM call** acts as quality gatekeeper. The Writer and Critic are two different prompt invocations — generate → evaluate → improve → repeat.

**`evaluate(subject, body, company_context)` at line 100**

Sends `_CRITIC_PROMPT` to LLM with the full email draft + company context. LLM returns structured JSON:

```json
{
  "criteria": {
    "personalization": 2,
    "savings_figure":  1,
    "clear_cta":       2,
    "human_tone":      2,
    "subject_quality": 1
  },
  "score": 8,
  "passed": true,
  "feedback": "Add a specific savings figure — '13% reduction' is vague."
}
```

**Rubric (2 pts each, 10 max):**

| Criterion | What it checks |
|---|---|
| `personalization` | Mentions company name or specific detail — not generic boilerplate |
| `savings_figure` | Specific dollar/% estimate — not "significant savings" |
| `clear_cta` | "free audit", "15-min call", "reply to schedule" — not vague |
| `human_tone` | Reads like a real person, not AI or template |
| `subject_quality` | Specific subject — not "Quick question" / "Hello" |

Score is **recalculated from criteria** (not trusted from LLM arithmetic) at line 152.

On any LLM failure: returns `{"score": 7.0, "passed": True}` — so Writer doesn't loop forever.

---

### 4. Writer + Critic Loop — `process_one_company()` at line 508

```python
_MAX_REWRITES = 2
_PASS_THRESHOLD = 7.0

subject, body, angle = _write_draft(writer_context)
critic_result = critic_agent.evaluate(subject, body, critic_context)

while not critic_result["passed"] and rewrite_count < _MAX_REWRITES:
    rewrite_count += 1
    subject, body, angle = _rewrite_draft(subject, body, critic_result["feedback"], angle)
    critic_result = critic_agent.evaluate(subject, body, critic_context)

low_confidence = not critic_result["passed"]  # True if never passed after 2 rewrites
```

**`_rewrite_draft()`** at line 217 uses `_REWRITE_PROMPT` — shows the LLM the original email + Critic's specific feedback + score. Angle is **preserved** through rewrites; only the content changes.

`low_confidence=True` is saved to the `email_drafts` table — the UI shows these drafts flagged for human review.

---

### 5. `get_best_angle()` at line 96 — Win Rate Learning

**Agentic concept: Learning from Feedback**

Before writing, the Writer queries the `email_win_rate` table for the highest-reply-rate angle for this industry (minimum 5 emails sent). If found, an **angle hint** is injected into the Writer prompt:

```
== WIN RATE HINT ==
For healthcare, the angle 'audit_offer' has the highest reply rate
based on past emails. Prefer this angle unless signals suggest otherwise.
```

Cold start (no history yet) → `angle_hint = ""` → LLM picks freely.

The 5 valid angles:

| Angle | Lead message |
|---|---|
| `cost_savings` | Dollar savings estimate |
| `audit_offer` | Free no-commitment energy audit |
| `risk_reduction` | Utility cost volatility / budget risk |
| `multi_site_savings` | Multi-location efficiency opportunity |
| `deregulation_opportunity` | Open energy market / supplier switch |

---

### 6. `agents/writer/llm_connector.py` — LLM Routing

- `select_provider()` at line 70 — reads `LLM_PROVIDER` env var, validates it's `"ollama"` or `"openai"`
- `call_ollama(prompt)` at line 16 — uses `ollama.Client(host=OLLAMA_BASE_URL).chat(model=LLM_MODEL, ...)`; handles both old (dict) and new (object) `ollama` SDK response formats
- `call_openai(prompt)` at line 46 — uses `openai.OpenAI(api_key=...).chat.completions.create(...)` with `temperature=0.7`, `max_tokens=1000`

Note: Writer uses `llm_connector` directly (not LangChain). Critic uses LangChain `HumanMessage`. Both call the same underlying model.

---

### 7. `agents/writer/tone_validator.py` — Spam + Tone Safety Checks

**No LLM. Pure rule-based regex.**

`validate_tone(subject, body)` at line 35 runs 5 checks and returns a 0–10 score:

| Check | Function | Rule |
|---|---|---|
| Spam words | `check_spam_words()` | Flags: "free", "guaranteed", "act now", "click here", etc. |
| Length | `check_length()` | Body must be 50–250 words |
| CTA present | `check_cta_present()` | Must contain: "call", "schedule", "meeting", "chat", etc. |
| Caps usage | `check_caps_usage()` | Max 3 ALL-CAPS words |
| Savings claim | `check_savings_claim()` | Flags any claim > $50M as unrealistic |

Score = `10 - (2 × number_of_issues)`.

---

### 8. `agents/writer/template_engine.py` — Fallback Template System

Industry-specific `.txt` templates in `data/templates/`:

| Industry | Template file |
|---|---|
| healthcare | `email_healthcare.txt` |
| hospitality | `email_hospitality.txt` |
| manufacturing | `email_manufacturing.txt` |
| retail | `email_retail.txt` |
| public_sector | `email_public_sector.txt` |

Follow-up templates: `followup_day3.txt`, `followup_day7.txt`, `followup_day14.txt`

`fill_static_fields(template, context)` at line 44 — replaces `{{placeholder}}` tokens. Unknown placeholders are left unchanged. This is the **fallback path** — primary path is the LLM Writer.

---

## What Gets Written to DB

| Table | Written by | Contents |
|---|---|---|
| `email_drafts` | `_save_draft()` | subject, body, angle, savings_estimate, critic_score, low_confidence, rewrite_count, `approved_human=False` |
| `companies` | `process_one_company()` | status → `"draft_created"` |
| `agent_runs` | `run()` | `drafts_created` counter incremented live |

---

## Full Data Flow

```
run(company_ids)
  └─ for each company_id:
       process_one_company()
         │
         ├─ DB load: Company + CompanyFeature + LeadScore
         ├─ enrichment_client.get_priority_contact()  ← CFO/VP/Facilities from contacts table
         ├─ get_best_angle()                          ← EmailWinRate table → angle hint
         │
         ├─ _write_draft()
         │    └─ _WRITER_PROMPT.format(context)
         │         → llm_connector.call_ollama() or call_openai()
         │         → _parse_writer_output()           ← extracts SUBJECT / BODY / ANGLE
         │
         ├─ critic_agent.evaluate()
         │    └─ _CRITIC_PROMPT → LangChain HumanMessage → LLM
         │         → JSON: {score, passed, feedback, criteria}
         │
         ├─ while score < 7 and rewrites < 2:
         │    ├─ _rewrite_draft()  ← _REWRITE_PROMPT with original + feedback
         │    └─ critic_agent.evaluate()
         │
         ├─ _save_draft()   → EmailDraft DB row
         └─ company.status = "draft_created"
```
