from __future__ import annotations

import copy
import sys
from datetime import date
from typing import Any

from scripts.sf_audit.improve_dashboard_layout import pack_layout, widget_size
from scripts.sf_audit.remediate_priority_dashboards import (
    CRO,
    DEAL_DESK,
    FORECAST,
    RENEWALS,
    SD_MONTHLY,
    Remediator,
)
from scripts.sf_audit.reports import _filter

SCORECARD = "01ZTb00000FyJSAMA3"

STANDARD_REMOVE_CRO = {
    "00OTb000008mw1tMAA",  # Bookings Trend by Region
    "00OTb000008mvKLMAY",  # Win/Loss by Fiscal Quarter
}

STANDARD_REMOVE_FORECAST = {
    "00OTb000008mxPNMAY",  # Einstein Score by Stage
    "00OTb000008mvYsMAI",  # Forecast Cat Trend
    "00OTb000008mwGPMAY",  # Won by Forecast Cat
    "00OTb000008mwJdMAI",  # Omitted Pipeline
}

STANDARD_REMOVE_RENEWALS = {
    "00OTb000008mviXMAQ",  # Lost This Quarter
    "00OTb000008mvfJMAQ",  # Renewal ACV by Industry
    "00OTb000008mvllMAA",  # At-Risk Renewals
}

STANDARD_REMOVE_DEAL_DESK = {
    "00OTb000008aTtJMAU",  # Commercial Approval Approved YTD (Land)
}

STANDARD_REMOVE_SCORECARD = {
    "00OTb000008nZsrMAE",  # Task Volume by Owner x Type
}

STANDARD_REMOVE_SD = {
    "00OTb000008mvFVMAY",  # Forecast Category Split
    "00OTb000008mvQnMAI",  # Top Accounts by Open ARR
}

SCORECARD_FILTER_COLS = [
    {"label": "Region", "name": "Account.Region__c"},
    {"label": "Product Family", "name": "Opportunity.APTS_RH_Product_Family__c"},
]

STANDARD_FILTER_COLS_LOCAL = [
    {"label": "Industry", "name": "INDUSTRY"},
    {"label": "Legal Country", "name": "ADDRESS1_COUNTRY_CODE"},
    {"label": "Sales Region", "name": "Account.Region__c"},
    {"label": "Account Unit Group", "name": "Opportunity.Account_Unit_Group__c"},
]

DASHBOARD_RO_FIELDS = (
    "id",
    "createdById",
    "createdDate",
    "lastModifiedDate",
    "namespace",
    "type",
    "developerName",
    "folderId",
    "folderName",
    "url",
    "labels",
    "ownerId",
)


def fetch_dashboard_filters(remediator: Remediator, dashboard_id: str) -> list[dict[str, Any]]:
    data = remediator._get(f"/analytics/dashboards/{dashboard_id}/describe")
    out: list[dict[str, Any]] = []
    for flt in data.get("filters") or []:
        item = {
            "name": flt["name"],
            "dataType": flt.get("dataType"),
            "errorMessage": flt.get("errorMessage"),
            "selectedOption": None,
            "options": [],
        }
        for opt in flt.get("options") or []:
            item["options"].append(
                {
                    "alias": opt.get("alias"),
                    "operation": opt.get("operation"),
                    "value": opt.get("value"),
                    "endValue": opt.get("endValue"),
                    "startValue": opt.get("startValue"),
                }
            )
        out.append(item)
    return out


def ensure_filter_columns(
    remediator: Remediator,
    component: dict[str, Any],
    report_id: str,
    filter_columns: list[dict[str, Any]],
) -> bool:
    if remediator._report_type(report_id) != "Opportunity":
        return False
    props = component.setdefault("properties", {})
    current = props.get("filterColumns") or []
    current_names = {item.get("name") for item in current}
    merged = list(current)
    changed = False
    for item in filter_columns:
        if item["name"] not in current_names:
            merged.append(copy.deepcopy(item))
            changed = True
    if changed:
        props["filterColumns"] = merged
    return changed


def patch_dashboard(
    remediator: Remediator,
    dashboard_id: str,
    *,
    new_components: list[dict[str, Any]],
    remove_report_ids: set[str],
    dashboard_filters: list[dict[str, Any]],
    filter_columns: list[dict[str, Any]],
    header_overrides: dict[str, str] | None = None,
    title_overrides: dict[str, str] | None = None,
) -> None:
    metadata = remediator._get(f"/analytics/dashboards/{dashboard_id}/describe")
    components = [
        component
        for component in (metadata.get("components") or [])
        if (component.get("reportId") or "") not in remove_report_ids
    ]
    changed = False
    current_filters = metadata.get("filters") or []
    current_names = [flt.get("name") for flt in current_filters]
    target_names = [flt.get("name") for flt in dashboard_filters]
    if current_names != target_names or len(current_filters) != len(dashboard_filters):
        metadata["filters"] = copy.deepcopy(dashboard_filters)
        changed = True

    header_overrides = header_overrides or {}
    title_overrides = title_overrides or {}
    existing_report_ids = {component.get("reportId") for component in components}
    for component in components:
        report_id = component.get("reportId")
        if not report_id:
            continue
        changed = ensure_filter_columns(remediator, component, report_id, filter_columns) or changed
        if report_id in header_overrides and component.get("header") != header_overrides[report_id]:
            component["header"] = header_overrides[report_id]
            changed = True
        if report_id in title_overrides and component.get("title") != title_overrides[report_id]:
            component["title"] = title_overrides[report_id]
            changed = True

    for component in new_components:
        report_id = component.get("reportId")
        if report_id and report_id in existing_report_ids:
            continue
        if report_id:
            ensure_filter_columns(remediator, component, report_id, filter_columns)
            existing_report_ids.add(report_id)
        components.append(component)
        changed = True

    if not changed:
        final = remediator._get(f"/analytics/dashboards/{dashboard_id}/describe")
        print(f"{final['name']}: no change")
        return

    metadata["components"] = components
    sizes = []
    for component in components:
        props = component.get("properties") or {}
        viz = props.get("visualizationType") or ""
        report_format = props.get("reportFormat") or ""
        sizes.append((3, 4) if viz == "Metric" else widget_size(viz, report_format))
    metadata["layout"] = {
        "components": pack_layout(sizes),
        "gridLayout": (metadata.get("layout") or {}).get("gridLayout", True),
        "numColumns": (metadata.get("layout") or {}).get("numColumns", 12),
        "rowHeight": (metadata.get("layout") or {}).get("rowHeight", 36),
    }
    for field in DASHBOARD_RO_FIELDS:
        metadata.pop(field, None)
    remediator._patch(f"/analytics/dashboards/{dashboard_id}", metadata)
    final = remediator._get(f"/analytics/dashboards/{dashboard_id}/describe")
    print(f"{final['name']}: filters={len(final.get('filters') or [])} components={len(final.get('components') or [])}")


def ensure_forecast_finance_reports(remediator: Remediator) -> tuple[str, str, str, str, str]:
    base = remediator._report_describe("00OTb000008mvIjMAI").get("reportMetadata") or {}
    folder_id = base.get("folderId")
    today = date.today()
    current_start = f"{today.year}-01-01"
    current_end = today.isoformat()
    prior_start = f"{today.year - 1}-01-01"
    prior_end = f"{today.year - 1}-{today.month:02d}-{today.day:02d}"
    common_arr_filters = [
        _filter("WON", "equals", "True"),
        _filter("TYPE", "equals", "Land,Expand"),
        _filter("ACCOUNT_NAME", "notContain", "simcorp,test,delete"),
        _filter("FULL_NAME", "notContain", "Sabiniewicz,Profit"),
    ]
    common_renewal_filters = [
        _filter("WON", "equals", "True"),
        _filter("TYPE", "equals", "Renewal"),
        _filter("ACCOUNT_NAME", "notContain", "simcorp,test,delete"),
        _filter("FULL_NAME", "notContain", "Sabiniewicz,Profit"),
    ]

    won_arr_8q = {
        "name": "FA · Won ARR 8Q",
        "developerName": "FA_Won_ARR_8Q_v1",
        "description": "Closed won Land and Expand ARR by fiscal quarter over the last eight quarters.",
        "folderId": folder_id,
        "reportFormat": "SUMMARY",
        "reportType": {"type": "Opportunity"},
        "detailColumns": [
            "ACCOUNT_NAME",
            "OPPORTUNITY_NAME",
            "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            "CLOSE_DATE",
        ],
        "groupingsDown": [
            {"name": "FISCAL_QUARTER", "sortOrder": "Asc", "dateGranularity": "None"}
        ],
        "aggregates": [
            "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            "RowCount",
        ],
        "reportFilters": common_arr_filters,
        "standardDateFilter": {
            "column": "CLOSE_DATE",
            "durationValue": "CUSTOM",
            "startDate": "2024-07-01",
            "endDate": "2026-06-30",
        },
    }

    arr_ytd = {
        "name": "FA · Won ARR YTD",
        "developerName": "FA_Won_ARR_YTD_v1",
        "description": "Closed won Land and Expand ARR in the current fiscal year through today.",
        "folderId": folder_id,
        "reportFormat": "SUMMARY",
        "reportType": {"type": "Opportunity"},
        "detailColumns": [
            "ACCOUNT_NAME",
            "OPPORTUNITY_NAME",
            "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            "CLOSE_DATE",
        ],
        "groupingsDown": [
            {"name": "FULL_NAME", "sortOrder": "Asc", "dateGranularity": "None"}
        ],
        "aggregates": [
            "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            "RowCount",
        ],
        "reportFilters": common_arr_filters,
        "standardDateFilter": {
            "column": "CLOSE_DATE",
            "durationValue": "CUSTOM",
            "startDate": current_start,
            "endDate": current_end,
        },
    }

    arr_ly = {
        "name": "FA · Won ARR Same Period LY",
        "developerName": "FA_Won_ARR_Same_Period_LY_v1",
        "description": "Closed won Land and Expand ARR over the same year-to-date window in the prior fiscal year.",
        "folderId": folder_id,
        "reportFormat": "SUMMARY",
        "reportType": {"type": "Opportunity"},
        "detailColumns": [
            "ACCOUNT_NAME",
            "OPPORTUNITY_NAME",
            "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            "CLOSE_DATE",
        ],
        "groupingsDown": [
            {"name": "FULL_NAME", "sortOrder": "Asc", "dateGranularity": "None"}
        ],
        "aggregates": [
            "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            "RowCount",
        ],
        "reportFilters": common_arr_filters,
        "standardDateFilter": {
            "column": "CLOSE_DATE",
            "durationValue": "CUSTOM",
            "startDate": prior_start,
            "endDate": prior_end,
        },
    }

    renewal_ytd = {
        "name": "FA · Renewal ACV YTD",
        "developerName": "FA_Renewal_ACV_YTD_v1",
        "description": "Closed won renewal ACV in the current fiscal year through today.",
        "folderId": folder_id,
        "reportFormat": "SUMMARY",
        "reportType": {"type": "Opportunity"},
        "detailColumns": [
            "ACCOUNT_NAME",
            "OPPORTUNITY_NAME",
            "Opportunity.APTS_Renewal_ACV__c.CONVERT",
            "CLOSE_DATE",
        ],
        "groupingsDown": [
            {"name": "FULL_NAME", "sortOrder": "Asc", "dateGranularity": "None"}
        ],
        "aggregates": [
            "s!Opportunity.APTS_Renewal_ACV__c.CONVERT",
            "RowCount",
        ],
        "reportFilters": common_renewal_filters,
        "standardDateFilter": {
            "column": "CLOSE_DATE",
            "durationValue": "CUSTOM",
            "startDate": current_start,
            "endDate": current_end,
        },
    }

    renewal_ly = {
        "name": "FA · Renewal ACV Same Period LY",
        "developerName": "FA_Renewal_ACV_Same_Period_LY_v1",
        "description": "Closed won renewal ACV over the same year-to-date window in the prior fiscal year.",
        "folderId": folder_id,
        "reportFormat": "SUMMARY",
        "reportType": {"type": "Opportunity"},
        "detailColumns": [
            "ACCOUNT_NAME",
            "OPPORTUNITY_NAME",
            "Opportunity.APTS_Renewal_ACV__c.CONVERT",
            "CLOSE_DATE",
        ],
        "groupingsDown": [
            {"name": "FULL_NAME", "sortOrder": "Asc", "dateGranularity": "None"}
        ],
        "aggregates": [
            "s!Opportunity.APTS_Renewal_ACV__c.CONVERT",
            "RowCount",
        ],
        "reportFilters": common_renewal_filters,
        "standardDateFilter": {
            "column": "CLOSE_DATE",
            "durationValue": "CUSTOM",
            "startDate": prior_start,
            "endDate": prior_end,
        },
    }

    return (
        remediator._ensure_report(won_arr_8q),
        remediator._ensure_report(arr_ytd),
        remediator._ensure_report(arr_ly),
        remediator._ensure_report(renewal_ytd),
        remediator._ensure_report(renewal_ly),
    )


def ensure_renewals_gap_reports(remediator: Remediator) -> tuple[str, str, str]:
    base = remediator._report_describe("00OTb000008msUXMAY").get("reportMetadata") or {}
    folder_id = base.get("folderId")
    broad_window = {
        "column": "CLOSE_DATE",
        "durationValue": "CUSTOM",
        "startDate": "2000-01-01",
        "endDate": "2099-12-31",
    }
    common_renewal_filters = [
        _filter("CLOSED", "equals", "False"),
        _filter("TYPE", "equals", "Renewal"),
        _filter("FULL_NAME", "notContain", "Sabiniewicz"),
        _filter("ACCOUNT_NAME", "notContain", "QtC"),
        _filter("OPPORTUNITY_NAME", "notContain", "TEST"),
        _filter("OPPORTUNITY_NAME", "notContain", "ASH Dummy"),
        _filter("OPPORTUNITY_NAME", "notContain", "SBL Opp"),
        _filter("OPPORTUNITY_NAME", "notContain", "Back Office"),
        _filter("OPPORTUNITY_NAME", "notContain", "QTC_Test"),
        _filter("OPPORTUNITY_NAME", "notContain", "Generic q"),
        _filter("OPPORTUNITY_NAME", "notContain", "To Be Deleted"),
    ]

    expansion = {
        "name": "REN · Expansion Pipeline by Account",
        "developerName": "REN_Expansion_Pipeline_By_Account_v1",
        "description": "Open Expand opportunities in the current fiscal quarter, sorted by ARR for renewals-side expansion ownership.",
        "folderId": folder_id,
        "reportFormat": "SUMMARY",
        "reportType": {"type": "Opportunity"},
        "detailColumns": [
            "ACCOUNT_NAME",
            "OPPORTUNITY_NAME",
            "FULL_NAME",
            "STAGE_NAME",
            "CLOSE_DATE",
            "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
        ],
        "aggregates": [
            "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            "RowCount",
        ],
        "reportFilters": [
            _filter("CLOSED", "equals", "False"),
            _filter("TYPE", "equals", "Expand"),
            _filter("FULL_NAME", "notContain", "Sabiniewicz"),
            _filter("ACCOUNT_NAME", "notContain", "QtC"),
            _filter("OPPORTUNITY_NAME", "notContain", "TEST"),
            _filter("OPPORTUNITY_NAME", "notContain", "ASH Dummy"),
            _filter("OPPORTUNITY_NAME", "notContain", "SBL Opp"),
            _filter("OPPORTUNITY_NAME", "notContain", "Back Office"),
            _filter("OPPORTUNITY_NAME", "notContain", "QTC_Test"),
            _filter("OPPORTUNITY_NAME", "notContain", "Generic q"),
            _filter("OPPORTUNITY_NAME", "notContain", "To Be Deleted"),
        ],
        "sortBy": [{"sortColumn": "Opportunity.APTS_Opportunity_ARR__c.CONVERT", "sortOrder": "Desc"}],
        "standardDateFilter": {
            "column": "CLOSE_DATE",
            "durationValue": "THIS_FISCAL_QUARTER",
            "startDate": "2026-04-01",
            "endDate": "2026-06-30",
        },
    }

    adoption = {
        "name": "REN · Adoption Score Distribution",
        "developerName": "REN_Adoption_Score_Distribution_v1",
        "description": "Open renewal opportunities bucketed by account adoption score on the live 2.5-5.0 scale.",
        "folderId": folder_id,
        "reportFormat": "SUMMARY",
        "reportType": {"type": "Opportunity"},
        "detailColumns": [
            "ACCOUNT_NAME",
            "OPPORTUNITY_NAME",
            "Account.Overall_Adoption_Score__c",
            "Opportunity.APTS_Renewal_ACV__c.CONVERT",
        ],
        "buckets": [
            {
                "bucketType": "number",
                "developerName": "BucketField_AdoptionBand",
                "label": "Adoption Band",
                "nullTreatedAsZero": False,
                "otherBucketLabel": None,
                "sourceColumnName": "Account.Overall_Adoption_Score__c",
                "values": [
                    {"label": "2.5-2.9", "rangeUpperBound": 2.9, "sourceDimensionValues": None},
                    {"label": "3.0-3.4", "rangeUpperBound": 3.4, "sourceDimensionValues": None},
                    {"label": "3.5-3.9", "rangeUpperBound": 3.9, "sourceDimensionValues": None},
                    {"label": "4.0-4.4", "rangeUpperBound": 4.4, "sourceDimensionValues": None},
                    {"label": "4.5+", "rangeUpperBound": None, "sourceDimensionValues": None},
                ],
            }
        ],
        "groupingsDown": [
            {"name": "BucketField_AdoptionBand", "sortOrder": "Asc", "dateGranularity": "None"}
        ],
        "aggregates": ["RowCount"],
        "reportFilters": [
            *common_renewal_filters,
            _filter("Account.Overall_Adoption_Score__c", "notEqual", ""),
        ],
        "standardDateFilter": broad_window,
    }

    stuck = {
        "name": "REN · Stuck Renewals >30d",
        "developerName": "REN_Stuck_Renewals_30d_v1",
        "description": "Open renewals with more than 30 days at the current stage.",
        "folderId": folder_id,
        "reportFormat": "SUMMARY",
        "reportType": {"type": "Opportunity"},
        "detailColumns": [
            "ACCOUNT_NAME",
            "OPPORTUNITY_NAME",
            "FULL_NAME",
            "STAGE_NAME",
            "STAGE_DURATION",
            "CLOSE_DATE",
            "Opportunity.APTS_Renewal_ACV__c.CONVERT",
        ],
        "aggregates": [
            "s!Opportunity.APTS_Renewal_ACV__c.CONVERT",
            "RowCount",
        ],
        "reportFilters": [
            *common_renewal_filters,
            _filter("STAGE_DURATION", "greaterThan", "30"),
        ],
        "sortBy": [{"sortColumn": "Opportunity.APTS_Renewal_ACV__c.CONVERT", "sortOrder": "Desc"}],
        "standardDateFilter": broad_window,
    }

    return (
        remediator._ensure_report(expansion),
        remediator._ensure_report(adoption),
        remediator._ensure_report(stuck),
    )


def ensure_deal_desk_discount_report(remediator: Remediator) -> str:
    base = remediator._report_describe("00OTb000008mvx3MAA").get("reportMetadata") or {}
    folder_id = base.get("folderId")
    metadata = {
        "name": "DD · Discount Depth Pending",
        "developerName": "DD_Discount_Depth_Pending_v1",
        "description": "Pending Stage 20 approvals with populated ZIMIT discount, bucketed by discount percent.",
        "folderId": folder_id,
        "reportFormat": "SUMMARY",
        "reportType": {"type": "Opportunity"},
        "detailColumns": [
            "ACCOUNT_NAME",
            "OPPORTUNITY_NAME",
            "FULL_NAME",
            "Opportunity.ZIMIT_Discount__c",
            "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
        ],
        "buckets": [
            {
                "bucketType": "number",
                "developerName": "BucketField_DiscountBand",
                "label": "Discount Band",
                "nullTreatedAsZero": False,
                "otherBucketLabel": None,
                "sourceColumnName": "Opportunity.ZIMIT_Discount__c",
                "values": [
                    {"label": "0-10%", "rangeUpperBound": 10.0, "sourceDimensionValues": None},
                    {"label": "11-20%", "rangeUpperBound": 20.0, "sourceDimensionValues": None},
                    {"label": "21-30%", "rangeUpperBound": 30.0, "sourceDimensionValues": None},
                    {"label": "30%+", "rangeUpperBound": None, "sourceDimensionValues": None},
                ],
            }
        ],
        "groupingsDown": [
            {"name": "BucketField_DiscountBand", "sortOrder": "Asc", "dateGranularity": "None"}
        ],
        "aggregates": [
            "RowCount",
            "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
        ],
        "reportFilters": [
            _filter("CLOSED", "equals", "False"),
            _filter("TYPE", "equals", "Land"),
            _filter("Opportunity.Submit_for_Stage_20_Review__c", "equals", "True"),
            _filter("Opportunity.Stage_20_Approval__c", "equals", "False"),
            _filter("Opportunity.ZIMIT_Discount__c", "notEqual", ""),
            _filter("FULL_NAME", "notContain", "Sabiniewicz"),
            _filter("ACCOUNT_NAME", "notContain", "QtC"),
            _filter("OPPORTUNITY_NAME", "notContain", "TEST"),
            _filter("OPPORTUNITY_NAME", "notContain", "ASH Dummy"),
            _filter("OPPORTUNITY_NAME", "notContain", "SBL Opp"),
            _filter("OPPORTUNITY_NAME", "notContain", "Back Office"),
            _filter("OPPORTUNITY_NAME", "notContain", "QTC_Test"),
            _filter("OPPORTUNITY_NAME", "notContain", "Generic q"),
            _filter("OPPORTUNITY_NAME", "notContain", "To Be Deleted"),
        ],
        "standardDateFilter": {
            "column": "CLOSE_DATE",
            "durationValue": "CUSTOM",
            "startDate": "2000-01-01",
            "endDate": "2099-12-31",
        },
    }
    return remediator._ensure_report(metadata)


def patch_cro(remediator: Remediator) -> None:
    _, _, slippage_id = remediator.ensure_forecast_wave2_reports()
    additions = [
        remediator._bar_component(
            slippage_id,
            "Forecast Volatility",
            "Current-quarter push-count mix",
            "PUSH_COUNT",
            "RowCount",
            sort_order="Asc",
        ),
        remediator._bar_component(
            "00OTb000008nUrZMAU",
            "Stage Stickiness",
            "Avg days at stage",
            "STAGE_NAME",
            "a!STAGE_DURATION",
            sort_order="Asc",
        ),
    ]
    patch_dashboard(
        remediator,
        CRO,
        new_components=additions,
        remove_report_ids=STANDARD_REMOVE_CRO,
        dashboard_filters=remediator.standard_filters,
        filter_columns=copy.deepcopy(STANDARD_FILTER_COLS_LOCAL),
    )


def patch_forecast(remediator: Remediator) -> None:
    won_arr_8q_id, arr_ytd_id, arr_ly_id, renewal_ytd_id, renewal_ly_id = ensure_forecast_finance_reports(remediator)
    additions = [
        remediator._column_component(
            won_arr_8q_id,
            "Won ARR 8Q",
            "Closed won L+E ARR",
            "FISCAL_QUARTER",
            "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
        ),
        remediator._metric_component(
            arr_ytd_id,
            "Won ARR YTD",
            "Current FY through today",
            "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
        ),
        remediator._metric_component(
            arr_ly_id,
            "Won ARR LY SP",
            "Prior-year same period",
            "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
        ),
        remediator._metric_component(
            renewal_ytd_id,
            "Renewal ACV YTD",
            "Current FY through today",
            "s!Opportunity.APTS_Renewal_ACV__c.CONVERT",
        ),
        remediator._metric_component(
            renewal_ly_id,
            "Renewal ACV LY SP",
            "Prior-year same period",
            "s!Opportunity.APTS_Renewal_ACV__c.CONVERT",
        ),
    ]
    patch_dashboard(
        remediator,
        FORECAST,
        new_components=additions,
        remove_report_ids=STANDARD_REMOVE_FORECAST,
        dashboard_filters=remediator.standard_filters,
        filter_columns=copy.deepcopy(STANDARD_FILTER_COLS_LOCAL),
        header_overrides={"00OTb000008ngO5MAI": "Forecast Accuracy Proxy 8Q"},
        title_overrides={"00OTb000008ngO5MAI": "Won / stored forecast ARR by FQ"},
    )


def patch_renewals(remediator: Remediator) -> None:
    expansion_id, adoption_id, stuck_id = ensure_renewals_gap_reports(remediator)
    additions = [
        remediator._tabular_flex_component(
            expansion_id,
            "Expansion Pipeline by Account",
            "Open Expand ARR this Q",
            [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "FULL_NAME",
                "STAGE_NAME",
                "CLOSE_DATE",
                "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            ],
            sort_column="Opportunity.APTS_Opportunity_ARR__c.CONVERT",
        ),
        remediator._bar_component(
            adoption_id,
            "Adoption Score Distribution",
            "Open renewals by adoption band",
            "BucketField_AdoptionBand",
            "RowCount",
            sort_order="Asc",
        ),
        remediator._tabular_flex_component(
            stuck_id,
            "Stuck Renewals >30d",
            "Open renewals with long stage age",
            [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "FULL_NAME",
                "STAGE_NAME",
                "STAGE_DURATION",
                "CLOSE_DATE",
                "Opportunity.APTS_Renewal_ACV__c.CONVERT",
            ],
            sort_column="Opportunity.APTS_Renewal_ACV__c.CONVERT",
        ),
    ]
    patch_dashboard(
        remediator,
        RENEWALS,
        new_components=additions,
        remove_report_ids=STANDARD_REMOVE_RENEWALS,
        dashboard_filters=remediator.standard_filters,
        filter_columns=copy.deepcopy(STANDARD_FILTER_COLS_LOCAL),
    )


def patch_deal_desk(remediator: Remediator) -> None:
    discount_id = ensure_deal_desk_discount_report(remediator)
    additions = [
        remediator._bar_component(
            discount_id,
            "Discount Depth Pending",
            "ZIMIT discount on live approvals",
            "BucketField_DiscountBand",
            "RowCount",
            sort_order="Asc",
        )
    ]
    patch_dashboard(
        remediator,
        DEAL_DESK,
        new_components=additions,
        remove_report_ids=STANDARD_REMOVE_DEAL_DESK,
        dashboard_filters=remediator.standard_filters,
        filter_columns=copy.deepcopy(STANDARD_FILTER_COLS_LOCAL),
    )


def patch_scorecard(remediator: Remediator, scorecard_filters: list[dict[str, Any]]) -> None:
    additions = [
        {
            "header": "Quota Attainment YTD",
            "footer": None,
            "title": "Won L+E / annual goal",
            "reportId": "00OTb000008nehFMAQ",
            "type": "Report",
            "componentData": 0,
            "chartTheme": None,
            "properties": {
                "aggregates": [{"name": "FORMULA1"}],
                "autoSelectColumns": False,
                "drillUrl": None,
                "filterColumns": copy.deepcopy(SCORECARD_FILTER_COLS),
                "groupings": [
                    {
                        "inheritedReportSort": None,
                        "name": "FULL_NAME",
                        "sortAggregate": None,
                        "sortOrder": "Asc",
                        "dateGranularity": "None",
                    }
                ],
                "maxRows": None,
                "reportFormat": "SUMMARY",
                "sort": None,
                "useReportChart": False,
                "visualizationProperties": {
                    "decimalPrecision": -1,
                    "displayUnits": "auto",
                    "legendPosition": "Right",
                    "showPercentages": False,
                    "showValues": True,
                },
                "visualizationType": "Bar",
            },
        }
    ]
    patch_dashboard(
        remediator,
        SCORECARD,
        new_components=additions,
        remove_report_ids=STANDARD_REMOVE_SCORECARD,
        dashboard_filters=scorecard_filters,
        filter_columns=copy.deepcopy(SCORECARD_FILTER_COLS),
    )


def patch_sd_monthly(remediator: Remediator) -> None:
    additions = [
        remediator._tabular_flex_component(
            "00OTb000008muo6MAA",
            "Top Deals at Risk (≥1M)",
            "Einstein / risk / probability",
            [
                "OPPORTUNITY_NAME",
                "ACCOUNT_NAME",
                "STAGE_NAME",
                "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                "OPPORTUNITY_SCORE",
                "Opportunity.Risk_Assessment_Level__c",
                "PROBABILITY",
                "CLOSE_DATE",
                "FULL_NAME",
            ],
            sort_column="Opportunity.APTS_Opportunity_ARR__c.CONVERT",
        ),
        remediator._tabular_flex_component(
            "00OTb000008ekp7MAA",
            "Commercial Approval Queue",
            "Pending approval drill list",
            [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "FULL_NAME",
                "CLOSE_DATE",
                "NEXT_STEP",
                "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            ],
            sort_column="Opportunity.APTS_Opportunity_ARR__c.CONVERT",
        ),
    ]
    patch_dashboard(
        remediator,
        SD_MONTHLY,
        new_components=additions,
        remove_report_ids=STANDARD_REMOVE_SD,
        dashboard_filters=remediator.standard_filters,
        filter_columns=copy.deepcopy(STANDARD_FILTER_COLS_LOCAL),
    )


def main() -> int:
    remediator = Remediator()
    scorecard_filters = fetch_dashboard_filters(remediator, SCORECARD)

    patch_cro(remediator)
    patch_forecast(remediator)
    patch_renewals(remediator)
    patch_deal_desk(remediator)
    patch_scorecard(remediator, scorecard_filters)
    patch_sd_monthly(remediator)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
