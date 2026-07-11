"""allow nullable narration draft cost

Revision ID: 0011_narr_cost_null
Revises: 0010_narr_draft_attempts
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_narr_cost_null"
down_revision = "0010_narr_draft_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("narration_drafts", "estimated_writer_cost", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE narration_drafts SET estimated_writer_cost = 0.0 WHERE estimated_writer_cost IS NULL")
    op.alter_column("narration_drafts", "estimated_writer_cost", existing_type=sa.Float(), nullable=False)
