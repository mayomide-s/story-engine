from __future__ import annotations

from app.config import get_settings
from app.db.session import SessionLocal
from app.models import AppSession


def _enable_auth(monkeypatch, *, environment: str = "test"):
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("APP_ACCESS_PASSWORD", "open-sesame")
    monkeypatch.setenv("APP_SESSION_SECRET", "session-secret")
    monkeypatch.setenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver,api.storyengine.soremekun.org")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://storyengine.soremekun.org")
    get_settings.cache_clear()


def _login(client) -> str:
    response = client.post("/api/access/login", json={"password": "open-sesame"})
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_login_creates_hashed_server_side_session_and_secure_cookie_flags(client, monkeypatch):
    _enable_auth(monkeypatch, environment="production")

    response = client.post("/api/access/login", json={"password": "open-sesame"})

    assert response.status_code == 200
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "secure" in set_cookie
    assert "samesite=lax" in set_cookie
    raw_cookie = client.cookies.get("story_engine_session")
    assert raw_cookie
    with SessionLocal() as db:
        sessions = db.query(AppSession).all()
        assert len(sessions) == 1
        assert sessions[0].token_hash != raw_cookie
        assert sessions[0].revoked_at is None


def test_mutating_requests_require_valid_csrf_token(client, monkeypatch):
    _enable_auth(monkeypatch)
    csrf_token = _login(client)

    missing = client.post("/api/pipeline-runs", json={"topic": "CSRF", "auto_mode": False})
    invalid = client.post(
        "/api/pipeline-runs",
        json={"topic": "CSRF", "auto_mode": False},
        headers={"X-CSRF-Token": "invalid-token"},
    )
    valid = client.post(
        "/api/pipeline-runs",
        json={"topic": "CSRF", "auto_mode": False},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert missing.status_code == 403
    assert missing.json()["detail"]["code"] == "csrf_validation_failed"
    assert invalid.status_code == 403
    assert invalid.json()["detail"]["code"] == "csrf_validation_failed"
    assert valid.status_code == 200


def test_unknown_origin_is_rejected_for_authenticated_mutation(client, monkeypatch):
    _enable_auth(monkeypatch)
    csrf_token = _login(client)

    response = client.post(
        "/api/pipeline-runs",
        json={"topic": "Origin", "auto_mode": False},
        headers={
            "X-CSRF-Token": csrf_token,
            "Origin": "https://evil.example.com",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "origin_not_allowed"


def test_logout_all_revokes_every_active_session(client, monkeypatch):
    _enable_auth(monkeypatch)

    first = client.post("/api/access/login", json={"password": "open-sesame"})
    second = client.post("/api/access/login", json={"password": "open-sesame"})
    csrf_token = second.json()["csrf_token"]

    response = client.post("/api/access/logout-all", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 200
    with SessionLocal() as db:
        sessions = db.query(AppSession).all()
        assert len(sessions) == 2
        assert all(session.revoked_at is not None for session in sessions)
        assert all(session.revocation_reason == "logout_all" for session in sessions)


def test_repeated_failed_login_attempts_are_rate_limited(client, monkeypatch):
    _enable_auth(monkeypatch)
    monkeypatch.setenv("LOGIN_RATE_LIMIT_ATTEMPTS", "2")
    monkeypatch.setenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60")
    get_settings.cache_clear()

    first = client.post("/api/access/login", json={"password": "wrong"})
    second = client.post("/api/access/login", json={"password": "wrong"})
    third = client.post("/api/access/login", json={"password": "wrong"})

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert third.json()["detail"]["code"] == "rate_limit_exceeded"


def test_unapproved_host_header_is_rejected(client, monkeypatch):
    _enable_auth(monkeypatch, environment="production")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.storyengine.soremekun.org,testserver")
    get_settings.cache_clear()

    response = client.get("/health", headers={"Host": "unapproved.example.com"})

    assert response.status_code == 400


def test_wildcard_credentialed_cors_is_rejected_by_configuration(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    monkeypatch.setenv("ALLOWED_HOSTS", "storyengine.soremekun.org,api.storyengine.soremekun.org")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    get_settings.cache_clear()

    errors = get_settings().configuration_errors()

    assert any("cannot contain '*'" in error for error in errors)
