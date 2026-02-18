"""Baseline squash — full prod schema as of 2026-02-18.

Replaces all prior migrations (51 files with broken dependency graph).
Generated from pg_dump --schema-only of production database.
Backup: /opt/sports-data-api/backups/prod_backup_20260216.dump

Revision ID: 20260218_baseline
Revises: (none)
Create Date: 2026-02-18
"""

from __future__ import annotations

from alembic import op

revision = "20260218_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Tables ──────────────────────────────────────────────────────────

    op.execute("""
    CREATE TABLE public.sports_leagues (
        id serial PRIMARY KEY,
        code character varying(20) NOT NULL,
        name character varying(100) NOT NULL,
        level character varying(20) NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_teams (
        id serial PRIMARY KEY,
        league_id integer NOT NULL REFERENCES public.sports_leagues(id) ON DELETE CASCADE,
        external_ref character varying(100),
        name character varying(200) NOT NULL,
        short_name character varying(100) NOT NULL,
        abbreviation character varying(20) NOT NULL,
        location character varying(100),
        external_codes jsonb DEFAULT '{}'::jsonb NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        x_handle character varying(50),
        color_light_hex character varying(7),
        color_dark_hex character varying(7)
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_players (
        id serial PRIMARY KEY,
        league_id integer NOT NULL REFERENCES public.sports_leagues(id),
        external_id character varying(100) NOT NULL,
        name character varying(200) NOT NULL,
        "position" character varying(10),
        sweater_number integer,
        team_id integer REFERENCES public.sports_teams(id),
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_games (
        id serial PRIMARY KEY,
        league_id integer NOT NULL REFERENCES public.sports_leagues(id) ON DELETE CASCADE,
        season integer NOT NULL,
        season_type character varying(50) NOT NULL,
        game_date timestamp with time zone NOT NULL,
        home_team_id integer NOT NULL REFERENCES public.sports_teams(id) ON DELETE CASCADE,
        away_team_id integer NOT NULL REFERENCES public.sports_teams(id) ON DELETE CASCADE,
        home_score integer,
        away_score integer,
        venue character varying(200),
        status character varying(20) DEFAULT 'scheduled'::character varying NOT NULL,
        source_game_key character varying(100),
        scrape_version integer DEFAULT 1 NOT NULL,
        last_scraped_at timestamp with time zone,
        external_ids jsonb DEFAULT '{}'::jsonb NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        end_time timestamp with time zone,
        last_ingested_at timestamp with time zone,
        last_pbp_at timestamp with time zone,
        last_social_at timestamp with time zone,
        tip_time timestamp with time zone,
        social_scrape_1_at timestamp with time zone,
        social_scrape_2_at timestamp with time zone,
        closed_at timestamp with time zone,
        last_boxscore_at timestamp with time zone
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_game_plays (
        id serial PRIMARY KEY,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        quarter integer,
        game_clock character varying(10),
        play_index integer NOT NULL,
        play_type character varying(50),
        team_id integer REFERENCES public.sports_teams(id),
        player_id character varying(100),
        player_name character varying(200),
        description text,
        home_score integer,
        away_score integer,
        raw_data jsonb DEFAULT '{}'::jsonb NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone NOT NULL,
        player_ref_id integer REFERENCES public.sports_players(id)
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_scrape_runs (
        id serial PRIMARY KEY,
        scraper_type character varying(50) NOT NULL,
        league_id integer NOT NULL REFERENCES public.sports_leagues(id) ON DELETE CASCADE,
        season integer,
        season_type character varying(50),
        start_date timestamp with time zone,
        end_date timestamp with time zone,
        status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
        requested_by character varying(200),
        job_id character varying(100),
        summary text,
        error_details text,
        config jsonb DEFAULT '{}'::jsonb NOT NULL,
        started_at timestamp with time zone,
        finished_at timestamp with time zone,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_team_boxscores (
        id serial PRIMARY KEY,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        team_id integer NOT NULL REFERENCES public.sports_teams(id) ON DELETE CASCADE,
        is_home boolean NOT NULL,
        points integer,
        rebounds integer,
        assists integer,
        turnovers integer,
        passing_yards integer,
        rushing_yards integer,
        receiving_yards integer,
        hits integer,
        runs integer,
        errors integer,
        shots_on_goal integer,
        penalty_minutes integer,
        raw_stats_json jsonb DEFAULT '{}'::jsonb NOT NULL,
        source character varying(50),
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_player_boxscores (
        id serial PRIMARY KEY,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        team_id integer NOT NULL REFERENCES public.sports_teams(id) ON DELETE CASCADE,
        player_external_ref character varying(100) NOT NULL,
        player_name character varying(200) NOT NULL,
        minutes double precision,
        points integer,
        rebounds integer,
        assists integer,
        yards integer,
        touchdowns integer,
        shots_on_goal integer,
        penalties integer,
        raw_stats_json jsonb DEFAULT '{}'::jsonb NOT NULL,
        source character varying(50),
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_game_odds (
        id serial PRIMARY KEY,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        book character varying(50) NOT NULL,
        market_type character varying(80) NOT NULL,
        side character varying(200),
        line double precision,
        price double precision,
        is_closing_line boolean DEFAULT false NOT NULL,
        observed_at timestamp with time zone,
        source_key character varying(100),
        raw_payload jsonb DEFAULT '{}'::jsonb NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        market_category character varying(30) DEFAULT 'mainline'::character varying NOT NULL,
        player_name character varying(150),
        description text
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_game_conflicts (
        id serial PRIMARY KEY,
        league_id integer NOT NULL REFERENCES public.sports_leagues(id) ON DELETE CASCADE,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        conflict_game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        external_id character varying(100) NOT NULL,
        source character varying(50) NOT NULL,
        conflict_fields jsonb DEFAULT '{}'::jsonb NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        resolved_at timestamp with time zone
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_missing_pbp (
        id serial PRIMARY KEY,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        league_id integer NOT NULL REFERENCES public.sports_leagues(id) ON DELETE CASCADE,
        status character varying(20) NOT NULL,
        reason character varying(50) NOT NULL,
        detected_at timestamp with time zone NOT NULL,
        updated_at timestamp with time zone NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_job_runs (
        id serial PRIMARY KEY,
        phase character varying(50) NOT NULL,
        leagues jsonb DEFAULT '[]'::jsonb NOT NULL,
        status character varying(20) NOT NULL,
        started_at timestamp with time zone NOT NULL,
        finished_at timestamp with time zone,
        duration_seconds double precision,
        error_summary text,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.compact_mode_thresholds (
        id serial PRIMARY KEY,
        sport_id integer NOT NULL REFERENCES public.sports_leagues(id) ON DELETE CASCADE,
        thresholds jsonb NOT NULL,
        description text,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.game_reading_positions (
        id serial PRIMARY KEY,
        user_id character varying(100) NOT NULL,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        moment integer NOT NULL,
        "timestamp" double precision NOT NULL,
        scroll_hint text,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_game_stories (
        id serial PRIMARY KEY,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        sport character varying(20) NOT NULL,
        story_version character varying(20) NOT NULL,
        generated_at timestamp with time zone NOT NULL,
        ai_model_used character varying(50),
        total_ai_calls integer NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        moments_json jsonb,
        moment_count integer,
        validated_at timestamp with time zone,
        blocks_json jsonb,
        block_count integer,
        blocks_version character varying(20),
        blocks_validated_at timestamp with time zone
    );
    """)

    op.execute("""
    CREATE TABLE public.openai_response_cache (
        id serial PRIMARY KEY,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        batch_key character varying(64) NOT NULL,
        prompt_preview text,
        response_json jsonb NOT NULL,
        model character varying(50) NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.bulk_story_generation_jobs (
        id serial PRIMARY KEY,
        job_uuid uuid DEFAULT gen_random_uuid() NOT NULL,
        status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
        start_date timestamp with time zone,
        end_date timestamp with time zone,
        leagues jsonb DEFAULT '[]'::jsonb NOT NULL,
        force_regenerate boolean DEFAULT false NOT NULL,
        total_games integer NOT NULL,
        current_game integer NOT NULL,
        successful integer NOT NULL,
        failed integer NOT NULL,
        skipped integer NOT NULL,
        errors_json jsonb DEFAULT '[]'::jsonb NOT NULL,
        triggered_by character varying(100),
        started_at timestamp with time zone,
        finished_at timestamp with time zone,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        max_games integer
    );
    """)

    op.execute("""
    CREATE TABLE public.fairbet_game_odds_work (
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        market_key character varying(80) NOT NULL,
        selection_key text NOT NULL,
        line_value double precision DEFAULT 0 NOT NULL,
        book character varying(50) NOT NULL,
        price double precision NOT NULL,
        observed_at timestamp with time zone NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        market_category character varying(30) DEFAULT 'mainline'::character varying NOT NULL,
        player_name character varying(150),
        PRIMARY KEY (game_id, market_key, selection_key, line_value, book)
    );
    """)

    op.execute("""
    CREATE TABLE public.team_social_accounts (
        id serial PRIMARY KEY,
        team_id integer NOT NULL REFERENCES public.sports_teams(id) ON DELETE CASCADE,
        league_id integer NOT NULL REFERENCES public.sports_leagues(id) ON DELETE CASCADE,
        platform character varying(20) NOT NULL,
        handle character varying(100) NOT NULL,
        is_active boolean DEFAULT true NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.team_social_posts (
        id serial PRIMARY KEY,
        team_id integer NOT NULL REFERENCES public.sports_teams(id) ON DELETE CASCADE,
        platform character varying(20) DEFAULT 'x'::character varying NOT NULL,
        external_post_id character varying(100),
        post_url text NOT NULL,
        posted_at timestamp with time zone NOT NULL,
        tweet_text text,
        likes_count integer,
        retweets_count integer,
        replies_count integer,
        has_video boolean DEFAULT false NOT NULL,
        media_type character varying(20),
        image_url text,
        video_url text,
        source_handle character varying(100),
        game_id integer REFERENCES public.sports_games(id) ON DELETE SET NULL,
        mapping_status character varying(20) DEFAULT 'unmapped'::character varying NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        game_phase character varying(20)
    );
    """)

    op.execute("""
    CREATE TABLE public.social_account_polls (
        id serial PRIMARY KEY,
        platform character varying(20) NOT NULL,
        handle character varying(100) NOT NULL,
        window_start timestamp with time zone NOT NULL,
        window_end timestamp with time zone NOT NULL,
        status character varying(30) NOT NULL,
        posts_found integer DEFAULT 0 NOT NULL,
        rate_limited_until timestamp with time zone,
        error_detail text,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_game_timeline_artifacts (
        id serial PRIMARY KEY,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        sport character varying(20) NOT NULL,
        timeline_version character varying(20) NOT NULL,
        generated_at timestamp with time zone NOT NULL,
        timeline_json jsonb DEFAULT '[]'::jsonb NOT NULL,
        summary_json jsonb DEFAULT '{}'::jsonb NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        game_analysis_json jsonb DEFAULT '{}'::jsonb NOT NULL,
        generated_by character varying(50),
        generation_reason character varying(100)
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_game_pipeline_runs (
        id serial PRIMARY KEY,
        run_uuid uuid DEFAULT gen_random_uuid() NOT NULL,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        triggered_by character varying(20) NOT NULL,
        auto_chain boolean DEFAULT false NOT NULL,
        current_stage character varying(30),
        status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
        started_at timestamp with time zone,
        finished_at timestamp with time zone,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_game_pipeline_stages (
        id serial PRIMARY KEY,
        run_id integer NOT NULL REFERENCES public.sports_game_pipeline_runs(id) ON DELETE CASCADE,
        stage character varying(30) NOT NULL,
        status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
        output_json jsonb,
        logs_json jsonb DEFAULT '[]'::jsonb,
        error_details text,
        started_at timestamp with time zone,
        finished_at timestamp with time zone,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_pbp_snapshots (
        id serial PRIMARY KEY,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        pipeline_run_id integer REFERENCES public.sports_game_pipeline_runs(id) ON DELETE SET NULL,
        scrape_run_id integer REFERENCES public.sports_scrape_runs(id) ON DELETE SET NULL,
        snapshot_type character varying(20) NOT NULL,
        source character varying(50),
        play_count integer NOT NULL,
        plays_json jsonb DEFAULT '[]'::jsonb NOT NULL,
        metadata_json jsonb DEFAULT '{}'::jsonb,
        resolution_stats jsonb,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_entity_resolutions (
        id serial PRIMARY KEY,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        pipeline_run_id integer REFERENCES public.sports_game_pipeline_runs(id) ON DELETE SET NULL,
        entity_type character varying(20) NOT NULL,
        source_identifier character varying(200) NOT NULL,
        source_context jsonb,
        resolved_id integer,
        resolved_name character varying(200),
        resolution_status character varying(20) NOT NULL,
        resolution_method character varying(50),
        confidence double precision,
        failure_reason character varying(200),
        candidates jsonb,
        occurrence_count integer NOT NULL,
        first_play_index integer,
        last_play_index integer,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    op.execute("""
    CREATE TABLE public.sports_frontend_payload_versions (
        id serial PRIMARY KEY,
        game_id integer NOT NULL REFERENCES public.sports_games(id) ON DELETE CASCADE,
        pipeline_run_id integer REFERENCES public.sports_game_pipeline_runs(id) ON DELETE SET NULL,
        version_number integer NOT NULL,
        is_active boolean DEFAULT false NOT NULL,
        payload_hash character varying(64) NOT NULL,
        timeline_json jsonb DEFAULT '[]'::jsonb NOT NULL,
        moments_json jsonb DEFAULT '[]'::jsonb NOT NULL,
        summary_json jsonb DEFAULT '{}'::jsonb NOT NULL,
        event_count integer NOT NULL,
        moment_count integer NOT NULL,
        generation_source character varying(50),
        generation_notes text,
        diff_from_previous jsonb,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """)

    # ── Unique constraints ──────────────────────────────────────────────

    op.execute("ALTER TABLE ONLY public.compact_mode_thresholds ADD CONSTRAINT compact_mode_thresholds_sport_id_key UNIQUE (sport_id);")
    op.execute("ALTER TABLE ONLY public.game_reading_positions ADD CONSTRAINT game_reading_positions_user_id_game_id_key UNIQUE (user_id, game_id);")
    op.execute("ALTER TABLE ONLY public.team_social_posts ADD CONSTRAINT team_social_posts_external_post_id_key UNIQUE (external_post_id);")
    op.execute("ALTER TABLE ONLY public.sports_game_conflicts ADD CONSTRAINT uq_game_conflict UNIQUE (game_id, conflict_game_id, external_id, source);")
    op.execute("ALTER TABLE ONLY public.sports_games ADD CONSTRAINT uq_game_identity UNIQUE (league_id, season, game_date, home_team_id, away_team_id);")
    op.execute("ALTER TABLE ONLY public.sports_game_stories ADD CONSTRAINT uq_game_story_version UNIQUE (game_id, story_version);")
    op.execute("ALTER TABLE ONLY public.sports_game_timeline_artifacts ADD CONSTRAINT uq_game_timeline_artifact_version UNIQUE (game_id, sport, timeline_version);")
    op.execute("ALTER TABLE ONLY public.sports_missing_pbp ADD CONSTRAINT uq_missing_pbp_game UNIQUE (game_id);")
    op.execute("ALTER TABLE ONLY public.openai_response_cache ADD CONSTRAINT uq_openai_cache_game_batch UNIQUE (game_id, batch_key);")
    op.execute("ALTER TABLE ONLY public.sports_game_pipeline_stages ADD CONSTRAINT uq_pipeline_stages_run_stage UNIQUE (run_id, stage);")
    op.execute("ALTER TABLE ONLY public.sports_player_boxscores ADD CONSTRAINT uq_player_boxscore_identity UNIQUE (game_id, team_id, player_external_ref);")
    op.execute("ALTER TABLE ONLY public.sports_players ADD CONSTRAINT uq_player_identity UNIQUE (league_id, external_id);")
    op.execute("ALTER TABLE ONLY public.social_account_polls ADD CONSTRAINT uq_social_account_poll_window UNIQUE (platform, handle, window_start, window_end);")
    op.execute("ALTER TABLE ONLY public.sports_games ADD CONSTRAINT uq_sports_game_league_source_key UNIQUE (league_id, source_game_key);")
    op.execute("ALTER TABLE ONLY public.sports_team_boxscores ADD CONSTRAINT uq_team_boxscore_game_team UNIQUE (game_id, team_id);")
    op.execute("ALTER TABLE ONLY public.team_social_accounts ADD CONSTRAINT uq_team_social_accounts_platform_handle UNIQUE (platform, handle);")
    op.execute("ALTER TABLE ONLY public.team_social_accounts ADD CONSTRAINT uq_team_social_accounts_team_platform UNIQUE (team_id, platform);")
    op.execute("ALTER TABLE ONLY public.sports_leagues ADD CONSTRAINT sports_leagues_code_key UNIQUE (code);")
    op.execute("ALTER TABLE ONLY public.sports_teams ADD CONSTRAINT sports_teams_league_name_unique UNIQUE (league_id, name);")

    # ── Indexes ─────────────────────────────────────────────────────────

    op.execute("CREATE UNIQUE INDEX idx_bulk_story_jobs_uuid ON public.bulk_story_generation_jobs USING btree (job_uuid);")
    op.execute("CREATE INDEX idx_compact_mode_thresholds_sport_id ON public.compact_mode_thresholds USING btree (sport_id);")
    op.execute("CREATE INDEX idx_entity_resolutions_entity_type ON public.sports_entity_resolutions USING btree (entity_type);")
    op.execute("CREATE INDEX idx_entity_resolutions_game ON public.sports_entity_resolutions USING btree (game_id);")
    op.execute("CREATE INDEX idx_entity_resolutions_game_type ON public.sports_entity_resolutions USING btree (game_id, entity_type);")
    op.execute("CREATE INDEX idx_entity_resolutions_pipeline_run ON public.sports_entity_resolutions USING btree (pipeline_run_id);")
    op.execute("CREATE INDEX idx_entity_resolutions_status ON public.sports_entity_resolutions USING btree (resolution_status);")
    op.execute("CREATE INDEX idx_fairbet_odds_game ON public.fairbet_game_odds_work USING btree (game_id);")
    op.execute("CREATE INDEX idx_fairbet_odds_market_category ON public.fairbet_game_odds_work USING btree (market_category);")
    op.execute("CREATE INDEX idx_fairbet_odds_observed ON public.fairbet_game_odds_work USING btree (observed_at);")
    op.execute("CREATE INDEX idx_frontend_payload_active ON public.sports_frontend_payload_versions USING btree (game_id, is_active) WHERE (is_active = true);")
    op.execute("CREATE INDEX idx_frontend_payload_game ON public.sports_frontend_payload_versions USING btree (game_id);")
    op.execute("CREATE INDEX idx_frontend_payload_pipeline_run ON public.sports_frontend_payload_versions USING btree (pipeline_run_id);")
    op.execute("CREATE UNIQUE INDEX idx_frontend_payload_unique_active ON public.sports_frontend_payload_versions USING btree (game_id) WHERE (is_active = true);")
    op.execute("CREATE INDEX idx_frontend_payload_version ON public.sports_frontend_payload_versions USING btree (game_id, version_number);")
    op.execute("CREATE INDEX idx_game_conflicts_league_created ON public.sports_game_conflicts USING btree (league_id, created_at);")
    op.execute("CREATE INDEX idx_game_odds_market_category ON public.sports_game_odds USING btree (market_category);")
    op.execute("CREATE INDEX idx_game_plays_game ON public.sports_game_plays USING btree (game_id);")
    op.execute("CREATE INDEX idx_game_plays_player ON public.sports_game_plays USING btree (player_id);")
    op.execute("CREATE INDEX idx_game_plays_type ON public.sports_game_plays USING btree (play_type);")
    op.execute("CREATE INDEX idx_game_stories_game_id ON public.sports_game_stories USING btree (game_id);")
    op.execute("CREATE INDEX idx_game_stories_generated_at ON public.sports_game_stories USING btree (generated_at);")
    op.execute("CREATE INDEX idx_game_stories_moments ON public.sports_game_stories USING btree (game_id) WHERE (moments_json IS NOT NULL);")
    op.execute("CREATE INDEX idx_game_stories_sport ON public.sports_game_stories USING btree (sport);")
    op.execute("CREATE INDEX idx_game_timeline_artifacts_game ON public.sports_game_timeline_artifacts USING btree (game_id);")
    op.execute("CREATE INDEX idx_game_timeline_artifacts_sport ON public.sports_game_timeline_artifacts USING btree (sport);")
    op.execute("CREATE INDEX idx_games_league_season_date ON public.sports_games USING btree (league_id, season, game_date);")
    op.execute("CREATE INDEX idx_games_league_status ON public.sports_games USING btree (league_id, status);")
    op.execute("CREATE INDEX idx_games_status_tip_time ON public.sports_games USING btree (status, tip_time);")
    op.execute("CREATE INDEX idx_games_teams ON public.sports_games USING btree (home_team_id, away_team_id);")
    op.execute("CREATE INDEX idx_job_runs_phase_started ON public.sports_job_runs USING btree (phase, started_at);")
    op.execute("CREATE INDEX idx_missing_pbp_league_status ON public.sports_missing_pbp USING btree (league_id, status);")
    op.execute("CREATE INDEX idx_openai_cache_game_id ON public.openai_response_cache USING btree (game_id);")
    op.execute("CREATE INDEX idx_pbp_snapshots_game ON public.sports_pbp_snapshots USING btree (game_id);")
    op.execute("CREATE INDEX idx_pbp_snapshots_game_type ON public.sports_pbp_snapshots USING btree (game_id, snapshot_type);")
    op.execute("CREATE INDEX idx_pbp_snapshots_pipeline_run ON public.sports_pbp_snapshots USING btree (pipeline_run_id);")
    op.execute("CREATE INDEX idx_pbp_snapshots_type ON public.sports_pbp_snapshots USING btree (snapshot_type);")
    op.execute("CREATE INDEX idx_pipeline_runs_created ON public.sports_game_pipeline_runs USING btree (created_at);")
    op.execute("CREATE INDEX idx_pipeline_runs_game ON public.sports_game_pipeline_runs USING btree (game_id);")
    op.execute("CREATE INDEX idx_pipeline_runs_status ON public.sports_game_pipeline_runs USING btree (status);")
    op.execute("CREATE UNIQUE INDEX idx_pipeline_runs_uuid ON public.sports_game_pipeline_runs USING btree (run_uuid);")
    op.execute("CREATE INDEX idx_pipeline_stages_run ON public.sports_game_pipeline_stages USING btree (run_id);")
    op.execute("CREATE INDEX idx_pipeline_stages_status ON public.sports_game_pipeline_stages USING btree (status);")
    op.execute("CREATE INDEX idx_players_external_id ON public.sports_players USING btree (external_id);")
    op.execute("CREATE INDEX idx_players_name ON public.sports_players USING btree (name);")
    op.execute("CREATE INDEX idx_plays_player_ref ON public.sports_game_plays USING btree (player_ref_id);")
    op.execute("CREATE INDEX idx_reading_positions_game_id ON public.game_reading_positions USING btree (game_id);")
    op.execute("CREATE INDEX idx_reading_positions_user_game ON public.game_reading_positions USING btree (user_id, game_id);")
    op.execute("CREATE INDEX idx_reading_positions_user_id ON public.game_reading_positions USING btree (user_id);")
    op.execute("CREATE INDEX idx_scrape_runs_created ON public.sports_scrape_runs USING btree (created_at);")
    op.execute("CREATE INDEX idx_scrape_runs_league_status ON public.sports_scrape_runs USING btree (league_id, status);")
    op.execute("CREATE INDEX idx_social_account_polls_handle_window ON public.social_account_polls USING btree (handle, window_start, window_end);")
    op.execute("CREATE INDEX idx_social_account_polls_platform ON public.social_account_polls USING btree (platform);")
    op.execute("CREATE UNIQUE INDEX idx_sports_teams_league_name ON public.sports_teams USING btree (league_id, name);")
    op.execute("CREATE INDEX idx_sports_teams_league_name_lower ON public.sports_teams USING btree (league_id, lower((name)::text));")
    op.execute("CREATE INDEX idx_sports_teams_x_handle ON public.sports_teams USING btree (x_handle) WHERE (x_handle IS NOT NULL);")
    op.execute("CREATE INDEX idx_team_social_accounts_league ON public.team_social_accounts USING btree (league_id);")
    op.execute("CREATE INDEX idx_team_social_accounts_team_id ON public.team_social_accounts USING btree (team_id);")
    op.execute("CREATE INDEX idx_team_social_posts_game ON public.team_social_posts USING btree (game_id);")
    op.execute("CREATE INDEX idx_team_social_posts_game_phase ON public.team_social_posts USING btree (game_phase);")
    op.execute("CREATE INDEX idx_team_social_posts_mapping_status ON public.team_social_posts USING btree (mapping_status);")
    op.execute("CREATE INDEX idx_team_social_posts_posted_at ON public.team_social_posts USING btree (posted_at);")
    op.execute("CREATE INDEX idx_team_social_posts_team ON public.team_social_posts USING btree (team_id);")
    op.execute("CREATE INDEX idx_team_social_posts_team_status ON public.team_social_posts USING btree (team_id, mapping_status);")
    op.execute("CREATE INDEX ix_bulk_story_generation_jobs_created_at ON public.bulk_story_generation_jobs USING btree (created_at);")
    op.execute("CREATE INDEX ix_bulk_story_generation_jobs_status ON public.bulk_story_generation_jobs USING btree (status);")
    op.execute("CREATE INDEX ix_player_boxscores_game ON public.sports_player_boxscores USING btree (game_id);")
    op.execute("CREATE INDEX ix_sports_game_conflicts_conflict_game_id ON public.sports_game_conflicts USING btree (conflict_game_id);")
    op.execute("CREATE INDEX ix_sports_game_conflicts_game_id ON public.sports_game_conflicts USING btree (game_id);")
    op.execute("CREATE INDEX ix_sports_game_conflicts_league_id ON public.sports_game_conflicts USING btree (league_id);")
    op.execute("CREATE INDEX ix_sports_games_tip_time ON public.sports_games USING btree (tip_time);")
    op.execute("CREATE INDEX ix_sports_job_runs_phase ON public.sports_job_runs USING btree (phase);")
    op.execute("CREATE INDEX ix_sports_job_runs_status ON public.sports_job_runs USING btree (status);")
    op.execute("CREATE UNIQUE INDEX ix_sports_leagues_code ON public.sports_leagues USING btree (code);")
    op.execute("CREATE INDEX ix_sports_missing_pbp_game_id ON public.sports_missing_pbp USING btree (game_id);")
    op.execute("CREATE INDEX ix_sports_missing_pbp_league_id ON public.sports_missing_pbp USING btree (league_id);")
    op.execute("CREATE INDEX ix_sports_teams_league ON public.sports_teams USING btree (league_id);")
    op.execute("CREATE INDEX ix_team_boxscores_game ON public.sports_team_boxscores USING btree (game_id);")
    op.execute("CREATE UNIQUE INDEX uq_game_play_index ON public.sports_game_plays USING btree (game_id, play_index);")
    op.execute("CREATE UNIQUE INDEX uq_sports_game_odds_identity ON public.sports_game_odds USING btree (game_id, book, market_type, side, is_closing_line);")

    # ── Column comments ─────────────────────────────────────────────────

    op.execute("COMMENT ON COLUMN public.sports_game_stories.moments_json IS 'Ordered list of condensed moments (v2 Story format)';")
    op.execute("COMMENT ON COLUMN public.sports_game_stories.moment_count IS 'Number of moments in moments_json';")
    op.execute("COMMENT ON COLUMN public.sports_game_stories.validated_at IS 'When moment validation passed';")
    op.execute("COMMENT ON COLUMN public.sports_game_pipeline_runs.triggered_by IS 'prod_auto, admin, manual, backfill';")
    op.execute("COMMENT ON COLUMN public.sports_game_pipeline_runs.auto_chain IS 'Whether to automatically proceed to next stage';")
    op.execute("COMMENT ON COLUMN public.sports_game_pipeline_runs.current_stage IS 'Current or last executed stage name';")
    op.execute("COMMENT ON COLUMN public.sports_game_pipeline_runs.status IS 'pending, running, completed, failed, paused';")
    op.execute("COMMENT ON COLUMN public.sports_game_pipeline_stages.stage IS 'NORMALIZE_PBP, DERIVE_SIGNALS, GENERATE_MOMENTS, VALIDATE_MOMENTS, FINALIZE_MOMENTS';")
    op.execute("COMMENT ON COLUMN public.sports_game_pipeline_stages.status IS 'pending, running, success, failed, skipped';")
    op.execute("COMMENT ON COLUMN public.sports_game_pipeline_stages.output_json IS 'Stage-specific output data';")
    op.execute("COMMENT ON COLUMN public.sports_game_pipeline_stages.logs_json IS 'Array of log entries with timestamps';")
    op.execute("COMMENT ON COLUMN public.sports_game_pipeline_stages.error_details IS 'Error message if stage failed';")
    op.execute("COMMENT ON COLUMN public.sports_pbp_snapshots.pipeline_run_id IS 'Pipeline run that created this snapshot (null for scrape-time snapshots)';")
    op.execute("COMMENT ON COLUMN public.sports_pbp_snapshots.scrape_run_id IS 'Scrape run that created this snapshot (for raw PBP)';")
    op.execute("COMMENT ON COLUMN public.sports_pbp_snapshots.snapshot_type IS 'raw, normalized, or resolved';")
    op.execute("COMMENT ON COLUMN public.sports_pbp_snapshots.source IS 'Data source (e.g., nba_live, nhl_api, sportsref)';")
    op.execute("COMMENT ON COLUMN public.sports_pbp_snapshots.plays_json IS 'Array of play objects';")
    op.execute("COMMENT ON COLUMN public.sports_pbp_snapshots.metadata_json IS 'Snapshot metadata (game timing, resolution stats, etc.)';")
    op.execute("COMMENT ON COLUMN public.sports_pbp_snapshots.resolution_stats IS 'Stats on team/player/score resolution';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.entity_type IS 'team or player';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.source_identifier IS 'Original identifier from source (e.g., team abbrev, player name)';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.source_context IS 'Additional source context (e.g., raw_data fields)';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.resolved_id IS 'Internal ID if resolved (team_id or future player_id)';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.resolved_name IS 'Resolved entity name';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.resolution_status IS 'success, failed, ambiguous, partial';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.resolution_method IS 'How resolution was performed (exact_match, fuzzy, abbreviation, etc.)';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.confidence IS 'Confidence score 0-1 if applicable';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.failure_reason IS 'Why resolution failed';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.candidates IS 'Candidate matches if ambiguous';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.occurrence_count IS 'How many times this source identifier appeared';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.first_play_index IS 'First play index where this entity appeared';")
    op.execute("COMMENT ON COLUMN public.sports_entity_resolutions.last_play_index IS 'Last play index where this entity appeared';")
    op.execute("COMMENT ON COLUMN public.sports_frontend_payload_versions.pipeline_run_id IS 'Pipeline run that created this version';")
    op.execute("COMMENT ON COLUMN public.sports_frontend_payload_versions.version_number IS 'Auto-incrementing version number per game';")
    op.execute("COMMENT ON COLUMN public.sports_frontend_payload_versions.is_active IS 'True if this is the currently active version for the frontend';")
    op.execute("COMMENT ON COLUMN public.sports_frontend_payload_versions.payload_hash IS 'SHA-256 hash of payload for change detection';")
    op.execute("COMMENT ON COLUMN public.sports_frontend_payload_versions.timeline_json IS 'Timeline events (PBP + social)';")
    op.execute("COMMENT ON COLUMN public.sports_frontend_payload_versions.moments_json IS 'Generated moments';")
    op.execute("COMMENT ON COLUMN public.sports_frontend_payload_versions.summary_json IS 'Game summary for frontend';")
    op.execute("COMMENT ON COLUMN public.sports_frontend_payload_versions.generation_source IS 'pipeline, manual, backfill, etc.';")
    op.execute("COMMENT ON COLUMN public.sports_frontend_payload_versions.generation_notes IS 'Any notes about this generation';")
    op.execute("COMMENT ON COLUMN public.sports_frontend_payload_versions.diff_from_previous IS 'Summary of changes from previous version';")


def downgrade() -> None:
    tables = [
        "sports_frontend_payload_versions",
        "sports_entity_resolutions",
        "sports_pbp_snapshots",
        "sports_game_pipeline_stages",
        "sports_game_pipeline_runs",
        "sports_game_timeline_artifacts",
        "social_account_polls",
        "team_social_posts",
        "team_social_accounts",
        "fairbet_game_odds_work",
        "bulk_story_generation_jobs",
        "openai_response_cache",
        "sports_game_stories",
        "game_reading_positions",
        "compact_mode_thresholds",
        "sports_job_runs",
        "sports_missing_pbp",
        "sports_game_conflicts",
        "sports_game_odds",
        "sports_player_boxscores",
        "sports_team_boxscores",
        "sports_scrape_runs",
        "sports_game_plays",
        "sports_games",
        "sports_players",
        "sports_teams",
        "sports_leagues",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS public.{t} CASCADE;")
