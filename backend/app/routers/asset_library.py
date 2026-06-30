from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.pipeline_runs import ManualPostingUpdate
from app.services.asset_library_service import (
    get_asset_export_pack,
    get_asset_library_detail,
    list_asset_library_items,
    update_asset_manual_posting,
)
from app.services.access_service import require_app_access

router = APIRouter(prefix="/asset-library", tags=["asset-library"], dependencies=[Depends(require_app_access)])


@router.get("")
def list_assets(
    provider: str | None = Query(default=None),
    status: str | None = Query(default=None),
    style_preset: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    manual_posting_status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return list_asset_library_items(
        db,
        provider=provider,
        status=status,
        style_preset=style_preset,
        platform=platform,
        manual_posting_status=manual_posting_status,
        search=q,
    )


@router.get("/{run_id}/export-pack")
def get_export_pack(run_id: str, db: Session = Depends(get_db)):
    try:
        return get_asset_export_pack(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{run_id}/manual-posting")
def update_manual_posting(run_id: str, payload: ManualPostingUpdate, db: Session = Depends(get_db)):
    try:
        return update_asset_manual_posting(db, run_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{run_id}")
def get_asset(run_id: str, db: Session = Depends(get_db)):
    try:
        return get_asset_library_detail(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
