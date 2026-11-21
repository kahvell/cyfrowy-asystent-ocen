"""employee.contract_type - podstawa zatrudnienia (art. 81 ust. 1: kto podlega ocenie okresowej)

Revision ID: 0006
Revises: 0005
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("employee", schema=None) as batch_op:
        batch_op.add_column(sa.Column("contract_type", sa.String(), nullable=False, server_default="nieokreslony"))
    op.execute("UPDATE employee SET contract_type = 'mianowanie' WHERE is_civil_servant")


def downgrade() -> None:
    with op.batch_alter_table("employee", schema=None) as batch_op:
        batch_op.drop_column("contract_type")
