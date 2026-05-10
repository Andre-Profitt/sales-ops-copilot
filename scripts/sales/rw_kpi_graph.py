"""RW (Richard Wyeth, MD Sales Operations) target-KPI knowledge graph.

Single source of truth for the 31 sales KPIs Richard Wyeth views as
VP Ops, sourced verbatim from `~/knowledge/simcorp/Simcorp/Metrics and KPIs.xlsx`
(sheet `RW - KPIs`, 2026-05-07).

Same KG-as-code shape as wf_kpi_graph.py (workforce intensity) and
sales_process_graph.py (sales motion stages). Typed dataclasses + an
aggregator + helpers + to_llm_context() for prompt injection.

Architecture: SF Reports remain canonical metric sources. This KG plus
the future Fabric semantic model (sm_sales_kpis_rw) form the presentation
contract — DAX measures, RAG thresholds, and target values flow from
this file into the Power BI report.

Cardinal SimCorp business rules (inherited):
- ARR for Land+Expand → APTS_Opportunity_ARR__c
- ACV for Renewals → APTS_Renewal_ACV__c
- NEVER blend Amount or sum across motions
- Multi-currency: trust SF Report `s!field` aggregates (FX-converted),
  NOT raw SOQL SUM (unconverted)

Versioning:
  SCHEMA_VERSION 1 (2026-05-07). Bump when entity shapes change in a way
  that breaks downstream consumers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

SCHEMA_VERSION = 1

KPI_SOURCE_XLSX = "~/knowledge/simcorp/Simcorp/Metrics and KPIs.xlsx"
SF_ORG = "simcorp.my.salesforce.com"
RICHARD_USER_ID = "005QA000003DbJUYA0"  # Richard Wyeth, MD Sales Operations

# Live deployment — updated in place when Fabric artifacts move
DEPLOYMENT = {
    "fabric_workspace_id": "b66233d5-9d4a-44ba-89a8-b70206d98ae7",
    "fabric_workspace_name": "Salesforce Analytics - Sales Manager",
    "lakehouse_id": "50f1721e-6b2e-44db-a1a7-7b8209c7a77b",
    "lakehouse_name": "lkh_sales_kpis_rw",
    "semantic_model_id": "3c58b5dd-b321-4aaa-a5cd-fb73e474edbb",
    "semantic_model_name": "sm_sales_kpis_rw",
    "deployed_at": "2026-05-07",
    "phase": "2.5",
    # KPIs operationally surfaced via DAX in the deployed model.
    # Phase 1 = pure-Opp aggregates (12). Phase 2 = + OFH stage transitions (2).
    # Phase 2.5 = + lead-source effectiveness + Land-only new-customer (2).
    # Remaining 15 require Phase 3 staging.
    "live_kpi_ids": (
        # Phase 1
        "forecast_closed_won",
        "pipeline_coverage_3x",  # numerator only; quota denominator pending
        "opp_win_rate",
        "closed_won_avg_deal_size",
        "sales_cycle_length",
        "opp_age",
        "stage3_acv_value",
        "partner_opps_pct",
        "renewals_mom_trend",
        "lost_arr_quarterly",
        "renewal_retention_rate",
        "new_opps_by_region",
        # Phase 2 (OFH)
        "time_in_stage",
        "stage_conversion",
        # Phase 2.5 (DAX-only)
        "opp_source_effectiveness",
        "new_customer_reporting",
    ),
    "dax_measure_count": 31,  # +6 YoY (Closed Won/Renewal ACV/Pipeline × LY + YoY%)
    "deployed_tables": (
        "f_opportunity",
        "d_account",
        "d_user",
        "d_region",
        "d_calendar",
        "f_stage_transition",
    ),
}


# ──────────────────────────────────────────────────────────────────────────
# Entity dataclasses
# ──────────────────────────────────────────────────────────────────────────


ProcessArea = Literal[
    "1.4 Opportunity Mgmt — Forecasting",
    "1.8 Renewals",
    "1.9 Conversion",
    "1.10 Cancellation",
    "1.14 Product/Pricing",
]
Impact = Literal["HIGH", "MEDIUM", "LOW"]
Bucket = Literal["Metrics", "Process"]
CoverageStatus = Literal["exists", "partial", "missing"]
Direction = Literal["higher_is_better", "lower_is_better", "track"]


@dataclass(frozen=True)
class SalesKPI:
    """A target KPI on Richard Wyeth's VP Ops scorecard."""

    kpi_id: str
    process_area: ProcessArea
    name: str
    target_text: str  # verbatim from Excel
    target_value: float | None  # numeric where extractable
    target_unit: str | None  # "%", "x", "days", "deals/qtr", etc.
    impact: Impact
    primary_bucket: Bucket
    direction: Direction
    motion_filter: Literal["land_expand", "renewal", "all"]  # ARR vs ACV vs both
    sf_source_id: str | None  # SF Report.Id if known
    sf_source_name: str | None  # SF Report.Name if known
    coverage_status: CoverageStatus
    definition: str
    why_it_matters: str
    soql_hint: str  # rough SOQL/aggregation pattern for builders
    caveats: tuple[str, ...] = ()


@dataclass(frozen=True)
class RWKPIGraph:
    """Aggregate."""

    kpis: tuple[SalesKPI, ...]


# ──────────────────────────────────────────────────────────────────────────
# Graph data — verbatim ingest of "RW - KPIs" sheet (2026-05-07)
# ──────────────────────────────────────────────────────────────────────────


_KPIS = (
    # ── 1.4 Opportunity Mgmt — Forecasting (16 KPIs) ───────────────────────
    SalesKPI(
        kpi_id="forecast_closed_won",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Forecast & Closed Won",
        target_text="Baseline +10% YoY",
        target_value=0.10,
        target_unit="YoY %",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id="00OTb000008qADBMA2",
        sf_source_name="Pipeline - Revenue Forecasting",
        coverage_status="exists",
        definition="Sum of ARR on Closed-Won opportunities, comparing current period vs prior YoY period.",
        why_it_matters="Headline number; everything else explains over- or under-performance against this.",
        soql_hint="SUM(APTS_Opportunity_ARR__c) WHERE IsClosed=true AND IsWon=true GROUP BY FISCAL_YEAR(CloseDate)",
    ),
    SalesKPI(
        kpi_id="pipeline_coverage_3x",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Pipeline Value / Pipeline Coverage",
        target_text="3x Coverage",
        target_value=3.0,
        target_unit="x quota",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id="00OTb000008mukrMAA",
        sf_source_name="Commit Forecast — Stage 5+6 ARR (CFQ)",
        coverage_status="partial",
        definition="Open pipeline ARR (excluding Won) divided by remaining quota for the period.",
        why_it_matters="Below 3x → at-risk to hit forecast; need pipeline build motion.",
        soql_hint="SUM(APTS_Opportunity_ARR__c) WHERE IsClosed=false AND CloseDate IN <period> / quota",
        caveats=("Partial coverage today — needs ratio formulation against quota target.",),
    ),
    SalesKPI(
        kpi_id="opp_win_rate",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Opportunity Win Rate (Close Rate)",
        target_text=">25%",
        target_value=0.25,
        target_unit="%",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id="00OTb000008neHRMAY",
        sf_source_name="Scorecard · Win Rate Trend · 8Q",
        coverage_status="exists",
        definition="Won opps / (Won + Lost) opps closed in the period.",
        why_it_matters="Velocity vs efficiency tradeoff — if pipeline builds but win rate drops, sales-execution issue.",
        soql_hint="COUNT(IsWon=true) / COUNT(IsClosed=true) BY CloseDate quarter",
    ),
    SalesKPI(
        kpi_id="stage_conversion",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Opportunity Stage Conversion Rate",
        target_text=">70% stage-to-stage",
        target_value=0.70,
        target_unit="%",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id="00OTb000008gUrVMAU",
        sf_source_name="SD Win Rate by Stage",
        coverage_status="partial",
        definition="Per-stage advancement rate computed from OpportunityFieldHistory.",
        why_it_matters="Identifies bottleneck stage. Stage 3 specifically flagged in 1.4.2 of AP framework.",
        soql_hint="OpportunityFieldHistory: count of advances vs entries per stage",
        caveats=(
            "Memory: ~70% of close-wons skip Stage 4 in OFH; partial close-won population only.",
        ),
    ),
    SalesKPI(
        kpi_id="opp_age",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Opportunity Age / Stale Opportunities",
        target_text="<120 days avg",
        target_value=120.0,
        target_unit="days",
        impact="MEDIUM",
        primary_bucket="Metrics",
        direction="lower_is_better",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="exists",
        definition="Average days since CreatedDate for open opportunities; flag stale ones.",
        why_it_matters="Aging pipeline = dead pipeline. Active hygiene metric for ops cadence.",
        soql_hint="AVG(TODAY() - CreatedDate) WHERE IsClosed=false",
    ),
    SalesKPI(
        kpi_id="opp_source_effectiveness",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Opportunity Source Effectiveness",
        target_text="Track & Optimize",
        target_value=None,
        target_unit=None,
        impact="MEDIUM",
        primary_bucket="Metrics",
        direction="track",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="exists",
        definition="Win rate × ARR per LeadSource; reveals which sources convert to revenue.",
        why_it_matters="Marketing/BDR investment decisions; informs lead-routing.",
        soql_hint="Group by LeadSource, sum ARR, count won/lost",
    ),
    SalesKPI(
        kpi_id="sales_cycle_length",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Sales Cycle Length (Avg Time to Close)",
        target_text="<90 days",
        target_value=90.0,
        target_unit="days",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="lower_is_better",
        motion_filter="land_expand",
        sf_source_id="00OTb000008ngUXMAY",
        sf_source_name="Scorecard · Sales Cycle Length 8Q",
        coverage_status="exists",
        definition="Average days from CreatedDate to CloseDate for Won opportunities.",
        why_it_matters="Cycle compression = sales velocity. The 90d target is aggressive for SimCorp's typical complex sale.",
        soql_hint="AVG(CloseDate - CreatedDate) WHERE IsWon=true",
        caveats=(
            "90d target may be Land-only; Land+Expand cycles often >180d in this org. Confirm scope.",
        ),
    ),
    SalesKPI(
        kpi_id="time_in_stage",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Time deals spent in each stage",
        target_text="Baseline & Optimize",
        target_value=None,
        target_unit="days",
        impact="MEDIUM",
        primary_bucket="Metrics",
        direction="track",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="missing",
        definition="Per-stage dwell time computed from OpportunityFieldHistory.",
        why_it_matters="Identifies process friction by stage. Pairs with stage_conversion.",
        soql_hint="OFH: stage_in_date to stage_out_date by stage",
    ),
    SalesKPI(
        kpi_id="closed_won_avg_deal_size",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Closed Won Average Deal Size by month",
        target_text=">$500K",  # Excel had ">00K" — likely typo for $500K or $100K; use $500K conservatively
        target_value=500000.0,
        target_unit="USD",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id="00OTb000008msRJMAY",
        sf_source_name="KPI · Closed Won ARR This Quarter (L+E)",
        coverage_status="exists",
        definition="Average ARR per Won opportunity, grouped by close month.",
        why_it_matters="Mix shift signal — declining avg deal size = downmarket drift or smaller-bite renewals.",
        soql_hint="AVG(APTS_Opportunity_ARR__c) WHERE IsWon=true GROUP BY CALENDAR_MONTH(CloseDate)",
        caveats=("Excel said '>00K' — assumed >$500K; confirm with Richard before signing off.",),
    ),
    SalesKPI(
        kpi_id="closed_won_value_tier",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Number of close won deals by value tier",
        target_text="Track distribution",
        target_value=None,
        target_unit="count",
        impact="MEDIUM",
        primary_bucket="Metrics",
        direction="track",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="exists",
        definition="Count of Won opps in value tiers (e.g. <$100K, $100K-$500K, $500K-$1M, >$1M).",
        why_it_matters="Mix-shift visibility — are we winning more big deals or more small deals?",
        soql_hint="CASE-WHEN bucketing on APTS_Opportunity_ARR__c, COUNT(*) by tier",
    ),
    SalesKPI(
        kpi_id="new_opps_by_region",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Number of New opportunities created by region",
        target_text="100/month",
        target_value=100.0,
        target_unit="count/month",
        impact="MEDIUM",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="missing",
        definition="Count of Opportunity records where CreatedDate falls in month, by Account.Region__c.",
        why_it_matters="Pipeline build motion check. Below 100/month = thin pipeline ahead.",
        soql_hint="COUNT(Id) WHERE CreatedDate IN <month> GROUP BY Account.Region__c",
    ),
    SalesKPI(
        kpi_id="stage3_approvals_compliance",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Stage 3 approvals by month",
        target_text="100% compliance",
        target_value=1.0,
        target_unit="% compliance",
        impact="MEDIUM",
        primary_bucket="Process",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="exists",
        definition="Count of Stage 3+ Land deals with required Commercial Approval submitted.",
        why_it_matters="Governance gate compliance — Land deals MUST have Commercial Approval per the 8-stage process.",
        soql_hint="Stage 3+ Land+Expand opps with Stage_20_Approval__c=true divided by eligible Stage 3+ opps",
        caveats=("Per memory: every Land deal requires Commercial Approval — non-negotiable.",),
    ),
    SalesKPI(
        kpi_id="stage3_acv_value",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="ACV of Stage 3 approvals",
        target_text="Track & Monitor",
        target_value=None,
        target_unit="USD",
        impact="MEDIUM",
        primary_bucket="Metrics",
        direction="track",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="exists",
        definition="Total ARR value of Stage 3+ deals that received Commercial Approval in the period.",
        why_it_matters="Approval committee capacity vs deal flow visibility.",
        soql_hint="SUM(APTS_Opportunity_ARR__c) WHERE Stage>=3 AND Approval_Status__c='Approved'",
    ),
    SalesKPI(
        kpi_id="commercial_approval_to_close_time",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Commercial approval to close time",
        target_text="<30 days",
        target_value=30.0,
        target_unit="days",
        impact="HIGH",
        primary_bucket="Process",
        direction="lower_is_better",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="exists",
        definition="Days from Commercial Approval received to CloseDate for Won deals.",
        why_it_matters="Post-approval bottleneck signal — friction is in legal/contracting if this stretches.",
        soql_hint="DATEDIFF(CloseDate, Stage_20_Approval_Date__c) WHERE IsWon=true",
    ),
    SalesKPI(
        kpi_id="forecast_accuracy",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Forecast Accuracy",
        target_text="±5%",
        target_value=0.05,
        target_unit="% deviation",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="lower_is_better",
        motion_filter="land_expand",
        sf_source_id="00OTb000008ngO5MAI",
        sf_source_name="FA · Forecast Accuracy 8Q",
        coverage_status="exists",
        definition="Absolute deviation: |Forecast at start of Q − Closed Won by end of Q| / Forecast.",
        why_it_matters="The headline ops-discipline metric. Wide deviation = rep/manager discipline issue or surprise pipeline movements.",
        soql_hint="Compare snapshot Forecast (e.g. ForecastingItem at -90d) vs actuals (Closed Won) at +90d",
    ),
    SalesKPI(
        kpi_id="partner_opps_pct",
        process_area="1.4 Opportunity Mgmt — Forecasting",
        name="Partner Opportunities",
        target_text="20% of pipeline",
        target_value=0.20,
        target_unit="% of pipeline",
        impact="MEDIUM",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="exists",
        definition="ARR of Partner-sourced opportunities / total open pipeline ARR.",
        why_it_matters="Channel-mix discipline; partner pipe expands TAM without hiring direct sellers.",
        soql_hint="SUM(ARR) WHERE LeadSource='Partner' OR Partner__c != null / total open",
    ),
    # ── 1.8 Renewals (4 KPIs) ──────────────────────────────────────────────
    SalesKPI(
        kpi_id="renewal_retention_rate",
        process_area="1.8 Renewals",
        name="Renewals per quarter detailing term length",
        target_text="95% retention",
        target_value=0.95,
        target_unit="% retained",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="renewal",
        sf_source_id="00OTb000008mwujMAA",
        sf_source_name="Cockpit · Renewal Health by FQ",
        coverage_status="partial",
        definition="(Renewal_ACV won) / (Renewal_ACV due in period). Term-length detail breaks down 1Y vs 3Y vs 5Y deals.",
        why_it_matters="Existing-base preservation; gross retention. <95% indicates churn risk.",
        soql_hint="SUM(APTS_Renewal_ACV__c) WHERE IsWon AND Type='Renewal' / SUM(APTS_Renewal_ACV__c) due",
        caveats=("Use APTS_Renewal_ACV__c; never blend with APTS_Opportunity_ARR__c.",),
    ),
    SalesKPI(
        kpi_id="renewals_mom_trend",
        process_area="1.8 Renewals",
        name="Renewals by month over year",
        target_text="Track & Trend",
        target_value=None,
        target_unit="ACV",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="track",
        motion_filter="renewal",
        sf_source_id="00OTb000008muuXMAQ",
        sf_source_name="Renewal ACV by Fiscal Quarter",
        coverage_status="exists",
        definition="Monthly Renewal ACV over rolling 12 months.",
        why_it_matters="Seasonality + lumpiness check on renewal book.",
        soql_hint="SUM(APTS_Renewal_ACV__c) GROUP BY CALENDAR_MONTH(CloseDate) WHERE Type='Renewal'",
    ),
    SalesKPI(
        kpi_id="existing_arr_run_rate",
        process_area="1.8 Renewals",
        name="Existing ARR (Run Rate) Indexed",
        target_text="Track & Monitor",
        target_value=None,
        target_unit="ARR",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="renewal",
        sf_source_id="Apttus_Config2__AssetLineItem__c",
        sf_source_name="Apttus Asset Line Item",
        coverage_status="exists",
        definition="Active subscription ARR run-rate, indexed to a baseline period.",
        why_it_matters="Existing-base health; pairs with NRR.",
        soql_hint="SUM(APTS_Asset_Line_Item_ARR__c) WHERE Apttus_Config2__IsInactive__c=false AND Apttus_Config2__EndDate__c >= TODAY",
        caveats=("Installed-base ARR from Apttus assets; keep separate from Renewal opportunity ACV.",),
    ),
    SalesKPI(
        kpi_id="indexation_arr_growth",
        process_area="1.8 Renewals",
        name="ARR growth attributed to indexation by Quarter",
        target_text="2-3% annually",
        target_value=0.025,
        target_unit="% annual",
        impact="MEDIUM",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="renewal",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="missing",
        definition="Year-over-year ARR uplift attributable to contractual price indexation (CPI/RPI clauses).",
        why_it_matters="Pure-mechanical revenue growth before any sales motion. Ops should be tracking this separately from new-business.",
        soql_hint="Custom field on Asset / Subscription; sum of Indexation_Uplift_Amount__c over period",
        caveats=(
            "Real gap — only 2 SF reports match 'Indexation' search. Likely needs new build OR lives in Finance system.",
        ),
    ),
    # ── 1.9 Conversion (6 KPIs) ────────────────────────────────────────────
    SalesKPI(
        kpi_id="ilf_arr_pipeline",
        process_area="1.9 Conversion",
        name="ILF ARR Pipes By Quarter",
        target_text="$X Million",  # Excel had " Million" — value redacted
        target_value=None,
        target_unit="USD millions",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="partial",
        definition="Open pipeline ARR attributed to In-Life Funnel (ILF) — likely existing-customer expansion deals.",
        why_it_matters="Expansion motion health; differentiates new-logo from expand pipeline.",
        soql_hint="SUM(APTS_Opportunity_ARR__c) WHERE Type='Expand' OR Funnel__c='ILF'",
        caveats=(
            "454 SF reports match 'ILF' literal — needs disambiguation. ILF target value redacted in Excel.",
        ),
    ),
    SalesKPI(
        kpi_id="alf_arr_pipeline",
        process_area="1.9 Conversion",
        name="ALF ARR By Quarter",
        target_text="$X Million",
        target_value=None,
        target_unit="USD millions",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="partial",
        definition="Open pipeline ARR for Acquired/Land Funnel (ALF) — new-logo / Land deals.",
        why_it_matters="New-logo motion health.",
        soql_hint="SUM(APTS_Opportunity_ARR__c) WHERE Type='Land' OR Funnel__c='ALF'",
        caveats=("374 SF reports match 'ALF'; needs disambiguation.",),
    ),
    SalesKPI(
        kpi_id="new_customer_reporting",
        process_area="1.9 Conversion",
        name="New Customer reporting amount by month and value and region",
        target_text="Track & Report",
        target_value=None,
        target_unit="USD",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="track",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="exists",
        definition="Land Won deals broken out by close month × ARR tier × Region.",
        why_it_matters="New-logo acquisition pace + territory mix.",
        soql_hint="Won + Type='Land', GROUP BY CALENDAR_MONTH, ARR tier, Account.Region__c",
    ),
    SalesKPI(
        kpi_id="cross_sell_to_acquired",
        process_area="1.9 Conversion",
        name="ARR from Cross Selling to Acquired Business",
        target_text="$X Million",
        target_value=None,
        target_unit="USD millions",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="exists",
        definition="ARR Won via Expand motion on Accounts originally acquired via M&A (Axioma, etc.).",
        why_it_matters="M&A synergy realization; CFO-level metric for acquisition economics.",
        soql_hint="SUM(APTS_RUS_Axioma_Order_Inflow__c) WHERE Type IN ('Land','Expand')",
        caveats=("Uses Axioma Order Inflow as the acquired-business cross-sell signal.",),
    ),
    SalesKPI(
        kpi_id="synergy_deals_won",
        process_area="1.9 Conversion",
        name="Synergy deals close won",
        target_text="10 deals/quarter",
        target_value=10.0,
        target_unit="deals/quarter",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="partial",
        definition="Count of Won opportunities flagged as Synergy (cross-product or post-M&A).",
        why_it_matters="Synergy realization; commitment to the Board on deal volume.",
        soql_hint="COUNT(Id) WHERE IsWon AND Synergy__c=true GROUP BY FISCAL_QUARTER(CloseDate)",
        caveats=("5 SF reports match 'Synergy'; needs disambiguation. Synergy__c field assumed.",),
    ),
    SalesKPI(
        kpi_id="synergy_deals_pipe",
        process_area="1.9 Conversion",
        name="Synergy deals in pipe",
        target_text="30 deals/quarter",
        target_value=30.0,
        target_unit="deals/quarter",
        impact="MEDIUM",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="partial",
        definition="Count of open opportunities flagged as Synergy.",
        why_it_matters="Coverage check — 30 in pipe vs 10/qtr won implies 33% conversion target.",
        soql_hint="COUNT(Id) WHERE IsClosed=false AND Synergy__c=true",
    ),
    # ── 1.10 Cancellation (2 KPIs) ─────────────────────────────────────────
    SalesKPI(
        kpi_id="lost_arr_quarterly",
        process_area="1.10 Cancellation",
        name="Lost ARR By Quarter (with reason)",
        target_text="<5% annually",
        target_value=0.05,
        target_unit="% of base annual",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="lower_is_better",
        motion_filter="renewal",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="exists",
        definition="Sum of ACV lost to non-renewal or cancellation, broken down by Reason_Won_Lost__c.",
        why_it_matters="Gross churn metric. Pairs with renewal_retention_rate (denominator: total renewable base).",
        soql_hint="SUM(APTS_Renewal_ACV__c) WHERE IsClosed AND IsWon=false AND Type='Renewal' GROUP BY Reason_Won_Lost__c",
        caveats=("Use ACV (Renewal field), not ARR.",),
    ),
    SalesKPI(
        kpi_id="business_at_risk",
        process_area="1.10 Cancellation",
        name="Business At Risk By Quarter",
        target_text="<10% of ARR",
        target_value=0.10,
        target_unit="% of ARR",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="lower_is_better",
        motion_filter="renewal",
        sf_source_id="Apttus_Config2__AssetLineItem__c + Account.Risk_of_Potential_Termination__c",
        sf_source_name="Apttus Asset Line Item + Account termination risk",
        coverage_status="exists",
        definition="Active subscription ARR with health flag = at-risk (manual or scored).",
        why_it_matters="Early-warning churn signal; pairs with QBR cadence.",
        soql_hint="SUM(APTS_Asset_Line_Item_ARR__c) WHERE active asset AND Account.Risk_of_Potential_Termination__c IN ('High','Medium')",
        caveats=("Active-base ARR risk, not Renewal opportunity ACV.",),
    ),
    # ── 1.14 Product/Pricing (3 KPIs) ──────────────────────────────────────
    SalesKPI(
        kpi_id="one_off_revenues",
        process_area="1.14 Product/Pricing",
        name="One Off Revenues by Quarter",
        target_text="Track & Monitor",
        target_value=None,
        target_unit="USD",
        impact="MEDIUM",
        primary_bucket="Metrics",
        direction="track",
        motion_filter="all",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="missing",
        definition="Non-ARR revenue (one-off services, training, custom dev) booked in the quarter.",
        why_it_matters="Revenue mix discipline; one-offs don't compound but they fund delivery margin.",
        soql_hint="SUM(One_Off_Amount__c) or sum of OpportunityLineItem where ProductFamily='Services'",
        caveats=("Real gap — 0 SF reports match. May live in Finance system, not SF.",),
    ),
    SalesKPI(
        kpi_id="ps_arr_attach",
        process_area="1.14 Product/Pricing",
        name="PS ARR by Quarter",
        target_text="15% attach rate",
        target_value=0.15,
        target_unit="% attach to license",
        impact="MEDIUM",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="land_expand",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="exists",
        definition="Professional Services ARR / License ARR for Won deals in period.",
        why_it_matters="PS attach predicts implementation success and downstream renewal probability.",
        soql_hint="SUM(APTS_PS_Recurring_ACV_Display__c) / SUM(APTS_Opportunity_ARR__c) WHERE Type IN ('Land','Expand')",
    ),
    SalesKPI(
        kpi_id="saas_arr_yoy_growth",
        process_area="1.14 Product/Pricing",
        name="SaaS ARR by Quarter",
        target_text="Growth >20% YoY",
        target_value=0.20,
        target_unit="% YoY",
        impact="HIGH",
        primary_bucket="Metrics",
        direction="higher_is_better",
        motion_filter="all",
        sf_source_id=None,
        sf_source_name=None,
        coverage_status="exists",
        definition="SaaS-deployment ARR growth YoY (vs On-Prem). Strategic shift metric.",
        why_it_matters="Cloud transformation is a top-line strategic metric for SimCorp; CRO + Board view.",
        soql_hint="SUM(APTS_RH_ASP_Annual__c) over time, YoY %",
    ),
)


GRAPH = RWKPIGraph(kpis=_KPIS)


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────


def find_kpi(kpi_id: str) -> SalesKPI | None:
    return next((k for k in GRAPH.kpis if k.kpi_id == kpi_id), None)


def kpis_by_process_area(area: ProcessArea) -> tuple[SalesKPI, ...]:
    return tuple(k for k in GRAPH.kpis if k.process_area == area)


def kpis_by_status(status: CoverageStatus) -> tuple[SalesKPI, ...]:
    return tuple(k for k in GRAPH.kpis if k.coverage_status == status)


def gaps() -> tuple[SalesKPI, ...]:
    return kpis_by_status("missing")


def high_impact() -> tuple[SalesKPI, ...]:
    return tuple(k for k in GRAPH.kpis if k.impact == "HIGH")


def to_json() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "source_xlsx": KPI_SOURCE_XLSX,
        "audience": "Richard Wyeth, MD Sales Operations (org-wide view)",
        "sf_org": SF_ORG,
        "kpis": [k.__dict__ for k in GRAPH.kpis],
    }


def to_llm_context() -> str:
    """Compact markdown summary for LLM prompt inclusion."""
    lines: list[str] = [
        f"# RW (Richard Wyeth, MD Sales Ops) Target KPIs — canonical (schema v{SCHEMA_VERSION})",
        "",
        f"Source: {KPI_SOURCE_XLSX} (sheet `RW - KPIs`)",
        "Audience: VP Ops view, org-wide (not personal book)",
        "",
        "## KPIs by process area",
        "",
    ]
    for area in (
        "1.4 Opportunity Mgmt — Forecasting",
        "1.8 Renewals",
        "1.9 Conversion",
        "1.10 Cancellation",
        "1.14 Product/Pricing",
    ):
        ks = kpis_by_process_area(area)
        if not ks:
            continue
        lines.append(f"### {area}  ({len(ks)} KPIs)")
        for k in ks:
            status = {"exists": "✅", "partial": "⚠️", "missing": "❌"}[k.coverage_status]
            lines.append(
                f"  {status} {k.kpi_id} — {k.name}  (target: {k.target_text}, impact: {k.impact}, motion: {k.motion_filter})"
            )
        lines.append("")
    lines += [
        "## Coverage roll-up",
        f"  - exists in SF reports: {len(kpis_by_status('exists'))}",
        f"  - partial (needs filter/aggregation work): {len(kpis_by_status('partial'))}",
        f"  - missing (real gaps, new build): {len(kpis_by_status('missing'))}",
        "",
        "## Cardinal rules (inherited from SimCorp shared agent directives)",
        "  - APTS_Opportunity_ARR__c for Land+Expand. APTS_Renewal_ACV__c for Renewal. Never blend.",
        "  - Multi-currency: trust SF Report `s!field` aggregates, not raw SOQL SUM.",
        "  - Type filter discipline ~98% in this org (per 2026-05-06 baseline).",
        "",
        "When the LLM cites any KPI, use the EXACT kpi_id — no paraphrasing.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(to_llm_context())
    print()
    print("=== Sample queries ===")
    print(f"Total KPIs: {len(GRAPH.kpis)}")
    print("By process area:")
    for area in (
        "1.4 Opportunity Mgmt — Forecasting",
        "1.8 Renewals",
        "1.9 Conversion",
        "1.10 Cancellation",
        "1.14 Product/Pricing",
    ):
        print(f"  {area}: {len(kpis_by_process_area(area))}")
    print("\nCoverage:")
    print(f"  exists: {len(kpis_by_status('exists'))}")
    print(f"  partial: {len(kpis_by_status('partial'))}")
    print(f"  missing: {len(kpis_by_status('missing'))}")
    print(f"\nHigh-impact KPIs: {len(high_impact())}")
    print(f"Gaps (missing): {[k.kpi_id for k in gaps()]}")
    print(f"\nJSON size: {len(json.dumps(to_json())):,} chars")
