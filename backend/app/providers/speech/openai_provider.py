from __future__ import annotations

from pathlib import Path

from openai import OpenAI

from app.config import get_settings


class OpenAISpeechProvider:
    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.narration_speech_model
        self.client = OpenAI(api_key=settings.openai_api_key, timeout=float(settings.narration_timeout_seconds))

    def synthesize(self, *, text: str, voice: str, destination: Path) -> dict:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.client.audio.speech.with_streaming_response.create(
            model=self.model,
            voice=voice,
            input=text,
            response_format="mp3",
        ) as response:
            response.stream_to_file(destination)
        return {
            "source_path": str(destination),
            "mime_type": "audio/mpeg",
            "provider_request_id": None,
            "usage": {"characters": len(text)},
            "cost_estimate": None,
            "voice": voice,
            "response_format": "mp3",
        }
