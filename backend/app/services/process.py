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
                   "criteria_reviewer_place", "signature_method"}
EVALUATION_FIELDS = {"criteria", "justification", "ipr_conclusions", "conversation_date", "period_start",
                     "period_end", "prev_result", "prev_level", "prev_date", "promotion_request", "appointment_year",
                     "civil_grade", "civil_grade_date", "promotion_justification", "reviewer_place",
                     "signature_method", "objection_body"}
EVALUATION_STATUSES = {"draft", "submitted", "discussed"}

# Etapy bramkowane potwierdzeniem przez ocenianego: 1. kryteria, 4. rozmowa oceniająca, 6. zapoznanie z oceną.
# Dopiero potwierdzenie na bramce zamyka etap. Przejście przez etap bez potwierdzenia drugiej strony
# (np. „okres oceny” -> „przygotowanie oceny”) nie blokuje powrotu i zmian w etapie wcześniejszym.
GATE_STAGES = ("criteria", "submitted", "final")


def editable_fields(review: Review) -> set[str]:
    """Pola arkusza edytowalne przez oceniającego przy bieżącym statusie (poza trybem korekty administratora).

    Etap I zamyka potwierdzenie wyznaczenia kryteriów przez oceniającego. Etapy „przygotowanie oceny”
    i „ocena na piśmie” (III i V) są edytowalne - a wraz z nimi etap IV, dopóki oceniany nie potwierdził
    terminu rozmowy. Blokady nie powoduje samo przejście do kolejnego etapu bez potwierdzenia drugiej strony.
    """
    allowed: set[str] = set()
    if review.status == "criteria" and review.criteria_reviewer_confirmed_at is None:
        allowed |= CRITERIA_FIELDS
    if review.status in ("draft", "discussed"):
        allowed |= EVALUATION_FIELDS
    elif review.status == "submitted" and not review.assessment_confirmed_at:
        # treść oceny (etap III) pozostaje otwarta do czasu potwierdzenia terminu rozmowy przez ocenianego;
        # samą datę rozmowy ustala się z chwilą jej odbycia (endpoint /discussed)
        allowed |= EVALUATION_FIELDS - {"conversation_date"}
    return allowed


def absences(session: Session, employee_id: int) -> list[dl.Period]:
    rows = session.exec(select(Absence).where(Absence.employee_id == employee_id)).all()
    return [dl.Period(a.start, a.end) for a in rows]


def office_of(session: Session, emp: Employee) -> Office | None:
    dept = session.get(Department, emp.department_id)
    return session.get(Office, dept.office_id) if dept else None


def previous_review(session: Session, review: Review) -> Review | None:
    """Ostatnia sporządzona ocena tego pracownika z wcześniejszego cyklu (kolejność cykli, nie dat okresu -
    „okres od-do” w arkuszu zmienia się w trakcie procesu)."""
    from sqlalchemy import func

    from app.models import ReviewCycle

    cur = session.get(ReviewCycle, review.cycle_id)
    q = (select(Review).join(ReviewCycle, ReviewCycle.id == Review.cycle_id)
         .where(Review.employee_id == review.employee_id, Review.id != review.id,
                Review.status.in_(["final", "acknowledged", "objection"]))
         # najpóźniej sporządzona (także oceny historyczne wprowadzone przez kadry)
         .order_by(func.coalesce(Review.reviewer_signed_at, Review.period_end).desc(), Review.id.desc()))
    if cur is not None:
        q = q.where(ReviewCycle.period_start < cur.period_start)
    return session.exec(q).first()


def drawn_up_date(r: Review) -> date:
    """Dzień sporządzenia oceny na piśmie (podpis oceniającego)."""
    return r.reviewer_signed_at or (r.finalized_at.date() if r.finalized_at else r.period_end)


def prefill_previous(session: Session, review: Review) -> None:
    """Dane poprzedniej oceny urzędnika - automatycznie z historii (pole edytowalne, gdy historii brak)."""
    prev = previous_review(session, review)
    if prev is None:
        return
    review.prev_result = prev.result
    review.prev_level = prev.overall_level
    review.prev_date = drawn_up_date(prev)


def obligatory_promotion(session: Session, review: Review) -> bool:
    """Art. 89 ust. 2: urzędnik z dwiema kolejnymi pozytywnymi ocenami na jednym z dwóch najwyższych poziomów
    otrzymuje kolejny stopień z mocy prawa (w terminie 30 dni od zapoznania z oceną)."""
    emp = session.get(Employee, review.employee_id)
    if not emp or not emp.is_civil_servant or (emp.civil_grade or 0) >= 9:
        return False
    if review.result != "pozytywna" or review.overall_level not in TOP_LEVELS:
        return False
    prev_level, prev_result, prev_date = review.prev_level, review.prev_result, review.prev_date
    prev = previous_review(session, review)
    if prev is not None:
        prev_level, prev_result, prev_date = prev.overall_level, prev.result, drawn_up_date(prev)
    # „od otrzymania ostatniego stopnia służbowego” - obie oceny muszą być sporządzone po przyznaniu stopnia
    if emp.civil_grade_date and (prev_date is None or prev_date < emp.civil_grade_date):
        return False
    return prev_result == "pozytywna" and prev_level in TOP_LEVELS


def second_negative_risk(session: Session, review: Review) -> bool:
    """Art. 71 ust. 1 pkt 1 ustawy: dwukrotna, następująca po sobie negatywna ocena okresowa urzędnika
    służby cywilnej skutkuje rozwiązaniem stosunku pracy (z 3-miesięcznym wypowiedzeniem)."""
    emp = session.get(Employee, review.employee_id)
    if not emp or not emp.is_civil_servant or review.result != "negatywna":
        return False
    prev = previous_review(session, review)
    prev_result = prev.result if prev is not None else review.prev_result
    return prev_result == "negatywna"


SECOND_NEGATIVE_WARNING = {
    "code": "second_negative", "severity": "warning", "criterion_id": None, "source": "rule", "evidence": [],
    "title": "Druga z rzędu ocena negatywna urzędnika (art. 71 ust. 1 pkt 1 ustawy)",
    "message": "Poprzednia ocena okresowa tego urzędnika służby cywilnej też była negatywna. Dwukrotna, następująca "
               "po sobie negatywna ocena skutkuje rozwiązaniem stosunku pracy z 3-miesięcznym wypowiedzeniem.",
    "suggestion": "Upewnij się, że uzasadnienie (§ 11 ust. 3) jest kompletne i oparte na faktach z całego okresu, "
                  "i skonsultuj sprawę z komórką kadrową przed sporządzeniem oceny na piśmie.",
}


def deadline_base(session: Session, review: Review) -> date:
    """Początek biegu terminów (art. 81 ust. 4, § 7 pkt 1): dzień sporządzenia na piśmie poprzedniej oceny,
    a przy pierwszej ocenie - dzień zatrudnienia na czas nieokreślony / mianowania.
    Nie mylić z polem „okres od” w arkuszu (data zapoznania z kryteriami, objaśnienie 6 do arkusza)."""
    from app.models import ReviewCycle

    prev = previous_review(session, review)
    if prev is not None:
        return drawn_up_date(prev)
    emp = session.get(Employee, review.employee_id)
    if emp and emp.employment_start:
        return emp.employment_start
    cycle = session.get(ReviewCycle, review.cycle_id)
    return cycle.period_start if cycle else review.period_start


def is_repeat_review(session: Session, review: Review) -> bool:
    """Ponowna ocena po ocenie negatywnej (art. 81 ust. 9) - termin sztywny: bez zmiany (art. 81 ust. 8)
    i bez przedłużania o nieobecności (poradnik KPRM, rozdz. 5)."""
    prev = previous_review(session, review)
    return bool(prev and prev.result == "negatywna")


def compute_due_date(session: Session, review: Review) -> date:
    """Termin sporządzenia oceny:
    - po ocenie negatywnej: 6 miesięcy od zapoznania się z nią (art. 81 ust. 9),
    - w pozostałych przypadkach: 24 miesiące od poprzedniej oceny / zatrudnienia (art. 81 ust. 4),
      przedłużone o nieobecności usprawiedliwione dłuższe niż miesiąc (art. 81 ust. 7)."""
    prev = previous_review(session, review)
    if prev is not None and prev.result == "negatywna":
        return dl.repeat_review_date(prev.acknowledged_at or drawn_up_date(prev))
    return dl.review_due_date(deadline_base(session, review), absences(session, review.employee_id))


def init_deadlines(session: Session, review: Review) -> None:
    """Termin wyznaczenia kryteriów (§ 7): 30 dni od sporządzenia poprzedniej oceny lub zatrudnienia,
    7 dni od sporządzenia oceny negatywnej; termin oceny wg compute_due_date."""
    prev = previous_review(session, review)
    review.criteria_deadline = dl.criteria_deadline(deadline_base(session, review), previous_negative=bool(
        prev and prev.result == "negatywna"))
    review.due_date = compute_due_date(session, review)


def review_deadlines(session: Session, review: Review, today: date | None = None) -> dict:
    today = today or date.today()
    repeat = is_repeat_review(session, review)
    out: dict = {
        "criteria_deadline": review.criteria_deadline.isoformat() if review.criteria_deadline else None,
        "due_date": review.due_date.isoformat() if review.due_date else None,
        "is_repeat_review": repeat,
        "can_change_due_date": not repeat and dl.can_change_due_date(deadline_base(session, review), today),
        "objection_deadline": None,
        "objection_open": False,
        "repeat_review_date": None,
        "obligatory_promotion": False,
        "promotion_deadline": None,
    }
    if review.acknowledged_at:
        od = dl.objection_deadline(review.acknowledged_at)
        out["objection_deadline"] = od.isoformat()
        # sprzeciw dotyczący wcześniejszej wersji oceny nie blokuje sprzeciwu od oceny sporządzonej po raz drugi
        # (art. 83 ust. 4)
        out["objection_open"] = review.status == "acknowledged" and today <= od and (
            not review.objection_at or review.objection_decision == "ponowne_sporzadzenie")
        if review.result == "negatywna":
            out["repeat_review_date"] = dl.repeat_review_date(review.acknowledged_at).isoformat()
        if obligatory_promotion(session, review):
            out["obligatory_promotion"] = True
            out["promotion_deadline"] = dl.promotion_deadline(review.acknowledged_at).isoformat()
    elif review.status == "final" and obligatory_promotion(session, review):
        out["obligatory_promotion"] = True
    out["termination_risk"] = second_negative_risk(session, review)
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
                   "objection_body": review.objection_body or (office.objection_body if office else
                                                               "dyrektora generalnego urzędu")},
        "employee_form": person(emp),
        "reviewer_form": person(reviewer, reviewer_user.full_name if reviewer_user else ""),
    }


ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"]
GRADE_NOM = ["", "pierwszy", "drugi", "trzeci", "czwarty", "piąty", "szósty", "siódmy", "ósmy", "dziewiąty"]


def grade_label(grade: int | None) -> str | None:
    """Stopień służbowy w formacie z arkusza KPRM, np. „III - trzeci”."""
    return f"{ROMAN[grade]} - {GRADE_NOM[grade]}" if grade and 1 <= grade <= 9 else None


def promotion_target(review: Review) -> str | None:
    if review.civil_grade and 1 <= review.civil_grade < 9:
        return GRADE_WORDS[review.civil_grade + 1]
    return None


def level_for(avg: float | None) -> str | None:
    return overall_level(avg) if avg is not None else None
