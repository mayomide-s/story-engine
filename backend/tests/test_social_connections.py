from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import SessionLocal
from app.models import OAuthState, SocialConnection
from app.providers.youtube import oauth as youtube_oauth
from app.providers.youtube.oauth import (
    MultipleYouTubeChannelsUnsupportedError,
    YOUTUBE_OAUTH_SCOPES,
    YOUTUBE_READONLY_SCOPE,
    YOUTUBE_UPLOAD_SCOPE,
    YouTubeChannelNotFoundError,
)
from app.services.oauth_state_service import OAuthStateError, consume_oauth_state, create_oauth_state
from app.services.social_token_crypto import SocialTokenCryptoError, decrypt_secret, encrypt_secret


def _configure_social_env(monkeypatch):
    monkeypatch.setenv("SOCIAL_TOKEN_ENCRYPTION_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-google-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-google-client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8000/api/social-connections/youtube/callback")
    monkeypatch.setenv("GOOGLE_OAUTH_FRONTEND_SUCCESS_URL", "http://localhost:5173/social/success")
    monkeypatch.setenv("GOOGLE_OAUTH_FRONTEND_ERROR_URL", "http://localhost:5173/social/error")
    get_settings.cache_clear()


def test_social_token_crypto_round_trip(monkeypatch):
    _configure_social_env(monkeypatch)

    ciphertext, version = encrypt_secret("refresh-token-value", purpose="refresh token")

    assert version == "v1"
    assert ciphertext != "refresh-token-value"
    assert decrypt_secret(ciphertext, purpose="refresh token") == "refresh-token-value"


def test_social_token_crypto_wrong_key_fails(monkeypatch):
    _configure_social_env(monkeypatch)
    ciphertext, _ = encrypt_secret("access-token-value", purpose="access token")

    monkeypatch.setenv("SOCIAL_TOKEN_ENCRYPTION_KEY", "QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo0NTY3ODk=")
    get_settings.cache_clear()

    with pytest.raises(SocialTokenCryptoError) as exc_info:
        decrypt_secret(ciphertext, purpose="access token")

    assert "access-token-value" not in str(exc_info.value)


def test_social_token_crypto_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("SOCIAL_TOKEN_ENCRYPTION_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(SocialTokenCryptoError):
        encrypt_secret("abc", purpose="access token")


def test_oauth_state_success_and_one_time_consumption():
    with SessionLocal() as db:
        raw_state, record = create_oauth_state(db, platform="youtube", return_path="/review")
        db.commit()

        consumed = consume_oauth_state(db, raw_state=raw_state, platform="youtube")
        db.commit()

        assert consumed.id == record.id
        assert consumed.return_path == "/review"
        assert consumed.consumed_at is not None

        with pytest.raises(OAuthStateError):
            consume_oauth_state(db, raw_state=raw_state, platform="youtube")


def test_oauth_state_wrong_platform_and_expiry():
    with SessionLocal() as db:
        raw_state, record = create_oauth_state(db, platform="youtube")
        db.commit()

        with pytest.raises(OAuthStateError):
            consume_oauth_state(db, raw_state=raw_state, platform="tiktok")

        record = db.get(OAuthState, record.id)
        record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.add(record)
        db.commit()

        with pytest.raises(OAuthStateError):
            consume_oauth_state(db, raw_state=raw_state, platform="youtube")


def test_oauth_state_invalid_return_path_rejected():
    with SessionLocal() as db:
        with pytest.raises(OAuthStateError):
            create_oauth_state(db, platform="youtube", return_path="https://evil.example.com")


def test_authorize_youtube_connection_returns_expected_scope(client, monkeypatch):
    _configure_social_env(monkeypatch)

    response = client.post(
        "/api/social-connections/youtube/authorize",
        json={"return_path": "/review"},
    )

    assert response.status_code == 200
    payload = response.json()
    parsed = urlparse(payload["authorization_url"])
    query = parse_qs(parsed.query)
    scopes = set(query.get("scope", [""])[0].split())
    assert scopes == {YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READONLY_SCOPE}
    assert "openid" not in scopes
    assert "profile" not in scopes
    assert "https://www.googleapis.com/auth/youtube" not in scopes
    assert "https://www.googleapis.com/auth/youtube.force-ssl" not in scopes
    assert query["redirect_uri"][0] == "http://localhost:8000/api/social-connections/youtube/callback"
    assert payload["platform"] == "youtube"


def test_exchange_callback_code_resolves_exactly_one_youtube_channel(monkeypatch):
    _configure_social_env(monkeypatch)

    class FakeCredentials:
        token = "access-token"
        refresh_token = "refresh-token"
        expiry = datetime.now(UTC) + timedelta(hours=1)
        granted_scopes = list(YOUTUBE_OAUTH_SCOPES)

    class FakeFlow:
        credentials = FakeCredentials()

        def fetch_token(self, code):
            assert code == "valid-code"

    class FakeChannelsList:
        def execute(self):
            return {
                "items": [
                    {
                        "id": "UC1234567890ABCDEF",
                        "snippet": {
                            "title": "CodeToons Channel",
                            "customUrl": "@codetoons",
                        },
                    }
                ]
            }

    class FakeChannelsResource:
        def list(self, *, part, mine):
            assert part == "id,snippet"
            assert mine is True
            return FakeChannelsList()

    class FakeYouTubeService:
        def channels(self):
            return FakeChannelsResource()

    monkeypatch.setattr(youtube_oauth, "_build_flow", lambda settings: FakeFlow())
    monkeypatch.setattr(youtube_oauth, "build", lambda *args, **kwargs: FakeYouTubeService())

    payload = youtube_oauth.exchange_callback_code("valid-code")

    assert payload.external_account_id == "UC1234567890ABCDEF"
    assert payload.display_name == "CodeToons Channel"
    assert payload.username == "@codetoons"
    assert payload.provider_metadata["channel_identity_source"] == "youtube.channels.list.mine"


def test_exchange_callback_code_fails_when_no_youtube_channel_is_returned(monkeypatch):
    _configure_social_env(monkeypatch)

    class FakeCredentials:
        token = "access-token"
        refresh_token = "refresh-token"
        expiry = datetime.now(UTC) + timedelta(hours=1)
        granted_scopes = list(YOUTUBE_OAUTH_SCOPES)

    class FakeFlow:
        credentials = FakeCredentials()

        def fetch_token(self, code):
            assert code == "valid-code"

    class FakeChannelsList:
        def execute(self):
            return {"items": []}

    class FakeChannelsResource:
        def list(self, *, part, mine):
            return FakeChannelsList()

    class FakeYouTubeService:
        def channels(self):
            return FakeChannelsResource()

    monkeypatch.setattr(youtube_oauth, "_build_flow", lambda settings: FakeFlow())
    monkeypatch.setattr(youtube_oauth, "build", lambda *args, **kwargs: FakeYouTubeService())

    with pytest.raises(YouTubeChannelNotFoundError):
        youtube_oauth.exchange_callback_code("valid-code")


def test_exchange_callback_code_fails_when_multiple_youtube_channels_are_returned(monkeypatch):
    _configure_social_env(monkeypatch)

    class FakeCredentials:
        token = "access-token"
        refresh_token = "refresh-token"
        expiry = datetime.now(UTC) + timedelta(hours=1)
        granted_scopes = list(YOUTUBE_OAUTH_SCOPES)

    class FakeFlow:
        credentials = FakeCredentials()

        def fetch_token(self, code):
            assert code == "valid-code"

    class FakeChannelsList:
        def execute(self):
            return {
                "items": [
                    {"id": "UC111", "snippet": {"title": "Channel One"}},
                    {"id": "UC222", "snippet": {"title": "Channel Two"}},
                ]
            }

    class FakeChannelsResource:
        def list(self, *, part, mine):
            return FakeChannelsList()

    class FakeYouTubeService:
        def channels(self):
            return FakeChannelsResource()

    monkeypatch.setattr(youtube_oauth, "_build_flow", lambda settings: FakeFlow())
    monkeypatch.setattr(youtube_oauth, "build", lambda *args, **kwargs: FakeYouTubeService())

    with pytest.raises(MultipleYouTubeChannelsUnsupportedError):
        youtube_oauth.exchange_callback_code("valid-code")


def test_authorize_youtube_connection_missing_configuration_fails_safely(client):
    response = client.post("/api/social-connections/youtube/authorize", json={})
    assert response.status_code == 409
    assert "GOOGLE_OAUTH_CLIENT_ID" in response.json()["detail"]


def test_youtube_callback_encrypts_tokens_and_list_omits_ciphertext(client, monkeypatch):
    _configure_social_env(monkeypatch)

    import app.services.social_connection_service as social_service

    def fake_exchange(_code: str):
        return social_service.exchange_callback_code.__annotations__  # pragma: no cover

    class FakeTokenPayload:
        external_account_id = "UC1234567890ABCDEF"
        display_name = "CodeToons Channel"
        username = "@codetoons"
        access_token = "plain-access-token"
        refresh_token = "plain-refresh-token"
        token_expiry = datetime.now(UTC) + timedelta(hours=1)
        granted_scopes = list(YOUTUBE_OAUTH_SCOPES)
        provider_metadata = {"channel_identity_source": "youtube.channels.list.mine"}

    monkeypatch.setattr(social_service, "exchange_callback_code", lambda code: FakeTokenPayload())

    authorize = client.post("/api/social-connections/youtube/authorize", json={"return_path": "/review"})
    parsed = urlparse(authorize.json()["authorization_url"])
    state = parse_qs(parsed.query)["state"][0]

    callback = client.get(
        "/api/social-connections/youtube/callback",
        params={"state": state, "code": "auth-code"},
        follow_redirects=False,
    )

    assert callback.status_code == 302
    redirect_query = parse_qs(urlparse(callback.headers["location"]).query)
    connection_id = redirect_query["connection_id"][0]

    with SessionLocal() as db:
        connection = db.get(SocialConnection, connection_id)
        assert connection is not None
        assert connection.encrypted_access_token != "plain-access-token"
        assert connection.encrypted_refresh_token != "plain-refresh-token"
        assert decrypt_secret(connection.encrypted_access_token, purpose="access token") == "plain-access-token"
        assert decrypt_secret(connection.encrypted_refresh_token, purpose="refresh token") == "plain-refresh-token"

    listed = client.get("/api/social-connections")
    assert listed.status_code == 200
    item = listed.json()["items"][0]
    assert item["display_name"] == "CodeToons Channel"
    assert item["username"] == "@codetoons"
    assert "encrypted_access_token" not in str(listed.json())
    assert item["token_health"] == "healthy"


def test_youtube_reconnect_preserves_existing_refresh_token_when_google_omits_it(client, monkeypatch):
    _configure_social_env(monkeypatch)
    import app.services.social_connection_service as social_service

    class InitialPayload:
        external_account_id = "UCCHANNEL1234"
        display_name = "Channel One"
        username = "@channelone"
        access_token = "initial-access-token"
        refresh_token = "initial-refresh-token"
        token_expiry = datetime.now(UTC) + timedelta(hours=1)
        granted_scopes = list(YOUTUBE_OAUTH_SCOPES)
        provider_metadata = {}

    monkeypatch.setattr(social_service, "exchange_callback_code", lambda code: InitialPayload())
    first_authorize = client.post("/api/social-connections/youtube/authorize", json={})
    first_state = parse_qs(urlparse(first_authorize.json()["authorization_url"]).query)["state"][0]
    first_callback = client.get(
        "/api/social-connections/youtube/callback",
        params={"state": first_state, "code": "first"},
        follow_redirects=False,
    )
    connection_id = parse_qs(urlparse(first_callback.headers["location"]).query)["connection_id"][0]

    with SessionLocal() as db:
        original = db.get(SocialConnection, connection_id)
        assert original is not None
        original_refresh = original.encrypted_refresh_token

    class ReconnectPayload:
        external_account_id = "UCCHANNEL1234"
        display_name = "Channel One Updated"
        username = "@channeloneupdated"
        access_token = "updated-access-token"
        refresh_token = None
        token_expiry = datetime.now(UTC) + timedelta(hours=2)
        granted_scopes = list(YOUTUBE_OAUTH_SCOPES)
        provider_metadata = {}

    monkeypatch.setattr(social_service, "exchange_callback_code", lambda code: ReconnectPayload())
    second_authorize = client.post("/api/social-connections/youtube/authorize", json={})
    second_state = parse_qs(urlparse(second_authorize.json()["authorization_url"]).query)["state"][0]
    second_callback = client.get(
        "/api/social-connections/youtube/callback",
        params={"state": second_state, "code": "second"},
        follow_redirects=False,
    )

    second_connection_id = parse_qs(urlparse(second_callback.headers["location"]).query)["connection_id"][0]
    assert second_connection_id == connection_id

    with SessionLocal() as db:
        updated = db.get(SocialConnection, connection_id)
        assert updated is not None
        assert updated.encrypted_refresh_token == original_refresh
        assert updated.is_default is True
        assert updated.display_name == "Channel One Updated"


def test_youtube_callback_rejects_zero_channels_without_creating_a_connection(client, monkeypatch):
    _configure_social_env(monkeypatch)
    import app.services.social_connection_service as social_service

    with SessionLocal() as db:
        initial_count = db.query(SocialConnection).count()

    monkeypatch.setattr(
        social_service,
        "exchange_callback_code",
        lambda code: (_ for _ in ()).throw(YouTubeChannelNotFoundError("no channel")),
    )

    authorize = client.post("/api/social-connections/youtube/authorize", json={})
    state = parse_qs(urlparse(authorize.json()["authorization_url"]).query)["state"][0]
    callback = client.get(
        "/api/social-connections/youtube/callback",
        params={"state": state, "code": "connect"},
        follow_redirects=False,
    )

    assert callback.status_code == 302
    query = parse_qs(urlparse(callback.headers["location"]).query)
    assert query["error_code"][0] == "youtube_channel_not_found"
    with SessionLocal() as db:
        assert db.query(SocialConnection).count() == initial_count


def test_youtube_callback_rejects_multiple_channels_without_creating_a_connection(client, monkeypatch):
    _configure_social_env(monkeypatch)
    import app.services.social_connection_service as social_service

    with SessionLocal() as db:
        initial_count = db.query(SocialConnection).count()

    monkeypatch.setattr(
        social_service,
        "exchange_callback_code",
        lambda code: (_ for _ in ()).throw(MultipleYouTubeChannelsUnsupportedError("multiple channels")),
    )

    authorize = client.post("/api/social-connections/youtube/authorize", json={})
    state = parse_qs(urlparse(authorize.json()["authorization_url"]).query)["state"][0]
    callback = client.get(
        "/api/social-connections/youtube/callback",
        params={"state": state, "code": "connect"},
        follow_redirects=False,
    )

    assert callback.status_code == 302
    query = parse_qs(urlparse(callback.headers["location"]).query)
    assert query["error_code"][0] == "multiple_youtube_channels_unsupported"
    with SessionLocal() as db:
        assert db.query(SocialConnection).count() == initial_count


def test_refresh_and_disconnect_social_connection(client, monkeypatch):
    _configure_social_env(monkeypatch)
    import app.services.social_connection_service as social_service

    class ConnectPayload:
        external_account_id = "UCREFRESH9876"
        display_name = "Refreshable Channel"
        username = "@refreshable"
        access_token = "first-access-token"
        refresh_token = "first-refresh-token"
        token_expiry = datetime.now(UTC) + timedelta(hours=1)
        granted_scopes = list(YOUTUBE_OAUTH_SCOPES)
        provider_metadata = {}

    monkeypatch.setattr(social_service, "exchange_callback_code", lambda code: ConnectPayload())
    authorize = client.post("/api/social-connections/youtube/authorize", json={})
    state = parse_qs(urlparse(authorize.json()["authorization_url"]).query)["state"][0]
    callback = client.get(
        "/api/social-connections/youtube/callback",
        params={"state": state, "code": "connect"},
        follow_redirects=False,
    )
    connection_id = parse_qs(urlparse(callback.headers["location"]).query)["connection_id"][0]

    class RefreshPayload:
        external_account_id = "UCREFRESH9876"
        display_name = "Refreshable Channel"
        username = "@refreshable"
        access_token = "refreshed-access-token"
        refresh_token = None
        token_expiry = datetime.now(UTC) + timedelta(hours=3)
        granted_scopes = list(YOUTUBE_OAUTH_SCOPES)
        provider_metadata = {"refreshed": True}

    monkeypatch.setattr(social_service, "refresh_tokens", lambda **kwargs: RefreshPayload())
    refreshed = client.post(f"/api/social-connections/{connection_id}/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["connection"]["token_health"] == "healthy"

    disconnected = client.delete(f"/api/social-connections/{connection_id}")
    assert disconnected.status_code == 200
    assert disconnected.json()["connection"]["connection_status"] == "disconnected"

    with SessionLocal() as db:
        stored = db.get(SocialConnection, connection_id)
        assert stored is not None
        assert stored.encrypted_access_token is None
        assert stored.encrypted_refresh_token is None


def test_callback_error_redirect_does_not_leak_secrets(client, monkeypatch):
    _configure_social_env(monkeypatch)

    authorize = client.post("/api/social-connections/youtube/authorize", json={})
    state = parse_qs(urlparse(authorize.json()["authorization_url"]).query)["state"][0]
    callback = client.get(
        "/api/social-connections/youtube/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )

    assert callback.status_code == 302
    location = callback.headers["location"]
    assert "access_denied" not in location
    assert "token" not in location.lower()
