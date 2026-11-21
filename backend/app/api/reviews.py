"""Arkusz oceny (A/B/C), pełny proces oceny okresowej i samoocena.

Kolejność etapów i to, kiedy które pole arkusza można edytować, odwzorowują „schemat pól formularza”
oraz przypadki użycia KPRM - szczegóły w app/services/process.py.
"""

import unicodedata
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.analytics.quality_rules import has_critical
from app.db import get_session
from app.models import (
    AuditLog,
    Criterion,
    DueDateRequest,
    Employee,
    Review,
    ReviewCriterion,
    ReviewCycle,
    SelfAssessment,
    User,
    utcnow,
)
from app.security import get_current_user
from app.services import deadlines as dl
from app.services.access import ensure_employee_access, get_review_for, is_manager_of, is_reviewer
from app.services.audit import audit
from app.services.cycle import CycleError, start_next_cycle, start_review
from app.services.form_pdf import render_review_pdf
from app.services.notify import notify_employee, notify_hr, notify_reviewer
from app.services.process import (
    CRITERIA_FIELDS,
    EVALUATION_FIELDS,
    EVALUATION_STATUSES,
    deadline_base,
    editable_fields,
    is_repeat_review,
    obligatory_promotion,
    office_of,
    prefill_previous,
    promotion_target,
    second_negative_risk,
)
from app.services.reviews import (
    all_criteria,
    mandatory_criteria,
    notes_for_review,
    recompute,
    review_entries,
    rule_warnings,
    serialize_note,
    serialize_review,
)
from app.services.scoring import MAX_ADDITIONAL_CRITERIA, VALID_SCORES

router = APIRouter(tags=["reviews"])


def _err(code: str, title: str, message: str, suggestion: str = "") -> dict:
    return {"code": code, "severity": "critical", "title": title, "message": message, "criterion_id": None,
            "suggestion": suggestion, "evidence": [], "source": "rule"}


class ReviewCreate(BaseModel):
    employee_id: int
    cycle_id: int
    additional_criterion_ids: list[int] = Field(default_factory=list, max_length=MAX_ADDITIONAL_CRITERIA)


@router.get("/reviews")
def list_reviews(employee_id: int | None = None, user: User = Depends(get_current_user),
                 session: Session = Depends(get_session)):
    q = select(Review, ReviewCycle, Employee).join(ReviewCycle, ReviewCycle.id == Review.cycle_id) \
        .join(Employee, Employee.id == Review.employee_id)
    if employee_id is not None:
        if user.role != "admin":
            ensure_employee_access(session, user, employee_id)
        q = q.where(Review.employee_id == employee_id)
    elif user.role == "manager":
        q = q.where(Review.reviewer_id == user.id)
    elif user.role == "admin":
        # administrator: lista arkuszy do trybu korekty (wyniki szkiców ukryte poniżej)
        pass
    elif user.role == "hr":
        # komórka kadrowa: dokumentacja ocen sporządzonych (bez szkiców i notatek)
        q = q.where(Review.status.in_(["final", "acknowledged", "objection"]))
    elif user.employee_id:
        q = q.where(Review.employee_id == user.employee_id)
    else:
        raise HTTPException(403, "Brak dostępu")
    return [
        {"id": r.id, "status": r.status, "employee_id": e.id, "employee_name": e.full_name, "cycle_name": c.name,
         "due_date": r.due_date.isoformat() if r.due_date else None,
         "overall_level": r.overall_level if is_reviewer(session, user, r) or r.status not in ("draft",) else None}
        for r, c, e in session.exec(q.order_by(ReviewCycle.period_start.desc())).all()
    ]


@router.post("/reviews", status_code=201)
def create_review(body: ReviewCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Rozpoczęcie cyklu oceny: arkusz wg stanowiska (A/B/C), kryteria obowiązkowe, termin oceny."""
    emp = session.get(Employee, body.employee_id)
    if emp is None:
        raise HTTPException(404, "Nie ma takiego pracownika")
    if not is_manager_of(session, user, emp.id):
        raise HTTPException(403, "Ocenę sporządza bezpośredni przełożony (art. 81 ust. 1 ustawy)")
    cycle = session.get(ReviewCycle, body.cycle_id)
    if cycle is None or cycle.status != "open":
        raise HTTPException(422, "Cykl oceny nie istnieje lub jest zamknięty")
    try:
        review = start_review(session, emp, user, cycle, body.additional_criterion_ids, explicit=True)
    except CycleError as exc:
        raise HTTPException(409 if "już istnieje" in str(exc) else 422, str(exc)) from exc
    audit(session, user, "create", "review", review.id, employee_id=emp.id)
    session.commit()
    session.refresh(review)
    out = serialize_review(session, review, viewer_is_reviewer=True)
    if emp.senior_position:
        out["notice"] = SENIOR_NOTICE
    return out


SENIOR_NOTICE = ("Oceniany zajmuje wyższe stanowisko w służbie cywilnej (art. 52). Wg poradnika KPRM (rozdz. 3) takie "
                 "osoby nie podlegają ocenie okresowej z art. 81 - cykl nie startuje automatycznie, a ocena założona "
                 "ręcznie ma charakter oceny wg praktyki urzędu; IPR nie jest sporządzany (art. 108).")


@router.get("/reviews/{review_id}")
def get_review(review_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id)
    audit(session, user, "view", "review", review.id)
    session.commit()
    return serialize_review(session, review, viewer_is_reviewer=is_reviewer(session, user, review))


@router.get("/reviews/{review_id}/evidence")
def review_evidence(review_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Notatki z okresu oceny - panel „dowody” w arkuszu."""
    review = get_review_for(session, user, review_id, manage=True)
    notes, tags = notes_for_review(session, review)
    crit = {c.id: c for c in all_criteria(session)}
    authors = {u.id: u for u in session.exec(select(User).where(User.id.in_({n.author_id for n in notes}))).all()}
    return [serialize_note(n, tags.get(n.id, []), crit, authors) for n in notes]


def _ascii(value: str) -> str:
    """Nazwa pliku w nagłówku HTTP musi być w ASCII (nagłówki kodowane latin-1)."""
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode() or "ocena"


@router.get("/reviews/{review_id}/form.pdf")
def review_form_pdf(review_id: int, user: User = Depends(get_current_user),
                    session: Session = Depends(get_session)):
    """Arkusz oceny (A/B/C) jako plik PDF - wzory: załączniki nr 2-4 rozporządzenia PRM (Dz.U. 2016 poz. 470)."""
    review = get_review_for(session, user, review_id)
    audit(session, user, "export", "review", review.id)
    session.commit()
    data = serialize_review(session, review, viewer_is_reviewer=is_reviewer(session, user, review))
    emp = session.get(Employee, review.employee_id)
    filename = f"arkusz-oceny-{review.sheet_type}-{review.id}-{_ascii(emp.full_name if emp else '')}.pdf"
    return Response(content=render_review_pdf(data), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


class CriterionPatch(BaseModel):
    criterion_id: int
    score: int | None = None
    justification: str | None = None
    source_note_ids: list[int] | None = None


class ReviewPatch(BaseModel):
    # Część I
    additional_criterion_ids: list[int] | None = Field(default=None, max_length=MAX_ADDITIONAL_CRITERIA)
    due_date: date | None = None
    opening_conversation_date: date | None = None
    opening_notes: str | None = None
    criteria_reviewer_place: str | None = None
    # Część II
    criteria: list[CriterionPatch] = Field(default_factory=list)
    justification: str | None = None
    ipr_conclusions: str | None = None
    conversation_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    prev_result: Literal["pozytywna", "negatywna", "brak"] | None = None
    prev_level: str | None = None
    prev_date: date | None = None
    promotion_request: Literal["tak", "nie", "nie_dotyczy"] | None = None
    reviewer_place: str | None = None
    signature_method: Literal["system", "wydruk", "elektroniczny"] | None = None
    objection_body: str | None = None  # arkusz A: organ, do którego służy sprzeciw
    # Część III
    appointment_year: int | None = Field(default=None, ge=1996, le=2100)
    civil_grade: int | None = Field(default=None, ge=1, le=9)
    civil_grade_date: date | None = None
    promotion_justification: str | None = None
    # tryb korekty błędów przez administratora (poza etapem edycji pola) - wymaga powodu
    correction_reason: str | None = Field(default=None, min_length=5)


@router.patch("/reviews/{review_id}")
def patch_review(review_id: int, body: ReviewPatch, user: User = Depends(get_current_user),
                 session: Session = Depends(get_session)):
    # administrator nie jest oceniającym - zmienia wyłącznie pola zablokowane na danym etapie, w trybie korekty
    correction = user.role == "admin"
    review = get_review_for(session, user, review_id, manage=not correction)
    sent = {k for k in body.model_fields_set if not (k == "criteria" and not body.criteria)} - {"correction_reason"}
    if correction and not body.correction_reason:
        raise HTTPException(409, "Administrator zmienia arkusz wyłącznie w trybie korekty błędów - podaj powód korekty.")
    if correction:
        allowed = (CRITERIA_FIELDS | EVALUATION_FIELDS) - editable_fields(review)
    else:
        allowed = editable_fields(review)
    blocked = sent - allowed
    if blocked:
        raise HTTPException(409, f"Na etapie „{review.status}” tych pól nie można zmieniać: {', '.join(sorted(blocked))}. "
                                 "Zmiana możliwa tylko w trybie korekty błędów przez administratora.")
    emp = session.get(Employee, review.employee_id)

    if body.additional_criterion_ids is not None:
        current = {rc.criterion_id: rc for rc, _ in review_entries(session, review)}
        mandatory_ids = {c.id for c in mandatory_criteria(session, review.sheet_type)}
        wanted = [cid for cid in dict.fromkeys(body.additional_criterion_ids) if cid not in mandatory_ids]
        for cid, rc in current.items():
            if rc.is_additional and cid not in wanted:
                session.delete(rc)
        for cid in wanted:
            if cid in current:
                continue
            if session.get(Criterion, cid) is None:
                raise HTTPException(422, "Nieznane kryterium dodatkowe")
            session.add(ReviewCriterion(review_id=review.id, criterion_id=cid, is_additional=True))
        session.flush()

    entries = {rc.criterion_id: rc for rc, _ in review_entries(session, review)}
    for cp in body.criteria:
        rc = entries.get(cp.criterion_id)
        if rc is None:
            raise HTTPException(422, f"Kryterium {cp.criterion_id} nie należy do tej oceny")
        if "score" in cp.model_fields_set:
            if cp.score is not None and cp.score not in VALID_SCORES:
                raise HTTPException(422, "Ocena cząstkowa musi wynosić 1, 3, 5, 7 lub 9 pkt (§ 11 ust. 1 pkt 1)")
            rc.score = cp.score
        if cp.justification is not None:
            rc.justification = cp.justification
        if cp.source_note_ids is not None:
            rc.source_note_ids = cp.source_note_ids
        session.add(rc)

    if body.promotion_request is not None and emp and not emp.is_civil_servant and body.promotion_request != "nie_dotyczy":
        raise HTTPException(422, "Wniosek o stopień służbowy dotyczy tylko urzędnika służby cywilnej (art. 89)")
    if body.civil_grade == 9:
        raise HTTPException(422, "Ocenianemu nie można przyznać kolejnego stopnia służbowego. "
                                 "Oceniany posiada już najwyższy możliwy stopień służbowy.")
    simple = sent - {"criteria", "additional_criterion_ids"}
    for field in ("period_start", "period_end", "due_date"):
        if field in simple and getattr(body, field) is None:
            raise HTTPException(422, "Daty okresu oceny i terminu nie mogą być puste")
    # walidacja tylko przy zmianie dat okresu (ocena po terminie może mieć „okres do” sprzed „okres od”
    # do chwili sporządzenia - wtedy „okres do” ustawia się na datę sporządzenia, objaśnienie 7 do arkusza)
    if ("period_start" in simple or "period_end" in simple) and             (body.period_start or review.period_start) > (body.period_end or review.period_end):
        raise HTTPException(422, "Początek okresu oceny musi być wcześniejszy niż jego koniec")
    for field in simple:
        setattr(review, field, getattr(body, field))
    if "due_date" in simple and body.due_date:
        review.due_date_history = [*review.due_date_history, {"date": body.due_date.isoformat(),
                                                              "reason": "ustalony przy wyznaczeniu kryteriów",
                                                              "at": date.today().isoformat()}]
    recompute(session, review)
    if review.result == "negatywna" and review.promotion_request == "tak":
        review.promotion_request = "nie"  # wniosek tylko przy ocenie pozytywnej
    session.add(review)
    audit(session, user, "correction" if correction else "update", "review", review.id, fields=sorted(sent),
          reason=body.correction_reason)
    if correction:
        msg = f"Administrator poprawił błąd w arkuszu ({', '.join(sorted(sent))}). Powód: {body.correction_reason}"
        notify_employee(session, review, "Korekta błędu w arkuszu oceny", msg)
        notify_reviewer(session, review, "Korekta błędu w arkuszu oceny", msg)
    session.commit()
    session.refresh(review)
    return serialize_review(session, review, viewer_is_reviewer=True)


def _transition(session: Session, review: Review, user: User, frm: set[str], to: str, **details) -> dict:
    if review.status not in frm:
        raise HTTPException(409, f"Nie można zmienić statusu z „{review.status}” na „{to}”")
    review.status = to
    review.updated_at = utcnow()
    session.add(review)
    audit(session, user, "status", "review", review.id, status=to, **details)
    session.commit()
    session.refresh(review)
    return serialize_review(session, review, viewer_is_reviewer=is_reviewer(session, user, review))


# ------------------------------------------------------------------ Etap I: kryteria i rozmowa rozpoczynająca


class PlaceIn(BaseModel):
    place: str = ""


@router.post("/reviews/{review_id}/criteria/confirm")
def confirm_criteria(review_id: int, body: PlaceIn | None = None, user: User = Depends(get_current_user),
                     session: Session = Depends(get_session)):
    """Oceniający potwierdza przeprowadzenie rozmowy (§ 5 ust. 1) i wyznaczenie kryteriów oraz terminu."""
    review = get_review_for(session, user, review_id, manage=True)
    if review.status != "criteria" or review.criteria_reviewer_confirmed_at:
        raise HTTPException(409, "Kryteria zostały już potwierdzone")
    problems = []
    if not review.opening_conversation_date:
        problems.append(_err("missing_opening", "Brak daty rozmowy rozpoczynającej",
                             "Podaj datę rozmowy, w której omówiono obowiązki, kryteria i oczekiwania (§ 5 ust. 1).",
                             "Uzupełnij datę rozmowy."))
    if not review.due_date:
        problems.append(_err("missing_due", "Brak terminu sporządzenia oceny", "Termin oceny musi być określony."))
    extra = sum(1 for rc, _ in review_entries(session, review) if rc.is_additional)
    if extra > MAX_ADDITIONAL_CRITERIA:
        problems.append(_err("too_many_additional", "Za dużo kryteriów dodatkowych", "Najwyżej 3 kryteria dodatkowe."))
    if problems:
        raise HTTPException(409, {"message": "Nie można potwierdzić wyznaczenia kryteriów", "warnings": problems})
    review.criteria_reviewer_confirmed_at = date.today()
    review.criteria_reviewer_place = (body.place if body else "") or review.criteria_reviewer_place
    session.add(review)
    notify_employee(session, review, "Potwierdź zapoznanie z kryteriami oceny okresowej",
                    "Przełożony wyznaczył kryteria i termin oceny po rozmowie rozpoczynającej.")
    audit(session, user, "confirm_criteria", "review", review.id)
    session.commit()
    session.refresh(review)
    return serialize_review(session, review, viewer_is_reviewer=True)


@router.post("/reviews/{review_id}/criteria/acknowledge")
def acknowledge_criteria(review_id: int, body: PlaceIn | None = None, user: User = Depends(get_current_user),
                         session: Session = Depends(get_session)):
    """Oceniany potwierdza odbycie rozmowy i zapoznanie się z kryteriami oraz terminem oceny."""
    review = get_review_for(session, user, review_id)
    if user.employee_id != review.employee_id:
        raise HTTPException(403, "Potwierdza oceniany")
    if review.status != "criteria" or not review.criteria_reviewer_confirmed_at:
        raise HTTPException(409, "Oceniający nie potwierdził jeszcze wyznaczenia kryteriów")
    review.criteria_employee_confirmed_at = date.today()
    review.criteria_employee_place = (body.place if body else "") or review.criteria_reviewer_place
    notify_reviewer(session, review, "Oceniany potwierdził kryteria oceny")
    return _transition(session, review, user, {"criteria"}, "observation")


class DueDateChange(BaseModel):
    due_date: date
    reason: Literal["zmiana_oceniajacego", "nieobecnosc_ocenianego", "nieobecnosc_oceniajacego",
                    "wniosek_ocenianego", "dluga_nieobecnosc"]
    note: str = ""


REPEAT_FIXED = ("Ponowna ocena po ocenie negatywnej odbywa się po upływie 6 miesięcy od zapoznania się z oceną "
                "(art. 81 ust. 9) - tego terminu nie zmienia się w trybie art. 81 ust. 8 ani nie przedłuża o nieobecności.")

DUE_REASONS = {
    "zmiana_oceniajacego": "zmiana na stanowisku oceniającego (art. 81 ust. 8 pkt 1)",
    "nieobecnosc_ocenianego": "przewidywana dłuższa nieobecność ocenianego (art. 81 ust. 8 pkt 2)",
    "nieobecnosc_oceniajacego": "przewidywana dłuższa nieobecność oceniającego (art. 81 ust. 8 pkt 3)",
    "wniosek_ocenianego": "wniosek ocenianego (art. 81 ust. 8 pkt 4)",
    "dluga_nieobecnosc": "nieobecność usprawiedliwiona > 1 miesiąca (art. 81 ust. 7)",
}


@router.post("/reviews/{review_id}/due-date")
def change_due_date(review_id: int, body: DueDateChange, user: User = Depends(get_current_user),
                    session: Session = Depends(get_session)):
    """Zmiana terminu oceny przez oceniającego (art. 81 ust. 7-8) - z powodem, zapisywana w historii."""
    review = get_review_for(session, user, review_id, manage=True)
    if review.status not in ("observation", "draft", "submitted"):
        raise HTTPException(409, "Termin można zmienić w okresie oceny, przed rozmową oceniającą")
    if is_repeat_review(session, review):
        raise HTTPException(409, REPEAT_FIXED)
    if body.reason != "dluga_nieobecnosc" and not dl.can_change_due_date(deadline_base(session, review), date.today()):
        raise HTTPException(409, "Zmiana terminu jest możliwa, gdy od początku okresu oceny minęło ponad 6 miesięcy "
                                 "(art. 81 ust. 8)")
    review.due_date_history = [*review.due_date_history, {
        "from": review.due_date.isoformat() if review.due_date else None, "date": body.due_date.isoformat(),
        "reason": DUE_REASONS[body.reason], "note": body.note, "at": date.today().isoformat()}]
    review.due_date = body.due_date
    session.add(review)
    notify_employee(session, review, "Zmiana terminu oceny okresowej",
                    f"Nowy termin sporządzenia oceny: {body.due_date.isoformat()}. Podstawa: {DUE_REASONS[body.reason]}.")
    audit(session, user, "change_due_date", "review", review.id, reason=body.reason)
    session.commit()
    session.refresh(review)
    return serialize_review(session, review, viewer_is_reviewer=True)


class DueDateRequestIn(BaseModel):
    proposed_date: date
    reason: str = Field(min_length=5)


def _request_out(r: DueDateRequest) -> dict:
    return {"id": r.id, "proposed_date": r.proposed_date.isoformat(), "reason": r.reason, "status": r.status,
            "decision_note": r.decision_note, "created_at": r.created_at.isoformat()}


@router.get("/reviews/{review_id}/due-date-requests")
def list_due_requests(review_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id)
    rows = session.exec(select(DueDateRequest).where(DueDateRequest.review_id == review.id)
                        .order_by(DueDateRequest.created_at.desc())).all()
    return [_request_out(r) for r in rows]


@router.post("/reviews/{review_id}/due-date-requests", status_code=201)
def request_due_date(review_id: int, body: DueDateRequestIn, user: User = Depends(get_current_user),
                     session: Session = Depends(get_session)):
    """Wniosek ocenianego o zmianę terminu oceny - po 6 miesiącach od początku okresu oceny."""
    review = get_review_for(session, user, review_id)
    if user.employee_id != review.employee_id:
        raise HTTPException(403, "Wniosek składa oceniany")
    if review.status not in ("observation", "draft", "submitted"):
        raise HTTPException(409, "Wniosek można złożyć w okresie oceny, przed rozmową oceniającą")
    if is_repeat_review(session, review):
        raise HTTPException(409, REPEAT_FIXED)
    if not dl.can_change_due_date(deadline_base(session, review), date.today()):
        raise HTTPException(409, "Wniosek o zmianę terminu można złożyć po upływie 6 miesięcy od początku okresu oceny "
                                 "(art. 81 ust. 8)")
    if session.exec(select(DueDateRequest).where(DueDateRequest.review_id == review.id,
                                                 DueDateRequest.status == "pending")).first():
        raise HTTPException(409, "Poprzedni wniosek czeka na rozpatrzenie")
    r = DueDateRequest(review_id=review.id, requested_by=user.id, proposed_date=body.proposed_date, reason=body.reason)
    session.add(r)
    notify_reviewer(session, review, "Wniosek o zmianę terminu oceny",
                    f"Proponowany termin: {body.proposed_date.isoformat()}. Uzasadnienie: {body.reason}")
    audit(session, user, "due_date_request", "review", review.id)
    session.commit()
    session.refresh(r)
    return _request_out(r)


class DueDateDecision(BaseModel):
    accept: bool
    note: str = ""


@router.post("/due-date-requests/{request_id}/decision")
def decide_due_request(request_id: int, body: DueDateDecision, user: User = Depends(get_current_user),
                       session: Session = Depends(get_session)):
    r = session.get(DueDateRequest, request_id)
    if r is None:
        raise HTTPException(404, "Nie ma takiego wniosku")
    review = get_review_for(session, user, r.review_id, manage=True)
    if r.status != "pending":
        raise HTTPException(409, "Wniosek został już rozpatrzony")
    r.status = "accepted" if body.accept else "rejected"
    r.decision_note = body.note
    r.decided_at = utcnow()
    session.add(r)
    if body.accept:
        review.due_date_history = [*review.due_date_history, {
            "from": review.due_date.isoformat() if review.due_date else None, "date": r.proposed_date.isoformat(),
            "reason": DUE_REASONS["wniosek_ocenianego"], "note": r.reason, "at": date.today().isoformat()}]
        review.due_date = r.proposed_date
        session.add(review)
    notify_employee(session, review, "Rozpatrzono wniosek o zmianę terminu oceny",
                    ("Termin zmieniony na " + r.proposed_date.isoformat()) if body.accept
                    else ("Wniosek nieuwzględniony. " + body.note).strip())
    audit(session, user, "due_date_request_decision", "review", review.id, accepted=body.accept)
    session.commit()
    session.refresh(review)
    return serialize_review(session, review, viewer_is_reviewer=True)


# ------------------------------------------------------------------ Etap II: ocena


@router.post("/reviews/{review_id}/start")
def start_evaluation(review_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Okres obserwacji -> przygotowanie oceny. Dane poprzedniej oceny uzupełniane z historii."""
    review = get_review_for(session, user, review_id, manage=True)
    if review.status == "observation":
        prefill_previous(session, review)
        # „okres od” = data zapoznania ocenianego z kryteriami (objaśnienie 6 do wzoru arkusza)
        review.period_start = review.criteria_employee_confirmed_at or review.period_start
        review.period_end = max(review.period_end, review.period_start)  # ocena po terminie
        emp = session.get(Employee, review.employee_id)
        if emp and emp.is_civil_servant:
            review.appointment_year = review.appointment_year or emp.appointment_year
            review.civil_grade = review.civil_grade or emp.civil_grade
            review.civil_grade_date = review.civil_grade_date or emp.civil_grade_date
    return _transition(session, review, user, {"observation"}, "draft")


@router.post("/reviews/{review_id}/submit")
def submit_review(review_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Szkic -> gotowa do rozmowy. Blokowane przez krytyczne ostrzeżenia kontroli jakości."""
    review = get_review_for(session, user, review_id, manage=True)
    warnings = rule_warnings(session, review)
    if has_critical(warnings):
        raise HTTPException(409, {"message": "Ocena zawiera krytyczne braki", "warnings": warnings})
    review.submitted_at = utcnow()
    notify_employee(session, review, "Zbliża się rozmowa oceniająca",
                    "Przełożony przygotował ocenę. Przed rozmową możesz wypełnić samoocenę.")
    return _transition(session, review, user, {"draft"}, "submitted")


class DiscussedIn(BaseModel):
    conversation_date: date


@router.post("/reviews/{review_id}/assessment/confirm")
def confirm_assessment_term(review_id: int, user: User = Depends(get_current_user),
                            session: Session = Depends(get_session)):
    """Oceniany potwierdza termin rozmowy oceniającej - bramka odblokowująca pola etapu IV (§ 10)."""
    review = get_review_for(session, user, review_id)
    if user.employee_id != review.employee_id:
        raise HTTPException(403, "Termin rozmowy oceniającej potwierdza oceniany")
    if review.status != "submitted":
        raise HTTPException(409, "Termin rozmowy oceniającej potwierdza się przed rozmową (§ 10)")
    if not review.assessment_invited_at:
        raise HTTPException(409, "Oceniający nie zaprosił jeszcze na rozmowę oceniającą")
    review.assessment_confirmed_at = utcnow()
    session.add(review)
    notify_reviewer(session, review, "Oceniany potwierdził termin rozmowy oceniającej")
    audit(session, user, "confirm_assessment_term", "review", review.id)
    session.commit()
    session.refresh(review)
    return serialize_review(session, review, viewer_is_reviewer=False)


@router.post("/reviews/{review_id}/discussed")
def mark_discussed(review_id: int, body: DiscussedIn, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)):
    """Rozmowa oceniająca przeprowadzona (§ 10). Oceniający może jeszcze skorygować ocenę (§ 11 ust. 2).

    Pola etapu „Rozmowa oceniająca” odblokowuje umówienie rozmowy (zaproszenie .ics) potwierdzone przez ocenianego.
    """
    review = get_review_for(session, user, review_id, manage=True)
    if not review.assessment_confirmed_at:
        raise HTTPException(409, "Najpierw umów rozmowę oceniającą (zaproszenie .ics) i poczekaj na potwierdzenie "
                                 "terminu przez ocenianego (§ 10).")
    review.conversation_date = body.conversation_date
    return _transition(session, review, user, {"submitted"}, "discussed")


@router.post("/reviews/{review_id}/reopen")
def reopen(review_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id, manage=True)
    return _transition(session, review, user, {"submitted"}, "draft")


def finalize_problems(session: Session, review: Review) -> list[dict]:
    warnings = [w for w in rule_warnings(session, review) if w["severity"] == "critical"]
    if not review.ipr_conclusions.strip():
        warnings.append(_err("missing_ipr", "Brak wniosków do IPR",
                             "Arkusz musi zawierać wnioski dotyczące IPR (art. 81 ust. 5, § 11 ust. 1 pkt 5).",
                             "Wygeneruj i zatwierdź IPR."))
    if not review.conversation_date:
        warnings.append(_err("missing_conversation", "Brak daty rozmowy oceniającej", "Uzupełnij datę rozmowy (§ 10)."))
    if review.promotion_request == "tak":
        if review.result != "pozytywna":
            warnings.append(_err("promotion_negative", "Wniosek o stopień przy ocenie negatywnej",
                                 "Wniosek można dołączyć tylko do oceny pozytywnej (art. 89 ust. 1)."))
        if not review.promotion_justification.strip():
            warnings.append(_err("missing_promotion_justification", "Brak umotywowania wniosku",
                                 "Wniosek o kolejny stopień służbowy musi być umotywowany (art. 89 ust. 1)."))
        if not review.civil_grade:
            warnings.append(_err("missing_grade", "Brak posiadanego stopnia służbowego",
                                 "Uzupełnij posiadany stopień służbowy w części III."))
    return warnings


@router.post("/reviews/{review_id}/finalize")
def finalize(review_id: int, body: PlaceIn | None = None, user: User = Depends(get_current_user),
             session: Session = Depends(get_session)):
    """Sporządzenie oceny na piśmie i przekazanie ocenianemu (podpis oceniającego, § 11)."""
    review = get_review_for(session, user, review_id, manage=True)
    recompute(session, review)
    warnings = finalize_problems(session, review)
    if warnings:
        raise HTTPException(409, {"message": "Nie można zatwierdzić oceny", "warnings": warnings})
    review.finalized_at = utcnow()
    review.reviewer_signed_at = date.today()
    # „okres do” = data sporządzenia oceny na piśmie (objaśnienie 7 do wzoru arkusza), a gdy ocenę sporządza się
    # po upływie terminu - data terminu oceny (schemat pól formularza KPRM)
    review.period_end = min(review.reviewer_signed_at, review.due_date) if review.due_date else review.reviewer_signed_at
    review.period_end = max(review.period_end, review.period_start)
    if body and body.place:
        review.reviewer_place = body.place
    elif not review.reviewer_place:
        emp = session.get(Employee, review.employee_id)
        office = office_of(session, emp) if emp else None
        review.reviewer_place = office.city if office else ""
    if review.promotion_request == "tak":
        emp = session.get(Employee, review.employee_id)
        notify_hr(session, f"Wniosek o przyznanie kolejnego stopnia służbowego: {emp.full_name if emp else ''}",
                  f"Oceniający wnioskuje o przyznanie {promotion_target(review) or 'kolejnego'} stopnia służbowego "
                  "(art. 89 ust. 1 ustawy). Decyzję podejmuje dyrektor generalny urzędu.", f"/reviews/{review.id}")
        notify_employee(session, review, "Złożono wniosek o przyznanie Ci kolejnego stopnia służbowego",
                        "Wniosek został dołączony do oceny okresowej (część III arkusza, art. 89 ust. 1 ustawy).")
    if second_negative_risk(session, review):
        emp = session.get(Employee, review.employee_id)
        notify_hr(session, f"Druga z rzędu ocena negatywna urzędnika: {emp.full_name if emp else ''}",
                  "Art. 71 ust. 1 pkt 1 ustawy o służbie cywilnej - rozwiązanie stosunku pracy.", f"/reviews/{review.id}")
    notify_employee(session, review, "Ocena okresowa do zapoznania",
                    "Zapoznaj się z oceną i potwierdź to w systemie. Od oceny przysługuje sprzeciw w terminie 7 dni "
                    "od dnia zapoznania się z nią (art. 83 ust. 1 ustawy o służbie cywilnej).")
    if review.status != "discussed":
        raise HTTPException(409, f"Nie można zmienić statusu z „{review.status}” na „final”")
    review.status = "final"
    review.updated_at = utcnow()
    session.add(review)
    session.flush()
    # schemat procesu KPRM: „koniec cyklu oceny i początek następnego” (kryteria w 30 / 7 dni, § 7)
    nxt = start_next_cycle(session, review)
    audit(session, user, "status", "review", review.id, status="final", next_review=nxt.id if nxt else None)
    session.commit()
    session.refresh(review)
    return serialize_review(session, review, viewer_is_reviewer=True)


@router.post("/reviews/{review_id}/acknowledge")
def acknowledge(review_id: int, body: PlaceIn | None = None, user: User = Depends(get_current_user),
                session: Session = Depends(get_session)):
    """Oceniany potwierdza odbycie rozmowy i zapoznanie się z oceną oraz wnioskami do IPR."""
    review = get_review_for(session, user, review_id)
    if user.employee_id != review.employee_id:
        raise HTTPException(403, "Zapoznanie z oceną potwierdza oceniany")
    review.acknowledged_at = date.today()
    review.employee_place = (body.place if body else "") or review.reviewer_place
    notify_reviewer(session, review, "Oceniany zapoznał się z oceną")
    _notify_obligatory_promotion(session, review)
    return _transition(session, review, user, {"final"}, "acknowledged")


class FictionIn(BaseModel):
    note: str = Field(min_length=5)


@router.post("/reviews/{review_id}/ack-fiction")
def ack_fiction(review_id: int, body: FictionIn, user: User = Depends(get_current_user),
                session: Session = Depends(get_session)):
    """Stwierdzenie fikcji zapoznania: informacja o ocenie dotarła do ocenianego, ale nie mógł lub nie chciał
    potwierdzić zapoznania się z nią."""
    review = get_review_for(session, user, review_id, manage=True)
    review.acknowledged_at = date.today()
    review.ack_fiction = True
    review.ack_fiction_note = body.note
    _notify_obligatory_promotion(session, review)
    notify_employee(session, review, "Stwierdzono doręczenie oceny okresowej",
                    "Termin 7 dni na sprzeciw biegnie od dnia doręczenia informacji o ocenie.")
    return _transition(session, review, user, {"final"}, "acknowledged", fiction=True)


def _notify_obligatory_promotion(session: Session, review: Review) -> None:
    """Scheduler: weryfikuje warunki obligatoryjnego stopnia (art. 89 ust. 2) i powiadamia kadry."""
    if obligatory_promotion(session, review):
        emp = session.get(Employee, review.employee_id)
        notify_hr(session, f"Obowiązek przyznania kolejnego stopnia służbowego: {emp.full_name if emp else ''}",
                  "Druga kolejna ocena na jednym z dwóch najwyższych poziomów - stopień przysługuje w terminie 30 dni "
                  f"od zapoznania z oceną, tj. do {dl.promotion_deadline(review.acknowledged_at).isoformat()} "
                  "(art. 89 ust. 2 ustawy).", f"/reviews/{review.id}")


# ------------------------------------------------------------------ sprzeciw (art. 83)


class ObjectionIn(BaseModel):
    text: str = Field(min_length=10)


@router.post("/reviews/{review_id}/objection")
def file_objection(review_id: int, body: ObjectionIn, user: User = Depends(get_current_user),
                   session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id)
    if user.employee_id != review.employee_id:
        raise HTTPException(403, "Sprzeciw wnosi oceniany")
    if review.status not in ("final", "acknowledged"):
        raise HTTPException(409, f"Sprzeciw wnosi się na etapie zapoznania z oceną (obecny status: „{review.status}”)")
    # Termin 7 dni biegnie od rzeczywistego zapoznania się z oceną - potwierdzonego przez ocenianego albo
    # w trybie fikcji zapoznania. Gdy oceniany wnosi sprzeciw bezpośrednio z etapu zapoznania (bez wcześniejszego
    # potwierdzenia), zapoznanie następuje w chwili wniesienia sprzeciwu i dopiero wtedy rusza zegar terminu
    # (art. 83 ust. 1). Nieobecność pracownika przed zapoznaniem nie uruchamia terminu; po zapoznaniu biegnie on
    # nieprzerwanie, a gdy koniec wypada w dzień wolny - przesuwa się na najbliższy dzień roboczy (liczenie terminów).
    if review.acknowledged_at is None:
        review.acknowledged_at = date.today()
        review.employee_place = review.employee_place or review.reviewer_place
    elif date.today() > dl.objection_deadline(review.acknowledged_at):
        raise HTTPException(409, "Minął termin 7 dni od zapoznania się z oceną (art. 83 ust. 1)")
    review.objection_at = date.today()
    review.objection_text = body.text
    review.objection_decision = None
    emp = session.get(Employee, review.employee_id)
    notify_hr(session, f"Sprzeciw od oceny okresowej: {emp.full_name if emp else ''}",
              "Sprzeciw rozpatruje się w terminie 14 dni od dnia wniesienia (art. 83 ust. 3).", f"/reviews/{review.id}")
    notify_reviewer(session, review, "Wniesiono sprzeciw od oceny")
    return _transition(session, review, user, {"final", "acknowledged"}, "objection")


class ObjectionChange(BaseModel):
    criteria: list[CriterionPatch] = Field(default_factory=list)
    justification: str | None = None
    ipr_conclusions: str | None = None


class ObjectionDecision(BaseModel):
    decision: Literal["odrzucony", "zmiana", "ponowne_sporzadzenie"]
    note: str = ""
    # przy „zmiana”: zmiany wprowadzane w formularzu przez dyrektora generalnego (art. 83 ust. 4)
    changes: ObjectionChange | None = None


@router.post("/reviews/{review_id}/objection/decision")
def decide_objection(review_id: int, body: ObjectionDecision, user: User = Depends(get_current_user),
                     session: Session = Depends(get_session)):
    """Rozpatrzenie sprzeciwu przez dyrektora generalnego (art. 83 ust. 3-4)."""
    if user.role != "hr":
        raise HTTPException(403, "Sprzeciw rozpatruje dyrektor generalny urzędu (komórka kadrowa)")
    review = session.get(Review, review_id)
    if review is None:
        raise HTTPException(404, "Nie ma takiej oceny")
    review.objection_decision = body.decision
    review.objection_decided_at = date.today()
    labels = {"odrzucony": "sprzeciw nieuwzględniony (możliwe odwołanie do sądu pracy w 14 dni)",
              "zmiana": "ocena zostanie zmieniona", "ponowne_sporzadzenie": "ocena zostanie sporządzona po raz drugi"}
    notify_employee(session, review, "Rozpatrzono sprzeciw od oceny", labels[body.decision])
    notify_reviewer(session, review, "Rozpatrzono sprzeciw od oceny", labels[body.decision])
    if body.decision == "odrzucony":
        return _transition(session, review, user, {"objection"}, "acknowledged", decision=body.decision)
    if body.decision == "zmiana":
        # schemat procesu KPRM: dyrektor generalny wprowadza zmianę w formularzu oceny
        ch = body.changes or ObjectionChange()
        if not ch.criteria and ch.justification is None and ch.ipr_conclusions is None:
            raise HTTPException(422, "Wprowadź zmiany w formularzu oceny (oceny cząstkowe lub uzasadnienie)")
        entries = {rc.criterion_id: rc for rc, _ in review_entries(session, review)}
        before = (review.overall_score, review.result)
        changed = []
        for cp in ch.criteria:
            rc = entries.get(cp.criterion_id)
            if rc is None:
                raise HTTPException(422, f"Kryterium {cp.criterion_id} nie należy do tej oceny")
            if cp.score is not None:
                if cp.score not in VALID_SCORES:
                    raise HTTPException(422, "Ocena cząstkowa musi wynosić 1, 3, 5, 7 lub 9 pkt")
                if rc.score is not None and cp.score < rc.score:
                    raise HTTPException(422, "Uwzględnienie sprzeciwu oznacza przyznanie racji ocenianemu - nie można "
                                             "obniżyć oceny ani jej elementów (art. 83 ust. 4, poradnik KPRM rozdz. 7)")
                if cp.score != rc.score:
                    changed.append({"criterion_id": cp.criterion_id, "from": rc.score, "to": cp.score})
                rc.score = cp.score
            if cp.justification is not None:
                rc.justification = cp.justification
            session.add(rc)
        if ch.justification is not None:
            review.justification = ch.justification
        if ch.ipr_conclusions is not None:
            review.ipr_conclusions = ch.ipr_conclusions
        recompute(session, review)
        if before[1] == "pozytywna" and review.result == "negatywna":
            raise HTTPException(422, "Zmiana oceny po sprzeciwie nie może pogorszyć wyniku ocenianego (art. 83 ust. 4)")
        if review.result == "negatywna" and not review.justification.strip():
            raise HTTPException(422, "Ocena negatywna wymaga uzasadnienia (§ 11 ust. 3)")
        msg =f"Dyrektor generalny zmienił ocenę po uwzględnieniu sprzeciwu. Wynik: {review.result}, {review.overall_level}."
        notify_employee(session, review, "Ocena okresowa zmieniona po sprzeciwie", msg)
        notify_reviewer(session, review, "Ocena zmieniona po sprzeciwie", msg)
        return _transition(session, review, user, {"objection"}, "acknowledged", decision=body.decision, changed=changed)
    # sporządzenie oceny po raz drugi - powrót do etapu „rozmowa oceniająca i dokonanie oceny”
    review.reviewer_signed_at = None
    review.acknowledged_at = None
    review.ack_fiction = False
    review.attempt += 1
    review.conversation_date = None
    # poradnik KPRM rozdz. 7: ocenę po raz drugi sporządza bezpośredni przełożony w terminie 14 dni od wniesienia
    # sprzeciwu (rozpatrzenie sprzeciwu obejmuje jego wykonanie - art. 83 ust. 3)
    redo_due = dl.days_deadline(review.objection_at or date.today(), dl.RULES["objection_decision_days"])
    review.due_date_history = [*review.due_date_history, {
        "from": review.due_date.isoformat() if review.due_date else None, "date": redo_due.isoformat(),
        "reason": "sporządzenie oceny po raz drugi po uwzględnieniu sprzeciwu (art. 83 ust. 3-4)",
        "note": body.note, "at": date.today().isoformat()}]
    review.due_date = redo_due
    notify_reviewer(session, review, "Sporządź ocenę po raz drugi",
                    f"Dyrektor generalny uwzględnił sprzeciw. Przeprowadź ponownie rozmowę oceniającą i sporządź ocenę "
                    f"do {redo_due.isoformat()} (14 dni od wniesienia sprzeciwu). Przy sprzeciwie ogólnym sam decydujesz, "
                    "które fragmenty oceny zmienić; oceny nie można obniżyć.")
    return _transition(session, review, user, {"objection"}, "draft", decision=body.decision)


# ------------------------------------------------------------------ samoocena


class SelfItem(BaseModel):
    score: int | None = None
    comment: str = ""


class SelfAssessmentIn(BaseModel):
    items: dict[int, SelfItem]
    summary: str = ""
    submit: bool = False


def _sa_out(sa: SelfAssessment | None, review: Review, session: Session) -> dict:
    entries = review_entries(session, review)
    return {
        "review_id": review.id,
        "criteria": [{"criterion_id": c.id, "code": c.code, "name": c.name, "description": c.description,
                      "indicators": c.behavioral_indicators} for _, c in entries],
        "items": sa.items if sa else {},
        "summary": sa.summary if sa else "",
        "submitted_at": sa.submitted_at.isoformat() if sa and sa.submitted_at else None,
    }


@router.get("/reviews/{review_id}/self-assessment")
def get_self_assessment(review_id: int, user: User = Depends(get_current_user),
                        session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id)
    if user.role == "admin":
        raise HTTPException(403, "Samoocena nie jest częścią arkusza - administrator nie ma do niej wglądu")
    sa = session.exec(select(SelfAssessment).where(SelfAssessment.review_id == review.id)).first()
    if user.employee_id != review.employee_id and not (sa and sa.submitted_at):
        sa = None  # przełożony widzi samoocenę dopiero po jej przekazaniu
    return _sa_out(sa, review, session)


@router.put("/reviews/{review_id}/self-assessment")
def put_self_assessment(review_id: int, body: SelfAssessmentIn, user: User = Depends(get_current_user),
                        session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id)
    if user.employee_id != review.employee_id:
        raise HTTPException(403, "Samoocenę wypełnia oceniany")
    if review.status not in ("observation", *EVALUATION_STATUSES):
        raise HTTPException(409, "Samoocenę wypełnia się w okresie oceny, przed sporządzeniem oceny")
    valid_ids = {c.id for _, c in review_entries(session, review)}
    for cid, item in body.items.items():
        if cid not in valid_ids:
            raise HTTPException(422, f"Kryterium {cid} nie należy do tej oceny")
        if item.score is not None and item.score not in VALID_SCORES:
            raise HTTPException(422, "Ocena musi wynosić 1, 3, 5, 7 lub 9 pkt")
    sa = session.exec(select(SelfAssessment).where(SelfAssessment.review_id == review.id)).first() \
        or SelfAssessment(review_id=review.id)
    if sa.submitted_at:
        raise HTTPException(409, "Samoocena została już przekazana przełożonemu")
    sa.items = {str(k): v.model_dump() for k, v in body.items.items()}
    sa.summary = body.summary
    sa.updated_at = utcnow()
    if body.submit:
        sa.submitted_at = utcnow()
    session.add(sa)
    audit(session, user, "submit" if body.submit else "save", "self_assessment", review.id)
    session.commit()
    session.refresh(sa)
    return _sa_out(sa, review, session)


# ------------------------------------------------------------------ integracja: zaproszenie do kalendarza


@router.get("/reviews/{review_id}/invite.ics")
def invite_ics(review_id: int, kind: Literal["opening", "assessment", "feedback"], when: str,
               minutes: int = 60, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Zaproszenie na rozmowę w formacie iCalendar (RFC 5545) - działa z Outlookiem, Thunderbirdem,
    kalendarzem Google i większością systemów EZD z modułem poczty. `when`: 2026-12-01T10:00."""
    review = get_review_for(session, user, review_id, manage=True)
    emp = session.get(Employee, review.employee_id)
    try:
        start = datetime.fromisoformat(when)
    except ValueError as exc:
        raise HTTPException(422, "Podaj datę i godzinę w formacie RRRR-MM-DDTGG:MM") from exc
    end = start + timedelta(minutes=minutes)
    titles = {"opening": "Rozmowa rozpoczynająca ocenę okresową (§ 5 rozporządzenia)",
              "assessment": "Rozmowa oceniająca (§ 10 rozporządzenia)",
              "feedback": "Rozmowa - bieżąca informacja zwrotna"}
    desc = {"opening": "Omówimy obowiązki z opisu stanowiska, kryteria oceny, oczekiwania i cele na okres oceny.",
            "assessment": "Omówimy wyniki z okresu oceny, Twoją samoocenę i kierunki rozwoju (wnioski do IPR). "
                          "Jeśli jeszcze jej nie wypełniłeś(-aś), możesz przygotować samoocenę w systemie.",
            "feedback": "Krótka rozmowa o bieżącej pracy: co działa, co poprawić, jakiego wsparcia potrzebujesz."}

    def fmt(d: datetime) -> str:
        return d.strftime("%Y%m%dT%H%M%S")

    def esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace(";", "\;").replace(",", "\,").replace("\n", "\n")

    body = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Cyfrowy Asystent Ocen Okresowych//PL", "METHOD:REQUEST",
        "BEGIN:VEVENT", f"UID:review-{review.id}-{kind}-{fmt(start)}@asystent-ocen",
        f"DTSTAMP:{fmt(datetime.now())}", f"DTSTART:{fmt(start)}", f"DTEND:{fmt(end)}",
        f"SUMMARY:{esc(titles[kind] + ' - ' + emp.full_name)}", f"DESCRIPTION:{esc(desc[kind])}",
        "END:VEVENT", "END:VCALENDAR", ""])
    if kind == "assessment":
        # zaproszenie na rozmowę oceniającą odblokowuje pola tego etapu (datę rozmowy i jej potwierdzenie)
        review.assessment_invited_at = utcnow()
        session.add(review)
    notify_employee(session, review, titles[kind].split(" (")[0] + " - zaproszenie",
                    f"Termin: {start.strftime('%d.%m.%Y, godz. %H:%M')}. {desc[kind]}")
    audit(session, user, "invite", "review", review.id, kind=kind)
    session.commit()
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="rozmowa-{kind}-{review.id}.ics"'})


# ------------------------------------------------------------------ tryb korekty błędów (administrator)


@router.get("/reviews/{review_id}/corrections")
def list_corrections(review_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Historia korekt błędów wprowadzonych przez administratora (z dziennika zdarzeń) - jawna dla stron oceny."""
    review = get_review_for(session, user, review_id)
    rows = session.exec(select(AuditLog).where(AuditLog.entity == "review", AuditLog.entity_id == review.id,
                                               AuditLog.action == "correction").order_by(AuditLog.created_at.desc())).all()
    users = {u.id: u.full_name for u in session.exec(select(User)).all()}
    return [{"at": a.created_at.isoformat(), "by": users.get(a.user_id, "-"), "fields": a.details.get("fields", []),
             "reason": a.details.get("reason", "")} for a in rows]
