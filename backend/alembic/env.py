from logging.config import fileConfig

from alembic import context
from sqlalchemy import (
    Column,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    engine_from_config,
    inspect,
    pool,
)
from sqlalchemy.exc import DBAPIError

from app.config import get_settings
from app.db.base import Base
from app.models import *  # noqa: F403

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _alembic_version_table():
    version_table = Table(
        "alembic_version",
        MetaData(),
        Column("version_num", String(64), nullable=False),
    )
    version_table.append_constraint(
        PrimaryKeyConstraint("version_num", name="alembic_version_pkc")
    )
    return version_table


def _is_duplicate_table_error(exc: DBAPIError) -> bool:
    return getattr(exc.orig, "sqlstate", None) == "42P07"


def ensure_alembic_version_table_compatibility(connection) -> None:
    if connection.dialect.name != "postgresql":
        return

    inspector = inspect(connection)
    if not inspector.has_table("alembic_version"):
        try:
            with connection.begin_nested():
                _alembic_version_table().create(connection)
        except DBAPIError as exc:
            if not _is_duplicate_table_error(exc):
                raise
        inspector = inspect(connection)

    version_columns = {
        column["name"]: column
        for column in inspector.get_columns("alembic_version")
    }
    version_num = version_columns.get("version_num")
    if version_num is None:
        raise RuntimeError("alembic_version.version_num column is missing.")

    declared_length = version_num.get("type").length
    if declared_length is not None and declared_length >= 64:
        return

    connection.exec_driver_sql(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"
    )


def run_migrations_offline():
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        with connection.begin():
            ensure_alembic_version_table_compatibility(connection)
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
