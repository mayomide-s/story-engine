"""add narration draft and render persistence

Revision ID: 0009_narration_workflow
Revises: 0008_semantic_video_critic
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_narration_workflow"
down_revision = "0008_semantic_video_critic"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def upgrade() -> None:
    tables = _table_names()
    if "narration_drafts" not in tables:
        op.create_table(
            "narration_drafts",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
            sa.Column("source_video_id", sa.String(length=36), sa.ForeignKey("videos.id"), nullable=False),
            sa.Column("narration_version", sa.String(length=100), nullable=False),
            sa.Column("status", sa.Enum("QUEUED", "WRITER_GENERATING", "READY", "FAILED", "UNAVAILABLE", name="narrationdraftstatus"), nullable=False),
            sa.Column("has_valid_content", sa.Boolean(), nullable=False),
            sa.Column("writer_task_id", sa.String(length=255), nullable=True),
            sa.Column("writer_started_at", sa.DateTime(), nullable=True),
            sa.Column("writer_completed_at", sa.DateTime(), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("failure_stage", sa.String(length=50), nullable=True),
            sa.Column("generation_revision", sa.Integer(), nullable=False),
            sa.Column("provider_attempt_id", sa.String(length=255), nullable=True),
            sa.Column("paid_call_started_at", sa.DateTime(), nullable=True),
            sa.Column("paid_call_completed_at", sa.DateTime(), nullable=True),
            sa.Column("provider_request_id", sa.String(length=255), nullable=True),
            sa.Column("paid_call_outcome_uncertain", sa.Boolean(), nullable=False),
            sa.Column("writer_provider", sa.String(length=100), nullable=False),
            sa.Column("writer_model", sa.String(length=100), nullable=False),
            sa.Column("writer_prompt_version", sa.String(length=100), nullable=False),
            sa.Column("script_json", sa.JSON(), nullable=False),
            sa.Column("full_spoken_text", sa.Text(), nullable=False),
            sa.Column("estimated_word_count", sa.Integer(), nullable=False),
            sa.Column("source_duration_seconds", sa.Float(), nullable=False),
            sa.Column("estimated_writer_cost", sa.Float(), nullable=False),
            sa.Column("usage_metadata_json", sa.JSON(), nullable=False),
            sa.Column("manually_modified", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("pipeline_run_id", "source_video_id", "narration_version", name="uq_narration_draft_run_source_version"),
        )
    if "narration_renders" not in tables:
        op.create_table(
            "narration_renders",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
            sa.Column("narration_draft_id", sa.String(length=36), sa.ForeignKey("narration_drafts.id"), nullable=False),
            sa.Column("source_video_id", sa.String(length=36), sa.ForeignKey("videos.id"), nullable=False),
            sa.Column("narration_version", sa.String(length=100), nullable=False),
            sa.Column("status", sa.Enum("QUEUED", "SPEECH_GENERATING", "SPEECH_READY", "COMPOSING", "PENDING_REVIEW", "APPROVED", "NEEDS_REVISION", "REJECTED", "FAILED", "UNAVAILABLE", name="narrationrenderstatus"), nullable=False),
            sa.Column("worker_task_id", sa.String(length=255), nullable=True),
            sa.Column("speech_started_at", sa.DateTime(), nullable=True),
            sa.Column("speech_completed_at", sa.DateTime(), nullable=True),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("failure_stage", sa.String(length=50), nullable=True),
            sa.Column("provider_attempt_id", sa.String(length=255), nullable=True),
            sa.Column("paid_call_started_at", sa.DateTime(), nullable=True),
            sa.Column("paid_call_completed_at", sa.DateTime(), nullable=True),
            sa.Column("provider_request_id", sa.String(length=255), nullable=True),
            sa.Column("paid_call_outcome_uncertain", sa.Boolean(), nullable=False),
            sa.Column("writer_provider", sa.String(length=100), nullable=False),
            sa.Column("writer_model", sa.String(length=100), nullable=False),
            sa.Column("writer_prompt_version", sa.String(length=100), nullable=False),
            sa.Column("speech_provider", sa.String(length=100), nullable=False),
            sa.Column("speech_model", sa.String(length=100), nullable=False),
            sa.Column("voice", sa.String(length=100), nullable=False),
            sa.Column("voice_is_ai_generated", sa.Boolean(), nullable=False),
            sa.Column("caption_version", sa.String(length=100), nullable=False),
            sa.Column("render_version", sa.String(length=100), nullable=False),
            sa.Column("script_json", sa.JSON(), nullable=False),
            sa.Column("full_spoken_text", sa.Text(), nullable=False),
            sa.Column("caption_cues_json", sa.JSON(), nullable=False),
            sa.Column("caption_source_json", sa.JSON(), nullable=False),
            sa.Column("source_duration_seconds", sa.Float(), nullable=False),
            sa.Column("usable_narration_window_seconds", sa.Float(), nullable=True),
            sa.Column("original_audio_duration_seconds", sa.Float(), nullable=True),
            sa.Column("final_audio_duration_seconds", sa.Float(), nullable=True),
            sa.Column("applied_atempo_factor", sa.Float(), nullable=True),
            sa.Column("narration_duration_seconds", sa.Float(), nullable=True),
            sa.Column("idempotency_key", sa.String(length=255), nullable=False),
            sa.Column("usage_metadata_json", sa.JSON(), nullable=False),
            sa.Column("estimated_writer_cost", sa.Float(), nullable=False),
            sa.Column("estimated_speech_cost", sa.Float(), nullable=False),
            sa.Column("audio_asset_id", sa.String(length=36), sa.ForeignKey("assets.id"), nullable=True),
            sa.Column("caption_asset_id", sa.String(length=36), sa.ForeignKey("assets.id"), nullable=True),
            sa.Column("rendered_video_asset_id", sa.String(length=36), sa.ForeignKey("assets.id"), nullable=True),
            sa.Column("human_review_status", sa.String(length=50), nullable=True),
            sa.Column("human_review_notes", sa.Text(), nullable=True),
            sa.Column("human_reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("story_approval_status_snapshot", sa.String(length=50), nullable=False),
            sa.Column("story_approval_source_snapshot", sa.String(length=50), nullable=False),
            sa.Column("ai_voice_disclosure", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_narration_render_idempotency_key"),
        )


def downgrade() -> None:
    tables = _table_names()
    if "narration_renders" in tables:
        op.drop_table("narration_renders")
    if "narration_drafts" in tables:
        op.drop_table("narration_drafts")
