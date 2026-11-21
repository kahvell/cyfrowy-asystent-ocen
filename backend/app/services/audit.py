from typing import Any

from sqlmodel import Session

from app.models import AuditLog, User


def audit(
    session: Session,
    user: User | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    **details: Any,
) -> None:
    """Dopisuje wpis do audit_log (dostęp do danych osobowych, decyzje dot. AI). Nie commituje."""
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details,
        )
    )
