"""Manufactured fixtures only; these are not real-sample acceptance evidence."""

from calendar import monthrange
from datetime import date
from pathlib import Path

import xlwt

from bestar_work_hours.wage import parse_attendance_workbook


def write_attendance(
    path: Path,
    *,
    year: int = 2026,
    month: int = 6,
    employee_count: int = 2,
    punches: dict[int, str] | None = None,
    marker: str = "",
) -> Path:
    days = monthrange(year, month)[1]
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Synthetic Attendance")
    sheet.write(0, 0, "员 工 刷 卡 记 录 表")
    sheet.write(1, 0, f"考勤日期：{date(year, month, 1)} 至 {date(year, month, days)}")
    sheet.write(2, 0, "SYNTHETIC TEST DATA ONLY / 非真实员工数据 " + marker)
    for employee in range(1, employee_count + 1):
        row = 3 + (employee - 1) * 3
        for column, value in enumerate(
            ["工号：", f"TEST{employee:03d}", "姓名：", f"Test Member {employee:03d}",
             "部门：", "Synthetic Team"]
        ):
            sheet.write(row, column, value)
        for day in range(1, days + 1):
            sheet.write(row + 1, day - 1, day)
            sheet.write(row + 2, day - 1, (punches or {}).get(day, "08:00\n17:00"))
    workbook.save(str(path))
    return path


def synthetic_result(tmp_path: Path, *, year: int = 2026, month: int = 6, employees: int = 2):
    return parse_attendance_workbook(write_attendance(
        tmp_path / f"synthetic-{year}-{month}-{employees}.xls",
        year=year, month=month, employee_count=employees,
    ))
