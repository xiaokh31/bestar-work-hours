# Adapted from Bestar stripSystem (Apache-2.0); standalone imports/resources. See NOTICE.
from __future__ import annotations

import json
import os
import shutil
import stat
import struct
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import xlrd  # type: ignore[import-untyped]
import xlwt  # type: ignore[import-untyped]
from xlrd.compdoc import CompDoc  # type: ignore[import-untyped]

from bestar_work_hours.hashing import compute_sha256
from bestar_work_hours.wage.legacy_xls import (
    BIFF_BOUNDSHEET,
    BIFF_CONTINUE,
    BIFF_FORMULA,
    BIFF_LABELSST,
    BIFF_SST,
    BIFF_STRING,
    LegacyXlsTemplateEditor,
    _BiffRecord,
    _parse_records,
    _parse_sheet_records,
    _patch_boundsheet_offsets,
    _replace_compound_stream,
    _sheet_offsets,
    _single_cell_coordinate,
    _workbook_stream_name,
)


WAGE_TEMPLATE_VERSION = "bestar-wage-template-v1"
WAGE_TEMPLATE_FILENAME = f"{WAGE_TEMPLATE_VERSION}.xls"
WAGE_TEMPLATE_SOURCE_SHA256 = (
    "6f2fb31f54e7cca39e696c11e8891f0a6e36041c28b98f1d287f703f9ecf375a"
)
# Updated only when the deterministic, privacy-audited template is intentionally rebuilt.
WAGE_TEMPLATE_SHA256 = (
    "f9e11d6f2c6f45b0453f8346df2ff8347f2e6f5c8b7505a642367f1dade4206c"
)
WAGE_TEMPLATE_SOURCE_SLOT_COUNT = 9
WAGE_TEMPLATE_EMPLOYEE_SLOT_COUNT = 16
WAGE_TEMPLATE_SHEET_COUNT = 17
WAGE_TEMPLATE_FORMULA_COUNT = 284
WAGE_TEMPLATE_MERGE_COUNT = 58
WAGE_TEMPLATE_XF_COUNT = 107
# Versioned semantic roles derived from the approved 2026-05 source workbook.
# Runtime generation verifies that these XFs still differ only by fill before use.
WAGE_TEMPLATE_WEEKDAY_XF_INDEX = 83
WAGE_TEMPLATE_WEEKEND_XF_INDEX = 87

EMPLOYEE_SLOT_PREFIX = "EMPLOYEE-"
ADJUSTMENTS_SHEET_NAME = "ADJUSTMENTS"
WEEKDAY_SLOT = "WEEKDAY_SLOT"
DATE_SLOT = "DATE_SLOT"
IDENTITY_CELL = (0, 0)
BIFF_EXTSST = 0x00FF
STANDARD_HEADERS = (
    "DATE",
    "HOURS",
    "LUNCH HOURS",
    "START TIME",
    "END TIME",
)
WEEKDAY_VALUES = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}

APPROVED_STATIC_LABELS = frozenset(
    {
        "DATE",
        "HOURS",
        "LUNCH HOURS",
        "START TIME",
        "END TIME",
        "TOTAL HOURS",
    }
)


@dataclass(frozen=True)
class WageTemplateAudit:
    version: str
    sha256: str
    sizeBytes: int
    sheetCount: int
    employeeSlotCount: int
    formulaCount: int
    mergeCount: int
    rowInfoCount: int
    colInfoCount: int
    xfCount: int
    nonEmptyCellCount: int
    dateCellCount: int
    unsupportedValueCount: int
    metadataStreamCount: int
    metadataNonZeroByteCount: int
    readable: bool
    readOnly: bool

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class _SourceSheetContract:
    sheetIndex: int
    headerRow: int
    weekdayColumn: int
    columns: dict[str, int]
    dateRows: tuple[int, ...]
    totalRow: int


def default_template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "wage" / WAGE_TEMPLATE_FILENAME


def build_wage_template(*, source_path: Path, output_path: Path) -> WageTemplateAudit:
    if compute_sha256(source_path) != WAGE_TEMPLATE_SOURCE_SHA256:
        raise ValueError("WAGE_TEMPLATE_SOURCE_SHA_MISMATCH")

    workbook = xlrd.open_workbook(source_path, formatting_info=True)
    contracts = _source_contracts(workbook)
    if len(contracts) != WAGE_TEMPLATE_SOURCE_SLOT_COUNT:
        raise ValueError("WAGE_TEMPLATE_SOURCE_SLOT_COUNT_INVALID")
    if workbook.nsheets != WAGE_TEMPLATE_SOURCE_SLOT_COUNT + 1:
        raise ValueError("WAGE_TEMPLATE_SOURCE_SHEET_COUNT_INVALID")

    formula_coordinates = _formula_coordinates(source_path)
    editor = LegacyXlsTemplateEditor(
        source_path,
        update_dimensions=False,
        sanitize_shared_strings=True,
    )
    contract_by_index = {contract.sheetIndex: contract for contract in contracts}
    slot_number = 0

    for sheet_index, sheet in enumerate(workbook.sheets()):
        contract = contract_by_index.get(sheet_index)
        if contract is not None:
            slot_number += 1
            slot_name = employee_slot_name(slot_number)
            editor.rename_sheet(sheet_index, slot_name)
        else:
            slot_name = ADJUSTMENTS_SHEET_NAME
            editor.rename_sheet(sheet_index, slot_name)

        formulas = formula_coordinates[sheet_index]
        for row_index in range(sheet.nrows):
            for column_index in range(sheet.ncols):
                coordinate = (row_index, column_index)
                if coordinate in formulas:
                    continue
                cell = sheet.cell(row_index, column_index)
                if cell.ctype in {xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK}:
                    continue
                value: str | None = None
                normalized = _normalized_header(cell.value)
                if normalized in APPROVED_STATIC_LABELS:
                    value = normalized
                editor.write(sheet_index, row_index, column_index, value)

        editor.write(sheet_index, *IDENTITY_CELL, slot_name)
        if contract is None:
            continue
        for row_index in contract.dateRows:
            editor.write(sheet_index, row_index, contract.weekdayColumn, WEEKDAY_SLOT)
            editor.write(sheet_index, row_index, contract.columns["DATE"], DATE_SLOT)
        editor.write(
            sheet_index,
            contract.totalRow,
            contract.weekdayColumn,
            "TOTAL HOURS",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    editor.save(output_path)
    _remove_historical_biff_payloads(output_path)
    _expand_employee_slots(output_path)
    _zero_document_metadata(output_path)
    os.chmod(output_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    audit = audit_wage_template(output_path)
    _validate_audit(audit, expected_sha256=None, require_read_only=True)
    return audit


def audit_wage_template(path: Path) -> WageTemplateAudit:
    readable = False
    sheet_count = 0
    slot_count = 0
    formula_count = 0
    merge_count = 0
    rowinfo_count = 0
    colinfo_count = 0
    xf_count = 0
    nonempty_count = 0
    date_count = 0
    unsupported_count = 0
    metadata_count = 0
    metadata_nonzero_count = 0

    workbook = xlrd.open_workbook(path, formatting_info=True)
    readable = True
    sheet_count = workbook.nsheets
    xf_count = len(workbook.xf_list)
    expected_names = [
        employee_slot_name(index)
        for index in range(1, WAGE_TEMPLATE_EMPLOYEE_SLOT_COUNT + 1)
    ] + [ADJUSTMENTS_SHEET_NAME]
    if sorted(workbook.sheet_names()) != sorted(expected_names):
        unsupported_count += 1

    formula_coordinates = _formula_coordinates(path)
    formula_count = sum(len(coordinates) for coordinates in formula_coordinates)
    for sheet_index, sheet in enumerate(workbook.sheets()):
        merge_count += len(sheet.merged_cells)
        rowinfo_count += len(sheet.rowinfo_map)
        colinfo_count += len(sheet.colinfo_map)
        if sheet.name.startswith(EMPLOYEE_SLOT_PREFIX):
            slot_count += 1
        formulas = formula_coordinates[sheet_index]
        for row_index in range(sheet.nrows):
            for column_index in range(sheet.ncols):
                cell = sheet.cell(row_index, column_index)
                if cell.ctype in {xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK}:
                    continue
                nonempty_count += 1
                if cell.ctype == xlrd.XL_CELL_DATE:
                    date_count += 1
                coordinate = (row_index, column_index)
                if coordinate in formulas:
                    if cell.value not in (0, 0.0, "", None):
                        unsupported_count += 1
                    continue
                if isinstance(cell.value, str):
                    if not _approved_template_text(cell.value):
                        unsupported_count += 1
                elif cell.value not in (0, 0.0, "", None):
                    unsupported_count += 1

    compound = CompDoc(path.read_bytes())
    for name in ("\x05SummaryInformation", "\x05DocumentSummaryInformation"):
        payload = compound.get_named_stream(name)
        if payload is None:
            continue
        metadata_count += 1
        metadata_nonzero_count += sum(byte != 0 for byte in payload)

    mode = path.stat().st_mode
    return WageTemplateAudit(
        version=WAGE_TEMPLATE_VERSION,
        sha256=compute_sha256(path),
        sizeBytes=path.stat().st_size,
        sheetCount=sheet_count,
        employeeSlotCount=slot_count,
        formulaCount=formula_count,
        mergeCount=merge_count,
        rowInfoCount=rowinfo_count,
        colInfoCount=colinfo_count,
        xfCount=xf_count,
        nonEmptyCellCount=nonempty_count,
        dateCellCount=date_count,
        unsupportedValueCount=unsupported_count,
        metadataStreamCount=metadata_count,
        metadataNonZeroByteCount=metadata_nonzero_count,
        readable=readable,
        readOnly=mode & 0o222 == 0,
    )


def preflight_wage_template(
    path: Path,
    *,
    expected_sha256: str = WAGE_TEMPLATE_SHA256,
    expected_version: str = WAGE_TEMPLATE_VERSION,
    require_read_only: bool = True,
) -> WageTemplateAudit:
    if expected_version != WAGE_TEMPLATE_VERSION:
        raise ValueError("WAGE_TEMPLATE_VERSION_MISMATCH")
    if not path.exists():
        raise ValueError("WAGE_TEMPLATE_MISSING")
    if not path.is_file():
        raise ValueError("WAGE_TEMPLATE_NOT_REGULAR_FILE")
    if path.stat().st_size <= 0:
        raise ValueError("WAGE_TEMPLATE_EMPTY")
    try:
        audit = audit_wage_template(path)
    except Exception as exc:
        raise ValueError("WAGE_TEMPLATE_UNREADABLE") from exc
    _validate_audit(
        audit,
        expected_sha256=expected_sha256,
        require_read_only=require_read_only,
    )
    _validate_weekday_style_contract(path)
    return audit


def employee_slot_name(index: int) -> str:
    return f"{EMPLOYEE_SLOT_PREFIX}{index:02d}"


def _approved_template_text(value: str) -> bool:
    normalized = _normalized_header(value)
    return (
        normalized in APPROVED_STATIC_LABELS
        or normalized in {WEEKDAY_SLOT, DATE_SLOT, ADJUSTMENTS_SHEET_NAME}
        or normalized.startswith(EMPLOYEE_SLOT_PREFIX)
    )


def _normalized_header(value: object) -> str:
    return " ".join(str(value).strip().upper().split())


def _parse_date_slot(value: object, *, cell_type: int, datemode: int) -> date | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        if cell_type != xlrd.XL_CELL_DATE:
            return None
        try:
            return xlrd.xldate_as_datetime(float(value), datemode).date()
        except (OverflowError, TypeError, ValueError):
            return None
    text = str(value).strip()
    for separator in (".", "-", "/"):
        parts = text.split(separator)
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            continue
        try:
            return date(*(int(part) for part in parts))
        except ValueError:
            return None
    return None


def _validate_audit(
    audit: WageTemplateAudit,
    *,
    expected_sha256: str | None,
    require_read_only: bool,
) -> None:
    if expected_sha256 is not None and audit.sha256 != expected_sha256:
        raise ValueError("WAGE_TEMPLATE_SHA_MISMATCH")
    if not audit.readable:
        raise ValueError("WAGE_TEMPLATE_UNREADABLE")
    if audit.sheetCount != WAGE_TEMPLATE_SHEET_COUNT:
        raise ValueError("WAGE_TEMPLATE_SHEET_COUNT_INVALID")
    if audit.employeeSlotCount != WAGE_TEMPLATE_EMPLOYEE_SLOT_COUNT:
        raise ValueError("WAGE_TEMPLATE_EMPLOYEE_SLOT_COUNT_INVALID")
    if audit.formulaCount != WAGE_TEMPLATE_FORMULA_COUNT:
        raise ValueError("WAGE_TEMPLATE_FORMULA_COUNT_INVALID")
    if audit.mergeCount != WAGE_TEMPLATE_MERGE_COUNT:
        raise ValueError("WAGE_TEMPLATE_MERGE_COUNT_INVALID")
    if audit.xfCount != WAGE_TEMPLATE_XF_COUNT:
        raise ValueError("WAGE_TEMPLATE_XF_COUNT_INVALID")
    if audit.dateCellCount != 0 or audit.unsupportedValueCount != 0:
        raise ValueError("WAGE_TEMPLATE_PRIVACY_AUDIT_FAILED")
    if audit.metadataNonZeroByteCount != 0:
        raise ValueError("WAGE_TEMPLATE_METADATA_NOT_CLEARED")
    if require_read_only and not audit.readOnly:
        raise ValueError("WAGE_TEMPLATE_NOT_READ_ONLY")


def _validate_weekday_style_contract(path: Path) -> None:
    workbook = xlrd.open_workbook(path, formatting_info=True)
    expected_xfs = {
        WAGE_TEMPLATE_WEEKDAY_XF_INDEX,
        WAGE_TEMPLATE_WEEKEND_XF_INDEX,
    }
    if not all(0 <= xf_index < len(workbook.xf_list) for xf_index in expected_xfs):
        raise ValueError("WAGE_TEMPLATE_WEEKDAY_STYLE_CONTRACT_OUT_OF_RANGE")
    if (
        _xf_without_fill(workbook, WAGE_TEMPLATE_WEEKDAY_XF_INDEX)
        != _xf_without_fill(workbook, WAGE_TEMPLATE_WEEKEND_XF_INDEX)
        or _xf_fill(workbook, WAGE_TEMPLATE_WEEKDAY_XF_INDEX)
        == _xf_fill(workbook, WAGE_TEMPLATE_WEEKEND_XF_INDEX)
    ):
        raise ValueError("WAGE_TEMPLATE_WEEKDAY_STYLE_CONTRACT_UNSAFE")
    for sheet in workbook.sheets():
        if not sheet.name.startswith(EMPLOYEE_SLOT_PREFIX):
            continue
        actual_xfs = {
            sheet.cell_xf_index(row_index, column_index)
            for row_index in range(sheet.nrows)
            for column_index in range(sheet.ncols)
            if _normalized_header(sheet.cell_value(row_index, column_index))
            == WEEKDAY_SLOT
        }
        if actual_xfs != expected_xfs:
            raise ValueError("WAGE_TEMPLATE_WEEKDAY_STYLE_CONTRACT_MISSING")


def _xf_without_fill(workbook, xf_index: int) -> tuple[object, ...]:
    xf = workbook.xf_list[xf_index]
    font = workbook.font_list[xf.font_index]
    return (
        tuple(sorted((key, value) for key, value in vars(font).items() if key != "font_index")),
        tuple(sorted(vars(xf.border).items())),
        tuple(sorted(vars(xf.alignment).items())),
        tuple(sorted(vars(xf.protection).items())),
        workbook.format_map[xf.format_key].format_str,
    )


def _xf_fill(workbook, xf_index: int) -> tuple[tuple[str, object], ...]:
    return tuple(sorted(vars(workbook.xf_list[xf_index].background).items()))


def _source_contracts(workbook) -> list[_SourceSheetContract]:
    contracts: list[_SourceSheetContract] = []
    for sheet_index, sheet in enumerate(workbook.sheets()):
        contract = _source_contract(sheet, sheet_index, workbook.datemode)
        if contract is not None:
            contracts.append(contract)
    return contracts


def _source_contract(sheet, sheet_index: int, datemode: int) -> _SourceSheetContract | None:
    for header_row in range(sheet.nrows):
        values = [
            _normalized_header(sheet.cell_value(header_row, column_index))
            for column_index in range(sheet.ncols)
        ]
        if not all(values.count(header) == 1 for header in STANDARD_HEADERS):
            continue
        columns = {header: values.index(header) for header in STANDARD_HEADERS}
        weekday_column = columns["DATE"] - 1
        date_rows: list[int] = []
        total_row: int | None = None
        for row_index in range(header_row + 1, sheet.nrows):
            row_values = [
                _normalized_header(sheet.cell_value(row_index, column_index))
                for column_index in range(sheet.ncols)
            ]
            if any(value.startswith("TOTAL HOURS") for value in row_values):
                total_row = row_index
                break
            weekday = _normalized_header(sheet.cell_value(row_index, weekday_column))
            date_cell = sheet.cell(row_index, columns["DATE"])
            if weekday in WEEKDAY_VALUES and _parse_date_slot(
                date_cell.value,
                cell_type=date_cell.ctype,
                datemode=datemode,
            ) is not None:
                date_rows.append(row_index)
        if total_row is None or len(date_rows) != 31:
            raise ValueError("WAGE_TEMPLATE_SOURCE_DATE_GRID_INVALID")
        return _SourceSheetContract(
            sheetIndex=sheet_index,
            headerRow=header_row,
            weekdayColumn=weekday_column,
            columns=columns,
            dateRows=tuple(date_rows),
            totalRow=total_row,
        )
    return None


def _formula_coordinates(path: Path) -> list[set[tuple[int, int]]]:
    source = path.read_bytes()
    compound = CompDoc(source)
    stream = compound.get_named_stream(_workbook_stream_name(compound))
    if stream is None:
        raise ValueError("WAGE_TEMPLATE_WORKBOOK_STREAM_MISSING")
    offsets = _sheet_offsets(stream)
    coordinates: list[set[tuple[int, int]]] = []
    for sheet_index, offset in enumerate(offsets):
        end = offsets[sheet_index + 1] if sheet_index + 1 < len(offsets) else len(stream)
        records = _parse_sheet_records(stream[offset:end])
        coordinates.append(
            {
                coordinate
                for record in records
                if record.record_id == BIFF_FORMULA
                and (coordinate := _single_cell_coordinate(record)) is not None
            }
        )
    return coordinates


def _remove_historical_biff_payloads(path: Path) -> None:
    source = path.read_bytes()
    compound = CompDoc(source)
    stream_name = _workbook_stream_name(compound)
    stream = compound.get_named_stream(stream_name)
    if stream is None:
        raise ValueError("WAGE_TEMPLATE_WORKBOOK_STREAM_MISSING")
    offsets = _sheet_offsets(stream)
    global_records = _parse_records(stream[: offsets[0]])
    sanitized_globals: list[_BiffRecord] = []
    skipping_sst_continuations = False
    for record in global_records:
        if record.record_id == BIFF_SST:
            skipping_sst_continuations = True
            continue
        if skipping_sst_continuations and record.record_id == BIFF_CONTINUE:
            continue
        skipping_sst_continuations = False
        if record.record_id == BIFF_EXTSST:
            continue
        sanitized_globals.append(record)

    sheets: list[list[_BiffRecord]] = []
    for sheet_index, offset in enumerate(offsets):
        end = offsets[sheet_index + 1] if sheet_index + 1 < len(offsets) else len(stream)
        sanitized: list[_BiffRecord] = []
        remove_next_string = False
        for record in _parse_sheet_records(stream[offset:end]):
            if record.record_id == BIFF_LABELSST:
                raise ValueError("WAGE_TEMPLATE_SENSITIVE_SST_REFERENCE_REMAINS")
            if remove_next_string and record.record_id == BIFF_STRING:
                remove_next_string = False
                continue
            remove_next_string = False
            if record.record_id == BIFF_FORMULA:
                if len(record.payload) < 14:
                    raise ValueError("WAGE_TEMPLATE_FORMULA_RECORD_TRUNCATED")
                payload = bytearray(record.payload)
                payload[6:14] = struct.pack("<d", 0.0)
                record = _BiffRecord(record.record_id, bytes(payload))
                remove_next_string = True
            sanitized.append(record)
        sheets.append(sanitized)

    global_size = sum(len(record.to_bytes()) for record in sanitized_globals)
    new_offsets: list[int] = []
    next_offset = global_size
    for records in sheets:
        new_offsets.append(next_offset)
        next_offset += sum(len(record.to_bytes()) for record in records)
    _patch_boundsheet_offsets(sanitized_globals, new_offsets)
    output_stream = b"".join(record.to_bytes() for record in sanitized_globals)
    output_stream += b"".join(
        record.to_bytes() for records in sheets for record in records
    )
    if len(output_stream) > len(stream):
        raise ValueError("WAGE_TEMPLATE_WORKBOOK_STREAM_CAPACITY_EXCEEDED")
    _replace_compound_stream(
        path,
        stream_name=stream_name,
        stream_bytes=output_stream.ljust(len(stream), b"\x00"),
    )


def _expand_employee_slots(path: Path) -> None:
    workbook = xlrd.open_workbook(path, formatting_info=True)
    existing_slot_indexes = [
        index
        for index, name in enumerate(workbook.sheet_names())
        if name.startswith(EMPLOYEE_SLOT_PREFIX)
    ]
    if len(existing_slot_indexes) != WAGE_TEMPLATE_SOURCE_SLOT_COUNT:
        raise ValueError("WAGE_TEMPLATE_SOURCE_SLOT_COUNT_INVALID")
    clone_sheet_index = existing_slot_indexes[-1]

    source = path.read_bytes()
    compound = CompDoc(source)
    stream_name = _workbook_stream_name(compound)
    stream = compound.get_named_stream(stream_name)
    if stream is None:
        raise ValueError("WAGE_TEMPLATE_WORKBOOK_STREAM_MISSING")
    offsets = _sheet_offsets(stream)
    global_records = _parse_records(stream[: offsets[0]])
    sheets = [
        _parse_sheet_records(
            stream[
                offset : offsets[index + 1]
                if index + 1 < len(offsets)
                else len(stream)
            ]
        )
        for index, offset in enumerate(offsets)
    ]
    boundsheets = [
        record for record in global_records if record.record_id == BIFF_BOUNDSHEET
    ]
    clone_boundsheet = boundsheets[clone_sheet_index]
    last_boundsheet_index = max(
        index
        for index, record in enumerate(global_records)
        if record.record_id == BIFF_BOUNDSHEET
    )
    additions = WAGE_TEMPLATE_EMPLOYEE_SLOT_COUNT - len(existing_slot_indexes)
    new_boundsheets = [
        _boundsheet_with_name(
            clone_boundsheet,
            employee_slot_name(WAGE_TEMPLATE_SOURCE_SLOT_COUNT + offset + 1),
        )
        for offset in range(additions)
    ]
    global_records[last_boundsheet_index + 1 : last_boundsheet_index + 1] = (
        new_boundsheets
    )
    sheets.extend([list(sheets[clone_sheet_index]) for _ in range(additions)])

    global_size = sum(len(record.to_bytes()) for record in global_records)
    new_offsets: list[int] = []
    next_offset = global_size
    for records in sheets:
        new_offsets.append(next_offset)
        next_offset += sum(len(record.to_bytes()) for record in records)
    _patch_boundsheet_offsets(global_records, new_offsets)
    expanded_stream = b"".join(record.to_bytes() for record in global_records)
    expanded_stream += b"".join(
        record.to_bytes() for records in sheets for record in records
    )

    with tempfile.TemporaryDirectory(prefix="bestar-wage-template-") as temp_dir:
        carrier_path = Path(temp_dir) / "carrier.xls"
        carrier = xlwt.Workbook()
        for index in range(4):
            sheet = carrier.add_sheet(f"PADDING-{index + 1}")
            sheet.write(0, 0, f"capacity-{index}-" + ("x" * 30_000))
        carrier.save(str(carrier_path))
        carrier_compound = CompDoc(carrier_path.read_bytes())
        carrier_stream_name = _workbook_stream_name(carrier_compound)
        carrier_stream = carrier_compound.get_named_stream(carrier_stream_name)
        if carrier_stream is None or len(carrier_stream) < len(expanded_stream):
            raise ValueError("WAGE_TEMPLATE_WORKBOOK_STREAM_CAPACITY_EXCEEDED")
        shutil.copyfile(carrier_path, path)
        _replace_compound_stream(
            path,
            stream_name=carrier_stream_name,
            stream_bytes=expanded_stream.ljust(len(carrier_stream), b"\x00"),
        )

    verification = xlrd.open_workbook(path, formatting_info=True)
    if verification.nsheets != WAGE_TEMPLATE_SHEET_COUNT:
        raise ValueError("WAGE_TEMPLATE_EXPANDED_SHEET_COUNT_INVALID")


def _boundsheet_with_name(record: _BiffRecord, name: str) -> _BiffRecord:
    encoded = name.encode("latin1")
    if len(record.payload) < 8:
        raise ValueError("WAGE_TEMPLATE_BOUNDSHEET_RECORD_TRUNCATED")
    payload = record.payload[:6] + struct.pack("<BB", len(name), 0) + encoded
    return _BiffRecord(record.record_id, payload)


def _zero_document_metadata(path: Path) -> None:
    for name in ("\x05SummaryInformation", "\x05DocumentSummaryInformation"):
        _zero_compound_stream(path, name)


def _zero_compound_stream(path: Path, name: str) -> None:
    file_bytes = bytearray(path.read_bytes())
    compound = CompDoc(bytes(file_bytes))
    directory = compound._dir_search(name.split("/"))
    if directory is None or directory.tot_size <= 0:
        return
    if directory.tot_size >= compound.min_size_std_stream:
        sector_id = directory.first_SID
        remaining = directory.tot_size
        while sector_id >= 0 and remaining > 0:
            chunk_size = min(compound.sec_size, remaining)
            offset = 512 + sector_id * compound.sec_size
            file_bytes[offset : offset + chunk_size] = b"\x00" * chunk_size
            remaining -= chunk_size
            sector_id = compound.SAT[sector_id]
        if remaining != 0:
            raise ValueError("WAGE_TEMPLATE_METADATA_STREAM_CHAIN_TRUNCATED")
    else:
        short_stream = bytearray(compound.SSCS)
        short_sector_id = directory.first_SID
        remaining = directory.tot_size
        while short_sector_id >= 0 and remaining > 0:
            chunk_size = min(compound.short_sec_size, remaining)
            offset = short_sector_id * compound.short_sec_size
            short_stream[offset : offset + chunk_size] = b"\x00" * chunk_size
            remaining -= chunk_size
            short_sector_id = compound.SSAT[short_sector_id]
        if remaining != 0:
            raise ValueError("WAGE_TEMPLATE_METADATA_SHORT_STREAM_CHAIN_TRUNCATED")
        root = compound.dirlist[0]
        sector_id = root.first_SID
        position = 0
        while sector_id >= 0 and position < len(short_stream):
            chunk = short_stream[position : position + compound.sec_size]
            offset = 512 + sector_id * compound.sec_size
            file_bytes[offset : offset + len(chunk)] = chunk
            position += len(chunk)
            sector_id = compound.SAT[sector_id]
        if position != len(short_stream):
            raise ValueError("WAGE_TEMPLATE_SHORT_STREAM_CONTAINER_TRUNCATED")
    path.write_bytes(file_bytes)


def write_template_manifest(audit: WageTemplateAudit, output_path: Path) -> None:
    payload = {
        "schema_version": 1,
        "template_version": audit.version,
        "template_sha256": audit.sha256,
        "source_reference_sha256": WAGE_TEMPLATE_SOURCE_SHA256,
        "style_contract": {
            "weekday_column": {
                "weekday_xf_index": WAGE_TEMPLATE_WEEKDAY_XF_INDEX,
                "weekend_xf_index": WAGE_TEMPLATE_WEEKEND_XF_INDEX,
            }
        },
        "privacy_contract": {
            "historical_dates": 0,
            "historical_business_values": 0,
            "unapproved_personal_values": 0,
            "metadata_non_zero_bytes": audit.metadataNonZeroByteCount,
        },
        "structure": {
            "sheet_count": audit.sheetCount,
            "employee_slot_count": audit.employeeSlotCount,
            "formula_count": audit.formulaCount,
            "merge_count": audit.mergeCount,
            "rowinfo_count": audit.rowInfoCount,
            "colinfo_count": audit.colInfoCount,
            "xf_count": audit.xfCount,
        },
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
