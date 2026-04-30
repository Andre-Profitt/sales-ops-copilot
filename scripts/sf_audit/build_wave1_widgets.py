"""Wave 1 — six widgets that surface signals already in the org but never
visualized. Built 2026-04-28 from `docs/sf_audit/ROLE_BASED_DASHBOARD_DESIGN_2026-04-28.md`.

| # | Widget | Dashboard | Data signal |
|---|---|---|---|
| 1 | High-Value Deals at Risk      | CRO Cockpit            | ARR≥1M + Einstein/Risk/Prob mismatch |
| 2 | At-Risk Accounts              | Renewals               | Risk_of_Potential_Termination__c |
| 3 | Pardot-Hot Unconverted Leads  | Marketing & Lead Funnel| pi__score__c ≥ 100 |
| 4 | Probability Mismatch by Stage | Sales Ops Quarterly KPI| Stage vs Probability band gap |
| 5 | Adoption Score Distribution   | Account Health Watch   | Account.Overall_Adoption_Score__c |
| 6 | Einstein IqScore by Stage     | Forecast Accuracy      | Opportunity.IqScore × Stage |

EUR 1M chosen as the high-value floor: 199 of 676 open L+E opps qualify (top 30%
by count, ~90%+ of pipeline VALUE).

Idempotent — re-runs check existing report by name first, skips if found.
"""

from __future__ import annotations

import logging
import sys

import requests

from scripts.sf_audit.improve_dashboard_layout import pack_layout, widget_size
from scripts.sf_audit.kpi_reports import POLLUTION_FILTERS
from scripts.sf_audit.rebuild_sd_dashboard import STANDARD_FILTER_COLS
from scripts.sf_audit.reports import _filter, create_report, sf_session

DASHBOARD_FOLDER_ID = "00lTb000006OCRBIA4"  # Andre folder
ARR = "Opportunity.APTS_Opportunity_ARR__c.CONVERT"
ACV = "Opportunity.APTS_Renewal_ACV__c.CONVERT"
sARR, sACV = f"s!{ARR}", f"s!{ACV}"

DASHBOARDS = {
    "cro": "01ZTb00000FxYZhMAN",
    "renewals": "01ZTb00000FxYTFMA3",
    "marketing": "01ZTb00000FxYbJMAV",
    "salesops_q": "01ZTb00000FSP9JMAX",
    "account_health": "01ZTb00000FxYeXMAV",
    "forecast": "01ZTb00000FxYcvMAF",
}


def find_existing(instance: str, token: str, name: str) -> str | None:
    """Return report ID if a report with this exact name already exists."""
    headers = {"Authorization": f"Bearer {token}"}
    soql = f"SELECT Id FROM Report WHERE Name='{name}' LIMIT 1"
    r = requests.get(
        f"{instance}/services/data/v65.0/query",
        headers=headers,
        params={"q": soql},
        timeout=20,
    )
    if r.status_code == 200:
        recs = r.json().get("records", [])
        if recs:
            return recs[0]["Id"]
    return None


def reports_spec() -> list[dict]:
    base = {"folderId": DASHBOARD_FOLDER_ID}
    return [
        # 1. CRO — High-Value Deals at Risk (ARR ≥ EUR 1M AND any risk signal)
        # NOTE: no folderId — Andre folder rejects similar reports with FORBIDDEN; private folder works.
        {
            "key": "wave1-cro-high-value-at-risk",
            "metadata": {
                "name": "CRO · High-Value Deals at Risk (≥1M)",
                "description": "Open Land/Expand opps with ARR≥EUR 1M flagged by Einstein (IqScore≤4), explicit Risk Assessment Medium+, or probability below stage band.",
                "reportFormat": "TABULAR",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "STAGE_NAME",
                    ARR,
                    "OPPORTUNITY_SCORE",
                    "Opportunity.Risk_Assessment_Level__c",
                    "PROBABILITY",
                    "CLOSE_DATE",
                    "FULL_NAME",
                ],
                # Logic: closed=false AND type IN (Land,Expand) AND ARR>=1M AND
                #        (IqScore<=4 OR Risk_Assessment_Level__c IN (...))
                # FX caveat (Codex review 2026-04-30): SF report filters on
                # currency fields evaluate in the row's transactional currency
                # by default. The "EUR 1M" threshold below will under/over-
                # include opps in non-EUR books. Two paths to fix when this
                # report is next deployed:
                #   1. SF admin sets the report's "Display Currencies Using"
                #      to corporate (EUR), which makes filters compare
                #      converted values too.
                #   2. OR replace this filter column with a custom formula
                #      field on Opportunity that exposes convertCurrency().
                # Until then, treat the deployed report as approximate for
                # non-EUR books.
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    _filter("Opportunity.APTS_Opportunity_ARR__c", "greaterOrEqual", "1000000"),
                    _filter("OPPORTUNITY_SCORE", "lessOrEqual", "4"),
                    _filter(
                        "Opportunity.Risk_Assessment_Level__c",
                        "equals",
                        "High,Medium - High,Medium",
                    ),
                    *POLLUTION_FILTERS,
                ],
                # 5 main + 9 pollution = 14 total. Logic = 1 AND 2 AND 3 AND (4 OR 5) AND 6..14 (pollution AND'd)
                "reportBooleanFilter": (
                    "1 AND 2 AND 3 AND (4 OR 5) AND 6 AND 7 AND 8 AND 9 AND "
                    "10 AND 11 AND 12 AND 13 AND 14"
                ),
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "CUSTOM",
                    "startDate": None,
                    "endDate": None,
                },
            },
        },
        # 2. Renewals — At-Risk Accounts
        # NOTE: no folderId — Andre folder rejects with FORBIDDEN; private folder works.
        {
            "key": "wave1-renewals-at-risk-accounts",
            "metadata": {
                "name": "REN · At-Risk Accounts",
                "description": "Open Renewal opps on accounts flagged Risk_of_Potential_Termination__c High or Medium. 146 accounts currently flagged. Built on Opportunity to bypass AccountList sharing restrictions.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "ACCOUNT_NAME",
                    "Account.Overall_Adoption_Score__c",
                    "Account.Tier_Calculation__c",
                    "OPPORTUNITY_NAME",
                    ACV,
                    "CLOSE_DATE",
                ],
                "groupingsDown": [
                    {
                        "name": "Account.Risk_of_Potential_Termination__c",
                        "sortOrder": "Asc",
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": [sACV, "RowCount"],
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Renewal"),
                    _filter(
                        "Account.Risk_of_Potential_Termination__c",
                        "equals",
                        "High,Medium",
                    ),
                ],
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "CUSTOM",
                    "startDate": None,
                    "endDate": None,
                },
            },
        },
        # 3. Marketing — Pardot-Hot Unconverted Leads (score ≥ 100)
        # NOTE: no folderId — LeadList in Andre folder hits FORBIDDEN; private folder works.
        {
            "key": "wave1-mk-pardot-hot",
            "metadata": {
                "name": "MK · Pardot-Hot Unconverted Leads",
                "description": "Leads with Pardot Account Engagement score ≥ 100 that haven't converted. ~155 currently hot and unactioned.",
                "reportFormat": "TABULAR",
                "reportType": {"type": "LeadList"},
                "scope": "org",
                "detailColumns": [
                    "COMPANY",
                    "LAST_NAME",
                    "EMAIL",
                    "LEAD_SOURCE",
                    "STATUS",
                    "Lead.pi__score__c",
                    "CREATED_DATE",
                ],
                "reportFilters": [
                    _filter("CONVERTED", "equals", "0"),
                    _filter("Lead.pi__score__c", "greaterOrEqual", "100"),
                ],
            },
        },
        # 4. Sales Ops Q — Probability Mismatch by Stage
        # Logic: stage 3 prob<20, stage 4 prob<50, stage 5 prob<70, stage 6 prob<85
        # NOTE: no folderId — Andre folder rejects this exact report name with FORBIDDEN; private folder works.
        {
            "key": "wave1-prob-mismatch",
            "metadata": {
                "name": "OPS · Probability Mismatch by Stage",
                "description": "Open L+E opps where Probability is below the stage's expected band (S3<20, S4<50, S5<70, S6<85). Forecast hygiene flag.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "PROBABILITY",
                    ARR,
                    "FULL_NAME",
                ],
                "groupingsDown": [
                    {"name": "STAGE_NAME", "sortOrder": "Asc", "dateGranularity": "None"}
                ],
                "aggregates": [sARR, "RowCount"],
                # Filters 1-2 = baseline; 3-6 = stage+prob OR pairs
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    _filter("STAGE_NAME", "equals", "3 - Engagement"),
                    _filter("PROBABILITY", "lessThan", "20"),
                    _filter("STAGE_NAME", "equals", "4 - Shortlisted"),
                    _filter("PROBABILITY", "lessThan", "50"),
                    _filter("STAGE_NAME", "equals", "5 - Preferred"),
                    _filter("PROBABILITY", "lessThan", "70"),
                    _filter("STAGE_NAME", "equals", "6 - Contracting"),
                    _filter("PROBABILITY", "lessThan", "85"),
                    *POLLUTION_FILTERS,
                ],
                "reportBooleanFilter": (
                    "1 AND 2 AND ((3 AND 4) OR (5 AND 6) OR (7 AND 8) OR (9 AND 10)) "
                    "AND 11 AND 12 AND 13 AND 14 AND 15 AND 16 AND 17 AND 18 AND 19"
                ),
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "CUSTOM",
                    "startDate": None,
                    "endDate": None,
                },
            },
        },
        # 5. Account Health — Adoption Score Distribution by Tier
        # NOTE: no folderId — Andre folder rejects with FORBIDDEN; private folder works.
        {
            "key": "wave1-acct-adoption-distribution",
            "metadata": {
                "name": "ACC · Adoption Score by Tier",
                "description": "Open opps' accounts grouped by Tier; aggregated by avg Account Overall Adoption Score. Built on Opportunity to bypass AccountList sharing.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    "Account.Overall_Adoption_Score__c",
                ],
                "groupingsDown": [
                    {
                        "name": "Account.Tier_Calculation__c",
                        "sortOrder": "Asc",
                        "dateGranularity": "None",
                    }
                ],
                "aggregates": ["a!Account.Overall_Adoption_Score__c", "RowCount"],
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("Account.Overall_Adoption_Score__c", "notEqual", ""),
                    *POLLUTION_FILTERS,
                ],
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "CUSTOM",
                    "startDate": None,
                    "endDate": None,
                },
            },
        },
        # 6. Forecast Accuracy — Einstein IqScore by Stage
        # NOTE: no folderId — Andre folder rejects with FORBIDDEN; private folder works.
        {
            "key": "wave1-fcst-iqscore-stage",
            "metadata": {
                "name": "FCST · Einstein IqScore by Stage",
                "description": "Open L+E opps grouped by Stage and Einstein IqScore (1=lowest, 10=highest). Identifies where the model is calling deals at risk.",
                "reportFormat": "SUMMARY",
                "reportType": {"type": "Opportunity"},
                "detailColumns": [
                    "OPPORTUNITY_NAME",
                    "ACCOUNT_NAME",
                    ARR,
                ],
                "groupingsDown": [
                    {"name": "STAGE_NAME", "sortOrder": "Asc", "dateGranularity": "None"},
                    {"name": "OPPORTUNITY_SCORE", "sortOrder": "Asc", "dateGranularity": "None"},
                ],
                "aggregates": [sARR, "RowCount"],
                "reportFilters": [
                    _filter("CLOSED", "equals", "0"),
                    _filter("TYPE", "equals", "Land,Expand"),
                    _filter("OPPORTUNITY_SCORE", "notEqual", ""),
                    *POLLUTION_FILTERS,
                ],
                "standardDateFilter": {
                    "column": "CLOSE_DATE",
                    "durationValue": "CUSTOM",
                    "startDate": None,
                    "endDate": None,
                },
            },
        },
    ]


def make_widget(
    rid: str,
    header: str,
    title: str,
    viz: str,
    fmt: str,
    agg: str,
    grouping: str | None = None,
    lead_typed: bool = False,
    table_columns: list[str] | None = None,
    sort_column: str | None = None,
) -> dict:
    # Lead-typed widgets can't carry the Opp-scoped standard filterColumns.
    filter_cols: list = [] if lead_typed else list(STANDARD_FILTER_COLS)
    is_tabular_flextable = viz == "FlexTable" and fmt == "TABULAR"
    if is_tabular_flextable:
        cols = table_columns or []
        viz_props = {
            "breakPoints": [],
            "decimalPrecision": -1,
            "displayUnits": "auto",
            "flexTableType": "tabular",
            "showChatterPhotos": False,
            "tableColumns": [
                {"column": c, "showSubTotal": False, "showTotal": False, "type": "detail"}
                for c in cols
            ],
        }
    else:
        viz_props = {
            "decimalPrecision": -1,
            "displayUnits": "auto",
            "legendPosition": "Right",
            "showPercentages": False,
            "showValues": True,
        }
    props: dict = {
        "aggregates": [{"name": agg}] if agg else [],
        "autoSelectColumns": False,
        "drillUrl": None,
        "filterColumns": filter_cols,
        "groupings": (
            [
                {
                    "inheritedReportSort": None,
                    "name": grouping,
                    "sortAggregate": None,
                    "sortOrder": "Desc",
                    "dateGranularity": "None",
                }
            ]
            if grouping
            else []
        ),
        "maxRows": 25 if (viz == "FlexTable" and not is_tabular_flextable) else None,
        "reportFormat": fmt,
        "sort": (
            {"column": sort_column, "sortOrder": "Desc", "type": "label"} if sort_column else None
        ),
        "useReportChart": False,
        "visualizationProperties": viz_props,
        "visualizationType": viz,
    }
    if is_tabular_flextable:
        props["useReportTableSetting"] = False
    return {
        "header": header,
        "footer": None,
        "title": title,
        "reportId": rid,
        "type": "Report",
        "componentData": 0,
        "chartTheme": None,
        "properties": props,
    }


# Widget placement spec — dicts so the optional table_columns/sort fields are
# clear when present.
WIDGET_PLACEMENT: list[dict] = [
    {
        "key": "wave1-cro-high-value-at-risk",
        "dash": "cro",
        "header": "Top Deals at Risk (≥1M)",
        "title": "Einstein/Risk/Prob",
        "viz": "FlexTable",
        "fmt": "TABULAR",
        "agg": "",
        "grouping": None,
        "lead_typed": False,
        "table_columns": [
            "OPPORTUNITY_NAME",
            "ACCOUNT_NAME",
            "STAGE_NAME",
            ARR,
            "OPPORTUNITY_SCORE",
            "Opportunity.Risk_Assessment_Level__c",
            "PROBABILITY",
            "CLOSE_DATE",
            "FULL_NAME",
        ],
        "sort_column": ARR,
    },
    {
        "key": "wave1-renewals-at-risk-accounts",
        "dash": "renewals",
        "header": "At-Risk Accounts",
        "title": "High/Med termination",
        "viz": "Bar",
        "fmt": "SUMMARY",
        "agg": "RowCount",
        "grouping": "Account.Risk_of_Potential_Termination__c",
        "lead_typed": False,
    },
    {
        "key": "wave1-mk-pardot-hot",
        "dash": "marketing",
        "header": "Pardot-Hot Unconverted Leads",
        "title": "Score ≥ 100",
        "viz": "FlexTable",
        "fmt": "TABULAR",
        "agg": "",
        "grouping": None,
        "lead_typed": True,
        "table_columns": [
            "COMPANY",
            "LAST_NAME",
            "EMAIL",
            "LEAD_SOURCE",
            "STATUS",
            "Lead.pi__score__c",
            "CREATED_DATE",
        ],
        "sort_column": "Lead.pi__score__c",
    },
    {
        "key": "wave1-prob-mismatch",
        "dash": "salesops_q",
        "header": "Probability Mismatch by Stage",
        "title": "Open L+E forecast hygiene",
        "viz": "Bar",
        "fmt": "SUMMARY",
        "agg": f"s!{ARR}",
        "grouping": "STAGE_NAME",
        "lead_typed": False,
    },
    {
        "key": "wave1-acct-adoption-distribution",
        "dash": "account_health",
        "header": "Adoption Score by Tier",
        "title": "Account health profile",
        "viz": "Bar",
        "fmt": "SUMMARY",
        "agg": "a!Account.Overall_Adoption_Score__c",
        "grouping": "Account.Tier_Calculation__c",
        "lead_typed": False,
    },
    {
        "key": "wave1-fcst-iqscore-stage",
        "dash": "forecast",
        "header": "Einstein Score by Stage",
        "title": "Where model flags risk",
        "viz": "Column",
        "fmt": "SUMMARY",
        "agg": f"s!{ARR}",
        "grouping": "STAGE_NAME",
        "lead_typed": False,
    },
]

DASHBOARD_RO = (
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


def add_widget_to_dashboard(instance: str, token: str, dashboard_id: str, widget: dict) -> bool:
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{instance}/services/data/v65.0/analytics/dashboards/{dashboard_id}"
    r = requests.get(url + "/describe", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"    ✗ GET dashboard {dashboard_id}: {r.status_code}")
        return False
    md = r.json()
    components = list(md.get("components") or [])
    # Skip if widget for same report already on dashboard
    if any(c.get("reportId") == widget["reportId"] for c in components):
        print("    ⚪ already on dashboard")
        return True
    if len(components) >= 20:
        print("    ✗ dashboard at 20-widget cap; skipping")
        return False
    components.append(widget)
    sizes = []
    for c in components:
        p = c.get("properties") or {}
        viz = p.get("visualizationType") or ""
        if viz == "Metric":
            sizes.append((3, 4))
        else:
            sizes.append(widget_size(viz, p.get("reportFormat") or ""))
    new_layout = pack_layout(sizes)
    md["components"] = components
    md["layout"] = {
        "components": new_layout,
        "gridLayout": (md.get("layout") or {}).get("gridLayout"),
    }
    for ro in DASHBOARD_RO:
        md.pop(ro, None)
    pr = requests.patch(
        url, headers={**headers, "Content-Type": "application/json"}, json=md, timeout=60
    )
    if pr.status_code in (200, 201):
        print("    ✓ added")
        return True
    print(f"    ✗ PATCH {pr.status_code}: {pr.text[:300]}")
    return False


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    instance, token, _ = sf_session()

    rids: dict[str, str] = {}
    print("=== Creating reports ===")
    for spec in reports_spec():
        existing = find_existing(instance, token, spec["metadata"]["name"])
        if existing:
            print(f"  ⚪ exists: {spec['key']:35s} → {existing}")
            rids[spec["key"]] = existing
            continue
        result = create_report(instance, token, spec["metadata"])
        if result.get("ok"):
            rids[spec["key"]] = result["id"]
            print(f"  ✓ {spec['key']:35s} → {result['id']}")
        else:
            err = (result.get("error") or "")[:300]
            print(f"  ✗ {spec['key']}: {err}")

    print("\n=== Wiring widgets onto dashboards ===")
    for spec in WIDGET_PLACEMENT:
        if spec["key"] not in rids:
            print(f"  skip {spec['key']} — report not created")
            continue
        rid = rids[spec["key"]]
        dashboard_id = DASHBOARDS[spec["dash"]]
        print(f"  [{spec['dash']}] + {spec['header']}")
        widget = make_widget(
            rid,
            spec["header"],
            spec["title"],
            spec["viz"],
            spec["fmt"],
            spec["agg"],
            spec.get("grouping"),
            spec.get("lead_typed", False),
            spec.get("table_columns"),
            spec.get("sort_column"),
        )
        add_widget_to_dashboard(instance, token, dashboard_id, widget)

    return 0


if __name__ == "__main__":
    sys.exit(main())
