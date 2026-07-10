from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import get_settings


CRITIC_RESPONSE_SCHEMA = {
    "name": "semantic_video_critic_observations",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "issues": {"type": "array", "items": {"type": "string"}},
            "criteria": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    key: {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "value": {"type": "string", "enum": ["true", "false", "uncertain"]},
                            "confidence": {"type": "number"},
                            "evidence_frames": {"type": "array", "items": {"type": "number"}},
                            "reason": {"type": "string"},
                        },
                        "required": ["value", "confidence", "evidence_frames", "reason"],
                    }
                    for key in (
                        "initial_problem_shown",
                        "intended_subject_present",
                        "trigger_visible",
                        "transformation_attempted",
                        "transformation_completed",
                        "required_final_state_visible",
                        "ending_held_clearly",
                        "unrelated_characters_or_actions",
                        "unwanted_generated_text",
                    )
                },
                "required": [
                    "initial_problem_shown",
                    "intended_subject_present",
                    "trigger_visible",
                    "transformation_attempted",
                    "transformation_completed",
                    "required_final_state_visible",
                    "ending_held_clearly",
                    "unrelated_characters_or_actions",
                    "unwanted_generated_text",
                ],
            },
        },
        "required": ["summary", "issues", "criteria"],
    },
}


class OpenAISemanticCriticProvider:
    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.semantic_critic_model
        self.client = OpenAI(api_key=settings.openai_api_key, timeout=float(settings.semantic_critic_timeout_seconds))

    def review(self, prompt: str, frames: list[dict], context: dict) -> dict[str, Any]:
        user_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for frame in frames:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": str(frame["data_url"]),
                        "detail": "low",
                    },
                }
            )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a sampled-frame story reviewer for short generated videos. "
                        "Judge only what is visibly supported by the supplied frames. "
                        "Do not assume unseen actions occurred between frames."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_schema", "json_schema": CRITIC_RESPONSE_SCHEMA},
            max_completion_tokens=1400,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
