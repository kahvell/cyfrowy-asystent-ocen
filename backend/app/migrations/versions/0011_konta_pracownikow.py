"""konta pracowników: e-mail imie.nazwisko@demo.gov.pl dla każdego pracownika

Revision ID: 0011
Revises: 0010

Konta i adresy e-mail tworzy `seed.py` tylko na pustej bazie. Baza uruchomiona wcześniej (demo albo
instalacja w urzędzie) nie dostałaby kont dla pracowników ani nowych adresów. Ta migracja:
  - zakłada konto z hasłem demo123 każdemu pracownikowi, który go jeszcze nie ma,
  - porządkuje adresy kont powiązanych z pracownikami do formatu imie.nazwisko@demo.gov.pl.

Konta kadr (`hr@`) i administratora (`admin@`) - niepowiązane z pracownikiem - nie są zmieniane.
Migracja jest zachowawcza: gdy adres docelowy jest już zajęty, wpis zostaje bez zmian.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.demo_data import DEMO_PASSWORD, email_for
from app.security import hash_password

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

employee = sa.table(
    "employee",
    sa.column("id", sa.Integer),
    sa.column("full_name", sa.String),
    sa.column("sheet_type", sa.String),
)

user = sa.table(
    "user",
    sa.column("id", sa.Integer),
    sa.column("email", sa.String),
    sa.column("full_name", sa.String),
    sa.column("password_hash", sa.String),
    sa.column("role", sa.String),
    sa.column("employee_id", sa.Integer),
)


def _role(sheet_type: str | None) -> str:
    return "manager" if sheet_type in ("A", "B") else "employee"


def upgrade() -> None:
    bind = op.get_bind()
    employees = bind.execute(sa.select(employee.c.id, employee.c.full_name, employee.c.sheet_type)).all()
    if not employees:
        return  # świeża baza - dane demo utworzy seed
    users = bind.execute(sa.select(user.c.id, user.c.email, user.c.employee_id)).all()
    linked = {u.employee_id: u for u in users if u.employee_id is not None}
    taken = {u.email.lower() for u in users}
    password_hash = hash_password(DEMO_PASSWORD)
    for emp in employees:
        target = email_for(emp.full_name)
        account = linked.get(emp.id)
        if account is None:
            if target.lower() in taken:
                continue  # adres zajęty (inny pracownik o tym samym imieniu i nazwisku) - nie nadpisujemy
            bind.execute(user.insert().values(
                email=target, full_name=emp.full_name, password_hash=password_hash,
                role=_role(emp.sheet_type), employee_id=emp.id))
            taken.add(target.lower())
        elif account.email.lower() != target.lower():
            if target.lower() in taken:
                continue
            bind.execute(user.update().where(user.c.id == account.id).values(email=target))
            taken.discard(account.email.lower())
            taken.add(target.lower())


def downgrade() -> None:
    # migracja danych: nie przywracamy poprzednich adresów ani nie usuwamy kont (są potrzebne do logowania)
    pass
