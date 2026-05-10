"""RW dashboard unit policy.

Currency values in the RW dashboard are reported in org reporting currency,
EUR, and shown in millions. Visuals must not apply their own display-unit
scaling on top of semantic-model formats.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Literal

from scripts.sales.rw_push_semantic_model import build_model_bim

Severity = Literal["info", "low", "medium", "high", "critical"]

CURRENCY_UNIT_LABEL = "EUR M"
CURRENCY_M_FORMAT = 'EUR #,0,,.0"M";(EUR #,0,,.0"M");"-"'
COUNT_FORMATS = {"#,0", "0"}
PERCENT_FORMATS = {"0.0%"}
DURATION_FORMATS = {"0", "0.0"}
FORBIDDEN_VISUAL_UNIT_KEYS = {
    "labelDisplayUnits",
    "displayUnits",
    "DisplayUnits",
    "labelPrecision",
}
FORBIDDEN_FORMAT_TOKENS = ("$#", "$", "BMM", "MM", "KM")
VISIBLE_UNIT_PATH_TOKENS = (
    "displayname",
    "format",
    "formatstring",
    "label",
    "labels",
    "title",
    "text",
    "unit",
)
VISIBLE_BAD_UNIT_RE = re.compile(r"(?<![A-Z0-9])(BMM|MM|KM)(?![A-Z0-9])")

DEFAULT_JSON = Path("output/rw_dashboard_harness/unit_policy_audit.json")
DEFAULT_MARKDOWN = Path("docs/sales/RW_UNIT_POLICY.md")


def is_currency_measure(name: str) -> bool:
    normalized = name.lower()
    if any(token in normalized for token in (" pct", " rate", " count", " days", "remaining")):
        return False
    return any(
        token in normalized
        for token in (
            "arr",
            "acv",
            "pipeline value",
            "open pipeline value",
            "deal size",
            "revenue",
            "amount",
        )
    )


def _finding(
    *,
    finding_id: str,
    severity: Severity,
    message: str,
    next_action: str,
    measure: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": finding_id,
        "severity": severity,
        "message": message,
        "next_action": next_action,
    }
    if measure:
        out["measure"] = measure
    return out


def audit_model_units(model_bim: dict | None = None) -> list[dict[str, Any]]:
    model_bim = model_bim or build_model_bim()
    findings: list[dict[str, Any]] = []
    for table in model_bim["model"]["tables"]:
        for measure in table.get("measures", []):
            name = str(measure.get("name") or "")
            fmt = str(measure.get("formatString") or "")
            if is_currency_measure(name):
                if fmt != CURRENCY_M_FORMAT:
                    findings.append(
                        _finding(
                            finding_id="currency_measure_format_mismatch",
                            severity="high",
                            measure=name,
                            message=f"{name} uses {fmt!r}; expected {CURRENCY_M_FORMAT!r}.",
                            next_action=f"Set all currency/ARR/ACV/value measures to {CURRENCY_UNIT_LABEL}.",
                        )
                    )
            elif any(token in fmt for token in ("$", "EUR ", '"M"')):
                findings.append(
                    _finding(
                        finding_id="non_currency_measure_has_currency_unit",
                        severity="high",
                        measure=name,
                        message=f"{name} is not classified as currency but uses {fmt!r}.",
                        next_action="Move currency units only to monetary measures.",
                    )
                )
            if any(token in fmt.upper() for token in FORBIDDEN_FORMAT_TOKENS):
                findings.append(
                    _finding(
                        finding_id="forbidden_unit_token",
                        severity="high",
                        measure=name,
                        message=f"{name} format contains a forbidden unit token: {fmt!r}.",
                        next_action="Use the single RW currency unit policy: EUR M.",
                    )
                )
    return findings


def _walk(obj: Any, path: str = "$"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            current = f"{path}.{key}"
            yield current, key, value
            yield from _walk(value, current)
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            yield from _walk(value, f"{path}[{idx}]")


def _strip_keys(obj: Any, forbidden: set[str]) -> int:
    removed = 0
    if isinstance(obj, dict):
        for key in list(obj):
            if key in forbidden:
                obj.pop(key, None)
                removed += 1
            else:
                removed += _strip_keys(obj[key], forbidden)
    elif isinstance(obj, list):
        for value in obj:
            removed += _strip_keys(value, forbidden)
    return removed


def strip_report_unit_scaling(report: dict) -> int:
    """Remove Power BI visual/theme display-unit overrides in-place."""
    removed = 0
    try:
        report_config = json.loads(report.get("config", "{}"))
    except json.JSONDecodeError:
        report_config = {}
    removed += _strip_keys(report_config, FORBIDDEN_VISUAL_UNIT_KEYS)
    report["config"] = json.dumps(report_config)

    for section in report.get("sections", []):
        for visual in section.get("visualContainers", []):
            try:
                cfg = json.loads(visual.get("config", "{}"))
            except json.JSONDecodeError:
                continue
            stripped = _strip_keys(cfg, FORBIDDEN_VISUAL_UNIT_KEYS)
            if stripped:
                visual["config"] = json.dumps(cfg)
            removed += stripped
            if visual.get("dataTransforms"):
                try:
                    transforms = json.loads(visual["dataTransforms"])
                except json.JSONDecodeError:
                    continue
                stripped = _strip_keys(transforms, FORBIDDEN_VISUAL_UNIT_KEYS)
                if stripped:
                    visual["dataTransforms"] = json.dumps(transforms)
                removed += stripped
    return removed


def _is_visible_text_path(path: str, key: str) -> bool:
    normalized = f"{path}.{key}".lower()
    return any(token in normalized for token in VISIBLE_UNIT_PATH_TOKENS)


def _visible_bad_unit(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    upper = value.upper()
    if "$" in upper:
        return "$"
    match = VISIBLE_BAD_UNIT_RE.search(upper)
    return match.group(1) if match else None


def _audit_visible_unit_text(container: Any, *, scope: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path, key, value in _walk(container):
        if key in FORBIDDEN_VISUAL_UNIT_KEYS:
            continue
        if not _is_visible_text_path(path, str(key)):
            continue
        bad_unit = _visible_bad_unit(value)
        if bad_unit:
            findings.append(
                _finding(
                    finding_id="report_forbidden_unit_token",
                    severity="high",
                    message=f"{scope} contains visible unit token {bad_unit!r} at {path}.",
                    next_action="Use EUR M labels/formats and remove K/MM/BMM/$ visual text.",
                )
            )
    return findings


def audit_report_units(report: dict) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    try:
        report_config = json.loads(report.get("config", "{}"))
    except json.JSONDecodeError:
        report_config = {}
    findings.extend(_audit_visible_unit_text(report_config, scope="Report theme"))
    for path, key, _value in _walk(report_config):
        if key in FORBIDDEN_VISUAL_UNIT_KEYS:
            findings.append(
                _finding(
                    finding_id="theme_visual_unit_scaling",
                    severity="high",
                    message=f"Report theme contains visual unit override {key!r} at {path}.",
                    next_action="Remove visual-level display unit overrides from the report theme.",
                )
            )
    for section in report.get("sections", []):
        page = section.get("displayName") or section.get("name") or ""
        for vc in section.get("visualContainers", []):
            try:
                cfg = json.loads(vc.get("config", "{}"))
            except json.JSONDecodeError:
                continue
            visual_name = cfg.get("name", "")
            findings.extend(
                _audit_visible_unit_text(cfg, scope=f"{page}/{visual_name or 'visual'}")
            )
            for path, key, _value in _walk(cfg):
                if key in FORBIDDEN_VISUAL_UNIT_KEYS:
                    findings.append(
                        _finding(
                            finding_id="visual_unit_scaling",
                            severity="high",
                            message=f"{page}/{visual_name} contains visual unit override {key!r} at {path}.",
                            next_action="Remove visual-level display unit overrides and rely on semantic model EUR M formats.",
                        )
                    )
    return findings


def audit_unit_policy(report: dict | None = None, model_bim: dict | None = None) -> dict[str, Any]:
    findings = audit_model_units(model_bim)
    if report is not None:
        findings.extend(audit_report_units(report))
    counts = {"info": 0, "low": 0, "medium": 0, "high": 0, "critical": 0}
    for finding in findings:
        counts[finding["severity"]] += 1
    return {
        "schema": "rw-unit-policy-audit.v1",
        "unit_policy": {
            "currency_unit": CURRENCY_UNIT_LABEL,
            "currency_format": CURRENCY_M_FORMAT,
            "visual_display_units": "forbidden",
        },
        "counts": counts,
        "findings": findings,
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    policy = result["unit_policy"]
    lines = [
        "# RW Unit Policy",
        "",
        f"- Currency unit: `{policy['currency_unit']}`",
        f"- Semantic format: `{policy['currency_format']}`",
        "- Visual/theme display-unit scaling: forbidden",
        "- Count format: `#,0`",
        "- Percent format: `0.0%`",
        "- Day/duration format: `0.0` where decimal precision is useful, otherwise `0`.",
        "",
        "## Findings",
        "",
        "| Severity | Finding | Next action |",
        "| --- | --- | --- |",
    ]
    if not result["findings"]:
        lines.append("| `info` | No unit policy findings. | Keep the unit audit in the publish gate. |")
    for finding in result["findings"]:
        lines.append(
            f"| `{finding['severity']}` | {finding['message']} | {finding['next_action']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--fail-on-high", action="store_true")
    args = parser.parse_args()

    report = json.loads(args.report_json.expanduser().read_text()) if args.report_json else None
    result = audit_unit_policy(report=report)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    write_markdown(result, args.markdown)
    print(
        "unit-policy-audit: "
        + " ".join(f"{severity}={result['counts'][severity]}" for severity in result["counts"])
    )
    print(f"json={args.json}")
    print(f"markdown={args.markdown}")
    if args.fail_on_high and (result["counts"]["high"] or result["counts"]["critical"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
