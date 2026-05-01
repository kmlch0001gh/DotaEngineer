"""PostgreSQL connection management and schema initialization.

Uses psycopg (sync) with a connection pool. Provides a Connection wrapper
that matches the DuckDB-like API (con.execute().fetchone()) so services
don't need to change their query patterns.
"""

from __future__ import annotations

import psycopg
import psycopg.rows
import structlog
from psycopg_pool import ConnectionPool

from dotaengineer.config import settings

log = structlog.get_logger()

_pool: ConnectionPool | None = None

SCHEMA_SQL = """
-- Players
CREATE TABLE IF NOT EXISTS players (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR NOT NULL UNIQUE,
    display_name    VARCHAR NOT NULL,
    pin_hash        VARCHAR,
    mmr             INTEGER DEFAULT 1000,
    games_played    INTEGER DEFAULT 0,
    wins            INTEGER DEFAULT 0,
    losses          INTEGER DEFAULT 0,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMP DEFAULT now(),
    updated_at      TIMESTAMP DEFAULT now()
);

-- Matches
CREATE TABLE IF NOT EXISTS matches (
    id                  SERIAL PRIMARY KEY,
    replay_file         VARCHAR,
    played_at           TIMESTAMP NOT NULL,
    duration_seconds    INTEGER,
    radiant_win         BOOLEAN NOT NULL,
    game_mode           VARCHAR DEFAULT 'captains_mode',
    radiant_score       INTEGER DEFAULT 0,
    dire_score          INTEGER DEFAULT 0,
    source              VARCHAR DEFAULT 'manual',
    notes               VARCHAR,
    created_at          TIMESTAMP DEFAULT now()
);

-- Match Players (10 per match)
CREATE TABLE IF NOT EXISTS match_players (
    id              SERIAL PRIMARY KEY,
    match_id        INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    slot            INTEGER NOT NULL,
    hero_id         INTEGER NOT NULL,
    hero_name       VARCHAR NOT NULL,
    team            VARCHAR NOT NULL,
    player_id       INTEGER REFERENCES players(id),
    kills           INTEGER DEFAULT 0,
    deaths          INTEGER DEFAULT 0,
    assists         INTEGER DEFAULT 0,
    last_hits       INTEGER DEFAULT 0,
    denies          INTEGER DEFAULT 0,
    gpm             INTEGER DEFAULT 0,
    xpm             INTEGER DEFAULT 0,
    net_worth       INTEGER DEFAULT 0,
    hero_damage     INTEGER DEFAULT 0,
    tower_damage    INTEGER DEFAULT 0,
    hero_healing    INTEGER DEFAULT 0,
    level           INTEGER DEFAULT 0,
    items_json      VARCHAR DEFAULT '[]',
    won             BOOLEAN NOT NULL,
    UNIQUE(match_id, slot)
);

-- MMR History
CREATE TABLE IF NOT EXISTS mmr_history (
    id              SERIAL PRIMARY KEY,
    player_id       INTEGER NOT NULL REFERENCES players(id),
    match_id        INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    mmr_before      INTEGER NOT NULL,
    mmr_after       INTEGER NOT NULL,
    mmr_change      INTEGER NOT NULL,
    created_at      TIMESTAMP DEFAULT now(),
    UNIQUE(player_id, match_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_match_players_match ON match_players(match_id);
CREATE INDEX IF NOT EXISTS idx_match_players_player ON match_players(player_id);
CREATE INDEX IF NOT EXISTS idx_match_players_hero ON match_players(hero_id);
CREATE INDEX IF NOT EXISTS idx_mmr_history_player ON mmr_history(player_id);
CREATE INDEX IF NOT EXISTS idx_matches_played_at ON matches(played_at DESC);
"""


class Connection:
    """Thin wrapper around psycopg.Connection that provides a DuckDB-like API.

    This lets all service code keep using `con.execute(sql, params).fetchone()`
    without knowing whether the backend is DuckDB or PostgreSQL.
    """

    def __init__(self, pg_conn: psycopg.Connection):
        self._conn = pg_conn
        self._cursor: psycopg.Cursor | None = None

    def execute(self, sql: str, params: list | tuple | None = None) -> Connection:
        # Convert DuckDB-style ? placeholders to psycopg %s placeholders
        sql = sql.replace("?", "%s")
        if self._cursor:
            self._cursor.close()
        self._cursor = self._conn.execute(sql, params)
        return self

    def fetchone(self) -> tuple | None:
        if self._cursor is None:
            return None
        return self._cursor.fetchone()

    def fetchall(self) -> list[tuple]:
        if self._cursor is None:
            return []
        return self._cursor.fetchall()

    @property
    def description(self):
        if self._cursor is None:
            return []
        return self._cursor.description

    def commit(self):
        self._conn.commit()

    def close(self):
        if self._cursor:
            self._cursor.close()
        self._conn.commit()


def get_pool() -> ConnectionPool:
    """Get or create the connection pool (singleton)."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=5,
            open=True,
        )
    return _pool


def get_connection() -> Connection:
    """Get a connection from the pool, wrapped in our DuckDB-compatible API."""
    pool = get_pool()
    pg_conn = pool.getconn()
    pg_conn.autocommit = False
    return Connection(pg_conn)


def release_connection(con: Connection) -> None:
    """Return a connection to the pool."""
    con.close()
    get_pool().putconn(con._conn)


def init_schema() -> None:
    """Create all tables if they don't exist."""
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(SCHEMA_SQL)
        conn.commit()
    log.info("database_schema_initialized", url=_mask_url(settings.database_url))


def _mask_url(url: str) -> str:
    """Mask password in database URL for logging."""
    if "@" in url:
        pre, post = url.split("@", 1)
        if ":" in pre:
            scheme_user = pre.rsplit(":", 1)[0]
            return f"{scheme_user}:****@{post}"
    return url
