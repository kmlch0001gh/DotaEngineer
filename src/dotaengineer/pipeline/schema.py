"""Pipeline database schema — tables for external Dota 2 data."""

PIPELINE_SCHEMA_SQL = """
-- Hero meta stats (winrate/pickrate per bracket)
CREATE TABLE IF NOT EXISTS dota_hero_meta (
    id          SERIAL PRIMARY KEY,
    hero_id     INTEGER NOT NULL,
    hero_name   VARCHAR NOT NULL,
    bracket     VARCHAR NOT NULL,
    picks       INTEGER DEFAULT 0,
    wins        INTEGER DEFAULT 0,
    bans        INTEGER DEFAULT 0,
    win_rate    REAL DEFAULT 0,
    pick_rate   REAL DEFAULT 0,
    ban_rate    REAL DEFAULT 0,
    synced_at   TIMESTAMP DEFAULT now(),
    UNIQUE(hero_id, bracket)
);

-- Hero counters (matchup advantage data)
CREATE TABLE IF NOT EXISTS dota_hero_counters (
    id              SERIAL PRIMARY KEY,
    hero_id         INTEGER NOT NULL,
    counter_hero_id INTEGER NOT NULL,
    advantage       REAL NOT NULL,
    games           INTEGER DEFAULT 0,
    synced_at       TIMESTAMP DEFAULT now(),
    UNIQUE(hero_id, counter_hero_id)
);

-- Popular item builds per hero/bracket/phase
CREATE TABLE IF NOT EXISTS dota_hero_builds (
    id          SERIAL PRIMARY KEY,
    hero_id     INTEGER NOT NULL,
    hero_name   VARCHAR NOT NULL,
    bracket     VARCHAR NOT NULL,
    build_type  VARCHAR NOT NULL,
    items       JSONB NOT NULL,
    synced_at   TIMESTAMP DEFAULT now(),
    UNIQUE(hero_id, bracket, build_type)
);

-- Tracked pro/high-MMR players
CREATE TABLE IF NOT EXISTS dota_tracked_players (
    id          SERIAL PRIMARY KEY,
    account_id  BIGINT NOT NULL UNIQUE,
    name        VARCHAR NOT NULL,
    team        VARCHAR,
    category    VARCHAR NOT NULL,
    region      VARCHAR,
    mmr         INTEGER,
    rank        INTEGER,
    avatar_url  VARCHAR,
    synced_at   TIMESTAMP DEFAULT now()
);

-- Matches from tracked players
CREATE TABLE IF NOT EXISTS dota_tracked_matches (
    id              SERIAL PRIMARY KEY,
    match_id        BIGINT NOT NULL,
    account_id      BIGINT NOT NULL,
    hero_id         INTEGER NOT NULL,
    hero_name       VARCHAR,
    won             BOOLEAN,
    kills           INTEGER,
    deaths          INTEGER,
    assists         INTEGER,
    gpm             INTEGER,
    xpm             INTEGER,
    duration_seconds INTEGER,
    played_at       TIMESTAMP,
    bracket         VARCHAR,
    synced_at       TIMESTAMP DEFAULT now(),
    UNIQUE(match_id, account_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_hero_meta_hero ON dota_hero_meta(hero_id);
CREATE INDEX IF NOT EXISTS idx_hero_meta_bracket ON dota_hero_meta(bracket);
CREATE INDEX IF NOT EXISTS idx_hero_counters_hero ON dota_hero_counters(hero_id);
CREATE INDEX IF NOT EXISTS idx_hero_builds_hero ON dota_hero_builds(hero_id);
CREATE INDEX IF NOT EXISTS idx_tracked_players_cat ON dota_tracked_players(category);
CREATE INDEX IF NOT EXISTS idx_tracked_matches_account
    ON dota_tracked_matches(account_id);
CREATE INDEX IF NOT EXISTS idx_tracked_matches_match
    ON dota_tracked_matches(match_id);
CREATE INDEX IF NOT EXISTS idx_tracked_matches_played
    ON dota_tracked_matches(played_at DESC);
"""
