import hashlib
import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import xlrd
from sqlalchemy import select, insert, update, func
from sqlalchemy.exc import IntegrityError

from bestar_work_hours.serialization import json_ready
from bestar_work_hours.wage import generate_wage_record, parse_attendance_workbook
from bestar_work_hours.wage.attendance import (
    AttendanceParseResult, WageFormatType, _employee_summaries, calculate_attendance_hours,
)
from bestar_work_hours.wage.template import default_template_path
from .database import imports, rows, files, audit
from .errors import ServiceError
from .persisted import _persisted_day, _persisted_issue


def now():
    return datetime.now(timezone.utc).isoformat()


def row_key(day):
    identity = [day.get(key) for key in ("employeeId", "employeeName", "department", "workDate", "rowNumbers")]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def row_dto(row):
    data = row["data"]
    return {**data, "id": row["id"], "rowKey": row["row_key"], "rawJson": data,
            **{key: str(data[key]) if data.get(key) is not None else None
               for key in ("pairedGrossHours", "lunchHours", "calculatedHours")}}


def effective_issues(record, active):
    parsed = record["parsed"] or {}
    # Date-specific issues come from effective rows, so deletions/corrections are
    # reflected in both export eligibility and UI, while the original stays stored.
    return {
        key: [issue for issue in parsed.get(key, []) if not issue.get("workDate")]
             + [issue for row in active for issue in row["data"].get(key, [])]
        for key in ("warnings", "errors")
    }


def import_dto(record, active=None):
    parsed = record["parsed"] or {}
    issues = effective_issues(record, active) if active is not None else parsed
    days = [r["data"] for r in active] if active is not None else parsed.get("days", [])
    errors, warnings = issues.get("errors", []), issues.get("warnings", [])
    status = "NOT_PARSED" if record["parsed"] is None else "ERROR" if errors else "WARNING" if warnings else "PARSED"
    return {
        "id": record["id"], "originalFilename": record["filename"], "filenameReviewCode": None,
        "fileSha256": record["sha256"], "mimeType": "application/vnd.ms-excel",
        "fileSizeBytes": str(len(record["original"])), "importStatus": "DELETED" if record["deleted"] else "UPLOADED",
        "parseStatus": status, "parserVersion": parsed.get("parserVersion"),
        "settlementMonth": (parsed.get("periodStart") or "")[:7] or None,
        "periodStart": parsed.get("periodStart"), "periodEnd": parsed.get("periodEnd"),
        "employeeCount": len({(d["employeeId"], d["employeeName"], d["department"]) for d in days}),
        "dayCount": len(days), "warningCount": len(warnings), "errorCount": len(errors),
        "errorMessage": errors[0]["code"] if errors else None, "dataRevision": record["revision"],
        "createdAt": record["created_at"], "updatedAt": record["updated_at"],
    }


def file_dto(file):
    return {
        "id": file["id"], "attendanceImportId": file["import_id"], "fileType": "WAGE_RECORD_XLS",
        "storagePath": file["filename"] or "generation-failed.xls",
        "fileSha256": file["sha256"], "mimeType": "application/vnd.ms-excel",
        "fileSizeBytes": str(len(file["content"])) if file.get("content") is not None else (str(file["_size"]) if file.get("_size") is not None else None),
        "status": file["status"], "errorMessage": file["report"].get("errorCode"),
        "createdAt": file["created_at"], "updatedAt": file["created_at"],
    }


class AttendanceService:
    def __init__(self, db, config):
        self.db, self.config = db, config

    def _load(self, con, import_id, include_deleted=False):
        record = con.execute(select(imports).where(imports.c.id == import_id)).mappings().first()
        if not record:
            raise ServiceError("ATTENDANCE_IMPORT_NOT_FOUND", 404)
        if record["deleted"] and not include_deleted:
            raise ServiceError("ATTENDANCE_IMPORT_DELETED", 410)
        return record

    def _rows(self, con, import_id, include_deleted=False):
        query = select(rows).where(rows.c.import_id == import_id)
        if not include_deleted:
            query = query.where(rows.c.deleted.is_(False))
        return list(con.execute(query.order_by(rows.c.row_key)).mappings())

    def _change(self, con, record, **values):
        # Database-level compare-and-swap; no process-local mutex or background job.
        result = con.execute(update(imports).where(
            imports.c.id == record["id"], imports.c.revision == record["revision"],
            imports.c.deleted.is_(False),
        ).values(revision=record["revision"] + 1, updated_at=now(), **values))
        if result.rowcount != 1:
            raise ServiceError("ATTENDANCE_DATA_REVISION_CHANGED", 409)
        affected = list(con.execute(select(files.c.id).where(
            files.c.import_id == record["id"], files.c.status == "READY",
        )).mappings())
        con.execute(update(files).where(files.c.import_id == record["id"], files.c.status == "READY")
                    .values(status="SUPERSEDED"))
        return [{"id": f["id"], "fileType": "WAGE_RECORD_XLS", "previousStatus": "READY", "nextStatus": "SUPERSEDED", "status": "SUPERSEDED"}
                for f in affected]

    def _audit(self, con, record, action, actor, snapshot, reason="", row_id=None):
        event = dict(id=str(uuid4()), import_id=record["id"], row_id=row_id, action=action,
                     actor=actor, reason=reason, snapshot=snapshot, occurred_at=now())
        con.execute(insert(audit).values(**event))
        return event

    def upload(self, filename, content, actor):
        filename = Path(filename.replace("\\", "/")).name.strip()
        if not filename.lower().endswith(".xls") or len(filename) > 240 or any(ord(c) < 32 for c in filename):
            raise ServiceError("UNSUPPORTED_ATTENDANCE_FILE")
        if not content or len(content) > self.config.max_upload_bytes:
            raise ServiceError("ATTENDANCE_FILE_TOO_LARGE", 413)
        # Actual BIFF parsing, not extension/MIME trust. Layout errors remain visible
        # when parsed; unreadable files never enter the attendance repository.
        try:
            workbook = xlrd.open_workbook(file_contents=content)
            if not workbook.nsheets or workbook.sheet_by_index(0).nrows > 2048 or workbook.sheet_by_index(0).ncols > 64:
                raise ServiceError("ATTENDANCE_WORKBOOK_TOO_LARGE", 413)
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError("UNSUPPORTED_ATTENDANCE_FILE") from exc
        record = dict(id=str(uuid4()), sha256=hashlib.sha256(content).hexdigest(), filename=filename,
                      original=content, parsed=None, revision=0, deleted=False, created_at=now(), updated_at=now())
        record["summary"] = import_dto(record)
        try:
            with self.db.transaction() as con:
                con.execute(insert(imports).values(**record))
                self._audit(con, record, "UPLOADED", actor, {"sha256": record["sha256"], "filename": filename})
        except IntegrityError as exc:
            raise ServiceError("DUPLICATE_ATTENDANCE_IMPORT", 409) from exc
        return import_dto(record)

    def _refresh_summary(self, con, import_id):
        record = self._load(con, import_id)
        summary = import_dto(record, self._rows(con, import_id))
        con.execute(update(imports).where(imports.c.id == import_id).values(summary=summary))

    def list_imports(self, limit=25, offset=0, parse_status=None):
        with self.db.engine.connect() as con:
            query = select(imports.c.summary, imports.c.updated_at).where(imports.c.deleted.is_(False))
            if parse_status:
                query = query.where(imports.c.summary["parseStatus"].as_string() == parse_status)
            records = con.execute(query.order_by(imports.c.created_at.desc()).limit(limit).offset(offset)).mappings()
            items = [{**record["summary"], "updatedAt": record["updated_at"]} for record in records]
            return {"items": items, "limit": limit, "offset": offset}

    def detail(self, import_id):
        with self.db.engine.connect() as con:
            record = self._load(con, import_id)
            all_rows = self._rows(con, import_id, True)
            active = [r for r in all_rows if not r["deleted"]]
            return {"attendanceImport": import_dto(record, active), "rows": [row_dto(r) for r in active],
                    **effective_issues(record, active), "activeRowCount": len(active),
                    "deletedRowCount": len(all_rows) - len(active)}

    def parse(self, import_id, actor):
        with self.db.engine.connect() as con:
            record = self._load(con, import_id)
        with tempfile.TemporaryDirectory(prefix="bestar-parse-") as temp:
            source = Path(temp) / "original.xls"
            source.write_bytes(record["original"])
            parsed = json_ready(parse_attendance_workbook(source))
        with self.db.transaction() as con:
            self._change(con, record, parsed=parsed)
            existing = {r["row_key"]: r for r in self._rows(con, import_id, True)}
            seen = set()
            for day in parsed["days"]:
                key = row_key(day)
                if key in seen:
                    raise ServiceError("ATTENDANCE_ROW_IDENTITY_CONFLICT", 409)
                seen.add(key)
                if key not in existing:
                    con.execute(insert(rows).values(id=str(uuid5(UUID(import_id), key)), import_id=import_id,
                                                   row_key=key, data=day, deleted=False, corrected=False))
                elif not existing[key]["deleted"] and not existing[key]["corrected"]:
                    con.execute(update(rows).where(rows.c.id == existing[key]["id"]).values(data=day))
            # Immutable original + same parser must produce the same row identities.
            if set(existing) - seen:
                raise ServiceError("ATTENDANCE_ROW_AUDIT_INCONSISTENT", 409)
            self._refresh_summary(con, import_id)
            self._audit(con, record, "PARSED", actor, {"parserVersion": parsed["parserVersion"],
                        "revision": record["revision"] + 1, "warnings": parsed["warnings"], "errors": parsed["errors"]})
        return self.detail(import_id)

    def list_files(self, import_id, limit=100, offset=0):
        with self.db.engine.connect() as con:
            self._load(con, import_id)
            result = con.execute(select(*[c for c in files.c if c.name != "content"], func.length(files.c.content).label("_size")).where(files.c.import_id == import_id)
                                 .order_by(files.c.created_at.desc(), files.c.id).limit(limit).offset(offset)).mappings()
            return {"items": [file_dto(f) for f in result]}

    def generate(self, import_id, actor):
        with self.db.engine.connect() as con:
            record = self._load(con, import_id)
            active = self._rows(con, import_id)
        saved = record["parsed"]
        if not saved:
            raise ServiceError("ATTENDANCE_IMPORT_NOT_PARSED", 409)
        if not active:
            raise ServiceError("ATTENDANCE_ACTIVE_ROWS_REQUIRED", 409)
        days = tuple(_persisted_day(row["data"]) for row in active)
        issues = effective_issues(record, active)
        parsed = AttendanceParseResult(
            formatType=WageFormatType(saved["formatType"]), parserVersion=saved["parserVersion"],
            sourceSheet=saved["sourceSheet"], periodStart=date.fromisoformat(saved["periodStart"]) if saved["periodStart"] else None,
            periodEnd=date.fromisoformat(saved["periodEnd"]) if saved["periodEnd"] else None,
            confidence=saved["confidence"], employees=tuple(_employee_summaries(list(days))), days=days, rawRows=(),
            warnings=tuple(_persisted_issue(i) for i in issues["warnings"]),
            errors=tuple(_persisted_issue(i) for i in issues["errors"]), assumptions=tuple(saved["assumptions"]),
        )
        with tempfile.TemporaryDirectory(prefix="bestar-generate-") as temp:
            result = generate_wage_record(attendance_result=parsed, template_path=default_template_path(), output_dir=Path(temp))
            content = result.outputPath.read_bytes() if result.validated and not result.errors else None
            report = json_ready(result)
            # Do not persist ephemeral paths as storage locators.
            for key in ("outputPath", "templatePath", "manifestPath"):
                report.pop(key, None)
        if content is not None and len(content) > self.config.max_response_bytes:
            raise ServiceError("GENERATED_FILE_TOO_LARGE", 413)
        file = dict(id=str(uuid4()), import_id=import_id, revision=record["revision"],
                    status="READY" if content is not None else "FAILED", filename=result.generatedFilename,
                    sha256=hashlib.sha256(content).hexdigest() if content is not None else None,
                    content=content, report=report, created_at=now())
        with self.db.transaction() as con:
            # Acquire a row lock and recheck revision without advancing the data
            # revision: concurrent corrections/deletions must not publish stale bytes.
            checked = con.execute(update(imports).where(
                imports.c.id == import_id, imports.c.revision == record["revision"], imports.c.deleted.is_(False),
            ).values(updated_at=now()))
            if checked.rowcount != 1:
                raise ServiceError("ATTENDANCE_DATA_REVISION_CHANGED", 409)
            con.execute(insert(files).values(**file))
            self._audit(con, record, "GENERATED" if content is not None else "GENERATION_FAILED", actor,
                        {"fileId": file["id"], "revision": record["revision"], "sha256": file["sha256"], "report": report})
        if content is None:
            raise ServiceError(result.errorCode or "WAGE_RECORD_GENERATION_FAILED", 422)
        return {"generatedFile": file_dto(file), "taskReport": None, "warnings": report["warnings"], "errors": []}

    def download(self, file_id):
        with self.db.engine.connect() as con:
            file = con.execute(select(files).where(files.c.id == file_id)).mappings().first()
            if not file:
                raise ServiceError("FILE_NOT_FOUND", 404)
            record = self._load(con, file["import_id"])
            if file["status"] != "READY" or file["revision"] != record["revision"]:
                raise ServiceError("ATTENDANCE_DATA_REVISION_CHANGED", 409)
            if file["content"] is None or hashlib.sha256(file["content"]).hexdigest() != file["sha256"]:
                raise ServiceError("GENERATED_FILE_INTEGRITY_ERROR", 409)
            return file["filename"], file["content"]

    def row_history(self, import_id, limit=50, offset=0):
        with self.db.engine.connect() as con:
            self._load(con, import_id)
            query = select(audit).where(audit.c.import_id == import_id, audit.c.row_id.is_not(None))
            total = con.execute(select(func.count()).select_from(query.subquery())).scalar_one()
            events = con.execute(query.order_by(audit.c.occurred_at.desc()).limit(limit).offset(offset)).mappings().all()
        return {"items": [self._row_event(e) for e in events],
                "limit": limit, "offset": offset, "total": total}

    def _row_event(self, event):
        snap = event["snapshot"]
        row = snap.get("before", snap)
        data = row.get("rawJson", row)
        return {"id": event["id"], "eventCode": event["action"], "attendanceImportId": event["import_id"],
                "attendanceRowId": event["row_id"], "rowKey": row.get("rowKey", ""),
                **{key: data.get(key) for key in ("employeeId", "employeeName", "department", "workDate")},
                "rowSnapshot": row, "afterSnapshot": snap.get("after"), "actor": {"id": None, "displayLabel": event["actor"]},
                "reason": event["reason"], "occurredAt": event["occurred_at"]}

    def change_row(self, import_id, row_id, reason, actor, punch_times=None, expected_revision=None):
        with self.db.transaction() as con:
            record = self._load(con, import_id)
            if expected_revision is not None and record["revision"] != expected_revision:
                raise ServiceError("ATTENDANCE_DATA_REVISION_CHANGED", 409)
            row = con.execute(select(rows).where(rows.c.id == row_id, rows.c.import_id == import_id)).mappings().first()
            if not row or row["deleted"]:
                raise ServiceError("ATTENDANCE_ROW_NOT_FOUND", 404)
            affected = self._change(con, record)
            snapshot = row_dto(row)
            if punch_times is None:
                con.execute(update(rows).where(rows.c.id == row_id).values(deleted=True))
                action = "DELETED"
            else:
                calc = calculate_attendance_hours(tuple(punch_times))
                normalized = sorted(punch_times)
                data = {**row["data"], "punchTimes": normalized, "calculationMethod": calc.calculationMethod.value,
                        "workIntervals": json_ready(calc.workIntervals), "pairedGrossHours": calc.grossHours,
                        "lunchHours": calc.lunchHours, "calculatedHours": calc.calculatedHours,
                        "firstPunch": normalized[0] if normalized else None, "lastPunch": normalized[-1] if normalized else None,
                        "errors": [], "warnings": []}
                if not normalized or len(normalized) % 2:
                    code = "ODD_PUNCH_COUNT" if normalized else "MISSING_PUNCH_TIMES"
                    data["warnings"] = [{**{k: data[k] for k in ("employeeId", "employeeName", "workDate")},
                                         "code": code, "message": code, "rowNumber": None, "field": "punchTimes"}]
                con.execute(update(rows).where(rows.c.id == row_id).values(data=data, corrected=True))
                action = "CORRECTED"
                row = {**row, "data": data}
                snapshot = {"before": snapshot, "after": row_dto({**row, "data": data})}
            self._refresh_summary(con, import_id)
            event = self._audit(con, record, action, actor, snapshot, reason, row_id)
            active = self._rows(con, import_id)
            all_rows = self._rows(con, import_id, True)
        return {"code": "ATTENDANCE_ROW_" + action, "deleted": action == "DELETED", "alreadyDeleted": False,
                "activeRowCount": len(active), "deletedRowCount": len(all_rows) - len(active),
                "row": row_dto(row), "event": self._row_event(event), "affectedGeneratedFiles": affected}

    def impact(self, import_id):
        with self.db.engine.connect() as con:
            record = self._load(con, import_id)
            active, all_rows = self._rows(con, import_id), self._rows(con, import_id, True)
            generated = list(con.execute(select(files.c.id, files.c.status).where(files.c.import_id == import_id)).mappings())
            dto = import_dto(record, active)
        summary = {}
        for f in generated:
            summary[f["status"]] = summary.get(f["status"], 0) + 1
        return {**dto, "attendanceImportId": import_id, "activeRowCount": len(active),
                "deletedRowCount": len(all_rows) - len(active), "generatedFileCount": len(generated),
                "generatedFileSummary": [{"fileType": "WAGE_RECORD_XLS", "status": k, "count": v} for k, v in summary.items()]}

    def delete_import(self, import_id, reason, actor):
        with self.db.transaction() as con:
            record = self._load(con, import_id)
            active, all_rows = self._rows(con, import_id), self._rows(con, import_id, True)
            affected = self._change(con, record, deleted=True)
            snapshot = {**import_dto(record, active), "attendanceImportId": import_id,
                        "activeRowCount": len(active), "deletedRowCount": len(all_rows) - len(active),
                        "generatedFiles": affected}
            event = self._audit(con, record, "IMPORT_DELETED", actor, snapshot, reason)
        fallback = self.list_imports(limit=1)["items"]
        return {"code": "ATTENDANCE_IMPORT_DELETED", "deleted": True, "alreadyDeleted": False,
                "event": self._import_event(event), "affectedGeneratedFiles": affected,
                "fallbackImport": fallback[0] if fallback else None}

    def _import_event(self, event):
        return {**event["snapshot"], "id": event["id"], "eventCode": "DELETED",
                "actor": {"id": None, "displayLabel": event["actor"]},
                "reason": event["reason"], "occurredAt": event["occurred_at"]}

    def import_history(self, limit=50, offset=0):
        with self.db.engine.connect() as con:
            query = select(audit).where(audit.c.action == "IMPORT_DELETED")
            total = con.execute(select(func.count()).select_from(query.subquery())).scalar_one()
            events = con.execute(query.order_by(audit.c.occurred_at.desc()).limit(limit).offset(offset)).mappings().all()
        return {"items": [self._import_event(e) for e in events],
                "limit": limit, "offset": offset, "total": total}
