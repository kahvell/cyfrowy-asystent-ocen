"""Powiadomienia: zawsze w systemie (dzwonek), a przy skonfigurowanym SMTP także e-mailem.

Integracja z pocztą urzędu wymaga tylko zmiennych SMTP_* w .env. Codzienne przypomnienia o terminach:
    python -m app.services.notify digest      (np. z crona / harmonogramu zadań o 7:00)
"""

import logging
import smtplib
import sys
from email.message import EmailMessage

from sqlmodel import Session, select

from app.config import settings
from app.models import Employee, Notification, Review, User, utcnow

log = logging.getLogger(__name__)


def _send_email(to: str, subject: str, body: str) -> bool:
    if not settings.smtp_host:
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
            if settings.smtp_starttls:
                s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        log.warning("Nie wysłano e-maila do %s: %s", to, exc)
        return False


def notify(session: Session, user_id: int | None, subject: str, body: str = "", link: str = "") -> None:
    """Dodaje powiadomienie (commit po stronie wywołującego). Treść bez danych wrażliwych - szczegóły w systemie."""
    if user_id is None:
        return
    n = Notification(user_id=user_id, subject=subject, body=body, link=link)
    user = session.get(User, user_id)
    if user and _send_email(user.email, subject, f"{body}\n\n{settings.app_url}{link}".strip()):
        n.emailed_at = utcnow()
    session.add(n)


def employee_user_id(session: Session, employee_id: int) -> int | None:
    u = session.exec(select(User).where(User.employee_id == employee_id)).first()
    return u.id if u else None


def notify_employee(session: Session, review: Review, subject: str, body: str = "") -> None:
    notify(session, employee_user_id(session, review.employee_id), subject, body, f"/reviews/{review.id}")


def notify_reviewer(session: Session, review: Review, subject: str, body: str = "") -> None:
    emp = session.get(Employee, review.employee_id)
    notify(session, review.reviewer_id, f"{subject}: {emp.full_name if emp else ''}", body, f"/reviews/{review.id}")


def notify_hr(session: Session, subject: str, body: str = "", link: str = "") -> None:
    for u in session.exec(select(User).where(User.role == "hr")).all():
        notify(session, u.id, subject, body, link)


def daily_digest(session: Session) -> int:
    """Przypomnienia o terminach dla wszystkich użytkowników (scheduler z przypadków użycia)."""
    from app.api.reminders import reminders_for

    sent = 0
    for user in session.exec(select(User)).all():
        items = [r for r in reminders_for(session, user) if r["severity"] in ("critical", "warning")]
        if not items:
            continue
        body = "\n".join(f"- {r['title']}" + (f" (termin: {r['due']})" if r["due"] else "") for r in items)
        notify(session, user.id, f"Terminy w procesie ocen okresowych ({len(items)})", body, "/")
        sent += 1
    session.commit()
    return sent


if __name__ == "__main__" and sys.argv[1:2] == ["digest"]:
    from app.db import engine, init_db

    init_db()
    with Session(engine) as s:
        print(f"Wysłano przypomnienia do {daily_digest(s)} użytkowników")
