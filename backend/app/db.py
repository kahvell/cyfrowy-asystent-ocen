"""Silnik bazy, sesje i migracje schematu (Alembic).

Aktualizacja systemu w urzędzie = nowy obraz + automatyczne `alembic upgrade head` przy starcie,
bez utraty danych. Baza utworzona wcześniej przez create_all (wersje MVP) jest oznaczana jako
wersja bazowa i dalej migrowana.
"""

import sys
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import inspect
from sqlmodel import Session, create_engine

from app.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args, pool_pre_ping=True)

MIGRATIONS = Path(__file__).resolve().parent / "migrations"
BASELINE = "0001"


def alembic_config():
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return cfg


def init_db() -> None:
    from alembic import command
    from alembic.runtime.migration import MigrationContext

    cfg = alembic_config()
    with engine.begin() as conn:
        app_tables = set(inspect(conn).get_table_names()) - {"alembic_version"}
        current = MigrationContext.configure(conn).get_current_revision()
        cfg.attributes["connection"] = conn
        if app_tables and current is None:
            command.stamp(cfg, BASELINE)  # baza z create_all (MVP) = wersja bazowa
        command.upgrade(cfg, "head")


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


if __name__ == "__main__":  # python -m app.db upgrade | revision "opis zmiany"
    from alembic import command

    if sys.argv[1:2] == ["revision"]:
        command.revision(alembic_config(), message=" ".join(sys.argv[2:]) or "zmiana", autogenerate=True)
    else:
        init_db()
