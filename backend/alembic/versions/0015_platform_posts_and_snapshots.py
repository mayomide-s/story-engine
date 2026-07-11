"""add platform posts and performance snapshots

Revision ID: 0015_platform_posts_snapshots
Revises: 0014_final_asset_select
Create Date: 2026-07-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015_platform_posts_snapshots"
down_revision = "0014_final_asset_select"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_posts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=36), nullable=False),
        sa.Column("manual_post_package_id", sa.String(length=36), nullable=False),
        sa.Column("final_asset_id", sa.String(length=36), nullable=False),
        sa.Column("final_asset_source", sa.String(length=50), nullable=False),
        sa.Column("platform", sa.Enum("tiktok", "instagram", "youtube", "other", name="performanceplatform", native_enum=False), nullable=False),
        sa.Column("post_url", sa.String(length=2048), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("custom_platform_name", sa.String(length=80), nullable=True),
        sa.Column("final_narration_render_id", sa.String(length=36), nullable=True),
        sa.Column("final_asset_selection_revision", sa.Integer(), nullable=True),
        sa.Column("final_asset_metadata_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(platform = 'other' AND custom_platform_name IS NOT NULL AND length(trim(custom_platform_name)) > 0) "
            "OR (platform != 'other' AND custom_platform_name IS NULL)",
            name="ck_platform_posts_custom_platform_name",
        ),
        sa.ForeignKeyConstraint(["final_asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["final_narration_render_id"], ["narration_renders.id"]),
        sa.ForeignKeyConstraint(["manual_post_package_id"], ["manual_post_packages.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "post_url", name="uq_platform_posts_platform_post_url"),
    )
    op.create_index("ix_platform_posts_pipeline_run_id", "platform_posts", ["pipeline_run_id"], unique=False)
    op.create_index("ix_platform_posts_manual_post_package_id", "platform_posts", ["manual_post_package_id"], unique=False)
    op.create_index("ix_platform_posts_platform", "platform_posts", ["platform"], unique=False)
    op.create_index("ix_platform_posts_posted_at", "platform_posts", ["posted_at"], unique=False)
    op.create_index("ix_platform_posts_final_asset_id", "platform_posts", ["final_asset_id"], unique=False)

    op.create_table(
        "performance_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("platform_post_id", sa.String(length=36), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("likes", sa.BigInteger(), nullable=True),
        sa.Column("comments", sa.BigInteger(), nullable=True),
        sa.Column("shares", sa.BigInteger(), nullable=True),
        sa.Column("saves", sa.BigInteger(), nullable=True),
        sa.Column("average_watch_time_seconds", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("completion_rate", sa.Numeric(precision=6, scale=5), nullable=True),
        sa.Column("followers_gained", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("views IS NULL OR views >= 0", name="ck_performance_snapshots_views_non_negative"),
        sa.CheckConstraint("likes IS NULL OR likes >= 0", name="ck_performance_snapshots_likes_non_negative"),
        sa.CheckConstraint("comments IS NULL OR comments >= 0", name="ck_performance_snapshots_comments_non_negative"),
        sa.CheckConstraint("shares IS NULL OR shares >= 0", name="ck_performance_snapshots_shares_non_negative"),
        sa.CheckConstraint("saves IS NULL OR saves >= 0", name="ck_performance_snapshots_saves_non_negative"),
        sa.CheckConstraint(
            "average_watch_time_seconds IS NULL OR average_watch_time_seconds >= 0",
            name="ck_performance_snapshots_watch_time_non_negative",
        ),
        sa.CheckConstraint(
            "completion_rate IS NULL OR (completion_rate >= 0 AND completion_rate <= 1)",
            name="ck_performance_snapshots_completion_rate_range",
        ),
        sa.CheckConstraint(
            "followers_gained IS NULL OR followers_gained >= 0",
            name="ck_performance_snapshots_followers_gained_non_negative",
        ),
        sa.ForeignKeyConstraint(["platform_post_id"], ["platform_posts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_post_id", "captured_at", name="uq_performance_snapshots_post_captured_at"),
    )
    op.create_index(
        "ix_performance_snapshots_post_captured_at",
        "performance_snapshots",
        ["platform_post_id", "captured_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_performance_snapshots_post_captured_at", table_name="performance_snapshots")
    op.drop_table("performance_snapshots")
    op.drop_index("ix_platform_posts_final_asset_id", table_name="platform_posts")
    op.drop_index("ix_platform_posts_posted_at", table_name="platform_posts")
    op.drop_index("ix_platform_posts_platform", table_name="platform_posts")
    op.drop_index("ix_platform_posts_manual_post_package_id", table_name="platform_posts")
    op.drop_index("ix_platform_posts_pipeline_run_id", table_name="platform_posts")
    op.drop_table("platform_posts")
    sa.Enum(name="performanceplatform").drop(op.get_bind(), checkfirst=True)
