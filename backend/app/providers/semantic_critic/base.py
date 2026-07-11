from __future__ import annotations

from typing import Protocol


class SemanticCriticProvider(Protocol):
    name: str
    model: str

    def review(self, prompt: str, frames: list[dict], context: dict) -> dict:
        ...
