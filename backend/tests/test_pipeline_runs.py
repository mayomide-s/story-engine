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


def test_config_validation_accepts_mock_local_mode():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///./test.db",
        redis_url="redis://redis:6379/0",
        video_provider="mock",
        storage_provider="local",
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
    assert [scene["time"] for scene in scenes] == ["0-2s", "2-5s", "5-8s", "8-10s"]
    assert response.json()["script"]["duration_seconds"] == 10
    get_settings.cache_clear()


def test_runway_prompt_preview_stays_within_provider_limit(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    response = client.post("/api/pipeline-runs", json={"topic": "Python decorators", "auto_mode": False})
    assert response.status_code == 200
    prompt_preview = response.json()["prompt_preview"]
    assert len(prompt_preview) <= 1000
    assert "End tag:" in prompt_preview
    assert "Use real motion" in prompt_preview
    get_settings.cache_clear()


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

    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Use runway"})
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

    resume = client.post(f"/api/pipeline-runs/{run_id}/resume")
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

    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Approved"})
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


def test_duplicate_resume_does_not_create_second_submission(client, monkeypatch):
    from app.services import pipeline_service

    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]
    queued = {"count": 0}

    def fake_enqueue(task_run_id, countdown=None):
        queued["count"] += 1

    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    monkeypatch.setattr(pipeline_service, "enqueue_resume_pipeline_task", fake_enqueue)

    first = client.post(f"/api/pipeline-runs/{run_id}/resume")
    second = client.post(f"/api/pipeline-runs/{run_id}/resume")
    assert first.status_code == 200
    assert second.status_code == 200
    assert queued["count"] == 1
    get_settings.cache_clear()


def test_resume_rejects_run_with_completed_video(client):
    create = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    run_id = create.json()["pipeline_run"]["id"]

    first_resume = client.post(f"/api/pipeline-runs/{run_id}/resume")
    assert first_resume.status_code == 200

    second_resume = client.post(f"/api/pipeline-runs/{run_id}/resume")
    assert second_resume.status_code == 400
    assert "Open Video Review" in second_resume.json()["detail"]


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

    resume = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Approved"})
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
