"""Unit tests for Pydantic models."""

import pytest
from dotaengineer.models.match import Match, PlayerSlot


def make_player(slot: int, hero_id: int = 1, kills: int = 5, deaths: int = 2) -> PlayerSlot:
    return PlayerSlot(player_slot=slot, hero_id=hero_id, kills=kills, deaths=deaths, assists=3)


def test_player_is_radiant():
    p = make_player(slot=0)
    assert p.is_radiant is True


def test_player_is_dire():
    p = make_player(slot=128)
    assert p.is_radiant is False


def test_player_kda():
    p = make_player(slot=0, kills=5, deaths=2)
    assert p.kda == pytest.approx((5 + 3) / 2)


def test_player_kda_zero_deaths():
    p = make_player(slot=0, kills=10, deaths=0)
    assert p.kda == pytest.approx(13.0)  # (10+3)/1


def test_match_duration_minutes():
    m = Match(
        match_id=1,
        start_time=0,
        duration=2400,
        radiant_win=True,
        game_mode=22,
        lobby_type=7,
    )
    assert m.duration_minutes == pytest.approx(40.0)


def test_match_get_player_found():
    p = make_player(slot=0, hero_id=10)
    p.account_id = 12345
    m = Match(
        match_id=1,
        start_time=0,
        duration=2400,
        radiant_win=True,
        game_mode=22,
        lobby_type=7,
        players=[p],
    )
    found = m.get_player(12345)
    assert found is not None
    assert found.hero_id == 10


def test_match_get_player_not_found():
    m = Match(
        match_id=1,
        start_time=0,
        duration=2400,
        radiant_win=True,
        game_mode=22,
        lobby_type=7,
    )
    assert m.get_player(99999) is None
