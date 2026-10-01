import hmac
import json
from typing import Annotated
from urllib.parse import quote

from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.exc import DBAPIError

from .attendance import AttendanceService, now
from .config import Settings
from .database import Database
from .errors import ServiceError


class ReasonBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=1000)


class ImportReasonBody(ReasonBody):
    reason: str = Field(min_length=5, max_length=1000)


class CorrectionBody(ReasonBody):
    punchTimes: list[Annotated[str, StringConstraints(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")]] = Field(max_length=32)
    expectedRevision: int = Field(ge=1)


class RequestBoundary:
    """Authenticate the service and cap the actual body before multipart parsing."""
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        async def error(code, status):
            await JSONResponse({"code": code, "message": code}, status_code=status)(
                scope, receive, send,
            )
        if self.settings is None:
            return await error("CONFIGURATION_REQUIRED", 503)
        if scope["path"] != "/health":
            headers = dict(scope["headers"])
            supplied = headers.get(b"x-service-key", b"")
            if not hmac.compare_digest(supplied, self.settings.service_secret.encode()):
                return await error("UNAUTHORIZED", 401)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.settings.max_upload_bytes + 200_000:
                return await error("ATTENDANCE_FILE_TOO_LARGE", 413)
            if not message.get("more_body"):
                break
        replayed = False
        async def replay():
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}
        async def private_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")])
                message = {**message, "headers": headers}
            await send(message)
        await self.app(scope, replay, private_send)


def create_app(settings: Settings | None = None, database: Database | None = None):
    if settings is None:
        try:
            settings = Settings.from_env()
        except ValueError:
            settings = None
    elif settings is not None:
        settings.validate()
    app = FastAPI(title="Bestar Work Hours API", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(RequestBoundary, settings=settings)
    db = database or (Database(settings.database_url) if settings else None)
    service = AttendanceService(db, settings) if settings else None
    app.state.database, app.state.service = db, service

    @app.exception_handler(ServiceError)
    async def service_error(_, exc):
        return JSONResponse({"code": exc.code, "message": exc.code}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        # Pydantic error details can include submitted employee input.
        return JSONResponse({"code": "INVALID_REQUEST", "message": "INVALID_REQUEST"}, status_code=422)

    @app.exception_handler(DBAPIError)
    async def database_error(_, exc):
        # SQL/DSN and employee parameters must never be reflected to the browser.
        return JSONResponse({"code": "DATABASE_UNAVAILABLE", "message": "DATABASE_UNAVAILABLE"}, status_code=503)

    def bounded(value):
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        if len(payload) > settings.max_response_bytes:
            raise ServiceError("ATTENDANCE_RESPONSE_TOO_LARGE", 413)
        return Response(payload, media_type="application/json")

    @app.get("/health")
    def health():
        healthy = db.healthy()
        return JSONResponse({"status": "ok" if healthy else "degraded",
                             "database": {"status": "up" if healthy else "down"},
                             "serverTime": now(), "version": "0.1.0"}, status_code=200 if healthy else 503)

    @app.get("/attendance-imports/deletion-history")
    def import_history(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        return bounded(service.import_history(limit, offset))

    @app.get("/attendance-imports")
    def list_imports(limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0),
                     parseStatus: str | None = None):
        return bounded(service.list_imports(limit, offset, parseStatus))

    @app.post("/attendance-imports")
    def upload(file: UploadFile = File(...)):
        try:
            content = file.file.read(settings.max_upload_bytes + 1)
            return service.upload(file.filename or "", content, "Unattributed")
        finally:
            file.file.close()

    @app.get("/attendance-imports/{import_id}")
    def get_import(import_id: str):
        return bounded(service.detail(import_id)["attendanceImport"])

    @app.get("/attendance-imports/{import_id}/parse-result")
    def detail(import_id: str):
        return bounded(service.detail(import_id))

    @app.post("/attendance-imports/{import_id}/parse")
    def parse(import_id: str):
        return bounded(service.parse(import_id, "Unattributed"))

    @app.post("/attendance-imports/{import_id}/generate-wage-record")
    def generate(import_id: str):
        return bounded(service.generate(import_id, "Unattributed"))

    @app.get("/attendance-imports/{import_id}/files")
    def list_files(import_id: str, limit: int = Query(100, ge=1, le=100),
                   offset: int = Query(0, ge=0)):
        return bounded(service.list_files(import_id, limit, offset))

    @app.get("/attendance-imports/{import_id}/row-history")
    def row_history(import_id: str, limit: int = Query(50, ge=1, le=100),
                    offset: int = Query(0, ge=0)):
        return bounded(service.row_history(import_id, limit, offset))

    @app.delete("/attendance-imports/{import_id}/rows/{row_id}")
    def delete_row(import_id: str, row_id: str, body: ReasonBody):
        return bounded(service.change_row(import_id, row_id, body.reason, "Unattributed"))

    @app.patch("/attendance-imports/{import_id}/rows/{row_id}")
    def correct_row(import_id: str, row_id: str, body: CorrectionBody):
        return bounded(service.change_row(import_id, row_id, body.reason, "Unattributed",
                                         body.punchTimes, body.expectedRevision))

    @app.get("/attendance-imports/{import_id}/deletion-impact")
    def impact(import_id: str):
        return bounded(service.impact(import_id))

    @app.delete("/attendance-imports/{import_id}")
    def delete_import(import_id: str, body: ImportReasonBody):
        return bounded(service.delete_import(import_id, body.reason, "Unattributed"))

    @app.get("/attendance-files/{file_id}/download")
    def download(file_id: str):
        filename, content = service.download(file_id)
        return Response(content, media_type="application/vnd.ms-excel", headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename),
        })

    return app
