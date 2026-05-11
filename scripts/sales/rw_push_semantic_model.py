"""Create the `sm_sales_kpis_rw` semantic model in Fabric.

Direct Lake on `lkh_sales_kpis_rw`. Includes Opportunity, stage/forecast
transition facts, and active Apttus asset line items for renewal-base ARR.
measures in Phase 1 (the subset of the 31 RW KPIs that's computable
from Opportunity + Account + User alone — no OFH, Approval, or Asset
data yet). Region slicer-ready via d_region.

Phase 2 (deferred): add OpportunityFieldHistory for stage_conversion +
time_in_stage, ApprovalProcess for commercial-approval timing, and
Asset/Subscription for indexation.

Same Fabric REST pattern as scripts/workforce/wf_push_semantic_model.py.

Usage:
    python3 scripts/sales/rw_push_semantic_model.py

Idempotent: if the model exists, updates definition in place; else creates.
"""

from __future__ import annotations

import base64
import json
import time

import requests
from azure.identity import AzureCliCredential

WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"
LAKEHOUSE_ID = "50f1721e-6b2e-44db-a1a7-7b8209c7a77b"  # lkh_sales_kpis_rw
MODEL_NAME = "sm_sales_kpis_rw"

FABRIC = "https://api.fabric.microsoft.com"
FABRIC_RES = "https://api.fabric.microsoft.com/.default"
PBI = "https://api.powerbi.com"
PBI_RES = "https://analysis.windows.net/powerbi/api/.default"

# Power BI custom numeric formats parse bare letters as formatting tokens.
# Keep the EUR prefix quoted as a literal or Desktop renders the format string
# itself in card/table cells.
CURRENCY_M_FORMAT = '"EUR" #,0,,.0"M";("EUR" #,0,,.0"M");"-"'
NON_OMITTED_FORECAST_FILTER = 'NOT ( f_opportunity[forecast_category] = "Omitted" )'
CORE_STAGE_TRANSITION_FILTER = "f_stage_transition[from_stage_num] IN { 1, 2, 3, 4, 5, 6 }"


def _b64(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return base64.b64encode(data).decode("ascii")


def build_pbism() -> dict:
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "5.0",
        "settings": {"qnaEnabled": False},
    }


def build_model_bim() -> dict:
    onelake_url = f"https://onelake.dfs.fabric.microsoft.com/{WORKSPACE_ID}/{LAKEHOUSE_ID}"
    database_query = "\n".join(
        [
            "let",
            f'  Source = AzureStorage.DataLake("{onelake_url}")',
            "in",
            "  Source",
        ]
    )

    def col(
        name: str,
        dtype: str,
        source: str | None = None,
        *,
        key: bool = False,
        fmt: str | None = None,
        sort_by: str | None = None,
    ) -> dict:
        c: dict = {
            "name": name,
            "dataType": dtype,
            "sourceColumn": source or name,
            "summarizeBy": "none",
        }
        if key:
            c["isKey"] = True
        if fmt:
            c["formatString"] = fmt
        if sort_by:
            c["sortByColumn"] = sort_by
        return c

    def dl_partition(table_name: str) -> dict:
        return {
            "name": f"{table_name}-p1",
            "mode": "directLake",
            "source": {
                "type": "entity",
                "entityName": table_name,
                "expressionSource": "DatabaseQuery",
            },
        }

    # Window-bound delta helper: 3 windows × N families.
    # 1d / 7d / FQTD (fiscal-quarter-to-date — start of current calendar quarter).
    _windows = {
        "1d": "TODAY() - 1",
        "7d": "TODAY() - 7",
        "FQTD": "DATE(YEAR(TODAY()), CEILING(MONTH(TODAY())/3, 1)*3 - 2, 1)",
    }
    non_omitted = NON_OMITTED_FORECAST_FILTER
    core_stage = CORE_STAGE_TRANSITION_FILTER

    def _window_measures():
        out = []
        for label, since in _windows.items():
            out.append(
                {
                    "name": f"New Opps Count {label}",
                    "expression": f"CALCULATE ( COUNTROWS ( f_opportunity ), {non_omitted}, f_opportunity[created_date] >= {since} )",
                    "formatString": "#,0",
                    "description": f"Non-Omitted opps created in the last {label} window.",
                }
            )
            out.append(
                {
                    "name": f"Closed Won Count {label}",
                    "expression": f"CALCULATE ( COUNTROWS ( f_opportunity ), f_opportunity[is_won] = TRUE(), f_opportunity[close_date] >= {since} )",
                    "formatString": "#,0",
                    "description": f"Opps won and closed in the last {label} window.",
                }
            )
            out.append(
                {
                    "name": f"Closed Lost Count {label}",
                    "expression": f"CALCULATE ( COUNTROWS ( f_opportunity ), f_opportunity[is_closed] = TRUE(), f_opportunity[is_won] = FALSE(), f_opportunity[close_date] >= {since} )",
                    "formatString": "#,0",
                    "description": f"Opps closed-lost in the last {label} window.",
                }
            )
        return out

    def _stage_window_measures():
        out = []
        for label, since in _windows.items():
            out.append(
                {
                    "name": f"Stage Moves Count {label}",
                    "expression": (
                        "CALCULATE ( COUNTROWS ( f_stage_transition ), "
                        f"{core_stage}, "
                        f"f_stage_transition[transition_at] >= {since}, "
                        "TREATAS ( "
                        f"CALCULATETABLE ( VALUES ( f_opportunity[opp_id] ), {non_omitted} ), "
                        "f_stage_transition[opp_id] ) )"
                    ),
                    "formatString": "#,0",
                    "description": f"Stage transitions (any direction) in the last {label} window, excluding current Omitted pipeline.",
                }
            )
            out.append(
                {
                    "name": f"Backward Moves Count {label}",
                    "expression": (
                        "CALCULATE ( COUNTROWS ( f_stage_transition ), "
                        f"{core_stage}, "
                        'f_stage_transition[direction] = "backward", '
                        f"f_stage_transition[transition_at] >= {since}, "
                        "TREATAS ( "
                        f"CALCULATETABLE ( VALUES ( f_opportunity[opp_id] ), {non_omitted} ), "
                        "f_stage_transition[opp_id] ) )"
                    ),
                    "formatString": "#,0",
                    "description": f"Backward stage transitions in the last {label} window, excluding current Omitted pipeline.",
                }
            )
            out.append(
                {
                    "name": f"Stage Moves ARR {label}",
                    "expression": (
                        "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), "
                        f"{non_omitted}, "
                        "TREATAS ( "
                        f"CALCULATETABLE ( VALUES ( f_stage_transition[opp_id] ), {core_stage}, f_stage_transition[transition_at] >= {since} ), "
                        "f_opportunity[opp_id] ) )"
                    ),
                    "formatString": CURRENCY_M_FORMAT,
                    "description": f"ARR of non-Omitted opps with any stage move in the last {label} window.",
                }
            )
        return out

    def _heatmap_color_expression(
        value_measure: str,
        *,
        table: str,
        group_columns: tuple[str, ...],
        palette: tuple[str, str, str, str],
    ) -> str:
        groups = ", ".join(f"{table}[{column}]" for column in group_columns)
        low, mid, high, max_color = palette
        return (
            f"VAR _value = [{value_measure}] "
            "VAR _max_value = "
            f"MAXX ( SUMMARIZE ( ALLSELECTED ( {table} ), {groups}, "
            f'"__rw_heat_value", [{value_measure}] ), [__rw_heat_value] ) '
            "VAR _pct = DIVIDE ( _value, _max_value ) "
            "RETURN "
            "SWITCH ( "
            "TRUE(), "
            'ISBLANK ( _value ) || _value = 0, "#FFFFFF", '
            f'_pct >= 0.75, "{max_color}", '
            f'_pct >= 0.50, "{high}", '
            f'_pct >= 0.25, "{mid}", '
            f'"{low}" )'
        )

    def _heatmap_color_measure(
        name: str,
        value_measure: str,
        *,
        table: str,
        group_columns: tuple[str, ...],
        palette: tuple[str, str, str, str],
        description: str,
    ) -> dict:
        return {
            "name": name,
            "expression": _heatmap_color_expression(
                value_measure,
                table=table,
                group_columns=group_columns,
                palette=palette,
            ),
            "description": description,
        }

    blue_heat = ("#EEF4FA", "#C9DBEF", "#6F9FD2", "#083EA7")
    green_heat = ("#EEF8F0", "#CBE8D0", "#79B982", "#1F6F3B")
    amber_heat = ("#FFF7E6", "#F3D28A", "#E6A329", "#A65E00")
    red_heat = ("#FFF0EE", "#F4B8B3", "#DF6B61", "#8B2C25")

    # Phase 1 measures — computable from f_opportunity alone. Names use
    # "Total"/"Avg"/"Pct"/"Count" prefixes so they don't collide with raw
    # column names (lesson from sm_workforce_rw).
    measures = [
        # Headlines (Land + Expand → ARR)
        {
            "name": "Total Closed Won ARR",
            "expression": 'CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] IN { "Land", "Expand" } )',
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: forecast_closed_won. ARR field, Land + Expand only.",
        },
        {
            "name": "Total Open Pipeline ARR",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[is_closed] = FALSE(), f_opportunity[motion_type] IN { "Land", "Expand" } )'
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: pipeline_coverage_3x (numerator). Open Land + Expand ARR, excluding current Omitted pipeline.",
        },
        _heatmap_color_measure(
            "Total Open Pipeline ARR Heat Color",
            "Total Open Pipeline ARR",
            table="f_opportunity",
            group_columns=("region", "motion_type"),
            palette=blue_heat,
            description="Field-value background color for Region x Motion Open ARR heatmaps.",
        ),
        {
            "name": "Total Closed Lost ARR",
            "expression": 'CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), f_opportunity[is_closed] = TRUE(), f_opportunity[is_won] = FALSE(), f_opportunity[motion_type] IN { "Land", "Expand" } )',
            "formatString": CURRENCY_M_FORMAT,
        },
        {
            "name": "Total Closed Won ARR FYTD",
            "expression": "CALCULATE ( [Total Closed Won ARR], REMOVEFILTERS ( d_calendar ), DATESBETWEEN ( d_calendar[date], DATE ( YEAR ( TODAY () ), 1, 1 ), TODAY () ) )",
            "formatString": CURRENCY_M_FORMAT,
            "description": "Current fiscal-year-to-date Closed Won ARR, Land + Expand only. FY = calendar year per d_calendar.",
        },
        {
            "name": "Total Closed Lost ARR FYTD",
            "expression": "CALCULATE ( [Total Closed Lost ARR], REMOVEFILTERS ( d_calendar ), DATESBETWEEN ( d_calendar[date], DATE ( YEAR ( TODAY () ), 1, 1 ), TODAY () ) )",
            "formatString": CURRENCY_M_FORMAT,
            "description": "Current fiscal-year-to-date Closed Lost ARR, Land + Expand only. FY = calendar year per d_calendar.",
        },
        # Win rate
        {
            "name": "Win Rate ARR",
            "expression": "DIVIDE ( [Total Closed Won ARR], [Total Closed Won ARR] + [Total Closed Lost ARR] )",
            "formatString": "0.0%",
            "description": "RW KPI: opp_win_rate (ARR-weighted). Target >25%.",
        },
        {
            "name": "Win Rate ARR FYTD",
            "expression": "DIVIDE ( [Total Closed Won ARR FYTD], [Total Closed Won ARR FYTD] + [Total Closed Lost ARR FYTD] )",
            "formatString": "0.0%",
            "description": "Current fiscal-year-to-date ARR-weighted win rate, Land + Expand only.",
        },
        {
            "name": "Win Rate Count",
            "expression": 'DIVIDE ( CALCULATE ( COUNTROWS ( f_opportunity ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] IN { "Land", "Expand" } ), CALCULATE ( COUNTROWS ( f_opportunity ), f_opportunity[is_closed] = TRUE(), f_opportunity[motion_type] IN { "Land", "Expand" } ) )',
            "formatString": "0.0%",
            "description": "RW KPI: opp_win_rate (count-based). Target >25%.",
        },
        # Velocity / size
        {
            "name": "Avg Deal Size Won",
            "expression": 'CALCULATE ( AVERAGE ( f_opportunity[arr_org_ccy] ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] IN { "Land", "Expand" } )',
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: closed_won_avg_deal_size. Target >$500K (verify with Richard).",
        },
        {
            "name": "Avg Sales Cycle Days",
            "expression": 'CALCULATE ( AVERAGEX ( f_opportunity, DATEDIFF ( f_opportunity[created_date], f_opportunity[close_date], DAY ) ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] IN { "Land", "Expand" } )',
            "formatString": "0",
            "description": "RW KPI: sales_cycle_length. Target <90d (likely Land-only; verify scope).",
        },
        {
            "name": "Avg Open Opp Age Days",
            "expression": (
                "CALCULATE ( AVERAGEX ( f_opportunity, DATEDIFF ( f_opportunity[created_date], TODAY (), DAY ) ), "
                f"{non_omitted}, "
                'f_opportunity[is_closed] = FALSE(), f_opportunity[motion_type] IN { "Land", "Expand" } )'
            ),
            "formatString": "0",
            "description": "RW KPI: opp_age. Non-Omitted Land + Expand open opps; target <120d avg.",
        },
        {
            "name": "Open Opp Count",
            "expression": f"CALCULATE ( COUNTROWS ( f_opportunity ), {non_omitted}, f_opportunity[is_closed] = FALSE() )",
            "formatString": "#,0",
        },
        # Stage 3+ proxy
        {
            "name": "Stage 3 Plus ARR",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[is_closed] = FALSE(), f_opportunity[motion_type] IN { "Land", "Expand" }, NOT ( f_opportunity[stage_name] IN { "1. Prospecting", "2. Discovery" } ) )'
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: stage3_acv_value (proxy). Stage 3+ open ARR, excluding current Omitted pipeline.",
        },
        {
            "name": "S3 Plus Open ACV",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[acv_org_ccy] ), "
                f"{non_omitted}, "
                "f_opportunity[is_closed] = FALSE(), "
                'f_opportunity[stage_name] IN { "3 - Engagement", "4 - Shortlisted", "5 - Preferred", "6 - Contracting", "7 - Sales Ops QC" } )'
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "S3+ open ACV (companion to Stage 3 Plus ARR; covers Renewal motion via ACV field). Real stage-name list verified vs OpportunityStage.",
        },
        # ── Forecast tab support ───────────────────────────────────────
        {
            "name": "Days Remaining In FQ",
            "expression": (
                "VAR _today = TODAY () "
                "VAR _q_end = EOMONTH ( _today, 3 - MOD ( MONTH ( _today ) - 1, 3 ) - 1 ) "
                "RETURN DATEDIFF ( _today, _q_end, DAY )"
            ),
            "formatString": "0",
            "description": "Calendar days from today to end-of-current-fiscal-quarter (FY = calendar year per d_calendar).",
        },
        {
            "name": "Total Open Pipeline Value",
            "expression": (
                "CALCULATE ( "
                'SUMX ( f_opportunity, IF ( f_opportunity[motion_type] = "Renewal", '
                "f_opportunity[acv_org_ccy], f_opportunity[arr_org_ccy] ) ), "
                f"{non_omitted}, "
                "f_opportunity[is_closed] = FALSE() )"
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": (
                "Open pipeline value combining ARR (Land + Expand) and ACV (Renewal) per "
                "SimCorp business rules — never blend, but render in one column when "
                "comparing motions side-by-side. Use ONLY for cross-motion visuals."
            ),
        },
        # Partner mix
        {
            "name": "Partner ARR",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[is_closed] = FALSE(), CONTAINSSTRING ( LOWER ( f_opportunity[lead_source] ), "partner" ), f_opportunity[motion_type] IN { "Land", "Expand" } )'
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: partner_opps_pct numerator. Non-Omitted open Land + Expand ARR where lead source contains partner.",
        },
        _heatmap_color_measure(
            "Partner ARR Heat Color",
            "Partner ARR",
            table="f_opportunity",
            group_columns=("region", "motion_type"),
            palette=amber_heat,
            description="Field-value background color for Region x Motion Partner ARR heatmaps.",
        ),
        {
            "name": "Partner Pct",
            "expression": "DIVIDE ( [Partner ARR], [Total Open Pipeline ARR] )",
            "formatString": "0.0%",
            "description": "RW KPI: partner_opps_pct. Target 20% of pipeline.",
        },
        {
            "name": "Total Land Expand ARR",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" } )'
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "Non-Omitted Land + Expand ARR in the current filter context. Denominator for mix/attach diagnostics; excludes Renewal ACV.",
        },
        {
            "name": "Closed Won Deals Count",
            "expression": 'CALCULATE ( COUNTROWS ( f_opportunity ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] IN { "Land", "Expand" } )',
            "formatString": "#,0",
            "description": "RW KPI: closed_won_value_tier. Slice by f_opportunity[won_value_tier].",
        },
        {
            "name": "Commercial Approval Eligible Opps",
            "expression": (
                "COUNTROWS ( "
                "FILTER ( f_opportunity, "
                f"{non_omitted} && "
                'f_opportunity[motion_type] IN { "Land", "Expand" } && '
                "NOT ( f_opportunity[stage_name] IN { \"1 - Prospecting\", \"2 - Discovery\" } ) "
                ") )"
            ),
            "formatString": "#,0",
            "description": "Stage 3+ Land + Expand opps eligible for Commercial Approval monitoring.",
        },
        {
            "name": "Commercial Approved Opps",
            "expression": (
                "COUNTROWS ( "
                "FILTER ( f_opportunity, "
                f"{non_omitted} && "
                'f_opportunity[motion_type] IN { "Land", "Expand" } && '
                "f_opportunity[commercial_approval] = TRUE() && "
                "NOT ( f_opportunity[stage_name] IN { \"1 - Prospecting\", \"2 - Discovery\" } ) "
                ") )"
            ),
            "formatString": "#,0",
            "description": "Stage 3+ Land + Expand opps with Commercial Approval checked.",
        },
        {
            "name": "Commercial Approval Compliance Pct",
            "expression": "DIVIDE ( [Commercial Approved Opps], [Commercial Approval Eligible Opps] )",
            "formatString": "0.0%",
            "description": "RW KPI: stage3_approvals_compliance. Stage 3+ Land + Expand approval compliance.",
        },
        {
            "name": "Commercial Approval To Close Days",
            "expression": (
                "CALCULATE ( "
                "AVERAGEX ( "
                "FILTER ( f_opportunity, "
                "f_opportunity[is_won] = TRUE() && "
                'f_opportunity[motion_type] IN { "Land", "Expand" } && '
                "NOT ( ISBLANK ( f_opportunity[commercial_approval_date] ) ) "
                "), "
                "DATEDIFF ( f_opportunity[commercial_approval_date], f_opportunity[close_date], DAY ) "
                ") )"
            ),
            "formatString": "0.0",
            "description": "RW KPI: commercial_approval_to_close_time. Days from Commercial Approval date to won close.",
        },
        {
            "name": "Cross Sell To Acquired ARR",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[axioma_order_inflow_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" } )'
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: cross_sell_to_acquired. Uses Axioma Order Inflow on Land + Expand opps.",
        },
        {
            "name": "PS Recurring ACV",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[ps_recurring_acv_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" } )'
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "Recurring PS ACV on Land + Expand opps.",
        },
        {
            "name": "One Off Revenues",
            "expression": f"CALCULATE ( SUM ( f_opportunity[one_off_revenue_org_ccy] ), {non_omitted} )",
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: one_off_revenues. Non-recurring/one-off revenue from Opportunity one-off fields; not ARR and not Renewal ACV.",
        },
        {
            "name": "PS Non-Recurring Revenue",
            "expression": f"CALCULATE ( SUM ( f_opportunity[ps_non_recurring_org_ccy] ), {non_omitted} )",
            "formatString": CURRENCY_M_FORMAT,
            "description": "PS non-recurring revenue component from APTS_PS_Non_Recurring_NPP_Display__c.",
        },
        {
            "name": "One-Off Revenue Opp Count",
            "expression": f"COUNTROWS ( FILTER ( f_opportunity, {non_omitted} && f_opportunity[one_off_revenue_org_ccy] > 0 ) )",
            "formatString": "#,0",
            "description": "Opportunity count with non-recurring/one-off revenue > 0.",
        },
        {
            "name": "PS ARR Attach Pct",
            "expression": "DIVIDE ( [PS Recurring ACV], [Total Land Expand ARR] )",
            "formatString": "0.0%",
            "description": "RW KPI: ps_arr_attach. PS recurring ACV divided by Land + Expand ARR.",
        },
        {
            "name": "SaaS ARR",
            "expression": f"CALCULATE ( SUM ( f_opportunity[saas_acv_org_ccy] ), {non_omitted} )",
            "formatString": CURRENCY_M_FORMAT,
            "description": "SimCorp SaaS ACV/ARR signal from APTS_RH_ASP_Annual__c.",
        },
        {
            "name": "SaaS ARR LY YTD",
            "expression": "CALCULATE ( [SaaS ARR], REMOVEFILTERS ( d_calendar ), DATESBETWEEN ( d_calendar[date], DATE ( YEAR ( TODAY () ) - 1, 1, 1 ), DATE ( YEAR ( TODAY () ) - 1, MONTH ( TODAY () ), DAY ( TODAY () ) ) ) )",
            "formatString": CURRENCY_M_FORMAT,
            "description": "SaaS ARR for Jan 1 -> same-day prior year.",
        },
        {
            "name": "SaaS YoY Growth Pct",
            "expression": "DIVIDE ( [SaaS ARR] - [SaaS ARR LY YTD], [SaaS ARR LY YTD] )",
            "formatString": "0.0%",
            "description": "RW KPI: saas_arr_yoy_growth. SaaS ARR growth rate; target growth >20% YoY.",
        },
        # Renewals (ACV, never blend with ARR)
        {
            "name": "Total Open Renewal ACV",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[acv_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[is_closed] = FALSE(), f_opportunity[motion_type] = "Renewal" )'
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "Non-Omitted open renewal pipeline ACV. Renewal-only; never blended with ARR.",
        },
        {
            "name": "Total Renewal ACV Due",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[acv_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] = "Renewal" )'
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "Non-Omitted renewal ACV in current filter context: open + won + lost. Renewal-only denominator candidate.",
        },
        {
            "name": "Total Renewal ACV Won",
            "expression": 'CALCULATE ( SUM ( f_opportunity[acv_org_ccy] ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] = "Renewal" )',
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: renewals_mom_trend. ACV field, Renewal only.",
        },
        {
            "name": "Total Renewal ACV Lost",
            "expression": 'CALCULATE ( SUM ( f_opportunity[acv_org_ccy] ), f_opportunity[is_closed] = TRUE(), f_opportunity[is_won] = FALSE(), f_opportunity[motion_type] = "Renewal" )',
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: lost_arr_quarterly. ACV field, Renewal lost.",
        },
        {
            "name": "Renewal Retention Pct",
            "expression": "DIVIDE ( [Total Renewal ACV Won], [Total Renewal ACV Won] + [Total Renewal ACV Lost] )",
            "formatString": "0.0%",
            "description": "RW KPI: renewal_retention_rate (partial — uses closed-period basis, not term-due basis). Target 95%.",
        },
        {
            "name": "Business At Risk ACV",
            "expression": (
                "CALCULATE ( "
                "SUM ( f_opportunity[acv_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] = "Renewal", '
                "f_opportunity[is_closed] = FALSE(), "
                'f_opportunity[risk_assessment_level] IN { "High", "Medium - High" } '
                ")"
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI proxy: business_at_risk. Open Renewal ACV with High or Medium-High opportunity risk; active ARR base still requires subscription data.",
        },
        # New business pacing
        {
            "name": "New Opps Created",
            "expression": f"CALCULATE ( COUNTROWS ( f_opportunity ), {non_omitted}, USERELATIONSHIP ( f_opportunity[created_date], d_calendar[date] ) )",
            "formatString": "#,0",
            "description": "RW KPI: new_opps_by_region. Non-Omitted opportunity creation; target 100/month per region.",
        },
        # ── Phase 2.5: pure-DAX KPIs from existing data ─────────────────
        {
            "name": "Source ARR Won",
            "expression": 'CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] IN { "Land", "Expand" } )',
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: opp_source_effectiveness — slice by [lead_source] for per-source ARR.",
        },
        _heatmap_color_measure(
            "Source ARR Won Heat Color",
            "Source ARR Won",
            table="f_opportunity",
            group_columns=("lead_source", "region"),
            palette=blue_heat,
            description="Field-value background color for Source x Region ARR heatmaps.",
        ),
        {
            "name": "Source Win Rate",
            "expression": 'DIVIDE ( CALCULATE ( COUNTROWS ( f_opportunity ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] IN { "Land", "Expand" } ), CALCULATE ( COUNTROWS ( f_opportunity ), f_opportunity[is_closed] = TRUE(), f_opportunity[motion_type] IN { "Land", "Expand" } ) )',
            "formatString": "0.0%",
            "description": "RW KPI: opp_source_effectiveness — slice by [lead_source] for per-source win rate.",
        },
        _heatmap_color_measure(
            "Source Win Rate Heat Color",
            "Source Win Rate",
            table="f_opportunity",
            group_columns=("lead_source", "region"),
            palette=green_heat,
            description="Field-value background color for Source x Region win-rate heatmaps.",
        ),
        {
            "name": "Total Land Won ARR",
            "expression": 'CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] = "Land" )',
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: new_customer_reporting (Land-only Won ARR). Slice by region × month.",
        },
        {
            "name": "Total Land Won Count",
            "expression": 'CALCULATE ( COUNTROWS ( f_opportunity ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] = "Land" )',
            "formatString": "#,0",
            "description": "RW KPI: new_customer_reporting (Land-only count). Slice by region × month.",
        },
        _heatmap_color_measure(
            "Total Land Won Count Heat Color",
            "Total Land Won Count",
            table="f_opportunity",
            group_columns=("lead_source", "region"),
            palette=blue_heat,
            description="Field-value background color for Source x Region Land won count heatmaps.",
        ),
        # ── YoY comparison measures (default page filter should be year=2026) ──
        {
            "name": "Closed Won ARR LY",
            "expression": "CALCULATE ( [Total Closed Won ARR], SAMEPERIODLASTYEAR ( d_calendar[date] ) )",
            "formatString": CURRENCY_M_FORMAT,
            "description": "Same-period prior fiscal year. Pairs with Total Closed Won ARR for YoY math.",
        },
        {
            "name": "Closed Won ARR YoY Pct",
            "expression": "DIVIDE ( [Total Closed Won ARR] - [Closed Won ARR LY], [Closed Won ARR LY] )",
            "formatString": "0.0%",
            "description": "RW KPI: forecast_closed_won (YoY %). Target +10%.",
        },
        {
            "name": "Renewal ACV Won LY",
            "expression": "CALCULATE ( [Total Renewal ACV Won], SAMEPERIODLASTYEAR ( d_calendar[date] ) )",
            "formatString": CURRENCY_M_FORMAT,
        },
        {
            "name": "Renewal ACV YoY Pct",
            "expression": "DIVIDE ( [Total Renewal ACV Won] - [Renewal ACV Won LY], [Renewal ACV Won LY] )",
            "formatString": "0.0%",
            "description": "Renewal book YoY change.",
        },
        {
            "name": "Pipeline ARR LY",
            "expression": "CALCULATE ( [Total Open Pipeline ARR], SAMEPERIODLASTYEAR ( d_calendar[date] ) )",
            "formatString": CURRENCY_M_FORMAT,
        },
        {
            "name": "Pipeline ARR YoY Pct",
            "expression": "DIVIDE ( [Total Open Pipeline ARR] - [Pipeline ARR LY], [Pipeline ARR LY] )",
            "formatString": "0.0%",
            "description": "Pipeline build YoY — leading indicator for next-year's Closed Won.",
        },
        # ── YTD-comparable YoY (the apples-to-apples version) ───────────
        # The non-YTD versions above compare full-year to full-year. With a
        # page filter on year=2026 (which is YTD by definition since today is
        # May 7), the prior-year measure pulls FULL 2025 -> -91% misleading.
        # Fixed below: explicitly anchor prior-year-YTD via DATESBETWEEN.
        {
            "name": "Closed Won ARR LY YTD",
            "expression": "CALCULATE ( [Total Closed Won ARR], REMOVEFILTERS ( d_calendar ), DATESBETWEEN ( d_calendar[date], DATE ( YEAR ( TODAY () ) - 1, 1, 1 ), DATE ( YEAR ( TODAY () ) - 1, MONTH ( TODAY () ), DAY ( TODAY () ) ) ) )",
            "formatString": CURRENCY_M_FORMAT,
            "description": "Closed Won ARR for Jan 1 -> same-day prior year. Apples-to-apples vs current-YTD.",
        },
        {
            "name": "Closed Won ARR YTD YoY Pct",
            "expression": "DIVIDE ( [Total Closed Won ARR] - [Closed Won ARR LY YTD], [Closed Won ARR LY YTD] )",
            "formatString": "0.0%",
            "description": "RW KPI: forecast_closed_won YTD-comparable YoY. Target +10%.",
        },
        {
            "name": "Renewal ACV LY YTD",
            "expression": "CALCULATE ( [Total Renewal ACV Won], REMOVEFILTERS ( d_calendar ), DATESBETWEEN ( d_calendar[date], DATE ( YEAR ( TODAY () ) - 1, 1, 1 ), DATE ( YEAR ( TODAY () ) - 1, MONTH ( TODAY () ), DAY ( TODAY () ) ) ) )",
            "formatString": CURRENCY_M_FORMAT,
        },
        {
            "name": "Renewal ACV YTD YoY Pct",
            "expression": "DIVIDE ( [Total Renewal ACV Won] - [Renewal ACV LY YTD], [Renewal ACV LY YTD] )",
            "formatString": "0.0%",
            "description": "Renewal book YoY (YTD-comparable).",
        },
        # ── Period-anchored renewal retention ──────────────────────────
        # Original `Renewal Retention Pct` denominator = won + lost ACV
        # in period -> undercounts because some renewals due this period
        # haven't closed yet (still open). This version uses ALL renewal
        # opps with close_date in period (regardless of state) as the
        # denominator, which is closer to "due to renew this period".
        {
            "name": "Renewal Retention Pct (Period)",
            "expression": (
                "DIVIDE ( [Total Renewal ACV Won], "
                "CALCULATE ( SUM ( f_opportunity[acv_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] = "Renewal" ) )'
            ),
            "formatString": "0.0%",
            "description": "RW KPI: renewal_retention_rate. Denom = non-Omitted renewal opps with close_date in current filter (won + lost + open). Target 95%.",
        },
        # ── Motion breakout (Land vs Expand vs Renewal) ─────────────────
        # Verbatim semantics from sales_process_graph._MOTIONS:
        #   LAND   → ARR field, new business
        #   EXPAND → ARR field, existing customer growth (different from Land in conversion mechanics)
        #   RENEWAL → ACV field (already separated above)
        # The blended Land + Expand measures stay; these are additional drill-downs.
        {
            "name": "Open Land ARR",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[is_closed] = FALSE(), f_opportunity[motion_type] = "Land" )'
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "Non-Omitted open Land ARR. New-business pipeline; excludes Expand and Renewal.",
        },
        {
            "name": "Land Closed Won ARR",
            "expression": 'CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] = "Land" )',
            "formatString": CURRENCY_M_FORMAT,
            "description": "Land-only Won ARR. Excludes Expand and Renewal.",
        },
        {
            "name": "Land Win Rate ARR",
            "expression": 'DIVIDE ( CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] = "Land" ), CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), f_opportunity[is_closed] = TRUE(), f_opportunity[motion_type] = "Land" ) )',
            "formatString": "0.0%",
            "description": "Land-only Win Rate (ARR-weighted). New-business sales execution.",
        },
        {
            "name": "Land Avg Sales Cycle Days",
            "expression": 'CALCULATE ( AVERAGEX ( f_opportunity, DATEDIFF ( f_opportunity[created_date], f_opportunity[close_date], DAY ) ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] = "Land" )',
            "formatString": "0",
            "description": "Land cycle length. RW target <90d most likely refers to this (Land deals).",
        },
        {
            "name": "Open Expand ARR",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[is_closed] = FALSE(), f_opportunity[motion_type] = "Expand" )'
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "Non-Omitted open Expand ARR. Existing-customer growth pipeline; excludes Land and Renewal.",
        },
        {
            "name": "Expand Closed Won ARR",
            "expression": 'CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] = "Expand" )',
            "formatString": CURRENCY_M_FORMAT,
            "description": "Expand-only Won ARR. Existing-customer growth motion.",
        },
        {
            "name": "Expand Win Rate ARR",
            "expression": 'DIVIDE ( CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] = "Expand" ), CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), f_opportunity[is_closed] = TRUE(), f_opportunity[motion_type] = "Expand" ) )',
            "formatString": "0.0%",
            "description": "Expand-only Win Rate (ARR-weighted).",
        },
        {
            "name": "Expand Avg Sales Cycle Days",
            "expression": 'CALCULATE ( AVERAGEX ( f_opportunity, DATEDIFF ( f_opportunity[created_date], f_opportunity[close_date], DAY ) ), f_opportunity[is_won] = TRUE(), f_opportunity[motion_type] = "Expand" )',
            "formatString": "0",
            "description": "Expand cycle length. Typically longer than Land in this org.",
        },
        # ── Stall detection (Tab 3 Stage Hygiene + Tab 1 What Changed) ────
        # Uses last_stage_change_date already on f_opportunity (no f_stage_transition LOOKUP needed).
        {
            "name": "Stalled Open Opps Count 14d",
            "expression": (
                "COUNTROWS ( "
                "FILTER ( f_opportunity, "
                f"{non_omitted} && "
                "f_opportunity[is_closed] = FALSE() && "
                'f_opportunity[motion_type] IN { "Land", "Expand" } && '
                "DATEDIFF ( f_opportunity[last_stage_change_date], TODAY(), DAY ) > 14 "
                ") )"
            ),
            "formatString": "#,0",
            "description": "Open Land + Expand opps with no stage movement in >14 days (Watch threshold).",
        },
        {
            "name": "Stalled Open Opps ARR 14d",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), "
                "FILTER ( f_opportunity, "
                f"{non_omitted} && "
                "f_opportunity[is_closed] = FALSE() && "
                'f_opportunity[motion_type] IN { "Land", "Expand" } && '
                "DATEDIFF ( f_opportunity[last_stage_change_date], TODAY(), DAY ) > 14 "
                ") )"
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "Open Land + Expand ARR for opps stalled >14 days.",
        },
        {
            "name": "Stalled Open Opps Count 21d",
            "expression": (
                "COUNTROWS ( "
                "FILTER ( f_opportunity, "
                f"{non_omitted} && "
                "f_opportunity[is_closed] = FALSE() && "
                'f_opportunity[motion_type] IN { "Land", "Expand" } && '
                "DATEDIFF ( f_opportunity[last_stage_change_date], TODAY(), DAY ) > 21 "
                ") )"
            ),
            "formatString": "#,0",
            "description": "Open Land + Expand opps with no stage movement in >21 days (At-risk threshold).",
        },
        {
            "name": "Stalled Open Opps ARR 21d",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), "
                "FILTER ( f_opportunity, "
                f"{non_omitted} && "
                "f_opportunity[is_closed] = FALSE() && "
                'f_opportunity[motion_type] IN { "Land", "Expand" } && '
                "DATEDIFF ( f_opportunity[last_stage_change_date], TODAY(), DAY ) > 21 "
                ") )"
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "Open Land + Expand ARR for opps stalled >21 days.",
        },
        # ── Risk classification (Tab 1 What Changed risk band) ──────────────
        # Stage 5+ open = IN {"5 - Preferred","6 - Contracting","7 - Sales Ops QC"}.
        # Stage 3-4 open = IN {"3 - Engagement","4 - Shortlisted"}.
        # Verified against OpportunityStage (apro@simcorp.com) 2026-05-08.
        {
            "name": "At Risk Opps Count",
            "expression": (
                "COUNTROWS ( "
                "FILTER ( f_opportunity, "
                f"{non_omitted} && "
                "f_opportunity[is_closed] = FALSE() && "
                'f_opportunity[motion_type] IN { "Land", "Expand" } && '
                'f_opportunity[stage_name] IN { "5 - Preferred", "6 - Contracting", "7 - Sales Ops QC" } && '
                "DATEDIFF ( f_opportunity[last_stage_change_date], TODAY(), DAY ) > 21 "
                ") )"
            ),
            "formatString": "#,0",
            "description": "At Risk: Stage 5+ open Land + Expand AND stalled >21d.",
        },
        {
            "name": "At Risk Opps ARR",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), "
                "FILTER ( f_opportunity, "
                f"{non_omitted} && "
                "f_opportunity[is_closed] = FALSE() && "
                'f_opportunity[motion_type] IN { "Land", "Expand" } && '
                'f_opportunity[stage_name] IN { "5 - Preferred", "6 - Contracting", "7 - Sales Ops QC" } && '
                "DATEDIFF ( f_opportunity[last_stage_change_date], TODAY(), DAY ) > 21 "
                ") )"
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "Land + Expand ARR exposed in At Risk bucket (Stage 5+ stalled >21d).",
        },
        {
            "name": "Watch Opps Count",
            "expression": (
                "COUNTROWS ( "
                "FILTER ( f_opportunity, "
                f"{non_omitted} && "
                "f_opportunity[is_closed] = FALSE() && "
                'f_opportunity[motion_type] IN { "Land", "Expand" } && '
                'f_opportunity[stage_name] IN { "3 - Engagement", "4 - Shortlisted" } && '
                "DATEDIFF ( f_opportunity[last_stage_change_date], TODAY(), DAY ) > 14 "
                ") )"
            ),
            "formatString": "#,0",
            "description": "Watch: Stage 3-4 open Land + Expand AND stalled >14d.",
        },
        {
            "name": "Watch Opps ARR",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), "
                "FILTER ( f_opportunity, "
                f"{non_omitted} && "
                "f_opportunity[is_closed] = FALSE() && "
                'f_opportunity[motion_type] IN { "Land", "Expand" } && '
                'f_opportunity[stage_name] IN { "3 - Engagement", "4 - Shortlisted" } && '
                "DATEDIFF ( f_opportunity[last_stage_change_date], TODAY(), DAY ) > 14 "
                ") )"
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "Land + Expand ARR exposed in Watch bucket (Stage 3-4 stalled >14d).",
        },
        {
            "name": "Exception Opps Count",
            "expression": "[At Risk Opps Count] + [Watch Opps Count]",
            "formatString": "#,0",
            "description": "Land + Expand exception count: At Risk + Watch. Keeps count universe aligned to ARR exposure.",
        },
        {
            "name": "Exception ARR",
            "expression": "[At Risk Opps ARR] + [Watch Opps ARR]",
            "formatString": CURRENCY_M_FORMAT,
            "description": "Land + Expand ARR exception exposure: At Risk + Watch.",
        },
        {
            "name": "Healthy Moves Count",
            "expression": (
                "CALCULATE ( COUNTROWS ( f_stage_transition ), "
                f"{core_stage}, "
                'f_stage_transition[direction] = "forward", '
                "f_stage_transition[transition_at] >= TODAY() - 7, "
                "TREATAS ( "
                "CALCULATETABLE ( VALUES ( f_opportunity[opp_id] ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" } ), '
                "f_stage_transition[opp_id] ) )"
            ),
            "formatString": "#,0",
            "description": "Land + Expand forward stage moves in the last 7 days.",
        },
        {
            "name": "Healthy Moves ARR",
            "expression": (
                "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" }, '
                "TREATAS ( "
                f'CALCULATETABLE ( VALUES ( f_stage_transition[opp_id] ), {core_stage}, f_stage_transition[direction] = "forward", '
                "f_stage_transition[transition_at] >= TODAY() - 7 ), "
                "f_opportunity[opp_id] ) )"
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "Land + Expand ARR of opps with a forward stage move in the last 7 days.",
        },
        # Window-bound deltas (Tab 1 What Changed) — 3 families × 3 windows = 9 measures.
        # Slips family deferred — requires f_ofh_close_date table not in current ETL.
        *_window_measures(),
    ]

    # Stage-transition measures (Phase 2; require f_stage_transition table).
    stage_measures = [
        {
            "name": "Total Stage Transitions",
            "expression": "COUNTROWS ( f_stage_transition )",
            "formatString": "#,0",
        },
        {
            "name": "Core Stage Transitions (LE)",
            "expression": (
                "VAR _stage = SELECTEDVALUE ( d_stage[stage_order] ) "
                "VAR _oppids = CALCULATETABLE ( VALUES ( f_opportunity[opp_id] ), "
                "REMOVEFILTERS ( d_stage ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" } ) '
                "RETURN IF ( "
                "NOT ( ISBLANK ( _stage ) ), "
                "IF ( _stage >= 1 && _stage <= 6, CALCULATE ( COUNTROWS ( f_stage_transition ), f_stage_transition[from_stage_num] = _stage, TREATAS ( _oppids, f_stage_transition[opp_id] ) ) ), "
                "CALCULATE ( COUNTROWS ( f_stage_transition ), "
                f"{core_stage}, "
                "TREATAS ( _oppids, f_stage_transition[opp_id] ) ) )"
            ),
            "formatString": "#,0",
            "description": "Land + Expand transitions restricted to the real stage ladder: 1 Prospecting through 6 Contracting.",
        },
        {
            "name": "Core Stage Forward Pct (LE)",
            "expression": (
                "VAR _stage = SELECTEDVALUE ( d_stage[stage_order] ) "
                "VAR _oppids = CALCULATETABLE ( VALUES ( f_opportunity[opp_id] ), "
                "REMOVEFILTERS ( d_stage ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" } ) '
                "RETURN IF ( "
                "NOT ( ISBLANK ( _stage ) ), "
                "IF ( _stage >= 1 && _stage <= 6, "
                "DIVIDE ( "
                'CALCULATE ( COUNTROWS ( f_stage_transition ), f_stage_transition[from_stage_num] = _stage, f_stage_transition[direction] = "forward", TREATAS ( _oppids, f_stage_transition[opp_id] ) ), '
                "CALCULATE ( COUNTROWS ( f_stage_transition ), f_stage_transition[from_stage_num] = _stage, TREATAS ( _oppids, f_stage_transition[opp_id] ) ) ) ), "
                "CALCULATE ( [Stage Forward Pct (LE)], REMOVEFILTERS ( d_stage ) ) )"
            ),
            "formatString": "0.0%",
            "description": "Stage Forward Pct (LE) projected onto canonical d_stage rows 1-6 only.",
        },
        {
            "name": "Core Stage Backward Pct (LE)",
            "expression": (
                "VAR _stage = SELECTEDVALUE ( d_stage[stage_order] ) "
                "VAR _oppids = CALCULATETABLE ( VALUES ( f_opportunity[opp_id] ), "
                "REMOVEFILTERS ( d_stage ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" } ) '
                "RETURN IF ( "
                "NOT ( ISBLANK ( _stage ) ), "
                "IF ( _stage >= 1 && _stage <= 6, "
                "DIVIDE ( "
                'CALCULATE ( COUNTROWS ( f_stage_transition ), f_stage_transition[from_stage_num] = _stage, f_stage_transition[direction] = "backward", TREATAS ( _oppids, f_stage_transition[opp_id] ) ), '
                "CALCULATE ( COUNTROWS ( f_stage_transition ), f_stage_transition[from_stage_num] = _stage, TREATAS ( _oppids, f_stage_transition[opp_id] ) ) ) ), "
                "CALCULATE ( [Stage Backward Pct (LE)], REMOVEFILTERS ( d_stage ) ) )"
            ),
            "formatString": "0.0%",
            "description": "Stage Backward Pct (LE) projected onto canonical d_stage rows 1-6 only.",
        },
        {
            "name": "Core Avg Days In Prior Stage (LE)",
            "expression": (
                "VAR _stage = SELECTEDVALUE ( d_stage[stage_order] ) "
                "VAR _oppids = CALCULATETABLE ( VALUES ( f_opportunity[opp_id] ), "
                "REMOVEFILTERS ( d_stage ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" } ) '
                "RETURN IF ( "
                "NOT ( ISBLANK ( _stage ) ), "
                "IF ( _stage >= 1 && _stage <= 6, "
                "CALCULATE ( AVERAGE ( f_stage_transition[days_in_prior_stage] ), f_stage_transition[from_stage_num] = _stage, TREATAS ( _oppids, f_stage_transition[opp_id] ) ) ), "
                "CALCULATE ( [Avg Days In Prior Stage (LE)], REMOVEFILTERS ( d_stage ) ) )"
            ),
            "formatString": "0.0",
            "description": "Avg days in prior stage projected onto canonical d_stage rows 1-6 only.",
        },
        {
            "name": "Core Stage Moves ARR 7d",
            "expression": (
                "VAR _stage = SELECTEDVALUE ( d_stage[stage_order] ) "
                "VAR _transition_oppids = CALCULATETABLE ( VALUES ( f_stage_transition[opp_id] ), f_stage_transition[from_stage_num] = _stage, f_stage_transition[transition_at] >= TODAY() - 7 ) "
                "RETURN IF ( "
                "NOT ( ISBLANK ( _stage ) ), "
                "IF ( _stage >= 1 && _stage <= 6, "
                "CALCULATE ( SUM ( f_opportunity[arr_org_ccy] ), REMOVEFILTERS ( d_stage ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" }, '
                "TREATAS ( _transition_oppids, f_opportunity[opp_id] ) ) ), "
                "CALCULATE ( [Stage Moves ARR 7d], REMOVEFILTERS ( d_stage ) ) )"
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "7-day Land + Expand ARR moved, projected onto canonical d_stage rows 1-6 only.",
        },
        {
            "name": "Avg Days In Prior Stage",
            "expression": "AVERAGE ( f_stage_transition[days_in_prior_stage] )",
            "formatString": "0.0",
            "description": "RW KPI: time_in_stage. Slice by from_stage_name for per-stage view.",
        },
        {
            "name": "Forward Stage Transitions",
            "expression": 'CALCULATE ( COUNTROWS ( f_stage_transition ), f_stage_transition[direction] = "forward" )',
            "formatString": "#,0",
        },
        {
            "name": "Backward Stage Transitions",
            "expression": 'CALCULATE ( COUNTROWS ( f_stage_transition ), f_stage_transition[direction] = "backward" )',
            "formatString": "#,0",
        },
        {
            "name": "Stage Forward Pct",
            "expression": "DIVIDE ( [Forward Stage Transitions], [Total Stage Transitions] )",
            "formatString": "0.0%",
            "description": "RW KPI: stage_conversion (proxy). Target >70% — forward transitions / all. Slice by from_stage_name.",
        },
        {
            "name": "Stage Backward Pct",
            "expression": "DIVIDE ( [Backward Stage Transitions], [Total Stage Transitions] )",
            "formatString": "0.0%",
            "description": "Stage regression rate — pairs with Stage Forward Pct.",
        },
        # Land + Expand motion filter, pushed from f_opportunity → f_stage_transition via TREATAS
        # because rel_stage_opp is oneDirection. KG: stage_conversion.motion_filter = land_expand.
        {
            "name": "Stage Forward Pct (LE)",
            "expression": (
                "CALCULATE ( [Stage Forward Pct], "
                f"{core_stage}, "
                "TREATAS ( "
                "CALCULATETABLE ( VALUES ( f_opportunity[opp_id] ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" } ), '
                "f_stage_transition[opp_id] ) )"
            ),
            "formatString": "0.0%",
            "description": "Stage Forward Pct restricted to Land + Expand opps (excludes Renewal). RW KG motion_filter=land_expand.",
        },
        # Per-stage forward rates — wrap [Stage Forward Pct (LE)] with from_stage_num filter.
        # Caveat (KG): ~70% of close-wons skip Stage 4 in OFH, so S3→S4 and S4→S5 are computed
        # on a partial close-won population. Surface footer note on cards.
        {
            "name": "Stage 1 Forward Pct",
            "expression": "CALCULATE ( [Stage Forward Pct (LE)], f_stage_transition[from_stage_num] = 1 )",
            "formatString": "0.0%",
            "description": "Prospecting → Discovery forward rate (Land + Expand). RW KPI stage_conversion target >70%.",
        },
        {
            "name": "Stage 2 Forward Pct",
            "expression": "CALCULATE ( [Stage Forward Pct (LE)], f_stage_transition[from_stage_num] = 2 )",
            "formatString": "0.0%",
            "description": "Discovery → Engagement forward rate (Land + Expand). RW KPI stage_conversion target >70%.",
        },
        {
            "name": "Stage 3 Forward Pct",
            "expression": "CALCULATE ( [Stage Forward Pct (LE)], f_stage_transition[from_stage_num] = 3 )",
            "formatString": "0.0%",
            "description": "Engagement → Shortlisted forward rate (Land + Expand). Caveat: ~70% of close-wons skip Stage 4 — partial population.",
        },
        {
            "name": "Stage 4 Forward Pct",
            "expression": "CALCULATE ( [Stage Forward Pct (LE)], f_stage_transition[from_stage_num] = 4 )",
            "formatString": "0.0%",
            "description": "Shortlisted → Preferred forward rate (Land + Expand). Caveat: small/skewed sample due to S4 funnel-skip pattern.",
        },
        {
            "name": "Stage 5 Forward Pct",
            "expression": "CALCULATE ( [Stage Forward Pct (LE)], f_stage_transition[from_stage_num] = 5 )",
            "formatString": "0.0%",
            "description": "Preferred → Contracting forward rate (Land + Expand). RW KPI stage_conversion target >70%.",
        },
        {
            "name": "Stage 6 Forward Pct",
            "expression": "CALCULATE ( [Stage Forward Pct (LE)], f_stage_transition[from_stage_num] = 6 )",
            "formatString": "0.0%",
            "description": "Contracting → Won forward rate (Land + Expand). RW KPI stage_conversion target >70%.",
        },
        # Stage Backward Pct + per-stage variants (Land + Expand). Mirrors the forward family;
        # uses TREATAS to push motion filter from f_opportunity into f_stage_transition.
        {
            "name": "Stage Backward Pct (LE)",
            "expression": (
                "CALCULATE ( [Stage Backward Pct], "
                f"{core_stage}, "
                "TREATAS ( "
                "CALCULATETABLE ( VALUES ( f_opportunity[opp_id] ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" } ), '
                "f_stage_transition[opp_id] ) )"
            ),
            "formatString": "0.0%",
            "description": "Stage Backward Pct restricted to Land + Expand opps (excludes Renewal).",
        },
        {
            "name": "Stage 1 Backward Pct",
            "expression": "CALCULATE ( [Stage Backward Pct (LE)], f_stage_transition[from_stage_num] = 1 )",
            "formatString": "0.0%",
            "description": "Backward rate out of Prospecting (Land + Expand). Pairs with Stage 1 Forward Pct.",
        },
        {
            "name": "Stage 2 Backward Pct",
            "expression": "CALCULATE ( [Stage Backward Pct (LE)], f_stage_transition[from_stage_num] = 2 )",
            "formatString": "0.0%",
            "description": "Backward rate out of Discovery (Land + Expand).",
        },
        {
            "name": "Stage 3 Backward Pct",
            "expression": "CALCULATE ( [Stage Backward Pct (LE)], f_stage_transition[from_stage_num] = 3 )",
            "formatString": "0.0%",
            "description": "Backward rate out of Engagement (Land + Expand). Caveat: ~70% close-won S4 skip — partial population.",
        },
        {
            "name": "Stage 4 Backward Pct",
            "expression": "CALCULATE ( [Stage Backward Pct (LE)], f_stage_transition[from_stage_num] = 4 )",
            "formatString": "0.0%",
            "description": "Backward rate out of Shortlisted (Land + Expand). Caveat: small/skewed sample.",
        },
        {
            "name": "Stage 5 Backward Pct",
            "expression": "CALCULATE ( [Stage Backward Pct (LE)], f_stage_transition[from_stage_num] = 5 )",
            "formatString": "0.0%",
            "description": "Backward rate out of Preferred (Land + Expand).",
        },
        {
            "name": "Stage 6 Backward Pct",
            "expression": "CALCULATE ( [Stage Backward Pct (LE)], f_stage_transition[from_stage_num] = 6 )",
            "formatString": "0.0%",
            "description": "Backward rate out of Contracting (Land + Expand).",
        },
        # Time-in-stage: Land + Expand restriction + per-stage variants of Avg Days In Prior Stage.
        {
            "name": "Avg Days In Prior Stage (LE)",
            "expression": (
                "CALCULATE ( [Avg Days In Prior Stage], "
                f"{core_stage}, "
                "TREATAS ( "
                "CALCULATETABLE ( VALUES ( f_opportunity[opp_id] ), "
                f"{non_omitted}, "
                'f_opportunity[motion_type] IN { "Land", "Expand" } ), '
                "f_stage_transition[opp_id] ) )"
            ),
            "formatString": "0.0",
            "description": "Avg days an opp spent in its prior stage before transitioning (Land + Expand only).",
        },
        {
            "name": "Avg Days In Stage 1",
            "expression": "CALCULATE ( [Avg Days In Prior Stage (LE)], f_stage_transition[from_stage_num] = 1 )",
            "formatString": "0.0",
            "description": "Avg days in Prospecting (Land + Expand).",
        },
        {
            "name": "Avg Days In Stage 2",
            "expression": "CALCULATE ( [Avg Days In Prior Stage (LE)], f_stage_transition[from_stage_num] = 2 )",
            "formatString": "0.0",
            "description": "Avg days in Discovery (Land + Expand).",
        },
        {
            "name": "Avg Days In Stage 3",
            "expression": "CALCULATE ( [Avg Days In Prior Stage (LE)], f_stage_transition[from_stage_num] = 3 )",
            "formatString": "0.0",
            "description": "Avg days in Engagement (Land + Expand).",
        },
        {
            "name": "Avg Days In Stage 4",
            "expression": "CALCULATE ( [Avg Days In Prior Stage (LE)], f_stage_transition[from_stage_num] = 4 )",
            "formatString": "0.0",
            "description": "Avg days in Shortlisted (Land + Expand). Caveat: small/skewed sample due to S4 funnel-skip pattern.",
        },
        {
            "name": "Avg Days In Stage 5",
            "expression": "CALCULATE ( [Avg Days In Prior Stage (LE)], f_stage_transition[from_stage_num] = 5 )",
            "formatString": "0.0",
            "description": "Avg days in Preferred (Land + Expand).",
        },
        {
            "name": "Avg Days In Stage 6",
            "expression": "CALCULATE ( [Avg Days In Prior Stage (LE)], f_stage_transition[from_stage_num] = 6 )",
            "formatString": "0.0",
            "description": "Avg days in Contracting (Land + Expand).",
        },
        # Window-bound stage-transition deltas — 3 families × 3 windows = 9 measures.
        *_stage_window_measures(),
    ]

    # Forecast-category transition measures (Phase 3; require f_forecast_transition).
    forecast_measures = [
        {
            "name": "Total Forecast Transitions",
            "expression": 'CALCULATE ( COUNTROWS ( f_forecast_transition ), f_forecast_transition[from_category] <> "Omitted", f_forecast_transition[to_category] <> "Omitted" )',
            "formatString": "#,0",
            "description": "Forecast-category transitions excluding Omitted; Omitted is pipeline hygiene, not executive forecast movement.",
        },
        {
            "name": "Forecast Upgrades",
            "expression": 'CALCULATE ( COUNTROWS ( f_forecast_transition ), f_forecast_transition[direction] = "upgrade", f_forecast_transition[from_category] <> "Omitted", f_forecast_transition[to_category] <> "Omitted" )',
            "formatString": "#,0",
            "description": "Pipeline → Best Case → Commit → Closed direction. Excludes Omitted transitions.",
        },
        {
            "name": "Forecast Slips",
            "expression": 'CALCULATE ( COUNTROWS ( f_forecast_transition ), f_forecast_transition[direction] = "slip", f_forecast_transition[from_category] <> "Omitted", f_forecast_transition[to_category] <> "Omitted" )',
            "formatString": "#,0",
            "description": "Commit → Pipeline / Best Case → Pipeline (downgrade), excluding Omitted. RW pain — undermines forecast trust.",
        },
        {
            "name": "Forecast Slip Pct",
            "expression": "DIVIDE ( [Forecast Slips], [Total Forecast Transitions] )",
            "formatString": "0.0%",
            "description": "Forecast hygiene: % of category transitions that are slips. Target <15%.",
        },
        {
            "name": "Avg Days In Forecast Category",
            "expression": 'CALCULATE ( AVERAGE ( f_forecast_transition[days_in_prior_category] ), f_forecast_transition[from_category] <> "Omitted", f_forecast_transition[to_category] <> "Omitted" )',
            "formatString": "0.0",
            "description": "How long opps sit in each non-Omitted forecast category before moving. Slice by from_category.",
        },
    ]

    # Active Apttus asset base. These are ARR measures over installed assets,
    # not Renewal-opportunity ACV, so they intentionally live on a separate fact.
    asset_measures = [
        {
            "name": "Existing ARR Run Rate",
            "expression": (
                "CALCULATE ( "
                "SUM ( f_asset_line_item[asset_arr_org_ccy] ), "
                "f_asset_line_item[is_active_base] = TRUE(), "
                "REMOVEFILTERS ( d_calendar ) )"
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: existing_arr_run_rate. Current active/non-expired installed ARR base from Apttus Asset Line Item; not Renewal ACV.",
        },
        _heatmap_color_measure(
            "Existing ARR Run Rate Heat Color",
            "Existing ARR Run Rate",
            table="f_asset_line_item",
            group_columns=("region", "termination_risk", "product_family", "industry"),
            palette=blue_heat,
            description="Field-value background color for active-base ARR heatmaps.",
        ),
        {
            "name": "Existing ARR Expiring In Period",
            "expression": (
                "CALCULATE ( "
                "SUM ( f_asset_line_item[asset_arr_org_ccy] ), "
                "f_asset_line_item[is_active_base] = TRUE() )"
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "Active installed ARR filtered by asset end date / selected renewal period.",
        },
        _heatmap_color_measure(
            "Existing ARR Expiring In Period Heat Color",
            "Existing ARR Expiring In Period",
            table="f_asset_line_item",
            group_columns=("region", "termination_risk", "product_family", "industry"),
            palette=blue_heat,
            description="Field-value background color for expiring active-base ARR heatmaps.",
        ),
        {
            "name": "Business At Risk ARR",
            "expression": (
                "CALCULATE ( "
                "SUM ( f_asset_line_item[asset_arr_org_ccy] ), "
                "f_asset_line_item[is_active_base] = TRUE(), "
                'f_asset_line_item[termination_risk] IN { "High", "Medium" } )'
            ),
            "formatString": CURRENCY_M_FORMAT,
            "description": "RW KPI: business_at_risk. Active installed ARR where Account termination risk is High or Medium; replaces Renewal-opportunity ACV proxy.",
        },
        _heatmap_color_measure(
            "Business At Risk ARR Heat Color",
            "Business At Risk ARR",
            table="f_asset_line_item",
            group_columns=("region", "termination_risk", "product_family", "industry"),
            palette=red_heat,
            description="Field-value background color for at-risk active-base ARR heatmaps.",
        ),
        {
            "name": "Business At Risk Pct",
            "expression": "DIVIDE ( [Business At Risk ARR], [Existing ARR Run Rate] )",
            "formatString": "0.0%",
            "description": "At-risk active ARR as a share of current installed ARR run-rate.",
        },
        _heatmap_color_measure(
            "Business At Risk Pct Heat Color",
            "Business At Risk Pct",
            table="f_asset_line_item",
            group_columns=("region", "termination_risk", "product_family", "industry"),
            palette=amber_heat,
            description="Field-value background color for active-base risk percent heatmaps.",
        ),
        {
            "name": "Active Asset Line Count",
            "expression": (
                "CALCULATE ( "
                "COUNTROWS ( f_asset_line_item ), "
                "f_asset_line_item[is_active_base] = TRUE() )"
            ),
            "formatString": "#,0",
            "description": "Active/non-expired Apttus asset line count.",
        },
    ]

    return {
        "name": MODEL_NAME,
        "compatibilityLevel": 1604,
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "discourageImplicitMeasures": True,
            "expressions": [{"name": "DatabaseQuery", "kind": "m", "expression": database_query}],
            "tables": [
                {
                    "name": "f_opportunity",
                    "columns": [
                        col("opp_id", "string", key=True),
                        col("opp_name", "string"),
                        col("account_id", "string"),
                        col("owner_id", "string"),
                        col("stage_name", "string", sort_by="stage_order"),
                        col("stage_order", "int64"),
                        col("motion_type", "string"),
                        col("record_type", "string"),
                        col("primary_quote_type", "string"),
                        col("reason_won_lost", "string"),
                        col("lost_to_competitor", "string"),
                        col("native_currency", "string"),
                        col("arr_org_ccy", "double"),
                        col("acv_org_ccy", "double"),
                        col("saas_acv_org_ccy", "double"),
                        col("axioma_order_inflow_org_ccy", "double"),
                        col("ps_recurring_acv_org_ccy", "double"),
                        col("ps_one_off_org_ccy", "double"),
                        col("ps_non_recurring_org_ccy", "double"),
                        col("third_party_one_off_org_ccy", "double"),
                        col("cdd_one_off_tcv_org_ccy", "double"),
                        col("pso_one_off_tcv_org_ccy", "double"),
                        col("psi_psa_one_off_org_ccy", "double"),
                        col("one_off_revenue_org_ccy", "double"),
                        col("quota_org_ccy", "double"),
                        col("amount_org_ccy", "double"),
                        col("lead_source", "string"),
                        col("forecast_category", "string"),
                        col("commercial_approval", "boolean"),
                        col("commercial_approval_date", "dateTime", fmt="yyyy-mm-dd"),
                        col("commercial_approval_submit_date", "dateTime", fmt="yyyy-mm-dd"),
                        col("risk_assessment_level", "string"),
                        col("is_won", "boolean"),
                        col("is_closed", "boolean"),
                        col("close_date", "dateTime", fmt="yyyy-mm-dd"),
                        col("created_date", "dateTime"),
                        col("last_stage_change_date", "dateTime"),
                        col("region", "string"),
                        col("billing_country", "string"),
                        col("industry", "string"),
                        col("account_name", "string"),
                        col("won_value_tier", "string"),
                    ],
                    "partitions": [dl_partition("f_opportunity")],
                    "measures": measures,
                },
                {
                    "name": "d_account",
                    "columns": [
                        col("account_id", "string", key=True),
                        col("account_name", "string"),
                        col("region", "string"),
                        col("billing_country", "string"),
                        col("industry", "string"),
                        col("owner_id", "string"),
                        col("account_type", "string"),
                        col("axioma_client", "boolean"),
                        col("termination_risk", "string"),
                    ],
                    "partitions": [dl_partition("d_account")],
                },
                {
                    "name": "d_user",
                    "columns": [
                        col("user_id", "string", key=True),
                        col("user_name", "string"),
                        col("title", "string"),
                        col("department", "string"),
                        col("is_active", "boolean"),
                        col("role_name", "string"),
                        col("role_dev_name", "string"),
                    ],
                    "partitions": [dl_partition("d_user")],
                },
                {
                    "name": "d_region",
                    "columns": [
                        col("region", "string", key=True),
                        col("sort_order", "int64"),
                    ],
                    "partitions": [dl_partition("d_region")],
                },
                {
                    "name": "d_stage",
                    "columns": [
                        col("stage_order", "int64", key=True),
                        col("stage_name", "string", sort_by="stage_order"),
                        col("stage_short_name", "string", sort_by="stage_order"),
                        col("is_terminal", "boolean"),
                    ],
                    "partitions": [dl_partition("d_stage")],
                },
                {
                    "name": "d_calendar",
                    "columns": [
                        col("date", "dateTime", key=True, fmt="yyyy-mm-dd"),
                        col("year", "int64"),
                        col("quarter", "int64"),
                        col("fiscal_quarter", "string"),
                        col("month", "int64"),
                        col("month_name", "string"),
                        col("year_month", "string"),
                        col("day_of_week", "int64"),
                        col("is_weekend", "boolean"),
                    ],
                    "partitions": [dl_partition("d_calendar")],
                },
                {
                    "name": "f_stage_transition",
                    "columns": [
                        col("opp_id", "string"),
                        col("from_stage_raw", "string"),
                        col("to_stage_raw", "string"),
                        col("transition_at", "dateTime"),
                        col("prior_transition_at", "dateTime"),
                        col("days_in_prior_stage", "double"),
                        col("from_stage_num", "int64"),
                        col("from_stage_name", "string", sort_by="from_stage_order"),
                        col("from_stage_order", "int64"),
                        col("from_stage_display", "string", sort_by="from_stage_order"),
                        col("to_stage_num", "int64"),
                        col("to_stage_name", "string", sort_by="to_stage_order"),
                        col("to_stage_order", "int64"),
                        col("to_stage_display", "string", sort_by="to_stage_order"),
                        col("direction", "string"),
                    ],
                    "partitions": [dl_partition("f_stage_transition")],
                    "measures": stage_measures,
                },
                {
                    "name": "f_forecast_transition",
                    "columns": [
                        col("opp_id", "string"),
                        col("from_category", "string"),
                        col("to_category", "string"),
                        col("transition_at", "dateTime"),
                        col("prior_transition_at", "dateTime"),
                        col("days_in_prior_category", "double"),
                        col("from_rank", "int64"),
                        col("to_rank", "int64"),
                        col("direction", "string"),
                    ],
                    "partitions": [dl_partition("f_forecast_transition")],
                    "measures": forecast_measures,
                },
                {
                    "name": "f_asset_line_item",
                    "columns": [
                        col("asset_line_item_id", "string", key=True),
                        col("asset_name", "string"),
                        col("account_id", "string"),
                        col("account_name", "string"),
                        col("region", "string"),
                        col("billing_country", "string"),
                        col("industry", "string"),
                        col("termination_risk", "string"),
                        col("asset_status", "string"),
                        col("is_inactive", "boolean"),
                        col("asset_start_date", "dateTime", fmt="yyyy-mm-dd"),
                        col("asset_end_date", "dateTime", fmt="yyyy-mm-dd"),
                        col("product_id", "string"),
                        col("product_name", "string"),
                        col("product_family", "string"),
                        col("product_area", "string"),
                        col("product_type", "string"),
                        col("native_currency", "string"),
                        col("asset_arr_org_ccy", "double"),
                        col("renewal_scope", "string"),
                        col("is_active_base", "boolean"),
                    ],
                    "partitions": [dl_partition("f_asset_line_item")],
                    "measures": asset_measures,
                },
            ],
            "relationships": [
                {
                    "name": "rel_opp_account",
                    "fromTable": "f_opportunity",
                    "fromColumn": "account_id",
                    "toTable": "d_account",
                    "toColumn": "account_id",
                    "crossFilteringBehavior": "oneDirection",
                },
                {
                    "name": "rel_opp_user",
                    "fromTable": "f_opportunity",
                    "fromColumn": "owner_id",
                    "toTable": "d_user",
                    "toColumn": "user_id",
                    "crossFilteringBehavior": "oneDirection",
                },
                {
                    "name": "rel_opp_region",
                    "fromTable": "f_opportunity",
                    "fromColumn": "region",
                    "toTable": "d_region",
                    "toColumn": "region",
                    "crossFilteringBehavior": "oneDirection",
                },
                {
                    "name": "rel_opp_stage",
                    "fromTable": "f_opportunity",
                    "fromColumn": "stage_order",
                    "toTable": "d_stage",
                    "toColumn": "stage_order",
                    "crossFilteringBehavior": "oneDirection",
                },
                {
                    "name": "rel_opp_close_date",
                    "fromTable": "f_opportunity",
                    "fromColumn": "close_date",
                    "toTable": "d_calendar",
                    "toColumn": "date",
                    "crossFilteringBehavior": "oneDirection",
                },
                {
                    "name": "rel_opp_created_date",
                    "fromTable": "f_opportunity",
                    "fromColumn": "created_date",
                    "toTable": "d_calendar",
                    "toColumn": "date",
                    "crossFilteringBehavior": "oneDirection",
                    "isActive": False,  # second relationship to date dim — activated by USERELATIONSHIP for "New Opps Created"
                },
                {
                    "name": "rel_asset_account",
                    "fromTable": "f_asset_line_item",
                    "fromColumn": "account_id",
                    "toTable": "d_account",
                    "toColumn": "account_id",
                    "crossFilteringBehavior": "oneDirection",
                },
                {
                    "name": "rel_asset_region",
                    "fromTable": "f_asset_line_item",
                    "fromColumn": "region",
                    "toTable": "d_region",
                    "toColumn": "region",
                    "crossFilteringBehavior": "oneDirection",
                },
                {
                    "name": "rel_asset_end_date",
                    "fromTable": "f_asset_line_item",
                    "fromColumn": "asset_end_date",
                    "toTable": "d_calendar",
                    "toColumn": "date",
                    "crossFilteringBehavior": "oneDirection",
                },
                {
                    "name": "rel_forecast_opp",
                    "fromTable": "f_forecast_transition",
                    "fromColumn": "opp_id",
                    "toTable": "f_opportunity",
                    "toColumn": "opp_id",
                    "crossFilteringBehavior": "oneDirection",
                },
                {
                    "name": "rel_stage_opp",
                    "fromTable": "f_stage_transition",
                    "fromColumn": "opp_id",
                    "toTable": "f_opportunity",
                    "toColumn": "opp_id",
                    "crossFilteringBehavior": "oneDirection",
                },
            ],
        },
    }


def _token(resource: str) -> str:
    return AzureCliCredential().get_token(resource).token


def _wait_lro(response: requests.Response, fabric_token: str) -> dict | None:
    if response.status_code in (200, 201):
        return response.json() if response.text else None
    if response.status_code != 202:
        response.raise_for_status()
    op_id = response.headers.get("x-ms-operation-id")
    location = response.headers.get("Location") or f"{FABRIC}/v1/operations/{op_id}"
    print(f"  LRO accepted; polling op {op_id}")
    while True:
        time.sleep(int(response.headers.get("Retry-After", 3)))
        r = requests.get(location, headers={"Authorization": f"Bearer {fabric_token}"})
        if r.status_code == 200:
            body = r.json() if r.text else {}
            status = body.get("status")
            if status in ("Succeeded", "Failed"):
                print(f"  LRO {status}")
                if status == "Failed":
                    print("  error:", body.get("error"))
                    return None
                rr = requests.get(
                    f"{FABRIC}/v1/operations/{op_id}/result",
                    headers={"Authorization": f"Bearer {fabric_token}"},
                )
                return rr.json() if rr.text else None
            print(f"  status={status}")
        else:
            print(f"  poll status {r.status_code}: {r.text[:200]}")
            return None


def find_existing(fabric_token: str) -> str | None:
    r = requests.get(
        f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/semanticModels",
        headers={"Authorization": f"Bearer {fabric_token}"},
    )
    r.raise_for_status()
    for sm in r.json().get("value", []):
        if sm.get("displayName") == MODEL_NAME:
            return sm["id"]
    return None


def deploy() -> str:
    fabric_token = _token(FABRIC_RES)
    parts = [
        {
            "path": "definition.pbism",
            "payload": _b64(json.dumps(build_pbism())),
            "payloadType": "InlineBase64",
        },
        {
            "path": "model.bim",
            "payload": _b64(json.dumps(build_model_bim(), indent=2)),
            "payloadType": "InlineBase64",
        },
    ]
    headers = {"Authorization": f"Bearer {fabric_token}", "Content-Type": "application/json"}
    existing_id = find_existing(fabric_token)

    if existing_id:
        print(f"Updating existing semantic model {existing_id}")
        r = requests.post(
            f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/semanticModels/{existing_id}/updateDefinition",
            headers=headers,
            json={"definition": {"parts": parts}},
        )
        _wait_lro(r, fabric_token)
        return existing_id

    print("Creating semantic model sm_sales_kpis_rw")
    r = requests.post(
        f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/semanticModels",
        headers=headers,
        json={
            "displayName": MODEL_NAME,
            "description": "RW (Richard Wyeth, MD Sales Ops) sales KPIs — region-filterable. Source of truth: scripts/sales/rw_kpi_graph.py schema v1.",
            "definition": {"parts": parts},
        },
    )
    if r.status_code in (200, 201):
        return r.json()["id"]
    if r.status_code == 202:
        result = _wait_lro(r, fabric_token)
        if result and isinstance(result, dict):
            return result.get("id", "")
    r.raise_for_status()
    return ""


def refresh(model_id: str) -> None:
    pbi_token = _token(PBI_RES)
    r = requests.post(
        f"{PBI}/v1.0/myorg/groups/{WORKSPACE_ID}/datasets/{model_id}/refreshes",
        headers={"Authorization": f"Bearer {pbi_token}", "Content-Type": "application/json"},
        json={"type": "Full", "commitMode": "transactional"},
    )
    if r.status_code in (200, 202):
        print("  refresh enqueued")
    else:
        print(f"  refresh response {r.status_code}: {r.text[:300]}")


def main() -> None:
    model_id = deploy()
    if not model_id:
        return
    print(f"\nsemantic model id: {model_id}")
    refresh(model_id)
    print(f"\nopen: https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/datasets/{model_id}")


if __name__ == "__main__":
    main()
