# Chatbot Architecture — How It Works

> Last updated: 2026-03-22
> Covers: request flow, memory & context, agentic concepts, tech stack, what is and is not RAG

---

## Table of Contents

1. [Overview](#overview)
2. [Request Flow (end-to-end)](#request-flow-end-to-end)
3. [How Memory & Context Work](#how-memory--context-work)
4. [Is This RAG? (Explained)](#is-this-rag-explained)
5. [Agentic Concepts in Use](#agentic-concepts-in-use)
6. [Tools the Agent Can Call](#tools-the-agent-can-call)
7. [LLM Intent Extraction (Routing)](#llm-intent-extraction-routing)
8. [Observe → Ask → Act Pattern](#observe--ask--act-pattern)
9. [UI Rendering](#ui-rendering)
10. [LLM Configuration](#llm-configuration)
11. [Database Tracking](#database-tracking)
12. [Tech Stack Summary](#tech-stack-summary)

---

## Overview

The chatbot is the **primary interface** for the platform. The user types natural language
and the agent decides what to do — no forms, no buttons required.

The agent is built using **LangChain ReAct** (Reason + Act) on top of either
**Ollama / llama3.2** (local) or **OpenAI GPT-4o-mini** (cloud).

**Key design principle:** The LLM reasons; the code executes.
No rigid keyword lists or regex routing. One LLM call classifies intent → deterministic
Python executes the result.

---

## Request Flow (end-to-end)

```
User types message
       │
       ▼
React Chat UI  (localhost:3000)
  src/pages/Chat.jsx
       │
       │  1. Reads last 6 messages from state (conversation history)
       │  2. POST /chat  { "message": "...", "history": [...last 6 msgs...] }
       ▼
FastAPI  (localhost:8001)
  api/routes/chat.py
       │
       │  3. Spawns background thread — returns run_id immediately
       │  4. Frontend polls GET /pipeline/run/{run_id}  every 2s (live logs)
       │  5. Frontend polls GET /chat/result/{run_id}   every 2s (final reply)
       ▼
agents/chat_agent.py   ← LangChain ReAct agent
       │
       │  6. Calls _extract_intent(message, history, llm)
       │     → single LLM call → returns {action, tier, industry, location, count}
       │
       │  7. Routes deterministically by action:
       │     get_leads       → SQL query on companies + lead_scores
       │     search_companies → check for missing info → ask OR run Scout
       │     run_full_pipeline → check for missing info → ask OR run Orchestrator
       │     get_outreach_history / get_replies → SQL query on outreach_events
       │     unknown         → LangChain ReAct agent loop (free-form reasoning)
       │
       │  8. Tool executes → writes to DB → logs to agent_run_logs
       │
       └── Returns { reply: str, data: dict, run_id: str }
                        │
                        ▼
              Chat UI renders reply + inline data cards
```

---

## How Memory & Context Work

### The problem this solves
Each `/chat` POST is stateless — the server has no memory of prior messages.
Without context, "and low?" after "show me medium leads" would fail because the
server sees only `"and low?"` and has no idea what "low" refers to.

### Solution: Short-Term Conversation Memory (3-layer mechanism)

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: Storage                                               │
│  frontend React state  →  localStorage["chatMessages"]          │
│  Every message (user + agent) is appended and persisted.        │
│  Survives page refresh. Cleared only on "New Chat".             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 2: Context Passthrough                                   │
│  handleSend() in Chat.jsx slices the last 6 messages            │
│  (= ~3 back-and-forth turns) and sends them in the POST body:   │
│                                                                 │
│  POST /chat                                                     │
│  {                                                              │
│    "message": "and low?",                                       │
│    "history": [                                                 │
│      { "role": "user",      "content": "show me medium leads" },│
│      { "role": "assistant", "content": "Here are 4 medium..." } │
│    ]                                                            │
│  }                                                              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 3: LLM Intent Extraction with History                    │
│  _extract_intent() in chat_agent.py builds this prompt:         │
│                                                                 │
│  "Conversation so far:                                          │
│   User: show me medium leads                                    │
│   Agent: Here are 4 medium-tier leads...                        │
│                                                                 │
│   Current message: 'and low?'                                   │
│   Return JSON: {action, tier, industry, location, count}"       │
│                                                                 │
│  LLM reads full context → returns {"action":"get_leads",        │
│  "tier":"low"} — correctly resolved from conversation.          │
└─────────────────────────────────────────────────────────────────┘
```

### Why only 6 messages (not more)?
- Keeps LLM prompt short → faster response, lower token cost
- 3 back-and-forth turns covers 99% of follow-up intent resolution
- Older context is in DB (agent_run_logs) if needed for audit

### What this memory is NOT
- It is **not** persistent across browser sessions after "New Chat"
- It is **not** stored server-side between requests
- It is **not** a vector database or semantic search
- It is **not** RAG (see below)

---

## Is This RAG? (Explained)

**No. This is NOT RAG.**

| Concept | What it means | Do we use it? |
|---|---|---|
| **RAG** (Retrieval-Augmented Generation) | Embed a knowledge base into vectors → at query time, retrieve top-K similar chunks → inject into LLM prompt | ❌ No |
| **Short-term Conversation Memory** | Pass last N messages as text in the prompt for context carry-forward | ✅ Yes (our approach) |
| **Tool-augmented Generation** | LLM calls Python functions (tools) to read live DB data → uses results in its reply | ✅ Yes |
| **Structured Output Extraction** | LLM returns JSON from a free-text analysis (intent extraction) | ✅ Yes |

### When would we add RAG?
RAG would make sense if we wanted the agent to answer questions like:
- "What is our company's outreach policy?"
- "Summarize our Q3 sales strategy document"
- "What did we decide about healthcare pricing last month?"

That would require a vector store (e.g. Chroma, Pinecone, pgvector) and an embedding model.
We do not have that today. Our agent only reads **live database rows**, not documents.

---

## Agentic Concepts in Use

Below is every agentic concept used in this project with a plain-English explanation.

### 1. ReAct (Reason + Act)
**What it is:** A pattern where the LLM alternates between reasoning ("I need to find healthcare companies in Buffalo") and acting (calls `search_companies` tool). Popularized in the [ReAct paper (2022)](https://arxiv.org/abs/2210.03629).
**Where we use it:** `create_agent()` in `chat_agent.py` — LangChain's `AgentExecutor` with `create_react_agent`.
**Tech:** `langchain.agents.create_react_agent`, `langchain.agents.AgentExecutor`

### 2. LLM Intent Extraction (Structured Output)
**What it is:** Instead of regex/keyword routing, we ask the LLM to read the message + history and return structured JSON classifying the user's intent. The LLM reasons; the code acts.
**Where we use it:** `_extract_intent()` in `chat_agent.py`
**Tech:** LLM prompt engineering, JSON parsing with `json.loads()`, fallback to `{"action": "unknown"}`

### 3. Short-Term Conversation Memory (Context Window Memory)
**What it is:** Passing the last N conversation turns directly in the prompt so the LLM can resolve follow-up references ("and low?", "what about those companies?"). This is called **context window memory** — the history lives in the prompt itself, not in a database or vector store.
**Where we use it:** `history` parameter in `run_chat()`, `_extract_intent()`, `handleSend()` in Chat.jsx
**Tech:** Plain JSON array passed in POST body, sliced to last 6 entries

### 4. Tool Use / Function Calling
**What it is:** The LLM can call Python functions (tools) to read/write real data. Each tool has a name, description, and input schema. The agent decides which tool to call based on the user's intent.
**Where we use it:** `@tool` decorated functions in `chat_agent.py`
**Tech:** `langchain.tools` `@tool` decorator, LangChain `AgentExecutor`

### 5. Observe → Ask → Act (Clarification Loop)
**What it is:** Before running an expensive operation, the agent checks if it has enough information. If not, it asks the user — instead of guessing or running with defaults.
**Where we use it:** `search_companies` and `run_full_pipeline` routing in `chat_agent.py` — checks for missing `location` and `industry` before triggering Scout
**Tech:** Conditional logic + targeted LLM prompt to generate a clarifying question

### 6. LLM Query Planner (Multi-Query Search)
**What it is:** Instead of one rigid search query, the LLM generates 3–5 diverse query variants from different angles ("elementary schools Buffalo NY", "primary education institutions western NY", "K-12 school district Buffalo"). Each query hits the search API separately → broader coverage.
**Where we use it:** `agents/scout/llm_query_planner.py` — `plan_queries()`, `plan_retry_queries()`
**Tech:** LLM prompt → parse numbered list → fallback to static queries

### 7. LLM Deduplication
**What it is:** After multi-query search returns many results, an LLM reviews suspicious pairs (similar names, same domain) and decides which are duplicates. Two-pass: fast domain-exact match → LLM name-similarity review.
**Where we use it:** `agents/scout/llm_deduplicator.py` — `deduplicate()`
**Tech:** `difflib.SequenceMatcher` for similarity scoring, LLM for pair review

### 8. Quality Check + Retry Loop
**What it is:** After Scout saves results, if `saved < target * 0.8` (less than 80% of goal), the agent generates new search angles and retries instead of silently returning partial results.
**Where we use it:** `agents/scout/scout_agent.py` — retry loop after `_save_companies()`
**Tech:** Conditional retry with `plan_retry_queries()`, max retry guard

### 9. Background Thread + Polling (Async Agent Execution)
**What it is:** The API spawns the agent in a background thread and returns a `run_id` immediately. The frontend polls two endpoints — one for live progress logs, one for the final result. This keeps the UI responsive during long agent runs.
**Where we use it:** `api/routes/chat.py` — `threading.Thread`, in-memory `_results` dict
**Tech:** Python `threading`, FastAPI background pattern, React `setInterval` polling

### 10. Human-in-the-Loop (HITL)
**What it is:** The agent pauses and waits for human approval before taking irreversible actions (sending emails). Humans review and approve/reject leads and email drafts before the agent proceeds.
**Where we use it:** Lead approval/rejection (`/leads/{id}/approve`), email draft approval (`/emails/{id}/approve`)
**Tech:** PostgreSQL status fields (`approved`, `pending`, `rejected`), FastAPI PATCH endpoints

---

## Tools the Agent Can Call

| Tool | When triggered | What it does |
|---|---|---|
| `search_companies` | "find companies", "search for", "discover X in Y" | Checks for location+industry → asks if missing → runs Scout agent |
| `get_leads` | "show me leads", "high-tier", "scored leads", "low level" | SQL query on `companies + lead_scores`, returns tier + score_reason |
| `get_outreach_history` | "who did we email", "already contacted" | Queries `outreach_events` where type=sent |
| `get_replies` | "any replies?", "who replied", "interested" | Queries `outreach_events` where type=replied |
| `run_full_pipeline` | "run everything", "full pipeline", "start from scratch" | Checks location+industry → asks if missing → runs Orchestrator |

---

## LLM Intent Extraction (Routing)

**Old approach (brittle):** Regex + keyword lists
- `_TIER_KEYWORDS = ["high-tier", "high tier", "top leads", ...]`
- Failed silently on variants like "low level", "top companies", "find me some good ones"

**New approach (robust):** Single LLM call per message

```python
def _extract_intent(message: str, history: list[dict], llm) -> dict:
    """
    Calls LLM with message + last 6 history messages.
    Returns: { action, tier, industry, location, count }
    Falls back to: { "action": "unknown" } on any error.
    """
```

The LLM returns one of these `action` values:
| action | Meaning |
|---|---|
| `get_leads` | User wants to see scored/tiered leads |
| `search_companies` | User wants to find new companies |
| `run_full_pipeline` | User wants end-to-end Scout + Analyst + Writer |
| `get_outreach_history` | User wants to see sent emails |
| `get_replies` | User wants to see replies |
| `unknown` | Free-form / conversational → falls to ReAct agent loop |

**Why this is better:**
- "show me the top ones" → `get_leads, tier=high` ✅
- "can we find low level" → `get_leads, tier=low` ✅
- "what about medium?" (follow-up) → `get_leads, tier=medium` ✅ (via history)
- New phrasing we've never seen → LLM handles it without code changes ✅

---

## Observe → Ask → Act Pattern

Before expensive operations (`search_companies`, `run_full_pipeline`):

```
Intent extracted → check required fields
       │
       ├── location missing? ──► ask: "Which city/region?"
       │
       ├── industry missing? ──► ask: "What type of companies?"
       │
       └── both present? ──────► run Scout / Orchestrator
```

**Without this:** "find 5 religious sector" → Scout would load 78 Buffalo-specific directory
sources with no location filter → useless results.

**With this:** "find 5 religious sector" → agent replies "Could you tell me which city
or region you'd like to search in?" → waits for user input.

---

## UI Rendering

The chat UI (`src/pages/Chat.jsx`) renders agent responses in two parts:

1. **Text bubble** — natural language reply from the agent
2. **Inline data cards** — structured results:
   - `CompanyCard` — name, industry, city, website, source badge
   - `LeadCard` — name, tier badge, score, **score_reason** (LLM-written explanation), approved status
   - `ReplyCard` — name, sentiment badge, reply snippet, date
   - `Pipeline Summary` — companies found, scored, drafts created

**Welcome experience:**
- `WELCOME_VERSION` in localStorage invalidates stale cached welcome messages after UI updates
- Capability cards toggle ("What can I do?") — 4 cards explaining agentic features
- 8 suggestion prompts reflecting current agent capabilities

---

## LLM Configuration

```env
LLM_PROVIDER=ollama          # switch to "openai" for GPT-4o-mini
LLM_MODEL=llama3.2           # or "gpt-4o-mini"
OLLAMA_BASE_URL=http://host.docker.internal:11434
OPENAI_API_KEY=              # fill in if using openai
```

| Provider | Model | Speed | Cost | Best for |
|---|---|---|---|---|
| Ollama | llama3.2 | Medium | Free (local) | Development, privacy |
| OpenAI | gpt-4o-mini | Fast | ~$0.01/call | Production, accuracy |

---

## Database Tracking

Every chat message creates one `agent_runs` row:

```
agent_runs
├── id              (UUID — this is the run_id returned to frontend)
├── trigger_source  = "chat"
├── trigger_input   = { "message": "..." }
├── status          started → scout_running → scout_complete → completed / failed
├── current_stage   chat → scout → analyst → writer → outreach
├── companies_found
├── companies_scored
├── drafts_created
└── error_message
```

Every tool call appends one row to `agent_run_logs`:
```
agent_run_logs
├── run_id          (FK to agent_runs)
├── agent           "scout" | "chat" | "orchestrator"
├── action          "companies_found" | "get_leads" | etc.
├── status          "success" | "failure"
├── output_summary  human-readable result
└── duration_ms
```

---

## Tech Stack Summary

| Layer | Technology | Purpose |
|---|---|---|
| **LLM (local)** | Ollama + llama3.2 | Free local inference |
| **LLM (cloud)** | OpenAI GPT-4o-mini | Production-grade reasoning |
| **Agent framework** | LangChain | ReAct agent, tool binding, prompt templates |
| **API** | FastAPI (Python) | REST endpoints, background threading |
| **Frontend** | React + TailwindCSS | Chat UI, polling, card rendering |
| **Database** | PostgreSQL | Lead data, scores, email drafts, run logs |
| **Web search** | Tavily API | Directory and news search for Scout |
| **Maps search** | Google Maps API | Business discovery for Scout |
| **Containerization** | Docker + docker-compose | Reproducible dev environment |
| **Context memory** | localStorage + POST body | Short-term conversation carry-forward |
| **Deduplication** | difflib + LLM | Domain + name-similarity duplicate removal |

---

## What Is Coming Next (Phase C)

| Feature | Agentic Concept | Status |
|---|---|---|
| Writer generates from company context (not template) | Context-aware generation | Phase C |
| Critic evaluates draft 0–10 → rewrite loop max 2x | Self-critique + reflection loop | Phase C |
| `low_confidence=true` if draft never reaches score 7 | Uncertainty flagging | Phase C |
| Dynamic chat filters (industry, tier, date) | Tool parameter extraction | Phase D |
| pgvector semantic search over leads | RAG (first true RAG in the platform) | Future |
