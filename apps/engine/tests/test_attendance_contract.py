"""Migrated synthetic calculation/layout tests; no private sample dependencies."""
from pathlib import Path

import xlwt

from bestar_work_hours.wage import (
    AttendanceCalculationMethod,
    WageFormatType,
    calculate_attendance_hours,
    calculate_paired_work_hours,
    calculate_work_hours_after_lunch,
    detect_attendance_workbook,
    parse_attendance_workbook,
)


def test_wage_attendance_calculates_four_punch_day_by_pairing() -> None:
    assert calculate_paired_work_hours(("08:00", "12:00", "13:00", "17:30")) == 8.5
    assert (
        calculate_work_hours_after_lunch(("08:00", "12:00", "13:00", "17:30")) == 8.0
    )



def test_wage_attendance_calculation_contract_covers_parity_lunch_and_rounding() -> None:
    no_punches = calculate_attendance_hours(())
    assert no_punches.calculationMethod == AttendanceCalculationMethod.NO_PUNCHES
    assert no_punches.workIntervals == ()
    assert (no_punches.grossHours, no_punches.lunchHours, no_punches.calculatedHours) == (
        0.0,
        0.0,
        0.0,
    )

    one_punch = calculate_attendance_hours(("08:00",))
    assert one_punch.calculationMethod == AttendanceCalculationMethod.FIRST_LAST_FALLBACK
    assert one_punch.workIntervals[0].start == "08:00"
    assert one_punch.workIntervals[0].end == "08:00"
    assert (one_punch.grossHours, one_punch.lunchHours, one_punch.calculatedHours) == (
        0.0,
        0.0,
        0.0,
    )

    two_punches = calculate_attendance_hours(("17:00", "08:00"))
    assert two_punches.calculationMethod == AttendanceCalculationMethod.PAIRED_INTERVALS
    assert (two_punches.grossHours, two_punches.lunchHours, two_punches.calculatedHours) == (
        9.0,
        0.5,
        8.5,
    )

    three_punches = calculate_attendance_hours(("17:10", "09:00", "17:09"))
    assert three_punches.calculationMethod == AttendanceCalculationMethod.FIRST_LAST_FALLBACK
    assert len(three_punches.workIntervals) == 1
    assert three_punches.workIntervals[0].minutes == 490
    assert (three_punches.grossHours, three_punches.lunchHours, three_punches.calculatedHours) == (
        8.17,
        0.5,
        7.67,
    )

    four_punches = calculate_attendance_hours(("13:00", "17:30", "08:00", "12:00"))
    assert [interval.minutes for interval in four_punches.workIntervals] == [240, 270]
    assert (four_punches.grossHours, four_punches.lunchHours, four_punches.calculatedHours) == (
        8.5,
        0.5,
        8.0,
    )

    six_punches = calculate_attendance_hours(
        ("17:00", "08:00", "12:00", "10:00", "13:00", "10:00")
    )
    assert [interval.minutes for interval in six_punches.workIntervals] == [120, 120, 240]
    assert (six_punches.grossHours, six_punches.lunchHours, six_punches.calculatedHours) == (
        8.0,
        0.5,
        7.5,
    )

    repeated = calculate_attendance_hours(("17:00", "08:00", "17:00", "08:00"))
    assert [interval.minutes for interval in repeated.workIntervals] == [0, 0]
    assert repeated.grossHours == 0.0
    assert repeated.lunchHours == 0.5
    assert repeated.calculatedHours == 0.0

    accumulated_before_rounding = calculate_attendance_hours(
        ("08:00", "08:01", "09:00", "09:01")
    )
    assert [interval.hours for interval in accumulated_before_rounding.workIntervals] == [
        0.02,
        0.02,
    ]
    assert accumulated_before_rounding.grossHours == 0.03
    assert accumulated_before_rounding.calculatedHours == 0.0



def test_wage_attendance_parser_filters_invalid_times_and_preserves_raw_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid-and-unsorted-times.xls"
    _write_xls(
        path,
        [
            ["员 工 刷 卡 记 录 表"],
            ["考勤日期：2026-06-01 至 2026-06-01"],
            ["工号：", "42", "姓名：", "edge", "部门：", "公司"],
            [1],
            ["17:00\ninvalid\n25:61\n08:00"],
        ],
    )

    parsed = parse_attendance_workbook(path)
    day = parsed.days[0]

    assert day.punchTimes == ("08:00", "17:00")
    assert day.rawCellValues == ("17:00\ninvalid\n25:61\n08:00",)
    assert day.rowNumbers == (5,)
    assert day.calculationMethod == AttendanceCalculationMethod.PAIRED_INTERVALS
    assert day.calculatedHours == 8.5



def test_wage_attendance_detector_returns_error_for_unsupported_xls(
    tmp_path: Path,
) -> None:
    unsupported_path = tmp_path / "unsupported.xls"
    _write_xls(
        unsupported_path,
        [
            ["not an attendance workbook"],
            ["DATE", "HOURS"],
        ],
    )

    detection = detect_attendance_workbook(unsupported_path)
    parsed = parse_attendance_workbook(unsupported_path)

    assert detection.format_type == WageFormatType.UNKNOWN
    assert detection.reason == "Unsupported wage attendance workbook layout."
    assert "Missing wage attendance title row." in detection.errors
    assert "Missing wage attendance employee headers." in detection.errors
    assert parsed.errors
    assert parsed.errors[0].code == "DETECTOR_ERROR"
    assert "Missing wage attendance title row." in parsed.errors[0].message



def test_wage_attendance_parser_errors_when_attendance_period_is_missing(
    tmp_path: Path,
) -> None:
    missing_period_path = tmp_path / "missing-period.xls"
    _write_xls(
        missing_period_path,
        [
            ["员 工 刷 卡 记 录 表"],
            ["工号：", "42", "姓名：", "manual edge", "部门：", "公司"],
            [1, 2],
            ["08:00\n17:00", ""],
        ],
    )

    detection = detect_attendance_workbook(missing_period_path)
    parsed = parse_attendance_workbook(missing_period_path)

    assert detection.format_type == WageFormatType.WAGE_ATTENDANCE
    assert "Attendance period was not found in the workbook." in detection.warnings
    assert parsed.days == ()
    assert parsed.rawRows
    assert parsed.errors[0].code == "ATTENDANCE_PERIOD_MISSING"



def _write_xls(path: Path, rows: list[list[object]]) -> None:
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Sheet1")
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            sheet.write(row_index, column_index, value)
    workbook.save(str(path))
