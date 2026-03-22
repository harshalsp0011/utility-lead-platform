# Writer Agent

Generates personalized outreach email drafts for approved high-tier companies.

---

## Current Behavior (template + LLM polish)

```
writer_agent.run(company_ids)
  ↓
For each approved company:
  1. Load company, features, score, contact from DB
  2. template_engine.load_template(industry) → loads industry-specific template file
  3. template_engine.fill_static_fields() → fills {{company_name}}, {{savings}}, etc.
  4. llm_connector: LLM polishes subject line and body text
  5. tone_validator: rule-based spam/length/CTA check
  6. If tone fails: regenerate body once
  7. Save draft to email_drafts table
```

No quality evaluation of the output — whatever LLM returns is saved.

---

## Agentic Upgrade — Phase 3

### 1. Context-Driven Generation (replaces template slot-fill)

Instead of filling a template, Writer LLM reads company context and **reasons about the best angle**:

```
Input: company name, industry, site_count, savings_mid, contact name,
       score_reason, state, deregulated (yes/no)

LLM reasons:
  "3-site healthcare company, deregulated NY, $180k savings →
   lead with electricity cost angle + mention audit process"
  OR
  "single-site hospitality, national average rates →
   lead with telecom savings, softer ask"

Output: full email (subject + body) — not a template, reasoned for this company
```

### 2. Critic Agent (new: `critic_agent.py`)

After Writer generates a draft, Critic evaluates it on a 0–10 rubric:

| Criterion | What it checks |
|---|---|
| Personalized | Mentions company name and something specific to them |
| Specific number | Has a dollar figure (e.g. "$180k") not just "significant savings" |
| Clear CTA | Has a specific ask — call, meeting, reply |
| Sounds human | Not template-like, reads naturally |
| Subject line | Specific and relevant, not generic ("reduce your costs") |

Critic returns:
```json
{
  "score": 6,
  "reason": "savings mentioned but no specific dollar figure",
  "instruction": "add the $180k annual savings estimate in paragraph 2"
}
```

### 3. Rewrite Loop

```
Writer generates draft
  ↓
Critic evaluates → score = 6 (< 7)
  ↓
Writer rewrites using Critic's instruction
  ↓
Critic re-evaluates → score = 8 (≥ 7)
  ↓
Save draft → move to human review queue

Max 2 rewrite loops.
If still < 7 after 2 loops: save with low_confidence=true → flagged in UI.
All attempts logged to agent_run_logs.
```

---

## Files

| File | Purpose |
|---|---|
| `writer_agent.py` | Main entry point — coordinates generation, validation, persistence |
| `llm_connector.py` | LLM API calls — Ollama or OpenAI, context-driven generation |
| `critic_agent.py` | **NEW (Phase 3)** — evaluates draft quality 0–10, returns instruction |
| `template_engine.py` | Loads templates, fills static placeholders (still used as base context) |
| `tone_validator.py` | Rule-based spam/length/CTA validation (still runs after Critic approves) |

---

## Learning: email_win_rate

Before generating, Writer queries `email_win_rate` for best-performing angle per industry:

```sql
SELECT angle, reply_rate
FROM email_win_rate
WHERE industry = :industry
ORDER BY reply_rate DESC
LIMIT 1
```

If history exists: LLM is told which angle has the highest reply rate and reasons whether to use it.
If no history: LLM picks angle freely based on company context.

After each reply/open event, Tracker updates `email_win_rate` counters.
After 3+ email cycles, Writer automatically favors angles that have worked before.

---

## Data Contract

Input: companies with `lead_scores.approved_human = true` and `tier = 'high'` and no existing draft.

Output: `email_drafts` row per company with:
- `subject_line` — specific, non-generic
- `body` — personalized, with savings figure, clear CTA
- `template_used` — which industry angle was used
- `low_confidence` — true if Critic score never reached 7 after 2 rewrites
- `company.status` updated to `'draft_created'`

---

## LLM Usage (Phase 3)

- **Provider:** Ollama llama3.2 (local, free) or OpenAI GPT-4o-mini
- **Calls per email:** 2–6 (1 write + 1–2 Critic evaluations + 0–2 rewrites)
- **Tokens per email:** ~1,000
- **Cost with Ollama:** $0
- **Cost with GPT-4o-mini:** ~$0.0015 per email
