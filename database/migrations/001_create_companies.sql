-- Creates the main companies table used by the app.
-- Other tables connect back to this table through company_id.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    website VARCHAR(500),
    industry VARCHAR(100),
    sub_industry VARCHAR(100),
    city VARCHAR(100),
    state VARCHAR(50),
    employee_count INTEGER,
    site_count INTEGER,
    source VARCHAR(200),
    source_url VARCHAR(500),
    date_found TIMESTAMP DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'new',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_companies_industry ON companies (industry);
CREATE INDEX IF NOT EXISTS idx_companies_state ON companies (state);
CREATE INDEX IF NOT EXISTS idx_companies_status ON companies (status);