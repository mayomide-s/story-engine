from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.account_settings import (
    AccountDefaultsResponse,
    AccountDefaultsUpdate,
    AccountDeletionExecuteRequest,
    AccountDeletionPreviewResponse,
    AccountDeletionResultResponse,
    AccountDeletionValidateRequest,
    AccountDeletionValidationResponse,
    RetentionReportResponse,
)
from app.services.account_deletion_service import (
    AccountDeletionConflictError,
    build_account_deletion_preview,
    build_retention_report,
    execute_account_deletion,
    validate_account_deletion,
)
from app.services.account_service import get_account_defaults, update_account_defaults
from app.services.access_service import require_app_access

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Depends(require_app_access)])


@router.get("/account-defaults", response_model=AccountDefaultsResponse)
def read_account_defaults(db: Session = Depends(get_db)):
    return get_account_defaults(db)


@router.patch("/account-defaults", response_model=AccountDefaultsResponse)
def patch_account_defaults(payload: AccountDefaultsUpdate, db: Session = Depends(get_db)):
    return update_account_defaults(db, payload)


@router.get("/account-deletion/preview", response_model=AccountDeletionPreviewResponse)
def read_account_deletion_preview(db: Session = Depends(get_db)):
    return AccountDeletionPreviewResponse(**build_account_deletion_preview(db))


@router.post("/account-deletion/validate", response_model=AccountDeletionValidationResponse)
def validate_account_deletion_route(payload: AccountDeletionValidateRequest, db: Session = Depends(get_db)):
    try:
        return AccountDeletionValidationResponse(
            **validate_account_deletion(
                db,
                confirmation_phrase=payload.confirmation_phrase,
                acknowledge_provider_videos_remain_online=payload.acknowledge_provider_videos_remain_online,
                password=payload.password,
            )
        )
    except AccountDeletionConflictError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail=exc.to_detail()) from exc


@router.post("/account-deletion", response_model=AccountDeletionResultResponse)
def execute_account_deletion_route(payload: AccountDeletionExecuteRequest, db: Session = Depends(get_db)):
    try:
        return AccountDeletionResultResponse(
            **execute_account_deletion(
                db,
                confirmation_phrase=payload.confirmation_phrase,
                acknowledge_provider_videos_remain_online=payload.acknowledge_provider_videos_remain_online,
                password=payload.password,
            )
        )
    except AccountDeletionConflictError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail=exc.to_detail()) from exc


@router.get("/data-retention/report", response_model=RetentionReportResponse)
def read_data_retention_report(db: Session = Depends(get_db)):
    return RetentionReportResponse(**build_retention_report(db))
