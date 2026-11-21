"""Przypomnienia o terminach - „scheduler” z przypadków użycia KPRM.

Liczone przy odczycie z dat w bazie (bez osobnego procesu), więc działają tak samo w każdym urzędzie.
Ten sam moduł można wywołać z crona i wysyłać e-maile (integracja opisana w README).
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.models import IPR, Employee, IPRGoal, Review, ReviewCycle, SelfAssessment, User
from app.security import get_current_user
from app.services import deadlines as dl
from app.services.access import direct_report_ids
from app.services.process import obligatory_promotion, second_negative_risk

router = APIRouter(tags=["reminders"])


def _item(kind: str, title: str, detail: str, due: date | None, link: str, today: date,
          severity: str | None = None) -> dict:
    if severity is None:
        days = (due - today).days if due else None
        severity = "critical" if days is not None and days < 0 else "warning" if days is not None and days <= 14 else "info"
    return {"kind": kind, "title": title, "detail": detail, "due": due.isoformat() if due else None,
            "severity": severity, "link": link}


def reminders_for(session: Session, user: User, today: date | None = None, scope: str = "all") -> list[dict]:
    """`scope`: „self” - tylko sprawy samego użytkownika jako ocenianego (widok /me),
    „team” - zadania o zespole / sprawy kadrowe (widok /team, dashboard), „all” - jedno i drugie."""
    today = today or date.today()
    out: list[dict] = []
    soon = dl.RULES["reminder_days"]
    with_team = scope in ("all", "team")
    with_self = scope in ("all", "self")

    if with_team and user.role == "manager":
        team_ids = direct_report_ids(session, user)
        q = select(Review, Employee).join(Employee, Employee.id == Review.employee_id)
        if team_ids is not None:
            q = q.where(Review.employee_id.in_(team_ids or {-1}))
        for r, e in session.exec(q).all():
            link = f"/reviews/{r.id}"
            if r.status == "criteria" and not r.criteria_reviewer_confirmed_at:
                out.append(_item("criteria_deadline", f"Wyznacz kryteria: {e.full_name}",
                                 "Wybierz kryteria dodatkowe (maks. 3), przeprowadź rozmowę rozpoczynającą i potwierdź "
                                 "w części I arkusza - 30 dni od zatrudnienia lub poprzedniej oceny (§ 5-7 rozporządzenia).",
                                 r.criteria_deadline, link, today))
            elif r.status == "criteria":
                out.append(_item("employee_confirm_criteria", f"Czeka na potwierdzenie: {e.full_name}",
                                 "Oceniany nie potwierdził jeszcze zapoznania z kryteriami.", None, link, today, "info"))
            elif r.status in ("observation", "draft", "submitted", "discussed") and r.due_date \
                    and (r.due_date - today).days <= soon:
                stage = {"observation": "okres oceny - rozpocznij przygotowanie oceny",
                         "draft": "przygotowanie oceny - uzupełnij oceny cząstkowe i uzasadnienia",
                         "submitted": "gotowa do rozmowy - przeprowadź rozmowę oceniającą (§ 10)",
                         "discussed": "po rozmowie - sporządź ocenę na piśmie i wnioski do IPR (§ 11)"}[r.status]
                out.append(_item("review_due", f"Zbliża się termin oceny: {e.full_name}",
                                 f"Etap: {stage}. Ocena co 24 miesiące (art. 81 ust. 4 ustawy).", r.due_date, link, today))
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
        # cele IPR z bliskim lub minionym terminem - przełożony monitoruje rozwój (Standardy ZZL VI pkt 3 ust. 5)
        if team_ids:
            goals = session.exec(select(IPRGoal, IPR, Employee).join(IPR, IPR.id == IPRGoal.ipr_id)
                                 .join(Employee, Employee.id == IPR.employee_id)
                                 .where(IPR.employee_id.in_(team_ids), IPR.status != "draft",
                                        IPRGoal.deadline.is_not(None))).all()
            for g, ipr, e in goals:
                if (g.deadline - today).days <= 30:
                    out.append(_item("ipr_goal", f"Cel IPR do sprawdzenia: {e.full_name}",
                                     f"„{g.goal[:90]}” - porozmawiaj o postępach (monitorowanie rozwoju, Standardy ZZL).",
                                     g.deadline, f"/ipr/{ipr.id}", today))
        # pracownicy bez arkusza w otwartym cyklu
        if team_ids:
            open_cycle = session.exec(select(ReviewCycle).where(ReviewCycle.status == "open")).first()
            if open_cycle:
                has = set(session.exec(select(Review.employee_id).where(Review.cycle_id == open_cycle.id)).all())
                for e in session.exec(select(Employee).where(Employee.id.in_(team_ids - has), Employee.active,
                                                             Employee.contract_type != "okreslony")).all():
                    out.append(_item("no_review", f"Brak arkusza oceny: {e.full_name}",
                                     "Rozpocznij cykl oceny: wybór arkusza i kryteriów.", None,
                                     f"/employees/{e.id}", today, "info"))

    if with_self and user.employee_id:
        for r in session.exec(select(Review).where(Review.employee_id == user.employee_id)).all():
            link = f"/reviews/{r.id}"
            if r.status == "criteria" and r.criteria_reviewer_confirmed_at:
                out.append(_item("confirm_criteria", "Potwierdź zapoznanie z kryteriami oceny",
                                 "Przełożony wyznaczył kryteria i termin oceny.", None, link, today, "warning"))
            elif r.status == "final":
                out.append(_item("acknowledge", "Zapoznaj się z oceną okresową",
                                 "Po zapoznaniu masz 7 dni na ewentualny sprzeciw (art. 83 ust. 1).", None, link, today,
                                 "warning"))
            elif r.status in ("observation", "draft", "submitted") and r.due_date and (r.due_date - today).days <= soon:
                sa_done = session.exec(select(SelfAssessment).where(SelfAssessment.review_id == r.id,
                                                                    SelfAssessment.submitted_at.is_not(None))).first()
                can_self = r.status in ("observation", "draft") and not sa_done
                out.append(_item("review_due_employee", "Zbliża się termin Twojej oceny okresowej",
                                 "Przełożony zaprosi Cię na rozmowę oceniającą." + (
                                     " Wypełnij samoocenę, zanim przełożony przekaże ocenę do rozmowy." if can_self
                                     else ""),
                                 r.due_date, f"{link}/self" if can_self else link, today))
            elif r.status == "acknowledged" and r.acknowledged_at:
                od = dl.objection_deadline(r.acknowledged_at)
                if today <= od:
                    out.append(_item("objection_window", "Termin na sprzeciw od oceny",
                                     "Sprzeciw do dyrektora generalnego urzędu (art. 83 ust. 1).", od, link, today, "info"))

    if with_team and user.role == "hr":
        for r, e in session.exec(select(Review, Employee).join(Employee, Employee.id == Review.employee_id)
                                 .where(Review.status.in_(["objection", "acknowledged"]))).all():
            link = f"/reviews/{r.id}"
            if r.status == "objection" and r.objection_at:
                out.append(_item("objection", f"Sprzeciw do rozpatrzenia: {e.full_name}",
                                 "Rozpatrzenie w 14 dni od wniesienia (art. 83 ust. 3).",
                                 dl.days_deadline(r.objection_at, dl.RULES["objection_decision_days"]), link, today))
            elif r.acknowledged_at and second_negative_risk(session, r):
                out.append(_item("termination", f"Druga z rzędu ocena negatywna: {e.full_name}",
                                 "Urzędnik służby cywilnej - rozwiązanie stosunku pracy z 3-miesięcznym wypowiedzeniem "
                                 "(art. 71 ust. 1 pkt 1 ustawy).", None, link, today, "critical"))
            elif r.acknowledged_at and today <= dl.promotion_deadline(r.acknowledged_at) \
                    and obligatory_promotion(session, r):
                out.append(_item("obligatory_promotion", f"Obligatoryjny kolejny stopień służbowy: {e.full_name}",
                                 "Dwie kolejne oceny na jednym z dwóch najwyższych poziomów (art. 89 ust. 2).",
                                 dl.promotion_deadline(r.acknowledged_at), link, today))

    if with_team and user.role == "hr":
        for ipr, e in session.exec(select(IPR, Employee).join(Employee, Employee.id == IPR.employee_id)
                                   .where(IPR.status == "accepted")).all():
            out.append(_item("ipr_approval", f"IPR do zatwierdzenia: {e.full_name}",
                             "Zaakceptowany przez kierującego komórką - zatwierdza dyrektor generalny (art. 108 ust. 2).",
                             None, f"/ipr/{ipr.id}", today, "warning"))

    order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(out, key=lambda x: (order[x["severity"]], x["due"] or "9999"))


@router.get("/reminders")
def get_reminders(scope: Literal["self", "team", "all"] = "all", user: User = Depends(get_current_user),
                  session: Session = Depends(get_session)):
    return reminders_for(session, user, scope=scope)
