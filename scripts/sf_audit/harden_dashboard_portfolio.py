"""Harden the remaining recent Salesforce dashboard portfolio.

Idempotent remediation after the core 11-dashboard gate is clean:

- Add dashboard filter pass-through to Win/Loss and Activity Health.
- Add Commercial Health-style filter pass-through to Pipeline Hygiene.
- Add explicit Type/pollution controls to SimCorp One product reports.
- Clean shared hygiene report pollution/date gaps.
- Mark operational work dashboards as count-based internal views and remove
  raw ARR aggregation from their field-audit report.

No visualization type changes.
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

SD_MONTHLY = "01ZTb00000FSP7hMAH"
WIN_LOSS = "01ZTb00000FxYUrMAN"
ACTIVITY_HEALTH = "01ZTb00000FxYg9MAF"
PIPELINE_HYGIENE = "01ZTb00000FyyLdMAJ"
COMMERCIAL_HEALTH = "01ZTb00000FxX2YMAV"
SIMCORP_ONE = "01ZTb00000FyrbtMAB"
OP_WORK_DASH = "01ZTb00000FvDSvMAN"
OP_WORK_DONE = "01ZTb00000FvBZCMA3"

SC1_REPORTS = {
    "00OTb000008njfKMAQ",
    "00OTb000008nk6jMAA",
    "00OTb000008nk57MAA",
}

ZOMBIE_REPORT = "00OTb000008nijFMAQ"
COVERAGE_GAP_REPORT = "00OTb000008nirJMAQ"
OP_WORK_REPORT = "00OQA000003msve2AA"
KYC_REPORT = "00OTb000008KnSzMAK"

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

OPP_POLLUTION_FILTERS = [
    _filter("FULL_NAME", "notContain", "Sabiniewicz,Profit"),
    _filter("ACCOUNT_NAME", "notContain", "simcorp,test,delete"),
    _filter("OPPORTUNITY_NAME", "notContain", "test,simcorp,delete"),
]


class PortfolioHardener:
    def __init__(self) -> None:
        self.instance, self.token, _ = sf_session()
        self.base = f"{self.instance}/services/data/{API_VERSION}"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.report_type_cache: dict[str, str] = {}

    def _get(self, path: str) -> dict[str, Any]:
        response = requests.get(f"{self.base}{path}", headers=self.headers, timeout=60)
        response.raise_for_status()
        return response.json()

    def _patch(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = requests.patch(
            f"{self.base}{path}",
            headers=self.headers,
            json=body,
            timeout=90,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"PATCH {path} failed {response.status_code}: {response.text[:1200]}")
        return response.json() if response.text else {}

    def _report_metadata(self, report_id: str) -> dict[str, Any]:
        return self._get(f"/analytics/reports/{report_id}/describe").get("reportMetadata") or {}

    def _report_type(self, report_id: str) -> str:
        if report_id not in self.report_type_cache:
            metadata = self._report_metadata(report_id)
            self.report_type_cache[report_id] = (metadata.get("reportType") or {}).get("type") or ""
        return self.report_type_cache[report_id]

    def _clean_report(self, metadata: dict[str, Any]) -> dict[str, Any]:
        cleaned = copy.deepcopy(metadata)
        for key in REPORT_READONLY_KEYS:
            cleaned.pop(key, None)
        return cleaned

    def _clean_dashboard(self, metadata: dict[str, Any]) -> dict[str, Any]:
        cleaned = copy.deepcopy(metadata)
        for key in DASHBOARD_READONLY_KEYS:
            cleaned.pop(key, None)
        if isinstance(cleaned.get("runningUser"), dict):
            cleaned["runningUser"] = None
        return cleaned

    @staticmethod
    def _dashboard_filters_from(metadata: dict[str, Any]) -> list[dict[str, Any]]:
        filters = []
        for flt in metadata.get("filters") or []:
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
            filters.append(item)
        return filters

    @staticmethod
    def _merge_filters(existing: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged = list(existing)
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

    def _patch_report_metadata(self, report_id: str, mutate, dry_run: bool) -> bool:
        metadata = self._clean_report(self._report_metadata(report_id))
        before = json.dumps(metadata, sort_keys=True, default=str)
        mutate(metadata)
        after = json.dumps(metadata, sort_keys=True, default=str)
        if before == after:
            return False
        if dry_run:
            print(f"[dry-run] report {report_id} would change")
            return True
        self._patch(f"/analytics/reports/{report_id}", {"reportMetadata": metadata})
        print(f"patched report {report_id}")
        return True

    def patch_sc1_reports(self, dry_run: bool) -> None:
        def mutate_for(report_id: str):
            def mutate(metadata: dict[str, Any]) -> None:
                filters = list(metadata.get("reportFilters") or [])
                has_type = False
                for flt in filters:
                    if flt.get("column") == "TYPE":
                        flt["operator"] = "equals"
                        flt["value"] = "Land,Expand"
                        has_type = True
                if not has_type:
                    filters.append(_filter("TYPE", "equals", "Land,Expand"))
                filters = self._merge_filters(filters, OPP_POLLUTION_FILTERS)
                metadata["reportFilters"] = filters
                metadata["description"] = (
                    "SimCorp One product pipeline view. Explicitly scoped to Land and Expand "
                    "ARR with standard internal/test-data exclusions."
                )

            return mutate

        for report_id in sorted(SC1_REPORTS):
            self._patch_report_metadata(report_id, mutate_for(report_id), dry_run)

    def patch_hygiene_reports(self, dry_run: bool) -> None:
        def mutate_zombie(metadata: dict[str, Any]) -> None:
            metadata["reportFilters"] = self._merge_filters(
                list(metadata.get("reportFilters") or []),
                OPP_POLLUTION_FILTERS,
            )
            metadata["standardDateFilter"] = {
                "column": "CREATED_DATE",
                "durationValue": "CUSTOM",
                "startDate": "2000-01-01",
                "endDate": "2099-12-31",
            }

        def mutate_coverage(metadata: dict[str, Any]) -> None:
            metadata["reportFilters"] = self._merge_filters(
                list(metadata.get("reportFilters") or []),
                [_filter("ACCOUNT.NAME", "notContain", "test,simcorp,delete")],
            )

        self._patch_report_metadata(ZOMBIE_REPORT, mutate_zombie, dry_run)
        self._patch_report_metadata(COVERAGE_GAP_REPORT, mutate_coverage, dry_run)

    def patch_operational_reports(self, dry_run: bool) -> None:
        def mutate_work(metadata: dict[str, Any]) -> None:
            metadata["aggregates"] = ["RowCount"]
            metadata["detailColumns"] = [
                col
                for col in metadata.get("detailColumns") or []
                if col != "Opportunity.APTS_Opportunity_ARR__c"
            ]
            metadata["description"] = (
                "Internal operational field-audit activity count. Not a pipeline or ARR "
                "valuation report."
            )

        def mutate_kyc(metadata: dict[str, Any]) -> None:
            metadata["standardDateFilter"] = {
                "column": "Account.KYC_Approval_Date__c",
                "durationValue": "CUSTOM",
                "startDate": "2000-01-01",
                "endDate": "2099-12-31",
            }

        self._patch_report_metadata(OP_WORK_REPORT, mutate_work, dry_run)
        self._patch_report_metadata(KYC_REPORT, mutate_kyc, dry_run)

    def _component_filter_columns(
        self,
        report_id: str,
        filter_columns: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        report_type = self._report_type(report_id)
        if report_type in {"Opportunity", "OpportunityProduct"}:
            return copy.deepcopy(filter_columns)
        return None

    def patch_standard_filter_dashboard(self, dashboard_id: str, dry_run: bool) -> None:
        source = self._get(f"/analytics/dashboards/{SD_MONTHLY}/describe")
        target = self._get(f"/analytics/dashboards/{dashboard_id}/describe")
        changed = False

        target["filters"] = self._dashboard_filters_from(source)
        components = list(target.get("components") or [])
        for component in components:
            report_id = component.get("reportId")
            if not report_id:
                continue
            filter_columns = self._component_filter_columns(report_id, STANDARD_FILTER_COLS)
            if filter_columns is None:
                continue
            props = component.setdefault("properties", {})
            current = props.get("filterColumns") or []
            if {item.get("name") for item in current} != {item["name"] for item in STANDARD_FILTER_COLS}:
                props["filterColumns"] = filter_columns
                changed = True
        current_names = [flt.get("name") for flt in target.get("filters") or []]
        if current_names != [flt.get("name") for flt in self._dashboard_filters_from(source)]:
            changed = True

        # Always compare against the live target filter names because we set target above.
        live = self._get(f"/analytics/dashboards/{dashboard_id}/describe")
        if [flt.get("name") for flt in live.get("filters") or []] != current_names:
            changed = True

        if not changed:
            print(f"{dashboard_id}: no standard-filter dashboard change")
            return
        target["components"] = components
        body = self._clean_dashboard(target)
        if dry_run:
            print(f"[dry-run] dashboard {dashboard_id} would get standard filters/filterColumns")
            return
        self._patch(f"/analytics/dashboards/{dashboard_id}", body)
        final = self._get(f"/analytics/dashboards/{dashboard_id}/describe")
        print(
            f"patched dashboard {final.get('name')}: "
            f"filters={len(final.get('filters') or [])} components={len(final.get('components') or [])}"
        )

    def patch_pipeline_hygiene_dashboard(self, dry_run: bool) -> None:
        commercial = self._get(f"/analytics/dashboards/{COMMERCIAL_HEALTH}/describe")
        target = self._get(f"/analytics/dashboards/{PIPELINE_HYGIENE}/describe")
        commercial_filters = self._dashboard_filters_from(commercial)
        fc_by_report: dict[str, list[dict[str, Any]]] = {}
        for component in commercial.get("components") or []:
            report_id = component.get("reportId")
            filters = (component.get("properties") or {}).get("filterColumns") or []
            if report_id and filters:
                fc_by_report[report_id] = copy.deepcopy(filters)

        changed = False
        if [flt.get("name") for flt in target.get("filters") or []] != [
            flt.get("name") for flt in commercial_filters
        ]:
            target["filters"] = commercial_filters
            changed = True

        components = list(target.get("components") or [])
        for component in components:
            report_id = component.get("reportId")
            if not report_id or report_id not in fc_by_report:
                continue
            props = component.setdefault("properties", {})
            current = props.get("filterColumns") or []
            if {item.get("name") for item in current} != {item.get("name") for item in fc_by_report[report_id]}:
                props["filterColumns"] = copy.deepcopy(fc_by_report[report_id])
                changed = True

        if not changed:
            print(f"{PIPELINE_HYGIENE}: no Pipeline Hygiene dashboard change")
            return
        target["components"] = components
        body = self._clean_dashboard(target)
        if dry_run:
            print("[dry-run] Pipeline Hygiene dashboard would get Commercial Health filters/filterColumns")
            return
        self._patch(f"/analytics/dashboards/{PIPELINE_HYGIENE}", body)
        final = self._get(f"/analytics/dashboards/{PIPELINE_HYGIENE}/describe")
        print(
            f"patched dashboard {final.get('name')}: "
            f"filters={len(final.get('filters') or [])} components={len(final.get('components') or [])}"
        )

    def mark_operational_dashboards(self, dry_run: bool) -> None:
        for dashboard_id in [OP_WORK_DASH, OP_WORK_DONE]:
            metadata = self._get(f"/analytics/dashboards/{dashboard_id}/describe")
            target_description = (
                "Internal operational activity dashboard. Count-based field-audit and KYC "
                "workflow views; not a leadership pipeline, ARR, or ACV dashboard."
            )
            if metadata.get("description") == target_description:
                print(f"{dashboard_id}: no operational dashboard description change")
                continue
            metadata["description"] = target_description
            body = self._clean_dashboard(metadata)
            if dry_run:
                print(f"[dry-run] dashboard {dashboard_id} would be marked internal operational")
                continue
            self._patch(f"/analytics/dashboards/{dashboard_id}", body)
            print(f"marked operational dashboard {dashboard_id}")

    def run(self, dry_run: bool) -> None:
        self.patch_sc1_reports(dry_run)
        self.patch_hygiene_reports(dry_run)
        self.patch_operational_reports(dry_run)
        for dashboard_id in [WIN_LOSS, ACTIVITY_HEALTH, SIMCORP_ONE]:
            self.patch_standard_filter_dashboard(dashboard_id, dry_run)
        self.patch_pipeline_hygiene_dashboard(dry_run)
        self.mark_operational_dashboards(dry_run)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    PortfolioHardener().run(args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
