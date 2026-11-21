"""ipr: ustalenie, akceptacja kierującego komórką, zatwierdzenie DG (art. 108 ustawy)

Revision ID: 0004
Revises: 0003
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ipr", schema=None) as batch_op:
        batch_op.add_column(sa.Column("established_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("accepted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("accepted_by", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("approved_by", sa.Integer(), nullable=True))
    # dotychczasowe „approved” (zatwierdzenie przez przełożonego) = ustalenie przez przełożonego
    op.execute("UPDATE ipr SET status = 'established', established_at = approved_at, approved_at = NULL "
               "WHERE status = 'approved'")


def downgrade() -> None:
    op.execute("UPDATE ipr SET status = 'approved', approved_at = established_at WHERE status <> 'draft'")
    with op.batch_alter_table("ipr", schema=None) as batch_op:
        batch_op.drop_column("approved_by")
        batch_op.drop_column("accepted_by")
        batch_op.drop_column("accepted_at")
        batch_op.drop_column("established_at")
