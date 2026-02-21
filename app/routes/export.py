from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.services.audit_service import log_action
from app.services.export_service import export_daily_xlsx, export_daily_simple_xlsx, export_weekly_xlsx

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
