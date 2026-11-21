"""Terminy w procesie oceny okresowej - liczone kodem, zgodnie z zasadami obliczania terminów
(materiał KPRM „liczenie terminów”; art. 81 i 83 ustawy o służbie cywilnej; § 5 rozporządzenia).

Wszystkie stałe są w jednym miejscu (`RULES`), żeby zmiana przepisów (np. częstotliwości ocen)
oznaczała zmianę konfiguracji, a nie przebudowę systemu.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

RULES = {
    "review_every_months": 24,          # art. 81 ust. 4
    "criteria_days": 30,                # wyznaczenie kryteriów od początku okresu oceny
    "criteria_days_after_negative": 7,  # ... gdy poprzednia ocena była negatywna
    "objection_days": 7,                # art. 83 ust. 1 - sprzeciw od oceny
    "objection_decision_days": 14,      # art. 83 ust. 3
    "repeat_after_negative_months": 6,  # art. 81 ust. 9
    "min_months_for_change": 6,         # art. 81 ust. 6 i 8 - zmiana terminu / ocena po raz pierwszy
    "promotion_days": 30,               # art. 89 ust. 2 - obligatoryjny kolejny stopień
    "absence_extends_after_months": 1,  # art. 81 ust. 7 - nieobecność dłuższa niż miesiąc
    "reminder_days": 60,                # przypomnienie o zbliżającym się terminie oceny
}


# ------------------------------------------------------------------ dni wolne od pracy


def _easter(year: int) -> date:
    """Wielkanoc (algorytm Meeusa/Jonesa/Butchera)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@lru_cache(maxsize=64)
def polish_holidays(year: int) -> frozenset[date]:
    """Dni ustawowo wolne od pracy (ustawa z 18 stycznia 1951 r.; Wigilia od 2025 r.)."""
    easter = _easter(year)
    days = {
        date(year, 1, 1), date(year, 1, 6), date(year, 5, 1), date(year, 5, 3), date(year, 8, 15),
        date(year, 11, 1), date(year, 11, 11), date(year, 12, 25), date(year, 12, 26),
        easter, easter + timedelta(days=1),       # Wielkanoc, Poniedziałek Wielkanocny
        easter + timedelta(days=49),              # Zielone Świątki (niedziela)
        easter + timedelta(days=60),              # Boże Ciało
    }
    if year >= 2025:
        days.add(date(year, 12, 24))
    return frozenset(days)


def is_working_day(d: date) -> bool:
    return d.weekday() < 5 and d not in polish_holidays(d.year)


def next_working_day(d: date) -> date:
    """Koniec terminu w sobotę lub dzień wolny przesuwa się na najbliższy dzień roboczy."""
    while not is_working_day(d):
        d += timedelta(days=1)
    return d


# ------------------------------------------------------------------ liczenie terminów


def add_months(d: date, months: int) -> date:
    """Termin w miesiącach kończy się w dniu odpowiadającym dniowi początkowemu,
    a gdy takiego dnia nie ma - w ostatnim dniu miesiąca (31.01 + 1 mies. = 28/29.02)."""
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def months_deadline(start: date, months: int) -> date:
    return next_working_day(add_months(start, months))


def days_deadline(event: date, days: int) -> date:
    """Termin w dniach od zdarzenia: dnia zdarzenia nie wlicza się (event + n dni)."""
    return next_working_day(event + timedelta(days=days))


# ------------------------------------------------------------------ nieobecności


@dataclass(frozen=True)
class Period:
    start: date
    end: date  # włącznie

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def merge_absences(periods: list[Period]) -> list[Period]:
    """Łączy następujące po sobie nieobecności usprawiedliwione. Dni wolne od pracy między nimi
    nie przerywają ciągłości (np. zwolnienie pn-pt, weekend, urlop od poniedziałku)."""
    out: list[Period] = []
    for p in sorted(periods, key=lambda p: p.start):
        if out:
            last = out[-1]
            gap = last.end + timedelta(days=1)
            while gap < p.start and not is_working_day(gap):
                gap += timedelta(days=1)
            if gap >= p.start:
                out[-1] = Period(last.start, max(last.end, p.end))
                continue
        out.append(p)
    return out


def is_long_absence(p: Period) -> bool:
    """Nieobecność ciągła „trwająca dłużej niż miesiąc” (art. 81 ust. 7)."""
    return p.end >= add_months(p.start, RULES["absence_extends_after_months"])


def extension_days(periods: list[Period], since: date | None = None, until: date | None = None) -> int:
    """O ile dni przedłuża się termin oceny: suma długości nieobecności dłuższych niż miesiąc."""
    total = 0
    for p in merge_absences(periods):
        if since and p.end < since:
            continue
        if until and p.start > until:
            continue
        if is_long_absence(p):
            total += p.days
    return total


# ------------------------------------------------------------------ terminy procesu oceny


def review_due_date(period_start: date, absences: list[Period] | None = None) -> date:
    """Termin sporządzenia oceny: 24 miesiące od początku okresu (poprzedniej oceny lub nawiązania
    stosunku pracy na czas nieokreślony), przedłużony o długie nieobecności."""
    base = add_months(period_start, RULES["review_every_months"])
    ext = extension_days(absences or [], since=period_start, until=base)
    return next_working_day(base + timedelta(days=ext))


def criteria_deadline(period_start: date, previous_negative: bool = False) -> date:
    days = RULES["criteria_days_after_negative"] if previous_negative else RULES["criteria_days"]
    return days_deadline(period_start, days)


def objection_deadline(acknowledged: date) -> date:
    return days_deadline(acknowledged, RULES["objection_days"])


def repeat_review_date(acknowledged: date) -> date:
    return months_deadline(acknowledged, RULES["repeat_after_negative_months"])


def promotion_deadline(acknowledged: date) -> date:
    return days_deadline(acknowledged, RULES["promotion_days"])


def can_change_due_date(period_start: date, today: date) -> bool:
    """Zmiana terminu oceny (art. 81 ust. 8) - gdy od początku okresu minęło ponad 6 miesięcy."""
    return today > add_months(period_start, RULES["min_months_for_change"])
