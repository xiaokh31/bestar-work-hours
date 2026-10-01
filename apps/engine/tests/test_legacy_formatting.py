"""Migrated synthetic BIFF adaptive-dimensions regression."""
from pathlib import Path

import xlrd
import xlwt

from bestar_work_hours.hashing import compute_sha256
from bestar_work_hours.wage.legacy_xls import (
    LegacyXlsTemplateEditor, MAX_COLUMN_WIDTH_CHARS, MAX_ROW_HEIGHT_TWIPS,
    XLS_COLUMN_WIDTH_UNIT,
)


def test_legacy_xls_adaptive_dimensions_are_bounded_cjk_aware_and_deterministic(
    tmp_path: Path,
) -> None:
    template_path = tmp_path / "adaptive-template.xls"
    _write_adaptive_template(template_path)
    source = xlrd.open_workbook(template_path, formatting_info=True)

    outputs: list[Path] = []
    for index in range(2):
        output_path = tmp_path / f"adaptive-output-{index}.xls"
        editor = LegacyXlsTemplateEditor(template_path)
        editor.write(0, 3, 0, "A" * 100)
        editor.write(0, 4, 1, "ABCDEFGHIJ")
        editor.write(0, 5, 2, "中" * 10)
        editor.write(0, 6, 3, "first line\n第二行内容超过宽度")
        editor.write(0, 7, 4, "ok")
        editor.save(output_path)
        outputs.append(output_path)

    assert compute_sha256(outputs[0]) == compute_sha256(outputs[1])
    output = xlrd.open_workbook(outputs[0], formatting_info=True)
    source_sheet = source.sheet_by_index(0)
    output_sheet = output.sheet_by_index(0)

    assert output_sheet.colinfo_map[0].width == int(
        MAX_COLUMN_WIDTH_CHARS * XLS_COLUMN_WIDTH_UNIT
    )
    assert output_sheet.colinfo_map[1].width < output_sheet.colinfo_map[2].width
    assert output_sheet.colinfo_map[4].width == source_sheet.colinfo_map[4].width
    assert output_sheet.rowinfo_map[3].height > source_sheet.rowinfo_map[3].height
    assert output_sheet.rowinfo_map[6].height > source_sheet.rowinfo_map[6].height
    assert output_sheet.rowinfo_map[3].height <= MAX_ROW_HEIGHT_TWIPS
    assert output_sheet.rowinfo_map[6].height <= MAX_ROW_HEIGHT_TWIPS

    for row_index, column_index in ((3, 0), (4, 1), (5, 2), (6, 3)):
        source_style = _normalized_style(source, source_sheet, row_index, column_index)
        output_style = _normalized_style(output, output_sheet, row_index, column_index)
        assert source_style[:-1] == output_style[:-1]
        assert output_style[-1]["text_wrapped"] == 1



def _write_adaptive_template(path: Path) -> None:
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Adaptive")
    style = xlwt.easyxf(
        "font: name Arial, colour blue; pattern: pattern solid, fore_colour yellow; "
        "align: horiz center, vert center; "
        "borders: left thin, right thin, top thin, bottom thin"
    )
    for column_index, width_chars in enumerate((8, 8, 8, 8, 20)):
        sheet.col(column_index).width = width_chars * XLS_COLUMN_WIDTH_UNIT
    for row_index in range(3, 8):
        sheet.row(row_index).height = 300
        for column_index in range(5):
            sheet.write(row_index, column_index, "template", style)
    workbook.save(str(path))



def _normalized_style(workbook, sheet, row_index: int, column_index: int):
    xf = workbook.xf_list[sheet.cell_xf_index(row_index, column_index)]
    font = workbook.font_list[xf.font_index]
    font_properties = {
        key: value for key, value in vars(font).items() if key != "font_index"
    }
    colour_properties = {
        "font": workbook.colour_map.get(font.colour_index),
        "pattern": workbook.colour_map.get(xf.background.pattern_colour_index),
        "background": workbook.colour_map.get(xf.background.background_colour_index),
    }
    return (
        font_properties,
        colour_properties,
        vars(xf.border).copy(),
        vars(xf.background).copy(),
        workbook.format_map[xf.format_key].format_str,
        vars(xf.protection).copy(),
        vars(xf.alignment).copy(),
    )
