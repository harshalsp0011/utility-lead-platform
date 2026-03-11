CREATE TABLE IF NOT EXISTS email_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    contact_id UUID REFERENCES contacts(id),
    subject_line VARCHAR(300),
    body TEXT,
    savings_estimate VARCHAR(100),
    template_used VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    approved_human BOOLEAN DEFAULT false,
    approved_by VARCHAR(100),
    approved_at TIMESTAMP,
    edited_human BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_email_drafts_company_id
    ON email_drafts (company_id);

CREATE INDEX IF NOT EXISTS idx_email_drafts_approved_human
    ON email_drafts (approved_human);