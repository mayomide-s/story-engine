import json

from app.config import get_settings


def _enable_auth(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("APP_ACCESS_PASSWORD", "open-sesame")
    monkeypatch.setenv("APP_SESSION_SECRET", "session-secret")
    get_settings.cache_clear()


def _auth_headers(client):
    login = client.post("/api/access/login", json={"password": "open-sesame"})
    assert login.status_code == 200
    token = login.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_auth_disabled_preserves_existing_behavior(client, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.delenv("APP_ACCESS_PASSWORD", raising=False)
    get_settings.cache_clear()

    response = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    assert response.status_code == 200
    assert response.json()["pipeline_run"]["status"] == "awaiting_review"


def test_auth_enabled_rejects_unauthenticated_protected_api_calls(client, monkeypatch):
    _enable_auth(monkeypatch)

    runs = client.get("/api/pipeline-runs")
    queue = client.get("/api/idea-queue")
    settings_response = client.get("/api/settings/account-defaults")

    assert runs.status_code == 401
    assert queue.status_code == 401
    assert settings_response.status_code == 401


def test_login_succeeds_with_correct_password(client, monkeypatch):
    _enable_auth(monkeypatch)

    response = client.post("/api/access/login", json={"password": "open-sesame"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["auth_enabled"] is True
    assert payload["token"]


def test_login_fails_with_wrong_password(client, monkeypatch):
    _enable_auth(monkeypatch)

    response = client.post("/api/access/login", json={"password": "wrong-password"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid access password."


def test_protected_apis_work_after_valid_auth(client, monkeypatch):
    _enable_auth(monkeypatch)
    headers = _auth_headers(client)

    defaults = client.get("/api/settings/account-defaults", headers=headers)
    create = client.post("/api/pipeline-runs", json={"topic": "JWT", "auto_mode": False}, headers=headers)

    assert defaults.status_code == 200
    assert create.status_code == 200
    assert create.json()["pipeline_run"]["status"] == "awaiting_review"


def test_health_endpoints_remain_safe_when_auth_enabled(client, monkeypatch):
    _enable_auth(monkeypatch)

    health = client.get("/health")
    details = client.get("/health/details")

    assert health.status_code == 200
    assert details.status_code == 200
    payload = details.json()
    assert payload["auth_enabled"] is True
    serialized = json.dumps(payload)
    assert "open-sesame" not in serialized
    assert "session-secret" not in serialized


def test_security_headers_apply_to_health_response(client):
    response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
