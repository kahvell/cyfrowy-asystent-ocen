from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.analytics import stats
from app.db import get_session
from app.models import Employee, User
from app.security import require_roles
from app.services.access import direct_report_ids
from app.services.audit import audit

router = APIRouter(prefix="/analytics", tags=["analytics"])
# dashboard urzędu jest wyłącznie dla HR - administrator ma tryb korekty i panel kadrowy
hr_only = require_roles("hr")
# statystyki zespołu - przełożony (swoi podwładni) oraz administrator (tryb korekty)
team_only = require_roles("manager", "admin")


def _frame(session: Session, cycle_id: int | None, date_from: date | None, date_to: date | None) -> int | None:
    """Cykl, do którego zawężamy statystyki. Gdy podano zakres dat - obejmujemy wszystkie cykle
    w tym zakresie (bez domyślnego cyklu); w przeciwnym razie domyślny (najnowszy zamknięty) cykl."""
    if cycle_id:
        return cycle_id
    if date_from or date_to:
        return None
    c = stats.default_cycle(session)
    return c.id if c else None


@router.get("/overview")
def overview(cycle_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
             user: User = Depends(hr_only), session: Session = Depends(get_session)):
    cid = _frame(session, cycle_id, date_from, date_to)
    audit(session, user, "view", "analytics", cid)
    session.commit()
    return {
        "cycle_id": cid,
        "distribution": stats.distribution(session, cid, date_from, date_to),
        "competency_gaps": stats.competency_gaps(session, cid, date_from, date_to),
        "reviewer_calibration": stats.reviewer_calibration(session, cid, date_from, date_to),
        "gender_gap": stats.gender_gap(session, cid, date_from, date_to),
        "ai_adoption": stats.ai_adoption(session),
    }


@router.get("/distribution")
def distribution(cycle_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
                 _: User = Depends(hr_only), session: Session = Depends(get_session)):
    return stats.distribution(session, _frame(session, cycle_id, date_from, date_to), date_from, date_to)


@router.get("/competency-gaps")
def competency_gaps(cycle_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
                    _: User = Depends(hr_only), session: Session = Depends(get_session)):
    return stats.competency_gaps(session, _frame(session, cycle_id, date_from, date_to), date_from, date_to)


@router.get("/reviewer-calibration")
def reviewer_calibration(cycle_id: int | None = None, date_from: date | None = None, date_to: date | None = None,
                         _: User = Depends(hr_only), session: Session = Depends(get_session)):
    return stats.reviewer_calibration(session, _frame(session, cycle_id, date_from, date_to), date_from, date_to)


@router.get("/team")
def team(date_from: date | None = None, date_to: date | None = None,
         employee_ids: list[int] | None = Query(default=None, description="Wybrani podwładni (pominięte = wszyscy)"),
         user: User = Depends(team_only), session: Session = Depends(get_session)):
    """Statystyki wyników ocen podwładnych dla przełożonego. Pełne dane zespołu (bez progu k-anonimowości)."""
    allowed = set(session.exec(select(Employee.id)).all()) if user.role == "admin" \
        else direct_report_ids(session, user)
    if employee_ids:
        allowed = allowed & set(employee_ids)
    audit(session, user, "view", "analytics-team", None, employees=len(allowed))
    session.commit()
    return stats.team_stats(session, allowed, date_from, date_to)


@router.get("/ai-adoption")
def ai_adoption(_: User = Depends(hr_only), session: Session = Depends(get_session)):
    return stats.ai_adoption(session)
