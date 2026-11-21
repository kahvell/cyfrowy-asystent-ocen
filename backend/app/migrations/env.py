"""Środowisko migracji Alembic. Uruchamiane automatycznie przy starcie aplikacji (app.db.init_db)
albo ręcznie: python -m app.db upgrade | revision "opis" """

from alembic import context
from sqlmodel import SQLModel

from app import models  # noqa: F401  (rejestracja tabel w metadanych)

target_metadata = SQLModel.metadata


def run_migrations_online() -> None:
    connectable = context.config.attributes.get("connection")
    if connectable is None:
        from app.db import engine

        connectable = engine.connect()
    context.configure(connection=connectable, target_metadata=target_metadata,
                      render_as_batch=True,  # ALTER TABLE na SQLite
                      compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
