# Adapted from Bestar stripSystem (Apache-2.0); standalone imports/resources. See NOTICE.
from __future__ import annotations

import math
import shutil
import struct
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import xlrd  # type: ignore[import-untyped]
from xlrd.compdoc import CompDoc  # type: ignore[import-untyped]


BIFF_BLANK = 0x0201
BIFF_BOUNDSHEET = 0x0085
BIFF_COLINFO = 0x007D
BIFF_DBCELL = 0x00D7
BIFF_EOF = 0x000A
BIFF_FORMULA = 0x0006
BIFF_INDEX = 0x020B
BIFF_LABEL = 0x0204
BIFF_LABELSST = 0x00FD
BIFF_MULBLANK = 0x00BE
BIFF_MULRK = 0x00BD
BIFF_NUMBER = 0x0203
BIFF_RK = 0x027E
BIFF_ROW = 0x0208
BIFF_SHRFMLA = 0x04BC
BIFF_STRING = 0x0207
BIFF_SST = 0x00FC
BIFF_CONTINUE = 0x003C
BIFF_EXTSST = 0x00FF
BIFF_XF = 0x00E0

CELL_RECORD_IDS = {
    BIFF_BLANK,
    BIFF_FORMULA,
    BIFF_LABEL,
    BIFF_LABELSST,
    BIFF_NUMBER,
    BIFF_RK,
}

COLUMN_WIDTH_PADDING_CHARS = 2.0
MAX_COLUMN_WIDTH_CHARS = 32.0
MAX_ROW_HEIGHT_TWIPS = 1_920
XLS_COLUMN_WIDTH_UNIT = 256


@dataclass(frozen=True)
class _BiffRecord:
    record_id: int
    payload: bytes

    def to_bytes(self) -> bytes:
        return struct.pack("<HH", self.record_id, len(self.payload)) + self.payload


@dataclass(frozen=True)
class _CellWrite:
    value: str | float | int | None
    display_text: str
    xf_index: int
    needs_wrap: bool


class LegacyXlsTemplateEditor:
    """Patch visible values into a BIFF8 template without rebuilding the workbook.

    xlrd/xlwt-based workbook copies cannot retain formula tokens. This editor keeps
    the original compound document and BIFF records, replacing only explicitly
    written cells plus deterministic ROW/COLINFO dimension records.
    """

    def __init__(
        self,
        template_path: Path,
        *,
        update_dimensions: bool = True,
        sanitize_shared_strings: bool = False,
    ):
        self.template_path = template_path
        self.workbook = xlrd.open_workbook(template_path, formatting_info=True)
        self._writes: dict[int, dict[tuple[int, int], _CellWrite]] = {}
        self._sheet_names: dict[int, str] = {}
        self._retained_sheets: tuple[int, ...] | None = None
        self._update_dimensions = update_dimensions
        self._sanitize_shared_strings = sanitize_shared_strings

    def retain_sheets(self, indexes: tuple[int, ...]) -> None:
        """Keep selected sheets in their original order, preserving their BIFF cells."""
        if not indexes or tuple(sorted(set(indexes))) != indexes or any(
            index < 0 or index >= self.workbook.nsheets for index in indexes
        ):
            raise ValueError("WAGE_TEMPLATE_SHEET_SELECTION_INVALID")
        self._retained_sheets = indexes

    def rename_sheet(self, sheet_index: int, name: str) -> None:
        if not 0 <= sheet_index < self.workbook.nsheets:
            raise ValueError("WAGE_TEMPLATE_SHEET_INDEX_INVALID")
        if not name or len(name) > 31 or any(character in name for character in "[]:*?/\\"):
            raise ValueError("WAGE_TEMPLATE_SHEET_NAME_INVALID")
        existing = {
            self._sheet_names.get(index, sheet_name).casefold()
            for index, sheet_name in enumerate(self.workbook.sheet_names())
            if index != sheet_index
        }
        if name.casefold() in existing:
            raise ValueError("WAGE_TEMPLATE_SHEET_NAME_DUPLICATE")
        self._sheet_names[sheet_index] = name

    def write(
        self,
        sheet_index: int,
        row_index: int,
        column_index: int,
        value: Any,
        *,
        style_xf_index: int | None = None,
    ) -> None:
        sheet = self.workbook.sheet_by_index(sheet_index)
        if row_index >= sheet.nrows or column_index >= sheet.ncols:
            raise ValueError(
                "WAGE_TEMPLATE_STYLE_MISSING: "
                f"{sheet.name}!R{row_index + 1}C{column_index + 1}"
            )

        xf_index = (
            sheet.cell_xf_index(row_index, column_index)
            if style_xf_index is None
            else style_xf_index
        )
        if xf_index is None:
            raise ValueError(
                "WAGE_TEMPLATE_STYLE_MISSING: "
                f"{sheet.name}!R{row_index + 1}C{column_index + 1}"
            )
        if not isinstance(xf_index, int) or not 0 <= xf_index < len(self.workbook.xf_list):
            raise ValueError("WAGE_TEMPLATE_STYLE_OVERRIDE_INVALID")

        normalized = _normalized_cell_value(value)
        display_text = _measurement_text(self.workbook, xf_index, normalized)
        current_width = _column_width(sheet, column_index)
        needs_wrap = _needs_wrap(display_text, current_width)
        self._writes.setdefault(sheet_index, {})[(row_index, column_index)] = (
            _CellWrite(
                value=normalized,
                display_text=display_text,
                xf_index=xf_index,
                needs_wrap=needs_wrap,
            )
        )

    def save(self, output_path: Path) -> None:
        source_bytes = self.template_path.read_bytes()
        compound = CompDoc(source_bytes)
        stream_name = _workbook_stream_name(compound)
        source_stream = compound.get_named_stream(stream_name)
        if source_stream is None:
            raise ValueError("WAGE_TEMPLATE_WORKBOOK_STREAM_MISSING")

        sheet_offsets = _sheet_offsets(source_stream)
        if len(sheet_offsets) != self.workbook.nsheets:
            raise ValueError("WAGE_TEMPLATE_SHEET_DIRECTORY_MISMATCH")

        global_records = _parse_records(source_stream[: sheet_offsets[0]])
        sheet_records = [
            _parse_sheet_records(
                source_stream[offset : sheet_offsets[index + 1]]
                if index + 1 < len(sheet_offsets)
                else source_stream[offset:]
            )
            for index, offset in enumerate(sheet_offsets)
        ]

        width_updates, height_updates = (
            self._dimension_updates() if self._update_dimensions else ({}, {})
        )
        wrap_xf_map = _append_wrapped_xfs(global_records, self.workbook, self._writes)
        _patch_boundsheet_names(global_records, self._sheet_names)
        patched_sheets: list[list[_BiffRecord]] = []
        for sheet_index, records in enumerate(sheet_records):
            writes = {
                coordinate: _CellWrite(
                    value=cell_write.value,
                    display_text=cell_write.display_text,
                    xf_index=wrap_xf_map.get(cell_write.xf_index, cell_write.xf_index)
                    if cell_write.needs_wrap
                    else cell_write.xf_index,
                    needs_wrap=cell_write.needs_wrap,
                )
                for coordinate, cell_write in self._writes.get(sheet_index, {}).items()
            }
            patched_sheets.append(
                _patch_sheet_records(
                    records,
                    writes=writes,
                    width_updates=width_updates.get(sheet_index, {}),
                    height_updates=height_updates.get(sheet_index, {}),
                )
            )

        if self._retained_sheets is not None:
            global_records = _retain_sheet_directory(global_records, self._retained_sheets)
            patched_sheets = [patched_sheets[index] for index in self._retained_sheets]

        if self._sanitize_shared_strings:
            global_records = _without_shared_string_records(global_records)
            for records in patched_sheets:
                if any(record.record_id == BIFF_LABELSST for record in records):
                    raise ValueError("WAGE_TEMPLATE_SENSITIVE_SST_REFERENCE_REMAINS")

        global_size = sum(len(record.to_bytes()) for record in global_records)
        new_offsets: list[int] = []
        next_offset = global_size
        for records in patched_sheets:
            new_offsets.append(next_offset)
            next_offset += sum(len(record.to_bytes()) for record in records)
        _patch_boundsheet_offsets(global_records, new_offsets)

        output_stream = b"".join(record.to_bytes() for record in global_records)
        output_stream += b"".join(
            record.to_bytes() for records in patched_sheets for record in records
        )
        if len(output_stream) > len(source_stream):
            raise ValueError(
                "WAGE_TEMPLATE_WORKBOOK_STREAM_CAPACITY_EXCEEDED: "
                f"{len(output_stream)} > {len(source_stream)}"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.template_path, output_path)
        _replace_compound_stream(
            output_path,
            stream_name=stream_name,
            stream_bytes=output_stream.ljust(len(source_stream), b"\x00"),
        )

        # Reopen before returning so corrupt record offsets never reach a manifest.
        verification = xlrd.open_workbook(output_path, formatting_info=True)
        expected_sheet_names = [
            self._sheet_names.get(index, name)
            for index, name in enumerate(self.workbook.sheet_names())
            if self._retained_sheets is None or index in self._retained_sheets
        ]
        if verification.sheet_names() != expected_sheet_names:
            raise ValueError("WAGE_TEMPLATE_OUTPUT_SHEET_DIRECTORY_MISMATCH")

    def _dimension_updates(
        self,
    ) -> tuple[
        dict[int, dict[int, int]],
        dict[int, dict[int, int]],
    ]:
        width_updates: dict[int, dict[int, int]] = {}
        height_updates: dict[int, dict[int, int]] = {}

        for sheet_index, writes in self._writes.items():
            sheet = self.workbook.sheet_by_index(sheet_index)
            sheet_widths: dict[int, int] = {}
            for (_, column_index), cell_write in writes.items():
                template_width = _column_width(sheet, column_index)
                content_width = max(
                    _display_width(line)
                    for line in _text_lines(cell_write.display_text)
                )
                desired_width = math.ceil(
                    min(
                        content_width + COLUMN_WIDTH_PADDING_CHARS,
                        MAX_COLUMN_WIDTH_CHARS,
                    )
                    * XLS_COLUMN_WIDTH_UNIT
                )
                sheet_widths[column_index] = max(
                    sheet_widths.get(column_index, template_width),
                    template_width,
                    desired_width,
                )
            width_updates[sheet_index] = sheet_widths

            sheet_heights: dict[int, int] = {}
            for (row_index, column_index), cell_write in writes.items():
                template_height = _row_height(sheet, row_index)
                column_width_chars = max(
                    sheet_widths[column_index] / XLS_COLUMN_WIDTH_UNIT
                    - COLUMN_WIDTH_PADDING_CHARS,
                    1.0,
                )
                line_count = sum(
                    max(1, math.ceil(_display_width(line) / column_width_chars))
                    for line in _text_lines(cell_write.display_text)
                )
                desired_height = min(
                    template_height * max(1, line_count),
                    MAX_ROW_HEIGHT_TWIPS,
                )
                sheet_heights[row_index] = max(
                    sheet_heights.get(row_index, template_height),
                    template_height,
                    desired_height,
                )
            height_updates[sheet_index] = sheet_heights

        return width_updates, height_updates


def _retain_sheet_directory(
    records: list[_BiffRecord], retained: tuple[int, ...],
) -> list[_BiffRecord]:
    # MS-XLS BoundSheet8, XTI, Lbl, RRTabId and Window1 use sheet indexes.
    # Keep XTI indexes stable so existing formula tokens need no rewriting.
    mapping = {old: new for new, old in enumerate(retained)}
    internal_books = {
        index for index, record in enumerate(r for r in records if r.record_id == 0x01AE)
        if len(record.payload) >= 4 and record.payload[2:4] == b"\x01\x04"
    }
    output: list[_BiffRecord] = []
    sheet_index = 0
    for record in records:
        payload = bytearray(record.payload)
        if record.record_id == BIFF_BOUNDSHEET:
            keep = sheet_index in mapping
            sheet_index += 1
            if not keep:
                continue
        elif record.record_id == 0x0017:  # ExternSheet / XTI
            count = struct.unpack_from("<H", payload)[0]
            if len(payload) != 2 + 6 * count:
                raise ValueError("WAGE_TEMPLATE_SHEET_REFERENCES_INVALID")
            for offset in range(2, len(payload), 6):
                book, first, last = struct.unpack_from("<Hhh", payload, offset)
                if book in internal_books and first >= 0:
                    remaining = [index for index in retained if first <= index <= last]
                    first, last = ((mapping[remaining[0]], mapping[remaining[-1]])
                                   if remaining else (-1, -1))
                    struct.pack_into("<hh", payload, offset + 2, first, last)
        elif record.record_id == 0x0018:  # Lbl's itab is one-based; zero is global.
            scope = struct.unpack_from("<H", payload, 8)[0]
            if scope:
                if scope - 1 not in mapping:
                    # Approved template only has built-in print names, never names
                    # referenced by cell formulas. Fail closed for other templates.
                    flags = struct.unpack_from("<H", payload)[0]
                    if not flags & 0x20 or payload[15] not in (6, 7, 13):
                        raise ValueError("WAGE_TEMPLATE_UNSUPPORTED_REMOVED_NAME")
                    continue
                struct.pack_into("<H", payload, 8, mapping[scope - 1] + 1)
        elif record.record_id == 0x013D:  # RRTabId: unique stable sheet identifiers.
            ids = list(struct.unpack("<" + "H" * (len(payload) // 2), payload))
            next_id = max(ids, default=0) + 1
            while len(ids) <= max(retained):
                ids.append(next_id)
                next_id += 1
            payload = bytearray(struct.pack("<" + "H" * len(retained), *(ids[i] for i in retained)))
        elif record.record_id == 0x003D:  # Window1 selected/first visible tab.
            for offset in (10, 12):
                old = struct.unpack_from("<H", payload, offset)[0]
                struct.pack_into("<H", payload, offset, mapping.get(old, 0))
            struct.pack_into("<H", payload, 14, 1)
        output.append(_BiffRecord(record.record_id, bytes(payload)))
    return output


def _normalized_cell_value(value: Any) -> str | float | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (float, int, str)):
        return value
    return str(value)


def _text_lines(value: str | float | int | None) -> tuple[str, ...]:
    if value is None:
        return ("",)
    return tuple(str(value).split("\n")) or ("",)


def _measurement_text(
    workbook,
    xf_index: int,
    value: str | float | int | None,
) -> str:
    if value is None:
        return ""
    if isinstance(value, (float, int)):
        format_string = workbook.format_map[
            workbook.xf_list[xf_index].format_key
        ].format_str.lower()
        if 0 <= value < 1 and "h" in format_string and "m" in format_string:
            minutes = round(float(value) * 24 * 60)
            return f"{minutes // 60:02d}:{minutes % 60:02d}"
    return str(value)


def _display_width(value: str) -> float:
    width = 0.0
    for character in value:
        if unicodedata.east_asian_width(character) in {"F", "W"}:
            width += 2.0
        elif unicodedata.combining(character):
            continue
        else:
            width += 1.0
    return width


def _column_width(sheet, column_index: int) -> int:
    column_info = sheet.colinfo_map.get(column_index)
    if column_info is not None:
        return column_info.width
    return sheet.standardwidth or 8 * XLS_COLUMN_WIDTH_UNIT


def _row_height(sheet, row_index: int) -> int:
    row_info = sheet.rowinfo_map.get(row_index)
    if row_info is not None:
        return row_info.height
    return sheet.default_row_height or 255


def _needs_wrap(value: str | float | int | None, current_width: int) -> bool:
    lines = _text_lines(value)
    available_width = max(
        current_width / XLS_COLUMN_WIDTH_UNIT - COLUMN_WIDTH_PADDING_CHARS,
        1.0,
    )
    return len(lines) > 1 or any(_display_width(line) > available_width for line in lines)


def _parse_records(data: bytes) -> list[_BiffRecord]:
    records: list[_BiffRecord] = []
    position = 0
    while position + 4 <= len(data):
        record_id, payload_size = struct.unpack_from("<HH", data, position)
        end = position + 4 + payload_size
        if end > len(data):
            raise ValueError("WAGE_TEMPLATE_BIFF_RECORD_TRUNCATED")
        records.append(_BiffRecord(record_id, data[position + 4 : end]))
        position = end
    return records


def _parse_sheet_records(data: bytes) -> list[_BiffRecord]:
    records: list[_BiffRecord] = []
    position = 0
    while position + 4 <= len(data):
        record_id, payload_size = struct.unpack_from("<HH", data, position)
        end = position + 4 + payload_size
        if end > len(data):
            raise ValueError("WAGE_TEMPLATE_BIFF_SHEET_RECORD_TRUNCATED")
        records.append(_BiffRecord(record_id, data[position + 4 : end]))
        position = end
        if record_id == BIFF_EOF:
            break
    if not records or records[-1].record_id != BIFF_EOF:
        raise ValueError("WAGE_TEMPLATE_BIFF_SHEET_EOF_MISSING")
    return records


def _sheet_offsets(stream: bytes) -> list[int]:
    offsets: list[int] = []
    for record in _parse_records_until_first_sheet(stream):
        if record.record_id == BIFF_BOUNDSHEET:
            offsets.append(struct.unpack_from("<I", record.payload, 0)[0])
    return offsets


def _parse_records_until_first_sheet(stream: bytes) -> list[_BiffRecord]:
    records: list[_BiffRecord] = []
    position = 0
    first_sheet_offset: int | None = None
    while position + 4 <= len(stream):
        if first_sheet_offset is not None and position >= first_sheet_offset:
            break
        record_id, payload_size = struct.unpack_from("<HH", stream, position)
        end = position + 4 + payload_size
        if end > len(stream):
            raise ValueError("WAGE_TEMPLATE_BIFF_GLOBAL_RECORD_TRUNCATED")
        record = _BiffRecord(record_id, stream[position + 4 : end])
        records.append(record)
        if record_id == BIFF_BOUNDSHEET:
            offset = struct.unpack_from("<I", record.payload, 0)[0]
            first_sheet_offset = min(first_sheet_offset or offset, offset)
        position = end
    return records


def _append_wrapped_xfs(
    global_records: list[_BiffRecord],
    workbook,
    writes_by_sheet: dict[int, dict[tuple[int, int], _CellWrite]],
) -> dict[int, int]:
    required_xfs = {
        cell_write.xf_index
        for writes in writes_by_sheet.values()
        for cell_write in writes.values()
        if cell_write.needs_wrap
        and not workbook.xf_list[cell_write.xf_index].alignment.text_wrapped
    }
    if not required_xfs:
        return {}

    xf_positions = [
        index for index, record in enumerate(global_records) if record.record_id == BIFF_XF
    ]
    if len(xf_positions) != len(workbook.xf_list):
        raise ValueError("WAGE_TEMPLATE_XF_DIRECTORY_MISMATCH")

    insert_at = xf_positions[-1] + 1
    wrap_xf_map: dict[int, int] = {}
    for xf_index in sorted(required_xfs):
        source_payload = bytearray(global_records[xf_positions[xf_index]].payload)
        if len(source_payload) < 7:
            raise ValueError("WAGE_TEMPLATE_XF_RECORD_TRUNCATED")
        source_payload[6] |= 0x08
        wrap_xf_map[xf_index] = len(xf_positions) + len(wrap_xf_map)
        global_records.insert(insert_at, _BiffRecord(BIFF_XF, bytes(source_payload)))
        insert_at += 1
    return wrap_xf_map


def _patch_boundsheet_offsets(
    global_records: list[_BiffRecord], offsets: list[int]
) -> None:
    offset_index = 0
    for index, record in enumerate(global_records):
        if record.record_id != BIFF_BOUNDSHEET:
            continue
        payload = bytearray(record.payload)
        struct.pack_into("<I", payload, 0, offsets[offset_index])
        global_records[index] = _BiffRecord(record.record_id, bytes(payload))
        offset_index += 1
    if offset_index != len(offsets):
        raise ValueError("WAGE_TEMPLATE_BOUNDSHEET_COUNT_MISMATCH")


def _patch_boundsheet_names(
    global_records: list[_BiffRecord], names_by_index: dict[int, str]
) -> None:
    sheet_index = 0
    for index, record in enumerate(global_records):
        if record.record_id != BIFF_BOUNDSHEET:
            continue
        if sheet_index not in names_by_index:
            sheet_index += 1
            continue
        name = names_by_index[sheet_index]
        if any(ord(character) > 0xFF for character in name):
            encoded = name.encode("utf-16le")
            option_flags = 0x01
        else:
            encoded = name.encode("latin1")
            option_flags = 0x00
        if len(record.payload) < 8:
            raise ValueError("WAGE_TEMPLATE_BOUNDSHEET_RECORD_TRUNCATED")
        payload = record.payload[:6] + struct.pack("<BB", len(name), option_flags) + encoded
        global_records[index] = _BiffRecord(record.record_id, payload)
        sheet_index += 1
    if sheet_index != len(
        [record for record in global_records if record.record_id == BIFF_BOUNDSHEET]
    ):
        raise ValueError("WAGE_TEMPLATE_BOUNDSHEET_COUNT_MISMATCH")


def _without_shared_string_records(records: list[_BiffRecord]) -> list[_BiffRecord]:
    output: list[_BiffRecord] = []
    skipping_continuations = False
    for record in records:
        if record.record_id == BIFF_SST:
            skipping_continuations = True
            continue
        if skipping_continuations and record.record_id == BIFF_CONTINUE:
            continue
        skipping_continuations = False
        if record.record_id == BIFF_EXTSST:
            continue
        output.append(record)
    return output


def _patch_sheet_records(
    records: list[_BiffRecord],
    *,
    writes: dict[tuple[int, int], _CellWrite],
    width_updates: dict[int, int],
    height_updates: dict[int, int],
) -> list[_BiffRecord]:
    if not writes and not width_updates and not height_updates:
        return records

    patched: list[_BiffRecord] = []
    written_coordinates: set[tuple[int, int]] = set()
    patched_columns: set[int] = set()
    patched_rows: set[int] = set()
    skip_following_string = False

    for record in records:
        if skip_following_string and record.record_id == BIFF_STRING:
            skip_following_string = False
            continue
        skip_following_string = False

        if record.record_id in {BIFF_INDEX, BIFF_DBCELL}:
            continue

        if record.record_id == BIFF_COLINFO:
            split_records, covered_columns = _patch_colinfo_record(
                record, width_updates
            )
            patched.extend(split_records)
            patched_columns.update(covered_columns)
            continue

        if record.record_id == BIFF_ROW and len(record.payload) >= 8:
            row_index = struct.unpack_from("<H", record.payload, 0)[0]
            if row_index in height_updates:
                payload = bytearray(record.payload)
                struct.pack_into("<H", payload, 6, height_updates[row_index])
                record = _BiffRecord(record.record_id, bytes(payload))
                patched_rows.add(row_index)

        coordinate = _single_cell_coordinate(record)
        if coordinate is not None and coordinate in writes:
            patched.append(_cell_record(coordinate, writes[coordinate]))
            written_coordinates.add(coordinate)
            skip_following_string = record.record_id == BIFF_FORMULA
            continue

        if record.record_id in {BIFF_MULBLANK, BIFF_MULRK}:
            replacement_records, replaced = _patch_multi_cell_record(record, writes)
            patched.extend(replacement_records)
            written_coordinates.update(replaced)
            continue

        patched.append(record)

    eof_index = next(
        index for index, record in enumerate(patched) if record.record_id == BIFF_EOF
    )
    for column_index, width in sorted(width_updates.items()):
        if column_index not in patched_columns:
            patched.insert(eof_index, _new_colinfo_record(column_index, width))
            eof_index += 1
    for row_index, height in sorted(height_updates.items()):
        if row_index not in patched_rows:
            patched.insert(eof_index, _new_row_record(row_index, height))
            eof_index += 1
    for coordinate, cell_write in sorted(writes.items()):
        if coordinate not in written_coordinates:
            patched.insert(eof_index, _cell_record(coordinate, cell_write))
            eof_index += 1

    if not any(record.record_id == BIFF_FORMULA for record in patched):
        patched = [record for record in patched if record.record_id != BIFF_SHRFMLA]
    return patched


def _single_cell_coordinate(record: _BiffRecord) -> tuple[int, int] | None:
    if record.record_id not in CELL_RECORD_IDS or len(record.payload) < 6:
        return None
    row_index, column_index = struct.unpack_from("<HH", record.payload, 0)
    return row_index, column_index


def _patch_multi_cell_record(
    record: _BiffRecord,
    writes: dict[tuple[int, int], _CellWrite],
) -> tuple[list[_BiffRecord], set[tuple[int, int]]]:
    if len(record.payload) < 6:
        return [record], set()
    row_index, first_column = struct.unpack_from("<HH", record.payload, 0)
    last_column = struct.unpack_from("<H", record.payload, len(record.payload) - 2)[0]
    coordinates = {
        (row_index, column_index)
        for column_index in range(first_column, last_column + 1)
    }
    replacements = coordinates.intersection(writes)
    if not replacements:
        return [record], set()

    output: list[_BiffRecord] = []
    if record.record_id == BIFF_MULRK:
        for column_index in range(first_column, last_column + 1):
            coordinate = (row_index, column_index)
            offset = 4 + (column_index - first_column) * 6
            xf_index = struct.unpack_from("<H", record.payload, offset)[0]
            if coordinate in writes:
                output.append(_cell_record(coordinate, writes[coordinate]))
            else:
                rk_value = record.payload[offset + 2 : offset + 6]
                payload = struct.pack("<HHH", row_index, column_index, xf_index)
                output.append(_BiffRecord(BIFF_RK, payload + rk_value))
    else:
        for column_index in range(first_column, last_column + 1):
            coordinate = (row_index, column_index)
            offset = 4 + (column_index - first_column) * 2
            xf_index = struct.unpack_from("<H", record.payload, offset)[0]
            if coordinate in writes:
                output.append(_cell_record(coordinate, writes[coordinate]))
            else:
                output.append(
                    _BiffRecord(
                        BIFF_BLANK,
                        struct.pack("<HHH", row_index, column_index, xf_index),
                    )
                )
    return output, replacements


def _cell_record(coordinate: tuple[int, int], cell_write: _CellWrite) -> _BiffRecord:
    row_index, column_index = coordinate
    prefix = struct.pack("<HHH", row_index, column_index, cell_write.xf_index)
    value = cell_write.value
    if value is None or value == "":
        return _BiffRecord(BIFF_BLANK, prefix)
    if isinstance(value, (float, int)):
        return _BiffRecord(BIFF_NUMBER, prefix + struct.pack("<d", float(value)))

    text = str(value)
    if any(ord(character) > 0xFF for character in text):
        encoded = text.encode("utf-16le")
        option_flags = 0x01
    else:
        encoded = text.encode("latin1")
        option_flags = 0x00
    payload = prefix + struct.pack("<HB", len(text), option_flags) + encoded
    return _BiffRecord(BIFF_LABEL, payload)


def _patch_colinfo_record(
    record: _BiffRecord, width_updates: dict[int, int]
) -> tuple[list[_BiffRecord], set[int]]:
    if len(record.payload) < 12:
        return [record], set()
    first_column, last_column, source_width = struct.unpack_from(
        "<HHH", record.payload, 0
    )
    covered_updates = {
        column_index
        for column_index in width_updates
        if first_column <= column_index <= last_column
    }
    if not covered_updates:
        return [record], set()

    output: list[_BiffRecord] = []
    segment_start = first_column
    segment_width = width_updates.get(first_column, source_width)
    for column_index in range(first_column + 1, last_column + 2):
        width = (
            width_updates.get(column_index, source_width)
            if column_index <= last_column
            else None
        )
        if width == segment_width:
            continue
        payload = bytearray(record.payload)
        struct.pack_into("<HHH", payload, 0, segment_start, column_index - 1, segment_width)
        output.append(_BiffRecord(BIFF_COLINFO, bytes(payload)))
        segment_start = column_index
        segment_width = width
    return output, covered_updates


def _new_colinfo_record(column_index: int, width: int) -> _BiffRecord:
    # Default XF 15 and no hidden/outline flags match a normal BIFF8 column.
    payload = struct.pack("<HHHHHH", column_index, column_index, width, 15, 0, 0)
    return _BiffRecord(BIFF_COLINFO, payload)


def _new_row_record(row_index: int, height: int) -> _BiffRecord:
    payload = struct.pack("<HHHHHHHH", row_index, 0, 256, height, 0, 0, 0, 0x0100)
    return _BiffRecord(BIFF_ROW, payload)


def _workbook_stream_name(compound: CompDoc) -> str:
    if compound._dir_search(["Workbook"]) is not None:
        return "Workbook"
    if compound._dir_search(["Book"]) is not None:
        return "Book"
    raise ValueError("WAGE_TEMPLATE_WORKBOOK_STREAM_MISSING")


def _replace_compound_stream(
    output_path: Path,
    *,
    stream_name: str,
    stream_bytes: bytes,
) -> None:
    file_bytes = bytearray(output_path.read_bytes())
    compound = CompDoc(bytes(file_bytes))
    directory = compound._dir_search(stream_name.split("/"))
    if directory is None or directory.tot_size != len(stream_bytes):
        raise ValueError("WAGE_TEMPLATE_WORKBOOK_STREAM_SIZE_MISMATCH")
    if directory.tot_size < compound.min_size_std_stream:
        raise ValueError("WAGE_TEMPLATE_SHORT_WORKBOOK_STREAM_UNSUPPORTED")

    sector_id = directory.first_SID
    stream_position = 0
    while sector_id >= 0 and stream_position < len(stream_bytes):
        chunk = stream_bytes[stream_position : stream_position + compound.sec_size]
        file_offset = 512 + sector_id * compound.sec_size
        file_bytes[file_offset : file_offset + len(chunk)] = chunk
        stream_position += len(chunk)
        sector_id = compound.SAT[sector_id]
    if stream_position != len(stream_bytes):
        raise ValueError("WAGE_TEMPLATE_WORKBOOK_STREAM_CHAIN_TRUNCATED")
    output_path.write_bytes(file_bytes)
