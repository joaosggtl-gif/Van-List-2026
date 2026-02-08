from app.models import Van, Driver


class TestVanBlocking:
    """Test that a van cannot be assigned to two drivers on the same day."""

    def _seed(self, db):
        v1 = Van(code="VAN-001", description="Test Van 1")
        v2 = Van(code="VAN-002", description="Test Van 2")
        d1 = Driver(employee_id="EMP-001", name="Driver One")
        d2 = Driver(employee_id="EMP-002", name="Driver Two")
        db.add_all([v1, v2, d1, d2])
        db.commit()
        return v1, v2, d1, d2

    def test_create_assignment(self, client, db_session, operator_headers):
        v1, v2, d1, d2 = self._seed(db_session)
        resp = client.post("/api/assignments", json={
            "assignment_date": "2026-01-05",
            "van_id": v1.id,
            "driver_id": d1.id,
        }, headers=operator_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["van"]["code"] == "VAN-001"
        assert data["driver"]["employee_id"] == "EMP-001"

    def test_van_blocked_same_day(self, client, db_session, operator_headers):
        v1, v2, d1, d2 = self._seed(db_session)

        resp1 = client.post("/api/assignments", json={
            "assignment_date": "2026-01-05",
            "van_id": v1.id,
            "driver_id": d1.id,
        }, headers=operator_headers)
        assert resp1.status_code == 201

        resp2 = client.post("/api/assignments", json={
            "assignment_date": "2026-01-05",
            "van_id": v1.id,
            "driver_id": d2.id,
        }, headers=operator_headers)
        assert resp2.status_code == 409
        assert "already assigned" in resp2.json()["detail"]

    def test_driver_blocked_same_day(self, client, db_session, operator_headers):
        v1, v2, d1, d2 = self._seed(db_session)

        resp1 = client.post("/api/assignments", json={
            "assignment_date": "2026-01-05",
            "van_id": v1.id,
            "driver_id": d1.id,
        }, headers=operator_headers)
        assert resp1.status_code == 201

        resp2 = client.post("/api/assignments", json={
            "assignment_date": "2026-01-05",
            "van_id": v2.id,
            "driver_id": d1.id,
        }, headers=operator_headers)
        assert resp2.status_code == 409
        assert "already has an assignment" in resp2.json()["detail"]

    def test_same_van_different_day_ok(self, client, db_session, operator_headers):
        v1, v2, d1, d2 = self._seed(db_session)

        resp1 = client.post("/api/assignments", json={
            "assignment_date": "2026-01-05",
            "van_id": v1.id,
            "driver_id": d1.id,
        }, headers=operator_headers)
        assert resp1.status_code == 201

        resp2 = client.post("/api/assignments", json={
            "assignment_date": "2026-01-06",
            "van_id": v1.id,
            "driver_id": d2.id,
        }, headers=operator_headers)
        assert resp2.status_code == 201

    def test_delete_and_reassign(self, client, db_session, operator_headers):
        v1, v2, d1, d2 = self._seed(db_session)

        resp1 = client.post("/api/assignments", json={
            "assignment_date": "2026-01-05",
            "van_id": v1.id,
            "driver_id": d1.id,
        }, headers=operator_headers)
        assert resp1.status_code == 201
        assignment_id = resp1.json()["id"]

        resp_del = client.delete(f"/api/assignments/{assignment_id}", headers=operator_headers)
        assert resp_del.status_code == 200

        resp3 = client.post("/api/assignments", json={
            "assignment_date": "2026-01-05",
            "van_id": v1.id,
            "driver_id": d2.id,
        }, headers=operator_headers)
        assert resp3.status_code == 201

    def test_list_assignments_by_date(self, client, db_session, operator_headers):
        v1, v2, d1, d2 = self._seed(db_session)

        client.post("/api/assignments", json={
            "assignment_date": "2026-01-05",
            "van_id": v1.id,
            "driver_id": d1.id,
        }, headers=operator_headers)
        client.post("/api/assignments", json={
            "assignment_date": "2026-01-05",
            "van_id": v2.id,
            "driver_id": d2.id,
        }, headers=operator_headers)

        resp = client.get("/api/assignments?date_from=2026-01-05", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_available_vans_excludes_assigned(self, client, db_session, operator_headers):
        v1, v2, d1, d2 = self._seed(db_session)

        client.post("/api/assignments", json={
            "assignment_date": "2026-01-05",
            "van_id": v1.id,
            "driver_id": d1.id,
        }, headers=operator_headers)

        resp = client.get("/api/assignments/available-vans?assignment_date=2026-01-05", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        codes = [v["code"] for v in data]
        assert "VAN-001" not in codes
        assert "VAN-002" in codes

    def test_available_drivers_excludes_assigned(self, client, db_session, operator_headers):
        v1, v2, d1, d2 = self._seed(db_session)

        client.post("/api/assignments", json={
            "assignment_date": "2026-01-05",
            "van_id": v1.id,
            "driver_id": d1.id,
        }, headers=operator_headers)

        resp = client.get("/api/assignments/available-drivers?assignment_date=2026-01-05", headers=operator_headers)
        assert resp.status_code == 200
        data = resp.json()
        ids = [d["employee_id"] for d in data]
        assert "EMP-001" not in ids
        assert "EMP-002" in ids
