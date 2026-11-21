"""Wirtualny HR partner przełożonego: sygnały dobrostanu, kultura doceniania, przygotowanie do rozmów.

Dostęp ma wyłącznie bezpośredni przełożony (nie HR, nie oceniany) - to narzędzie wsparcia w zarządzaniu
ludźmi, a nie element oceny okresowej. Sygnały nie wpływają na ocenę i nie są nigdzie agregowane.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.ai.pipelines import conversation_prep
from app.analytics.wellbeing import NoteIn, analyze
from app.api.ai import suggestion_out
from app.db import get_session
from app.models import AISuggestion, Employee, Note, SelfAssessment, User
from app.security import get_current_user
from app.services.access import direct_report_ids, get_review_for, is_manager_of
from app.services.audit import audit
from app.services.process import absences
from app.services.reviews import notes_for_review, people_names, review_entries

router = APIRouter(tags=["hr-partner"])


def _notes(session: Session, employee_id: int) -> list[Note]:
    return list(session.exec(select(Note).where(Note.employee_id == employee_id).order_by(Note.date)).all())


def employee_signals(session: Session, employee_id: int, today: date | None = None) -> dict:
    notes = [NoteIn(n.id, n.date, n.text, n.sentiment, n.source) for n in _notes(session, employee_id)]
    emp = session.get(Employee, employee_id)
    return analyze(notes, absences(session, employee_id), today or date.today(),
                   emp.employment_start if emp else None)


@router.get("/employees/{employee_id}/hr-partner")
def hr_partner(employee_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if not is_manager_of(session, user, employee_id):
        raise HTTPException(403, "Wsparcie HR partnera jest dostępne dla bezpośredniego przełożonego")
    emp = session.get(Employee, employee_id)
    audit(session, user, "view", "hr_partner", employee_id)
    session.commit()
    return {"employee_id": employee_id, "full_name": emp.full_name if emp else "", **employee_signals(session, employee_id)}


@router.get("/team/hr-partner")
def team_hr_partner(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Skrót dla listy zespołu: poziom sygnałów i momenty do docenienia (bez treści notatek)."""
    if user.role != "manager":
        raise HTTPException(403, "Dostępne dla przełożonych")
    out = []
    for eid in sorted(direct_report_ids(session, user)):
        a = employee_signals(session, eid)
        out.append({"employee_id": eid, "risk": a["risk"], "titles": [s["title"] for s in a["signals"]
                                                                      if s["severity"] != "info"],
                    "appreciation": len(a["appreciation"])})
    return out


@router.post("/reviews/{review_id}/ai/conversation-prep")
def ai_conversation_prep(review_id: int, kind: Literal["opening", "feedback", "assessment", "difficult"],
                         user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id, manage=True)
    emp = session.get(Employee, review.employee_id)
    entries = review_entries(session, review)
    notes = [n for n in _notes(session, review.employee_id) if n.date >= review.period_start]
    if kind == "feedback":
        notes = notes[-8:]
    ctx = {
        "employee_name": emp.full_name,
        "position": emp.position,
        "duties": emp.position_description,
        "criteria": [c.name for _, c in entries],
        "notes": [{"date": n.date.isoformat(), "text": n.text, "sentiment": n.sentiment} for n in notes[-20:]],
        "strong": [c.name for rc, c in entries if rc.score and rc.score >= 7],
        "weak": [c.name for rc, c in entries if rc.score and rc.score <= 3],
        "negative": review.result == "negatywna",
        "self_rows": [],
        "signals": [s for s in employee_signals(session, emp.id)["signals"] if s["severity"] != "info"],
    }
    if kind in ("assessment", "difficult"):
        # notatki przypisane do kryteriów - podstawa informacji zwrotnej „sytuacja - zachowanie - skutek”
        period_notes, tags = notes_for_review(session, review)
        detail = []
        for rc, c in entries:
            tagged = [n for n in period_notes if any(t.criterion_id == c.id for t in tags.get(n.id, []))]
            detail.append({"name": c.name, "score": rc.score, "justification": rc.justification,
                           "notes": [{"id": n.id, "date": n.date.isoformat(), "text": n.text, "sentiment": n.sentiment}
                                     for n in tagged[-3:]]})
        ctx["criteria_detail"] = detail
    sa = session.exec(select(SelfAssessment).where(SelfAssessment.review_id == review.id)).first()
    if kind in ("assessment", "difficult") and sa and sa.submitted_at:
        ctx["self_rows"] = [{"name": c.name, "manager_score": rc.score,
                             "self_score": sa.items.get(str(c.id), {}).get("score")} for rc, c in entries]
    res = conversation_prep(kind, ctx, people_names(session, review))
    s = AISuggestion(review_id=review.id, kind=f"conversation_prep:{kind}", payload=res.data.model_dump(),
                     model=res.model, prompt_version=res.prompt_version, status="info", created_by=user.id)
    session.add(s)
    session.commit()
    session.refresh(s)
    return suggestion_out(s)
