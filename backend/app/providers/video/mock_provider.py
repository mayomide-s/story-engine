from __future__ import annotations

import json
import subprocess
import tempfile
import uuid
from pathlib import Path


class MockVideoProvider:
    name = "mock"

    def create_video(self, prompt: str, settings: dict) -> dict:
        job_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())
        working_dir = Path(tempfile.gettempdir()) / "story-engine-mock-assets" / job_id
        working_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = working_dir / "request.json"
        metadata_path.write_text(json.dumps({"prompt": prompt, "settings": settings}), encoding="utf-8")
        return {
            "job_id": job_id,
            "request_id": request_id,
            "status": "queued",
            "response": {"prompt_preview": prompt[:120], "settings": settings},
        }

    def get_status(self, job_id: str) -> dict:
        return {"job_id": job_id, "status": "completed"}

    def download_video(self, job_id: str) -> dict:
        working_dir = Path(tempfile.gettempdir()) / "story-engine-mock-assets" / job_id
        working_dir.mkdir(parents=True, exist_ok=True)
        video_path = working_dir / f"{job_id}.mp4"
        thumbnail_path = working_dir / f"{job_id}.jpg"
        requested_duration = self._read_requested_duration(working_dir)

        if not video_path.exists():
            self._generate_video(video_path, requested_duration)
        if not thumbnail_path.exists():
            self._generate_thumbnail(video_path, thumbnail_path)

        video_metadata = self._probe_video(video_path)
        thumbnail_metadata = self._probe_image(thumbnail_path)

        return {
            "storage_key": f"videos/{job_id}.mp4",
            "source_path": str(video_path),
            "mime_type": "video/mp4",
            "size_bytes": video_path.stat().st_size,
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

    def _read_requested_duration(self, working_dir: Path) -> int:
        metadata_path = working_dir / "request.json"
        if not metadata_path.exists():
            return 18
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            return max(5, int(payload.get("settings", {}).get("duration_seconds", 18)))
        except (ValueError, TypeError):
            return 18

    def _generate_video(self, destination: Path, duration_seconds: int) -> None:
        filter_graph = (
            "drawbox=x=mod(t*70\\,420):y=220:w=120:h=120:color=0x7ee0ff@0.9:t=fill,"
            "drawbox=x=420-mod(t*55\\,420):y=520:w=100:h=100:color=0xff8c42@0.9:t=fill,"
            "drawbox=x=210+sin(t*2)*120:y=760:w=80:h=80:color=0x7bd389@0.9:t=fill"
        )
        command = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x172033:s=540x960:d={duration_seconds}:r=12",
            "-vf",
            filter_graph,
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(destination),
        ]
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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
