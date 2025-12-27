-- Migration: Add game_social_posts table for X/Twitter timeline integration
-- Run with: psql "$DATABASE_URL" -f sql/001_game_social_posts.sql

-- Create the table
CREATE TABLE IF NOT EXISTS game_social_posts (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES sports_games(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES sports_teams(id) ON DELETE CASCADE,
    tweet_url TEXT NOT NULL,
    posted_at TIMESTAMPTZ NOT NULL,
    has_video BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_social_posts_game ON game_social_posts(game_id);
CREATE INDEX IF NOT EXISTS idx_social_posts_team ON game_social_posts(team_id);
CREATE INDEX IF NOT EXISTS idx_social_posts_posted_at ON game_social_posts(posted_at);

-- Unique constraint to prevent duplicate tweet URLs
CREATE UNIQUE INDEX IF NOT EXISTS uq_social_posts_url ON game_social_posts(tweet_url);

-- Verify the table was created
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'game_social_posts') THEN
        RAISE NOTICE 'game_social_posts table created successfully';
    ELSE
        RAISE EXCEPTION 'Failed to create game_social_posts table';
    END IF;
END $$;

