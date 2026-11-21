from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.analytics import stats
from app.db import get_session
from app.models import User
from app.security import require_roles
from app.services.audit import audit

router = APIRouter(prefix="/analytics", tags=["analytics"])
hr_only = require_roles("hr", "admin")


def _cycle(session: Session, cycle_id: int | None) -> int | None:
    if cycle_id:
        return cycle_id
    c = stats.default_cycle(session)
    return c.id if c else None


@router.get("/overview")
def overview(cycle_id: int | None = None, user: User = Depends(hr_only), session: Session = Depends(get_session)):
    cid = _cycle(session, cycle_id)
    audit(session, user, "view", "analytics", cid)
    session.commit()
    return {
        "cycle_id": cid,
        "distribution": stats.distribution(session, cid),
        "competency_gaps": stats.competency_gaps(session, cid),
        "reviewer_calibration": stats.reviewer_calibration(session, cid),
        "gender_gap": stats.gender_gap(session, cid),
        "ai_adoption": stats.ai_adoption(session),
    }


@router.get("/distribution")
def distribution(cycle_id: int | None = None, _: User = Depends(hr_only), session: Session = Depends(get_session)):
    return stats.distribution(session, _cycle(session, cycle_id))


@router.get("/competency-gaps")
def competency_gaps(cycle_id: int | None = None, _: User = Depends(hr_only), session: Session = Depends(get_session)):
    return stats.competency_gaps(session, _cycle(session, cycle_id))


@router.get("/reviewer-calibration")
def reviewer_calibration(cycle_id: int | None = None, _: User = Depends(hr_only),
                         session: Session = Depends(get_session)):
    return stats.reviewer_calibration(session, _cycle(session, cycle_id))


@router.get("/ai-adoption")
def ai_adoption(_: User = Depends(hr_only), session: Session = Depends(get_session)):
    return stats.ai_adoption(session)
