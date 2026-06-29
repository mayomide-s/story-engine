"""add review config fields

Revision ID: 0004_review_cfg
Revises: 0003_req_duration
Create Date: 2026-06-29 10:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_review_cfg"
down_revision = "0003_req_duration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("pipeline_runs")}

    if "style_preset" not in existing_columns:
        op.add_column("pipeline_runs", sa.Column("style_preset", sa.String(length=100), nullable=True))
        op.execute("UPDATE pipeline_runs SET style_preset = 'clean_3d_cartoon' WHERE style_preset IS NULL")
        op.alter_column("pipeline_runs", "style_preset", nullable=False)
    if "prompt_override" not in existing_columns:
        op.add_column("pipeline_runs", sa.Column("prompt_override", sa.Text(), nullable=True))
    if "caption_override" not in existing_columns:
        op.add_column("pipeline_runs", sa.Column("caption_override", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("pipeline_runs")}

    if "caption_override" in existing_columns:
        op.drop_column("pipeline_runs", "caption_override")
    if "prompt_override" in existing_columns:
        op.drop_column("pipeline_runs", "prompt_override")
    if "style_preset" in existing_columns:
        op.drop_column("pipeline_runs", "style_preset")
