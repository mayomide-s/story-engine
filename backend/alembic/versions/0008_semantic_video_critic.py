"""add semantic video critic persistence

Revision ID: 0008_semantic_video_critic
Revises: 0007_brand_defaults
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_semantic_video_critic"
down_revision = "0007_brand_defaults"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def upgrade() -> None:
    tables = _table_names()
    if "story_adherence_reviews" not in tables:
        op.create_table(
            "story_adherence_reviews",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
            sa.Column("video_id", sa.String(length=36), sa.ForeignKey("videos.id"), nullable=False),
            sa.Column("critic_version", sa.String(length=100), nullable=False),
            sa.Column("model", sa.String(length=100), nullable=False),
            sa.Column("review_status", sa.String(length=50), nullable=False),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("criteria_json", sa.JSON(), nullable=False),
            sa.Column("explanation", sa.Text(), nullable=False),
            sa.Column("sampled_frames_json", sa.JSON(), nullable=False),
            sa.Column("failure_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("video_id", "critic_version", name="uq_story_adherence_video_version"),
        )
    if "story_adherence_human_reviews" not in tables:
        op.create_table(
            "story_adherence_human_reviews",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=False),
            sa.Column("story_adherence_review_id", sa.String(length=36), sa.ForeignKey("story_adherence_reviews.id"), nullable=True),
            sa.Column("decision", sa.String(length=50), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("pipeline_run_id"),
        )


def downgrade() -> None:
    tables = _table_names()
    if "story_adherence_human_reviews" in tables:
        op.drop_table("story_adherence_human_reviews")
    if "story_adherence_reviews" in tables:
        op.drop_table("story_adherence_reviews")
