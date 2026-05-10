"""Audit source -> model -> KPI contract -> BI surface readiness.

This answers the exec-readiness question in operational terms. A KPI is not
"done" just because a card exists; it needs source coverage, a semantic measure,
an explicit page/visual role, and filter behavior that does not contradict the
motion guardrail.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal

from scripts.sales.rw_compose_all_pages import compose_report
from scripts.sales.rw_dashboard_intelligence import build_intelligence_rows, rollup
from scripts.sales.rw_page_kpi_contract import PAGE_KPI_CONTRACTS
from scripts.sales.rw_push_semantic_model import build_model_bim
from scripts.sales.rw_semantic_filter_audit import SEVERITY_RANK, audit_semantic_filter_flow
from scripts.sales.rw_unit_policy import CURRENCY_UNIT_LABEL, audit_unit_policy

Severity = Literal["info", "low", "medium", "high", "critical"]

DEFAULT_JSON = Path("output/rw_dashboard_harness/data_surface_flow_audit.json")
DEFAULT_MARKDOWN = Path("docs/sales/RW_DATA_SURFACE_FLOW_READINESS.md")


def _measure_count(model: dict) -> int:
    return sum(len(table.get("measures", [])) for table in model.get("tables", []))


def _table_names(model: dict) -> list[str]:
    return sorted(str(table.get("name")) for table in model.get("tables", []) if table.get("name"))


def _placement_index() -> dict[str, list[dict[str, str]]]:
    placements: dict[str, list[dict[str, str]]] = {}
    for page, contract in PAGE_KPI_CONTRACTS.items():
        for placement in contract.placements:
            placements.setdefault(placement.kpi_id, []).append(
                {
                    "page": page,
                    "measure": placement.measure,
                    "visual_role": placement.visual_role,
                    "motion_guardrail": placement.motion_guardrail,
                    "data_status": placement.data_status,
                    "label": placement.label,
                }
            )
    return placements


def _semantic_status(model_measures: tuple[str, ...], missing_measures: tuple[str, ...]) -> str:
    if model_measures and not missing_measures:
        return "complete"
    if model_measures and missing_measures:
        return "partial"
    if missing_measures:
        return "missing"
    return "unmapped"


def _surface_status(dashboard_status: str) -> str:
    if dashboard_status == "surfaced":
        return "complete"
    if dashboard_status == "surfaced_partial":
        return "partial_or_proxy"
    if dashboard_status == "model_available_not_surfaced":
        return "not_surfaced"
    return "blocked_upstream"


def _flow_severity(row) -> Severity:
    if row.dashboard_status == "surfaced":
        return "info"
    if row.impact == "HIGH":
        return "high"
    if row.dashboard_status in {"source_data_gap", "partial_data_or_measure_gap"}:
        return "medium"
    return "low"


def _readiness_verdict(counts: dict[str, int], semantic_counts: dict[str, int]) -> str:
    if counts["critical"] or semantic_counts["critical"]:
        return "blocked_by_guardrail"
    if counts["high"] or semantic_counts["high"]:
        return "not_exec_complete"
    if counts["medium"] or semantic_counts["medium"]:
        return "exec_lab_ready_with_model_debt"
    return "exec_complete"


def audit_data_surface_flow(report: dict | None = None, model_bim: dict | None = None) -> dict[str, Any]:
    report = report or compose_report({"sections": []})
    model_bim = model_bim or build_model_bim()
    model = model_bim["model"]
    rows = build_intelligence_rows()
    placements = _placement_index()
    semantic_filter = audit_semantic_filter_flow(report=report, model_bim=model_bim)
    unit_policy = audit_unit_policy(report=report, model_bim=model_bim)

    flow_rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    severity_counts = {severity: 0 for severity in SEVERITY_RANK}
    for row in rows:
        severity = _flow_severity(row)
        severity_counts[severity] += 1
        flow = {
            "kpi_id": row.kpi_id,
            "name": row.name,
            "impact": row.impact,
            "motion_filter": row.motion_filter,
            "source_coverage": row.source_coverage,
            "semantic_status": _semantic_status(row.model_measures, row.missing_measures),
            "surface_status": _surface_status(row.dashboard_status),
            "dashboard_status": row.dashboard_status,
            "pages": list(row.pages),
            "model_measures": list(row.model_measures),
            "missing_measures": list(row.missing_measures),
            "placements": placements.get(row.kpi_id, []),
            "next_action": row.next_action,
            "severity": severity,
        }
        flow_rows.append(flow)
        if severity in {"medium", "high", "critical"}:
            findings.append(
                {
                    "id": f"kpi_flow:{row.kpi_id}",
                    "severity": severity,
                    "kpi_id": row.kpi_id,
                    "message": f"{row.name} is {row.dashboard_status}.",
                    "impact": row.impact,
                    "next_action": row.next_action,
                }
            )

    semantic_counts = semantic_filter["counts"]
    summary = {
        "kpi_rollup": rollup(rows),
        "flow_severity_counts": severity_counts,
        "semantic_filter_counts": semantic_counts,
        "unit_policy_counts": unit_policy["counts"],
        "unit_policy": unit_policy["unit_policy"],
        "model": {
            "table_count": len(model.get("tables", [])),
            "tables": _table_names(model),
            "measure_count": _measure_count(model),
            "relationship_count": len(model.get("relationships", [])),
        },
        "page_contracts": {
            "executive_pages": len(PAGE_KPI_CONTRACTS),
            "contracted_kpi_ids": len(
                {kpi_id for contract in PAGE_KPI_CONTRACTS.values() for kpi_id in contract.kpi_ids}
            ),
        },
    }
    gate_counts = {
        severity: semantic_counts[severity] + unit_policy["counts"][severity]
        for severity in SEVERITY_RANK
    }
    summary["verdict"] = _readiness_verdict(severity_counts, gate_counts)

    return {
        "schema": "rw-data-surface-flow-audit.v1",
        "summary": summary,
        "findings": findings,
        "flow_rows": flow_rows,
        "semantic_filter_findings": semantic_filter["findings"],
        "unit_policy_findings": unit_policy["findings"],
        "necessary_to_finish": necessary_to_finish(),
    }


def necessary_to_finish() -> list[dict[str, str]]:
    return [
        {
            "lane": "unit policy",
            "need": f"Keep every monetary visual on {CURRENCY_UNIT_LABEL}; forbid visual/theme display-unit scaling.",
            "why": "Mixed K/M/MM/BMM labels make executive reads look ungoverned and can double-scale values.",
        },
        {
            "lane": "semantic model",
            "need": "Add canonical d_stage and stage keys/order.",
            "why": "Stage visuals need business-order semantics, not label sorting.",
        },
        {
            "lane": "semantic model",
            "need": "Add transition-date roles for stage and forecast movements.",
            "why": "Close FQ is a cohort selector; it is not the same as movement-period filtering.",
        },
        {
            "lane": "target/plan data",
            "need": "Stage quota/target denominator for Pipeline Coverage Ratio.",
            "why": "Open pipeline numerator is surfaced, but 3x coverage cannot be executive-grade without quota.",
        },
        {
            "lane": "forecast data",
            "need": "Stage ForecastingItem/snapshot history for true forecast accuracy.",
            "why": "Current Forecast page uses slip/upgrade proxies, not accuracy versus submitted forecast.",
        },
        {
            "lane": "approval/process data",
            "need": "Stage Commercial Approval status/date from Apttus or the approved SimCorp source.",
            "why": "Stage 3/approval KPIs are proxy-only without the actual approval event.",
        },
        {
            "lane": "renewal base data",
            "need": "Stage Asset/Subscription base, existing ARR run-rate, and indexation/uplift fields.",
            "why": "Renewal page can show ACV exposure, but not full renewal economics or retained base quality.",
        },
        {
            "lane": "growth segmentation",
            "need": "Stage Axioma/acquired, synergy, SaaS, product/PS, and one-off revenue flags.",
            "why": "Growth Mix is credible for Land/Expand/partner today, but not yet the full RW segmentation agenda.",
        },
        {
            "lane": "BI surface",
            "need": "Add controlled drill paths from Scorecard -> exception ledger -> owner/account/opportunity detail.",
            "why": "The pages answer executive questions, but the action flow is not yet as strong as a boardroom operating review.",
        },
    ]


def write_markdown(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = result["summary"]
    roll = summary["kpi_rollup"]
    lines = [
        "# RW Data-to-Surface Flow Readiness",
        "",
        f"Verdict: `{summary['verdict']}`.",
        "",
        "No, the dashboard is not fully done yet. It is guarded and inspectable, but the data/schema-to-BI flow is not complete enough to call it a finished executive operating system.",
        "",
        "## What We Have",
        "",
        f"- Canonical KPI graph: `{roll['total_kpis']}` RW KPIs.",
        f"- Cleanly surfaced KPIs: `{roll['surfaced']}`.",
        f"- Surfaced partial/proxy KPIs: `{roll['surfaced_partial']}`.",
        f"- Model/measure gaps: `{roll['partial_data_or_measure_gap']}`.",
        f"- Source-data gaps: `{roll['source_data_gap']}`.",
        f"- Semantic model: `{summary['model']['table_count']}` tables, `{summary['model']['measure_count']}` measures, `{summary['model']['relationship_count']}` relationships.",
        f"- Page contract: `{summary['page_contracts']['executive_pages']}` executive pages covering `{summary['page_contracts']['contracted_kpi_ids']}` KPI IDs.",
        f"- Unit policy: `{summary['unit_policy']['currency_unit']}`; visual display-unit scaling is forbidden.",
        "- Guardrails: ARR/Renewal ACV separation, page-specific slicer policy, unit policy, visual QA, semantic-filter audit, Zebra visual/schema benchmarks.",
        "",
        "## What Is Still Necessary",
        "",
        "| Lane | Need | Why |",
        "| --- | --- | --- |",
    ]
    for item in result["necessary_to_finish"]:
        lines.append(f"| {item['lane']} | {item['need']} | {item['why']} |")

    blockers = [row for row in result["flow_rows"] if row["severity"] == "high"]
    medium = [row for row in result["flow_rows"] if row["severity"] == "medium"]
    lines += [
        "",
        "## High-Impact Blockers",
        "",
        "| KPI | Status | Pages | Measures present | Missing | Next action |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in blockers:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row['kpi_id']}`",
                    row["dashboard_status"],
                    ", ".join(row["pages"]) or "-",
                    ", ".join(f"`{m}`" for m in row["model_measures"]) or "-",
                    ", ".join(f"`{m}`" for m in row["missing_measures"]) or "-",
                    row["next_action"],
                ]
            )
            + " |"
        )

    lines += [
        "",
        "## Medium Flow Gaps",
        "",
        "| KPI | Status | Next action |",
        "| --- | --- | --- |",
    ]
    for row in medium:
        lines.append(f"| `{row['kpi_id']}` | {row['dashboard_status']} | {row['next_action']} |")

    lines += [
        "",
        "## Definition Of Done",
        "",
        "1. No critical/high semantic-filter findings.",
        "2. No high-impact RW KPI remains proxy-only unless explicitly descoped in the exec narrative.",
        "3. `d_stage` and transition-date semantics exist before adding richer stage/forecast period flows.",
        "4. Forecast, approval, renewal-base, and growth-segmentation source gaps are either staged or clearly excluded from the dashboard scope.",
        "5. Unit audit has zero high/critical findings; every monetary measure reads in one unit.",
        "6. The BI surface supports an action flow from headline exception to account/opportunity detail without ARR/ACV blending.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--fail-on", choices=tuple(SEVERITY_RANK), default="critical")
    args = parser.parse_args()

    result = audit_data_surface_flow()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    write_markdown(result, args.markdown)
    print(
        "data-surface-flow-audit: "
        f"verdict={result['summary']['verdict']} "
        + " ".join(
            f"{severity}={result['summary']['flow_severity_counts'][severity]}"
            for severity in SEVERITY_RANK
        )
    )
    print(f"json={args.json}")
    print(f"markdown={args.markdown}")
    threshold = SEVERITY_RANK[args.fail_on]
    blocking = [
        finding for finding in result["findings"] if SEVERITY_RANK[finding["severity"]] >= threshold
    ]
    if blocking:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
