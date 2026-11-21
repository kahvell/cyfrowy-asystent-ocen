"""Klasyfikacja notatek (classify_note) - uruchamiana w tle po dodaniu notatki."""

import logging

from sqlmodel import Session, select

from app.ai.pipelines import classify_note
from app.db import engine
from app.models import AISuggestion, Criterion, Employee, Note, NoteCriterion
from app.services.reviews import all_criteria, criterion_ctx

log = logging.getLogger(__name__)


def classify_and_store(session: Session, note: Note) -> None:
    criteria = all_criteria(session)
    emp = session.get(Employee, note.employee_id)
    result = classify_note(note.text, note.date, [criterion_ctx(c) for c in criteria], [emp.full_name] if emp else [])
    by_code: dict[str, Criterion] = {c.code: c for c in criteria}
    # nie nadpisujemy tagów nadanych ręcznie przez człowieka
    existing = session.exec(select(NoteCriterion).where(NoteCriterion.note_id == note.id)).all()
    if any(t.assigned_by == "human" for t in existing):
        note.classified = True
        session.add(note)
        session.commit()
        return
    for t in existing:
        session.delete(t)
    for tag in result.data.criteria:
        session.add(NoteCriterion(note_id=note.id, criterion_id=by_code[tag.criterion_code].id,
                                  confidence=tag.confidence, assigned_by="ai"))
    note.sentiment = result.data.sentiment
    note.classified = True
    session.add(note)
    session.add(AISuggestion(kind="classify_note", payload={"note_id": note.id, **result.data.model_dump()},
                             model=result.model, prompt_version=result.prompt_version, status="info"))
    session.commit()


def classify_in_background(note_id: int) -> None:
    with Session(engine) as session:
        note = session.get(Note, note_id)
        if note is None:
            return
        try:
            classify_and_store(session, note)
        except Exception:  # tło - nie wywracamy procesu
            log.exception("Klasyfikacja notatki %s nie powiodła się", note_id)
