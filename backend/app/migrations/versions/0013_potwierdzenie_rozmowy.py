"""review.assessment_confirmed_at - potwierdzenie terminu rozmowy oceniającej przez ocenianego

Revision ID: 0013
Revises: 0012

Etap IV („Rozmowa oceniająca”) jest bramkowany potwierdzeniem przez ocenianego: dopiero po zaproszeniu
(.ics, `assessment_invited_at`) i zatwierdzeniu terminu przez ocenianego odblokowuje się ustalenie daty
rozmowy i stwierdzenie jej odbycia (§ 10). Migracja dodaje kolumnę na moment tego potwierdzenia.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.add_column(sa.Column("assessment_confirmed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.drop_column("assessment_confirmed_at")
