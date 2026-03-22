-- Migration 014: Add intent_signal column to companies table
-- Stores the buying signal found for this company via news/press release scouting.
-- Examples: "expansion: opening new facility in Greece NY"
--           "cost pressure: district cited rising utility bills in budget meeting"
--           "renovation: hotel chain renovating 4 Upstate NY properties"
-- NULL means company was found via regular directory/maps search (no news signal).

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS intent_signal TEXT;
