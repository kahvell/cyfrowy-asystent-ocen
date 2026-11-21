"""Panel kadrowy (rola hr i admin): dane pracowników, podległość służbowa (kto kogo ocenia),
nieobecności, ustanie zatrudnienia, a także powiadomienia użytkownika.

Komórka kadrowa prowadzi dane pracowników i dokumentację ocen, ale nie widzi dziennika obserwacji
ani szkiców ocen (to robocze materiały przełożonego).
"""

import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, delete, select

from app.analytics.stats import DONE
from app.db import get_session
from app.models import (
    Absence,
    Department,
    Employee,
    Note,
    NoteCriterion,
    Notification,
    Review,
    ReviewCriterion,
    User,
    utcnow,
)
from app.security import get_current_user, hash_password, require_roles
from app.services import deadlines as dl
from app.services.audit import audit
from app.services.cycle import start_for_new_employee
from app.services.notify import notify, notify_employee
from app.services.process import compute_due_date, deadline_base, previous_review

router = APIRouter(tags=["kadry"])
hr_only = require_roles("hr", "admin")

ACTIVE = ("criteria", "observation", "draft", "submitted", "discussed")


def _emp_out(session: Session, e: Employee, depts: dict[int, Department], people: dict[int, Employee]) -> dict:
    current = session.exec(select(Review).where(Review.employee_id == e.id).order_by(Review.period_start.desc())).first()
    user = session.exec(select(User).where(User.employee_id == e.id)).first()
    return {
        "id": e.id, "full_name": e.full_name, "position": e.position, "department_id": e.department_id,
        "department": depts[e.department_id].name if e.department_id in depts else "",
        "manager_id": e.manager_id, "manager_name": people[e.manager_id].full_name if e.manager_id in people else None,
        "sheet_type": e.sheet_type, "is_civil_servant": e.is_civil_servant, "gender": e.gender,
        "contract_type": e.contract_type,
        "employment_start": e.employment_start.isoformat() if e.employment_start else None,
        "employment_end": e.employment_end.isoformat() if e.employment_end else None,
        "appointment_year": e.appointment_year, "civil_grade": e.civil_grade,
        "civil_grade_date": e.civil_grade_date.isoformat() if e.civil_grade_date else None,
        "position_description": e.position_description, "active": e.active, "senior_position": e.senior_position,
        "email": user.email if user else None, "role": user.role if user else None,
        "review": {"id": current.id, "status": current.status,
                   "due_date": current.due_date.isoformat() if current.due_date else None} if current else None,
    }


@router.get("/admin/employees")
def list_employees(q: str = "", include_inactive: bool = False, user: User = Depends(hr_only),
                   session: Session = Depends(get_session)):
    rows = session.exec(select(Employee).order_by(Employee.full_name)).all()
    depts = {d.id: d for d in session.exec(select(Department)).all()}
    people = {e.id: e for e in rows}
    ql = q.lower().strip()
    out = []
    for e in rows:
        if not include_inactive and not e.active:
            continue
        if ql and ql not in f"{e.full_name} {e.position} {depts.get(e.department_id).name if e.department_id in depts else ''}".lower():
            continue
        out.append(_emp_out(session, e, depts, people))
    return out


@router.get("/admin/structure")
def structure(user: User = Depends(hr_only), session: Session = Depends(get_session)):
    """Słowniki do formularzy: komórki organizacyjne i możliwi przełożeni."""
    depts = session.exec(select(Department).order_by(Department.name)).all()
    managers = session.exec(select(Employee).where(Employee.active, Employee.sheet_type.in_(["A", "B"]))
                            .order_by(Employee.full_name)).all()
    return {"departments": [{"id": d.id, "name": d.name} for d in depts],
            "managers": [{"id": m.id, "full_name": m.full_name, "position": m.position} for m in managers]}


class EmployeeIn(BaseModel):
    full_name: str = Field(min_length=3)
    position: str = Field(min_length=2)
    department_id: int
    manager_id: int | None = None
    sheet_type: str = Field(default="C", pattern="^[ABC]$")
    is_civil_servant: bool = False
    contract_type: str = Field(default="nieokreslony", pattern="^(mianowanie|nieokreslony|okreslony)$")
    gender: str | None = Field(default=None, pattern="^[KM]$")
    employment_start: date | None = None
    appointment_year: int | None = None
    civil_grade: int | None = Field(default=None, ge=1, le=9)
    civil_grade_date: date | None = None
    position_description: str = ""
    senior_position: bool = False  # wyższe stanowisko w służbie cywilnej (art. 52) - bez IPR
    email: str | None = None  # utworzenie konta w systemie


class EmployeePatch(BaseModel):
    full_name: str | None = None
    position: str | None = None
    department_id: int | None = None
    manager_id: int | None = None
    sheet_type: str | None = Field(default=None, pattern="^[ABC]$")
    is_civil_servant: bool | None = None
    contract_type: str | None = Field(default=None, pattern="^(mianowanie|nieokreslony|okreslony)$")
    employment_start: date | None = None
    appointment_year: int | None = None
    civil_grade: int | None = Field(default=None, ge=1, le=9)
    civil_grade_date: date | None = None
    position_description: str | None = None
    senior_position: bool | None = None
    reason: str = ""  # np. „zmiana struktury”, „powierzenie innego stanowiska”
    # zmiana stanowiska wiążąca się z istotną zmianą zakresu obowiązków (art. 81 ust. 6, § 9 rozporządzenia)
    significant_change_date: date | None = None


@router.post("/admin/employees", status_code=201)
def create_employee(body: EmployeeIn, user: User = Depends(hr_only), session: Session = Depends(get_session)):
    if session.get(Department, body.department_id) is None:
        raise HTTPException(422, "Nieznana komórka organizacyjna")
    data = body.model_dump(exclude={"email"})
    e = Employee(**data)
    session.add(e)
    session.flush()
    password = None
    if body.email:
        if session.exec(select(User).where(User.email == body.email)).first():
            raise HTTPException(409, "Konto z tym adresem już istnieje")
        password = secrets.token_urlsafe(9)
        session.add(User(email=body.email, full_name=e.full_name, password_hash=hash_password(password),
                         role="manager" if e.sheet_type in ("A", "B") else "employee", employee_id=e.id))
    audit(session, user, "create", "employee", e.id)
    session.flush()
    started = start_for_new_employee(session, e)  # schemat procesu: dane pracownika -> początek cyklu oceny
    session.commit()
    depts = {d.id: d for d in session.exec(select(Department)).all()}
    people = {x.id: x for x in session.exec(select(Employee)).all()}
    return {**_emp_out(session, e, depts, people), "initial_password": password,
            "review_started": started.id if started else None}


def _delete_notes(session: Session, employee_id: int) -> int:
    """Usuwa notatki z dziennika wraz z ich przypisaniami do kryteriów."""
    notes = session.exec(select(Note).where(Note.employee_id == employee_id)).all()
    ids = [n.id for n in notes]
    if ids:
        session.exec(delete(NoteCriterion).where(NoteCriterion.note_id.in_(ids)))
    for n in notes:
        session.delete(n)
    return len(ids)


def _manager_user(session: Session, manager_employee_id: int | None) -> User | None:
    if manager_employee_id is None:
        return None
    return session.exec(select(User).where(User.employee_id == manager_employee_id)).first()


@router.patch("/admin/employees/{employee_id}")
def update_employee(employee_id: int, body: EmployeePatch, user: User = Depends(hr_only),
                    session: Session = Depends(get_session)):
    e = session.get(Employee, employee_id)
    if e is None:
        raise HTTPException(404, "Nie ma takiego pracownika")
    changes = body.model_dump(exclude_unset=True, exclude={"reason", "significant_change_date"})
    if changes.get("manager_id") == e.id:
        raise HTTPException(422, "Pracownik nie może być swoim przełożonym")
    old_manager = e.manager_id
    for k, v in changes.items():
        setattr(e, k, v)
    session.add(e)
    moved = []
    # zmiana podległości = zmiana oceniającego w trwających ocenach (art. 81 ust. 8 pkt 1)
    if "manager_id" in changes and changes["manager_id"] != old_manager:
        new_reviewer = _manager_user(session, e.manager_id)
        if new_reviewer is None and e.manager_id is not None:
            raise HTTPException(422, "Nowy przełożony nie ma konta w systemie - utwórz je najpierw")
        for r in session.exec(select(Review).where(Review.employee_id == e.id, Review.status.in_(ACTIVE))).all():
            if new_reviewer is None:
                continue
            r.reviewer_id = new_reviewer.id
            r.due_date_history = [*r.due_date_history, {
                "from": r.due_date.isoformat() if r.due_date else None,
                "date": r.due_date.isoformat() if r.due_date else None,
                "reason": f"zmiana oceniającego na: {new_reviewer.full_name} - termin można zmienić (art. 81 ust. 8 pkt 1)",
                "note": body.reason, "at": date.today().isoformat()}]
            session.add(r)
            moved.append(r.id)
            notify(session, new_reviewer.id, f"Przejmujesz ocenę okresową: {e.full_name}",
                   "Od teraz pełnisz rolę bezpośredniego przełożonego ocenianego. Poradnik KPRM zaleca: przeprowadź "
                   "z ocenianym rozmowę o obowiązkach, kryteriach i oczekiwaniach (w razie potrzeby wyznacz kryteria "
                   "na nowo), poproś poprzedniego przełożonego o opinię o pracy ocenianego i sprawdź termin oceny - "
                   "można go zmienić (art. 81 ust. 8 pkt 1).", f"/reviews/{r.id}")
            old_user = _manager_user(session, old_manager) if old_manager else None
            if old_user is not None:
                notify(session, old_user.id, f"Zmiana oceniającego: {e.full_name}",
                       f"Ocenę przejmuje {new_reviewer.full_name}. Jeżeli od początku okresu oceny minęło ponad "
                       "6 miesięcy, ocenę możesz sporządzić jeszcze przed zmianą (art. 81 ust. 8 pkt 1); w przeciwnym "
                       "razie przekaż nowemu przełożonemu opinię i notatki z obserwacji.", f"/reviews/{r.id}")
            notify_employee(session, r, "Zmiana oceniającego", f"Twoim oceniającym jest teraz {new_reviewer.full_name}.")
    position_effects = position_change(session, e, body.significant_change_date) if body.significant_change_date else []
    audit(session, user, "update", "employee", e.id, fields=sorted(changes), reason=body.reason, reviews_moved=moved,
          position_change=position_effects)
    session.commit()
    depts = {d.id: d for d in session.exec(select(Department)).all()}
    people = {x.id: x for x in session.exec(select(Employee)).all()}
    return {**_emp_out(session, e, depts, people), "reviews_moved": moved, "position_change": position_effects}


def position_change(session: Session, e: Employee, changed: date) -> list[dict]:
    """Zmiana stanowiska z istotną zmianą zakresu obowiązków:
    - w ciągu 6 mies. od ustalenia kryteriów (pierwsza ocena) albo od ostatniej oceny: ponownie rozmowa
      i kryteria (§ 5-6) w 30 dni od zmiany, termin oceny bez zmian (§ 9 ust. 1 rozporządzenia),
    - później: ocena sporządzana w związku ze zmianą stanowiska (art. 81 ust. 6) - nie wcześniej niż 7 dni
      przed i nie później niż 30 dni po zmianie (§ 9 ust. 2)."""
    effects = []
    for r in session.exec(select(Review).where(Review.employee_id == e.id, Review.status.in_(ACTIVE))).all():
        prev = previous_review(session, r)
        ref = (prev.reviewer_signed_at if prev and prev.reviewer_signed_at else None) or \
            r.criteria_reviewer_confirmed_at or deadline_base(session, r)
        if changed <= dl.add_months(ref, 6):
            r.status = "criteria"
            r.criteria_reviewer_confirmed_at = r.criteria_employee_confirmed_at = None
            r.criteria_deadline = dl.days_deadline(changed, 30)
            note = ("zmiana stanowiska w ciągu 6 mies. - ponownie rozmowa i kryteria w 30 dni, "
                    "termin oceny bez zmian (§ 9 ust. 1 rozporządzenia)")
            effects.append({"review_id": r.id, "effect": "criteria_reopened", "criteria_deadline": r.criteria_deadline.isoformat()})
            notify(session, r.reviewer_id, f"Zmiana stanowiska: ponownie wyznacz kryteria - {e.full_name}",
                   f"Rozmowa i kryteria do {r.criteria_deadline.isoformat()} (§ 9 ust. 1).", f"/reviews/{r.id}")
        else:
            new = dl.days_deadline(changed, 30)
            note = (f"zmiana stanowiska - ocena w związku z istotną zmianą zakresu obowiązków (art. 81 ust. 6): "
                    f"od {(changed - timedelta(days=7)).isoformat()} do {new.isoformat()} (§ 9 ust. 2)")
            r.due_date_history = [*r.due_date_history, {"from": r.due_date.isoformat() if r.due_date else None,
                                                        "date": new.isoformat(), "reason": note, "at": date.today().isoformat()}]
            r.due_date = new
            effects.append({"review_id": r.id, "effect": "review_due", "due_date": new.isoformat()})
            notify(session, r.reviewer_id, f"Zmiana stanowiska: sporządź ocenę - {e.full_name}",
                   f"Ocena najpóźniej {new.isoformat()} (art. 81 ust. 6, § 9 ust. 2).", f"/reviews/{r.id}")
        if effects and effects[-1]["effect"] == "criteria_reopened":
            r.due_date_history = [*r.due_date_history, {"from": r.due_date.isoformat() if r.due_date else None,
                                                        "date": r.due_date.isoformat() if r.due_date else None,
                                                        "reason": note, "at": date.today().isoformat()}]
        notify_employee(session, r, "Zmiana stanowiska a ocena okresowa", note)
        session.add(r)
    return effects


class TerminateIn(BaseModel):
    employment_end: date
    # Standardy ZZL VII pkt 3: na wniosek pracownika, z którym rozwiązano stosunek pracy, przełożony sporządza ocenę
    review_requested: bool = False


@router.post("/admin/employees/{employee_id}/terminate")
def terminate(employee_id: int, body: TerminateIn, user: User = Depends(hr_only),
              session: Session = Depends(get_session)):
    """Ustanie stosunku pracy: sporządzone oceny zostają w dokumentacji (akta osobowe), robocze notatki
    przełożonego są usuwane (minimalizacja danych, RODO), konto jest blokowane."""
    e = session.get(Employee, employee_id)
    if e is None:
        raise HTTPException(404, "Nie ma takiego pracownika")
    if session.exec(select(Employee).where(Employee.manager_id == e.id, Employee.active)).first():
        raise HTTPException(409, "Najpierw przypisz podwładnym nowego przełożonego")
    if body.review_requested and e.manager_id:
        mgr = _manager_user(session, e.manager_id)
        if mgr:
            notify(session, mgr.id, f"Wniosek o ocenę okresową odchodzącego pracownika: {e.full_name}",
                   "Standardy ZZL (rozdz. VII pkt 3): na wniosek pracownika, z którym rozwiązano stosunek pracy, "
                   "przełożony przeprowadza ocenę okresową. Sporządź ją przed datą ustania zatrudnienia - "
                   "dziennik obserwacji zostanie usunięty po zakończeniu zatrudnienia.", f"/employees/{e.id}")
        audit(session, user, "review_requested_on_exit", "employee", e.id)
        session.commit()
        return {"id": e.id, "active": True, "notes_deleted": 0, "review_requested": True}
    deleted = _delete_notes(session, e.id)
    e.active, e.employment_end = False, body.employment_end
    session.add(e)
    acc = session.exec(select(User).where(User.employee_id == e.id)).first()
    if acc:
        acc.password_hash = "!"  # konto zablokowane
        session.add(acc)
    audit(session, user, "terminate", "employee", e.id, notes_deleted=deleted)
    session.commit()
    return {"id": e.id, "active": False, "notes_deleted": deleted}


@router.delete("/admin/employees/{employee_id}")
def delete_employee(employee_id: int, user: User = Depends(hr_only), session: Session = Depends(get_session)):
    """Usunięcie danych wprowadzonych omyłkowo - tylko gdy nie ma sporządzonych ocen (te są dokumentacją pracowniczą)."""
    e = session.get(Employee, employee_id)
    if e is None:
        raise HTTPException(404, "Nie ma takiego pracownika")
    if session.exec(select(Review).where(Review.employee_id == e.id, Review.status.in_(DONE))).first():
        raise HTTPException(409, "Pracownik ma sporządzone oceny (dokumentacja pracownicza) - użyj „ustanie zatrudnienia”")
    if session.exec(select(Employee).where(Employee.manager_id == e.id)).first():
        raise HTTPException(409, "Pracownik jest przełożonym innych osób")
    reviews = session.exec(select(Review).where(Review.employee_id == e.id)).all()
    if any(r.status != "criteria" or r.criteria_reviewer_confirmed_at for r in reviews):
        raise HTTPException(409, "Pracownik ma rozpoczętą ocenę - użyj „ustanie zatrudnienia”")
    for r in reviews:  # arkusz założony automatycznie, bez żadnych czynności - usuwamy razem z danymi
        session.exec(delete(ReviewCriterion).where(ReviewCriterion.review_id == r.id))
        session.delete(r)
    _delete_notes(session, e.id)
    for a in session.exec(select(Absence).where(Absence.employee_id == e.id)).all():
        session.delete(a)
    for u in session.exec(select(User).where(User.employee_id == e.id)).all():
        session.delete(u)
    session.delete(e)
    audit(session, user, "delete", "employee", employee_id)
    session.commit()
    return {"deleted": employee_id}


# ------------------------------------------------------------------ nieobecności (art. 81 ust. 7)


class AbsenceIn(BaseModel):
    start: date
    end: date
    kind: str = "zwolnienie lekarskie"


def _absence_out(a: Absence) -> dict:
    return {"id": a.id, "start": a.start.isoformat(), "end": a.end.isoformat(), "kind": a.kind,
            "days": (a.end - a.start).days + 1}


def recompute_due_dates(session: Session, employee_id: int) -> list[dict]:
    """Termin oceny przedłuża się o czas nieobecności dłuższych niż miesiąc. Ręczne zmiany terminu
    (art. 81 ust. 8) są zachowane - przeliczamy tylko terminy wyznaczone z kalendarza."""
    periods = [dl.Period(a.start, a.end) for a in
               session.exec(select(Absence).where(Absence.employee_id == employee_id)).all()]
    changed = []
    for r in session.exec(select(Review).where(Review.employee_id == employee_id, Review.status.in_(ACTIVE))).all():
        manual = any("art. 81 ust. 8" in h.get("reason", "") and "zmiana oceniającego" not in h.get("reason", "")
                     for h in r.due_date_history)
        if manual:
            continue
        _ = periods  # nieobecności z bazy (już zapisane) uwzględnia compute_due_date
        new = compute_due_date(session, r)
        if new != r.due_date:
            r.due_date_history = [*r.due_date_history, {
                "from": r.due_date.isoformat() if r.due_date else None, "date": new.isoformat(),
                "reason": "przeliczenie po zmianie nieobecności (art. 81 ust. 7)", "at": date.today().isoformat()}]
            changed.append({"review_id": r.id, "from": r.due_date.isoformat() if r.due_date else None,
                            "to": new.isoformat()})
            r.due_date = new
            if r.status in ("criteria", "observation"):
                r.period_end = new  # okres oceny trwa do terminu sporządzenia oceny
            session.add(r)
            notify_employee(session, r, "Zmiana terminu oceny okresowej",
                            f"Termin przedłużony o czas nieobecności: {new.isoformat()} (art. 81 ust. 7).")
            notify(session, r.reviewer_id, "Termin oceny przedłużony o nieobecność",
                   f"Nowy termin: {new.isoformat()}", f"/reviews/{r.id}")
    return changed


@router.get("/admin/employees/{employee_id}/absences")
def list_absences(employee_id: int, user: User = Depends(hr_only), session: Session = Depends(get_session)):
    rows = session.exec(select(Absence).where(Absence.employee_id == employee_id).order_by(Absence.start)).all()
    merged = dl.merge_absences([dl.Period(a.start, a.end) for a in rows])
    return {"absences": [_absence_out(a) for a in rows],
            "continuous": [{"start": p.start.isoformat(), "end": p.end.isoformat(), "days": p.days,
                            "extends_deadline": dl.is_long_absence(p)} for p in merged]}


@router.post("/admin/employees/{employee_id}/absences", status_code=201)
def add_absence(employee_id: int, body: AbsenceIn, user: User = Depends(hr_only),
                session: Session = Depends(get_session)):
    if session.get(Employee, employee_id) is None:
        raise HTTPException(404, "Nie ma takiego pracownika")
    if body.end < body.start:
        raise HTTPException(422, "Koniec nieobecności przed jej początkiem")
    a = Absence(employee_id=employee_id, start=body.start, end=body.end, kind=body.kind)
    session.add(a)
    session.flush()
    changed = recompute_due_dates(session, employee_id)
    audit(session, user, "create", "absence", a.id, employee_id=employee_id)
    session.commit()
    return {"absence": _absence_out(a), "due_dates_changed": changed}


@router.delete("/admin/absences/{absence_id}")
def delete_absence(absence_id: int, user: User = Depends(hr_only), session: Session = Depends(get_session)):
    a = session.get(Absence, absence_id)
    if a is None:
        raise HTTPException(404, "Nie ma takiej nieobecności")
    emp_id = a.employee_id
    session.delete(a)
    session.flush()
    changed = recompute_due_dates(session, emp_id)
    audit(session, user, "delete", "absence", absence_id, employee_id=emp_id)
    session.commit()
    return {"deleted": absence_id, "due_dates_changed": changed}


# ------------------------------------------------------------------ powiadomienia (wszyscy użytkownicy)


@router.get("/notifications")
def my_notifications(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    rows = session.exec(select(Notification).where(Notification.user_id == user.id)
                        .order_by(Notification.created_at.desc()).limit(30)).all()
    return [{"id": n.id, "subject": n.subject, "body": n.body, "link": n.link, "created_at": n.created_at.isoformat(),
             "read": n.read_at is not None, "emailed": n.emailed_at is not None} for n in rows]


@router.post("/notifications/read")
def mark_read(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    for n in session.exec(select(Notification).where(Notification.user_id == user.id,
                                                     Notification.read_at.is_(None))).all():
        n.read_at = utcnow()
        session.add(n)
    session.commit()
    return {"ok": True}

