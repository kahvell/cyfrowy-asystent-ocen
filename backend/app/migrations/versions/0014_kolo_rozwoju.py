"""developmentwheel - koło rozwoju ocenianego na etapie I

Revision ID: 0014
Revises: 0013

Przed rozmową rozpoczynającą (§ 5) oceniany zaznacza, gdzie jest i gdzie chciałby być w każdym kryterium,
wskazuje maks. 2 kryteria, nad którymi chce pracować, i może zaproponować kryterium dodatkowe. Przełożony widzi
koło po udostępnieniu; wskazania pracownika są jednym z sygnałów propozycji kryteriów dodatkowych.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "developmentwheel",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("review_id", sa.Integer(), sa.ForeignKey("review.id"), nullable=False, unique=True),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("focus", sa.JSON(), nullable=False),
        sa.Column("proposed_criterion_id", sa.Integer(), sa.ForeignKey("criterion.id"), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("shared_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("developmentwheel")
