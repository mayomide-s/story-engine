"""add publishing gateway foundation tables

Revision ID: 0019_publishing_gateway_core
Revises: 0018_postgres_migration_compatibility
Create Date: 2026-07-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_publishing_gateway_core"
down_revision = "0018_postgres_migration_compatibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "social_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("external_account_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("token_cipher_version", sa.String(length=20), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("granted_scopes_json", sa.JSON(), nullable=False),
        sa.Column("connection_status", sa.String(length=50), nullable=False),
        sa.Column("provider_metadata_json", sa.JSON(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "connection_status IN ('active', 'expired', 'revoked', 'error', 'disconnected')",
            name="ck_social_connections_connection_status",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "platform",
            "external_account_id",
            name="uq_social_connections_account_platform_external",
        ),
    )
    op.create_index(
        "ix_social_connections_account_platform",
        "social_connections",
        ["account_id", "platform"],
        unique=False,
    )
    op.create_index("ix_social_connections_status", "social_connections", ["connection_status"], unique=False)
    op.create_index(
        "ix_social_connections_platform_default",
        "social_connections",
        ["platform", "is_default"],
        unique=False,
    )

    op.create_table(
        "oauth_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("return_path", sa.String(length=1024), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash", name="uq_oauth_states_state_hash"),
    )
    op.create_index("ix_oauth_states_expires_at", "oauth_states", ["expires_at"], unique=False)

    op.create_table(
        "publication_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=36), nullable=False),
        sa.Column("manual_post_package_id", sa.String(length=36), nullable=False),
        sa.Column("final_asset_id", sa.String(length=36), nullable=False),
        sa.Column("final_asset_selection_revision", sa.Integer(), nullable=False),
        sa.Column("final_asset_source", sa.String(length=50), nullable=False),
        sa.Column("final_asset_sha256", sa.String(length=64), nullable=False),
        sa.Column("final_asset_metadata_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'ready', 'approved', 'active', 'published', 'partially_published', 'failed', 'cancelled')",
            name="ck_publication_jobs_status",
        ),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["manual_post_package_id"], ["manual_post_packages.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["final_asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_publication_jobs_pipeline_run_id", "publication_jobs", ["pipeline_run_id"], unique=False)
    op.create_index("ix_publication_jobs_status", "publication_jobs", ["status"], unique=False)
    op.create_index("ix_publication_jobs_created_at", "publication_jobs", ["created_at"], unique=False)

    op.create_table(
        "publication_targets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("publication_job_id", sa.String(length=36), nullable=False),
        sa.Column("social_connection_id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("provider_upload_uri_encrypted", sa.Text(), nullable=True),
        sa.Column("provider_submission_id", sa.String(length=255), nullable=True),
        sa.Column("provider_media_id", sa.String(length=255), nullable=True),
        sa.Column("public_post_url", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('pending', 'validating', 'queued', 'uploading', 'processing', 'uploaded_private', 'published', 'retryable_failure', 'permanent_failure', 'outcome_uncertain', 'cancelled')",
            name="ck_publication_targets_state",
        ),
        sa.CheckConstraint(
            "visibility IN ('private', 'unlisted', 'public')",
            name="ck_publication_targets_visibility",
        ),
        sa.ForeignKeyConstraint(["publication_job_id"], ["publication_jobs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["social_connection_id"], ["social_connections.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "publication_job_id",
            "platform",
            "social_connection_id",
            name="uq_publication_targets_job_platform_connection",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_publication_targets_idempotency_key"),
    )
    op.create_index(
        "ix_publication_targets_publication_job_id",
        "publication_targets",
        ["publication_job_id"],
        unique=False,
    )
    op.create_index("ix_publication_targets_state", "publication_targets", ["state"], unique=False)
    op.create_index("ix_publication_targets_next_poll_at", "publication_targets", ["next_poll_at"], unique=False)
    op.create_index(
        "ix_publication_targets_provider_submission_id",
        "publication_targets",
        ["provider_submission_id"],
        unique=False,
    )
    op.create_index(
        "ix_publication_targets_provider_media_id",
        "publication_targets",
        ["provider_media_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_publication_targets_provider_media_id", table_name="publication_targets")
    op.drop_index("ix_publication_targets_provider_submission_id", table_name="publication_targets")
    op.drop_index("ix_publication_targets_next_poll_at", table_name="publication_targets")
    op.drop_index("ix_publication_targets_state", table_name="publication_targets")
    op.drop_index("ix_publication_targets_publication_job_id", table_name="publication_targets")
    op.drop_table("publication_targets")

    op.drop_index("ix_publication_jobs_created_at", table_name="publication_jobs")
    op.drop_index("ix_publication_jobs_status", table_name="publication_jobs")
    op.drop_index("ix_publication_jobs_pipeline_run_id", table_name="publication_jobs")
    op.drop_table("publication_jobs")

    op.drop_index("ix_oauth_states_expires_at", table_name="oauth_states")
    op.drop_table("oauth_states")

    op.drop_index("ix_social_connections_platform_default", table_name="social_connections")
    op.drop_index("ix_social_connections_status", table_name="social_connections")
    op.drop_index("ix_social_connections_account_platform", table_name="social_connections")
    op.drop_table("social_connections")
