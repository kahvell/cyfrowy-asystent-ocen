"""Indywidualny Program Rozwoju Zawodowego (IPR) - art. 108 ustawy o służbie cywilnej.

Bezpośredni przełożony ustala IPR (m.in. na podstawie wniosków z oceny okresowej), program akceptuje
osoba kierująca komórką organizacyjną, a zatwierdza dyrektor generalny urzędu (w systemie: rola hr).
Wnioski do IPR trafiają do arkusza oceny w chwili ustalenia programu (§ 11 ust. 1 pkt 5 rozporządzenia).
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from app.ai.pipelines import generate_ipr
from app.ai.rag import retrieve
from app.db import get_session
from app.models import IPR, AISuggestion, Criterion, Employee, IPRGoal, Review, Training, User, utcnow
from app.security import get_current_user
from app.services.access import get_review_for, is_reviewer
from app.services.audit import audit
from app.services.notify import notify, notify_employee, notify_hr
from app.services.reviews import review_entries

router = APIRouter(tags=["ipr"])

VISIBLE_TO_EMPLOYEE = {"established", "accepted", "approved"}


def unit_head_user(session: Session, employee: Employee) -> User | None:
    """Osoba kierująca komórką organizacyjną ocenianego: kierownik w tej komórce, który nie podlega
    nikomu z tej samej komórki."""
    heads = session.exec(select(Employee).where(Employee.department_id == employee.department_id,
                                                Employee.sheet_type.in_(["A", "B"]), Employee.active)).all()
    for h in heads:
        boss = session.get(Employee, h.manager_id) if h.manager_id else None
        if boss is None or boss.department_id != h.department_id:
            return session.exec(select(User).where(User.employee_id == h.id)).first()
    return None


def _can_accept(session: Session, user: User, ipr: IPR) -> bool:
    emp = session.get(Employee, ipr.employee_id)
    head = unit_head_user(session, emp) if emp else None
    return ipr.status == "established" and (user.role == "admin" or (head is not None and head.id == user.id))


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, min(d.day, 28))


def ipr_out(session: Session, ipr: IPR) -> dict:
    goals = session.exec(select(IPRGoal).where(IPRGoal.ipr_id == ipr.id).order_by(IPRGoal.id)).all()
    crit = {c.id: c for c in session.exec(select(Criterion)).all()}
    trainings = {t.id: t for t in session.exec(select(Training)).all()}
    emp = session.get(Employee, ipr.employee_id)
    sugg = session.get(AISuggestion, ipr.ai_suggestion_id) if ipr.ai_suggestion_id else None
    return {
        "id": ipr.id, "review_id": ipr.review_id, "status": ipr.status, "summary": ipr.summary,
        "employee": {"id": emp.id, "full_name": emp.full_name, "position": emp.position},
        "established_at": ipr.established_at.isoformat() if ipr.established_at else None,
        "accepted_at": ipr.accepted_at.isoformat() if ipr.accepted_at else None,
        "approved_at": ipr.approved_at.isoformat() if ipr.approved_at else None,
        "ai": {"model": sugg.model, "prompt_version": sugg.prompt_version, "status": sugg.status} if sugg else None,
        "goals": [
            {
                "id": g.id, "criterion_id": g.criterion_id,
                "criterion_name": crit[g.criterion_id].name if g.criterion_id in crit else None,
                "goal": g.goal, "actions": g.actions, "success_measure": g.success_measure,
                "deadline": g.deadline.isoformat() if g.deadline else None,
                "training": ({"id": g.training_id, "code": trainings[g.training_id].code,
                              "title": trainings[g.training_id].title, "hours": trainings[g.training_id].hours,
                              "format": trainings[g.training_id].format}
                             if g.training_id in trainings else None),
            }
            for g in goals
        ],
    }


@router.post("/reviews/{review_id}/ipr/generate")
def generate(review_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id, manage=True)
    emp = session.get(Employee, review.employee_id)
    if emp and emp.senior_position:
        raise HTTPException(409, "Osoby na wyższych stanowiskach w służbie cywilnej (art. 52) nie mają IPR "
                                 "(art. 108 ust. 1). Wnioski dotyczące rozwoju zawodowego wpisz bezpośrednio w arkuszu "
                                 "(art. 81 ust. 5).")
    entries = review_entries(session, review)
    scored = [(rc, c) for rc, c in entries if rc.score is not None]
    if not scored:
        raise HTTPException(409, "Najpierw wystaw oceny cząstkowe - IPR opiera się na słabszych kryteriach")
    weak = sorted([x for x in scored if x[0].score <= 5], key=lambda x: x[0].score)[:3]
    focus = weak or sorted(scored, key=lambda x: x[0].score)[:2]
    focus_ctx = [{"code": c.code, "name": c.name, "score": rc.score, "justification": rc.justification}
                 for rc, c in focus]
    all_trainings = session.exec(select(Training)).all()
    codes = {f["code"] for f in focus_ctx}
    trainings = [{"code": t.code, "title": t.title, "criterion_codes": t.criterion_codes}
                 for t in all_trainings if codes & set(t.criterion_codes)]
    legal = [{"ref": h.ref, "text": h.text} for h in
             retrieve(session, "indywidualny program rozwoju zawodowego kierunki rozwoju wnioski", k=2)]
    emp = session.get(Employee, review.employee_id)
    res = generate_ipr(focus_ctx, trainings, legal, employee_name=emp.full_name, position=emp.position,
                       position_description=emp.position_description)

    ipr = session.exec(select(IPR).where(IPR.review_id == review.id)).first()
    if ipr and ipr.status != "draft":
        raise HTTPException(409, "IPR jest już zatwierdzony")
    sugg = AISuggestion(review_id=review.id, kind="ipr", payload=res.data.model_dump(), model=res.model,
                        prompt_version=res.prompt_version, created_by=user.id)
    session.add(sugg)
    session.flush()
    if ipr is None:
        ipr = IPR(review_id=review.id, employee_id=review.employee_id)
        session.add(ipr)
        session.flush()
    else:
        session.exec(delete(IPRGoal).where(IPRGoal.ipr_id == ipr.id))
    ipr.summary = res.data.summary
    ipr.ai_suggestion_id = sugg.id
    ipr.updated_at = utcnow()
    crit_by_code = {c.code: c for _, c in entries}
    train_by_code = {t.code: t for t in all_trainings}
    base = date.today()
    for g in res.data.goals:
        session.add(IPRGoal(
            ipr_id=ipr.id,
            criterion_id=crit_by_code[g.criterion_code].id if g.criterion_code in crit_by_code else None,
            goal=g.goal, actions=g.actions, success_measure=g.success_measure,
            deadline=_add_months(base, g.deadline_months),
            training_id=train_by_code[g.training_code].id if g.training_code in train_by_code else None,
        ))
    session.add(ipr)
    audit(session, user, "ai_generate", "ipr", ipr.id, model=res.model)
    session.commit()
    session.refresh(ipr)
    return ipr_out(session, ipr)


def _get_ipr(session: Session, user: User, ipr_id: int, manage: bool = False) -> IPR:
    ipr = session.get(IPR, ipr_id)
    if ipr is None:
        raise HTTPException(404, "Nie ma takiego IPR")
    if not manage and user.role == "hr" and ipr.status in ("accepted", "approved"):
        return ipr  # dyrektor generalny / komórka kadrowa: zatwierdzenie programu
    if not manage and ipr.status in ("established", "accepted") and _can_accept(session, user, ipr):
        return ipr  # kierujący komórką (gdy nie jest bezpośrednim przełożonym)
    get_review_for(session, user, ipr.review_id, manage=manage)
    return ipr


def _with_rights(session: Session, user: User, ipr: IPR) -> dict:
    out = ipr_out(session, ipr)
    review = session.get(Review, ipr.review_id)
    out["can_edit"] = ipr.status == "draft" and review is not None and is_reviewer(session, user, review)
    out["can_accept"] = _can_accept(session, user, ipr)
    out["can_approve"] = ipr.status == "accepted" and user.role in ("hr", "admin")
    return out


@router.get("/ipr/{ipr_id}")
def get_ipr(ipr_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    ipr = _get_ipr(session, user, ipr_id)
    review = session.get(Review, ipr.review_id)
    if user.employee_id == review.employee_id and ipr.status not in VISIBLE_TO_EMPLOYEE:
        raise HTTPException(403, "IPR będzie widoczny po ustaleniu go przez przełożonego")
    return _with_rights(session, user, ipr)


@router.get("/ipr")
def list_ipr(status: str = "accepted", user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Programy czekające na zatwierdzenie przez dyrektora generalnego."""
    if user.role not in ("hr", "admin"):
        raise HTTPException(403, "Lista dla dyrektora generalnego / komórki kadrowej")
    rows = session.exec(select(IPR).where(IPR.status == status).order_by(IPR.updated_at)).all()
    return [ipr_out(session, i) for i in rows]


class GoalIn(BaseModel):
    criterion_id: int | None = None
    goal: str
    actions: str = ""
    success_measure: str = ""
    deadline: date | None = None
    training_id: int | None = None


class IPRPatch(BaseModel):
    summary: str | None = None
    goals: list[GoalIn] | None = None
    status: str | None = None  # "established" - ustalenie programu przez bezpośredniego przełożonego


@router.patch("/ipr/{ipr_id}")
def patch_ipr(ipr_id: int, body: IPRPatch, user: User = Depends(get_current_user),
              session: Session = Depends(get_session)):
    ipr = _get_ipr(session, user, ipr_id, manage=True)
    if ipr.status != "draft":
        raise HTTPException(409, "IPR został już ustalony - zmiany wymagają nowego programu")
    if body.summary is not None:
        ipr.summary = body.summary
    if body.goals is not None:
        session.exec(delete(IPRGoal).where(IPRGoal.ipr_id == ipr.id))
        for g in body.goals:
            session.add(IPRGoal(ipr_id=ipr.id, **g.model_dump()))
    session.flush()
    if body.status in ("established", "approved"):  # "approved" - zgodność wsteczna API
        ipr.status = "established"
        ipr.established_at = utcnow()
        sugg = session.get(AISuggestion, ipr.ai_suggestion_id) if ipr.ai_suggestion_id else None
        if sugg and sugg.status == "pending":
            original = {g["goal"] for g in sugg.payload.get("goals", [])}
            current = {g.goal for g in session.exec(select(IPRGoal).where(IPRGoal.ipr_id == ipr.id)).all()}
            sugg.status = "accepted" if original == current and sugg.payload.get("summary") == ipr.summary else "edited"
            sugg.decided_at = utcnow()
            sugg.decided_by = user.id
            session.add(sugg)
        # wnioski do arkusza oceny (§ 11 ust. 1 pkt 5)
        review = get_review_for(session, user, ipr.review_id, manage=True)
        out = ipr_out(session, ipr)
        lines = [ipr.summary] + [
            f"- {g['goal']} (termin: {g['deadline'] or 'do ustalenia'}"
            f"{'; szkolenie: ' + g['training']['title'] if g['training'] else ''})" for g in out["goals"]]
        review.ipr_conclusions = "\n".join(lines)
        session.add(review)
        emp = session.get(Employee, ipr.employee_id)
        head = unit_head_user(session, emp) if emp else None
        if head is not None and head.id == user.id:
            # przełożony jest jednocześnie kierującym komórką - ustalenie i akceptacja w jednym kroku
            ipr.status, ipr.accepted_at, ipr.accepted_by = "accepted", utcnow(), user.id
            notify_hr(session, f"IPR do zatwierdzenia: {emp.full_name}", "Art. 108 ust. 2 ustawy o służbie cywilnej.",
                      f"/ipr/{ipr.id}")
        elif head is not None:
            notify(session, head.id, f"IPR do akceptacji: {emp.full_name}", "Art. 108 ust. 2 ustawy.", f"/ipr/{ipr.id}")
    ipr.updated_at = utcnow()
    session.add(ipr)
    audit(session, user, "update", "ipr", ipr.id, status=ipr.status)
    session.commit()
    session.refresh(ipr)
    return _with_rights(session, user, ipr)


@router.post("/ipr/{ipr_id}/accept")
def accept_ipr(ipr_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Akceptacja przez osobę kierującą komórką organizacyjną (art. 108 ust. 2)."""
    ipr = session.get(IPR, ipr_id)
    if ipr is None:
        raise HTTPException(404, "Nie ma takiego IPR")
    if not _can_accept(session, user, ipr):
        raise HTTPException(403, "IPR akceptuje osoba kierująca komórką organizacyjną (po ustaleniu programu)")
    ipr.status, ipr.accepted_at, ipr.accepted_by, ipr.updated_at = "accepted", utcnow(), user.id, utcnow()
    session.add(ipr)
    emp = session.get(Employee, ipr.employee_id)
    notify_hr(session, f"IPR do zatwierdzenia: {emp.full_name if emp else ''}", "Art. 108 ust. 2 ustawy.", f"/ipr/{ipr.id}")
    audit(session, user, "accept", "ipr", ipr.id)
    session.commit()
    session.refresh(ipr)
    return _with_rights(session, user, ipr)


@router.post("/ipr/{ipr_id}/approve")
def approve_ipr(ipr_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Zatwierdzenie przez dyrektora generalnego urzędu (art. 108 ust. 2) - w systemie rola hr."""
    if user.role not in ("hr", "admin"):
        raise HTTPException(403, "IPR zatwierdza dyrektor generalny urzędu")
    ipr = session.get(IPR, ipr_id)
    if ipr is None:
        raise HTTPException(404, "Nie ma takiego IPR")
    if ipr.status != "accepted":
        raise HTTPException(409, "IPR musi być najpierw ustalony przez przełożonego i zaakceptowany przez kierującego komórką")
    ipr.status, ipr.approved_at, ipr.approved_by, ipr.updated_at = "approved", utcnow(), user.id, utcnow()
    session.add(ipr)
    review = session.get(Review, ipr.review_id)
    if review:
        notify_employee(session, review, "Zatwierdzono Twój indywidualny program rozwoju zawodowego",
                        "Program jest podstawą kierowania na szkolenia (art. 108 ustawy o służbie cywilnej).")
        notify(session, review.reviewer_id, "Zatwierdzono IPR", "", f"/ipr/{ipr.id}")
    audit(session, user, "approve", "ipr", ipr.id)
    session.commit()
    session.refresh(ipr)
    return _with_rights(session, user, ipr)
