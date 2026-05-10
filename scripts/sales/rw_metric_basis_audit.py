"""RW metric-basis label audit.

The dashboard must make the calculation basis visible: ARR versus Renewal ACV,
active-base ARR, cross-motion ARR+ACV, ARR-weighted rates, ACV-weighted rates,
and count-based rates/counts. This gate audits visual display labels, not just
measure definitions, because the ambiguity shows up for executives on the BI
surface.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_REPORT_JSON = (
    Path.home()
    / "Downloads"
    / "rw-pbi-format-lab"
    / "rpt_vp_ops_scorecard_zebra_lab_20260509_pbip"
    / "rpt_vp_ops_scorecard.Report"
    / "report.json"
)
DEFAULT_OUT_DIR = Path("output") / "rw_dashboard_harness"
DEFAULT_MARKDOWN = Path("docs") / "sales" / "RW_METRIC_BASIS_LABELS.md"

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass(frozen=True)
class BasisRule:
    basis: str
    required_groups: tuple[tuple[str, ...], ...]
    severity: str = "medium"


def _tokens(*values: str) -> tuple[str, ...]:
    return tuple(values)


EXACT_RULES: dict[str, BasisRule] = {
    "Total Open Pipeline Value": BasisRule(
        "cross_motion_arr_acv",
        (_tokens("arr+acv", "cross-motion", "cross motion"),),
        "high",
    ),
    "Win Rate ARR": BasisRule("arr_weighted_rate", (_tokens("arr-wtd", "arr weighted"),)),
    "Win Rate Count": BasisRule("count_weighted_rate", (_tokens("count", "count-wtd", "count based"),)),
    "Source Win Rate": BasisRule("count_weighted_rate", (_tokens("count", "count-wtd", "count based"),)),
    "Renewal Retention Pct (Period)": BasisRule("acv_weighted_rate", (_tokens("acv-wtd", "acv weighted"),)),
    "Forecast Slip Pct": BasisRule("count_proxy_rate", (_tokens("count",), _tokens("proxy",))),
    "Forecast Slips": BasisRule("count_proxy", (_tokens("count", "slip"), _tokens("proxy",))),
    "Forecast Upgrades": BasisRule("count", (_tokens("count", "upgrade"),)),
    "Stage Forward Pct (LE)": BasisRule("count_rate_land_expand", (_tokens("count",), _tokens("l+e", "land", "expand"))),
    "Stage Backward Pct (LE)": BasisRule("count_rate_land_expand", (_tokens("count",), _tokens("l+e", "land", "expand"))),
    "Stage 4 Forward Pct": BasisRule("count_rate", (_tokens("count",),)),
    "Commercial Approval Compliance Pct": BasisRule("count_rate", (_tokens("count",),)),
    "Partner Pct": BasisRule("arr_share", (_tokens("arr",),)),
    "PS ARR Attach Pct": BasisRule("acv_arr_ratio", (_tokens("acv",), _tokens("arr",))),
    "SaaS YoY Growth Pct": BasisRule("arr_yoy_rate", (_tokens("arr",), _tokens("yoy",))),
    "Business At Risk Pct": BasisRule("active_base_arr_share", (_tokens("base",),)),
    "Existing ARR Run Rate": BasisRule("active_base_arr", (_tokens("arr",), _tokens("active", "base"))),
    "Existing ARR Expiring In Period": BasisRule("active_base_arr", (_tokens("arr",), _tokens("active", "base"))),
    "Business At Risk ARR": BasisRule("active_base_arr", (_tokens("arr",), _tokens("active", "base"))),
    "Open Land ARR": BasisRule("land_arr", (_tokens("arr",), _tokens("land",))),
    "Open Expand ARR": BasisRule("expand_arr", (_tokens("arr",), _tokens("expand",))),
    "Total Land Won Count": BasisRule("count", (_tokens("count", "deals"), _tokens("land",))),
}

RENEWAL_ACV_RE = re.compile(r"Renewal\s+ACV", re.IGNORECASE)
COUNT_RE = re.compile(r"\b(Count|Slips|Upgrades|Transitions)\b")
DAY_RE = re.compile(r"\b(Days|Remaining)\b")
LAND_EXPAND_ARR_RE = re.compile(r"\bARR\b", re.IGNORECASE)

ACTIVE_BASE_ARR_MEASURES = {
    "Existing ARR Run Rate",
    "Existing ARR Expiring In Period",
    "Business At Risk ARR",
}

LAND_EXPAND_ARR_MEASURES = {
    "Total Closed Won ARR",
    "Total Open Pipeline ARR",
    "Total Closed Lost ARR",
    "Stage 3 Plus ARR",
    "Open Land ARR",
    "Open Expand ARR",
    "Total Land Won ARR",
    "Partner ARR",
    "Cross Sell To Acquired ARR",
    "SaaS ARR",
    "SaaS ARR LY YTD",
    "At Risk Opps ARR",
    "Watch Opps ARR",
    "Exception ARR",
    "Healthy Moves ARR",
    "Stage Moves ARR 1d",
    "Stage Moves ARR 7d",
    "Stage Moves ARR FQTD",
    "Avg Deal Size Won",
}


def _literal_value(node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    value = node.get("expr", {}).get("Literal", {}).get("Value")
    if value is None:
        return node
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("'") and text.endswith("'"):
            return text[1:-1]
    return value


def _find_property(obj: Any, property_name: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == property_name:
                found.append(_literal_value(value))
            found.extend(_find_property(value, property_name))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(_find_property(value, property_name))
    return found


def decode_config(vc: dict) -> dict:
    raw = vc.get("config", {})
    return json.loads(raw) if isinstance(raw, str) and raw else raw or {}


def single_visual(vc: dict) -> dict:
    return decode_config(vc).get("singleVisual", {})


def visual_type(vc: dict) -> str:
    return str(single_visual(vc).get("visualType", ""))


def visual_name(vc: dict) -> str:
    return str(decode_config(vc).get("name") or "")


def display_titles(vc: dict) -> list[str]:
    props = single_visual(vc).get("columnProperties", {})
    titles = [
        str(value.get("displayName"))
        for value in props.values()
        if isinstance(value, dict) and value.get("displayName")
    ]
    titles.extend(str(text) for text in _find_property(single_visual(vc).get("vcObjects", {}), "text") if text)
    return titles


def textbox_text(vc: dict) -> str:
    paragraphs = _find_property(single_visual(vc), "paragraphs")
    chunks: list[str] = []
    for paragraphs_value in paragraphs:
        if not isinstance(paragraphs_value, list):
            continue
        for para in paragraphs_value:
            for run in para.get("textRuns", []):
                chunks.append(str(run.get("value") or ""))
    return "".join(chunks)


def measure_label_pairs(vc: dict) -> list[tuple[str, str]]:
    sv = single_visual(vc)
    props = sv.get("columnProperties", {})
    out: list[tuple[str, str]] = []
    for selected in sv.get("prototypeQuery", {}).get("Select", []):
        measure = selected.get("Measure")
        if not isinstance(measure, dict):
            continue
        query_name = str(selected.get("Name") or "")
        measure_name = str(measure.get("Property") or "")
        label = ""
        if isinstance(props.get(query_name), dict):
            label = str(props[query_name].get("displayName") or "")
        out.append((measure_name, label))
    return out


def rule_for_measure(measure: str) -> BasisRule | None:
    if measure in EXACT_RULES:
        return EXACT_RULES[measure]
    if measure in ACTIVE_BASE_ARR_MEASURES:
        return BasisRule("active_base_arr", (_tokens("arr",), _tokens("active", "base")))
    if RENEWAL_ACV_RE.search(measure):
        return BasisRule("renewal_acv", (_tokens("renewal",), _tokens("acv",)))
    if measure in LAND_EXPAND_ARR_MEASURES:
        return BasisRule("land_expand_arr", (_tokens("arr",), _tokens("l+e", "land", "expand")))
    if COUNT_RE.search(measure):
        return BasisRule("count", (_tokens("count", "opp", "opps", "deal", "deals", "move", "moves", "slip", "upgrade", "transition"),))
    if DAY_RE.search(measure):
        return BasisRule("duration_days", (_tokens("day", "days", "remaining"),), "low")
    if LAND_EXPAND_ARR_RE.search(measure):
        return BasisRule("arr", (_tokens("arr",),))
    return None


def label_satisfies(label: str, rule: BasisRule) -> bool:
    normalized = label.lower().replace("weighted", "weighted")
    return all(any(token in normalized for token in group) for group in rule.required_groups)


def finding(
    *,
    page: str,
    vc: dict,
    measure: str,
    label: str,
    rule: BasisRule,
) -> dict[str, Any]:
    return {
        "id": "ambiguous_metric_basis_label",
        "severity": rule.severity,
        "page": page,
        "visual_name": visual_name(vc),
        "visual_type": visual_type(vc),
        "visual_label": " | ".join(display_titles(vc)) or textbox_text(vc),
        "measure": measure,
        "label": label,
        "basis": rule.basis,
        "required_basis_tokens": [list(group) for group in rule.required_groups],
        "message": f"{measure} is labeled {label!r} without explicit {rule.basis} basis.",
        "next_action": "Use visible labels such as ARR (L+E), renewal ACV, active-base ARR, ARR-wtd, ACV-wtd, or count.",
    }


def audit_metric_basis(report: dict) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    inspected = 0
    for section in report.get("sections", []):
        page = section.get("displayName") or section.get("name") or "Untitled"
        for vc in section.get("visualContainers", []):
            for measure, label in measure_label_pairs(vc):
                rule = rule_for_measure(measure)
                if rule is None:
                    continue
                inspected += 1
                if not label_satisfies(label, rule):
                    findings.append(
                        finding(page=page, vc=vc, measure=measure, label=label, rule=rule)
                    )
    counts = {severity: 0 for severity in SEVERITY_RANK}
    for item in findings:
        counts[item["severity"]] += 1
    return {
        "schema": "rw-metric-basis-audit.v1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "basis_standard": {
            "land_expand_arr": "ARR (L+E), or explicit Land ARR / Expand ARR",
            "renewal_acv": "renewal ACV",
            "active_base_arr": "active-base ARR / base ARR",
            "cross_motion_arr_acv": "ARR+ACV or cross-motion value",
            "weighted_rates": "ARR-wtd / ACV-wtd",
            "count_rates": "count",
        },
        "summary": {
            "inspected_measure_labels": inspected,
            "finding_count": len(findings),
            "severity_counts": counts,
        },
        "findings": sorted(
            findings,
            key=lambda item: (
                -SEVERITY_RANK[item["severity"]],
                item["page"],
                item["measure"],
                item["label"],
            ),
        ),
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = result["summary"]
    lines = [
        "# RW Metric Basis Labels",
        "",
        f"Generated: {result['generated_at']}",
        "",
        "## Basis Standard",
        "",
    ]
    for key, value in result["basis_standard"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- Measure labels inspected: {summary['inspected_measure_labels']}",
            f"- Findings: {summary['finding_count']}",
            "- Severity counts: "
            + ", ".join(f"{severity}={count}" for severity, count in summary["severity_counts"].items()),
            "",
            "## Findings",
            "",
        ]
    )
    if not result["findings"]:
        lines.append("No metric-basis label findings.")
    else:
        lines.extend(["| Severity | Page | Measure | Label | Required basis |", "| --- | --- | --- | --- | --- |"])
        for item in result["findings"]:
            required = "; ".join(" or ".join(group) for group in item["required_basis_tokens"])
            lines.append(
                f"| `{item['severity']}` | {item['page']} | `{item['measure']}` | {item['label']} | {required} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--json", type=Path, default=DEFAULT_OUT_DIR / "metric_basis_audit.json")
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--fail-on", choices=tuple(SEVERITY_RANK), default="medium")
    args = parser.parse_args()

    report = json.loads(args.report_json.expanduser().read_text(encoding="utf-8"))
    result = audit_metric_basis(report)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(result, args.markdown)
    counts = result["summary"]["severity_counts"]
    print(
        "metric-basis-audit: "
        + f"findings={result['summary']['finding_count']} "
        + " ".join(f"{severity}={counts[severity]}" for severity in SEVERITY_RANK)
    )
    threshold = SEVERITY_RANK[args.fail_on]
    if any(SEVERITY_RANK[item["severity"]] >= threshold for item in result["findings"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
