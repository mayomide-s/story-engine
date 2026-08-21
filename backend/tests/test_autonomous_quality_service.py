from app.services.autonomous_quality_service import (
    apply_corrective_instructions,
    build_corrective_instructions,
    decide_autonomous_quality_action,
)


def _passing_criteria():
    return {
        "initial_problem_shown": {"value": "true"},
        "intended_subject_present": {"value": "true"},
        "trigger_visible": {"value": "true"},
        "transformation_attempted": {"value": "true"},
        "transformation_completed": {"value": "true"},
        "required_final_state_visible": {"value": "true"},
        "ending_held_clearly": {"value": "true"},
        "unrelated_characters_or_actions": {"value": "false"},
        "unwanted_generated_text": {"value": "false"},
    }


def test_accepts_only_high_confidence_semantic_pass():
    decision = decide_autonomous_quality_action(
        technical_quality_passed=True,
        review_status="accept",
        score=94.0,
        criteria=_passing_criteria(),
        attempt_number=1,
        max_attempts=3,
    )
    assert decision.action == "accept"


def test_low_score_accept_is_escalated_not_auto_approved():
    decision = decide_autonomous_quality_action(
        technical_quality_passed=True,
        review_status="accept",
        score=82.0,
        criteria=_passing_criteria(),
        attempt_number=1,
        max_attempts=3,
    )
    assert decision.action == "human_review"


def test_regeneration_builds_targeted_motion_corrections():
    criteria = _passing_criteria()
    criteria["transformation_completed"] = {"value": "false"}
    criteria["required_final_state_visible"] = {"value": "false"}
    criteria["unrelated_characters_or_actions"] = {"value": "true"}
    decision = decide_autonomous_quality_action(
        technical_quality_passed=True,
        review_status="regenerate",
        score=61.0,
        criteria=criteria,
        attempt_number=1,
        max_attempts=3,
    )
    assert decision.action == "regenerate"
    joined = " ".join(decision.corrective_instructions).lower()
    assert "cause-and-effect" in joined
    assert "final state" in joined
    assert "no running" in joined


def test_retry_cap_escalates_to_human():
    criteria = _passing_criteria()
    criteria["transformation_completed"] = {"value": "false"}
    decision = decide_autonomous_quality_action(
        technical_quality_passed=True,
        review_status="regenerate",
        score=55.0,
        criteria=criteria,
        attempt_number=3,
        max_attempts=3,
    )
    assert decision.action == "human_review"


def test_uncertain_semantic_review_never_spends_retry_automatically():
    decision = decide_autonomous_quality_action(
        technical_quality_passed=True,
        review_status="needs_review",
        score=78.0,
        criteria=_passing_criteria(),
        attempt_number=1,
        max_attempts=3,
    )
    assert decision.action == "human_review"


def test_technical_failure_never_triggers_paid_regeneration():
    decision = decide_autonomous_quality_action(
        technical_quality_passed=False,
        review_status="regenerate",
        score=20.0,
        criteria={},
        attempt_number=1,
        max_attempts=3,
    )
    assert decision.action == "human_review"


def test_corrective_prompt_preserves_original_story_and_appends_guidance():
    prompt = "A developer watches a broken bridge become connected."
    corrections = build_corrective_instructions({
        **_passing_criteria(),
        "ending_held_clearly": {"value": "false"},
    })
    corrected = apply_corrective_instructions(prompt, corrections)
    assert corrected.startswith(prompt)
    assert "AUTONOMOUS RETRY CORRECTIONS" in corrected
    assert "final two seconds" in corrected
