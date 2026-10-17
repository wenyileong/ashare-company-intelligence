"""Alembic environment. Run through ``ashare.migrate.upgrade`` (or the
``db-upgrade`` command), which passes the open connection in
``config.attributes['connection']``; the database URL comes from the
application's own settings (``ASHARE_DB`` or ``ASHARE_DB_URL``)."""
from alembic import context

from ashare.models import Base, engine

target_metadata = Base.metadata
connection = context.config.attributes.get("connection")


def _run(conn):
    context.configure(connection=conn, target_metadata=target_metadata,
                      render_as_batch=conn.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=str(engine().url), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif connection is not None:
    _run(connection)
else:
    with engine().begin() as conn:
        _run(conn)
