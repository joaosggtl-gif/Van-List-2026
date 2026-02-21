import io
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from sqlalchemy.orm import Session, joinedload

from app.models import DailyAssignment
from app.routes.pages import short_name
from app.services.week_service import get_week_number, get_week_days


HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
HEADER_FILL = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center")
THIN_BORDER = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin"),
)


def _style_header(ws, row=1):
    for cell in ws[row]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGNMENT
        cell.border = THIN_BORDER


def _auto_width(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            if cell.value:
                max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_len + 3, 40)


def _assignment_row(a: DailyAssignment) -> list:
    # Determine status
    if a.van_id is not None and a.driver_id is not None:
        status = "Assigned"
    elif a.driver_id is not None:
        status = "Driver Only"
    else:
        status = "Van Only"

    return [
        a.assignment_date.isoformat(),
        get_week_number(a.assignment_date),
        a.driver.employee_id if a.driver else "",
        short_name(a.driver.name) if a.driver else "",
        a.van.code if a.van else "",
        (a.van.description or "") if a.van else "",
        (a.van.operational_status or "") if a.van else "",
        status,
        a.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        a.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
        a.notes or "",
    ]


HEADERS = [
    "Date", "Week #", "Driver ID", "Driver Name",
    "Van (Plate)", "Van Description", "Operational Status", "Status",
    "Created At", "Updated At", "Notes",
]


def export_daily_xlsx(db: Session, target_date: date) -> bytes:
    """Export a single day's assignments to XLSX."""
    assignments = (
        db.query(DailyAssignment)
        .options(joinedload(DailyAssignment.van), joinedload(DailyAssignment.driver))
        .filter(DailyAssignment.assignment_date == target_date)
        .order_by(DailyAssignment.id)
        .all()
    )

    wb = Workbook()
    ws = wb.active
    ws.title = f"Assignments {target_date.isoformat()}"

    ws.append(HEADERS)
    _style_header(ws)

    for a in assignments:
        ws.append(_assignment_row(a))

    _auto_width(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_weekly_xlsx(db: Session, week_number: int) -> bytes:
    """Export a full week's assignments to XLSX."""
    days = get_week_days(week_number)
    start_date = days[0]
    end_date = days[-1]

    assignments = (
        db.query(DailyAssignment)
        .options(joinedload(DailyAssignment.van), joinedload(DailyAssignment.driver))
        .filter(
            DailyAssignment.assignment_date >= start_date,
            DailyAssignment.assignment_date <= end_date,
        )
        .order_by(DailyAssignment.assignment_date, DailyAssignment.id)
        .all()
    )

    wb = Workbook()
    ws = wb.active
    ws.title = f"Week {week_number}"

    ws.append(HEADERS)
    _style_header(ws)

    for a in assignments:
        ws.append(_assignment_row(a))

    _auto_width(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
