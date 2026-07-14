"""add app sessions for production security hardening

Revision ID: 0024_production_security_sessions
Revises: 0023_account_deletion_retention
Create Date: 2026-07-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_production_security_sessions"
down_revision = "0023_account_deletion_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=128), nullable=False),
        sa.Column("password_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revocation_reason", sa.String(length=100), nullable=True),
        sa.Column("session_metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_app_sessions_account_id_accounts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_app_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_app_sessions_token_hash"),
    )
    op.create_index("ix_app_sessions_account_id", "app_sessions", ["account_id"], unique=False)
    op.create_index("ix_app_sessions_expires_at", "app_sessions", ["expires_at"], unique=False)
    op.create_index("ix_app_sessions_last_used_at", "app_sessions", ["last_used_at"], unique=False)
    op.create_index("ix_app_sessions_revoked_at", "app_sessions", ["revoked_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_app_sessions_revoked_at", table_name="app_sessions")
    op.drop_index("ix_app_sessions_last_used_at", table_name="app_sessions")
    op.drop_index("ix_app_sessions_expires_at", table_name="app_sessions")
    op.drop_index("ix_app_sessions_account_id", table_name="app_sessions")
    op.drop_table("app_sessions")
