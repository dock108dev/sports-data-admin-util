-- Migration: Add sports_game_plays table for play-by-play events
-- Run with: psql "$DATABASE_URL" -f sql/004_game_play_by_play.sql

CREATE TABLE IF NOT EXISTS sports_game_plays (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES sports_games(id) ON DELETE CASCADE,
    quarter INTEGER,
    game_clock VARCHAR(10),
    play_index INTEGER NOT NULL,
    play_type VARCHAR(50),
    team_id INTEGER REFERENCES sports_teams(id),
    player_id VARCHAR(100),
    player_name VARCHAR(200),
    description TEXT,
    home_score INTEGER,
    away_score INTEGER,
    raw_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- Ensure uniqueness per game ordering
CREATE UNIQUE INDEX IF NOT EXISTS uq_game_play_index ON sports_game_plays(game_id, play_index);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_game_plays_game ON sports_game_plays(game_id);
CREATE INDEX IF NOT EXISTS idx_game_plays_player ON sports_game_plays(player_id);
CREATE INDEX IF NOT EXISTS idx_game_plays_type ON sports_game_plays(play_type);

-- Verify the table was created
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'sports_game_plays') THEN
        RAISE NOTICE 'sports_game_plays table created successfully';
    ELSE
        RAISE EXCEPTION 'Failed to create sports_game_plays table';
    END IF;
END $$;



