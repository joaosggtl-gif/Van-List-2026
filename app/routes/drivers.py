from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import Driver, User
from app.schemas import DriverOut
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/drivers", tags=["drivers"])


@router.get("", response_model=list[DriverOut])
def list_drivers(
    active_only: bool = True,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    q = db.query(Driver)
    if active_only:
        q = q.filter(Driver.active == True)
    return q.order_by(Driver.name).all()


@router.get("/search", response_model=list[DriverOut])
def search_drivers(
    q: str = Query("", min_length=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Driver).filter(Driver.active == True)
    if q:
        query = query.filter(
            (Driver.name.ilike(f"%{q}%")) | (Driver.employee_id.ilike(f"%{q}%"))
        )
    return query.order_by(Driver.name).limit(20).all()


@router.delete("/{driver_id}")
def delete_driver(
    driver_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    driver.active = False
    log_action(db, user, "delete", "driver", driver.id, f"Deactivated driver '{driver.name}'")
    db.commit()
    return {"id": driver.id, "active": driver.active}


@router.post("/{driver_id}/toggle")
def toggle_driver(
    driver_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        return {"error": "Driver not found"}
    driver.active = not driver.active
    log_action(db, user, "update", "driver", driver.id, f"Toggled driver '{driver.name}' active={driver.active}")
    db.commit()
    return {"id": driver.id, "active": driver.active}
