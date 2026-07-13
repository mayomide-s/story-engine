import os
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import Account, PipelineRun
from app.models.entities import PipelineStatus
from app.models.entities import PerformanceLearning


BACKEND_DIR = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "0020_youtube_publication_execution"
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


def _current_revision(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _version_column_length(engine) -> int | None:
    inspector = inspect(engine)
    version_column = next(
        column for column in inspector.get_columns("alembic_version")
        if column["name"] == "version_num"
    )
    return version_column["type"].length


def _create_run(engine, topic: str) -> str:
    with Session(engine) as session:
        account = Account(name=f"acct-{uuid.uuid4().hex[:8]}", niche="coding")
        session.add(account)
        session.flush()
        run = PipelineRun(account_id=account.id, topic=topic, status=PipelineStatus.COMPLETED)
        session.add(run)
        session.commit()
        return run.id


def _insert_learning_without_is_archived(engine, run_id: str, observation: str) -> PerformanceLearning:
    learning_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO performance_learnings (
                    id,
                    pipeline_run_id,
                    learning_type,
                    observation,
                    created_at,
                    updated_at
                ) VALUES (
                    :id,
                    :pipeline_run_id,
                    :learning_type,
                    :observation,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "id": learning_id,
                "pipeline_run_id": run_id,
                "learning_type": "observation",
                "observation": observation,
                "created_at": now,
                "updated_at": now,
            },
        )
    with Session(engine) as session:
        learning = session.get(PerformanceLearning, learning_id)
        assert learning is not None
        return learning


def _create_learning_with_explicit_is_archived(engine, run_id: str, observation: str, is_archived: bool) -> PerformanceLearning:
    with Session(engine) as session:
        learning = PerformanceLearning(
            pipeline_run_id=run_id,
            learning_type="observation",
            observation=observation,
            is_archived=is_archived,
        )
        session.add(learning)
        session.commit()
        session.refresh(learning)
        return learning


def _postgres_default_expression(engine) -> str | None:
    with engine.connect() as connection:
        return connection.execute(
            text(
                """
                SELECT column_default
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'performance_learnings'
                  AND column_name = 'is_archived'
                """
            )
        ).scalar_one()


def _widen_version_column(engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"
        )


@pytest.mark.skipif(not TEST_POSTGRES_DATABASE_URL, reason="TEST_POSTGRES_DATABASE_URL is not configured.")
def test_postgres_fresh_database_upgrades_from_base_to_head_and_is_idempotent():
    admin_url = _get_admin_url()
    with _temporary_database(admin_url, "story_engine_pgbase") as (_database_name, database_url):
        engine = create_engine(database_url, future=True)
        inspector = inspect(engine)
        assert "alembic_version" not in inspector.get_table_names()

        _run_alembic(database_url, "upgrade", "head")

        assert _current_revision(engine) == EXPECTED_HEAD
        assert _version_column_length(engine) == 64

        with engine.connect() as connection:
            version_rows = connection.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar_one()
        assert version_rows == 1

        inspector = inspect(engine)
        manual_package_columns = {column["name"] for column in inspector.get_columns("manual_post_packages")}
        assert {"winner_platform_post_id", "winner_selected_at", "winner_selection_revision"} <= manual_package_columns
        assert "performance_learnings" in inspector.get_table_names()

        run_id = _create_run(engine, "Postgres fresh base")
        learning = _insert_learning_without_is_archived(engine, run_id, "Fresh base default should be false.")
        assert learning.is_archived is False
        assert _postgres_default_expression(engine) == "false"

        _run_alembic(database_url, "upgrade", "head")
        assert _current_revision(engine) == EXPECTED_HEAD
        assert _version_column_length(engine) == 64
        engine.dispose()


@pytest.mark.skipif(not TEST_POSTGRES_DATABASE_URL, reason="TEST_POSTGRES_DATABASE_URL is not configured.")
def test_postgres_migration_upgrade_from_0015_and_repeated_head_is_idempotent():
    admin_url = _get_admin_url()
    with _temporary_database(admin_url, "story_engine_pg0015") as (_database_name, database_url):
        _run_alembic(database_url, "upgrade", "0015_platform_posts_snapshots")

        engine = create_engine(database_url, future=True)
        assert _version_column_length(engine) == 64
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)"
            )
        assert _version_column_length(engine) == 32

        _run_alembic(database_url, "upgrade", "head")

        inspector = inspect(engine)
        assert _version_column_length(engine) == 64
        assert _current_revision(engine) == EXPECTED_HEAD

        manual_package_columns = {column["name"] for column in inspector.get_columns("manual_post_packages")}
        assert {"winner_platform_post_id", "winner_selected_at", "winner_selection_revision"} <= manual_package_columns
        assert "performance_learnings" in inspector.get_table_names()

        run_id = _create_run(engine, "Postgres scenario A")
        learning = _insert_learning_without_is_archived(engine, run_id, "Default should be false.")
        assert learning.is_archived is False
        assert _postgres_default_expression(engine) == "false"

        _run_alembic(database_url, "upgrade", "head")
        assert _current_revision(engine) == EXPECTED_HEAD
        engine.dispose()


@pytest.mark.skipif(not TEST_POSTGRES_DATABASE_URL, reason="TEST_POSTGRES_DATABASE_URL is not configured.")
def test_postgres_existing_0017_upgrades_to_0018_without_rewriting_learning_data():
    admin_url = _get_admin_url()
    with _temporary_database(admin_url, "story_engine_pg0017") as (_database_name, database_url):
        _run_alembic(database_url, "upgrade", "0015_platform_posts_snapshots")
        engine = create_engine(database_url, future=True)
        _widen_version_column(engine)
        _run_alembic(database_url, "upgrade", "0017_performance_learnings")

        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE performance_learnings ALTER COLUMN is_archived DROP DEFAULT"
            )

        run_id = _create_run(engine, "Postgres scenario B")
        learning = _create_learning_with_explicit_is_archived(engine, run_id, "Existing learning survives.", False)
        before = {
            "id": learning.id,
            "observation": learning.observation,
            "is_archived": learning.is_archived,
        }

        _run_alembic(database_url, "upgrade", "head")
        assert _current_revision(engine) == EXPECTED_HEAD

        with Session(engine) as session:
            persisted = session.get(PerformanceLearning, learning.id)
            assert persisted is not None
            assert persisted.id == before["id"]
            assert persisted.observation == before["observation"]
            assert persisted.is_archived == before["is_archived"]

        second_run_id = _create_run(engine, "Postgres scenario B follow-up")
        second_learning = _insert_learning_without_is_archived(engine, second_run_id, "New default remains false.")
        assert second_learning.is_archived is False
        assert _postgres_default_expression(engine) == "false"
        engine.dispose()


@pytest.mark.skipif(not TEST_POSTGRES_DATABASE_URL, reason="TEST_POSTGRES_DATABASE_URL is not configured.")
def test_postgres_direct_create_all_uses_portable_false_default():
    admin_url = _get_admin_url()
    with _temporary_database(admin_url, "story_engine_pgcreateall") as (_database_name, database_url):
        engine = create_engine(database_url, future=True)
        Base.metadata.create_all(bind=engine)

        inspector = inspect(engine)
        assert "performance_learnings" in inspector.get_table_names()

        run_id = _create_run(engine, "Postgres create_all")
        learning = _insert_learning_without_is_archived(engine, run_id, "Create all succeeds.")
        assert learning.is_archived is False
        assert _postgres_default_expression(engine) == "false"
        engine.dispose()


def test_sqlite_direct_create_all_accepts_false_default():
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()
    try:
        engine = create_engine(f"sqlite:///{temp_db.name}", future=True)
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)
        columns = {column["name"]: column for column in inspector.get_columns("performance_learnings")}
        assert columns["is_archived"]["default"] in {"0", "false", "FALSE", "False", None}

        run_id = _create_run(engine, "SQLite create_all")
        learning = _insert_learning_without_is_archived(engine, run_id, "SQLite create_all succeeds.")
        assert learning.is_archived is False
        engine.dispose()
    finally:
        if os.path.exists(temp_db.name):
            os.unlink(temp_db.name)
