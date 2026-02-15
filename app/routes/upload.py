from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import User
from app.services.audit_service import log_action
from app.services.import_service import import_vans, import_drivers

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("/vans")
async def upload_vans(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed = (".csv", ".xlsx", ".xls")
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        raise HTTPException(status_code=400, detail=f"File must be one of: {', '.join(allowed)}")

    content = await file.read()
    try:
        result = import_vans(db, content, file.filename, uploaded_by=user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    log_action(
        db, user, "upload", "van", None,
        f"Uploaded '{file.filename}': {result.records_imported} imported, {result.records_skipped} skipped, {result.records_errors} errors",
    )
    db.commit()
    return result.model_dump()


@router.post("/drivers")
async def upload_drivers(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    allowed = (".csv", ".xlsx", ".xls")
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        raise HTTPException(status_code=400, detail=f"File must be one of: {', '.join(allowed)}")

    content = await file.read()
    try:
        result = import_drivers(db, content, file.filename, uploaded_by=user.username)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    log_action(
        db, user, "upload", "driver", None,
        f"Uploaded '{file.filename}': {result.records_imported} imported, {result.records_skipped} skipped, {result.records_errors} errors",
    )
    db.commit()
    return result.model_dump()
