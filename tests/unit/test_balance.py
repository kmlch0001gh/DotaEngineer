"""Unit tests for auto-balance algorithm."""

import os

import psycopg
import pytest

from dotaengineer.db import SCHEMA_SQL, Connection
from dotaengineer.services.balance_service import balance_teams

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/dotacafe_test")


@pytest.fixture
def con():
    """PostgreSQL connection with test players."""
    try:
        pg = psycopg.connect(DATABASE_URL)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL not available")
    pg.autocommit = False
    pg.execute(SCHEMA_SQL)
    pg.commit()
    pg.execute("TRUNCATE mmr_history, match_players, matches, players RESTART IDENTITY CASCADE")
    pg.commit()
    pg.execute("INSERT INTO players (username,display_name,mmr) VALUES ('p1','Player1',1400)")
    pg.execute("INSERT INTO players (username,display_name,mmr) VALUES ('p2','Player2',1200)")
    pg.execute("INSERT INTO players (username,display_name,mmr) VALUES ('p3','Player3',1100)")
    pg.execute("INSERT INTO players (username,display_name,mmr) VALUES ('p4','Player4',1000)")
    pg.execute("INSERT INTO players (username,display_name,mmr) VALUES ('p5','Player5',900)")
    pg.execute("INSERT INTO players (username,display_name,mmr) VALUES ('p6','Player6',800)")
    pg.commit()
    c = Connection(pg)
    yield c
    pg.rollback()
    pg.close()


def test_balance_two_players(con):
    result = balance_teams([1, 2], con)
    assert result is not None
    assert len(result.team_a.players) == 1
    assert len(result.team_b.players) == 1


def test_balance_four_players(con):
    result = balance_teams([1, 2, 3, 4], con)
    assert result is not None
    assert len(result.team_a.players) == 2
    assert len(result.team_b.players) == 2
    assert result.mmr_difference <= 200


def test_balance_six_players(con):
    result = balance_teams([1, 2, 3, 4, 5, 6], con)
    assert result is not None
    assert len(result.team_a.players) == 3
    assert len(result.team_b.players) == 3
    assert result.mmr_difference <= 200


def test_balance_win_probability_sums_to_100(con):
    result = balance_teams([1, 2, 3, 4], con)
    assert result is not None
    assert result.predicted_win_a + result.predicted_win_b == pytest.approx(100.0)


def test_balance_too_few_players(con):
    result = balance_teams([1], con)
    assert result is None


def test_balance_no_players(con):
    result = balance_teams([], con)
    assert result is None
