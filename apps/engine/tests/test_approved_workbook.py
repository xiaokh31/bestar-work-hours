"""Binary workbook checks on generated synthetic data, not Excel visual acceptance."""

import struct
from pathlib import Path

import xlrd
import pytest

from bestar_work_hours.wage import generate_wage_record
from bestar_work_hours.wage.template import default_template_path
from .biff_helpers import _biff_record_payloads, _sheet_record_payloads
from .fixtures import synthetic_result


@pytest.mark.parametrize("employees", [1, 2, 5, 6, 13, 16])
def test_approved_workbook_keeps_only_used_employee_sheets_and_preserves_formatting(tmp_path: Path, employees):
    template = default_template_path()
    result = generate_wage_record(
        attendance_result=synthetic_result(tmp_path, employees=employees),
        template_path=template, output_dir=tmp_path / "output",
    )
    assert result.validated, result.errors
    before = xlrd.open_workbook(template, formatting_info=True)
    after = xlrd.open_workbook(result.outputPath, formatting_info=True)
    assert before.nsheets == 17
    assert after.nsheets == employees + 1  # Actual employees + original adjustments sheet.
    assert not any(name.startswith("EMPLOYEE-") for name in after.sheet_names())
    assert not any(isinstance(cell.value, str) and "EMPLOYEE-" in cell.value
                   for sheet in after.sheets() for row in range(sheet.nrows) for cell in sheet.row(row))
    tab_ids = struct.unpack("<" + "H" * after.nsheets, _biff_record_payloads(result.outputPath, 0x013D)[0])
    assert len(set(tab_ids)) == after.nsheets
    for payload in _biff_record_payloads(result.outputPath, 0x0017):
        for offset in range(2, len(payload), 6):
            _, first, last = struct.unpack_from("<Hhh", payload, offset)
            assert (first, last) == (-1, -1) or 0 <= first <= last < after.nsheets
    for payload in _biff_record_payloads(result.outputPath, 0x003D):
        assert all(struct.unpack_from("<H", payload, offset)[0] < after.nsheets for offset in (10, 12))
    retained = [i for i, sheet in enumerate(before.sheets())
                if sheet.name == "ADJUSTMENTS" or int(sheet.name.split("-")[1]) <= employees]
    assert len(before.xf_list) == len(after.xf_list) == 107
    # The only defined name is local to employee slot 2 (print range).
    if employees == 1:
        assert not _biff_record_payloads(result.outputPath, 0x0018)
    else:
        assert _biff_record_payloads(template, 0x0018) == _biff_record_payloads(result.outputPath, 0x0018)
    for output_index, index in enumerate(retained):
        source_sheet = before.sheet_by_index(index)
        output_sheet = after.sheet_by_index(output_index)
        assert source_sheet.merged_cells == output_sheet.merged_cells
        for record_id in (0x00A1, 0x0026, 0x0027, 0x0028, 0x0029, 0x001A, 0x001B):
            assert _sheet_record_payloads(template, source_sheet.name, record_id) == _sheet_record_payloads(result.outputPath, output_sheet.name, record_id)
        source_formulas = _sheet_record_payloads(template, source_sheet.name, 0x0006)
        output_formulas = _sheet_record_payloads(result.outputPath, output_sheet.name, 0x0006)
        output_by_cell = {struct.unpack_from("<HH", item): item for item in output_formulas}
        header_row = next((row for row in range(source_sheet.nrows)
                           if "DATE" in source_sheet.row_values(row)), None)
        total_row = next((row for row in range(source_sheet.nrows)
                          if any(str(value).upper().startswith("TOTAL HOURS")
                                 for value in source_sheet.row_values(row))), None)
        for formula in source_formulas:
            row, col = struct.unpack_from("<HH", formula)
            # Explicit date/hour/total cells are rewritten by the inherited engine.
            if source_sheet.name != "ADJUSTMENTS" and ((header_row < row < total_row and col < 6) or (row == total_row and col in (0, 2))):
                continue
            assert output_by_cell[(row, col)] == formula
        if source_sheet.name == "ADJUSTMENTS":
            assert output_sheet.name == source_sheet.name
            assert source_formulas == output_formulas
            assert source_sheet.nrows == output_sheet.nrows
            assert source_sheet.ncols == output_sheet.ncols
            for row in range(source_sheet.nrows):
                assert source_sheet.row_values(row) == output_sheet.row_values(row)
                for col in range(source_sheet.ncols):
                    assert source_sheet.cell_xf_index(row, col) == output_sheet.cell_xf_index(row, col)
