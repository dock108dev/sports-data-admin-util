--
-- PostgreSQL database dump
--

\restrict GXxoOz2wemdtE4ic8t9JY993WaP9f9qr3gARxEvRjiR2nNXPeprhwwZBfm88ShD

-- Dumped from database version 16.12
-- Dumped by pg_dump version 16.12

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: dock108
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO dock108;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.alembic_version (
    version_num character varying(64) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO dock108;

--
-- Name: bulk_story_generation_jobs; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.bulk_story_generation_jobs (
    id integer NOT NULL,
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


ALTER TABLE public.bulk_story_generation_jobs OWNER TO dock108;

--
-- Name: bulk_story_generation_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.bulk_story_generation_jobs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.bulk_story_generation_jobs_id_seq OWNER TO dock108;

--
-- Name: bulk_story_generation_jobs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.bulk_story_generation_jobs_id_seq OWNED BY public.bulk_story_generation_jobs.id;


--
-- Name: compact_mode_thresholds; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.compact_mode_thresholds (
    id integer NOT NULL,
    sport_id integer NOT NULL,
    thresholds jsonb NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.compact_mode_thresholds OWNER TO dock108;

--
-- Name: compact_mode_thresholds_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.compact_mode_thresholds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.compact_mode_thresholds_id_seq OWNER TO dock108;

--
-- Name: compact_mode_thresholds_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.compact_mode_thresholds_id_seq OWNED BY public.compact_mode_thresholds.id;


--
-- Name: fairbet_game_odds_work; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.fairbet_game_odds_work (
    game_id integer NOT NULL,
    market_key character varying(80) NOT NULL,
    selection_key text NOT NULL,
    line_value double precision DEFAULT '0'::double precision NOT NULL,
    book character varying(50) NOT NULL,
    price double precision NOT NULL,
    observed_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    market_category character varying(30) DEFAULT 'mainline'::character varying NOT NULL,
    player_name character varying(150)
);


ALTER TABLE public.fairbet_game_odds_work OWNER TO dock108;

--
-- Name: game_reading_positions; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.game_reading_positions (
    id integer NOT NULL,
    user_id character varying(100) NOT NULL,
    game_id integer NOT NULL,
    moment integer NOT NULL,
    "timestamp" double precision NOT NULL,
    scroll_hint text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.game_reading_positions OWNER TO dock108;

--
-- Name: game_reading_positions_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.game_reading_positions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.game_reading_positions_id_seq OWNER TO dock108;

--
-- Name: game_reading_positions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.game_reading_positions_id_seq OWNED BY public.game_reading_positions.id;


--
-- Name: openai_response_cache; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.openai_response_cache (
    id integer NOT NULL,
    game_id integer NOT NULL,
    batch_key character varying(64) NOT NULL,
    prompt_preview text,
    response_json jsonb NOT NULL,
    model character varying(50) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.openai_response_cache OWNER TO dock108;

--
-- Name: openai_response_cache_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.openai_response_cache_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.openai_response_cache_id_seq OWNER TO dock108;

--
-- Name: openai_response_cache_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.openai_response_cache_id_seq OWNED BY public.openai_response_cache.id;


--
-- Name: social_account_polls; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.social_account_polls (
    id integer NOT NULL,
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


ALTER TABLE public.social_account_polls OWNER TO dock108;

--
-- Name: social_account_polls_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.social_account_polls_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.social_account_polls_id_seq OWNER TO dock108;

--
-- Name: social_account_polls_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.social_account_polls_id_seq OWNED BY public.social_account_polls.id;


--
-- Name: sports_entity_resolutions; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_entity_resolutions (
    id integer NOT NULL,
    game_id integer NOT NULL,
    pipeline_run_id integer,
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


ALTER TABLE public.sports_entity_resolutions OWNER TO dock108;

--
-- Name: COLUMN sports_entity_resolutions.entity_type; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.entity_type IS 'team or player';


--
-- Name: COLUMN sports_entity_resolutions.source_identifier; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.source_identifier IS 'Original identifier from source (e.g., team abbrev, player name)';


--
-- Name: COLUMN sports_entity_resolutions.source_context; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.source_context IS 'Additional source context (e.g., raw_data fields)';


--
-- Name: COLUMN sports_entity_resolutions.resolved_id; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.resolved_id IS 'Internal ID if resolved (team_id or future player_id)';


--
-- Name: COLUMN sports_entity_resolutions.resolved_name; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.resolved_name IS 'Resolved entity name';


--
-- Name: COLUMN sports_entity_resolutions.resolution_status; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.resolution_status IS 'success, failed, ambiguous, partial';


--
-- Name: COLUMN sports_entity_resolutions.resolution_method; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.resolution_method IS 'How resolution was performed (exact_match, fuzzy, abbreviation, etc.)';


--
-- Name: COLUMN sports_entity_resolutions.confidence; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.confidence IS 'Confidence score 0-1 if applicable';


--
-- Name: COLUMN sports_entity_resolutions.failure_reason; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.failure_reason IS 'Why resolution failed';


--
-- Name: COLUMN sports_entity_resolutions.candidates; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.candidates IS 'Candidate matches if ambiguous';


--
-- Name: COLUMN sports_entity_resolutions.occurrence_count; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.occurrence_count IS 'How many times this source identifier appeared';


--
-- Name: COLUMN sports_entity_resolutions.first_play_index; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.first_play_index IS 'First play index where this entity appeared';


--
-- Name: COLUMN sports_entity_resolutions.last_play_index; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_entity_resolutions.last_play_index IS 'Last play index where this entity appeared';


--
-- Name: sports_entity_resolutions_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_entity_resolutions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_entity_resolutions_id_seq OWNER TO dock108;

--
-- Name: sports_entity_resolutions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_entity_resolutions_id_seq OWNED BY public.sports_entity_resolutions.id;


--
-- Name: sports_frontend_payload_versions; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_frontend_payload_versions (
    id integer NOT NULL,
    game_id integer NOT NULL,
    pipeline_run_id integer,
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


ALTER TABLE public.sports_frontend_payload_versions OWNER TO dock108;

--
-- Name: COLUMN sports_frontend_payload_versions.pipeline_run_id; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_frontend_payload_versions.pipeline_run_id IS 'Pipeline run that created this version';


--
-- Name: COLUMN sports_frontend_payload_versions.version_number; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_frontend_payload_versions.version_number IS 'Auto-incrementing version number per game';


--
-- Name: COLUMN sports_frontend_payload_versions.is_active; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_frontend_payload_versions.is_active IS 'True if this is the currently active version for the frontend';


--
-- Name: COLUMN sports_frontend_payload_versions.payload_hash; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_frontend_payload_versions.payload_hash IS 'SHA-256 hash of payload for change detection';


--
-- Name: COLUMN sports_frontend_payload_versions.timeline_json; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_frontend_payload_versions.timeline_json IS 'Timeline events (PBP + social)';


--
-- Name: COLUMN sports_frontend_payload_versions.moments_json; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_frontend_payload_versions.moments_json IS 'Generated moments';


--
-- Name: COLUMN sports_frontend_payload_versions.summary_json; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_frontend_payload_versions.summary_json IS 'Game summary for frontend';


--
-- Name: COLUMN sports_frontend_payload_versions.generation_source; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_frontend_payload_versions.generation_source IS 'pipeline, manual, backfill, etc.';


--
-- Name: COLUMN sports_frontend_payload_versions.generation_notes; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_frontend_payload_versions.generation_notes IS 'Any notes about this generation';


--
-- Name: COLUMN sports_frontend_payload_versions.diff_from_previous; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_frontend_payload_versions.diff_from_previous IS 'Summary of changes from previous version';


--
-- Name: sports_frontend_payload_versions_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_frontend_payload_versions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_frontend_payload_versions_id_seq OWNER TO dock108;

--
-- Name: sports_frontend_payload_versions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_frontend_payload_versions_id_seq OWNED BY public.sports_frontend_payload_versions.id;


--
-- Name: sports_game_conflicts; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_game_conflicts (
    id integer NOT NULL,
    league_id integer NOT NULL,
    game_id integer NOT NULL,
    conflict_game_id integer NOT NULL,
    external_id character varying(100) NOT NULL,
    source character varying(50) NOT NULL,
    conflict_fields jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone
);


ALTER TABLE public.sports_game_conflicts OWNER TO dock108;

--
-- Name: sports_game_conflicts_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_game_conflicts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_game_conflicts_id_seq OWNER TO dock108;

--
-- Name: sports_game_conflicts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_game_conflicts_id_seq OWNED BY public.sports_game_conflicts.id;


--
-- Name: sports_game_odds; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_game_odds (
    id integer NOT NULL,
    game_id integer NOT NULL,
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


ALTER TABLE public.sports_game_odds OWNER TO dock108;

--
-- Name: sports_game_odds_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_game_odds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_game_odds_id_seq OWNER TO dock108;

--
-- Name: sports_game_odds_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_game_odds_id_seq OWNED BY public.sports_game_odds.id;


--
-- Name: sports_game_pipeline_runs; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_game_pipeline_runs (
    id integer NOT NULL,
    run_uuid uuid DEFAULT gen_random_uuid() NOT NULL,
    game_id integer NOT NULL,
    triggered_by character varying(20) NOT NULL,
    auto_chain boolean DEFAULT false NOT NULL,
    current_stage character varying(30),
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.sports_game_pipeline_runs OWNER TO dock108;

--
-- Name: COLUMN sports_game_pipeline_runs.triggered_by; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_game_pipeline_runs.triggered_by IS 'prod_auto, admin, manual, backfill';


--
-- Name: COLUMN sports_game_pipeline_runs.auto_chain; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_game_pipeline_runs.auto_chain IS 'Whether to automatically proceed to next stage';


--
-- Name: COLUMN sports_game_pipeline_runs.current_stage; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_game_pipeline_runs.current_stage IS 'Current or last executed stage name';


--
-- Name: COLUMN sports_game_pipeline_runs.status; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_game_pipeline_runs.status IS 'pending, running, completed, failed, paused';


--
-- Name: sports_game_pipeline_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_game_pipeline_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_game_pipeline_runs_id_seq OWNER TO dock108;

--
-- Name: sports_game_pipeline_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_game_pipeline_runs_id_seq OWNED BY public.sports_game_pipeline_runs.id;


--
-- Name: sports_game_pipeline_stages; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_game_pipeline_stages (
    id integer NOT NULL,
    run_id integer NOT NULL,
    stage character varying(30) NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    output_json jsonb,
    logs_json jsonb DEFAULT '[]'::jsonb,
    error_details text,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.sports_game_pipeline_stages OWNER TO dock108;

--
-- Name: COLUMN sports_game_pipeline_stages.stage; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_game_pipeline_stages.stage IS 'NORMALIZE_PBP, DERIVE_SIGNALS, GENERATE_MOMENTS, VALIDATE_MOMENTS, FINALIZE_MOMENTS';


--
-- Name: COLUMN sports_game_pipeline_stages.status; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_game_pipeline_stages.status IS 'pending, running, success, failed, skipped';


--
-- Name: COLUMN sports_game_pipeline_stages.output_json; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_game_pipeline_stages.output_json IS 'Stage-specific output data';


--
-- Name: COLUMN sports_game_pipeline_stages.logs_json; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_game_pipeline_stages.logs_json IS 'Array of log entries with timestamps';


--
-- Name: COLUMN sports_game_pipeline_stages.error_details; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_game_pipeline_stages.error_details IS 'Error message if stage failed';


--
-- Name: sports_game_pipeline_stages_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_game_pipeline_stages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_game_pipeline_stages_id_seq OWNER TO dock108;

--
-- Name: sports_game_pipeline_stages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_game_pipeline_stages_id_seq OWNED BY public.sports_game_pipeline_stages.id;


--
-- Name: sports_game_plays; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_game_plays (
    id integer NOT NULL,
    game_id integer NOT NULL,
    quarter integer,
    game_clock character varying(10),
    play_index integer NOT NULL,
    play_type character varying(50),
    team_id integer,
    player_id character varying(100),
    player_name character varying(200),
    description text,
    home_score integer,
    away_score integer,
    raw_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    player_ref_id integer
);


ALTER TABLE public.sports_game_plays OWNER TO dock108;

--
-- Name: sports_game_plays_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_game_plays_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_game_plays_id_seq OWNER TO dock108;

--
-- Name: sports_game_plays_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_game_plays_id_seq OWNED BY public.sports_game_plays.id;


--
-- Name: sports_game_stories; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_game_stories (
    id integer NOT NULL,
    game_id integer NOT NULL,
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


ALTER TABLE public.sports_game_stories OWNER TO dock108;

--
-- Name: COLUMN sports_game_stories.moments_json; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_game_stories.moments_json IS 'Ordered list of condensed moments (v2 Story format)';


--
-- Name: COLUMN sports_game_stories.moment_count; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_game_stories.moment_count IS 'Number of moments in moments_json';


--
-- Name: COLUMN sports_game_stories.validated_at; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_game_stories.validated_at IS 'When moment validation passed';


--
-- Name: sports_game_stories_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_game_stories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_game_stories_id_seq OWNER TO dock108;

--
-- Name: sports_game_stories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_game_stories_id_seq OWNED BY public.sports_game_stories.id;


--
-- Name: sports_game_timeline_artifacts; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_game_timeline_artifacts (
    id integer NOT NULL,
    game_id integer NOT NULL,
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


ALTER TABLE public.sports_game_timeline_artifacts OWNER TO dock108;

--
-- Name: sports_game_timeline_artifacts_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_game_timeline_artifacts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_game_timeline_artifacts_id_seq OWNER TO dock108;

--
-- Name: sports_game_timeline_artifacts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_game_timeline_artifacts_id_seq OWNED BY public.sports_game_timeline_artifacts.id;


--
-- Name: sports_games; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_games (
    id integer NOT NULL,
    league_id integer NOT NULL,
    season integer NOT NULL,
    season_type character varying(50) NOT NULL,
    game_date timestamp with time zone NOT NULL,
    home_team_id integer NOT NULL,
    away_team_id integer NOT NULL,
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
    closed_at timestamp with time zone
);


ALTER TABLE public.sports_games OWNER TO dock108;

--
-- Name: sports_games_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_games_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_games_id_seq OWNER TO dock108;

--
-- Name: sports_games_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_games_id_seq OWNED BY public.sports_games.id;


--
-- Name: sports_job_runs; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_job_runs (
    id integer NOT NULL,
    phase character varying(50) NOT NULL,
    leagues jsonb DEFAULT '[]'::jsonb NOT NULL,
    status character varying(20) NOT NULL,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    duration_seconds double precision,
    error_summary text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.sports_job_runs OWNER TO dock108;

--
-- Name: sports_job_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_job_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_job_runs_id_seq OWNER TO dock108;

--
-- Name: sports_job_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_job_runs_id_seq OWNED BY public.sports_job_runs.id;


--
-- Name: sports_leagues; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_leagues (
    id integer NOT NULL,
    code character varying(20) NOT NULL,
    name character varying(100) NOT NULL,
    level character varying(20) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.sports_leagues OWNER TO dock108;

--
-- Name: sports_leagues_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_leagues_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_leagues_id_seq OWNER TO dock108;

--
-- Name: sports_leagues_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_leagues_id_seq OWNED BY public.sports_leagues.id;


--
-- Name: sports_missing_pbp; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_missing_pbp (
    id integer NOT NULL,
    game_id integer NOT NULL,
    league_id integer NOT NULL,
    status character varying(20) NOT NULL,
    reason character varying(50) NOT NULL,
    detected_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


ALTER TABLE public.sports_missing_pbp OWNER TO dock108;

--
-- Name: sports_missing_pbp_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_missing_pbp_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_missing_pbp_id_seq OWNER TO dock108;

--
-- Name: sports_missing_pbp_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_missing_pbp_id_seq OWNED BY public.sports_missing_pbp.id;


--
-- Name: sports_pbp_snapshots; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_pbp_snapshots (
    id integer NOT NULL,
    game_id integer NOT NULL,
    pipeline_run_id integer,
    scrape_run_id integer,
    snapshot_type character varying(20) NOT NULL,
    source character varying(50),
    play_count integer NOT NULL,
    plays_json jsonb DEFAULT '[]'::jsonb NOT NULL,
    metadata_json jsonb DEFAULT '{}'::jsonb,
    resolution_stats jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.sports_pbp_snapshots OWNER TO dock108;

--
-- Name: COLUMN sports_pbp_snapshots.pipeline_run_id; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_pbp_snapshots.pipeline_run_id IS 'Pipeline run that created this snapshot (null for scrape-time snapshots)';


--
-- Name: COLUMN sports_pbp_snapshots.scrape_run_id; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_pbp_snapshots.scrape_run_id IS 'Scrape run that created this snapshot (for raw PBP)';


--
-- Name: COLUMN sports_pbp_snapshots.snapshot_type; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_pbp_snapshots.snapshot_type IS 'raw, normalized, or resolved';


--
-- Name: COLUMN sports_pbp_snapshots.source; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_pbp_snapshots.source IS 'Data source (e.g., nba_live, nhl_api, sportsref)';


--
-- Name: COLUMN sports_pbp_snapshots.plays_json; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_pbp_snapshots.plays_json IS 'Array of play objects';


--
-- Name: COLUMN sports_pbp_snapshots.metadata_json; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_pbp_snapshots.metadata_json IS 'Snapshot metadata (game timing, resolution stats, etc.)';


--
-- Name: COLUMN sports_pbp_snapshots.resolution_stats; Type: COMMENT; Schema: public; Owner: dock108
--

COMMENT ON COLUMN public.sports_pbp_snapshots.resolution_stats IS 'Stats on team/player/score resolution';


--
-- Name: sports_pbp_snapshots_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_pbp_snapshots_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_pbp_snapshots_id_seq OWNER TO dock108;

--
-- Name: sports_pbp_snapshots_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_pbp_snapshots_id_seq OWNED BY public.sports_pbp_snapshots.id;


--
-- Name: sports_player_boxscores; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_player_boxscores (
    id integer NOT NULL,
    game_id integer NOT NULL,
    team_id integer NOT NULL,
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


ALTER TABLE public.sports_player_boxscores OWNER TO dock108;

--
-- Name: sports_player_boxscores_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_player_boxscores_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_player_boxscores_id_seq OWNER TO dock108;

--
-- Name: sports_player_boxscores_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_player_boxscores_id_seq OWNED BY public.sports_player_boxscores.id;


--
-- Name: sports_players; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_players (
    id integer NOT NULL,
    league_id integer NOT NULL,
    external_id character varying(100) NOT NULL,
    name character varying(200) NOT NULL,
    "position" character varying(10),
    sweater_number integer,
    team_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.sports_players OWNER TO dock108;

--
-- Name: sports_players_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_players_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_players_id_seq OWNER TO dock108;

--
-- Name: sports_players_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_players_id_seq OWNED BY public.sports_players.id;


--
-- Name: sports_scrape_runs; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_scrape_runs (
    id integer NOT NULL,
    scraper_type character varying(50) NOT NULL,
    league_id integer NOT NULL,
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


ALTER TABLE public.sports_scrape_runs OWNER TO dock108;

--
-- Name: sports_scrape_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_scrape_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_scrape_runs_id_seq OWNER TO dock108;

--
-- Name: sports_scrape_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_scrape_runs_id_seq OWNED BY public.sports_scrape_runs.id;


--
-- Name: sports_team_boxscores; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_team_boxscores (
    id integer NOT NULL,
    game_id integer NOT NULL,
    team_id integer NOT NULL,
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


ALTER TABLE public.sports_team_boxscores OWNER TO dock108;

--
-- Name: sports_team_boxscores_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_team_boxscores_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_team_boxscores_id_seq OWNER TO dock108;

--
-- Name: sports_team_boxscores_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_team_boxscores_id_seq OWNED BY public.sports_team_boxscores.id;


--
-- Name: sports_teams; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.sports_teams (
    id integer NOT NULL,
    league_id integer NOT NULL,
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


ALTER TABLE public.sports_teams OWNER TO dock108;

--
-- Name: sports_teams_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.sports_teams_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sports_teams_id_seq OWNER TO dock108;

--
-- Name: sports_teams_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.sports_teams_id_seq OWNED BY public.sports_teams.id;


--
-- Name: team_social_accounts; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.team_social_accounts (
    id integer NOT NULL,
    team_id integer NOT NULL,
    league_id integer NOT NULL,
    platform character varying(20) NOT NULL,
    handle character varying(100) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.team_social_accounts OWNER TO dock108;

--
-- Name: team_social_accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.team_social_accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.team_social_accounts_id_seq OWNER TO dock108;

--
-- Name: team_social_accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.team_social_accounts_id_seq OWNED BY public.team_social_accounts.id;


--
-- Name: team_social_posts; Type: TABLE; Schema: public; Owner: dock108
--

CREATE TABLE public.team_social_posts (
    id integer NOT NULL,
    team_id integer NOT NULL,
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
    game_id integer,
    mapping_status character varying(20) DEFAULT 'unmapped'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    game_phase character varying(20)
);


ALTER TABLE public.team_social_posts OWNER TO dock108;

--
-- Name: team_social_posts_id_seq; Type: SEQUENCE; Schema: public; Owner: dock108
--

CREATE SEQUENCE public.team_social_posts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.team_social_posts_id_seq OWNER TO dock108;

--
-- Name: team_social_posts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: dock108
--

ALTER SEQUENCE public.team_social_posts_id_seq OWNED BY public.team_social_posts.id;


--
-- Name: bulk_story_generation_jobs id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.bulk_story_generation_jobs ALTER COLUMN id SET DEFAULT nextval('public.bulk_story_generation_jobs_id_seq'::regclass);


--
-- Name: compact_mode_thresholds id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.compact_mode_thresholds ALTER COLUMN id SET DEFAULT nextval('public.compact_mode_thresholds_id_seq'::regclass);


--
-- Name: game_reading_positions id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.game_reading_positions ALTER COLUMN id SET DEFAULT nextval('public.game_reading_positions_id_seq'::regclass);


--
-- Name: openai_response_cache id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.openai_response_cache ALTER COLUMN id SET DEFAULT nextval('public.openai_response_cache_id_seq'::regclass);


--
-- Name: social_account_polls id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.social_account_polls ALTER COLUMN id SET DEFAULT nextval('public.social_account_polls_id_seq'::regclass);


--
-- Name: sports_entity_resolutions id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_entity_resolutions ALTER COLUMN id SET DEFAULT nextval('public.sports_entity_resolutions_id_seq'::regclass);


--
-- Name: sports_frontend_payload_versions id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_frontend_payload_versions ALTER COLUMN id SET DEFAULT nextval('public.sports_frontend_payload_versions_id_seq'::regclass);


--
-- Name: sports_game_conflicts id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_conflicts ALTER COLUMN id SET DEFAULT nextval('public.sports_game_conflicts_id_seq'::regclass);


--
-- Name: sports_game_odds id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_odds ALTER COLUMN id SET DEFAULT nextval('public.sports_game_odds_id_seq'::regclass);


--
-- Name: sports_game_pipeline_runs id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_pipeline_runs ALTER COLUMN id SET DEFAULT nextval('public.sports_game_pipeline_runs_id_seq'::regclass);


--
-- Name: sports_game_pipeline_stages id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_pipeline_stages ALTER COLUMN id SET DEFAULT nextval('public.sports_game_pipeline_stages_id_seq'::regclass);


--
-- Name: sports_game_plays id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_plays ALTER COLUMN id SET DEFAULT nextval('public.sports_game_plays_id_seq'::regclass);


--
-- Name: sports_game_stories id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_stories ALTER COLUMN id SET DEFAULT nextval('public.sports_game_stories_id_seq'::regclass);


--
-- Name: sports_game_timeline_artifacts id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_timeline_artifacts ALTER COLUMN id SET DEFAULT nextval('public.sports_game_timeline_artifacts_id_seq'::regclass);


--
-- Name: sports_games id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_games ALTER COLUMN id SET DEFAULT nextval('public.sports_games_id_seq'::regclass);


--
-- Name: sports_job_runs id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_job_runs ALTER COLUMN id SET DEFAULT nextval('public.sports_job_runs_id_seq'::regclass);


--
-- Name: sports_leagues id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_leagues ALTER COLUMN id SET DEFAULT nextval('public.sports_leagues_id_seq'::regclass);


--
-- Name: sports_missing_pbp id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_missing_pbp ALTER COLUMN id SET DEFAULT nextval('public.sports_missing_pbp_id_seq'::regclass);


--
-- Name: sports_pbp_snapshots id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_pbp_snapshots ALTER COLUMN id SET DEFAULT nextval('public.sports_pbp_snapshots_id_seq'::regclass);


--
-- Name: sports_player_boxscores id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_player_boxscores ALTER COLUMN id SET DEFAULT nextval('public.sports_player_boxscores_id_seq'::regclass);


--
-- Name: sports_players id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_players ALTER COLUMN id SET DEFAULT nextval('public.sports_players_id_seq'::regclass);


--
-- Name: sports_scrape_runs id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_scrape_runs ALTER COLUMN id SET DEFAULT nextval('public.sports_scrape_runs_id_seq'::regclass);


--
-- Name: sports_team_boxscores id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_team_boxscores ALTER COLUMN id SET DEFAULT nextval('public.sports_team_boxscores_id_seq'::regclass);


--
-- Name: sports_teams id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_teams ALTER COLUMN id SET DEFAULT nextval('public.sports_teams_id_seq'::regclass);


--
-- Name: team_social_accounts id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.team_social_accounts ALTER COLUMN id SET DEFAULT nextval('public.team_social_accounts_id_seq'::regclass);


--
-- Name: team_social_posts id; Type: DEFAULT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.team_social_posts ALTER COLUMN id SET DEFAULT nextval('public.team_social_posts_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: bulk_story_generation_jobs bulk_story_generation_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.bulk_story_generation_jobs
    ADD CONSTRAINT bulk_story_generation_jobs_pkey PRIMARY KEY (id);


--
-- Name: compact_mode_thresholds compact_mode_thresholds_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.compact_mode_thresholds
    ADD CONSTRAINT compact_mode_thresholds_pkey PRIMARY KEY (id);


--
-- Name: compact_mode_thresholds compact_mode_thresholds_sport_id_key; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.compact_mode_thresholds
    ADD CONSTRAINT compact_mode_thresholds_sport_id_key UNIQUE (sport_id);


--
-- Name: fairbet_game_odds_work fairbet_game_odds_work_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.fairbet_game_odds_work
    ADD CONSTRAINT fairbet_game_odds_work_pkey PRIMARY KEY (game_id, market_key, selection_key, line_value, book);


--
-- Name: game_reading_positions game_reading_positions_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.game_reading_positions
    ADD CONSTRAINT game_reading_positions_pkey PRIMARY KEY (id);


--
-- Name: game_reading_positions game_reading_positions_user_id_game_id_key; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.game_reading_positions
    ADD CONSTRAINT game_reading_positions_user_id_game_id_key UNIQUE (user_id, game_id);


--
-- Name: openai_response_cache openai_response_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.openai_response_cache
    ADD CONSTRAINT openai_response_cache_pkey PRIMARY KEY (id);


--
-- Name: social_account_polls social_account_polls_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.social_account_polls
    ADD CONSTRAINT social_account_polls_pkey PRIMARY KEY (id);


--
-- Name: sports_entity_resolutions sports_entity_resolutions_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_entity_resolutions
    ADD CONSTRAINT sports_entity_resolutions_pkey PRIMARY KEY (id);


--
-- Name: sports_frontend_payload_versions sports_frontend_payload_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_frontend_payload_versions
    ADD CONSTRAINT sports_frontend_payload_versions_pkey PRIMARY KEY (id);


--
-- Name: sports_game_conflicts sports_game_conflicts_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_conflicts
    ADD CONSTRAINT sports_game_conflicts_pkey PRIMARY KEY (id);


--
-- Name: sports_game_odds sports_game_odds_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_odds
    ADD CONSTRAINT sports_game_odds_pkey PRIMARY KEY (id);


--
-- Name: sports_game_pipeline_runs sports_game_pipeline_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_pipeline_runs
    ADD CONSTRAINT sports_game_pipeline_runs_pkey PRIMARY KEY (id);


--
-- Name: sports_game_pipeline_stages sports_game_pipeline_stages_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_pipeline_stages
    ADD CONSTRAINT sports_game_pipeline_stages_pkey PRIMARY KEY (id);


--
-- Name: sports_game_plays sports_game_plays_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_plays
    ADD CONSTRAINT sports_game_plays_pkey PRIMARY KEY (id);


--
-- Name: sports_game_stories sports_game_stories_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_stories
    ADD CONSTRAINT sports_game_stories_pkey PRIMARY KEY (id);


--
-- Name: sports_game_timeline_artifacts sports_game_timeline_artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_timeline_artifacts
    ADD CONSTRAINT sports_game_timeline_artifacts_pkey PRIMARY KEY (id);


--
-- Name: sports_games sports_games_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_games
    ADD CONSTRAINT sports_games_pkey PRIMARY KEY (id);


--
-- Name: sports_job_runs sports_job_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_job_runs
    ADD CONSTRAINT sports_job_runs_pkey PRIMARY KEY (id);


--
-- Name: sports_leagues sports_leagues_code_key; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_leagues
    ADD CONSTRAINT sports_leagues_code_key UNIQUE (code);


--
-- Name: sports_leagues sports_leagues_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_leagues
    ADD CONSTRAINT sports_leagues_pkey PRIMARY KEY (id);


--
-- Name: sports_missing_pbp sports_missing_pbp_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_missing_pbp
    ADD CONSTRAINT sports_missing_pbp_pkey PRIMARY KEY (id);


--
-- Name: sports_pbp_snapshots sports_pbp_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_pbp_snapshots
    ADD CONSTRAINT sports_pbp_snapshots_pkey PRIMARY KEY (id);


--
-- Name: sports_player_boxscores sports_player_boxscores_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_player_boxscores
    ADD CONSTRAINT sports_player_boxscores_pkey PRIMARY KEY (id);


--
-- Name: sports_players sports_players_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_players
    ADD CONSTRAINT sports_players_pkey PRIMARY KEY (id);


--
-- Name: sports_scrape_runs sports_scrape_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_scrape_runs
    ADD CONSTRAINT sports_scrape_runs_pkey PRIMARY KEY (id);


--
-- Name: sports_team_boxscores sports_team_boxscores_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_team_boxscores
    ADD CONSTRAINT sports_team_boxscores_pkey PRIMARY KEY (id);


--
-- Name: sports_teams sports_teams_league_name_unique; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_teams
    ADD CONSTRAINT sports_teams_league_name_unique UNIQUE (league_id, name);


--
-- Name: sports_teams sports_teams_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_teams
    ADD CONSTRAINT sports_teams_pkey PRIMARY KEY (id);


--
-- Name: team_social_accounts team_social_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.team_social_accounts
    ADD CONSTRAINT team_social_accounts_pkey PRIMARY KEY (id);


--
-- Name: team_social_posts team_social_posts_external_post_id_key; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.team_social_posts
    ADD CONSTRAINT team_social_posts_external_post_id_key UNIQUE (external_post_id);


--
-- Name: team_social_posts team_social_posts_pkey; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.team_social_posts
    ADD CONSTRAINT team_social_posts_pkey PRIMARY KEY (id);


--
-- Name: sports_game_conflicts uq_game_conflict; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_conflicts
    ADD CONSTRAINT uq_game_conflict UNIQUE (game_id, conflict_game_id, external_id, source);


--
-- Name: sports_games uq_game_identity; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_games
    ADD CONSTRAINT uq_game_identity UNIQUE (league_id, season, game_date, home_team_id, away_team_id);


--
-- Name: sports_game_stories uq_game_story_version; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_stories
    ADD CONSTRAINT uq_game_story_version UNIQUE (game_id, story_version);


--
-- Name: sports_game_timeline_artifacts uq_game_timeline_artifact_version; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_timeline_artifacts
    ADD CONSTRAINT uq_game_timeline_artifact_version UNIQUE (game_id, sport, timeline_version);


--
-- Name: sports_missing_pbp uq_missing_pbp_game; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_missing_pbp
    ADD CONSTRAINT uq_missing_pbp_game UNIQUE (game_id);


--
-- Name: openai_response_cache uq_openai_cache_game_batch; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.openai_response_cache
    ADD CONSTRAINT uq_openai_cache_game_batch UNIQUE (game_id, batch_key);


--
-- Name: sports_game_pipeline_stages uq_pipeline_stages_run_stage; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_pipeline_stages
    ADD CONSTRAINT uq_pipeline_stages_run_stage UNIQUE (run_id, stage);


--
-- Name: sports_player_boxscores uq_player_boxscore_identity; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_player_boxscores
    ADD CONSTRAINT uq_player_boxscore_identity UNIQUE (game_id, team_id, player_external_ref);


--
-- Name: sports_players uq_player_identity; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_players
    ADD CONSTRAINT uq_player_identity UNIQUE (league_id, external_id);


--
-- Name: social_account_polls uq_social_account_poll_window; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.social_account_polls
    ADD CONSTRAINT uq_social_account_poll_window UNIQUE (platform, handle, window_start, window_end);


--
-- Name: sports_games uq_sports_game_league_source_key; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_games
    ADD CONSTRAINT uq_sports_game_league_source_key UNIQUE (league_id, source_game_key);


--
-- Name: sports_team_boxscores uq_team_boxscore_game_team; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_team_boxscores
    ADD CONSTRAINT uq_team_boxscore_game_team UNIQUE (game_id, team_id);


--
-- Name: team_social_accounts uq_team_social_accounts_platform_handle; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.team_social_accounts
    ADD CONSTRAINT uq_team_social_accounts_platform_handle UNIQUE (platform, handle);


--
-- Name: team_social_accounts uq_team_social_accounts_team_platform; Type: CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.team_social_accounts
    ADD CONSTRAINT uq_team_social_accounts_team_platform UNIQUE (team_id, platform);


--
-- Name: idx_bulk_story_jobs_uuid; Type: INDEX; Schema: public; Owner: dock108
--

CREATE UNIQUE INDEX idx_bulk_story_jobs_uuid ON public.bulk_story_generation_jobs USING btree (job_uuid);


--
-- Name: idx_compact_mode_thresholds_sport_id; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_compact_mode_thresholds_sport_id ON public.compact_mode_thresholds USING btree (sport_id);


--
-- Name: idx_entity_resolutions_entity_type; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_entity_resolutions_entity_type ON public.sports_entity_resolutions USING btree (entity_type);


--
-- Name: idx_entity_resolutions_game; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_entity_resolutions_game ON public.sports_entity_resolutions USING btree (game_id);


--
-- Name: idx_entity_resolutions_game_type; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_entity_resolutions_game_type ON public.sports_entity_resolutions USING btree (game_id, entity_type);


--
-- Name: idx_entity_resolutions_pipeline_run; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_entity_resolutions_pipeline_run ON public.sports_entity_resolutions USING btree (pipeline_run_id);


--
-- Name: idx_entity_resolutions_status; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_entity_resolutions_status ON public.sports_entity_resolutions USING btree (resolution_status);


--
-- Name: idx_fairbet_odds_game; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_fairbet_odds_game ON public.fairbet_game_odds_work USING btree (game_id);


--
-- Name: idx_fairbet_odds_market_category; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_fairbet_odds_market_category ON public.fairbet_game_odds_work USING btree (market_category);


--
-- Name: idx_fairbet_odds_observed; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_fairbet_odds_observed ON public.fairbet_game_odds_work USING btree (observed_at);


--
-- Name: idx_frontend_payload_active; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_frontend_payload_active ON public.sports_frontend_payload_versions USING btree (game_id, is_active) WHERE (is_active = true);


--
-- Name: idx_frontend_payload_game; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_frontend_payload_game ON public.sports_frontend_payload_versions USING btree (game_id);


--
-- Name: idx_frontend_payload_pipeline_run; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_frontend_payload_pipeline_run ON public.sports_frontend_payload_versions USING btree (pipeline_run_id);


--
-- Name: idx_frontend_payload_unique_active; Type: INDEX; Schema: public; Owner: dock108
--

CREATE UNIQUE INDEX idx_frontend_payload_unique_active ON public.sports_frontend_payload_versions USING btree (game_id) WHERE (is_active = true);


--
-- Name: idx_frontend_payload_version; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_frontend_payload_version ON public.sports_frontend_payload_versions USING btree (game_id, version_number);


--
-- Name: idx_game_conflicts_league_created; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_game_conflicts_league_created ON public.sports_game_conflicts USING btree (league_id, created_at);


--
-- Name: idx_game_odds_market_category; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_game_odds_market_category ON public.sports_game_odds USING btree (market_category);


--
-- Name: idx_game_plays_game; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_game_plays_game ON public.sports_game_plays USING btree (game_id);


--
-- Name: idx_game_plays_player; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_game_plays_player ON public.sports_game_plays USING btree (player_id);


--
-- Name: idx_game_plays_type; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_game_plays_type ON public.sports_game_plays USING btree (play_type);


--
-- Name: idx_game_stories_game_id; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_game_stories_game_id ON public.sports_game_stories USING btree (game_id);


--
-- Name: idx_game_stories_generated_at; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_game_stories_generated_at ON public.sports_game_stories USING btree (generated_at);


--
-- Name: idx_game_stories_moments; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_game_stories_moments ON public.sports_game_stories USING btree (game_id) WHERE (moments_json IS NOT NULL);


--
-- Name: idx_game_stories_sport; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_game_stories_sport ON public.sports_game_stories USING btree (sport);


--
-- Name: idx_game_timeline_artifacts_game; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_game_timeline_artifacts_game ON public.sports_game_timeline_artifacts USING btree (game_id);


--
-- Name: idx_game_timeline_artifacts_sport; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_game_timeline_artifacts_sport ON public.sports_game_timeline_artifacts USING btree (sport);


--
-- Name: idx_games_league_season_date; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_games_league_season_date ON public.sports_games USING btree (league_id, season, game_date);


--
-- Name: idx_games_league_status; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_games_league_status ON public.sports_games USING btree (league_id, status);


--
-- Name: idx_games_status_tip_time; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_games_status_tip_time ON public.sports_games USING btree (status, tip_time);


--
-- Name: idx_games_teams; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_games_teams ON public.sports_games USING btree (home_team_id, away_team_id);


--
-- Name: idx_job_runs_phase_started; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_job_runs_phase_started ON public.sports_job_runs USING btree (phase, started_at);


--
-- Name: idx_missing_pbp_league_status; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_missing_pbp_league_status ON public.sports_missing_pbp USING btree (league_id, status);


--
-- Name: idx_openai_cache_game_id; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_openai_cache_game_id ON public.openai_response_cache USING btree (game_id);


--
-- Name: idx_pbp_snapshots_game; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_pbp_snapshots_game ON public.sports_pbp_snapshots USING btree (game_id);


--
-- Name: idx_pbp_snapshots_game_type; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_pbp_snapshots_game_type ON public.sports_pbp_snapshots USING btree (game_id, snapshot_type);


--
-- Name: idx_pbp_snapshots_pipeline_run; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_pbp_snapshots_pipeline_run ON public.sports_pbp_snapshots USING btree (pipeline_run_id);


--
-- Name: idx_pbp_snapshots_type; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_pbp_snapshots_type ON public.sports_pbp_snapshots USING btree (snapshot_type);


--
-- Name: idx_pipeline_runs_created; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_pipeline_runs_created ON public.sports_game_pipeline_runs USING btree (created_at);


--
-- Name: idx_pipeline_runs_game; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_pipeline_runs_game ON public.sports_game_pipeline_runs USING btree (game_id);


--
-- Name: idx_pipeline_runs_status; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_pipeline_runs_status ON public.sports_game_pipeline_runs USING btree (status);


--
-- Name: idx_pipeline_runs_uuid; Type: INDEX; Schema: public; Owner: dock108
--

CREATE UNIQUE INDEX idx_pipeline_runs_uuid ON public.sports_game_pipeline_runs USING btree (run_uuid);


--
-- Name: idx_pipeline_stages_run; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_pipeline_stages_run ON public.sports_game_pipeline_stages USING btree (run_id);


--
-- Name: idx_pipeline_stages_status; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_pipeline_stages_status ON public.sports_game_pipeline_stages USING btree (status);


--
-- Name: idx_players_external_id; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_players_external_id ON public.sports_players USING btree (external_id);


--
-- Name: idx_players_name; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_players_name ON public.sports_players USING btree (name);


--
-- Name: idx_plays_player_ref; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_plays_player_ref ON public.sports_game_plays USING btree (player_ref_id);


--
-- Name: idx_reading_positions_game_id; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_reading_positions_game_id ON public.game_reading_positions USING btree (game_id);


--
-- Name: idx_reading_positions_user_game; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_reading_positions_user_game ON public.game_reading_positions USING btree (user_id, game_id);


--
-- Name: idx_reading_positions_user_id; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_reading_positions_user_id ON public.game_reading_positions USING btree (user_id);


--
-- Name: idx_scrape_runs_created; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_scrape_runs_created ON public.sports_scrape_runs USING btree (created_at);


--
-- Name: idx_scrape_runs_league_status; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_scrape_runs_league_status ON public.sports_scrape_runs USING btree (league_id, status);


--
-- Name: idx_social_account_polls_handle_window; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_social_account_polls_handle_window ON public.social_account_polls USING btree (handle, window_start, window_end);


--
-- Name: idx_social_account_polls_platform; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_social_account_polls_platform ON public.social_account_polls USING btree (platform);


--
-- Name: idx_sports_teams_league_name; Type: INDEX; Schema: public; Owner: dock108
--

CREATE UNIQUE INDEX idx_sports_teams_league_name ON public.sports_teams USING btree (league_id, name);


--
-- Name: idx_sports_teams_league_name_lower; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_sports_teams_league_name_lower ON public.sports_teams USING btree (league_id, lower((name)::text));


--
-- Name: idx_sports_teams_x_handle; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_sports_teams_x_handle ON public.sports_teams USING btree (x_handle) WHERE (x_handle IS NOT NULL);


--
-- Name: idx_team_social_accounts_league; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_team_social_accounts_league ON public.team_social_accounts USING btree (league_id);


--
-- Name: idx_team_social_accounts_team_id; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_team_social_accounts_team_id ON public.team_social_accounts USING btree (team_id);


--
-- Name: idx_team_social_posts_game; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_team_social_posts_game ON public.team_social_posts USING btree (game_id);


--
-- Name: idx_team_social_posts_game_phase; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_team_social_posts_game_phase ON public.team_social_posts USING btree (game_phase);


--
-- Name: idx_team_social_posts_mapping_status; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_team_social_posts_mapping_status ON public.team_social_posts USING btree (mapping_status);


--
-- Name: idx_team_social_posts_posted_at; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_team_social_posts_posted_at ON public.team_social_posts USING btree (posted_at);


--
-- Name: idx_team_social_posts_team; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_team_social_posts_team ON public.team_social_posts USING btree (team_id);


--
-- Name: idx_team_social_posts_team_status; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX idx_team_social_posts_team_status ON public.team_social_posts USING btree (team_id, mapping_status);


--
-- Name: ix_bulk_story_generation_jobs_created_at; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_bulk_story_generation_jobs_created_at ON public.bulk_story_generation_jobs USING btree (created_at);


--
-- Name: ix_bulk_story_generation_jobs_status; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_bulk_story_generation_jobs_status ON public.bulk_story_generation_jobs USING btree (status);


--
-- Name: ix_player_boxscores_game; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_player_boxscores_game ON public.sports_player_boxscores USING btree (game_id);


--
-- Name: ix_sports_game_conflicts_conflict_game_id; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_sports_game_conflicts_conflict_game_id ON public.sports_game_conflicts USING btree (conflict_game_id);


--
-- Name: ix_sports_game_conflicts_game_id; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_sports_game_conflicts_game_id ON public.sports_game_conflicts USING btree (game_id);


--
-- Name: ix_sports_game_conflicts_league_id; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_sports_game_conflicts_league_id ON public.sports_game_conflicts USING btree (league_id);


--
-- Name: ix_sports_games_tip_time; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_sports_games_tip_time ON public.sports_games USING btree (tip_time);


--
-- Name: ix_sports_job_runs_phase; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_sports_job_runs_phase ON public.sports_job_runs USING btree (phase);


--
-- Name: ix_sports_job_runs_status; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_sports_job_runs_status ON public.sports_job_runs USING btree (status);


--
-- Name: ix_sports_leagues_code; Type: INDEX; Schema: public; Owner: dock108
--

CREATE UNIQUE INDEX ix_sports_leagues_code ON public.sports_leagues USING btree (code);


--
-- Name: ix_sports_missing_pbp_game_id; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_sports_missing_pbp_game_id ON public.sports_missing_pbp USING btree (game_id);


--
-- Name: ix_sports_missing_pbp_league_id; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_sports_missing_pbp_league_id ON public.sports_missing_pbp USING btree (league_id);


--
-- Name: ix_sports_teams_league; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_sports_teams_league ON public.sports_teams USING btree (league_id);


--
-- Name: ix_team_boxscores_game; Type: INDEX; Schema: public; Owner: dock108
--

CREATE INDEX ix_team_boxscores_game ON public.sports_team_boxscores USING btree (game_id);


--
-- Name: uq_game_play_index; Type: INDEX; Schema: public; Owner: dock108
--

CREATE UNIQUE INDEX uq_game_play_index ON public.sports_game_plays USING btree (game_id, play_index);


--
-- Name: uq_sports_game_odds_identity; Type: INDEX; Schema: public; Owner: dock108
--

CREATE UNIQUE INDEX uq_sports_game_odds_identity ON public.sports_game_odds USING btree (game_id, book, market_type, side, is_closing_line);


--
-- Name: compact_mode_thresholds compact_mode_thresholds_sport_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.compact_mode_thresholds
    ADD CONSTRAINT compact_mode_thresholds_sport_id_fkey FOREIGN KEY (sport_id) REFERENCES public.sports_leagues(id) ON DELETE CASCADE;


--
-- Name: fairbet_game_odds_work fairbet_game_odds_work_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.fairbet_game_odds_work
    ADD CONSTRAINT fairbet_game_odds_work_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_game_plays fk_plays_player; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_plays
    ADD CONSTRAINT fk_plays_player FOREIGN KEY (player_ref_id) REFERENCES public.sports_players(id);


--
-- Name: game_reading_positions game_reading_positions_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.game_reading_positions
    ADD CONSTRAINT game_reading_positions_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: openai_response_cache openai_response_cache_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.openai_response_cache
    ADD CONSTRAINT openai_response_cache_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_entity_resolutions sports_entity_resolutions_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_entity_resolutions
    ADD CONSTRAINT sports_entity_resolutions_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_entity_resolutions sports_entity_resolutions_pipeline_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_entity_resolutions
    ADD CONSTRAINT sports_entity_resolutions_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.sports_game_pipeline_runs(id) ON DELETE SET NULL;


--
-- Name: sports_frontend_payload_versions sports_frontend_payload_versions_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_frontend_payload_versions
    ADD CONSTRAINT sports_frontend_payload_versions_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_frontend_payload_versions sports_frontend_payload_versions_pipeline_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_frontend_payload_versions
    ADD CONSTRAINT sports_frontend_payload_versions_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.sports_game_pipeline_runs(id) ON DELETE SET NULL;


--
-- Name: sports_game_conflicts sports_game_conflicts_conflict_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_conflicts
    ADD CONSTRAINT sports_game_conflicts_conflict_game_id_fkey FOREIGN KEY (conflict_game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_game_conflicts sports_game_conflicts_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_conflicts
    ADD CONSTRAINT sports_game_conflicts_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_game_conflicts sports_game_conflicts_league_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_conflicts
    ADD CONSTRAINT sports_game_conflicts_league_id_fkey FOREIGN KEY (league_id) REFERENCES public.sports_leagues(id) ON DELETE CASCADE;


--
-- Name: sports_game_odds sports_game_odds_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_odds
    ADD CONSTRAINT sports_game_odds_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_game_pipeline_runs sports_game_pipeline_runs_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_pipeline_runs
    ADD CONSTRAINT sports_game_pipeline_runs_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_game_pipeline_stages sports_game_pipeline_stages_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_pipeline_stages
    ADD CONSTRAINT sports_game_pipeline_stages_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.sports_game_pipeline_runs(id) ON DELETE CASCADE;


--
-- Name: sports_game_plays sports_game_plays_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_plays
    ADD CONSTRAINT sports_game_plays_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_game_plays sports_game_plays_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_plays
    ADD CONSTRAINT sports_game_plays_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.sports_teams(id);


--
-- Name: sports_game_stories sports_game_stories_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_stories
    ADD CONSTRAINT sports_game_stories_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_game_timeline_artifacts sports_game_timeline_artifacts_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_game_timeline_artifacts
    ADD CONSTRAINT sports_game_timeline_artifacts_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_games sports_games_away_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_games
    ADD CONSTRAINT sports_games_away_team_id_fkey FOREIGN KEY (away_team_id) REFERENCES public.sports_teams(id) ON DELETE CASCADE;


--
-- Name: sports_games sports_games_home_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_games
    ADD CONSTRAINT sports_games_home_team_id_fkey FOREIGN KEY (home_team_id) REFERENCES public.sports_teams(id) ON DELETE CASCADE;


--
-- Name: sports_games sports_games_league_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_games
    ADD CONSTRAINT sports_games_league_id_fkey FOREIGN KEY (league_id) REFERENCES public.sports_leagues(id) ON DELETE CASCADE;


--
-- Name: sports_missing_pbp sports_missing_pbp_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_missing_pbp
    ADD CONSTRAINT sports_missing_pbp_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_missing_pbp sports_missing_pbp_league_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_missing_pbp
    ADD CONSTRAINT sports_missing_pbp_league_id_fkey FOREIGN KEY (league_id) REFERENCES public.sports_leagues(id) ON DELETE CASCADE;


--
-- Name: sports_pbp_snapshots sports_pbp_snapshots_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_pbp_snapshots
    ADD CONSTRAINT sports_pbp_snapshots_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_pbp_snapshots sports_pbp_snapshots_pipeline_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_pbp_snapshots
    ADD CONSTRAINT sports_pbp_snapshots_pipeline_run_id_fkey FOREIGN KEY (pipeline_run_id) REFERENCES public.sports_game_pipeline_runs(id) ON DELETE SET NULL;


--
-- Name: sports_pbp_snapshots sports_pbp_snapshots_scrape_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_pbp_snapshots
    ADD CONSTRAINT sports_pbp_snapshots_scrape_run_id_fkey FOREIGN KEY (scrape_run_id) REFERENCES public.sports_scrape_runs(id) ON DELETE SET NULL;


--
-- Name: sports_player_boxscores sports_player_boxscores_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_player_boxscores
    ADD CONSTRAINT sports_player_boxscores_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_player_boxscores sports_player_boxscores_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_player_boxscores
    ADD CONSTRAINT sports_player_boxscores_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.sports_teams(id) ON DELETE CASCADE;


--
-- Name: sports_players sports_players_league_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_players
    ADD CONSTRAINT sports_players_league_id_fkey FOREIGN KEY (league_id) REFERENCES public.sports_leagues(id);


--
-- Name: sports_players sports_players_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_players
    ADD CONSTRAINT sports_players_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.sports_teams(id);


--
-- Name: sports_scrape_runs sports_scrape_runs_league_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_scrape_runs
    ADD CONSTRAINT sports_scrape_runs_league_id_fkey FOREIGN KEY (league_id) REFERENCES public.sports_leagues(id) ON DELETE CASCADE;


--
-- Name: sports_team_boxscores sports_team_boxscores_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_team_boxscores
    ADD CONSTRAINT sports_team_boxscores_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE CASCADE;


--
-- Name: sports_team_boxscores sports_team_boxscores_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_team_boxscores
    ADD CONSTRAINT sports_team_boxscores_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.sports_teams(id) ON DELETE CASCADE;


--
-- Name: sports_teams sports_teams_league_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.sports_teams
    ADD CONSTRAINT sports_teams_league_id_fkey FOREIGN KEY (league_id) REFERENCES public.sports_leagues(id) ON DELETE CASCADE;


--
-- Name: team_social_accounts team_social_accounts_league_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.team_social_accounts
    ADD CONSTRAINT team_social_accounts_league_id_fkey FOREIGN KEY (league_id) REFERENCES public.sports_leagues(id) ON DELETE CASCADE;


--
-- Name: team_social_accounts team_social_accounts_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.team_social_accounts
    ADD CONSTRAINT team_social_accounts_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.sports_teams(id) ON DELETE CASCADE;


--
-- Name: team_social_posts team_social_posts_game_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.team_social_posts
    ADD CONSTRAINT team_social_posts_game_id_fkey FOREIGN KEY (game_id) REFERENCES public.sports_games(id) ON DELETE SET NULL;


--
-- Name: team_social_posts team_social_posts_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: dock108
--

ALTER TABLE ONLY public.team_social_posts
    ADD CONSTRAINT team_social_posts_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.sports_teams(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict GXxoOz2wemdtE4ic8t9JY993WaP9f9qr3gARxEvRjiR2nNXPeprhwwZBfm88ShD

