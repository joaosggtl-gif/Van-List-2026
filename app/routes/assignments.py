from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import DailyAssignment, Van, Driver, User
from app.schemas import AssignmentCreate, AssignmentOut, AssignmentPair
from app.services.audit_service import log_action
from app.services.import_service import import_vans, import_drivers

router = APIRouter(prefix="/api/assignments", tags=["assignments"])


def _load_assignment(db: Session, assignment_id: int) -> DailyAssignment:
    return (
        db.query(DailyAssignment)
        .options(joinedload(DailyAssignment.van), joinedload(DailyAssignment.driver))
        .filter(DailyAssignment.id == assignment_id)
        .first()
    )


@router.get("", response_model=list[AssignmentOut])
def list_assignments(
    date_from: date = Query(...),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if date_to is None:
        date_to = date_from
    return (
        db.query(DailyAssignment)
        .options(joinedload(DailyAssignment.van), joinedload(DailyAssignment.driver))
        .filter(
            DailyAssignment.assignment_date >= date_from,
            DailyAssignment.assignment_date <= date_to,
        )
        .order_by(DailyAssignment.assignment_date, DailyAssignment.id)
        .all()
    )


@router.post("", response_model=AssignmentOut, status_code=201)
def create_assignment(
    data: AssignmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    van = None
    driver = None

    if data.van_id is not None:
        van = db.query(Van).filter(Van.id == data.van_id).first()
        if not van:
            raise HTTPException(status_code=404, detail="Van not found")

        existing_van = (
            db.query(DailyAssignment)
            .filter(
                DailyAssignment.assignment_date == data.assignment_date,
                DailyAssignment.van_id == data.van_id,
            )
            .first()
        )
        if existing_van:
            raise HTTPException(
                status_code=409,
                detail=f"Van '{van.code}' is already assigned on {data.assignment_date}",
            )

    if data.driver_id is not None:
        driver = db.query(Driver).filter(Driver.id == data.driver_id).first()
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")

        existing_driver = (
            db.query(DailyAssignment)
            .filter(
                DailyAssignment.assignment_date == data.assignment_date,
                DailyAssignment.driver_id == data.driver_id,
            )
            .first()
        )
        if existing_driver:
            raise HTTPException(
                status_code=409,
                detail=f"Driver '{driver.name}' already has an assignment on {data.assignment_date}",
            )

    assignment = DailyAssignment(
        assignment_date=data.assignment_date,
        van_id=data.van_id,
        driver_id=data.driver_id,
        notes=data.notes,
    )
    db.add(assignment)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Conflict: this van or driver is already assigned on this date",
        )

    van_label = f"van '{van.code}'" if van else "no van"
    driver_label = f"driver '{driver.name}'" if driver else "no driver"
    log_action(
        db, user, "create", "assignment", assignment.id,
        f"Assigned {van_label} to {driver_label} on {data.assignment_date}",
    )
    db.commit()

    db.refresh(assignment)
    return _load_assignment(db, assignment.id)


@router.put("/{assignment_id}", response_model=AssignmentOut)
def update_assignment(
    assignment_id: int,
    data: AssignmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    assignment = db.query(DailyAssignment).filter(DailyAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if data.van_id is not None:
        conflict = (
            db.query(DailyAssignment)
            .filter(
                DailyAssignment.assignment_date == data.assignment_date,
                DailyAssignment.van_id == data.van_id,
                DailyAssignment.id != assignment_id,
            )
            .first()
        )
        if conflict:
            van = db.query(Van).filter(Van.id == data.van_id).first()
            raise HTTPException(
                status_code=409,
                detail=f"Van '{van.code}' is already assigned on {data.assignment_date}",
            )

    if data.driver_id is not None:
        conflict = (
            db.query(DailyAssignment)
            .filter(
                DailyAssignment.assignment_date == data.assignment_date,
                DailyAssignment.driver_id == data.driver_id,
                DailyAssignment.id != assignment_id,
            )
            .first()
        )
        if conflict:
            driver = db.query(Driver).filter(Driver.id == data.driver_id).first()
            raise HTTPException(
                status_code=409,
                detail=f"Driver '{driver.name}' already has an assignment on {data.assignment_date}",
            )

    assignment.assignment_date = data.assignment_date
    assignment.van_id = data.van_id
    assignment.driver_id = data.driver_id
    assignment.notes = data.notes

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict: duplicate assignment")

    log_action(db, user, "update", "assignment", assignment.id, f"Updated assignment on {data.assignment_date}")
    db.commit()

    db.refresh(assignment)
    return _load_assignment(db, assignment.id)


@router.delete("/{assignment_id}")
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    assignment = db.query(DailyAssignment).filter(DailyAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    log_action(
        db, user, "delete", "assignment", assignment.id,
        f"Deleted assignment: van_id={assignment.van_id} driver_id={assignment.driver_id} on {assignment.assignment_date}",
    )
    db.delete(assignment)
    db.commit()
    return {"deleted": True, "id": assignment_id}


@router.post("/pair", response_model=AssignmentOut)
def pair_assignments(
    data: AssignmentPair,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """Merge a driver-only assignment and a van-only assignment into one paired row."""
    driver_asgn = db.query(DailyAssignment).filter(DailyAssignment.id == data.driver_assignment_id).first()
    if not driver_asgn:
        raise HTTPException(status_code=404, detail="Driver assignment not found")
    if driver_asgn.driver_id is None:
        raise HTTPException(status_code=400, detail="Assignment has no driver")
    if driver_asgn.van_id is not None:
        raise HTTPException(status_code=400, detail="Driver assignment already has a van")

    van_asgn = db.query(DailyAssignment).filter(DailyAssignment.id == data.van_assignment_id).first()
    if not van_asgn:
        raise HTTPException(status_code=404, detail="Van assignment not found")
    if van_asgn.van_id is None:
        raise HTTPException(status_code=400, detail="Assignment has no van")
    if van_asgn.driver_id is not None:
        raise HTTPException(status_code=400, detail="Van assignment already has a driver")

    if driver_asgn.assignment_date != van_asgn.assignment_date:
        raise HTTPException(status_code=400, detail="Assignments must be on the same date")

    # Merge: delete the van-only row first (to free the unique constraint),
    # then give the driver assignment the van
    target_van_id = van_asgn.van_id
    # Preserve notes from both if any
    notes_parts = [n for n in [driver_asgn.notes, van_asgn.notes] if n]

    db.delete(van_asgn)
    db.flush()  # Free the unique constraint on (date, van_id)

    driver_asgn.van_id = target_van_id
    if notes_parts:
        driver_asgn.notes = "; ".join(notes_parts)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict when pairing assignments")

    log_action(
        db, user, "update", "assignment", driver_asgn.id,
        f"Paired driver assignment {data.driver_assignment_id} with van assignment {data.van_assignment_id}",
    )
    db.commit()
    db.refresh(driver_asgn)
    return _load_assignment(db, driver_asgn.id)


@router.post("/{assignment_id}/unpair", response_model=dict)
def unpair_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """Split a paired assignment back into driver-only + van-only rows."""
    assignment = db.query(DailyAssignment).filter(DailyAssignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment.van_id is None or assignment.driver_id is None:
        raise HTTPException(status_code=400, detail="Assignment is not fully paired")

    # Create a new van-only row
    van_only = DailyAssignment(
        assignment_date=assignment.assignment_date,
        van_id=assignment.van_id,
        driver_id=None,
        notes=None,
    )
    db.add(van_only)

    # Original row becomes driver-only
    assignment.van_id = None

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflict when unpairing assignment")

    log_action(
        db, user, "update", "assignment", assignment.id,
        f"Unpaired assignment {assignment_id} into driver-only + van-only",
    )
    db.commit()
    db.refresh(assignment)
    db.refresh(van_only)

    return {
        "driver_assignment_id": assignment.id,
        "van_assignment_id": van_only.id,
    }


@router.get("/available-vans")
def available_vans_for_date(
    assignment_date: date = Query(...),
    q: str = Query(""),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    assigned_van_ids = (
        select(DailyAssignment.van_id)
        .where(
            DailyAssignment.assignment_date == assignment_date,
            DailyAssignment.van_id.isnot(None),
        )
        .scalar_subquery()
    )
    query = (
        db.query(Van)
        .filter(Van.active == True, Van.id.notin_(assigned_van_ids))
    )
    if q:
        query = query.filter(Van.code.ilike(f"%{q}%"))
    return [{"id": v.id, "code": v.code, "description": v.description, "operational_status": v.operational_status} for v in query.order_by(Van.code).limit(20).all()]


@router.get("/available-drivers")
def available_drivers_for_date(
    assignment_date: date = Query(...),
    q: str = Query(""),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    assigned_driver_ids = (
        select(DailyAssignment.driver_id)
        .where(
            DailyAssignment.assignment_date == assignment_date,
            DailyAssignment.driver_id.isnot(None),
        )
        .scalar_subquery()
    )
    query = (
        db.query(Driver)
        .filter(Driver.active == True, Driver.id.notin_(assigned_driver_ids))
    )
    if q:
        query = query.filter(
            (Driver.name.ilike(f"%{q}%")) | (Driver.employee_id.ilike(f"%{q}%"))
        )
    return [{"id": d.id, "employee_id": d.employee_id, "name": d.name} for d in query.order_by(Driver.name).limit(20).all()]


@router.post("/bulk-upload-drivers")
async def bulk_upload_drivers(
    assignment_date: date = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """Upload XLSX/CSV to add drivers to a specific day as driver-only assignments."""
    content = await file.read()
    result = import_drivers(db, content, file.filename, uploaded_by=user.username)

    # Now create driver-only assignments for each imported/existing driver
    created = 0
    skipped_assign = 0
    drivers = db.query(Driver).filter(Driver.active == True).all()

    # Get all driver_ids already assigned on this date
    existing_ids = {
        a.driver_id for a in
        db.query(DailyAssignment)
        .filter(
            DailyAssignment.assignment_date == assignment_date,
            DailyAssignment.driver_id.isnot(None),
        )
        .all()
    }

    # Use the imported file to determine which drivers to add
    from app.services.import_service import _read_file, _safe_str, _detect_schedule_format
    df = _read_file(content, file.filename)
    schedule_info = _detect_schedule_format(df)

    target_employee_ids = set()
    if schedule_info is not None:
        header_idx, name_col, id_col = schedule_info
        if id_col is not None:
            for idx in range(header_idx + 1, len(df)):
                eid = _safe_str(df.iloc[idx][id_col])
                if eid:
                    target_employee_ids.add(eid)
    else:
        df.columns = [c.strip().lower() for c in df.columns]
        if "employee_id" in df.columns:
            for _, row in df.iterrows():
                eid = _safe_str(row.get("employee_id"))
                if eid:
                    target_employee_ids.add(eid)

    # Map employee_id -> Driver object
    driver_map = {d.employee_id: d for d in drivers}

    for eid in target_employee_ids:
        drv = driver_map.get(eid)
        if not drv:
            continue
        if drv.id in existing_ids:
            skipped_assign += 1
            continue
        asgn = DailyAssignment(
            assignment_date=assignment_date,
            driver_id=drv.id,
            van_id=None,
        )
        db.add(asgn)
        created += 1

    db.commit()

    log_action(
        db, user, "upload", "assignment", None,
        f"Bulk uploaded drivers for {assignment_date}: {created} assignments created, {skipped_assign} skipped",
    )
    db.commit()

    return {
        "import_result": {
            "records_imported": result.records_imported,
            "records_skipped": result.records_skipped,
            "records_errors": result.records_errors,
        },
        "assignments_created": created,
        "assignments_skipped": skipped_assign,
    }


@router.post("/bulk-upload-vans")
async def bulk_upload_vans(
    assignment_date: date = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """Upload XLSX/CSV to add vans to a specific day as van-only assignments."""
    content = await file.read()
    result = import_vans(db, content, file.filename, uploaded_by=user.username)

    # Now create van-only assignments for each imported/existing van
    created = 0
    skipped_assign = 0
    vans = db.query(Van).filter(Van.active == True).all()

    # Get all van_ids already assigned on this date
    existing_ids = {
        a.van_id for a in
        db.query(DailyAssignment)
        .filter(
            DailyAssignment.assignment_date == assignment_date,
            DailyAssignment.van_id.isnot(None),
        )
        .all()
    }

    # Use the imported file to determine which vans to add
    from app.services.import_service import _read_file, _safe_str
    df = _read_file(content, file.filename)
    original_columns = list(df.columns)
    col_map = {c.strip().lower(): c for c in df.columns}
    is_vehicles_data = "licenseplatenumber" in col_map

    target_codes = set()
    if is_vehicles_data:
        plate_col = col_map["licenseplatenumber"]
        for _, row in df.iterrows():
            code = _safe_str(row.get(plate_col))
            if code:
                target_codes.add(code)
    else:
        df.columns = [c.strip().lower() for c in df.columns]
        if "code" in df.columns:
            for _, row in df.iterrows():
                code = _safe_str(row.get("code"))
                if code:
                    target_codes.add(code)

    # Map code -> Van object
    van_map = {v.code: v for v in vans}

    for code in target_codes:
        van = van_map.get(code)
        if not van:
            continue
        if van.id in existing_ids:
            skipped_assign += 1
            continue
        asgn = DailyAssignment(
            assignment_date=assignment_date,
            van_id=van.id,
            driver_id=None,
        )
        db.add(asgn)
        created += 1

    db.commit()

    log_action(
        db, user, "upload", "assignment", None,
        f"Bulk uploaded vans for {assignment_date}: {created} assignments created, {skipped_assign} skipped",
    )
    db.commit()

    return {
        "import_result": {
            "records_imported": result.records_imported,
            "records_skipped": result.records_skipped,
            "records_errors": result.records_errors,
        },
        "assignments_created": created,
        "assignments_skipped": skipped_assign,
    }
