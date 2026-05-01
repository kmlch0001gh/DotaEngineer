"""Unit tests for ELO calculation."""

import pytest

from dotaengineer.elo import expected_score, k_factor


def test_expected_score_equal():
    assert expected_score(1000, 1000) == pytest.approx(0.5)


def test_expected_score_higher_wins():
    score = expected_score(1200, 1000)
    assert score > 0.5
    assert score == pytest.approx(0.76, abs=0.01)


def test_expected_score_lower_loses():
    score = expected_score(800, 1000)
    assert score < 0.5
    assert score == pytest.approx(0.24, abs=0.01)


def test_expected_score_symmetric():
    """E(A vs B) + E(B vs A) = 1.0"""
    e_ab = expected_score(1100, 900)
    e_ba = expected_score(900, 1100)
    assert e_ab + e_ba == pytest.approx(1.0)


def test_k_factor_calibration():
    """New players (< 10 games) get higher K."""
    assert k_factor(0) == 48
    assert k_factor(5) == 48
    assert k_factor(9) == 48


def test_k_factor_normal():
    """After calibration, K drops to standard."""
    assert k_factor(10) == 32
    assert k_factor(100) == 32
