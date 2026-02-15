import io

from app.models import Van, Driver


class TestUploadVans:
    def test_upload_csv(self, client, db_session, admin_headers):
        csv_content = "code,description\nVAN-100,Test Van\nVAN-101,Another Van\n"
        files = {"file": ("vans.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        resp = client.post("/api/upload/vans", files=files, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["records_imported"] == 2
        assert data["records_errors"] == 0

        vans = db_session.query(Van).all()
        assert len(vans) == 2

    def test_upload_duplicate_vans_skipped(self, client, db_session, admin_headers):
        csv = "code,description\nVAN-100,Test\n"
        files1 = {"file": ("v.csv", io.BytesIO(csv.encode()), "text/csv")}
        resp1 = client.post("/api/upload/vans", files=files1, headers=admin_headers)
        assert resp1.json()["records_imported"] == 1

        files2 = {"file": ("v.csv", io.BytesIO(csv.encode()), "text/csv")}
        resp2 = client.post("/api/upload/vans", files=files2, headers=admin_headers)
        assert resp2.json()["records_imported"] == 0
        assert resp2.json()["records_skipped"] == 1

        assert db_session.query(Van).count() == 1

    def test_upload_empty_code_error(self, client, db_session, admin_headers):
        csv = "code,description\n,No Code Van\nVAN-200,Good Van\n"
        files = {"file": ("v.csv", io.BytesIO(csv.encode()), "text/csv")}
        resp = client.post("/api/upload/vans", files=files, headers=admin_headers)
        data = resp.json()
        assert data["records_imported"] == 1
        assert data["records_errors"] == 1
        assert "empty code" in data["errors"][0]

    def test_upload_wrong_format(self, client, db_session, admin_headers):
        files = {"file": ("v.txt", io.BytesIO(b"hello"), "text/plain")}
        resp = client.post("/api/upload/vans", files=files, headers=admin_headers)
        assert resp.status_code == 400

    def test_upload_missing_column(self, client, db_session, admin_headers):
        csv = "name,description\nTest,Desc\n"
        files = {"file": ("v.csv", io.BytesIO(csv.encode()), "text/csv")}
        resp = client.post("/api/upload/vans", files=files, headers=admin_headers)
        assert resp.status_code == 400
        assert "code" in resp.json()["detail"].lower()

    def test_upload_vehicles_data_format(self, client, db_session, admin_headers):
        """Test auto-detection of VehiclesData format with licensePlateNumber."""
        csv = "licensePlateNumber,operationalStatus,make,model\nAB12CDE,OPERATIONAL,Ford,Transit\nXY34FGH,GROUNDED,Mercedes,Sprinter\n"
        files = {"file": ("vehicles.csv", io.BytesIO(csv.encode()), "text/csv")}
        resp = client.post("/api/upload/vans", files=files, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["records_imported"] == 2

        van1 = db_session.query(Van).filter(Van.code == "AB12CDE").first()
        assert van1 is not None
        assert van1.operational_status == "OPERATIONAL"
        assert van1.description == "Ford Transit"

        van2 = db_session.query(Van).filter(Van.code == "XY34FGH").first()
        assert van2.operational_status == "GROUNDED"
        assert van2.description == "Mercedes Sprinter"

    def test_upload_csv_with_operational_status(self, client, db_session, admin_headers):
        """Test simple CSV format with operational_status column."""
        csv = "code,description,operational_status\nVAN-300,Ford Transit,OPERATIONAL\nVAN-301,Mercedes,GROUNDED\n"
        files = {"file": ("v.csv", io.BytesIO(csv.encode()), "text/csv")}
        resp = client.post("/api/upload/vans", files=files, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["records_imported"] == 2

        van = db_session.query(Van).filter(Van.code == "VAN-300").first()
        assert van.operational_status == "OPERATIONAL"


class TestUploadDrivers:
    def test_upload_csv(self, client, db_session, admin_headers):
        csv = "employee_id,name\nEMP-100,John Smith\nEMP-101,Jane Doe\n"
        files = {"file": ("d.csv", io.BytesIO(csv.encode()), "text/csv")}
        resp = client.post("/api/upload/drivers", files=files, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["records_imported"] == 2

        drivers = db_session.query(Driver).all()
        assert len(drivers) == 2

    def test_upload_missing_name_error(self, client, db_session, admin_headers):
        csv = "employee_id,name\nEMP-100,\n"
        files = {"file": ("d.csv", io.BytesIO(csv.encode()), "text/csv")}
        resp = client.post("/api/upload/drivers", files=files, headers=admin_headers)
        data = resp.json()
        assert data["records_errors"] == 1
        assert "empty name" in data["errors"][0]

    def test_upload_duplicate_drivers_updates_name(self, client, db_session, admin_headers):
        csv1 = "employee_id,name\nEMP-100,Old Name\n"
        files1 = {"file": ("d.csv", io.BytesIO(csv1.encode()), "text/csv")}
        client.post("/api/upload/drivers", files=files1, headers=admin_headers)

        csv2 = "employee_id,name\nEMP-100,New Name\n"
        files2 = {"file": ("d.csv", io.BytesIO(csv2.encode()), "text/csv")}
        resp2 = client.post("/api/upload/drivers", files=files2, headers=admin_headers)
        assert resp2.json()["records_skipped"] == 1

        driver = db_session.query(Driver).filter(Driver.employee_id == "EMP-100").first()
        assert driver.name == "New Name"

    def test_upload_schedule_format(self, client, db_session, admin_headers):
        """Test auto-detection of Schedule format with Associate name."""
        csv = (
            "Time stamp,Company,Station\n"
            "08/02/2026,Generation Group,DRR1\n"
            "\n"
            "Associate name,Transporter ID,Sun 08/Feb\n"
            "Total rostered,,19\n"
            "John Smith,A1IJXPH2IRZX4C,Standard Parcel\n"
            "Maria Garcia,A2LHHOJQDNXRJF,Standard Parcel\n"
        )
        files = {"file": ("schedule.csv", io.BytesIO(csv.encode()), "text/csv")}
        resp = client.post("/api/upload/drivers", files=files, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["records_imported"] == 2
        assert data["records_errors"] == 0

        d1 = db_session.query(Driver).filter(Driver.employee_id == "A1IJXPH2IRZX4C").first()
        assert d1 is not None
        assert d1.name == "John Smith"

        d2 = db_session.query(Driver).filter(Driver.employee_id == "A2LHHOJQDNXRJF").first()
        assert d2.name == "Maria Garcia"
