"""RW native visual upgrade audit.

This is an opinionated design-engineering audit, separate from basic visual QA.
Visual QA answers "is anything broken?"  This audit answers "where is the
report still underusing Power BI native/Zebra-derived visual vocabulary?"
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from scripts.sales.rw_compose_all_pages import compose_report

DEFAULT_JSON = Path("output") / "rw_dashboard_harness" / "native_visual_upgrade_audit.json"
DEFAULT_MARKDOWN = Path("docs") / "sales" / "RW_NATIVE_VISUAL_UPGRADE_AUDIT.md"
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
Severity = Literal["info", "low", "medium", "high", "critical"]

VALUE_VISUALS = {"card", "tableEx", "pivotTable", "clusteredBarChart", "waterfallChart"}
HEATMAP_VISUALS = {"tableEx", "pivotTable"}
BRIDGE_CANDIDATE_MEASURES = {
    "Total Open Pipeline ARR",
    "Total Open Pipeline Value",
    "Business At Risk ARR",
    "Total Open Renewal ACV",
}
HEATMAP_CANDIDATE_MEASURES = {
    "Source ARR Won",
    "Source Win Rate",
    "Total Land Won Count",
    "Partner ARR",
    "Partner Pct",
    "Business At Risk ARR",
    "Business At Risk Pct",
    "Existing ARR Run Rate",
    "Existing ARR Expiring In Period",
}


def _generated_at() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _decode_config(vc: dict) -> dict:
    raw = vc.get("config", {})
    if isinstance(raw, str):
        return json.loads(raw) if raw else {}
    return raw or {}


def _single_visual(vc: dict) -> dict:
    return _decode_config(vc).get("singleVisual", {})


def _visual_type(vc: dict) -> str:
    return str(_single_visual(vc).get("visualType") or "")


def _visual_name(vc: dict) -> str:
    return str(_decode_config(vc).get("name") or "")


def _aliases(sv: dict) -> dict[str, str]:
    rows = sv.get("prototypeQuery", {}).get("From", [])
    return {str(row.get("Name")): str(row.get("Entity")) for row in rows}


def _refs(vc: dict) -> list[str]:
    sv = _single_visual(vc)
    aliases = _aliases(sv)
    out: list[str] = []
    for selected in sv.get("prototypeQuery", {}).get("Select", []):
        if "Measure" in selected:
            node = selected["Measure"]
            source = node.get("Expression", {}).get("SourceRef", {}).get("Source")
            out.append(f"M:{aliases.get(str(source), '?')}.{node.get('Property')}")
        elif "Column" in selected:
            node = selected["Column"]
            source = node.get("Expression", {}).get("SourceRef", {}).get("Source")
            out.append(f"C:{aliases.get(str(source), '?')}.{node.get('Property')}")
    return out


def _measure_names(vc: dict) -> set[str]:
    out: set[str] = set()
    for ref in _refs(vc):
        if ref.startswith("M:"):
            out.add(ref.split(".", 1)[1])
    return out


def _column_names(vc: dict) -> set[str]:
    out: set[str] = set()
    for ref in _refs(vc):
        if ref.startswith("C:"):
            out.add(ref.split(".", 1)[1])
    return out


def _titles(vc: dict) -> list[str]:
    props = _single_visual(vc).get("columnProperties", {})
    return [
        str(value.get("displayName"))
        for value in props.values()
        if isinstance(value, dict) and value.get("displayName")
    ]


def _objects(vc: dict) -> dict:
    objects = _single_visual(vc).get("objects") or {}
    return objects if isinstance(objects, dict) else {}


def _has_zebra_metadata(vc: dict) -> bool:
    objects = _objects(vc)
    return (
        (objects.get("stylePreset") or {}).get("source") == "zebra-visual-dna"
        and str((objects.get("zebraGrammar") or {}).get("schema") or "").startswith(
            "rw-zebra-native-transfer."
        )
    )


def _style_pattern(vc: dict) -> str:
    return str((_objects(vc).get("stylePreset") or {}).get("pattern") or "")


def _finding(
    *,
    finding_id: str,
    severity: Severity,
    page: str,
    visual: dict | None,
    message: str,
    recommended_visual: str,
    next_action: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = {
        "id": finding_id,
        "severity": severity,
        "page": page,
        "message": message,
        "recommended_visual": recommended_visual,
        "next_action": next_action,
        "evidence": evidence or {},
    }
    if visual:
        out.update(
            {
                "visual_name": _visual_name(visual),
                "visual_type": _visual_type(visual),
                "visual_label": " | ".join(_titles(visual)),
                "x": visual.get("x"),
                "y": visual.get("y"),
                "width": visual.get("width"),
                "height": visual.get("height"),
            }
        )
    return out


def _page(report: dict, page_name: str) -> dict:
    for section in report.get("sections", []):
        if section.get("displayName") == page_name:
            return section
    return {"displayName": page_name, "visualContainers": []}


def _growth_mix_findings(report: dict) -> list[dict[str, Any]]:
    section = _page(report, "Growth Mix")
    visuals = section.get("visualContainers", [])
    findings: list[dict[str, Any]] = []

    source_heatmaps = [
        visual
        for visual in visuals
        if _visual_type(visual) in HEATMAP_VISUALS
        and {"lead_source", "region"}.issubset(_column_names(visual))
        and {"Source ARR Won", "Source Win Rate"}.issubset(_measure_names(visual))
        and "dataBars" in _objects(visual)
    ]
    if not source_heatmaps:
        findings.append(
            _finding(
                finding_id="growth_mix_missing_source_heatmap",
                severity="high",
                page="Growth Mix",
                visual=None,
                message="Growth Mix does not expose source effectiveness as a source x region heatmap.",
                recommended_visual="tableEx or pivotTable heatmap with dataBars",
                next_action=(
                    "Add Source ARR Won, Source Win Rate, and Land won count by lead source x region."
                ),
                evidence={
                    "required_columns": ["lead_source", "region"],
                    "required_measures": ["Source ARR Won", "Source Win Rate"],
                },
            )
        )

    motion_heatmaps = [
        visual
        for visual in visuals
        if _visual_type(visual) in HEATMAP_VISUALS
        and {"region", "motion_type"}.issubset(_column_names(visual))
        and "Total Open Pipeline ARR" in _measure_names(visual)
        and "dataBars" in _objects(visual)
    ]
    if not motion_heatmaps:
        findings.append(
            _finding(
                finding_id="growth_mix_missing_motion_heatmap",
                severity="medium",
                page="Growth Mix",
                visual=None,
                message="Growth Mix does not show Land and Expand mix as a region x motion heatmap.",
                recommended_visual="tableEx or pivotTable heatmap with dataBars",
                next_action="Add Region x Motion with Open ARR (Land + Expand) and Partner ARR.",
                evidence={
                    "required_columns": ["region", "motion_type"],
                    "required_measure": "Total Open Pipeline ARR",
                },
            )
        )
    return findings


def _visual_findings(report: dict) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for section in report.get("sections", []):
        page = str(section.get("displayName") or section.get("name") or "")
        for visual in section.get("visualContainers", []):
            vt = _visual_type(visual)
            measures = _measure_names(visual)
            objects = _objects(visual)
            if vt == "clusteredBarChart" and measures.intersection(BRIDGE_CANDIDATE_MEASURES):
                findings.append(
                    _finding(
                        finding_id="bar_chart_should_be_bridge_or_heatmap",
                        severity="medium",
                        page=page,
                        visual=visual,
                        message="A bar chart is carrying an executive value decomposition candidate.",
                        recommended_visual="waterfallChart or pivotTable heatmap",
                        next_action="Use a native bridge when explaining contribution; use heatmap when comparing slices.",
                        evidence={"measures": sorted(measures)},
                    )
                )
            if (
                vt in HEATMAP_VISUALS
                and measures.intersection(HEATMAP_CANDIDATE_MEASURES)
                and "dataBars" not in objects
                and _style_pattern(visual) != "detail-ledger"
            ):
                findings.append(
                    _finding(
                        finding_id="matrix_missing_heatmap_encoding",
                        severity="medium",
                        page=page,
                        visual=visual,
                        message="A slice/dice matrix has metric candidates but no heatmap/data-bar encoding.",
                        recommended_visual="tableEx or pivotTable heatmap with dataBars",
                        next_action="Add Zebra-native matrix objects with dataBars for the key metric columns.",
                        evidence={"measures": sorted(measures.intersection(HEATMAP_CANDIDATE_MEASURES))},
                    )
                )
            if vt in VALUE_VISUALS and not _has_zebra_metadata(visual):
                findings.append(
                    _finding(
                        finding_id="decision_visual_missing_zebra_metadata",
                        severity="low",
                        page=page,
                        visual=visual,
                        message="Decision visual is native but does not carry Zebra-derived grammar metadata.",
                        recommended_visual="same native visual with Zebra-native helper objects",
                        next_action="Apply a shared Zebra-native helper if this visual remains in the executive path.",
                        evidence={"visual_type": vt},
                    )
                )
    return findings


def audit_native_visual_upgrades(report: dict | None = None) -> dict[str, Any]:
    report = report if report is not None else compose_report({"sections": []})
    findings = _growth_mix_findings(report) + _visual_findings(report)
    counts = Counter(finding["severity"] for finding in findings)
    severity_counts = {severity: counts.get(severity, 0) for severity in SEVERITY_RANK}
    by_page: dict[str, int] = {}
    for finding in findings:
        by_page[finding["page"]] = by_page.get(finding["page"], 0) + 1
    ranked = sorted(
        findings,
        key=lambda item: (
            -SEVERITY_RANK[item["severity"]],
            item["page"],
            item["id"],
            str(item.get("visual_label") or ""),
        ),
    )
    return {
        "schema": "rw-native-visual-upgrade-audit.v1",
        "generated_at": _generated_at(),
        "summary": {
            "finding_count": len(findings),
            "severity_counts": severity_counts,
            "pages_with_findings": dict(sorted(by_page.items())),
        },
        "findings": ranked,
        "target_visual_vocabulary": [
            {
                "visual": "waterfallChart",
                "use_for": "contribution bridges, gap explanations, renewal-base movement",
            },
            {
                "visual": "tableEx/pivotTable + dataBars",
                "use_for": "product/segment/region/source heatmaps and variance matrices",
            },
            {
                "visual": "tableEx + Zebra detail grammar",
                "use_for": "action ledgers and accountable drill rows",
            },
            {
                "visual": "card + neutral Zebra-native grammar",
                "use_for": "compact KPI spine only; not for explanatory card walls",
            },
        ],
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = result["summary"]["severity_counts"]
    lines = [
        "# RW Native Visual Upgrade Audit",
        "",
        f"Generated: `{result['generated_at']}`",
        "",
        "This audit ranks where the dashboard is still underusing native Power BI/Zebra-derived visual grammar. It is not a basic correctness gate.",
        "",
        "## Summary",
        "",
        f"- Findings: `{result['summary']['finding_count']}`",
        "- Severity: " + ", ".join(f"{k}={v}" for k, v in counts.items()),
        "",
        "## Target Visual Vocabulary",
        "",
        "| Visual | Use for |",
        "| --- | --- |",
    ]
    for row in result["target_visual_vocabulary"]:
        lines.append(f"| `{row['visual']}` | {row['use_for']} |")
    lines.extend(
        [
            "",
            "## Ranked Upgrade Queue",
            "",
            "| Severity | Page | Current visual | Recommended visual | Finding | Next action |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if not result["findings"]:
        lines.append("| `info` | all | - | - | No native visual upgrade findings. | Keep this audit in the publish path. |")
    for finding in result["findings"]:
        current = finding.get("visual_type") or "-"
        label = finding.get("visual_label") or finding.get("visual_name") or ""
        if label:
            current = f"`{current}` - {label}"
        lines.append(
            "| {severity} | {page} | {current} | `{recommended}` | {message} | {next_action} |".format(
                severity=f"`{finding['severity']}`",
                page=finding["page"],
                current=current.replace("|", "\\|"),
                recommended=finding["recommended_visual"],
                message=finding["message"].replace("|", "\\|"),
                next_action=finding["next_action"].replace("|", "\\|"),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--report-json", type=Path, help="Optional report.json path; default uses composed report.")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument(
        "--fail-on",
        choices=tuple(SEVERITY_RANK),
        default="critical",
        help="Exit non-zero when a finding at this severity or higher is present.",
    )
    args = parser.parse_args()

    report = json.loads(args.report_json.expanduser().read_text(encoding="utf-8")) if args.report_json else None
    result = audit_native_visual_upgrades(report)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(result, args.markdown)
    print(
        "native-visual-upgrade-audit: "
        f"findings={result['summary']['finding_count']} "
        + " ".join(
            f"{severity}={result['summary']['severity_counts'][severity]}"
            for severity in SEVERITY_RANK
        )
    )
    threshold = SEVERITY_RANK[args.fail_on]
    blocking = [
        finding
        for finding in result["findings"]
        if SEVERITY_RANK[finding["severity"]] >= threshold
    ]
    raise SystemExit(1 if blocking else 0)


if __name__ == "__main__":
    main()
