from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas.account_settings import AccountDefaultsUpdate
from app.services.pipeline_service import build_account_config, get_default_account


def get_account_defaults(db: Session) -> dict:
    account = get_default_account(db)
    return {
        "account_name": account.name,
        "niche": account.niche,
        "account_config_json": build_account_config(account.account_config_json or {}),
    }


def update_account_defaults(db: Session, payload: AccountDefaultsUpdate) -> dict:
    account = get_default_account(db)
    updates = payload.model_dump(exclude_none=True)
    config = build_account_config(account.account_config_json or {})
    config.update(updates)
    account.account_config_json = build_account_config(config)
    db.commit()
    db.refresh(account)
    return {
        "account_name": account.name,
        "niche": account.niche,
        "account_config_json": account.account_config_json,
    }
