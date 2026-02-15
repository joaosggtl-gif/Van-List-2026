from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import DriverVanPreassignment, Driver, Van, User
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/preassignments", tags=["preassignments"])


class PreassignmentCreate(BaseModel):
    driver_id: int
    van_id: int


@router.get("")
def list_preassignments(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    rows = (
        db.query(DriverVanPreassignment)
        .options(
            joinedload(DriverVanPreassignment.driver),
            joinedload(DriverVanPreassignment.van),
        )
        .all()
    )
    return [
        {
            "id": r.id,
            "driver_id": r.driver_id,
            "van_id": r.van_id,
            "driver_name": r.driver.name,
            "driver_employee_id": r.driver.employee_id,
            "van_code": r.van.code,
        }
        for r in rows
    ]


@router.post("", status_code=201)
def create_or_update_preassignment(
    data: PreassignmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    driver = db.query(Driver).filter(Driver.id == data.driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    van = db.query(Van).filter(Van.id == data.van_id).first()
    if not van:
        raise HTTPException(status_code=404, detail="Van not found")

    existing = (
        db.query(DriverVanPreassignment)
        .filter(DriverVanPreassignment.driver_id == data.driver_id)
        .first()
    )
    if existing:
        old_van = existing.van_id
        existing.van_id = data.van_id
        db.flush()
        log_action(
            db, user, "update", "preassignment", existing.id,
            f"Updated preassignment for driver '{driver.name}': van changed from {old_van} to {van.code}",
        )
        db.commit()
        db.refresh(existing)
        return {
            "id": existing.id,
            "driver_id": existing.driver_id,
            "van_id": existing.van_id,
            "van_code": van.code,
        }

    pa = DriverVanPreassignment(driver_id=data.driver_id, van_id=data.van_id)
    db.add(pa)
    db.flush()
    log_action(
        db, user, "create", "preassignment", pa.id,
        f"Pre-assigned van '{van.code}' to driver '{driver.name}'",
    )
    db.commit()
    db.refresh(pa)
    return {
        "id": pa.id,
        "driver_id": pa.driver_id,
        "van_id": pa.van_id,
        "van_code": van.code,
    }


@router.delete("/{preassignment_id}")
def delete_preassignment(
    preassignment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    pa = (
        db.query(DriverVanPreassignment)
        .options(
            joinedload(DriverVanPreassignment.driver),
            joinedload(DriverVanPreassignment.van),
        )
        .filter(DriverVanPreassignment.id == preassignment_id)
        .first()
    )
    if not pa:
        raise HTTPException(status_code=404, detail="Preassignment not found")

    log_action(
        db, user, "delete", "preassignment", pa.id,
        f"Removed preassignment: driver '{pa.driver.name}' was assigned van '{pa.van.code}'",
    )
    db.delete(pa)
    db.commit()
    return {"deleted": True, "id": preassignment_id}
