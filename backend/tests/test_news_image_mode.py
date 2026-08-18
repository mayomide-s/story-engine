from app.schemas.pipeline_runs import PipelineRunCreate
from app.services.pipeline_service import build_account_config, build_idea_input_config, build_run_input_config


def test_pipeline_run_content_type_defaults_to_coding_video():
    payload = PipelineRunCreate(topic="OpenAI revenue")

    assert payload.content_type == "coding_video"
    config = build_run_input_config(build_account_config(), payload)
    assert config["content_type"] == "coding_video"


def test_pipeline_run_accepts_news_image_content_type():
    payload = PipelineRunCreate(
        topic="OpenAI revenue",
        content_type="news_image",
        target_platforms=["instagram"],
    )

    config = build_run_input_config(build_account_config(), payload)
    assert config["content_type"] == "news_image"
    assert config["target_platforms"] == ["instagram"]


def test_idea_input_config_preserves_news_image_content_type():
    config = build_idea_input_config(
        build_account_config(),
        {"content_type": "news_image", "target_platforms": ["instagram"]},
    )

    assert config["content_type"] == "news_image"
