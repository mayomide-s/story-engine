from __future__ import annotations

from app.providers.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    name = "mock-llm"
    model = "mock-story-engine-v1"

    def generate(self, stage: str, prompt: str, context: dict) -> dict:
        return {
            "stage": stage,
            "prompt": prompt,
            "context": context,
            "output": f"Mock output for {stage}",
            "token_usage": {"prompt_tokens": 100, "completion_tokens": 150, "total_tokens": 250},
            "cost_estimate": 0.01,
        }
