"""Indywidualny Program Rozwoju Zawodowego (IPR)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from app.ai.pipelines import generate_ipr
from app.ai.rag import retrieve
from app.db import get_session
from app.models import IPR, AISuggestion, Criterion, Employee, IPRGoal, Training, User, utcnow
from app.security import get_current_user
from app.services.access import get_review_for, is_reviewer
from app.services.audit import audit
from app.services.reviews import review_entries

router = APIRouter(tags=["ipr"])


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
    if ipr and ipr.status == "approved":
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
    get_review_for(session, user, ipr.review_id, manage=manage)
    return ipr


@router.get("/ipr/{ipr_id}")
def get_ipr(ipr_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    ipr = _get_ipr(session, user, ipr_id)
    review = get_review_for(session, user, ipr.review_id)
    if not is_reviewer(session, user, review) and ipr.status != "approved":
        raise HTTPException(403, "IPR będzie widoczny po zatwierdzeniu przez przełożonego")
    return ipr_out(session, ipr)


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
    status: str | None = None  # "approved"


@router.patch("/ipr/{ipr_id}")
def patch_ipr(ipr_id: int, body: IPRPatch, user: User = Depends(get_current_user),
              session: Session = Depends(get_session)):
    ipr = _get_ipr(session, user, ipr_id, manage=True)
    if ipr.status == "approved":
        raise HTTPException(409, "IPR jest już zatwierdzony")
    if body.summary is not None:
        ipr.summary = body.summary
    if body.goals is not None:
        session.exec(delete(IPRGoal).where(IPRGoal.ipr_id == ipr.id))
        for g in body.goals:
            session.add(IPRGoal(ipr_id=ipr.id, **g.model_dump()))
    session.flush()
    if body.status == "approved":
        ipr.status = "approved"
        ipr.approved_at = utcnow()
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
    ipr.updated_at = utcnow()
    session.add(ipr)
    audit(session, user, "update", "ipr", ipr.id, status=ipr.status)
    session.commit()
    session.refresh(ipr)
    return ipr_out(session, ipr)
