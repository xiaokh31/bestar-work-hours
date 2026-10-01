"""Synthetic HTTP/storage contract tests; never real employee acceptance."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
from pathlib import Path
import os
from uuid import uuid4
from sqlalchemy.engine import make_url
from sqlalchemy import text, inspect

from fastapi.testclient import TestClient
import pytest
import xlrd

from bestar_work_hours.service.config import Settings
from bestar_work_hours.service.database import Database, imports, rows, files, audit, versions
from bestar_work_hours.service.errors import ServiceError
from bestar_work_hours.service.http import create_app
import bestar_work_hours.service.attendance as attendance_module
from sqlalchemy import select

from .fixtures import write_attendance

SECRET = "synthetic-test-service-secret-only-2026"


@pytest.fixture(params=["sqlite"] + (["postgresql"] if os.environ.get("TEST_DATABASE_URL") else []))
def system(tmp_path, request):
    url = "sqlite:///" + (tmp_path / "test.db").as_posix()
    admin = None
    schema = None
    if request.param == "postgresql":
        url = os.environ["TEST_DATABASE_URL"]
        parsed_url = make_url(url)
        assert parsed_url.database == "synthetic_test", "Only the isolated synthetic test database is allowed"
        schema = "test_" + uuid4().hex
        admin = Database(url)
        with admin.transaction() as con:
            con.execute(text('CREATE SCHEMA "' + schema + '"'))
        url = parsed_url.update_query_dict({"options": "-csearch_path=" + schema}).render_as_string(hide_password=False)
    config = Settings(url, SECRET, environment="test")
    db = Database(config.database_url)
    db.migrate()
    app = create_app(config, db)
    with TestClient(app, headers={"x-service-key": SECRET}) as client:
        yield client, db, config, app
    db.engine.dispose()
    if admin:
        with admin.transaction() as con:
            con.execute(text('DROP SCHEMA "' + schema + '" CASCADE'))
        admin.engine.dispose()


def uploaded(client, tmp_path, employees=2):
    content = write_attendance(tmp_path / "synthetic-api.xls", employee_count=employees).read_bytes()
    response = client.post("/attendance-imports", files={"file": ("synthetic.xls", content)})
    assert response.status_code == 200, response.text
    return response.json()["id"], content


def parsed(client, import_id):
    response = client.post("/attendance-imports/" + import_id + "/parse")
    assert response.status_code == 200, response.text
    return response.json()


def generated(client, import_id):
    response = client.post("/attendance-imports/" + import_id + "/generate-wage-record")
    assert response.status_code == 200, response.text
    return response.json()["generatedFile"]["id"]


def test_no_user_auth_or_session_but_internal_service_key_is_required(system):
    client, db, config, app = system
    with TestClient(app) as direct:
        assert direct.get("/attendance-imports").status_code == 401
        assert direct.get("/attendance-files/unknown/download").status_code == 401
        assert direct.get("/attendance-imports", headers={"x-service-key": SECRET}).status_code == 200
    assert client.get("/attendance-imports").status_code == 200
    assert not client.cookies
    for path, method in [("/auth/login", "POST"), ("/auth/logout", "POST"), ("/auth/me", "GET")]:
        assert client.request(method, path).status_code == 404
    assert not {"manager_sessions", "login_throttle"} & set(inspect(db.engine).get_table_names())


def test_v1_upgrade_removes_login_state_and_preserves_attendance(system, tmp_path):
    client, db, config, app = system
    import_id, _ = uploaded(client, tmp_path)
    parsed(client, import_id)
    file_id = generated(client, import_id)
    tables = (imports, rows, files, audit)
    with db.transaction() as con:
        before = [con.execute(select(table)).mappings().all() for table in tables]
        con.execute(versions.update().values(version=1))
        con.execute(text("CREATE TABLE manager_sessions (token_hash VARCHAR(64) PRIMARY KEY, auth_version VARCHAR(64), expires INTEGER)"))
        con.execute(text("CREATE TABLE login_throttle (bucket INTEGER PRIMARY KEY, attempts INTEGER)"))
        con.execute(text("INSERT INTO manager_sessions VALUES ('synthetic-token', 'synthetic-version', 0)"))
    assert not db.healthy()
    db.migrate()
    db.migrate()  # Repeat deployment is safe.
    assert db.healthy()
    assert not {"manager_sessions", "login_throttle"} & set(inspect(db.engine).get_table_names())
    with db.transaction() as con:
        after = [con.execute(select(table)).mappings().all() for table in tables]
    assert after == before
    assert client.get("/attendance-files/" + file_id + "/download").status_code == 200


def test_upload_parse_export_survive_new_instance_without_session(system, tmp_path):
    client, db, config, app = system
    import_id, original = uploaded(client, tmp_path)
    detail = parsed(client, import_id)
    assert detail["activeRowCount"] == 60
    assert detail["attendanceImport"]["parserVersion"] == "wage-attendance-v2"
    file_id = generated(client, import_id)
    with TestClient(create_app(config, Database(config.database_url)), headers={
        "x-service-key": SECRET,
    }) as fresh:
        response = fresh.get("/attendance-files/" + file_id + "/download")
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/vnd.ms-excel"
        assert response.headers["cache-control"] == "no-store"
        book = xlrd.open_workbook(file_contents=response.content)
        assert book.nsheets == 17
        assert book.sheet_by_index(0).cell_value(3, 2) == 8.5
        assert book.sheet_by_index(0).cell_value(34, 2) == 255
        assert fresh.get("/attendance-imports").json()["items"][0]["id"] == import_id
    with db.engine.connect() as con:
        record = con.execute(select(imports).where(imports.c.id == import_id)).mappings().one()
        assert record["original"] == original
        assert record["sha256"] == hashlib.sha256(original).hexdigest()
        assert record["parsed"]["rawRows"]


def test_sha_dedup_is_content_based_and_preserved_after_batch_deletion(system, tmp_path):
    client, db, config, app = system
    import_id, content = uploaded(client, tmp_path)
    assert client.post("/attendance-imports", files={"file": ("renamed.xls", content)}).status_code == 409
    detail = parsed(client, import_id)
    file_id = generated(client, import_id)
    response = client.request(
        "DELETE", "/attendance-imports/" + import_id, json={"reason": "Synthetic duplicate batch"})
    assert response.status_code == 200, response.text
    assert client.get("/attendance-imports").json()["items"] == []
    assert client.get("/attendance-files/" + file_id + "/download").status_code == 410
    assert client.post("/attendance-imports", files={"file": ("renamed.xls", content)}).status_code == 409
    history = client.get("/attendance-imports/deletion-history").json()
    assert history["total"] == 1
    assert history["items"][0]["reason"] == "Synthetic duplicate batch"


def test_deleted_row_stays_deleted_after_reparse_and_export_is_invalidated(system, tmp_path):
    client, db, config, app = system
    import_id, _ = uploaded(client, tmp_path)
    detail = parsed(client, import_id)
    row = next(r for r in detail["rows"] if r["employeeId"] == "TEST001" and r["workDate"] == "2026-06-01")
    file_id = generated(client, import_id)
    url = "/attendance-imports/" + import_id
    response = client.request("DELETE", url + "/rows/" + row["id"], json={"reason": "Synthetic row exclusion"})
    assert response.status_code == 200, response.text
    assert client.get("/attendance-files/" + file_id + "/download").status_code == 409
    detail = parsed(client, import_id)
    assert detail["activeRowCount"] == 59
    assert detail["deletedRowCount"] == 1
    assert row["id"] not in [r["id"] for r in detail["rows"]]
    assert client.get(url + "/row-history").json()["total"] == 1
    download = client.get("/attendance-files/" + generated(client, import_id) + "/download")
    book = xlrd.open_workbook(file_contents=download.content)
    assert book.sheet_by_index(0).cell_value(3, 2) == "/"
    assert book.sheet_by_index(0).cell_value(34, 2) == 246.5


def test_correction_uses_engine_and_survives_reparse_with_raw_evidence(system, tmp_path):
    client, db, config, app = system
    import_id, _ = uploaded(client, tmp_path)
    detail = parsed(client, import_id)
    row = next(r for r in detail["rows"] if r["employeeId"] == "TEST001" and r["workDate"] == "2026-06-01")
    file_id = generated(client, import_id)
    url = "/attendance-imports/" + import_id + "/rows/" + row["id"]
    body = {"punchTimes": ["10:00", "08:00"], "reason": "Synthetic correction", "expectedRevision": 1}
    assert client.patch(url, json=body).status_code == 200
    assert client.patch(url, json=body).status_code == 409
    assert client.get("/attendance-files/" + file_id + "/download").status_code == 409
    detail = parsed(client, import_id)
    corrected = next(r for r in detail["rows"] if r["id"] == row["id"])
    assert corrected["calculatedHours"] == "1.5"
    history = client.get("/attendance-imports/" + import_id + "/row-history").json()
    assert history["items"][0]["actor"] == {"id": None, "displayLabel": "Unattributed"}
    assert corrected["rawJson"]["rawCellValues"] == row["rawJson"]["rawCellValues"]
    response = client.get("/attendance-files/" + generated(client, import_id) + "/download")
    sheet = xlrd.open_workbook(file_contents=response.content).sheet_by_index(0)
    assert sheet.cell_value(3, 2) == 1.5
    assert sheet.cell_value(34, 2) == 248


def test_generation_detects_mutation_before_publishing(system, tmp_path, monkeypatch):
    client, db, config, app = system
    import_id, _ = uploaded(client, tmp_path)
    row = parsed(client, import_id)["rows"][0]
    original_generate = attendance_module.generate_wage_record
    def change_during_generation(**kwargs):
        result = original_generate(**kwargs)
        app.state.service.change_row(import_id, row["id"], "Concurrent test deletion", "test-manager")
        return result
    monkeypatch.setattr(attendance_module, "generate_wage_record", change_during_generation)
    response = client.post("/attendance-imports/" + import_id + "/generate-wage-record")
    assert response.status_code == 409
    assert client.get("/attendance-imports/" + import_id + "/files").json()["items"] == []


def test_duplicate_upload_is_database_enforced_under_concurrency(system, tmp_path):
    client, db, config, app = system
    content = write_attendance(tmp_path / "concurrent.xls").read_bytes()
    def upload(_):
        try:
            app.state.service.upload("synthetic.xls", content, "test-manager")
            return 200
        except ServiceError as exc:
            return exc.status
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(upload, range(4))) == [200, 409, 409, 409]


def test_invalid_and_oversized_uploads_are_rejected(system):
    client, _, _, _ = system
    assert client.post("/attendance-imports", files={"file": ("fake.xls", b"garbage")}).status_code == 400
    assert client.post("/attendance-imports", files={"file": ("wrong.xlsx", b"garbage")}).status_code == 400
    response = client.post("/attendance-imports", content=(b"x" * 1_100_000 for _ in range(3)))
    assert response.status_code == 413
    assert client.get("/attendance-imports").json()["items"] == []


def test_template_capacity_failure_is_persisted_without_downloadable_file(system, tmp_path):
    client, _, _, _ = system
    import_id, _ = uploaded(client, tmp_path, employees=17)
    parsed(client, import_id)
    response = client.post("/attendance-imports/" + import_id + "/generate-wage-record")
    assert response.status_code == 422
    assert response.json()["code"] == "WAGE_TEMPLATE_EMPLOYEE_CAPACITY_EXCEEDED"
    failed = client.get("/attendance-imports/" + import_id + "/files").json()["items"][0]
    assert failed["status"] == "FAILED"
    assert client.get("/attendance-files/" + failed["id"] + "/download").status_code == 409


def test_production_rejects_sqlite_and_missing_configuration(monkeypatch):
    with pytest.raises(ValueError):
        Settings("sqlite:///:memory:", SECRET).validate()
    for name in ("DATABASE_URL", "API_SERVICE_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 503
        assert client.get("/attendance-imports").status_code == 503



def test_validation_does_not_echo_sensitive_input(system):
    client, *_ = system
    value = "sensitive-employee-input-" * 60
    response = client.patch("/attendance-imports/example/rows/example", json={"reason": value, "punchTimes": [], "expectedRevision": 1})
    assert response.status_code == 422
    assert value not in response.text
    assert response.json()["code"] == "INVALID_REQUEST"


def test_generated_history_pagination_can_reach_older_exports(system, tmp_path):
    client, *_ = system
    import_id, _ = uploaded(client, tmp_path)
    parsed(client, import_id)
    expected = [generated(client, import_id) for _ in range(3)]
    url = "/attendance-imports/" + import_id + "/files"
    first = client.get(url + "?limit=2&offset=0").json()["items"]
    second = client.get(url + "?limit=2&offset=2").json()["items"]
    assert len(first) == 2 and len(second) == 1
    assert {f["id"] for f in first + second} == set(expected)
    assert client.get(url + "?limit=101").status_code == 422
    assert client.get("/attendance-files/" + second[0]["id"] + "/download").status_code == 200
