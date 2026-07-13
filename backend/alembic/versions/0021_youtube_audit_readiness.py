"""add youtube audit readiness compliance state

Revision ID: 0021_youtube_audit_readiness
Revises: 0020_youtube_publication_execution
Create Date: 2026-07-13
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0021_youtube_audit_readiness"
down_revision = "0020_youtube_publication_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "youtube_project_compliance",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("compliance_status", sa.String(length=50), nullable=False, server_default="private_only"),
        sa.Column("status_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("submission_date", sa.Date(), nullable=True),
        sa.Column("approval_date", sa.Date(), nullable=True),
        sa.Column("case_reference", sa.String(length=255), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("platform = 'youtube'", name="ck_youtube_project_compliance_platform"),
        sa.CheckConstraint(
            "compliance_status IN ('unknown', 'private_only', 'audit_pending', 'audit_approved')",
            name="ck_youtube_project_compliance_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", name="uq_youtube_project_compliance_platform"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO youtube_project_compliance (
                id,
                platform,
                compliance_status,
                status_updated_at,
                created_at,
                updated_at
            ) VALUES (
                :id,
                'youtube',
                'private_only',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        ).bindparams(id=str(uuid.uuid4()))
    )


def downgrade() -> None:
    op.drop_table("youtube_project_compliance")
