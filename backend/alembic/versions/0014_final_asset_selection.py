"""add manual package final asset selection

Revision ID: 0014_final_asset_select
Revises: 0013_render_speech_hist
Create Date: 2026-07-10
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0014_final_asset_select"
down_revision = "0013_render_speech_hist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manual_post_packages") as batch_op:
        batch_op.add_column(sa.Column("final_asset_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("final_asset_source", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("final_narration_render_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column("final_asset_selection_revision", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.add_column(sa.Column("final_asset_selected_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("final_asset_metadata_json", sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            "fk_manual_post_packages_final_asset_id_assets",
            "assets",
            ["final_asset_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_manual_post_packages_final_narration_render_id",
            "narration_renders",
            ["final_narration_render_id"],
            ["id"],
        )

    conn = op.get_bind()
    packages = conn.execute(
        sa.text("SELECT id, video_id, created_at, updated_at FROM manual_post_packages")
    ).mappings().all()
    source_metadata = json.dumps(
        {
            "narration_transcript": None,
            "caption_cues": [],
            "ai_voice_disclosure": None,
            "voice_is_ai_generated": False,
            "narration_render_status": None,
            "caption_version": None,
            "render_version": None,
        }
    )
    for package in packages:
        asset_id = conn.execute(
            sa.text(
                """
                SELECT assets.id
                FROM assets
                JOIN videos ON videos.pipeline_run_id = assets.pipeline_run_id
                WHERE videos.id = :video_id
                  AND assets.asset_type = 'video_mp4'
                ORDER BY assets.created_at DESC
                LIMIT 1
                """
            ),
            {"video_id": package["video_id"]},
        ).scalar()
        conn.execute(
            sa.text(
                """
                UPDATE manual_post_packages
                SET final_asset_id = COALESCE(final_asset_id, :asset_id),
                    final_asset_source = COALESCE(final_asset_source, 'source_video'),
                    final_asset_selection_revision = COALESCE(final_asset_selection_revision, 1),
                    final_asset_selected_at = COALESCE(final_asset_selected_at, updated_at, created_at),
                    final_asset_metadata_json = COALESCE(final_asset_metadata_json, :metadata_json)
                WHERE id = :package_id
                """
            ),
            {
                "package_id": package["id"],
                "asset_id": asset_id,
                "metadata_json": source_metadata,
            },
        )

    with op.batch_alter_table("manual_post_packages") as batch_op:
        batch_op.alter_column("final_asset_selection_revision", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("manual_post_packages") as batch_op:
        batch_op.drop_constraint("fk_manual_post_packages_final_narration_render_id", type_="foreignkey")
        batch_op.drop_constraint("fk_manual_post_packages_final_asset_id_assets", type_="foreignkey")
        batch_op.drop_column("final_asset_metadata_json")
        batch_op.drop_column("final_asset_selected_at")
        batch_op.drop_column("final_asset_selection_revision")
        batch_op.drop_column("final_narration_render_id")
        batch_op.drop_column("final_asset_source")
        batch_op.drop_column("final_asset_id")
