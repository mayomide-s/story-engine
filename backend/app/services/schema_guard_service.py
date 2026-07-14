from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.orm import Session

from app.config import get_settings


def _alembic_config() -> Config:
    backend_root = Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    settings = get_settings()
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def get_expected_schema_revisions() -> list[str]:
    script = ScriptDirectory.from_config(_alembic_config())
    return sorted(script.get_heads())


def get_current_schema_revision(db: Session) -> str | None:
    connection = db.connection()
    context = MigrationContext.configure(connection)
    return context.get_current_revision()


def assert_schema_up_to_date(db: Session) -> None:
    current = get_current_schema_revision(db)
    expected = get_expected_schema_revisions()
    if current not in expected:
        raise RuntimeError(
            "Database schema is not up to date. "
            f"Current revision: {current or 'none'}. Expected head: {', '.join(expected)}."
        )
