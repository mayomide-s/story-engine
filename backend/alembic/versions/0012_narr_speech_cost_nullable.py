"""allow nullable narration render speech cost

Revision ID: 0012_narr_speech_cost
Revises: 0011_narr_cost_null
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_narr_speech_cost"
down_revision = "0011_narr_cost_null"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("narration_renders", "estimated_speech_cost", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE narration_renders SET estimated_speech_cost = 0.0 WHERE estimated_speech_cost IS NULL")
    op.alter_column("narration_renders", "estimated_speech_cost", existing_type=sa.Float(), nullable=False)
