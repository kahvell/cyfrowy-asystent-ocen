"""Rozpoczęcie cyklu oceny okresowej - wg schematu procesu KPRM (BPMN):

- „wprowadza dane pracownika podlegającego ocenie” -> scheduler wysyła przypomnienie o wyznaczeniu kryteriów,
  oceniany otrzymuje informację o rozpoczęciu cyklu oceny,
- „dokonuje oceny i przekazuje do zapoznania” -> „koniec cyklu oceny i początek następnego”.

Cykl (ReviewCycle) to grupa ocen do raportowania; termin każdej oceny liczony jest indywidualnie od
poprzedniej oceny / zatrudnienia (app.services.process).
"""

from datetime import date

from sqlmodel import Session, select

from app.models import Criterion, Employee, Review, ReviewCriterion, ReviewCycle, User
from app.services import deadlines as dl
from app.services.notify import notify, notify_employee
from app.services.process import deadline_base, init_deadlines, office_of
from app.services.reviews import mandatory_criteria


class CycleError(Exception):
    pass


def subject_to_review(emp: Employee) -> bool:
    """Art. 81 ust. 1: urzędnik albo pracownik zatrudniony na czas nieokreślony, w aktywnym zatrudnieniu,
    z wyjątkiem osoby zajmującej wyższe stanowisko w służbie cywilnej (art. 52)."""
    return emp.active and emp.contract_type in ("mianowanie", "nieokreslony") and not emp.senior_position


def reviewer_user(session: Session, emp: Employee) -> User | None:
    if emp.manager_id is None:
        return None
    return session.exec(select(User).where(User.employee_id == emp.manager_id)).first()


def cycle_for(session: Session, emp: Employee, start: date) -> ReviewCycle:
    """Otwarty cykl obejmujący datę rozpoczęcia, w którym pracownik nie ma jeszcze oceny - albo nowy."""
    has = set(session.exec(select(Review.cycle_id).where(Review.employee_id == emp.id)).all())
    for c in session.exec(select(ReviewCycle).where(ReviewCycle.status == "open")
                          .order_by(ReviewCycle.period_start.desc())).all():
        if c.id not in has and c.period_start <= start <= c.period_end:
            return c
    end = dl.add_months(start, 24)
    for name in (f"Ocena {start.year}–{end.year}", f"Ocena {start:%m.%Y}–{end:%m.%Y}"):
        c = session.exec(select(ReviewCycle).where(ReviewCycle.name == name)).first()
        if c is None:
            c = ReviewCycle(name=name, period_start=start, period_end=end, status="open")
            session.add(c)
            session.flush()
            return c
        if c.id not in has:
            return c
    raise CycleError("Nie można dobrać cyklu oceny")


def start_review(session: Session, emp: Employee, reviewer: User, cycle: ReviewCycle | None = None,
                 additional: list[int] | None = None, *, start: date | None = None, announce: bool = True,
                 explicit: bool = False) -> Review:
    """Tworzy arkusz w etapie „wyznaczanie kryteriów” z terminami wg § 7 i art. 81 ust. 4/9.

    Wyższe stanowiska (art. 52): wg poradnika KPRM (rozdz. 3) nie podlegają ocenie okresowej, więc cykl nie
    startuje automatycznie; przykładowy arkusz B KPRM dla dyrektora departamentu pokazuje jednak praktykę
    oceniania - dlatego ręczne założenie oceny (explicit) jest dozwolone, z ostrzeżeniem w odpowiedzi API."""
    senior_ok = explicit and emp.senior_position and emp.active and emp.contract_type in ("mianowanie", "nieokreslony")
    if not subject_to_review(emp) and not senior_ok:
        raise CycleError("Ocenie okresowej podlegają urzędnicy służby cywilnej i pracownicy zatrudnieni na czas "
                         "nieokreślony (art. 81 ust. 1 ustawy). Osoba na umowie na czas określony podlega pierwszej "
                         "ocenie w służbie cywilnej (art. 37-38) - odrębny tryb.")
    cycle = cycle or cycle_for(session, emp, start or date.today())
    if session.exec(select(Review).where(Review.employee_id == emp.id, Review.cycle_id == cycle.id)).first():
        raise CycleError("Ocena dla tego pracownika w tym cyklu już istnieje")
    mandatory = mandatory_criteria(session, emp.sheet_type)
    mandatory_ids = {c.id for c in mandatory}
    extra = [cid for cid in dict.fromkeys(additional or []) if cid not in mandatory_ids]
    if any(session.get(Criterion, cid) is None for cid in extra):
        raise CycleError("Nieznane kryterium dodatkowe")
    office = office_of(session, emp)
    review = Review(employee_id=emp.id, reviewer_id=reviewer.id, cycle_id=cycle.id, sheet_type=emp.sheet_type,
                    status="criteria", period_start=cycle.period_start, period_end=cycle.period_end,
                    criteria_reviewer_place=office.city if office else "",
                    promotion_request="nie" if emp.is_civil_servant else "nie_dotyczy")
    session.add(review)
    session.flush()
    init_deadlines(session, review)
    review.period_start = deadline_base(session, review)
    review.period_end = review.due_date or review.period_end
    for c in mandatory:
        session.add(ReviewCriterion(review_id=review.id, criterion_id=c.id))
    for cid in extra:
        session.add(ReviewCriterion(review_id=review.id, criterion_id=cid, is_additional=True))
    session.add(review)
    if announce:
        crit = review.criteria_deadline.isoformat() if review.criteria_deadline else "-"
        notify(session, reviewer.id, f"Wyznacz kryteria oceny: {emp.full_name}",
               f"Rozpoczął się cykl oceny okresowej. Rozmowa rozpoczynająca i kryteria do {crit} (§ 5-7 rozporządzenia).",
               f"/reviews/{review.id}")
        notify_employee(session, review, "Rozpoczął się cykl oceny okresowej",
                        f"Termin sporządzenia oceny: {review.due_date.isoformat() if review.due_date else '-'}. "
                        "Przełożony zaprosi Cię na rozmowę o obowiązkach, kryteriach i oczekiwaniach.")
    return review


def start_next_cycle(session: Session, finished: Review) -> Review | None:
    """„Koniec cyklu oceny i początek następnego” - po sporządzeniu oceny na piśmie."""
    emp = session.get(Employee, finished.employee_id)
    reviewer = reviewer_user(session, emp) if emp else None
    if emp is None or reviewer is None or not subject_to_review(emp):
        return None
    nxt = session.exec(select(Review).where(Review.employee_id == emp.id, Review.id != finished.id,
                                            Review.status.in_(["criteria", "observation", "draft", "submitted",
                                                               "discussed"]))).first()
    if nxt is not None:
        if nxt.status == "criteria" and not nxt.criteria_reviewer_confirmed_at:
            init_deadlines(session, nxt)  # ocena sporządzona ponownie (np. po sprzeciwie) - nowe terminy
            nxt.period_start = deadline_base(session, nxt)
            session.add(nxt)
        return None
    start = finished.reviewer_signed_at or date.today()
    try:
        return start_review(session, emp, reviewer, start=start)
    except CycleError:
        return None


def start_for_new_employee(session: Session, emp: Employee) -> Review | None:
    """„Wprowadza dane pracownika podlegającego ocenie” -> początek pierwszego cyklu."""
    reviewer = reviewer_user(session, emp)
    if reviewer is None or not subject_to_review(emp):
        return None
    try:
        return start_review(session, emp, reviewer, start=emp.employment_start or date.today())
    except CycleError:
        return None
