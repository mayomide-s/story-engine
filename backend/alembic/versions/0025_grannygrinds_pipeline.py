"""add GrannyGrinds source/edit/review pipeline

Revision ID: 0025_grannygrinds_pipeline
Revises: 0024_production_security_sessions
Create Date: 2026-10-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0025_grannygrinds_pipeline"
down_revision = "0024_production_security_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grannygrind_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_post_url", sa.Text(), nullable=False),
        sa.Column("source_media_url", sa.Text(), nullable=False),
        sa.Column("source_creator_handle", sa.String(length=255), nullable=True),
        sa.Column("source_credit_text", sa.Text(), nullable=True),
        sa.Column("rights_status", sa.String(length=50), server_default="unreviewed", nullable=False),
        sa.Column("granny_key", sa.String(length=50), nullable=False),
        sa.Column("granny_name", sa.String(length=100), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="queued", nullable=False),
        sa.Column("source_storage_key", sa.Text(), nullable=True),
        sa.Column("source_public_url", sa.Text(), nullable=True),
        sa.Column("source_metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("generation_attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("runway_task_id", sa.String(length=255), nullable=True),
        sa.Column("runway_response_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("transformed_storage_key", sa.Text(), nullable=True),
        sa.Column("transformed_public_url", sa.Text(), nullable=True),
        sa.Column("transformed_metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("qc_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("instagram_container_id", sa.String(length=255), nullable=True),
        sa.Column("instagram_media_id", sa.String(length=255), nullable=True),
        sa.Column("instagram_permalink", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','ingesting','submitted','generating','postprocessing','needs_review','approved','rejected','publishing','published','failed')",
            name="ck_grannygrind_jobs_status",
        ),
        sa.CheckConstraint(
            "rights_status IN ('unreviewed','credited','permission_confirmed')",
            name="ck_grannygrind_jobs_rights_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_grannygrind_jobs"),
    )
    op.create_index("ix_grannygrind_jobs_status", "grannygrind_jobs", ["status"], unique=False)
    op.create_index("ix_grannygrind_jobs_created_at", "grannygrind_jobs", ["created_at"], unique=False)
    op.create_index("ix_grannygrind_jobs_granny_key", "grannygrind_jobs", ["granny_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_grannygrind_jobs_granny_key", table_name="grannygrind_jobs")
    op.drop_index("ix_grannygrind_jobs_created_at", table_name="grannygrind_jobs")
    op.drop_index("ix_grannygrind_jobs_status", table_name="grannygrind_jobs")
    op.drop_table("grannygrind_jobs")
