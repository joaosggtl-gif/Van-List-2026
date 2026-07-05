import io

import pandas as pd
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import User
from app.services.audit_service import log_action
from app.services.import_service import import_vans, import_drivers, _map_ownership_type, _find_col, _safe_str

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("/debug-columns")
async def debug_columns(
    file: UploadFile = File(...),
    _user: User = Depends(require_role("admin")),
):
    """Diagnostic: show what columns and ownership values are in the uploaded file."""
    content = await file.read()
    if file.filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(content), dtype=str)
    else:
        df = pd.read_excel(io.BytesIO(content), dtype=str, engine="openpyxl")

    col_map = {c.strip().lower(): c for c in df.columns}
    is_vehicles_data = "licenseplatenumber" in col_map
    ownership_col = _find_col(col_map, "ownershipType", "ownershiptype", "ownership_type", "ownership type")

    sample_values = []
    mapped_values = {}
    if ownership_col:
        raw_vals = [_safe_str(v) for v in df[ownership_col].head(20)]
        sample_values = [v for v in raw_vals if v]
        for v in sample_values:
            mapped_values[v] = _map_ownership_type(v)

    return {
        "filename": file.filename,
        "is_vehicles_data_format": is_vehicles_data,
        "all_columns": list(df.columns),
        "ownership_col_found": ownership_col,
        "sample_ownership_values": sample_values,
        "mapped_values": mapped_values,
        "total_rows": len(df),
    }


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
        f"Uploaded '{file.filename}': {result.records_imported} imported, {result.records_skipped} updated, {result.records_removed} removed, {result.records_errors} errors",
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
        f"Uploaded '{file.filename}': {result.records_imported} imported, {result.records_skipped} updated, {result.records_removed} removed, {result.records_errors} errors",
    )
    db.commit()
    return result.model_dump()
