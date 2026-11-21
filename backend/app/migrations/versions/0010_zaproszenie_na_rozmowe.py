"""review.assessment_invited_at - moment zaproszenia na rozmowę oceniającą

Revision ID: 0010
Revises: 0009

Pola etapu „Rozmowa oceniająca” (data rozmowy i jej potwierdzenie) są zablokowane, dopóki
oceniający nie umówi rozmowy - wysłanie zaproszenia .ics zapisuje tu datę odblokowania.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.add_column(sa.Column("assessment_invited_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("review", schema=None) as batch_op:
        batch_op.drop_column("assessment_invited_at")
