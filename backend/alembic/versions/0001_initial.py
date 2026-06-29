"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-28
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("niche", sa.String(length=255), nullable=False),
        sa.Column("account_config_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("account_id", sa.String(length=36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("auto_mode", sa.Boolean(), nullable=False),
        sa.Column("style_preset", sa.String(length=100), nullable=False),
        sa.Column("priority", sa.Enum("LOW", "NORMAL", "HIGH", name="pipelinepriority"), nullable=False),
        sa.Column("current_stage", sa.Enum("IDEA_GENERATION", "SCRIPT_GENERATION", "STORYBOARD_GENERATION", "VIDEO_PROMPT_BUILD", "VIDEO_GENERATION_SUBMIT", "VIDEO_GENERATION_POLLING", "ASSET_UPLOAD", "QUALITY_CHECK", "MANUAL_PACKAGE_CREATION", "COMPLETED", name="pipelinestage"), nullable=False),
        sa.Column("status", sa.Enum("QUEUED", "RUNNING", "AWAITING_REVIEW", "NEEDS_REVIEW", "COMPLETED", "FAILED", "CANCELLED", name="pipelinestatus"), nullable=False),
        sa.Column("idea_id", sa.String(length=36), nullable=True),
        sa.Column("script_id", sa.String(length=36), nullable=True),
        sa.Column("storyboard_id", sa.String(length=36), nullable=True),
        sa.Column("video_id", sa.String(length=36), nullable=True),
        sa.Column("manual_post_package_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("retry_after", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("prompt_override", sa.Text(), nullable=True),
        sa.Column("caption_override", sa.Text(), nullable=True),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
        sa.Column("resumed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "content_ideas",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("concept", sa.Text(), nullable=False),
        sa.Column("format", sa.String(length=100), nullable=False),
        sa.Column("difficulty", sa.String(length=50), nullable=False),
        sa.Column("trend_score", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "scripts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("script_json", sa.JSON(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "storyboards",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("frames_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "videos",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("provider_job_id", sa.String(length=255), nullable=True),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("provider_status", sa.String(length=100), nullable=True),
        sa.Column("provider_response_json", sa.JSON(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("QUEUED", "GENERATING", "COMPLETED", "FAILED", "PENDING_REVIEW", "APPROVED", "REJECTED", name="videostatus"), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=20), nullable=False),
        sa.Column("requested_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("review_status", sa.String(length=50), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("retry_after", sa.DateTime(), nullable=True),
        sa.Column("max_poll_attempts", sa.Integer(), nullable=False),
        sa.Column("poll_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("provider_timeout_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "manual_post_packages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("video_id", sa.String(length=36), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("hashtags_json", sa.JSON(), nullable=False),
        sa.Column("target_platforms_json", sa.JSON(), nullable=False),
        sa.Column("platform_variants_json", sa.JSON(), nullable=False),
        sa.Column("checklist_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.Enum("DRAFT", "READY", "ARCHIVED", name="manualpackagestatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "pipeline_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("asset_type", sa.String(length=100), nullable=False),
        sa.Column("created_by_stage", sa.String(length=100), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("public_url", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "prompt_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("output_text", sa.Text(), nullable=False),
        sa.Column("token_usage_json", sa.JSON(), nullable=False),
        sa.Column("cost_estimate", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "generation_costs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("stage", sa.String(length=100), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False),
        sa.Column("credits_used", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "quality_checks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("video_id", sa.String(length=36), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("checks_json", sa.JSON(), nullable=False),
        sa.Column("llm_critique", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "idea_queue_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("account_id", sa.String(length=36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("style_preset", sa.String(length=100), nullable=False),
        sa.Column("target_platform", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.Enum("LOW", "NORMAL", "HIGH", name="pipelinepriority"), nullable=False),
        sa.Column("status", sa.Enum("DRAFT", "READY", "GENERATED", "ARCHIVED", name="ideaqueuestatus"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("planned_date", sa.DateTime(), nullable=True),
        sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_foreign_key(None, "pipeline_runs", "content_ideas", ["idea_id"], ["id"])
    op.create_foreign_key(None, "pipeline_runs", "scripts", ["script_id"], ["id"])
    op.create_foreign_key(None, "pipeline_runs", "storyboards", ["storyboard_id"], ["id"])
    op.create_foreign_key(None, "pipeline_runs", "videos", ["video_id"], ["id"])
    op.create_foreign_key(None, "pipeline_runs", "manual_post_packages", ["manual_post_package_id"], ["id"])


def downgrade() -> None:
    op.drop_table("quality_checks")
    op.drop_table("idea_queue_items")
    op.drop_table("generation_costs")
    op.drop_table("prompt_logs")
    op.drop_table("assets")
    op.drop_table("pipeline_events")
    op.drop_table("manual_post_packages")
    op.drop_table("videos")
    op.drop_table("storyboards")
    op.drop_table("scripts")
    op.drop_table("content_ideas")
    op.drop_table("pipeline_runs")
    op.drop_table("accounts")
