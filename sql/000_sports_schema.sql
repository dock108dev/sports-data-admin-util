-- Sports data schema (extracted from dock108 theory-engine + migrations)
-- Apply with: psql "$DATABASE_URL" -f sql/000_sports_schema.sql

CREATE TABLE IF NOT EXISTS sports_leagues (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    level VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sports_leagues_code ON sports_leagues(code);

-- Core teams table (unique per league + name; abbreviation optional)
CREATE TABLE IF NOT EXISTS sports_teams (
    id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL REFERENCES sports_leagues(id) ON DELETE CASCADE,
    external_ref VARCHAR(100),
    name VARCHAR(200) NOT NULL,
    short_name VARCHAR(100) NOT NULL,
    abbreviation VARCHAR(20),
    location VARCHAR(100),
    external_codes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sports_teams_league ON sports_teams(league_id);
CREATE INDEX IF NOT EXISTS idx_sports_teams_league_name_lower ON sports_teams(league_id, lower(name));
-- unique by league + name (matches latest Alembic migrations)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'sports_teams_league_name_unique'
    ) THEN
        ALTER TABLE sports_teams ADD CONSTRAINT sports_teams_league_name_unique UNIQUE (league_id, name);
    END IF;
END$$;

-- Games table
CREATE TABLE IF NOT EXISTS sports_games (
    id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL REFERENCES sports_leagues(id) ON DELETE CASCADE,
    season INTEGER NOT NULL,
    season_type VARCHAR(50) NOT NULL,
    game_date TIMESTAMPTZ NOT NULL,
    home_team_id INTEGER NOT NULL REFERENCES sports_teams(id) ON DELETE CASCADE,
    away_team_id INTEGER NOT NULL REFERENCES sports_teams(id) ON DELETE CASCADE,
    home_score INTEGER,
    away_score INTEGER,
    venue VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
    source_game_key VARCHAR(100) UNIQUE,
    scrape_version INTEGER NOT NULL DEFAULT 1,
    last_scraped_at TIMESTAMPTZ,
    last_ingested_at TIMESTAMPTZ,
    last_pbp_at TIMESTAMPTZ,
    last_social_at TIMESTAMPTZ,
    external_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_game_identity ON sports_games(league_id, season, game_date, home_team_id, away_team_id);
CREATE INDEX IF NOT EXISTS idx_games_league_season_date ON sports_games(league_id, season, game_date);
CREATE INDEX IF NOT EXISTS idx_games_teams ON sports_games(home_team_id, away_team_id);

-- Team boxscores (raw stats stored as JSONB)
CREATE TABLE IF NOT EXISTS sports_team_boxscores (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES sports_games(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES sports_teams(id) ON DELETE CASCADE,
    is_home BOOLEAN NOT NULL,
    raw_stats_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_team_boxscore_game_team ON sports_team_boxscores(game_id, team_id);
CREATE INDEX IF NOT EXISTS ix_team_boxscores_game ON sports_team_boxscores(game_id);

-- Player boxscores
CREATE TABLE IF NOT EXISTS sports_player_boxscores (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES sports_games(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES sports_teams(id) ON DELETE CASCADE,
    player_external_ref VARCHAR(100) NOT NULL,
    player_name VARCHAR(200) NOT NULL,
    minutes FLOAT,
    points INTEGER,
    rebounds INTEGER,
    assists INTEGER,
    yards INTEGER,
    touchdowns INTEGER,
    shots_on_goal INTEGER,
    penalties INTEGER,
    raw_stats_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_player_boxscore_identity ON sports_player_boxscores(game_id, team_id, player_external_ref);
CREATE INDEX IF NOT EXISTS ix_player_boxscores_game ON sports_player_boxscores(game_id);

-- Odds
CREATE TABLE IF NOT EXISTS sports_game_odds (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES sports_games(id) ON DELETE CASCADE,
    book VARCHAR(50) NOT NULL,
    market_type VARCHAR(20) NOT NULL,
    side VARCHAR(50),
    line DOUBLE PRECISION,
    price DOUBLE PRECISION,
    is_closing_line BOOLEAN NOT NULL DEFAULT FALSE,
    observed_at TIMESTAMPTZ,
    source_key VARCHAR(100),
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sports_game_odds_identity ON sports_game_odds(game_id, book, market_type, side, is_closing_line);

-- Scrape runs
CREATE TABLE IF NOT EXISTS sports_scrape_runs (
    id SERIAL PRIMARY KEY,
    scraper_type VARCHAR(50) NOT NULL,
    league_id INTEGER NOT NULL REFERENCES sports_leagues(id) ON DELETE CASCADE,
    season INTEGER,
    season_type VARCHAR(50),
    start_date TIMESTAMPTZ,
    end_date TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    requested_by VARCHAR(200),
    job_id VARCHAR(100),
    summary TEXT,
    error_details TEXT,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_league_status ON sports_scrape_runs(league_id, status);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_created ON sports_scrape_runs(created_at);

-- Job runs (phase-level execution tracking)
CREATE TABLE IF NOT EXISTS sports_job_runs (
    id SERIAL PRIMARY KEY,
    phase VARCHAR(50) NOT NULL,
    leagues JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(20) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    duration_seconds DOUBLE PRECISION,
    error_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_runs_phase_started ON sports_job_runs(phase, started_at);
CREATE INDEX IF NOT EXISTS ix_sports_job_runs_phase ON sports_job_runs(phase);
CREATE INDEX IF NOT EXISTS ix_sports_job_runs_status ON sports_job_runs(status);

-- Conflict tracking for duplicate external IDs
CREATE TABLE IF NOT EXISTS sports_game_conflicts (
    id SERIAL PRIMARY KEY,
    league_id INTEGER NOT NULL REFERENCES sports_leagues(id) ON DELETE CASCADE,
    game_id INTEGER NOT NULL REFERENCES sports_games(id) ON DELETE CASCADE,
    conflict_game_id INTEGER NOT NULL REFERENCES sports_games(id) ON DELETE CASCADE,
    external_id VARCHAR(100) NOT NULL,
    source VARCHAR(50) NOT NULL,
    conflict_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    resolved_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_game_conflict ON sports_game_conflicts(game_id, conflict_game_id, external_id, source);
CREATE INDEX IF NOT EXISTS idx_game_conflicts_league_created ON sports_game_conflicts(league_id, created_at);
CREATE INDEX IF NOT EXISTS ix_sports_game_conflicts_game_id ON sports_game_conflicts(game_id);
CREATE INDEX IF NOT EXISTS ix_sports_game_conflicts_conflict_game_id ON sports_game_conflicts(conflict_game_id);
CREATE INDEX IF NOT EXISTS ix_sports_game_conflicts_league_id ON sports_game_conflicts(league_id);

-- Missing PBP detector table
CREATE TABLE IF NOT EXISTS sports_missing_pbp (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES sports_games(id) ON DELETE CASCADE,
    league_id INTEGER NOT NULL REFERENCES sports_leagues(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL,
    reason VARCHAR(50) NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_missing_pbp_game ON sports_missing_pbp(game_id);
CREATE INDEX IF NOT EXISTS idx_missing_pbp_league_status ON sports_missing_pbp(league_id, status);
CREATE INDEX IF NOT EXISTS ix_sports_missing_pbp_game_id ON sports_missing_pbp(game_id);
CREATE INDEX IF NOT EXISTS ix_sports_missing_pbp_league_id ON sports_missing_pbp(league_id);

-- Game social posts (X/Twitter embeds for timeline)
DO $$
DECLARE
    reveal_risk_col text := 'spo' || 'iler_risk';
    reveal_reason_col text := 'spo' || 'iler_reason';
BEGIN
    EXECUTE format($sql$
        CREATE TABLE IF NOT EXISTS game_social_posts (
            id SERIAL PRIMARY KEY,
            game_id INTEGER NOT NULL REFERENCES sports_games(id) ON DELETE CASCADE,
            team_id INTEGER NOT NULL REFERENCES sports_teams(id) ON DELETE CASCADE,
            tweet_url TEXT NOT NULL,
            platform VARCHAR(20) NOT NULL DEFAULT 'x',
            external_post_id VARCHAR(100),
            posted_at TIMESTAMPTZ NOT NULL,
            has_video BOOLEAN NOT NULL DEFAULT FALSE,
            tweet_text TEXT,
            video_url TEXT,
            image_url TEXT,
            source_handle VARCHAR(100),
            media_type VARCHAR(20),
            %I BOOLEAN NOT NULL DEFAULT FALSE,
            %I VARCHAR(200),
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL
        );
    $sql$, reveal_risk_col, reveal_reason_col);
END $$;
CREATE INDEX IF NOT EXISTS idx_social_posts_game ON game_social_posts(game_id);
CREATE INDEX IF NOT EXISTS idx_social_posts_team ON game_social_posts(team_id);
CREATE INDEX IF NOT EXISTS idx_social_posts_posted_at ON game_social_posts(posted_at);
CREATE INDEX IF NOT EXISTS idx_social_posts_media_type ON game_social_posts(media_type);
CREATE INDEX IF NOT EXISTS idx_social_posts_external_id ON game_social_posts(external_post_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_social_posts_platform_external_id ON game_social_posts(platform, external_post_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_social_posts_url ON game_social_posts(tweet_url);

-- Team social account registry
CREATE TABLE IF NOT EXISTS team_social_accounts (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES sports_teams(id) ON DELETE CASCADE,
    league_id INTEGER NOT NULL REFERENCES sports_leagues(id) ON DELETE CASCADE,
    platform VARCHAR(20) NOT NULL,
    handle VARCHAR(100) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    UNIQUE (platform, handle),
    UNIQUE (team_id, platform)
);
CREATE INDEX IF NOT EXISTS idx_team_social_accounts_league ON team_social_accounts(league_id);
CREATE INDEX IF NOT EXISTS idx_team_social_accounts_team ON team_social_accounts(team_id);

-- Social polling cache metadata
CREATE TABLE IF NOT EXISTS social_account_polls (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(20) NOT NULL,
    handle VARCHAR(100) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    status VARCHAR(30) NOT NULL,
    posts_found INTEGER NOT NULL DEFAULT 0,
    rate_limited_until TIMESTAMPTZ,
    error_detail TEXT,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    UNIQUE (platform, handle, window_start, window_end)
);
CREATE INDEX IF NOT EXISTS idx_social_account_polls_handle_window ON social_account_polls(handle, window_start, window_end);
CREATE INDEX IF NOT EXISTS idx_social_account_polls_platform ON social_account_polls(platform);

-- Compact mode thresholds
CREATE TABLE IF NOT EXISTS compact_mode_thresholds (
    id SERIAL PRIMARY KEY,
    sport_id INTEGER NOT NULL REFERENCES sports_leagues(id) ON DELETE CASCADE,
    thresholds JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    UNIQUE (sport_id)
);
CREATE INDEX IF NOT EXISTS idx_compact_mode_thresholds_sport_id ON compact_mode_thresholds(sport_id);

-- Seed leagues
INSERT INTO sports_leagues (code, name, level) VALUES
    ('NBA', 'National Basketball Association', 'pro'),
    ('NFL', 'National Football League', 'pro'),
    ('NCAAF', 'NCAA Football', 'college'),
    ('NCAAB', 'NCAA Basketball', 'college'),
    ('MLB', 'Major League Baseball', 'pro'),
    ('NHL', 'National Hockey League', 'pro')
ON CONFLICT (code) DO NOTHING;

-- Seed compact mode thresholds
INSERT INTO compact_mode_thresholds (sport_id, thresholds, description)
SELECT id, '[1, 2, 3, 5]'::jsonb, 'Score-lead thresholds for compact mode moments.'
FROM sports_leagues
WHERE code = 'NFL'
ON CONFLICT (sport_id) DO NOTHING;
INSERT INTO compact_mode_thresholds (sport_id, thresholds, description)
SELECT id, '[1, 2, 3, 5]'::jsonb, 'Score-lead thresholds for compact mode moments.'
FROM sports_leagues
WHERE code = 'NCAAF'
ON CONFLICT (sport_id) DO NOTHING;
INSERT INTO compact_mode_thresholds (sport_id, thresholds, description)
SELECT id, '[3, 6, 10, 16]'::jsonb, 'Point-lead thresholds for compact mode moments.'
FROM sports_leagues
WHERE code = 'NBA'
ON CONFLICT (sport_id) DO NOTHING;
INSERT INTO compact_mode_thresholds (sport_id, thresholds, description)
SELECT id, '[3, 6, 10, 16]'::jsonb, 'Point-lead thresholds for compact mode moments.'
FROM sports_leagues
WHERE code = 'NCAAB'
ON CONFLICT (sport_id) DO NOTHING;
INSERT INTO compact_mode_thresholds (sport_id, thresholds, description)
SELECT id, '[1, 2, 3, 5]'::jsonb, 'Run-lead thresholds for compact mode moments.'
FROM sports_leagues
WHERE code = 'MLB'
ON CONFLICT (sport_id) DO NOTHING;
INSERT INTO compact_mode_thresholds (sport_id, thresholds, description)
SELECT id, '[1, 2, 3]'::jsonb, 'Goal-lead thresholds for compact mode moments.'
FROM sports_leagues
WHERE code = 'NHL'
ON CONFLICT (sport_id) DO NOTHING;
