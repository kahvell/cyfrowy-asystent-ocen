"""Proces oceny okresowej wg ustawy o służbie cywilnej (art. 81, 83, 89) i rozporządzenia (§ 5, 10, 11).

Etapy (statusy Review):
  criteria      - wyznaczenie kryteriów, termin oceny, rozmowa rozpoczynająca; potwierdzenia obu stron (§ 5)
  observation   - okres oceny: dziennik obserwacji, bieżąca informacja zwrotna
  draft         - przygotowanie oceny (asystent AI, kontrola jakości)
  submitted     - gotowa do rozmowy oceniającej
  discussed     - po rozmowie oceniającej (§ 10), ocenę można skorygować (§ 11 ust. 2)
  final         - sporządzona na piśmie, podpisana przez oceniającego, przekazana ocenianemu
  acknowledged  - oceniany zapoznał się z oceną (albo stwierdzono fikcję zapoznania)
  objection     - wniesiono sprzeciw do dyrektora generalnego (art. 83)
"""

from datetime import date

from sqlmodel import Session, select

from app.models import Absence, Department, Employee, Office, Review, User
from app.services import deadlines as dl
from app.services.scoring import overall_level

STAGES = ["criteria", "observation", "draft", "submitted", "discussed", "final", "acknowledged"]
TOP_LEVELS = {"powyżej oczekiwań", "znacznie powyżej oczekiwań"}  # dwa najwyższe poziomy (art. 89 ust. 2)
GRADE_WORDS = ["", "pierwszego", "drugiego", "trzeciego", "czwartego", "piątego", "szóstego", "siódmego", "ósmego",
               "dziewiątego"]

# pola edytowalne na danym etapie - wg „schematu pól formularza” (KPRM)
CRITERIA_FIELDS = {"additional_criterion_ids", "due_date", "opening_conversation_date", "opening_notes",
                   "criteria_reviewer_place"}
EVALUATION_FIELDS = {"criteria", "justification", "ipr_conclusions", "conversation_date", "period_start",
                     "period_end", "prev_result", "prev_level", "prev_date", "promotion_request", "appointment_year",
                     "civil_grade", "civil_grade_date", "promotion_justification", "reviewer_place"}
EVALUATION_STATUSES = {"draft", "submitted", "discussed"}


def absences(session: Session, employee_id: int) -> list[dl.Period]:
    rows = session.exec(select(Absence).where(Absence.employee_id == employee_id)).all()
    return [dl.Period(a.start, a.end) for a in rows]


def office_of(session: Session, emp: Employee) -> Office | None:
    dept = session.get(Department, emp.department_id)
    return session.get(Office, dept.office_id) if dept else None


def previous_review(session: Session, review: Review) -> Review | None:
    """Ostatnia zakończona ocena tego pracownika sprzed bieżącej."""
    q = (select(Review)
         .where(Review.employee_id == review.employee_id, Review.id != review.id,
                Review.status.in_(["final", "acknowledged"]), Review.period_end <= review.period_start)
         .order_by(Review.period_end.desc()))
    return session.exec(q).first()


def prefill_previous(session: Session, review: Review) -> None:
    """Dane poprzedniej oceny urzędnika - automatycznie z historii (pole edytowalne, gdy historii brak)."""
    prev = previous_review(session, review)
    if prev is None:
        return
    review.prev_result = prev.result
    review.prev_level = prev.overall_level
    review.prev_date = prev.reviewer_signed_at or (prev.finalized_at.date() if prev.finalized_at else prev.period_end)


def obligatory_promotion(session: Session, review: Review) -> bool:
    """Art. 89 ust. 2: urzędnik z dwiema kolejnymi pozytywnymi ocenami na jednym z dwóch najwyższych poziomów
    otrzymuje kolejny stopień z mocy prawa (w terminie 30 dni od zapoznania z oceną)."""
    emp = session.get(Employee, review.employee_id)
    if not emp or not emp.is_civil_servant or (emp.civil_grade or 0) >= 9:
        return False
    if review.result != "pozytywna" or review.overall_level not in TOP_LEVELS:
        return False
    prev_level = review.prev_level
    prev_result = review.prev_result
    prev = previous_review(session, review)
    if prev is not None:
        prev_level, prev_result = prev.overall_level, prev.result
    return prev_result == "pozytywna" and prev_level in TOP_LEVELS


def init_deadlines(session: Session, review: Review) -> None:
    prev = previous_review(session, review)
    review.criteria_deadline = dl.criteria_deadline(review.period_start, previous_negative=bool(
        prev and prev.result == "negatywna"))
    review.due_date = dl.review_due_date(review.period_start, absences(session, review.employee_id))


def review_deadlines(session: Session, review: Review, today: date | None = None) -> dict:
    today = today or date.today()
    out: dict = {
        "criteria_deadline": review.criteria_deadline.isoformat() if review.criteria_deadline else None,
        "due_date": review.due_date.isoformat() if review.due_date else None,
        "can_change_due_date": dl.can_change_due_date(review.period_start, today),
        "objection_deadline": None,
        "objection_open": False,
        "repeat_review_date": None,
        "obligatory_promotion": False,
        "promotion_deadline": None,
    }
    if review.acknowledged_at:
        od = dl.objection_deadline(review.acknowledged_at)
        out["objection_deadline"] = od.isoformat()
        out["objection_open"] = review.status == "acknowledged" and today <= od and not review.objection_at
        if review.result == "negatywna":
            out["repeat_review_date"] = dl.repeat_review_date(review.acknowledged_at).isoformat()
        if obligatory_promotion(session, review):
            out["obligatory_promotion"] = True
            out["promotion_deadline"] = dl.promotion_deadline(review.acknowledged_at).isoformat()
    elif review.status == "final" and obligatory_promotion(session, review):
        out["obligatory_promotion"] = True
    return out


def form_people(session: Session, review: Review) -> dict:
    """Dane do części I i II arkusza (uzupełniane automatycznie ze struktury i bazy pracowników)."""
    emp = session.get(Employee, review.employee_id)
    reviewer_user = session.get(User, review.reviewer_id)
    reviewer = session.get(Employee, reviewer_user.employee_id) if reviewer_user and reviewer_user.employee_id else None
    office = office_of(session, emp)

    def person(e: Employee | None, fallback: str = "") -> dict:
        name = e.full_name if e else fallback
        first, _, last = name.partition(" ")
        dept = session.get(Department, e.department_id) if e else None
        return {"first_name": first, "last_name": last, "full_name": name,
                "department": dept.name if dept else "", "position": e.position if e else ""}

    return {
        "office": {"name": office.name if office else "", "city": office.city if office else "",
                   "objection_body": office.objection_body if office else "dyrektora generalnego urzędu"},
        "employee_form": person(emp),
        "reviewer_form": person(reviewer, reviewer_user.full_name if reviewer_user else ""),
    }


def promotion_target(review: Review) -> str | None:
    if review.civil_grade and 1 <= review.civil_grade < 9:
        return GRADE_WORDS[review.civil_grade + 1]
    return None


def level_for(avg: float | None) -> str | None:
    return overall_level(avg) if avg is not None else None
