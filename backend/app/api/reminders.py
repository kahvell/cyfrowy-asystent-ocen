"""Przypomnienia o terminach - „scheduler” z przypadków użycia KPRM.

Liczone przy odczycie z dat w bazie (bez osobnego procesu), więc działają tak samo w każdym urzędzie.
Ten sam moduł można wywołać z crona i wysyłać e-maile (integracja opisana w README).
"""

from datetime import date

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.models import Employee, Review, ReviewCycle, SelfAssessment, User
from app.security import get_current_user
from app.services import deadlines as dl
from app.services.access import direct_report_ids
from app.services.process import obligatory_promotion

router = APIRouter(tags=["reminders"])


def _item(kind: str, title: str, detail: str, due: date | None, link: str, today: date,
          severity: str | None = None) -> dict:
    if severity is None:
        days = (due - today).days if due else None
        severity = "critical" if days is not None and days < 0 else "warning" if days is not None and days <= 14 else "info"
    return {"kind": kind, "title": title, "detail": detail, "due": due.isoformat() if due else None,
            "severity": severity, "link": link}


def reminders_for(session: Session, user: User, today: date | None = None) -> list[dict]:
    today = today or date.today()
    out: list[dict] = []
    soon = dl.RULES["reminder_days"]

    if user.role in ("manager", "admin"):
        team_ids = direct_report_ids(session, user) if user.role == "manager" else None
        q = select(Review, Employee).join(Employee, Employee.id == Review.employee_id)
        if team_ids is not None:
            q = q.where(Review.employee_id.in_(team_ids or {-1}))
        for r, e in session.exec(q).all():
            link = f"/reviews/{r.id}"
            if r.status == "criteria" and not r.criteria_reviewer_confirmed_at:
                out.append(_item("criteria_deadline", f"Wyznacz kryteria: {e.full_name}",
                                 "Wybór kryteriów dodatkowych i rozmowa rozpoczynająca ocenę (§ 5).",
                                 r.criteria_deadline, link, today))
            elif r.status == "criteria":
                out.append(_item("employee_confirm_criteria", f"Czeka na potwierdzenie: {e.full_name}",
                                 "Oceniany nie potwierdził jeszcze zapoznania z kryteriami.", None, link, today, "info"))
            elif r.status in ("observation", "draft", "submitted", "discussed") and r.due_date \
                    and (r.due_date - today).days <= soon:
                out.append(_item("review_due", f"Zbliża się termin oceny: {e.full_name}",
                                 "Przygotuj ocenę i umów rozmowę oceniającą (§ 10).", r.due_date, link, today))
            elif r.status == "final":
                waited = (today - r.reviewer_signed_at).days if r.reviewer_signed_at else 0
                out.append(_item("awaiting_ack", f"Oczekuje na zapoznanie: {e.full_name}",
                                 "Oceniany nie potwierdził zapoznania z oceną." + (
                                     " Jeśli nie może lub nie chce - możesz stwierdzić fikcję zapoznania."
                                     if waited >= 7 else ""), None, link, today, "warning" if waited >= 7 else "info"))
            if r.status == "acknowledged" and r.result == "negatywna" and r.acknowledged_at:
                out.append(_item("repeat_review", f"Ponowna ocena po ocenie negatywnej: {e.full_name}",
                                 "Oceniany podlega ponownej ocenie po 6 miesiącach (art. 81 ust. 9).",
                                 dl.repeat_review_date(r.acknowledged_at), link, today))
        # pracownicy bez arkusza w otwartym cyklu
        if team_ids:
            open_cycle = session.exec(select(ReviewCycle).where(ReviewCycle.status == "open")).first()
            if open_cycle:
                has = set(session.exec(select(Review.employee_id).where(Review.cycle_id == open_cycle.id)).all())
                for e in session.exec(select(Employee).where(Employee.id.in_(team_ids - has))).all():
                    out.append(_item("no_review", f"Brak arkusza oceny: {e.full_name}",
                                     "Rozpocznij cykl oceny: wybór arkusza i kryteriów.", None,
                                     f"/employees/{e.id}", today, "info"))

    if user.employee_id:
        for r in session.exec(select(Review).where(Review.employee_id == user.employee_id)).all():
            link = f"/reviews/{r.id}"
            if r.status == "criteria" and r.criteria_reviewer_confirmed_at:
                out.append(_item("confirm_criteria", "Potwierdź zapoznanie z kryteriami oceny",
                                 "Przełożony wyznaczył kryteria i termin oceny.", None, link, today, "warning"))
            elif r.status == "final":
                out.append(_item("acknowledge", "Zapoznaj się z oceną okresową",
                                 "Po zapoznaniu masz 7 dni na ewentualny sprzeciw (art. 83 ust. 1).", None, link, today,
                                 "warning"))
            elif r.status in ("observation", "draft") and r.due_date and (r.due_date - today).days <= soon                     and not session.exec(select(SelfAssessment).where(SelfAssessment.review_id == r.id,
                                                                      SelfAssessment.submitted_at.is_not(None))).first():
                out.append(_item("self_assessment", "Zbliża się ocena okresowa - wypełnij samoocenę",
                                 "Samoocena pomoże w rozmowie oceniającej.", r.due_date, f"{link}/self", today))
            elif r.status == "acknowledged" and r.acknowledged_at:
                od = dl.objection_deadline(r.acknowledged_at)
                if today <= od:
                    out.append(_item("objection_window", "Termin na sprzeciw od oceny",
                                     "Sprzeciw do dyrektora generalnego urzędu (art. 83 ust. 1).", od, link, today, "info"))

    if user.role in ("hr", "admin"):
        for r, e in session.exec(select(Review, Employee).join(Employee, Employee.id == Review.employee_id)
                                 .where(Review.status.in_(["objection", "acknowledged"]))).all():
            link = f"/reviews/{r.id}"
            if r.status == "objection" and r.objection_at:
                out.append(_item("objection", f"Sprzeciw do rozpatrzenia: {e.full_name}",
                                 "Rozpatrzenie w 14 dni od wniesienia (art. 83 ust. 3).",
                                 dl.days_deadline(r.objection_at, dl.RULES["objection_decision_days"]), link, today))
            elif r.acknowledged_at and today <= dl.promotion_deadline(r.acknowledged_at) \
                    and obligatory_promotion(session, r):
                out.append(_item("obligatory_promotion", f"Obligatoryjny kolejny stopień służbowy: {e.full_name}",
                                 "Dwie kolejne oceny na jednym z dwóch najwyższych poziomów (art. 89 ust. 2).",
                                 dl.promotion_deadline(r.acknowledged_at), link, today))

    order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda x: (order[x["severity"]], x["due"] or "9999"))


@router.get("/reminders")
def get_reminders(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return reminders_for(session, user)
