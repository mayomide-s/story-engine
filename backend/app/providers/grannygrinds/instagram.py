from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings


class InstagramReelsPublisher:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.instagram_access_token or not self.settings.instagram_user_id:
            raise ValueError("INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_USER_ID are required for publishing.")

    @property
    def base_url(self) -> str:
        version = self.settings.instagram_graph_api_version.strip() or "v26.0"
        return f"https://graph.facebook.com/{version}"

    def create_container(self, *, video_url: str, caption: str, share_to_feed: bool) -> dict[str, Any]:
        params = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": str(bool(share_to_feed)).lower(),
            "access_token": self.settings.instagram_access_token,
        }
        with httpx.Client(timeout=60.0) as client:
            response = client.post(f"{self.base_url}/{self.settings.instagram_user_id}/media", params=params)
            response.raise_for_status()
            return response.json()

    def get_container_status(self, container_id: str) -> dict[str, Any]:
        params = {
            "fields": "status_code,status",
            "access_token": self.settings.instagram_access_token,
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{self.base_url}/{container_id}", params=params)
            response.raise_for_status()
            return response.json()

    def publish_container(self, container_id: str) -> dict[str, Any]:
        params = {
            "creation_id": container_id,
            "access_token": self.settings.instagram_access_token,
        }
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{self.base_url}/{self.settings.instagram_user_id}/media_publish",
                params=params,
            )
            response.raise_for_status()
            return response.json()

    def get_media(self, media_id: str) -> dict[str, Any]:
        params = {
            "fields": "id,permalink",
            "access_token": self.settings.instagram_access_token,
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{self.base_url}/{media_id}", params=params)
            response.raise_for_status()
            return response.json()
