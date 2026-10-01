"""Container-only synthetic verification; never use against a production dataset."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener
from uuid import uuid4


ORIGIN = "http://localhost:3100"
BASE_URL = "http://web:3000/api"
OUTPUT = Path("/out")


def initial_environment():
    # Only the caller captures this output to the ignored .env.smoke file.
    print("\n".join([
        "# SYNTHETIC LOCAL VERIFICATION ONLY. Do not expose on a company network.",
        "POSTGRES_PASSWORD=" + secrets.token_hex(32),
        "API_SERVICE_SECRET=" + secrets.token_hex(32),
        "APP_ORIGIN=" + ORIGIN,
        "WEB_PORT=3100",
        "WEB_BIND_ADDRESS=127.0.0.1",
        "",
    ]))


def wait_for_web(opener):
    for _ in range(30):
        try:
            with opener.open(BASE_URL + "/health", timeout=3) as response:
                if json.load(response)["database"]["status"] == "up":
                    return
        except (URLError, TimeoutError):
            time.sleep(1)
    raise RuntimeError("Web/API did not become healthy")


def exercise(resume=False):
    OUTPUT.mkdir(exist_ok=True)
    state_path = OUTPUT / "synthetic-state.json"
    opener = build_opener()
    wait_for_web(opener)

    def request(route, method="GET", data=None, content_type=None, expected=200):
        headers = {"Origin": ORIGIN}
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        req = Request(BASE_URL + route, data=data, headers=headers, method=method)
        try:
            response = opener.open(req, timeout=60)
        except HTTPError as exc:
            response = exc
        with response:
            assert not response.headers.get("Set-Cookie"), "Public API must not create sessions"
            payload = response.read()
            assert response.status == expected, f"{method} {route}: expected {expected}, got {response.status}"
            if response.headers.get_content_type() == "application/json":
                return json.loads(payload)
            return payload

    if resume:
        state = json.loads(state_path.read_text())
        detail = request("/attendance-imports/" + state["importId"] + "/parse-result")
        assert detail["activeRowCount"] == 59 and detail["deletedRowCount"] == 1
        content = request("/attendance-files/" + state["fileId"] + "/download")
        assert hashlib.sha256(content).hexdigest() == state["sha256"]
        summary = json.loads((OUTPUT / "result.json").read_text())
        summary["restartPersistence"] = "passed"
        (OUTPUT / "result.json").write_text(json.dumps(summary, indent=2) + "\n")
        print("PASS: effective rows and identical XLS survived service restart without login")
        return

    request("/attendance-imports")
    request("/auth/login", "POST", {}, expected=404)
    request("/auth/me", expected=404)

    # Fixture code is included only in the engine test image, not the runtime image.
    sys.path.insert(0, "/app")
    from tests.fixtures import write_attendance
    import xlrd
    source = write_attendance(OUTPUT / ("synthetic-" + uuid4().hex + ".xls"), marker=uuid4().hex)
    original = source.read_bytes()
    boundary = "bestar-" + uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{source.name}"\r\n'
            'Content-Type: application/vnd.ms-excel\r\n\r\n').encode() + original + f"\r\n--{boundary}--\r\n".encode()
    content_type = "multipart/form-data; boundary=" + boundary
    uploaded = request("/attendance-imports", "POST", body, content_type)
    assert uploaded["fileSha256"] == hashlib.sha256(original).hexdigest()
    request("/attendance-imports", "POST", body, content_type, expected=409)
    prefix = "/attendance-imports/" + uploaded["id"]
    detail = request(prefix + "/parse", "POST")
    assert detail["activeRowCount"] == 60
    first = request(prefix + "/generate-wage-record", "POST")["generatedFile"]
    row1 = next(row for row in detail["rows"] if row["employeeId"] == "TEST001" and row["workDate"] == "2026-06-01")
    row2 = next(row for row in detail["rows"] if row["employeeId"] == "TEST001" and row["workDate"] == "2026-06-02")
    request(prefix + "/rows/" + row1["id"], "PATCH", {
        "punchTimes": ["08:00", "10:00"], "reason": "Synthetic Docker correction",
        "expectedRevision": detail["attendanceImport"]["dataRevision"],
    })
    request("/attendance-files/" + first["id"] + "/download", expected=409)
    request(prefix + "/rows/" + row2["id"], "DELETE", {"reason": "Synthetic Docker deletion"})
    detail = request(prefix + "/parse", "POST")
    assert detail["activeRowCount"] == 59 and detail["deletedRowCount"] == 1
    corrected = next(row for row in detail["rows"] if row["id"] == row1["id"])
    assert corrected["calculatedHours"] == "1.5"
    exported = request(prefix + "/generate-wage-record", "POST")["generatedFile"]
    content = request("/attendance-files/" + exported["id"] + "/download")
    assert hashlib.sha256(content).hexdigest() == exported["fileSha256"]
    workbook = xlrd.open_workbook(file_contents=content)
    assert workbook.sheet_by_index(0).cell_value(3, 2) == 1.5
    assert source.read_bytes() == original
    output = OUTPUT / (source.stem + "-wage.xls")
    output.write_bytes(content)
    state = {"importId": uploaded["id"], "fileId": exported["id"], "sha256": exported["fileSha256"]}
    state_path.write_text(json.dumps(state))
    summary = {"syntheticOnly": True, "httpFlow": "passed", "loginRequired": False, "activeRows": 59, "deletedRows": 1,
               "downloadBytes": len(content), "source": source.name, "export": output.name,
               "restartPersistence": "pending"}
    (OUTPUT / "result.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("PASS: no-login access, immutable upload, SHA dedup, parse, correction, deletion, reparse and actual XLS download")
    print("Synthetic files saved to storage/docker-verification/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["init", "run", "resume"])
    args = parser.parse_args()
    if args.mode == "init":
        initial_environment()
    else:
        exercise(resume=args.mode == "resume")
