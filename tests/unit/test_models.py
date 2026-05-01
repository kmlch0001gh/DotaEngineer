"""Unit tests for cafe Pydantic models."""

import pytest

from dotaengineer.models.match import CafeMatch, MatchCreate, MatchPlayer, MatchPlayerCreate
from dotaengineer.models.player import Player, PlayerCreate

# ── Player models ─────────────────────────────────────────────────────────────


def test_player_create_valid():
    p = PlayerCreate(username="testuser", display_name="Test")
    assert p.username == "testuser"
    assert p.display_name == "Test"


def test_player_create_invalid_username():
    with pytest.raises(Exception):
        PlayerCreate(username="a", display_name="Test")  # too short


def test_player_create_valid_display_name():
    p = PlayerCreate(username="test_user", display_name="Mi Nombre")
    assert p.display_name == "Mi Nombre"


def test_player_win_rate():
    p = Player(
        id=1,
        username="test",
        display_name="Test",
        mmr=1000,
        games_played=10,
        wins=6,
        losses=4,
        is_active=True,
        created_at="2026-01-01T00:00:00",
    )
    assert p.win_rate == pytest.approx(0.6)
    assert p.win_rate_pct == "60.0%"


def test_player_win_rate_zero_games():
    p = Player(
        id=1,
        username="test",
        display_name="Test",
        mmr=1000,
        games_played=0,
        wins=0,
        losses=0,
        is_active=True,
        created_at="2026-01-01T00:00:00",
    )
    assert p.win_rate == 0.0


# ── Match models ──────────────────────────────────────────────────────────────


def test_match_player_kda():
    mp = MatchPlayer(
        id=1,
        match_id=1,
        slot=0,
        hero_id=1,
        hero_name="Anti-Mage",
        team="radiant",
        kills=10,
        deaths=3,
        assists=5,
        won=True,
    )
    assert mp.kda == "10/3/5"


def test_match_create_minimum():
    players = [
        MatchPlayerCreate(slot=i, hero_id=i + 1, team="radiant" if i < 5 else "dire")
        for i in range(10)
    ]
    mc = MatchCreate(radiant_win=True, players=players)
    assert mc.radiant_win is True
    assert len(mc.players) == 10


def test_cafe_match_properties():
    players = [
        MatchPlayer(
            id=i,
            match_id=1,
            slot=i,
            hero_id=i + 1,
            hero_name=f"Hero{i}",
            team="radiant" if i < 5 else "dire",
            player_id=1 if i == 0 else None,
            won=True if i < 5 else False,
        )
        for i in range(10)
    ]
    m = CafeMatch(
        id=1,
        played_at="2026-01-01T00:00:00",
        radiant_win=True,
        duration_seconds=2535,
        radiant_score=30,
        dire_score=20,
        players=players,
    )
    assert m.winner == "Radiant"
    assert m.duration_display == "42:15"
    assert len(m.radiant_players) == 5
    assert len(m.dire_players) == 5
    assert m.claimed_count == 1
    assert m.all_claimed is False


def test_cafe_match_no_duration():
    m = CafeMatch(
        id=1,
        played_at="2026-01-01T00:00:00",
        radiant_win=False,
    )
    assert m.duration_display == "--:--"
    assert m.winner == "Dire"
