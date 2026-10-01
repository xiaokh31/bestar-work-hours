# Adapted from Bestar stripSystem (Apache-2.0); standalone imports/resources. See NOTICE.
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time
from enum import StrEnum
from pathlib import Path
from typing import Any

import xlrd  # type: ignore[import-untyped]


ATTENDANCE_PARSER_VERSION = "wage-attendance-v2"
LUNCH_HOURS = 0.5
ATTENDANCE_ASSUMPTIONS = (
    "Valid HH:mm punch times are normalized into chronological order per employee-day.",
    "Odd punch counts use one first-to-last fallback interval and retain an audit warning.",
    "Even punch counts sum adjacent chronological intervals.",
    "Lunch hours are fixed at 0.5 hours once after gross calculation when at least two punch boundaries exist.",
    "No overtime, tax, statutory holiday, or vacation calculations are applied.",
    "Blank punch cells are emitted as zero-hour days with review warnings.",
)


class WageFormatType(StrEnum):
    WAGE_ATTENDANCE = "WAGE_ATTENDANCE"
    UNKNOWN = "UNKNOWN"


class AttendanceCalculationMethod(StrEnum):
    NO_PUNCHES = "NO_PUNCHES"
    FIRST_LAST_FALLBACK = "FIRST_LAST_FALLBACK"
    PAIRED_INTERVALS = "PAIRED_INTERVALS"


@dataclass(frozen=True)
class WageIssue:
    code: str
    message: str
    rowNumber: int | None = None
    field: str | None = None
    employeeId: str | None = None
    employeeName: str | None = None
    workDate: date | None = None


@dataclass(frozen=True)
class WageDetectionResult:
    format_type: WageFormatType
    confidence: float
    reason: str
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    matched_sheet: str | None = None
    matched_row: int | None = None
    matched_headers: tuple[str, ...] = ()
    period_start: date | None = None
    period_end: date | None = None


@dataclass(frozen=True)
class RawCell:
    rowNumber: int
    columnNumber: int
    value: str


@dataclass(frozen=True)
class RawRow:
    rowNumber: int
    cells: tuple[RawCell, ...]


@dataclass(frozen=True)
class AttendanceWorkInterval:
    start: str
    end: str
    minutes: int
    hours: float


@dataclass(frozen=True)
class AttendanceCalculation:
    calculationMethod: AttendanceCalculationMethod
    workIntervals: tuple[AttendanceWorkInterval, ...]
    grossHours: float
    lunchHours: float
    calculatedHours: float


@dataclass(frozen=True)
class AttendanceDay:
    employeeId: str | None
    employeeName: str | None
    department: str | None
    workDate: date
    dayNumber: int
    punchTimes: tuple[str, ...]
    calculationMethod: AttendanceCalculationMethod
    workIntervals: tuple[AttendanceWorkInterval, ...]
    pairedGrossHours: float | None
    lunchHours: float
    calculatedHours: float | None
    firstPunch: str | None
    lastPunch: str | None
    rawCellValues: tuple[str, ...]
    rowNumbers: tuple[int, ...]
    warnings: tuple[WageIssue, ...] = ()
    errors: tuple[WageIssue, ...] = ()


@dataclass(frozen=True)
class AttendanceEmployeeSummary:
    employeeId: str | None
    employeeName: str | None
    department: str | None
    dayCount: int
    workedDayCount: int
    reviewDayCount: int
    totalCalculatedHours: float


@dataclass(frozen=True)
class AttendanceParseResult:
    formatType: WageFormatType
    parserVersion: str
    sourceSheet: str | None
    periodStart: date | None
    periodEnd: date | None
    confidence: float
    employees: tuple[AttendanceEmployeeSummary, ...]
    days: tuple[AttendanceDay, ...]
    rawRows: tuple[RawRow, ...]
    warnings: tuple[WageIssue, ...]
    errors: tuple[WageIssue, ...]
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class _EmployeeBlock:
    header_row_index: int
    next_header_row_index: int
    employee_id: str | None
    employee_name: str | None
    department: str | None


def detect_attendance_workbook(path: Path) -> WageDetectionResult:
    if not path.is_file():
        return WageDetectionResult(
            format_type=WageFormatType.UNKNOWN,
            confidence=0.0,
            reason=f"Wage attendance file does not exist: {path}",
            errors=(f"Wage attendance file does not exist: {path}",),
        )
    if path.suffix.lower() != ".xls":
        return WageDetectionResult(
            format_type=WageFormatType.UNKNOWN,
            confidence=0.0,
            reason=f"WAGE-P0 supports legacy .xls attendance files only: {path}",
            errors=(f"WAGE-P0 supports legacy .xls attendance files only: {path}",),
        )

    try:
        workbook = xlrd.open_workbook(path)
    except Exception as exc:
        return WageDetectionResult(
            format_type=WageFormatType.UNKNOWN,
            confidence=0.0,
            reason=f"Unable to read wage attendance workbook: {exc}",
            errors=(f"Unable to read wage attendance workbook: {exc}",),
        )

    if not workbook.sheet_names():
        return WageDetectionResult(
            format_type=WageFormatType.UNKNOWN,
            confidence=0.0,
            reason="Wage attendance workbook has no sheets.",
            errors=("Wage attendance workbook has no sheets.",),
        )

    sheet = workbook.sheet_by_index(0)
    title_row = _find_row_containing(sheet, "员 工 刷 卡 记 录 表")
    period_start, period_end = _find_period(sheet)
    employee_rows = _employee_header_row_indexes(sheet)
    matched_headers = []
    if title_row is not None:
        matched_headers.append("员 工 刷 卡 记 录 表")
    if period_start and period_end:
        matched_headers.append("考勤日期")
    if employee_rows:
        matched_headers.extend(("工号", "姓名"))

    if title_row is None or not employee_rows:
        layout_errors = []
        if title_row is None:
            layout_errors.append("Missing wage attendance title row.")
        if not employee_rows:
            layout_errors.append("Missing wage attendance employee headers.")
        return WageDetectionResult(
            format_type=WageFormatType.UNKNOWN,
            confidence=0.0,
            reason="Unsupported wage attendance workbook layout.",
            errors=tuple(layout_errors) or ("Unsupported wage attendance workbook layout.",),
            matched_sheet=sheet.name,
        )

    confidence = 0.99 if period_start and period_end else 0.85
    warnings: tuple[str, ...] = ()
    if not period_start or not period_end:
        warnings = ("Attendance period was not found in the workbook.",)

    return WageDetectionResult(
        format_type=WageFormatType.WAGE_ATTENDANCE,
        confidence=confidence,
        reason="Matched wage attendance title, employee headers, and day grid.",
        warnings=warnings,
        matched_sheet=sheet.name,
        matched_row=title_row + 1,
        matched_headers=tuple(matched_headers),
        period_start=period_start,
        period_end=period_end,
    )


def parse_attendance_workbook(path: Path) -> AttendanceParseResult:
    detection = detect_attendance_workbook(path)
    if detection.format_type != WageFormatType.WAGE_ATTENDANCE:
        return AttendanceParseResult(
            formatType=detection.format_type,
            parserVersion=ATTENDANCE_PARSER_VERSION,
            sourceSheet=detection.matched_sheet,
            periodStart=detection.period_start,
            periodEnd=detection.period_end,
            confidence=detection.confidence,
            employees=(),
            days=(),
            rawRows=(),
            warnings=tuple(
                WageIssue(code="DETECTOR_WARNING", message=warning)
                for warning in detection.warnings
            ),
            errors=tuple(
                WageIssue(code="DETECTOR_ERROR", message=error)
                for error in detection.errors
            ),
            assumptions=ATTENDANCE_ASSUMPTIONS,
        )

    workbook = xlrd.open_workbook(path)
    sheet = workbook.sheet_by_index(0)
    period_start = detection.period_start
    period_end = detection.period_end
    raw_rows = tuple(_raw_rows(sheet))
    warnings: list[WageIssue] = [
        WageIssue(code="DETECTOR_WARNING", message=warning)
        for warning in detection.warnings
    ]
    errors: list[WageIssue] = []

    if period_start is None or period_end is None:
        errors.append(
            WageIssue(
                code="ATTENDANCE_PERIOD_MISSING",
                message="Attendance period is required before parsing employee days.",
            )
        )
        return AttendanceParseResult(
            formatType=detection.format_type,
            parserVersion=ATTENDANCE_PARSER_VERSION,
            sourceSheet=sheet.name,
            periodStart=period_start,
            periodEnd=period_end,
            confidence=detection.confidence,
            employees=(),
            days=(),
            rawRows=raw_rows,
            warnings=tuple(warnings),
            errors=tuple(errors),
            assumptions=ATTENDANCE_ASSUMPTIONS,
        )

    employee_blocks = _employee_blocks(sheet)
    days: list[AttendanceDay] = []

    for block in employee_blocks:
        employee_warnings = _employee_warnings(block)
        warnings.extend(employee_warnings)
        days.extend(_parse_employee_days(sheet, block, period_start, period_end))

    for day in days:
        warnings.extend(day.warnings)
        errors.extend(day.errors)

    employees = _employee_summaries(days)

    return AttendanceParseResult(
        formatType=detection.format_type,
        parserVersion=ATTENDANCE_PARSER_VERSION,
        sourceSheet=sheet.name,
        periodStart=period_start,
        periodEnd=period_end,
        confidence=detection.confidence,
        employees=tuple(employees),
        days=tuple(days),
        rawRows=raw_rows,
        warnings=tuple(warnings),
        errors=tuple(errors),
        assumptions=ATTENDANCE_ASSUMPTIONS,
    )


def calculate_paired_work_hours(punch_times: tuple[str, ...]) -> float:
    parsed = sorted(_parse_hhmm(value) for value in punch_times)
    if len(parsed) % 2:
        raise ValueError("Paired work-hours calculation requires an even punch count.")
    total_minutes = 0
    for start, end in zip(parsed[0::2], parsed[1::2], strict=True):
        total_minutes += _minutes_since_midnight(end) - _minutes_since_midnight(start)
    return _hours_from_minutes(total_minutes)


def calculate_work_hours_after_lunch(punch_times: tuple[str, ...]) -> float:
    calculation = calculate_attendance_hours(punch_times)
    if calculation.calculationMethod != AttendanceCalculationMethod.PAIRED_INTERVALS:
        raise ValueError("Paired work-hours calculation requires an even punch count.")
    return calculation.calculatedHours


def calculate_attendance_hours(
    punch_times: tuple[str, ...],
) -> AttendanceCalculation:
    normalized = tuple(
        value.strftime("%H:%M")
        for value in sorted(_parse_hhmm(value) for value in punch_times)
    )
    if not normalized:
        return AttendanceCalculation(
            calculationMethod=AttendanceCalculationMethod.NO_PUNCHES,
            workIntervals=(),
            grossHours=0.0,
            lunchHours=0.0,
            calculatedHours=0.0,
        )

    interval_boundaries = (
        ((normalized[0], normalized[-1]),)
        if len(normalized) % 2
        else tuple(zip(normalized[0::2], normalized[1::2], strict=True))
    )
    method = (
        AttendanceCalculationMethod.FIRST_LAST_FALLBACK
        if len(normalized) % 2
        else AttendanceCalculationMethod.PAIRED_INTERVALS
    )
    intervals = tuple(
        _work_interval(start, end) for start, end in interval_boundaries
    )
    gross_minutes = sum(interval.minutes for interval in intervals)
    lunch_minutes = 30 if len(normalized) >= 2 else 0
    return AttendanceCalculation(
        calculationMethod=method,
        workIntervals=intervals,
        grossHours=_hours_from_minutes(gross_minutes),
        lunchHours=_hours_from_minutes(lunch_minutes),
        calculatedHours=_hours_from_minutes(max(gross_minutes - lunch_minutes, 0)),
    )


def _parse_employee_days(
    sheet: Any,
    block: _EmployeeBlock,
    period_start: date,
    period_end: date,
) -> list[AttendanceDay]:
    day_header_row = block.header_row_index + 1
    if day_header_row >= block.next_header_row_index:
        return []

    day_columns = _day_columns(sheet, day_header_row, period_start, period_end)
    punch_row_indexes = range(day_header_row + 1, block.next_header_row_index)
    days: list[AttendanceDay] = []

    for column_index, day_number in day_columns:
        work_date = date(period_start.year, period_start.month, day_number)
        raw_values: list[str] = []
        row_numbers: list[int] = []

        for row_index in punch_row_indexes:
            value = _cell_text(sheet.cell_value(row_index, column_index))
            if value:
                raw_values.append(value)
                row_numbers.append(row_index + 1)

        punch_times = tuple(
            sorted(
                time_value
                for raw_value in raw_values
                for time_value in _extract_hhmm_values(raw_value)
            )
        )
        day_warnings: list[WageIssue] = []
        day_errors: list[WageIssue] = []
        calculation = calculate_attendance_hours(punch_times)

        if not punch_times:
            day_warnings.append(
                _day_issue(
                    "MISSING_PUNCH_TIMES",
                    "No usable punch times found for employee-day.",
                    block,
                    work_date,
                    row_numbers,
                )
            )
        elif len(punch_times) % 2:
            day_warnings.append(
                _day_issue(
                    "ODD_PUNCH_COUNT",
                    "Odd punch count used the first-to-last fallback interval.",
                    block,
                    work_date,
                    row_numbers,
                )
            )
        days.append(
            AttendanceDay(
                employeeId=block.employee_id,
                employeeName=block.employee_name,
                department=block.department,
                workDate=work_date,
                dayNumber=day_number,
                punchTimes=punch_times,
                calculationMethod=calculation.calculationMethod,
                workIntervals=calculation.workIntervals,
                pairedGrossHours=calculation.grossHours,
                lunchHours=calculation.lunchHours,
                calculatedHours=calculation.calculatedHours,
                firstPunch=punch_times[0] if punch_times else None,
                lastPunch=punch_times[-1] if punch_times else None,
                rawCellValues=tuple(raw_values),
                rowNumbers=tuple(row_numbers),
                warnings=tuple(day_warnings),
                errors=tuple(day_errors),
            )
        )

    return days


def _employee_summaries(
    days: list[AttendanceDay],
) -> list[AttendanceEmployeeSummary]:
    grouped: dict[tuple[str | None, str | None, str | None], list[AttendanceDay]] = {}
    for day in days:
        key = (day.employeeId, day.employeeName, day.department)
        grouped.setdefault(key, []).append(day)

    summaries: list[AttendanceEmployeeSummary] = []
    for (employee_id, employee_name, department), employee_days in grouped.items():
        total_hours = sum(
            day.calculatedHours or 0.0
            for day in employee_days
            if day.calculatedHours is not None
        )
        summaries.append(
            AttendanceEmployeeSummary(
                employeeId=employee_id,
                employeeName=employee_name,
                department=department,
                dayCount=len(employee_days),
                workedDayCount=sum(1 for day in employee_days if day.punchTimes),
                reviewDayCount=sum(
                    1 for day in employee_days if day.warnings or day.errors
                ),
                totalCalculatedHours=round(total_hours, 2),
            )
        )

    return summaries


def _employee_blocks(sheet: Any) -> list[_EmployeeBlock]:
    header_indexes = _employee_header_row_indexes(sheet)
    blocks: list[_EmployeeBlock] = []

    for index, header_row_index in enumerate(header_indexes):
        next_header_row_index = (
            header_indexes[index + 1] if index + 1 < len(header_indexes) else sheet.nrows
        )
        row_values = [sheet.cell_value(header_row_index, col) for col in range(sheet.ncols)]
        blocks.append(
            _EmployeeBlock(
                header_row_index=header_row_index,
                next_header_row_index=next_header_row_index,
                employee_id=_value_after_label(row_values, "工号"),
                employee_name=_value_after_label(row_values, "姓名"),
                department=_value_after_label(row_values, "部门"),
            )
        )

    return blocks


def _employee_header_row_indexes(sheet: Any) -> list[int]:
    return [
        row_index
        for row_index in range(sheet.nrows)
        if _row_has_label(sheet, row_index, "工号")
        and _row_has_label(sheet, row_index, "姓名")
    ]


def _employee_warnings(block: _EmployeeBlock) -> tuple[WageIssue, ...]:
    warnings: list[WageIssue] = []
    row_number = block.header_row_index + 1
    if not block.employee_id:
        warnings.append(
            WageIssue(
                code="MISSING_EMPLOYEE_ID",
                message="Employee ID is missing.",
                rowNumber=row_number,
                field="employeeId",
                employeeName=block.employee_name,
            )
        )
    if not block.employee_name:
        warnings.append(
            WageIssue(
                code="MISSING_EMPLOYEE_NAME",
                message="Employee name is missing.",
                rowNumber=row_number,
                field="employeeName",
                employeeId=block.employee_id,
            )
        )
    if not block.department:
        warnings.append(
            WageIssue(
                code="MISSING_DEPARTMENT",
                message="Employee department is missing.",
                rowNumber=row_number,
                field="department",
                employeeId=block.employee_id,
                employeeName=block.employee_name,
            )
        )
    return tuple(warnings)


def _day_issue(
    code: str,
    message: str,
    block: _EmployeeBlock,
    work_date: date,
    row_numbers: list[int],
) -> WageIssue:
    return WageIssue(
        code=code,
        message=message,
        rowNumber=row_numbers[0] if row_numbers else block.header_row_index + 1,
        field="punchTimes",
        employeeId=block.employee_id,
        employeeName=block.employee_name,
        workDate=work_date,
    )


def _day_columns(
    sheet: Any,
    day_header_row: int,
    period_start: date,
    period_end: date,
) -> list[tuple[int, int]]:
    columns: list[tuple[int, int]] = []
    for column_index in range(sheet.ncols):
        day_number = _day_number(sheet.cell_value(day_header_row, column_index))
        if day_number is None:
            continue
        try:
            work_date = date(period_start.year, period_start.month, day_number)
        except ValueError:
            continue
        if period_start <= work_date <= period_end:
            columns.append((column_index, day_number))
    return columns


def _day_number(value: object) -> int | None:
    if isinstance(value, (int, float)) and float(value).is_integer():
        day_number = int(value)
        return day_number if 1 <= day_number <= 31 else None
    text = _cell_text(value)
    if text.isdigit():
        day_number = int(text)
        return day_number if 1 <= day_number <= 31 else None
    return None


def _raw_rows(sheet: Any) -> list[RawRow]:
    rows: list[RawRow] = []
    for row_index in range(sheet.nrows):
        cells: list[RawCell] = []
        for column_index in range(sheet.ncols):
            value = _cell_text(sheet.cell_value(row_index, column_index))
            if value:
                cells.append(
                    RawCell(
                        rowNumber=row_index + 1,
                        columnNumber=column_index + 1,
                        value=value,
                    )
                )
        if cells:
            rows.append(RawRow(rowNumber=row_index + 1, cells=tuple(cells)))
    return rows


def _find_row_containing(sheet: Any, needle: str) -> int | None:
    compact_needle = _compact(needle)
    for row_index in range(sheet.nrows):
        for column_index in range(sheet.ncols):
            if compact_needle in _compact(_cell_text(sheet.cell_value(row_index, column_index))):
                return row_index
    return None


def _find_period(sheet: Any) -> tuple[date | None, date | None]:
    pattern = re.compile(
        r"(\d{4})-(\d{1,2})-(\d{1,2}).*?(\d{4})-(\d{1,2})-(\d{1,2})"
    )
    for row_index in range(sheet.nrows):
        for column_index in range(sheet.ncols):
            match = pattern.search(_cell_text(sheet.cell_value(row_index, column_index)))
            if match:
                values = [int(value) for value in match.groups()]
                return (
                    date(values[0], values[1], values[2]),
                    date(values[3], values[4], values[5]),
                )
    return None, None


def _row_has_label(sheet: Any, row_index: int, label: str) -> bool:
    compact_label = _compact(label)
    return any(
        compact_label in _compact(_cell_text(sheet.cell_value(row_index, column_index)))
        for column_index in range(sheet.ncols)
    )


def _value_after_label(row_values: list[object], label: str) -> str | None:
    compact_label = _compact(label)
    for index, value in enumerate(row_values):
        if compact_label not in _compact(_cell_text(value)):
            continue
        for candidate in row_values[index + 1 :]:
            text = _cell_text(candidate)
            if text:
                return text
    return None


def _extract_hhmm_values(value: str) -> tuple[str, ...]:
    return tuple(
        f"{int(hour):02d}:{int(minute):02d}"
        for hour, minute in re.findall(r"\b(\d{1,2}):(\d{2})\b", value)
        if 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59
    )


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


def _minutes_since_midnight(value: time) -> int:
    return value.hour * 60 + value.minute


def _work_interval(start: str, end: str) -> AttendanceWorkInterval:
    start_time = _parse_hhmm(start)
    end_time = _parse_hhmm(end)
    minutes = _minutes_since_midnight(end_time) - _minutes_since_midnight(start_time)
    return AttendanceWorkInterval(
        start=start,
        end=end,
        minutes=minutes,
        hours=_hours_from_minutes(minutes),
    )


def _hours_from_minutes(minutes: int) -> float:
    return round(minutes / 60, 2)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return re.sub(r"\s+\n", "\n", text)


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("：", ":").replace(":", "")
