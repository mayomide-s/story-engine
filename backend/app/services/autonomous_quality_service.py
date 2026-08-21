from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


AutonomousAction = Literal["accept", "regenerate", "human_review"]


@dataclass(frozen=True)
class AutonomousQualityDecision:
    action: AutonomousAction
    reason: str
    corrective_instructions: tuple[str, ...] = ()


def _criterion(criteria: dict[str, Any], name: str) -> str:
    item = criteria.get(name, {})
    if not isinstance(item, dict):
        return "uncertain"
    value = str(item.get("value", "uncertain")).lower()
    return value if value in {"true", "false", "uncertain"} else "uncertain"


def build_corrective_instructions(criteria: dict[str, Any]) -> tuple[str, ...]:
    """Translate critic failures into concrete instructions for the next generation attempt."""
    fixes: list[str] = []
    if _criterion(criteria, "initial_problem_shown") != "true":
        fixes.append("Show the coding problem clearly in the opening shot before any solution begins.")
    if _criterion(criteria, "intended_subject_present") != "true":
        fixes.append("Keep the intended main subject clearly visible and do not introduce replacement characters.")
    if _criterion(criteria, "trigger_visible") != "true":
        fixes.append("Make the intervention or trigger visibly cause the change on screen.")
    if _criterion(criteria, "transformation_attempted") != "true" or _criterion(criteria, "transformation_completed") != "true":
        fixes.append("Show one continuous cause-and-effect transformation; do not cut away or substitute unrelated motion.")
    if _criterion(criteria, "required_final_state_visible") != "true":
        fixes.append("End on the exact solved state described by the storyboard, visibly completed on screen.")
    if _criterion(criteria, "ending_held_clearly") != "true":
        fixes.append("Hold the completed final state still and readable for the final two seconds.")
    if _criterion(criteria, "unrelated_characters_or_actions") != "false":
        fixes.append("Remove unrelated characters and actions. No running, wandering, dancing, or decorative motion unless required by the story.")
    if _criterion(criteria, "unwanted_generated_text") != "false":
        fixes.append("Render no generated words, labels, code, captions, signs, or other text inside the video.")
    return tuple(dict.fromkeys(fixes))


def decide_autonomous_quality_action(
    *,
    technical_quality_passed: bool,
    review_status: str | None,
    score: float | None,
    criteria: dict[str, Any] | None,
    attempt_number: int,
    max_attempts: int,
    accept_score: float = 90.0,
) -> AutonomousQualityDecision:
    """Pure policy function: decide whether to accept, retry, or escalate.

    This function intentionally does not spend credits or mutate database state. The pipeline
    orchestrator remains responsible for paid-generation confirmation and retry execution.
    """
    if not technical_quality_passed:
        return AutonomousQualityDecision("human_review", "Technical quality checks failed; do not spend another generation automatically.")

    normalized_status = (review_status or "unavailable").lower()
    normalized_criteria = criteria if isinstance(criteria, dict) else {}

    if normalized_status == "accept" and score is not None and score >= accept_score:
        return AutonomousQualityDecision("accept", f"Semantic story review passed at {score:.1f}/100.")

    if normalized_status in {"unavailable", "needs_review"}:
        return AutonomousQualityDecision("human_review", "Semantic evidence is uncertain or unavailable, so human judgement is required.")

    if normalized_status != "regenerate":
        return AutonomousQualityDecision("human_review", f"Unsupported semantic review status '{normalized_status}'.")

    fixes = build_corrective_instructions(normalized_criteria)
    if attempt_number >= max_attempts:
        return AutonomousQualityDecision(
            "human_review",
            f"Story adherence still failed after {attempt_number} generation attempt(s).",
            fixes,
        )

    if not fixes:
        return AutonomousQualityDecision("human_review", "The critic requested regeneration but did not identify a safe targeted correction.")

    return AutonomousQualityDecision(
        "regenerate",
        f"Story adherence failed on attempt {attempt_number}; retry with targeted corrections.",
        fixes,
    )


def apply_corrective_instructions(prompt_text: str, instructions: tuple[str, ...]) -> str:
    """Append bounded, explicit retry guidance without rewriting the approved story."""
    if not instructions:
        return prompt_text
    correction_block = " AUTONOMOUS RETRY CORRECTIONS: " + " ".join(instructions)
    return (prompt_text.rstrip() + correction_block).strip()
