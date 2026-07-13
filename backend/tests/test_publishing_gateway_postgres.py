from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.models import (
    Account,
    Asset,
    ManualPostPackage,
    PipelineEvent,
    PipelineRun,
    PublicationJob,
    PublicationTarget,
    SocialConnection,
    Video,
)
from app.models.entities import ManualPackageStatus, ManualPostingStatus, PipelineStatus, VideoStatus
from app.providers.youtube.oauth import YOUTUBE_OAUTH_SCOPES
from app.services.oauth_state_service import consume_oauth_state, create_oauth_state
from app.services.publication_service import approve_publication_job, create_publication_job_draft
from app.services.social_connection_service import complete_youtube_callback, disconnect_social_connection
from app.services.social_token_crypto import decrypt_secret


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


def _configure_social_env(monkeypatch):
    monkeypatch.setenv("SOCIAL_TOKEN_ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-google-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-google-client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/social-connections/youtube/callback")
    monkeypatch.setenv("GOOGLE_OAUTH_FRONTEND_SUCCESS_URL", "http://localhost:5173/social/success")
    monkeypatch.setenv("GOOGLE_OAUTH_FRONTEND_ERROR_URL", "http://localhost:5173/social/error")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("STORAGE_PROVIDER", "local")


def _build_runtime_engine(database_url: str):
    return create_engine(database_url, future=True, poolclass=NullPool)


def _create_completed_run_with_selected_asset(session: Session, storage_root: Path) -> tuple[PipelineRun, ManualPostPackage, Asset]:
    now = datetime.now(UTC)
    account = Account(name=f"acct-{uuid.uuid4().hex[:8]}", niche="coding")
    session.add(account)
    session.flush()

    run = PipelineRun(
        account_id=account.id,
        topic="PG publishing gateway integration",
        status=PipelineStatus.COMPLETED,
    )
    session.add(run)
    session.flush()

    video = Video(
        pipeline_run_id=run.id,
        provider="mock",
        prompt_text="Prompt",
        status=VideoStatus.COMPLETED,
        created_at=now,
        updated_at=now,
    )
    session.add(video)
    session.flush()

    asset_rel_path = Path("exports") / f"{uuid.uuid4().hex}.mp4"
    asset_path = storage_root / asset_rel_path
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"fake-mp4-content")

    asset = Asset(
        pipeline_run_id=run.id,
        asset_type="video_mp4",
        created_by_stage="video_generation",
        storage_key=str(asset_rel_path).replace("\\", "/"),
        public_url=f"http://localhost:8000/assets/{asset_rel_path.as_posix()}",
        mime_type="video/mp4",
        size_bytes=asset_path.stat().st_size,
        duration_seconds=32,
        width=1080,
        height=1920,
        created_at=now,
        updated_at=now,
    )
    session.add(asset)
    session.flush()

    package = ManualPostPackage(
        video_id=video.id,
        caption="Caption",
        hashtags_json=[],
        target_platforms_json=["youtube"],
        platform_variants_json={},
        checklist_json=[],
        status=ManualPackageStatus.READY,
        manual_posting_status=ManualPostingStatus.NOT_POSTED,
        final_asset_id=asset.id,
        final_asset_source="source_video",
        final_asset_selection_revision=1,
        final_asset_selected_at=now,
        final_asset_metadata_json={},
        winner_selection_revision=0,
        created_at=now,
        updated_at=now,
    )
    session.add(package)
    session.flush()

    run.manual_post_package_id = package.id
    session.add(run)
    session.commit()
    session.refresh(run)
    session.refresh(package)
    session.refresh(asset)
    return run, package, asset


@pytest.mark.skipif(not TEST_POSTGRES_DATABASE_URL, reason="TEST_POSTGRES_DATABASE_URL is not configured.")
def test_postgres_publication_gateway_migration_upgrade_downgrade_reupgrade():
    admin_url = _get_admin_url()
    with _temporary_database(admin_url, "story_engine_pgpub") as (_database_name, database_url):
        _run_alembic(database_url, "upgrade", "0018_postgres_migration_compatibility")
        _run_alembic(database_url, "upgrade", "0020_youtube_publication_execution")

        engine = create_engine(database_url, future=True)
        inspector = inspect(engine)
        assert "social_connections" in inspector.get_table_names()
        assert "oauth_states" in inspector.get_table_names()
        assert "publication_jobs" in inspector.get_table_names()
        assert "publication_targets" in inspector.get_table_names()
        assert "uq_social_connections_account_platform_external" in {
            constraint["name"] for constraint in inspector.get_unique_constraints("social_connections")
        }
        assert "uq_oauth_states_state_hash" in {
            constraint["name"] for constraint in inspector.get_unique_constraints("oauth_states")
        }
        assert "uq_publication_targets_job_platform_connection" in {
            constraint["name"] for constraint in inspector.get_unique_constraints("publication_targets")
        }
        assert "uq_publication_targets_idempotency_key" in {
            constraint["name"] for constraint in inspector.get_unique_constraints("publication_targets")
        }
        assert "uq_publication_targets_platform_post_id" in {
            constraint["name"] for constraint in inspector.get_unique_constraints("publication_targets")
        }
        assert "ix_oauth_states_expires_at" in {index["name"] for index in inspector.get_indexes("oauth_states")}
        assert "ix_social_connections_account_platform" in {
            index["name"] for index in inspector.get_indexes("social_connections")
        }
        assert "ix_publication_jobs_pipeline_run_id" in {
            index["name"] for index in inspector.get_indexes("publication_jobs")
        }
        assert "ix_publication_targets_next_poll_at" in {
            index["name"] for index in inspector.get_indexes("publication_targets")
        }
        assert "ix_publication_targets_platform_post_id" in {
            index["name"] for index in inspector.get_indexes("publication_targets")
        }
        social_columns = {column["name"]: column for column in inspector.get_columns("social_connections")}
        assert social_columns["encrypted_access_token"]["type"].__class__.__name__.lower() == "text"
        assert social_columns["encrypted_refresh_token"]["type"].__class__.__name__.lower() == "text"
        assert social_columns["token_expires_at"]["type"].timezone is True
        oauth_columns = {column["name"]: column for column in inspector.get_columns("oauth_states")}
        assert oauth_columns["expires_at"]["type"].timezone is True
        target_columns = {column["name"]: column for column in inspector.get_columns("publication_targets")}
        assert target_columns["provider_upload_uri_encrypted"]["type"].__class__.__name__.lower() == "text"
        assert target_columns["next_poll_at"]["type"].timezone is True
        assert "platform_post_id" in target_columns
        assert "actual_visibility" in target_columns
        assert "upload_bytes_sent" in target_columns

        _run_alembic(database_url, "downgrade", "0018_postgres_migration_compatibility")
        inspector = inspect(engine)
        assert "social_connections" not in inspector.get_table_names()
        assert "publication_jobs" not in inspector.get_table_names()

        _run_alembic(database_url, "upgrade", "0020_youtube_publication_execution")
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert revision == EXPECTED_HEAD
        engine.dispose()


@pytest.mark.skipif(not TEST_POSTGRES_DATABASE_URL, reason="TEST_POSTGRES_DATABASE_URL is not configured.")
def test_postgres_fresh_database_upgrades_from_base_to_head():
    admin_url = _get_admin_url()
    with _temporary_database(admin_url, "story_engine_pgpubbase") as (_database_name, database_url):
        _run_alembic(database_url, "upgrade", "head")
        engine = create_engine(database_url, future=True)
        inspector = inspect(engine)
        assert "social_connections" in inspector.get_table_names()
        assert "oauth_states" in inspector.get_table_names()
        assert "publication_jobs" in inspector.get_table_names()
        assert "publication_targets" in inspector.get_table_names()
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
        assert "platform_post_id" in target_columns
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


def test_sqlite_publication_gateway_downgrade_reupgrade_from_current_schema():
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()
    database_url = f"sqlite:///{temp_db.name.replace(os.sep, '/')}"
    try:
        engine = create_engine(database_url, future=True)
        Base.metadata.create_all(bind=engine)
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL PRIMARY KEY)")
            connection.exec_driver_sql(
                "INSERT INTO alembic_version (version_num) VALUES ('0020_youtube_publication_execution')"
            )

        _run_alembic(database_url, "downgrade", "0019_publishing_gateway_core")
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert revision == "0019_publishing_gateway_core"

        _run_alembic(database_url, "upgrade", "0020_youtube_publication_execution")
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert revision == EXPECTED_HEAD

        inspector = inspect(engine)
        target_columns = {column["name"] for column in inspector.get_columns("publication_targets")}
        assert "platform_post_id" in target_columns
        assert "actual_visibility" in target_columns
        engine.dispose()
    finally:
        if os.path.exists(temp_db.name):
            os.unlink(temp_db.name)


@pytest.mark.skipif(not TEST_POSTGRES_DATABASE_URL, reason="TEST_POSTGRES_DATABASE_URL is not configured.")
def test_postgres_publication_gateway_service_integration(monkeypatch):
    _configure_social_env(monkeypatch)

    admin_url = _get_admin_url()
    with _temporary_database(admin_url, "story_engine_pgpubsvc") as (_database_name, database_url):
        _run_alembic(database_url, "upgrade", "0020_youtube_publication_execution")
        engine = _build_runtime_engine(database_url)
        storage_root = Path(tempfile.mkdtemp(prefix="story_engine_pgpub_storage_"))
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setenv("LOCAL_STORAGE_PATH", str(storage_root))

        from app.config import get_settings
        import app.services.social_connection_service as social_service

        get_settings.cache_clear()

        class FirstPayload:
            external_account_id = "UCPOSTGRES123"
            display_name = "Postgres Channel"
            username = "@postgreschannel"
            access_token = "pg-access-token"
            refresh_token = "pg-refresh-token"
            token_expiry = datetime.now(UTC) + timedelta(hours=1)
            granted_scopes = list(YOUTUBE_OAUTH_SCOPES)
            provider_metadata = {"channel_identity_source": "youtube.channels.list.mine"}

        class ReconnectPayload:
            external_account_id = "UCPOSTGRES123"
            display_name = "Postgres Channel Updated"
            username = "@postgreschannel"
            access_token = "pg-access-token-2"
            refresh_token = None
            token_expiry = datetime.now(UTC) + timedelta(hours=2)
            granted_scopes = list(YOUTUBE_OAUTH_SCOPES)
            provider_metadata = {"channel_identity_source": "youtube.channels.list.mine"}

        payloads = [FirstPayload(), ReconnectPayload()]
        monkeypatch.setattr(
            social_service,
            "exchange_callback_code",
            lambda code: payloads.pop(0),
        )

        try:
            with Session(engine) as session:
                run, _package, _asset = _create_completed_run_with_selected_asset(session, storage_root)
                raw_state, _ = create_oauth_state(session, platform="youtube", return_path="/review")
                session.commit()

                redirect = complete_youtube_callback(session, state=raw_state, code="first", error=None)
                assert "status=connected" in redirect
                connection = session.query(SocialConnection).one()
                assert connection.external_account_id == "UCPOSTGRES123"
                assert connection.display_name == "Postgres Channel"
                assert decrypt_secret(connection.encrypted_access_token, purpose="access token") == "pg-access-token"
                assert decrypt_secret(connection.encrypted_refresh_token, purpose="refresh token") == "pg-refresh-token"

                second_state, _ = create_oauth_state(session, platform="youtube")
                session.commit()
                reconnect_redirect = complete_youtube_callback(session, state=second_state, code="second", error=None)
                assert "status=connected" in reconnect_redirect

                reconnected = session.query(SocialConnection).one()
                assert reconnected.external_account_id == "UCPOSTGRES123"
                assert reconnected.display_name == "Postgres Channel Updated"
                assert decrypt_secret(reconnected.encrypted_refresh_token, purpose="refresh token") == "pg-refresh-token"

                disconnect_social_connection(session, reconnected.id)
                disconnected = session.get(SocialConnection, reconnected.id)
                assert disconnected is not None
                assert disconnected.connection_status == "disconnected"

                disconnected.connection_status = "active"
                disconnected.is_default = True
                disconnected.connected_at = disconnected.connected_at or datetime.now(UTC)
                disconnected.updated_at = datetime.now(UTC)
                session.add(disconnected)
                session.commit()

                job_payload = {
                    "title": "Postgres publish test",
                    "caption": "Safe draft",
                    "tags": ["youtube", "story-engine"],
                    "privacy": "private",
                    "self_declared_made_for_kids": False,
                    "contains_synthetic_media": False,
                }
                from app.schemas.publication import PublicationJobDraftRequest

                job = create_publication_job_draft(session, run.id, PublicationJobDraftRequest(**job_payload))
                approved = approve_publication_job(session, job["id"])
                assert approved["status"] == "approved"
                assert session.query(PublicationJob).filter(PublicationJob.pipeline_run_id == run.id).count() == 1
                assert session.query(PublicationTarget).filter(PublicationTarget.publication_job_id == job["id"]).count() == 1
                assert session.query(PipelineEvent).filter(PipelineEvent.pipeline_run_id == run.id).count() >= 2
        finally:
            get_settings.cache_clear()
            engine.dispose()
            for child in storage_root.glob("**/*"):
                if child.is_file():
                    child.unlink()
            for child in sorted(storage_root.glob("**/*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
            if storage_root.exists():
                storage_root.rmdir()
