from __future__ import annotations

from typing import Any

from app.config import get_settings


class MockNarrationWriterProvider:
    name = "mock"

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.narration_writer_model

    def write(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_duration = max(float(payload.get("source_duration_seconds") or 10.0), 1.0)
        topic = str(payload.get("topic") or "coding concept")
        audience = str(payload.get("audience_level") or "beginner")
        segments = [
            {
                "start_seconds": 0.3,
                "end_seconds": round(min(source_duration * 0.28, source_duration - 0.3), 2),
                "spoken_text": f"{topic} starts with a coding problem.",
                "caption_text": f"{topic} starts with a coding problem.",
            },
            {
                "start_seconds": round(min(source_duration * 0.28, source_duration - 0.3), 2),
                "end_seconds": round(min(source_duration * 0.72, source_duration - 0.2), 2),
                "spoken_text": "The fix starts step by step.",
                "caption_text": "The fix starts step by step.",
            },
            {
                "start_seconds": round(min(source_duration * 0.72, source_duration - 0.2), 2),
                "end_seconds": round(max(source_duration - 0.4, 0.8), 2),
                "spoken_text": "The solved result holds at the end.",
                "caption_text": "The solved result holds at the end.",
            },
        ]
        full_spoken_text = " ".join(segment["spoken_text"] for segment in segments)
        return {
            "segments": segments,
            "full_spoken_text": full_spoken_text,
            "estimated_word_count": len(full_spoken_text.split()),
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "cost_estimate": 0.0,
            "provider_request_id": None,
        }
