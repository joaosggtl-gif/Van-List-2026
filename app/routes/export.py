from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.audit_service import log_action
from app.services.export_service import (
    export_daily_xlsx,
    export_daily_simple_xlsx,
    export_weekly_xlsx,
    export_period_xlsx,
)

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/daily")
def download_daily(
    target_date: date = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = export_daily_xlsx(db, target_date)
    log_action(db, user, "export", "assignment", None, f"Exported daily XLSX for {target_date}")
    db.commit()
    filename = f"assignments_{target_date.isoformat()}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/daily-simple")
def download_daily_simple(
    target_date: date = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = export_daily_simple_xlsx(db, target_date)
    log_action(db, user, "export", "assignment", None, f"Exported daily simple XLSX for {target_date}")
    db.commit()
    filename = f"assignments_{target_date.isoformat()}_simple.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/weekly")
def download_weekly(
    week: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = export_weekly_xlsx(db, week)
    log_action(db, user, "export", "assignment", None, f"Exported weekly XLSX for week {week}")
    db.commit()
    filename = f"assignments_week_{week}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/period")
def download_period(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")
    if (end_date - start_date).days > 30:
        raise HTTPException(status_code=400, detail="Date range must not exceed 30 days")

    data = export_period_xlsx(db, start_date, end_date)
    log_action(
        db, user, "export", "assignment", None,
        f"Exported period XLSX for {start_date} to {end_date}",
    )
    db.commit()
    filename = f"assignments_{start_date.isoformat()}_{end_date.isoformat()}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
