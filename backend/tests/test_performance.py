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


def test_get_run_performance_builds_comparison_metrics_and_uses_latest_snapshot(client):
    run_id, _payload = _create_completed_run(client)
    first_post = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "tiktok", "post_url": "https://www.tiktok.com/@storyengine/video/compare-a", "posted_at": "2026-07-10T10:00:00+00:00"},
    )
    second_post = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "instagram", "post_url": "https://instagram.com/reel/compare-b", "posted_at": "2026-07-10T10:00:00+00:00"},
    )
    first_id = first_post.json()["id"]
    second_id = second_post.json()["id"]

    older = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{first_id}/snapshots",
        json={"captured_at": "2026-07-11T09:00:00+00:00", "views": 80, "likes": 8, "comments": 2, "shares": 1, "saves": 1},
    )
    newer = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{first_id}/snapshots",
        json={
            "captured_at": "2026-07-11T10:00:00+00:00",
            "views": 100,
            "likes": 11,
            "comments": 2,
            "shares": 1,
            "saves": 1,
            "completion_rate": 0.625,
            "average_watch_time_seconds": 8.5,
            "followers_gained": 4,
        },
    )
    second_snapshot = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{second_id}/snapshots",
        json={
            "captured_at": "2026-07-11T11:00:00+00:00",
            "views": 200,
            "likes": 22,
            "comments": 4,
            "shares": 2,
            "saves": 2,
            "completion_rate": 0.625,
            "average_watch_time_seconds": 8.5,
            "followers_gained": 8,
        },
    )
    assert older.status_code == 201
    assert newer.status_code == 201
    assert second_snapshot.status_code == 201

    with SessionLocal() as db:
        first_post_row = db.get(PlatformPost, first_id)
        second_post_row = db.get(PlatformPost, second_id)
        db.get(Asset, first_post_row.final_asset_id).duration_seconds = 10
        db.get(Asset, second_post_row.final_asset_id).duration_seconds = 10
        db.commit()

    response = client.get(f"/api/pipeline-runs/{run_id}/performance")
    assert response.status_code == 200
    body = response.json()
    assert body["comparison"]["latest_snapshot_ordering"] == ["captured_at_desc", "created_at_desc", "id_desc"]

    posts = {post["id"]: post for post in body["platform_posts"]}
    first = posts[first_id]
    second = posts[second_id]

    assert first["latest_snapshot"]["views"] == 100
    assert [snapshot["views"] for snapshot in first["snapshots"]] == [100, 80]
    assert first["comparison_metrics"]["engagement_rate"] == 0.15
    assert first["comparison_metrics"]["like_rate"] == 0.11
    assert first["comparison_metrics"]["comment_rate"] == 0.02
    assert first["comparison_metrics"]["share_rate"] == 0.01
    assert first["comparison_metrics"]["save_rate"] == 0.01
    assert first["comparison_metrics"]["completion_rate"] == 0.625
    assert first["comparison_metrics"]["follower_conversion_rate"] == 0.04
    assert first["comparison_metrics"]["average_watch_time_ratio"] == 0.85

    assert second["comparison_metrics"]["engagement_rate"] == 0.15
    assert second["comparison_metrics"]["like_rate"] == 0.11
    assert body["comparison"]["metrics"]["views"]["status"] == "leader"
    assert body["comparison"]["metrics"]["views"]["leader_post_ids"] == [second_id]
    assert body["comparison"]["metrics"]["engagement_rate"]["status"] == "tie"
    assert sorted(body["comparison"]["metrics"]["engagement_rate"]["leader_post_ids"]) == sorted([first_id, second_id])
    assert body["comparison"]["metrics"]["like_rate"]["status"] == "tie"


def test_get_run_performance_handles_missing_values_zero_values_and_only_available(client):
    run_id, _payload = _create_completed_run(client)
    created = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "youtube", "post_url": "https://youtube.com/shorts/only-available", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    post_id = created.json()["id"]

    snapshot = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post_id}/snapshots",
        json={
            "captured_at": "2026-07-11T12:00:00+00:00",
            "views": 0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "completion_rate": 0,
            "followers_gained": 0,
        },
    )
    assert snapshot.status_code == 201

    response = client.get(f"/api/pipeline-runs/{run_id}/performance")
    assert response.status_code == 200
    post = response.json()["platform_posts"][0]
    comparison = response.json()["comparison"]["metrics"]

    assert post["comparison_metrics"]["views"] == 0
    assert post["comparison_metrics"]["engagement_rate"] is None
    assert post["comparison_metrics"]["like_rate"] is None
    assert post["comparison_metrics"]["completion_rate"] == 0
    assert post["comparison_metrics"]["follower_conversion_rate"] is None
    assert comparison["views"]["status"] == "only_available"
    assert comparison["views"]["leader_post_ids"] == [post_id]
    assert comparison["completion_rate"]["status"] == "only_available"
    assert comparison["engagement_rate"]["status"] == "unavailable"


def test_get_run_performance_uses_duration_fallback_and_null_ratio_when_missing(client):
    run_id, payload = _create_completed_run(client)
    created = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "other", "custom_platform_name": "Acceptance", "post_url": "https://example.com/perf/duration", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    post_id = created.json()["id"]
    snapshot = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post_id}/snapshots",
        json={"captured_at": "2026-07-11T11:00:00+00:00", "views": 100, "average_watch_time_seconds": 5},
    )
    assert snapshot.status_code == 201

    with SessionLocal() as db:
        post = db.get(PlatformPost, post_id)
        asset = db.get(Asset, post.final_asset_id)
        asset.duration_seconds = None
        post.final_asset_metadata_json = {**(post.final_asset_metadata_json or {}), "duration_seconds": 20}
        db.add(asset)
        db.add(post)
        db.commit()

    response = client.get(f"/api/pipeline-runs/{run_id}/performance")
    assert response.status_code == 200
    post = next(item for item in response.json()["platform_posts"] if item["id"] == post_id)
    assert post["attributed_asset_duration_seconds"] == 20
    assert post["comparison_metrics"]["average_watch_time_ratio"] == 0.25

    with SessionLocal() as db:
        post = db.get(PlatformPost, post_id)
        post.final_asset_metadata_json = {**(post.final_asset_metadata_json or {}), "duration_seconds": 0}
        db.add(post)
        db.commit()

    response = client.get(f"/api/pipeline-runs/{run_id}/performance")
    assert response.status_code == 200
    post = next(item for item in response.json()["platform_posts"] if item["id"] == post_id)
    assert post["comparison_metrics"]["average_watch_time_ratio"] is None


def test_get_run_performance_builds_age_buckets_and_warnings(client):
    run_id, _payload = _create_completed_run(client)
    bodies = [
        ("tiktok", "https://www.tiktok.com/@storyengine/video/age-1", "2026-07-10T10:00:00+00:00", "2026-07-10T16:00:00+00:00"),
        ("instagram", "https://instagram.com/reel/age-2", "2026-07-10T10:00:00+00:00", "2026-07-12T10:00:00+00:00"),
        ("youtube", "https://youtube.com/shorts/age-3", "2026-07-10T10:00:00+00:00", "2026-07-10T09:00:00+00:00"),
    ]
    post_ids = []
    for platform, url, posted_at, captured_at in bodies:
        created = client.post(
            f"/api/pipeline-runs/{run_id}/performance/posts",
            json={"platform": platform, "post_url": url, "posted_at": posted_at},
        )
        post_ids.append(created.json()["id"])
        client.post(
            f"/api/pipeline-runs/{run_id}/performance/posts/{created.json()['id']}/snapshots",
            json={"captured_at": captured_at, "views": 100},
        )

    response = client.get(f"/api/pipeline-runs/{run_id}/performance")
    assert response.status_code == 200
    body = response.json()
    posts = {post["id"]: post for post in body["platform_posts"]}

    valid_under_24h = next(post for post in posts.values() if post["latest_snapshot_age_bucket"] == "under_24h")
    valid_one_to_three = next(post for post in posts.values() if post["latest_snapshot_age_bucket"] == "1_3d")
    invalid = next(post for post in posts.values() if post["latest_snapshot_age_status"] == "captured_before_posting")

    assert valid_under_24h["latest_snapshot_age_label"] == "6h after posting"
    assert valid_one_to_three["latest_snapshot_age_seconds"] == 172800
    assert invalid["latest_snapshot_age_label"] == "Captured before posting"
    assert body["comparison"]["mixed_age_warning"] is True
    assert body["comparison"]["mixed_age_warning_text"] == "These posts were measured at different ages after posting, so raw comparisons may not reflect equivalent windows."
    assert body["comparison"]["has_invalid_capture_age"] is True


def test_get_run_performance_does_not_mutate_rows(client):
    run_id, _payload = _create_completed_run(client)
    created = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "tiktok", "post_url": "https://www.tiktok.com/@storyengine/video/read-only", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    post_id = created.json()["id"]
    client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{post_id}/snapshots",
        json={"captured_at": "2026-07-11T11:00:00+00:00", "views": 123},
    )

    with SessionLocal() as db:
        package = db.query(ManualPostPackage).filter(ManualPostPackage.id == created.json()["manual_post_package_id"]).first()
        post = db.get(PlatformPost, post_id)
        event_count = db.query(PipelineEvent).filter(PipelineEvent.pipeline_run_id == run_id).count()
        package_updated_at = package.updated_at
        post_updated_at = post.updated_at

    response = client.get(f"/api/pipeline-runs/{run_id}/performance")
    assert response.status_code == 200

    with SessionLocal() as db:
        package = db.query(ManualPostPackage).filter(ManualPostPackage.id == created.json()["manual_post_package_id"]).first()
        post = db.get(PlatformPost, post_id)
        assert db.query(PipelineEvent).filter(PipelineEvent.pipeline_run_id == run_id).count() == event_count
        assert package.updated_at == package_updated_at
        assert post.updated_at == post_updated_at


def test_manual_winner_defaults_are_exposed_without_selection(client):
    run_id, _payload = _create_completed_run(client)

    performance = client.get(f"/api/pipeline-runs/{run_id}/performance")
    run_detail = client.get(f"/api/pipeline-runs/{run_id}")
    library_detail = client.get(f"/api/asset-library/{run_id}")

    assert performance.status_code == 200
    assert run_detail.status_code == 200
    assert library_detail.status_code == 200
    assert performance.json()["winner_selection"] == {
        "platform_post_id": None,
        "selected_at": None,
        "selection_revision": 0,
        "post": None,
    }
    assert run_detail.json()["winner_selection"] == performance.json()["winner_selection"]
    assert library_detail.json()["winner_selection"] == performance.json()["winner_selection"]


def test_select_replace_and_clear_manual_winner(client):
    run_id, _payload = _create_completed_run(client)
    first_post = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "tiktok", "post_url": "https://www.tiktok.com/@storyengine/video/winner-a", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    second_post = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "instagram", "post_url": "https://instagram.com/reel/winner-b", "posted_at": "2026-07-11T11:00:00+00:00"},
    )
    first_id = first_post.json()["id"]
    second_id = second_post.json()["id"]

    selected = client.put(
        f"/api/pipeline-runs/{run_id}/performance/winner",
        json={"platform_post_id": first_id},
    )
    assert selected.status_code == 200
    winner = selected.json()["winner_selection"]
    assert winner["platform_post_id"] == first_id
    assert winner["selection_revision"] == 1
    assert winner["post"]["id"] == first_id
    assert winner["post"]["platform"] == "tiktok"
    first_selected_at = winner["selected_at"]
    assert first_selected_at is not None

    replaced = client.put(
        f"/api/pipeline-runs/{run_id}/performance/winner",
        json={"platform_post_id": second_id},
    )
    assert replaced.status_code == 200
    replaced_winner = replaced.json()["winner_selection"]
    assert replaced_winner["platform_post_id"] == second_id
    assert replaced_winner["selection_revision"] == 2
    assert replaced_winner["post"]["id"] == second_id
    assert replaced_winner["selected_at"] != first_selected_at

    cleared = client.delete(f"/api/pipeline-runs/{run_id}/performance/winner")
    assert cleared.status_code == 200
    assert cleared.json()["winner_selection"] == {
        "platform_post_id": None,
        "selected_at": None,
        "selection_revision": 3,
        "post": None,
    }

    with SessionLocal() as db:
        package = db.get(ManualPostPackage, cleared.json()["platform_posts"][0]["manual_post_package_id"])
        assert package.winner_platform_post_id is None
        assert package.winner_selected_at is None
        assert package.winner_selection_revision == 3
        winner_events = [
            event.event_type
            for event in db.query(PipelineEvent)
            .filter(PipelineEvent.pipeline_run_id == run_id)
            .order_by(PipelineEvent.created_at.asc())
            .all()
            if event.event_type.startswith("performance.winner_")
        ]
        assert winner_events == [
            "performance.winner_selected",
            "performance.winner_changed",
            "performance.winner_cleared",
        ]


def test_manual_winner_selection_and_clear_are_idempotent(client):
    run_id, _payload = _create_completed_run(client)
    created = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "youtube", "post_url": "https://youtube.com/shorts/winner-idempotent", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    post_id = created.json()["id"]

    first = client.put(
        f"/api/pipeline-runs/{run_id}/performance/winner",
        json={"platform_post_id": post_id},
    )
    second = client.put(
        f"/api/pipeline-runs/{run_id}/performance/winner",
        json={"platform_post_id": post_id},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["winner_selection"] == first.json()["winner_selection"]

    cleared = client.delete(f"/api/pipeline-runs/{run_id}/performance/winner")
    cleared_again = client.delete(f"/api/pipeline-runs/{run_id}/performance/winner")
    assert cleared.status_code == 200
    assert cleared_again.status_code == 200
    assert cleared_again.json()["winner_selection"] == cleared.json()["winner_selection"]

    with SessionLocal() as db:
        winner_events = [
            event.event_type
            for event in db.query(PipelineEvent)
            .filter(PipelineEvent.pipeline_run_id == run_id)
            .all()
            if event.event_type.startswith("performance.winner_")
        ]
        assert winner_events.count("performance.winner_selected") == 1
        assert winner_events.count("performance.winner_cleared") == 1
        assert "performance.winner_changed" not in winner_events


def test_manual_winner_rejects_missing_and_cross_run_posts(client):
    run_id, _payload = _create_completed_run(client)
    other_run_id, _ = _create_completed_run(client)
    other_post = client.post(
        f"/api/pipeline-runs/{other_run_id}/performance/posts",
        json={"platform": "other", "custom_platform_name": "Cross", "post_url": "https://example.com/cross-winner", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    other_post_id = other_post.json()["id"]

    missing = client.put(
        f"/api/pipeline-runs/{run_id}/performance/winner",
        json={"platform_post_id": "00000000-0000-0000-0000-000000000000"},
    )
    cross_run = client.put(
        f"/api/pipeline-runs/{run_id}/performance/winner",
        json={"platform_post_id": other_post_id},
    )

    assert missing.status_code == 404
    assert cross_run.status_code == 404


def test_manual_winner_rejects_malformed_uuid(client):
    run_id, _payload = _create_completed_run(client)

    response = client.put(
        f"/api/pipeline-runs/{run_id}/performance/winner",
        json={"platform_post_id": "not-a-uuid"},
    )

    assert response.status_code == 422


def test_manual_winner_rejects_incomplete_run_and_missing_package(client):
    created = client.post("/api/pipeline-runs", json={"topic": "Winner Incomplete", "auto_mode": False})
    run_id = created.json()["pipeline_run"]["id"]

    incomplete = client.put(
        f"/api/pipeline-runs/{run_id}/performance/winner",
        json={"platform_post_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert incomplete.status_code == 409

    completed_run_id, _payload = _create_completed_run(client)
    with SessionLocal() as db:
        from app.models import PipelineRun

        run = db.get(PipelineRun, completed_run_id)
        run.manual_post_package_id = None
        db.add(run)
        db.commit()

    no_package = client.delete(f"/api/pipeline-runs/{completed_run_id}/performance/winner")
    assert no_package.status_code == 409


def test_manual_winner_does_not_change_comparison_attribution_or_final_asset_selection(client):
    run_id, _payload = _create_completed_run(client)
    first_post = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "tiktok", "post_url": "https://www.tiktok.com/@storyengine/video/winner-compare-a", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    second_post = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "instagram", "post_url": "https://instagram.com/reel/winner-compare-b", "posted_at": "2026-07-11T11:00:00+00:00"},
    )
    first_id = first_post.json()["id"]
    second_id = second_post.json()["id"]
    client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{first_id}/snapshots",
        json={"captured_at": "2026-07-11T12:00:00+00:00", "views": 100, "likes": 10, "comments": 5, "shares": 2, "saves": 3},
    )
    client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts/{second_id}/snapshots",
        json={"captured_at": "2026-07-11T13:00:00+00:00", "views": 200, "likes": 20, "comments": 10, "shares": 4, "saves": 6},
    )

    before = client.get(f"/api/pipeline-runs/{run_id}/performance").json()
    before_comparison = before["comparison"]
    before_posts = {post["id"]: post for post in before["platform_posts"]}
    before_final_selection = before["current_final_asset_selection"]

    selected = client.put(
        f"/api/pipeline-runs/{run_id}/performance/winner",
        json={"platform_post_id": first_id},
    )
    assert selected.status_code == 200
    after = selected.json()
    after_posts = {post["id"]: post for post in after["platform_posts"]}

    assert after["comparison"] == before_comparison
    assert after["current_final_asset_selection"] == before_final_selection
    assert after_posts[first_id]["final_asset_id"] == before_posts[first_id]["final_asset_id"]
    assert after_posts[first_id]["comparison_metrics"] == before_posts[first_id]["comparison_metrics"]
    assert after_posts[second_id]["comparison_metrics"] == before_posts[second_id]["comparison_metrics"]


def test_manual_winner_surfaces_in_run_detail_and_asset_library_detail(client):
    run_id, _payload = _create_completed_run(client)
    created = client.post(
        f"/api/pipeline-runs/{run_id}/performance/posts",
        json={"platform": "other", "custom_platform_name": "Acceptance Network", "post_url": "https://example.com/winner-summary", "posted_at": "2026-07-11T10:00:00+00:00"},
    )
    post_id = created.json()["id"]

    selected = client.put(
        f"/api/pipeline-runs/{run_id}/performance/winner",
        json={"platform_post_id": post_id},
    )
    assert selected.status_code == 200
    expected = selected.json()["winner_selection"]

    run_detail = client.get(f"/api/pipeline-runs/{run_id}")
    library_detail = client.get(f"/api/asset-library/{run_id}")

    assert run_detail.status_code == 200
    assert library_detail.status_code == 200
    assert run_detail.json()["winner_selection"] == expected
    assert library_detail.json()["winner_selection"] == expected
