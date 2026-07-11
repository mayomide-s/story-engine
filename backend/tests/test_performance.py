from app.config import get_settings
from app.db.session import SessionLocal
from app.models import Asset, ManualPostPackage, PipelineEvent, PlatformPost


def _create_completed_run(client):
    created = client.post("/api/pipeline-runs", json={"topic": "Performance Test", "auto_mode": False})
    assert created.status_code == 200
    run_id = created.json()["pipeline_run"]["id"]
    resumed = client.post(f"/api/pipeline-runs/{run_id}/resume", json={"review_notes": "Ready for performance tracking"})
    assert resumed.status_code == 200
    return run_id, resumed.json()


def _enable_mock_narration(monkeypatch):
    monkeypatch.setenv("NARRATION_ENABLED", "true")
    monkeypatch.setenv("NARRATION_WRITER_PROVIDER", "mock")
    monkeypatch.setenv("NARRATION_SPEECH_PROVIDER", "mock")
    get_settings.cache_clear()


def _create_approved_narration_render(client, monkeypatch, run_id: str):
    _enable_mock_narration(monkeypatch)
    draft = client.post(f"/api/pipeline-runs/{run_id}/narration/draft", json={"confirm_paid_draft": False})
    assert draft.status_code == 200
    story_review = client.post(
        f"/api/pipeline-runs/{run_id}/story-adherence/human-review",
        json={"decision": "approve", "notes": "Approved for narration selection."},
    )
    assert story_review.status_code == 200
    render = client.post(
        f"/api/pipeline-runs/{run_id}/narration/render",
        json={"confirm_paid_narration": True, "voice": "alloy"},
    )
    assert render.status_code == 200
    render_id = render.json()["latest_narration_render"]["id"]
    approved = client.post(
        f"/api/pipeline-runs/{run_id}/narration/human-review",
        json={"narration_render_id": render_id, "decision": "approve", "notes": "Approved render."},
    )
    assert approved.status_code == 200
    return approved.json()["latest_narration_render"]


def test_create_tiktok_platform_post(client):
    run_id, payload = _create_completed_run(client)
    source_asset = next(asset for asset in payload["assets"] if asset["asset_type"] == "video_mp4")

    response = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={
            "platform": "tiktok",
            "post_url": "https://www.tiktok.com/@storyengine/video/123456",
            "posted_at": "2026-07-11T10:00:00+00:00",
            "notes": "First TikTok post",
        },
    )

    assert response.status_code == 201
    post = response.json()
    assert post["platform"] == "tiktok"
    assert post["final_asset_id"] == source_asset["id"]
    assert post["final_asset_source"] == "source_video"


def test_create_other_platform_post_requires_custom_name(client):
    run_id, _payload = _create_completed_run(client)

    response = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={
            "platform": "other",
            "post_url": "https://example.com/posts/1",
            "posted_at": "2026-07-11T10:00:00+00:00",
        },
    )

    assert response.status_code == 422


def test_create_other_platform_post_succeeds_with_custom_name(client):
    run_id, _payload = _create_completed_run(client)

    response = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={
            "platform": "other",
            "custom_platform_name": "LinkedIn Shorts",
            "post_url": "https://example.com/posts/other-1",
            "posted_at": "2026-07-11T10:00:00+00:00",
        },
    )

    assert response.status_code == 201
    assert response.json()["custom_platform_name"] == "LinkedIn Shorts"


def test_named_platform_rejects_custom_platform_name(client):
    run_id, _payload = _create_completed_run(client)

    response = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={
            "platform": "youtube",
            "custom_platform_name": "Should fail",
            "post_url": "https://youtube.com/shorts/abc",
            "posted_at": "2026-07-11T10:00:00+00:00",
        },
    )

    assert response.status_code == 422


def test_platform_post_rejects_malformed_url_and_credentials(client):
    run_id, _payload = _create_completed_run(client)

    malformed = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={
            "platform": "instagram",
            "post_url": "notaurl",
            "posted_at": "2026-07-11T10:00:00+00:00",
        },
    )
    assert malformed.status_code == 422

    credentialed = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={
            "platform": "instagram",
            "post_url": "https://user:pass@example.com/post/1",
            "posted_at": "2026-07-11T10:00:00+00:00",
        },
    )
    assert credentialed.status_code == 422


def test_platform_post_rejects_duplicate_platform_and_url(client):
    run_id, _payload = _create_completed_run(client)
    body = {
        "platform": "tiktok",
        "post_url": "https://www.tiktok.com/@storyengine/video/duplicate",
        "posted_at": "2026-07-11T10:00:00+00:00",
    }
    first = client.post(f"/api/pipeline-runs/{run_id}/performance/posts", json=body)
    second = client.post(f"/api/pipeline-runs/{run_id}/performance/posts", json=body)

    assert first.status_code == 201
    assert second.status_code == 409


def test_platform_post_allows_multiple_posts_for_same_platform_and_run(client):
    run_id, _payload = _create_completed_run(client)

    first = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "tiktok", "post_url": "https://www.tiktok.com/@storyengine/video/1", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    second = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "tiktok", "post_url": "https://www.tiktok.com/@storyengine/video/2", "posted_at": "2026-07-12T10:00:00+00:00"},
    )

    assert first.status_code == 201
    assert second.status_code == 201


def test_platform_post_rejects_incomplete_run(client):
    created = client.post("/api/pipeline-runs", json={"topic": "Incomplete", "auto_mode": False})
    run_id = created.json()["pipeline_run"]["id"]

    response = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "tiktok", "post_url": "https://www.tiktok.com/@storyengine/video/incomplete", "posted_at": "2026-07-11T10:00:00+00:00"},
    )

    assert response.status_code == 409


def test_platform_post_rejects_run_without_manual_post_package(client):
    run_id, _payload = _create_completed_run(client)
    with SessionLocal() as db:
        from app.models import PipelineRun

        run = db.get(PipelineRun, run_id)
        run.manual_post_package_id = None
        db.add(run)
        db.commit()

    response = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "tiktok", "post_url": "https://www.tiktok.com/@storyengine/video/no-package", "posted_at": "2026-07-11T10:00:00+00:00"},
    )

    assert response.status_code == 409


def test_platform_post_rejects_unresolvable_final_asset(client):
    run_id, payload = _create_completed_run(client)
    with SessionLocal() as db:
        asset_ids = [asset["id"] for asset in payload["assets"] if asset["asset_type"] == "video_mp4"]
        for asset_id in asset_ids:
            asset = db.get(Asset, asset_id)
            db.delete(asset)
        db.commit()

    response = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "instagram", "post_url": "https://instagram.com/reel/noasset", "posted_at": "2026-07-11T10:00:00+00:00"},
    )

    assert response.status_code == 409


def test_platform_post_snapshot_is_immutable_after_final_selection_changes(client, monkeypatch):
    run_id, payload = _create_completed_run(client)
    first_post = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "youtube", "post_url": "https://youtube.com/shorts/source-video", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    assert first_post.status_code == 201
    source_snapshot = first_post.json()

    render = _create_approved_narration_render(client, monkeypatch, run_id)
    selected = client.post(
        f"/api/pipeline-runs/{run_id}/final-asset/select",
        json={"source": "narration_render", "narration_render_id": render["id"], "confirm_change_after_posting": True},
    )
    assert selected.status_code == 200

    performance = client.get(f"/api/pipeline-runs/{run_id}/performance")
    assert performance.status_code == 200
    posts = performance.json()["platform_posts"]
    preserved = next(post for post in posts if post["id"] == source_snapshot["id"])
    assert preserved["final_asset_source"] == "source_video"
    assert preserved["final_asset_id"] == source_snapshot["final_asset_id"]
    assert preserved["final_narration_render_id"] is None


def test_platform_post_update_changes_only_permitted_metadata(client):
    run_id, _payload = _create_completed_run(client)
    created = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "instagram", "post_url": "https://instagram.com/reel/update-me", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    post = created.json()

    updated = client.patch(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post['id']}",
        json={
            "platform": "other",
            "custom_platform_name": "X Reels",
            "post_url": "https://example.com/updated-post",
            "posted_at": "2026-07-12T12:30:00+00:00",
            "notes": "Updated notes",
            "final_asset_id": "should-be-ignored",
        },
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["platform"] == "other"
    assert body["custom_platform_name"] == "X Reels"
    assert body["post_url"] == "https://example.com/updated-post"
    assert body["notes"] == "Updated notes"
    assert body["final_asset_id"] == post["final_asset_id"]


def test_cross_run_platform_post_access_returns_not_found(client):
    first_run_id, _ = _create_completed_run(client)
    second_run_id, _ = _create_completed_run(client)
    created = client.post(
        f"/api/pipeline-runs/{first_run_id}/performance/posts",
        json={"platform": "tiktok", "post_url": "https://www.tiktok.com/@storyengine/video/cross-run", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    post_id = created.json()["id"]

    response = client.patch(
        f"/api/pipeline-runs/{second_run_id}/performance/posts/{post_id}",
        json={"notes": "wrong run"},
    )

    assert response.status_code == 404


def test_manual_post_package_status_updates_safely_and_existing_url_not_overwritten(client):
    run_id, _payload = _create_completed_run(client)
    existing = client.patch(
        f"/api/asset-library/{run_id}/manual-posting",
        json={"manual_posting_status": "posted_tiktok", "tiktok_post_url": "https://www.tiktok.com/@storyengine/video/original"},
    )
    assert existing.status_code == 200

    created = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "tiktok", "post_url": "https://www.tiktok.com/@storyengine/video/newer", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    assert created.status_code == 201

    detail = client.get(f"/api/pipeline-runs/{run_id}").json()
    manual_package = detail["manual_post_package"]
    assert manual_package["manual_posting_status"] == "posted_tiktok"
    assert manual_package["tiktok_post_url"] == "https://www.tiktok.com/@storyengine/video/original"


def test_append_snapshots_and_order_newest_first(client):
    run_id, _payload = _create_completed_run(client)
    created = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "youtube", "post_url": "https://youtube.com/shorts/snapshots", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    post_id = created.json()["id"]

    first = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post_id}/snapshots",
        json={"captured_at": "2026-07-12T10:00:00+00:00", "views": 100, "likes": 12},
    )
    second = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post_id}/snapshots",
        json={"captured_at": "2026-07-13T10:00:00+00:00", "views": 200, "likes": 25},
    )

    assert first.status_code == 201
    assert second.status_code == 201

    performance = client.get(f"/api/pipeline-runs/{run_id}/performance")
    snapshots = performance.json()["platform_posts"][0]["snapshots"]
    assert [snapshot["views"] for snapshot in snapshots] == [200, 100]


def test_snapshot_allows_zero_values_and_preserves_nulls(client):
    run_id, _payload = _create_completed_run(client)
    created = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "other", "custom_platform_name": "Blog", "post_url": "https://example.com/blog/perf", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    post_id = created.json()["id"]

    response = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post_id}/snapshots",
        json={"captured_at": "2026-07-12T10:00:00+00:00", "views": 0, "likes": 0},
    )

    assert response.status_code == 201
    snapshot = response.json()
    assert snapshot["views"] == 0
    assert snapshot["likes"] == 0
    assert snapshot["shares"] is None


def test_snapshot_rejects_negative_values_invalid_completion_and_empty_metrics(client):
    run_id, _payload = _create_completed_run(client)
    created = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "instagram", "post_url": "https://instagram.com/reel/metrics", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    post_id = created.json()["id"]

    negative = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post_id}/snapshots",
        json={"captured_at": "2026-07-12T10:00:00+00:00", "views": -1},
    )
    assert negative.status_code == 422

    invalid_completion = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post_id}/snapshots",
        json={"captured_at": "2026-07-12T11:00:00+00:00", "completion_rate": 1.1},
    )
    assert invalid_completion.status_code == 422

    empty = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post_id}/snapshots",
        json={"captured_at": "2026-07-12T12:00:00+00:00", "notes": "No metrics"},
    )
    assert empty.status_code == 422


def test_snapshot_rejects_duplicate_capture_timestamp_and_cross_run_access(client):
    first_run_id, _ = _create_completed_run(client)
    second_run_id, _ = _create_completed_run(client)
    created = client.post(
        f"/api/pipeline-runs/{first_run_id}/performance/posts",
        json={"platform": "youtube", "post_url": "https://youtube.com/shorts/dupe-snapshot", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    post_id = created.json()["id"]
    body = {"captured_at": "2026-07-12T10:00:00+00:00", "views": 50}

    first = client.post(f"/api/pipeline-runs/{first_run_id}/performance/posts/{post_id}/snapshots", json=body)
    duplicate = client.post(f"/api/pipeline-runs/{first_run_id}/performance/posts/{post_id}/snapshots", json=body)
    wrong_run = client.post(f"/api/pipeline-runs/{second_run_id}/performance/posts/{post_id}/snapshots", json={"captured_at": "2026-07-12T11:00:00+00:00", "views": 60})

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert wrong_run.status_code == 404


def test_performance_audit_events_and_failed_requests_create_no_event(client):
    run_id, _payload = _create_completed_run(client)
    failed = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "youtube", "post_url": "bad-url", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    assert failed.status_code == 422

    created = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "youtube", "post_url": "https://youtube.com/shorts/events", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    assert created.status_code == 201
    post_id = created.json()["id"]

    updated = client.patch(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post_id}",
        json={"notes": "Updated"},
    )
    assert updated.status_code == 200

    snapshot = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post_id}/snapshots",
        json={"captured_at": "2026-07-12T10:00:00+00:00", "views": 321},
    )
    assert snapshot.status_code == 201

    with SessionLocal() as db:
        events = db.query(PipelineEvent).filter(PipelineEvent.pipeline_run_id == run_id).all()
        event_types = [event.event_type for event in events]
        assert "performance.post_created" in event_types
        assert "performance.post_updated" in event_types
        assert "performance.snapshot_added" in event_types
        assert event_types.count("performance.post_created") == 1


def test_get_run_performance_returns_current_selection_and_platform_posts(client):
    run_id, _payload = _create_completed_run(client)
    created = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "instagram", "post_url": "https://instagram.com/reel/perf-get", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    assert created.status_code == 201

    response = client.get(f"/api/pipeline-runs/{run_id}/performance")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["current_final_asset_selection"]["source"] == "source_video"
    assert len(body["platform_posts"]) == 1


def test_platform_post_unique_constraint_is_global(client):
    first_run_id, _ = _create_completed_run(client)
    second_run_id, _ = _create_completed_run(client)
    body = {"platform": "tiktok", "post_url": "https://www.tiktok.com/@storyengine/video/global", "posted_at": "2026-07-11T10:00:00+00:00"}

    first = client.post(f"/api/pipeline-runs/{first_run_id}/performance/posts", json=body)
    second = client.post(f"/api/pipeline-runs/{second_run_id}/performance/posts", json=body)

    assert first.status_code == 201
    assert second.status_code == 409
