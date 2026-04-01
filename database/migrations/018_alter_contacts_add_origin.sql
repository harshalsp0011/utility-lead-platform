-- Migration 018: Add data_origin and last_synced_at to contacts table
--
-- data_origin: high-level tag indicating where this contact record came from.
--   'scout'        — found during enrichment waterfall (Hunter, Apollo, Snov, Prospeo, Serper, etc.)
--   'hubspot_crm'  — pulled from HubSpot CRM (batch sync or webhook)
--   'manual'       — added manually by a user
--   NULL           — legacy records created before this column existed (treat as 'scout')
--
-- last_synced_at: timestamp of the last time this record was synced with HubSpot.
--   NULL means never synced with any external system.

ALTER TABLE contacts
  ADD COLUMN IF NOT EXISTS data_origin    VARCHAR(50),
  ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP;
