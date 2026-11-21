"""Pipeline'y AI. Każdy ma:
- schemat wyjścia (Pydantic),
- prompt (.j2, wersjonowany),
- heurystykę (tryb bez modelu / fallback),
- walidację po stronie kodu (np. odrzucenie źródeł spoza przekazanych notatek).
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.ai.lexicon import match_criteria, sentiment_of
from app.ai.service import render_prompt, run_structured

Score = Literal[1, 3, 5, 7, 9]
_MONTHS = ["W styczniu", "W lutym", "W marcu", "W kwietniu", "W maju", "W czerwcu", "W lipcu", "W sierpniu",
           "We wrześniu", "W październiku", "W listopadzie", "W grudniu"]


@dataclass
class CriterionCtx:
    id: int
    code: str
    name: str
    indicators: list[str]
    keywords: list[str]


@dataclass
class NoteCtx:
    id: int
    date: date
    text: str
    sentiment: str | None
    source: str = "manager"  # manager | self


@dataclass
class PipelineResult:
    data: BaseModel
    model: str
    prompt_version: str


# ---------------------------------------------------------------- classify_note


class CriterionTag(BaseModel):
    criterion_code: str
    confidence: float = Field(ge=0, le=1)


class ClassifyResult(BaseModel):
    criteria: list[CriterionTag] = Field(default_factory=list, max_length=5)
    sentiment: Literal["positive", "neutral", "negative"] = "neutral"


def classify_note(text: str, note_date: date, criteria: list[CriterionCtx], people: list[str]) -> PipelineResult:
    prompt, version = render_prompt("classify_note", criteria=criteria, note_text=text, note_date=note_date)

    def heuristic() -> ClassifyResult:
        tags = match_criteria(text, {c.code: c.keywords for c in criteria})
        return ClassifyResult(
            criteria=[CriterionTag(criterion_code=c, confidence=round(conf, 2)) for c, conf in tags],
            sentiment=sentiment_of(text),
        )

    data, model = run_structured(prompt, ClassifyResult, heuristic, people)
    valid = {c.code for c in criteria}
    data.criteria = [t for t in data.criteria if t.criterion_code in valid][:3]
    return PipelineResult(data, model, version)


# ---------------------------------------------------------------- draft_justification


class JustificationSentence(BaseModel):
    text: str
    source_note_ids: list[int] = Field(default_factory=list)


class DraftResult(BaseModel):
    sentences: list[JustificationSentence]
    proposed_score: Score | None = None
    rationale: str = ""


def score_from_notes(notes: list[NoteCtx]) -> int | None:
    pos = sum(1 for n in notes if n.sentiment == "positive")
    neg = sum(1 for n in notes if n.sentiment == "negative")
    if pos + neg == 0:
        return 5 if notes else None
    ratio = pos / (pos + neg)
    if ratio >= 0.9 and len(notes) >= 6:
        return 9
    if ratio >= 0.75:
        return 7
    if ratio >= 0.45:
        return 5
    if ratio >= 0.2:
        return 3
    return 1


def draft_justification(
    criterion: CriterionCtx, notes: list[NoteCtx], *, employee_name: str, position: str,
    period_start: date, period_end: date,
) -> PipelineResult:
    prompt, version = render_prompt(
        "draft_justification", criterion=criterion, notes=notes, employee_name=employee_name, position=position,
        period_start=period_start, period_end=period_end,
    )

    def heuristic() -> DraftResult:
        positives = [n for n in notes if n.sentiment != "negative"]
        negatives = [n for n in notes if n.sentiment == "negative"]
        sentences = []
        for n in positives[:4]:
            sentences.append(JustificationSentence(
                text=f"{_MONTHS[n.date.month - 1]} {n.date.year} r."
                     + (" (wg wpisu pracownika)" if n.source == "self" else "") + f": {n.text.rstrip('.')}.",
                source_note_ids=[n.id]))
        if negatives:
            sentences.append(JustificationSentence(
                text="Obszar do poprawy: " + "; ".join(n.text.rstrip(".") for n in negatives[:2]) + ".",
                source_note_ids=[n.id for n in negatives[:2]]))
        score = score_from_notes(notes)
        pos, neg = len(positives), len(negatives)
        return DraftResult(
            sentences=sentences, proposed_score=score,
            rationale=f"Na podstawie {len(notes)} notatek z całego okresu ({pos} pozytywnych/neutralnych, {neg} negatywnych).",
        )

    data, model = run_structured(prompt, DraftResult, heuristic, [employee_name])
    # Śledzalność: tylko identyfikatory notatek, które faktycznie przekazaliśmy modelowi.
    allowed = {n.id for n in notes}
    for s in data.sentences:
        s.source_note_ids = [i for i in s.source_note_ids if i in allowed]
        # źródła pokazuje UI jako klikalne #id - usuwamy dopiski modelu typu "(id=12)", "[#3, #7]"
        s.text = _INLINE_REF.sub("", s.text).strip()
    return PipelineResult(data, model, version)


_REF = r"(?:(?:id|notatk[aiy])\s*[=:]?\s*#?|#)\d+"
_INLINE_REF = re.compile(rf"\s*[\(\[]\s*{_REF}(?:\s*[,;]\s*{_REF})*\s*[\)\]]", re.I)


# ---------------------------------------------------------------- quality_check (część językowa)


class LLMIssue(BaseModel):
    criterion_code: str | None = None
    kind: Literal["vague", "biased", "inconsistent"]
    excerpt: str = ""
    explanation: str
    suggestion: str = ""


class LLMQualityResult(BaseModel):
    issues: list[LLMIssue] = Field(default_factory=list)


def quality_check_llm(entries: list[dict], overall_justification: str, people: list[str]) -> PipelineResult:
    prompt, version = render_prompt("quality_check", entries=entries, overall_justification=overall_justification)
    # heurystyka = pusto; reguły słownikowe i tak działają zawsze (analytics/quality_rules.py)
    data, model = run_structured(prompt, LLMQualityResult, lambda: LLMQualityResult(), people)
    return PipelineResult(data, model, version)


# ---------------------------------------------------------------- compare_self


class CompareLLM(BaseModel):
    questions: list[str]
    summary: str = ""


def compare_self(rows: list[dict], self_summary: str, people: list[str]) -> PipelineResult:
    prompt, version = render_prompt("compare_self", rows=rows, self_summary=self_summary)

    def heuristic() -> CompareLLM:
        diffs = sorted(
            [r for r in rows if r["manager_score"] and r["self_score"]],
            key=lambda r: -abs(r["manager_score"] - r["self_score"]),
        )
        qs = []
        for r in diffs[:4]:
            d = r["self_score"] - r["manager_score"]
            if d >= 2:
                qs.append(f"„{r['name']}”: oceniasz się wyżej niż ja. Jakie sytuacje z tego okresu najlepiej to pokazują?")
            elif d <= -2:
                qs.append(f"„{r['name']}”: widzę tu więcej Twoich mocnych stron niż Ty. Co sprawia, że oceniasz się ostrożniej?")
        qs.append("Które zadania z ostatniego okresu dały Ci najwięcej satysfakcji, a które były najtrudniejsze?")
        qs.append("W jakim kierunku chcesz się rozwijać i jakiego wsparcia ode mnie potrzebujesz?")
        big = [r["name"] for r in diffs if abs(r["manager_score"] - r["self_score"]) >= 4]
        summary = (f"Największe rozbieżności: {', '.join(big)}." if big else "Brak dużych rozbieżności między oceną a samooceną.")
        return CompareLLM(questions=qs, summary=summary)

    data, model = run_structured(prompt, CompareLLM, heuristic, people)
    return PipelineResult(data, model, version)


# ---------------------------------------------------------------- generate_ipr


class IPRGoalDraft(BaseModel):
    criterion_code: str
    goal: str
    actions: str
    success_measure: str
    deadline_months: int = Field(ge=1, le=24)
    training_code: str | None = None


class IPRDraft(BaseModel):
    summary: str
    goals: list[IPRGoalDraft]


_ACTIONS = {
    "default": "Zadanie rozwojowe przydzielone przez przełożonego; comiesięczna krótka rozmowa o postępach.",
}


def generate_ipr(
    focus: list[dict], trainings: list[dict], legal: list[dict], *, employee_name: str, position: str,
    position_description: str,
) -> PipelineResult:
    prompt, version = render_prompt(
        "generate_ipr", focus=focus, trainings=trainings, legal=legal, employee_name=employee_name,
        position=position, position_description=position_description,
    )

    def heuristic() -> IPRDraft:
        goals = []
        for c in focus:
            training = next((t for t in trainings if c["code"] in t["criterion_codes"]), None)
            strength = c["score"] is not None and c["score"] >= 7
            goals.append(IPRGoalDraft(
                criterion_code=c["code"],
                goal=(f"Wykorzystanie mocnej strony „{c['name']}” do wspierania zespołu" if strength
                      else f"Podniesienie poziomu w kryterium „{c['name']}” do co najmniej „na poziomie oczekiwań”"),
                actions=(f"{'Udział w szkoleniu „' + training['title'] + '”; ' if training else ''}"
                         f"{_ACTIONS['default']} Mentoring z doświadczoną osobą z zespołu."),
                success_measure="Co najmniej 3 obserwacje w dzienniku potwierdzające postęp; omówienie na rozmowie śródokresowej.",
                deadline_months=6 if not strength else 12,
                training_code=training["code"] if training else None,
            ))
        names = ", ".join(c["name"] for c in focus)
        return IPRDraft(summary=f"Kierunki rozwoju na kolejny okres: {names}. Program łączy szkolenia z zadaniami w miejscu pracy.",
                        goals=goals)

    data, model = run_structured(prompt, IPRDraft, heuristic, [employee_name])
    valid_codes = {t["code"] for t in trainings}
    focus_codes = {c["code"] for c in focus}
    data.goals = [g for g in data.goals if g.criterion_code in focus_codes] or data.goals
    for g in data.goals:
        if g.training_code not in valid_codes:
            g.training_code = None
    return PipelineResult(data, model, version)


# ---------------------------------------------------------------- legal_qa


class LegalAnswer(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)


def legal_qa(question: str, chunks: list[dict]) -> PipelineResult:
    prompt, version = render_prompt("legal_qa", question=question, chunks=chunks)

    def heuristic() -> LegalAnswer:
        if not chunks:
            return LegalAnswer(answer="Nie znalazłem przepisu odpowiadającego na to pytanie.", citations=[])
        top = chunks[:2]
        return LegalAnswer(
            answer="Najbardziej pasujące przepisy (tryb bez modelu językowego - cytuję wprost):\n\n"
            + "\n\n".join(f"{c['ref']}: {c['text']}" for c in top),
            citations=[c["ref"] for c in top],
        )

    data, model = run_structured(prompt, LegalAnswer, heuristic, [])
    refs = {c["ref"] for c in chunks}
    data.citations = [c for c in data.citations if c in refs]
    return PipelineResult(data, model, version)


# ---------------------------------------------------------------- conversation_prep (wirtualny HR partner)

ConvKind = Literal["opening", "feedback", "assessment", "difficult"]


class DifficultCase(BaseModel):
    situation: str
    how: str


class ConversationPrepResult(BaseModel):
    goal: str
    agenda: list[str]
    questions: list[str]
    communication_tips: list[str]
    difficult: list[DifficultCase] = Field(default_factory=list)
    wellbeing: list[str] = Field(default_factory=list)


CONV_GOALS = {
    "opening": "Wspólne ustalenie, czego oczekujemy w okresie oceny: obowiązki z opisu stanowiska, kryteria, "
               "oczekiwania co do sposobu ich spełniania i cele (§ 5 ust. 1 rozporządzenia).",
    "feedback": "Bieżąca informacja zwrotna: docenić to, co działa, omówić jedną-dwie rzeczy do poprawy "
                "i ustalić wsparcie - zanim nadejdzie ocena.",
    "assessment": "Omówienie wyników z całego okresu oceny na podstawie faktów, wysłuchanie perspektywy "
                  "ocenianego i ustalenie kierunków rozwoju (§ 10 rozporządzenia).",
    "difficult": "Rozmowa o trudnościach w pracy: nazwać fakty, zrozumieć przyczyny, wspólnie ustalić "
                 "plan naprawczy i formę wsparcia.",
}

_AGENDA = {
    "opening": ["Cel rozmowy i przebieg procesu oceny (terminy, rozmowa oceniająca, IPR)",
                "Główne obowiązki z opisu stanowiska - czy opis jest aktualny?",
                "Kryteria oceny: {criteria}",
                "Oczekiwania: jak w praktyce wygląda spełnianie kryteriów na poziomie oczekiwań",
                "Cele na okres oceny i sposób ich realizacji",
                "Wsparcie i forma bieżącej informacji zwrotnej"],
    "feedback": ["Co poszło dobrze od ostatniej rozmowy (konkretne sytuacje)",
                 "Jedna-dwie rzeczy do poprawy - fakty i skutki",
                 "Obciążenie i priorytety",
                 "Ustalenia i wsparcie do następnej rozmowy"],
    "assessment": ["Cel i przebieg rozmowy; na początek perspektywa ocenianego",
                   "Mocne strony: {strong}",
                   "Obszary do rozwoju: {weak}",
                   "Rozbieżności z samooceną (jeśli są)",
                   "Kierunki rozwoju i wnioski do IPR",
                   "Podsumowanie i dalsze kroki (ocena na piśmie, 7 dni na sprzeciw)"],
}
_AGENDA["difficult"] = _AGENDA["assessment"]

_QUESTIONS = {
    "opening": ["Które zadania z opisu stanowiska zajmują Ci najwięcej czasu? Czy opis jest aktualny?",
                "Jak rozumiesz poszczególne kryteria w swojej pracy? Jak wygląda zachowanie na poziomie oczekiwań?",
                "Jakie cele chcesz osiągnąć w okresie oceny?",
                "Czego potrzebujesz ode mnie, żeby je zrealizować?",
                "Jak często i w jakiej formie chcesz dostawać informację zwrotną?"],
    "feedback": ["Z czego jesteś najbardziej zadowolony(-a) w ostatnich tygodniach?",
                 "Co Ci przeszkadza w pracy albo zabiera najwięcej energii?",
                 "Jak oceniasz swoje obciążenie zadaniami? Co możemy przesunąć?",
                 "Co mogę zrobić inaczej, żeby Ci pomóc?"],
    "assessment": ["Jak oceniasz miniony okres? Co uważasz za swój największy sukces?",
                   "Co pomogłoby Ci osiągnąć wyższy poziom w obszarach do rozwoju?",
                   "W jakim kierunku chcesz się rozwijać? Jakie szkolenia lub zadania byłyby dla Ciebie wartościowe?"],
}
_QUESTIONS["difficult"] = _QUESTIONS["assessment"]

_TIPS = ["Zacznij od pytania otwartego i słuchaj - niech pracownik mówi więcej niż Ty.",
         "Mów o faktach i zachowaniach (sytuacja - zachowanie - skutek), nie o cechach osoby.",
         "Doceniaj konkretnie: co zrobił(a), jaki był efekt, dlaczego to ważne.",
         "Na koniec podsumuj ustalenia i zapisz je w dzienniku."]


def conversation_prep(kind: str, ctx: dict, people: list[str]) -> PipelineResult:
    """ctx: employee_name, position, duties, criteria[], notes[] {date, text, sentiment}, weak[], strong[],
    self_rows[], signals[] {title, message}, negative (bool)."""
    prompt, version = render_prompt("conversation_prep", kind=kind, goal=CONV_GOALS[kind], **ctx)

    def heuristic() -> ConversationPrepResult:
        fill = {"criteria": ", ".join(ctx.get("criteria") or []) or "-",
                "strong": ", ".join(ctx.get("strong") or []) or "z dziennika obserwacji",
                "weak": ", ".join(ctx.get("weak") or []) or "do ustalenia wspólnie"}
        agenda = [a.format(**fill) for a in _AGENDA[kind]]
        questions = list(_QUESTIONS[kind])
        if kind in ("assessment", "difficult"):
            questions[1:1] = [f"„{c}”: jakie sytuacje najlepiej pokazują, jak sobie radzisz w tym obszarze?"
                              for c in (ctx.get("weak") or [])[:2]]
        difficult = [
            DifficultCase(situation="Pracownik nie zgadza się z oceną",
                          how="Wysłuchaj argumentów, poproś o przykłady, odwołaj się do notatek. Poinformuj o prawie "
                              "do sprzeciwu w 7 dni (art. 83) - to normalna część procesu."),
            DifficultCase(situation="Silne emocje (płacz, złość)",
                          how="Zrób przerwę, nazwij emocję bez oceniania („widzę, że to dla Ciebie ważne”), "
                              "zaproponuj kontynuację w innym terminie."),
        ]
        if ctx.get("negative"):
            difficult.insert(0, DifficultCase(
                situation="Ocena negatywna",
                how="Przedstaw fakty z całego okresu, wyjaśnij konsekwencje (ponowna ocena po 6 miesiącach, "
                    "art. 81 ust. 9) i zaproponuj konkretny plan wsparcia w IPR."))
        signals = ctx.get("signals") or []
        wellbeing = [f"{s['title']}: {s['message']}" for s in signals[:3]]
        if wellbeing:
            questions.append("Jak się czujesz z obecną ilością pracy? Czy coś możemy zmienić?")
        return ConversationPrepResult(goal=CONV_GOALS[kind], agenda=agenda, questions=questions,
                                      communication_tips=_TIPS, difficult=difficult, wellbeing=wellbeing)

    data, model = run_structured(prompt, ConversationPrepResult, heuristic, people)
    return PipelineResult(data, model, version)
