-- Migration: Add x_handle column to sports_teams for X/Twitter integration
-- Run with: psql "$DATABASE_URL" -f sql/002_team_x_handles.sql

-- Add the column
ALTER TABLE sports_teams 
ADD COLUMN IF NOT EXISTS x_handle VARCHAR(50);

-- Create index for efficient lookups
CREATE INDEX IF NOT EXISTS idx_sports_teams_x_handle ON sports_teams(x_handle) 
WHERE x_handle IS NOT NULL;

-- Verify the column was added
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'sports_teams' AND column_name = 'x_handle'
    ) THEN
        RAISE NOTICE 'x_handle column added successfully to sports_teams';
    ELSE
        RAISE EXCEPTION 'Failed to add x_handle column';
    END IF;
END $$;

