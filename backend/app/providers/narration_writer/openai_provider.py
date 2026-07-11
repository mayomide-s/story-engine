from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import get_settings


NARRATION_SCHEMA = {
    "name": "narration_writer_response",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "start_seconds": {"type": "number"},
                        "end_seconds": {"type": "number"},
                        "spoken_text": {"type": "string"},
                        "caption_text": {"type": "string"},
                    },
                    "required": ["start_seconds", "end_seconds", "spoken_text", "caption_text"],
                },
            },
            "full_spoken_text": {"type": "string"},
            "estimated_word_count": {"type": "integer"},
        },
        "required": ["segments", "full_spoken_text", "estimated_word_count"],
    },
}


class OpenAINarrationWriterProvider:
    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.narration_writer_model
        self.client = OpenAI(api_key=settings.openai_api_key, timeout=float(settings.narration_timeout_seconds))

    def write(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_duration = float(payload.get("source_duration_seconds") or 10.0)
        settings = get_settings()
        prompt = (
            "Write a concise AI-video narration for a short coding explainer. "
            "Explain the coding meaning, not just visible objects. "
            "Use beginner-friendly language, no hashtags, no emojis, no intro like 'In this video', and no branding outro. "
            f"Keep the total spoken words at or below {settings.narration_max_words}. "
            f"The video duration is {source_duration:.1f} seconds. "
            "Return timed segments that fit setup, transformation, and payoff."
            f"\nTopic: {payload.get('topic', '')}"
            f"\nHook: {payload.get('hook', '')}"
            f"\nConcept: {payload.get('concept', '')}"
            f"\nOutcome contract: {json.dumps(payload.get('outcome_contract', {}))}"
            f"\nStoryboard: {json.dumps(payload.get('storyboard', {}))}"
            f"\nGeneration prompt: {payload.get('generation_prompt', '')}"
            f"\nStory review explanation: {payload.get('story_review_explanation', '')}"
            f"\nHuman story review notes: {payload.get('human_story_review_notes', '')}"
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You write structured narration drafts for short internal review videos.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_schema", "json_schema": NARRATION_SCHEMA},
            max_completion_tokens=900,
        )
        content = response.choices[0].message.content or "{}"
        usage = getattr(response, "usage", None)
        return {
            **json.loads(content),
            "usage": {
                "input_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                "output_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
                "total_tokens": getattr(usage, "total_tokens", 0) if usage else 0,
            },
            "cost_estimate": None,
            "provider_request_id": None,
        }
