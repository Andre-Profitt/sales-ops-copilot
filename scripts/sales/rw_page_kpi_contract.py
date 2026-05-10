"""RW Power BI page-to-KPI targeting contract.

This keeps the report from drifting into attractive-but-generic dashboard pages.
Every production tab must declare the RW KPI IDs it serves and the deployed
measures it uses. ARR and Renewal ACV remain separated at the measure layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Motion = Literal["land_expand_arr", "renewal_acv", "cross_motion_labeled", "process"]


@dataclass(frozen=True)
class PageKPIContract:
    page: str
    job: str
    kpi_ids: tuple[str, ...]
    measures: tuple[str, ...]
    motion: Motion
    caveat: str = ""


PAGE_KPI_CONTRACTS: dict[str, PageKPIContract] = {
    "VP Ops Scorecard": PageKPIContract(
        page="VP Ops Scorecard",
        job="Executive control room: outcome, conversion, exceptions, stage health, 7-day movement.",
        kpi_ids=(
            "forecast_closed_won",
            "opp_win_rate",
            "renewal_retention_rate",
            "stage_conversion",
            "time_in_stage",
            "new_opps_by_region",
        ),
        measures=(
            "Total Closed Won ARR",
            "Win Rate ARR",
            "Exception ARR",
            "Renewal Retention Pct (Period)",
            "Total Open Pipeline ARR",
            "Stage Forward Pct (LE)",
            "Stage Backward Pct (LE)",
            "Avg Days In Prior Stage (LE)",
            "Stage Moves ARR 7d",
            "New Opps Count 7d",
            "Closed Won Count 7d",
            "Backward Moves Count 7d",
        ),
        motion="cross_motion_labeled",
        caveat="Renewal retention is displayed beside ARR KPIs but not blended into ARR.",
    ),
    "What Changed": PageKPIContract(
        page="What Changed",
        job="Daily/weekly movement review: new, won/lost, stage moves, and exception deltas.",
        kpi_ids=(
            "new_opps_by_region",
            "stage_conversion",
            "opp_age",
            "forecast_closed_won",
        ),
        measures=(
            "At Risk Opps Count",
            "At Risk Opps ARR",
            "Watch Opps Count",
            "Watch Opps ARR",
            "Healthy Moves Count",
            "Healthy Moves ARR",
            "Stage Moves Count 7d",
            "Stage Moves ARR 7d",
            "New Opps Count 7d",
            "Closed Won Count 7d",
            "Closed Lost Count 7d",
            "Total Open Pipeline ARR",
        ),
        motion="land_expand_arr",
    ),
    "Forecast": PageKPIContract(
        page="Forecast",
        job="Quarter answer: remaining days, open value, won ARR, forecast movement discipline.",
        kpi_ids=(
            "forecast_closed_won",
            "pipeline_coverage_3x",
            "forecast_accuracy",
            "stage3_acv_value",
        ),
        measures=(
            "Days Remaining In FQ",
            "Total Open Pipeline Value",
            "Total Closed Won ARR",
            "Forecast Slip Pct",
            "Forecast Slips",
            "Forecast Upgrades",
            "Avg Days In Forecast Category",
        ),
        motion="cross_motion_labeled",
        caveat="Total Open Pipeline Value is the only explicit cross-motion value measure.",
    ),
    "Stage Hygiene": PageKPIContract(
        page="Stage Hygiene",
        job="Funnel diagnosis: stage conversion, backward movement, and time-in-stage bottlenecks.",
        kpi_ids=(
            "stage_conversion",
            "time_in_stage",
            "sales_cycle_length",
            "stage3_approvals_compliance",
        ),
        measures=(
            "Stage Forward Pct (LE)",
            "Stage Backward Pct (LE)",
            "Avg Days In Prior Stage (LE)",
            "Avg Sales Cycle Days",
            "Land Avg Sales Cycle Days",
            "Total Stage Transitions",
            "Stage Moves ARR 7d",
            "Stage 3 Forward Pct",
            "Avg Days In Stage 3",
            "Stage 4 Forward Pct",
            "Avg Days In Stage 4",
        ),
        motion="process",
        caveat="Stage 3 and Stage 4 are the control points for approval friction and late-funnel slippage.",
    ),
    "Renewals": PageKPIContract(
        page="Renewals",
        job="Renewal ACV cockpit: open exposure, retained ACV, lost ACV, and regional pressure.",
        kpi_ids=(
            "renewal_retention_rate",
            "renewals_mom_trend",
            "lost_arr_quarterly",
            "existing_arr_run_rate",
            "indexation_arr_growth",
        ),
        measures=(
            "Total Open Renewal ACV",
            "Total Renewal ACV Due",
            "Renewal Retention Pct (Period)",
            "Total Renewal ACV Won",
            "Total Renewal ACV Lost",
        ),
        motion="renewal_acv",
        caveat="Renewal ACV only. Land and Expand ARR are excluded from this page.",
    ),
    "Growth Mix": PageKPIContract(
        page="Growth Mix",
        job="Growth mix cockpit: open Land, open Expand, partner contribution, and new-customer signal.",
        kpi_ids=(
            "ilf_arr_pipeline",
            "alf_arr_pipeline",
            "new_customer_reporting",
            "closed_won_avg_deal_size",
            "partner_opps_pct",
            "opp_source_effectiveness",
            "synergy_deals_won",
        ),
        measures=(
            "Open Land ARR",
            "Open Expand ARR",
            "Partner ARR",
            "Partner Pct",
            "Total Open Pipeline ARR",
            "Total Land Won Count",
            "Avg Deal Size Won",
        ),
        motion="land_expand_arr",
        caveat="Land and Expand ARR only. Renewal ACV is excluded from this page.",
    ),
}


def contract_for(page: str) -> PageKPIContract:
    return PAGE_KPI_CONTRACTS[page]


def required_measures() -> set[str]:
    out: set[str] = set()
    for contract in PAGE_KPI_CONTRACTS.values():
        out.update(contract.measures)
    return out
