from __future__ import annotations

from typing import Protocol


class VideoProvider(Protocol):
    name: str

    def create_video(self, prompt: str, settings: dict) -> dict:
        ...

    def get_status(self, job_id: str) -> dict:
        ...

    def download_video(self, job_id: str) -> dict:
        ...
