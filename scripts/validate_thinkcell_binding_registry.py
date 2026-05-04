"""Validate a Think-Cell binding registry YAML against schema + cross-rules.

Exit codes:
  0 — valid
  1 — invalid (details to stderr)
  2 — usage error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema
import yaml

REPO = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO / "schemas" / "thinkcell_binding_registry.schema.json"

CHART_KINDS = {"bar_chart", "column_chart", "waterfall_chart", "stacked_bar_chart", "line_chart"}


def _load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def _check_unique_names(registry: dict, errors: list[str]) -> None:
    seen: dict[str, str] = {}
    for slide in registry["slides"]:
        for el in slide.get("elements", []):
            name = el["name"]
            if name in seen:
                errors.append(
                    f"duplicate element name '{name}' on slides {seen[name]} and {slide['slide_id']}"
                )
            else:
                seen[name] = slide["slide_id"]


def _check_lane_kind_consistency(registry: dict, errors: list[str]) -> None:
    for slide in registry["slides"]:
        for el in slide.get("elements", []):
            kind, lane, name = el["kind"], el["lane"], el["name"]
            if kind in CHART_KINDS and lane != "ppttc_chart":
                errors.append(f"{name}: kind '{kind}' must use lane 'ppttc_chart', got '{lane}'")
            if kind == "text" and lane not in {"ppttc_text", "static"}:
                errors.append(
                    f"{name}: kind 'text' must use lane 'ppttc_text' or 'static', got '{lane}'"
                )
            if kind == "table_image" and lane != "excel_table_image":
                errors.append(
                    f"{name}: kind 'table_image' must use lane 'excel_table_image', got '{lane}'"
                )
            if kind == "scalar" and lane != "ppttc_text":
                errors.append(f"{name}: kind 'scalar' must use lane 'ppttc_text', got '{lane}'")


def _check_image_suffix(registry: dict, errors: list[str]) -> None:
    for slide in registry["slides"]:
        for el in slide.get("elements", []):
            if el["kind"] == "table_image" and not el["name"].endswith("_Image"):
                errors.append(f"{el['name']}: table_image elements must end in '_Image' suffix")


def _check_slide_id_matches_name_prefix(registry: dict, errors: list[str]) -> None:
    for slide in registry["slides"]:
        sid = slide["slide_id"]
        for el in slide.get("elements", []):
            if not el["name"].startswith(sid + "_"):
                errors.append(f"{el['name']}: name prefix must match slide_id '{sid}'")


def _check_required_per_analytic_slide(registry: dict, errors: list[str]) -> None:
    """Every non-divider, non-cover, non-closing analytic slide must have a Title and Source.

    Heuristic: any slide whose purpose does not end in 'divider', or whose
    purpose is not 'cover'/'closing', is considered analytic.
    """
    analytic_skip = {"cover", "closing"}
    for slide in registry["slides"]:
        purpose = slide["purpose"]
        if purpose in analytic_skip or purpose.endswith("_divider"):
            continue
        names = {el["name"] for el in slide.get("elements", [])}
        sid = slide["slide_id"]
        if f"{sid}_Title" not in names:
            errors.append(f"{sid} ({purpose}): missing required {sid}_Title")
        if f"{sid}_Source" not in names and not any(
            n.startswith(f"{sid}_") and ("Source" in n or "Footnote" in n) for n in names
        ):
            errors.append(f"{sid} ({purpose}): missing required {sid}_Source / Footnote")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.registry.exists():
        sys.stderr.write(f"registry not found: {args.registry}\n")
        return 2

    schema = json.loads(SCHEMA_PATH.read_text())
    try:
        registry = _load_yaml(args.registry)
    except yaml.YAMLError as exc:
        sys.stderr.write(f"YAML parse error: {exc}\n")
        return 1

    errors: list[str] = []
    try:
        jsonschema.validate(registry, schema)
    except jsonschema.ValidationError as exc:
        errors.append(f"schema: {exc.message} at {list(exc.absolute_path)}")

    if not errors:
        _check_unique_names(registry, errors)
        _check_lane_kind_consistency(registry, errors)
        _check_image_suffix(registry, errors)
        _check_slide_id_matches_name_prefix(registry, errors)
        _check_required_per_analytic_slide(registry, errors)

    if errors:
        for e in errors:
            sys.stderr.write(f"  - {e}\n")
        sys.stderr.write(f"FAIL: {len(errors)} registry error(s)\n")
        return 1

    print(f"OK: {args.registry} ({len(registry['slides'])} slides)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
