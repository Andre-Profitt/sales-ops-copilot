"""RW Power BI page-to-KPI targeting contract.

This keeps the report from drifting into attractive-but-generic dashboard pages.
Every production tab must declare the executive question it answers, the RW KPI
IDs it serves, the visual role each required KPI needs, and the motion/data
status guardrails. ARR and Renewal ACV remain separated at the measure layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal


Motion = Literal[
    "land_expand_arr",
    "renewal_acv",
    "renewal_base_arr",
    "cross_motion_labeled",
    "process",
]
VisualRole = Literal[
    "hero KPI",
    "RAG card",
    "exception ledger",
    "movement ledger",
    "variance table",
    "bridge/waterfall",
    "detail table",
    "slicer",
]
DataStatus = Literal["clean", "proxy", "partial", "missing model measure", "missing source data"]


@dataclass(frozen=True)
class KPIPlacement:
    kpi_id: str
    measure: str
    visual_role: VisualRole
    motion_guardrail: Motion
    data_status: DataStatus
    label: str
    secondary: bool = False
    missing_measure: str = ""


@dataclass(frozen=True)
class PageKPIContract:
    page: str
    job: str
    executive_question: str
    primary_kpis: tuple[str, ...]
    secondary_diagnostics: tuple[str, ...]
    kpi_ids: tuple[str, ...]
    measures: tuple[str, ...]
    motion: Motion
    placements: tuple[KPIPlacement, ...]
    caveat: str = ""


def p(
    kpi_id: str,
    measure: str,
    role: VisualRole,
    motion: Motion,
    status: DataStatus,
    label: str,
    *,
    secondary: bool = False,
    missing_measure: str = "",
) -> KPIPlacement:
    return KPIPlacement(kpi_id, measure, role, motion, status, label, secondary, missing_measure)


PAGE_KPI_CONTRACTS: dict[str, PageKPIContract] = {
    "VP Ops Scorecard": PageKPIContract(
        page="VP Ops Scorecard",
        job="Executive control room: outcome, conversion, exceptions, stage health, 7-day movement.",
        executive_question="Where is RW off plan right now, and which lane needs executive action first?",
        primary_kpis=("forecast_closed_won", "opp_win_rate", "stage_conversion", "renewal_retention_rate"),
        secondary_diagnostics=("time_in_stage", "new_opps_by_region"),
        kpi_ids=("forecast_closed_won", "opp_win_rate", "renewal_retention_rate", "stage_conversion", "time_in_stage", "new_opps_by_region"),
        measures=("Total Closed Won ARR", "Win Rate ARR", "Exception ARR", "Renewal Retention Pct (Period)", "Total Open Pipeline ARR", "Stage Forward Pct (LE)", "Stage Backward Pct (LE)", "Avg Days In Prior Stage (LE)", "Stage Moves ARR 7d", "New Opps Count 7d", "Closed Won Count 7d", "Backward Moves Count 7d"),
        motion="cross_motion_labeled",
        placements=(
            p("forecast_closed_won", "Total Closed Won ARR", "hero KPI", "land_expand_arr", "clean", "Closed won ARR (Land + Expand)"),
            p("opp_win_rate", "Win Rate ARR", "hero KPI", "land_expand_arr", "clean", "Win rate (ARR-wtd)"),
            p("stage_conversion", "Stage Forward Pct (LE)", "variance table", "land_expand_arr", "partial", "Stage hygiene (count rates, Land + Expand)"),
            p("renewal_retention_rate", "Renewal Retention Pct (Period)", "hero KPI", "renewal_acv", "partial", "Retention % (ACV-wtd)"),
            p("time_in_stage", "Avg Days In Prior Stage (LE)", "variance table", "land_expand_arr", "partial", "Stage hygiene (count rates, Land + Expand)", secondary=True),
            p("new_opps_by_region", "New Opps Count 7d", "RAG card", "land_expand_arr", "clean", "New opp count 7d", secondary=True),
        ),
        caveat="Renewal retention is displayed beside ARR KPIs but not blended into ARR.",
    ),
    "What Changed": PageKPIContract(
        page="What Changed",
        job="Daily/weekly movement review: new, won/lost, stage moves, and exception deltas.",
        executive_question="What materially changed in the last operating window, and which open opportunities need inspection?",
        primary_kpis=("new_opps_by_region", "stage_conversion", "opp_age", "forecast_closed_won"),
        secondary_diagnostics=(),
        kpi_ids=("new_opps_by_region", "stage_conversion", "opp_age", "forecast_closed_won"),
        measures=("At Risk Opps Count", "At Risk Opps ARR", "Watch Opps Count", "Watch Opps ARR", "Healthy Moves Count", "Healthy Moves ARR", "Stage Moves Count 7d", "Stage Moves ARR 7d", "New Opps Count 7d", "Closed Won Count 7d", "Closed Lost Count 7d", "Total Open Pipeline ARR"),
        motion="land_expand_arr",
        placements=(
            p("opp_age", "At Risk Opps ARR", "exception ledger", "land_expand_arr", "clean", "At-risk ARR (Land + Expand)"),
            p("opp_age", "Watch Opps ARR", "exception ledger", "land_expand_arr", "clean", "Watch ARR (Land + Expand)"),
            p("stage_conversion", "Stage Moves ARR 7d", "movement ledger", "land_expand_arr", "clean", "Stage ARR (Land + Expand)"),
            p("new_opps_by_region", "New Opps Count 7d", "movement ledger", "land_expand_arr", "clean", "New opp count"),
            p("forecast_closed_won", "Closed Won Count 7d", "movement ledger", "land_expand_arr", "clean", "Won count"),
            p("opp_age", "Total Open Pipeline ARR", "detail table", "land_expand_arr", "clean", "Top Open ARR (Land + Expand) Movement Queue"),
        ),
    ),
    "Forecast": PageKPIContract(
        page="Forecast",
        job="Quarter answer: remaining days, open value, won ARR, forecast movement discipline.",
        executive_question="Can the quarter still land, and is forecast movement disciplined enough to trust?",
        primary_kpis=("forecast_closed_won", "pipeline_coverage_3x", "forecast_accuracy"),
        secondary_diagnostics=("stage3_acv_value",),
        kpi_ids=("forecast_closed_won", "pipeline_coverage_3x", "forecast_accuracy", "stage3_acv_value"),
        measures=("Days Remaining In FQ", "Total Open Pipeline Value", "Total Closed Won ARR", "Forecast Slip Pct", "Forecast Slips", "Forecast Upgrades", "Avg Days In Forecast Category"),
        motion="cross_motion_labeled",
        placements=(
            p("pipeline_coverage_3x", "Total Open Pipeline Value", "hero KPI", "cross_motion_labeled", "partial", "Open Value (ARR+ACV, cross-motion)", missing_measure="Pipeline Coverage Ratio"),
            p("forecast_closed_won", "Total Closed Won ARR", "hero KPI", "land_expand_arr", "clean", "Closed won ARR (Land + Expand)"),
            p("pipeline_coverage_3x", "Total Open Pipeline Value", "variance table", "cross_motion_labeled", "partial", "Stage x Motion Open Value (ARR+ACV)", secondary=True, missing_measure="Pipeline Coverage Ratio"),
            p("forecast_accuracy", "Forecast Slip Pct", "RAG card", "land_expand_arr", "proxy", "Slip % (count proxy)", missing_measure="Forecast Accuracy"),
            p("forecast_accuracy", "Forecast Slips", "RAG card", "land_expand_arr", "proxy", "Slip count proxy", secondary=True, missing_measure="Forecast Accuracy"),
            p("stage3_acv_value", "Total Open Pipeline Value", "detail table", "cross_motion_labeled", "partial", "Late-Stage Commit Risk", secondary=True),
        ),
        caveat="Total Open Pipeline Value is the only explicit cross-motion value measure.",
    ),
    "Stage Hygiene": PageKPIContract(
        page="Stage Hygiene",
        job="Funnel diagnosis: stage conversion, backward movement, and time-in-stage bottlenecks.",
        executive_question="Which stage is slowing or reversing Land + Expand opportunities, and is the Stage 3/4 control point healthy?",
        primary_kpis=("stage_conversion", "time_in_stage", "sales_cycle_length"),
        secondary_diagnostics=("stage3_approvals_compliance", "commercial_approval_to_close_time"),
        kpi_ids=("stage_conversion", "time_in_stage", "sales_cycle_length", "stage3_approvals_compliance", "commercial_approval_to_close_time"),
        measures=("Stage Forward Pct (LE)", "Stage Backward Pct (LE)", "Avg Days In Prior Stage (LE)", "Avg Sales Cycle Days", "Land Avg Sales Cycle Days", "Total Stage Transitions", "Stage Moves ARR 7d", "Stage 4 Forward Pct", "Avg Days In Stage 4", "Commercial Approval Compliance Pct", "Commercial Approval To Close Days"),
        motion="process",
        placements=(
            p("stage_conversion", "Stage Forward Pct (LE)", "hero KPI", "land_expand_arr", "partial", "Forward % (count, Land + Expand)"),
            p("stage_conversion", "Stage Backward Pct (LE)", "hero KPI", "land_expand_arr", "partial", "Backward % (count, Land + Expand)"),
            p("time_in_stage", "Avg Days In Prior Stage (LE)", "hero KPI", "land_expand_arr", "partial", "Stage days (Land + Expand)"),
            p("sales_cycle_length", "Land Avg Sales Cycle Days", "hero KPI", "land_expand_arr", "clean", "Land cycle days"),
            p("sales_cycle_length", "Avg Sales Cycle Days", "hero KPI", "land_expand_arr", "clean", "Land + Expand cycle days"),
            p("stage_conversion", "Stage Forward Pct (LE)", "variance table", "land_expand_arr", "partial", "Stage Conversion Matrix (count, Land + Expand)"),
            p("stage3_approvals_compliance", "Commercial Approval Compliance Pct", "RAG card", "land_expand_arr", "clean", "Approval % (count)", secondary=True),
            p("commercial_approval_to_close_time", "Commercial Approval To Close Days", "RAG card", "land_expand_arr", "clean", "Approval-close days", secondary=True),
        ),
        caveat="Stage 3 and Stage 4 are the control points for approval friction and late-funnel slippage.",
    ),
    "Renewals": PageKPIContract(
        page="Renewals",
        job="Renewal ACV cockpit: open exposure, retained ACV, lost ACV, and regional pressure.",
        executive_question="How much Renewal ACV is exposed, retained, or lost, and where is the pressure?",
        primary_kpis=("renewal_retention_rate", "renewals_mom_trend", "lost_arr_quarterly"),
        secondary_diagnostics=("business_at_risk", "existing_arr_run_rate", "indexation_arr_growth"),
        kpi_ids=("renewal_retention_rate", "renewals_mom_trend", "lost_arr_quarterly", "business_at_risk", "existing_arr_run_rate", "indexation_arr_growth"),
        measures=(
            "Total Open Renewal ACV",
            "Total Renewal ACV Due",
            "Renewal Retention Pct (Period)",
            "Total Renewal ACV Won",
            "Total Renewal ACV Lost",
            "Existing ARR Run Rate",
            "Existing ARR Expiring In Period",
            "Business At Risk ARR",
            "Business At Risk Pct",
        ),
        motion="renewal_acv",
        placements=(
            p("renewals_mom_trend", "Total Open Renewal ACV", "hero KPI", "renewal_acv", "clean", "Open renewal ACV"),
            p("renewal_retention_rate", "Renewal Retention Pct (Period)", "hero KPI", "renewal_acv", "partial", "Retention % (ACV-wtd)"),
            p("renewals_mom_trend", "Total Renewal ACV Won", "hero KPI", "renewal_acv", "clean", "Won renewal ACV"),
            p("lost_arr_quarterly", "Total Renewal ACV Lost", "hero KPI", "renewal_acv", "partial", "Lost renewal ACV"),
            p("existing_arr_run_rate", "Existing ARR Run Rate", "hero KPI", "renewal_base_arr", "clean", "Active-base ARR", secondary=True),
            p("business_at_risk", "Business At Risk ARR", "hero KPI", "renewal_base_arr", "clean", "At-risk base ARR", secondary=True),
            p("business_at_risk", "Business At Risk ARR", "bridge/waterfall", "renewal_base_arr", "clean", "At-risk active-base ARR by Region", secondary=True),
            p("existing_arr_run_rate", "Existing ARR Expiring In Period", "detail table", "renewal_base_arr", "clean", "Active-base ARR Detail", secondary=True),
            p("indexation_arr_growth", "Indexation ARR Growth", "detail table", "renewal_acv", "missing source data", "Indexation ARR Growth", secondary=True, missing_measure="Indexation ARR Growth"),
        ),
        caveat="Renewal opportunity ACV and active-base ARR are separated. Land and Expand new-business ARR are excluded from this page.",
    ),
    "Product Retention": PageKPIContract(
        page="Product Retention",
        job="Product active-base view: product heatmaps and account-product retention scaffold.",
        executive_question="Which product, segment, and region combinations carry active-base ARR retention or churn risk?",
        primary_kpis=("existing_arr_run_rate", "business_at_risk"),
        secondary_diagnostics=("indexation_arr_growth",),
        kpi_ids=("existing_arr_run_rate", "business_at_risk", "indexation_arr_growth"),
        measures=(
            "Existing ARR Run Rate",
            "Existing ARR Expiring In Period",
            "Business At Risk ARR",
            "Business At Risk Pct",
            "Active Asset Line Count",
        ),
        motion="renewal_base_arr",
        placements=(
            p("existing_arr_run_rate", "Existing ARR Run Rate", "hero KPI", "renewal_base_arr", "clean", "Active-base ARR"),
            p("existing_arr_run_rate", "Existing ARR Expiring In Period", "variance table", "renewal_base_arr", "clean", "Active-base ARR by Product x Region"),
            p("business_at_risk", "Business At Risk ARR", "hero KPI", "renewal_base_arr", "clean", "At-risk active-base ARR"),
            p("business_at_risk", "Business At Risk Pct", "variance table", "renewal_base_arr", "clean", "Risk % of active base"),
            p("existing_arr_run_rate", "Existing ARR Expiring In Period", "detail table", "renewal_base_arr", "clean", "Account-product Retention Ledger", secondary=True),
            p("indexation_arr_growth", "Indexation ARR Growth", "detail table", "renewal_base_arr", "missing source data", "Indexation ARR Growth", secondary=True, missing_measure="Indexation ARR Growth"),
        ),
        caveat=(
            "Product heatmaps use active-base ARR from asset line items. True churn requires prior/current "
            "active-base snapshots or effective-dated asset rows. This is not Renewal ACV and not Land + Expand ARR."
        ),
    ),
    "Growth Mix": PageKPIContract(
        page="Growth Mix",
        job="Growth mix cockpit: open Land, open Expand, partner contribution, and new-customer signal.",
        executive_question="Is growth coming from the right Land, Expand, partner, source, and new-customer mix?",
        primary_kpis=("ilf_arr_pipeline", "alf_arr_pipeline", "new_customer_reporting", "closed_won_avg_deal_size", "partner_opps_pct"),
        secondary_diagnostics=("opp_source_effectiveness", "closed_won_value_tier", "cross_sell_to_acquired", "ps_arr_attach", "saas_arr_yoy_growth", "synergy_deals_won"),
        kpi_ids=("ilf_arr_pipeline", "alf_arr_pipeline", "new_customer_reporting", "closed_won_avg_deal_size", "partner_opps_pct", "opp_source_effectiveness", "closed_won_value_tier", "cross_sell_to_acquired", "ps_arr_attach", "saas_arr_yoy_growth", "synergy_deals_won"),
        measures=("Open Land ARR", "Open Expand ARR", "Partner ARR", "Partner Pct", "Total Open Pipeline ARR", "Total Land Won Count", "Avg Deal Size Won", "Closed Won Deals Count", "Cross Sell To Acquired ARR", "PS ARR Attach Pct", "SaaS YoY Growth Pct"),
        motion="land_expand_arr",
        placements=(
            p("alf_arr_pipeline", "Open Land ARR", "hero KPI", "land_expand_arr", "partial", "Open Land ARR"),
            p("ilf_arr_pipeline", "Open Expand ARR", "hero KPI", "land_expand_arr", "partial", "Open Expand ARR"),
            p("closed_won_avg_deal_size", "Avg Deal Size Won", "hero KPI", "land_expand_arr", "partial", "Avg won ARR (Land + Expand)"),
            p("partner_opps_pct", "Partner ARR", "hero KPI", "land_expand_arr", "clean", "Partner ARR (Land + Expand)"),
            p("partner_opps_pct", "Partner Pct", "hero KPI", "land_expand_arr", "clean", "Partner % ARR share"),
            p("alf_arr_pipeline", "Total Open Pipeline ARR", "bridge/waterfall", "land_expand_arr", "partial", "Open Land + Expand ARR by Region"),
            p("new_customer_reporting", "Total Land Won Count", "detail table", "land_expand_arr", "clean", "Land won count"),
            p("opp_source_effectiveness", "Partner ARR", "detail table", "land_expand_arr", "clean", "Strategic Mix Detail", secondary=True),
            p("closed_won_value_tier", "Closed Won Deals Count", "detail table", "land_expand_arr", "clean", "Won value tier", secondary=True),
            p("cross_sell_to_acquired", "Cross Sell To Acquired ARR", "detail table", "land_expand_arr", "clean", "Axioma ARR (Land + Expand)", secondary=True),
            p("ps_arr_attach", "PS ARR Attach Pct", "detail table", "land_expand_arr", "clean", "PS attach % (ACV/ARR)", secondary=True),
            p("saas_arr_yoy_growth", "SaaS YoY Growth Pct", "detail table", "process", "clean", "SaaS ARR YoY %", secondary=True),
            p("synergy_deals_won", "Total Land Won Count", "detail table", "land_expand_arr", "proxy", "Land count proxy", secondary=True, missing_measure="Synergy Deals Won"),
        ),
        caveat="Land and Expand ARR stay separate from Renewal ACV. SaaS and PS use their own source fields; Synergy remains proxy-only until the source flag exists.",
    ),
}


def contract_for(page: str) -> PageKPIContract:
    return PAGE_KPI_CONTRACTS[page]


def required_measures() -> set[str]:
    out: set[str] = set()
    for contract in PAGE_KPI_CONTRACTS.values():
        out.update(contract.measures)
    return out


def target_map_as_dict() -> dict[str, dict]:
    """Serializable page-by-page KPI decision target map for docs/artifacts."""
    return {
        page: {
            "executive_question": contract.executive_question,
            "job": contract.job,
            "primary_kpis": list(contract.primary_kpis),
            "secondary_diagnostics": list(contract.secondary_diagnostics),
            "required_motion_guardrail": contract.motion,
            "caveat": contract.caveat,
            "placements": [
                {
                    "kpi_id": placement.kpi_id,
                    "measure": placement.measure,
                    "visual_role": placement.visual_role,
                    "motion_guardrail": placement.motion_guardrail,
                    "data_status": placement.data_status,
                    "label": placement.label,
                    "secondary": placement.secondary,
                    "missing_measure": placement.missing_measure,
                }
                for placement in contract.placements
            ],
        }
        for page, contract in PAGE_KPI_CONTRACTS.items()
    }


def _visual_type(vc: dict) -> str:
    try:
        return json.loads(vc.get("config", "{}"))["singleVisual"].get("visualType", "")
    except (json.JSONDecodeError, KeyError, TypeError):
        return ""


def _page_text(section: dict) -> str:
    return "\n".join(v.get("config", "") for v in section.get("visualContainers", []))


def _measure_visual_types(section: dict, measure: str) -> set[str]:
    return {
        _visual_type(vc)
        for vc in section.get("visualContainers", [])
        if measure and measure in vc.get("config", "")
    }


ROLE_VISUAL_TYPES: dict[VisualRole, set[str]] = {
    "hero KPI": {"card"},
    "RAG card": {"card"},
    "exception ledger": {"tableEx", "pivotTable"},
    "movement ledger": {"tableEx", "pivotTable"},
    "variance table": {"tableEx", "pivotTable"},
    "bridge/waterfall": {"waterfallChart", "clusteredBarChart", "pivotTable"},
    "detail table": {"tableEx", "pivotTable"},
    "slicer": {"slicer"},
}


def validate_decision_contracts(contracts: dict[str, PageKPIContract] | None = None) -> list[str]:
    contracts = contracts or PAGE_KPI_CONTRACTS
    errors: list[str] = []
    for page, contract in contracts.items():
        if not contract.executive_question.strip().endswith("?"):
            errors.append(f"{page}: executive question must be explicit and end with '?'")
        placement_ids = {placement.kpi_id for placement in contract.placements}
        for kpi_id in contract.primary_kpis:
            if kpi_id not in contract.kpi_ids:
                errors.append(f"{page}: primary KPI {kpi_id!r} is not in kpi_ids")
            if kpi_id not in placement_ids:
                errors.append(f"{page}: primary KPI {kpi_id!r} has no required visual placement")
        for placement in contract.placements:
            if placement.kpi_id not in contract.kpi_ids:
                errors.append(f"{page}: placement references undeclared KPI {placement.kpi_id!r}")
            if placement.data_status == "clean" and placement.missing_measure:
                errors.append(f"{page}: proxy/gap KPI {placement.kpi_id!r} cannot be counted clean")
            if placement.data_status == "proxy" and "proxy" not in placement.label.lower() and "proxy" not in contract.caveat.lower():
                errors.append(f"{page}: proxy KPI {placement.kpi_id!r} must be labeled as proxy/partial")
            if placement.motion_guardrail == "cross_motion_labeled":
                label_text = f"{placement.label} {contract.caveat}".lower()
                if "cross-motion" not in label_text and "cross motion" not in label_text:
                    errors.append(f"{page}: cross-motion measure {placement.measure!r} is not explicitly labeled")
            if placement.motion_guardrail == "land_expand_arr" and "Renewal ACV" in placement.measure:
                errors.append(f"{page}: Land + Expand ARR placement uses Renewal ACV measure {placement.measure!r}")
            if placement.motion_guardrail == "renewal_acv" and placement.measure.endswith(" ARR"):
                errors.append(f"{page}: Renewal ACV placement uses ARR measure {placement.measure!r}")
    return errors


def validate_contract_pages(rj: dict, contracts: dict[str, PageKPIContract] | None = None) -> list[str]:
    contracts = contracts or PAGE_KPI_CONTRACTS
    errors = validate_decision_contracts(contracts)
    pages = {s.get("displayName"): s for s in rj.get("sections", [])}
    for page, contract in contracts.items():
        section = pages.get(page)
        if section is None:
            errors.append(f"missing target page {page!r}")
            continue
        if not section.get("visualContainers"):
            errors.append(f"target page {page!r} has no visuals")
            continue
        encoded = _page_text(section)
        for measure in contract.measures:
            if measure not in encoded:
                errors.append(f"{page}: contract measure {measure!r} not present in page JSON")
        if "Total Open Pipeline Value" in encoded and contract.motion != "cross_motion_labeled":
            errors.append(f"{page}: unlabeled cross-motion Total Open Pipeline Value is not allowed")
        for placement in contract.placements:
            if placement.data_status in {"missing model measure", "missing source data"}:
                if placement.measure in encoded:
                    errors.append(f"{page}: gap KPI {placement.kpi_id!r} appears as solved measure {placement.measure!r}")
                continue
            if placement.measure not in encoded:
                errors.append(f"{page}: required KPI {placement.kpi_id!r} measure {placement.measure!r} missing")
                continue
            actual_types = _measure_visual_types(section, placement.measure)
            allowed_types = ROLE_VISUAL_TYPES[placement.visual_role]
            if not actual_types & allowed_types:
                errors.append(
                    f"{page}: KPI {placement.kpi_id!r} requires role {placement.visual_role!r} "
                    f"via {sorted(allowed_types)}, found {sorted(actual_types)}"
                )
    return errors
