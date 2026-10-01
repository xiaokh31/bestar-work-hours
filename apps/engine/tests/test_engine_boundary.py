"""Synthetic integration tests for the standalone public entry point."""

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import xlrd

from bestar_work_hours.cli import main
from bestar_work_hours.hashing import compute_sha256
from bestar_work_hours.serialization import json_ready
from bestar_work_hours.wage import parse_attendance_workbook
from bestar_work_hours.wage.template import WAGE_TEMPLATE_SHA256, default_template_path
from .fixtures import write_attendance


def test_parse_retains_unknown_text_raw_rows_issues_and_month_boundaries(tmp_path: Path):
    source = write_attendance(tmp_path / "synthetic.xls", punches={
        1: "", 2: "08:00", 3: "17:10\n09:00\n17:09",
        4: "17:00\nUNKNOWN-TEXT\n25:61\n08:00",
    })
    parsed = parse_attendance_workbook(source)
    assert parsed.errors == ()
    assert parsed.parserVersion == "wage-attendance-v2"
    assert (parsed.periodStart, parsed.periodEnd) == (date(2026, 6, 1), date(2026, 6, 30))
    assert len(parsed.employees) == 2
    assert len(parsed.days) == 60
    assert parsed.days[0].calculatedHours == 0
    assert parsed.days[0].warnings[0].code == "MISSING_PUNCH_TIMES"
    assert parsed.days[1].warnings[0].code == "ODD_PUNCH_COUNT"
    assert parsed.days[2].calculatedHours == 7.67
    assert parsed.days[3].calculatedHours == 8.5
    assert "UNKNOWN-TEXT" in parsed.days[3].rawCellValues[0]
    payload = json_ready(parsed)
    assert "SYNTHETIC TEST DATA ONLY" in json.dumps(payload["rawRows"])
    assert "UNKNOWN-TEXT" in json.dumps(payload["rawRows"])
    assert payload["days"][2]["workDate"] == "2026-06-03"
    assert payload["days"][2]["workIntervals"][0]["minutes"] == 490


def test_parse_command_records_source_hash_and_never_overwrites(tmp_path: Path):
    source = write_attendance(tmp_path / "synthetic.xls")
    original = source.read_bytes()
    output = tmp_path / "parsed.json"
    assert main(["parse", str(source), "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["sourceSha256"] == compute_sha256(source)
    assert payload["parsedResult"]["rawRows"]
    before = output.read_bytes()
    assert main(["parse", str(source), "--output", str(output)]) == 2
    assert output.read_bytes() == before
    assert main(["parse", str(source), "--output", str(source)]) == 2
    assert source.read_bytes() == original


@pytest.mark.parametrize("filename,content", [
    ("fake.xls", b"not an Excel workbook"), ("wrong.xlsx", b"not an Excel workbook"),
])
def test_invalid_input_reports_error_without_excel_output(tmp_path: Path, filename, content):
    source = tmp_path / filename
    source.write_bytes(content)
    output = tmp_path / "failed"
    assert main(["generate", str(source), "--output-dir", str(output)]) == 2
    assert not list(output.glob("*.xls"))
    report = json.loads((output / "generation.json").read_text(encoding="utf-8"))
    assert report["validated"] is False
    assert report["errors"]
    assert source.read_bytes() == content


def test_generate_command_preserves_original_and_produces_auditable_xls(tmp_path: Path):
    source = write_attendance(tmp_path / "synthetic.xls")
    original = source.read_bytes()
    output = tmp_path / "run-1"
    assert main(["generate", str(source), "--output-dir", str(output)]) == 0
    report = json.loads((output / "generation.json").read_text(encoding="utf-8"))
    assert report["validated"] is True
    assert report["writtenEmployeeCount"] == 2
    assert report["writtenDayCount"] == 60
    generated = output / report["generatedFilename"]
    assert generated.suffix == ".xls"
    assert compute_sha256(generated) == report["outputSha256"]
    manifest = json.loads((output / "wage_record_manifest.json").read_text(encoding="utf-8"))
    assert manifest["records"][0]["sha256"] == report["outputSha256"]
    book = xlrd.open_workbook(generated, formatting_info=True)
    assert book.nsheets == 3
    first = book.sheet_by_name(report["matchedSheets"][0])
    assert first.cell_value(3, 1) == "2026.6.1"
    assert first.cell_value(3, 2) == 8.5
    assert first.cell_value(3, 3) == 0.5
    assert first.cell_value(34, 2) == 255
    assert source.read_bytes() == original
    assert compute_sha256(default_template_path()) == WAGE_TEMPLATE_SHA256
    generated_before = generated.read_bytes()
    assert main(["generate", str(source), "--output-dir", str(output)]) == 2
    assert generated.read_bytes() == generated_before
    assert main(["generate", str(source), "--output-dir", str(tmp_path)]) == 2
    assert source.read_bytes() == original


def test_installed_package_audits_template_outside_checkout(tmp_path: Path):
    # -I discards PYTHONPATH and the working-directory import fallback. This test
    # requires the built wheel (or explicit local installation), not source tricks.
    result = subprocess.run(
        [sys.executable, "-I", "-m", "bestar_work_hours", "inspect-template"],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    audit = json.loads(result.stdout)
    assert audit["sha256"] == WAGE_TEMPLATE_SHA256
    assert audit["formulaCount"] == 284
    assert audit["mergeCount"] == 58
    assert audit["employeeSlotCount"] == 16


def test_sha256_changes_with_content_not_filename(tmp_path: Path):
    first = tmp_path / "first.xls"
    second = tmp_path / "second.xls"
    first.write_bytes(b"abc")
    second.write_bytes(b"abc")
    assert compute_sha256(first) == compute_sha256(second)
    assert compute_sha256(first) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    second.write_bytes(b"abd")
    assert compute_sha256(first) != compute_sha256(second)
