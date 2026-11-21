from datetime import date, timedelta

from app.analytics.quality_rules import CriterionEntry, NoteInfo, has_critical, run_rules

START, END, TODAY = date(2024, 12, 1), date(2026, 11, 30), date(2026, 11, 20)


def entries(scores, texts=None):
    texts = texts or {}
    return [CriterionEntry(i, f"C{i}", f"Kryterium {i}", s, texts.get(i, "")) for i, s in enumerate(scores, start=1)]


def codes(ws):
    return {w["code"] for w in ws}


def run(es, notes, **kw):
    return run_rules(es, notes, period_start=START, period_end=END, today=TODAY, **kw)


def test_recency_effect_detected():
    notes = [NoteInfo(i, TODAY - timedelta(days=5 * i), "positive", {1}) for i in range(6)]
    notes.append(NoteInfo(99, date(2025, 3, 1), "positive", {1}))
    assert "recency" in codes(run(entries([7]), notes))


def test_no_recency_when_notes_spread():
    notes = [NoteInfo(i, START + timedelta(days=60 * i), "positive", {1}) for i in range(12)]
    assert "recency" not in codes(run(entries([7]), notes))


def test_halo_effect():
    ws = run(entries([9, 9, 9, 9, 9]), [])
    assert "halo" in codes(ws)


def test_missing_score_is_critical():
    ws = run(entries([7, None]), [])
    assert has_critical(ws)


def test_negative_requires_justification():
    ws = run(entries([1, 5, 5]), [])
    assert "negative_without_justification" in codes(ws)
    ws2 = run(entries([1, 5, 5]), [], overall_justification="Konkretne powody...")
    assert "negative_without_justification" not in codes(ws2)


def test_no_evidence_and_inconsistency():
    notes = [NoteInfo(1, date(2025, 5, 1), "negative", {1}), NoteInfo(2, date(2025, 9, 1), "negative", {1}),
             NoteInfo(3, date(2026, 2, 1), "positive", {1})]
    ws = run(entries([9, 5]), notes)
    assert "inconsistent_high" in codes(ws)
    assert any(w["code"] == "no_evidence" and w["criterion_id"] == 2 for w in ws)


def test_vague_and_biased_language():
    ws = run(entries([7, 7], {1: "Pracuje dobrze, bez zastrzeżeń.", 2: "Bardzo sympatyczny i młody, lubiany przez zespół, "
                                                                     "zawsze uśmiechnięty i pomocny w każdej sytuacji."}), [])
    c = codes(ws)
    assert "vague" in c
    assert "biased_language" in c


def test_starannie_is_not_age_bias():
    text = "Starannie przygotował dokumentację przetargu, którą zespół zamówień przyjął bez żadnych poprawek merytorycznych."
    ws = run(entries([7], {1: text}), [])
    assert "biased_language" not in codes(ws)
