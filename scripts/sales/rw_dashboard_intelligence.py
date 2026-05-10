"""RW dashboard KPI intelligence matrix.

This bridges the canonical 31-KPI graph to the actual Power BI page contract.
It answers three practical questions:

1. Which RW KPIs are surfaced on dashboard pages today?
2. Which KPIs are model-available but not yet surfaced clearly?
3. Which KPIs need new source data before a consultant-grade visual can exist?
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.sales.rw_kpi_graph import GRAPH, SalesKPI
from scripts.sales.rw_page_kpi_contract import PAGE_KPI_CONTRACTS, target_map_as_dict
from scripts.sales.rw_push_semantic_model import build_model_bim


DEFAULT_OUT = Path("docs/sales/RW_DASHBOARD_KPI_INTELLIGENCE.md")


KPI_MEASURE_HINTS: dict[str, tuple[str, ...]] = {
    "forecast_closed_won": ("Total Closed Won ARR", "Closed Won ARR YoY Pct"),
    "pipeline_coverage_3x": ("Total Open Pipeline ARR", "Pipeline Coverage Ratio"),
    "opp_win_rate": ("Win Rate ARR", "Win Rate Count"),
    "stage_conversion": ("Stage Forward Pct (LE)", "Stage Backward Pct (LE)"),
    "opp_age": ("Avg Open Opp Age Days",),
    "opp_source_effectiveness": ("Source ARR Won", "Source Win Rate"),
    "sales_cycle_length": ("Avg Sales Cycle Days", "Land Avg Sales Cycle Days"),
    "time_in_stage": ("Avg Days In Prior Stage (LE)",),
    "closed_won_avg_deal_size": ("Avg Deal Size Won",),
    "new_opps_by_region": ("New Opps Created", "New Opps Count 7d"),
    "stage3_approvals_compliance": (
        "Commercial Approval Compliance Pct",
        "Stage 3 Forward Pct",
        "Avg Days In Stage 3",
    ),
    "stage3_acv_value": ("Stage 3 Plus ARR", "S3 Plus Open ACV"),
    "commercial_approval_to_close_time": ("Commercial Approval To Close Days",),
    "forecast_accuracy": (
        "Forecast Accuracy",
        "Forecast Slip Pct",
        "Forecast Slips",
        "Forecast Upgrades",
    ),
    "partner_opps_pct": ("Partner ARR", "Partner Pct"),
    "renewal_retention_rate": ("Renewal Retention Pct (Period)",),
    "renewals_mom_trend": ("Total Open Renewal ACV", "Total Renewal ACV Won"),
    "existing_arr_run_rate": ("Existing ARR Run Rate",),
    "indexation_arr_growth": ("Indexation ARR Growth",),
    "ilf_arr_pipeline": ("Open Expand ARR",),
    "alf_arr_pipeline": ("Open Land ARR",),
    "new_customer_reporting": ("Total Land Won Count", "Total Land Won ARR"),
    "cross_sell_to_acquired": ("Cross Sell To Acquired ARR",),
    "lost_arr_quarterly": ("Total Renewal ACV Lost",),
    "business_at_risk": ("Business At Risk ARR",),
    "synergy_deals_won": ("Synergy Deals Won", "Total Land Won Count"),
    "synergy_deals_pipe": ("Synergy Deals Pipeline",),
    "one_off_revenues": ("One Off Revenues",),
    "ps_arr_attach": ("PS ARR Attach Pct",),
    "saas_arr_yoy_growth": ("SaaS ARR YoY Growth",),
}


NEXT_SURFACE: dict[str, str] = {
    "pipeline_coverage_3x": "Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator.",
    "closed_won_avg_deal_size": "Add to Growth Mix as value-tier / deal-size strip.",
    "closed_won_value_tier": "Add DAX value-tier measures or a calculated tier column, then surface on Growth Mix.",
    "sales_cycle_length": "Add to Stage Hygiene as cycle-time companion to time-in-stage.",
    "stage3_approvals_compliance": "Add Commercial Approval compliance measure; current Stage Hygiene page only shows Stage 3 flow proxies.",
    "commercial_approval_to_close_time": "Needs Commercial Approval date in ETL; then add to Stage Hygiene.",
    "forecast_accuracy": "Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies.",
    "synergy_deals_pipe": "Needs synergy flag; then add open/won synergy strip to Growth Mix.",
    "cross_sell_to_acquired": "Needs Axioma/acquired-account flag; then add to Growth Mix.",
    "synergy_deals_won": "Needs synergy flag; current Growth Mix page uses Land won count as a proxy.",
    "lost_arr_quarterly": "Add to Renewals as loss waterfall / reason table.",
    "business_at_risk": "Needs account/subscription health flag; then add to Renewals.",
    "one_off_revenues": "Needs one-off/PS product fields; likely Product/Pricing future page.",
    "ps_arr_attach": "Needs PS/license product split; likely Product/Pricing future page.",
    "saas_arr_yoy_growth": "Needs SaaS deployment field; likely Product/Pricing future page.",
    "existing_arr_run_rate": "Needs Asset/Subscription base; keep as Renewals caveat until staged.",
    "indexation_arr_growth": "Needs indexation/contract uplift field; keep as Renewals caveat until staged.",
}


@dataclass(frozen=True)
class KPIIntelligenceRow:
    kpi_id: str
    name: str
    impact: str
    motion_filter: str
    source_coverage: str
    dashboard_status: str
    pages: tuple[str, ...]
    model_measures: tuple[str, ...]
    missing_measures: tuple[str, ...]
    next_action: str


def deployed_measure_names() -> set[str]:
    model = build_model_bim()["model"]
    return {
        measure["name"]
        for table in model["tables"]
        for measure in table.get("measures", [])
    }


def page_index() -> dict[str, tuple[str, ...]]:
    pages_by_kpi: dict[str, list[str]] = {}
    known_ids = {k.kpi_id for k in GRAPH.kpis}
    for page, contract in PAGE_KPI_CONTRACTS.items():
        for kpi_id in contract.kpi_ids:
            if kpi_id not in known_ids:
                raise ValueError(f"{page} references unknown RW KPI {kpi_id!r}")
            pages_by_kpi.setdefault(kpi_id, []).append(page)
    return {kpi_id: tuple(pages) for kpi_id, pages in pages_by_kpi.items()}


def dashboard_status(kpi: SalesKPI, pages: tuple[str, ...], missing: tuple[str, ...]) -> str:
    has_measure_hints = kpi.kpi_id in KPI_MEASURE_HINTS
    if pages and not missing and has_measure_hints:
        return "surfaced"
    if pages:
        return "surfaced_partial"
    if kpi.coverage_status in {"exists", "partial"} and not missing:
        return "model_available_not_surfaced"
    if kpi.coverage_status in {"exists", "partial"}:
        return "partial_data_or_measure_gap"
    return "source_data_gap"


def build_intelligence_rows() -> tuple[KPIIntelligenceRow, ...]:
    measures = deployed_measure_names()
    pages_by_kpi = page_index()
    rows: list[KPIIntelligenceRow] = []
    for kpi in GRAPH.kpis:
        hints = KPI_MEASURE_HINTS.get(kpi.kpi_id, ())
        missing = tuple(measure for measure in hints if measure not in measures)
        pages = pages_by_kpi.get(kpi.kpi_id, ())
        status = dashboard_status(kpi, pages, missing)
        if status == "surfaced":
            next_action = "Keep in page QA; tighten visual treatment if Desktop review flags it."
        else:
            next_action = NEXT_SURFACE.get(
                kpi.kpi_id,
                "Add explicit measure mapping and decide target page.",
            )
        rows.append(
            KPIIntelligenceRow(
                kpi_id=kpi.kpi_id,
                name=kpi.name,
                impact=kpi.impact,
                motion_filter=kpi.motion_filter,
                source_coverage=kpi.coverage_status,
                dashboard_status=status,
                pages=pages,
                model_measures=tuple(measure for measure in hints if measure in measures),
                missing_measures=missing,
                next_action=next_action,
            )
        )
    return tuple(rows)


def rollup(rows: tuple[KPIIntelligenceRow, ...]) -> dict[str, int]:
    out = {
        "total_kpis": len(rows),
        "surfaced": 0,
        "surfaced_partial": 0,
        "model_available_not_surfaced": 0,
        "partial_data_or_measure_gap": 0,
        "source_data_gap": 0,
    }
    for row in rows:
        out[row.dashboard_status] += 1
    return out


def _append_queue(lines: list[str], rows: list[KPIIntelligenceRow]) -> None:
    if not rows:
        lines.append("- None.")
        return
    for row in rows:
        lines.append(f"- `{row.kpi_id}`: {row.next_action}")


def _append_page_target_map(lines: list[str]) -> None:
    lines += [
        "",
        "## Page Decision Target Map",
        "",
        "The page contract is executable via `scripts/sales/rw_page_kpi_contract.py`; tests fail if a required KPI loses its page, visual role, motion guardrail, or proxy/gap label.",
    ]
    for page, contract in PAGE_KPI_CONTRACTS.items():
        lines += [
            "",
            f"### {page}",
            "",
            f"- Executive question: {contract.executive_question}",
            f"- Primary KPIs: {', '.join(f'`{kpi}`' for kpi in contract.primary_kpis)}",
            f"- Secondary diagnostics: {', '.join(f'`{kpi}`' for kpi in contract.secondary_diagnostics) if contract.secondary_diagnostics else 'None'}",
            f"- Required motion guardrail: `{contract.motion}`",
            f"- Caveat: {contract.caveat or 'None'}",
            "",
            "| KPI | Measure | Role | Motion | Data status | Label |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for placement in contract.placements:
            lines.append(
                f"| `{placement.kpi_id}` | `{placement.measure}` | {placement.visual_role} | "
                f"`{placement.motion_guardrail}` | {placement.data_status} | {placement.label} |"
            )


def to_markdown(rows: tuple[KPIIntelligenceRow, ...]) -> str:
    counts = rollup(rows)
    fast_page_upgrades = [
        row for row in rows if row.dashboard_status == "model_available_not_surfaced"
    ]
    semantic_upgrades = [
        row
        for row in rows
        if row.dashboard_status in {"surfaced_partial", "partial_data_or_measure_gap"}
    ]
    source_upgrades = [
        row for row in rows if row.dashboard_status == "source_data_gap"
    ]
    lines = [
        "# RW Dashboard KPI Intelligence",
        "",
        "Generated from `scripts/sales/rw_kpi_graph.py`, `rw_page_kpi_contract.py`, and the local semantic-model definition.",
        "",
        "## Rollup",
        "",
        f"- Total RW KPIs: {counts['total_kpis']}",
        f"- Surfaced cleanly on dashboard pages: {counts['surfaced']}",
        f"- Surfaced but still partial: {counts['surfaced_partial']}",
        f"- Model-available but not clearly surfaced: {counts['model_available_not_surfaced']}",
        f"- Partial data or measure gap: {counts['partial_data_or_measure_gap']}",
        f"- Source-data gap: {counts['source_data_gap']}",
        "",
        "Cardinal rule: ARR is Land+Expand only; Renewal ACV is Renewal only. The only cross-motion value measure remains `Total Open Pipeline Value`.",
        "",
        "`KG Source Status` comes from the canonical RW KPI graph. `Dashboard Status` reflects the deployed model measures and current page contract.",
        "",
        "## Immediate Upgrade Lanes",
        "",
        "Fast page-only upgrades; the model already has the measure, but the dashboard does not clearly surface it:",
    ]
    _append_queue(lines, fast_page_upgrades)
    lines += [
        "",
        "Semantic/model upgrades; a page exists or the KPI is close, but the current visual is still proxy/incomplete:",
    ]
    _append_queue(lines, semantic_upgrades)
    lines += [
        "",
        "Source-data upgrades; these need ETL/source-field work before a real dashboard visual can be trusted:",
    ]
    _append_queue(lines, source_upgrades)
    lines += [
        "",
        "## Slice/Dice Explorer",
        "",
        "The generated report also includes a native `RW KPI Explorer` page for interactive analysis outside the executive narrative tabs.",
        "",
        "- Executive page slicers: Region and Close FQ. Motion is not a page slicer because ARR/Renewal ACV measures enforce motion in DAX.",
        "- Explorer-only slicer: Stage. Motion appears as visual columns where comparison is explicit.",
        "- Explorer views: Land + Expand ARR mix, Renewal ACV exposure, Stage conversion diagnostics, Growth mix and new-customer signal.",
        "- ARR and Renewal ACV remain separate in the explorer; it does not use `Total Open Pipeline Value`.",
    ]
    _append_page_target_map(lines)
    lines += [
        "",
        "## KPI Matrix",
        "",
        "| KPI | Impact | Motion | KG Source Status | Dashboard Status | Pages | Measures | Next Action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        pages = ", ".join(row.pages) if row.pages else "-"
        measures = ", ".join(row.model_measures) if row.model_measures else "-"
        if row.missing_measures:
            measures += f" (missing: {', '.join(row.missing_measures)})"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.kpi_id}`",
                    row.impact,
                    row.motion_filter,
                    row.source_coverage,
                    row.dashboard_status,
                    pages,
                    measures,
                    row.next_action,
                ]
            )
            + " |"
        )

    high_risk = [
        row
        for row in rows
        if row.impact == "HIGH" and row.dashboard_status != "surfaced"
    ]
    lines += [
        "",
        "## High-Impact Follow-Up Queue",
        "",
    ]
    for row in high_risk:
        lines.append(f"- `{row.kpi_id}`: {row.next_action}")
    return "\n".join(lines) + "\n"


def write_outputs(out_path: Path) -> None:
    rows = build_intelligence_rows()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(to_markdown(rows), encoding="utf-8")
    json_path = out_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(
            {
                "rollup": rollup(rows),
                "page_target_map": target_map_as_dict(),
                "rows": [asdict(row) for row in rows],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out_path}")
    print(f"wrote {json_path}")
    print(json.dumps(rollup(rows), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    write_outputs(args.out)


if __name__ == "__main__":
    main()
