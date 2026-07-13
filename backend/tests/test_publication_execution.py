from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.session import SessionLocal
from app.models import PipelineEvent, PlatformPost, PublicationTarget, SocialConnection
from app.providers.youtube.publishing import YouTubeUploadProgress, YouTubeVideoState
from app.services.pipeline_service import seed_default_account
from app.services.publication_execution_service import poll_youtube_publication_target, process_youtube_publication_target


def _create_completed_run(client):
    created = client.post("/api/pipeline-runs", json={"topic": "Publication Execution Test", "auto_mode": False})
    assert created.status_code == 200
    run_id = created.json()["pipeline_run"]["id"]
    resumed = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Ready for publishing"})
    assert resumed.status_code == 200
    return run_id, resumed.json()


def _create_active_youtube_connection():
    with SessionLocal() as db:
        account = seed_default_account(db)
        for item in db.query(SocialConnection).filter(SocialConnection.account_id == account.id).all():
            item.is_default = False
            db.add(item)
        connection = (
            db.query(SocialConnection)
            .filter(
                SocialConnection.account_id == account.id,
                SocialConnection.platform == "youtube",
                SocialConnection.external_account_id == "UCEXEC12345",
            )
            .first()
        )
        if connection is None:
            connection = SocialConnection(
                account_id=account.id,
                platform="youtube",
                external_account_id="UCEXEC12345",
            )
        connection.display_name = "Execution Test Channel"
        connection.username = "@executiontest"
        connection.encrypted_access_token = "v1:fake-access"
        connection.encrypted_refresh_token = "v1:fake-refresh"
        connection.token_cipher_version = "v1"
        connection.token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        connection.granted_scopes_json = ["https://www.googleapis.com/auth/youtube.upload", "openid", "profile"]
        connection.connection_status = "active"
        connection.provider_metadata_json = {"identity_resolution": "google_openid_subject"}
        connection.is_default = True
        connection.connected_at = datetime.now(UTC)
        connection.disconnected_at = None
        connection.updated_at = datetime.now(UTC)
        db.add(connection)
        db.commit()
        db.refresh(connection)
        return connection.id


def _patch_execution_isolation(monkeypatch):
    monkeypatch.setattr("app.services.publication_execution_service._encrypt_session_uri", lambda value: value)
    monkeypatch.setattr("app.services.publication_execution_service._decrypt_session_uri", lambda value: value)


def _create_and_approve_job(client, run_id: str, connection_id: str, *, privacy: str = "private"):
    created = client.post(
        f"/api/pipeline-runs/{run_id}/publication-jobs",
        json={
            "connection_id": connection_id,
            "title": "API Waiter upload",
            "caption": "Publication execution test",
            "tags": ["api", "youtube"],
            "category_id": "27",
            "privacy": privacy,
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": True,
        },
    )
    assert created.status_code == 201
    job_id = created.json()["job"]["id"]
    approved = client.post(f"/api/publication-jobs/{job_id}/approve")
    assert approved.status_code == 200
    return job_id


def test_private_publication_execution_completes_without_platform_post(client, monkeypatch):
    run_id, _payload = _create_completed_run(client)
    connection_id = _create_active_youtube_connection()
    job_id = _create_and_approve_job(client, run_id, connection_id, privacy="private")

    enqueued_start: list[tuple[str, int]] = []
    enqueued_poll: list[tuple[str, int]] = []
    _patch_execution_isolation(monkeypatch)
    monkeypatch.setattr("app.services.publication_execution_service._enqueue_start_target", lambda target_id, countdown=0: enqueued_start.append((target_id, countdown)))
    monkeypatch.setattr("app.services.publication_execution_service._enqueue_poll_target", lambda target_id, countdown=0: enqueued_poll.append((target_id, countdown)))
    monkeypatch.setattr("app.services.publication_execution_service.refresh_youtube_connection_tokens_if_needed", lambda db, connection, force=False: connection)
    monkeypatch.setattr("app.services.publication_execution_service.initiate_resumable_upload", lambda db, connection, target, media_path, mime_type: "https://upload.example/session/private")
    monkeypatch.setattr(
        "app.services.publication_execution_service.upload_media_chunks",
        lambda db, connection, session_uri, media_path, mime_type, chunk_size, bytes_sent=0, probe_existing_session=False: YouTubeUploadProgress(
            bytes_sent=media_path.stat().st_size,
            total_bytes=media_path.stat().st_size,
            session_uri=session_uri,
            video_id="abc123xyz98",
        ),
    )
    monkeypatch.setattr(
        "app.services.publication_execution_service.fetch_youtube_video_state",
        lambda db, connection, video_id: YouTubeVideoState(
            video_id=video_id,
            upload_status="processed",
            privacy_status="private",
            processing_status="succeeded",
            failure_reason=None,
            rejection_reason=None,
            raw_status={},
            raw_processing_details={},
        ),
    )

    dispatched = client.post(f"/api/publication-jobs/{job_id}/dispatch")
    assert dispatched.status_code == 200
    target_id = dispatched.json()["job"]["targets"][0]["id"]
    assert enqueued_start == [(target_id, 0)]

    with SessionLocal() as db:
        started = process_youtube_publication_target(db, target_id)
        assert started["state"] == "processing"
    assert enqueued_poll

    with SessionLocal() as db:
        finished = poll_youtube_publication_target(db, target_id)
        assert finished["state"] == "uploaded_private"
        assert finished["public_post_url"] is None

        target = db.get(PublicationTarget, target_id)
        assert target is not None
        assert target.actual_visibility == "private"
        assert target.platform_post_id is None
        assert db.query(PlatformPost).filter(PlatformPost.pipeline_run_id == run_id).count() == 0
        assert (
            db.query(PipelineEvent)
            .filter(
                PipelineEvent.pipeline_run_id == run_id,
                PipelineEvent.event_type == "publication.uploaded_private",
            )
            .count()
            == 1
        )


def test_public_publication_creates_exactly_one_platform_post_and_reconciliation_is_idempotent(client, monkeypatch):
    run_id, _payload = _create_completed_run(client)
    connection_id = _create_active_youtube_connection()
    job_id = _create_and_approve_job(client, run_id, connection_id, privacy="public")

    _patch_execution_isolation(monkeypatch)
    monkeypatch.setattr("app.services.publication_execution_service._enqueue_start_target", lambda target_id, countdown=0: None)
    monkeypatch.setattr("app.services.publication_execution_service._enqueue_poll_target", lambda target_id, countdown=0: None)
    monkeypatch.setattr("app.services.publication_execution_service.refresh_youtube_connection_tokens_if_needed", lambda db, connection, force=False: connection)
    monkeypatch.setattr("app.services.publication_execution_service.initiate_resumable_upload", lambda db, connection, target, media_path, mime_type: "https://upload.example/session/public")
    monkeypatch.setattr(
        "app.services.publication_execution_service.upload_media_chunks",
        lambda db, connection, session_uri, media_path, mime_type, chunk_size, bytes_sent=0, probe_existing_session=False: YouTubeUploadProgress(
            bytes_sent=media_path.stat().st_size,
            total_bytes=media_path.stat().st_size,
            session_uri=session_uri,
            video_id="pub123xyz98",
        ),
    )
    monkeypatch.setattr(
        "app.services.publication_execution_service.fetch_youtube_video_state",
        lambda db, connection, video_id: YouTubeVideoState(
            video_id=video_id,
            upload_status="processed",
            privacy_status="public",
            processing_status="succeeded",
            failure_reason=None,
            rejection_reason=None,
            raw_status={},
            raw_processing_details={},
        ),
    )

    dispatched = client.post(f"/api/publication-jobs/{job_id}/dispatch")
    target_id = dispatched.json()["job"]["targets"][0]["id"]

    with SessionLocal() as db:
        started = process_youtube_publication_target(db, target_id)
        assert started["state"] == "processing"

    with SessionLocal() as db:
        finished = poll_youtube_publication_target(db, target_id)
        assert finished["state"] == "published"
        assert finished["public_post_url"] == "https://www.youtube.com/watch?v=pub123xyz98"
        assert finished["platform_post_id"] is not None

    with SessionLocal() as db:
        again = poll_youtube_publication_target(db, target_id)
        assert again["state"] == "published"
        assert db.query(PlatformPost).filter(PlatformPost.pipeline_run_id == run_id).count() == 1
        assert (
            db.query(PipelineEvent)
            .filter(
                PipelineEvent.pipeline_run_id == run_id,
                PipelineEvent.event_type == "publication.platform_post_created",
            )
            .count()
            == 1
        )


def test_redelivered_upload_worker_with_video_id_skips_second_upload(client, monkeypatch):
    run_id, _payload = _create_completed_run(client)
    connection_id = _create_active_youtube_connection()
    job_id = _create_and_approve_job(client, run_id, connection_id, privacy="unlisted")

    upload_calls = {"initiate": 0, "chunks": 0}
    _patch_execution_isolation(monkeypatch)
    monkeypatch.setattr("app.services.publication_execution_service._enqueue_start_target", lambda target_id, countdown=0: None)
    monkeypatch.setattr("app.services.publication_execution_service._enqueue_poll_target", lambda target_id, countdown=0: None)
    monkeypatch.setattr("app.services.publication_execution_service.refresh_youtube_connection_tokens_if_needed", lambda db, connection, force=False: connection)

    def initiate(*args, **kwargs):
        upload_calls["initiate"] += 1
        return "https://upload.example/session/unlisted"

    def upload(*args, **kwargs):
        upload_calls["chunks"] += 1
        media_path = kwargs["media_path"]
        return YouTubeUploadProgress(
            bytes_sent=media_path.stat().st_size,
            total_bytes=media_path.stat().st_size,
            session_uri=kwargs["session_uri"],
            video_id="unl123xyz98",
        )

    monkeypatch.setattr("app.services.publication_execution_service.initiate_resumable_upload", initiate)
    monkeypatch.setattr("app.services.publication_execution_service.upload_media_chunks", upload)
    monkeypatch.setattr(
        "app.services.publication_execution_service.fetch_youtube_video_state",
        lambda db, connection, video_id: YouTubeVideoState(
            video_id=video_id,
            upload_status="processed",
            privacy_status="unlisted",
            processing_status="succeeded",
            failure_reason=None,
            rejection_reason=None,
            raw_status={},
            raw_processing_details={},
        ),
    )

    dispatched = client.post(f"/api/publication-jobs/{job_id}/dispatch")
    target_id = dispatched.json()["job"]["targets"][0]["id"]

    with SessionLocal() as db:
        process_youtube_publication_target(db, target_id)
        process_youtube_publication_target(db, target_id)

    assert upload_calls == {"initiate": 1, "chunks": 1}


def test_retryable_failure_can_be_retried_without_provider_video_id(client, monkeypatch):
    run_id, _payload = _create_completed_run(client)
    connection_id = _create_active_youtube_connection()
    job_id = _create_and_approve_job(client, run_id, connection_id, privacy="private")

    enqueued: list[tuple[str, int]] = []
    _patch_execution_isolation(monkeypatch)
    monkeypatch.setattr("app.services.publication_execution_service._enqueue_start_target", lambda target_id, countdown=0: enqueued.append((target_id, countdown)))
    monkeypatch.setattr("app.services.publication_execution_service.refresh_youtube_connection_tokens_if_needed", lambda db, connection, force=False: connection)
    monkeypatch.setattr("app.services.publication_execution_service.initiate_resumable_upload", lambda db, connection, target, media_path, mime_type: "https://upload.example/session/retry")

    def failing_upload(*args, **kwargs):
        raise PublicationProviderError(
            code="youtube_transport_error",
            safe_message="Temporary upload interruption.",
            retryable=True,
        )

    from app.services.publication_error_service import PublicationProviderError

    monkeypatch.setattr("app.services.publication_execution_service.upload_media_chunks", failing_upload)

    dispatched = client.post(f"/api/publication-jobs/{job_id}/dispatch")
    target_id = dispatched.json()["job"]["targets"][0]["id"]

    with SessionLocal() as db:
        failed = process_youtube_publication_target(db, target_id)
        assert failed["state"] == "retryable_failure"
        assert failed["provider_video_id"] is None

    retried = client.post(f"/api/publication-targets/{target_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["job"]["targets"][0]["state"] == "queued"
    assert len(enqueued) >= 2


def test_crash_after_session_persistence_reuses_resumable_session_without_reupload(client, monkeypatch):
    run_id, _payload = _create_completed_run(client)
    connection_id = _create_active_youtube_connection()
    job_id = _create_and_approve_job(client, run_id, connection_id, privacy="unlisted")

    upload_calls: list[dict[str, object]] = []
    _patch_execution_isolation(monkeypatch)
    monkeypatch.setattr("app.services.publication_execution_service._enqueue_start_target", lambda target_id, countdown=0: None)
    monkeypatch.setattr("app.services.publication_execution_service._enqueue_poll_target", lambda target_id, countdown=0: None)
    monkeypatch.setattr("app.services.publication_execution_service.refresh_youtube_connection_tokens_if_needed", lambda db, connection, force=False: connection)
    monkeypatch.setattr(
        "app.services.publication_execution_service.initiate_resumable_upload",
        lambda db, connection, target=None, media_path=None, mime_type=None: "https://upload.example/session/reused",
    )

    def crashing_upload(*args, **kwargs):
        upload_calls.append(
            {
                "probe_existing_session": kwargs["probe_existing_session"],
                "session_uri": kwargs["session_uri"],
            }
        )
        raise SystemExit("simulated worker crash")

    monkeypatch.setattr("app.services.publication_execution_service.upload_media_chunks", crashing_upload)

    dispatched = client.post(f"/api/publication-jobs/{job_id}/dispatch")
    target_id = dispatched.json()["job"]["targets"][0]["id"]

    with SessionLocal() as db:
        try:
            process_youtube_publication_target(db, target_id)
        except SystemExit:
            pass

    with SessionLocal() as db:
        target = db.get(PublicationTarget, target_id)
        assert target is not None
        assert target.state == "uploading"
        assert target.provider_upload_uri_encrypted == "https://upload.example/session/reused"
        assert target.provider_submission_id is None
        target.worker_claimed_at = datetime.now(UTC) - timedelta(hours=1)
        db.add(target)
        db.commit()

    def resumed_upload(*args, **kwargs):
        upload_calls.append(
            {
                "probe_existing_session": kwargs["probe_existing_session"],
                "session_uri": kwargs["session_uri"],
            }
        )
        media_path = kwargs["media_path"]
        return YouTubeUploadProgress(
            bytes_sent=media_path.stat().st_size,
            total_bytes=media_path.stat().st_size,
            session_uri=kwargs["session_uri"],
            video_id="resume12345",
        )

    monkeypatch.setattr("app.services.publication_execution_service.upload_media_chunks", resumed_upload)
    monkeypatch.setattr(
        "app.services.publication_execution_service.fetch_youtube_video_state",
        lambda db, connection, video_id: YouTubeVideoState(
            video_id=video_id,
            upload_status="processed",
            privacy_status="unlisted",
            processing_status="succeeded",
            failure_reason=None,
            rejection_reason=None,
            raw_status={},
            raw_processing_details={},
        ),
    )

    with SessionLocal() as db:
        resumed = process_youtube_publication_target(db, target_id)
        assert resumed["state"] == "processing"
        assert resumed["provider_video_id"] == "resume12345"

    with SessionLocal() as db:
        finished = poll_youtube_publication_target(db, target_id)
        assert finished["state"] == "published"
        assert finished["platform_post_id"] is not None

    assert upload_calls == [
        {"probe_existing_session": False, "session_uri": "https://upload.example/session/reused"},
        {"probe_existing_session": True, "session_uri": "https://upload.example/session/reused"},
    ]


def test_platform_post_creation_failure_does_not_mark_target_published(client, monkeypatch):
    run_id, _payload = _create_completed_run(client)
    connection_id = _create_active_youtube_connection()
    job_id = _create_and_approve_job(client, run_id, connection_id, privacy="public")

    _patch_execution_isolation(monkeypatch)
    monkeypatch.setattr("app.services.publication_execution_service._enqueue_start_target", lambda target_id, countdown=0: None)
    monkeypatch.setattr("app.services.publication_execution_service._enqueue_poll_target", lambda target_id, countdown=0: None)
    monkeypatch.setattr("app.services.publication_execution_service.refresh_youtube_connection_tokens_if_needed", lambda db, connection, force=False: connection)
    monkeypatch.setattr("app.services.publication_execution_service.initiate_resumable_upload", lambda db, connection, target, media_path, mime_type: "https://upload.example/session/post-failure")
    monkeypatch.setattr(
        "app.services.publication_execution_service.upload_media_chunks",
        lambda db, connection, session_uri, media_path, mime_type, chunk_size, bytes_sent=0, probe_existing_session=False: YouTubeUploadProgress(
            bytes_sent=media_path.stat().st_size,
            total_bytes=media_path.stat().st_size,
            session_uri=session_uri,
            video_id="failpost123",
        ),
    )
    monkeypatch.setattr(
        "app.services.publication_execution_service.fetch_youtube_video_state",
        lambda db, connection, video_id: YouTubeVideoState(
            video_id=video_id,
            upload_status="processed",
            privacy_status="public",
            processing_status="succeeded",
            failure_reason=None,
            rejection_reason=None,
            raw_status={},
            raw_processing_details={},
        ),
    )
    monkeypatch.setattr(
        "app.services.publication_execution_service.create_platform_post_for_publication_target",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Platform post transaction failed.")),
    )

    dispatched = client.post(f"/api/publication-jobs/{job_id}/dispatch")
    target_id = dispatched.json()["job"]["targets"][0]["id"]

    with SessionLocal() as db:
        started = process_youtube_publication_target(db, target_id)
        assert started["state"] == "processing"

    with SessionLocal() as db:
        failed = poll_youtube_publication_target(db, target_id)
        assert failed["state"] == "permanent_failure"
        assert failed["platform_post_id"] is None
        assert failed["public_post_url"] == "https://www.youtube.com/watch?v=failpost123"
        target = db.get(PublicationTarget, target_id)
        assert target is not None
        assert target.state == "permanent_failure"
        assert target.platform_post_id is None
        assert db.query(PlatformPost).filter(PlatformPost.pipeline_run_id == run_id).count() == 0
