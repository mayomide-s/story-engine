from __future__ import annotations

from typing import Protocol


class LLMProvider(Protocol):
    name: str
    model: str

    def generate(self, stage: str, prompt: str, context: dict) -> dict:
        ...
