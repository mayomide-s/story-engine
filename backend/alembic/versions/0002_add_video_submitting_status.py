"""add video submitting status

Revision ID: 0002_add_video_submitting_status
Revises: 0001_initial
Create Date: 2026-06-29 06:15:00
"""

from alembic import op


revision = "0002_add_video_submitting_status"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE videostatus ADD VALUE IF NOT EXISTS 'SUBMITTING'")


def downgrade() -> None:
    pass
