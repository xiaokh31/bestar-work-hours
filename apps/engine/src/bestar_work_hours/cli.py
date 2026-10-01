"""Developer entry point; the application HTTP/storage layer is separate work."""

import argparse
import json
import sys
from pathlib import Path

from .hashing import compute_sha256
from .serialization import json_ready
from .wage import generate_wage_record, parse_attendance_workbook
from .wage.template import default_template_path, preflight_wage_template


def _write_json(path: Path, payload: object) -> None:
    # Exclusive creation: never replace an original, template, or previous result.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(json_ready(payload), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bestar work-hours engine developer tools")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect-template", help="Audit the bundled sanitized template")
    parse_command = commands.add_parser("parse", help="Parse a legacy time-clock .xls")
    parse_command.add_argument("source", type=Path)
    parse_command.add_argument("--output", type=Path, required=True, help="New JSON file")
    generate_command = commands.add_parser("generate", help="Generate using the approved template")
    generate_command.add_argument("source", type=Path)
    generate_command.add_argument("--output-dir", type=Path, required=True, help="New directory")
    args = parser.parse_args(argv)

    try:
        if args.command == "inspect-template":
            audit = preflight_wage_template(default_template_path(), require_read_only=False)
            print(json.dumps(audit.to_dict(), indent=2))
            return 0

        source = args.source.resolve(strict=True)
        source_hash = compute_sha256(source)
        parsed = parse_attendance_workbook(source)
        payload = {
            "schemaVersion": 1,
            "sourceFilename": source.name,
            "sourceSha256": source_hash,
            "parsedResult": parsed,
        }
        if args.command == "parse":
            _write_json(args.output, payload)
            return 2 if parsed.errors else 0

        # Each run owns its directory: no input files or other runs can be replaced.
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=False)
        _write_json(output_dir / "attendance.json", payload)
        generated = generate_wage_record(
            attendance_result=parsed,
            template_path=default_template_path(),
            output_dir=output_dir,
        )
        _write_json(output_dir / "generation.json", generated)
        if generated.errors or not generated.validated:
            print(generated.errorCode or "WAGE_GENERATION_FAILED", file=sys.stderr)
            return 2
        print(generated.outputPath)
        return 0
    except (OSError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
