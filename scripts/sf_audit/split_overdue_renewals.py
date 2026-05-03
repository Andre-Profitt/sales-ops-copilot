"""Split overdue pipeline into L+E ARR and Renewal ACV surfaces.

Idempotent remediation for the ARR/ACV dashboard audit finding:

- Existing `Overdue Opportunities` report becomes explicit Land+Expand ARR.
- New/updated `REN · Overdue Renewals ACV` report uses Renewal ACV only.
- Sales Ops KPI, Renewals, and Quarter Close dashboards get explicit widgets.

Read/write via Salesforce Analytics REST using the active sf CLI session.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from typing import Any

import requests

from scripts.sf_audit.rebuild_sd_dashboard import STANDARD_FILTER_COLS
from scripts.sf_audit.reports import _filter, sf_session

API_VERSION = "v66.0"

OVERDUE_LE_REPORT = "00OTb000008SrmLMAS"
RENEWAL_REPORT_NAME = "REN · Overdue Renewals ACV"
RENEWAL_REPORT_DEVNAME = "REN_Overdue_Renewals_ACV_v1"

SALES_OPS = "01ZTb00000FSP9JMAX"
RENEWALS = "01ZTb00000FxYTFMA3"
QUARTER_CLOSE = "01ZTb00000FxYhlMAF"

ARR_AGG = "s!Opportunity.APTS_Opportunity_ARR__c.CONVERT"
ACV_AGG = "s!Opportunity.APTS_Renewal_ACV__c.CONVERT"

REPORT_READONLY_KEYS = {
    "id",
    "type",
    "currency",
    "buckets",
    "crossFilters",
    "historicalSnapshotDates",
    "supportsRoleHierarchy",
}

DASHBOARD_READONLY_KEYS = {
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
    "canChangeRunningUser",
    "canUseStickyFilter",
    "flexTableImplementation",
    "maxFilterOptions",
}


class Splitter:
    def __init__(self) -> None:
        self.instance, self.token, _ = sf_session()
        self.base = f"{self.instance}/services/data/{API_VERSION}"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> dict[str, Any]:
        r = requests.get(f"{self.base}{path}", headers=self.headers, timeout=60)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = requests.post(f"{self.base}{path}", headers=self.headers, json=body, timeout=90)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"POST {path} failed {r.status_code}: {r.text[:1200]}")
        return r.json()

    def _patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = requests.patch(f"{self.base}{path}", headers=self.headers, json=body, timeout=90)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"PATCH {path} failed {r.status_code}: {r.text[:1200]}")
        return r.json() if r.text else {}

    def _query(self, soql: str) -> list[dict[str, Any]]:
        r = requests.get(
            f"{self.base}/query",
            headers=self.headers,
            params={"q": soql},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("records") or []

    def _report_metadata(self, report_id: str) -> dict[str, Any]:
        return self._get(f"/analytics/reports/{report_id}/describe").get("reportMetadata") or {}

    def _clean_report_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        out = copy.deepcopy(metadata)
        for key in REPORT_READONLY_KEYS:
            out.pop(key, None)
        return out

    def patch_overdue_le_report(self, dry_run: bool) -> None:
        metadata = self._report_metadata(OVERDUE_LE_REPORT)
        patched = self._clean_report_metadata(metadata)
        patched["name"] = "Overdue L+E Opportunities"
        patched["description"] = (
            "Open Land and Expand opportunities past close date. Value is ARR in org "
            "currency via APTS_Opportunity_ARR__c.CONVERT. Renewals are tracked "
            "separately as ACV."
        )
        patched["aggregates"] = [ARR_AGG, "RowCount"]
        patched["standardDateFilter"] = {
            "column": "CLOSE_DATE",
            "durationValue": "CUSTOM",
            "startDate": "2000-01-01",
            "endDate": "2099-12-31",
        }

        filters = []
        saw_type = False
        saw_closed = False
        for item in patched.get("reportFilters") or []:
            item = copy.deepcopy(item)
            if item.get("column") == "TYPE":
                item["operator"] = "equals"
                item["value"] = "Land,Expand"
                saw_type = True
            if item.get("column") == "CLOSED":
                item["operator"] = "equals"
                item["value"] = "False"
                saw_closed = True
            filters.append(item)
        if not saw_type:
            filters.append(_filter("TYPE", "equals", "Land,Expand"))
        if not saw_closed:
            filters.insert(0, _filter("CLOSED", "equals", "False"))
        patched["reportFilters"] = filters

        if dry_run:
            print(f"[dry-run] would PATCH {OVERDUE_LE_REPORT} as Overdue L+E ARR")
            return
        self._patch(f"/analytics/reports/{OVERDUE_LE_REPORT}", {"reportMetadata": patched})
        print(f"patched L+E report: {OVERDUE_LE_REPORT}")

    def renewal_report_metadata(self) -> dict[str, Any]:
        base = self._report_metadata(OVERDUE_LE_REPORT)
        folder_id = base.get("folderId")
        standard_filters = [
            {"name": "terr", "value": "all"},
            {"name": "open", "value": "open"},
            {"name": "probability", "value": ">0"},
        ]
        return {
            "name": RENEWAL_REPORT_NAME,
            "developerName": RENEWAL_REPORT_DEVNAME,
            "description": (
                "Open Renewal opportunities past close date. Value is Renewal ACV "
                "in org currency via APTS_Renewal_ACV__c.CONVERT. Kept separate "
                "from L+E ARR."
            ),
            "folderId": folder_id,
            "reportFormat": "SUMMARY",
            "reportType": {"type": "Opportunity"},
            "detailColumns": [
                "ACCOUNT_NAME",
                "OPPORTUNITY_NAME",
                "FULL_NAME",
                "STAGE_NAME",
                "CLOSE_DATE",
                "Opportunity.APTS_Renewal_ACV__c.CONVERT",
            ],
            "groupingsDown": [
                {
                    "name": "Opportunity.Sales_Region__c",
                    "sortOrder": "Asc",
                    "dateGranularity": "None",
                },
                {
                    "name": "FISCAL_QUARTER",
                    "sortOrder": "Asc",
                    "dateGranularity": "None",
                },
            ],
            "groupingsAcross": [],
            "aggregates": [ACV_AGG, "RowCount"],
            "reportFilters": [
                _filter("CLOSED", "equals", "False"),
                _filter("TYPE", "equals", "Renewal"),
                _filter("CLOSE_DATE", "lessThan", "TODAY"),
                _filter("ACCOUNT_NAME", "notContain", "simcorp,delete"),
                _filter("FULL_NAME", "notContain", "Sabiniewicz,Profit"),
                _filter("OPPORTUNITY_NAME", "notContain", "test,simcorp,delete"),
                _filter("STAGE_NAME", "notEqual", ",8 - Won,0 - Lost,0 - No Opportunity,Quota"),
            ],
            "reportBooleanFilter": None,
            "standardDateFilter": {
                "column": "CLOSE_DATE",
                "durationValue": "CUSTOM",
                "startDate": "2000-01-01",
                "endDate": "2099-12-31",
            },
            "standardFilters": standard_filters,
            "scope": "organization",
            "showGrandTotal": True,
            "showSubtotals": False,
        }

    def find_renewal_report(self) -> str | None:
        recs = self._query(
            "SELECT Id FROM Report "
            f"WHERE DeveloperName = '{RENEWAL_REPORT_DEVNAME}' "
            f"OR Name = '{RENEWAL_REPORT_NAME}' "
            "ORDER BY LastModifiedDate DESC LIMIT 1"
        )
        return recs[0]["Id"] if recs else None

    def ensure_renewal_report(self, dry_run: bool) -> str:
        metadata = self.renewal_report_metadata()
        existing = self.find_renewal_report()
        if dry_run:
            action = "PATCH" if existing else "POST"
            print(f"[dry-run] would {action} renewal report {existing or RENEWAL_REPORT_NAME}")
            return existing or "<new renewal report>"
        if existing:
            patched = self._clean_report_metadata(metadata)
            self._patch(f"/analytics/reports/{existing}", {"reportMetadata": patched})
            print(f"patched renewal report: {existing}")
            return existing
        result = self._post("/analytics/reports", {"reportMetadata": metadata})
        report_id = (result.get("reportMetadata") or {}).get("id") or result.get("id")
        if not report_id:
            raise RuntimeError(f"report create returned no id: {json.dumps(result)[:500]}")
        print(f"created renewal report: {report_id}")
        return report_id

    def _clean_dashboard_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        out = copy.deepcopy(metadata)
        for key in DASHBOARD_READONLY_KEYS:
            out.pop(key, None)
        if isinstance(out.get("runningUser"), dict):
            out["runningUser"] = None
        return out

    def _bar_template(self, components: list[dict[str, Any]]) -> dict[str, Any]:
        for comp in components:
            props = comp.get("properties") or {}
            if props.get("visualizationType") == "Bar":
                return copy.deepcopy(comp)
        raise RuntimeError("dashboard has no Bar component to clone")

    def _configure_overdue_component(
        self,
        comp: dict[str, Any],
        report_id: str,
        header: str,
        title: str,
        aggregate: str,
    ) -> dict[str, Any]:
        comp = copy.deepcopy(comp)
        comp.pop("id", None)
        comp.pop("lastModifiedDate", None)
        comp["reportId"] = report_id
        comp["header"] = header
        comp["title"] = title
        comp["type"] = "Report"
        comp.setdefault("properties", {})
        props = comp["properties"]
        props["aggregates"] = [{"name": aggregate}]
        props["autoSelectColumns"] = False
        props["drillUrl"] = None
        props["filterColumns"] = copy.deepcopy(STANDARD_FILTER_COLS)
        props["groupings"] = [
            {
                "inheritedReportSort": None,
                "name": "Opportunity.Sales_Region__c",
                "sortAggregate": None,
                "sortOrder": "Asc",
                "dateGranularity": "None",
            },
            {
                "inheritedReportSort": None,
                "name": "FISCAL_QUARTER",
                "sortAggregate": None,
                "sortOrder": "Asc",
                "dateGranularity": "None",
            },
        ]
        props["maxRows"] = None
        props["reportFormat"] = "SUMMARY"
        props["sort"] = None
        props["useReportChart"] = False
        props.setdefault("visualizationProperties", {})
        props["visualizationProperties"].update(
            {
                "axisRange": {"max": None, "min": None, "rangeType": "auto"},
                "decimalPrecision": -1,
                "displayUnits": "auto",
                "groupByType": "grouped",
                "legendPosition": "Right",
                "referenceLineColors": [],
                "referenceLineValues": [],
                "showValues": True,
                "sortLegendValues": False,
            }
        )
        props["visualizationType"] = "Bar"
        return comp

    def patch_dashboard(self, dashboard_id: str, renewal_report_id: str, dry_run: bool) -> None:
        metadata = self._get(f"/analytics/dashboards/{dashboard_id}/describe")
        components = list(metadata.get("components") or [])
        layout = copy.deepcopy(metadata.get("layout") or {})
        layout_components = list(layout.get("components") or [])

        changed = False
        for idx, comp in enumerate(components):
            if comp.get("reportId") == OVERDUE_LE_REPORT:
                configured = self._configure_overdue_component(
                    comp,
                    OVERDUE_LE_REPORT,
                    "Overdue L+E Opportunities",
                    "Past close date (ARR)",
                    ARR_AGG,
                )
                configured["id"] = comp.get("id")
                if comp.get("lastModifiedDate"):
                    configured["lastModifiedDate"] = comp.get("lastModifiedDate")
                if json.dumps(configured, sort_keys=True, default=str) != json.dumps(
                    comp, sort_keys=True, default=str
                ):
                    components[idx] = configured
                    changed = True

        if not any(comp.get("reportId") == renewal_report_id for comp in components):
            template = self._bar_template(components)
            components.append(
                self._configure_overdue_component(
                    template,
                    renewal_report_id,
                    "Overdue Renewals",
                    "Past close date (ACV)",
                    ACV_AGG,
                )
            )
            max_row = max(
                (item.get("row", 0) + item.get("rowspan", 0) for item in layout_components),
                default=0,
            )
            layout_components.append({"row": max_row, "column": 0, "rowspan": 8, "colspan": 6})
            changed = True

        if not changed:
            print(f"{dashboard_id}: no dashboard change")
            return

        layout["components"] = layout_components
        metadata["components"] = components
        metadata["layout"] = layout
        body = self._clean_dashboard_metadata(metadata)
        if dry_run:
            print(
                f"[dry-run] would PATCH dashboard {dashboard_id}: "
                f"components={len(components)} filters={len(metadata.get('filters') or [])}"
            )
            return
        self._patch(f"/analytics/dashboards/{dashboard_id}", body)
        verify = self._get(f"/analytics/dashboards/{dashboard_id}/describe")
        print(
            f"patched dashboard: {verify.get('name')} "
            f"components={len(verify.get('components') or [])}"
        )

    def run_report(self, report_id: str) -> tuple[str, str]:
        result = self._get(f"/analytics/reports/{report_id}?includeDetails=false")
        fact = result.get("factMap") or {}
        grand = fact.get("T!T") or {}
        aggregates = grand.get("aggregates") or []
        values = []
        for item in aggregates:
            label = item.get("label")
            value = item.get("value")
            if label is not None:
                values.append(str(label))
            elif value is not None:
                values.append(str(value))
        rows = sum(len((entry.get("rows") or [])) for entry in fact.values() if isinstance(entry, dict))
        return f"{rows} rows", ", ".join(values)

    def verify(self, renewal_report_id: str) -> None:
        for report_id, label in [
            (OVERDUE_LE_REPORT, "L+E ARR"),
            (renewal_report_id, "Renewal ACV"),
        ]:
            desc = self._report_metadata(report_id)
            filters = desc.get("reportFilters") or []
            type_values = [f.get("value") for f in filters if f.get("column") == "TYPE"]
            rows, values = self.run_report(report_id)
            print(f"verify report {label}: TYPE={type_values} {rows} totals={values}")
        for dashboard_id in [SALES_OPS, RENEWALS, QUARTER_CLOSE]:
            dash = self._get(f"/analytics/dashboards/{dashboard_id}/describe")
            rids = {comp.get("reportId") for comp in dash.get("components") or []}
            print(
                f"verify dashboard {dash.get('name')}: "
                f"L+E={OVERDUE_LE_REPORT in rids} Renewal={renewal_report_id in rids}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    splitter = Splitter()
    splitter.patch_overdue_le_report(args.dry_run)
    renewal_report_id = splitter.ensure_renewal_report(args.dry_run)
    for dashboard_id in [SALES_OPS, RENEWALS, QUARTER_CLOSE]:
        splitter.patch_dashboard(dashboard_id, renewal_report_id, args.dry_run)
    if not args.dry_run:
        splitter.verify(renewal_report_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
