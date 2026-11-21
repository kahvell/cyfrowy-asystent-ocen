"""substitution - zastępstwa przełożonych (przypadek użycia „zarządza zastępstwami”)

Revision ID: 0007
Revises: 0006
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "substitution",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("absent_employee_id", sa.Integer(), nullable=False),
        sa.Column("deputy_employee_id", sa.Integer(), nullable=False),
        sa.Column("start", sa.Date(), nullable=False),
        sa.Column("end", sa.Date(), nullable=False),
        sa.Column("note", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["absent_employee_id"], ["employee.id"]),
        sa.ForeignKeyConstraint(["deputy_employee_id"], ["employee.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("substitution", schema=None) as batch_op:
        batch_op.create_index("ix_substitution_absent_employee_id", ["absent_employee_id"])
        batch_op.create_index("ix_substitution_deputy_employee_id", ["deputy_employee_id"])


def downgrade() -> None:
    op.drop_table("substitution")
