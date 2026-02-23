from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import HistoricalAssignment, User
from app.services.audit_service import log_action

router = APIRouter(prefix="/api/historical-assignments", tags=["historical"])


class HistoricalUpsert(BaseModel):
    van_reg: str
    assignment_date: date
    driver_name: Optional[str] = None
    is_vor: bool = False


@router.put("")
def upsert_historical_assignment(
    data: HistoricalUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """Upsert a historical assignment record.

    - If driver_name is empty/null AND is_vor is false → delete (= "Free").
    - Otherwise create or update.
    """
    existing = (
        db.query(HistoricalAssignment)
        .filter(
            HistoricalAssignment.assignment_date == data.assignment_date,
            HistoricalAssignment.van_reg == data.van_reg,
        )
        .first()
    )

    driver_name = (data.driver_name or "").strip() or None
    is_free = driver_name is None and not data.is_vor

    if is_free:
        # Delete record if it exists (cell becomes "Free")
        if existing:
            db.delete(existing)
            log_action(
                db, user, "delete", "historical_assignment", existing.id,
                f"Cleared historical: {data.van_reg} on {data.assignment_date}",
            )
            db.commit()
        return {"status": "free", "van_reg": data.van_reg, "date": str(data.assignment_date)}

    if existing:
        existing.driver_name = driver_name
        existing.is_vor = data.is_vor
        log_action(
            db, user, "update", "historical_assignment", existing.id,
            f"Updated historical: {data.van_reg} on {data.assignment_date} → "
            f"{'VOR' if data.is_vor else driver_name}",
        )
        db.commit()
        return {
            "status": "updated",
            "id": existing.id,
            "van_reg": data.van_reg,
            "date": str(data.assignment_date),
            "driver_name": existing.driver_name,
            "is_vor": existing.is_vor,
        }

    record = HistoricalAssignment(
        assignment_date=data.assignment_date,
        van_reg=data.van_reg,
        driver_name=driver_name,
        is_vor=data.is_vor,
    )
    db.add(record)
    db.flush()
    log_action(
        db, user, "create", "historical_assignment", record.id,
        f"Created historical: {data.van_reg} on {data.assignment_date} → "
        f"{'VOR' if data.is_vor else driver_name}",
    )
    db.commit()
    return {
        "status": "created",
        "id": record.id,
        "van_reg": data.van_reg,
        "date": str(data.assignment_date),
        "driver_name": record.driver_name,
        "is_vor": record.is_vor,
    }
