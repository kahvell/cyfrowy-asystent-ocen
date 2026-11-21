"""Wirtualny HR partner: sygnały do rozmowy o kondycji pracownika i kultura doceniania.

Zasady (ważne przy systemie wysokiego ryzyka z AI Act i danych o zdrowiu z RODO):
- reguły są jawne i deterministyczne; każdy sygnał wskazuje notatki, z których wynika,
- sygnał to podpowiedź do rozmowy wspierającej, a NIE diagnoza ani element oceny okresowej,
- nie wnioskujemy o emocjach ani o zdrowiu; z nieobecności bierzemy tylko łączny czas, bez rodzaju,
- sygnały widzi wyłącznie bezpośredni przełożony; HR nie ma do nich dostępu indywidualnie.
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.services.deadlines import Period, merge_absences

RECENT_DAYS = 90

OVERLOAD = re.compile(r"po godzinach|nadgodzin|w weekend|do późna|przeciąż|nie nadąża|nie wyrabia|dwa obszary|"
                      r"kilka projektów naraz|jednocześnie prowadzi|zaległości|przejęł[aio]|przejął", re.I)
DISENGAGE = re.compile(r"wycofan|zamknięt[ay] w sobie|brak zaangażowania|nie zgłasza|unika|frustr|zniechęc|"
                       r"demotyw|wypal|konflikt|rezygn|zmęcz", re.I)
SCOPE = re.compile(r"przejęł[aio]|przejął|nowe obowiązki|zmiana zakresu|dodatkowo odpowiada|po odejściu", re.I)

ACTIONS = {
    "overload": [
        "Rozmowa wspierająca 1:1: zapytaj o obciążenie i priorytety (bez oceniania).",
        "Przegląd zadań: co można odłożyć, przekazać lub uprościć - zmiana priorytetów na najbliższe 4 tygodnie.",
        "Tymczasowe wsparcie zespołu lub podział obowiązków przejętych po innej osobie.",
        "Uzgodnij realne terminy i jasno komunikuj je odbiorcom.",
    ],
    "disengagement": [
        "Rozmowa o motywacji: co daje satysfakcję, co przeszkadza - słuchaj, nie oceniaj.",
        "Zaproponuj zadanie rozwojowe zgodne z zainteresowaniami albo mentoring.",
        "Rozważ szkolenie z zarządzania stresem lub przeciwdziałania wypaleniu (katalog szkoleń).",
        "Ustal krótki cykl informacji zwrotnej (np. co 2 tygodnie przez 2 miesiące).",
    ],
    "performance_drop": [
        "Rozmowa o przyczynach, zanim pojawi się problem w ocenie - najpierw zapytaj o kontekst.",
        "Wspólnie ustal 1-2 konkretne cele na najbliższy miesiąc i formę wsparcia.",
    ],
    "return": [
        "Rozmowa po powrocie: co się zmieniło, czego potrzebuje na start.",
        "Stopniowe przywracanie zadań i aktualizacja wiedzy o zmianach w zespole.",
        "Sprawdź, czy termin oceny został przesunięty o czas nieobecności (art. 81 ust. 7).",
    ],
    "feedback_gap": [
        "Krótka rozmowa o bieżącej pracy i oczekiwaniach (standard informacji zwrotnej w służbie cywilnej).",
        "Zapisz w dzienniku choć jedną obserwację - ocena nie powinna opierać się na pamięci.",
    ],
    "scope_change": [
        "Zaktualizuj opis stanowiska, jeśli zmiana zakresu jest trwała.",
        "Przy istotnej zmianie zakresu obowiązków sprawdź, czy nie jest wymagana ocena (art. 81 ust. 6).",
    ],
}


@dataclass
class NoteIn:
    id: int
    date: date
    text: str
    sentiment: str | None
    source: str = "manager"


@dataclass
class Signal:
    code: str
    severity: str  # high | medium | info
    title: str
    message: str
    evidence: list[int] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


def analyze(notes: list[NoteIn], absences: list[Period], today: date) -> dict:
    recent_from = today - timedelta(days=RECENT_DAYS)
    recent = [n for n in notes if n.date >= recent_from]
    earlier = [n for n in notes if n.date < recent_from]
    signals: list[Signal] = []

    over = [n for n in recent if OVERLOAD.search(n.text)]
    if over:
        signals.append(Signal("overload", "high" if len(over) >= 2 else "medium", "Sygnały przeciążenia",
                              f"{len(over)} obserwacje z ostatnich {RECENT_DAYS} dni wskazują na nadmiar zadań lub pracę "
                              "po godzinach.", [n.id for n in over], ACTIONS["overload"]))

    dis = [n for n in recent if DISENGAGE.search(n.text)]
    if dis:
        signals.append(Signal("disengagement", "medium", "Możliwy spadek zaangażowania",
                              "W obserwacjach pojawiają się opisy wycofania lub frustracji. To sygnał do rozmowy, "
                              "nie wniosek o przyczynach.", [n.id for n in dis], ACTIONS["disengagement"]))

    neg_recent = [n for n in recent if n.sentiment == "negative"]
    share_recent = len(neg_recent) / len(recent) if recent else 0
    share_before = sum(1 for n in earlier if n.sentiment == "negative") / len(earlier) if earlier else 0
    if len(neg_recent) >= 2 and share_recent >= 0.5 and share_recent - share_before >= 0.25:
        signals.append(Signal("performance_drop", "high" if over else "medium", "Zmiana trendu w obserwacjach",
                              f"Ostatnio {round(share_recent * 100)}% obserwacji to trudności (wcześniej "
                              f"{round(share_before * 100)}%). Warto porozmawiać, zanim przełoży się to na ocenę.",
                              [n.id for n in neg_recent], ACTIONS["performance_drop"]))

    scope = [n for n in notes if SCOPE.search(n.text) and n.date >= today - timedelta(days=180)]
    if scope:
        signals.append(Signal("scope_change", "info", "Zmiana zakresu zadań",
                              "Pracownik przejął nowe obowiązki - sprawdź, czy zakres pracy jest realny.",
                              [n.id for n in scope], ACTIONS["scope_change"]))

    long_abs = [p for p in merge_absences(absences) if p.days > 30 and p.end >= today - timedelta(days=365)]
    if long_abs:
        p = long_abs[-1]
        signals.append(Signal("return", "info", "Powrót po dłuższej nieobecności",
                              f"Nieobecność {p.days} dni (do {p.end.isoformat()}). Zaplanuj rozmowę po powrocie.",
                              [], ACTIONS["return"]))

    manager_notes = [n for n in notes if n.source == "manager"]
    last = max((n.date for n in manager_notes), default=None)
    if last is None or (today - last).days > RECENT_DAYS:
        signals.append(Signal("feedback_gap", "medium", "Brak bieżącej informacji zwrotnej",
                              "Brak obserwacji przełożonego od ponad 3 miesięcy." if last else "Brak obserwacji przełożonego.",
                              [], ACTIONS["feedback_gap"]))

    # kultura doceniania: świeże sukcesy, które warto docenić
    praise = [n for n in notes if n.sentiment == "positive" and n.date >= today - timedelta(days=30)]
    appreciation = [{"note_id": n.id, "date": n.date.isoformat(), "text": n.text,
                     "suggestion": "Doceń to wprost i konkretnie: co zrobił(a), jaki był efekt, dlaczego to ważne."}
                    for n in sorted(praise, key=lambda n: n.date, reverse=True)[:3]]
    long_no_praise = not any(n.sentiment == "positive" for n in notes if n.date >= today - timedelta(days=120))
    if long_no_praise and notes:
        signals.append(Signal("no_recognition", "info", "Dawno nie było docenienia",
                              "W ostatnich 4 miesiącach brak pozytywnych obserwacji. Poszukaj sytuacji, które warto docenić.",
                              [], ["Przy najbliższej okazji zwróć uwagę na to, co działa, i powiedz o tym."]))

    order = {"high": 0, "medium": 1, "info": 2}
    signals.sort(key=lambda s: order[s.severity])
    risk = "high" if any(s.severity == "high" for s in signals) else "medium" if any(
        s.severity == "medium" for s in signals) else "low"
    return {"risk": risk, "signals": [s.__dict__ for s in signals], "appreciation": appreciation}
