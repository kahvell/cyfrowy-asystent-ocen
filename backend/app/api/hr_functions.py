"""Funkcje kadrowe z diagramu przypadków użycia KPRM (rola hr / admin):

- zarządza schematem urzędu (komórki organizacyjne),
- zarządza zastępstwami przełożonych,
- wprowadza oceny historyczne (sprzed wdrożenia systemu),
- weryfikuje i importuje dane pobrane z systemu kadrowego (CSV, podgląd przed zapisem),
- pobiera zestawienia na potrzeby archiwizacji / kontroli oraz sprawozdawczości,
- wgląd w historię ocen pracownika.
"""

import csv
import io
import secrets
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.analytics.stats import DONE
from app.config import settings
from app.db import get_session
from app.models import (
    Criterion,
    Department,
    Employee,
    Office,
    Review,
    ReviewCriterion,
    ReviewCycle,
    Substitution,
    User,
)
from app.security import hash_password, require_roles
from app.services import deadlines as dl
from app.services.audit import audit
from app.services.cycle import start_for_new_employee
from app.services.notify import notify
from app.services.process import compute_due_date, drawn_up_date
from app.services.scoring import overall_level

router = APIRouter(tags=["kadry"])
hr_only = require_roles("hr", "admin")

ACTIVE = ("criteria", "observation", "draft", "submitted", "discussed")
HISTORICAL_CYCLE = "Oceny historyczne (sprzed wdrożenia systemu)"
LEVELS = ["znacznie poniżej oczekiwań", "poniżej oczekiwań", "na poziomie oczekiwań", "powyżej oczekiwań",
          "znacznie powyżej oczekiwań"]


def _user_of(session: Session, employee_id: int | None) -> User | None:
    if employee_id is None:
        return None
    return session.exec(select(User).where(User.employee_id == employee_id)).first()


# ------------------------------------------------------------------ schemat urzędu


class DepartmentIn(BaseModel):
    name: str = Field(min_length=3)


@router.post("/admin/departments", status_code=201)
def add_department(body: DepartmentIn, user: User = Depends(hr_only), session: Session = Depends(get_session)):
    office = session.exec(select(Office)).first()
    if office is None:
        raise HTTPException(409, "Brak urzędu w bazie")
    if session.exec(select(Department).where(Department.name == body.name)).first():
        raise HTTPException(409, "Taka komórka już istnieje")
    d = Department(office_id=office.id, name=body.name)
    session.add(d)
    session.flush()
    audit(session, user, "create", "department", d.id, name=body.name)
    session.commit()
    return {"id": d.id, "name": d.name}


@router.patch("/admin/departments/{department_id}")
def rename_department(department_id: int, body: DepartmentIn, user: User = Depends(hr_only),
                      session: Session = Depends(get_session)):
    d = session.get(Department, department_id)
    if d is None:
        raise HTTPException(404, "Nie ma takiej komórki")
    old, d.name = d.name, body.name
    session.add(d)
    audit(session, user, "rename", "department", d.id, old=old, new=body.name)
    session.commit()
    return {"id": d.id, "name": d.name}


@router.get("/admin/departments")
def departments(user: User = Depends(hr_only), session: Session = Depends(get_session)):
    out = []
    for d in session.exec(select(Department).order_by(Department.name)).all():
        staff = session.exec(select(Employee).where(Employee.department_id == d.id, Employee.active)).all()
        heads = [e for e in staff if e.sheet_type in ("A", "B") and not any(x.id == e.manager_id for x in staff)]
        out.append({"id": d.id, "name": d.name, "employees": len(staff),
                    "head": heads[0].full_name if heads else None})
    return out


# ------------------------------------------------------------------ zastępstwa


class SubstitutionIn(BaseModel):
    absent_employee_id: int
    deputy_employee_id: int
    start: date
    end: date
    note: str = ""


def _sub_out(session: Session, s: Substitution) -> dict:
    a, d = session.get(Employee, s.absent_employee_id), session.get(Employee, s.deputy_employee_id)
    today = date.today()
    return {"id": s.id, "absent_employee_id": s.absent_employee_id, "absent_name": a.full_name if a else "",
            "deputy_employee_id": s.deputy_employee_id, "deputy_name": d.full_name if d else "",
            "start": s.start.isoformat(), "end": s.end.isoformat(), "note": s.note,
            "active": s.start <= today <= s.end}


@router.get("/admin/substitutions")
def list_substitutions(user: User = Depends(hr_only), session: Session = Depends(get_session)):
    rows = session.exec(select(Substitution).order_by(Substitution.start.desc())).all()
    return [_sub_out(session, s) for s in rows]


@router.post("/admin/substitutions", status_code=201)
def add_substitution(body: SubstitutionIn, user: User = Depends(hr_only), session: Session = Depends(get_session)):
    if body.end < body.start:
        raise HTTPException(422, "Koniec zastępstwa przed jego początkiem")
    if body.absent_employee_id == body.deputy_employee_id:
        raise HTTPException(422, "Zastępca musi być inną osobą")
    absent, deputy = session.get(Employee, body.absent_employee_id), session.get(Employee, body.deputy_employee_id)
    if absent is None or deputy is None:
        raise HTTPException(404, "Nie ma takiego pracownika")
    deputy_user = _user_of(session, deputy.id)
    if deputy_user is None:
        raise HTTPException(422, "Zastępca nie ma konta w systemie - utwórz je w Kadrach")
    if deputy_user.role == "employee":
        deputy_user.role = "manager"  # zastępca dostaje widok „Mój zespół” na czas zastępstwa
        session.add(deputy_user)
    s = Substitution(**body.model_dump())
    session.add(s)
    session.flush()
    team = session.exec(select(Employee).where(Employee.manager_id == absent.id, Employee.active)).all()
    notify(session, deputy_user.id, f"Zastępstwo: przejmujesz zespół - {absent.full_name}",
           f"Od {body.start.isoformat()} do {body.end.isoformat()} pełnisz zadania oceniającego wobec "
           f"{len(team)} osób. Oceny prowadzi się na wcześniej wybranych kryteriach (§ 9 ust. 3 rozporządzenia).",
           "/team")
    for e in team:
        u = _user_of(session, e.id)
        if u:
            notify(session, u.id, "Zastępstwo przełożonego",
                   f"Od {body.start.isoformat()} do {body.end.isoformat()} sprawy oceny okresowej prowadzi "
                   f"{deputy.full_name} (zastępstwo za {absent.full_name}).", "/me")
    audit(session, user, "create", "substitution", s.id, absent=absent.id, deputy=deputy.id)
    session.commit()
    session.refresh(s)
    return _sub_out(session, s)


@router.delete("/admin/substitutions/{substitution_id}")
def end_substitution(substitution_id: int, user: User = Depends(hr_only), session: Session = Depends(get_session)):
    s = session.get(Substitution, substitution_id)
    if s is None:
        raise HTTPException(404, "Nie ma takiego zastępstwa")
    session.delete(s)
    audit(session, user, "delete", "substitution", substitution_id)
    session.commit()
    return {"deleted": substitution_id}


# ------------------------------------------------------------------ historia ocen i oceny historyczne


def _history(session: Session, employee_id: int) -> list[dict]:
    rows = session.exec(select(Review, ReviewCycle).join(ReviewCycle, ReviewCycle.id == Review.cycle_id)
                        .where(Review.employee_id == employee_id).order_by(ReviewCycle.period_start.desc())).all()
    return [{"id": r.id, "cycle_name": c.name, "status": r.status, "result": r.result, "level": r.overall_level,
             "average": r.overall_score, "drawn_up": drawn_up_date(r).isoformat() if r.status in DONE else None,
             "acknowledged_at": r.acknowledged_at.isoformat() if r.acknowledged_at else None,
             "historical": c.name == HISTORICAL_CYCLE} for r, c in rows]


@router.get("/admin/employees/{employee_id}/reviews")
def review_history(employee_id: int, user: User = Depends(hr_only), session: Session = Depends(get_session)):
    """Wgląd w historię ocen (bez szkiców - komórka kadrowa widzi oceny sporządzone)."""
    return [h for h in _history(session, employee_id) if h["status"] in DONE or h["historical"]]


class HistoricalIn(BaseModel):
    drawn_up: date  # data sporządzenia oceny na piśmie
    acknowledged_at: date | None = None
    result: Literal["pozytywna", "negatywna"]
    level: str
    average: float | None = Field(default=None, ge=1, le=9)
    note: str = ""


def historical_cycle(session: Session) -> ReviewCycle:
    c = session.exec(select(ReviewCycle).where(ReviewCycle.name == HISTORICAL_CYCLE)).first()
    if c is None:
        c = ReviewCycle(name=HISTORICAL_CYCLE, period_start=date(1990, 1, 1), period_end=date(1990, 1, 1),
                        status="closed")
        session.add(c)
        session.flush()
    return c


@router.post("/admin/employees/{employee_id}/historical-reviews", status_code=201)
def add_historical(employee_id: int, body: HistoricalIn, user: User = Depends(hr_only),
                   session: Session = Depends(get_session)):
    """Ocena sprzed wdrożenia systemu - podstawa terminów (art. 81 ust. 4 i 9, § 7), art. 71 i art. 89."""
    emp = session.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(404, "Nie ma takiego pracownika")
    if body.level not in LEVELS:
        raise HTTPException(422, "Nieznany poziom oceny")
    if body.drawn_up > date.today():
        raise HTTPException(422, "Data sporządzenia nie może być z przyszłości")
    if body.average is not None and overall_level(body.average) != body.level:
        raise HTTPException(422, f"Średnia {body.average} odpowiada poziomowi „{overall_level(body.average)}” (§ 11 ust. 1 pkt 2)")
    cycle = historical_cycle(session)
    r = Review(employee_id=emp.id, reviewer_id=user.id, cycle_id=cycle.id, status="acknowledged",
               sheet_type=emp.sheet_type, period_start=dl.add_months(body.drawn_up, -24), period_end=body.drawn_up,
               result=body.result, overall_level=body.level, overall_score=body.average,
               reviewer_signed_at=body.drawn_up, acknowledged_at=body.acknowledged_at or body.drawn_up,
               conversation_date=body.drawn_up, promotion_request="nie" if emp.is_civil_servant else "nie_dotyczy",
               ipr_conclusions=f"Ocena wprowadzona z dokumentacji papierowej. {body.note}".strip(),
               justification=body.note)
    session.add(r)
    session.flush()
    # terminy trwających ocen zależą od poprzedniej oceny - przeliczamy (bez ręcznych zmian terminu)
    changed = []
    for cur in session.exec(select(Review).where(Review.employee_id == emp.id, Review.status.in_(ACTIVE))).all():
        if any("art. 81 ust. 8" in h.get("reason", "") for h in cur.due_date_history):
            continue
        new = compute_due_date(session, cur)
        if new != cur.due_date:
            cur.due_date_history = [*cur.due_date_history, {
                "from": cur.due_date.isoformat() if cur.due_date else None, "date": new.isoformat(),
                "reason": "przeliczenie po wprowadzeniu oceny historycznej (art. 81 ust. 4/9)",
                "at": date.today().isoformat()}]
            cur.due_date = new
            session.add(cur)
            changed.append({"review_id": cur.id, "due_date": new.isoformat()})
    audit(session, user, "create_historical", "review", r.id, employee_id=emp.id)
    session.commit()
    return {"id": r.id, "due_dates_changed": changed, "history": _history(session, emp.id)}


# ------------------------------------------------------------------ import z systemu kadrowego


class ImportIn(BaseModel):
    csv: str = Field(min_length=10)
    dry_run: bool = True


COLUMNS = ["imie_nazwisko", "stanowisko", "komorka", "przelozony", "arkusz", "podstawa_zatrudnienia",
           "data_zatrudnienia", "email"]
CONTRACTS = {"mianowanie": "mianowanie", "nieokreslony": "nieokreslony", "nieokreślony": "nieokreslony",
             "czas nieokreślony": "nieokreslony", "okreslony": "okreslony", "określony": "okreslony",
             "czas określony": "okreslony"}


@router.post("/admin/import/employees")
def import_employees(body: ImportIn, user: User = Depends(hr_only), session: Session = Depends(get_session)):
    """Dane nowych pracowników z systemu kadrowego (CSV, separator ; lub ,). Najpierw podgląd z weryfikacją
    (dry_run=true), potem zapis tylko poprawnych wierszy (dry_run=false)."""
    sample = body.csv.splitlines()[0] if body.csv.strip() else ""
    delim = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(body.csv.strip()), delimiter=delim)
    missing = [c for c in COLUMNS[:5] if c not in (reader.fieldnames or [])]
    if missing:
        raise HTTPException(422, f"Brak kolumn: {', '.join(missing)}. Wymagane: {', '.join(COLUMNS)}")
    depts = {d.name.lower(): d for d in session.exec(select(Department)).all()}
    people = {e.full_name.lower(): e for e in session.exec(select(Employee).where(Employee.active)).all()}
    emails = {u.email.lower() for u in session.exec(select(User)).all()}
    rows, seen = [], set()
    for i, raw in enumerate(reader, start=2):
        r = {k: (v or "").strip() for k, v in raw.items() if k}
        errors, warnings = [], []
        name = r.get("imie_nazwisko", "")
        if len(name.split()) < 2:
            errors.append("podaj imię i nazwisko")
        if name.lower() in people or name.lower() in seen:
            errors.append("pracownik o tym imieniu i nazwisku już istnieje")
        dept = depts.get(r.get("komorka", "").lower())
        if dept is None:
            errors.append(f"nieznana komórka „{r.get('komorka', '')}” - dodaj ją w schemacie urzędu")
        mgr_name = r.get("przelozony", "")
        mgr = people.get(mgr_name.lower()) if mgr_name else None
        if mgr_name and mgr is None:
            errors.append(f"nieznany przełożony „{mgr_name}”")
        sheet = r.get("arkusz", "C").upper() or "C"
        if sheet not in ("A", "B", "C"):
            errors.append("arkusz musi być A, B albo C")
        contract = CONTRACTS.get(r.get("podstawa_zatrudnienia", "nieokreslony").lower() or "nieokreslony")
        if contract is None:
            errors.append("podstawa zatrudnienia: mianowanie / nieokreślony / określony")
        start = None
        if r.get("data_zatrudnienia"):
            try:
                start = date.fromisoformat(r["data_zatrudnienia"])
            except ValueError:
                errors.append("data zatrudnienia w formacie RRRR-MM-DD")
        email = r.get("email", "").lower()
        if email and email in emails:
            errors.append("konto z tym adresem e-mail już istnieje")
        if contract == "okreslony":
            warnings.append("umowa na czas określony - nie podlega ocenie okresowej (art. 81 ust. 1)")
        if sheet == "C" and mgr is None:
            warnings.append("brak przełożonego - nikt nie będzie oceniającym")
        seen.add(name.lower())
        rows.append({"row": i, "full_name": name, "position": r.get("stanowisko", ""),
                     "department": dept.name if dept else r.get("komorka", ""), "manager": mgr.full_name if mgr else None,
                     "sheet_type": sheet, "contract_type": contract, "employment_start": start.isoformat() if start else None,
                     "email": email or None, "errors": errors, "warnings": warnings,
                     "_dept": dept, "_mgr": mgr, "_start": start})
    created = 0
    if not body.dry_run:
        for r in rows:
            if r["errors"]:
                continue
            e = Employee(full_name=r["full_name"], position=r["position"] or "-", department_id=r["_dept"].id,
                         manager_id=r["_mgr"].id if r["_mgr"] else None, sheet_type=r["sheet_type"],
                         contract_type=r["contract_type"], is_civil_servant=r["contract_type"] == "mianowanie",
                         employment_start=r["_start"])
            session.add(e)
            session.flush()
            if r["email"]:
                session.add(User(email=r["email"], full_name=e.full_name, password_hash=hash_password(secrets.token_urlsafe(12)),
                                 role="manager" if e.sheet_type in ("A", "B") else "employee", employee_id=e.id))
            session.flush()
            start_for_new_employee(session, e)
            created += 1
        audit(session, user, "import", "employee", None, created=created, rows=len(rows))
        session.commit()
    for r in rows:
        for k in ("_dept", "_mgr", "_start"):
            r.pop(k)
    return {"dry_run": body.dry_run, "rows": rows, "valid": sum(1 for r in rows if not r["errors"]), "created": created}


@router.get("/admin/import/template.csv")
def import_template(user: User = Depends(hr_only)):
    body = ";".join(COLUMNS) + "\n" + ";".join([
        "Jan Przykładowy", "Inspektor ds. kontroli", "Wydział Cyfryzacji", "Marek Zieliński", "C", "nieokreślony",
        "2026-12-01", "jan.przykladowy@demo.gov.pl"]) + "\n"
    return Response("﻿" + body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="import_pracownikow_wzor.csv"'})


# ------------------------------------------------------------------ zestawienia: archiwizacja / kontrola


@router.get("/admin/export/reviews.csv")
def export_reviews(date_from: date | None = None, date_to: date | None = None, user: User = Depends(hr_only),
                   session: Session = Depends(get_session)):
    """Zestawienie sporządzonych ocen do archiwizacji lub kontroli (CSV, Excel otworzy je bezpośrednio)."""
    crit = {c.id: c for c in session.exec(select(Criterion).order_by(Criterion.order)).all()}
    depts = {d.id: d.name for d in session.exec(select(Department)).all()}
    users = {u.id: u.full_name for u in session.exec(select(User)).all()}
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["id_oceny", "pracownik", "komorka", "stanowisko", "arkusz", "podstawa_zatrudnienia", "oceniajacy",
                "cykl", "okres_od", "okres_do", "data_rozmowy_oceniajacej", "data_sporzadzenia", "data_zapoznania",
                "fikcja_zapoznania", "srednia", "poziom", "ocena", "oceny_czastkowe", "uzasadnienie", "wnioski_ipr",
                "wniosek_o_stopien", "sprzeciw", "rozstrzygniecie_sprzeciwu", "status"])
    q = select(Review, Employee, ReviewCycle).join(Employee, Employee.id == Review.employee_id) \
        .join(ReviewCycle, ReviewCycle.id == Review.cycle_id).where(Review.status.in_(DONE))
    n = 0
    for r, e, c in session.exec(q.order_by(Employee.full_name)).all():
        drawn = drawn_up_date(r)
        if (date_from and drawn < date_from) or (date_to and drawn > date_to):
            continue
        scores = session.exec(select(ReviewCriterion).where(ReviewCriterion.review_id == r.id)).all()
        w.writerow([r.id, e.full_name, depts.get(e.department_id, ""), e.position, r.sheet_type, e.contract_type,
                    users.get(r.reviewer_id, ""), c.name, r.period_start, r.period_end, r.conversation_date or "",
                    drawn, r.acknowledged_at or "", "tak" if r.ack_fiction else "nie",
                    f"{r.overall_score:.2f}".replace(".", ",") if r.overall_score else "", r.overall_level or "",
                    r.result or "", " | ".join(f"{crit[s.criterion_id].name}: {s.score}" for s in scores
                                               if s.criterion_id in crit and s.score),
                    r.justification, r.ipr_conclusions, r.promotion_request, r.objection_at or "",
                    r.objection_decision or "", r.status])
        n += 1
    audit(session, user, "export", "review", None, rows=n, purpose="archiwizacja/kontrola")
    session.commit()
    return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="oceny_okresowe_{date.today().isoformat()}.csv"'})


# ------------------------------------------------------------------ zestawienia: sprawozdawczość


@router.get("/admin/export/statistics")
def export_statistics(year: int | None = None, user: User = Depends(hr_only), session: Session = Depends(get_session)):
    """Zestawienie zagregowane na potrzeby sprawozdawczości (JSON - do systemu sprawozdawczego lub raportu).
    Grupy mniejsze niż K osób są ukrywane (k-anonimowość)."""
    k = settings.k_anonymity
    q = select(Review, Employee).join(Employee, Employee.id == Review.employee_id).where(Review.status.in_(DONE))
    rows = [(r, e) for r, e in session.exec(q).all() if year is None or drawn_up_date(r).year == year]
    depts = {d.id: d.name for d in session.exec(select(Department)).all()}
    by_dept: dict[str, list[Review]] = defaultdict(list)
    for r, e in rows:
        by_dept[depts.get(e.department_id, "-")].append(r)

    def summary(rs: list[Review]) -> dict:
        if len(rs) < k:
            return {"n": len(rs), "hidden": True}
        scores = [r.overall_score for r in rs if r.overall_score]
        return {"n": len(rs), "hidden": False, "results": dict(Counter(r.result for r in rs)),
                "levels": dict(Counter(r.overall_level for r in rs)),
                "average": round(sum(scores) / len(scores), 2) if scores else None}

    today = date.today()
    active = session.exec(select(Review).where(Review.status.in_(ACTIVE))).all()
    return {
        "generated": today.isoformat(), "year": year, "k_anonymity": k,
        "total": summary([r for r, _ in rows]),
        "departments": {name: summary(rs) for name, rs in sorted(by_dept.items())},
        "process": {
            "reviews_in_progress": len(active),
            "overdue": sum(1 for r in active if r.due_date and r.due_date < today),
            "due_next_60_days": sum(1 for r in active if r.due_date and today <= r.due_date <= today + timedelta(days=60)),
            "objections": sum(1 for r, _ in rows if r.objection_at),
            "promotion_requests": sum(1 for r, _ in rows if r.promotion_request == "tak"),
            "ack_fiction": sum(1 for r, _ in rows if r.ack_fiction),
        },
    }
