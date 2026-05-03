"""Validate / lint a think-cell `.ppttc` JSON automation file.

The reusable monthly deck factory emits `.ppttc` files (see
``scripts/build_ppttc.py``) that the Windows VM bridge feeds into
``ppttc.exe``. think-cell's ``.ppttc`` format is a top-level array of
template objects:

    [
      {
        "template": "/abs/path/to/template.pptx",
        "data": [
          {"name": "S01_DirectorName",
           "table": [[{"string": "Jesper Tyrer"}]]},
          {"name": "S04_PipeMovement",
           "table": [[null, "Adds", "Outflows"], ["ARR", 1.2, -0.4]]}
        ]
      }
    ]

This module checks that contract structurally and surfaces three classes
of issue the factory has hit before:

* invalid JSON or the wrong shape (array/template/data/name/table),
* duplicate ``name`` entries inside a template (silently lose a binding),
* drift between emitted names and the expected-name manifest baked into
  the wired template (the most common cause of think-cell loading the
  template but applying no data).

The ``ppttc.exe`` runtime tolerates unknown ``name`` entries — it just
ignores them — so an unknown emitted name is treated as a *warning* by
default. ``--strict`` promotes both unknown emitted and missing expected
names to errors.

CLI exit codes are factory-runner friendly: 0 = ok, 2 = errors found,
3 = warnings only and ``--warnings-as-errors``. Validation findings go
to stderr; a one-line summary goes to stdout so a runner can capture it.

The validator never imports Office, the VM bridge, or think-cell.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# Severity vocabulary used by the runner:
ERROR = "error"
WARNING = "warning"

# Known leaf cell tags emitted by build_ppttc._json_cell. Anything else is
# either ``null`` (unset cell) or unknown/malformed and surfaces as an error.
KNOWN_CELL_TAGS = frozenset({"string", "number", "date"})


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    template_index: int | None = None
    template_path: str | None = None
    entry_index: int | None = None
    entry_name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "template_index": self.template_index,
            "template_path": self.template_path,
            "entry_index": self.entry_index,
            "entry_name": self.entry_name,
        }

    def as_line(self) -> str:
        loc = []
        if self.template_index is not None:
            loc.append(f"template[{self.template_index}]")
        if self.entry_index is not None:
            loc.append(f"data[{self.entry_index}]")
        if self.entry_name:
            loc.append(self.entry_name)
        prefix = " ".join(loc) or "(top level)"
        return f"{self.severity.upper()} {self.code} {prefix}: {self.message}"


@dataclass
class TemplateReport:
    template_index: int
    template_path: str | None
    emitted_names: list[str] = field(default_factory=list)
    duplicate_names: list[str] = field(default_factory=list)
    missing_expected_names: list[str] = field(default_factory=list)
    unknown_emitted_names: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    findings: list[Finding] = field(default_factory=list)
    templates: list[TemplateReport] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def emitted_names(self) -> set[str]:
        names: set[str] = set()
        for tmpl in self.templates:
            names.update(tmpl.emitted_names)
        return names

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "thinkcell-ppttc-validation/v1",
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [finding.as_dict() for finding in self.findings],
            "templates": [
                {
                    "template_index": tmpl.template_index,
                    "template_path": tmpl.template_path,
                    "emitted_names": list(tmpl.emitted_names),
                    "duplicate_names": list(tmpl.duplicate_names),
                    "missing_expected_names": list(tmpl.missing_expected_names),
                    "unknown_emitted_names": list(tmpl.unknown_emitted_names),
                }
                for tmpl in self.templates
            ],
        }


def validate_ppttc(
    payload: Any,
    *,
    expected_names: Iterable[str] | None = None,
    strict: bool = False,
) -> ValidationResult:
    """Validate an already-parsed `.ppttc` payload.

    ``expected_names`` is the manifest of named think-cell elements the
    consuming template is known to wire. When supplied, missing entries
    are reported (warning, or error in ``strict``) and emitted names that
    are not in the manifest are surfaced (warning, or error in ``strict``).
    """

    expected = sorted({str(name) for name in expected_names}) if expected_names else None
    drift_severity = ERROR if strict else WARNING
    result = ValidationResult()

    if not isinstance(payload, list):
        result.findings.append(
            Finding(
                ERROR,
                "ppttc.not_array",
                "top-level payload must be a JSON array of template objects",
            )
        )
        return result

    if not payload:
        result.findings.append(
            Finding(
                ERROR,
                "ppttc.empty",
                "top-level array is empty; expected at least one template object",
            )
        )
        return result

    for tmpl_idx, template_obj in enumerate(payload):
        if not isinstance(template_obj, dict):
            result.findings.append(
                Finding(
                    ERROR,
                    "template.not_object",
                    f"template entry must be a JSON object, got {type(template_obj).__name__}",
                    template_index=tmpl_idx,
                )
            )
            continue

        template_path: str | None = None
        if "template" not in template_obj:
            result.findings.append(
                Finding(
                    ERROR,
                    "template.missing_template_key",
                    "template object is missing required 'template' key",
                    template_index=tmpl_idx,
                )
            )
        else:
            template_path_raw = template_obj["template"]
            if not isinstance(template_path_raw, str) or not template_path_raw.strip():
                result.findings.append(
                    Finding(
                        ERROR,
                        "template.invalid_template_value",
                        "'template' must be a non-empty string path",
                        template_index=tmpl_idx,
                    )
                )
            else:
                template_path = template_path_raw

        report = TemplateReport(template_index=tmpl_idx, template_path=template_path)
        result.templates.append(report)

        data = template_obj.get("data")
        if data is None:
            result.findings.append(
                Finding(
                    ERROR,
                    "template.missing_data",
                    "template object is missing required 'data' array",
                    template_index=tmpl_idx,
                    template_path=template_path,
                )
            )
            continue
        if not isinstance(data, list):
            result.findings.append(
                Finding(
                    ERROR,
                    "template.data_not_array",
                    f"'data' must be a JSON array, got {type(data).__name__}",
                    template_index=tmpl_idx,
                    template_path=template_path,
                )
            )
            continue

        seen_counts: dict[str, int] = {}
        for entry_idx, entry in enumerate(data):
            _validate_entry(
                entry,
                entry_idx=entry_idx,
                template_index=tmpl_idx,
                template_path=template_path,
                report=report,
                findings=result.findings,
                seen_counts=seen_counts,
            )

        for name, count in seen_counts.items():
            if count > 1:
                report.duplicate_names.append(name)
                result.findings.append(
                    Finding(
                        ERROR,
                        "data.duplicate_name",
                        f"name '{name}' appears {count} times; later entries silently overwrite earlier ones",
                        template_index=tmpl_idx,
                        template_path=template_path,
                        entry_name=name,
                    )
                )

        if expected is not None:
            emitted_set = set(report.emitted_names)
            missing = sorted(set(expected) - emitted_set)
            unknown = sorted(emitted_set - set(expected))
            report.missing_expected_names = missing
            report.unknown_emitted_names = unknown
            for name in missing:
                result.findings.append(
                    Finding(
                        drift_severity,
                        "manifest.missing_expected_name",
                        f"expected name '{name}' is not emitted in this template",
                        template_index=tmpl_idx,
                        template_path=template_path,
                        entry_name=name,
                    )
                )
            for name in unknown:
                result.findings.append(
                    Finding(
                        drift_severity,
                        "manifest.unknown_emitted_name",
                        f"emitted name '{name}' is not in the expected-name manifest",
                        template_index=tmpl_idx,
                        template_path=template_path,
                        entry_name=name,
                    )
                )

    return result


def _validate_entry(
    entry: Any,
    *,
    entry_idx: int,
    template_index: int,
    template_path: str | None,
    report: TemplateReport,
    findings: list[Finding],
    seen_counts: dict[str, int],
) -> None:
    if not isinstance(entry, dict):
        findings.append(
            Finding(
                ERROR,
                "data.entry_not_object",
                f"data entry must be a JSON object, got {type(entry).__name__}",
                template_index=template_index,
                template_path=template_path,
                entry_index=entry_idx,
            )
        )
        return

    name_raw = entry.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        findings.append(
            Finding(
                ERROR,
                "data.invalid_name",
                "data entry is missing a non-empty string 'name'",
                template_index=template_index,
                template_path=template_path,
                entry_index=entry_idx,
            )
        )
        # Continue: we still want to inspect 'table' so the user gets all
        # findings in one pass.
        name = None
    else:
        name = name_raw
        report.emitted_names.append(name)
        seen_counts[name] = seen_counts.get(name, 0) + 1

    if "table" not in entry:
        findings.append(
            Finding(
                ERROR,
                "data.missing_table",
                "data entry is missing required 'table' array",
                template_index=template_index,
                template_path=template_path,
                entry_index=entry_idx,
                entry_name=name,
            )
        )
        return

    table = entry["table"]
    if not isinstance(table, list):
        findings.append(
            Finding(
                ERROR,
                "data.table_not_array",
                f"'table' must be a JSON array, got {type(table).__name__}",
                template_index=template_index,
                template_path=template_path,
                entry_index=entry_idx,
                entry_name=name,
            )
        )
        return

    for row_idx, row in enumerate(table):
        if not isinstance(row, list):
            findings.append(
                Finding(
                    ERROR,
                    "data.row_not_array",
                    f"row {row_idx} must be a JSON array, got {type(row).__name__}",
                    template_index=template_index,
                    template_path=template_path,
                    entry_index=entry_idx,
                    entry_name=name,
                )
            )
            continue
        for col_idx, cell in enumerate(row):
            if cell is None:
                continue
            if not isinstance(cell, dict):
                findings.append(
                    Finding(
                        ERROR,
                        "data.cell_not_object",
                        f"row {row_idx} col {col_idx} must be null or an object, got {type(cell).__name__}",
                        template_index=template_index,
                        template_path=template_path,
                        entry_index=entry_idx,
                        entry_name=name,
                    )
                )
                continue
            tags = [key for key in cell.keys() if key in KNOWN_CELL_TAGS]
            unknown_tags = [key for key in cell.keys() if key not in KNOWN_CELL_TAGS]
            if not tags:
                findings.append(
                    Finding(
                        ERROR,
                        "data.cell_missing_tag",
                        f"row {row_idx} col {col_idx} cell has no recognized tag (string/number/date)",
                        template_index=template_index,
                        template_path=template_path,
                        entry_index=entry_idx,
                        entry_name=name,
                    )
                )
            elif len(tags) > 1:
                findings.append(
                    Finding(
                        ERROR,
                        "data.cell_multiple_tags",
                        f"row {row_idx} col {col_idx} cell has multiple value tags {sorted(tags)}; expected exactly one",
                        template_index=template_index,
                        template_path=template_path,
                        entry_index=entry_idx,
                        entry_name=name,
                    )
                )
            if unknown_tags:
                findings.append(
                    Finding(
                        WARNING,
                        "data.cell_unknown_tag",
                        f"row {row_idx} col {col_idx} cell has unknown tag(s) {sorted(unknown_tags)}",
                        template_index=template_index,
                        template_path=template_path,
                        entry_index=entry_idx,
                        entry_name=name,
                    )
                )


def load_payload(path: Path) -> Any:
    """Read and parse a `.ppttc` file. Wraps JSON errors in SystemExit."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"{path}: invalid JSON ({exc.msg} at line {exc.lineno} col {exc.colno})"
        ) from exc


def load_expected_names(path: Path) -> list[str]:
    """Load the expected-name manifest from JSON or a newline-delimited file.

    Supported JSON shapes:
        - ["name1", "name2"]
        - {"expected_names": ["name1"]}
        - {"names": ["name1"]}
        - {"chart_names": [...], "text_names": [...], "table_names": [...]}
    """

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to newline-delimited list (one name per line, # comments).
        names: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            names.append(stripped)
        return names

    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    if isinstance(parsed, dict):
        for key in ("expected_names", "names"):
            if isinstance(parsed.get(key), list):
                return [str(item) for item in parsed[key]]
        merged: list[str] = []
        for key in ("chart_names", "text_names", "table_names"):
            value = parsed.get(key)
            if isinstance(value, list):
                merged.extend(str(item) for item in value)
        if merged:
            return merged
    raise SystemExit(f"{path}: cannot extract expected-name list from payload")


def render_findings(result: ValidationResult, *, json_output: bool) -> str:
    if json_output:
        return json.dumps(result.as_dict(), indent=2, ensure_ascii=False)
    if not result.findings:
        return "ok no findings"
    return "\n".join(finding.as_line() for finding in result.findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ppttc", type=Path, help="Path to a `.ppttc` JSON file.")
    parser.add_argument(
        "--expected-names",
        type=Path,
        help=(
            "Optional manifest of expected named think-cell elements "
            "(JSON array, JSON object with 'expected_names'/'names', or "
            "newline-delimited file)."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Promote manifest drift (missing expected names, unknown "
            "emitted names) from warnings to errors."
        ),
    )
    parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="Exit non-zero if any warnings were reported even without errors.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit findings as JSON to stdout instead of a text report on stderr.",
    )
    args = parser.parse_args(argv)

    payload = load_payload(args.ppttc)
    expected_names: list[str] | None = None
    if args.expected_names:
        expected_names = load_expected_names(args.expected_names)

    result = validate_ppttc(payload, expected_names=expected_names, strict=args.strict)

    if args.json:
        print(render_findings(result, json_output=True))
    else:
        if result.findings:
            print(render_findings(result, json_output=False), file=sys.stderr)
        n_templates = len(result.templates)
        n_emitted = sum(len(t.emitted_names) for t in result.templates)
        print(
            f"ppttc={args.ppttc.name} templates={n_templates} names={n_emitted} "
            f"errors={len(result.errors)} warnings={len(result.warnings)} "
            f"ok={'yes' if result.ok else 'no'}"
        )

    if result.errors:
        return 2
    if args.warnings_as_errors and result.warnings:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
