-- Migration: Seed NBA team X handles
-- Run with: psql "$DATABASE_URL" -f sql/003_seed_nba_x_handles.sql

-- NBA Team X Handles (official accounts)
UPDATE sports_teams SET x_handle = 'ATLHawks' WHERE abbreviation = 'ATL';
UPDATE sports_teams SET x_handle = 'celtics' WHERE abbreviation = 'BOS';
UPDATE sports_teams SET x_handle = 'BrooklynNets' WHERE abbreviation = 'BKN';
UPDATE sports_teams SET x_handle = 'hornets' WHERE abbreviation = 'CHA';
UPDATE sports_teams SET x_handle = 'chicagobulls' WHERE abbreviation = 'CHI';
UPDATE sports_teams SET x_handle = 'cavs' WHERE abbreviation = 'CLE';
UPDATE sports_teams SET x_handle = 'dallasmavs' WHERE abbreviation = 'DAL';
UPDATE sports_teams SET x_handle = 'nuggets' WHERE abbreviation = 'DEN';
UPDATE sports_teams SET x_handle = 'DetroitPistons' WHERE abbreviation = 'DET';
UPDATE sports_teams SET x_handle = 'warriors' WHERE abbreviation = 'GSW';
UPDATE sports_teams SET x_handle = 'HoustonRockets' WHERE abbreviation = 'HOU';
UPDATE sports_teams SET x_handle = 'Pacers' WHERE abbreviation = 'IND';
UPDATE sports_teams SET x_handle = 'LAClippers' WHERE abbreviation = 'LAC';
UPDATE sports_teams SET x_handle = 'Lakers' WHERE abbreviation = 'LAL';
UPDATE sports_teams SET x_handle = 'memgrizz' WHERE abbreviation = 'MEM';
UPDATE sports_teams SET x_handle = 'MiamiHEAT' WHERE abbreviation = 'MIA';
UPDATE sports_teams SET x_handle = 'Bucks' WHERE abbreviation = 'MIL';
UPDATE sports_teams SET x_handle = 'Timberwolves' WHERE abbreviation = 'MIN';
UPDATE sports_teams SET x_handle = 'PelicansNBA' WHERE abbreviation = 'NOP';
UPDATE sports_teams SET x_handle = 'nyknicks' WHERE abbreviation = 'NYK';
UPDATE sports_teams SET x_handle = 'okcthunder' WHERE abbreviation = 'OKC';
UPDATE sports_teams SET x_handle = 'OrlandoMagic' WHERE abbreviation = 'ORL';
UPDATE sports_teams SET x_handle = 'sixers' WHERE abbreviation = 'PHI';
UPDATE sports_teams SET x_handle = 'Suns' WHERE abbreviation = 'PHX';
UPDATE sports_teams SET x_handle = 'trailblazers' WHERE abbreviation = 'POR';
UPDATE sports_teams SET x_handle = 'SacramentoKings' WHERE abbreviation = 'SAC';
UPDATE sports_teams SET x_handle = 'spurs' WHERE abbreviation = 'SAS';
UPDATE sports_teams SET x_handle = 'Raptors' WHERE abbreviation = 'TOR';
UPDATE sports_teams SET x_handle = 'utahjazz' WHERE abbreviation = 'UTA';
UPDATE sports_teams SET x_handle = 'WashWizards' WHERE abbreviation = 'WAS';

-- Verify updates
DO $$
DECLARE
    updated_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO updated_count 
    FROM sports_teams 
    WHERE x_handle IS NOT NULL;
    
    RAISE NOTICE 'Updated % teams with X handles', updated_count;
END $$;

