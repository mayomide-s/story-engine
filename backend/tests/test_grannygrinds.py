from app.services.grannygrinds_service import (
    GRANNY_CHARACTER_SPECS,
    build_granny_prompt,
    build_preservation_qc,
)


def test_granny_rotation_has_three_stable_characters():
    assert [item["key"] for item in GRANNY_CHARACTER_SPECS] == ["mabel", "gloria", "dorothy"]
    assert len({item["seed"] for item in GRANNY_CHARACTER_SPECS}) == 3


def test_granny_prompt_is_preservation_first():
    prompt = build_granny_prompt(GRANNY_CHARACTER_SPECS[0]).lower()
    assert "replace only the primary skateboarder" in prompt
    assert "keep the skateboard itself unchanged" in prompt
    assert "camera" in prompt
    assert "do not change the environment" in prompt
    assert "powder-blue floral midi dress" in prompt


def test_preservation_qc_passes_matching_video_metadata():
    source = {
        "width": 1080,
        "height": 1920,
        "duration_seconds": 8.0,
        "fps": 30.0,
        "has_audio": True,
    }
    final = {
        "width": 1080,
        "height": 1920,
        "duration_seconds": 8.08,
        "fps": 30.0,
        "has_audio": True,
    }
    qc = build_preservation_qc(source, final)
    assert qc["structural_pass"] is True
    assert qc["human_review_required"] is True


def test_preservation_qc_rejects_geometry_drift():
    source = {
        "width": 1080,
        "height": 1920,
        "duration_seconds": 8.0,
        "fps": 30.0,
        "has_audio": True,
    }
    final = {
        "width": 720,
        "height": 1280,
        "duration_seconds": 8.0,
        "fps": 30.0,
        "has_audio": True,
    }
    qc = build_preservation_qc(source, final)
    assert qc["resolution_match"] is False
    assert qc["structural_pass"] is False
