# Chat Agent

## Tech Stack Used

| Tech | Purpose |
|---|---|
| **LangChain** (`create_agent`, `@tool`, `AgentExecutor`) | Builds the ReAct agent loop for complex/unknown requests |
| **`langchain_ollama.ChatOllama`** | Local LLM via Ollama (e.g. `llama3.2`) |
| **`langchain_openai.ChatOpenAI`** | Cloud LLM via OpenAI (e.g. `gpt-4o-mini`) |
| **`langchain_core.messages`** (`HumanMessage`, `SystemMessage`) | Wraps all LLM calls — intent classification, summarisation, disambiguation |
| **LangSmith** (`LANGCHAIN_TRACING_V2`) | Distributed tracing — every `run_chat()` call logged to LangSmith project |
| **SQLAlchemy ORM** | Reads `Company`, `LeadScore`, `OutreachEvent`; writes `AgentRun`, `AgentRunLog` |
| **Python `json`** | Parses LLM intent output + tool return values |
| **`uuid`** | Generates `run_id` for `AgentRun` rows |

---

## Agentic Concepts Used

| Concept | Tool / Tech | Where |
|---|---|---|
| LLM Intent Classification | LangChain LLM + `_INTENT_PROMPT` | `_extract_intent()` — one LLM call classifies every user message |
| Confidence-Gated Routing | `_CONFIDENCE_THRESHOLD = 0.65` | `run_chat()` — low confidence triggers disambiguation instead of wrong action |
| Context Carry-Forward | Last 6 messages passed to intent LLM | `_extract_intent()` — resolves follow-ups like "what about medium?" |
| Clarification Before Action | Missing param check → ask user | `search_companies` and `run_full_pipeline` branches |
| Tool Calling | LangChain `@tool` decorator | `_make_tools()` — 6 tools with docstrings the LLM reads to decide which to call |
| Full Agent Loop Fallback | `create_agent()` ReAct loop | `action == "unknown"` branch — handles complex multi-step requests |
| Run Tracing | `AgentRun` + `AgentRunLog` + LangSmith | `_create_run()`, `_log_action()`, `_finish_run()` |

---

## File Breakdown

### `agents/chat_agent.py` — Single-File Agent

The Chat Agent lives in one file: `agents/chat_agent.py`. The public entry point is `run_chat()`.

---

### System Prompt (`SYSTEM_PROMPT` at line 76)

The `SYSTEM_PROMPT` gives the LLM its personality and hard routing rules:

- **Role**: Lead Intelligence Agent for a utility cost consulting firm
- **Critical tool rules**: Greetings, capability questions, confirmations → NO tool call, reply conversationally only
- **`get_leads` argument rules**: Explicit tier words required (`"high tier"`, `"top leads"`) — never guess `tier="high"` for generic requests
- **`search_companies` rules**: Only trigger on explicit external discovery requests
- **Response rules**: Short and direct; never invent company names, scores, or contacts

---

### LLM Factory (`_build_llm()` at line 134)

Returns a LangChain chat model based on `LLM_PROVIDER` setting:

| Setting | Model |
|---|---|
| `"openai"` | `ChatOpenAI(model=LLM_MODEL, api_key=OPENAI_API_KEY, temperature=0)` |
| `"ollama"` (default) | `ChatOllama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, temperature=0)` |

`temperature=0` is set on both — deterministic output for tool routing.

---

### LangSmith Tracing (`_setup_tracing()` at line 53)

Called at module load time (line 69) before any LangChain import initialises its tracer:
```python
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
```
If `LANGCHAIN_API_KEY` is not set, tracing is silently skipped.

---

### Intent Classifier (`_extract_intent()` at line 543)

**Agentic concept: LLM Intent Classification + Context Carry-Forward**

One LLM call per user message. The `_INTENT_PROMPT` at line 477 instructs the LLM to return **only a JSON object**:

```json
{
  "action": "get_leads",
  "confidence": 0.92,
  "tier": "high",
  "industry": "healthcare",
  "location": "",
  "count": 10
}
```

**Context carry-forward**: Last 6 messages (3 turns) from `history` are injected into the prompt:
```
User: show me leads
Agent: Found 12 leads with no filters.
User: what about medium?
```
The LLM reads this and correctly routes "what about medium?" → `get_leads(tier="medium")`.

**Action definitions in the prompt**: Each action has a PURPOSE description (not just keyword triggers), so the LLM understands semantic meaning:
- `get_leads` = read ALREADY stored data (instant, no API calls)
- `search_companies` = external discovery (slow, costs API credits)

**Fallback**: Any JSON parse failure → `{"action": "unknown", "confidence": 0.0}`.

---

### Confidence-Gated Routing (in `run_chat()` at line 657)

**Agentic concept: Confidence-Gated Routing**

After `_extract_intent()` returns, the routing logic checks confidence before acting:

```
confidence < 0.65  AND  action in {get_leads, search_companies, run_full_pipeline, ...}
  → send disambig_prompt to LLM → ask user one clarifying question
  → return immediately, no tool called

confidence ≥ 0.65
  → route to the appropriate action branch
```

This prevents wrong tool calls and hallucination from misclassification — the agent asks instead of guessing.

---

### Tools (`_make_tools()` at line 212)

All 6 tools are created as closures bound to the current `db` session and `run` object. The LLM reads each function's docstring to decide which tool to call and what args to pass.

**Tool 1: `search_companies(industry, location, count=10)` at line 215**
```
1. Set run.status = "scout_running"
2. Log progress to agent_run_logs
3. Call scout_agent.run(industry, location, count, db)
4. Query Company rows for returned company_ids
5. Write results["companies"] list
6. Log success/failure to agent_run_logs
7. Return JSON: {found, industry, location}
```

**Tool 2: `get_leads(tier="", industry="")` at line 275**
- SQLAlchemy JOIN: `Company` LEFT JOIN `LeadScore`
- Optional filters: `func.lower(Company.industry) == industry` and `LeadScore.tier == tier`
- Returns top 50 leads sorted by score descending
- Writes `results["leads"]`

**Tool 3: `get_outreach_history()` at line 317**
- JOIN `Company` + `OutreachEvent` where `event_type = "sent"`
- Returns: company name, city, emailed_at, follow_up_number, status
- Writes `results["outreach_history"]`

**Tool 4: `get_replies()` at line 347**
- JOIN `Company` + `OutreachEvent` where `event_type = "replied"`
- Returns: company name, reply_sentiment, first 200 chars of reply_content, replied_at
- Writes `results["replies"]`

**Tool 5: `run_full_pipeline(industry, location, count=10)` at line 377**
```
1. Set run.status = "scout_running"
2. Call orchestrator.run_full_pipeline(industry, location, count, db)
3. Update run.companies_found, companies_scored, drafts_created
4. Set run.status = "writer_awaiting_approval"
5. Log to agent_run_logs
6. Return JSON summary
```

**Tool 6: `approve_leads(company_ids, approved_by="sales_team")` at line 421**
```
For each company_id in company_ids:
  1. Query latest LeadScore row for company
  2. Set score_row.approved_human = True, approved_by, approved_at
  3. Set company.status = "approved", updated_at = now
4. db.commit()
5. Return JSON: {approved: N, approved_by}
```

---

### Action Routing (`run_chat()` at line 606)

After confidence check, `run_chat()` routes by `action`:

| Action | What happens |
|---|---|
| `conversational` | Direct `llm.invoke([SystemMessage, HumanMessage])` — no tool called |
| `get_leads` | Call tool[1] directly → summarise result with a follow-up LLM call |
| `get_outreach_history` | Call tool[2] directly → summarise result |
| `get_replies` | Call tool[3] directly → summarise result |
| `search_companies` | Check for missing industry/location → clarify if missing → call tool[0] directly |
| `run_full_pipeline` | Check for missing industry/location → clarify if missing → call tool[4] directly |
| `approve_leads` | Full agent loop handles (complex — needs company ID list) |
| `unknown` | `create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)` → ReAct loop |

**Direct tool calls vs agent loop**: For all clearly-classified actions, tools are called directly (`tools[N].invoke()`). The full ReAct agent loop is only used for `unknown` — this avoids hallucination risk from the LLM generating wrong arguments in a multi-step loop.

**Clarification Before Action** (search_companies and run_full_pipeline branches):
```python
missing = []
if not location: missing.append("location (e.g. Buffalo NY)")
if not industry: missing.append("type of companies")

if missing:
    → ask user one short sentence
    → return without calling any tool
```

---

### Run Tracking

Three helpers write to `agent_runs` and `agent_run_logs`:

**`_create_run(db, trigger_input, run_id)` at line 157:**
- Inserts `AgentRun(trigger_source="chat", status="started", current_stage="chat")`

**`_log_action(db, run_id, agent, action, status, ...)` at line 175:**
- Appends `AgentRunLog` row with: agent name, action label, status, output_summary, duration_ms, error_message

**`_finish_run(db, run, status)` at line 201:**
- Sets `run.status` + `run.completed_at`

---

## Full Data Flow

```
run_chat(message, db, run_id, history)
  │
  ├─ _create_run()             → AgentRun(status="started") in DB
  ├─ _build_llm()              → ChatOllama or ChatOpenAI
  ├─ _make_tools()             → 6 LangChain @tool functions (bound to db + run)
  │
  ├─ _extract_intent()         → single LLM call → {action, confidence, tier, industry, location, count}
  │    └─ uses last 6 history messages for context carry-forward
  │
  ├─ Confidence gate:
  │    confidence < 0.65  → disambiguation LLM call → ask user to clarify → return
  │
  ├─ Route by action:
  │    "conversational"        → llm.invoke([System + Human]) → reply
  │    "get_leads"             → tools[1].invoke() → summarise LLM call → reply
  │    "get_outreach_history"  → tools[2].invoke() → summarise LLM call → reply
  │    "get_replies"           → tools[3].invoke() → summarise LLM call → reply
  │    "search_companies"      → missing check → tools[0].invoke() → summarise LLM call → reply
  │    "run_full_pipeline"     → missing check → tools[4].invoke() → summarise LLM call → reply
  │    "unknown"               → create_agent() ReAct loop → reply
  │
  ├─ _finish_run()             → AgentRun(status="completed") in DB
  │
  └─ return {reply, data, run_id}
```

---

## What Gets Written to DB

| Table | Written by | Contents |
|---|---|---|
| `agent_runs` | `_create_run()` | `trigger_source="chat"`, `status`, `current_stage`, `started_at` |
| `agent_runs` | `search_companies` tool | `companies_found`, `status="scout_complete"` |
| `agent_runs` | `run_full_pipeline` tool | `companies_found`, `companies_scored`, `drafts_created`, `status="writer_awaiting_approval"` |
| `agent_runs` | `_finish_run()` | `status="completed"/"failed"`, `completed_at` |
| `agent_run_logs` | `_log_action()` | Every significant action: intent, tool calls, errors, disambiguations |
| `lead_scores` | `approve_leads` tool | `approved_human=True`, `approved_by`, `approved_at` |
| `companies` | `approve_leads` tool | `status="approved"`, `updated_at` |
