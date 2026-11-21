import datetime as dt
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, delete, func, select

from app.analytics.stats import DONE
from app.db import get_session
from app.models import Criterion, Department, Employee, Note, NoteCriterion, Review, ReviewCycle, User
from app.security import get_current_user
from app.services.access import direct_report_ids, ensure_employee_access, is_manager_of
from app.services.audit import audit
from app.services.notes import classify_and_store, classify_in_background
from app.services.reviews import employee_notes, note_tags, serialize_note

router = APIRouter(tags=["employees & notes"])

REMINDER_DAYS = 90


def _employee_out(session: Session, emp: Employee) -> dict:
    dept = session.get(Department, emp.department_id)
    manager = session.get(Employee, emp.manager_id) if emp.manager_id else None
    return {
        "id": emp.id,
        "full_name": emp.full_name,
        "position": emp.position,
        "department": dept.name if dept else None,
        "manager_name": manager.full_name if manager else None,
        "position_description": emp.position_description,
        "sheet_type": emp.sheet_type,
        "is_civil_servant": emp.is_civil_servant,
        "contract_type": emp.contract_type,
        "senior_position": emp.senior_position,
    }


@router.get("/employees")
def list_employees(
    team: str = "mine",
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if user.role == "admin":
        raise HTTPException(403, "Administrator nie ma wglądu w zespoły ani dziennik obserwacji - arkusze do korekty: /reviews")
    if user.role == "manager":
        ids = direct_report_ids(session, user)
    elif user.employee_id:
        ids = {user.employee_id}
    else:
        raise HTTPException(403, "HR ma dostęp wyłącznie do danych zagregowanych (dashboard)")

    out = []
    today = date.today()
    for emp in session.exec(select(Employee).where(Employee.id.in_(ids), Employee.active)
                            .order_by(Employee.full_name)).all():
        stats = session.exec(
            select(func.count(Note.id), func.max(Note.date)).where(Note.employee_id == emp.id)
        ).one()
        # trwająca ocena, a jeśli brak - najnowsza (kolejne cykle zakładają się automatycznie)
        mine = session.exec(select(Review).join(ReviewCycle, ReviewCycle.id == Review.cycle_id)
                            .where(Review.employee_id == emp.id)
                            .order_by(ReviewCycle.period_start.desc(), Review.id.desc())).all()
        review = next((r for r in mine if r.status not in DONE), None)
        if review is None and mine and mine[0].reviewer_signed_at and (today - mine[0].reviewer_signed_at).days <= 30:
            review = mine[0]  # świeżo sporządzona ocena - widoczna jeszcze przez 30 dni
        last = stats[1]
        item = _employee_out(session, emp)
        item.update({
            "notes_count": stats[0],
            "last_note_date": last.isoformat() if last else None,
            "reminder": (last is None or (today - last) > timedelta(days=REMINDER_DAYS)),
            "current_review": {"id": review.id, "status": review.status} if review else None,
        })
        out.append(item)
    return out


@router.get("/employees/{employee_id}")
def get_employee(employee_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    emp = ensure_employee_access(session, user, employee_id)
    reviews = session.exec(select(Review, ReviewCycle).join(ReviewCycle, ReviewCycle.id == Review.cycle_id)
                           .where(Review.employee_id == emp.id).order_by(ReviewCycle.period_start.desc())).all()
    out = _employee_out(session, emp)
    out["reviews"] = [
        {"id": r.id, "status": r.status, "cycle_id": c.id, "cycle_name": c.name, "overall_level": r.overall_level
         if r.status in DONE or is_manager_of(session, user, emp.id) else None,
         "result": r.result if r.status in DONE else None}
        for r, c in reviews
    ]
    audit(session, user, "view", "employee", emp.id)
    session.commit()
    return out


# ------------------------------------------------------------------ dziennik obserwacji


@router.get("/employees/{employee_id}/notes")
def list_notes(
    employee_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
    criterion_id: int | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ensure_employee_access(session, user, employee_id)
    notes = employee_notes(session, employee_id, date_from, date_to)
    if not is_manager_of(session, user, employee_id):
        # pracownik widzi swoje notatki oraz te notatki przełożonego, które zostały mu udostępnione
        notes = [n for n in notes if n.source == "self" or n.shared_with_employee]
    tags = note_tags(session, [n.id for n in notes])
    if criterion_id:
        notes = [n for n in notes if any(t.criterion_id == criterion_id for t in tags.get(n.id, []))]
    crit = {c.id: c for c in session.exec(select(Criterion)).all()}
    authors = {u.id: u for u in session.exec(select(User).where(User.id.in_({n.author_id for n in notes}))).all()}
    audit(session, user, "view", "notes", employee_id, count=len(notes))
    session.commit()
    return [serialize_note(n, tags.get(n.id, []), crit, authors) for n in notes]


class NoteIn(BaseModel):
    text: str = Field(min_length=3, max_length=4000)
    date: dt.date | None = None


@router.post("/employees/{employee_id}/notes", status_code=201)
def add_note(
    employee_id: int,
    body: NoteIn,
    background: BackgroundTasks,
    sync: bool = False,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ensure_employee_access(session, user, employee_id)
    is_self = user.employee_id == employee_id
    if not is_self and not is_manager_of(session, user, employee_id):
        raise HTTPException(403, "Notatki może dodawać przełożony lub sam pracownik (własne osiągnięcia)")
    note_date = body.date or date.today()
    if note_date > date.today():
        raise HTTPException(422, "Data notatki nie może być z przyszłości")
    note = Note(employee_id=employee_id, author_id=user.id, date=note_date, text=body.text.strip(),
                source="self" if is_self else "manager")
    session.add(note)
    audit(session, user, "create", "note", None, employee_id=employee_id)
    session.commit()
    session.refresh(note)
    if sync:
        classify_and_store(session, note)
    else:
        background.add_task(classify_in_background, note.id)
    crit = {c.id: c for c in session.exec(select(Criterion)).all()}
    return serialize_note(note, note_tags(session, [note.id]).get(note.id, []), crit, {user.id: user})


class NoteCriteriaIn(BaseModel):
    criterion_ids: list[int]


class NoteShareIn(BaseModel):
    shared: bool = True


@router.patch("/notes/{note_id}/criteria")
def set_note_criteria(note_id: int, body: NoteCriteriaIn, user: User = Depends(get_current_user),
                      session: Session = Depends(get_session)):
    note = session.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Nie ma takiej notatki")
    if note.author_id != user.id and not is_manager_of(session, user, note.employee_id):
        raise HTTPException(403, "Brak uprawnień do edycji tej notatki")
    valid = set(session.exec(select(Criterion.id)).all())
    session.exec(delete(NoteCriterion).where(NoteCriterion.note_id == note_id))
    for cid in dict.fromkeys(body.criterion_ids):
        if cid in valid:
            session.add(NoteCriterion(note_id=note_id, criterion_id=cid, confidence=1.0, assigned_by="human"))
    note.classified = True
    session.add(note)
    audit(session, user, "retag", "note", note_id, criterion_ids=body.criterion_ids)
    session.commit()
    crit = {c.id: c for c in session.exec(select(Criterion)).all()}
    return serialize_note(note, note_tags(session, [note_id]).get(note_id, []), crit)


@router.patch("/notes/{note_id}/share")
def share_note(note_id: int, body: NoteShareIn, user: User = Depends(get_current_user),
               session: Session = Depends(get_session)):
    """Udostępnia (lub cofa udostępnienie) notatkę przełożonego pracownikowi.

    Notatki naczelnika są domyślnie niejawne - widzi je tylko przełożony, dopóki nie zdecyduje
    się jej udostępnić podwładnemu."""
    note = session.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Nie ma takiej notatki")
    if note.source != "manager":
        raise HTTPException(422, "Udostępnić można tylko notatkę przełożonego")
    if note.author_id != user.id and not is_manager_of(session, user, note.employee_id):
        raise HTTPException(403, "Brak uprawnień do udostępnienia tej notatki")
    note.shared_with_employee = body.shared
    session.add(note)
    audit(session, user, "share" if body.shared else "unshare", "note", note_id, employee_id=note.employee_id)
    session.commit()
    crit = {c.id: c for c in session.exec(select(Criterion)).all()}
    return serialize_note(note, note_tags(session, [note_id]).get(note_id, []), crit)


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    note = session.get(Note, note_id)
    if note is None:
        raise HTTPException(404, "Nie ma takiej notatki")
    if note.author_id != user.id:
        raise HTTPException(403, "Usunąć notatkę może tylko jej autor")
    session.exec(delete(NoteCriterion).where(NoteCriterion.note_id == note_id))
    session.delete(note)
    audit(session, user, "delete", "note", note_id)
    session.commit()
