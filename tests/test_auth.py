class TestAuthentication:
    def test_login_success(self, client, admin_user):
        resp = client.post("/api/auth/login", json={"username": "testadmin", "password": "admin123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["username"] == "testadmin"
        assert data["user"]["role"] == "admin"

    def test_login_wrong_password(self, client, admin_user):
        resp = client.post("/api/auth/login", json={"username": "testadmin", "password": "wrong"})
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/api/auth/login", json={"username": "nobody", "password": "test"})
        assert resp.status_code == 401

    def test_login_inactive_user(self, client, db_session, admin_user):
        admin_user.active = False
        db_session.commit()
        resp = client.post("/api/auth/login", json={"username": "testadmin", "password": "admin123"})
        assert resp.status_code == 403

    def test_protected_route_without_auth(self, client):
        resp = client.get("/api/vans")
        assert resp.status_code == 401

    def test_protected_route_with_auth(self, client, admin_headers):
        resp = client.get("/api/vans", headers=admin_headers)
        assert resp.status_code == 200

    def test_me_endpoint(self, client, admin_headers):
        resp = client.get("/api/auth/me", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["username"] == "testadmin"


class TestRBAC:
    def test_admin_can_create_user(self, client, admin_headers):
        resp = client.post("/api/auth/users", json={
            "username": "newuser",
            "full_name": "New User",
            "password": "test123",
            "role": "operator",
        }, headers=admin_headers)
        assert resp.status_code == 201
        assert resp.json()["role"] == "operator"

    def test_operator_cannot_create_user(self, client, operator_headers):
        resp = client.post("/api/auth/users", json={
            "username": "x", "full_name": "X", "password": "test123", "role": "readonly",
        }, headers=operator_headers)
        assert resp.status_code == 403

    def test_readonly_cannot_create_assignment(self, client, readonly_headers, db_session):
        from app.models import Van, Driver
        v = Van(code="V1")
        d = Driver(employee_id="D1", name="Driver")
        db_session.add_all([v, d])
        db_session.commit()

        resp = client.post("/api/assignments", json={
            "assignment_date": "2026-01-05", "van_id": v.id, "driver_id": d.id,
        }, headers=readonly_headers)
        assert resp.status_code == 403

    def test_operator_can_create_assignment(self, client, operator_headers, db_session):
        from app.models import Van, Driver
        v = Van(code="V2")
        d = Driver(employee_id="D2", name="Driver2")
        db_session.add_all([v, d])
        db_session.commit()

        resp = client.post("/api/assignments", json={
            "assignment_date": "2026-01-05", "van_id": v.id, "driver_id": d.id,
        }, headers=operator_headers)
        assert resp.status_code == 201

    def test_readonly_can_view_assignments(self, client, readonly_headers):
        resp = client.get("/api/assignments?date_from=2026-01-05", headers=readonly_headers)
        assert resp.status_code == 200

    def test_operator_cannot_upload(self, client, operator_headers):
        import io
        files = {"file": ("v.csv", io.BytesIO(b"code\nVAN1"), "text/csv")}
        resp = client.post("/api/upload/vans", files=files, headers=operator_headers)
        assert resp.status_code == 403

    def test_admin_can_upload(self, client, admin_headers):
        import io
        files = {"file": ("v.csv", io.BytesIO(b"code\nVAN1"), "text/csv")}
        resp = client.post("/api/upload/vans", files=files, headers=admin_headers)
        assert resp.status_code == 200

    def test_admin_can_toggle_van(self, client, admin_headers, db_session):
        from app.models import Van
        v = Van(code="V3")
        db_session.add(v)
        db_session.commit()
        resp = client.post(f"/api/vans/{v.id}/toggle", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["active"] is False

    def test_operator_cannot_toggle_van(self, client, operator_headers, db_session):
        from app.models import Van
        v = Van(code="V4")
        db_session.add(v)
        db_session.commit()
        resp = client.post(f"/api/vans/{v.id}/toggle", headers=operator_headers)
        assert resp.status_code == 403

    def test_duplicate_username_rejected(self, client, admin_headers):
        client.post("/api/auth/users", json={
            "username": "dup", "full_name": "Dup", "password": "test123", "role": "readonly",
        }, headers=admin_headers)
        resp = client.post("/api/auth/users", json={
            "username": "dup", "full_name": "Dup2", "password": "test123", "role": "readonly",
        }, headers=admin_headers)
        assert resp.status_code == 409

    def test_short_password_rejected(self, client, admin_headers):
        resp = client.post("/api/auth/users", json={
            "username": "short", "full_name": "Short", "password": "12", "role": "readonly",
        }, headers=admin_headers)
        assert resp.status_code == 400


class TestAuditLogging:
    def test_login_creates_audit(self, client, admin_user, db_session):
        client.post("/api/auth/login", json={"username": "testadmin", "password": "admin123"})
        from app.models import AuditLog
        from sqlalchemy.orm import sessionmaker
        logs = db_session.query(AuditLog).filter(AuditLog.action == "login").all()
        assert len(logs) >= 1
        assert logs[0].username == "testadmin"

    def test_assignment_creates_audit(self, client, operator_headers, db_session):
        from app.models import Van, Driver, AuditLog
        v = Van(code="AV1")
        d = Driver(employee_id="AD1", name="AuditDriver")
        db_session.add_all([v, d])
        db_session.commit()

        client.post("/api/assignments", json={
            "assignment_date": "2026-01-05", "van_id": v.id, "driver_id": d.id,
        }, headers=operator_headers)

        logs = db_session.query(AuditLog).filter(
            AuditLog.action == "create", AuditLog.entity_type == "assignment"
        ).all()
        assert len(logs) >= 1
