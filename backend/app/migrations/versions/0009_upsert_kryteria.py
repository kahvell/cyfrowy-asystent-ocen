"""kryteria z seed/criteria.json - upsert po code (zmiana przepisów w działającej bazie)

Revision ID: 0009
Revises: 0008

`seed_reference()` wstawia kryteria tylko na pustej tabeli, więc zmiana rozporządzenia
albo korekta danych referencyjnych nie trafiałaby do bazy, która już działa w urzędzie.
Ta migracja synchronizuje kryteria z plikiem: brakujące kody dodaje, istniejące aktualizuje,
niczego nie usuwa (kryteria użyte w arkuszach muszą pozostać czytelne w historii ocen).
"""
import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_JSON = Path(__file__).resolve().parents[3] / "seed" / "criteria.json"

criterion = sa.table(
    "criterion",
    sa.column("id", sa.Integer),
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.Text),
    sa.column("behavioral_indicators", sa.JSON),
    sa.column("mandatory_for", sa.JSON),
    sa.column("keywords", sa.JSON),
    sa.column("order", sa.Integer),
)


def upgrade() -> None:
    data = json.loads(SEED_JSON.read_text(encoding="utf-8"))
    bind = op.get_bind()
    for i, c in enumerate(data["criteria"]):
        values = {
            "name": c["name"],
            "description": " ".join(c["indicators"]),
            "behavioral_indicators": c["indicators"],
            "mandatory_for": c["mandatory_for"],
            "keywords": c["keywords"],
            "order": i,
        }
        exists = bind.execute(sa.select(criterion.c.id).where(criterion.c.code == c["code"])).first()
        if exists:
            bind.execute(criterion.update().where(criterion.c.code == c["code"]).values(**values))
        else:
            bind.execute(criterion.insert().values(code=c["code"], **values))


def downgrade() -> None:
    # migracja danych: nie usuwamy kryteriów, bo są referencjami w arkuszach ocen
    pass
