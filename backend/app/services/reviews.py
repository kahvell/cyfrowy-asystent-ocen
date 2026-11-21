"""Logika domenowa ocen i dziennika (bez HTTP)."""

from collections import defaultdict
from datetime import date
from typing import Any

from sqlmodel import Session, select

from app.ai.pipelines import CriterionCtx, NoteCtx
from app.analytics.quality_rules import CriterionEntry, NoteInfo, run_rules
from app.config import settings
from app.models import (
    IPR,
    Criterion,
    Employee,
    Note,
    NoteCriterion,
    Review,
    ReviewCriterion,
    SelfAssessment,
    User,
    utcnow,
)
from app.services.process import (
    SECOND_NEGATIVE_WARNING,
    form_people,
    grade_label,
    promotion_target,
    review_deadlines,
    second_negative_risk,
)
from app.services.scoring import SCALE, compute_outcome


def criterion_ctx(c: Criterion) -> CriterionCtx:
    return CriterionCtx(id=c.id, code=c.code, name=c.name, indicators=c.behavioral_indicators, keywords=c.keywords)


def all_criteria(session: Session) -> list[Criterion]:
    return list(session.exec(select(Criterion).order_by(Criterion.order)).all())


def mandatory_criteria(session: Session, sheet_type: str) -> list[Criterion]:
    return [c for c in all_criteria(session) if sheet_type in c.mandatory_for]


def note_tags(session: Session, note_ids: list[int]) -> dict[int, list[NoteCriterion]]:
    out: dict[int, list[NoteCriterion]] = defaultdict(list)
    if not note_ids:
        return out
    for nc in session.exec(select(NoteCriterion).where(NoteCriterion.note_id.in_(note_ids))).all():
        out[nc.note_id].append(nc)
    return out


def employee_notes(session: Session, employee_id: int, start: date | None = None, end: date | None = None) -> list[Note]:
    q = select(Note).where(Note.employee_id == employee_id)
    if start:
        q = q.where(Note.date >= start)
    if end:
        q = q.where(Note.date <= end)
    return list(session.exec(q.order_by(Note.date.desc())).all())


def serialize_note(note: Note, tags: list[NoteCriterion], crit_by_id: dict[int, Criterion],
                   authors: dict[int, User] | None = None) -> dict[str, Any]:
    author = authors.get(note.author_id) if authors else None
    return {
        "id": note.id,
        "employee_id": note.employee_id,
        "author_id": note.author_id,
        "author_name": author.full_name if author else None,
        "date": note.date.isoformat(),
        "text": note.text,
        "sentiment": note.sentiment,
        "source": note.source,
        "shared_with_employee": note.shared_with_employee,
        "classified": note.classified,
        "criteria": [
            {
                "criterion_id": t.criterion_id,
                "code": crit_by_id[t.criterion_id].code,
                "name": crit_by_id[t.criterion_id].name,
                "confidence": t.confidence,
                "assigned_by": t.assigned_by,
            }
            for t in sorted(tags, key=lambda t: -t.confidence)
            if t.criterion_id in crit_by_id
        ],
    }


def review_entries(session: Session, review: Review) -> list[tuple[ReviewCriterion, Criterion]]:
    rows = session.exec(
        select(ReviewCriterion, Criterion)
        .join(Criterion, Criterion.id == ReviewCriterion.criterion_id)
        .where(ReviewCriterion.review_id == review.id)
        .order_by(ReviewCriterion.is_additional, Criterion.order)
    ).all()
    return list(rows)


def recompute(session: Session, review: Review) -> None:
    entries = review_entries(session, review)
    outcome = compute_outcome([rc.score for rc, _ in entries])
    review.overall_score = outcome.average if outcome else None
    review.overall_level = outcome.level if outcome else None
    review.result = outcome.result if outcome and outcome.complete else None
    review.updated_at = utcnow()


def serialize_review(session: Session, review: Review, *, viewer_is_reviewer: bool) -> dict[str, Any]:
    emp = session.get(Employee, review.employee_id)
    reviewer = session.get(User, review.reviewer_id)
    entries = review_entries(session, review)
    # Pracownik widzi oceny przełożonego dopiero po przekazaniu oceny do rozmowy.
    hide = not viewer_is_reviewer and review.status in ("criteria", "observation", "draft")
    outcome = compute_outcome([rc.score for rc, _ in entries])
    sa = session.exec(select(SelfAssessment).where(SelfAssessment.review_id == review.id)).first()
    ipr = session.exec(select(IPR).where(IPR.review_id == review.id)).first()

    def iso(d):
        return d.isoformat() if d else None

    return {
        "id": review.id,
        "status": review.status,
        "sheet_type": review.sheet_type,
        "cycle_id": review.cycle_id,
        "period_start": review.period_start.isoformat(),
        "period_end": review.period_end.isoformat(),
        "conversation_date": review.conversation_date.isoformat() if review.conversation_date else None,
        "employee": {
            "id": emp.id, "full_name": emp.full_name, "position": emp.position,
            "position_description": emp.position_description, "is_civil_servant": emp.is_civil_servant,
            "senior_position": emp.senior_position,
        },
        "reviewer": {"id": reviewer.id, "full_name": reviewer.full_name},
        "criteria": [
            {
                "criterion_id": c.id,
                "code": c.code,
                "name": c.name,
                "description": c.description,
                "indicators": c.behavioral_indicators,
                "is_additional": rc.is_additional,
                "score": None if hide else rc.score,
                "justification": "" if hide else rc.justification,
                "source_note_ids": [] if hide else rc.source_note_ids,
            }
            for rc, c in entries
        ],
        "summary": None if hide or not outcome else {
            "average": outcome.average, "level": outcome.level,
            "result": outcome.result if outcome.complete else None, "complete": outcome.complete,
        },
        "justification": "" if hide else review.justification,
        "ipr_conclusions": "" if hide else review.ipr_conclusions,
        "self_assessment_submitted": bool(sa and sa.submitted_at),
        "self_assessment_submitted_at": sa.submitted_at.date().isoformat() if sa and sa.submitted_at else None,
        "ipr_id": ipr.id if ipr else None,
        "scale": [{"value": k, "label": v} for k, v in SCALE.items()],
        "updated_at": review.updated_at.isoformat(),
        # --- pola arkusza (części I-III) i proces ---
        **form_people(session, review),
        "attempt": review.attempt,
        "assessment_invited_at": iso(review.assessment_invited_at),
        "assessment_confirmed_at": iso(review.assessment_confirmed_at),
        "opening_conversation_date": iso(review.opening_conversation_date),
        "opening_notes": review.opening_notes,
        "criteria_reviewer_confirmed_at": iso(review.criteria_reviewer_confirmed_at),
        "criteria_reviewer_place": review.criteria_reviewer_place,
        "criteria_employee_confirmed_at": iso(review.criteria_employee_confirmed_at),
        "criteria_employee_place": review.criteria_employee_place,
        "due_date_history": review.due_date_history,
        "prev_result": None if hide else review.prev_result,
        "prev_level": None if hide else review.prev_level,
        "prev_date": None if hide else iso(review.prev_date),
        "promotion_request": review.promotion_request,
        "appointment_year": review.appointment_year,
        "civil_grade": review.civil_grade,
        "civil_grade_date": iso(review.civil_grade_date),
        "promotion_target": promotion_target(review),
        "civil_grade_label": grade_label(review.civil_grade),
        "signature_method": review.signature_method,
        "objection_body": review.objection_body,
        "promotion_justification": "" if hide else review.promotion_justification,
        "reviewer_place": review.reviewer_place,
        "reviewer_signed_at": iso(review.reviewer_signed_at),
        "employee_place": review.employee_place,
        "acknowledged_at": iso(review.acknowledged_at),
        "ack_fiction": review.ack_fiction,
        "ack_fiction_note": review.ack_fiction_note,
        "objection_at": iso(review.objection_at),
        "objection_text": review.objection_text,
        "objection_decision": review.objection_decision,
        "objection_decided_at": iso(review.objection_decided_at),
        "deadlines": review_deadlines(session, review),
    }


def notes_for_review(session: Session, review: Review) -> tuple[list[Note], dict[int, list[NoteCriterion]]]:
    notes = employee_notes(session, review.employee_id, review.period_start, review.period_end)
    return notes, note_tags(session, [n.id for n in notes])


def notes_for_criterion(session: Session, review: Review, criterion_id: int) -> list[NoteCtx]:
    notes, tags = notes_for_review(session, review)
    picked = [n for n in notes if any(t.criterion_id == criterion_id for t in tags.get(n.id, []))]
    return [NoteCtx(n.id, n.date, n.text, n.sentiment, n.source) for n in sorted(picked, key=lambda n: n.date)]


def rule_warnings(session: Session, review: Review, today: date | None = None) -> list[dict[str, Any]]:
    entries = review_entries(session, review)
    notes, tags = notes_for_review(session, review)
    recompute(session, review)
    extra = [SECOND_NEGATIVE_WARNING] if second_negative_risk(session, review) else []
    return extra + run_rules(
        [CriterionEntry(c.id, c.code, c.name, rc.score, rc.justification, rc.is_additional) for rc, c in entries],
        [NoteInfo(n.id, n.date, n.sentiment, {t.criterion_id for t in tags.get(n.id, [])}) for n in notes],
        period_start=review.period_start,
        period_end=review.period_end,
        today=today or date.today(),
        overall_justification=review.justification,
        recency_days=settings.recency_window_days,
        recency_threshold=settings.recency_threshold,
    )


def people_names(session: Session, review: Review) -> list[str]:
    emp = session.get(Employee, review.employee_id)
    reviewer = session.get(User, review.reviewer_id)
    return [n for n in [emp.full_name if emp else None, reviewer.full_name if reviewer else None] if n]
