"""employee.senior_position - wyższe stanowiska w służbie cywilnej (art. 52, wyłączenie z IPR art. 108)

Revision ID: 0005
Revises: 0004
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("employee", schema=None) as batch_op:
        batch_op.add_column(sa.Column("senior_position", sa.Boolean(), nullable=False, server_default=sa.false()))
    # kierujący wydziałem w urzędzie wojewódzkim to wyższe stanowisko (art. 52 pkt 2) - dane demo:
    # kierownicy (arkusz B) bez przełożonego w strukturze
    op.execute("UPDATE employee SET senior_position = true WHERE sheet_type IN ('A', 'B') AND manager_id IS NULL")


def downgrade() -> None:
    with op.batch_alter_table("employee", schema=None) as batch_op:
        batch_op.drop_column("senior_position")
