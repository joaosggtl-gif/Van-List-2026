from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.auth import hash_password
from app.config import DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD
from app.database import Base, engine, SessionLocal
from app.models import User
from app.routes import pages, assignments, vans, drivers, upload, export, auth, preassignments, historical

# Create tables (safe if already exist; Alembic handles migrations in production)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Van List 2026", version="2.0.0")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(assignments.router)
app.include_router(vans.router)
app.include_router(drivers.router)
app.include_router(upload.router)
app.include_router(export.router)
app.include_router(preassignments.router)
app.include_router(historical.router)


@app.on_event("startup")
def create_default_admin():
    """Create default admin user on first startup."""
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == DEFAULT_ADMIN_USERNAME).first()
        if not existing:
            admin = User(
                username=DEFAULT_ADMIN_USERNAME,
                full_name="System Administrator",
                hashed_password=hash_password(DEFAULT_ADMIN_PASSWORD),
                role="admin",
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()
