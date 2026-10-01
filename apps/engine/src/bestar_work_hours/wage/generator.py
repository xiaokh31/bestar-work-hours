# Adapted from Bestar stripSystem (Apache-2.0); standalone imports/resources. See NOTICE.
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import xlrd  # type: ignore[import-untyped]

from bestar_work_hours.hashing import compute_sha256
from bestar_work_hours.time_utils import operational_now
from bestar_work_hours.wage.attendance import (
    AttendanceDay,
    AttendanceParseResult,
    WageIssue,
)
from bestar_work_hours.wage.legacy_xls import LegacyXlsTemplateEditor
from bestar_work_hours.wage.template import (
    WAGE_TEMPLATE_SHA256,
    WAGE_TEMPLATE_WEEKDAY_XF_INDEX,
    WAGE_TEMPLATE_WEEKEND_XF_INDEX,
)


WAGE_RECORD_MANIFEST_FILENAME = "wage_record_manifest.json"
WAGE_RECORD_FILE_TYPE = "wage_record_xls"
STANDARD_HEADERS = (
    "DATE",
    "HOURS",
    "LUNCH HOURS",
    "START TIME",
    "END TIME",
)
WEEKDAY_VALUES = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}
MIN_EMPLOYEE_MATCH_TOKEN_LENGTH = 3


@dataclass(frozen=True)
class _StandardSheet:
    sheetIndex: int
    sheetName: str
    headerRow: int
    weekdayColumn: int
    columns: dict[str, int]
    dateRows: tuple[int, ...]
    totalRow: int | None


@dataclass(frozen=True)
class _WeekdayStyleRoles:
    weekdayXfIndex: int
    weekendXfIndex: int


@dataclass(frozen=True)
class _WrittenSheetValidation:
    sheetIndex: int
    weekdayColumn: int
    dateColumn: int
    dateRows: tuple[int, ...]
    styles: _WeekdayStyleRoles


@dataclass(frozen=True)
class WageRecordGenerationResult:
    outputPath: Path
    templatePath: Path
    generatedFilename: str
    manifestPath: Path
    outputSha256: str | None
    outputSizeBytes: int | None
    fileType: str
    writtenEmployeeCount: int
    writtenDayCount: int
    unmatchedEmployees: tuple[str, ...]
    matchedSheets: tuple[str, ...]
    warnings: tuple[WageIssue, ...]
    errors: tuple[WageIssue, ...]
    generationStage: str
    errorCode: str | None
    validated: bool


def generate_wage_record(
    *,
    attendance_result: AttendanceParseResult,
    template_path: Path,
    output_dir: Path,
    generated_at: datetime | None = None,
    enforce_approved_template: bool = True,
) -> WageRecordGenerationResult:
    generated_at = generated_at or operational_now()
    output_dir.mkdir(parents=True, exist_ok=True)

    if attendance_result.periodStart is None or attendance_result.periodEnd is None:
        return _generation_error(
            template_path=template_path,
            output_dir=output_dir,
            code="WAGE_GENERATION_PERIOD_MISSING",
            stage="PERIOD",
            message="Attendance period is missing; wage record was not generated.",
        )
    if attendance_result.errors:
        return _generation_error(
            template_path=template_path,
            output_dir=output_dir,
            code="WAGE_GENERATION_INPUT_HAS_ERRORS",
            stage="NORMALIZED_INPUT",
            message="Attendance parser has errors; wage record was not generated.",
        )
    if not template_path.is_file():
        return _generation_error(
            template_path=template_path,
            output_dir=output_dir,
            code="WAGE_TEMPLATE_MISSING",
            stage="TEMPLATE_OPEN",
            message=f"Wage template does not exist: {template_path}",
        )

    if enforce_approved_template:
        from bestar_work_hours.wage.template import preflight_wage_template

        try:
            preflight_wage_template(template_path, require_read_only=False)
        except ValueError as exc:
            code = str(exc)
            return _generation_error(
                template_path=template_path,
                output_dir=output_dir,
                code=code,
                stage="TEMPLATE_OPEN",
                message=code,
            )

    warnings: list[WageIssue] = []
    errors: list[WageIssue] = []

    template_sha256 = compute_sha256(template_path)
    try:
        editor = LegacyXlsTemplateEditor(template_path)
        readable = editor.workbook
    except Exception as exc:
        return _generation_error(
            template_path=template_path,
            output_dir=output_dir,
            code="WAGE_TEMPLATE_UNREADABLE",
            stage="TEMPLATE_OPEN",
            message=f"Unable to open wage template: {type(exc).__name__}: {exc}",
        )

    days_by_employee = _days_by_employee(attendance_result.days)
    matched_employee_keys: set[tuple[str | None, str | None]] = set()
    matched_sheets: list[str] = []
    written_sheet_validations: list[_WrittenSheetValidation] = []
    written_day_count = 0

    standard_sheets: list[_StandardSheet] = []
    for sheet_index, readable_sheet in enumerate(readable.sheets()):
        contract = _standard_sheet(
            readable_sheet,
            sheet_index,
            datemode=readable.datemode,
            period_start=attendance_result.periodStart,
            period_end=attendance_result.periodEnd,
        )
        if contract is None:
            warnings.append(
                WageIssue(
                    code="WAGE_TEMPLATE_SHEET_UNSUPPORTED_CONTRACT",
                    message=(
                        "Wage template sheet does not have the complete standard "
                        f"attendance contract: sheet={readable_sheet.name}; "
                        f"headers={_sheet_header_details(readable_sheet)}"
                    ),
                )
            )
            continue

        if not contract.dateRows or contract.totalRow is None:
            warnings.append(
                WageIssue(
                    code="WAGE_TEMPLATE_DATE_ROWS_NOT_FOUND",
                    message=(
                        "Standard wage template date slots or TOTAL row were not found: "
                        f"sheet={readable_sheet.name}"
                    ),
                )
            )
            continue
        standard_sheets.append(contract)

    try:
        weekday_styles_by_sheet = {
            contract.sheetIndex: _weekday_style_roles(
                readable,
                contract,
                approved_template=template_sha256 == WAGE_TEMPLATE_SHA256,
            )
            for contract in standard_sheets
        }
    except ValueError as exc:
        code = str(exc)
        return _generation_error(
            template_path=template_path,
            output_dir=output_dir,
            code=code,
            stage="TEMPLATE_STYLE",
            message=code,
            warnings=tuple(warnings),
        )

    slot_template = _is_employee_slot_template(standard_sheets)
    if slot_template and len(days_by_employee) > len(standard_sheets):
        return _generation_error(
            template_path=template_path,
            output_dir=output_dir,
            code="WAGE_TEMPLATE_EMPLOYEE_CAPACITY_EXCEEDED",
            stage="SHEET_MATCH",
            message="Attendance employee count exceeds approved template capacity.",
            warnings=tuple(warnings),
        )
    if slot_template:
        employee_keys = sorted(days_by_employee, key=_employee_sort_key)
        matches = list(zip(standard_sheets, employee_keys, strict=False))
        match_warnings: list[WageIssue] = []
    else:
        legacy_matches, match_warnings = _resolve_sheet_matches(
            standard_sheets,
            days_by_employee,
        )
        matches = [
            (contract, employee_key)
            for contract, employee_key in legacy_matches
        ]
    warnings.extend(match_warnings)

    output_sheet_names = list(readable.sheet_names())
    reserved_sheet_names = {
        name.casefold()
        for name in readable.sheet_names()
        if not name.startswith("EMPLOYEE-")
    }

    for contract, employee_key in matches:
        employee_days = days_by_employee[employee_key]
        output_sheet_name = contract.sheetName
        if slot_template:
            output_sheet_name = _unique_employee_sheet_name(
                employee_key,
                reserved=reserved_sheet_names,
            )
            reserved_sheet_names.add(output_sheet_name.casefold())
            editor.rename_sheet(contract.sheetIndex, output_sheet_name)
            editor.write(
                contract.sheetIndex,
                0,
                0,
                _employee_label(*employee_key),
            )
            output_sheet_names[contract.sheetIndex] = output_sheet_name
        written_day_count += _write_employee_sheet(
            editor,
            contract=contract,
            weekday_styles=weekday_styles_by_sheet[contract.sheetIndex],
            employee_days=employee_days,
            period_start=attendance_result.periodStart,
            period_end=attendance_result.periodEnd,
        )
        matched_employee_keys.add(employee_key)
        matched_sheets.append(output_sheet_name)
        written_sheet_validations.append(
            _WrittenSheetValidation(
                sheetIndex=contract.sheetIndex,
                weekdayColumn=contract.weekdayColumn,
                dateColumn=contract.columns["DATE"],
                dateRows=contract.dateRows,
                styles=weekday_styles_by_sheet[contract.sheetIndex],
            )
        )

    unmatched_employees = tuple(
        _employee_label(employee_id, employee_name)
        for employee_id, employee_name in days_by_employee
        if (employee_id, employee_name) not in matched_employee_keys
    )
    for employee in unmatched_employees:
        warnings.append(
            WageIssue(
                code="WAGE_TEMPLATE_EMPLOYEE_NOT_MATCHED",
                message=f"Attendance employee was not matched to a wage template sheet: {employee}",
            )
        )

    if not matched_employee_keys or written_day_count <= 0:
        return _generation_error(
            template_path=template_path,
            output_dir=output_dir,
            code="WAGE_GENERATION_ZERO_EFFECTIVE_OUTPUT",
            stage="SHEET_WRITE",
            message="No matched employee work days were written to the wage template.",
            warnings=tuple(warnings),
        )

    output_path = output_dir / _output_filename(
        attendance_result.periodStart,
        attendance_result.periodEnd,
        generated_at,
    )
    staging_path = output_dir / f".{output_path.name}.{uuid4().hex}.staging"
    try:
        editor.save(staging_path)
    except Exception as exc:
        staging_path.unlink(missing_ok=True)
        return _generation_error(
            template_path=template_path,
            output_dir=output_dir,
            code="WAGE_GENERATION_SAVE_FAILED",
            stage="SAVE",
            message=f"Unable to save wage record: {type(exc).__name__}: {exc}",
            warnings=tuple(warnings),
        )
    if compute_sha256(template_path) != template_sha256:
        staging_path.unlink(missing_ok=True)
        return _generation_error(
            template_path=template_path,
            output_dir=output_dir,
            code="WAGE_TEMPLATE_CHANGED_DURING_GENERATION",
            stage="VALIDATE",
            message="Wage template SHA-256 changed during generation.",
            warnings=tuple(warnings),
        )
    try:
        _validate_staged_workbook(
            staging_path=staging_path,
            expected_sheet_names=tuple(output_sheet_names),
            matched_sheets=tuple(matched_sheets),
            period_start=attendance_result.periodStart,
            period_end=attendance_result.periodEnd,
            written_employee_count=len(matched_employee_keys),
            written_day_count=written_day_count,
            written_sheets=tuple(written_sheet_validations),
        )
        staging_path.replace(output_path)
    except Exception as exc:
        staging_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        validation_code = _safe_validation_error_code(exc)
        return _generation_error(
            template_path=template_path,
            output_dir=output_dir,
            code=validation_code,
            stage="VALIDATE",
            message=validation_code,
            warnings=tuple(warnings),
        )
    output_sha256 = compute_sha256(output_path)
    output_size_bytes = output_path.stat().st_size
    manifest_path = output_dir / WAGE_RECORD_MANIFEST_FILENAME
    try:
        _append_manifest_record(
            manifest_path=manifest_path,
            output_path=output_path,
            template_path=template_path,
            output_sha256=output_sha256,
            output_size_bytes=output_size_bytes,
            generated_at=generated_at,
            attendance_result=attendance_result,
            warnings=warnings,
            written_employee_count=len(matched_employee_keys),
            written_day_count=written_day_count,
            matched_sheet_count=len(matched_sheets),
        )
        _validate_manifest_record(
            manifest_path=manifest_path,
            output_path=output_path,
            output_sha256=output_sha256,
            output_size_bytes=output_size_bytes,
            period_start=attendance_result.periodStart,
            period_end=attendance_result.periodEnd,
            written_employee_count=len(matched_employee_keys),
            written_day_count=written_day_count,
        )
    except Exception as exc:
        output_path.unlink(missing_ok=True)
        return _generation_error(
            template_path=template_path,
            output_dir=output_dir,
            code="WAGE_GENERATION_MANIFEST_INVALID",
            stage="MANIFEST",
            message=f"Generated wage manifest validation failed: {type(exc).__name__}: {exc}",
            warnings=tuple(warnings),
        )

    return WageRecordGenerationResult(
        outputPath=output_path,
        templatePath=template_path,
        generatedFilename=output_path.name,
        manifestPath=manifest_path,
        outputSha256=output_sha256,
        outputSizeBytes=output_size_bytes,
        fileType=WAGE_RECORD_FILE_TYPE,
        writtenEmployeeCount=len(matched_employee_keys),
        writtenDayCount=written_day_count,
        unmatchedEmployees=unmatched_employees,
        matchedSheets=tuple(matched_sheets),
        warnings=tuple(warnings),
        errors=tuple(errors),
        generationStage="COMPLETED",
        errorCode=None,
        validated=True,
    )


def _write_employee_sheet(
    editor: LegacyXlsTemplateEditor,
    *,
    contract: _StandardSheet,
    weekday_styles: _WeekdayStyleRoles,
    employee_days: list[AttendanceDay],
    period_start: date,
    period_end: date,
) -> int:
    days_by_date = {day.workDate: day for day in employee_days}
    period_dates = _period_dates(period_start, period_end)
    written = 0

    for row_offset, row_index in enumerate(contract.dateRows):
        if row_offset >= len(period_dates):
            _write_empty_day(editor, contract, weekday_styles, row_index)
            continue

        work_date = period_dates[row_offset]
        attendance_day = days_by_date.get(work_date)
        editor.write(
            contract.sheetIndex,
            row_index,
            contract.weekdayColumn,
            work_date.strftime("%a").upper(),
            style_xf_index=_weekday_style_xf(work_date, weekday_styles),
        )
        editor.write(
            contract.sheetIndex,
            row_index,
            contract.columns["DATE"],
            _date_text(work_date),
        )

        if attendance_day is None or not attendance_day.punchTimes:
            _write_empty_values(editor, contract, row_index)
            continue
        if attendance_day.calculatedHours is None:
            _write_review_values(editor, contract, row_index)
            continue

        editor.write(
            contract.sheetIndex,
            row_index,
            contract.columns["HOURS"],
            attendance_day.calculatedHours,
        )
        editor.write(
            contract.sheetIndex,
            row_index,
            contract.columns["LUNCH HOURS"],
            attendance_day.lunchHours,
        )
        editor.write(
            contract.sheetIndex,
            row_index,
            contract.columns["START TIME"],
            _excel_time_cell_value(
                editor,
                contract,
                row_index,
                "START TIME",
                attendance_day.firstPunch,
            ),
        )
        editor.write(
            contract.sheetIndex,
            row_index,
            contract.columns["END TIME"],
            _excel_time_cell_value(
                editor,
                contract,
                row_index,
                "END TIME",
                attendance_day.lastPunch,
            ),
        )
        written += 1

    if contract.totalRow is None:
        raise ValueError(f"Missing TOTAL row for standard sheet: {contract.sheetName}")
    total_hours = round(
        sum(
            day.calculatedHours or 0.0
            for day in employee_days
            if day.calculatedHours is not None and day.punchTimes
        ),
        2,
    )
    editor.write(
        contract.sheetIndex,
        contract.totalRow,
        contract.weekdayColumn,
        "TOTAL HOURS",
    )
    editor.write(
        contract.sheetIndex,
        contract.totalRow,
        contract.columns["HOURS"],
        total_hours,
    )
    return written


def _write_empty_day(
    editor: LegacyXlsTemplateEditor,
    contract: _StandardSheet,
    weekday_styles: _WeekdayStyleRoles,
    row_index: int,
) -> None:
    editor.write(
        contract.sheetIndex,
        row_index,
        contract.weekdayColumn,
        "",
        style_xf_index=weekday_styles.weekdayXfIndex,
    )
    editor.write(contract.sheetIndex, row_index, contract.columns["DATE"], "")
    _write_empty_values(editor, contract, row_index)


def _write_empty_values(
    editor: LegacyXlsTemplateEditor,
    contract: _StandardSheet,
    row_index: int,
) -> None:
    for header in STANDARD_HEADERS[1:]:
        editor.write(contract.sheetIndex, row_index, contract.columns[header], "/")


def _write_review_values(
    editor: LegacyXlsTemplateEditor,
    contract: _StandardSheet,
    row_index: int,
) -> None:
    editor.write(
        contract.sheetIndex,
        row_index,
        contract.columns["HOURS"],
        "REVIEW",
    )
    for header in STANDARD_HEADERS[2:]:
        editor.write(contract.sheetIndex, row_index, contract.columns[header], "/")


def _weekday_style_roles(
    workbook,
    contract: _StandardSheet,
    *,
    approved_template: bool,
) -> _WeekdayStyleRoles:
    if approved_template:
        weekday_xfs = {WAGE_TEMPLATE_WEEKDAY_XF_INDEX}
        weekend_xfs = {WAGE_TEMPLATE_WEEKEND_XF_INDEX}
        actual_xfs = {
            workbook.sheet_by_index(contract.sheetIndex).cell_xf_index(
                row_index, contract.weekdayColumn
            )
            for row_index in contract.dateRows
        }
        if actual_xfs != weekday_xfs | weekend_xfs:
            raise ValueError("WAGE_TEMPLATE_WEEKDAY_STYLE_CONTRACT_MISSING")
    else:
        sheet = workbook.sheet_by_index(contract.sheetIndex)
        weekday_xfs = set()
        weekend_xfs = set()
        for row_index in contract.dateRows:
            date_cell = sheet.cell(row_index, contract.columns["DATE"])
            work_date = _parse_date_slot(
                date_cell.value,
                cell_type=date_cell.ctype,
                datemode=workbook.datemode,
            )
            weekday_text = _cell_text(
                sheet.cell_value(row_index, contract.weekdayColumn)
            ).upper()
            if work_date is None or weekday_text != work_date.strftime("%a").upper():
                raise ValueError("WAGE_TEMPLATE_WEEKDAY_STYLE_CONTRACT_MISSING")
            target = weekend_xfs if work_date.weekday() >= 5 else weekday_xfs
            target.add(sheet.cell_xf_index(row_index, contract.weekdayColumn))
        if len(weekday_xfs) != 1 or len(weekend_xfs) != 1:
            raise ValueError("WAGE_TEMPLATE_WEEKDAY_STYLE_CONTRACT_AMBIGUOUS")

    weekday_xf = next(iter(weekday_xfs))
    weekend_xf = next(iter(weekend_xfs))
    if not all(
        isinstance(index, int) and 0 <= index < len(workbook.xf_list)
        for index in (weekday_xf, weekend_xf)
    ):
        raise ValueError("WAGE_TEMPLATE_WEEKDAY_STYLE_CONTRACT_OUT_OF_RANGE")
    if (
        weekday_xf == weekend_xf
        or _xf_without_fill(workbook, weekday_xf)
        != _xf_without_fill(workbook, weekend_xf)
        or _xf_fill(workbook, weekday_xf) == _xf_fill(workbook, weekend_xf)
    ):
        raise ValueError("WAGE_TEMPLATE_WEEKDAY_STYLE_CONTRACT_UNSAFE")
    return _WeekdayStyleRoles(
        weekdayXfIndex=weekday_xf,
        weekendXfIndex=weekend_xf,
    )


def _weekday_style_xf(work_date: date, styles: _WeekdayStyleRoles) -> int:
    return styles.weekendXfIndex if work_date.weekday() >= 5 else styles.weekdayXfIndex


def _xf_without_fill(workbook, xf_index: int) -> tuple[object, ...]:
    xf = workbook.xf_list[xf_index]
    font = workbook.font_list[xf.font_index]
    return (
        tuple(sorted((key, value) for key, value in vars(font).items() if key != "font_index")),
        tuple(sorted(vars(xf.border).items())),
        tuple(sorted(vars(xf.alignment).items())),
        tuple(sorted(vars(xf.protection).items())),
        workbook.format_map[xf.format_key].format_str,
    )


def _xf_fill(workbook, xf_index: int) -> tuple[tuple[str, object], ...]:
    return tuple(sorted(vars(workbook.xf_list[xf_index].background).items()))


def _safe_validation_error_code(exc: Exception) -> str:
    code = str(exc)
    if code in {
        "WAGE_OUTPUT_PERIOD_DATE_MISMATCH",
        "WAGE_OUTPUT_WEEKDAY_TEXT_MISMATCH",
        "WAGE_OUTPUT_WEEKDAY_STYLE_MISMATCH",
        "WAGE_OUTPUT_BLANK_SLOT_MISMATCH",
    }:
        return code
    return "WAGE_GENERATION_OUTPUT_VALIDATION_FAILED"


def _generation_error(
    *,
    template_path: Path,
    output_dir: Path,
    code: str,
    stage: str,
    message: str,
    warnings: tuple[WageIssue, ...] = (),
) -> WageRecordGenerationResult:
    output_path = output_dir / "wage-record-not-generated.xls"
    return WageRecordGenerationResult(
        outputPath=output_path,
        templatePath=template_path,
        generatedFilename=output_path.name,
        manifestPath=output_dir / WAGE_RECORD_MANIFEST_FILENAME,
        outputSha256=None,
        outputSizeBytes=None,
        fileType=WAGE_RECORD_FILE_TYPE,
        writtenEmployeeCount=0,
        writtenDayCount=0,
        unmatchedEmployees=(),
        matchedSheets=(),
        warnings=warnings,
        errors=(WageIssue(code=code, message=message),),
        generationStage=stage,
        errorCode=code,
        validated=False,
    )


def _days_by_employee(
    days: tuple[AttendanceDay, ...],
) -> dict[tuple[str | None, str | None], list[AttendanceDay]]:
    grouped: dict[tuple[str | None, str | None], list[AttendanceDay]] = {}
    for day in days:
        key = (day.employeeId, day.employeeName)
        grouped.setdefault(key, []).append(day)
    return grouped


def _resolve_sheet_matches(
    standard_sheets: list[_StandardSheet],
    days_by_employee: dict[tuple[str | None, str | None], list[AttendanceDay]],
) -> tuple[
    list[tuple[_StandardSheet, tuple[str | None, str | None]]],
    list[WageIssue],
]:
    warnings: list[WageIssue] = []
    candidates_by_sheet: dict[int, list[tuple[str | None, str | None]]] = {}
    candidate_sheets_by_employee: dict[
        tuple[str | None, str | None], list[_StandardSheet]
    ] = {}

    for contract in standard_sheets:
        sheet = contract.sheetName
        candidate_keys = [
            employee_key
            for employee_key in days_by_employee
            if _employee_matches_sheet(employee_key, sheet)
        ]
        candidates_by_sheet[contract.sheetIndex] = candidate_keys
        for employee_key in candidate_keys:
            candidate_sheets_by_employee.setdefault(employee_key, []).append(contract)

        if not candidate_keys:
            warnings.append(
                WageIssue(
                    code="WAGE_TEMPLATE_SHEET_NOT_MATCHED",
                    message=f"Standard wage template sheet was not matched: sheet={sheet}",
                )
            )
        elif len(candidate_keys) > 1:
            warnings.append(
                WageIssue(
                    code="WAGE_TEMPLATE_SHEET_EMPLOYEE_AMBIGUOUS",
                    message=(
                        "Standard wage template sheet matched multiple attendance "
                        f"employees and was left unchanged: sheet={sheet}; "
                        f"employees={_employee_details(candidate_keys)}"
                    ),
                )
            )

    multiply_matched_employees = {
        employee_key
        for employee_key, sheets in candidate_sheets_by_employee.items()
        if len(sheets) > 1
    }
    for employee_key in sorted(
        multiply_matched_employees,
        key=lambda item: ((item[1] or ""), (item[0] or "")),
    ):
        sheets = candidate_sheets_by_employee[employee_key]
        warnings.append(
            WageIssue(
                code="WAGE_TEMPLATE_EMPLOYEE_MULTIPLE_SHEETS",
                message=(
                    "Attendance employee matched multiple wage template sheets and "
                    "all candidates were left unchanged: "
                    f"employee={_employee_label(*employee_key)}; "
                    f"sheets={'|'.join(sheet.sheetName for sheet in sheets)}"
                ),
                employeeId=employee_key[0],
                employeeName=employee_key[1],
            )
        )

    matches: list[tuple[_StandardSheet, tuple[str | None, str | None]]] = []
    for contract in standard_sheets:
        candidate_keys = candidates_by_sheet[contract.sheetIndex]
        if len(candidate_keys) != 1:
            continue
        employee_key = candidate_keys[0]
        if employee_key in multiply_matched_employees:
            continue
        matches.append((contract, employee_key))
    return matches, warnings


def _employee_matches_sheet(
    employee_key: tuple[str | None, str | None],
    sheet_text: str,
) -> bool:
    employee_id, employee_name = employee_key
    sheet_tokens = _tokens(sheet_text)
    if not sheet_tokens:
        return False

    normalized_employee_id = _normalized_identifier(employee_id)
    if (
        len(normalized_employee_id) >= MIN_EMPLOYEE_MATCH_TOKEN_LENGTH
        and normalized_employee_id in sheet_tokens
    ):
        return True

    employee_tokens = _tokens(employee_name or "")
    return bool(
        employee_tokens
        and all(
            len(token) >= MIN_EMPLOYEE_MATCH_TOKEN_LENGTH for token in employee_tokens
        )
        and employee_tokens.issubset(sheet_tokens)
    )


def _standard_sheet(
    sheet,
    sheet_index: int,
    *,
    datemode: int,
    period_start: date,
    period_end: date,
) -> _StandardSheet | None:
    for row_index in range(sheet.nrows):
        normalized_values = [
            _normalized_header(sheet.cell_value(row_index, column_index))
            for column_index in range(sheet.ncols)
        ]
        if not all(normalized_values.count(header) == 1 for header in STANDARD_HEADERS):
            continue

        columns = {
            header: normalized_values.index(header) for header in STANDARD_HEADERS
        }
        weekday_column = columns["DATE"] - 1
        if weekday_column < 0:
            return None

        total_row: int | None = None
        candidate_dates: list[tuple[int, date]] = []
        placeholder_rows: list[int] = []
        for candidate_row in range(row_index + 1, sheet.nrows):
            row_values = [
                _cell_text(sheet.cell_value(candidate_row, column_index))
                for column_index in range(sheet.ncols)
            ]
            if any(value.upper().startswith("TOTAL HOURS") for value in row_values):
                total_row = candidate_row
                break
            weekday = _cell_text(
                sheet.cell_value(candidate_row, weekday_column)
            ).upper()
            date_cell = sheet.cell(candidate_row, columns["DATE"])
            parsed_date = _parse_date_slot(
                date_cell.value,
                cell_type=date_cell.ctype,
                datemode=datemode,
            )
            if weekday in WEEKDAY_VALUES and parsed_date is not None:
                candidate_dates.append((candidate_row, parsed_date))

            if weekday == "WEEKDAY_SLOT" and _cell_text(date_cell.value).upper() == "DATE_SLOT":
                placeholder_rows.append(candidate_row)

        date_rows = (
            tuple(placeholder_rows)
            if len(placeholder_rows) == 31
            else _validated_date_rows(
                candidate_dates,
                period_start=period_start,
                period_end=period_end,
            )
        )

        return _StandardSheet(
            sheetIndex=sheet_index,
            sheetName=sheet.name,
            headerRow=row_index,
            weekdayColumn=weekday_column,
            columns=columns,
            dateRows=tuple(date_rows),
            totalRow=total_row,
        )
    return None


def _parse_date_slot(
    value: object,
    *,
    cell_type: int,
    datemode: int,
) -> date | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        if cell_type != xlrd.XL_CELL_DATE:
            return None
        try:
            return xlrd.xldate_as_datetime(float(value), datemode).date()
        except (OverflowError, TypeError, ValueError):
            return None
    text = _cell_text(value)
    match = re.fullmatch(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", text)
    if match is None:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def _validated_date_rows(
    candidate_dates: list[tuple[int, date]],
    *,
    period_start: date,
    period_end: date,
) -> tuple[int, ...]:
    current_period_rows = tuple(
        row_index
        for row_index, candidate_date in candidate_dates
        if period_start <= candidate_date <= period_end
    )
    current_period_dates = [
        candidate_date
        for _, candidate_date in candidate_dates
        if period_start <= candidate_date <= period_end
    ]
    if current_period_dates == _period_dates(period_start, period_end):
        return current_period_rows

    # The supplied legacy template is a prior-month office form. It is safe to
    # reuse only when its cells prove a complete, ordered calendar-month grid;
    # isolated numeric/date notes must never become writable slots.
    dates_by_month: dict[tuple[int, int], list[tuple[int, date]]] = defaultdict(list)
    for candidate in candidate_dates:
        dates_by_month[(candidate[1].year, candidate[1].month)].append(candidate)
    required_days = (period_end - period_start).days + 1
    complete_placeholder_months = [
        candidates
        for candidates in dates_by_month.values()
        if len(candidates) >= required_days
        and [candidate.day for _, candidate in candidates]
        == list(range(1, len(candidates) + 1))
    ]
    if len(complete_placeholder_months) != 1:
        return ()
    return tuple(row_index for row_index, _ in complete_placeholder_months[0])


def _normalized_header(value: object) -> str:
    return " ".join(_cell_text(value).upper().split())


def _sheet_header_details(sheet) -> str:
    details: list[str] = []
    for row_index in range(min(sheet.nrows, 12)):
        values = [
            _normalized_header(sheet.cell_value(row_index, column_index))
            for column_index in range(sheet.ncols)
        ]
        row_headers = [value for value in values if value]
        if "DATE" in row_headers or "HOURS" in row_headers:
            details.extend(row_headers)
    return "|".join(details) or "NONE"


def _employee_details(
    employee_keys: list[tuple[str | None, str | None]],
) -> str:
    return "|".join(_employee_label(*employee_key) for employee_key in employee_keys)


def _is_employee_slot_template(standard_sheets: list[_StandardSheet]) -> bool:
    return bool(standard_sheets) and all(
        re.fullmatch(r"EMPLOYEE-\d{2}", contract.sheetName) is not None
        for contract in standard_sheets
    )


def _employee_sort_key(
    employee_key: tuple[str | None, str | None],
) -> tuple[str, str]:
    employee_id, employee_name = employee_key
    return (
        _normalized_identifier(employee_id),
        " ".join((employee_name or "").casefold().split()),
    )


def _unique_employee_sheet_name(
    employee_key: tuple[str | None, str | None],
    *,
    reserved: set[str],
) -> str:
    employee_id, employee_name = employee_key
    base = employee_name or employee_id or "Employee"
    base = re.sub(r"[\[\]:*?/\\\x00-\x1f]", " ", base)
    base = " ".join(base.split()).strip(" '") or "Employee"
    candidate = base[:31]
    suffix = 2
    while candidate.casefold() in reserved:
        marker = f"-{suffix}"
        candidate = f"{base[: 31 - len(marker)]}{marker}"
        suffix += 1
    return candidate


def _normalized_identifier(value: str | None) -> str:
    if not value:
        return ""
    return "".join(re.findall(r"[a-z0-9]+", value.lower()))


def _period_dates(period_start: date, period_end: date) -> list[date]:
    dates: list[date] = []
    current = period_start
    while current <= period_end:
        dates.append(current)
        current = date.fromordinal(current.toordinal() + 1)
    return dates


def _date_text(value: date) -> str:
    return f"{value.year}.{value.month}.{value.day}"


def _excel_time_fraction(value: str | None) -> float | str:
    if not value:
        return "/"
    hour, minute = value.split(":", 1)
    return (int(hour) * 60 + int(minute)) / (24 * 60)


def _excel_time_cell_value(
    editor: LegacyXlsTemplateEditor,
    contract: _StandardSheet,
    row_index: int,
    header: str,
    value: str | None,
) -> float | str:
    if not value:
        return "/"
    sheet = editor.workbook.sheet_by_index(contract.sheetIndex)
    column_index = contract.columns[header]
    xf = editor.workbook.xf_list[sheet.cell_xf_index(row_index, column_index)]
    format_string = editor.workbook.format_map[xf.format_key].format_str.lower()
    if "h" in format_string and "m" in format_string:
        return _excel_time_fraction(value)
    return value


def _employee_label(employee_id: str | None, employee_name: str | None) -> str:
    if employee_id and employee_name:
        return f"{employee_id} {employee_name}"
    return employee_id or employee_name or "UNKNOWN"


def _output_filename(
    period_start: date,
    period_end: date,
    generated_at: datetime,
) -> str:
    timestamp = generated_at.strftime("%Y%m%d%H%M%S")
    return f"wage-record-{period_start.isoformat()}-{period_end.isoformat()}-{timestamp}.xls"


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _append_manifest_record(
    *,
    manifest_path: Path,
    output_path: Path,
    template_path: Path,
    output_sha256: str,
    output_size_bytes: int,
    generated_at: datetime,
    attendance_result: AttendanceParseResult,
    warnings: list[WageIssue],
    written_employee_count: int,
    written_day_count: int,
    matched_sheet_count: int,
) -> None:
    manifest = _load_manifest(manifest_path)
    record = {
        "generated_at": generated_at.isoformat(),
        "path": str(output_path),
        "sha256": output_sha256,
        "size_bytes": output_size_bytes,
        "type": WAGE_RECORD_FILE_TYPE,
        "template_path": str(template_path),
        "template_sha256": compute_sha256(template_path),
        "period_start": attendance_result.periodStart.isoformat()
        if attendance_result.periodStart
        else None,
        "period_end": attendance_result.periodEnd.isoformat()
        if attendance_result.periodEnd
        else None,
        "parser_version": attendance_result.parserVersion,
        "written_employee_count": written_employee_count,
        "written_day_count": written_day_count,
        "matched_sheet_count": matched_sheet_count,
        "warning_codes": [warning.code for warning in warnings],
    }
    manifest["records"] = [
        existing
        for existing in manifest["records"]
        if existing.get("path") != str(output_path)
    ]
    manifest["records"].append(record)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _validate_staged_workbook(
    *,
    staging_path: Path,
    expected_sheet_names: tuple[str, ...],
    matched_sheets: tuple[str, ...],
    period_start: date,
    period_end: date,
    written_employee_count: int,
    written_day_count: int,
    written_sheets: tuple[_WrittenSheetValidation, ...],
) -> None:
    if not staging_path.is_file() or staging_path.stat().st_size <= 0:
        raise ValueError("Generated staging workbook is missing or empty.")
    if written_employee_count <= 0 or written_day_count <= 0:
        raise ValueError("Generated workbook has no effective employee-day output.")
    workbook = xlrd.open_workbook(staging_path, formatting_info=True)
    if tuple(workbook.sheet_names()) != expected_sheet_names:
        raise ValueError(
            "Generated workbook sheet inventory differs from the template."
        )
    expected_dates = _period_dates(period_start, period_end)
    if not matched_sheets or len(matched_sheets) != written_employee_count:
        raise ValueError("Generated workbook matched-sheet count is inconsistent.")
    if len(written_sheets) != written_employee_count:
        raise ValueError("Generated workbook style-validation count is inconsistent.")
    for validation in written_sheets:
        sheet = workbook.sheet_by_index(validation.sheetIndex)
        if len(validation.dateRows) < len(expected_dates):
            raise ValueError("WAGE_OUTPUT_PERIOD_DATE_MISMATCH")
        for offset, row_index in enumerate(validation.dateRows):
            weekday_text = _cell_text(
                sheet.cell_value(row_index, validation.weekdayColumn)
            ).upper()
            date_cell = sheet.cell(row_index, validation.dateColumn)
            xf_index = sheet.cell_xf_index(row_index, validation.weekdayColumn)
            if offset >= len(expected_dates):
                if (
                    weekday_text
                    or _cell_text(date_cell.value)
                    or xf_index != validation.styles.weekdayXfIndex
                ):
                    raise ValueError("WAGE_OUTPUT_BLANK_SLOT_MISMATCH")
                continue

            expected_date = expected_dates[offset]
            actual_date = _parse_date_slot(
                date_cell.value,
                cell_type=date_cell.ctype,
                datemode=workbook.datemode,
            )
            if actual_date != expected_date:
                raise ValueError("WAGE_OUTPUT_PERIOD_DATE_MISMATCH")
            if weekday_text != expected_date.strftime("%a").upper():
                raise ValueError("WAGE_OUTPUT_WEEKDAY_TEXT_MISMATCH")
            expected_xf = _weekday_style_xf(expected_date, validation.styles)
            if xf_index != expected_xf:
                raise ValueError("WAGE_OUTPUT_WEEKDAY_STYLE_MISMATCH")


def _validate_manifest_record(
    *,
    manifest_path: Path,
    output_path: Path,
    output_sha256: str,
    output_size_bytes: int,
    period_start: date,
    period_end: date,
    written_employee_count: int,
    written_day_count: int,
) -> None:
    manifest = _load_manifest(manifest_path)
    record = next(
        (item for item in manifest["records"] if item.get("path") == str(output_path)),
        None,
    )
    if not isinstance(record, dict):
        raise ValueError("Generated workbook manifest record is missing.")
    expected = {
        "sha256": output_sha256,
        "size_bytes": output_size_bytes,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "written_employee_count": written_employee_count,
        "written_day_count": written_day_count,
    }
    if any(record.get(key) != value for key, value in expected.items()):
        raise ValueError("Generated workbook manifest record is inconsistent.")


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        return {"schema_version": 1, "records": []}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError(f"Unsupported wage record manifest schema: {manifest_path}")
    if not isinstance(manifest.get("records"), list):
        raise ValueError(
            f"Wage record manifest records must be a list: {manifest_path}"
        )
    return manifest


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()
