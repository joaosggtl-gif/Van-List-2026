from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator


# --- Auth ---
class LoginRequest(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    full_name: str
    password: str
    role: str = "readonly"


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str
    role: str
    active: bool
    created_at: datetime


# --- Van ---
class VanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    description: Optional[str] = None
    operational_status: Optional[str] = None
    active: bool


# --- Driver ---
class DriverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: str
    name: str
    active: bool


# --- Assignment ---
class AssignmentCreate(BaseModel):
    assignment_date: date
    van_id: Optional[int] = None
    driver_id: Optional[int] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one(self):
        if self.van_id is None and self.driver_id is None:
            raise ValueError("At least one of van_id or driver_id must be provided")
        return self


class AssignmentUpdate(BaseModel):
    van_id: Optional[int] = None
    driver_id: Optional[int] = None
    notes: Optional[str] = None


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    assignment_date: date
    van_id: Optional[int] = None
    driver_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    van: Optional[VanOut] = None
    driver: Optional[DriverOut] = None


class AssignmentPair(BaseModel):
    driver_assignment_id: int
    van_assignment_id: int


# --- Week ---
class WeekInfo(BaseModel):
    week_number: int
    start_date: date
    end_date: date


# --- Import ---
class ImportResult(BaseModel):
    filename: str
    import_type: str
    records_total: int
    records_imported: int
    records_skipped: int
    records_removed: int = 0
    records_errors: int
    errors: list[str]


# --- Audit ---
class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    details: Optional[str] = None
    created_at: datetime
