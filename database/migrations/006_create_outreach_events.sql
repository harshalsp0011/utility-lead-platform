-- Creates outreach event history such as sends, replies, and follow-ups.
-- This table links outreach activity back to companies, contacts, and drafts.

CREATE TABLE IF NOT EXISTS outreach_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    contact_id UUID REFERENCES contacts(id),
    email_draft_id UUID REFERENCES email_drafts(id),
    event_type VARCHAR(50),
    event_at TIMESTAMP DEFAULT NOW(),
    reply_content TEXT,
    reply_sentiment VARCHAR(20),
    follow_up_number INTEGER DEFAULT 0,
    next_followup_date DATE,
    sales_alerted BOOLEAN DEFAULT false,
    alerted_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outreach_events_company_id
    ON outreach_events (company_id);

CREATE INDEX IF NOT EXISTS idx_outreach_events_event_type
    ON outreach_events (event_type);

CREATE INDEX IF NOT EXISTS idx_outreach_events_next_followup_date
    ON outreach_events (next_followup_date);