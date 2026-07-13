"""add youtube compliance submission package fields

Revision ID: 0022_youtube_compliance_submission_package
Revises: 0021_youtube_audit_readiness
Create Date: 2026-07-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0022_youtube_compliance_submission_package"
down_revision = "0021_youtube_audit_readiness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("youtube_project_compliance") as batch_op:
        batch_op.add_column(sa.Column("application_display_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("product_description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("organization_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("support_contact", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("privacy_policy_url", sa.String(length=2048), nullable=True))
        batch_op.add_column(sa.Column("terms_of_service_url", sa.String(length=2048), nullable=True))
        batch_op.add_column(sa.Column("application_homepage_url", sa.String(length=2048), nullable=True))
        batch_op.add_column(sa.Column("production_oauth_redirect_uri", sa.String(length=2048), nullable=True))
        batch_op.add_column(sa.Column("production_frontend_url", sa.String(length=2048), nullable=True))
        batch_op.add_column(sa.Column("production_api_url", sa.String(length=2048), nullable=True))
        batch_op.add_column(sa.Column("data_retention_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("user_data_deletion_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("token_revocation_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("account_disconnection_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("quota_monitoring_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("incident_response_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("security_contact_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("intended_submission_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by", sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column(
                "human_confirmations_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("youtube_project_compliance") as batch_op:
        batch_op.drop_column("human_confirmations_json")
        batch_op.drop_column("reviewed_by")
        batch_op.drop_column("last_reviewed_at")
        batch_op.drop_column("intended_submission_date")
        batch_op.drop_column("security_contact_summary")
        batch_op.drop_column("incident_response_summary")
        batch_op.drop_column("quota_monitoring_summary")
        batch_op.drop_column("account_disconnection_summary")
        batch_op.drop_column("token_revocation_summary")
        batch_op.drop_column("user_data_deletion_summary")
        batch_op.drop_column("data_retention_summary")
        batch_op.drop_column("production_api_url")
        batch_op.drop_column("production_frontend_url")
        batch_op.drop_column("production_oauth_redirect_uri")
        batch_op.drop_column("application_homepage_url")
        batch_op.drop_column("terms_of_service_url")
        batch_op.drop_column("privacy_policy_url")
        batch_op.drop_column("support_contact")
        batch_op.drop_column("organization_name")
        batch_op.drop_column("product_description")
        batch_op.drop_column("application_display_name")
