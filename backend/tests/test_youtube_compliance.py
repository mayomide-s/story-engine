from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.session import SessionLocal
from app.models import YouTubeProjectCompliance


@pytest.fixture(autouse=True)
def clear_youtube_compliance_records():
    with SessionLocal() as db:
        db.query(YouTubeProjectCompliance).delete()
        db.commit()
    yield


def test_compliance_status_defaults_to_private_only_without_persisting_on_read(client):
    with SessionLocal() as db:
        initial_count = db.query(YouTubeProjectCompliance).count()

    response = client.get("/api/social-connections/youtube/compliance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["compliance_status"] == "private_only"
    assert payload["can_publish_private"] is True
    assert payload["can_publish_unlisted"] is False
    assert payload["can_publish_public"] is False

    with SessionLocal() as db:
        assert db.query(YouTubeProjectCompliance).count() == initial_count


def test_compliance_status_update_requires_explicit_confirmation_for_audit_approved(client):
    response = client.patch(
        "/api/social-connections/youtube/compliance",
        json={
            "compliance_status": "audit_approved",
            "submission_date": "2026-07-13",
            "approval_date": "2026-07-14",
            "case_reference": "YT-AUDIT-1",
            "admin_note": "Approved",
            "confirm_audit_approved": False,
        },
    )

    assert response.status_code == 422
    assert "Explicit confirmation" in response.json()["detail"]


def test_compliance_status_update_persists_metadata_and_transitions(client):
    pending = client.patch(
        "/api/social-connections/youtube/compliance",
        json={
            "compliance_status": "audit_pending",
            "submission_date": "2026-07-13",
            "approval_date": None,
            "case_reference": "YT-AUDIT-2",
            "admin_note": "Submitted for review",
            "confirm_audit_approved": False,
        },
    )
    assert pending.status_code == 200
    assert pending.json()["compliance_status"] == "audit_pending"
    assert pending.json()["submission_date"] == "2026-07-13"

    approved = client.patch(
        "/api/social-connections/youtube/compliance",
        json={
            "compliance_status": "audit_approved",
            "submission_date": "2026-07-13",
            "approval_date": "2026-07-20",
            "case_reference": "YT-AUDIT-2",
            "admin_note": "Approved by Google",
            "confirm_audit_approved": True,
        },
    )
    assert approved.status_code == 200
    assert approved.json()["compliance_status"] == "audit_approved"
    assert approved.json()["can_publish_unlisted"] is True
    assert approved.json()["can_publish_public"] is True

    private_only = client.patch(
        "/api/social-connections/youtube/compliance",
        json={
            "compliance_status": "private_only",
            "submission_date": None,
            "approval_date": None,
            "case_reference": None,
            "admin_note": "Approval withdrawn",
            "confirm_audit_approved": False,
        },
    )
    assert private_only.status_code == 200
    assert private_only.json()["compliance_status"] == "private_only"

    with SessionLocal() as db:
        record = db.query(YouTubeProjectCompliance).one()
        assert record.compliance_status == "private_only"
        assert record.admin_note == "Approval withdrawn"


def test_audit_readiness_report_json_and_markdown_exclude_secrets(client, monkeypatch):
    monkeypatch.setenv("SOCIAL_TOKEN_ENCRYPTION_KEY", "super-secret-key-should-not-appear")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "super-secret-client-secret")

    client.patch(
        "/api/social-connections/youtube/compliance",
        json={
            "compliance_status": "audit_pending",
            "submission_date": "2026-07-13",
            "approval_date": None,
            "case_reference": "YT-AUDIT-3",
            "admin_note": "Waiting for review",
            "confirm_audit_approved": False,
        },
    )

    response = client.get("/api/social-connections/youtube/compliance/report")
    assert response.status_code == 200
    payload = response.json()
    assert payload["platform"] == "youtube"
    assert payload["current_compliance_status"] == "audit_pending"
    assert payload["requested_scopes"] == [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
    ]
    assert any(section["key"] == "visibility-controls" for section in payload["sections"])
    assert "super-secret" not in str(payload)
    assert "youtube.com/watch" not in str(payload)

    markdown = client.get("/api/social-connections/youtube/compliance/report?format=markdown")
    assert markdown.status_code == 200
    assert markdown.text.startswith("# YouTube Audit Readiness Report")
    assert "super-secret" not in markdown.text
    assert "youtube.com/watch" not in markdown.text
