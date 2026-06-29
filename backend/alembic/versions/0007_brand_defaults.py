"""add run and idea config snapshots

Revision ID: 0007_brand_defaults
Revises: 0006_export_pack
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_brand_defaults"
down_revision = "0006_export_pack"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    pipeline_columns = _column_names("pipeline_runs")
    if "input_config_json" not in pipeline_columns:
        op.add_column("pipeline_runs", sa.Column("input_config_json", sa.JSON(), nullable=True))
        op.execute("UPDATE pipeline_runs SET input_config_json = '{}' WHERE input_config_json IS NULL")

    idea_columns = _column_names("idea_queue_items")
    if "input_config_json" not in idea_columns:
        op.add_column("idea_queue_items", sa.Column("input_config_json", sa.JSON(), nullable=True))
        op.execute("UPDATE idea_queue_items SET input_config_json = '{}' WHERE input_config_json IS NULL")


def downgrade() -> None:
    idea_columns = _column_names("idea_queue_items")
    if "input_config_json" in idea_columns:
        op.drop_column("idea_queue_items", "input_config_json")

    pipeline_columns = _column_names("pipeline_runs")
    if "input_config_json" in pipeline_columns:
        op.drop_column("pipeline_runs", "input_config_json")
