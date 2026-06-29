from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path

import httpx
import runwayml
from runwayml import APIError, RunwayML

from app.config import get_settings

logger = logging.getLogger(__name__)


class RunwayVideoProvider:
    name = "runway"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.runway_api_key:
            raise ValueError("RUNWAY_API_KEY is required when VIDEO_PROVIDER=runway")
        self.settings = settings
        self.client = RunwayML(api_key=settings.runway_api_key)
        self.sdk_version = getattr(runwayml, "__version__", "unknown")
        logger.info("Initialized Runway provider with runwayml %s", self.sdk_version)
        if not hasattr(self.client, "text_to_video"):
            raise ValueError("Installed runwayml SDK does not expose text_to_video.create; update runwayml to a compatible version.")

    def create_video(self, prompt: str, settings: dict) -> dict:
        duration = self._select_duration(settings)
        ratio = self._select_ratio(settings)
        try:
            task = self.client.text_to_video.create(
                model="gen4.5",
                prompt_text=prompt,
                ratio=ratio,
                duration=duration,
            )
        except APIError:
            raise
        response = task.to_dict() if hasattr(task, "to_dict") else dict(task)
        return {
            "job_id": getattr(task, "id", response.get("id")),
            "request_id": response.get("id"),
            "status": self._normalize_status(getattr(task, "status", response.get("status"))),
            "response": response,
        }

    def get_status(self, job_id: str) -> dict:
        task = self.client.tasks.retrieve(job_id)
        response = task.to_dict() if hasattr(task, "to_dict") else dict(task)
        normalized = self._normalize_status(getattr(task, "status", response.get("status")))
        output_url = self._extract_output_url(response)
        failure = self._extract_failure_message(response)
        return {
            "job_id": job_id,
            "status": normalized,
            "raw_status": getattr(task, "status", response.get("status")),
            "output_url": output_url,
            "failure": failure,
            "response": response,
        }

    def download_video(self, job_id: str) -> dict:
        status = self.get_status(job_id)
        if status["status"] != "completed":
            raise RuntimeError(f"Runway task {job_id} is not complete: {status['raw_status']}")
        if not status["output_url"]:
            raise RuntimeError(f"Runway task {job_id} did not return an output URL")

        working_dir = Path(tempfile.gettempdir()) / "story-engine-runway-assets" / job_id
        working_dir.mkdir(parents=True, exist_ok=True)
        video_path = working_dir / f"{job_id}.mp4"
        thumbnail_path = working_dir / f"{job_id}.jpg"

        self._download_file(status["output_url"], video_path)
        self._generate_thumbnail(video_path, thumbnail_path)
        video_metadata = self._probe_video(video_path)
        thumbnail_metadata = self._probe_image(thumbnail_path)

        return {
            "storage_key": f"videos/{job_id}.mp4",
            "source_path": str(video_path),
            "mime_type": "video/mp4",
            "size_bytes": video_metadata["size_bytes"],
            "duration_seconds": video_metadata["duration_seconds"],
            "width": video_metadata["width"],
            "height": video_metadata["height"],
            "thumbnail": {
                "storage_key": f"thumbnails/{job_id}.jpg",
                "source_path": str(thumbnail_path),
                "mime_type": "image/jpeg",
                "size_bytes": thumbnail_path.stat().st_size,
                "width": thumbnail_metadata["width"],
                "height": thumbnail_metadata["height"],
            },
        }

    def _select_duration(self, settings: dict) -> int:
        requested = int(settings.get("duration_seconds") or 5)
        return min(max(requested, 5), 10)

    def _select_ratio(self, settings: dict) -> str:
        aspect_ratio = settings.get("aspect_ratio", "9:16")
        if aspect_ratio == "9:16":
            return "720:1280"
        return "1280:720"

    def _normalize_status(self, status: str | None) -> str:
        normalized = (status or "").upper()
        if normalized in {"SUCCEEDED", "COMPLETED"}:
            return "completed"
        if normalized in {"FAILED", "CANCELED", "CANCELLED"}:
            return "failed"
        if normalized in {"RUNNING", "PENDING", "PROCESSING", "THROTTLED"}:
            return "processing"
        return "queued"

    def _extract_output_url(self, payload: dict) -> str | None:
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

    def _extract_failure_message(self, payload: dict) -> str | None:
        failure = payload.get("failure") or payload.get("error")
        if isinstance(failure, dict):
            return failure.get("message") or json.dumps(failure)
        if failure:
            return str(failure)
        return None

    def _download_file(self, url: str, destination: Path) -> None:
        with httpx.stream("GET", url, timeout=120.0, follow_redirects=False) as response:
            response.raise_for_status()
            with destination.open("wb") as file_handle:
                for chunk in response.iter_bytes():
                    file_handle.write(chunk)

    def _generate_thumbnail(self, video_path: Path, thumbnail_path: Path) -> None:
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            "00:00:01",
            "-i",
            str(video_path),
            "-vframes",
            "1",
            str(thumbnail_path),
        ]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _probe_video(self, file_path: Path) -> dict:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration,size",
            "-of",
            "json",
            str(file_path),
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
        file_format = payload["format"]
        return {
            "width": int(stream["width"]),
            "height": int(stream["height"]),
            "duration_seconds": int(round(float(file_format["duration"]))),
            "size_bytes": int(file_format["size"]),
        }

    def _probe_image(self, file_path: Path) -> dict:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(file_path),
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout)
        stream = payload["streams"][0]
        return {"width": int(stream["width"]), "height": int(stream["height"])}
