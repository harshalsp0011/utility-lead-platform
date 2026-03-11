CREATE TABLE IF NOT EXISTS contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    full_name VARCHAR(200),
    title VARCHAR(200),
    email VARCHAR(200),
    linkedin_url VARCHAR(500),
    source VARCHAR(100),
    verified BOOLEAN DEFAULT false,
    unsubscribed BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contacts_company_id
    ON contacts (company_id);

CREATE INDEX IF NOT EXISTS idx_contacts_email
    ON contacts (email);