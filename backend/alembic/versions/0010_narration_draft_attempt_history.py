"""add immutable narration draft attempt history

Revision ID: 0010_narr_draft_attempts
Revises: 0009_narration_workflow
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_narr_draft_attempts"
down_revision = "0009_narration_workflow"
branch_labels = None
depends_on = None


def _table_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _table_columns("narration_drafts")
    if "attempts_json" not in columns:
        op.add_column("narration_drafts", sa.Column("attempts_json", sa.JSON(), nullable=False, server_default="[]"))
        op.execute(
            """
            UPDATE narration_drafts
            SET attempts_json = json_build_array(
                json_build_object(
                    'generation_revision', generation_revision,
                    'provider_attempt_id', provider_attempt_id,
                    'provider_request_id', provider_request_id,
                    'started_at', paid_call_started_at,
                    'completed_at', paid_call_completed_at,
                    'writer_provider', writer_provider,
                    'writer_model', writer_model,
                    'writer_prompt_version', writer_prompt_version,
                    'usage_metadata', usage_metadata_json,
                    'estimated_cost', estimated_writer_cost,
                    'attempt_output', COALESCE(usage_metadata_json->'attempt_output', '{}'::json),
                    'validation_result',
                        CASE
                            WHEN paid_call_completed_at IS NOT NULL AND failure_reason IS NOT NULL THEN 'failed_validation'
                            WHEN writer_completed_at IS NOT NULL THEN 'ready'
                            WHEN paid_call_started_at IS NOT NULL THEN 'started'
                            ELSE 'not_started'
                        END,
                    'validation_error', usage_metadata_json->>'validation_error',
                    'failure_reason', failure_reason,
                    'failure_stage', failure_stage,
                    'uncertain_outcome', paid_call_outcome_uncertain
                )
            )
            WHERE provider_attempt_id IS NOT NULL
               OR paid_call_started_at IS NOT NULL
               OR paid_call_completed_at IS NOT NULL
               OR failure_reason IS NOT NULL
               OR COALESCE(usage_metadata_json::text, '{}') <> '{}'
            """
        )
        op.alter_column("narration_drafts", "attempts_json", server_default=None)


def downgrade() -> None:
    columns = _table_columns("narration_drafts")
    if "attempts_json" in columns:
        op.drop_column("narration_drafts", "attempts_json")
