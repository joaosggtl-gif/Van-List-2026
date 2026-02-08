import pytest
from sqlalchemy import create_engine, event, StaticPool
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User

from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def db_engine():
    """Create a fresh in-memory SQLite engine for each test.
    Uses StaticPool so all threads share the same connection."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a session bound to the test engine."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db_engine, db_session):
    """FastAPI test client with overridden DB dependency."""
    def _override_get_db():
        session = sessionmaker(bind=db_engine)()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def admin_user(db_session) -> User:
    """Create an admin user in the test DB."""
    user = User(
        username="testadmin",
        full_name="Test Admin",
        hashed_password=hash_password("admin123"),
        role="admin",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def operator_user(db_session) -> User:
    """Create an operator user in the test DB."""
    user = User(
        username="testoperator",
        full_name="Test Operator",
        hashed_password=hash_password("oper123"),
        role="operator",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def readonly_user(db_session) -> User:
    """Create a read-only user in the test DB."""
    user = User(
        username="testreadonly",
        full_name="Test Readonly",
        hashed_password=hash_password("read123"),
        role="readonly",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def get_auth_headers(client: TestClient, username: str, password: str) -> dict:
    """Login and return Authorization headers with Bearer token."""
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def admin_headers(client, admin_user) -> dict:
    return get_auth_headers(client, "testadmin", "admin123")


@pytest.fixture(scope="function")
def operator_headers(client, operator_user) -> dict:
    return get_auth_headers(client, "testoperator", "oper123")


@pytest.fixture(scope="function")
def readonly_headers(client, readonly_user) -> dict:
    return get_auth_headers(client, "testreadonly", "read123")
