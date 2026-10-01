"""Narrow persisted-row reader adapted from stripSystem wage/api.py; see NOTICE."""
from datetime import date, datetime
from typing import Any

from bestar_work_hours.wage.attendance import (
    AttendanceCalculationMethod, AttendanceDay, AttendanceWorkInterval, WageIssue,
)

class PersistedAttendanceContractError(ValueError):
    pass

def _persisted_day(value: dict[str, Any]) -> AttendanceDay:
    if not isinstance(value, dict):
        raise PersistedAttendanceContractError(
            "Persisted attendance day must be an object."
        )
    work_date = _date_or_none(value.get("workDate"))
    if work_date is None:
        raise PersistedAttendanceContractError(
            "Persisted attendance day is missing workDate."
        )
    calculation_method = value.get("calculationMethod")
    if calculation_method not in {
        "NO_PUNCHES",
        "FIRST_LAST_FALLBACK",
        "PAIRED_INTERVALS",
    }:
        raise PersistedAttendanceContractError(
            "Persisted attendance calculation method is unsupported."
        )
    if not isinstance(value.get("workIntervals"), list):
        raise PersistedAttendanceContractError(
            "Persisted attendance workIntervals must be an array."
        )
    return AttendanceDay(
        employeeId=value.get("employeeId"),
        employeeName=value.get("employeeName"),
        department=value.get("department"),
        workDate=work_date,
        dayNumber=int(value.get("dayNumber", work_date.day)),
        punchTimes=tuple(str(item) for item in value.get("punchTimes", [])),
        calculationMethod=AttendanceCalculationMethod(str(calculation_method)),
        workIntervals=tuple(
            AttendanceWorkInterval(
                start=str(item.get("start", "")),
                end=str(item.get("end", "")),
                minutes=int(item.get("minutes", 0)),
                hours=float(item.get("hours", 0)),
            )
            for item in value.get("workIntervals", [])
        ),
        pairedGrossHours=_float_or_none(value.get("pairedGrossHours")),
        lunchHours=float(value.get("lunchHours") or 0),
        calculatedHours=_float_or_none(value.get("calculatedHours")),
        firstPunch=value.get("firstPunch"),
        lastPunch=value.get("lastPunch"),
        rawCellValues=tuple(str(item) for item in value.get("rawCellValues", [])),
        rowNumbers=tuple(int(item) for item in value.get("rowNumbers", [])),
        warnings=tuple(_persisted_issue(issue) for issue in value.get("warnings", [])),
        errors=tuple(_persisted_issue(issue) for issue in value.get("errors", [])),
    )



def _persisted_issue(value: dict[str, Any]) -> WageIssue:
    return WageIssue(
        code=str(value.get("code", "ATTENDANCE_REVIEW_REQUIRED")),
        message=str(value.get("message", value.get("code", "Review required"))),
        rowNumber=int(value["rowNumber"])
        if value.get("rowNumber") is not None
        else None,
        field=value.get("field"),
        employeeId=value.get("employeeId"),
        employeeName=value.get("employeeName"),
        workDate=_date_or_none(value.get("workDate")),
    )



def _date_or_none(value: Any) -> date | None:
    if value in (None, ""):
        return None
    return datetime.fromisoformat(str(value)[:10]).date()



def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
