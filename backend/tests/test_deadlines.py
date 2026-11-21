"""Przykłady wprost z materiału KPRM „liczenie terminów”."""

from datetime import date

from app.services.deadlines import (
    Period,
    add_months,
    criteria_deadline,
    days_deadline,
    is_long_absence,
    merge_absences,
    next_working_day,
    objection_deadline,
    review_due_date,
)


def test_months_same_day():
    # termin 24 miesięcy od 16 marca 2024 upłynie 16 marca 2026
    assert add_months(date(2024, 3, 16), 24) == date(2026, 3, 16)


def test_months_missing_day_end_of_month():
    # 13 miesięcy od 31 stycznia 2024 -> 28 lutego 2025
    assert add_months(date(2024, 1, 31), 13) == date(2025, 2, 28)
    # rok przestępny: 1 miesiąc od 31 stycznia 2024 -> 29 lutego 2024
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_weekend_and_holiday_shift():
    assert next_working_day(date(2026, 11, 21)) == date(2026, 11, 23)  # sobota -> poniedziałek
    assert next_working_day(date(2026, 11, 11)) == date(2026, 11, 12)  # Święto Niepodległości
    assert next_working_day(date(2026, 4, 6)) == date(2026, 4, 7)      # Poniedziałek Wielkanocny 2026
    assert next_working_day(date(2026, 12, 24)) == date(2026, 12, 28)  # Wigilia, święta, weekend


def test_days_exclude_event_day():
    # 7 dni na sprzeciw od zapoznania w poniedziałek 2.11.2026 -> poniedziałek 9.11.2026
    assert days_deadline(date(2026, 11, 2), 7) == date(2026, 11, 9)
    assert objection_deadline(date(2026, 11, 2)) == date(2026, 11, 9)


def test_absences_merge_over_weekend():
    # zwolnienie 5-16.10.2026 (pn-pt) + urlop 19.10-6.11.2026: weekend nie przerywa ciągłości
    merged = merge_absences([Period(date(2026, 10, 5), date(2026, 10, 16)), Period(date(2026, 10, 19), date(2026, 11, 6))])
    assert merged == [Period(date(2026, 10, 5), date(2026, 11, 6))]
    assert is_long_absence(merged[0])


def test_absences_not_merged_with_working_day_gap():
    merged = merge_absences([Period(date(2026, 10, 5), date(2026, 10, 15)), Period(date(2026, 10, 19), date(2026, 11, 6))])
    assert len(merged) == 2  # piątek 16.10 był dniem roboczym
    assert not any(is_long_absence(p) for p in merged)


def test_due_date_extended_by_long_absence():
    start = date(2025, 1, 2)
    assert review_due_date(start) == date(2027, 1, 4)  # 2.01.2027 to sobota
    absence = [Period(date(2025, 3, 3), date(2025, 4, 15))]  # 44 dni > miesiąc
    assert review_due_date(start, absence) == date(2027, 2, 15)  # 2.01.2027 + 44 dni = 15.02.2027 (pn)
    short = [Period(date(2025, 3, 3), date(2025, 3, 20))]
    assert review_due_date(start, short) == date(2027, 1, 4)


def test_criteria_deadline():
    assert criteria_deadline(date(2026, 1, 2)) == date(2026, 2, 2)  # 1.02 to niedziela
    assert criteria_deadline(date(2026, 1, 2), previous_negative=True) == date(2026, 1, 9)
