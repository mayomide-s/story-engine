from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url

from app.db.base import Base


BACKEND_DIR = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "0019_publishing_gateway_core"
TEST_POSTGRES_DATABASE_URL = os.environ.get("TEST_POSTGRES_DATABASE_URL")


def _get_admin_url() -> URL:
    if not TEST_POSTGRES_DATABASE_URL:
        pytest.skip("TEST_POSTGRES_DATABASE_URL is not configured.")
    admin_url = make_url(TEST_POSTGRES_DATABASE_URL)
    if admin_url.get_backend_name() != "postgresql":
        pytest.skip("TEST_POSTGRES_DATABASE_URL must point to PostgreSQL.")
    if admin_url.database in {None, "", "sociopost"}:
        raise RuntimeError("TEST_POSTGRES_DATABASE_URL must not point to the normal sociopost database.")
    return admin_url


def _db_url(admin_url: URL, database_name: str) -> str:
    return admin_url.set(database=database_name).render_as_string(hide_password=False)


@contextmanager
def _temporary_database(admin_url: URL, prefix: str):
    database_name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin_engine = create_engine(
        admin_url.render_as_string(hide_password=False),
        future=True,
        isolation_level="AUTOCOMMIT",
    )
    try:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        yield database_name, _db_url(admin_url, database_name)
    finally:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}" WITH (FORCE)')
        admin_engine.dispose()


def _run_alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["PYTHONPATH"] = str(BACKEND_DIR)
    return subprocess.run(
        ["alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(not TEST_POSTGRES_DATABASE_URL, reason="TEST_POSTGRES_DATABASE_URL is not configured.")
def test_postgres_publication_gateway_migration_upgrade_downgrade_reupgrade():
    admin_url = _get_admin_url()
    with _temporary_database(admin_url, "story_engine_pgpub") as (_database_name, database_url):
        _run_alembic(database_url, "upgrade", "0018_postgres_migration_compatibility")
        _run_alembic(database_url, "upgrade", "0019_publishing_gateway_core")

        engine = create_engine(database_url, future=True)
        inspector = inspect(engine)
        assert "social_connections" in inspector.get_table_names()
        assert "oauth_states" in inspector.get_table_names()
        assert "publication_jobs" in inspector.get_table_names()
        assert "publication_targets" in inspector.get_table_names()

        _run_alembic(database_url, "downgrade", "0018_postgres_migration_compatibility")
        inspector = inspect(engine)
        assert "social_connections" not in inspector.get_table_names()
        assert "publication_jobs" not in inspector.get_table_names()

        _run_alembic(database_url, "upgrade", "0019_publishing_gateway_core")
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert revision == EXPECTED_HEAD
        engine.dispose()


@pytest.mark.skipif(not TEST_POSTGRES_DATABASE_URL, reason="TEST_POSTGRES_DATABASE_URL is not configured.")
def test_postgres_publication_gateway_create_all_supports_new_tables():
    admin_url = _get_admin_url()
    with _temporary_database(admin_url, "story_engine_pgpubcreate") as (_database_name, database_url):
        engine = create_engine(database_url, future=True)
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)

        social_columns = {column["name"]: column for column in inspector.get_columns("social_connections")}
        assert "encrypted_access_token" in social_columns
        assert "token_expires_at" in social_columns

        job_columns = {column["name"]: column for column in inspector.get_columns("publication_jobs")}
        assert "final_asset_sha256" in job_columns

        target_columns = {column["name"]: column for column in inspector.get_columns("publication_targets")}
        assert "provider_upload_uri_encrypted" in target_columns
        assert "published_at" in target_columns
        engine.dispose()


def test_sqlite_publication_gateway_create_all_supports_new_tables():
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()
    try:
        engine = create_engine(f"sqlite:///{temp_db.name}", future=True)
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)
        assert "social_connections" in inspector.get_table_names()
        assert "oauth_states" in inspector.get_table_names()
        assert "publication_jobs" in inspector.get_table_names()
        assert "publication_targets" in inspector.get_table_names()
        engine.dispose()
    finally:
        if os.path.exists(temp_db.name):
            os.unlink(temp_db.name)
