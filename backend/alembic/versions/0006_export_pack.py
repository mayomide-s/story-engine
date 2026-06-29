"""add export pack manual posting fields

Revision ID: 0006_export_pack
Revises: 0005_idea_queue
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_export_pack"
down_revision = "0005_idea_queue"
branch_labels = None
depends_on = None


manual_posting_status = sa.Enum(
    "NOT_POSTED",
    "POSTED_TIKTOK",
    "POSTED_INSTAGRAM",
    "POSTED_YOUTUBE",
    "POSTED_MULTIPLE",
    name="manualpostingstatus",
)


def upgrade() -> None:
    bind = op.get_bind()
    manual_posting_status.create(bind, checkfirst=True)
    op.add_column(
        "manual_post_packages",
        sa.Column(
            "manual_posting_status",
            manual_posting_status,
            nullable=False,
            server_default="NOT_POSTED",
        ),
    )
    op.add_column("manual_post_packages", sa.Column("tiktok_post_url", sa.Text(), nullable=True))
    op.add_column("manual_post_packages", sa.Column("instagram_post_url", sa.Text(), nullable=True))
    op.add_column("manual_post_packages", sa.Column("youtube_post_url", sa.Text(), nullable=True))
    op.alter_column("manual_post_packages", "manual_posting_status", server_default=None)


def downgrade() -> None:
    op.drop_column("manual_post_packages", "youtube_post_url")
    op.drop_column("manual_post_packages", "instagram_post_url")
    op.drop_column("manual_post_packages", "tiktok_post_url")
    op.drop_column("manual_post_packages", "manual_posting_status")
    manual_posting_status.drop(op.get_bind(), checkfirst=True)
