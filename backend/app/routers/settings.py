from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.account_settings import AccountDefaultsResponse, AccountDefaultsUpdate
from app.services.account_service import get_account_defaults, update_account_defaults
from app.services.access_service import require_app_access

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_app_access)])


@router.get("/account-defaults", response_model=AccountDefaultsResponse)
def read_account_defaults(db: Session = Depends(get_db)):
    return get_account_defaults(db)


@router.patch("/account-defaults", response_model=AccountDefaultsResponse)
def patch_account_defaults(payload: AccountDefaultsUpdate, db: Session = Depends(get_db)):
    return update_account_defaults(db, payload)
