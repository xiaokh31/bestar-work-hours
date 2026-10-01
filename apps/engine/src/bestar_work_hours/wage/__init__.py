"""Focused public API; importing it does not load any legacy worker services."""

from .attendance import (
    ATTENDANCE_PARSER_VERSION,
    AttendanceCalculation,
    AttendanceCalculationMethod,
    AttendanceDay,
    AttendanceEmployeeSummary,
    AttendanceParseResult,
    AttendanceWorkInterval,
    WageDetectionResult,
    WageFormatType,
    WageIssue,
    calculate_attendance_hours,
    calculate_paired_work_hours,
    calculate_work_hours_after_lunch,
    detect_attendance_workbook,
    parse_attendance_workbook,
)
from .generator import WageRecordGenerationResult, generate_wage_record

__all__ = [
    "ATTENDANCE_PARSER_VERSION", "AttendanceCalculation", "AttendanceCalculationMethod",
    "AttendanceDay", "AttendanceEmployeeSummary", "AttendanceParseResult",
    "AttendanceWorkInterval", "WageDetectionResult", "WageFormatType", "WageIssue",
    "WageRecordGenerationResult", "calculate_attendance_hours", "calculate_paired_work_hours",
    "calculate_work_hours_after_lunch", "detect_attendance_workbook", "generate_wage_record",
    "parse_attendance_workbook",
]
