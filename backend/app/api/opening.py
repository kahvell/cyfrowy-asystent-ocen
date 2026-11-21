"""Etap I oceny (§ 5 rozporządzenia): wsparcie AI przy wyznaczaniu kryteriów i rozmowie rozpoczynającej.

- oceniający: propozycja kryteriów dodatkowych (maks. 3) na bazie danych historycznych - opis stanowiska,
  poprzednia ocena i IPR, wybory kryteriów dla tego samego stanowiska w urzędzie. Sygnały liczy kod (jawne
  i sprawdzalne), model tylko je porządkuje i uzasadnia. Wybór zawsze należy do oceniającego.
- oceniany: jak przygotować się do rozmowy - zrozumieć kryteria, przedstawić własne cele, rzeczowo zgodzić się
  albo nie zgodzić z kryterium. Bez dostępu do dziennika obserwacji przełożonego.
"""

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.ai.pipelines import employee_opening_prep, suggest_criteria
from app.api.ai import suggestion_out
from app.db import get_session
from app.models import (
    IPR,
    AISuggestion,
    Criterion,
    DevelopmentWheel,
    Employee,
    IPRGoal,
    Review,
    ReviewCriterion,
    ReviewCycle,
    User,
    utcnow,
)
from app.security import get_current_user
from app.services.access import get_review_for, is_reviewer
from app.services.audit import audit
from app.services.notify import notify_reviewer
from app.services.process import previous_review
from app.services.reviews import all_criteria, people_names, review_entries

router = APIRouter(tags=["ai"])

SCALE = {1: "znacznie poniżej oczekiwań", 3: "poniżej oczekiwań", 5: "na poziomie oczekiwań",
         7: "powyżej oczekiwań", 9: "znacznie powyżej oczekiwań"}


def _signal(kind: str, weight: float, text: str) -> dict:
    return {"kind": kind, "weight": weight, "text": text}


def criteria_signals(session: Session, review: Review) -> tuple[Employee, list[Criterion], list[dict]]:
    """Kandydaci na kryteria dodatkowe (spoza obowiązkowych dla arkusza) z sygnałami z danych systemu."""
    emp = session.get(Employee, review.employee_id)
    crit = all_criteria(session)
    mandatory = [c for c in crit if review.sheet_type in c.mandatory_for]
    candidates = {c.id: {"code": c.code, "name": c.name, "indicators": c.behavioral_indicators, "signals": []}
                  for c in crit if review.sheet_type not in c.mandatory_for}

    # 1) opis stanowiska - te same słowa kluczowe, którymi klasyfikowane są notatki
    duties = (emp.position_description or "").lower()
    if duties:
        for c in crit:
            if c.id not in candidates:
                continue
            hits = [k for k in c.keywords if k in duties]
            if hits:
                candidates[c.id]["signals"].append(_signal(
                    "duties", 1.5 + 0.5 * min(len(hits), 3),
                    f"Opis stanowiska: zadania związane z kryterium (np. „{'”, „'.join(hits[:3])}…”)"))

    # 2) poprzednia ocena - wybrane kryteria dodatkowe i słabsze wyniki
    prev = previous_review(session, review)
    if prev is not None:
        cycle = session.get(ReviewCycle, prev.cycle_id)
        label = cycle.name if cycle else "poprzedni cykl"
        for rc in session.exec(select(ReviewCriterion).where(ReviewCriterion.review_id == prev.id)).all():
            if rc.criterion_id not in candidates:
                continue
            if rc.score is not None and rc.score <= 5:
                candidates[rc.criterion_id]["signals"].append(_signal(
                    "prev_low", 3.0 if rc.score <= 3 else 2.0,
                    f"Poprzednia ocena ({label}): {rc.score} pkt - {SCALE.get(rc.score, '')}; obszar do rozwoju"))
            elif rc.is_additional:
                candidates[rc.criterion_id]["signals"].append(_signal(
                    "prev_chosen", 1.0,
                    f"Wybrane w poprzedniej ocenie ({label})" + (f": {rc.score} pkt" if rc.score else "")))
        # 3) cele z poprzedniego IPR powiązane z kryterium
        ipr = session.exec(select(IPR).where(IPR.review_id == prev.id)).first()
        if ipr is not None:
            for g in session.exec(select(IPRGoal).where(IPRGoal.ipr_id == ipr.id)).all():
                if g.criterion_id in candidates:
                    candidates[g.criterion_id]["signals"].append(_signal(
                        "ipr", 2.5, f"Cel z poprzedniego IPR: „{g.goal[:90]}”"))

    # 4) wybory kryteriów dodatkowych dla tego samego stanowiska w urzędzie (bez danych o ocenach innych osób)
    peers = session.exec(select(Employee.id).where(Employee.position == emp.position, Employee.id != emp.id)).all()
    if peers:
        rows = session.exec(select(ReviewCriterion.criterion_id, Review.employee_id)
                            .join(Review, Review.id == ReviewCriterion.review_id)
                            .where(Review.employee_id.in_(peers), ReviewCriterion.is_additional)).all()
        people = Counter(cid for cid, _ in set(rows))
        for cid, n in people.items():
            if cid in candidates:
                candidates[cid]["signals"].append(_signal(
                    "peers", min(2.0, 0.75 * n), f"Wybierane dla {n} os. na stanowisku „{emp.position}”"))

    # 5) koło rozwoju udostępnione przez ocenianego - jego własne wskazania (etap I, § 5: rozmowa o celach)
    wheel = session.exec(select(DevelopmentWheel).where(DevelopmentWheel.review_id == review.id)).first()
    if wheel is not None and wheel.shared_at:
        if wheel.proposed_criterion_id in candidates:
            candidates[wheel.proposed_criterion_id]["signals"].append(_signal(
                "employee", 3.0, "Pracownik proponuje to kryterium dodatkowe (koło rozwoju)"))
        for cid in wheel.focus:
            if cid in candidates:
                candidates[cid]["signals"].append(_signal(
                    "employee", 2.5, "Pracownik chce pracować nad tym obszarem (koło rozwoju)"))

    return emp, mandatory, list(candidates.values())


@router.post("/reviews/{review_id}/ai/suggest-criteria")
def ai_suggest_criteria(review_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id, manage=True)
    if review.status != "criteria" or review.criteria_reviewer_confirmed_at:
        raise HTTPException(409, "Kryteria wybiera się na etapie I, przed potwierdzeniem rozmowy rozpoczynającej")
    emp, mandatory, candidates = criteria_signals(session, review)
    ctx = {"employee_name": emp.full_name, "position": emp.position, "duties": emp.position_description,
           "sheet_type": review.sheet_type, "mandatory": [c.name for c in mandatory], "candidates": candidates}
    res = suggest_criteria(ctx, people_names(session, review))
    by_code = {c["code"]: c for c in candidates}
    ids = {c.code: c.id for c in all_criteria(session)}
    payload = res.data.model_dump()
    for p in payload["proposals"]:
        p["criterion_id"] = ids[p["criterion_code"]]
        p["name"] = by_code[p["criterion_code"]]["name"]
        # dowody zawsze z danych policzonych w kodzie - model pisze tylko uzasadnienie (bez zmyślonych faktów)
        p["evidence"] = [s["text"] for s in sorted(by_code[p["criterion_code"]]["signals"], key=lambda s: -s["weight"])][:4]
    s = AISuggestion(review_id=review.id, kind="criteria_suggestion", payload=payload, model=res.model,
                     prompt_version=res.prompt_version, status="pending", created_by=user.id)
    session.add(s)
    audit(session, user, "ai_generate", "criteria_suggestion", review.id)
    session.commit()
    session.refresh(s)
    return suggestion_out(s)


@router.post("/reviews/{review_id}/ai/employee-opening-prep")
def ai_employee_opening_prep(review_id: int, user: User = Depends(get_current_user),
                             session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id)
    if user.employee_id != review.employee_id:
        raise HTTPException(403, "To wsparcie jest dla ocenianego")
    if review.status != "criteria":
        raise HTTPException(409, "Przygotowanie do rozmowy rozpoczynającej jest dostępne na etapie I")
    emp = session.get(Employee, review.employee_id)
    prev = previous_review(session, review)
    ipr_goals: list[str] = []
    if prev is not None:
        ipr = session.exec(select(IPR).where(IPR.review_id == prev.id, IPR.status != "draft")).first()
        if ipr is not None:
            ipr_goals = [g.goal for g in session.exec(select(IPRGoal).where(IPRGoal.ipr_id == ipr.id)).all()]
    ctx = {"employee_name": emp.full_name, "position": emp.position, "duties": emp.position_description,
           "criteria": [{"name": c.name, "indicators": c.behavioral_indicators, "is_additional": rc.is_additional}
                        for rc, c in review_entries(session, review)],
           "prev_level": prev.overall_level if prev else None, "ipr_goals": ipr_goals}
    res = employee_opening_prep(ctx, people_names(session, review))
    s = AISuggestion(review_id=review.id, kind="employee_opening_prep", payload=res.data.model_dump(), model=res.model,
                     prompt_version=res.prompt_version, status="info", created_by=user.id)
    session.add(s)
    audit(session, user, "ai_generate", "employee_opening_prep", review.id)
    session.commit()
    session.refresh(s)
    return suggestion_out(s)


# ---------------------------------------------------------------- koło rozwoju (etap I - oceniany)


# najlepiej przed rozmową rozpoczynającą (etap I), ale cele można też doprecyzować w okresie oceny (etap II)
WHEEL_STATUSES = {"criteria", "observation"}


class WheelItem(BaseModel):
    now: int = Field(ge=1, le=10)
    target: int = Field(ge=1, le=10)


class WheelIn(BaseModel):
    items: dict[int, WheelItem] = Field(default_factory=dict)
    focus: list[int] = Field(default_factory=list, max_length=2)
    proposed_criterion_id: int | None = None
    note: str = Field(default="", max_length=2000)
    share: bool = False


def _wheel_out(session: Session, review: Review, wheel: DevelopmentWheel | None, *, editable: bool) -> dict:
    entries = review_entries(session, review)
    in_sheet = {c.id for _, c in entries}
    return {
        "review_id": review.id,
        "criteria": [{"criterion_id": c.id, "name": c.name, "is_additional": rc.is_additional,
                      "indicators": c.behavioral_indicators[:2]} for rc, c in entries],
        # kryteria spoza arkusza, które oceniany może zaproponować jako dodatkowe (§ 5 ust. 2 - wybiera oceniający)
        "proposable": [{"criterion_id": c.id, "name": c.name} for c in all_criteria(session)
                       if review.sheet_type not in c.mandatory_for and c.id not in in_sheet],
        "items": wheel.items if wheel else {},
        "focus": wheel.focus if wheel else [],
        "proposed_criterion_id": wheel.proposed_criterion_id if wheel else None,
        "note": wheel.note if wheel else "",
        "shared_at": wheel.shared_at.isoformat() if wheel and wheel.shared_at else None,
        "editable": editable,
    }


@router.get("/reviews/{review_id}/wheel")
def get_wheel(review_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id)
    wheel = session.exec(select(DevelopmentWheel).where(DevelopmentWheel.review_id == review.id)).first()
    is_employee = user.employee_id == review.employee_id
    if not is_employee:
        if not is_reviewer(session, user, review):
            raise HTTPException(403, "Koło rozwoju widzi oceniany i - po udostępnieniu - oceniający")
        if wheel is None or not wheel.shared_at:
            return {**_wheel_out(session, review, None, editable=False), "shared_at": None, "items": {}}
    return _wheel_out(session, review, wheel, editable=is_employee and review.status in WHEEL_STATUSES)


@router.put("/reviews/{review_id}/wheel")
def put_wheel(review_id: int, body: WheelIn, user: User = Depends(get_current_user),
              session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id)
    if user.employee_id != review.employee_id:
        raise HTTPException(403, "Koło rozwoju wypełnia oceniany")
    if review.status not in WHEEL_STATUSES:
        raise HTTPException(409, "Koło rozwoju można wypełniać na etapie I i w okresie oceny (etap II)")
    in_sheet = {c.id for _, c in review_entries(session, review)}
    if set(body.items) - in_sheet or set(body.focus) - in_sheet:
        raise HTTPException(422, "Koło obejmuje tylko kryteria z arkusza")
    out = _wheel_out(session, review, None, editable=True)
    if body.proposed_criterion_id is not None and body.proposed_criterion_id not in {
            c["criterion_id"] for c in out["proposable"]}:
        raise HTTPException(422, "Można zaproponować tylko kryterium dodatkowe spoza arkusza")
    wheel = session.exec(select(DevelopmentWheel).where(DevelopmentWheel.review_id == review.id)).first()         or DevelopmentWheel(review_id=review.id)
    wheel.items = {str(k): v.model_dump() for k, v in body.items.items()}
    wheel.focus = list(dict.fromkeys(body.focus))
    wheel.proposed_criterion_id = body.proposed_criterion_id
    wheel.note = body.note
    wheel.updated_at = utcnow()
    if body.share and not wheel.shared_at:
        wheel.shared_at = utcnow()
        notify_reviewer(session, review, "Oceniany udostępnił koło rozwoju",
                        "Przed rozmową rozpoczynającą: gdzie jest, gdzie chce być i nad czym chce pracować.")
    session.add(wheel)
    audit(session, user, "share" if body.share else "save", "development_wheel", review.id)
    session.commit()
    session.refresh(wheel)
    return _wheel_out(session, review, wheel, editable=True)
