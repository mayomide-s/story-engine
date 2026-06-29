"""add video requested duration

Revision ID: 0003_req_duration
Revises: 0002_add_video_submitting_status
Create Date: 2026-06-29 07:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_req_duration"
down_revision = "0002_add_video_submitting_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("videos")}

    if "requested_duration_seconds" not in existing_columns:
        op.add_column("videos", sa.Column("requested_duration_seconds", sa.Integer(), nullable=True))
        op.execute("UPDATE videos SET requested_duration_seconds = duration_seconds WHERE requested_duration_seconds IS NULL")
        op.alter_column("videos", "requested_duration_seconds", nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("videos")}

    if "requested_duration_seconds" in existing_columns:
        op.drop_column("videos", "requested_duration_seconds")
