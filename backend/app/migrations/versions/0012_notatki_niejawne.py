"""note.shared_with_employee - notatki przełożonego domyślnie niejawne

Revision ID: 0012
Revises: 0011

Dziennik obserwacji prowadzony przez naczelnika jest jego notatką roboczą. Do tej pory każda
notatka była od razu widoczna dla pracownika. Od teraz notatki przełożonego (source="manager")
są domyślnie niejawne i widzi je tylko przełożony; pracownik zobaczy je dopiero po świadomym
udostępnieniu (przycisk „Udostępnij podwładnemu”). Notatki własne pracownika (source="self")
pozostają widoczne dla pracownika niezależnie od tej flagi.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("note", schema=None) as batch_op:
        batch_op.add_column(sa.Column("shared_with_employee", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("note", schema=None) as batch_op:
        batch_op.drop_column("shared_with_employee")
