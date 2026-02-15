import io
import json
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Van, Driver, ImportLog
from app.schemas import ImportResult


def _read_file(content: bytes, filename: str) -> pd.DataFrame:
    """Read CSV or XLSX file into a DataFrame."""
    if filename.endswith(".csv"):
        return pd.read_csv(io.BytesIO(content), dtype=str)
    elif filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(content), dtype=str, engine="openpyxl")
    else:
        raise ValueError(f"Unsupported file format: {filename}. Use .csv or .xlsx")


def _safe_str(val) -> str | None:
    """Extract a clean string from a pandas cell, return None if empty/nan."""
    if pd.isna(val):
        return None
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def import_vans(db: Session, content: bytes, filename: str, uploaded_by: str = None) -> ImportResult:
    """Import vans from CSV/XLSX.

    Supports two formats:
    1. Simple: columns 'code', 'description' (optional), 'operational_status' (optional)
    2. VehiclesData: columns 'licensePlateNumber', 'operationalStatus', etc.
       Auto-detected when 'licensePlateNumber' column is present.
    """
    df = _read_file(content, filename)
    original_columns = list(df.columns)
    col_map = {c.strip().lower(): c for c in df.columns}

    # Auto-detect VehiclesData format
    is_vehicles_data = "licenseplatenumber" in col_map

    if is_vehicles_data:
        plate_col = col_map["licenseplatenumber"]
        status_col = col_map.get("operationalstatus")
        desc_parts = []
        for key in ("make", "model"):
            if key in col_map:
                desc_parts.append(col_map[key])
    else:
        df.columns = [c.strip().lower() for c in df.columns]
        if "code" not in df.columns:
            raise ValueError(
                "File must have a 'code' column (or 'licensePlateNumber' for VehiclesData format)"
            )

    errors = []
    imported = 0
    skipped = 0
    total = len(df)
    uploaded_codes = set()

    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel row (1-indexed + header)

        if is_vehicles_data:
            code = _safe_str(row.get(plate_col))
            op_status = _safe_str(row.get(status_col)) if status_col else None
            # Build description from make + model
            parts = [_safe_str(row.get(c)) for c in desc_parts]
            description = " ".join(p for p in parts if p) or None
        else:
            code = _safe_str(row.get("code"))
            description = _safe_str(row.get("description"))
            op_status = _safe_str(row.get("operational_status"))

        if not code:
            errors.append(f"Row {row_num}: empty {'licensePlateNumber' if is_vehicles_data else 'code'}")
            continue

        uploaded_codes.add(code)

        existing = db.query(Van).filter(Van.code == code).first()
        if existing:
            changed = False
            if description and existing.description != description:
                existing.description = description
                changed = True
            if op_status is not None and existing.operational_status != op_status:
                existing.operational_status = op_status
                changed = True
            if not existing.active:
                existing.active = True
                changed = True
            if changed:
                existing.updated_at = datetime.utcnow()
            skipped += 1
            continue

        van = Van(code=code, description=description, operational_status=op_status)
        db.add(van)
        imported += 1

    # Deactivate vans not present in the uploaded file
    removed = 0
    if uploaded_codes:
        stale_vans = db.query(Van).filter(Van.active == True, Van.code.notin_(uploaded_codes)).all()
        for v in stale_vans:
            v.active = False
            v.updated_at = datetime.utcnow()
            removed += 1

    db.flush()

    log = ImportLog(
        filename=filename,
        import_type="van",
        records_total=total,
        records_imported=imported,
        records_skipped=skipped,
        records_errors=len(errors),
        error_details=json.dumps(errors) if errors else None,
        uploaded_by=uploaded_by,
    )
    db.add(log)
    db.commit()

    return ImportResult(
        filename=filename,
        import_type="van",
        records_total=total,
        records_imported=imported,
        records_skipped=skipped,
        records_removed=removed,
        records_errors=len(errors),
        errors=errors,
    )


def _detect_schedule_format(df: pd.DataFrame):
    """Detect Schedule XLSX format where headers are in a lower row.

    Looks for 'Associate name' in the first 10 rows of any column.
    Returns (header_row_index, name_col, id_col) or None.
    """
    for idx in range(min(10, len(df))):
        for col in df.columns:
            val = _safe_str(df.iloc[idx][col])
            if val and val.lower() == "associate name":
                # Found the header row; determine column positions
                header_row = df.iloc[idx]
                name_col = col  # column where "Associate name" lives
                id_col = None
                for c in df.columns:
                    cell = _safe_str(header_row[c])
                    if cell and cell.lower() == "transporter id":
                        id_col = c
                        break
                return idx, name_col, id_col
    return None


def import_drivers(db: Session, content: bytes, filename: str, uploaded_by: str = None) -> ImportResult:
    """Import drivers from CSV/XLSX.

    Supports two formats:
    1. Simple: columns 'employee_id' (required), 'name' (required)
    2. Schedule: 'Associate name' and 'Transporter ID' found in a header row.
       Auto-detected when 'Associate name' appears in the first rows.
    """
    df = _read_file(content, filename)

    # Auto-detect Schedule format
    schedule_info = _detect_schedule_format(df)
    is_schedule = schedule_info is not None

    if is_schedule:
        header_idx, name_col, id_col = schedule_info
        # Skip rows: everything up to and including the header row,
        # plus the "Total rostered" summary row right after
        skip_rows = set(range(header_idx + 1))
        # Also skip the summary row (immediately after headers)
        summary_idx = header_idx + 1
        if summary_idx < len(df):
            val = _safe_str(df.iloc[summary_idx][name_col])
            if val and "total" in val.lower():
                skip_rows.add(summary_idx)
        df = df.drop(index=list(skip_rows)).reset_index(drop=True)
    else:
        df.columns = [c.strip().lower() for c in df.columns]
        if "employee_id" not in df.columns:
            raise ValueError(
                "File must have an 'employee_id' column (or 'Associate name' for Schedule format)"
            )
        if "name" not in df.columns:
            raise ValueError("File must have a 'name' column")

    errors = []
    imported = 0
    skipped = 0
    total = len(df)
    uploaded_ids = set()

    for idx, row in df.iterrows():
        row_num = idx + 2
        if is_schedule:
            name = _safe_str(row.get(name_col))
            employee_id = _safe_str(row.get(id_col)) if id_col else None
        else:
            employee_id = _safe_str(row.get("employee_id"))
            name = _safe_str(row.get("name"))

        if not employee_id:
            errors.append(f"Row {row_num}: empty employee_id")
            continue
        if not name:
            errors.append(f"Row {row_num}: empty name")
            continue

        uploaded_ids.add(employee_id)

        existing = db.query(Driver).filter(Driver.employee_id == employee_id).first()
        if existing:
            changed = False
            if name and existing.name != name:
                existing.name = name
                changed = True
            if not existing.active:
                existing.active = True
                changed = True
            if changed:
                existing.updated_at = datetime.utcnow()
            skipped += 1
            continue

        driver = Driver(employee_id=employee_id, name=name)
        db.add(driver)
        imported += 1

    # Deactivate drivers not present in the uploaded file
    removed = 0
    if uploaded_ids:
        stale_drivers = db.query(Driver).filter(Driver.active == True, Driver.employee_id.notin_(uploaded_ids)).all()
        for d in stale_drivers:
            d.active = False
            d.updated_at = datetime.utcnow()
            removed += 1

    db.flush()

    log = ImportLog(
        filename=filename,
        import_type="driver",
        records_total=total,
        records_imported=imported,
        records_skipped=skipped,
        records_errors=len(errors),
        error_details=json.dumps(errors) if errors else None,
        uploaded_by=uploaded_by,
    )
    db.add(log)
    db.commit()

    return ImportResult(
        filename=filename,
        import_type="driver",
        records_total=total,
        records_imported=imported,
        records_skipped=skipped,
        records_removed=removed,
        records_errors=len(errors),
        errors=errors,
    )
