-- Creates the lead_scores table for AI or analyst scoring results.
-- It connects each score back to a company record.

CREATE TABLE IF NOT EXISTS lead_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    score FLOAT,
    tier VARCHAR(20),
    score_reason TEXT,
    approved_human BOOLEAN DEFAULT false,
    approved_by VARCHAR(100),
    approved_at TIMESTAMP,
    scored_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lead_scores_company_id
    ON lead_scores (company_id);

CREATE INDEX IF NOT EXISTS idx_lead_scores_tier
    ON lead_scores (tier);

CREATE INDEX IF NOT EXISTS idx_lead_scores_score
    ON lead_scores (score);