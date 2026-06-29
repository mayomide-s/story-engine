"""add idea queue items

Revision ID: 0005_idea_queue
Revises: 0004_review_cfg
Create Date: 2026-06-29 11:45:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005_idea_queue"
down_revision = "0004_review_cfg"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "idea_queue_items" not in existing_tables:
        op.create_table(
            "idea_queue_items",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("account_id", sa.String(length=36), sa.ForeignKey("accounts.id"), nullable=False),
            sa.Column("topic", sa.String(length=255), nullable=False),
            sa.Column("style_preset", sa.String(length=100), nullable=False),
            sa.Column("target_platform", sa.String(length=50), nullable=False),
            sa.Column(
                "priority",
                postgresql.ENUM("LOW", "NORMAL", "HIGH", name="pipelinepriority", create_type=False),
                nullable=False,
            ),
            sa.Column("status", sa.Enum("DRAFT", "READY", "GENERATED", "ARCHIVED", name="ideaqueuestatus"), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("planned_date", sa.DateTime(), nullable=True),
            sa.Column("pipeline_run_id", sa.String(length=36), sa.ForeignKey("pipeline_runs.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "idea_queue_items" in existing_tables:
        op.drop_table("idea_queue_items")
