"""Zgodność z § 11 rozporządzenia (Dz.U. 2016 poz. 470)."""

import pytest

from app.services.scoring import compute_outcome, overall_level


@pytest.mark.parametrize(
    ("avg", "level"),
    [
        (1, "znacznie poniżej oczekiwań"),
        (2, "znacznie poniżej oczekiwań"),
        (2.01, "poniżej oczekiwań"),
        (4, "poniżej oczekiwań"),
        (4.2, "na poziomie oczekiwań"),
        (6, "na poziomie oczekiwań"),
        (6.5, "powyżej oczekiwań"),
        (8, "powyżej oczekiwań"),
        (8.2, "znacznie powyżej oczekiwań"),
        (9, "znacznie powyżej oczekiwań"),
    ],
)
def test_overall_level_boundaries(avg, level):
    assert overall_level(avg) == level


def test_positive_when_at_expectations():
    out = compute_outcome([5, 5, 7, 5, 3])
    assert out.average == 5.0
    assert out.result == "pozytywna"


def test_negative_when_any_partial_is_lowest_even_with_high_average():
    # § 11 ust. 1 pkt 4: co najmniej jedna ocena „znacznie poniżej oczekiwań” => negatywna
    out = compute_outcome([9, 9, 9, 9, 1])
    assert out.level == "powyżej oczekiwań"
    assert out.result == "negatywna"


def test_average_exactly_four_is_negative():
    out = compute_outcome([3, 5, 3, 5])
    assert out.average == 4
    assert out.result == "negatywna"


def test_incomplete():
    out = compute_outcome([5, None, 7])
    assert out.complete is False
    assert compute_outcome([None, None]) is None
