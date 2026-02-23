from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user_optional, ROLE_HIERARCHY
from app.database import get_db
from app.models import DailyAssignment, Van, Driver, User, AuditLog, DriverVanPreassignment
from app.services.week_service import (
    get_current_week_number,
    get_week_dates,
    get_week_days,
    get_week_number,
)

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


def short_name(name: str) -> str:
    """Return first and last name only, stripping middle names and suffixes like '• DRR1'."""
    if not name:
        return name or ""
    name = name.split("•")[0].strip()
    tokens = name.split()
    if len(tokens) <= 2:
        return name
    return f"{tokens[0]} {tokens[-1]}"


templates.env.filters["short_name"] = short_name


def _require_auth(request: Request, db: Session) -> User:
    """Check auth for page routes; redirect to login if unauthenticated."""
    user = get_current_user_optional(request, db)
    if user is None:
        raise _redirect_to_login()
    return user


def _redirect_to_login():
    """Return a redirect response to the login page."""
    from fastapi import HTTPException
    response = RedirectResponse(url="/login", status_code=302)
    raise HTTPException(status_code=302, detail="Redirect", headers={"Location": "/login"})


def _ctx(request: Request, user: User, **kwargs):
    """Build base template context with user info."""
    return {
        "request": request,
        "user": user,
        "user_role": user.role,
        "is_admin": user.role == "admin",
        "can_edit": ROLE_HIERARCHY.get(user.role, 0) >= ROLE_HIERARCHY["operator"],
        "today": date.today(),
        **kwargs,
    }


def _partition_assignments(assignments):
    """Partition assignments into paired, driver_only, and van_only lists."""
    paired = []
    driver_only = []
    van_only = []
    for a in assignments:
        if a.van_id is not None and a.driver_id is not None:
            paired.append(a)
        elif a.driver_id is not None and a.van_id is None:
            driver_only.append(a)
        elif a.van_id is not None and a.driver_id is None:
            van_only.append(a)
    return paired, driver_only, van_only


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/")
def index(
    request: Request,
    week: int | None = None,
    db: Session = Depends(get_db),
):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    if week is None:
        week = get_current_week_number()

    week_start, week_end = get_week_dates(week)
    days = get_week_days(week)

    # Load all active vans
    all_vans = db.query(Van).filter(Van.active == True).all()

    # Load preassignments
    preassignments = (
        db.query(DriverVanPreassignment)
        .options(
            joinedload(DriverVanPreassignment.driver),
            joinedload(DriverVanPreassignment.van),
        )
        .all()
    )
    preassign_by_van = {
        pa.van_id: {"name": pa.driver.name, "id": pa.id}
        for pa in preassignments
    }

    # Load assignments for the week
    assignments = (
        db.query(DailyAssignment)
        .options(joinedload(DailyAssignment.van), joinedload(DailyAssignment.driver))
        .filter(
            DailyAssignment.assignment_date >= week_start,
            DailyAssignment.assignment_date <= week_end,
        )
        .order_by(DailyAssignment.assignment_date, DailyAssignment.id)
        .all()
    )

    # Sort vans: OPERATIONAL first by code, then GROUNDED with drivers, then GROUNDED without
    vans_with_drivers = {a.van_id for a in assignments if a.van_id and a.driver_id}
    all_vans.sort(key=lambda v: (
        v.operational_status == 'GROUNDED',
        not (v.id in vans_with_drivers) if v.operational_status == 'GROUNDED' else False,
        v.code,
    ))

    # Build grid: van_id -> { day_iso -> assignment }
    grid = {}
    for van in all_vans:
        grid[van.id] = {}
        for day in days:
            grid[van.id][day.isoformat()] = None

    # Also track driver-only assignments (no van)
    driver_only_by_date = {d.isoformat(): [] for d in days}

    for a in assignments:
        day_iso = a.assignment_date.isoformat()
        if a.van_id and a.van_id in grid:
            grid[a.van_id][day_iso] = a
        elif a.driver_id and not a.van_id:
            driver_only_by_date[day_iso].append(a)

    # Count stats
    counts_by_date = {}
    for d in days:
        day_iso = d.isoformat()
        paired = 0
        total = 0
        for a in assignments:
            if a.assignment_date == d:
                total += 1
                if a.van_id and a.driver_id:
                    paired += 1
        counts_by_date[day_iso] = {"paired": paired, "total": total}

    total_vans = len(all_vans)
    total_drivers = db.query(Driver).filter(Driver.active == True).count()

    return templates.TemplateResponse("index.html", _ctx(
        request, user,
        current_week=week,
        week_start=week_start,
        week_end=week_end,
        days=days,
        all_vans=all_vans,
        grid=grid,
        preassign_by_van=preassign_by_van,
        driver_only_by_date=driver_only_by_date,
        counts_by_date=counts_by_date,
        total_vans=total_vans,
        total_drivers=total_drivers,
        today=date.today(),
    ))


@router.get("/day/{target_date}")
def daily_page(
    request: Request,
    target_date: date,
    db: Session = Depends(get_db),
):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    assignments = (
        db.query(DailyAssignment)
        .options(joinedload(DailyAssignment.van), joinedload(DailyAssignment.driver))
        .filter(DailyAssignment.assignment_date == target_date)
        .order_by(DailyAssignment.id)
        .all()
    )

    paired, driver_only, van_only = _partition_assignments(assignments)

    week_num = get_week_number(target_date)
    all_vans = db.query(Van).filter(Van.active == True).order_by(Van.code).all()
    total_drivers = db.query(Driver).filter(Driver.active == True).count()

    # Build set of van IDs already assigned on this date (paired or van-only)
    assigned_van_ids = set()
    for a in paired:
        if a.van_id:
            assigned_van_ids.add(a.van_id)
    for a in van_only:
        if a.van_id:
            assigned_van_ids.add(a.van_id)

    prev_date = target_date - timedelta(days=1)
    next_date = target_date + timedelta(days=1)

    return templates.TemplateResponse("daily.html", _ctx(
        request, user,
        target_date=target_date,
        prev_date=prev_date,
        next_date=next_date,
        week_number=week_num,
        assignments=assignments,
        paired=paired,
        driver_only=driver_only,
        van_only=van_only,
        all_vans=all_vans,
        assigned_van_ids=assigned_van_ids,
        total_vans=len(all_vans),
        total_drivers=total_drivers,
    ))


@router.get("/upload")
def upload_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("upload.html", _ctx(request, user))


@router.get("/lists")
def lists_page(
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    vans = db.query(Van).order_by(Van.active.desc(), Van.code).all()
    drivers = db.query(Driver).order_by(Driver.active.desc(), Driver.name).all()

    preassignments = (
        db.query(DriverVanPreassignment)
        .options(
            joinedload(DriverVanPreassignment.driver),
            joinedload(DriverVanPreassignment.van),
        )
        .all()
    )
    preassign_map = {pa.driver_id: pa for pa in preassignments}

    active_drivers = [d for d in drivers if d.active]

    # Map van_id -> driver name for showing in autocomplete
    preassigned_vans = {pa.van_id: short_name(pa.driver.name) for pa in preassignments}

    return templates.TemplateResponse("lists.html", _ctx(
        request, user,
        vans=vans,
        drivers=drivers,
        preassign_map=preassign_map,
        active_drivers=active_drivers,
        preassigned_vans=preassigned_vans,
    ))


@router.get("/users")
def users_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse(url="/", status_code=302)

    users = db.query(User).order_by(User.username).all()
    return templates.TemplateResponse("users.html", _ctx(request, user, users=users))


@router.get("/audit")
def audit_page(
    request: Request,
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    user = get_current_user_optional(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse(url="/", status_code=302)

    per_page = 50
    total = db.query(AuditLog).count()
    logs = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    total_pages = (total + per_page - 1) // per_page

    return templates.TemplateResponse("audit.html", _ctx(
        request, user,
        logs=logs,
        page=page,
        total_pages=total_pages,
        total=total,
    ))
