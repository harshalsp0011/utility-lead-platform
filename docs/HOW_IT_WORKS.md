# How the Utility Lead Platform Works
### A Plain-English Guide for Business Stakeholders

> **What this is:** An AI-powered Multi-Agent Lead Intelligence Platform for utility cost-reduction consulting. Specialized agents (Scout, Analyst, Writer) discover high-spend companies, research and score them, and draft personalized outreach — with human approval before anything is sent.

---

## 1. The Problem

B2B sales for utility cost-reduction consulting is a research-heavy, manual process. Every deal starts with:

- **Finding the right company** — who has high utility spend and might be overpaying?
- **Finding the right contact** — who at that company makes the decision?
- **Writing a credible, personalized email** — not a generic blast, but something specific to their situation
- **Following up multiple times** — most deals require 3–5 touches before a response
- **Tracking what happened** — who opened, who replied, who went cold?

Done manually, a sales rep spends 3–5 hours per lead before a single conversation happens. Most of that time is research and writing — not selling.

The result: reps spend the majority of their time on work that AI can do better and faster, leaving less time for the actual conversations that close deals.

### What specifically breaks down without this system

| Pain Point | What happens without it |
|---|---|
| **Lead discovery is reactive** | You find leads from referrals or cold lists — not from real-time signals |
| **Research is inconsistent** | Each rep does it differently; quality varies; important signals get missed |
| **Outreach is generic** | Templates lack personalization; low open and reply rates |
| **Follow-up falls through** | Busy reps forget; timing is inconsistent; deals die in silence |
| **No institutional memory** | When a rep leaves, their lead knowledge leaves with them |
| **CRM is always behind** | Reps manually update it — or don't |

---

## 2. The Architecture

The platform is built around a **multi-agent pipeline** — a chain of specialized AI agents, each with a defined job, that work together to move a company from "discovered in the news" to "email sent and follow-ups scheduled."

### Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│   NEWS / WEB / DIRECTORIES / MANUAL ENTRY / CRM IMPORT          │
│                         ↓                                       │
│   ┌─────────────┐    ┌──────────────┐    ┌──────────────┐       │
│   │  SCOUT      │    │  ANALYST     │    │  WRITER      │       │
│   │  Agent      │ →  │  Agent       │ →  │  Agent       │       │
│   │             │    │              │    │  + Critic    │       │
│   │ Finds       │    │ Enriches     │    │              │       │
│   │ companies   │    │ Contacts     │    │ Drafts       │       │
│   │ from news   │    │ Scores 0–100 │    │ personalized │       │
│   │ + signals   │    │ + explains   │    │ email        │       │
│   └─────────────┘    └──────────────┘    └──────────────┘       │
│                                                                  │
│         ↓ [HUMAN REVIEW #1]              ↓ [HUMAN REVIEW #2]    │
│         Approve / Skip leads             Approve / Edit / Reject │
│         on Leads page                    on Email Review page    │
│                                                                  │
│   ┌─────────────┐    ┌──────────────┐                           │
│   │  OUTREACH   │    │  TRACKER     │                           │
│   │  Agent      │ →  │  Agent       │                           │
│   │             │    │              │                           │
│   │ Sends email │    │ Monitors     │                           │
│   │ Schedules   │    │ opens/clicks │                           │
│   │ follow-ups  │    │ replies      │                           │
│   └─────────────┘    └──────────────┘                           │
│                                                                  │
│                    ↓ CRM sync (API + webhooks)                   │
│             Your CRM (HubSpot, Salesforce, Pipedrive…)           │
└─────────────────────────────────────────────────────────────────┘
```

### Two Approval Checkpoints — Nothing Moves Without a Human

The pipeline has two mandatory stops where a human must review and approve before the next stage begins:

1. **After Analyst scores** → Human reviews the lead on the Leads page (approve = email gets written, skip = company stays in queue, reject = archived)
2. **After Writer drafts** → Human reads the email on the Email Review page (approve = send, edit+approve = modify then send, reject = discard draft)

No email is ever sent without explicit human sign-off.

### System Components

| Component | Technology | Purpose |
|---|---|---|
| Dashboard | React + Vite + Tailwind | Visual interface — Leads, Email Review, Pipeline, Triggers |
| Chatbot | React + LangChain | Natural-language interface for all pipeline actions |
| API | FastAPI + Uvicorn | REST backend — all agents run inside this process |
| Agents | LangChain ReAct framework | Scout, Analyst, Writer, Outreach, Tracker |
| LLM | Ollama (local) or OpenAI | Reasoning, writing, evaluation, explanation |
| Database | PostgreSQL + SQLAlchemy | All companies, contacts, scores, emails, events |
| Email delivery | SendGrid | Outbound sending with open/click tracking |
| Containers | Docker (2 containers) | API + Frontend — deploys anywhere |
| Scheduler | Airflow (add-on) | Optional daily pipeline scheduling |

---

## 3. Tools the Agents Use

Agents don't do everything themselves — they call tools. A tool is a specific, reliable function the agent can invoke when it needs information or needs to take action. The LLM decides *when* and *why* to call each tool; the tool executes the action deterministically.

### Scout Agent Tools

| Tool | What it does |
|---|---|
| `tavily_news_search` | Searches business news for facility openings, expansions, new locations |
| `google_maps_search` | Finds businesses in a geography by industry category |
| `yelp_business_search` | Business listings with location, category, size signals |
| `directory_scraper` | Scrapes configured business directories (Yellow Pages, etc.) |
| `save_company` | Writes discovered company to database |
| `deduplicate_check` | Checks if company already exists before saving |

### Analyst Agent Tools

| Tool | What it does |
|---|---|
| `hunter_email_search` | Finds email addresses by company domain |
| `apollo_contact_lookup` | Business contact database — name, title, email |
| `website_scraper` | Scrapes company's own site for contact info |
| `serper_search` | Google search for "VP Operations [Company Name]" |
| `snov_contact_lookup` | Additional contact database |
| `prospeo_linkedin_lookup` | LinkedIn-based contact enrichment |
| `zerobounce_verify` | Verifies email addresses are deliverable |
| `email_permutation` | Constructs likely formats (first.last@domain.com) |
| `google_places_phone` | Phone number lookup via Google Maps |
| `compute_score` | Deterministic math: score 0–100 from enriched data |
| `save_contact` | Writes verified contact to database |
| `save_score` | Writes score + explanation to database |

### Writer Agent Tools

| Tool | What it does |
|---|---|
| `read_company_profile` | Loads company data, score, and narrative from DB |
| `read_email_win_rate` | Reads which email angles have worked for this industry |
| `read_service_memory` | Loads your company's service knowledge (see Section 8) |
| `llm_write_draft` | Generates personalized email: subject + body |
| `llm_critique_draft` | Critic evaluates draft on 5 criteria, returns score + notes |
| `save_email_draft` | Writes draft to queue for human review |

### Outreach Agent Tools

| Tool | What it does |
|---|---|
| `sendgrid_send` | Sends email via SendGrid with tracking enabled |
| `schedule_followup` | Creates 3 follow-up records in DB (Day 3, 7, 14) |
| `update_company_status` | Sets status = `contacted` after send |
| `log_outreach_event` | Records send event in `outreach_events` table |

### Tracker Agent Tools

| Tool | What it does |
|---|---|
| `get_due_followups` | Queries DB for follow-ups due today |
| `send_followup_email` | Sends the due follow-up via SendGrid |
| `cancel_remaining_followups` | Cancels Day 7 + 14 when a reply arrives |
| `log_reply_event` | Records reply event, updates `email_win_rate` |
| `alert_sales_team` | Sends notification email to sales team |

---

## 4. How the System Is Agentic

### What "Agentic" Means

A traditional automation system is a fixed script:

```
Step 1 → Step 2 → Step 3 → Done
```

If a step fails or the data looks different than expected, the script fails or produces wrong output. It cannot adapt.

An **agentic system** is different. Each agent follows an **Observe → Reason → Act → Reflect** loop — it looks at what it has, decides what to do, does it, checks if the result is good enough, and either continues or tries a different approach.

```
┌─────────────────────────────────────────────────────┐
│                   AGENT LOOP                        │
│                                                     │
│   OBSERVE          What data do I have?             │
│      ↓             What's the situation?            │
│   REASON           What should I do next?           │
│      ↓             Which tool should I call?        │
│   ACT              Execute the tool                 │
│      ↓             Get a result                     │
│   REFLECT          Is this good enough?             │
│      ↓             If yes → continue or finish      │
│      └──────────── If no  → try a different tool    │
│                            or adjust parameters     │
└─────────────────────────────────────────────────────┘
```

### The Scout Agent — Observe, Reason, Act, Reflect

**Observe:** The Scout is given a target — e.g., "find healthcare companies in Ohio with high utility spend potential."

**Reason:** It thinks about what search queries would surface the right signals — not one generic query but multiple variations targeting different intent signals (new construction, expansions, multi-site operations).

**Act:** Runs Tavily news search, Google Maps search, Yelp search in parallel. Gets results back.

**Reflect:** Evaluates each result — *Is this company relevant? Does it have the right industry? Is it new or already in our database? Is the signal strong enough?* Filters out irrelevant results. If a source returned too few results, it generates a new query variation and tries again.

```
Scout reasons: "search returned only 2 results for Ohio manufacturing"
→ generates alternate query: "Ohio factory expansion utility"
→ runs again → gets 8 more results
→ filters to 4 that are new and relevant
→ saves 4 companies to database
```

### The Analyst Agent — Observe, Reason, Act, Reflect

**Observe:** Loaded a company from the database. Has: name, city, industry. Missing: contact, phone, employee count.

**Reason:** Decides to start with Hunter.io (usually fastest for email by domain), then fall back to Apollo if Hunter fails.

**Act:** Calls `hunter_email_search`. Returns: no result for this domain.

**Reflect:** Hunter failed. Move to next source. Calls `apollo_contact_lookup`. Returns: David Chen, VP Facilities, david.chen@midwestsurgical.com.

**Reason again:** Email found but not verified. Calls `zerobounce_verify`. Returns: valid, deliverable. Good.

**Reflect again:** Contact complete. Now score. Calls `compute_score`. Runs the formula. Returns 84/100. Now writes the plain-English explanation.

```
Analyst reasons: "3-site healthcare company in Ohio (deregulated state),
                  estimated $210k spend, contact verified"
→ generates: "High savings potential. Strong audit candidate."
→ saves score + narrative to database
→ status → "scored", queued for human review
```

### The Writer Agent — Observe, Reason, Act, Reflect

**Observe:** Company profile loaded. Score: 84. Industry: healthcare. Contact: VP of Facilities. Past email performance: healthcare audit_offer angle has 34% reply rate.

**Reason:** Best angle for this industry is `audit_offer`. Use Indiana deregulation as the hook. Pull healthcare case study from service memory.

**Act:** Generates draft email. Subject: *"Cold storage operators in Indiana are overpaying — here's why"*. Body: personalized to 3-location footprint, estimated savings, 15-minute call ask.

**Reflect (Critic):** Second LLM call. Evaluates draft:
- Personalization: 9/10 — mentions 3 locations, Indiana, specific dollar estimate
- Savings figure: 10/10 — "$60–90k annual savings" quoted
- Clear CTA: 8/10 — one clear ask for 15-minute call
- Human tone: 7/10 — slightly formal in paragraph 2
- Subject line: 8/10 — specific and curiosity-driving

**Reflect outcome:** Score = 8.4/10. Above threshold. Save to review queue.

*If score had been 5/10:* Critic provides specific notes → Writer rewrites → Critic re-evaluates → up to 2 rewrites before flagging as low-confidence.

---

## 5. AI Reliability Architecture

### ReAct — Reasoning + Acting

The agents in this platform use the **ReAct pattern** (Reasoning + Acting) — a standard design for reliable AI agents. Every time an agent needs to do something, it follows the same structure internally:

```
Thought:  What is the situation? What do I need to figure out?
Action:   Which tool should I call? What parameters?
Observation: What did the tool return?
Thought:  What does this result mean? Is it enough? What next?
Action:   Call the next tool, or return final result.
```

This is not a metaphor — it is the literal structure of each agent's reasoning trace. Every thought, action, and observation is logged to `agent_run_logs` so the full reasoning chain is auditable.

Example trace from the Analyst agent:

```
Thought: Need to find contact for Midwest Surgical Associates.
         Domain is midwestsurgical.com. Try Hunter.io first.
Action:  hunter_email_search(domain="midwestsurgical.com")
Observation: No results returned.

Thought: Hunter failed. Try Apollo with company name.
Action:  apollo_contact_lookup(company="Midwest Surgical Associates", title="VP")
Observation: Found David Chen, VP of Facilities, david.chen@midwestsurgical.com

Thought: Email found. Need to verify it's deliverable before saving.
Action:  zerobounce_verify(email="david.chen@midwestsurgical.com")
Observation: Status = valid, deliverable

Thought: Contact complete. Proceed to scoring.
Action:  compute_score(company_id=..., industry="healthcare", ...)
Observation: score=84, tier="high"

Thought: Score computed. Generate explanation.
Action:  llm_narrate(score=84, company_data=...)
Observation: "3-site healthcare operator in deregulated Ohio..."

Thought: All steps complete. Save and queue for human review.
Action:  save_score(...) → save_contact(...) → update_status("scored")
```

### Guardrails — What the System Cannot Do

Guardrails are hard constraints built into the system — rules that cannot be overridden by the LLM or by any agent:

| Guardrail | Where it's enforced | What it prevents |
|---|---|---|
| **No send without human approval** | `send_email()` checks `approved = true` | Sending unapproved drafts |
| **Daily send limit** | `email_sender.py` checks count before every send | Spamming — default cap 50/day |
| **Unsubscribe block** | Contact lookup checks opt-out list before send | Contacting people who unsubscribed |
| **Email verification required** | ZeroBounce called before contact is saved | Sending to invalid/bouncing addresses |
| **Critic score threshold** | Writer will not queue draft below threshold | Sending low-quality emails |
| **Max rewrite limit** | Critic loop capped at 2 rewrites | Infinite Writer loops |
| **Deduplication** | Scout checks DB before saving | Duplicate companies in pipeline |

### HITL — Human in the Loop

**Human-in-the-Loop (HITL)** means that at defined checkpoints, the system stops and waits for a human decision. The AI cannot proceed past these points on its own.

```
┌─────────────────────────────────────────────────────────────────┐
│                  HUMAN-IN-THE-LOOP CHECKPOINTS                  │
│                                                                 │
│   CHECKPOINT 1 — Lead Review                                    │
│   ─────────────────────────                                     │
│   After: Analyst scores a company                               │
│   Human sees: company name, score, tier, score explanation,     │
│               contact name and title                            │
│   Options:                                                      │
│     ✓ Approve  → Writer drafts an email                         │
│     ⊘ Skip     → stays in queue (no action yet)                 │
│     ✗ Reject   → archived (not deleted)                         │
│                                                                 │
│   CHECKPOINT 2 — Email Review                                   │
│   ─────────────────────────                                     │
│   After: Writer generates a draft                               │
│   Human sees: full email (subject + body), contact details,     │
│               company score, Critic score                       │
│   Options:                                                      │
│     ✓ Approve & Send  → email goes out immediately              │
│     ✎ Edit & Send     → human edits inline, then sends          │
│     ✗ Reject          → draft discarded, company reset          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Why both checkpoints exist:**

- **Checkpoint 1** catches companies that scored high by the numbers but are not actually a good fit for a business reason — maybe you already know this company, or there's a relationship reason to hold off.
- **Checkpoint 2** catches emails that are technically correct but feel off — wrong tone, wrong contact, missing context that the human knows but the system doesn't.

The AI does the research and the writing. The human makes the judgment calls. That is the right division of labor.

---

## 6. How the System Finds Companies

The Scout agent doesn't wait for leads to come to you. It actively searches for companies that show **intent signals** — events in the news or business directories that correlate with high utility spend.

### What Signals It Looks For

| Signal | Why it matters |
|---|---|
| **New facility opening** | Moving into a large building = new utility contract to negotiate |
| **Production expansion** | Scaling manufacturing = more energy consumption |
| **Multi-location growth** | Chains across multiple sites = aggregate spend across all locations |
| **Healthcare construction** | Hospitals and clinics = among the highest utility consumers per sq ft |
| **Cold storage / logistics** | 24/7 refrigeration = very high energy intensity |
| **Data center announcements** | Most energy-intensive facilities in existence |

### Where It Searches

| Source | What it finds |
|---|---|
| **Tavily news search** | Business news, press releases — "XYZ Corp opens 200,000 sq ft distribution center in Ohio" |
| **Google Maps / Places** | Local businesses in a given city/region, filtered by industry |
| **Yelp Business Search** | Business listings with location and category data |
| **Directory scraper** | Configured directories (Yellow Pages, local industry directories) |

### Example — Scout in Action

> Tavily returns: *"Midwest Surgical Associates breaks ground on new 85,000 sq ft medical campus in Columbus, OH"*
>
> Scout extracts: company = Midwest Surgical Associates, industry = healthcare, city = Columbus, state = OH, signal = new facility construction
>
> Dedup check: not in database → saved as new company

---

## 7. How the System Researches a Company

Once a company is saved, the Analyst runs an 8-source enrichment waterfall to find the right contact, then scores the company.

### Contact Enrichment Waterfall

```
1. Hunter.io          — email search by company domain
2. Apollo             — business contact database
3. Website scraper    — scrapes company's own site
4. Serper / Google    — "VP Operations [Company Name]" search
5. Snov.io            — additional contact database
6. Prospeo            — LinkedIn-based contact enrichment
7. ZeroBounce         — verifies email is deliverable
8. Permutation guess  — constructs likely formats (first.last@domain.com)
```

The agent stops as soon as it finds a verified, deliverable contact. It does not call all 8 sources for every company — it calls them in order and stops when it has what it needs.

Goal: **full name, verified job title, verified email, phone number** for the best decision-maker (VP of Operations, Facilities Manager, Director of Finance, or CFO).

### Scoring Formula

```
Score (0–100) = (Estimated savings potential  × 40%)
              + (Industry fit                 × 25%)
              + (Multi-site factor            × 20%)
              + (Data quality / completeness  × 15%)
```

- **≥ 70 = High Tier** — prioritized for outreach
- **40–69 = Medium Tier** — worth reviewing, lower priority
- **< 40 = Low Tier** — typically skipped unless manually approved

After scoring, the LLM writes a plain-English explanation:

> *"3-site healthcare operator in Ohio — a deregulated state. Estimated $210k annual utility spend with ~$50k savings potential. Contact verified. Strong audit candidate."*

### Example — Research Output

> **Company:** Midwest Surgical Associates
> **Contact:** David Chen, VP of Facilities — david.chen@midwestsurgical.com — (614) 555-0182
> **Score:** 84 / 100 — High Tier
> **Reason:** "3-site healthcare operator in Ohio (deregulated). Estimated $210k annual utility spend. High savings potential from supply-side audit. Contact verified."

---

## 8. The Writer Agent Knows Your Business

The Writer is not a generic AI email generator. It is configured with your company's specific knowledge so every email it produces is grounded in what you actually offer.

### What You Can Embed as Service Memory

- **Your service offering** — "We audit energy contracts across natural gas and electricity, typically finding 8–24% savings in year one"
- **Industry-specific talking points** — different angles for hospitals vs. manufacturers vs. logistics
- **Past success stories** — "We saved a 12-location restaurant chain $340k over two years"
- **Your pricing model** — contingency-based, no upfront cost, etc.
- **Your sender's background** — "Jane is a former utility pricing analyst with 15 years of experience"

When writing for a healthcare company, the Writer pulls the healthcare angle and a relevant case study. For a manufacturer, it uses the manufacturing angle. The email reads like it was written by someone who knows both the prospect's situation and your business.

### The Critic Loop

After every draft, a second LLM (the Critic) evaluates on five criteria:

| Criterion | What it checks |
|---|---|
| Personalization | Is the email specific to *this* company, not generic? |
| Savings figure | Is a specific dollar estimate included? |
| CTA clarity | Is there one clear ask — not three vague ones? |
| Human tone | Does it sound like a person wrote it? |
| Subject line | Is the subject line specific enough to earn an open? |

Score ≥ 7 → saved to review queue. Score < 7 → Writer rewrites with the Critic's specific notes. Maximum 2 rewrites. If still below threshold after 2 attempts, flagged as `low_confidence = true` in the queue so the reviewer knows to look carefully.

### The System Learns What Works

Every sent email angle is tracked. When a reply comes in, the system records which angle worked, for which industry. The Writer reads this history and naturally shifts toward angles that get responses — without anyone manually configuring it.

---

## 9. The Chatbot — Control Everything in Plain English

The sales team does not need to use the dashboard to run the pipeline. The chatbot lets anyone on the team control the system by typing what they want.

### What You Can Say

| What you type | What happens |
|---|---|
| `"Find healthcare companies in Columbus Ohio"` | Scout runs, results appear in chat |
| `"Show me all high-tier leads we haven't contacted yet"` | Filtered lead list appears |
| `"Approve the top 5 leads"` | Those leads approved, move to writing queue |
| `"Run the analyst on new companies"` | Analyst starts enrichment and scoring |
| `"Write emails for all approved leads"` | Writer drafts for all ready leads |
| `"Show me emails waiting for my review"` | Draft queue appears |
| `"Approve the email for Midwest Surgical"` | Email approved and sent |
| `"Who replied to our emails this week?"` | Reply list with contact details |
| `"Run the full pipeline for manufacturing in Chicago"` | Scout → Analyst → Writer chain runs |

### How It Understands You

The chatbot uses the same LLM + ReAct pattern as the pipeline agents. It doesn't match keywords to commands — it reasons about intent:

```
You type: "how many healthcare leads are ready to go?"

Chatbot reasons:
  "healthcare" → filter industry = healthcare
  "ready to go" → status = approved (email written, pending review)
  "how many" → count query

Returns: "You have 7 healthcare leads with emails ready for your review."
```

No training required. No commands to memorize.

### Manual Entry via Chatbot

If you meet someone at a conference, get a referral, or want to add a company the Scout hasn't found:

> *"Add ABC Manufacturing in Detroit, contact is Sarah Johnson, VP Operations, sarah.johnson@abcmfg.com"*

The system creates the company and contact immediately and sends it through the same enrichment and scoring pipeline as any other lead.

---

## 10. This Is Not a CRM Replacement

**This platform is not a replacement for your CRM. It is an advanced intelligence plugin that sits in front of your CRM and makes it smarter.**

A traditional CRM (HubSpot, Salesforce, Pipedrive — any of them) is a record-keeping system. It stores what you manually put into it. Someone has to find the lead, research them, write the email, and log everything by hand. The CRM is a filing cabinet.

This platform is the intelligence layer that does all that work automatically, then pushes the results to your CRM via API and webhooks.

```
[This Platform]                    [Your CRM — any CRM with API/webhooks]
─────────────────────────────      ──────────────────────────────────────
Finds leads from news              Stores the contact record
Researches and scores them         Shows the sales team their pipeline
Writes the outreach email          Receives replies and meeting bookings
Sends and follows up               Tracks deal stage and history
Updates status automatically  →→→  CRM deal stage updated in real time
```

**How the integration works:**
- **Push (Platform → CRM):** After an email is sent, the platform creates or updates the contact and deal in your CRM via the CRM's REST API. As status changes (replied, meeting booked, won), the deal stage updates automatically.
- **Pull (CRM → Platform):** When a prospect replies or books a meeting, your CRM fires a webhook to the platform. The platform cancels follow-ups, updates pipeline status, and alerts the sales team.

*Example with HubSpot:* after send → `POST /crm/v3/objects/deals` creates the deal. When a reply arrives in HubSpot → HubSpot fires `POST /api/webhooks/crm/reply` to the platform. The same pattern works with Salesforce, Pipedrive, Zoho, or any CRM with outgoing webhooks.

Think of it this way: your CRM is the front desk. This platform is the research team, the copywriter, and the outreach coordinator — fully automated, reporting back to the front desk in real time.

---

## 11. Every Lead Is Stored — Forever

The system stores every company it encounters — regardless of whether they become a customer, reply, or never respond.

This is deliberate. A company that didn't reply today might be the right prospect in six months when their energy contract comes up for renewal. A lead that scored too low this quarter might be worth revisiting after they expand.

The full history of every company is preserved:
- When it was discovered and from which source
- What research was done and what was found
- Every email sent and when
- Whether they opened, clicked, or replied
- Every status change from first discovery to closed deal

Nothing is ever deleted. Archived leads can be reactivated. The system builds institutional memory that doesn't leave when a rep does.

---

## 12. Real-World Example — End to End

**Day 1 — 7:00 AM**
> Scout reads business news. Finds: *"Lakeside Cold Storage opens 3rd distribution center in Indiana."*
> Saves: company = Lakeside Cold Storage, industry = cold storage/logistics, city = Indianapolis, IN (deregulated state).

**Day 1 — 7:05 AM**
> Analyst enriches. 8-source waterfall runs.
> Contact found: Mark Rivera, Director of Operations, mark.rivera@lakesidecold.com, (317) 555-0241
> Score: 79/100 — High Tier
> Reason: *"3-location cold storage in Indiana. 24/7 refrigeration = very high utility intensity. Est. $380k annual spend. Strong savings candidate."*

**Day 1 — 9:00 AM**
> Alert email sent to sales team: "3 new high-tier leads ready for review."

**Day 1 — 10:30 AM**
> Consultant logs in. Reviews Lakeside Cold Storage — score 79, explanation solid. Clicks **Approve**. ← *HITL Checkpoint 1*

**Day 1 — 10:31 AM**
> Writer drafts email for Mark Rivera.
> Scout + service memory consulted. Indiana deregulation hook used. Healthcare case study swapped for cold storage angle.
> Subject: *"Cold storage operators in Indiana are overpaying — here's why"*
> Critic scores: 8.2/10. Saved to Email Review queue.

**Day 1 — 2:00 PM**
> Consultant reads the draft. Looks good. Clicks **Approve & Send**. ← *HITL Checkpoint 2*
> Email delivered to mark.rivera@lakesidecold.com at 2:01 PM. Open + click tracking enabled.
> Follow-ups scheduled: Day 4, Day 8, Day 15.

**Day 4**
> Follow-up 1 sent automatically. *"Just checking in..."*

**Day 8**
> Mark opens the Day 1 email. System records: `opened`.
> Mark clicks the call booking link. System records: `clicked`.

**Day 9**
> Mark replies: *"Yes — can we talk Thursday?"*
> System: cancels follow-ups 2 and 3. Status → `replied`. Alert sent to sales team.
> CRM: deal stage updated to "Replied" automatically via API.

**Thursday**
> Sales team takes the call. Marks status → `meeting_booked`.
> Learning table updated: cold storage + Indiana deregulation + `audit_offer` angle = win.
> Future Writer runs for cold storage companies will bias toward this angle.

---

## 13. How to Interact — No Technical Knowledge Required

The sales team has three ways to interact with the system:

**1. The Dashboard**
Visual pages for reviewing leads, reading email drafts, and watching the pipeline. Approve, reject, or edit with clicks — no forms, no data entry required.

**2. The Chatbot**
Type in plain English. The AI understands your intent and acts on it. Approve a lead, run the Scout for a new city, ask who replied — all in a conversation window.

**3. Trigger Buttons**
One-click buttons on the Triggers page to run Scout, Analyst, or Writer in the background. Progress updates appear live on screen.

---

## 14. What Happens to Each Company Over Time

| Status | What it means |
|---|---|
| **New** | Just discovered — not yet researched |
| **Enriched** | Contact found at the company |
| **Scored** | Research complete, score assigned — awaiting human review |
| **Approved** | Human approved — email will be written |
| **Draft Ready** | Email written — awaiting human review |
| **Contacted** | Email sent |
| **Replied** | They wrote back |
| **Meeting Booked** | Call or meeting scheduled |
| **Won** | Deal closed |
| **No Response** | All follow-ups sent, no reply received |
| **Archived** | Not a fit — removed from active pipeline (not deleted) |

---

## 15. How This System Can Be Extended

Because the system is agentic, new capabilities are added as new agents or new tools — not as modifications to what already works.

**Research Agent**
A dedicated deep-dive agent that runs before the Writer — reads the company's annual report, scans their website for facility details, checks recent news. Writer receives richer context, produces more credible emails.

**Newsletter / Content Draft Agent**
A Writer variant that produces a weekly newsletter or industry insight summary for a list of prospects — same personalization logic, different output format. Sales team approves before sending.

**LinkedIn Post Agent**
Drafts thought leadership posts or social content based on what the Scout is finding in the market. Sales team approves before publishing.

**Lookalike Scout Agent**
Takes your best closed deals and finds companies with similar profiles — same industry, size, state, growth pattern. A targeted Scout that learns from wins.

**Proposal Draft Agent**
After a meeting is booked, generates a first-draft proposal tailored to the company — their size, estimated spend, your pricing model. Sales team edits and sends.

**Competitive Intelligence Agent**
Monitors competitor press releases, pricing changes, and new service launches. Feeds context into Writer so outreach can be timed to competitive moments.

---

## 16. What This Is Configurable For

The agents are configured — not hardcoded. By changing configuration and adding tools, the same architecture runs:

| Configuration | What it does |
|---|---|
| **Personalized Scout** | Target specific geography, industry, revenue band, or growth stage |
| **Personalized Writer** | Your tone, your service positioning, your buyer personas |
| **Personalized Approval** | Route approvals to different people by tier, industry, or region |
| **Personalized Lister** | Texas reps see Texas leads; healthcare reps see healthcare leads |
| **Personalized Post Maker** | Draft LinkedIn posts, newsletters, or case studies from existing lead intelligence |
| **Custom Data Sources** | Plug in any API — a proprietary database, regulatory filings, tariff databases |
| **Custom Scoring** | Change the formula to weight what matters most for your business |

Every change is a configuration adjustment or a new tool — not a rebuild.

---

## 17. What This Does NOT Do

- Does not send any email without a human approving it first
- Does not contact anyone who has unsubscribed
- Does not exceed the configured daily send limit
- Does not make the final sale — that conversation happens person-to-person
- Does not replace your CRM — it feeds your CRM with richer, more current data
- Does not replace the sales team's judgment — it removes the research and writing burden so they can focus on conversations that matter

---

## 18. Technology and Tools

### Core Stack

- **FastAPI** — REST API backend; all agents run inside this process
- **React + Vite + Tailwind CSS** — dashboard UI served by nginx
- **PostgreSQL + SQLAlchemy** — all lead data, contacts, scores, emails, events
- **Docker** — two containers (API + frontend); deploys anywhere
- **LangChain** — agent framework; connects LLM reasoning to deterministic tools
- **Ollama / llama3.2** — default local LLM (runs on your machine, no API cost)
- **OpenAI GPT-4o-mini** — optional cloud LLM (one env var to switch)
- **LangSmith** — optional agent trace viewer (every Thought/Action/Observation logged)

### External APIs

- **Tavily** — news and web search for company discovery
- **Google Maps Places API** — local business search and phone lookup
- **Yelp Business API** — business listings and phone fallback
- **Apollo.io** — business contact database
- **Hunter.io** — email search by domain
- **Prospeo** — LinkedIn-based contact enrichment
- **Snov.io** — additional contact database
- **ZeroBounce** — email address verification
- **ScraperAPI** — proxy for web scraping
- **SendGrid** — email delivery with open + click tracking

### Why It Is Agentic

Traditional automation: fixed script, fixed steps, breaks on any deviation.

This platform: each agent uses the **ReAct (Reasoning + Acting)** pattern — it observes its situation, reasons about what to do, calls a tool, observes the result, and reasons about what to do next. The LLM handles judgment and reasoning; deterministic tools handle execution and math.

This is what makes the system:
- **Adaptive** — it tries a different source if the first one fails
- **Explainable** — every Thought, Action, and Observation is logged
- **Extensible** — add a new tool, the agent can use it without being retrained
- **Reliable** — guardrails and HITL checkpoints prevent the AI from acting beyond its lane

---

*Utility Lead Outreach Automation Platform*
*Internal documentation — updated March 2026*
