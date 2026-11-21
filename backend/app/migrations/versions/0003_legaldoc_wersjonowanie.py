"""legaldoc: nazwa pliku i skrót treści (ponowne indeksowanie zmienionych przepisów)

Revision ID: 0003
Revises: 0002
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("legaldoc", schema=None) as batch_op:
        batch_op.add_column(sa.Column("file_name", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("content_hash", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("legaldoc", schema=None) as batch_op:
        batch_op.drop_column("content_hash")
        batch_op.drop_column("file_name")
