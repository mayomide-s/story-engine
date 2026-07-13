"""add account deletion retention fields

Revision ID: 0023_account_deletion_retention
Revises: 0022_youtube_compliance_submission_package
Create Date: 2026-07-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0023_account_deletion_retention"
down_revision = "0022_youtube_compliance_submission_package"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "account_status",
                sa.String(length=50),
                nullable=False,
                server_default="active",
            )
        )
        batch_op.add_column(sa.Column("deletion_started_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        batch_op.create_check_constraint(
            "ck_accounts_account_status",
            "account_status IN ('active', 'deletion_in_progress', 'deleted')",
        )
        batch_op.create_index("ix_accounts_account_status", ["account_status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_index("ix_accounts_account_status")
        batch_op.drop_constraint("ck_accounts_account_status", type_="check")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("deletion_started_at")
        batch_op.drop_column("account_status")
