"""add manual performance winner selection

Revision ID: 0016_performance_winner_selection
Revises: 0015_platform_posts_snapshots
Create Date: 2026-07-11
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016_performance_winner_selection"
down_revision = "0015_platform_posts_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("manual_post_packages") as batch_op:
        batch_op.add_column(sa.Column("winner_platform_post_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("winner_selected_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column(
                "winner_selection_revision",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_foreign_key(
            "fk_manual_post_packages_winner_platform_post_id_platform_posts",
            "platform_posts",
            ["winner_platform_post_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_manual_post_packages_winner_platform_post_id",
            ["winner_platform_post_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("manual_post_packages") as batch_op:
        batch_op.drop_index("ix_manual_post_packages_winner_platform_post_id")
        batch_op.drop_constraint(
            "fk_manual_post_packages_winner_platform_post_id_platform_posts",
            type_="foreignkey",
        )
        batch_op.drop_column("winner_selection_revision")
        batch_op.drop_column("winner_selected_at")
        batch_op.drop_column("winner_platform_post_id")
