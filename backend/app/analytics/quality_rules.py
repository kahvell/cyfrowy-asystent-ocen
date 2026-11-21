"""Deterministyczne reguły kontroli jakości oceny (bez LLM).

Czyste funkcje na prostych strukturach -> łatwe do testowania i do obrony na pitchu.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.ai.lexicon import find_bias, find_vague
from app.services.scoring import MAX_ADDITIONAL_CRITERIA, compute_outcome


@dataclass
class NoteInfo:
    id: int
    date: date
    sentiment: str | None
    criterion_ids: set[int] = field(default_factory=set)


@dataclass
class CriterionEntry:
    criterion_id: int
    code: str
    name: str
    score: int | None
    justification: str
    is_additional: bool = False


def _w(code: str, severity: str, title: str, message: str, criterion_id: int | None = None,
       suggestion: str = "", evidence: list[Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,  # critical | warning | info
        "criterion_id": criterion_id,
        "title": title,
        "message": message,
        "suggestion": suggestion,
        "evidence": evidence or [],
        "source": "rule",
    }


def run_rules(
    entries: list[CriterionEntry],
    notes: list[NoteInfo],
    *,
    period_start: date,
    period_end: date,
    today: date,
    overall_justification: str = "",
    recency_days: int = 60,
    recency_threshold: float = 0.5,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    # --- kompletność i zgodność z rozporządzeniem (krytyczne) ---
    missing = [e for e in entries if e.score is None]
    for e in missing:
        out.append(_w("missing_score", "critical", f"Brak oceny cząstkowej: {e.name}",
                      "Każde kryterium obowiązkowe i wybrane dodatkowe musi mieć ocenę cząstkową (§ 11 ust. 1 pkt 1).",
                      e.criterion_id))
    additional = [e for e in entries if e.is_additional]
    if len(additional) > MAX_ADDITIONAL_CRITERIA:
        out.append(_w("too_many_additional", "critical", "Za dużo kryteriów dodatkowych",
                      f"Wybrano {len(additional)}, a rozporządzenie dopuszcza najwyżej 3 (§ 5 ust. 2)."))
    outcome = compute_outcome([e.score for e in entries])
    if outcome and outcome.complete and outcome.result == "negatywna" and not overall_justification.strip():
        out.append(_w("negative_without_justification", "critical", "Ocena negatywna bez uzasadnienia",
                      "Przy ocenie negatywnej uzasadnienie jest obowiązkowe (§ 11 ust. 3).",
                      suggestion="Uzupełnij pole „Uzasadnienie przyznanej oceny”."))

    # --- dowody z dziennika ---
    period_notes = [n for n in notes if period_start <= n.date <= period_end]
    for e in entries:
        if e.score is None:
            continue
        tagged = [n for n in period_notes if e.criterion_id in n.criterion_ids]
        if not tagged:
            out.append(_w("no_evidence", "warning", f"Brak dowodów: {e.name}",
                          "Kryterium ocenione bez żadnej notatki w dzienniku obserwacji z okresu oceny.",
                          e.criterion_id, "Dodaj obserwacje lub opisz w uzasadnieniu konkretne sytuacje."))
            continue
        pos = sum(1 for n in tagged if n.sentiment == "positive")
        neg = sum(1 for n in tagged if n.sentiment == "negative")
        if e.score >= 7 and neg > pos:
            out.append(_w("inconsistent_high", "warning", f"Niespójność: {e.name}",
                          f"Wysoka ocena ({e.score} pkt), ale w notatkach przeważają obserwacje negatywne ({neg} vs {pos}).",
                          e.criterion_id, "Sprawdź, czy ocena odzwierciedla cały okres.", [n.id for n in tagged]))
        if e.score <= 3 and pos > neg:
            out.append(_w("inconsistent_low", "warning", f"Niespójność: {e.name}",
                          f"Niska ocena ({e.score} pkt), ale w notatkach przeważają obserwacje pozytywne ({pos} vs {neg}).",
                          e.criterion_id, "Sprawdź, czy ocena nie jest zaniżona.", [n.id for n in tagged]))

    # --- efekt świeżości ---
    ref = min(period_end, today)
    window_start = ref - timedelta(days=recency_days)
    if len(period_notes) >= 3:
        recent = [n for n in period_notes if n.date >= window_start]
        share = len(recent) / len(period_notes)
        if share > recency_threshold:
            out.append(_w("recency", "warning", "Efekt świeżości",
                          f"{round(share * 100)}% notatek ({len(recent)} z {len(period_notes)}) pochodzi z ostatnich "
                          f"{recency_days} dni okresu oceny, który trwa {(period_end - period_start).days // 30} mies.",
                          suggestion="Przypomnij sobie wcześniejsze miesiące - ocena dotyczy całego okresu."))
    else:
        out.append(_w("few_notes", "info", "Mało obserwacji",
                      f"W dzienniku jest tylko {len(period_notes)} notatek z okresu oceny.",
                      suggestion="Ocena oparta na pamięci jest podatna na zniekształcenia - prowadź dziennik na bieżąco."))

    # --- efekt halo ---
    scored = [e.score for e in entries if e.score is not None]
    if len(scored) >= 4 and len(set(scored)) == 1:
        out.append(_w("halo", "warning", "Efekt halo",
                      f"Wszystkie kryteria mają identyczną ocenę ({scored[0]} pkt).",
                      suggestion="Oceń każde kryterium osobno - mało kto jest równie mocny we wszystkim."))

    # --- jakość tekstu uzasadnień ---
    for e in entries:
        text = e.justification.strip()
        if not text:
            if e.score in (1, 9):
                out.append(_w("extreme_without_text", "info", f"Skrajna ocena bez uzasadnienia: {e.name}",
                              "Ocena skrajna warto poprzeć konkretnymi przykładami.", e.criterion_id))
            continue
        vague = find_vague(text)
        if vague or len(text) < 60:
            out.append(_w("vague", "warning", f"Ogólnikowe uzasadnienie: {e.name}",
                          "Uzasadnienie nie opisuje konkretnych zachowań ani sytuacji."
                          + (f" Ogólniki: „{'”, „'.join(vague)}”." if vague else ""),
                          e.criterion_id, "Podaj przykład: co, kiedy, z jakim efektem.", vague))
        for match, cat, hint in find_bias(text):
            out.append(_w("biased_language", "warning", f"Język do weryfikacji ({cat}): {e.name}",
                          f"Sformułowanie „{match}” może świadczyć o ocenie osoby, a nie zachowań.",
                          e.criterion_id, hint, [match]))
    for match, cat, hint in find_bias(overall_justification):
        out.append(_w("biased_language", "warning", f"Język do weryfikacji ({cat}) w uzasadnieniu oceny",
                      f"Sformułowanie „{match}” może świadczyć o ocenie osoby, a nie zachowań.",
                      suggestion=hint, evidence=[match]))
    return out


def has_critical(warnings: list[dict[str, Any]]) -> bool:
    return any(w["severity"] == "critical" for w in warnings)
