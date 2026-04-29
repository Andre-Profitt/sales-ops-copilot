from __future__ import annotations

import copy
import json
import sys
from typing import Any

import requests

from scripts.sf_audit.improve_dashboard_layout import pack_layout, widget_size
from scripts.sf_audit.rebuild_sd_dashboard import STANDARD_FILTER_COLS
from scripts.sf_audit.reports import _filter, create_report, sf_session

API_VERSION = "v66.0"
BASE = lambda instance: f"{instance}/services/data/{API_VERSION}"

SD_MONTHLY = "01ZTb00000FSP7hMAH"
SALES_OPS = "01ZTb00000FSP9JMAX"
DEAL_DESK = "01ZTb00000FxYY5MAN"
CRO = "01ZTb00000FxYZhMAN"
FORECAST = "01ZTb00000FxYcvMAF"
QUARTER_CLOSE = "01ZTb00000FxYhlMAF"
RENEWALS = "01ZTb00000FxYTFMA3"
MARKETING = "01ZTb00000FxYbJMAV"
ACCOUNT_HEALTH = "01ZTb00000FxYeXMAV"

SALES_OPS_REPORTS = [
    "00OTb000008RfKDMA0",
    "00OTb000008TaEnMAK",
    "00OTb000008Ti97MAC",
    "00OQA000004OLk92AG",
    "00OTb000008Ti7VMAS",
    "00OTb000008fAlBMAU",
    "00OTb000008TZqcMAG",
    "00OTb000008fAjZMAU",
    "00OTb000008TZgvMAG",
    "00OTb000008fAmnMAE",
    "00OTb000008ekynMAA",
    "00OTb000008SrmLMAS",
    "00OTb000008eknVMAQ",
    "00OTb000008aTtJMAU",
    "00OTb000008ekp7MAA",
    "00OTb000008fBEDMA2",
    "00OTb000008ms4kMAA",
    "00OTb000008mvPBMAY",
    "00OTb000008mxM9MAI",
]

SALES_OPS_TYPE_FIXES = {
    "00OTb000008RfKDMA0": "Land,Expand",
    "00OTb000008TaEnMAK": "Land,Expand",
    "00OTb000008Ti7VMAS": "Land,Expand",
    "00OTb000008TZqcMAG": "Land,Expand",
    "00OTb000008fAjZMAU": "Land,Expand",
    "00OTb000008fAmnMAE": "Land,Expand",
    "00OTb000008ekynMAA": "Land,Expand",
    "00OTb000008eknVMAQ": "Land,Expand",
    "00OTb000008fBEDMA2": "Land",
}

SALES_OPS_OWNER_POLLUTION_FIXES = {
    "00OTb000008eknVMAQ",
}

DATE_FIX_REPORTS = {
    *SALES_OPS_REPORTS,
    "00OTb000008mvx3MAA",  # DD pending approval
    "00OTb000008muo6MAA",  # CRO top deals at risk
}

QUARTERLY_DATE_FIXES = {
    "00OTb000008mxPNMAY",  # Forecast · Einstein IqScore by Stage
}

BROAD_DATE_FIXES = {
    "00OTb000008mxNlMAI",  # Renewals · At-Risk Accounts
    "00OTb000008mwBZMAY",  # Marketing · Stale Open Leads >2y
    "00OTb000008mw8LMAQ",  # Marketing · Leads by Status
    "00OTb000008muswMAA",  # Account Health · Adoption Score by Tier
}

CRO_SOURCE_COMPONENTS = {
    "00OTb000008mvIjMAI": ("Bookings by Fiscal Quarter", "Won L+E ARR, last fiscal year"),
    "00OTb000008mvFVMAY": ("Forecast Category Split", "This-Q L+E by category"),
    "00OTb000008mvKLMAY": ("Win/Loss by Fiscal Quarter", "Bookings vs leakage trend (L+E)"),
}

DEAL_DESK_SOURCE_COMPONENTS = {
    "00OTb000008ekp7MAA": ("Commercial Approval Queue", "Commercial Approval Queue"),
    "00OTb000008fBEDMA2": ("Commercial Approval Current State", None),
    "00OTb000008aTtJMAU": ("Commercial Approval Approved YTD (Land)", "Approved deals YTD"),
    "00OTb000008fAlBMAU": ("Land Deals Lacking Commercial Approval Flow", "Lacking Approval Flow"),
}

POLLUTION_FILTERS = [
    _filter("FULL_NAME", "notEqual", "Maria Sabiniewicz"),
    _filter("ACCOUNT_NAME", "notContain", "QtC"),
    _filter("OPPORTUNITY_NAME", "notContain", "TEST"),
    _filter("OPPORTUNITY_NAME", "notContain", "ASH Dummy"),
    _filter("OPPORTUNITY_NAME", "notContain", "SBL Opp"),
    _filter("OPPORTUNITY_NAME", "notContain", "Back Office"),
    _filter("OPPORTUNITY_NAME", "notContain", "QTC_Test"),
    _filter("OPPORTUNITY_NAME", "notContain", "Generic q"),
    _filter("OPPORTUNITY_NAME", "notContain", "To Be Deleted"),
]

DESCRIPTION_FIXES = {
    "00OTb000008RfKDMA0": "Open opportunities below 50% probability, grouped by region, type, and owner. Forecast hygiene watchlist.",
    "00OTb000008TaEnMAK": "Open opportunities with no logged activity in 30+ days. Stale pipeline drill list.",
    "00OTb000008Ti97MAC": "Open high-value Land or Expand opportunities with no activity in 60+ days.",
    "00OQA000004OLk92AG": "Prospect or customer accounts with open opportunities but no approved KYC status.",
    "00OTb000008TZqcMAG": "Open opportunities where ARR is zero. Compensation and quoting cleanup queue.",
    "00OTb000008TZgvMAG": "Open Land or Expand opportunities with stale activity in the current quarter.",
    "00OTb000008ekynMAA": "Late-stage open opportunities missing Apttus Primary Quote Type.",
    "00OTb000008SrmLMAS": "Open overdue opportunities past their close date, grouped by region and fiscal quarter.",
    "00OTb000008eknVMAQ": "Open opportunities whose close date has already slipped past today.",
    "00OTb000008fBEDMA2": "Current commercial approval state split by approved versus pending.",
    "00OTb000008Ta9xMAC": "Open renewal opportunities on accounts flagged medium or high termination risk, grouped by risk tier and account tier.",
    "00OTb000008fBULMA2": "Open renewal opportunities in the current quarter, grouped by stage.",
    "00OTb000008ektxMAA": "Open renewal opportunities in the current quarter with renewal ACV and owner-level drilldown.",
}

TITLE_FIXES = {
    FORECAST: {
        "00OTb000008mwJdMAI": "By stage - discipline gap",
    },
}

HEADER_FIXES = {
    FORECAST: {
        "00OTb000008mwI1MAI": "Pacing - Won by Week",
    },
    QUARTER_CLOSE: {
        "00OTb000008mwTJMAY": "Pacing - Won by Week",
    },
}

CRO_WAVE2_REMOVE_REPORTS = {
    "00OTb000008mw3VMAQ",  # Renewal ACV by Region
    "00OTb000008mw0HMAQ",  # Won YTD by Region
}

SD_WAVE2_REMOVE_REPORTS = {
    "00OTb000008gHZJMA2",  # Closed Won FY26
    "00OTb000008gUrVMAU",  # Win Rate by Stage
    "00OTb000008msW9MAI",  # Pipeline Velocity by Type
    "00OTb000008msZNMAY",  # Governance Volume: Stage 3+ entry
    "00OTb000008mvLxMAI",  # Pipeline at Activity Risk
    "00OTb000008msSvMAI",  # Lost ARR by Stage (bar + metric)
}

SALES_OPS_WAVE2_REMOVE_REPORTS = {
    "00OTb000008RfKDMA0",  # Low Probability In Quarter
    "00OTb000008TaEnMAK",  # No Activity 30 Plus Days
    "00OTb000008fAmnMAE",  # Active Opps: No Activity
    "00OTb000008aTtJMAU",  # Commercial Approval Approved YTD (Land)
    "00OTb000008fBEDMA2",  # Commercial Approval Current State
}

FORECAST_WAVE2_REMOVE_REPORTS = {
    "00OTb000008mwEnMAI",  # Forecast Category Mix
}


class Remediator:
    def __init__(self) -> None:
        self.instance, self.token, _ = sf_session()
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        self.report_type_cache: dict[str, str] = {}
        self.report_name_cache: dict[str, str] = {}
        self.standard_filters = self._fetch_standard_filters()
        self.sd_components = self._component_map(SD_MONTHLY)
        self.sales_ops_components = self._component_map(SALES_OPS)

    def _get(self, path: str) -> dict[str, Any]:
        r = requests.get(f"{BASE(self.instance)}{path}", headers=self.headers, timeout=60)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = requests.patch(f"{BASE(self.instance)}{path}", headers=self.headers, json=body, timeout=60)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"PATCH {path} failed {r.status_code}: {r.text[:400]}")
        return r.json() if r.text else {}

    def _query(self, soql: str) -> list[dict[str, Any]]:
        r = requests.get(f"{BASE(self.instance)}/query", headers=self.headers, params={"q": soql}, timeout=60)
        r.raise_for_status()
        return r.json().get("records") or []

    def _fetch_standard_filters(self) -> list[dict[str, Any]]:
        d = self._get(f"/analytics/dashboards/{SD_MONTHLY}/describe")
        out = []
        for flt in d.get("filters") or []:
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

    def _component_map(self, dashboard_id: str) -> dict[str, dict[str, Any]]:
        d = self._get(f"/analytics/dashboards/{dashboard_id}/describe")
        out: dict[str, dict[str, Any]] = {}
        for comp in d.get("components") or []:
            rid = comp.get("reportId")
            if rid:
                out[rid] = comp
        return out

    def _report_describe(self, report_id: str) -> dict[str, Any]:
        return self._get(f"/analytics/reports/{report_id}/describe")

    def _report_type(self, report_id: str) -> str:
        if report_id not in self.report_type_cache:
            md = self._report_describe(report_id).get("reportMetadata") or {}
            self.report_type_cache[report_id] = ((md.get("reportType") or {}).get("type") or "")
            self.report_name_cache[report_id] = md.get("name") or report_id
        return self.report_type_cache[report_id]

    def _patch_report_metadata(self, report_id: str, mutate) -> bool:
        meta = copy.deepcopy((self._report_describe(report_id).get("reportMetadata") or {}))
        before = json.dumps(meta, sort_keys=True, default=str)
        mutate(meta)
        after = json.dumps(meta, sort_keys=True, default=str)
        if after == before:
            return False
        for ro in ("id", "type", "currency", "buckets", "crossFilters", "customSummaryFormula", "scope"):
            meta.pop(ro, None)
        self._patch(f"/analytics/reports/{report_id}", {"reportMetadata": meta})
        return True

    def _merge_filters(self, filters: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged = list(filters)
        seen = {
            (
                item.get("column"),
                item.get("operator"),
                item.get("value"),
                item.get("startValue"),
                item.get("endValue"),
            )
            for item in merged
        }
        for item in additions:
            key = (
                item.get("column"),
                item.get("operator"),
                item.get("value"),
                item.get("startValue"),
                item.get("endValue"),
            )
            if key not in seen:
                merged.append(copy.deepcopy(item))
                seen.add(key)
        return merged

    def patch_sales_ops_reports(self) -> None:
        type_fixed = 0
        date_fixed = 0
        pollution_fixed = 0
        for rid in SALES_OPS_REPORTS:
            def mutate(meta: dict[str, Any]) -> None:
                nonlocal type_fixed, date_fixed, pollution_fixed
                filters = list(meta.get("reportFilters") or [])
                target_type = SALES_OPS_TYPE_FIXES.get(rid)
                if target_type and not any(f.get("column") == "TYPE" for f in filters):
                    filters.append(_filter("TYPE", "equals", target_type))
                    meta["reportFilters"] = filters
                    type_fixed += 1
                if rid in SALES_OPS_OWNER_POLLUTION_FIXES and not any(
                    f.get("column") == "FULL_NAME" and "Sabiniewicz" in str(f.get("value") or "")
                    for f in filters
                ):
                    filters.append(_filter("FULL_NAME", "notContain", "Sabiniewicz"))
                    meta["reportFilters"] = filters
                    pollution_fixed += 1
                sdf = meta.get("standardDateFilter") or {}
                if sdf.get("durationValue") == "CUSTOM" and not sdf.get("startDate") and not sdf.get("endDate"):
                    sdf["startDate"] = "2000-01-01"
                    sdf["endDate"] = "2099-12-31"
                    meta["standardDateFilter"] = sdf
                    date_fixed += 1
            self._patch_report_metadata(rid, mutate)
        print(
            "Sales Ops report remediation: "
            f"type_fixes={type_fixed} owner_pollution_fixes={pollution_fixed} date_fixes={date_fixed}"
        )

    def patch_priority_date_filters(self) -> None:
        patched = 0
        for rid in sorted(DATE_FIX_REPORTS - set(SALES_OPS_REPORTS)):
            def mutate(meta: dict[str, Any]) -> None:
                nonlocal patched
                sdf = meta.get("standardDateFilter") or {}
                if sdf.get("durationValue") == "CUSTOM" and not sdf.get("startDate") and not sdf.get("endDate"):
                    sdf["startDate"] = "2000-01-01"
                    sdf["endDate"] = "2099-12-31"
                    meta["standardDateFilter"] = sdf
                    patched += 1
            self._patch_report_metadata(rid, mutate)
        print(f"CRO/Deal Desk date fixes={patched}")

    def patch_secondary_reports(self) -> None:
        patched = 0
        quarter_start = "2026-04-01"
        quarter_end = "2026-06-30"

        for rid in sorted(
            QUARTERLY_DATE_FIXES
            | BROAD_DATE_FIXES
            | set(DESCRIPTION_FIXES)
            | {
                "00OTb000008mwI1MAI",
                "00OTb000008mwJdMAI",
                "00OTb000008mwTJMAY",
                "00OTb000008mvc6MAA",
                "00OTb000008mxNlMAI",
                "00OTb000008muswMAA",
                "00OTb000008Ta9xMAC",
            }
        ):
            def mutate(meta: dict[str, Any]) -> None:
                nonlocal patched
                changed = False
                sdf = meta.get("standardDateFilter") or {}
                if rid in QUARTERLY_DATE_FIXES:
                    target = {
                        "column": "CLOSE_DATE",
                        "durationValue": "THIS_FISCAL_QUARTER",
                        "startDate": quarter_start,
                        "endDate": quarter_end,
                    }
                    if sdf != target:
                        meta["standardDateFilter"] = target
                        changed = True
                elif rid in BROAD_DATE_FIXES:
                    target = {
                        "column": sdf.get("column") or "CLOSE_DATE",
                        "durationValue": "CUSTOM",
                        "startDate": "2000-01-01",
                        "endDate": "2099-12-31",
                    }
                    if sdf != target:
                        meta["standardDateFilter"] = target
                        changed = True

                if rid == "00OTb000008mxNlMAI":
                    filters = list(meta.get("reportFilters") or [])
                    before = json.dumps(filters, sort_keys=True, default=str)
                    filters = self._merge_filters(filters, POLLUTION_FILTERS)
                    after = json.dumps(filters, sort_keys=True, default=str)
                    if after != before:
                        meta["reportFilters"] = filters
                        changed = True

                if rid == "00OTb000008muswMAA":
                    filters = list(meta.get("reportFilters") or [])
                    before = json.dumps(filters, sort_keys=True, default=str)
                    filters = self._merge_filters(filters, [_filter("TYPE", "equals", "Land,Expand")])
                    after = json.dumps(filters, sort_keys=True, default=str)
                    if after != before:
                        meta["reportFilters"] = filters
                        changed = True

                if rid == "00OTb000008mwJdMAI":
                    desc = meta.get("description") or ""
                    clean = desc.replace("—", "-")
                    if clean != desc:
                        meta["description"] = clean
                        changed = True

                if rid in {"00OTb000008mwI1MAI", "00OTb000008mwTJMAY", "00OTb000008mvc6MAA"}:
                    desc = meta.get("description") or ""
                    clean = desc.replace("—", "-")
                    if clean != desc:
                        meta["description"] = clean
                        changed = True

                if rid == "00OTb000008Ta9xMAC":
                    target = {
                        "column": "CLOSE_DATE",
                        "durationValue": "CUSTOM",
                        "startDate": "2000-01-01",
                        "endDate": "2099-12-31",
                    }
                    if sdf != target:
                        meta["standardDateFilter"] = target
                        changed = True
                    if meta.get("aggregates") != ["RowCount"]:
                        meta["aggregates"] = ["RowCount"]
                        changed = True

                if rid in DESCRIPTION_FIXES:
                    desc = meta.get("description") or ""
                    if desc != DESCRIPTION_FIXES[rid]:
                        meta["description"] = DESCRIPTION_FIXES[rid]
                        changed = True

                if changed:
                    patched += 1

            self._patch_report_metadata(rid, mutate)
        print(f"Forecast/Renewals/Marketing/Account Health report fixes={patched}")

    def patch_sd_wave2_reports(self) -> None:
        patched = 0
        target_ids = {
            "00OTb000008eknVMAQ",  # Close Date Slipped YTD
            "00OTb000008gUt7MAE",  # SD Days in Stage
            "00OTb000008nak5MAA",  # Scorecard · Stale Deals by Rep
            "00OTb000008navNMAQ",  # Scorecard · Approvals Stuck by Rep
        }
        for rid in sorted(target_ids):
            def mutate(meta: dict[str, Any]) -> None:
                nonlocal patched
                changed = False
                filters = list(meta.get("reportFilters") or [])
                before_filters = json.dumps(filters, sort_keys=True, default=str)
                if rid == "00OTb000008eknVMAQ":
                    filters = self._merge_filters(filters, POLLUTION_FILTERS)
                elif rid == "00OTb000008gUt7MAE":
                    next_filters = []
                    for item in filters:
                        if item.get("column") == "TYPE" and item.get("operator") == "equals":
                            if item.get("value") != "Land,Expand":
                                item = copy.deepcopy(item)
                                item["value"] = "Land,Expand"
                                changed = True
                        next_filters.append(item)
                    filters = next_filters
                elif rid == "00OTb000008nak5MAA":
                    filters = self._merge_filters(filters, [_filter("FULL_NAME", "notContain", "Sabiniewicz,Profit")])
                    boolean_filter = meta.get("reportBooleanFilter") or ""
                    if "16" not in boolean_filter:
                        meta["reportBooleanFilter"] = f"{boolean_filter} AND 16" if boolean_filter else "16"
                        changed = True
                elif rid == "00OTb000008navNMAQ":
                    filters = self._merge_filters(filters, [_filter("FULL_NAME", "notContain", "Sabiniewicz,Profit")])
                after_filters = json.dumps(filters, sort_keys=True, default=str)
                if after_filters != before_filters:
                    meta["reportFilters"] = filters
                    changed = True
                if changed:
                    patched += 1

            self._patch_report_metadata(rid, mutate)
        print(f"SD wave-2 report fixes={patched}")

    def _ensure_dashboard_filters(self, md: dict[str, Any]) -> bool:
        existing = md.get("filters") or []
        current_names = [f.get("name") for f in existing]
        target_names = [f.get("name") for f in self.standard_filters]
        if current_names == target_names and len(existing) == len(self.standard_filters):
            return False
        md["filters"] = copy.deepcopy(self.standard_filters)
        return True

    def _ensure_filter_columns(self, comp: dict[str, Any], report_id: str) -> bool:
        if self._report_type(report_id) != "Opportunity":
            return False
        props = comp.setdefault("properties", {})
        cur = props.get("filterColumns") or []
        cur_names = {f.get("name") for f in cur}
        changed = False
        merged = list(cur)
        for std in STANDARD_FILTER_COLS:
            if std["name"] not in cur_names:
                merged.append(copy.deepcopy(std))
                changed = True
        if changed:
            props["filterColumns"] = merged
        return changed

    def _clone_component(self, source: dict[str, Any], header: str | None = None, title: str | None = None) -> dict[str, Any]:
        comp = copy.deepcopy(source)
        comp.pop("id", None)
        comp.pop("lastModifiedDate", None)
        if header is not None:
            comp["header"] = header
        if title is not None:
            comp["title"] = title
        rid = comp.get("reportId")
        if rid:
            self._ensure_filter_columns(comp, rid)
        return comp

    def _metric_component(self, report_id: str, header: str, title: str, aggregate: str) -> dict[str, Any]:
        return {
            "header": header,
            "footer": None,
            "title": title,
            "reportId": report_id,
            "type": "Report",
            "componentData": 0,
            "chartTheme": None,
            "properties": {
                "aggregates": [{"name": aggregate}],
                "autoSelectColumns": False,
                "drillUrl": None,
                "filterColumns": list(STANDARD_FILTER_COLS),
                "groupings": [],
                "maxRows": None,
                "reportFormat": "SUMMARY",
                "sort": None,
                "useReportChart": False,
                "visualizationProperties": {
                    "decimalPrecision": 0,
                    "displayUnits": "auto",
                    "metric": aggregate,
                    "showPercentages": False,
                    "showValues": True,
                },
                "visualizationType": "Metric",
            },
        }

    def _bar_component(
        self,
        report_id: str,
        header: str,
        title: str,
        grouping: str,
        aggregate: str,
        sort_order: str = "Desc",
    ) -> dict[str, Any]:
        return {
            "header": header,
            "footer": None,
            "title": title,
            "reportId": report_id,
            "type": "Report",
            "componentData": 0,
            "chartTheme": None,
            "properties": {
                "aggregates": [{"name": aggregate}],
                "autoSelectColumns": False,
                "drillUrl": None,
                "filterColumns": list(STANDARD_FILTER_COLS),
                "groupings": [
                    {
                        "inheritedReportSort": None,
                        "name": grouping,
                        "sortAggregate": None,
                        "sortOrder": sort_order,
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

    def _column_component(
        self,
        report_id: str,
        header: str,
        title: str,
        grouping: str,
        aggregate: str,
    ) -> dict[str, Any]:
        return {
            "header": header,
            "footer": None,
            "title": title,
            "reportId": report_id,
            "type": "Report",
            "componentData": 0,
            "chartTheme": None,
            "properties": {
                "aggregates": [{"name": aggregate}],
                "autoSelectColumns": False,
                "drillUrl": None,
                "filterColumns": list(STANDARD_FILTER_COLS),
                "groupings": [
                    {
                        "inheritedReportSort": None,
                        "name": grouping,
                        "sortAggregate": None,
                        "sortOrder": "Asc",
                    }
                ],
                "maxRows": None,
                "reportFormat": "SUMMARY",
                "sort": None,
                "useReportChart": False,
                "visualizationProperties": {
                    "aggregateVisualizationInfos": [{"axis": "Y", "visualizationType": "Column"}],
                    "axisRange": {"max": None, "min": None, "rangeType": "auto"},
                    "decimalPrecision": -1,
                    "displayUnits": "auto",
                    "groupByType": "none",
                    "legendPosition": "Right",
                    "referenceLineColors": [],
                    "referenceLineValues": [],
                    "showValues": True,
                    "sortLegendValues": False,
                },
                "visualizationType": "Column",
            },
        }

    def _tabular_flex_component(
        self,
        report_id: str,
        header: str,
        title: str | None,
        columns: list[str],
        sort_column: str | None = None,
    ) -> dict[str, Any]:
        return {
            "header": header,
            "footer": None,
            "title": title,
            "reportId": report_id,
            "type": "Report",
            "componentData": 5,
            "chartTheme": None,
            "properties": {
                "aggregates": [],
                "autoSelectColumns": False,
                "drillUrl": None,
                "filterColumns": list(STANDARD_FILTER_COLS),
                "groupings": [],
                "maxRows": None,
                "reportFormat": "SUMMARY",
                "sort": (
                    {
                        "column": sort_column,
                        "sortOrder": "Desc",
                        "type": "label",
                    }
                    if sort_column
                    else None
                ),
                "useReportChart": False,
                "useReportTableSetting": False,
                "visualizationProperties": {
                    "breakPoints": [],
                    "decimalPrecision": -1,
                    "displayUnits": "auto",
                    "flexTableType": "tabular",
                    "showChatterPhotos": False,
                    "tableColumns": [
                        {
                            "column": column,
                            "showSubTotal": False,
                            "showTotal": False,
                            "type": "detail",
                        }
                        for column in columns
                    ],
                },
                "visualizationType": "FlexTable",
            },
        }

    def _find_report_by_name(self, name: str) -> str | None:
        safe = name.replace("'", "\\'")
        recs = self._query(f"SELECT Id, Name FROM Report WHERE Name = '{safe}' LIMIT 1")
        return recs[0]["Id"] if recs else None

    def _ensure_report(self, metadata: dict[str, Any]) -> str:
        existing_id = self._find_report_by_name(metadata["name"])
        if existing_id:
            def mutate(meta: dict[str, Any]) -> None:
                for k, v in metadata.items():
                    meta[k] = copy.deepcopy(v)
            self._patch_report_metadata(existing_id, mutate)
            return existing_id
        result = create_report(self.instance, self.token, metadata)
        if not result.get("ok"):
            raise RuntimeError(f"create report failed for {metadata['name']}: {result.get('error')}")
        return result["id"]

    def ensure_deal_desk_reports(self) -> tuple[str, str, str, str]:
        base = self._report_describe("00OTb000008mvx3MAA").get("reportMetadata") or {}
        folder_id = base.get("folderId")

        breach = copy.deepcopy(base)
        breach.update(
            {
                "name": "DD · Approval SLA Breach >5d",
                "developerName": "DD_Approval_SLA_Breach_5d_v1",
                "groupingsDown": [{"name": "FULL_NAME", "sortOrder": "Desc", "dateGranularity": "None"}],
                "aggregates": ["RowCount", "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT"],
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "Opportunity.Submit_for_Stage_20_Review_Date__c",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                "standardDateFilter": {
                    "column": "Opportunity.Submit_for_Stage_20_Review_Date__c",
                    "durationValue": "CUSTOM",
                    "startDate": "2000-01-01",
                    "endDate": "2099-12-31",
                },
            }
        )
        filters = [f for f in breach.get("reportFilters") or [] if f.get("column") != "Opportunity.Submit_for_Stage_20_Review_Date__c"]
        filters.append(_filter("Opportunity.Submit_for_Stage_20_Review_Date__c", "lessThan", "LAST_N_DAYS:5"))
        breach["reportFilters"] = filters

        workload = copy.deepcopy(base)
        workload.update(
            {
                "name": "DD · Pending Approval by Owner",
                "developerName": "DD_Pending_Approval_By_Owner_v1",
                "groupingsDown": [{"name": "FULL_NAME", "sortOrder": "Desc", "dateGranularity": "None"}],
                "aggregates": ["RowCount", "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT"],
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "Opportunity.Submit_for_Stage_20_Review_Date__c",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                "standardDateFilter": {
                    "column": "Opportunity.Submit_for_Stage_20_Review_Date__c",
                    "durationValue": "CUSTOM",
                    "startDate": "2000-01-01",
                    "endDate": "2099-12-31",
                },
            }
        )
        cycle = {
            "name": "DD · Approval Cycle Days by Month",
            "developerName": "DD_Approval_Cycle_Days_By_Month_v1",
            "description": "Average and max days from Stage 20 submission to approval, grouped by approval month, trailing 12 months.",
            "folderId": folder_id,
            "reportFormat": "SUMMARY",
            "reportType": {"type": "Opportunity"},
            "detailColumns": [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "Opportunity.Submit_for_Stage_20_Review_Date__c",
                "CDF1",
            ],
            "groupingsDown": [
                {
                    "name": "Opportunity.Stage_20_Approval_Date__c",
                    "sortOrder": "Asc",
                    "dateGranularity": "Month",
                }
            ],
            "aggregates": ["a!CDF1", "mx!CDF1", "RowCount"],
            "customDetailFormula": {
                "CDF1": {
                    "dataType": "double",
                    "decimalPlaces": 0,
                    "description": "Days from submit to approval",
                    "formula": "Opportunity.Stage_20_Approval_Date__c - Opportunity.Submit_for_Stage_20_Review_Date__c",
                    "formulaType": "number",
                    "label": "Approval Cycle Days",
                }
            },
            "reportFilters": [
                _filter("Opportunity.Stage_20_Approval_Date__c", "notEqual", ""),
                _filter("Opportunity.Submit_for_Stage_20_Review_Date__c", "notEqual", ""),
                _filter("TYPE", "equals", "Land"),
                _filter("FULL_NAME", "notContain", "Sabiniewicz"),
                _filter("ACCOUNT_NAME", "notContain", "QtC"),
                _filter("OPPORTUNITY_NAME", "notContain", "TEST"),
            ],
            "standardDateFilter": {
                "column": "Opportunity.Stage_20_Approval_Date__c",
                "durationValue": "CUSTOM",
                "startDate": "2025-04-29",
                "endDate": "2026-04-29",
            },
        }
        sla_trend = {
            "name": "DD · Approval SLA Breaches by Month",
            "developerName": "DD_Approval_SLA_Breaches_By_Month_v1",
            "description": "Count of approvals taking more than five days, grouped by approval month, trailing 12 months.",
            "folderId": folder_id,
            "reportFormat": "SUMMARY",
            "reportType": {"type": "Opportunity"},
            "detailColumns": ["ACCOUNT_NAME", "OPPORTUNITY_NAME", "CDF1"],
            "groupingsDown": [
                {
                    "name": "Opportunity.Stage_20_Approval_Date__c",
                    "sortOrder": "Asc",
                    "dateGranularity": "Month",
                }
            ],
            "aggregates": ["RowCount"],
            "customDetailFormula": {
                "CDF1": {
                    "dataType": "double",
                    "decimalPlaces": 0,
                    "description": "Days from submit to approval",
                    "formula": "Opportunity.Stage_20_Approval_Date__c - Opportunity.Submit_for_Stage_20_Review_Date__c",
                    "formulaType": "number",
                    "label": "Approval Cycle Days",
                }
            },
            "reportFilters": [
                _filter("Opportunity.Stage_20_Approval_Date__c", "notEqual", ""),
                _filter("Opportunity.Submit_for_Stage_20_Review_Date__c", "notEqual", ""),
                _filter("CDF1", "greaterThan", "5"),
                _filter("TYPE", "equals", "Land"),
                _filter("FULL_NAME", "notContain", "Sabiniewicz"),
            ],
            "standardDateFilter": {
                "column": "Opportunity.Stage_20_Approval_Date__c",
                "durationValue": "CUSTOM",
                "startDate": "2025-04-29",
                "endDate": "2026-04-29",
            },
        }
        breach_id = self._ensure_report(breach)
        workload_id = self._ensure_report(workload)
        cycle_id = self._ensure_report(cycle)
        sla_trend_id = self._ensure_report(sla_trend)
        return breach_id, workload_id, cycle_id, sla_trend_id

    def ensure_cro_wave2_reports(self) -> tuple[str, str, str]:
        base = self._report_describe("00OTb000008mvIjMAI").get("reportMetadata") or {}
        folder_id = base.get("folderId")
        common_filters = [
            _filter("TYPE", "equals", "Land,Expand"),
            _filter("User.Annual_Revenue_Goal__c", "greaterThan", "0"),
            _filter("ACCOUNT_NAME", "notContain", "simcorp,test,delete"),
            _filter("FULL_NAME", "notContain", "Sabiniewicz,Profit"),
        ]

        attainment = {
            "name": "CRO · Quota Attainment YTD",
            "developerName": "CRO_Quota_Attainment_YTD_v1",
            "description": "Won Land and Expand ARR in the current fiscal year divided by annual goal, grouped by rep and sorted from lowest attainment upward.",
            "folderId": folder_id,
            "reportFormat": "SUMMARY",
            "reportType": {"type": "Opportunity"},
            "detailColumns": [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                "User.Annual_Revenue_Goal__c.CONVERT",
            ],
            "groupingsDown": [
                {
                    "name": "FULL_NAME",
                    "sortOrder": "Asc",
                    "sortAggregate": "FORMULA1",
                    "dateGranularity": "None",
                }
            ],
            "aggregates": [
                "FORMULA1",
                "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                "mx!User.Annual_Revenue_Goal__c.CONVERT",
                "RowCount",
            ],
            "customSummaryFormula": {
                "FORMULA1": {
                    "label": "Attainment %",
                    "description": "Won ARR YTD divided by annual goal",
                    "formula": "Opportunity.APTS_Opportunity_ARR__c.CONVERT:SUM/User.Annual_Revenue_Goal__c.CONVERT:MAX",
                    "formulaType": "percent",
                    "downGroup": None,
                    "downGroupType": "all",
                    "acrossGroup": None,
                    "acrossGroupType": "all",
                    "decimalPlaces": 1,
                }
            },
            "reportFilters": [
                _filter("WON", "equals", "True"),
                *common_filters,
            ],
            "standardDateFilter": {
                "column": "CLOSE_DATE",
                "durationValue": "THIS_FISCAL_YEAR",
                "startDate": "2026-01-01",
                "endDate": "2026-12-31",
            },
        }
        coverage = {
            "name": "CRO · Coverage x by Rep",
            "developerName": "CRO_Coverage_X_By_Rep_v1",
            "description": "Open Land and Expand ARR in the next two fiscal quarters divided by half-year quota, grouped by rep and sorted from lowest coverage upward.",
            "folderId": folder_id,
            "reportFormat": "SUMMARY",
            "reportType": {"type": "Opportunity"},
            "detailColumns": [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                "User.Annual_Revenue_Goal__c.CONVERT",
            ],
            "groupingsDown": [
                {
                    "name": "FULL_NAME",
                    "sortOrder": "Asc",
                    "sortAggregate": "FORMULA1",
                    "dateGranularity": "None",
                }
            ],
            "aggregates": [
                "FORMULA1",
                "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                "mx!User.Annual_Revenue_Goal__c.CONVERT",
                "RowCount",
            ],
            "customSummaryFormula": {
                "FORMULA1": {
                    "label": "Coverage x",
                    "description": "Next two fiscal quarters open ARR divided by half-year goal",
                    "formula": "2*Opportunity.APTS_Opportunity_ARR__c.CONVERT:SUM/User.Annual_Revenue_Goal__c.CONVERT:MAX",
                    "formulaType": "number",
                    "downGroup": None,
                    "downGroupType": "all",
                    "acrossGroup": None,
                    "acrossGroupType": "all",
                    "decimalPlaces": 2,
                }
            },
            "reportFilters": [
                _filter("CLOSED", "equals", "False"),
                *common_filters,
            ],
            "standardDateFilter": {
                "column": "CLOSE_DATE",
                "durationValue": "CUSTOM",
                "startDate": "2026-04-01",
                "endDate": "2026-09-30",
            },
        }
        win_rate = {
            "name": "CRO · Win Rate Trend 8Q",
            "developerName": "CRO_Win_Rate_Trend_8Q_v1",
            "description": "Closed Land and Expand opportunities by fiscal quarter with win-rate summary formula over the last eight quarters.",
            "folderId": folder_id,
            "reportFormat": "SUMMARY",
            "reportType": {"type": "Opportunity"},
            "detailColumns": ["ACCOUNT_NAME", "OPPORTUNITY_NAME"],
            "groupingsDown": [
                {
                    "name": "FISCAL_QUARTER",
                    "sortOrder": "Asc",
                    "dateGranularity": "None",
                }
            ],
            "aggregates": ["FORMULA1", "RowCount"],
            "customSummaryFormula": {
                "FORMULA1": {
                    "label": "Win Rate %",
                    "description": "Won / closed by fiscal quarter",
                    "formula": "WON:SUM/CLOSED:SUM",
                    "formulaType": "percent",
                    "downGroup": None,
                    "downGroupType": "all",
                    "acrossGroup": None,
                    "acrossGroupType": "all",
                    "decimalPlaces": 1,
                }
            },
            "reportFilters": [
                _filter("CLOSED", "equals", "True"),
                _filter("TYPE", "equals", "Land,Expand"),
                _filter("ACCOUNT_NAME", "notContain", "simcorp,test,delete"),
                _filter("FULL_NAME", "notContain", "Sabiniewicz,Profit"),
            ],
            "standardDateFilter": {
                "column": "CLOSE_DATE",
                "durationValue": "CUSTOM",
                "startDate": "2024-07-01",
                "endDate": "2026-06-30",
            },
        }
        attainment_id = self._ensure_report(attainment)
        coverage_id = self._ensure_report(coverage)
        win_rate_id = self._ensure_report(win_rate)
        return attainment_id, coverage_id, win_rate_id

    def ensure_forecast_wave2_reports(self) -> tuple[str, str, str]:
        base = self._report_describe("00OTb000008mvYsMAI").get("reportMetadata") or {}
        folder_id = base.get("folderId")
        common_filters = [
            _filter("TYPE", "equals", "Land,Expand"),
            _filter("ACCOUNT_NAME", "notContain", "simcorp,test,delete"),
            _filter("FULL_NAME", "notContain", "Sabiniewicz,Profit"),
        ]

        accuracy = {
            "name": "FA · Forecast Accuracy 8Q",
            "developerName": "FA_Forecast_Accuracy_8Q_v1",
            "description": "Won ARR divided by forecast ARR by fiscal quarter over the last eight quarters. Practical calibration proxy using stored forecast ARR on closed won deals.",
            "folderId": folder_id,
            "reportFormat": "SUMMARY",
            "reportType": {"type": "Opportunity"},
            "detailColumns": [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                "Opportunity.APTS_Forecast_ARR__c.CONVERT",
                "CLOSE_DATE",
            ],
            "groupingsDown": [
                {
                    "name": "FISCAL_QUARTER",
                    "sortOrder": "Asc",
                    "dateGranularity": "None",
                }
            ],
            "aggregates": [
                "FORMULA1",
                "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                "s!Opportunity.APTS_Forecast_ARR__c.CONVERT",
                "RowCount",
            ],
            "customSummaryFormula": {
                "FORMULA1": {
                    "label": "Won / Forecast %",
                    "description": "Closed won ARR divided by stored forecast ARR",
                    "formula": "Opportunity.APTS_Opportunity_ARR__c.CONVERT:SUM/Opportunity.APTS_Forecast_ARR__c.CONVERT:SUM",
                    "formulaType": "percent",
                    "downGroup": None,
                    "downGroupType": "all",
                    "acrossGroup": None,
                    "acrossGroupType": "all",
                    "decimalPlaces": 1,
                }
            },
            "reportFilters": [
                _filter("WON", "equals", "True"),
                *common_filters,
            ],
            "standardDateFilter": {
                "column": "CLOSE_DATE",
                "durationValue": "CUSTOM",
                "startDate": "2024-07-01",
                "endDate": "2026-06-30",
            },
        }

        commit_risk = {
            "name": "FA · Commit Deals at Risk",
            "developerName": "FA_Commit_Deals_At_Risk_v1",
            "description": "Open commit deals in the current quarter with repeated push-count risk. Forecast review drill list.",
            "folderId": folder_id,
            "reportFormat": "SUMMARY",
            "reportType": {"type": "Opportunity"},
            "detailColumns": [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "FULL_NAME",
                "STAGE_NAME",
                "CLOSE_DATE",
                "PUSH_COUNT",
                "NEXT_STEP",
                "LAST_ACTIVITY",
                "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            ],
            "groupingsDown": [
                {
                    "name": "Opportunity.Sales_Region__c",
                    "sortOrder": "Desc",
                    "dateGranularity": "None",
                }
            ],
            "aggregates": [
                "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                "RowCount",
            ],
            "reportFilters": [
                _filter("CLOSED", "equals", "False"),
                _filter("FORECAST_CATEGORY", "equals", "Commit"),
                _filter("PUSH_COUNT", "greaterThan", "1"),
                *common_filters,
            ],
            "sortBy": [{"sortColumn": "Opportunity.APTS_Opportunity_ARR__c.CONVERT", "sortOrder": "Desc"}],
            "standardDateFilter": {
                "column": "CLOSE_DATE",
                "durationValue": "THIS_FISCAL_QUARTER",
                "startDate": "2026-04-01",
                "endDate": "2026-06-30",
            },
        }

        slippage = {
            "name": "FA · Slippage by Push Count",
            "developerName": "FA_Slippage_By_Push_Count_v1",
            "description": "Open current-quarter Land and Expand opportunities with at least one push, grouped by push count.",
            "folderId": folder_id,
            "reportFormat": "SUMMARY",
            "reportType": {"type": "Opportunity"},
            "detailColumns": [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "FULL_NAME",
                "STAGE_NAME",
                "FORECAST_CATEGORY",
                "CLOSE_DATE",
                "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            ],
            "groupingsDown": [
                {
                    "name": "PUSH_COUNT",
                    "sortOrder": "Desc",
                    "dateGranularity": "None",
                }
            ],
            "aggregates": [
                "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                "RowCount",
            ],
            "reportFilters": [
                _filter("CLOSED", "equals", "False"),
                _filter("PUSH_COUNT", "greaterThan", "0"),
                *common_filters,
            ],
            "standardDateFilter": {
                "column": "CLOSE_DATE",
                "durationValue": "THIS_FISCAL_QUARTER",
                "startDate": "2026-04-01",
                "endDate": "2026-06-30",
            },
        }

        accuracy_id = self._ensure_report(accuracy)
        commit_risk_id = self._ensure_report(commit_risk)
        slippage_id = self._ensure_report(slippage)
        return accuracy_id, commit_risk_id, slippage_id

    def ensure_forecast_wave3_reports(self) -> tuple[str, str]:
        base = self._report_describe("00OTb000008mvYsMAI").get("reportMetadata") or {}
        folder_id = base.get("folderId")
        common_arr_filters = [
            _filter("WON", "equals", "True"),
            _filter("TYPE", "equals", "Land,Expand"),
            _filter("ACCOUNT_NAME", "notContain", "simcorp,test,delete"),
            _filter("FULL_NAME", "notContain", "Sabiniewicz,Profit"),
        ]
        avg_deal_size = {
            "name": "FA · Avg Deal Size 8Q",
            "developerName": "FA_Avg_Deal_Size_8Q_v1",
            "description": "Average won Land and Expand ARR by fiscal quarter over the last eight quarters.",
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
                {
                    "name": "FISCAL_QUARTER",
                    "sortOrder": "Asc",
                    "dateGranularity": "None",
                }
            ],
            "aggregates": [
                "a!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
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
        renewal_bookings = {
            "name": "FA · Renewal ACV Won by FQ",
            "developerName": "FA_Renewal_ACV_Won_by_FQ_v1",
            "description": "Closed won renewal ACV by fiscal quarter over the last eight quarters.",
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
                {
                    "name": "FISCAL_QUARTER",
                    "sortOrder": "Asc",
                    "dateGranularity": "None",
                }
            ],
            "aggregates": [
                "s!Opportunity.APTS_Renewal_ACV__c.CONVERT",
                "RowCount",
            ],
            "reportFilters": [
                _filter("WON", "equals", "True"),
                _filter("TYPE", "equals", "Renewal"),
                _filter("ACCOUNT_NAME", "notContain", "simcorp,test,delete"),
                _filter("FULL_NAME", "notContain", "Sabiniewicz,Profit"),
            ],
            "standardDateFilter": {
                "column": "CLOSE_DATE",
                "durationValue": "CUSTOM",
                "startDate": "2024-07-01",
                "endDate": "2026-06-30",
            },
        }
        avg_id = self._ensure_report(avg_deal_size)
        renewal_id = self._ensure_report(renewal_bookings)
        return avg_id, renewal_id

    def patch_dashboard(
        self,
        dashboard_id: str,
        new_components: list[dict[str, Any]] | None = None,
        remove_report_ids: set[str] | None = None,
    ) -> None:
        md = self._get(f"/analytics/dashboards/{dashboard_id}/describe")
        components = [
            c
            for c in (md.get("components") or [])
            if (c.get("reportId") or "") not in (remove_report_ids or set())
        ]
        changed = self._ensure_dashboard_filters(md)
        if remove_report_ids:
            original_components = list(md.get("components") or [])
            if len(original_components) != len(components):
                changed = True
        existing_rids = {c.get("reportId") for c in components}
        for comp in components:
            rid = comp.get("reportId")
            if rid:
                changed = self._ensure_filter_columns(comp, rid) or changed
                fixed_title = TITLE_FIXES.get(dashboard_id, {}).get(rid)
                if fixed_title and comp.get("title") != fixed_title:
                    comp["title"] = fixed_title
                    changed = True
                fixed_header = HEADER_FIXES.get(dashboard_id, {}).get(rid)
                if fixed_header and comp.get("header") != fixed_header:
                    comp["header"] = fixed_header
                    changed = True
        for comp in new_components or []:
            rid = comp.get("reportId")
            if rid and rid in existing_rids:
                continue
            if rid:
                self._ensure_filter_columns(comp, rid)
            components.append(comp)
            existing_rids.add(rid)
            changed = True
        if not changed:
            print(f"{dashboard_id}: no dashboard change")
            return
        md["components"] = components
        sizes = []
        for c in components:
            props = c.get("properties") or {}
            viz = props.get("visualizationType") or ""
            rf = props.get("reportFormat") or ""
            sizes.append((3, 4) if viz == "Metric" else widget_size(viz, rf))
        md["layout"] = {
            "components": pack_layout(sizes),
            "gridLayout": (md.get("layout") or {}).get("gridLayout", True),
            "numColumns": (md.get("layout") or {}).get("numColumns", 12),
            "rowHeight": (md.get("layout") or {}).get("rowHeight", 36),
        }
        for ro in ("id", "createdById", "createdDate", "lastModifiedDate", "namespace", "type", "developerName", "folderId", "folderName", "url", "labels", "ownerId"):
            md.pop(ro, None)
        self._patch(f"/analytics/dashboards/{dashboard_id}", md)
        final = self._get(f"/analytics/dashboards/{dashboard_id}/describe")
        print(f"{final['name']}: filters={len(final.get('filters') or [])} components={len(final.get('components') or [])}")

    def remediate_sales_ops_dashboard(self) -> None:
        cycle_id = self._find_report_by_name("DD · Approval Cycle Days by Month")
        if not cycle_id:
            raise RuntimeError("missing report: DD · Approval Cycle Days by Month")
        additions = [
            self._bar_component(
                "00OTb000008nehFMAQ",
                "Quota Attainment YTD",
                "Won L+E / annual goal",
                "FULL_NAME",
                "FORMULA1",
                sort_order="Asc",
            ),
            self._bar_component(
                "00OTb000008nePVMAY",
                "Coverage x by Rep",
                "Next 2Q / half-year goal",
                "FULL_NAME",
                "FORMULA1",
                sort_order="Asc",
            ),
            self._bar_component(
                "00OTb000008nak5MAA",
                "Stale Deals by Rep",
                "No activity 14d+",
                "FULL_NAME",
                "RowCount",
            ),
            self._bar_component(
                "00OTb000008navNMAQ",
                "Approvals Stuck by Rep",
                "Stage 20 pending >5d",
                "FULL_NAME",
                "RowCount",
            ),
            self._column_component(
                cycle_id,
                "Approval Cycle Days by Month",
                "Avg submit-to-approve days",
                "Opportunity.Stage_20_Approval_Date__c",
                "a!CDF1",
            ),
        ]
        self.patch_dashboard(SALES_OPS, additions, remove_report_ids=SALES_OPS_WAVE2_REMOVE_REPORTS)

    def remediate_deal_desk_dashboard(self) -> None:
        breach_id, workload_id, cycle_id, sla_trend_id = self.ensure_deal_desk_reports()
        additions: list[dict[str, Any]] = []
        for rid, (header, title) in DEAL_DESK_SOURCE_COMPONENTS.items():
            additions.append(self._clone_component(self.sales_ops_components[rid], header=header, title=title))
        additions.append(self._metric_component(breach_id, "Approval SLA Breach (>5d)", "Pending approvals", "RowCount"))
        additions.append(self._bar_component(workload_id, "Pending Approvals by Owner", "Queue ownership", "FULL_NAME", "RowCount"))
        additions.append(
            self._column_component(
                cycle_id,
                "Approval Cycle Days by Month",
                "Avg submit-to-approve days",
                "Opportunity.Stage_20_Approval_Date__c",
                "a!CDF1",
            )
        )
        additions.append(
            self._column_component(
                sla_trend_id,
                "Approval SLA Breaches by Month",
                ">5d approvals",
                "Opportunity.Stage_20_Approval_Date__c",
                "RowCount",
            )
        )
        self.patch_dashboard(DEAL_DESK, additions)

    def remediate_cro_dashboard(self) -> None:
        additions: list[dict[str, Any]] = []
        for rid, (header, title) in CRO_SOURCE_COMPONENTS.items():
            additions.append(self._clone_component(self.sd_components[rid], header=header, title=title))
        self.patch_dashboard(CRO, additions)

    def remediate_cro_wave2_dashboard(self) -> None:
        attainment_id, coverage_id, win_rate_id = self.ensure_cro_wave2_reports()
        additions = [
            self._bar_component(
                attainment_id,
                "Quota Attainment YTD",
                "Won L+E / annual goal",
                "FULL_NAME",
                "FORMULA1",
                sort_order="Asc",
            ),
            self._bar_component(
                coverage_id,
                "Coverage x by Rep",
                "Next 2Q / half-year goal",
                "FULL_NAME",
                "FORMULA1",
                sort_order="Asc",
            ),
            self._column_component(
                win_rate_id,
                "Win Rate Trend 8Q",
                "Closed L+E by fiscal quarter",
                "FISCAL_QUARTER",
                "FORMULA1",
            ),
            self._metric_component(
                "00OTb000008mxNlMAI",
                "At-Risk Renewal ACV",
                "High/Med risk open ACV",
                "s!Opportunity.APTS_Renewal_ACV__c.CONVERT",
            ),
        ]
        self.patch_dashboard(CRO, additions, remove_report_ids=CRO_WAVE2_REMOVE_REPORTS)

    def remediate_sd_wave2_dashboard(self) -> None:
        additions = [
            self._bar_component(
                "00OTb000008nehFMAQ",
                "Quota Attainment YTD",
                "Won L+E / annual goal",
                "FULL_NAME",
                "FORMULA1",
                sort_order="Asc",
            ),
            self._bar_component(
                "00OTb000008nePVMAY",
                "Coverage x by Rep",
                "Next 2Q / half-year goal",
                "FULL_NAME",
                "FORMULA1",
                sort_order="Asc",
            ),
            self._bar_component(
                "00OTb000008nak5MAA",
                "Stale Deals by Rep",
                "No activity 14d+",
                "FULL_NAME",
                "RowCount",
            ),
            self._bar_component(
                "00OTb000008navNMAQ",
                "Approvals Stuck by Rep",
                "Stage 20 pending >5d",
                "FULL_NAME",
                "RowCount",
            ),
            self._tabular_flex_component(
                "00OTb000008eknVMAQ",
                "Slipped Deals",
                "Open opps past close date",
                [
                    "ACCOUNT_NAME",
                    "OPPORTUNITY_NAME",
                    "FULL_NAME",
                    "STAGE_NAME",
                    "CLOSE_DATE",
                    "AGE",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                sort_column="Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            ),
            self._tabular_flex_component(
                "00OTb000008mxM9MAI",
                "Probability Mismatch",
                "Stage 3+ below expected probability",
                [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "FULL_NAME",
                    "PROBABILITY",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                sort_column="Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            ),
        ]
        self.patch_dashboard(SD_MONTHLY, additions, remove_report_ids=SD_WAVE2_REMOVE_REPORTS)

    def remediate_forecast_dashboard(self) -> None:
        accuracy_id, commit_risk_id, slippage_id = self.ensure_forecast_wave2_reports()
        avg_deal_id, renewal_won_id = self.ensure_forecast_wave3_reports()
        additions = [
            self._column_component(
                accuracy_id,
                "Forecast Accuracy 8Q",
                "Won / forecast ARR by FQ",
                "FISCAL_QUARTER",
                "FORMULA1",
            ),
            self._tabular_flex_component(
                commit_risk_id,
                "Commit Deals at Risk",
                "Repeatedly pushed commit deals",
                [
                    "ACCOUNT_NAME",
                    "OPPORTUNITY_NAME",
                    "FULL_NAME",
                    "STAGE_NAME",
                    "CLOSE_DATE",
                    "PUSH_COUNT",
                    "NEXT_STEP",
                    "LAST_ACTIVITY",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                sort_column="Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            ),
            self._bar_component(
                slippage_id,
                "Slippage by Push Count",
                "Open current-quarter opps",
                "PUSH_COUNT",
                "RowCount",
            ),
            self._column_component(
                avg_deal_id,
                "Avg Deal Size 8Q",
                "Won L+E ARR average by FQ",
                "FISCAL_QUARTER",
                "a!Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            ),
            self._column_component(
                renewal_won_id,
                "Renewal ACV Won by FQ",
                "Closed won renewal ACV",
                "FISCAL_QUARTER",
                "s!Opportunity.APTS_Renewal_ACV__c.CONVERT",
            ),
            self._tabular_flex_component(
                "00OTb000008mxM9MAI",
                "Probability Mismatch",
                "Stage 3+ below expected probability",
                [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "FULL_NAME",
                    "PROBABILITY",
                    "Opportunity.APTS_Opportunity_ARR__c.CONVERT",
                ],
                sort_column="Opportunity.APTS_Opportunity_ARR__c.CONVERT",
            ),
        ]
        self.patch_dashboard(FORECAST, additions, remove_report_ids=FORECAST_WAVE2_REMOVE_REPORTS)

    def remediate_quarter_close_dashboard(self) -> None:
        pending_owner_id = self._find_report_by_name("DD · Pending Approval by Owner")
        sla_trend_id = self._find_report_by_name("DD · Approval SLA Breaches by Month")
        if not pending_owner_id or not sla_trend_id:
            raise RuntimeError("missing Deal Desk approval reports for Quarter Close")
        additions = [
            self._bar_component(
                pending_owner_id,
                "Pending Approvals by Owner",
                "Current-quarter bottleneck",
                "FULL_NAME",
                "RowCount",
            ),
            self._column_component(
                sla_trend_id,
                "Approval SLA Breaches by Month",
                ">5d approvals",
                "Opportunity.Stage_20_Approval_Date__c",
                "RowCount",
            ),
        ]
        self.patch_dashboard(QUARTER_CLOSE, additions)

    def remediate_renewals_dashboard(self) -> None:
        self.patch_dashboard(RENEWALS)

    def remediate_account_health_dashboard(self) -> None:
        additions = [
            self._tabular_flex_component(
                "00OTb000008mxNlMAI",
                "At-Risk Accounts",
                "High/Med risk renewal ACV",
                [
                    "ACCOUNT_NAME",
                    "Account.Overall_Adoption_Score__c",
                    "Account.Tier_Calculation__c",
                    "OPPORTUNITY_NAME",
                    "Opportunity.APTS_Renewal_ACV__c.CONVERT",
                    "CLOSE_DATE",
                ],
                sort_column="Opportunity.APTS_Renewal_ACV__c.CONVERT",
            ),
        ]
        self.patch_dashboard(ACCOUNT_HEALTH, additions)


def main() -> int:
    r = Remediator()
    r.patch_sales_ops_reports()
    r.patch_priority_date_filters()
    r.patch_secondary_reports()
    r.patch_sd_wave2_reports()
    r.remediate_sales_ops_dashboard()
    r.remediate_deal_desk_dashboard()
    r.remediate_cro_dashboard()
    r.remediate_cro_wave2_dashboard()
    r.remediate_sd_wave2_dashboard()
    r.remediate_forecast_dashboard()
    r.remediate_quarter_close_dashboard()
    r.remediate_renewals_dashboard()
    r.remediate_account_health_dashboard()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise
