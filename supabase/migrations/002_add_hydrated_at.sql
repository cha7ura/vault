-- Add hydrated_at column to guests table
-- This tracks when a guest profile was enriched with web search data

ALTER TABLE guests ADD COLUMN IF NOT EXISTS hydrated_at TIMESTAMP;

-- Create index for finding un-hydrated guests
CREATE INDEX IF NOT EXISTS idx_guests_hydrated ON guests(hydrated_at);
