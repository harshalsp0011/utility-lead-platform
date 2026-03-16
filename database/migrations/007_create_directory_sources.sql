-- Creates directory_sources to persist reusable Scout source URLs from JSON and Tavily.
-- Dependencies: PostgreSQL with pgcrypto extension for gen_random_uuid().
-- Usage: executed automatically by database.connection.run_migrations().

CREATE TABLE IF NOT EXISTS directory_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    url VARCHAR(1000) NOT NULL UNIQUE,
    category VARCHAR(100),
    location VARCHAR(255),
    pagination BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    discovered_via VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_directory_sources_active
    ON directory_sources (active);

CREATE INDEX IF NOT EXISTS idx_directory_sources_category_location
    ON directory_sources (category, location);
