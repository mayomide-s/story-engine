from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config import get_settings
from app.db.session import SessionLocal
from app.models import Asset, ManualPostPackage, PipelineEvent, PipelineRun, PublicationJob, PublicationTarget, SocialConnection
from app.services.pipeline_service import seed_default_account


def _create_completed_run(client):
    created = client.post("/api/pipeline-runs", json={"topic": "Publication Job Test", "auto_mode": False})
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
                SocialConnection.external_account_id == "google-sub:test-channel-123",
            )
            .first()
        )
        if connection is None:
            connection = SocialConnection(
                account_id=account.id,
                platform="youtube",
                external_account_id="google-sub:test-channel-123",
                created_at=datetime.now(UTC),
            )
        connection.display_name = "Test Channel"
        connection.username = "TestChannel"
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


def test_create_publication_job_draft_freezes_selected_asset_and_is_idempotent(client):
    run_id, payload = _create_completed_run(client)
    connection_id = _create_active_youtube_connection()
    selected_asset = payload["final_asset_selection"]["asset"]
    selected_asset_id = selected_asset["id"]

    first = client.post(
        f"/api/pipeline-runs/{run_id}/publication-jobs",
        json={
            "connection_id": connection_id,
            "title": "API Waiter Video",
            "caption": "A publish-ready explainer",
            "tags": ["api", "coding", "youtube"],
            "privacy": "private",
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": True,
        },
    )

    assert first.status_code == 201
    job = first.json()["job"]
    assert job["final_asset_id"] == selected_asset_id
    assert len(job["final_asset_sha256"]) == 64
    assert job["targets"][0]["visibility"] == "private"
    assert job["targets"][0]["platform_post_creation_eligible"] is False

    second = client.post(
        f"/api/pipeline-runs/{run_id}/publication-jobs",
        json={
            "connection_id": connection_id,
            "title": "API Waiter Video",
            "caption": "A publish-ready explainer",
            "tags": ["api", "coding", "youtube"],
            "privacy": "private",
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": True,
        },
    )

    assert second.status_code == 201
    assert second.json()["job"]["id"] == job["id"]

    with SessionLocal() as db:
        jobs = db.query(PublicationJob).filter(PublicationJob.pipeline_run_id == run_id).all()
        assert len(jobs) == 1
        targets = db.query(PublicationTarget).filter(PublicationTarget.publication_job_id == job["id"]).all()
        assert len(targets) == 1
        assert (
            db.query(PipelineEvent)
            .filter(
                PipelineEvent.pipeline_run_id == run_id,
                PipelineEvent.event_type == "publication.job_draft_created",
            )
            .count()
            == 1
        )


def test_publication_job_requires_completed_run_and_default_connection(client):
    created = client.post("/api/pipeline-runs", json={"topic": "Incomplete Publish", "auto_mode": False})
    run_id = created.json()["pipeline_run"]["id"]

    no_connection = client.post(
        f"/api/pipeline-runs/{run_id}/publication-jobs",
        json={
            "title": "No connection",
            "caption": "No connection",
            "tags": [],
            "privacy": "private",
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": False,
        },
    )
    assert no_connection.status_code == 409

    _create_active_youtube_connection()
    incomplete = client.post(
        f"/api/pipeline-runs/{run_id}/publication-jobs",
        json={
            "title": "Still incomplete",
            "caption": "Still incomplete",
            "tags": [],
            "privacy": "private",
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": False,
        },
    )
    assert incomplete.status_code == 409


def test_publication_job_rejects_non_selected_or_unreadable_asset(client):
    run_id, payload = _create_completed_run(client)
    _create_active_youtube_connection()

    with SessionLocal() as db:
        run = db.get(PipelineRun, run_id)
        assert run is not None
        package = db.get(ManualPostPackage, run.manual_post_package_id)
        assert package is not None
        package.final_asset_id = "missing-asset-id"
        db.add(package)
        db.commit()

    missing_asset = client.post(
        f"/api/pipeline-runs/{run_id}/publication-jobs",
        json={
            "title": "Missing asset",
            "caption": "Missing asset",
            "tags": [],
            "privacy": "private",
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": False,
        },
    )
    assert missing_asset.status_code == 409

    with SessionLocal() as db:
        run = db.get(PipelineRun, run_id)
        package = db.get(ManualPostPackage, run.manual_post_package_id)
        original_asset_id = payload["final_asset_selection"]["asset"]["id"]
        package.final_asset_id = original_asset_id
        db.add(package)
        db.commit()

        selected_asset = db.get(Asset, original_asset_id)
        assert selected_asset is not None
        asset_path = Path(get_settings().local_storage_path) / selected_asset.storage_key
        if asset_path.exists():
            asset_path.unlink()

    unreadable = client.post(
        f"/api/pipeline-runs/{run_id}/publication-jobs",
        json={
            "title": "Unreadable asset",
            "caption": "Unreadable asset",
            "tags": [],
            "privacy": "private",
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": False,
        },
    )
    assert unreadable.status_code == 409


def test_approve_and_cancel_publication_job_are_idempotent_and_do_not_create_platform_posts(client):
    run_id, _payload = _create_completed_run(client)
    connection_id = _create_active_youtube_connection()

    created = client.post(
        f"/api/pipeline-runs/{run_id}/publication-jobs",
        json={
            "connection_id": connection_id,
            "title": "Approval test",
            "caption": "Approval test",
            "tags": ["youtube"],
            "privacy": "unlisted",
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": False,
        },
    )
    job_id = created.json()["job"]["id"]

    approved = client.post(f"/api/publication-jobs/{job_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["job"]["status"] == "approved"
    assert approved.json()["job"]["targets"][0]["platform_post_creation_eligible"] is True

    approved_again = client.post(f"/api/publication-jobs/{job_id}/approve")
    assert approved_again.status_code == 200
    assert approved_again.json()["job"]["status"] == "approved"

    cancelled = client.post(f"/api/publication-jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"
    assert cancelled.json()["job"]["targets"][0]["state"] == "cancelled"

    cancelled_again = client.post(f"/api/publication-jobs/{job_id}/cancel")
    assert cancelled_again.status_code == 200
    assert cancelled_again.json()["job"]["status"] == "cancelled"

    with SessionLocal() as db:
        assert db.query(PublicationJob).filter(PublicationJob.pipeline_run_id == run_id).count() == 1
        assert db.query(PublicationTarget).filter(PublicationTarget.publication_job_id == job_id).count() == 1
        assert (
            db.query(PipelineEvent)
            .filter(
                PipelineEvent.pipeline_run_id == run_id,
                PipelineEvent.event_type == "publication.job_approved",
            )
            .count()
            == 1
        )
        assert (
            db.query(PipelineEvent)
            .filter(
                PipelineEvent.pipeline_run_id == run_id,
                PipelineEvent.event_type == "publication.job_cancelled",
            )
            .count()
            == 1
        )
        assert (
            db.query(PipelineEvent)
            .filter(
                PipelineEvent.pipeline_run_id == run_id,
                PipelineEvent.event_type == "performance.post_created",
            )
            .count()
            == 0
        )


def test_publication_job_detects_selected_asset_change_after_draft(client):
    run_id, payload = _create_completed_run(client)
    connection_id = _create_active_youtube_connection()

    created = client.post(
        f"/api/pipeline-runs/{run_id}/publication-jobs",
        json={
            "connection_id": connection_id,
            "title": "Frozen asset test",
            "caption": "Frozen asset test",
            "tags": ["asset"],
            "privacy": "public",
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": False,
        },
    )
    assert created.status_code == 201
    job_id = created.json()["job"]["id"]

    with SessionLocal() as db:
        run = db.get(PipelineRun, run_id)
        assert run is not None
        package = db.get(ManualPostPackage, run.manual_post_package_id)
        assert package is not None
        package.final_asset_selection_revision += 1
        db.add(package)
        db.commit()

    approved = client.post(f"/api/publication-jobs/{job_id}/approve")
    assert approved.status_code == 409


def test_publication_job_validation_limits(client):
    _create_active_youtube_connection()
    run_id, _payload = _create_completed_run(client)

    response = client.post(
        f"/api/pipeline-runs/{run_id}/publication-jobs",
        json={
            "title": " " * 3,
            "caption": "x" * 5001,
            "tags": ["tag"] * 200,
            "privacy": "friends-only",
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": False,
        },
    )
    assert response.status_code == 422


def test_publication_job_response_marks_reconnect_required_for_revoked_or_missing_scope_errors(client):
    run_id, _payload = _create_completed_run(client)
    connection_id = _create_active_youtube_connection()

    created = client.post(
        f"/api/pipeline-runs/{run_id}/publication-jobs",
        json={
            "connection_id": connection_id,
            "title": "Reconnect check",
            "caption": "Reconnect check",
            "tags": ["youtube"],
            "privacy": "private",
            "self_declared_made_for_kids": False,
            "contains_synthetic_media": False,
        },
    )
    assert created.status_code == 201
    job_id = created.json()["job"]["id"]
    target_id = created.json()["job"]["targets"][0]["id"]

    with SessionLocal() as db:
        target = db.get(PublicationTarget, target_id)
        assert target is not None
        target.state = "retryable_failure"
        target.last_error_code = "youtube_credentials_invalid"
        target.last_error_message = "Reconnect required."
        db.add(target)
        db.commit()

    response = client.get(f"/api/publication-jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["targets"][0]["reconnect_required"] is True
