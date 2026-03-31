# Utility Lead Intelligence Platform

AI-assisted B2B prospecting and outreach automation for utility cost-reduction sales teams. The platform runs a full pipeline from lead discovery to personalized email delivery — with two human approval checkpoints and no email ever sent without explicit review.

---

## What This Book Covers

This Jupyter Book is the deep technical documentation for every agent in the platform:
- What the agent does and why
- File names and key functions with line numbers
- Agentic concepts, tools, and technologies used
- Data flow diagrams and DB write tables

---

## Platform Overview

The platform is structured around a pipeline of specialized agents:

| Agent | Entry Point | Role |
|---|---|---|
| **Scout** | `agents/scout/scout_agent.py` | Discovers companies from news, Google Maps, Yelp, and directory scraping |
| **Analyst** | `agents/analyst/analyst_agent.py` | Enriches contacts, scores leads 0–100, estimates utility savings |
| **Writer** | `agents/writer/writer_agent.py` | Generates personalized outreach emails via LLM + Critic review loop |
| **Outreach** | `agents/outreach/outreach_agent.py` | Sends emails via SendGrid/Instantly, manages 3-touch follow-up sequences |
| **Tracker** | `agents/tracker/tracker_agent.py` | Classifies replies via LLM, updates lead status, alerts sales team |
| **Orchestrator** | `agents/orchestrator/orchestrator.py` | Chains all agents, manages task dispatch, retry, health monitoring, and weekly reports |
| **Chat Agent** | `agents/chat_agent.py` | Natural-language interface — intent classification, confidence-gated routing, 6 tools |

---

## Pipeline Flow

```
Scout finds companies (news + APIs)
        │
        ▼
Analyst enriches contacts + scores 0–100
        │
        ▼
  [HUMAN REVIEW #1]  ← Leads page: approve or skip each company
        │
        ▼
Writer drafts personalized email → Critic reviews → rewrites if needed
        │
        ▼
  [HUMAN REVIEW #2]  ← Email Review page: approve / edit / reject
        │
        ▼
Outreach sends email via SendGrid + schedules follow-ups (Day 3 / 7 / 14)
        │
        ▼
Tracker classifies replies → updates lead status → alerts sales team
```

---

## Full Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Agent framework | **LangChain** (`create_agent`, `@tool`, `AgentExecutor`) | ReAct loops, tool calling, LLM message wrapping |
| LLM (local) | **Ollama** + `llama3.2` | Default LLM provider — runs on-machine |
| LLM (cloud) | **OpenAI** `gpt-4o-mini` | Optional — set `LLM_PROVIDER=openai` |
| Tracing | **LangSmith** | Visual trace per agent run — LLM calls, tool args, latency |
| Search | **Tavily API** | Web search + news search for company discovery |
| Maps | **Google Places API v1** | Business discovery + phone lookup |
| Business search | **Yelp Business Search API** | Company discovery + phone fallback |
| Contact enrichment | **Apollo**, **Hunter.io**, **Prospeo**, **Snov.io** | Decision-maker email/title waterfall |
| Email verification | **ZeroBounce** | Email address validation |
| HTML parsing | **BeautifulSoup4** | Directory scraping with pagination |
| Email delivery | **SendGrid SDK** | Outreach sending with open/click tracking |
| Email delivery (alt) | **Instantly API** | Alternative provider via `EMAIL_PROVIDER` env var |
| Webhooks | **FastAPI + Uvicorn** | SendGrid inbound reply/open/click/bounce webhooks (port 8002) |
| Webhook security | **HMAC-SHA256** (`hashlib`, `hmac`) | SendGrid webhook signature validation |
| ORM | **SQLAlchemy** | All DB reads and writes across all agents |
| Database | **PostgreSQL** | External — not in Docker |
| Containerization | **Docker + nginx** | 2 containers: `api` + `frontend` |
| Scheduling | **Airflow** (add-on) | Optional daily pipeline scheduling |

---

## How to Read This Book

| Chapter | What it covers |
|---|---|
| **System Architecture** | Full pipeline flow, all 8 stages, data model, company status lifecycle, agent responsibilities, config reference |
| **Agentic Design** | What "agentic" means here, every agentic concept used (Tool Use, ReAct, HITL, Critic loop, Win-Rate Learning…), where each fires in the pipeline |
| **Agents: Deep Technical Walkthrough** | One chapter per agent — file names, function names, line numbers, tech stack, data flow diagrams |

Start with **System Architecture** for the big picture, then **Agentic Design** to understand the reasoning patterns, then dive into individual agent chapters in pipeline order: Scout → Analyst → Writer → Outreach → Tracker → Orchestrator → Chat Agent.

```{tableofcontents}
```
