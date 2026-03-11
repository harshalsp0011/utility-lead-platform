CREATE TABLE IF NOT EXISTS company_features (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    estimated_sqft_per_site FLOAT,
    estimated_site_count INTEGER,
    estimated_annual_utility_spend FLOAT,
    estimated_annual_telecom_spend FLOAT,
    estimated_total_spend FLOAT,
    savings_low FLOAT,
    savings_mid FLOAT,
    savings_high FLOAT,
    industry_fit_score FLOAT,
    multi_site_confirmed BOOLEAN DEFAULT false,
    deregulated_state BOOLEAN DEFAULT false,
    data_quality_score FLOAT,
    computed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_features_company_id
    ON company_features (company_id);