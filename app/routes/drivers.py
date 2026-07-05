import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import Driver, User
from app.routes.pages import short_name
from app.schemas import DriverOut
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/drivers", tags=["drivers"])


class QuickAddRequest(BaseModel):
    name: str


@router.post("/quick-add")
def quick_add_driver(
    data: QuickAddRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """Create a driver from a manually typed name, or return existing active driver with that name."""
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    existing = db.query(Driver).filter(Driver.name.ilike(name), Driver.active == True).first()
    if existing:
        return {"id": existing.id, "name": existing.name, "employee_id": existing.employee_id,
                "short_name": short_name(existing.name), "existing_assignment_id": None}

    employee_id = f"MANUAL_{uuid.uuid4().hex[:8].upper()}"
    driver = Driver(name=name, employee_id=employee_id)
    db.add(driver)
    db.flush()
    log_action(db, user, "create", "driver", driver.id, f"Manually added driver '{name}'")
    db.commit()
    db.refresh(driver)
    return {"id": driver.id, "name": driver.name, "employee_id": driver.employee_id,
            "short_name": short_name(driver.name), "existing_assignment_id": None}


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
    log_action(db, user, "delete", "driver", driver.id, f"Deactivated driver '{short_name(driver.name)}'")
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
    log_action(db, user, "update", "driver", driver.id, f"Toggled driver '{short_name(driver.name)}' active={driver.active}")
    db.commit()
    return {"id": driver.id, "active": driver.active}
