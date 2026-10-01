"""Migrated approved-template audit; historical template rebuild stays external."""
import json
import os
import stat
from pathlib import Path

import pytest

from bestar_work_hours.wage.template import (
    WAGE_TEMPLATE_EMPLOYEE_SLOT_COUNT, WAGE_TEMPLATE_SHA256, WAGE_TEMPLATE_VERSION,
    WAGE_TEMPLATE_WEEKDAY_XF_INDEX, WAGE_TEMPLATE_WEEKEND_XF_INDEX,
    audit_wage_template, default_template_path, preflight_wage_template,
    write_template_manifest,
)


def test_tracked_template_is_privacy_audited_readable_and_versioned() -> None:
    template = default_template_path()
    audit = preflight_wage_template(template, require_read_only=False)

    assert audit.sha256 == WAGE_TEMPLATE_SHA256
    assert audit.version == WAGE_TEMPLATE_VERSION
    assert audit.employeeSlotCount == WAGE_TEMPLATE_EMPLOYEE_SLOT_COUNT
    assert audit.dateCellCount == 0
    assert audit.unsupportedValueCount == 0
    assert audit.metadataNonZeroByteCount == 0
    assert audit.formulaCount > 0
    assert audit.mergeCount > 0



def test_template_preflight_fails_closed_with_stable_codes(tmp_path: Path) -> None:
    missing = tmp_path / "missing.xls"
    with pytest.raises(ValueError, match="^WAGE_TEMPLATE_MISSING$"):
        preflight_wage_template(missing)

    changed = tmp_path / "changed.xls"
    changed.write_bytes(default_template_path().read_bytes() + b"changed")
    os.chmod(changed, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    with pytest.raises(ValueError, match="^WAGE_TEMPLATE_SHA_MISMATCH$"):
        preflight_wage_template(changed)

    writable = tmp_path / "writable.xls"
    writable.write_bytes(default_template_path().read_bytes())
    os.chmod(writable, stat.S_IRUSR | stat.S_IWUSR)
    with pytest.raises(ValueError, match="^WAGE_TEMPLATE_NOT_READ_ONLY$"):
        preflight_wage_template(writable)



def test_template_audit_does_not_need_historical_reference() -> None:
    audit = audit_wage_template(default_template_path())
    assert audit.readable is True
    assert audit.sha256 == WAGE_TEMPLATE_SHA256



def test_tracked_manifest_records_reproducible_weekday_style_roles(
    tmp_path: Path,
) -> None:
    template = default_template_path()
    manifest = template.with_suffix(".json")
    generated_manifest = tmp_path / manifest.name

    write_template_manifest(audit_wage_template(template), generated_manifest)

    assert generated_manifest.read_bytes() == manifest.read_bytes()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["style_contract"]["weekday_column"] == {
        "weekday_xf_index": WAGE_TEMPLATE_WEEKDAY_XF_INDEX,
        "weekend_xf_index": WAGE_TEMPLATE_WEEKEND_XF_INDEX,
    }
