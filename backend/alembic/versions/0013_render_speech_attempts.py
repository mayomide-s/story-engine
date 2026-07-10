"""add narration render speech attempt history

Revision ID: 0013_render_speech_hist
Revises: 0012_narr_speech_cost
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_render_speech_hist"
down_revision = "0012_narr_speech_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "narration_renders",
        sa.Column("provider_request_dispatched", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("narration_renders", sa.Column("failure_kind", sa.String(length=50), nullable=True))
    op.add_column("narration_renders", sa.Column("speech_attempts_json", sa.JSON(), nullable=False, server_default="[]"))
    op.execute(
        """
        UPDATE narration_renders
        SET speech_attempts_json = json_build_array(
            json_build_object(
                'attempt_revision', 1,
                'provider_attempt_id', provider_attempt_id,
                'provider_request_id', provider_request_id,
                'provider_request_dispatched', provider_request_dispatched,
                'started_at', paid_call_started_at,
                'completed_at', paid_call_completed_at,
                'speech_provider', speech_provider,
                'speech_model', speech_model,
                'voice', voice,
                'response_format', 'mp3',
                'usage_metadata', COALESCE(usage_metadata_json->'speech', '{}'::json),
                'estimated_cost', estimated_speech_cost,
                'audio_asset_id', audio_asset_id,
                'failure_reason', failure_reason,
                'failure_stage', failure_stage,
                'failure_kind', CASE
                    WHEN failure_stage = 'speech' AND failure_reason LIKE '%unexpected keyword argument%' THEN 'client_configuration'
                    ELSE NULL
                END,
                'uncertain_outcome', paid_call_outcome_uncertain,
                'attempt_result', CASE
                    WHEN audio_asset_id IS NOT NULL THEN 'speech_ready'
                    WHEN status = 'UNAVAILABLE' THEN 'unavailable'
                    WHEN status = 'FAILED' THEN 'failed'
                    ELSE 'queued'
                END
            )
        )
        WHERE provider_attempt_id IS NOT NULL
           OR paid_call_started_at IS NOT NULL
           OR paid_call_completed_at IS NOT NULL
           OR failure_reason IS NOT NULL
           OR audio_asset_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE narration_renders
        SET failure_kind = 'client_configuration',
            provider_request_dispatched = false,
            estimated_speech_cost = NULL
        WHERE failure_stage = 'speech'
          AND failure_reason LIKE '%unexpected keyword argument%'
        """
    )
    op.alter_column("narration_renders", "provider_request_dispatched", server_default=None)
    op.alter_column("narration_renders", "speech_attempts_json", server_default=None)


def downgrade() -> None:
    op.drop_column("narration_renders", "speech_attempts_json")
    op.drop_column("narration_renders", "failure_kind")
    op.drop_column("narration_renders", "provider_request_dispatched")
