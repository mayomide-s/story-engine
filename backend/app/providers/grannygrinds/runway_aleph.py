from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings


RUNWAY_API_BASE = "https://api.dev.runwayml.com/v1"
RUNWAY_API_VERSION = "2024-11-06"


class RunwayAlephClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.runway_api_key:
            raise ValueError("RUNWAY_API_KEY is required for GrannyGrinds generation.")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.runway_api_key}",
            "X-Runway-Version": RUNWAY_API_VERSION,
            "Content-Type": "application/json",
        }

    def submit_edit(self, *, video_url: str, prompt: str, seed: int) -> dict[str, Any]:
        payload = {
            "model": "aleph2",
            "videoUri": video_url,
            "promptText": prompt,
            "seed": seed,
            "outputFormat": "mp4",
        }
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{RUNWAY_API_BASE}/video_to_video",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        return {
            "task_id": body["id"],
            "request": payload,
            "response": body,
        }

    def get_task(self, task_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"{RUNWAY_API_BASE}/tasks/{task_id}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    def normalize_status(payload: dict[str, Any]) -> str:
        status = str(payload.get("status") or "").upper()
        if status == "SUCCEEDED":
            return "completed"
        if status in {"FAILED", "CANCELED", "CANCELLED"}:
            return "failed"
        if status in {"RUNNING", "THROTTLED", "PENDING"}:
            return "processing"
        return "processing"

    @staticmethod
    def output_url(payload: dict[str, Any]) -> str | None:
        output = payload.get("output")
        if isinstance(output, list) and output:
            first = output[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get("url") or first.get("uri")
        if isinstance(output, dict):
            return output.get("url") or output.get("uri")
        return None
