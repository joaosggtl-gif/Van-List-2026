from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import DailyAssignment, Van, Driver, User, DriverVanPreassignment
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

    # Auto-assign van from preassignment if driver-only
    if assignment.driver_id is not None and assignment.van_id is None:
        preassign = (
            db.query(DriverVanPreassignment)
            .filter(DriverVanPreassignment.driver_id == assignment.driver_id)
            .first()
        )
        if preassign:
            van_conflict = (
                db.query(DailyAssignment)
                .filter(
                    DailyAssignment.assignment_date == data.assignment_date,
                    DailyAssignment.van_id == preassign.van_id,
                )
                .first()
            )
            if not van_conflict:
                assignment.van_id = preassign.van_id
                van = db.query(Van).filter(Van.id == preassign.van_id).first()
                db.flush()

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


@router.get("/assignable-drivers-for-van")
def assignable_drivers_for_van(
    assignment_date: date = Query(...),
    q: str = Query(""),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Return drivers that can be assigned to a van on a given date.

    Includes completely unassigned drivers AND drivers with driver-only
    assignments (who still need a van).  Excludes drivers already paired
    with a van on that date.
    """
    # IDs of drivers already paired with a van on this date
    paired_driver_ids = (
        select(DailyAssignment.driver_id)
        .where(
            DailyAssignment.assignment_date == assignment_date,
            DailyAssignment.driver_id.isnot(None),
            DailyAssignment.van_id.isnot(None),
        )
        .scalar_subquery()
    )
    query = (
        db.query(Driver)
        .filter(Driver.active == True, Driver.id.notin_(paired_driver_ids))
    )
    if q:
        query = query.filter(
            (Driver.name.ilike(f"%{q}%")) | (Driver.employee_id.ilike(f"%{q}%"))
        )
    drivers = query.order_by(Driver.name).limit(50).all()

    # Look up existing driver-only assignments so the frontend knows to PUT
    driver_ids = [d.id for d in drivers]
    driver_only_assignments = (
        db.query(DailyAssignment)
        .filter(
            DailyAssignment.assignment_date == assignment_date,
            DailyAssignment.driver_id.in_(driver_ids),
            DailyAssignment.van_id.is_(None),
        )
        .all()
    )
    existing_map = {a.driver_id: a.id for a in driver_only_assignments}

    return [
        {
            "id": d.id,
            "employee_id": d.employee_id,
            "name": d.name,
            "existing_assignment_id": existing_map.get(d.id),
        }
        for d in drivers
    ]


@router.post("/bulk-upload-drivers")
async def bulk_upload_drivers(
    assignment_date: date = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("operator")),
):
    """Upload XLSX/CSV to add drivers to a specific day as driver-only assignments.

    Supports three formats:
    1. Simple: employee_id + name columns
    2. Schedule: Associate name + Transporter ID
    3. Driver Route: two-panel IN/OFF layout (matched by name)
    """
    content = await file.read()

    # Check for Driver Route format first (match by name, no import into drivers table)
    from app.services.import_service import _detect_driver_route_format
    route_names = _detect_driver_route_format(content, file.filename)

    if route_names is not None:
        return _bulk_assign_by_name(db, user, assignment_date, route_names, file.filename)

    # Fallback to standard import (Schedule / Simple formats)
    result = import_drivers(db, content, file.filename, uploaded_by=user.username)

    created = 0
    skipped_assign = 0
    drivers = db.query(Driver).filter(Driver.active == True).all()

    existing_ids = {
        a.driver_id for a in
        db.query(DailyAssignment)
        .filter(
            DailyAssignment.assignment_date == assignment_date,
            DailyAssignment.driver_id.isnot(None),
        )
        .all()
    }

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

    driver_map = {d.employee_id: d for d in drivers}

    preassign_map = {
        pa.driver_id: pa.van_id
        for pa in db.query(DriverVanPreassignment).all()
    }

    existing_van_ids = {
        a.van_id for a in
        db.query(DailyAssignment)
        .filter(
            DailyAssignment.assignment_date == assignment_date,
            DailyAssignment.van_id.isnot(None),
        )
        .all()
    }

    for eid in target_employee_ids:
        drv = driver_map.get(eid)
        if not drv:
            continue
        if drv.id in existing_ids:
            skipped_assign += 1
            continue
        van_id = None
        preassigned_van = preassign_map.get(drv.id)
        if preassigned_van and preassigned_van not in existing_van_ids:
            van_id = preassigned_van
            existing_van_ids.add(van_id)
        asgn = DailyAssignment(
            assignment_date=assignment_date,
            driver_id=drv.id,
            van_id=van_id,
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


def _fuzzy_match_driver(file_name: str, drivers: list) -> "Driver | None":
    """Match a short/informal name from the driver route file to a registered driver.

    Strategy (in order):
    1. Exact match (case-insensitive)
    2. Last name exact + first name prefix (e.g., "Ben Angilley" -> "Benjamin Angilley")
    3. All file name tokens found as prefixes in the DB name tokens
       (e.g., "Simon Abbott" -> "Simon Peter Abbott")
    """
    normalized = file_name.strip().lower()
    file_tokens = normalized.split()
    if not file_tokens:
        return None

    # 1. Exact match
    for d in drivers:
        if d.name.strip().lower() == normalized:
            return d

    # 2. Last name exact + first name prefix
    file_last = file_tokens[-1]
    file_first = file_tokens[0]
    candidates = []
    for d in drivers:
        db_tokens = d.name.strip().lower().split()
        if not db_tokens:
            continue
        db_last = db_tokens[-1]
        db_first = db_tokens[0]
        # Last name must match exactly
        if db_last != file_last:
            continue
        # First name: exact or prefix
        if db_first == file_first or db_first.startswith(file_first) or file_first.startswith(db_first):
            candidates.append(d)

    if len(candidates) == 1:
        return candidates[0]

    # 3. Token-based: all file tokens appear as prefixes of some DB token
    for d in drivers:
        db_tokens = d.name.strip().lower().split()
        matched_all = True
        for ft in file_tokens:
            if not any(dt.startswith(ft) or ft.startswith(dt) for dt in db_tokens):
                matched_all = False
                break
        if matched_all:
            return d

    return None


def _bulk_assign_by_name(db: Session, user: User, assignment_date: date, names: list[str], filename: str):
    """Create daily assignments matching driver names from a Driver Route file."""

    active_drivers = db.query(Driver).filter(Driver.active == True).all()

    # Get already assigned driver_ids for this date
    existing_ids = {
        a.driver_id for a in
        db.query(DailyAssignment)
        .filter(
            DailyAssignment.assignment_date == assignment_date,
            DailyAssignment.driver_id.isnot(None),
        )
        .all()
    }

    # Load preassignments
    preassign_map = {
        pa.driver_id: pa.van_id
        for pa in db.query(DriverVanPreassignment).all()
    }

    existing_van_ids = {
        a.van_id for a in
        db.query(DailyAssignment)
        .filter(
            DailyAssignment.assignment_date == assignment_date,
            DailyAssignment.van_id.isnot(None),
        )
        .all()
    }

    created = 0
    skipped = 0
    not_found = []
    matched_drivers = set()  # Prevent same driver matched twice

    for name in names:
        # Filter out already-matched drivers to avoid duplicates
        available = [d for d in active_drivers if d.id not in matched_drivers]
        drv = _fuzzy_match_driver(name, available)

        if not drv:
            not_found.append(name)
            continue

        matched_drivers.add(drv.id)

        if drv.id in existing_ids:
            skipped += 1
            continue

        van_id = None
        preassigned_van = preassign_map.get(drv.id)
        if preassigned_van and preassigned_van not in existing_van_ids:
            van_id = preassigned_van
            existing_van_ids.add(van_id)

        asgn = DailyAssignment(
            assignment_date=assignment_date,
            driver_id=drv.id,
            van_id=van_id,
        )
        db.add(asgn)
        existing_ids.add(drv.id)
        created += 1

    db.commit()

    log_action(
        db, user, "upload", "assignment", None,
        f"Driver Route upload for {assignment_date} ({filename}): "
        f"{created} created, {skipped} already assigned, {len(not_found)} not found",
    )
    db.commit()

    return {
        "import_result": {
            "format": "driver_route",
            "drivers_in_file": len(names),
            "not_found": not_found,
        },
        "assignments_created": created,
        "assignments_skipped": skipped,
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
