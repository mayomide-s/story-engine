from __future__ import annotations

import wave
from pathlib import Path

from app.config import get_settings


class MockSpeechProvider:
    name = "mock"

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.narration_speech_model

    def synthesize(self, *, text: str, voice: str, destination: Path) -> dict:
        word_count = max(len(text.split()), 1)
        duration_seconds = min(max(word_count * 0.34 + 0.8, 1.2), 14.0)
        sample_rate = 24000
        frame_count = int(duration_seconds * sample_rate)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(destination), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"\x00\x00" * frame_count)
        return {
            "source_path": str(destination),
            "duration_seconds": round(duration_seconds, 2),
            "mime_type": "audio/wav",
            "provider_request_id": None,
            "usage": {"characters": len(text)},
            "cost_estimate": 0.0,
            "voice": voice,
        }
