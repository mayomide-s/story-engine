from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db.session import SessionLocal
from app.models import SocialConnection
from app.providers.youtube.publishing import (
    YouTubeUploadProgress,
    build_youtube_video_metadata,
    fetch_youtube_video_state,
    upload_media_chunks,
)
from app.services.publication_media_service import open_publication_media
from app.services.pipeline_service import seed_default_account


class _FakeResponse:
    def __init__(self, status_code: int, *, headers: dict[str, str] | None = None, payload: dict | None = None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {}

    def json(self):
        return self._payload


def _create_connection() -> str:
    with SessionLocal() as db:
        account = seed_default_account(db)
        connection = (
            db.query(SocialConnection)
            .filter(
                SocialConnection.account_id == account.id,
                SocialConnection.platform == "youtube",
                SocialConnection.external_account_id == "UCTESTPUBLISH1",
            )
            .first()
        )
        if connection is None:
            connection = SocialConnection(
                account_id=account.id,
                platform="youtube",
                external_account_id="UCTESTPUBLISH1",
            )
        connection.encrypted_access_token = "v1:test-access"
        connection.encrypted_refresh_token = "v1:test-refresh"
        connection.token_cipher_version = "v1"
        connection.token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        connection.granted_scopes_json = ["https://www.googleapis.com/auth/youtube.upload"]
        connection.connection_status = "active"
        connection.display_name = "Provider Test Channel"
        connection.username = "@providertest"
        connection.connected_at = connection.connected_at or datetime.now(UTC)
        connection.updated_at = datetime.now(UTC)
        db.add(connection)
        db.commit()
        db.refresh(connection)
        return connection.id


def test_build_youtube_video_metadata_includes_required_fields():
    target = SimpleNamespace(
        title="API Waiter",
        caption="Explaining request and response flow",
        tags_json=["api", "backend"],
        visibility="unlisted",
        options_json={
            "category_id": "27",
            "self_declared_made_for_kids": True,
            "contains_synthetic_media": False,
        },
    )

    payload = build_youtube_video_metadata(target)

    assert payload == {
        "snippet": {
            "title": "API Waiter",
            "description": "Explaining request and response flow",
            "tags": ["api", "backend"],
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": "unlisted",
            "selfDeclaredMadeForKids": True,
            "containsSyntheticMedia": False,
        },
    }


def test_upload_media_chunks_resumes_existing_session_without_network_calls(monkeypatch, tmp_path):
    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"abcdefgh")
    connection_id = _create_connection()
    with SessionLocal() as db:
        connection = db.get(SocialConnection, connection_id)
        assert connection is not None

        responses = iter(
            [
                _FakeResponse(308, headers={"Range": "bytes=0-3"}),
                _FakeResponse(200, payload={"id": "abc123xyz98"}),
            ]
        )

        class FakeSession:
            def put(self, url, *, headers, data=None, timeout):
                return next(responses)

        monkeypatch.setattr("app.providers.youtube.publishing.build_youtube_session", lambda db, connection: (FakeSession(), connection))

        progress = upload_media_chunks(
            db,
            connection,
            session_uri="https://upload.example/session/reused",
            media_path=media_path,
            mime_type="video/mp4",
            chunk_size=4,
            bytes_sent=0,
            probe_existing_session=True,
        )

    assert isinstance(progress, YouTubeUploadProgress)
    assert progress.video_id == "abc123xyz98"
    assert progress.bytes_sent == media_path.stat().st_size
    assert progress.total_bytes == media_path.stat().st_size


@pytest.mark.parametrize("privacy_status", ["private", "unlisted", "public"])
def test_fetch_youtube_video_state_reads_visibility_status_without_real_network(monkeypatch, privacy_status: str):
    connection_id = _create_connection()
    with SessionLocal() as db:
        connection = db.get(SocialConnection, connection_id)
        assert connection is not None

        class FakeSession:
            def get(self, url, *, params, timeout):
                return _FakeResponse(
                    200,
                    payload={
                        "items": [
                            {
                                "status": {
                                    "uploadStatus": "processed",
                                    "privacyStatus": privacy_status,
                                },
                                "processingDetails": {
                                    "processingStatus": "succeeded",
                                },
                            }
                        ]
                    },
                )

        monkeypatch.setattr("app.providers.youtube.publishing.build_youtube_session", lambda db, connection: (FakeSession(), connection))

        state = fetch_youtube_video_state(db, connection, video_id="abc123xyz98")

    assert state.video_id == "abc123xyz98"
    assert state.upload_status == "processed"
    assert state.processing_status == "succeeded"
    assert state.privacy_status == privacy_status


def test_open_publication_media_downloads_r2_asset_to_temporary_file_and_cleans_up(monkeypatch, tmp_path):
    asset = SimpleNamespace(storage_key="exports/final.mp4")

    class FakeBody:
        def __init__(self, content: bytes):
            self._content = content
            self._offset = 0

        def read(self, size: int):
            if self._offset >= len(self._content):
                return b""
            chunk = self._content[self._offset : self._offset + size]
            self._offset += len(chunk)
            return chunk

        def close(self):
            return None

    class FakeClient:
        def get_object(self, *, Bucket, Key):
            assert Bucket == "test-bucket"
            assert Key == "exports/final.mp4"
            return {"Body": FakeBody(b"r2-video-content")}

    fake_storage = SimpleNamespace(
        name="r2",
        client=FakeClient(),
        bucket_name="test-bucket",
    )
    monkeypatch.setattr("app.services.publication_media_service.get_storage_provider", lambda: fake_storage)

    temp_path: Path | None = None
    with open_publication_media(asset) as media_path:
        temp_path = media_path
        assert media_path.exists()
        assert media_path.read_bytes() == b"r2-video-content"

    assert temp_path is not None
    assert not temp_path.exists()
