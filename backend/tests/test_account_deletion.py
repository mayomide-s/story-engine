from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    Account,
    AppSession,
    Asset,
    ContentIdea,
    IdeaQueueItem,
    ManualPostPackage,
    NarrationDraft,
    NarrationRender,
    OAuthState,
    PerformanceLearning,
    PerformanceSnapshot,
    PipelineEvent,
    PipelineRun,
    PlatformPost,
    PromptLog,
    PublicationJob,
    PublicationTarget,
    QualityCheck,
    Script,
    SocialConnection,
    StoryAdherenceHumanReview,
    StoryAdherenceReview,
    Storyboard,
    Video,
    YouTubeProjectCompliance,
    GenerationCost,
)
from app.services.account_deletion_service import (
    ACCOUNT_DELETION_CONFIRMATION_PHRASE,
    build_retention_report,
    execute_account_deletion,
)
from app.services.pipeline_service import DEFAULT_ACCOUNT_NAME, seed_default_account


@pytest.fixture(autouse=True)
def isolate_account_deletion_tests():
    with SessionLocal() as db:
        db.query(PerformanceSnapshot).delete(synchronize_session=False)
        db.query(PerformanceLearning).delete(synchronize_session=False)
        db.query(PublicationTarget).delete(synchronize_session=False)
        db.query(PublicationJob).delete(synchronize_session=False)
        db.query(PlatformPost).delete(synchronize_session=False)
        db.query(StoryAdherenceHumanReview).delete(synchronize_session=False)
        db.query(StoryAdherenceReview).delete(synchronize_session=False)
        db.query(NarrationRender).delete(synchronize_session=False)
        db.query(NarrationDraft).delete(synchronize_session=False)
        db.query(QualityCheck).delete(synchronize_session=False)
        db.query(PromptLog).delete(synchronize_session=False)
        db.query(GenerationCost).delete(synchronize_session=False)
        db.query(PipelineEvent).delete(synchronize_session=False)
        db.query(Asset).delete(synchronize_session=False)
        db.query(ContentIdea).delete(synchronize_session=False)
        db.query(Script).delete(synchronize_session=False)
        db.query(Storyboard).delete(synchronize_session=False)
        db.query(Video).delete(synchronize_session=False)
        db.query(ManualPostPackage).delete(synchronize_session=False)
        db.query(PipelineRun).delete(synchronize_session=False)
        db.query(OAuthState).delete(synchronize_session=False)
        db.query(SocialConnection).delete(synchronize_session=False)
        db.query(IdeaQueueItem).delete(synchronize_session=False)
        db.query(YouTubeProjectCompliance).delete(synchronize_session=False)
        db.query(AppSession).delete(synchronize_session=False)
        db.query(Account).delete(synchronize_session=False)
        db.commit()
        seed_default_account(db)
        db.commit()

    get_settings.cache_clear()
    yield

    with SessionLocal() as db:
        db.query(PerformanceSnapshot).delete(synchronize_session=False)
        db.query(PerformanceLearning).delete(synchronize_session=False)
        db.query(PublicationTarget).delete(synchronize_session=False)
        db.query(PublicationJob).delete(synchronize_session=False)
        db.query(PlatformPost).delete(synchronize_session=False)
        db.query(StoryAdherenceHumanReview).delete(synchronize_session=False)
        db.query(StoryAdherenceReview).delete(synchronize_session=False)
        db.query(NarrationRender).delete(synchronize_session=False)
        db.query(NarrationDraft).delete(synchronize_session=False)
        db.query(QualityCheck).delete(synchronize_session=False)
        db.query(PromptLog).delete(synchronize_session=False)
        db.query(GenerationCost).delete(synchronize_session=False)
        db.query(PipelineEvent).delete(synchronize_session=False)
        db.query(Asset).delete(synchronize_session=False)
        db.query(ContentIdea).delete(synchronize_session=False)
        db.query(Script).delete(synchronize_session=False)
        db.query(Storyboard).delete(synchronize_session=False)
        db.query(Video).delete(synchronize_session=False)
        db.query(ManualPostPackage).delete(synchronize_session=False)
        db.query(PipelineRun).delete(synchronize_session=False)
        db.query(OAuthState).delete(synchronize_session=False)
        db.query(SocialConnection).delete(synchronize_session=False)
        db.query(IdeaQueueItem).delete(synchronize_session=False)
        db.query(YouTubeProjectCompliance).delete(synchronize_session=False)
        db.query(AppSession).delete(synchronize_session=False)
        db.query(Account).delete(synchronize_session=False)
        db.commit()
        seed_default_account(db)
        db.commit()

    get_settings.cache_clear()


def _create_completed_run(client):
    created = client.post("/api/pipeline-runs", json={"topic": "Account deletion test", "auto_mode": False})
    assert created.status_code == 200
    run_id = created.json()["pipeline_run"]["id"]
    resumed = client.post(
        f"/api/pipeline-runs/{run_id}/resume",
        json={"review_notes": "Ready for deletion coverage"},
    )
    assert resumed.status_code == 200
    return run_id, resumed.json()


def _create_active_youtube_connection() -> str:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        account = seed_default_account(db)
        connection = SocialConnection(
            account_id=account.id,
            platform="youtube",
            external_account_id="UCDELETE12345",
            display_name="Deletion Test Channel",
            username="@deletiontest",
            encrypted_access_token="v1:access-token",
            encrypted_refresh_token="v1:refresh-token",
            token_cipher_version="v1",
            token_expires_at=now + timedelta(hours=1),
            granted_scopes_json=[
                "https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube.readonly",
            ],
            connection_status="active",
            provider_metadata_json={"channel_identity_source": "youtube.channels.list.mine"},
            is_default=True,
            connected_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(connection)
        db.commit()
        db.refresh(connection)
        return connection.id


def _seed_local_account_deletion_records(client):
    run_id, payload = _create_completed_run(client)
    connection_id = _create_active_youtube_connection()

    with SessionLocal() as db:
        account = db.query(Account).filter_by(name=DEFAULT_ACCOUNT_NAME).first()
        assert account is not None
        db.add(
            OAuthState(
                account_id=account.id,
                platform="youtube",
                state_hash="state-hash-delete-test",
                return_path="/settings",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
                created_at=datetime.now(UTC),
            )
        )
        db.add(
            IdeaQueueItem(
                account_id=account.id,
                topic="Deletion queue item",
                style_preset="clean_3d_cartoon",
                input_config_json={},
                target_platform="youtube",
                status="draft",
                created_at=datetime.now(UTC).replace(tzinfo=None),
                updated_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        record = db.query(YouTubeProjectCompliance).filter(YouTubeProjectCompliance.platform == "youtube").first()
        if record is None:
            record = YouTubeProjectCompliance(
                platform="youtube",
                compliance_status="private_only",
                status_updated_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        record.application_display_name = "Story Engine"
        record.organization_name = "Mayo Soremekun"
        record.support_contact = "mayomide.sore@outlook.com"
        record.case_reference = "YT-DELETE-123"
        record.data_retention_summary = "Local retention summary."
        record.user_data_deletion_summary = "Users can delete data locally."
        db.add(record)
        db.commit()

    job = client.post(
        f"/api/pipeline-runs/{run_id}/publication-jobs",
        json={
            "connection_id": connection_id,
            "title": "Deletion-safe private job",
            "caption": "Deletion-safe caption",
            "tags": ["delete", "account"],
            "privacy": "private",
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": True,
        },
    )
    assert job.status_code == 201

    post = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={
            "platform": "youtube",
            "post_url": "https://youtube.com/shorts/delete-coverage",
            "posted_at": "2026-07-13T12:00:00+00:00",
        },
    )
    assert post.status_code == 201
    post_id = post.json()["id"]

    snapshot = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post_id}/snapshots",
        json={"captured_at": "2026-07-13T12:30:00+00:00", "views": 25, "likes": 5},
    )
    assert snapshot.status_code == 201

    learning = client.post(
        f"/api/pipeline-runs/{run_id}/performance/learnings",
        json={
            "learning_type": "observation",
            "observation": "Deletion flow should clean this up.",
            "evidence": "Manual verification",
            "next_action": "Remove all local traces.",
            "platform_post_id": post_id,
        },
    )
    assert learning.status_code == 201

    return run_id, payload["final_asset_selection"]["asset"]["storage_key"]


def _enable_auth(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("APP_ACCESS_PASSWORD", "open-sesame")
    monkeypatch.setenv("APP_SESSION_SECRET", "session-secret")
    get_settings.cache_clear()


def _auth_headers(client):
    login = client.post("/api/access/login", json={"password": "open-sesame"})
    assert login.status_code == 200
    csrf_token = login.json()["csrf_token"]
    return {"X-CSRF-Token": csrf_token}


def test_account_deletion_preview_execute_and_access_shutdown(client):
    run_id, storage_key = _seed_local_account_deletion_records(client)

    preview = client.get("/api/settings/account-deletion/preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["account_status"] == "active"
    assert body["confirmation_phrase"] == ACCOUNT_DELETION_CONFIRMATION_PHRASE
    assert "Videos already uploaded to YouTube" in body["provider_video_warning"]
    assert body["requires_password_confirmation"] is False
    assert any(item["key"] == "social-connections" and item["count"] == 1 for item in body["deletion_categories"])
    assert any(item["key"] == "account-tombstone" and item["count"] == 1 for item in body["anonymised_categories"])
    assert any(item["key"] == "deleted-account-marker" for item in body["temporarily_retained_categories"])
    assert body["connected_accounts"][0]["platform"] == "youtube"

    invalid_phrase = client.post(
        "/api/settings/account-deletion/validate",
        json={
            "confirmation_phrase": "DELETE",
            "acknowledge_provider_videos_remain_online": True,
            "password": None,
        },
    )
    assert invalid_phrase.status_code == 409
    assert invalid_phrase.json()["detail"]["code"] == "account_deletion_confirmation_required"

    missing_ack = client.post(
        "/api/settings/account-deletion/validate",
        json={
            "confirmation_phrase": ACCOUNT_DELETION_CONFIRMATION_PHRASE,
            "acknowledge_provider_videos_remain_online": False,
            "password": None,
        },
    )
    assert missing_ack.status_code == 409
    assert missing_ack.json()["detail"]["code"] == "account_deletion_confirmation_required"

    validated = client.post(
        "/api/settings/account-deletion/validate",
        json={
            "confirmation_phrase": ACCOUNT_DELETION_CONFIRMATION_PHRASE,
            "acknowledge_provider_videos_remain_online": True,
            "password": None,
        },
    )
    assert validated.status_code == 200
    assert validated.json()["can_delete"] is True

    with SessionLocal() as db:
        jobs_before = db.query(PublicationJob).count()
        targets_before = db.query(PublicationTarget).count()
        posts_before = db.query(PlatformPost).count()
        oauth_before = db.query(OAuthState).count()
        queue_before = db.query(IdeaQueueItem).count()
        account = db.query(Account).filter_by(name=DEFAULT_ACCOUNT_NAME).first()
        assert account is not None
        asset_path = Path(get_settings().local_storage_path) / storage_key
        assert asset_path.exists()

    deleted = client.post(
        "/api/settings/account-deletion",
        json={
            "confirmation_phrase": ACCOUNT_DELETION_CONFIRMATION_PHRASE,
            "acknowledge_provider_videos_remain_online": True,
            "password": None,
        },
    )
    assert deleted.status_code == 200
    deleted_body = deleted.json()
    assert deleted_body["deleted"] is True
    assert deleted_body["account_status"] == "deleted"
    assert deleted_body["deleted_pipeline_run_count"] == 1
    assert deleted_body["deleted_social_connection_count"] == 1
    assert deleted_body["deleted_publication_job_count"] == jobs_before
    assert deleted_body["deleted_publication_target_count"] == targets_before
    assert deleted_body["deleted_platform_post_count"] == posts_before
    assert deleted_body["deleted_local_file_count"] >= 1

    with SessionLocal() as db:
        account = db.query(Account).filter_by(name=DEFAULT_ACCOUNT_NAME).first()
        assert account is not None
        assert account.account_status == "deleted"
        assert account.deleted_at is not None
        assert account.account_config_json == {}
        assert account.niche == "deleted-account"
        assert db.query(PipelineRun).count() == 0
        assert db.query(SocialConnection).count() == 0
        assert db.query(PublicationJob).count() == 0
        assert db.query(PublicationTarget).count() == 0
        assert db.query(PlatformPost).count() == 0
        assert db.query(OAuthState).count() == 0
        assert db.query(IdeaQueueItem).count() == 0
        record = db.query(YouTubeProjectCompliance).filter(YouTubeProjectCompliance.platform == "youtube").first()
        assert record is not None
        assert record.compliance_status == "private_only"
        assert record.application_display_name is None
        assert record.organization_name is None
        assert record.support_contact is None
        assert record.case_reference is None
        assert record.data_retention_summary is None
        assert record.user_data_deletion_summary is None

    assert not asset_path.exists()

    status = client.get("/api/access/status")
    assert status.status_code == 200
    assert status.json()["account_deleted"] is True
    assert status.json()["authenticated"] is False

    protected = client.get("/api/settings/account-defaults")
    assert protected.status_code == 403

    assert oauth_before == 1
    assert queue_before == 1


def test_account_deletion_requires_auth_and_deleted_account_cannot_log_in(client, monkeypatch):
    _enable_auth(monkeypatch)

    unauthenticated = client.get("/api/settings/account-deletion/preview")
    assert unauthenticated.status_code == 401

    headers = _auth_headers(client)
    preview = client.get("/api/settings/account-deletion/preview", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["requires_password_confirmation"] is True

    missing_password = client.post(
        "/api/settings/account-deletion/validate",
        headers=headers,
        json={
            "confirmation_phrase": ACCOUNT_DELETION_CONFIRMATION_PHRASE,
            "acknowledge_provider_videos_remain_online": True,
        },
    )
    assert missing_password.status_code == 409
    assert missing_password.json()["detail"]["code"] == "account_deletion_password_required"

    wrong_password = client.post(
        "/api/settings/account-deletion/validate",
        headers=headers,
        json={
            "confirmation_phrase": ACCOUNT_DELETION_CONFIRMATION_PHRASE,
            "acknowledge_provider_videos_remain_online": True,
            "password": "wrong-password",
        },
    )
    assert wrong_password.status_code == 401

    deleted = client.post(
        "/api/settings/account-deletion",
        headers=headers,
        json={
            "confirmation_phrase": ACCOUNT_DELETION_CONFIRMATION_PHRASE,
            "acknowledge_provider_videos_remain_online": True,
            "password": "open-sesame",
        },
    )
    assert deleted.status_code == 200

    login_after = client.post("/api/access/login", json={"password": "open-sesame"})
    assert login_after.status_code == 403
    assert login_after.json()["detail"] == "Account has been deleted."

    with SessionLocal() as db:
        sessions = db.query(AppSession).all()
        assert sessions
        assert all(session.revoked_at is not None for session in sessions)
        assert all(session.revocation_reason == "account_deleted" for session in sessions)

    status = client.get("/api/access/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["account_deleted"] is True


def test_account_deletion_service_repeated_execution_is_idempotent(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    get_settings.cache_clear()

    with SessionLocal() as db:
        seed_default_account(db)
        first = execute_account_deletion(
            db,
            confirmation_phrase=ACCOUNT_DELETION_CONFIRMATION_PHRASE,
            acknowledge_provider_videos_remain_online=True,
            password=None,
        )
        assert first["deleted"] is True

    with SessionLocal() as db:
        second = execute_account_deletion(
            db,
            confirmation_phrase=ACCOUNT_DELETION_CONFIRMATION_PHRASE,
            acknowledge_provider_videos_remain_online=True,
            password=None,
        )
        assert second == {
            "deleted": True,
            "account_status": "deleted",
            "message": "The account has already been deleted.",
            "disconnected_connection_count": 0,
            "deleted_social_connection_count": 0,
            "deleted_pipeline_run_count": 0,
            "deleted_asset_count": 0,
            "deleted_local_file_count": 0,
            "deleted_publication_job_count": 0,
            "deleted_publication_target_count": 0,
            "deleted_platform_post_count": 0,
            "deleted_snapshot_count": 0,
            "deleted_learning_count": 0,
        }


def test_retention_report_uses_twelve_month_cutoff_and_excludes_shared_profile():
    now = datetime.now(UTC)
    with SessionLocal() as db:
        account = seed_default_account(db)
        account.account_status = "deleted"
        account.deleted_at = (now - timedelta(days=370)).replace(tzinfo=None)
        db.add(account)
        db.add(
            OAuthState(
                account_id=account.id,
                platform="youtube",
                state_hash="state-hash-retention",
                expires_at=now - timedelta(days=370),
                created_at=now - timedelta(days=370),
            )
        )
        db.add(
            YouTubeProjectCompliance(
                platform="youtube",
                compliance_status="private_only",
                status_updated_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

        report = build_retention_report(db)

    assert report["default_retention_months"] == 12
    categories = {item["key"]: item for item in report["categories"]}
    assert categories["deleted-account-tombstones"]["expired_record_count"] == 1
    assert categories["oauth-state-records"]["expired_record_count"] == 1
    assert categories["youtube-compliance-profile"]["cleanup_action"] == "excluded_from_automatic_cleanup"
    assert categories["youtube-compliance-profile"]["expired_record_count"] == 0
