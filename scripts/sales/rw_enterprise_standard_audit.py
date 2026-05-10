"""RW enterprise Zebra/consultant-grade readiness audit.

This is the top-level gate for the RW dashboard upgrade program. It consolidates
the lower-level gates into one opinionated standard:

- business question and KPI decision contract
- semantic/filter architecture
- source/model/data-surface flow
- unit policy
- visual QA
- Zebra-native visual grammar transfer

The audit is intentionally stricter than "can open in Desktop". A report can be
valid Power BI and still fail this standard if it lacks governed data semantics,
clear executive decision flow, or Zebra/IBCS-derived native visual grammar.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from scripts.sales.rw_compose_all_pages import compose_report
from scripts.sales.rw_dashboard_visual_qa import audit_report as audit_visual_quality
from scripts.sales.rw_data_surface_flow_audit import audit_data_surface_flow
from scripts.sales.rw_page_kpi_contract import PAGE_KPI_CONTRACTS, validate_decision_contracts
from scripts.sales.rw_semantic_filter_audit import SEVERITY_RANK, audit_semantic_filter_flow
from scripts.sales.rw_unit_policy import audit_unit_policy
from scripts.sales.rw_zebra_schema_architecture import build_zebra_schema_benchmark

Severity = Literal["info", "low", "medium", "high", "critical"]

DEFAULT_JSON = Path("output/rw_dashboard_harness/enterprise_standard_audit.json")
DEFAULT_MARKDOWN = Path("docs/sales/RW_ENTERPRISE_ZEBRA_STANDARD.md")
ADDITIONAL_POLISHED_TABS = ("RW KPI Explorer",)

DECISION_VISUAL_TYPES = {
    "card",
    "tableEx",
    "pivotTable",
    "clusteredBarChart",
    "waterfallChart",
}


def _decode_config(visual: dict) -> dict:
    raw = visual.get("config", {})
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {}
    return raw or {}


def _single_visual(visual: dict) -> dict:
    return _decode_config(visual).get("singleVisual", {})


def _visual_type(visual: dict) -> str:
    return str(_single_visual(visual).get("visualType") or "")


def _visual_name(visual: dict) -> str:
    return str(_decode_config(visual).get("name") or "")


def _has_zebra_native_metadata(visual: dict) -> bool:
    objects = _single_visual(visual).get("objects") or {}
    return (
        isinstance(objects, dict)
        and (objects.get("stylePreset") or {}).get("source") == "zebra-visual-dna"
        and (objects.get("zebraGrammar") or {}).get("schema", "").startswith(
            "rw-zebra-native-transfer."
        )
    )


def _finding(
    *,
    finding_id: str,
    severity: Severity,
    lane: str,
    message: str,
    next_action: str,
    page: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": finding_id,
        "severity": severity,
        "lane": lane,
        "message": message,
        "next_action": next_action,
        "evidence": evidence or {},
    }
    if page:
        out["page"] = page
    return out


def _count_findings(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(finding["severity"] for finding in findings)
    return {severity: counts.get(severity, 0) for severity in SEVERITY_RANK}


def _zebra_page_rows(report: dict) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pages = {section.get("displayName"): section for section in report.get("sections", [])}
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    for page in (*PAGE_KPI_CONTRACTS, *ADDITIONAL_POLISHED_TABS):
        section = pages.get(page, {})
        decision_visuals = [
            visual
            for visual in section.get("visualContainers", [])
            if _visual_type(visual) in DECISION_VISUAL_TYPES
        ]
        zebra_visuals = [visual for visual in decision_visuals if _has_zebra_native_metadata(visual)]
        coverage = len(zebra_visuals) / len(decision_visuals) if decision_visuals else 0.0
        rows.append(
            {
                "page": page,
                "decision_visuals": len(decision_visuals),
                "zebra_native_visuals": len(zebra_visuals),
                "zebra_native_coverage": round(coverage, 3),
                "missing_visual_names": [
                    _visual_name(visual) or _visual_type(visual)
                    for visual in decision_visuals
                    if not _has_zebra_native_metadata(visual)
                ],
            }
        )
        if not decision_visuals:
            findings.append(
                _finding(
                    finding_id="zebra_page_has_no_decision_visuals",
                    severity="high",
                    lane="zebra visual grammar",
                    page=page,
                    message=f"{page} has no native decision visuals to evaluate.",
                    next_action="Rebuild the page from the KPI contract before Desktop inspection.",
                )
            )
        elif not zebra_visuals:
            findings.append(
                _finding(
                    finding_id="zebra_native_grammar_absent",
                    severity="high",
                    lane="zebra visual grammar",
                    page=page,
                    message=f"{page} has no Zebra-native lineage on decision visuals.",
                    next_action=(
                        "Apply Zebra-derived native table/card/chart grammar to the page's primary "
                        "decision visual before calling it enterprise-grade."
                    ),
                    evidence={"decision_visuals": len(decision_visuals)},
                )
            )
        elif coverage < 0.9:
            findings.append(
                _finding(
                    finding_id="zebra_native_grammar_partial",
                    severity="medium",
                    lane="zebra visual grammar",
                    page=page,
                    message=f"{page} has incomplete Zebra-native grammar coverage.",
                    next_action="Convert remaining generic decision visuals to Zebra/IBCS native helpers.",
                    evidence={
                        "decision_visuals": len(decision_visuals),
                        "zebra_native_visuals": len(zebra_visuals),
                        "coverage": round(coverage, 3),
                    },
                )
            )

    return rows, findings


def _contract_findings() -> list[dict[str, Any]]:
    return [
        _finding(
            finding_id="decision_contract_error",
            severity="critical",
            lane="consulting decision contract",
            message=error,
            next_action="Fix scripts.sales.rw_page_kpi_contract before changing page visuals.",
        )
        for error in validate_decision_contracts()
    ]


def _gate_findings(
    *,
    visual_qa: dict[str, Any],
    semantic_filter: dict[str, Any],
    unit_policy: dict[str, Any],
    data_surface: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    v_counts = visual_qa["summary"]["severity_counts"]
    if v_counts["critical"] or v_counts["high"] or v_counts["medium"]:
        findings.append(
            _finding(
                finding_id="visual_qa_not_clear",
                severity="high" if v_counts["high"] or v_counts["critical"] else "medium",
                lane="visual surface",
                message=(
                    "Visual QA is not clear at consultant-grade threshold: "
                    + ", ".join(f"{k}={v}" for k, v in v_counts.items())
                ),
                next_action="Resolve visual QA findings before executive inspection.",
            )
        )

    u_counts = unit_policy["counts"]
    if u_counts["critical"] or u_counts["high"]:
        findings.append(
            _finding(
                finding_id="unit_policy_not_clear",
                severity="high",
                lane="unit governance",
                message="Unit policy has high/critical findings.",
                next_action="Keep all monetary values on EUR M and remove visual display-unit scaling.",
                evidence=u_counts,
            )
        )

    s_counts = semantic_filter["counts"]
    if s_counts["critical"] or s_counts["high"]:
        findings.append(
            _finding(
                finding_id="semantic_filter_blocked",
                severity="critical" if s_counts["critical"] else "high",
                lane="semantic/filter architecture",
                message="Semantic/filter flow has high/critical findings.",
                next_action="Fix page filter policy and relationship flow before visual upgrades.",
                evidence=s_counts,
            )
        )
    elif s_counts["medium"]:
        findings.append(
            _finding(
                finding_id="semantic_model_debt",
                severity="medium",
                lane="semantic/filter architecture",
                message="Semantic/filter flow is guarded but still has model debt.",
                next_action="Add d_stage and explicit transition-date roles.",
                evidence=s_counts,
            )
        )

    d_counts = data_surface["summary"]["flow_severity_counts"]
    if d_counts["critical"] or d_counts["high"]:
        findings.append(
            _finding(
                finding_id="kpi_flow_not_enterprise_complete",
                severity="high",
                lane="data-to-surface flow",
                message=(
                    f"Data-surface verdict is {data_surface['summary']['verdict']}; "
                    f"{d_counts['high']} high-impact KPI flows are incomplete."
                ),
                next_action=(
                    "Close or explicitly descope the high-impact KPI flow blockers before production deployment."
                ),
                evidence=d_counts,
            )
        )

    return findings


def _upgrade_backlog(data_surface: dict[str, Any], zebra_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    backlog = [
        {
            "sequence": "1",
            "lane": "semantic spine",
            "work": "Add canonical d_stage plus stage sort/key relationships.",
            "why": "Stage visuals need business-order semantics and reusable stage governance.",
        },
        {
            "sequence": "2",
            "lane": "movement dates",
            "work": "Add stage-transition and forecast-transition date roles.",
            "why": "Close FQ is cohort context; movement-period slicing needs separate transition dates.",
        },
        {
            "sequence": "3",
            "lane": "source data",
            "work": "Stage quota, forecast snapshots, renewal base/indexation, Synergy, and one-off revenue sources.",
            "why": "The remaining high-impact RW KPIs are data/model blockers, not layout blockers.",
        },
    ]
    for row in zebra_rows:
        if row["decision_visuals"] and row["zebra_native_coverage"] < 0.9:
            backlog.append(
                {
                    "sequence": str(len(backlog) + 1),
                    "lane": f"page: {row['page']}",
                    "work": "Rebuild primary visuals with Zebra-native helper grammar and IBCS table/chart ordering.",
                    "why": (
                        f"Current Zebra-native decision-visual coverage is "
                        f"{row['zebra_native_visuals']}/{row['decision_visuals']}."
                    ),
                }
            )

    for item in data_surface["necessary_to_finish"]:
        if item["lane"] in {"unit policy", "semantic model"}:
            continue
        backlog.append(
            {
                "sequence": str(len(backlog) + 1),
                "lane": item["lane"],
                "work": item["need"],
                "why": item["why"],
            }
        )
    return backlog


def _verdict(findings: list[dict[str, Any]]) -> str:
    counts = _count_findings(findings)
    if counts["critical"]:
        return "blocked"
    if counts["high"]:
        return "not_enterprise_ready"
    if counts["medium"]:
        return "enterprise_lab_ready_with_debt"
    return "enterprise_ready"


def audit_enterprise_standard(
    report: dict | None = None,
    model_bim: dict | None = None,
) -> dict[str, Any]:
    report = report or compose_report({"sections": []})
    visual_qa = audit_visual_quality(report)
    semantic_filter = audit_semantic_filter_flow(report=report, model_bim=model_bim)
    unit_policy = audit_unit_policy(report=report, model_bim=model_bim)
    data_surface = audit_data_surface_flow(report=report, model_bim=model_bim)
    zebra_schema = build_zebra_schema_benchmark()
    zebra_rows, zebra_findings = _zebra_page_rows(report)

    findings = (
        _contract_findings()
        + _gate_findings(
            visual_qa=visual_qa,
            semantic_filter=semantic_filter,
            unit_policy=unit_policy,
            data_surface=data_surface,
        )
        + zebra_findings
    )
    counts = _count_findings(findings)
    verdict = _verdict(findings)

    return {
        "schema": "rw-enterprise-zebra-standard.v1",
        "verdict": verdict,
        "counts": counts,
        "summary": {
            "standard": "Zebra-native + consultant-grade + data-engineering governed",
            "visual_qa_counts": visual_qa["summary"]["severity_counts"],
            "semantic_filter_counts": semantic_filter["counts"],
            "unit_policy_counts": unit_policy["counts"],
            "data_surface_verdict": data_surface["summary"]["verdict"],
            "data_surface_flow_counts": data_surface["summary"]["flow_severity_counts"],
            "kpi_rollup": data_surface["summary"]["kpi_rollup"],
            "zebra_schema_summary": zebra_schema["summary"],
        },
        "findings": findings,
        "zebra_native_page_coverage": zebra_rows,
        "upgrade_backlog": _upgrade_backlog(data_surface, zebra_rows),
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = result["summary"]
    rollup = summary["kpi_rollup"]
    lines = [
        "# RW Enterprise Zebra Standard",
        "",
        f"Verdict: `{result['verdict']}`.",
        "",
        "This is the governing standard for getting the RW Power BI dashboard to Zebra-native, consultant-grade, data-engineering quality. It intentionally combines visual polish with semantic and source-data readiness; visual polish alone is not enough.",
        "",
        "## Current State",
        "",
        f"- Visual QA counts: `{summary['visual_qa_counts']}`",
        f"- Unit policy counts: `{summary['unit_policy_counts']}`",
        f"- Semantic/filter counts: `{summary['semantic_filter_counts']}`",
        f"- Data-surface verdict: `{summary['data_surface_verdict']}`",
        f"- KPI rollup: `{rollup['surfaced']}` clean, `{rollup['surfaced_partial']}` partial/proxy, `{rollup['partial_data_or_measure_gap']}` model gaps, `{rollup['source_data_gap']}` source gaps out of `{rollup['total_kpis']}` RW KPIs.",
        f"- Zebra schema benchmark: `{summary['zebra_schema_summary']['template_count']}` templates, `{summary['zebra_schema_summary']['total_relationships']}` relationships, `{summary['zebra_schema_summary']['single_direction_relationships']}` single-direction relationships.",
        "",
        "## Standard",
        "",
        "1. Every page answers one explicit executive question from the KPI contract.",
        "2. ARR and Renewal ACV stay separated; only `Total Open Pipeline Value` may cross motions and it must be labeled.",
        "3. Monetary values use `EUR M`; visual/theme display-unit scaling is forbidden.",
        "4. Executive pages use governed slicers only: Region and Close FQ unless a page-specific contract allows more.",
        "5. Primary decision visuals use Zebra-derived native grammar or a documented native equivalent on every generated tab.",
        "6. Stage, movement-date, forecast, renewal-base, and segmentation semantics exist before the page claims those decisions.",
        "7. Visual QA has zero medium/high/critical findings before Desktop review.",
        "",
        "## Findings",
        "",
        "| Severity | Lane | Page | Finding | Next action |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not result["findings"]:
        lines.append("| `info` | all | - | No enterprise-standard findings. | Keep this gate in the publish path. |")
    for finding in result["findings"]:
        lines.append(
            f"| `{finding['severity']}` | {finding['lane']} | {finding.get('page', '-')} | "
            f"{finding['message']} | {finding['next_action']} |"
        )

    lines += [
        "",
        "## Zebra-Native Page Coverage",
        "",
        "| Page | Decision visuals | Zebra-native visuals | Coverage |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in result["zebra_native_page_coverage"]:
        lines.append(
            f"| {row['page']} | {row['decision_visuals']} | {row['zebra_native_visuals']} | "
            f"{row['zebra_native_coverage']:.0%} |"
        )

    lines += [
        "",
        "## Systematic Upgrade Backlog",
        "",
        "| # | Lane | Work | Why |",
        "| ---: | --- | --- | --- |",
    ]
    for item in result["upgrade_backlog"]:
        lines.append(f"| {item['sequence']} | {item['lane']} | {item['work']} | {item['why']} |")

    lines += [
        "",
        "## Publish Rule",
        "",
        "Do not call the RW dashboard production-ready until this audit returns `enterprise_ready` or the remaining findings are explicitly documented as out of scope for the release.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-json", type=Path)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--fail-on", choices=tuple(SEVERITY_RANK), default="critical")
    args = parser.parse_args()

    report = json.loads(args.report_json.expanduser().read_text()) if args.report_json else None
    result = audit_enterprise_standard(report=report)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    write_markdown(result, args.markdown)
    print(
        "enterprise-standard-audit: "
        f"verdict={result['verdict']} "
        + " ".join(f"{severity}={result['counts'][severity]}" for severity in SEVERITY_RANK)
    )
    print(f"json={args.json}")
    print(f"markdown={args.markdown}")
    threshold = SEVERITY_RANK[args.fail_on]
    blocking = [f for f in result["findings"] if SEVERITY_RANK[f["severity"]] >= threshold]
    if blocking:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
