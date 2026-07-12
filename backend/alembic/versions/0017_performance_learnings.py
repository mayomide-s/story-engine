"""add performance learnings

Revision ID: 0017_performance_learnings
Revises: 0016_performance_winner_selection
Create Date: 2026-07-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0017_performance_learnings"
down_revision = "0016_performance_winner_selection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "performance_learnings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=36), nullable=False),
        sa.Column("platform_post_id", sa.String(length=36), nullable=True),
        sa.Column("learning_type", sa.String(length=50), nullable=False),
        sa.Column("observation", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "learning_type IN ('worked', 'did_not_work', 'next_test', 'observation')",
            name="ck_performance_learnings_learning_type",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["pipeline_runs.id"],
            name="fk_performance_learnings_pipeline_run_id_pipeline_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["platform_post_id"],
            ["platform_posts.id"],
            name="fk_performance_learnings_platform_post_id_platform_posts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_performance_learnings_pipeline_run_id", "performance_learnings", ["pipeline_run_id"], unique=False)
    op.create_index("ix_performance_learnings_platform_post_id", "performance_learnings", ["platform_post_id"], unique=False)
    op.create_index("ix_performance_learnings_learning_type", "performance_learnings", ["learning_type"], unique=False)
    op.create_index(
        "ix_performance_learnings_run_archived_updated",
        "performance_learnings",
        ["pipeline_run_id", "is_archived", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_performance_learnings_run_archived_updated", table_name="performance_learnings")
    op.drop_index("ix_performance_learnings_learning_type", table_name="performance_learnings")
    op.drop_index("ix_performance_learnings_platform_post_id", table_name="performance_learnings")
    op.drop_index("ix_performance_learnings_pipeline_run_id", table_name="performance_learnings")
    op.drop_table("performance_learnings")
