from datetime import UTC, datetime
from pathlib import Path
import tempfile
from uuid import uuid4

from app.config import get_settings
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


def test_runway_storyboard_timings_fit_requested_duration(client, monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "runway")
    get_settings.cache_clear()
    response = client.post("/api/pipeline-runs", json={"topic": "CORS", "auto_mode": False})
    assert response.status_code == 200
    scenes = response.json()["script"]["script_json"]["scenes"]
    assert [scene["time"] for scene in scenes] == ["0-2s", "2-5s", "5-8s", "8-10s"]
    assert response.json()["script"]["duration_seconds"] == 10
    get_settings.cache_clear()


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
