"""Migrated regressions with manufactured attendance, never real-sample acceptance."""
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import xlrd

import bestar_work_hours.wage.generator as generator_module
from bestar_work_hours.hashing import compute_sha256
from bestar_work_hours.wage import generate_wage_record
from bestar_work_hours.wage.legacy_xls import LegacyXlsTemplateEditor
from bestar_work_hours.wage.template import (
    WAGE_TEMPLATE_WEEKDAY_XF_INDEX, WAGE_TEMPLATE_WEEKEND_XF_INDEX, default_template_path,
)
from .fixtures import synthetic_result

WAGE_TEMPLATE = default_template_path()


def test_weekday_fill_semantics_follow_actual_dates_across_month_offsets(
    tmp_path: Path,
) -> None:
    weekday_fill, weekend_fill = _approved_weekday_fill_contract()
    mismatch_counts = {
        "weekdayText": 0,
        "weekdayFill": 0,
        "weekendFill": 0,
        "blankSlot": 0,
    }

    for label, period_start, period_end in (
        ("june", date(2026, 6, 1), date(2026, 6, 30)),
        ("july", date(2026, 7, 1), date(2026, 7, 31)),
        ("leap-february", date(2024, 2, 1), date(2024, 2, 29)),
        ("short-february", date(2025, 2, 1), date(2025, 2, 28)),
    ):
        result = generate_wage_record(
            attendance_result=synthetic_result(tmp_path, year=period_start.year, month=period_start.month, employees=16),
            template_path=WAGE_TEMPLATE,
            output_dir=tmp_path / label,
            generated_at=datetime(2026, 8, 1, 9, 0, 0),
        )
        assert result.errors == ()
        assert result.writtenEmployeeCount == 16
        workbook = xlrd.open_workbook(result.outputPath, formatting_info=True)
        assert len(workbook.xf_list) == 107
        for sheet_name in result.matchedSheets:
            sheet = workbook.sheet_by_name(sheet_name)
            date_rows = _generated_date_rows(sheet)
            assert len(date_rows) == 31
            for offset, row_index in enumerate(date_rows):
                if offset > (period_end - period_start).days:
                    if (
                        str(sheet.cell_value(row_index, 0)).strip()
                        or str(sheet.cell_value(row_index, 1)).strip()
                        or _fill_signature(workbook, sheet, row_index, 0)
                        != weekday_fill
                    ):
                        mismatch_counts["blankSlot"] += 1
                    continue

                work_date = period_start + timedelta(days=offset)
                expected_weekday = work_date.strftime("%a").upper()
                if str(sheet.cell_value(row_index, 0)).strip() != expected_weekday:
                    mismatch_counts["weekdayText"] += 1
                actual_fill = _fill_signature(workbook, sheet, row_index, 0)
                if work_date.weekday() >= 5:
                    mismatch_counts["weekendFill"] += actual_fill != weekend_fill
                else:
                    mismatch_counts["weekdayFill"] += actual_fill != weekday_fill

    assert mismatch_counts == {
        "weekdayText": 0,
        "weekdayFill": 0,
        "weekendFill": 0,
        "blankSlot": 0,
    }



def test_generation_failures_have_distinct_codes_and_leave_no_partial_workbook(
    tmp_path: Path,
    monkeypatch,
) -> None:
    parsed = synthetic_result(tmp_path)
    template_sha = compute_sha256(WAGE_TEMPLATE)

    missing_period = generate_wage_record(
        attendance_result=replace(parsed, periodStart=None, periodEnd=None),
        template_path=WAGE_TEMPLATE,
        output_dir=tmp_path / "missing-period",
    )
    assert missing_period.errorCode == "WAGE_GENERATION_PERIOD_MISSING"

    missing_template = generate_wage_record(
        attendance_result=parsed,
        template_path=tmp_path / "missing-template.xls",
        output_dir=tmp_path / "missing-template",
    )
    assert missing_template.errorCode == "WAGE_TEMPLATE_MISSING"

    unreadable_template_path = tmp_path / "unreadable-template.xls"
    unreadable_template_path.write_bytes(b"not-an-ole-workbook")
    unreadable_template = generate_wage_record(
        attendance_result=parsed,
        template_path=unreadable_template_path,
        output_dir=tmp_path / "unreadable-template",
    )
    assert unreadable_template.errorCode == "WAGE_TEMPLATE_UNREADABLE"

    changed_template_path = tmp_path / "changed-template.xls"
    changed_template_path.write_bytes(WAGE_TEMPLATE.read_bytes() + b"changed")
    changed_template = generate_wage_record(
        attendance_result=parsed,
        template_path=changed_template_path,
        output_dir=tmp_path / "changed-template",
    )
    assert changed_template.errorCode == "WAGE_TEMPLATE_SHA_MISMATCH"

    def fail_save(self, output_path: Path) -> None:
        raise OSError("injected save failure")

    monkeypatch.setattr(LegacyXlsTemplateEditor, "save", fail_save)
    save_failure_dir = tmp_path / "save-failure"
    save_failure = generate_wage_record(
        attendance_result=parsed,
        template_path=WAGE_TEMPLATE,
        output_dir=save_failure_dir,
    )
    assert save_failure.errorCode == "WAGE_GENERATION_SAVE_FAILED"
    assert tuple(save_failure_dir.glob("*.staging")) == ()
    assert tuple(save_failure_dir.glob("wage-record-*.xls")) == ()
    monkeypatch.undo()

    def fail_validation(**_kwargs) -> None:
        raise ValueError("injected validation failure")

    monkeypatch.setattr(
        generator_module,
        "_validate_staged_workbook",
        fail_validation,
    )
    validation_failure_dir = tmp_path / "validation-failure"
    validation_failure = generate_wage_record(
        attendance_result=parsed,
        template_path=WAGE_TEMPLATE,
        output_dir=validation_failure_dir,
    )
    assert validation_failure.errorCode == ("WAGE_GENERATION_OUTPUT_VALIDATION_FAILED")
    assert tuple(validation_failure_dir.glob("*.staging")) == ()
    assert tuple(validation_failure_dir.glob("wage-record-*.xls")) == ()
    assert compute_sha256(WAGE_TEMPLATE) == template_sha



def test_saved_weekday_style_mismatch_fails_validation_and_cleans_staging(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_save = LegacyXlsTemplateEditor.save

    def save_with_corrupt_monday_style(self, output_path: Path) -> None:
        original_save(self, output_path)
        corrupt_editor = LegacyXlsTemplateEditor(output_path, update_dimensions=False)
        corrupt_editor.write(0, 3, 0, "MON", style_xf_index=87)
        corrupt_path = output_path.with_suffix(".corrupt")
        original_save(corrupt_editor, corrupt_path)
        corrupt_path.replace(output_path)

    monkeypatch.setattr(LegacyXlsTemplateEditor, "save", save_with_corrupt_monday_style)
    output_dir = tmp_path / "validation-cleanup"
    result = generate_wage_record(
        attendance_result=synthetic_result(tmp_path),
        template_path=WAGE_TEMPLATE,
        output_dir=output_dir,
        generated_at=datetime(2026, 8, 1, 9, 0, 0),
    )

    assert result.errorCode == "WAGE_OUTPUT_WEEKDAY_STYLE_MISMATCH"
    assert result.generationStage == "VALIDATE"
    assert result.validated is False
    assert tuple(output_dir.glob("*.staging")) == ()
    assert tuple(output_dir.glob("*.corrupt")) == ()
    assert tuple(output_dir.glob("wage-record-*.xls")) == ()
    assert not result.manifestPath.exists()



def test_generation_fails_closed_when_employee_slot_capacity_is_exceeded(
    tmp_path: Path,
) -> None:
    parsed = synthetic_result(tmp_path)
    worked_day = next(day for day in parsed.days if day.punchTimes)
    over_capacity_days = tuple(
        replace(
            worked_day,
            employeeId=f"EMP-{index:03d}",
            employeeName=f"Team Member {index:03d}",
        )
        for index in range(17)
    )

    result = generate_wage_record(
        attendance_result=replace(parsed, days=over_capacity_days),
        template_path=WAGE_TEMPLATE,
        output_dir=tmp_path,
    )

    assert result.errorCode == "WAGE_TEMPLATE_EMPLOYEE_CAPACITY_EXCEEDED"
    assert result.generationStage == "SHEET_MATCH"
    assert result.validated is False
    assert not result.outputPath.exists()



def _approved_weekday_fill_contract() -> tuple[tuple[object, ...], tuple[object, ...]]:
    workbook = xlrd.open_workbook(WAGE_TEMPLATE, formatting_info=True)
    weekday_fill = tuple(
        sorted(
            vars(
                workbook.xf_list[WAGE_TEMPLATE_WEEKDAY_XF_INDEX].background
            ).items()
        )
    )
    weekend_fill = tuple(
        sorted(
            vars(
                workbook.xf_list[WAGE_TEMPLATE_WEEKEND_XF_INDEX].background
            ).items()
        )
    )
    assert weekday_fill != weekend_fill
    return weekday_fill, weekend_fill



def _fill_signature(workbook, sheet, row_index: int, column_index: int):
    xf = workbook.xf_list[sheet.cell_xf_index(row_index, column_index)]
    return tuple(sorted(vars(xf.background).items()))



def _generated_date_rows(sheet) -> tuple[int, ...]:
    header_row = next(
        row_index
        for row_index in range(sheet.nrows)
        if "DATE"
        in {
            str(sheet.cell_value(row_index, column_index)).strip().upper()
            for column_index in range(sheet.ncols)
        }
    )
    rows: list[int] = []
    for row_index in range(header_row + 1, sheet.nrows):
        values = {
            str(sheet.cell_value(row_index, column_index)).strip().upper()
            for column_index in range(sheet.ncols)
        }
        if any(value.startswith("TOTAL HOURS") for value in values):
            break
        rows.append(row_index)
    return tuple(rows[-31:])
