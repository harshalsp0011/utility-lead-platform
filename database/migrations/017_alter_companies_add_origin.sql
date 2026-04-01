-- Migration 017: Add data_origin and last_synced_at to companies table
--
-- data_origin: high-level tag indicating where this company record came from.
--   'scout'        — discovered by our Scout agent (Google Maps, Yelp, Tavily, directory scrape)
--   'hubspot_crm'  — pulled from HubSpot CRM (batch sync or webhook)
--   'manual'       — added manually by a user
--   NULL           — legacy records created before this column existed (treat as 'scout')
--
-- last_synced_at: timestamp of the last time this record was synced with an external system.
--   For scout records: set to created_at (no external sync).
--   For hubspot_crm records: updated every time we pull from or push to HubSpot.
--   NULL means never synced with any external system.

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS data_origin    VARCHAR(50),
  ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP;
