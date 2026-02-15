from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Text,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=False)
    hashed_password = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="readonly")  # admin, operator, readonly
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    audit_logs = relationship("AuditLog", back_populates="user")

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_created", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)  # create, update, delete, login, upload, export
    entity_type = Column(String(50), nullable=True)  # assignment, van, driver, user
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return f"<Audit {self.action} by {self.username} at {self.created_at}>"


class Van(Base):
    __tablename__ = "vans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # licensePlateNumber
    description = Column(String(200), nullable=True)
    operational_status = Column(String(30), nullable=True)  # OPERATIONAL, GROUNDED
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    assignments = relationship("DailyAssignment", back_populates="van")

    def __repr__(self):
        return f"<Van {self.code}>"


class Driver(Base):
    __tablename__ = "drivers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    assignments = relationship("DailyAssignment", back_populates="driver")

    def __repr__(self):
        return f"<Driver {self.employee_id} - {self.name}>"


class DailyAssignment(Base):
    __tablename__ = "daily_assignments"
    __table_args__ = (
        UniqueConstraint("assignment_date", "van_id", name="uq_date_van"),
        UniqueConstraint("assignment_date", "driver_id", name="uq_date_driver"),
        Index("ix_assignments_date", "assignment_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    assignment_date = Column(Date, nullable=False)
    van_id = Column(Integer, ForeignKey("vans.id", ondelete="RESTRICT"), nullable=True)
    driver_id = Column(Integer, ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=True)
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    van = relationship("Van", back_populates="assignments")
    driver = relationship("Driver", back_populates="assignments")

    def __repr__(self):
        return f"<Assignment {self.assignment_date}: {self.driver_id} -> {self.van_id}>"


class DriverVanPreassignment(Base):
    __tablename__ = "driver_van_preassignments"
    __table_args__ = (
        UniqueConstraint("driver_id", name="uq_preassign_driver"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(Integer, ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False)
    van_id = Column(Integer, ForeignKey("vans.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    driver = relationship("Driver", backref="preassignment")
    van = relationship("Van", backref="preassignments")

    def __repr__(self):
        return f"<DriverVanPreassignment driver={self.driver_id} van={self.van_id}>"


class ImportLog(Base):
    __tablename__ = "import_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(300), nullable=False)
    import_type = Column(String(20), nullable=False)  # "van" or "driver"
    records_total = Column(Integer, default=0)
    records_imported = Column(Integer, default=0)
    records_skipped = Column(Integer, default=0)
    records_errors = Column(Integer, default=0)
    error_details = Column(Text, nullable=True)  # JSON string
    uploaded_by = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
