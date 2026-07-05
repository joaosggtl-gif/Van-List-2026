from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text, inspect as sa_inspect
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db, engine
from app.models import Van, User
from app.schemas import VanOut
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/vans", tags=["vans"])


class VanStatusUpdate(BaseModel):
    operational_status: str | None = None


@router.get("", response_model=list[VanOut])
def list_vans(
    active_only: bool = True,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    q = db.query(Van)
    if active_only:
        q = q.filter(Van.active == True)
    return q.order_by(Van.code).all()


@router.get("/search", response_model=list[VanOut])
def search_vans(
    q: str = Query("", min_length=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Van).filter(Van.active == True)
    if q:
        query = query.filter(Van.code.ilike(f"%{q}%"))
    return query.order_by(Van.code).all()


@router.post("/{van_id}/toggle")
def toggle_van(
    van_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    van = db.query(Van).filter(Van.id == van_id).first()
    if not van:
        return {"error": "Van not found"}
    van.active = not van.active
    log_action(db, user, "update", "van", van.id, f"Toggled van '{van.code}' active={van.active}")
    db.commit()
    return {"id": van.id, "active": van.active}


@router.delete("/{van_id}")
def delete_van(
    van_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    van = db.query(Van).filter(Van.id == van_id).first()
    if not van:
        raise HTTPException(status_code=404, detail="Van not found")
    van.active = False
    log_action(db, user, "delete", "van", van.id, f"Deactivated van '{van.code}'")
    db.commit()
    return {"id": van.id, "active": van.active}


@router.get("/debug/ownership")
def debug_ownership(
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("admin")),
):
    """Temporary diagnostic: shows ownership_type column state in DB."""
    inspector = sa_inspect(engine)
    col_names = [c["name"] for c in inspector.get_columns("vans")]
    has_col = "ownership_type" in col_names
    sample = db.query(Van).order_by(Van.id).limit(10).all()
    return {
        "column_exists": has_col,
        "vans_with_ownership": db.query(Van).filter(Van.ownership_type.isnot(None)).count(),
        "total_active_vans": db.query(Van).filter(Van.active == True).count(),
        "sample": [{"code": v.code, "ownership_type": v.ownership_type} for v in sample],
    }


@router.post("/{van_id}/operational-status")
def update_operational_status(
    van_id: int,
    data: VanStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    van = db.query(Van).filter(Van.id == van_id).first()
    if not van:
        raise HTTPException(status_code=404, detail="Van not found")
    old_status = van.operational_status
    van.operational_status = data.operational_status
    log_action(db, user, "update", "van", van.id,
               f"Changed van '{van.code}' operational_status: {old_status} -> {data.operational_status}")
    db.commit()
    return {"id": van.id, "operational_status": van.operational_status}
