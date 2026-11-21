from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.models import Criterion, Department, Employee, ReviewCycle, Training, User
from app.security import create_token, get_current_user, verify_password
from app.services.audit import audit
from app.services.scoring import SCALE

router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


def user_out(session: Session, user: User) -> dict:
    emp = session.get(Employee, user.employee_id) if user.employee_id else None
    dept = session.get(Department, emp.department_id) if emp else None
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "employee_id": user.employee_id,
        "position": emp.position if emp else None,
        "department": dept.name if dept else None,
    }


@router.post("/auth/login")
def login(body: LoginIn, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email == body.email.strip().lower())).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Nieprawidłowy e-mail lub hasło")
    audit(session, user, "login", "user", user.id)
    session.commit()
    return {"access_token": create_token(user), "token_type": "bearer", "user": user_out(session, user)}


@router.get("/me")
def me(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return user_out(session, user)


@router.get("/criteria")
def criteria(session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return session.exec(select(Criterion).order_by(Criterion.order)).all()


@router.get("/cycles")
def cycles(session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return session.exec(select(ReviewCycle).order_by(ReviewCycle.period_start.desc())).all()


@router.get("/trainings")
def trainings(session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return session.exec(select(Training)).all()


@router.get("/system/info")
def system_info():
    """Publiczna informacja, jaki model obsługuje asystenta - przejrzystość (AI Act)."""
    mode = settings.llm_mode
    return {
        "llm_mode": mode,
        "llm_model": "heurystyki (bez modelu językowego)" if mode == "fake" else settings.llm_model,
        "pseudonymize": settings.pseudonymize,
        "data_leaves_server": mode == "external",
        "k_anonymity": settings.k_anonymity,
        "scale": [{"value": k, "label": v} for k, v in SCALE.items()],
        "legal_basis": "Rozporządzenie Prezesa Rady Ministrów z dnia 4 kwietnia 2016 r. (Dz.U. 2016 poz. 470)",
    }
