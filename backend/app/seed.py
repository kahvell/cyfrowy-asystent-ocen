"""Seed: kryteria i skala z rozporządzenia, katalog szkoleń, przepisy do RAG oraz dane demo.

Uruchomienie ręczne:  python -m app.seed  (na pustej bazie)
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

from sqlmodel import Session, select

from app import demo_data as D
from app.ai.rag import backfill_embeddings, ingest_dir
from app.models import (
    Absence,
    AISuggestion,
    Criterion,
    Department,
    Employee,
    Note,
    NoteCriterion,
    Office,
    Review,
    ReviewCriterion,
    ReviewCycle,
    SelfAssessment,
    Training,
    User,
    utcnow,
)
from app.security import hash_password
from app.services import deadlines as dl
from app.services.process import init_deadlines, prefill_previous
from app.services.scoring import compute_outcome

SEED_DIR = Path(__file__).resolve().parents[1] / "seed"


def seed_reference(session: Session) -> None:
    if session.exec(select(Criterion)).first() is None:
        data = json.loads((SEED_DIR / "criteria.json").read_text(encoding="utf-8"))
        for i, c in enumerate(data["criteria"]):
            session.add(Criterion(
                code=c["code"], name=c["name"], description=" ".join(c["indicators"]),
                behavioral_indicators=c["indicators"], mandatory_for=c["mandatory_for"], keywords=c["keywords"],
                order=i,
            ))
    if session.exec(select(Training)).first() is None:
        data = json.loads((SEED_DIR / "trainings.json").read_text(encoding="utf-8"))
        for t in data["trainings"]:
            session.add(Training(**t))
    session.commit()

    ingest_dir(session, SEED_DIR / "legal")  # tylko nowe dokumenty
    backfill_embeddings(session)


def _snap(x: float) -> int:
    return min((1, 3, 5, 7, 9), key=lambda v: abs(v - x))


def seed_demo(session: Session) -> None:
    rnd = random.Random(2026)
    pw = hash_password(D.DEMO_PASSWORD)
    crit = {c.code: c for c in session.exec(select(Criterion)).all()}
    mandatory_c = [c for c in crit.values() if "C" in c.mandatory_for]

    office = Office(name=D.OFFICE, city=D.OFFICE_CITY)
    session.add(office)
    session.flush()
    prev = ReviewCycle(name=D.PREV_CYCLE[0], period_start=D.PREV_CYCLE[1], period_end=D.PREV_CYCLE[2], status="closed")
    cur = ReviewCycle(name=D.CUR_CYCLE[0], period_start=D.CUR_CYCLE[1], period_end=D.CUR_CYCLE[2], status="open")
    session.add_all([prev, cur])
    session.flush()

    employees: dict[str, Employee] = {}
    managers: dict[str, User] = {}
    for dept_def in D.DEPARTMENTS:
        dept = Department(office_id=office.id, name=dept_def["name"])
        session.add(dept)
        session.flush()
        hname, hgender, hpos = dept_def["head"]
        # kierujący wydziałem w urzędzie wojewódzkim - wyższe stanowisko w służbie cywilnej (art. 52 pkt 2)
        head = Employee(full_name=hname, gender=hgender, position=hpos, department_id=dept.id, sheet_type="B",
                        is_civil_servant=True, senior_position=True,
                        position_description=f"Kierowanie komórką: {dept.name}.")
        session.add(head)
        session.flush()
        muser = User(email=dept_def["email"], full_name=hname, password_hash=pw, role="manager", employee_id=head.id)
        session.add(muser)
        session.flush()
        managers[dept_def["name"]] = muser
        for name, gender, pos, civil, desc in dept_def["staff"]:
            e = Employee(full_name=name, gender=gender, position=pos, department_id=dept.id, manager_id=head.id,
                         sheet_type="C", is_civil_servant=civil, position_description=desc,
                         employment_start=D.NEW_HIRES.get(name, date(2019, 3, 1)))
            if civil:
                e.appointment_year, e.civil_grade = rnd.choice([2015, 2017, 2019]), rnd.choice([2, 3, 4])
                e.civil_grade_date = date(2022, 12, 20)
            session.add(e)
            session.flush()
            employees[name] = e

        # --- poprzedni cykl: oceny sporządzone i przyjęte do wiadomości (dashboard, historia ocen) ---
        for name, *_ in dept_def["staff"]:
            if name in D.NEW_HIRES:
                continue
            e = employees[name]
            base = rnd.uniform(4.6, 7.0) + dept_def["bias"]
            r = Review(employee_id=e.id, reviewer_id=muser.id, cycle_id=prev.id, status="acknowledged", sheet_type="C",
                       period_start=prev.period_start, period_end=prev.period_end,
                       due_date=dl.review_due_date(prev.period_start), criteria_deadline=date(2023, 1, 2),
                       opening_conversation_date=date(2022, 12, 14), criteria_reviewer_confirmed_at=date(2022, 12, 14),
                       criteria_employee_confirmed_at=date(2022, 12, 15), criteria_reviewer_place=D.OFFICE_CITY,
                       criteria_employee_place=D.OFFICE_CITY, reviewer_place=D.OFFICE_CITY,
                       employee_place=D.OFFICE_CITY, conversation_date=date(2024, 11, 20),
                       reviewer_signed_at=date(2024, 11, 25), acknowledged_at=date(2024, 11, 27),
                       promotion_request="nie" if e.is_civil_servant else "nie_dotyczy",
                       submitted_at=utcnow(), finalized_at=utcnow(),
                       ipr_conclusions="Kontynuacja rozwoju w obszarze specjalistycznym (dane demonstracyjne).")
            session.add(r)
            session.flush()
            scores = []
            for c in mandatory_c:
                s = D.PREV_FIXED.get(name) or _snap(base + rnd.gauss(0, 1.3))
                scores.append(s)
                session.add(ReviewCriterion(review_id=r.id, criterion_id=c.id, score=s,
                                            justification="(ocena archiwalna - dane demonstracyjne)"))
            out = compute_outcome(scores)
            r.overall_score, r.overall_level, r.result = out.average, out.level, out.result
            if out.result == "negatywna":
                r.justification = "Uzasadnienie oceny negatywnej (dane demonstracyjne)."
            session.add(r)
            # historia użycia asystenta AI (do wskaźnika adopcji)
            for _ in range(2):
                status = rnd.choices(["accepted", "edited", "rejected"], weights=[5, 4, 1])[0]
                session.add(AISuggestion(review_id=r.id, kind="draft_justification", payload={"demo": True},
                                         model="ollama_chat/bielik (demo)", prompt_version="draft_justification.v1",
                                         status=status, decided_at=utcnow(), decided_by=muser.id))

    # --- konta pomocnicze ---
    anna = employees[D.EMPLOYEE_LOGIN[1]]
    session.add(User(email=D.EMPLOYEE_LOGIN[0], full_name=anna.full_name, password_hash=pw, role="employee",
                     employee_id=anna.id))
    session.add(User(email=D.HR_USER[0], full_name=D.HR_USER[1], password_hash=pw, role="hr"))
    session.add(User(email=D.ADMIN_USER[0], full_name=D.ADMIN_USER[1], password_hash=pw, role="admin"))
    session.flush()
    anna_user = session.exec(select(User).where(User.email == D.EMPLOYEE_LOGIN[0])).one()
    cyf_manager = managers["Wydział Cyfryzacji"]

    # --- dziennik obserwacji (bieżący cykl) ---
    for name, notes in D.NOTES.items():
        e = employees[name]
        for d, text, codes, sentiment, source in notes:
            n = Note(employee_id=e.id, author_id=anna_user.id if source == "self" else cyf_manager.id, date=d,
                     text=text, sentiment=sentiment, source=source, classified=True,
                     created_at=utcnow() - timedelta(days=(date.today() - d).days))
            session.add(n)
            session.flush()
            for i, code in enumerate(codes):
                session.add(NoteCriterion(note_id=n.id, criterion_id=crit[code].id, confidence=0.85 - 0.1 * i,
                                          assigned_by="ai"))

    # --- nieobecności (art. 81 ust. 7): zwolnienie + urlop bez przerwy -> termin oceny przedłużony ---
    for name, periods in D.ABSENCES.items():
        for start, end, kind in periods:
            session.add(Absence(employee_id=employees[name].id, start=start, end=end, kind=kind))
    session.flush()

    def current_review(e: Employee, status: str, additional: tuple[str, ...] = ()) -> Review:
        """Ocena w bieżącym cyklu; etap I (kryteria + rozmowa rozpoczynająca) potwierdzony, chyba że status=criteria."""
        r = Review(employee_id=e.id, reviewer_id=cyf_manager.id, cycle_id=cur.id, sheet_type="C", status=status,
                   period_start=max(cur.period_start, e.employment_start or cur.period_start),
                   period_end=cur.period_end, criteria_reviewer_place=D.OFFICE_CITY,
                   promotion_request="nie" if e.is_civil_servant else "nie_dotyczy")
        session.add(r)
        session.flush()
        init_deadlines(session, r)
        r.period_end = r.due_date
        if status != "criteria":
            r.opening_conversation_date = date(2024, 12, 10)
            r.opening_notes = D.OPENING_NOTES.get(e.full_name, "")
            r.criteria_reviewer_confirmed_at, r.criteria_employee_confirmed_at = date(2024, 12, 10), date(2024, 12, 11)
            r.criteria_employee_place = D.OFFICE_CITY
        if status in ("draft", "submitted", "discussed"):
            r.period_start = r.criteria_employee_confirmed_at  # „okres od” (objaśnienie 6 do arkusza)
            prefill_previous(session, r)
            if e.is_civil_servant:
                r.appointment_year, r.civil_grade = e.appointment_year, e.civil_grade
                r.civil_grade_date = e.civil_grade_date
        for c in mandatory_c:
            session.add(ReviewCriterion(review_id=r.id, criterion_id=c.id))
        for code in additional:
            session.add(ReviewCriterion(review_id=r.id, criterion_id=crit[code].id, is_additional=True))
        session.add(r)
        session.flush()
        return r

    # --- bieżący cykl: ocena Anny (szkic + samoocena) ---
    r_anna = current_review(anna, "draft", ("KREATYWNOSC",))
    session.add(SelfAssessment(
        review_id=r_anna.id,
        items={str(crit[code].id): {"score": s, "comment": cm} for code, (s, cm) in D.ANNA_SELF["scores"].items()},
        summary=D.ANNA_SELF["summary"], submitted_at=utcnow(),
    ))

    # --- bieżący cykl: ocena Piotra (pisana „z pamięci” - do demo kontroli jakości) ---
    piotr = employees["Piotr Nowak"]
    r_p = current_review(piotr, "draft")
    for rc in session.exec(select(ReviewCriterion).where(ReviewCriterion.review_id == r_p.id)).all():
        c = session.get(Criterion, rc.criterion_id)
        rc.score = D.PIOTR_REVIEW["scores"][c.code]
        rc.justification = D.PIOTR_REVIEW["justifications"].get(c.code, "")
        session.add(rc)
    out = compute_outcome(list(D.PIOTR_REVIEW["scores"].values()))
    r_p.overall_score, r_p.overall_level = out.average, out.level
    session.add(r_p)

    # --- pozostałe etapy procesu do pokazania ---
    current_review(employees["Tomasz Wójcik"], "observation")  # długa nieobecność -> termin przesunięty
    current_review(employees["Magdalena Kamińska"], "observation", D.MAGDA_ADDITIONAL)
    current_review(employees["Jakub Lewandowski"], "criteria")  # nowa umowa: wyznacz kryteria w 30 dni
    session.commit()


def seed_all(session: Session) -> None:
    seed_reference(session)
    if session.exec(select(User)).first() is None:
        seed_demo(session)


if __name__ == "__main__":
    from app.db import engine, init_db

    init_db()
    with Session(engine) as s:
        seed_all(s)
    print("Seed zakończony.")
