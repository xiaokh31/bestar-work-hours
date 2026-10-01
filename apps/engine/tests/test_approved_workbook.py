"""Binary workbook checks on generated synthetic data, not Excel visual acceptance."""

import struct
from pathlib import Path

import xlrd

from bestar_work_hours.wage import generate_wage_record
from bestar_work_hours.wage.template import default_template_path
from .biff_helpers import _biff_record_payloads, _sheet_record_payloads
from .fixtures import synthetic_result


def test_approved_workbook_preserves_formulas_merges_print_and_untouched_sheets(tmp_path: Path):
    template = default_template_path()
    result = generate_wage_record(
        attendance_result=synthetic_result(tmp_path),
        template_path=template, output_dir=tmp_path / "output",
    )
    assert result.validated, result.errors
    before = xlrd.open_workbook(template, formatting_info=True)
    after = xlrd.open_workbook(result.outputPath, formatting_info=True)
    assert before.nsheets == after.nsheets == 17
    assert len(before.xf_list) == len(after.xf_list) == 107
    # NAME (including print areas), SETUP, margins and page breaks.
    for record_id in (0x0018, 0x00A1, 0x0026, 0x0027, 0x0028, 0x0029, 0x001A, 0x001B):
        assert _biff_record_payloads(template, record_id) == _biff_record_payloads(
            result.outputPath, record_id,
        )
    for index, source_sheet in enumerate(before.sheets()):
        output_sheet = after.sheet_by_index(index)
        assert source_sheet.merged_cells == output_sheet.merged_cells
        source_formulas = _sheet_record_payloads(template, source_sheet.name, 0x0006)
        output_formulas = _sheet_record_payloads(result.outputPath, output_sheet.name, 0x0006)
        output_by_cell = {struct.unpack_from("<HH", item): item for item in output_formulas}
        for formula in source_formulas:
            row, col = struct.unpack_from("<HH", formula)
            # Explicit date/hour/total cells are rewritten by the inherited engine.
            if index < 2 and ((3 <= row <= 33 and col < 6) or (row == 34 and col in (0, 2))):
                continue
            assert output_by_cell[(row, col)] == formula
        if index >= 2:
            assert output_sheet.name == source_sheet.name
            assert source_formulas == output_formulas
            assert source_sheet.nrows == output_sheet.nrows
            assert source_sheet.ncols == output_sheet.ncols
            for row in range(source_sheet.nrows):
                assert source_sheet.row_values(row) == output_sheet.row_values(row)
                for col in range(source_sheet.ncols):
                    assert source_sheet.cell_xf_index(row, col) == output_sheet.cell_xf_index(row, col)
