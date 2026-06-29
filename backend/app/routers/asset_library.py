from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.asset_library_service import get_asset_library_detail, list_asset_library_items

router = APIRouter(prefix="/asset-library", tags=["asset-library"])


@router.get("")
def list_assets(
    provider: str | None = Query(default=None),
    status: str | None = Query(default=None),
    style_preset: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return list_asset_library_items(
        db,
        provider=provider,
        status=status,
        style_preset=style_preset,
        platform=platform,
        search=q,
    )


@router.get("/{run_id}")
def get_asset(run_id: str, db: Session = Depends(get_db)):
    try:
        return get_asset_library_detail(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
