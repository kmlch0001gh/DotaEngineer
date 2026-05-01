"""Integration tests for services with PostgreSQL."""

import os

import psycopg
import pytest

from dotaengineer.db import SCHEMA_SQL, Connection
from dotaengineer.elo import recalculate_all
from dotaengineer.models.match import MatchCreate, MatchPlayerCreate
from dotaengineer.models.player import PlayerCreate
from dotaengineer.services import leaderboard_service, match_service, player_service

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/dotacafe_test")


@pytest.fixture
def con():
    """Fresh PostgreSQL connection with clean tables."""
    try:
        pg = psycopg.connect(DATABASE_URL)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL not available")
    pg.autocommit = False
    c = Connection(pg)
    # Create tables
    pg.execute(SCHEMA_SQL)
    pg.commit()
    # Truncate all tables for clean state
    pg.execute("TRUNCATE mmr_history, match_players, matches, players RESTART IDENTITY CASCADE")
    pg.commit()
    yield c
    pg.rollback()
    pg.close()


def _make_match_create(radiant_win: bool = True) -> MatchCreate:
    players = [
        MatchPlayerCreate(
            slot=i,
            hero_id=i + 1,
            team="radiant" if i < 5 else "dire",
            kills=10 - i,
            deaths=i,
            assists=5,
        )
        for i in range(10)
    ]
    return MatchCreate(radiant_win=radiant_win, players=players)


def test_player_creation(con):
    data = PlayerCreate(username="test", display_name="Test Player")
    pid = player_service.create_player(data, con)
    assert pid > 0

    player = player_service.get_player(pid, con)
    assert player is not None
    assert player.username == "test"
    assert player.mmr == 1000


def test_player_update(con):
    data = PlayerCreate(username="editme", display_name="Old Name")
    pid = player_service.create_player(data, con)

    player_service.update_player(pid, "New Name", "editme", con)
    player = player_service.get_player(pid, con)
    assert player.display_name == "New Name"


def test_match_creation(con):
    mc = _make_match_create()
    mid = match_service.create_match(mc, con)
    assert mid > 0

    match = match_service.get_match(mid, con)
    assert match is not None
    assert match.radiant_win is True
    assert len(match.players) == 10
    assert len(match.radiant_players) == 5
    assert len(match.dire_players) == 5


def test_match_list_pagination(con):
    for _ in range(15):
        match_service.create_match(_make_match_create(), con)

    matches, total = match_service.list_matches(page=1, per_page=10, con=con)
    assert total == 15
    assert len(matches) == 10

    matches2, _ = match_service.list_matches(page=2, per_page=10, con=con)
    assert len(matches2) == 5


def test_claim_slot(con):
    p1 = player_service.create_player(PlayerCreate(username="p1", display_name="Player 1"), con)
    mid = match_service.create_match(_make_match_create(), con)

    assert match_service.claim_slot(mid, 0, p1, con) is True

    match = match_service.get_match(mid, con)
    assert match.players[0].player_id == p1
    assert match.claimed_count == 1


def test_claim_slot_already_claimed(con):
    p1 = player_service.create_player(PlayerCreate(username="p1", display_name="P1"), con)
    p2 = player_service.create_player(PlayerCreate(username="p2", display_name="P2"), con)
    mid = match_service.create_match(_make_match_create(), con)

    assert match_service.claim_slot(mid, 0, p1, con) is True
    assert match_service.claim_slot(mid, 0, p2, con) is False


def test_claim_player_already_in_match(con):
    p1 = player_service.create_player(PlayerCreate(username="p1", display_name="P1"), con)
    mid = match_service.create_match(_make_match_create(), con)

    assert match_service.claim_slot(mid, 0, p1, con) is True
    assert match_service.claim_slot(mid, 1, p1, con) is False


def test_full_claim_triggers_elo(con):
    players = []
    for i in range(10):
        pid = player_service.create_player(
            PlayerCreate(username=f"elo{i}", display_name=f"ELO{i}"), con
        )
        players.append(pid)

    mid = match_service.create_match(_make_match_create(radiant_win=True), con)

    for i in range(10):
        match_service.claim_slot(mid, i, players[i], con)

    radiant_player = player_service.get_player(players[0], con)
    assert radiant_player.mmr > 1000

    dire_player = player_service.get_player(players[5], con)
    assert dire_player.mmr < 1000


def test_elo_recalculate(con):
    players = []
    for i in range(10):
        pid = player_service.create_player(
            PlayerCreate(username=f"recalc{i}", display_name=f"Recalc{i}"), con
        )
        players.append(pid)

    mid = match_service.create_match(_make_match_create(radiant_win=True), con)
    for i in range(10):
        match_service.claim_slot(mid, i, players[i], con)

    p0_mmr = player_service.get_player(players[0], con).mmr

    count = recalculate_all(con)
    assert count == 1

    p0_mmr_after = player_service.get_player(players[0], con).mmr
    assert p0_mmr_after == p0_mmr


def test_leaderboard(con):
    for i in range(3):
        player_service.create_player(PlayerCreate(username=f"lb{i}", display_name=f"LB{i}"), con)

    con.execute(
        "UPDATE players SET mmr=1200, games_played=5, wins=3, losses=2 WHERE username='lb0'"
    )
    con.execute(
        "UPDATE players SET mmr=1100, games_played=3, wins=2, losses=1 WHERE username='lb1'"
    )
    con.execute("UPDATE players SET mmr=900, games_played=4, wins=1, losses=3 WHERE username='lb2'")

    lb = leaderboard_service.get_leaderboard(con, limit=10)
    assert len(lb) == 3
    assert lb[0]["mmr"] == 1200
    assert lb[0]["rank"] == 1
    assert lb[2]["mmr"] == 900
    assert lb[2]["rank"] == 3


def test_delete_match(con):
    mid = match_service.create_match(_make_match_create(), con)
    assert match_service.get_match(mid, con) is not None

    match_service.delete_match(mid, con)
    assert match_service.get_match(mid, con) is None
