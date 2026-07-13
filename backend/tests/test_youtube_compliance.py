from __future__ import annotations

import pytest

from app.db.session import SessionLocal
from app.models import YouTubeProjectCompliance


@pytest.fixture(autouse=True)
def clear_youtube_compliance_records():
    with SessionLocal() as db:
        db.query(YouTubeProjectCompliance).delete()
        db.commit()
    yield


def _complete_submission_profile(client):
    response = client.patch(
        "/api/social-connections/youtube/compliance/profile",
        json={
            "application_display_name": "Story Engine",
            "product_description": "Story Engine lets a user review a selected final video and explicitly approve a YouTube upload.",
            "organization_name": "Mayomide Studio",
            "support_contact": "support@example.com",
            "privacy_policy_url": "https://storyengine.example.com/privacy",
            "terms_of_service_url": "https://storyengine.example.com/terms",
            "application_homepage_url": "https://storyengine.example.com",
            "production_oauth_redirect_uri": "https://api.storyengine.example.com/api/social-connections/youtube/callback",
            "production_frontend_url": "https://storyengine.example.com",
            "production_api_url": "https://api.storyengine.example.com",
            "data_retention_summary": "Publication jobs and targets are retained for auditability.",
            "user_data_deletion_summary": "Users can request data deletion through support.",
            "token_revocation_summary": "Disconnect removes stored encrypted tokens and users may revoke access in Google.",
            "account_disconnection_summary": "Disconnect marks the connection disconnected and clears encrypted tokens.",
            "quota_monitoring_summary": "The team monitors upload failures and API quota usage through operations logs.",
            "incident_response_summary": "Operational incidents are reviewed and resolved through a documented response process.",
            "security_contact_summary": "security@example.com",
            "intended_submission_date": "2026-07-20",
            "submission_case_reference": "YT-SUBMIT-123",
            "reviewed_by": "Admin Reviewer",
            "admin_note": "Submission profile complete for testing.",
        },
    )
    assert response.status_code == 200


def _complete_required_confirmations(client):
    for key in [
        "legal_review_completed",
        "privacy_policy_verified",
        "terms_of_service_verified",
        "support_contact_verified",
        "production_urls_verified",
        "deletion_and_revocation_reviewed",
        "incident_response_reviewed",
        "monitoring_reviewed",
        "submission_package_reviewed",
    ]:
        response = client.put(
            f"/api/social-connections/youtube/compliance/confirmations/{key}",
            json={"completed": True, "reviewed_by": "Admin Reviewer"},
        )
        assert response.status_code == 200


def test_compliance_reads_default_to_private_only_without_persisting_rows(client):
    compliance = client.get("/api/social-connections/youtube/compliance")
    profile = client.get("/api/social-connections/youtube/compliance/profile")
    readiness = client.get("/api/social-connections/youtube/compliance/readiness")

    assert compliance.status_code == 200
    assert compliance.json()["compliance_status"] == "private_only"
    assert profile.status_code == 200
    assert profile.json()["submission_case_reference"] is None
    assert readiness.status_code == 200
    assert readiness.json()["current_compliance_status"] == "private_only"
    assert readiness.json()["overall_status"] == "fail"

    with SessionLocal() as db:
        assert db.query(YouTubeProjectCompliance).count() == 0


def test_submission_profile_rejects_invalid_urls_and_persists_non_secret_fields(client):
    invalid = client.patch(
        "/api/social-connections/youtube/compliance/profile",
        json={"privacy_policy_url": "not-a-url"},
    )
    assert invalid.status_code == 422
    assert "privacy_policy_url" in invalid.json()["detail"]

    _complete_submission_profile(client)

    profile = client.get("/api/social-connections/youtube/compliance/profile")
    assert profile.status_code == 200
    payload = profile.json()
    assert payload["application_display_name"] == "Story Engine"
    assert payload["production_api_url"] == "https://api.storyengine.example.com"
    assert payload["submission_case_reference"] == "YT-SUBMIT-123"
    assert "encrypted_access_token" not in str(payload)
    assert "encrypted_refresh_token" not in str(payload)


def test_readiness_engine_reports_blockers_for_missing_production_and_policy_data(client):
    readiness = client.get("/api/social-connections/youtube/compliance/readiness")
    assert readiness.status_code == 200
    payload = readiness.json()
    assert payload["overall_status"] == "fail"
    assert payload["blocker_count"] > 0
    blocker_keys = {item["key"] for item in payload["blockers"]}
    assert "privacy-policy-url" in blocker_keys
    assert "terms-of-service-url" in blocker_keys
    assert "production-oauth-redirect-uri" in blocker_keys
    assert "support-contact" in blocker_keys


def test_human_confirmations_can_be_set_and_cleared(client):
    _complete_submission_profile(client)

    set_response = client.put(
        "/api/social-connections/youtube/compliance/confirmations/legal_review_completed",
        json={"completed": True, "reviewed_by": "Admin Reviewer"},
    )
    assert set_response.status_code == 200
    assert next(
        item for item in set_response.json()["human_confirmations"]
        if item["key"] == "legal_review_completed"
    )["completed"] is True

    clear_response = client.delete(
        "/api/social-connections/youtube/compliance/confirmations/legal_review_completed?reviewed_by=Admin%20Reviewer"
    )
    assert clear_response.status_code == 200
    assert next(
        item for item in clear_response.json()["human_confirmations"]
        if item["key"] == "legal_review_completed"
    )["completed"] is False


def test_audit_approval_is_blocked_until_readiness_and_confirmations_are_complete(client):
    blocked = client.patch(
        "/api/social-connections/youtube/compliance",
        json={
            "compliance_status": "audit_approved",
            "submission_date": "2026-07-13",
            "approval_date": "2026-07-20",
            "case_reference": "YT-AUDIT-2",
            "admin_note": "Approved by Google",
            "confirm_audit_approved": True,
            "confirm_google_audit_approval_received": True,
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "youtube_compliance_readiness_incomplete"
    assert blocked.json()["detail"]["blockers"]

    _complete_submission_profile(client)
    _complete_required_confirmations(client)

    approved = client.patch(
        "/api/social-connections/youtube/compliance",
        json={
            "compliance_status": "audit_approved",
            "submission_date": "2026-07-13",
            "approval_date": "2026-07-20",
            "case_reference": "YT-AUDIT-2",
            "admin_note": "Approved by Google",
            "confirm_audit_approved": True,
            "confirm_google_audit_approval_received": True,
        },
    )
    assert approved.status_code == 200
    assert approved.json()["compliance_status"] == "audit_approved"
    assert approved.json()["can_publish_unlisted"] is True
    assert approved.json()["can_publish_public"] is True


def test_submission_package_and_exports_exclude_secrets_private_urls_and_provider_ids(client, monkeypatch):
    monkeypatch.setenv("SOCIAL_TOKEN_ENCRYPTION_KEY", "super-secret-key-should-not-appear")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "super-secret-client-secret")
    _complete_submission_profile(client)

    package = client.get("/api/social-connections/youtube/compliance/package")
    assert package.status_code == 200
    payload = package.json()
    assert payload["platform"] == "youtube"
    assert payload["readiness"]["overall_status"] in {"fail", "needs_confirmation", "pass"}
    assert payload["evidence_manifest"]
    assert payload["submission_checklist"]
    assert "super-secret" not in str(payload)
    assert "youtube.com/watch" not in str(payload)
    assert "postgresql://" not in str(payload)
    assert "C:\\" not in str(payload)

    markdown = client.get("/api/social-connections/youtube/compliance/package?format=markdown")
    assert markdown.status_code == 200
    assert markdown.text.startswith("# YouTube Compliance Submission Package")
    assert "super-secret" not in markdown.text
    assert "youtube.com/watch" not in markdown.text

    checklist = client.get("/api/social-connections/youtube/compliance/package?format=checklist")
    assert checklist.status_code == 200
    assert checklist.text.startswith("# YouTube Submission Checklist")


def test_localhost_production_urls_remain_blockers_even_when_profile_exists(client):
    response = client.patch(
        "/api/social-connections/youtube/compliance/profile",
        json={
            "application_display_name": "Story Engine",
            "product_description": "Product description",
            "organization_name": "Mayomide Studio",
            "support_contact": "support@example.com",
            "privacy_policy_url": "https://storyengine.example.com/privacy",
            "terms_of_service_url": "https://storyengine.example.com/terms",
            "application_homepage_url": "https://storyengine.example.com",
            "production_oauth_redirect_uri": "http://localhost:8000/api/social-connections/youtube/callback",
            "production_frontend_url": "http://localhost:5173",
            "production_api_url": "http://localhost:8000",
        },
    )
    assert response.status_code == 200

    readiness = client.get("/api/social-connections/youtube/compliance/readiness")
    assert readiness.status_code == 200
    blocker_keys = {item["key"] for item in readiness.json()["blockers"]}
    assert "production-oauth-redirect-uri" in blocker_keys
    assert "production-frontend-url" in blocker_keys
    assert "production-api-url" in blocker_keys
