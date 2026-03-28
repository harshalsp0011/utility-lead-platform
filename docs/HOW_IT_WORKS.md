# How the Utility Lead Platform Works
### A Plain-English Guide for Business Stakeholders

> **What this is:** An AI-powered Multi-Agent Lead Intelligence Platform for utility cost-reduction consulting. Specialized agents (Scout, Analyst, Writer) discover high-spend companies, research and score them, and draft personalized outreach — with human approval before anything is sent.

---

## What Problem Does This Solve?

Finding companies that overpay on utilities, researching them, finding the right contact, writing a personalized email, following up multiple times, and tracking whether they responded — all of this takes hours per lead when done manually.

This platform does all of that automatically. A consultant's job shrinks down to two simple decisions:

1. **"Is this company worth reaching out to?"** — approve or skip
2. **"Is this email good enough to send?"** — approve or edit

Everything else — finding the company, researching it, building the contact profile, writing the email, following up, tracking replies — happens on its own.

---

## This Is Not a CRM Replacement

**This platform is not a replacement for your CRM. It is an advanced plugin that sits in front of your CRM and makes it smarter.**

A traditional CRM (HubSpot, Salesforce, Pipedrive — any of them) is a record-keeping system. It stores what you manually put in it. Someone has to find the lead, research them, write the email, and log everything by hand. The CRM is a filing cabinet.

This platform is the intelligence layer that does all that work automatically, then hands the result to your CRM. It connects to any CRM that supports an API or webhooks — which includes every major CRM in use today.

```
[This Platform]                    [Your CRM — any CRM with API/webhooks]
─────────────────────────────      ──────────────────────────────────────
Finds leads from news              Stores the contact record
Researches and scores them         Shows the sales team their pipeline
Writes the outreach email          Receives replies and meeting bookings
Sends and follows up               Tracks deal stage and history
Updates status automatically  →→→  Syncs deal status from platform
```

**How the integration works:**
- **Push (Platform → CRM):** After an email is sent, the platform creates or updates the contact and deal record in your CRM via the CRM's REST API. As status changes (replied, meeting booked, won), the deal stage updates automatically.
- **Pull (CRM → Platform):** When a prospect replies or books a meeting, your CRM fires a webhook to the platform. The platform receives it, cancels follow-ups, updates the pipeline status, and alerts the sales team.

*Example with HubSpot:* after send → `POST https://api.hubspot.com/crm/v3/objects/deals` creates the deal. When a reply lands in HubSpot → HubSpot fires `POST /api/webhooks/hubspot/reply` to the platform. The same pattern works with Salesforce, Pipedrive, Zoho, or any CRM that supports outgoing webhooks.

Think of it this way: your CRM is the front desk. This platform is the research team, the copywriter, and the outreach coordinator working behind it — fully automated, reporting back to the front desk in real time.

---

## How the System Finds Companies

The Scout agent doesn't wait for leads to come to you. It actively searches for companies that show signals of high utility spend.

### What signals it looks for

The Scout reads business news and looks for events that correlate with large, ongoing utility costs:

- **New facility opening** — a company moving into a large building has a utility contract to negotiate
- **Production expansion** — scaling up manufacturing means more energy consumption
- **Multi-location growth** — chains and franchises across multiple sites have large aggregate spend
- **Healthcare construction** — hospitals and clinics are among the highest utility consumers per square foot
- **Logistics and cold storage** — warehouses and refrigerated facilities run 24/7
- **Data center announcements** — among the most energy-intensive facilities in existence

### Where it searches

The Scout pulls from multiple sources in parallel:

| Source | What it finds |
|---|---|
| **Tavily news search** | Business news, press releases, announcements — "XYZ Corp opens 200,000 sq ft distribution center in Ohio" |
| **Google Maps / Places** | Local businesses in a given city or region, filtered by industry |
| **Yelp Business Search** | Business listings with location and category data |
| **Directory scraper** | Configured business directories (Yellow Pages, local industry directories) |

### What it extracts

For each company found, the Scout extracts:
- Company name, city, state, industry
- Website URL
- Why it appeared — the specific news signal or search result that surfaced it
- Estimated size signals (employee count, number of locations if visible)

All of this is saved automatically. Nothing needs to be done manually to trigger a daily scan.

### Example — what the Scout finds

> Tavily returns: *"Midwest Surgical Associates breaks ground on new 85,000 sq ft medical campus in Columbus, OH"*
>
> Scout extracts: company = Midwest Surgical Associates, industry = healthcare, city = Columbus, state = OH, signal = new facility construction
>
> → Saved to the system as a new lead for research

---

## How the System Researches a Company

Once a company is in the system, the Analyst agent goes to work. This is a multi-step research process — not a single lookup.

### Step 1 — Find the right contact

The Analyst runs through an 8-source waterfall to find the best decision-maker contact at the company:

```
1. Hunter.io          — email search by company domain
2. Apollo             — business contact database
3. Website scraper    — scrapes company's own site for contact info
4. Serper / Google    — "VP Operations Midwest Surgical Associates" search
5. Snov.io            — additional contact database
6. Prospeo            — LinkedIn-based contact enrichment
7. ZeroBounce         — verifies email addresses are deliverable
8. Permutation guess  — constructs likely email formats (first.last@domain.com)
```

The goal is to find: **full name, job title, verified email address, and phone number** for the most relevant decision-maker — typically a VP of Operations, Facilities Manager, Director of Finance, or CFO.

### Step 2 — Assess the company's fit

The Analyst looks at multiple data points to estimate how good a prospect this company is:

- **Employee count** — larger organizations have higher utility spend
- **Number of locations** — multi-site companies have aggregate spend across all sites
- **Industry** — healthcare, manufacturing, cold storage, logistics score higher than retail or services
- **State** — companies in deregulated energy states (Texas, Ohio, Illinois, Pennsylvania, etc.) can switch suppliers, which is the core service offering
- **Estimated utility spend** — calculated from employee count + industry benchmarks

### Step 3 — Score 0 to 100

A score is computed from the research:

```
Score = (Estimated savings potential × 40%)
      + (Industry fit × 25%)
      + (Multi-site factor × 20%)
      + (Data quality / completeness × 15%)
```

The AI then writes a plain-English explanation of the score — not just a number:

> *"250-employee healthcare company with 3 sites across Ohio — a deregulated state. Estimated $180k annual utility spend with ~$40k savings potential from supplier switching. Strong audit candidate."*

This explanation is shown on the Leads page so the consultant understands exactly why a company scored the way it did.

### Example — research output

> Company: Midwest Surgical Associates
> Contact found: David Chen, VP of Facilities, david.chen@midwestsurgical.com, (614) 555-0182
> Score: 84 / 100 — High Tier
> Reason: "3-site healthcare operator in Ohio (deregulated). Estimated $210k annual utility spend. High savings potential from supply-side audit. Contact verified."

---

## The Chatbot — Control Everything in Plain English

The platform includes a conversational chatbot interface. **Sales team members do not need to navigate dashboards, click buttons, or understand the technical pipeline.** They can simply type what they want.

### What the chatbot can do

| What you type | What happens |
|---|---|
| `"Find healthcare companies in Columbus Ohio"` | Scout runs, results appear in the chat |
| `"Show me all high-tier leads we haven't contacted yet"` | Filtered lead list appears |
| `"Approve the top 5 leads"` | Those leads are approved and move to the writing queue |
| `"Run the analyst on new companies"` | Analyst starts enrichment and scoring |
| `"Write emails for all approved leads"` | Writer agent drafts emails for all ready leads |
| `"Show me emails waiting for my review"` | Draft queue appears with approve/reject buttons |
| `"Approve the email for Midwest Surgical"` | That email is approved and sent |
| `"Who replied to our emails this week?"` | Reply list appears with company and contact details |
| `"Run the full pipeline for manufacturing companies in Chicago"` | Scout → Analyst → Writer chain runs automatically |

### How it understands you

The chatbot uses an AI language model to understand your intent — it does not match keywords to fixed commands. It reasons about what you mean and decides what action to take:

```
You type: "how many healthcare leads do we have that are ready to go?"

Chatbot reasons:
  "healthcare" → filter by industry = healthcare
  "ready to go" → status = approved (email written, waiting for review)
  "how many" → count query

Returns: "You have 7 healthcare leads with emails ready for your review."
```

No training required. No commands to memorize. Just describe what you need.

### Manual lead entry via chatbot

If you meet someone at a conference, receive a referral, or have a company in mind that the Scout hasn't found yet, you can add them directly through the chatbot:

> *"Add ABC Manufacturing in Detroit, contact is Sarah Johnson, VP Operations, sarah.johnson@abcmfg.com"*

The system creates the company and contact record immediately and sends it through the same research and scoring pipeline as any other lead. Nothing is treated differently based on how it entered the system.

---

## Every Lead Is Stored — Forever

The system stores every company it encounters — regardless of whether they become a customer, reply, or never respond.

This is deliberate. A company that didn't reply today might be the right prospect in six months when their contract comes up for renewal. A lead that was scored too low this quarter might be worth revisiting after they expand.

The full history of every company is preserved:
- When it was discovered and why
- What research was done and what was found
- Every email sent and when
- Whether they opened, clicked, or replied
- Every status change from first discovery to closed deal

Nothing is ever deleted. Archived leads can be reactivated. The system builds institutional memory over time.

---

## The Writer Agent Knows Your Business

The Writer agent is not a generic AI email writer. It can be configured with your company's specific knowledge — your services, your pricing approach, your case studies, your differentiators — so every email it writes is grounded in what you actually offer.

### What you can embed as "memory"

- **Your service offering** — e.g., "We audit energy contracts across natural gas and electricity, typically finding 8–24% savings in the first year"
- **Industry-specific talking points** — different angles for hospitals vs. manufacturers vs. logistics companies
- **Past success stories** — "We saved a 12-location restaurant chain $340k over two years"
- **Your pricing model** — contingency-based, no upfront cost, etc.
- **Your sender's background** — "John is a former utility pricing analyst with 15 years of experience"

When the Writer drafts an email for a healthcare company, it can automatically pull the healthcare-specific talking points and a relevant case study. When it drafts for a manufacturer, it uses the manufacturing angle. The email sounds like it was written by someone who knows both the prospect and your business deeply.

### The Critic loop

After every draft, a second AI (the Critic) reviews the email on five criteria:
1. Is it personalized to this specific company?
2. Does it include a specific savings figure?
3. Does it make one clear ask?
4. Does it sound like a human wrote it?
5. Is the subject line specific enough to get opened?

If the email scores below the threshold, the Writer rewrites it with the Critic's specific feedback. This loop runs up to twice before the email is sent to the human review queue.

### The system learns what works

Every email angle is tracked. When a reply comes in, the system records which angle was used, which industry it was for, and that it worked. Over time, the Writer reads this history and naturally shifts toward angles that get responses — without anyone manually telling it to.

---

## Real-World Example — End to End

Here is a complete example of one lead moving through the system:

**Day 1 — 7:00 AM**
> Scout reads business news. Finds: "Lakeside Cold Storage opens 3rd distribution center in Indiana."
> Saves: company = Lakeside Cold Storage, industry = logistics/cold storage, city = Indianapolis, IN (deregulated state).

**Day 1 — 7:05 AM**
> Analyst enriches the company.
> Finds: Mark Rivera, Director of Operations, mark.rivera@lakesidecold.com, (317) 555-0241
> Scores: 79/100 — High Tier
> Reason: "3-location cold storage operator in Indiana. 24/7 refrigeration = very high utility intensity. Estimated $380k annual utility spend. Strong savings candidate."

**Day 1 — 9:00 AM**
> Notification email sent to sales team: "3 new high-tier leads ready for review."

**Day 1 — 10:30 AM**
> Consultant logs into dashboard. Reviews Lakeside Cold Storage — score 79, explanation looks solid. Clicks Approve.

**Day 1 — 10:31 AM**
> Writer drafts email for Mark Rivera:
> Subject: "Cold storage operators in Indiana are overpaying — here's why"
> Body: personalized to Lakeside's 3-location footprint, mentions Indiana deregulation, quotes estimated $60–90k annual savings, asks for a 15-minute call.
> Critic scores it 8/10. Saved to review queue.

**Day 1 — 2:00 PM**
> Consultant reviews the draft. Looks good. Clicks Send.
> Email delivered to mark.rivera@lakesidecold.com at 2:01 PM.
> Open tracking and click tracking enabled.

**Day 4**
> Automated follow-up 1 sent. "Just checking in — wanted to make sure my note reached you..."

**Day 8**
> Mark Rivera opens the email. System records: opened.
> Mark clicks the "book a call" link. System records: clicked.

**Day 9**
> Mark replies: "Hi, yes we've been thinking about this. Can we talk Thursday?"
> System: cancels follow-up 2 and 3. Marks status = "Replied". Sends alert to sales team.

**Thursday**
> Sales team takes the call. Marks status = "Meeting Booked."
> System records win. That email angle (cold storage + Indiana deregulation + savings estimate) gets credited in the learning table.

---

## How to Interact — No Technical Knowledge Required

The sales team has three ways to interact with the system:

**1. The Dashboard**
Visual pages for reviewing leads, reading email drafts, and watching the pipeline. Approve, reject, or edit with clicks — no forms, no data entry.

**2. The Chatbot**
Type in plain English. The AI understands your intent and acts on it. Approve a lead, run the Scout for a new city, ask who replied — all in conversation.

**3. Trigger Buttons**
One-click buttons on the Triggers page to run Scout, run Analyst, or run Writer in the background while you do something else. Progress updates appear live on screen.

---

## What Happens to Each Company Over Time

| Status | What it means |
|---|---|
| **New** | Just discovered — not yet researched |
| **Enriched** | Right contact found at the company |
| **Scored** | Research complete, score assigned |
| **Approved** | Human said "yes, reach out" |
| **Draft Ready** | Email written and waiting for your review |
| **Contacted** | Email sent |
| **Replied** | They wrote back |
| **Meeting Booked** | They scheduled a call |
| **Won** | Deal closed |
| **No Response** | All follow-ups sent, no reply |
| **Archived** | Not a good fit — removed from active pipeline (but not deleted) |

---

## How This System Can Be Extended

This platform is built on an agentic architecture — meaning it can be extended by adding new agents and tools without redesigning what already works. Every agent is independent and plugs into the same pipeline.

### Extensions already possible today

**Research Agent**
Add a dedicated agent that deep-dives into a company before the email is written — reads their annual report, scans their website for facility details, checks recent news for context. The Writer agent receives richer input and produces a more specific, more credible email.

**Newsletter / Content Draft Agent**
A specialized Writer variant that, instead of one outreach email, produces a weekly newsletter or industry insight summary for a list of prospects. The same personalization logic applies — different angle, different output format. The sales team reviews and approves before sending, exactly as with outreach emails.

**LinkedIn Post / Content Agent**
An agent that drafts social posts or thought leadership content based on what the Scout is finding in the market — "here's a trend we're seeing across healthcare facilities this quarter." The sales team approves before publishing.

**Lookalike Scout Agent**
An agent that takes your best closed deals and finds companies with similar profiles — same industry, same size, same state, same growth pattern. A smarter, targeted Scout that learns from your wins.

**Competitive Intelligence Agent**
An agent that monitors what competitors are doing — press releases, pricing changes, new service launches — and feeds that context into the Writer so emails can be timed to competitive moments.

**Proposal Draft Agent**
After a meeting is booked, an agent that generates a first-draft proposal document tailored to the specific company — their size, their estimated spend, your pricing model. The sales team edits and sends.

### How extensions are added

Because the system is agentic, adding a new capability means:
1. Write the new agent with a clear system prompt defining its job
2. Add the tools it needs (a new API, a new data source, a web scraper, a document generator)
3. Connect it to the pipeline at the right stage

No redesign of existing agents. No changes to the database structure in most cases. The new agent slots in and the rest of the system works as before.

---

## What This Is Configurable For

This system is not built for one specific use case. The agents are configured — not hardcoded. By changing the configuration and adding tools, the same architecture can run:

| Configuration | What it does |
|---|---|
| **Personalized Scout** | Search for companies in a specific geography, industry, revenue band, or growth stage that you define |
| **Personalized Writer** | Write emails in your specific tone, with your specific service positioning, for your specific buyer personas |
| **Personalized Approval** | Route approvals to specific people based on lead tier, industry, or geography |
| **Personalized Lister** | Build filtered views of leads for different team members — a rep in Texas sees Texas leads, healthcare reps see healthcare leads |
| **Personalized Post Maker** | Draft LinkedIn posts, newsletters, or case study summaries from the same lead intelligence the platform already has |
| **Custom Data Sources** | Add any API or data source to the enrichment waterfall — a proprietary database, a regulatory filing source, a utility tariff database |
| **Custom Scoring Logic** | Change the scoring formula to weight what matters most for your business — contract size, geography, or industry mix |

Every one of these changes is a configuration or a new tool added to an existing agent — not a rebuild.

---

## What This Does NOT Do

- It does not send any email without a human approving it first
- It does not contact anyone who has unsubscribed
- It does not exceed the daily send limit
- It does not make the final sale — that conversation still happens person-to-person
- It does not replace your CRM — it feeds your CRM with better, richer data
- It does not replace the sales team's judgment — it removes the time-consuming research and writing work so they can focus on conversations that matter

---

## Technology and Tools (Technical Summary)

For those who want to know what is running under the hood:

### Core Tech Stack

- **FastAPI** — REST API backend, handles all requests from the dashboard and chatbot
- **React + Vite + Tailwind CSS** — dashboard frontend served via nginx
- **PostgreSQL** — all lead data, contacts, emails, scores, and pipeline status stored here
- **SQLAlchemy** — database ORM (Python)
- **Docker** — the entire platform runs in two containers (API + frontend), deployable anywhere
- **LangChain** — agent framework that connects the LLM to tools (APIs, database queries, scoring functions)
- **Ollama / llama3.2** — default local LLM for all reasoning (runs on your machine, no API cost)
- **OpenAI GPT-4o-mini** — optional cloud LLM (set one environment variable to switch)

### External APIs Used

- **Tavily** — AI-powered news and web search for company discovery
- **Google Maps Places API** — local business search and phone number lookup
- **Yelp Business API** — business listings and phone fallback
- **Apollo.io** — business contact database for enrichment
- **Hunter.io** — email address search by company domain
- **Prospeo** — LinkedIn-based contact enrichment
- **Snov.io** — additional contact database
- **ZeroBounce** — email address verification
- **ScraperAPI** — proxy for web scraping
- **SendGrid** — email delivery with open and click tracking
- **LangSmith** — optional agent tracing and observability

### Why It Is Agentic

A traditional automation system follows a fixed script: step 1, step 2, step 3. If step 2 fails, the system stops.

This platform uses agents — AI-powered processes that **reason about what to do next** rather than following a fixed script:

- The **Scout agent** doesn't run one fixed query. It generates multiple search variations, evaluates what came back, and decides whether to try more queries or accept the results.
- The **Analyst agent** doesn't just run a scoring formula. It looks at what data is available, notices when something is missing, decides whether to try another enrichment source, and explains its reasoning in plain English.
- The **Writer agent** doesn't fill in a template. It reads the company's profile, chooses the most relevant angle from past email performance, writes a genuinely personalized email, and then a second agent critiques it and requests specific improvements.
- The **Chatbot** doesn't match keywords to commands. It reasons about what you mean and decides which agents to call, in what order, with what parameters.

Each agent has a defined job, a set of tools it can call, and the reasoning capability to decide how to use those tools given the situation it finds. That is what makes this system adaptable, extensible, and able to handle situations that a fixed script would fail on.

---

*Utility Lead Outreach Automation Platform*
*Internal documentation — updated March 2026*
