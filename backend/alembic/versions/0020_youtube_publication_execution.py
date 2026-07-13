"""add youtube publication execution fields

Revision ID: 0020_youtube_publication_execution
Revises: 0019_publishing_gateway_core
Create Date: 2026-07-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0020_youtube_publication_execution"
down_revision = "0019_publishing_gateway_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("publication_targets") as batch_op:
        batch_op.add_column(sa.Column("actual_visibility", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("provider_upload_status", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("provider_processing_status", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("platform_post_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("upload_bytes_total", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("upload_bytes_sent", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("processing_last_checked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("outcome_confirmed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("worker_claimed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("worker_claim_token", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_publication_targets_platform_post_id_platform_posts",
            "platform_posts",
            ["platform_post_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            "ck_publication_targets_actual_visibility",
            "actual_visibility IS NULL OR actual_visibility IN ('private', 'unlisted', 'public')",
        )
        batch_op.create_check_constraint(
            "ck_publication_targets_upload_bytes_total_non_negative",
            "upload_bytes_total IS NULL OR upload_bytes_total >= 0",
        )
        batch_op.create_check_constraint(
            "ck_publication_targets_upload_bytes_sent_non_negative",
            "upload_bytes_sent IS NULL OR upload_bytes_sent >= 0",
        )
        batch_op.create_unique_constraint(
            "uq_publication_targets_platform_post_id",
            ["platform_post_id"],
        )
        batch_op.create_index(
            "ix_publication_targets_platform_post_id",
            ["platform_post_id"],
            unique=False,
        )


def downgrade() -> None:
    dialect_name = op.get_bind().dialect.name
    with op.batch_alter_table("publication_targets") as batch_op:
        batch_op.drop_index("ix_publication_targets_platform_post_id")
        batch_op.drop_constraint("uq_publication_targets_platform_post_id", type_="unique")
        batch_op.drop_constraint("ck_publication_targets_upload_bytes_sent_non_negative", type_="check")
        batch_op.drop_constraint("ck_publication_targets_upload_bytes_total_non_negative", type_="check")
        batch_op.drop_constraint("ck_publication_targets_actual_visibility", type_="check")
        if dialect_name != "sqlite":
            batch_op.drop_constraint(
                "fk_publication_targets_platform_post_id_platform_posts",
                type_="foreignkey",
            )
        batch_op.drop_column("last_attempt_at")
        batch_op.drop_column("worker_claim_token")
        batch_op.drop_column("worker_claimed_at")
        batch_op.drop_column("outcome_confirmed_at")
        batch_op.drop_column("processing_last_checked_at")
        batch_op.drop_column("upload_bytes_sent")
        batch_op.drop_column("upload_bytes_total")
        batch_op.drop_column("platform_post_id")
        batch_op.drop_column("provider_processing_status")
        batch_op.drop_column("provider_upload_status")
        batch_op.drop_column("actual_visibility")
