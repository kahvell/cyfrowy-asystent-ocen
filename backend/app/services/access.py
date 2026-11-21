"""Autoryzacja na poziomie danych (nie we frontendzie).

- manager widzi tylko swoich bezpośrednich podwładnych (employee.manager_id),
- employee widzi tylko siebie (w tym notatki na swój temat - przejrzystość, art. 15 RODO),
- hr widzi agregaty (endpointy /analytics) oraz sporządzone arkusze (dokumentacja kadrowa, sprzeciwy),
  bez szkiców ocen i bez dziennika obserwacji,
- admin widzi wszystko.
"""

from datetime import date

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import Employee, Review, Substitution, User

HR_VISIBLE = {"final", "acknowledged", "objection"}


def substituted_manager_ids(session: Session, user: User, on: date | None = None) -> set[int]:
    """Przełożeni, których użytkownik dziś zastępuje (zastępstwo wprowadzone przez komórkę kadrową)."""
    if user.employee_id is None:
        return set()
    on = on or date.today()
    rows = session.exec(select(Substitution.absent_employee_id).where(
        Substitution.deputy_employee_id == user.employee_id, Substitution.start <= on, Substitution.end >= on)).all()
    return set(rows)


def direct_report_ids(session: Session, user: User) -> set[int]:
    """Bezpośredni podwładni - także osób, które użytkownik aktualnie zastępuje."""
    if user.employee_id is None:
        return set()
    managers = {user.employee_id} | substituted_manager_ids(session, user)
    rows = session.exec(select(Employee.id).where(Employee.manager_id.in_(managers))).all()
    return set(rows) - {user.employee_id}


def can_access_employee(session: Session, user: User, employee_id: int) -> bool:
    if user.role == "admin":
        return True
    if user.employee_id == employee_id:
        return True
    if user.role == "manager":
        return employee_id in direct_report_ids(session, user)
    return False


def is_manager_of(session: Session, user: User, employee_id: int) -> bool:
    if user.role == "admin":
        return True
    return user.role == "manager" and employee_id in direct_report_ids(session, user)


def ensure_employee_access(session: Session, user: User, employee_id: int) -> Employee:
    emp = session.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma takiego pracownika")
    if not can_access_employee(session, user, employee_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Brak dostępu do danych tego pracownika")
    return emp


def get_review_for(session: Session, user: User, review_id: int, *, manage: bool = False) -> Review:
    """Zwraca ocenę, jeśli użytkownik ma do niej dostęp.
    manage=True wymaga roli oceniającego (przełożony ocenianego lub autor oceny)."""
    review = session.get(Review, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma takiej oceny")
    is_reviewer = review.reviewer_id == user.id or is_manager_of(session, user, review.employee_id)
    if manage:
        if not is_reviewer:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tylko oceniający może wykonać tę operację")
        return review
    if is_reviewer or user.employee_id == review.employee_id:
        return review
    # komórka kadrowa prowadzi dokumentację ocen sporządzonych i obsługuje sprzeciwy (bez szkiców i notatek)
    if user.role == "hr" and review.status in HR_VISIBLE:
        return review
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Brak dostępu do tej oceny")


def is_reviewer(session: Session, user: User, review: Review) -> bool:
    return review.reviewer_id == user.id or is_manager_of(session, user, review.employee_id)
