"""normalize PostgreSQL defaults after performance learnings

Revision ID: 0018_postgres_migration_compatibility
Revises: 0017_performance_learnings
Create Date: 2026-07-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0018_postgres_migration_compatibility"
down_revision = "0017_performance_learnings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.alter_column(
        "performance_learnings",
        "is_archived",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.false(),
    )


def downgrade() -> None:
    # Intentional no-op: restoring PostgreSQL DEFAULT 0 would recreate the
    # migration defect that this revision corrects.
    return
