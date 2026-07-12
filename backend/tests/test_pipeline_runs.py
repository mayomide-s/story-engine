from datetime import UTC, datetime
from pathlib import Path
import json
import tempfile
from uuid import uuid4

from app.config import Settings, get_settings
from app.db.session import SessionLocal
from app.providers.storage.r2_provider import R2StorageProvider
from app.providers.video.runway_provider import RunwayVideoProvider
from app.services.security import sanitize_for_json
from app.workers.celery_app import celery_app


def _runway_positive_prompt_body(prompt_preview: str) -> str:
    marker = "TEXT-FREE VIDEO. Do not render any words, letters, numbers, labels, captions, signs, logos, UI text, code, or subtitles."
    return prompt_preview.replace(marker, "").strip().lower()


def test_create_run_pauses_before_video(client):
    response = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    assert response.status_code == 200
    payload = response.json()
    assert payload["pipeline_run"]["status"] == "awaiting_review"
    assert payload["idea"] is not None
    assert payload["script"] is not None
    assert payload["storyboard"] is not None
    assert payload["video"] is None
    assert payload["content_critique"] is not None


def test_resume_run_completes_and_returns_aggregate(client):
    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Looks good"})
    assert resume.status_code == 200
    payload = resume.json()
    assert payload["pipeline_run"]["status"] == "completed"
    assert payload["video"] is not None
    assert payload["manual_post_package"] is not None
    assert len(payload["assets"]) >= 2
    video_assets = [asset for asset in payload["assets"] if asset["asset_type"] == "video_mp4"]
    assert video_assets
    assert video_assets[0]["mime_type"] == "video/mp4"
    assert video_assets[0]["duration_seconds"] >= 18
    assert payload["quality_checks"][0]["passed"] is True
    assert payload["video"]["status"] == "approved"
    assert payload["video"]["requested_duration_seconds"] == 18


def test_resume_run_accepts_no_body(client):
    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume")
    assert resume.status_code == 200
    payload = resume.json()
    assert payload["pipeline_run"]["status"] == "completed"
    assert payload["pipeline_run"]["review_notes"] == "Approved from dashboard"


def test_runway_resume_without_confirmation_is_rejected(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Looks good"})
    assert resume.status_code == 409
    assert "confirm_paid_generation=true" in resume.json()["detail"]
    get_settings.cache_clear()


def test_config_validation_accepts_mock_local_mode():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///./test.db",
        redis_url="redis://redis:6379/0",
        video_provider="mock",
        storage_provider="local",
    )

    assert settings.configuration_errors() == []


def test_settings_support_local_storage_path_env_alias(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///./test.db",
        redis_url="redis://redis:6379/0",
        video_provider="mock",
        storage_provider="local",
        LOCAL_STORAGE_PATH=str(tmp_path),
    )

    assert settings.local_storage_path == str(tmp_path)


def test_backend_assets_route_serves_local_storage_file(client):
    asset_root = Path(get_settings().local_storage_path)
    asset_path = asset_root / "narration" / "shared-route-check.txt"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_text("shared local asset", encoding="utf-8")

    response = client.get("/assets/narration/shared-route-check.txt")
    assert response.status_code == 200
    assert response.text == "shared local asset"


def test_backend_assets_route_uses_current_local_storage_path(client):
    asset_root = Path(get_settings().local_storage_path)
    asset_path = asset_root / "narration" / "isolated-route-check.txt"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_text("isolated local asset", encoding="utf-8")

    response = client.get("/assets/narration/isolated-route-check.txt")
    assert response.status_code == 200
    assert response.text == "isolated local asset"


def test_config_validation_does_not_require_openai_when_semantic_critic_disabled():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///./test.db",
        redis_url="redis://redis:6379/0",
        video_provider="mock",
        storage_provider="local",
        semantic_critic_enabled=False,
        openai_api_key="",
    )

    assert settings.configuration_errors() == []


def test_config_validation_requires_r2_and_runway_settings():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///./test.db",
        redis_url="redis://redis:6379/0",
        video_provider="runway",
        storage_provider="r2",
        r2_account_id="",
        r2_access_key_id="",
        r2_secret_access_key="",
        r2_bucket_name="",
        r2_public_base_url="",
        runway_api_key="",
    )

    errors = settings.configuration_errors()
    assert any("R2_ACCOUNT_ID" in error for error in errors)
    assert any("RUNWAY_API_KEY" in error for error in errors)


def test_health_details_endpoint_returns_safe_readiness_data(client, monkeypatch):
    monkeypatch.setenv("RUNWAY_API_KEY", "super-secret-runway-key")
    response = client.get("/health/details")

    assert response.status_code == 200
    payload = response.json()
    assert payload["backend_reachable"] is True
    assert payload["video_provider"] in {"mock", "runway"}
    assert "checks" in payload
    serialized = json.dumps(payload)
    assert "super-secret-runway-key" not in serialized


def test_runway_storyboard_timings_fit_requested_duration(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    response = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    assert response.status_code == 200
    scenes = response.json()["script"]["script_json"]["scenes"]
    assert [scene["time"] for scene in scenes] == ["0-2s", "2-8s", "8-10s"]
    assert response.json()["script"]["duration_seconds"] == 10
    get_settings.cache_clear()


def test_runway_prompt_preview_stays_within_provider_limit(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    response = client.post("/api/pipeline-runs", json={"topic": "Python decorators", "auto_mode": False})
    assert response.status_code == 200
    prompt_preview = response.json()["prompt_preview"]
    assert len(prompt_preview) <= 1000
    assert prompt_preview.startswith("TEXT-FREE VIDEO.")
    assert prompt_preview.count("TEXT-FREE VIDEO.") == 1
    assert "End tag:" not in prompt_preview
    assert "Made by CodeToons AI" not in prompt_preview
    assert "Here is why" not in prompt_preview
    assert "That is" not in prompt_preview
    assert "Story beats:" not in prompt_preview
    assert "core metaphor" not in prompt_preview.lower()
    assert "tied to the topic" not in prompt_preview.lower()
    assert "core metaphor for with" not in prompt_preview.lower()
    positive_body = _runway_positive_prompt_body(prompt_preview)
    for banned_term in ("caption", "subtitle", "terminal", "code snippet", "whiteboard"):
        assert banned_term not in positive_body
    get_settings.cache_clear()


def test_mock_prompt_preview_omits_runway_visual_guardrails(client):
    response = client.post("/api/pipeline-runs", json={"topic": "Python decorators", "auto_mode": False})
    assert response.status_code == 200
    prompt_preview = response.json()["prompt_preview"]
    assert "TEXT-FREE VIDEO." not in prompt_preview
    assert "Do not render any words, letters, numbers" not in prompt_preview


def test_style_preset_selection_updates_prompt_preview(client):
    response = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False, "style_preset": "bug_monster"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["pipeline_run"]["style_preset"] == "bug_monster"
    assert "bug monster" in payload["prompt_preview"].lower()


def test_prompt_preview_uses_saved_edits(client):
    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    patch = client.patch(
        f"/api/pipeline-runs/{run_id}/review-config",
        json={"prompt_override": "Custom paid Runway prompt", "caption_override": "Custom caption", "style_preset": "office_comedy"},
    )
    assert patch.status_code == 200
    payload = patch.json()
    assert payload["prompt_preview"] == "Custom paid Runway prompt"
    assert payload["pipeline_run"]["caption_override"] == "Custom caption"


def test_runway_prompt_preview_does_not_include_script_narration_lines(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    response = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    assert response.status_code == 200
    prompt_preview = response.json()["prompt_preview"]
    assert "line " not in prompt_preview.lower()
    assert "dialogue" not in prompt_preview.lower()
    assert "here is why cors matters" not in prompt_preview.lower()
    assert "this is the part that makes cors feel simple instead of random" not in prompt_preview.lower()
    get_settings.cache_clear()


def test_runway_prompt_preserves_cors_bouncer_metaphor_visually(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    response = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    assert response.status_code == 200
    prompt_preview = response.json()["prompt_preview"].lower()
    for expected_term in ("bouncer", "doorway", "pass", "matching", "blocked"):
        assert expected_term in prompt_preview
    assert "nightclub" not in prompt_preview or "club doorway" in prompt_preview
    assert "Made by CodeToons AI" not in prompt_preview
    assert "core metaphor for with" not in prompt_preview
    get_settings.cache_clear()


def test_text_only_regeneration_does_not_create_video_jobs(client):
    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    regenerated = client.post(f"/api/pipeline-runs/{run_id}/regenerate-text", json={"review_notes": "Refresh text"})
    assert regenerated.status_code == 200
    payload = regenerated.json()
    assert payload["video"] is None
    assert payload["pipeline_run"]["video_id"] is None
    assert payload["pipeline_run"]["status"] == "awaiting_review"
    assert any(event["event_type"] == "review.text_regenerated" for event in payload["pipeline_events"])


def test_improve_prompt_updates_preview_without_calling_runway(client):
    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    improved = client.post(f"/api/pipeline-runs/{run_id}/prompt-actions", json={"action": "improve"})
    assert improved.status_code == 200
    payload = improved.json()
    assert payload["pipeline_run"]["video_id"] is None
    assert payload["prompt_preview"]
    assert payload["pipeline_run"]["prompt_override"] == payload["prompt_preview"]
    assert any(event["event_type"] == "review.prompt_improved" for event in payload["pipeline_events"])


def test_shorten_prompt_respects_provider_prompt_limits(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    create = client.post("/api/pipeline-runs", json={"topic": "Long prompt CORS explainer", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    client.patch(
        f"/api/pipeline-runs/{run_id}/review-config",
        json={"prompt_override": " ".join(["verbose-runway-prompt"] * 120)},
    )

    shortened = client.post(f"/api/pipeline-runs/{run_id}/prompt-actions", json={"action": "shorten"})
    assert shortened.status_code == 200
    payload = shortened.json()
    assert len(payload["prompt_preview"]) <= 700
    assert payload["review_preflight"]["prompt_length"]["target"] == 700
    assert payload["review_preflight"]["prompt_length"]["limit"] == 1000
    get_settings.cache_clear()


def test_prompt_length_indicator_uses_correct_limit_and_target(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    response = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    assert response.status_code == 200
    preflight = response.json()["review_preflight"]
    assert preflight["prompt_length"]["limit"] == 1000
    assert preflight["prompt_length"]["target"] == 700
    assert preflight["prompt_valid"] is True
    get_settings.cache_clear()


def test_runway_storyboard_scenes_include_concrete_contract_fields(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    response = client.post("/api/pipeline-runs", json={"topic": "Developer fixes a bug with an AI assistant", "auto_mode": False, "style_preset": "office_comedy"})
    assert response.status_code == 200
    payload = response.json()
    scene = payload["script"]["script_json"]["scenes"][0]
    for key in ("purpose", "subject", "setting", "visible_action", "state_before", "state_after", "camera_direction", "forbidden_actions"):
        assert scene[key]
    assert "core metaphor" not in scene["visible_action"].lower()
    contract = payload["story_adherence_review"]
    for key in ("initial_state", "trigger", "required_transformation", "required_final_state", "final_state_hold", "prohibited_actions"):
        assert contract[key]
    assert contract["review_status"] == "preview_only"
    get_settings.cache_clear()


def test_controlled_topics_generate_distinct_storyboards_and_reject_generic_similarity(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    first = client.post("/api/pipeline-runs", json={"topic": "Developer fixes a bug with an AI assistant", "auto_mode": False, "style_preset": "office_comedy"})
    second = client.post("/api/pipeline-runs", json={"topic": "Messy code becomes clean and organised", "auto_mode": False, "style_preset": "office_comedy"})
    third = client.post("/api/pipeline-runs", json={"topic": "A slow manual coding task becomes automated", "auto_mode": False, "style_preset": "office_comedy"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200

    first_scenes = first.json()["script"]["script_json"]["scenes"]
    second_scenes = second.json()["script"]["script_json"]["scenes"]
    third_scenes = third.json()["script"]["script_json"]["scenes"]
    assert "cracked gear" in json.dumps(first_scenes).lower()
    assert "folders" in json.dumps(second_scenes).lower()
    assert "conveyor" in json.dumps(third_scenes).lower()
    assert first_scenes != second_scenes
    assert second_scenes != third_scenes
    assert third.json()["review_preflight"]["summary"] == "Preflight looks healthy for generation."
    assert third.json()["review_preflight"]["generic_output_flags"]["similar_storyboards"] == []
    get_settings.cache_clear()


def test_preflight_rejects_generic_prompt_override_with_abstract_placeholders(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    create = client.post("/api/pipeline-runs", json={"topic": "Developer fixes a bug with an AI assistant", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    patch = client.patch(
        f"/api/pipeline-runs/{run_id}/review-config",
        json={"prompt_override": "TEXT-FREE VIDEO. Show the core metaphor tied to the topic and explain the coding problem with one memorable interaction."},
    )
    assert patch.status_code == 200
    preflight = patch.json()["review_preflight"]
    assert preflight["prompt_valid"] is False
    assert "core metaphor" in preflight["generic_output_flags"]["abstract_phrase_hits"]
    assert preflight["summary"] == "Preflight rejected generic output. Make the scenes more topic-specific before spending credits."
    get_settings.cache_clear()


def test_story_adherence_review_is_unavailable_without_vision_provider(client):
    response = client.post("/api/pipeline-runs", json={"topic": "Messy code becomes clean and organised", "auto_mode": False, "style_preset": "office_comedy"})
    assert response.status_code == 200
    review = response.json()["story_adherence_review"]
    assert review["available"] is False
    assert review["review_source"] == "none"
    assert review["review_status"] == "preview_only"
    assert "vision-capable provider" not in review["explanation"].lower()
    assert "preview only" in review["explanation"].lower()


def test_semantic_critic_persists_review_without_changing_completed_run_status(client, monkeypatch):
    from app.models import StoryAdherenceReview
    from app.services import semantic_critic_service

    class FakeCritic:
        name = "openai"
        model = "fake-vision-model"

        def review(self, prompt: str, frames: list[dict], context: dict) -> dict:
            assert "Topic:" in prompt
            assert len(frames) == 5
            return {
                "summary": "The visual sequence stays on-topic and finishes cleanly.",
                "issues": [],
                "criteria": {
                    "initial_problem_shown": {"value": "true", "confidence": 0.91, "evidence_frames": [1.0], "reason": "The blocked state is visible immediately."},
                    "intended_subject_present": {"value": "true", "confidence": 0.9, "evidence_frames": [1.0, 4.0], "reason": "The same subject stays present."},
                    "trigger_visible": {"value": "true", "confidence": 0.86, "evidence_frames": [4.0], "reason": "The trigger action is visible."},
                    "transformation_attempted": {"value": "true", "confidence": 0.9, "evidence_frames": [4.0, 7.0], "reason": "The transformation begins on screen."},
                    "transformation_completed": {"value": "true", "confidence": 0.93, "evidence_frames": [7.0, 8.3], "reason": "The mess is fully resolved."},
                    "required_final_state_visible": {"value": "true", "confidence": 0.95, "evidence_frames": [8.3, 9.5], "reason": "The clean final state is obvious."},
                    "ending_held_clearly": {"value": "true", "confidence": 0.89, "evidence_frames": [8.3, 9.5], "reason": "The final state remains visible across both hold frames."},
                    "unrelated_characters_or_actions": {"value": "false", "confidence": 0.9, "evidence_frames": [1.0, 9.5], "reason": "No unrelated intrusions appear."},
                    "unwanted_generated_text": {"value": "false", "confidence": 0.88, "evidence_frames": [1.0, 9.5], "reason": "No generated text is visible."},
                },
            }

    monkeypatch.setenv("SEMANTIC_CRITIC_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(semantic_critic_service, "get_semantic_critic_provider", lambda: FakeCritic())
    monkeypatch.setattr(
        semantic_critic_service,
        "sample_story_frames",
        lambda _path: (
            [
                {"timestamp_seconds": 1.0, "frame_hash": "hash-1", "width": 540, "height": 960, "data_url": "data:image/jpeg;base64,QQ=="},
                {"timestamp_seconds": 4.0, "frame_hash": "hash-2", "width": 540, "height": 960, "data_url": "data:image/jpeg;base64,QQ=="},
                {"timestamp_seconds": 7.0, "frame_hash": "hash-3", "width": 540, "height": 960, "data_url": "data:image/jpeg;base64,QQ=="},
                {"timestamp_seconds": 8.3, "frame_hash": "hash-4", "width": 540, "height": 960, "data_url": "data:image/jpeg;base64,QQ=="},
                {"timestamp_seconds": 9.5, "frame_hash": "hash-5", "width": 540, "height": 960, "data_url": "data:image/jpeg;base64,QQ=="},
            ],
            {
                "video_duration_seconds": 10.0,
                "sampling_strategy": "fixed_10s",
                "frames": [
                    {"timestamp_seconds": 1.0, "frame_hash": "hash-1", "width": 540, "height": 960, "persisted_asset": None},
                    {"timestamp_seconds": 4.0, "frame_hash": "hash-2", "width": 540, "height": 960, "persisted_asset": None},
                    {"timestamp_seconds": 7.0, "frame_hash": "hash-3", "width": 540, "height": 960, "persisted_asset": None},
                    {"timestamp_seconds": 8.3, "frame_hash": "hash-4", "width": 540, "height": 960, "persisted_asset": None},
                    {"timestamp_seconds": 9.5, "frame_hash": "hash-5", "width": 540, "height": 960, "persisted_asset": None},
                ],
            },
        ),
    )

    create = client.post("/api/pipeline-runs", json={"topic": "Messy code becomes clean and organised", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Generate baseline"})
    assert resume.status_code == 200
    payload = resume.json()
    assert payload["pipeline_run"]["status"] == "completed"
    assert payload["story_adherence_review"]["review_status"] == "accept"
    assert payload["story_adherence_review"]["score"] == 100.0
    assert payload["story_adherence_review"]["human_review"] is None
    assert payload["story_adherence_review"]["sampled_frames"]["frames"][0]["frame_hash"] == "hash-1"
    assert "data_url" not in json.dumps(payload["story_adherence_review"]["sampled_frames"])

    with SessionLocal() as db:
        reviews = db.query(StoryAdherenceReview).filter(StoryAdherenceReview.pipeline_run_id == run_id).all()
        assert len(reviews) == 1
        assert reviews[0].review_status == "accept"
        assert reviews[0].model == "fake-vision-model"
    get_settings.cache_clear()


def test_story_adherence_recheck_reuses_existing_review_without_new_provider_call(client, monkeypatch):
    from app.services import semantic_critic_service

    call_count = {"count": 0}

    class FakeCritic:
        name = "openai"
        model = "fake-vision-model"

        def review(self, prompt: str, frames: list[dict], context: dict) -> dict:
            call_count["count"] += 1
            return {
                "summary": "The story completes.",
                "issues": [],
                "criteria": {
                    "initial_problem_shown": {"value": "true", "confidence": 0.9, "evidence_frames": [1.0], "reason": "Visible."},
                    "intended_subject_present": {"value": "true", "confidence": 0.9, "evidence_frames": [1.0], "reason": "Visible."},
                    "trigger_visible": {"value": "true", "confidence": 0.9, "evidence_frames": [4.0], "reason": "Visible."},
                    "transformation_attempted": {"value": "true", "confidence": 0.9, "evidence_frames": [4.0], "reason": "Visible."},
                    "transformation_completed": {"value": "true", "confidence": 0.9, "evidence_frames": [7.0], "reason": "Visible."},
                    "required_final_state_visible": {"value": "true", "confidence": 0.9, "evidence_frames": [8.3], "reason": "Visible."},
                    "ending_held_clearly": {"value": "true", "confidence": 0.9, "evidence_frames": [8.3, 9.5], "reason": "Visible."},
                    "unrelated_characters_or_actions": {"value": "false", "confidence": 0.9, "evidence_frames": [1.0], "reason": "None."},
                    "unwanted_generated_text": {"value": "false", "confidence": 0.9, "evidence_frames": [1.0], "reason": "None."},
                },
            }

    monkeypatch.setenv("SEMANTIC_CRITIC_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(semantic_critic_service, "get_semantic_critic_provider", lambda: FakeCritic())
    monkeypatch.setattr(
        semantic_critic_service,
        "sample_story_frames",
        lambda _path: (
            [{"timestamp_seconds": 1.0, "frame_hash": "hash-1", "width": 540, "height": 960, "data_url": "data:image/jpeg;base64,QQ=="}] * 5,
            {"video_duration_seconds": 10.0, "sampling_strategy": "fixed_10s", "frames": [{"timestamp_seconds": 1.0, "frame_hash": "hash-1", "width": 540, "height": 960, "persisted_asset": None}] * 5},
        ),
    )

    create = client.post("/api/pipeline-runs", json={"topic": "Developer fixes a bug with an AI assistant", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Generate baseline"})
    assert resume.status_code == 200
    assert call_count["count"] == 1

    recheck = client.post(f"/api/pipeline-runs/{run_id}/story-adherence/recheck", json={"review_notes": "Try again"})
    assert recheck.status_code == 200
    payload = recheck.json()
    assert payload["pipeline_run"]["status"] == "completed"
    assert payload["story_adherence_review"]["review_status"] == "accept"
    assert call_count["count"] == 1
    get_settings.cache_clear()


def test_human_story_review_is_stored_separately_from_critic_output(client, monkeypatch):
    from app.models import StoryAdherenceHumanReview, StoryAdherenceReview
    from app.services import semantic_critic_service

    class FakeCritic:
        name = "openai"
        model = "fake-vision-model"

        def review(self, prompt: str, frames: list[dict], context: dict) -> dict:
            return {
                "summary": "Final state is present but the hold is uncertain.",
                "issues": ["Final hold is short."],
                "criteria": {
                    "initial_problem_shown": {"value": "true", "confidence": 0.9, "evidence_frames": [1.0], "reason": "Visible."},
                    "intended_subject_present": {"value": "true", "confidence": 0.9, "evidence_frames": [1.0], "reason": "Visible."},
                    "trigger_visible": {"value": "true", "confidence": 0.9, "evidence_frames": [4.0], "reason": "Visible."},
                    "transformation_attempted": {"value": "true", "confidence": 0.9, "evidence_frames": [4.0], "reason": "Visible."},
                    "transformation_completed": {"value": "true", "confidence": 0.9, "evidence_frames": [7.0], "reason": "Visible."},
                    "required_final_state_visible": {"value": "true", "confidence": 0.9, "evidence_frames": [8.3], "reason": "Visible."},
                    "ending_held_clearly": {"value": "uncertain", "confidence": 0.6, "evidence_frames": [8.3, 9.5], "reason": "Borderline hold."},
                    "unrelated_characters_or_actions": {"value": "false", "confidence": 0.9, "evidence_frames": [1.0], "reason": "None."},
                    "unwanted_generated_text": {"value": "false", "confidence": 0.9, "evidence_frames": [1.0], "reason": "None."},
                },
            }

    monkeypatch.setenv("SEMANTIC_CRITIC_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr(semantic_critic_service, "get_semantic_critic_provider", lambda: FakeCritic())
    monkeypatch.setattr(
        semantic_critic_service,
        "sample_story_frames",
        lambda _path: (
            [{"timestamp_seconds": 1.0, "frame_hash": "hash-1", "width": 540, "height": 960, "data_url": "data:image/jpeg;base64,QQ=="}] * 5,
            {"video_duration_seconds": 10.0, "sampling_strategy": "fixed_10s", "frames": [{"timestamp_seconds": 1.0, "frame_hash": "hash-1", "width": 540, "height": 960, "persisted_asset": None}] * 5},
        ),
    )

    create = client.post("/api/pipeline-runs", json={"topic": "A slow manual coding task becomes automated", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Generate baseline"})
    assert resume.status_code == 200
    before = resume.json()["story_adherence_review"]

    human = client.post(
        f"/api/pipeline-runs/{run_id}/story-adherence/human-review",
        json={"decision": "approve", "notes": "Accepting this one manually."},
    )
    assert human.status_code == 200
    payload = human.json()["story_adherence_review"]
    assert payload["review_status"] == before["review_status"]
    assert payload["score"] == before["score"]
    assert payload["human_review"]["decision"] == "approve"
    assert payload["human_review"]["notes"] == "Accepting this one manually."

    with SessionLocal() as db:
        critic = db.query(StoryAdherenceReview).filter(StoryAdherenceReview.pipeline_run_id == run_id).one()
        human_review = db.query(StoryAdherenceHumanReview).filter(StoryAdherenceHumanReview.pipeline_run_id == run_id).one()
        assert critic.review_status == "needs_review"
        assert human_review.decision == "approve"
    get_settings.cache_clear()


def test_semantic_frame_sampling_scales_for_non_ten_second_videos():
    from app.services.semantic_critic_service import build_sample_timestamps

    timestamps, strategy = build_sample_timestamps(18.0)
    assert strategy == "scaled_by_duration"
    assert timestamps == [1.8, 7.2, 12.6, 14.94, 17.1]


def test_semantic_critic_downloads_video_when_local_storage_path_is_missing(monkeypatch, tmp_path):
    from app.services import semantic_critic_service

    class FakeStorage:
        name = "local"

        def resolve_path(self, storage_key: str) -> str:
            return str(tmp_path / storage_key)

    class FakeAsset:
        id = "asset-123"
        storage_key = "videos/missing.mp4"
        public_url = "https://example.com/video.mp4"

    downloaded = {}

    def fake_download(asset, destination):
        downloaded["asset_id"] = asset.id
        destination.write_bytes(b"video-bytes")

    monkeypatch.setattr(semantic_critic_service, "get_storage_provider", lambda: FakeStorage())
    monkeypatch.setattr(semantic_critic_service, "_download_video_to_temp", fake_download)

    resolved_path, should_delete = semantic_critic_service.resolve_video_source_path(FakeAsset())

    assert should_delete is True
    assert resolved_path.exists()
    assert resolved_path.read_bytes() == b"video-bytes"
    assert downloaded["asset_id"] == "asset-123"


def test_preflight_scoring_appears_in_run_detail(client):
    response = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    assert response.status_code == 200
    preflight = response.json()["review_preflight"]
    assert preflight is not None
    assert "overall_preflight_score" in preflight["scores"]
    assert "clarity_score" in preflight["scores"]
    assert "prompt_length" in preflight


def test_critique_data_appears_in_aggregate_response(client):
    response = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    assert response.status_code == 200
    critique = response.json()["content_critique"]
    assert critique is not None
    assert "beginner_clarity" in critique
    assert "social_hook_strength" in critique


def test_r2_storage_provider_returns_public_url(monkeypatch):
    uploaded = {}

    class FakeClient:
        def upload_file(self, source_path, bucket_name, storage_key, ExtraArgs=None):
            uploaded["source_path"] = source_path
            uploaded["bucket_name"] = bucket_name
            uploaded["storage_key"] = storage_key
            uploaded["content_type"] = ExtraArgs["ContentType"]

    monkeypatch.setenv("R2_ACCOUNT_ID", "acct")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "key")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("R2_BUCKET_NAME", "bucket")
    monkeypatch.setenv("R2_PUBLIC_BASE_URL", "https://cdn.example.com")
    get_settings.cache_clear()

    provider = R2StorageProvider()
    provider.client = FakeClient()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as handle:
        handle.write(b"video")
        file_path = Path(handle.name)

    result = provider.save_file(str(file_path), "videos/test.mp4")
    assert uploaded["bucket_name"] == "bucket"
    assert uploaded["storage_key"] == "videos/test.mp4"
    assert result["public_url"] == "https://cdn.example.com/videos/test.mp4"
    assert result["mime_type"] == "video/mp4"
    get_settings.cache_clear()


def test_upload_failure_marks_pipeline_failed(client, monkeypatch):
    from app.services import pipeline_service

    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    class FailingStorage:
        name = "r2"

        def save_file(self, source_path: str, storage_key: str) -> dict:
            raise RuntimeError("R2 upload failed")

        def build_public_url(self, storage_key: str) -> str:
            return f"https://cdn.example.com/{storage_key}"

        def resolve_path(self, storage_key: str) -> str:
            return storage_key

    monkeypatch.setattr(pipeline_service, "get_storage_provider", lambda: FailingStorage())
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Try upload"})
    assert resume.status_code == 200
    payload = resume.json()
    assert payload["pipeline_run"]["status"] == "failed"
    assert any(event["event_type"] == "asset.upload_failed" for event in payload["pipeline_events"])


def test_runway_provider_create_and_status(monkeypatch):
    class FakeTask:
        def __init__(self, payload):
            self.id = payload["id"]
            self.status = payload["status"]
            self.payload = payload

        def to_dict(self):
            return self.payload

    class FakeTextToVideo:
        def create(self, **kwargs):
            return FakeTask({"id": "task-123", "status": "PENDING", "request": kwargs})

    class FakeTasks:
        def retrieve(self, job_id):
            return FakeTask({"id": job_id, "status": "SUCCEEDED", "output": ["https://example.com/video.mp4"]})

    class FakeClient:
        def __init__(self):
            self.text_to_video = FakeTextToVideo()
            self.tasks = FakeTasks()

    monkeypatch.setenv("RUNWAY_API_KEY", "runway-secret")
    get_settings.cache_clear()
    provider = RunwayVideoProvider()
    provider.client = FakeClient()

    created = provider.create_video("prompt", {"aspect_ratio": "9:16", "duration_seconds": 8})
    assert created["job_id"] == "task-123"
    assert created["status"] in {"processing", "queued"}
    assert created["response"]["request"]["model"] == "gen4.5"
    assert created["response"]["request"]["prompt_text"] == "prompt"

    status = provider.get_status("task-123")
    assert status["status"] == "completed"
    assert status["output_url"] == "https://example.com/video.mp4"
    get_settings.cache_clear()


def test_runway_provider_failure_path(client, monkeypatch):
    from app.services import pipeline_service

    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    class FailingRunwayProvider:
        name = "runway"
        sdk_version = "5.4.0"

        def create_video(self, prompt: str, settings: dict) -> dict:
            raise RuntimeError("Runway request invalid")

        def get_status(self, job_id: str) -> dict:
            return {"job_id": job_id, "status": "failed"}

        def download_video(self, job_id: str) -> dict:
            raise RuntimeError("not used")

    monkeypatch.setattr(pipeline_service, "get_video_provider", lambda: FailingRunwayProvider())
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    monkeypatch.setattr(pipeline_service, "enqueue_resume_pipeline_task", lambda run_id, countdown=None: None)

    resume = client.post(
        f"/api/pipeline-runs/{run_id}/resume",
        json={"review_notes": "Use runway", "confirm_paid_generation": True},
    )
    assert resume.status_code == 200

    with SessionLocal() as db:
        try:
            pipeline_service.process_resume_pipeline(db, run_id)
        except RuntimeError:
            pass

    detail = client.get(f"/api/pipeline-runs/{run_id}")
    payload = detail.json()
    assert payload["pipeline_run"]["status"] == "failed"
    assert any(event["event_type"] == "pipeline.resume_failed" for event in payload["pipeline_events"])
    get_settings.cache_clear()


def test_resume_commits_running_state_before_provider_work(client, monkeypatch):
    from app.services import pipeline_service

    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    queued = {}

    def fake_enqueue(task_run_id, countdown=None):
        queued["run_id"] = task_run_id
        queued["countdown"] = countdown

    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    monkeypatch.setattr(pipeline_service, "enqueue_resume_pipeline_task", fake_enqueue)

    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"confirm_paid_generation": True})
    assert resume.status_code == 200
    payload = resume.json()
    assert payload["pipeline_run"]["status"] == "running"
    assert payload["pipeline_run"]["resumed_at"] is not None
    assert payload["pipeline_run"]["current_stage"] == "video_prompt_build"
    assert payload["video"] is None
    assert queued["run_id"] == run_id
    assert any(event["event_type"] == "pipeline.resumed" for event in payload["pipeline_events"])
    get_settings.cache_clear()


def test_runway_submit_saves_provider_job_id_before_polling(client, monkeypatch):
    from app.services import pipeline_service

    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    class FakeProvider:
        name = "runway"

        def create_video(self, prompt: str, settings: dict) -> dict:
            return {
                "job_id": "job-123",
                "request_id": "req-123",
                "status": "queued",
                "response": {"prompt": prompt, "settings": settings},
            }

        def get_status(self, job_id: str) -> dict:
            return {"job_id": job_id, "status": "processing", "raw_status": "RUNNING", "response": {"job_id": job_id}}

        def download_video(self, job_id: str) -> dict:
            raise RuntimeError("not used")

    queued = []

    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    monkeypatch.setattr(pipeline_service, "get_video_provider", lambda: FakeProvider())
    monkeypatch.setattr(pipeline_service, "enqueue_resume_pipeline_task", lambda task_run_id, countdown=None: queued.append((task_run_id, countdown)))

    resume = client.post(
        f"/api/pipeline-runs/{run_id}/resume",
        json={"review_notes": "Approved", "confirm_paid_generation": True},
    )
    assert resume.status_code == 200

    with SessionLocal() as db:
        pipeline_service.process_resume_pipeline(db, run_id)

    detail = client.get(f"/api/pipeline-runs/{run_id}")
    payload = detail.json()
    assert payload["pipeline_run"]["status"] == "running"
    assert payload["pipeline_run"]["current_stage"] == "video_generation_polling"
    assert payload["pipeline_run"]["video_id"] is not None
    assert payload["video"]["provider_job_id"] == "job-123"
    assert payload["video"]["provider_status"] == "RUNNING"
    assert payload["video"]["status"] == "generating"
    assert payload["video"]["requested_duration_seconds"] == 10
    assert any(event["event_type"] == "video.submitted" for event in payload["pipeline_events"])
    assert queued and queued[-1][0] == run_id
    get_settings.cache_clear()


def test_repeated_runway_resume_is_rejected_safely(client, monkeypatch):
    from app.services import pipeline_service

    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    queued = {"count": 0}

    def fake_enqueue(task_run_id, countdown=None):
        queued["count"] += 1

    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    monkeypatch.setattr(pipeline_service, "enqueue_resume_pipeline_task", fake_enqueue)

    first = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"confirm_paid_generation": True})
    second = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"confirm_paid_generation": True})
    assert first.status_code == 200
    assert second.status_code == 409
    assert "no longer eligible for resume" in second.json()["detail"].lower()
    assert queued["count"] == 1
    get_settings.cache_clear()


def test_resume_rejects_run_with_completed_video(client):
    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    first_resume = client.post(f"/api/pipeline-runs/{run_id}/resume")
    assert first_resume.status_code == 200

    second_resume = client.post(f"/api/pipeline-runs/{run_id}/resume")
    assert second_resume.status_code == 409
    assert "Open Video Review" in second_resume.json()["detail"]


def test_runway_long_prompt_override_is_compacted_to_safe_limit(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    response = client.patch(
        f"/api/pipeline-runs/{run_id}/review-config",
        json={"prompt_override": " ".join(["too-long"] * 250)},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["prompt_preview"]) <= 1000
    assert payload["review_preflight"]["prompt_length"]["too_long"] is False
    assert payload["prompt_preview"].startswith("TEXT-FREE VIDEO.")
    get_settings.cache_clear()


def test_celery_task_registered():
    assert "app.workers.jobs.resume_pipeline_task" in celery_app.tasks


def test_failure_after_submit_does_not_revert_run_state(client, monkeypatch):
    from app.services import pipeline_service

    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    class FakeProvider:
        name = "runway"

        def create_video(self, prompt: str, settings: dict) -> dict:
            return {"job_id": "job-1", "request_id": "req-1", "status": "queued", "response": {"created_at": "now"}}

        def get_status(self, job_id: str) -> dict:
            return {
                "job_id": job_id,
                "status": "completed",
                "raw_status": "SUCCEEDED",
                "output_url": "https://example.com/video.mp4",
                "failure": None,
                "response": {},
            }

        def download_video(self, job_id: str) -> dict:
            raise RuntimeError("download failed")

    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    monkeypatch.setattr(pipeline_service, "get_video_provider", lambda: FakeProvider())
    monkeypatch.setattr(pipeline_service, "enqueue_resume_pipeline_task", lambda task_run_id, countdown=None: None)

    resume = client.post(
        f"/api/pipeline-runs/{run_id}/resume",
        json={"review_notes": "Approved", "confirm_paid_generation": True},
    )
    assert resume.status_code == 200

    with SessionLocal() as db:
        pipeline_service.process_resume_pipeline(db, run_id)

    detail = client.get(f"/api/pipeline-runs/{run_id}")
    payload = detail.json()
    assert payload["pipeline_run"]["status"] == "failed"
    assert payload["pipeline_run"]["resumed_at"] is not None
    assert payload["pipeline_run"]["current_stage"] == "asset_upload"
    assert payload["video"]["provider_job_id"] == "job-1"
    assert payload["video"]["status"] == "failed"
    get_settings.cache_clear()


def test_recheck_pipeline_assets_completes_existing_run_without_resubmit(client, monkeypatch):
    from app.models import Asset, PipelineRun, PipelineStage, PipelineStatus, Video, VideoStatus
    from app.services import pipeline_service
    from app.services.pipeline_service import now_utc, recheck_pipeline_assets

    class FakeR2Storage:
        name = "r2"

        def resolve_path(self, storage_key: str) -> str:
            return storage_key

    monkeypatch.setattr(pipeline_service, "get_storage_provider", lambda: FakeR2Storage())

    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    with SessionLocal() as db:
        run = db.get(PipelineRun, run_id)
        video = Video(
            pipeline_run_id=run.id,
            provider="runway",
            provider_job_id="job-existing",
            provider_status="SUCCEEDED",
            provider_response_json={"job_id": "job-existing"},
            prompt_text="Create a 9:16 animated video. End tag: Made by CodeToons AI",
            status=VideoStatus.REJECTED,
            aspect_ratio="9:16",
            requested_duration_seconds=10,
            duration_seconds=10,
            completed_at=now_utc(),
        )
        db.add(video)
        db.flush()
        run.video_id = video.id
        run.status = PipelineStatus.NEEDS_REVIEW
        run.current_stage = PipelineStage.QUALITY_CHECK
        db.add(
            Asset(
                pipeline_run_id=run.id,
                asset_type="video_mp4",
                created_by_stage="video_generation",
                storage_key="videos/existing.mp4",
                public_url="https://cdn.example.com/videos/existing.mp4",
                mime_type="video/mp4",
                size_bytes=1024,
                duration_seconds=10,
                width=720,
                height=1280,
            )
        )
        db.commit()

        updated = recheck_pipeline_assets(db, run_id, "Recheck after duration fix")
        assert updated.status == PipelineStatus.COMPLETED

    detail = client.get(f"/api/pipeline-runs/{run_id}")
    payload = detail.json()
    assert payload["pipeline_run"]["status"] == "completed"
    assert payload["video"]["status"] == "approved"
    assert payload["manual_post_package"] is not None
    latest_quality = payload["quality_checks"][-1]
    assert latest_quality["passed"] is True
    assert latest_quality["checks_json"]["duration_in_range"] is True


def test_recheck_endpoint_returns_completed_run_for_existing_runway_asset(client, monkeypatch):
    from app.models import Asset, PipelineRun, PipelineStage, PipelineStatus, Video, VideoStatus
    from app.services.pipeline_service import now_utc
    from app.services import pipeline_service

    class FakeR2Storage:
        name = "r2"

        def resolve_path(self, storage_key: str) -> str:
            return storage_key

    monkeypatch.setattr(pipeline_service, "get_storage_provider", lambda: FakeR2Storage())

    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    with SessionLocal() as db:
        run = db.get(PipelineRun, run_id)
        video = Video(
            pipeline_run_id=run.id,
            provider="runway",
            provider_job_id="job-existing",
            provider_status="SUCCEEDED",
            provider_response_json={"job_id": "job-existing"},
            prompt_text="Create a 9:16 animated video. End tag: Made by CodeToons AI",
            status=VideoStatus.REJECTED,
            aspect_ratio="9:16",
            requested_duration_seconds=10,
            duration_seconds=10,
            completed_at=now_utc(),
        )
        db.add(video)
        db.flush()
        run.video_id = video.id
        run.status = PipelineStatus.NEEDS_REVIEW
        run.current_stage = PipelineStage.QUALITY_CHECK
        db.add(
            Asset(
                pipeline_run_id=run.id,
                asset_type="video_mp4",
                created_by_stage="video_generation",
                storage_key="videos/existing.mp4",
                public_url="https://cdn.example.com/videos/existing.mp4",
                mime_type="video/mp4",
                size_bytes=1024,
                duration_seconds=10,
                width=720,
                height=1280,
            )
        )
        db.commit()

    response = client.post(f"/api/pipeline-runs/{run_id}/recheck", json={"review_notes": "Re-run checks"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["pipeline_run"]["status"] == "completed"
    assert payload["video"]["status"] == "approved"


def test_manual_package_alternatives_generated(client):
    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Looks good"})
    assert resume.status_code == 200
    payload = resume.json()
    variants = payload["manual_post_package"]["platform_variants_json"]
    assert len(variants["alternative_captions"]) == 3
    assert len(variants["alternative_hooks"]) == 3


def test_sanitize_for_json_handles_datetime_uuid_and_objects():
    class FakeSdkObject:
        def to_dict(self):
            return {"created_at": datetime(2026, 1, 2, tzinfo=UTC), "id": uuid4()}

    payload = {
        "started_at": datetime(2026, 1, 1, 12, 30, tzinfo=UTC),
        "task": FakeSdkObject(),
        "items": [uuid4(), {"finished_at": datetime(2026, 1, 3, tzinfo=UTC)}],
    }
    sanitized = sanitize_for_json(payload)
    assert isinstance(sanitized["started_at"], str)
    assert isinstance(sanitized["task"]["created_at"], str)
    assert isinstance(sanitized["task"]["id"], str)
    assert isinstance(sanitized["items"][0], str)


def test_cancel_run_sets_cancelled_status(client):
    create = client.post("/api/pipeline-runs", json={"topic": "Git branches", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    cancel = client.post(f"/api/pipeline-runs/{run_id}/cancel", json={"review_notes": "Stop this"})
    assert cancel.status_code == 200
    assert cancel.json()["pipeline_run"]["status"] == "cancelled"


def test_account_defaults_can_be_saved(client):
    update = client.patch(
        "/api/settings/account-defaults",
        json={
            "default_style_preset": "office_comedy",
            "target_platforms": ["youtube", "instagram"],
            "default_caption_tone": "dry and witty",
            "default_hashtag_set": ["#python", "#backend"],
            "default_duration_seconds": 22,
            "default_audience_level": "intermediate",
            "default_content_format": "bug explanation",
            "brand_description": "Dry humor coding stories.",
            "preferred_cta": "Save this for your next debugging session.",
            "avoid_phrases": ["guru hack"],
            "emoji_preference": "none",
        },
    )
    assert update.status_code == 200
    payload = update.json()
    assert payload["account_config_json"]["default_style_preset"] == "office_comedy"
    assert payload["account_config_json"]["target_platforms"] == ["youtube", "instagram"]
    assert payload["account_config_json"]["default_caption_tone"] == "dry and witty"

    read = client.get("/api/settings/account-defaults")
    assert read.status_code == 200
    assert read.json()["account_config_json"]["preferred_cta"] == "Save this for your next debugging session."


def test_brand_defaults_apply_to_new_idea_queue_items(client):
    client.patch(
        "/api/settings/account-defaults",
        json={
            "default_style_preset": "whiteboard_character",
            "target_platforms": ["youtube"],
            "default_caption_tone": "clean teacher mode",
            "default_duration_seconds": 20,
            "default_audience_level": "advanced",
            "default_content_format": "quick concept explainer",
        },
    )
    response = client.post("/api/idea-queue", json={"topic": "Memoization"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["style_preset"] == "whiteboard_character"
    assert payload["target_platform"] == "youtube"
    assert payload["input_config_json"]["caption_tone"] == "clean teacher mode"
    assert payload["input_config_json"]["audience_level"] == "advanced"
    assert payload["input_config_json"]["content_format"] == "quick concept explainer"


def test_brand_defaults_apply_to_new_direct_runs(client):
    client.patch(
        "/api/settings/account-defaults",
        json={
            "default_style_preset": "bug_monster",
            "target_platforms": ["tiktok", "instagram"],
            "default_caption_tone": "chaotic but clear",
            "default_duration_seconds": 24,
            "default_audience_level": "intermediate",
            "default_content_format": "bug explanation",
        },
    )
    response = client.post("/api/pipeline-runs", json={"topic": "Race conditions", "auto_mode": False})
    assert response.status_code == 200
    payload = response.json()
    assert payload["pipeline_run"]["style_preset"] == "bug_monster"
    assert payload["pipeline_run"]["input_config_json"]["target_platforms"] == ["tiktok", "instagram"]
    assert payload["pipeline_run"]["input_config_json"]["caption_tone"] == "chaotic but clear"
    assert payload["idea"]["difficulty"] == "intermediate"
    assert payload["idea"]["format"] == "bug explanation"


def test_run_and_idea_overrides_take_priority_over_brand_defaults(client):
    client.patch(
        "/api/settings/account-defaults",
        json={
            "default_style_preset": "office_comedy",
            "target_platforms": ["youtube"],
            "default_caption_tone": "dry and witty",
            "default_duration_seconds": 20,
            "default_audience_level": "advanced",
            "default_content_format": "interview-style tip",
        },
    )

    idea = client.post(
        "/api/idea-queue",
        json={
            "topic": "TCP handshake",
            "style_preset": "clean_3d_cartoon",
            "target_platform": "instagram",
            "caption_tone": "friendly coach",
            "duration_preference_seconds": 18,
            "audience_level": "beginner",
            "content_format": "coding metaphor",
        },
    )
    assert idea.status_code == 200
    idea_payload = idea.json()
    assert idea_payload["style_preset"] == "clean_3d_cartoon"
    assert idea_payload["target_platform"] == "instagram"
    assert idea_payload["input_config_json"]["caption_tone"] == "friendly coach"
    assert idea_payload["input_config_json"]["content_format"] == "coding metaphor"

    run = client.post(
        "/api/pipeline-runs",
        json={
            "topic": "Caching",
            "auto_mode": False,
            "style_preset": "whiteboard_character",
            "target_platforms": ["instagram"],
            "caption_tone": "warm explainer",
            "duration_preference_seconds": 18,
            "audience_level": "beginner",
            "content_format": "quick concept explainer",
        },
    )
    assert run.status_code == 200
    run_payload = run.json()
    assert run_payload["pipeline_run"]["style_preset"] == "whiteboard_character"
    assert run_payload["pipeline_run"]["input_config_json"]["target_platforms"] == ["instagram"]
    assert run_payload["pipeline_run"]["input_config_json"]["caption_tone"] == "warm explainer"
    assert run_payload["idea"]["difficulty"] == "beginner"
    assert run_payload["idea"]["format"] == "quick concept explainer"
    assert run_payload["pipeline_run"]["input_config_json"]["target_platforms"] == ["instagram"]


def test_manual_post_package_uses_brand_tone_hashtags_and_cta_defaults(client):
    client.patch(
        "/api/settings/account-defaults",
        json={
            "default_caption_tone": "dry and witty",
            "default_hashtag_set": ["#python", "#testing"],
            "preferred_cta": "Save this before your next code review.",
            "emoji_preference": "none",
            "target_platforms": ["youtube", "instagram"],
        },
    )
    create = client.post("/api/pipeline-runs", json={"topic": "Pytest fixtures", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Ship it"})
    assert resume.status_code == 200
    payload = resume.json()
    manual_package = payload["manual_post_package"]
    assert "dry and witty" in manual_package["caption"]
    assert "Save this before your next code review." in manual_package["caption"]
    assert manual_package["hashtags_json"] == ["#python", "#testing"]
    assert manual_package["target_platforms_json"] == ["youtube", "instagram"]


def test_mock_provider_respects_default_duration_and_completes(client):
    client.patch(
        "/api/settings/account-defaults",
        json={"default_duration_seconds": 22},
    )
    create = client.post("/api/pipeline-runs", json={"topic": "Semaphore", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "duration smoke"})
    assert resume.status_code == 200
    payload = resume.json()
    assert payload["pipeline_run"]["status"] == "completed"
    assert payload["video"]["requested_duration_seconds"] == 22
    assert payload["video"]["duration_seconds"] == 22
    assert payload["manual_post_package"] is not None


def test_idea_queue_creation(client):
    response = client.post(
        "/api/idea-queue",
        json={
            "topic": "Event loop",
            "style_preset": "office_comedy",
            "target_platform": "youtube",
            "priority": "high",
            "status": "ready",
            "notes": "Great for a queue of explainer ideas",
            "planned_date": "2026-07-02T09:00:00",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["topic"] == "Event loop"
    assert payload["style_preset"] == "office_comedy"
    assert payload["status"] == "ready"


def test_idea_queue_editing(client):
    create = client.post("/api/idea-queue", json={"topic": "Caching", "style_preset": "clean_3d_cartoon"})
    item_id = create.json()["id"]
    update = client.patch(
        f"/api/idea-queue/{item_id}",
        json={"notes": "Shift this toward Instagram", "target_platform": "instagram", "status": "ready"},
    )
    assert update.status_code == 200
    payload = update.json()
    assert payload["notes"] == "Shift this toward Instagram"
    assert payload["target_platform"] == "instagram"
    assert payload["status"] == "ready"


def test_idea_queue_archiving(client):
    create = client.post("/api/idea-queue", json={"topic": "Webhooks"})
    item_id = create.json()["id"]
    archive = client.post(f"/api/idea-queue/{item_id}/archive")
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"


def test_generate_run_from_idea_queue_item(client):
    create = client.post(
        "/api/idea-queue",
        json={"topic": "JWT", "style_preset": "whiteboard_character", "target_platform": "tiktok", "priority": "high", "status": "ready"},
    )
    item_id = create.json()["id"]
    generate = client.post(f"/api/idea-queue/{item_id}/generate-run")
    assert generate.status_code == 200
    payload = generate.json()
    assert payload["idea_queue_item"]["status"] == "generated"
    assert payload["pipeline_run"]["topic"] == "JWT"
    assert payload["pipeline_run"]["style_preset"] == "whiteboard_character"
    assert payload["pipeline_run"]["status"] == "awaiting_review"


def test_batch_update_idea_queue_items(client):
    first = client.post("/api/idea-queue", json={"topic": "Caching", "status": "draft"})
    second = client.post("/api/idea-queue", json={"topic": "Queues", "status": "draft"})
    payload = {
        "item_ids": [first.json()["id"], second.json()["id"]],
        "status": "ready",
        "target_platform": "youtube",
        "style_preset": "office_comedy",
        "priority": "high",
        "planned_date": "2026-07-20T09:00:00",
    }
    response = client.post("/api/idea-queue/batch-update", json=payload)
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert all(item["status"] == "ready" for item in items)
    assert all(item["target_platform"] == "youtube" for item in items)
    assert all(item["style_preset"] == "office_comedy" for item in items)
    assert all(item["priority"] == "high" for item in items)
    assert all(item["planned_date"] == "2026-07-20T09:00:00" for item in items)
    assert all(item["input_config_json"]["target_platforms"] == ["youtube"] for item in items)


def test_batch_archive_selected_ideas(client):
    first = client.post("/api/idea-queue", json={"topic": "Retries"})
    second = client.post("/api/idea-queue", json={"topic": "Workers"})
    response = client.post(
        "/api/idea-queue/batch-update",
        json={"item_ids": [first.json()["id"], second.json()["id"]], "archive_selected": True},
    )
    assert response.status_code == 200
    assert all(item["status"] == "archived" for item in response.json())


def test_idea_queue_scoring_does_not_generate_video(client):
    first = client.post("/api/idea-queue", json={"topic": "Circuit breakers", "priority": "high"})
    second = client.post("/api/idea-queue", json={"topic": "Cron jobs", "target_platform": "youtube"})
    response = client.post("/api/idea-queue/score", json={"item_ids": [first.json()["id"], second.json()["id"]]})
    assert response.status_code == 200
    scores = response.json()
    assert len(scores) == 2
    assert all("overall_score" in item for item in scores)
    runs = client.get("/api/pipeline-runs").json()
    assert all(run["topic"] not in {"Circuit breakers", "Cron jobs"} for run in runs)


def test_idea_queue_list_includes_scores(client):
    client.post("/api/idea-queue", json={"topic": "Memory leaks", "priority": "high"})
    response = client.get("/api/idea-queue")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["idea_score"] is not None
    assert "overall_score" in payload[0]["idea_score"]


def test_no_bulk_runway_generation_path_exists(client):
    response = client.post("/api/idea-queue/batch-update", json={"item_ids": ["fake"], "generate_runs": True})
    assert response.status_code in {404, 422}
    missing = client.post("/api/idea-queue/batch-generate", json={"item_ids": ["fake"]})
    assert missing.status_code in {404, 405}


def test_asset_library_api_returns_generated_completed_assets(client):
    create = client.post(
        "/api/pipeline-runs",
        json={"topic": "CORS", "auto_mode": False, "style_preset": "office_comedy"},
    )
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Approved for archive"})
    assert resume.status_code == 200

    response = client.get("/api/asset-library")
    assert response.status_code == 200
    items = response.json()
    item = next(entry for entry in items if entry["run_id"] == run_id)
    assert item["provider"] == "mock"
    assert item["run_status"] == "completed"
    assert item["video_status"] == "approved"
    assert item["style_preset"] == "office_comedy"
    assert item["video_url"]


def test_asset_library_filters_by_provider_status_style_and_platform(client):
    idea = client.post(
        "/api/idea-queue",
        json={
            "topic": "Queues",
            "style_preset": "bug_monster",
            "target_platform": "instagram",
            "priority": "high",
            "status": "ready",
        },
    )
    item_id = idea.json()["id"]
    generate = client.post(f"/api/idea-queue/{item_id}/generate-run")
    run_id = generate.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Archive this"})
    assert resume.status_code == 200

    response = client.get(
        "/api/asset-library",
        params={
            "provider": "mock",
            "status": "approved",
            "style_preset": "bug_monster",
            "platform": "instagram",
        },
    )
    assert response.status_code == 200
    items = response.json()
    assert any(entry["run_id"] == run_id for entry in items)
    assert all(entry["provider"] == "mock" for entry in items)
    assert all(entry["style_preset"] == "bug_monster" for entry in items)
    assert all(entry["target_platform"] == "instagram" for entry in items)


def test_asset_library_detail_includes_prompt_captions_urls_and_quality(client):
    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Ready"})
    assert resume.status_code == 200

    response = client.get(f"/api/asset-library/{run_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["video"]["prompt_text"]
    assert payload["video_asset"]["public_url"]
    assert payload["video_asset"]["mime_type"] == "video/mp4"
    assert payload["thumbnail_asset"]["public_url"]
    assert payload["quality_check"]["checks_json"]["aspect_ratio_9_16"] is True
    assert payload["manual_post_package"]["caption"]
    assert payload["manual_post_package"]["platform_variants_json"]["instagram"]["caption"]


def test_asset_library_detail_includes_linked_idea_queue_metadata(client):
    idea = client.post(
        "/api/idea-queue",
        json={
            "topic": "Rate limiting",
            "style_preset": "whiteboard_character",
            "target_platform": "youtube",
            "priority": "normal",
            "status": "ready",
        },
    )
    item_id = idea.json()["id"]
    generate = client.post(f"/api/idea-queue/{item_id}/generate-run")
    run_id = generate.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Ship it"})
    assert resume.status_code == 200

    response = client.get(f"/api/asset-library/{run_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["idea_queue_item"]["id"] == item_id
    assert payload["idea_queue_item"]["target_platform"] == "youtube"
    assert payload["pipeline_run"]["id"] == run_id


def test_asset_export_pack_api_returns_manual_posting_bundle(client):
    create = client.post("/api/pipeline-runs", json={"topic": "Export Pack", "auto_mode": False, "style_preset": "office_comedy"})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Ready to export"})
    assert resume.status_code == 200

    response = client.get(f"/api/asset-library/{run_id}/export-pack")
    assert response.status_code == 200
    payload = response.json()
    assert payload["video_public_url"]
    assert payload["thumbnail_public_url"]
    assert payload["caption"]
    assert payload["hashtags"]
    assert payload["final_prompt_used"]
    assert payload["quality_score"] == 0.92
    assert payload["platform_sections"]["tiktok"]["recommended_caption"]
    assert payload["platform_sections"]["instagram_reels"]["recommended_caption"]
    assert payload["platform_sections"]["youtube_shorts"]["title"]
    assert payload["alternative_captions"]
    assert payload["alternative_hooks"]


def test_manual_post_package_defaults_final_asset_to_source_video(client):
    run_id, payload = _create_completed_run(client)

    manual_package = payload["manual_post_package"]
    final_selection = payload["final_asset_selection"]
    source_asset = next(asset for asset in payload["assets"] if asset["asset_type"] == "video_mp4")

    assert manual_package["final_asset_source"] == "source_video"
    assert manual_package["final_asset_id"] == source_asset["id"]
    assert final_selection["source"] == "source_video"
    assert final_selection["asset"]["id"] == source_asset["id"]
    assert final_selection["original_video_asset"]["id"] == source_asset["id"]

    export_pack = client.get(f"/api/asset-library/{run_id}/export-pack")
    assert export_pack.status_code == 200
    assert export_pack.json()["video_public_url"] == source_asset["public_url"]


def test_final_asset_selection_uses_approved_same_run_narration_render(client, monkeypatch):
    run_id, payload = _create_approved_narration_render(client, monkeypatch)
    render = payload["latest_narration_render"]

    response = client.post(
        f"/api/pipeline-runs/{run_id}/final-asset/select",
        json={"source": "narration_render", "narration_render_id": render["id"], "confirm_change_after_posting": False},
    )
    assert response.status_code == 200
    selected = response.json()
    final_selection = selected["final_asset_selection"]

    assert final_selection["source"] == "narration_render"
    assert final_selection["narration_render_id"] == render["id"]
    assert final_selection["asset"]["id"] == render["rendered_video_asset_id"]
    assert final_selection["narration_transcript"] == render["full_spoken_text"]
    assert final_selection["caption_cues"] == render["caption_cues_json"]
    assert final_selection["ai_voice_disclosure"] == render["ai_voice_disclosure"]

    library_detail = client.get(f"/api/asset-library/{run_id}")
    assert library_detail.status_code == 200
    assert library_detail.json()["final_video_asset"]["id"] == render["rendered_video_asset_id"]

    export_pack = client.get(f"/api/asset-library/{run_id}/export-pack")
    assert export_pack.status_code == 200
    export_payload = export_pack.json()
    assert export_payload["final_asset_source"] == "narration_render"
    assert export_payload["final_narration_render_id"] == render["id"]
    assert export_payload["video_public_url"] == render["rendered_video_asset"]["public_url"]
    assert export_payload["narration_transcript"] == render["full_spoken_text"]
    assert export_payload["caption_cues"] == render["caption_cues_json"]


def test_final_asset_selection_is_idempotent_for_same_asset(client, monkeypatch):
    run_id, payload = _create_approved_narration_render(client, monkeypatch)
    render = payload["latest_narration_render"]
    first = client.post(
        f"/api/pipeline-runs/{run_id}/final-asset/select",
        json={"source": "narration_render", "narration_render_id": render["id"], "confirm_change_after_posting": False},
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/pipeline-runs/{run_id}/final-asset/select",
        json={"source": "narration_render", "narration_render_id": render["id"], "confirm_change_after_posting": False},
    )
    assert second.status_code == 200
    assert first.json()["final_asset_selection"]["selection_revision"] == second.json()["final_asset_selection"]["selection_revision"]

    events = [event for event in second.json()["pipeline_events"] if event["event_type"] == "final_asset.selected"]
    assert len(events) == 1


def test_final_asset_selection_requires_confirmation_after_posting(client, monkeypatch):
    run_id, payload = _create_approved_narration_render(client, monkeypatch)
    render = payload["latest_narration_render"]

    posted = client.patch(
        f"/api/asset-library/{run_id}/manual-posting",
        json={
            "manual_posting_status": "posted_tiktok",
            "tiktok_post_url": "https://tiktok.com/@codextest/video/123",
        },
    )
    assert posted.status_code == 200

    blocked = client.post(
        f"/api/pipeline-runs/{run_id}/final-asset/select",
        json={"source": "narration_render", "narration_render_id": render["id"], "confirm_change_after_posting": False},
    )
    assert blocked.status_code == 409
    assert "confirm_change_after_posting=true" in blocked.json()["detail"]

    confirmed = client.post(
        f"/api/pipeline-runs/{run_id}/final-asset/select",
        json={"source": "narration_render", "narration_render_id": render["id"], "confirm_change_after_posting": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["manual_post_package"]["manual_posting_status"] == "posted_tiktok"


def test_final_asset_selection_rejects_non_approved_render(client, monkeypatch):
    from app.models import NarrationRender, NarrationRenderStatus

    run_id, payload = _create_approved_narration_render(client, monkeypatch)
    render_id = payload["latest_narration_render"]["id"]
    with SessionLocal() as db:
        render = db.get(NarrationRender, render_id)
        render.status = NarrationRenderStatus.NEEDS_REVISION
        db.add(render)
        db.commit()

    response = client.post(
        f"/api/pipeline-runs/{run_id}/final-asset/select",
        json={"source": "narration_render", "narration_render_id": render_id, "confirm_change_after_posting": False},
    )
    assert response.status_code == 409
    assert "not approved" in response.json()["detail"].lower()


def test_final_asset_selection_can_revert_to_original_source(client, monkeypatch):
    run_id, payload = _create_approved_narration_render(client, monkeypatch)
    render = payload["latest_narration_render"]

    select_narrated = client.post(
        f"/api/pipeline-runs/{run_id}/final-asset/select",
        json={"source": "narration_render", "narration_render_id": render["id"], "confirm_change_after_posting": False},
    )
    assert select_narrated.status_code == 200

    revert = client.post(
        f"/api/pipeline-runs/{run_id}/final-asset/select",
        json={"source": "source_video", "confirm_change_after_posting": False},
    )
    assert revert.status_code == 200
    final_selection = revert.json()["final_asset_selection"]
    assert final_selection["source"] == "source_video"
    assert final_selection["narration_render_id"] is None
    assert final_selection["narration_transcript"] is None
    assert final_selection["caption_cues"] == []


def test_runway_quality_checklist_uses_provider_aware_branding_item(client, monkeypatch):
    from app.models import Asset, ManualPostPackage, PipelineRun, PipelineStage, PipelineStatus, QualityCheck, Video, VideoStatus
    from app.services import pipeline_service
    from app.services.pipeline_service import create_manual_post_package, now_utc, run_quality_check

    class FakeR2Storage:
        name = "r2"

        def resolve_path(self, storage_key: str) -> str:
            return storage_key

    monkeypatch.setattr(pipeline_service, "get_storage_provider", lambda: FakeR2Storage())

    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    with SessionLocal() as db:
        run = db.get(PipelineRun, run_id)
        video = Video(
            pipeline_run_id=run.id,
            provider="runway",
            provider_job_id="job-runway-checklist",
            provider_status="SUCCEEDED",
            provider_response_json={"job_id": "job-runway-checklist"},
            prompt_text="TEXT-FREE VIDEO. Do not render any words, letters, numbers, labels, captions, signs, logos, UI text, code, or subtitles. A clean 3D cartoon short with a bouncer and matching pass. TEXT-FREE VIDEO. Do not render any words, letters, numbers, labels, captions, signs, logos, UI text, code, or subtitles.",
            status=VideoStatus.COMPLETED,
            aspect_ratio="9:16",
            requested_duration_seconds=10,
            duration_seconds=10,
            completed_at=now_utc(),
        )
        db.add(video)
        db.flush()
        run.video_id = video.id
        run.status = PipelineStatus.RUNNING
        run.current_stage = PipelineStage.QUALITY_CHECK
        db.add(
            Asset(
                pipeline_run_id=run.id,
                asset_type="video_mp4",
                created_by_stage="video_generation",
                storage_key="videos/runway-quality.mp4",
                public_url="https://cdn.example.com/videos/runway-quality.mp4",
                mime_type="video/mp4",
                size_bytes=1024,
                duration_seconds=10,
                width=720,
                height=1280,
            )
        )
        db.commit()

        run_quality_check(db, run)
        db.commit()
        create_manual_post_package(db, run)
        db.commit()

        refreshed_run = db.get(PipelineRun, run_id)
        quality = db.query(QualityCheck).filter(QualityCheck.pipeline_run_id == run_id).order_by(QualityCheck.created_at.desc()).first()
        manual_package = db.get(ManualPostPackage, refreshed_run.manual_post_package_id)

        assert "end_tag_present" not in quality.checks_json
        assert quality.checks_json["branding_handled_separately"] is True
        assert "Confirm the thumbnail and opening frame look clean" in manual_package.checklist_json
        assert "Confirm end tag visibility" not in manual_package.checklist_json


def test_runway_export_pack_instructions_omit_end_tag_language(client, monkeypatch):
    from app.models import Asset, PipelineRun, PipelineStage, PipelineStatus, Video, VideoStatus
    from app.services import pipeline_service
    from app.services.asset_library_service import get_asset_export_pack
    from app.services.pipeline_service import create_manual_post_package, now_utc, run_quality_check

    class FakeR2Storage:
        name = "r2"

        def resolve_path(self, storage_key: str) -> str:
            return storage_key

    monkeypatch.setattr(pipeline_service, "get_storage_provider", lambda: FakeR2Storage())

    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    with SessionLocal() as db:
        run = db.get(PipelineRun, run_id)
        video = Video(
            pipeline_run_id=run.id,
            provider="runway",
            provider_job_id="job-runway-export",
            provider_status="SUCCEEDED",
            provider_response_json={"job_id": "job-runway-export"},
            prompt_text="TEXT-FREE VIDEO. Do not render any words, letters, numbers, labels, captions, signs, logos, UI text, code, or subtitles. A robot bouncer metaphor short. TEXT-FREE VIDEO. Do not render any words, letters, numbers, labels, captions, signs, logos, UI text, code, or subtitles.",
            status=VideoStatus.COMPLETED,
            aspect_ratio="9:16",
            requested_duration_seconds=10,
            duration_seconds=10,
            completed_at=now_utc(),
        )
        db.add(video)
        db.flush()
        run.video_id = video.id
        run.status = PipelineStatus.RUNNING
        run.current_stage = PipelineStage.QUALITY_CHECK
        db.add(
            Asset(
                pipeline_run_id=run.id,
                asset_type="video_mp4",
                created_by_stage="video_generation",
                storage_key="videos/runway-export.mp4",
                public_url="https://cdn.example.com/videos/runway-export.mp4",
                mime_type="video/mp4",
                size_bytes=1024,
                duration_seconds=10,
                width=720,
                height=1280,
            )
        )
        db.commit()

        run_quality_check(db, run)
        db.commit()
        create_manual_post_package(db, run)
        db.commit()

        export_pack = get_asset_export_pack(db, run_id)
        assert "end_tag_present" not in export_pack["quality_checklist"]
        assert export_pack["quality_checklist"]["branding_handled_separately"] is True
        assert all("end tag" not in step.lower() for step in export_pack["platform_sections"]["youtube_shorts"]["checklist"])
        assert any("opening frame" in step.lower() for step in export_pack["platform_sections"]["youtube_shorts"]["checklist"])


def test_mock_export_pack_instructions_keep_end_tag_language(client):
    create = client.post("/api/pipeline-runs", json={"topic": "Mock Export Pack", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Ready to export"})
    assert resume.status_code == 200

    response = client.get(f"/api/asset-library/{run_id}/export-pack")
    assert response.status_code == 200
    payload = response.json()
    assert payload["quality_checklist"]["end_tag_present"] is True
    assert "branding_handled_separately" not in payload["quality_checklist"]
    assert any("end tag" in step.lower() for step in payload["platform_sections"]["youtube_shorts"]["checklist"])


def test_manual_posting_status_update_and_url_storage(client):
    create = client.post("/api/pipeline-runs", json={"topic": "Manual Posting", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Ship it"})
    assert resume.status_code == 200

    update = client.patch(
        f"/api/asset-library/{run_id}/manual-posting",
        json={
            "manual_posting_status": "posted_multiple",
            "tiktok_post_url": "https://tiktok.com/@codetoons/video/123",
            "instagram_post_url": "https://instagram.com/reel/456",
            "youtube_post_url": "https://youtube.com/shorts/789",
        },
    )
    assert update.status_code == 200
    payload = update.json()
    assert payload["manual_posting_status"] == "posted_multiple"
    assert payload["manual_post_urls"]["tiktok"] == "https://tiktok.com/@codetoons/video/123"
    assert payload["manual_post_urls"]["instagram"] == "https://instagram.com/reel/456"
    assert payload["manual_post_urls"]["youtube"] == "https://youtube.com/shorts/789"

    detail = client.get(f"/api/asset-library/{run_id}")
    assert detail.status_code == 200
    manual_package = detail.json()["manual_post_package"]
    assert manual_package["manual_posting_status"] == "posted_multiple"
    assert manual_package["tiktok_post_url"] == "https://tiktok.com/@codetoons/video/123"


def test_manual_posting_status_derives_from_single_url_when_not_explicit(client):
    create = client.post("/api/pipeline-runs", json={"topic": "TikTok Only", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Ready"})
    assert resume.status_code == 200

    update = client.patch(
        f"/api/asset-library/{run_id}/manual-posting",
        json={"tiktok_post_url": "https://tiktok.com/@codetoons/video/abc"},
    )
    assert update.status_code == 200
    assert update.json()["manual_posting_status"] == "posted_tiktok"


def test_asset_library_filters_by_manual_posting_status(client):
    create = client.post("/api/pipeline-runs", json={"topic": "Posted Filter", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Archive"})
    assert resume.status_code == 200

    update = client.patch(
        f"/api/asset-library/{run_id}/manual-posting",
        json={"manual_posting_status": "posted_youtube", "youtube_post_url": "https://youtube.com/shorts/filter"},
    )
    assert update.status_code == 200

    response = client.get("/api/asset-library", params={"manual_posting_status": "posted_youtube"})
    assert response.status_code == 200
    items = response.json()
    assert any(item["run_id"] == run_id for item in items)
    assert all(item["manual_posting_status"] == "posted_youtube" for item in items)


def _enable_mock_narration(monkeypatch):
    monkeypatch.setenv("NARRATION_ENABLED", "true")
    monkeypatch.setenv("NARRATION_WRITER_PROVIDER", "mock")
    monkeypatch.setenv("NARRATION_SPEECH_PROVIDER", "mock")
    get_settings.cache_clear()


def _create_completed_run(client):
    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Looks good"})
    assert resume.status_code == 200
    return run_id, resume.json()


def _create_approved_narration_render(client, monkeypatch):
    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    draft = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    assert draft.status_code == 200
    story_review = client.post(
        f"/api/pipeline-runs/{run_id}/story-adherence/human-review",
        json={"decision": "approve", "notes": "Approved for final asset selection."},
    )
    assert story_review.status_code == 200
    render = client.post(
        f"/api/pipeline-runs/{run_id}/narration/render",
        json={"confirm_paid_narration": True, "voice": "alloy"},
    )
    assert render.status_code == 200
    render_payload = render.json()
    narration_render = render_payload["latest_narration_render"]
    review = client.post(
        f"/api/pipeline-runs/{run_id}/narration/human-review",
        json={"narration_render_id": narration_render["id"], "decision": "approve", "notes": "Approved narration render."},
    )
    assert review.status_code == 200
    return run_id, review.json()


def test_narration_draft_creation_uses_mock_writer_and_persists_detail(client, monkeypatch):
    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)

    response = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    assert response.status_code == 200
    payload = response.json()
    draft = payload["narration_draft"]
    assert draft is not None
    assert draft["status"] == "ready"
    assert draft["has_valid_content"] is True
    assert draft["full_spoken_text"]
    assert payload["latest_narration_render"] is None


def test_narration_draft_duplicate_create_returns_existing_draft(client, monkeypatch):
    from app.models import NarrationDraft

    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)

    first = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    second = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["narration_draft"]["id"] == second.json()["narration_draft"]["id"]

    with SessionLocal() as db:
        assert db.query(NarrationDraft).filter(NarrationDraft.pipeline_run_id == run_id).count() == 1


def test_narration_draft_patch_updates_manual_text(client, monkeypatch):
    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    created = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False}).json()
    segments = created["narration_draft"]["script_json"]["segments"]
    segments[0]["spoken_text"] = "Updated spoken text."
    segments[0]["caption_text"] = "Updated spoken text."
    patch = client.patch(
        f"/api/pipeline-runs/{run_id}/narration/draft",
        json={
            "segments": segments,
            "full_spoken_text": "Updated spoken text. The fix lands. The solved result holds at the end.",
        },
    )
    assert patch.status_code == 200
    payload = patch.json()
    assert payload["narration_draft"]["manually_modified"] is True
    assert payload["narration_draft"]["script_json"]["segments"][0]["caption_text"] == "Updated spoken text."


def test_narration_render_requires_paid_confirmation(client, monkeypatch):
    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})

    response = client.post(f"/api/pipeline-runs/{run_id}/narration/render", json={"confirm_paid_narration": False})
    assert response.status_code == 409
    assert "confirm_paid_narration=true" in response.json()["detail"]


def test_narration_render_requires_unapproved_story_confirmation(client, monkeypatch):
    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})

    response = client.post(
        f"/api/pipeline-runs/{run_id}/narration/render",
        json={"confirm_paid_narration": True, "confirm_unapproved_story": False},
    )
    assert response.status_code == 409
    assert "confirm_unapproved_story=true" in response.json()["detail"]


def test_narration_render_creates_derived_assets_without_changing_run_status(client, monkeypatch):
    _enable_mock_narration(monkeypatch)
    run_id, resumed = _create_completed_run(client)
    original_story_status = resumed["story_adherence_review"]["review_status"]
    original_quality_score = resumed["quality_checks"][-1]["score"]
    client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    client.post(
        f"/api/pipeline-runs/{run_id}/story-adherence/human-review",
        json={"decision": "approve", "notes": "Approved for narration."},
    )

    response = client.post(
        f"/api/pipeline-runs/{run_id}/narration/render",
        json={"confirm_paid_narration": True, "voice": "alloy"},
    )
    assert response.status_code == 200
    payload = response.json()
    render = payload["latest_narration_render"]
    assert render is not None
    assert render["status"] == "pending_review"
    assert render["voice_is_ai_generated"] is True
    assert render["audio_asset"] is not None
    assert render["caption_asset"] is not None
    assert render["rendered_video_asset"] is not None
    assert payload["pipeline_run"]["status"] == "completed"
    assert payload["story_adherence_review"]["review_status"] == original_story_status
    assert payload["quality_checks"][-1]["score"] == original_quality_score
    asset_types = {asset["asset_type"] for asset in payload["assets"]}
    assert "video_mp4" in asset_types
    assert "narration_audio" in asset_types
    assert "narration_captions" in asset_types
    assert "narrated_video_mp4" in asset_types


def test_narration_timing_plan_uses_actual_audio_window_for_shorter_audio():
    from app.services import narration_service

    window = narration_service._narration_window_plan(10.0, 7.42)
    assert window["lead_in_seconds"] == 0.4
    assert window["speech_window_start_seconds"] == 0.4
    assert window["speech_window_end_seconds"] == 7.82
    assert window["ending_silence_seconds"] == 2.18
    assert window["available_speech_window_seconds"] == 9.2


def test_narration_caption_cues_follow_actual_narration_window():
    from app.models import NarrationRender
    from app.services import narration_service

    render = NarrationRender(
        source_duration_seconds=10.0,
        script_json={
            "segments": [
                {"spoken_text": "Repeated failures stop the build.", "caption_text": "Repeated failures stop the build."},
                {"spoken_text": "The AI spots the broken gear.", "caption_text": "The AI spots the broken gear."},
                {"spoken_text": "Replace it, and the machine runs smoothly again.", "caption_text": "Replace it, and the machine runs smoothly again."},
            ]
        },
    )

    cues, metadata = narration_service._derive_caption_cues(render, 7.42)
    assert cues[0]["start_seconds"] == 0.4
    assert cues[-1]["end_seconds"] == 7.82
    assert metadata["speech_window_end_seconds"] == 7.82
    assert metadata["ending_silence_seconds"] == 2.18
    assert metadata["available_speech_window_seconds"] == 9.2


def test_failed_narration_regeneration_keeps_previous_draft_usable(client, monkeypatch):
    from app.services import narration_service

    class FailingWriter:
        name = "mock"
        model = "mock-writer"

        def write(self, payload):
            raise RuntimeError("Writer failed")

    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    created = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    original = created.json()["narration_draft"]
    monkeypatch.setattr(narration_service, "get_narration_writer_provider", lambda: FailingWriter())

    regenerated = client.post(f"/api/pipeline-runs/{run_id}/narration/draft/regenerate", json={"confirm_paid_draft": False})
    assert regenerated.status_code == 200
    draft = regenerated.json()["narration_draft"]
    assert draft["status"] == "ready"
    assert draft["has_valid_content"] is True
    assert draft["failure_reason"] == "Writer failed"
    assert draft["generation_revision"] == original["generation_revision"] + 1
    assert draft["full_spoken_text"] == original["full_spoken_text"]


def test_narration_recompose_reuses_existing_audio_without_new_tts(client, monkeypatch):
    from app.models import NarrationRender
    from app.services import narration_service

    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    client.post(
        f"/api/pipeline-runs/{run_id}/story-adherence/human-review",
        json={"decision": "approve", "notes": "Approved for narration."},
    )
    rendered = client.post(
        f"/api/pipeline-runs/{run_id}/narration/render",
        json={"confirm_paid_narration": True},
    ).json()
    render_id = rendered["latest_narration_render"]["id"]
    rendered_asset_id = rendered["latest_narration_render"]["rendered_video_asset_id"]
    original_caption_asset_id = rendered["latest_narration_render"]["caption_asset_id"]
    speech_calls = {"count": 0}

    class ShouldNotBeCalledSpeechProvider:
        name = "mock"
        model = "mock-speech"

        def synthesize(self, *, text, voice, destination):
            speech_calls["count"] += 1
            raise AssertionError("Recompose should not call TTS when audio already exists.")

    def inline_recompose(render_id):
        with SessionLocal() as db:
            narration_service.process_narration_render(db, render_id, mode="recompose", task_id="inline-recompose")

    monkeypatch.setattr(narration_service, "get_speech_provider", lambda: ShouldNotBeCalledSpeechProvider())
    monkeypatch.setattr(narration_service, "enqueue_narration_recompose_task", inline_recompose)

    recomposed = client.post(f"/api/pipeline-runs/{run_id}/narration/renders/{render_id}/recompose")
    assert recomposed.status_code == 200
    payload = recomposed.json()
    assert payload["latest_narration_render"]["rendered_video_asset_id"] != rendered_asset_id
    assert payload["latest_narration_render"]["caption_asset_id"] != original_caption_asset_id
    assert payload["latest_narration_render"]["audio_asset_id"] == rendered["latest_narration_render"]["audio_asset_id"]
    assert speech_calls["count"] == 0
    with SessionLocal() as db:
        render = db.get(NarrationRender, render_id)
        assert render is not None
        assert render.status == "pending_review"


def test_narration_compose_uses_h264_aac_and_preserves_source_duration(tmp_path, monkeypatch):
    from app.services import narration_service

    captured = {}

    def fake_run(command, check, stdout, stderr, capture_output=False, text=False):
        captured["command"] = command
        destination = Path(command[-1])
        destination.write_bytes(b"video")
        class Result:
            stdout = ""
        return Result()

    monkeypatch.setattr(narration_service.subprocess, "run", fake_run)
    narration_service._compose_video(
        tmp_path / "source.mp4",
        tmp_path / "audio.mp3",
        tmp_path / "captions.ass",
        tmp_path / "out.mp4",
        atempo=1.0,
        lead_in_seconds=0.4,
        source_duration_seconds=10.0,
    )

    command = captured["command"]
    assert "-shortest" not in command
    assert "libx264" in command
    assert "aac" in command
    assert "yuv420p" in command
    assert "+faststart" in command
    assert any("adelay=400:all=1" in item for item in command)
    assert any("apad=pad_dur=10.00" in item for item in command)
    assert any("atrim=duration=10.00" in item for item in command)


def test_narration_output_validation_requires_full_duration_and_caption_alignment():
    from app.services import narration_service

    with_caption_overrun = {
        "format_duration_seconds": 10.0,
        "streams": [
            {"codec_type": "video", "width": 720, "height": 1280, "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }
    try:
        narration_service._validate_render_output(
            with_caption_overrun,
            source_duration_seconds=10.0,
            expected_width=720,
            expected_height=1280,
            caption_cues=[{"start_seconds": 0.4, "end_seconds": 9.6}],
            narration_end_seconds=7.82,
        )
        assert False, "Expected caption alignment validation to fail."
    except RuntimeError as exc:
        assert "materially exceed" in str(exc)

    narration_service._validate_render_output(
        {
            "format_duration_seconds": 10.0,
            "streams": [
                {"codec_type": "video", "width": 720, "height": 1280, "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        },
        source_duration_seconds=10.0,
        expected_width=720,
        expected_height=1280,
        caption_cues=[{"start_seconds": 0.4, "end_seconds": 7.82}],
        narration_end_seconds=7.82,
    )


def test_narration_draft_normalizes_writer_timestamps_that_end_at_source_duration(client, monkeypatch):
    from app.services import narration_service

    class AdvisoryTimingWriter:
        name = "mock"
        model = "timing-writer"

        def write(self, payload):
            return {
                "segments": [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 4.0,
                        "spoken_text": "Bug first breaks the machine.",
                        "caption_text": "Bug first breaks the machine.",
                    },
                    {
                        "start_seconds": 4.0,
                        "end_seconds": 10.0,
                        "spoken_text": "The AI spots the fault and fixes it.",
                        "caption_text": "The AI spots the fault and fixes it.",
                    },
                ],
                "full_spoken_text": "Bug first breaks the machine. The AI spots the fault and fixes it.",
                "estimated_word_count": 12,
                "usage": {"input_tokens": 11, "output_tokens": 13, "total_tokens": 24},
                "cost_estimate": 0.12,
                "provider_request_id": "req-equal",
            }

    response = AdvisoryTimingWriter().write({})
    segments, _text, _count = narration_service._normalize_segments(response, source_duration_seconds=10.0)
    assert segments[0]["start_seconds"] == 0.4
    assert segments[-1]["end_seconds"] == 9.6
    assert segments[-1]["end_seconds"] < 10.0


def test_narration_draft_normalizes_writer_timestamps_beyond_source_duration_deterministically(client, monkeypatch):
    from app.services import narration_service

    class BeyondTimingWriter:
        name = "mock"
        model = "timing-writer"

        def write(self, payload):
            return {
                "segments": [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 7.5,
                        "spoken_text": "A broken robot arm jams the coding line.",
                        "caption_text": "A broken robot arm jams the coding line.",
                    },
                    {
                        "start_seconds": 7.5,
                        "end_seconds": 12.5,
                        "spoken_text": "The AI swaps one bad gear and the robot works again.",
                        "caption_text": "The AI swaps one bad gear and the robot works again.",
                    },
                ],
                "full_spoken_text": "A broken robot arm jams the coding line. The AI swaps one bad gear and the robot works again.",
                "estimated_word_count": 18,
                "usage": {"input_tokens": 9, "output_tokens": 15, "total_tokens": 24},
                "cost_estimate": 0.08,
                "provider_request_id": "req-beyond",
            }

    response = BeyondTimingWriter().write({})
    first_segments, _text, _count = narration_service._normalize_segments(response, source_duration_seconds=10.0)
    second_segments, _text, _count = narration_service._normalize_segments(response, source_duration_seconds=10.0)
    assert first_segments == second_segments
    assert first_segments[0]["start_seconds"] == 0.4
    assert first_segments[1]["end_seconds"] == 9.6
    assert first_segments[1]["end_seconds"] < 10.0


def test_narration_draft_rejects_over_word_limit_after_normalization(client, monkeypatch):
    from app.services import narration_service

    class LongWriter:
        name = "mock"
        model = "long-writer"

        def write(self, payload):
            text = (
                "One developer keeps checking every broken panel while the AI helper points to the bad wire, "
                "explains the bug, and confirms the machine is fully fixed at the end."
            )
            return {
                "segments": [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 3.0,
                        "spoken_text": text,
                        "caption_text": text,
                    }
                ],
                "full_spoken_text": text,
                "estimated_word_count": len(text.split()),
                "usage": {"input_tokens": 20, "output_tokens": 30, "total_tokens": 50},
                "cost_estimate": 0.14,
                "provider_request_id": "req-long",
            }

    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    monkeypatch.setattr(narration_service, "get_narration_writer_provider", lambda: LongWriter())

    response = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    assert response.status_code == 200
    draft = response.json()["narration_draft"]
    assert draft["status"] == "failed"
    assert draft["failure_reason"] == "Narration draft exceeds the 20-word limit."
    assert "validation_error" in draft["usage_metadata_json"]


def test_narration_draft_uses_full_spoken_text_word_count_for_thirty_three_word_failure(client, monkeypatch):
    from app.services import narration_service

    class WrongCountWriter:
        name = "mock"
        model = "wrong-count-writer"

        def write(self, payload):
            text = (
                "A broken gear jams the build process, causing repeated failures. "
                "The AI highlights the faulty gear; replacing it fixes the machine smoothly. "
                "Now the machine runs flawlessly with the new gear in place."
            )
            return {
                "segments": [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 3.0,
                        "spoken_text": text,
                        "caption_text": text,
                    }
                ],
                "full_spoken_text": text,
                "estimated_word_count": 20,
                "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
                "cost_estimate": 0.13,
                "provider_request_id": "req-wrong-count",
            }

    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    monkeypatch.setattr(narration_service, "get_narration_writer_provider", lambda: WrongCountWriter())

    response = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    assert response.status_code == 200
    draft = response.json()["narration_draft"]
    assert narration_service.calculate_spoken_word_count(WrongCountWriter().write({})["full_spoken_text"]) == 33
    assert draft["estimated_word_count"] == 0
    assert draft["failure_reason"] == "Narration draft exceeds the 20-word limit."
    assert draft["usage_metadata_json"]["validation_error"] == "Narration draft exceeds the 20-word limit."


def test_narration_draft_persists_calculated_word_count(client, monkeypatch):
    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    response = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    assert response.status_code == 200
    draft = response.json()["narration_draft"]
    assert draft["estimated_word_count"] > 0
    assert draft["estimated_word_count"] == len(draft["full_spoken_text"].replace(".", "").split())


def test_narration_draft_defaults_caption_text_to_spoken_text_for_writer_output(client, monkeypatch):
    from app.services import narration_service

    class MissingCaptionWriter:
        name = "mock"
        model = "missing-caption-writer"

        def write(self, payload):
            return {
                "segments": [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 4.0,
                        "spoken_text": "Repeated failures stop the build.",
                        "caption_text": "",
                    },
                    {
                        "start_seconds": 4.0,
                        "end_seconds": 10.0,
                        "spoken_text": "The AI spots the broken gear and the fix lands.",
                        "caption_text": "",
                    },
                ],
                "full_spoken_text": "Repeated failures stop the build. The AI spots the broken gear and the fix lands.",
                "estimated_word_count": 7,
                "usage": {"input_tokens": 9, "output_tokens": 12, "total_tokens": 21},
                "cost_estimate": 0.06,
                "provider_request_id": "req-missing-caption",
            }

    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    monkeypatch.setattr(narration_service, "get_narration_writer_provider", lambda: MissingCaptionWriter())
    response = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    assert response.status_code == 200
    draft = response.json()["narration_draft"]
    for segment in draft["script_json"]["segments"]:
        assert segment["caption_text"] == segment["spoken_text"]


def test_narration_patch_rejects_materially_shortened_captions(client, monkeypatch):
    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    created = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False}).json()
    segments = created["narration_draft"]["script_json"]["segments"]
    segments[0]["caption_text"] = "Short caption."
    response = client.patch(
        f"/api/pipeline-runs/{run_id}/narration/draft",
        json={
            "segments": segments,
            "full_spoken_text": created["narration_draft"]["full_spoken_text"],
        },
    )
    assert response.status_code == 400
    assert "caption text must remain identical or extremely close" in response.json()["detail"]


def test_narration_draft_retains_usage_metadata_when_post_provider_validation_fails(client, monkeypatch):
    from app.services import narration_service

    class InvalidTimingWriter:
        name = "mock"
        model = "invalid-writer"

        def write(self, payload):
            return {
                "segments": [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 10.0,
                        "spoken_text": "The machine is broken first.",
                        "caption_text": "The machine is broken first.",
                    },
                    {
                        "start_seconds": 10.0,
                        "end_seconds": 12.0,
                        "spoken_text": "",
                        "caption_text": "The AI fixes it.",
                    },
                ],
                "full_spoken_text": "The machine is broken first. The AI fixes it.",
                "estimated_word_count": 9,
                "usage": {"input_tokens": 21, "output_tokens": 14, "total_tokens": 35},
                "cost_estimate": 0.11,
                "provider_request_id": "req-invalid",
            }

    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    monkeypatch.setattr(narration_service, "get_narration_writer_provider", lambda: InvalidTimingWriter())

    response = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    assert response.status_code == 200
    draft = response.json()["narration_draft"]
    assert draft["status"] == "failed"
    assert draft["paid_call_completed_at"] is not None
    assert draft["usage_metadata_json"]["total_tokens"] == 35
    assert draft["usage_metadata_json"]["validation_error"] == "Narration spoken text may not be empty."
    assert draft["usage_metadata_json"]["attempt_output"]["provider_request_id"] == "req-invalid"
    assert draft["estimated_writer_cost"] == 0.11


def test_narration_regeneration_preserves_prior_attempt_history(client, monkeypatch):
    from app.services import narration_service

    class FirstFailingWriter:
        name = "mock"
        model = "first-failing-writer"

        def write(self, payload):
            return {
                "segments": [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 10.0,
                        "spoken_text": "",
                        "caption_text": "The bug stays visible.",
                    }
                ],
                "full_spoken_text": "",
                "estimated_word_count": 0,
                "usage": {"input_tokens": 5, "output_tokens": 6, "total_tokens": 11},
                "cost_estimate": 0.07,
                "provider_request_id": "req-first-fail",
            }

    class SecondSuccessfulWriter:
        name = "mock"
        model = "second-success-writer"

        def write(self, payload):
            return {
                "segments": [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 3.0,
                        "spoken_text": "The bug stops the machine.",
                        "caption_text": "The bug stops the machine.",
                    },
                    {
                        "start_seconds": 3.0,
                        "end_seconds": 6.0,
                        "spoken_text": "The AI finds the bad wire.",
                        "caption_text": "The AI finds the bad wire.",
                    },
                    {
                        "start_seconds": 6.0,
                        "end_seconds": 10.0,
                        "spoken_text": "One fix restores the working machine.",
                        "caption_text": "One fix restores the working machine.",
                    },
                ],
                "full_spoken_text": "The bug stops the machine. The AI finds the bad wire. One fix restores the working machine.",
                "estimated_word_count": 16,
                "usage": {"input_tokens": 8, "output_tokens": 12, "total_tokens": 20},
                "cost_estimate": 0.09,
                "provider_request_id": "req-second-success",
            }

    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    monkeypatch.setattr(narration_service, "get_narration_writer_provider", lambda: FirstFailingWriter())

    failed = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    assert failed.status_code == 200
    failed_draft = failed.json()["narration_draft"]
    assert failed_draft["status"] == "failed"
    assert len(failed_draft["attempts_json"]) == 1
    assert failed_draft["attempts_json"][0]["provider_request_id"] == "req-first-fail"
    assert failed_draft["attempts_json"][0]["validation_result"] == "failed_validation"

    monkeypatch.setattr(narration_service, "get_narration_writer_provider", lambda: SecondSuccessfulWriter())
    regenerated = client.post(f"/api/pipeline-runs/{run_id}/narration/draft/regenerate", json={"confirm_paid_draft": False})
    assert regenerated.status_code == 200
    draft = regenerated.json()["narration_draft"]
    assert draft["status"] == "ready"
    assert draft["generation_revision"] == 2
    assert len(draft["attempts_json"]) == 2
    assert draft["attempts_json"][0]["provider_request_id"] == "req-first-fail"
    assert draft["attempts_json"][0]["validation_result"] == "failed_validation"
    assert draft["attempts_json"][1]["provider_request_id"] == "req-second-success"
    assert draft["attempts_json"][1]["validation_result"] == "ready"
    assert draft["attempts_json"][1]["attempt_output"]["full_spoken_text"] == draft["full_spoken_text"]
    assert draft["attempts_json"][1]["attempt_output"]["segments"]
    assert draft["failure_reason"] is None
    assert draft["failure_stage"] is None


def test_narration_success_with_unavailable_cost_uses_null_and_status(client, monkeypatch):
    from app.services import narration_service

    class UnpricedWriter:
        name = "mock"
        model = "unpriced-writer"

        def write(self, payload):
            return {
                "segments": [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 3.0,
                        "spoken_text": "Repeated failures stop the build.",
                        "caption_text": "Repeated failures stop the build.",
                    },
                    {
                        "start_seconds": 3.0,
                        "end_seconds": 10.0,
                        "spoken_text": "The AI spots the broken gear and the machine runs again.",
                        "caption_text": "The AI spots the broken gear and the machine runs again.",
                    },
                ],
                "full_spoken_text": "Repeated failures stop the build. The AI spots the broken gear and the machine runs again.",
                "estimated_word_count": 8,
                "usage": {"input_tokens": 13, "output_tokens": 11, "total_tokens": 24},
                "cost_estimate": None,
                "provider_request_id": "req-unpriced",
            }

    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    monkeypatch.setattr(narration_service, "get_narration_writer_provider", lambda: UnpricedWriter())
    response = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    assert response.status_code == 200
    draft = response.json()["narration_draft"]
    assert draft["estimated_writer_cost"] is None
    assert draft["usage_metadata_json"]["cost_estimation_status"] == "unavailable"
    assert draft["attempts_json"][0]["estimated_cost"] is None


def test_openai_speech_provider_uses_response_format_mp3(monkeypatch, tmp_path):
    from app.providers.speech import openai_provider

    captured = {}

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def stream_to_file(self, destination):
            Path(destination).write_bytes(b"mp3")

    class DummySpeech:
        def __init__(self):
            self.with_streaming_response = self

        def create(self, **kwargs):
            captured.update(kwargs)
            return DummyResponse()

    class DummyClient:
        def __init__(self, api_key=None, timeout=None):
            self.audio = type("Audio", (), {"speech": DummySpeech()})()

    monkeypatch.setattr(openai_provider, "OpenAI", DummyClient)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("NARRATION_TIMEOUT_SECONDS", "90")
    get_settings.cache_clear()

    provider = openai_provider.OpenAISpeechProvider()
    destination = tmp_path / "speech.mp3"
    result = provider.synthesize(text="hello world", voice="alloy", destination=destination)

    assert "response_format" in captured
    assert captured["response_format"] == "mp3"
    assert "format" not in captured
    assert result["mime_type"] == "audio/mpeg"
    assert destination.suffix == ".mp3"


def _create_failed_speech_render(client, monkeypatch, *, enqueue_immediately=True):
    from app.models import GenerationCost
    from app.services import narration_service

    class ConfigFailingSpeechProvider:
        name = "openai"
        model = "gpt-4o-mini-tts"

        def synthesize(self, *, text, voice, destination):
            raise TypeError("Speech.create() got an unexpected keyword argument 'format'")

    def inline_enqueue(render_id):
        with SessionLocal() as db:
            narration_service.process_narration_render(db, render_id, mode="full", task_id="inline-fail")

    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    client.post(
        f"/api/pipeline-runs/{run_id}/story-adherence/human-review",
        json={"decision": "approve", "notes": "Approved for narration."},
    )
    monkeypatch.setattr(narration_service, "get_speech_provider", lambda: ConfigFailingSpeechProvider())
    enqueue_calls = {"count": 0}

    def tracked_enqueue(render_id):
        enqueue_calls["count"] += 1
        if enqueue_immediately:
            inline_enqueue(render_id)

    monkeypatch.setattr(narration_service, "enqueue_narration_render_task", tracked_enqueue)

    response = client.post(
        f"/api/pipeline-runs/{run_id}/narration/render",
        json={"confirm_paid_narration": True},
    )
    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.query(GenerationCost).filter(GenerationCost.pipeline_run_id == run_id, GenerationCost.stage == "narration_speech").count() == 0
    return run_id, response.json(), enqueue_calls


def test_narration_render_client_configuration_failure_is_not_uncertain_and_has_no_speech_cost(client, monkeypatch):
    run_id, payload, _enqueue_calls = _create_failed_speech_render(client, monkeypatch)
    render = payload["latest_narration_render"]
    assert render["status"] == "failed"
    assert render["failure_stage"] == "speech"
    assert render["failure_kind"] == "client_configuration"
    assert render["provider_request_dispatched"] is False
    assert render["paid_call_outcome_uncertain"] is False
    assert render["audio_asset_id"] is None
    assert render["estimated_speech_cost"] is None
    assert len(render["speech_attempts_json"]) == 1
    attempt = render["speech_attempts_json"][0]
    assert attempt["attempt_revision"] == 1
    assert attempt["provider_request_dispatched"] is False
    assert attempt["failure_kind"] == "client_configuration"
    assert attempt["attempt_result"] == "failed"


def test_narration_speech_retry_requires_paid_confirmation(client, monkeypatch):
    run_id, payload, _enqueue_calls = _create_failed_speech_render(client, monkeypatch)
    render_id = payload["latest_narration_render"]["id"]
    response = client.post(
        f"/api/pipeline-runs/{run_id}/narration/renders/{render_id}/retry-speech",
        json={"confirm_paid_narration": False},
    )
    assert response.status_code == 409
    assert "confirm_paid_narration=true" in response.json()["detail"]


def test_narration_speech_retry_appends_attempt_revision_two(client, monkeypatch):
    from app.services import narration_service

    run_id, payload, _enqueue_calls = _create_failed_speech_render(client, monkeypatch)
    render_id = payload["latest_narration_render"]["id"]

    class RetryFailingSpeechProvider:
        name = "openai"
        model = "gpt-4o-mini-tts"

        def synthesize(self, *, text, voice, destination):
            raise TypeError("Speech.create() got an unexpected keyword argument 'format'")

    def inline_enqueue(render_id):
        with SessionLocal() as db:
            narration_service.process_narration_render(db, render_id, mode="full", task_id="inline-retry-fail")

    monkeypatch.setattr(narration_service, "get_speech_provider", lambda: RetryFailingSpeechProvider())
    monkeypatch.setattr(narration_service, "enqueue_narration_render_task", inline_enqueue)

    response = client.post(
        f"/api/pipeline-runs/{run_id}/narration/renders/{render_id}/retry-speech",
        json={"confirm_paid_narration": True},
    )
    assert response.status_code == 200
    render = response.json()["latest_narration_render"]
    assert len(render["speech_attempts_json"]) == 2
    assert render["speech_attempts_json"][0]["attempt_revision"] == 1
    assert render["speech_attempts_json"][1]["attempt_revision"] == 2
    assert render["speech_attempts_json"][0]["provider_attempt_id"] != render["speech_attempts_json"][1]["provider_attempt_id"]


def test_narration_speech_retry_only_queues_once_when_already_queued(client, monkeypatch):
    from app.services import narration_service

    run_id, payload, _enqueue_calls = _create_failed_speech_render(client, monkeypatch)
    render_id = payload["latest_narration_render"]["id"]
    enqueue_calls = {"count": 0}

    def tracked_enqueue(render_id):
        enqueue_calls["count"] += 1

    monkeypatch.setattr(narration_service, "enqueue_narration_render_task", tracked_enqueue)

    first = client.post(
        f"/api/pipeline-runs/{run_id}/narration/renders/{render_id}/retry-speech",
        json={"confirm_paid_narration": True},
    )
    second = client.post(
        f"/api/pipeline-runs/{run_id}/narration/renders/{render_id}/retry-speech",
        json={"confirm_paid_narration": True},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert enqueue_calls["count"] == 1
    assert second.json()["latest_narration_render"]["status"] == "queued"


def test_narration_speech_retry_blocked_when_audio_exists(client, monkeypatch):
    _enable_mock_narration(monkeypatch)
    run_id, _payload = _create_completed_run(client)
    client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    client.post(
        f"/api/pipeline-runs/{run_id}/story-adherence/human-review",
        json={"decision": "approve", "notes": "Approved for narration."},
    )
    rendered = client.post(
        f"/api/pipeline-runs/{run_id}/narration/render",
        json={"confirm_paid_narration": True},
    ).json()
    render_id = rendered["latest_narration_render"]["id"]
    response = client.post(
        f"/api/pipeline-runs/{run_id}/narration/renders/{render_id}/retry-speech",
        json={"confirm_paid_narration": True},
    )
    assert response.status_code == 400
    assert "Recompose the existing render instead" in response.json()["detail"]


def test_narration_speech_retry_uncertain_requires_extra_confirmation(client, monkeypatch):
    run_id, payload, _enqueue_calls = _create_failed_speech_render(client, monkeypatch)
    render_id = payload["latest_narration_render"]["id"]
    from app.models import NarrationRender

    with SessionLocal() as db:
        render = db.get(NarrationRender, render_id)
        render.paid_call_outcome_uncertain = True
        db.commit()

    response = client.post(
        f"/api/pipeline-runs/{run_id}/narration/renders/{render_id}/retry-speech",
        json={"confirm_paid_narration": True},
    )
    assert response.status_code == 409
    assert "confirm_possible_duplicate_charge=true" in response.json()["detail"]
