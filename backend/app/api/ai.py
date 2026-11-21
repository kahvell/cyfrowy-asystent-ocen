"""Asystent AI w arkuszu oceny. AI tylko proponuje; każda propozycja to `ai_suggestion`
ze statusem pending -> accepted / edited / rejected (decyzja człowieka trafia do audit_log)."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.ai.pipelines import compare_self, draft_justification, quality_check_llm
from app.analytics.stats import reviewer_calibration
from app.db import get_session
from app.models import (
    AISuggestion,
    Criterion,
    Employee,
    Review,
    ReviewCriterion,
    SelfAssessment,
    User,
    utcnow,
)
from app.security import get_current_user
from app.services.access import get_review_for
from app.services.audit import audit
from app.services.reviews import (
    criterion_ctx,
    notes_for_criterion,
    people_names,
    review_entries,
    rule_warnings,
)

router = APIRouter(tags=["ai"])


def suggestion_out(s: AISuggestion) -> dict[str, Any]:
    return {
        "id": s.id, "kind": s.kind, "review_id": s.review_id, "criterion_id": s.criterion_id, "payload": s.payload,
        "model": s.model, "prompt_version": s.prompt_version, "status": s.status, "final_payload": s.final_payload,
        "created_at": s.created_at.isoformat(), "decided_at": s.decided_at.isoformat() if s.decided_at else None,
    }


def _ensure_editable(review: Review) -> None:
    if review.status not in ("draft", "discussed"):
        raise HTTPException(409, "Ocena nie jest w trakcie edycji")


@router.post("/reviews/{review_id}/ai/draft")
def ai_draft(review_id: int, criterion_id: int, user: User = Depends(get_current_user),
             session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id, manage=True)
    _ensure_editable(review)
    crit = session.get(Criterion, criterion_id)
    if crit is None or criterion_id not in {c.id for _, c in review_entries(session, review)}:
        raise HTTPException(422, "Kryterium nie należy do tej oceny")
    notes = notes_for_criterion(session, review, criterion_id)
    emp = session.get(Employee, review.employee_id)
    if not notes:
        payload = {"sentences": [], "proposed_score": None, "notes_used": 0,
                   "rationale": "Brak notatek dla tego kryterium w okresie oceny - asystent nie generuje "
                                "uzasadnienia bez dowodów. Dodaj obserwacje w dzienniku lub napisz uzasadnienie samodzielnie."}
        model, version = "none", "n/a"
    else:
        res = draft_justification(criterion_ctx(crit), notes, employee_name=emp.full_name, position=emp.position,
                                  period_start=review.period_start, period_end=review.period_end)
        data = res.data.model_dump()
        for s in data["sentences"]:
            s["unsupported"] = not s["source_note_ids"]
        payload = {**data, "notes_used": len(notes)}
        model, version = res.model, res.prompt_version
    s = AISuggestion(review_id=review.id, criterion_id=criterion_id, kind="draft_justification", payload=payload,
                     model=model, prompt_version=version, created_by=user.id)
    session.add(s)
    audit(session, user, "ai_generate", "ai_suggestion", None, kind="draft_justification", review_id=review.id,
          model=model)
    session.commit()
    session.refresh(s)
    return suggestion_out(s)


@router.post("/reviews/{review_id}/ai/quality-check")
def ai_quality_check(review_id: int, use_llm: bool = True, user: User = Depends(get_current_user),
                     session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id, manage=True)
    warnings = rule_warnings(session, review)
    entries = review_entries(session, review)
    by_code = {c.code: c for _, c in entries}

    # kalibracja: jak ten oceniający wypada na tle urzędu (SQL)
    calib = next((r for r in reviewer_calibration(session) if r["reviewer_id"] == review.reviewer_id), None)
    if calib and calib.get("flag"):
        warnings.append({
            "code": "calibration", "severity": "info", "criterion_id": None, "source": "rule", "evidence": [],
            "title": "Kalibracja oceniającego",
            "message": f"Twoje wcześniejsze oceny są średnio {calib['delta']:+.1f} pkt od średniej urzędu "
                       f"({calib['flag']}).",
            "suggestion": "Porównaj swoją skalę z innymi oceniającymi - to nie zarzut, tylko punkt odniesienia.",
        })

    model, version = "rules", "rules"
    if use_llm and any(rc.justification.strip() for rc, _ in entries):
        res = quality_check_llm(
            [{"code": c.code, "score": rc.score, "justification": rc.justification} for rc, c in entries],
            review.justification, people_names(session, review))
        model, version = res.model, res.prompt_version
        seen = {(w.get("criterion_id"), w["code"]) for w in warnings}
        titles = {"vague": "Ogólnikowe uzasadnienie", "biased": "Język do weryfikacji",
                  "inconsistent": "Niespójność tekstu z oceną"}
        for issue in res.data.issues:
            c = by_code.get(issue.criterion_code or "")
            key = (c.id if c else None, {"vague": "vague", "biased": "biased_language"}.get(issue.kind, issue.kind))
            if key in seen:
                continue
            warnings.append({
                "code": f"ai_{issue.kind}", "severity": "warning", "criterion_id": c.id if c else None,
                "title": f"{titles[issue.kind]}{': ' + c.name if c else ''}", "message": issue.explanation,
                "suggestion": issue.suggestion, "evidence": [issue.excerpt] if issue.excerpt else [], "source": "ai",
            })
    s = AISuggestion(review_id=review.id, kind="quality_check", payload={"warnings": warnings}, model=model,
                     prompt_version=version, status="info", created_by=user.id)
    session.add(s)
    audit(session, user, "ai_generate", "ai_suggestion", None, kind="quality_check", review_id=review.id)
    session.commit()
    session.refresh(s)
    return {"suggestion_id": s.id, "model": model, "warnings": warnings}


@router.post("/reviews/{review_id}/ai/compare-self")
def ai_compare_self(review_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id, manage=True)
    sa = session.exec(select(SelfAssessment).where(SelfAssessment.review_id == review.id)).first()
    if sa is None or sa.submitted_at is None:
        raise HTTPException(409, "Pracownik nie przekazał jeszcze samooceny")
    rows = []
    for rc, c in review_entries(session, review):
        item = sa.items.get(str(c.id), {})
        rows.append({"criterion_id": c.id, "code": c.code, "name": c.name, "manager_score": rc.score,
                     "self_score": item.get("score"), "comment": item.get("comment", "")})
    res = compare_self(rows, sa.summary, people_names(session, review))
    for r in rows:
        diff = (r["self_score"] - r["manager_score"]) if r["self_score"] and r["manager_score"] else None
        r["diff"] = diff
        r["level"] = None if diff is None else ("major" if abs(diff) >= 4 else "minor" if abs(diff) >= 2 else "agree")
    payload = {"rows": rows, **res.data.model_dump()}
    s = AISuggestion(review_id=review.id, kind="compare_self", payload=payload, model=res.model,
                     prompt_version=res.prompt_version, status="info", created_by=user.id)
    session.add(s)
    session.commit()
    session.refresh(s)
    return suggestion_out(s)


@router.get("/reviews/{review_id}/ai-suggestions")
def list_suggestions(review_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    review = get_review_for(session, user, review_id, manage=True)
    # przygotowanie ocenianego do rozmowy jest jego własnym materiałem - oceniający go nie widzi
    rows = session.exec(select(AISuggestion).where(AISuggestion.review_id == review.id,
                                                   AISuggestion.kind != "employee_opening_prep")
                        .order_by(AISuggestion.created_at.desc())).all()
    return [suggestion_out(s) for s in rows]


class DecisionIn(BaseModel):
    status: Literal["accepted", "edited", "rejected"]
    final_text: str | None = None
    source_note_ids: list[int] | None = None


@router.post("/ai-suggestions/{suggestion_id}/decision")
def decide(suggestion_id: int, body: DecisionIn, user: User = Depends(get_current_user),
           session: Session = Depends(get_session)):
    s = session.get(AISuggestion, suggestion_id)
    if s is None or s.review_id is None:
        raise HTTPException(404, "Nie ma takiej sugestii")
    review = get_review_for(session, user, s.review_id, manage=True)
    if s.status not in ("pending",):
        raise HTTPException(409, "O tej sugestii już zdecydowano")
    s.status = body.status
    s.decided_at = utcnow()
    s.decided_by = user.id
    if s.kind == "draft_justification" and body.status in ("accepted", "edited"):
        _ensure_editable(review)
        text = body.final_text if body.status == "edited" and body.final_text else \
            " ".join(x["text"] for x in s.payload.get("sentences", []))
        sources = body.source_note_ids if body.source_note_ids is not None else sorted(
            {i for x in s.payload.get("sentences", []) for i in x["source_note_ids"]})
        rc = session.exec(select(ReviewCriterion).where(ReviewCriterion.review_id == review.id,
                                                        ReviewCriterion.criterion_id == s.criterion_id)).first()
        if rc:
            # AI pisze tylko uzasadnienie; ocenę cząstkową zawsze wystawia człowiek
            rc.justification = text
            rc.source_note_ids = sources
            session.add(rc)
        s.final_payload = {"text": text, "source_note_ids": sources}
    session.add(s)
    audit(session, user, f"ai_{body.status}", "ai_suggestion", s.id, kind=s.kind, review_id=review.id)
    session.commit()
    session.refresh(s)
    return suggestion_out(s)
