"""
Audit 11 SF dashboards for convention compliance + data quality.

Read-only — does NOT modify any reports or dashboards.

Output:
  state/sf_audit/dashboard_quality_audit.md       (markdown report)
  state/sf_audit/dashboard_quality_audit.json     (raw scoring per report)

Conventions scored:
  TYPE       — Land,Expand for ARR; Renewal for ACV
  Aggregate  — APTS_Opportunity_ARR__c.CONVERT vs APTS_Renewal_ACV__c.CONVERT
  Pollution  — FULL_NAME notContain Sabiniewicz, OR Account name notContain test/simcorp
  DateScope  — standardDateFilter set, or CUSTOM with values
  Data       — factMap returns non-zero rows
  Quality    — description has no em-dashes / debug text

Status emoji: ✓ = compliant, ⚠ = minor issue, ✗ = violation, n/a = not applicable.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "state" / "sf_audit"
RAW_DIR = OUT_DIR / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

DASHBOARDS = [
    ("01ZTb00000FSP7hMAH", "Sales Directors Monthly"),
    ("01ZTb00000FSP9JMAX", "Sales Ops Quarterly KPI"),
    ("01ZTb00000FxYTFMA3", "Renewals"),
    ("01ZTb00000FxYUrMAN", "Win/Loss Analysis"),
    ("01ZTb00000FxYY5MAN", "Deal Desk Operations"),
    ("01ZTb00000FxYZhMAN", "CRO Cockpit"),
    ("01ZTb00000FxYbJMAV", "Marketing & Lead Funnel"),
    ("01ZTb00000FxYcvMAF", "Forecast Accuracy & Pacing"),
    ("01ZTb00000FxYeXMAV", "Account Health Watch"),
    ("01ZTb00000FxYg9MAF", "Activity Health"),
    ("01ZTb00000FxYhlMAF", "Quarter Close Pacing"),
]

API_VERSION = "v66.0"


def get_org() -> tuple[str, str]:
    """Get instance URL and access token via sf CLI."""
    result = subprocess.run(
        ["sf", "org", "display", "--target-org", "apro@simcorp.com", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)["result"]
    return payload["instanceUrl"], payload["accessToken"]


def http_get(url: str, token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    resp = requests.get(url, headers=headers, timeout=60)
    if resp.status_code >= 400:
        return {"_error": resp.status_code, "_body": resp.text[:500]}
    try:
        return resp.json()
    except json.JSONDecodeError:
        return {"_error": "json", "_body": resp.text[:500]}


def http_post_run(url: str, token: str) -> dict[str, Any]:
    """GET to run a report synchronously (saved metadata).

    Despite the function name, this uses GET because the Analytics REST
    `POST /reports/{id}` requires a metadata payload while `GET /reports/{id}`
    runs the report's saved definition.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    resp = requests.get(url, headers=headers, timeout=120)
    if resp.status_code >= 400:
        return {"_error": resp.status_code, "_body": resp.text[:500]}
    try:
        return resp.json()
    except json.JSONDecodeError:
        return {"_error": "json", "_body": resp.text[:500]}


# ----- scoring helpers --------------------------------------------------


def detect_motion(report_meta: dict, report_name: str) -> str:
    """Determine if report is ARR (Land/Expand), ACV (Renewal), or n/a (non-opp).

    Priority: TYPE filter > aggregate field > report name keyword.
    """
    rmd = report_meta.get("reportMetadata") or {}
    rt = (rmd.get("reportType") or {}).get("type", "") or ""
    name = report_name.lower()
    # Non-opportunity report types
    if rt and "Opportunity" not in rt:
        non_opp_keywords = ("Account", "Lead", "Activity", "Task", "Event", "Case", "Asset")
        if any(k in rt for k in non_opp_keywords):
            return "non_opp"
        if rt:
            return "non_opp"
    # 1. Authoritative: TYPE filter
    for f in rmd.get("reportFilters") or []:
        col = (f.get("column") or "").upper()
        op = (f.get("operator") or "").lower()
        val = f.get("value") or ""
        if col == "TYPE" and op == "equals":
            if "Renewal" in val and not any(x in val for x in ["Land", "Expand"]):
                return "renewal"
            if any(x in val for x in ["Land", "Expand"]) and "Renewal" not in val:
                return "arr"
    # 2. Authoritative: aggregate field
    aggs = ",".join(rmd.get("aggregates") or [])
    if "APTS_Renewal_ACV__c" in aggs and "APTS_Opportunity_ARR__c" not in aggs:
        return "renewal"
    if "APTS_Opportunity_ARR__c" in aggs and "APTS_Renewal_ACV__c" not in aggs:
        return "arr"
    # 3. Fallback: name
    if "renewal" in name or name.startswith("ren "):
        return "renewal"
    if "Opportunity" in rt:
        return "arr"
    return "non_opp"


def has_type_filter(report_meta: dict, motion: str) -> tuple[str, str]:
    """Return (status, detail). Status: ✓ ⚠ ✗ n/a.

    Severity: if report sums ARR or ACV, missing TYPE is ✗ (numbers are wrong).
    If report only counts rows or uses Amount, missing TYPE is ⚠ (data-quality report).
    """
    if motion == "non_opp":
        return "n/a", "non-opp report"
    rmd = report_meta.get("reportMetadata") or {}
    filters = rmd.get("reportFilters") or []
    aggs = ",".join(rmd.get("aggregates") or [])
    sums_revenue = "APTS_Opportunity_ARR__c" in aggs or "APTS_Renewal_ACV__c" in aggs
    for f in filters:
        col = (f.get("column") or "").upper()
        op = (f.get("operator") or "").lower()
        val = f.get("value") or ""
        if col == "TYPE":
            if motion == "arr":
                # Allow Land,Expand or Land or Expand
                if op == "equals" and any(x in val for x in ["Land", "Expand"]):
                    if "Renewal" in val:
                        return "⚠", f"TYPE=blended ({val})"
                    return "✓", f"TYPE={val}"
                if op == "notequal" and "Renewal" in val:
                    return "✓", f"TYPE!=Renewal ({val})"
                return "⚠", f"TYPE op={op} val={val}"
            if motion == "renewal":
                if op == "equals" and "Renewal" in val:
                    if any(x in val for x in ["Land", "Expand"]):
                        return "⚠", f"TYPE=blended ({val})"
                    return "✓", f"TYPE={val}"
                return "⚠", f"TYPE op={op} val={val}"
    # No TYPE filter present — severity by aggregate
    if sums_revenue:
        return "✗", "no TYPE filter (sums revenue)"
    return "⚠", "no TYPE filter (count/Amount only)"


def has_correct_aggregate(report_meta: dict, motion: str) -> tuple[str, str]:
    if motion == "non_opp":
        return "n/a", ""
    rmd = report_meta.get("reportMetadata") or {}
    aggs = rmd.get("aggregates") or []
    aggs_str = ",".join(aggs)
    if "Overall_Adoption_Score__c" in aggs_str:
        return "n/a", "operational score aggregate"
    if "STAGE_DURATION" in aggs_str or "Number_of_Days_Since_Created__c" in aggs_str:
        return "n/a", "operational duration aggregate"
    arr_field = "APTS_Opportunity_ARR__c"
    acv_field = "APTS_Renewal_ACV__c"
    has_arr = arr_field in aggs_str
    has_acv = acv_field in aggs_str
    has_amount = "Amount" in aggs_str and "ARR" not in aggs_str and "ACV" not in aggs_str
    if motion == "arr":
        if has_arr and not has_acv:
            return "✓", "ARR aggregate"
        if has_arr and has_acv:
            return "⚠", "blended ARR+ACV aggregates"
        if has_acv and not has_arr:
            return "✗", "ACV agg on Land/Expand"
        if has_amount:
            return "✗", "uses Opportunity.Amount"
        # Maybe RecordCount only
        if not aggs or all("RowCount" in a for a in aggs):
            return "n/a", "count-only"
        return "⚠", f"unexpected aggs: {aggs_str[:60]}"
    if motion == "renewal":
        if has_acv and not has_arr:
            return "✓", "ACV aggregate"
        if has_arr and has_acv:
            return "⚠", "blended ARR+ACV aggregates"
        if has_arr and not has_acv:
            return "✗", "ARR agg on Renewal"
        if has_amount:
            return "✗", "uses Opportunity.Amount"
        if not aggs or all("RowCount" in a for a in aggs):
            return "n/a", "count-only"
        return "⚠", f"unexpected aggs: {aggs_str[:60]}"
    return "n/a", ""


def has_pollution_filter(report_meta: dict) -> tuple[str, str]:
    rmd = report_meta.get("reportMetadata") or {}
    filters = rmd.get("reportFilters") or []
    rt = (rmd.get("reportType") or {}).get("type", "") or ""
    if "Opportunity" not in rt and "Lead" not in rt and "Account" not in rt:
        return "n/a", "non-opportunity report"
    saw_owner = False
    saw_acct = False
    saw_opp_name = False
    for f in filters:
        col = (f.get("column") or "").upper()
        op = (f.get("operator") or "").lower()
        val = f.get("value") or ""
        # Owner full name notContains/notEqual Sabiniewicz
        if "FULL_NAME" in col or "OWNER" in col or "USERS_NAME" in col:
            if op in ("notcontain", "notequal") and "sabiniewicz" in val.lower():
                saw_owner = True
        if "ACCOUNT_NAME" in col or "ACCOUNT.NAME" in col:
            if "notcontain" in op:
                v = val.lower()
                if "test" in v or "simcorp" in v or "qtc" in v or "sc" in v:
                    saw_acct = True
        if "OPPORTUNITY_NAME" in col or "OPPORTUNITY.NAME" in col or col == "NAME":
            if "notcontain" in op:
                v = val.lower()
                if any(
                    s in v
                    for s in ["test", "back office", "qtc", "sbl", "ash dummy", "generic", "delete"]
                ):
                    saw_opp_name = True
    is_lead_typed = "Lead" in rt and "Opportunity" not in rt
    is_account_typed = ("Account" in rt and "Opportunity" not in rt) or "AccountList" in rt
    if is_lead_typed:
        # Leads can't have account pollution; just need to not be ridiculous
        return "n/a", "Lead-typed (no pollution rules)"
    if is_account_typed:
        if saw_acct:
            return "✓", "Account name pollution filter"
        return "✗", "no Account-name pollution filter"
    # Opportunity-typed
    if saw_owner and (saw_acct or saw_opp_name):
        return "✓", "owner + name pollution"
    if saw_owner:
        return "✓", "owner pollution"
    if saw_acct or saw_opp_name:
        return "⚠", "name-only pollution (no owner filter)"
    return "✗", "no pollution filter"


def has_date_scope(report_meta: dict) -> tuple[str, str]:
    rmd = report_meta.get("reportMetadata") or {}
    sdf = rmd.get("standardDateFilter") or {}
    duration = sdf.get("durationValue") or ""
    col = sdf.get("column") or ""
    start = sdf.get("startDate") or ""
    end = sdf.get("endDate") or ""
    if duration and duration != "CUSTOM":
        return "✓", f"{col} {duration}"
    if duration == "CUSTOM":
        if start or end:
            return "✓", f"CUSTOM {start}..{end}"
        return "✗", "CUSTOM with no dates"
    if not duration and not start and not end:
        return "⚠", "no date scope"
    return "⚠", f"col={col} dur={duration}"


def has_data(execute_result: dict) -> tuple[str, str]:
    if "_error" in execute_result:
        return "✗", f"exec err {execute_result.get('_error')}"
    fact_map = execute_result.get("factMap") or {}
    if not fact_map:
        return "✗", "empty factMap"
    grand = fact_map.get("T!T") or {}
    grand_aggs = grand.get("aggregates") or []
    # Pull any non-zero aggregate value from T!T
    grand_max = 0.0
    for a in grand_aggs:
        if not isinstance(a, dict):
            continue
        v = a.get("value")
        if isinstance(v, (int, float)):
            grand_max = max(grand_max, abs(v))
    # Sum rows across all factMap entries
    any_rows = sum(len((entry.get("rows") or [])) for entry in fact_map.values() if isinstance(entry, dict))
    if any_rows > 0:
        return "✓", f"{any_rows} rows"
    if grand_max > 0:
        # No detail rows but aggregates non-zero (summary/matrix report)
        return "✓", f"agg={grand_max:.0f}"
    return "⚠", "0 rows, 0 aggregates"


def has_clean_description(report_meta: dict, dash_meta_component: dict | None) -> tuple[str, str]:
    rdesc = (
        (report_meta.get("attributes") or {}).get("description")
        or (report_meta.get("reportMetadata") or {}).get("description")
        or ""
    )
    cdesc = ""
    if dash_meta_component:
        cdesc = (
            (dash_meta_component.get("header") or "")
            + " "
            + (dash_meta_component.get("title") or "")
            + " "
            + (dash_meta_component.get("description") or "")
        )
    text = (rdesc + " " + cdesc).strip()
    if not text:
        return "⚠", "no description"
    issues = []
    if "—" in text or "–" in text:
        issues.append("em-dash")
    lower = text.lower()
    for bad in ["todo", "tbd", "fixme", "xxx", "debug"]:
        if bad in lower:
            issues.append(bad)
    if issues:
        return "⚠", ",".join(issues)
    return "✓", "clean"


# ----- main -----


def main() -> int:
    use_cache = "--cache" in sys.argv
    if use_cache:
        instance_url, token = "", ""
        print("Using cached describes/executes from raw/", flush=True)
    else:
        instance_url, token = get_org()
        print(f"Instance: {instance_url}", flush=True)

    audit: dict[str, Any] = {"dashboards": []}
    api_calls = 0
    seen_reports: dict[str, dict] = {}
    seen_executions: dict[str, dict] = {}

    for dash_id, dash_name in DASHBOARDS:
        print(f"\n=== {dash_id} {dash_name} ===", flush=True)
        cache_path = RAW_DIR / f"dash_{dash_id}.json"
        if use_cache and cache_path.exists():
            dash = json.loads(cache_path.read_text())
        else:
            url = f"{instance_url}/services/data/{API_VERSION}/analytics/dashboards/{dash_id}/describe"
            dash = http_get(url, token)
            api_calls += 1
            cache_path.write_text(json.dumps(dash, indent=2))

        if "_error" in dash:
            print(f"  DESCRIBE FAILED: {dash}")
            audit["dashboards"].append(
                {
                    "id": dash_id,
                    "name": dash_name,
                    "describe_error": dash,
                    "components": [],
                }
            )
            continue

        components = dash.get("components") or []
        comp_results = []
        # Map componentId -> dashboard meta block to pull title/description
        # The dashboard object has 'components' alongside 'layouts'.
        for comp in components:
            comp_id = comp.get("id")
            comp_label = comp.get("label") or comp.get("title") or comp_id
            comp_type = comp.get("type") or comp.get("componentType") or ""
            # Report ID lives in dataSource.subtype=report or top-level reportId
            ds = comp.get("dataSource") or {}
            report_id = ds.get("id") or comp.get("reportId") or comp.get("reportID")
            if not report_id:
                comp_results.append(
                    {
                        "component_id": comp_id,
                        "component_label": comp_label,
                        "component_type": comp_type,
                        "report_id": None,
                        "report_name": None,
                        "scores": {
                            "type": ("n/a", "no report"),
                            "agg": ("n/a", ""),
                            "pollution": ("n/a", ""),
                            "date": ("n/a", ""),
                            "data": ("n/a", ""),
                            "desc": ("n/a", ""),
                        },
                        "motion": "n/a",
                    }
                )
                continue

            # Describe the report (cached)
            if report_id in seen_reports:
                rmeta = seen_reports[report_id]
            else:
                rurl = f"{instance_url}/services/data/{API_VERSION}/analytics/reports/{report_id}/describe"
                rmeta = http_get(rurl, token)
                api_calls += 1
                seen_reports[report_id] = rmeta
                (RAW_DIR / f"report_{report_id}.json").write_text(json.dumps(rmeta, indent=2))

            if "_error" in rmeta:
                comp_results.append(
                    {
                        "component_id": comp_id,
                        "component_label": comp_label,
                        "component_type": comp_type,
                        "report_id": report_id,
                        "report_name": "<describe failed>",
                        "scores": {
                            "type": ("✗", f"err {rmeta.get('_error')}"),
                            "agg": ("✗", ""),
                            "pollution": ("✗", ""),
                            "date": ("✗", ""),
                            "data": ("✗", ""),
                            "desc": ("✗", ""),
                        },
                        "motion": "?",
                    }
                )
                continue

            report_name = (
                (rmeta.get("attributes") or {}).get("reportName") or rmeta.get("name") or ""
            )
            motion = detect_motion(rmeta, report_name)

            type_score = has_type_filter(rmeta, motion)
            agg_score = has_correct_aggregate(rmeta, motion)
            pol_score = has_pollution_filter(rmeta)
            date_score = has_date_scope(rmeta)

            # Execute report (cached)
            if report_id in seen_executions:
                exec_result = seen_executions[report_id]
            else:
                exec_url = f"{instance_url}/services/data/{API_VERSION}/analytics/reports/{report_id}?includeDetails=false"
                exec_result = http_post_run(exec_url, token)
                api_calls += 1
                seen_executions[report_id] = exec_result
                (RAW_DIR / f"exec_{report_id}.json").write_text(
                    json.dumps(exec_result, indent=2)[:200_000]
                )

            data_score = has_data(exec_result)
            desc_score = has_clean_description(rmeta, comp)

            comp_results.append(
                {
                    "component_id": comp_id,
                    "component_label": comp_label,
                    "component_type": comp_type,
                    "report_id": report_id,
                    "report_name": report_name,
                    "scores": {
                        "type": type_score,
                        "agg": agg_score,
                        "pollution": pol_score,
                        "date": date_score,
                        "data": data_score,
                        "desc": desc_score,
                    },
                    "motion": motion,
                }
            )
            print(
                f"  {comp_label[:40]:40s} -> {report_name[:50]:50s} "
                f"T={type_score[0]} A={agg_score[0]} P={pol_score[0]} D={date_score[0]} "
                f"R={data_score[0]} Q={desc_score[0]}",
                flush=True,
            )

        audit["dashboards"].append(
            {
                "id": dash_id,
                "name": dash_name,
                "components": comp_results,
            }
        )

    audit["api_calls"] = api_calls
    (OUT_DIR / "dashboard_quality_audit.json").write_text(json.dumps(audit, indent=2))
    print(f"\nAPI calls: {api_calls}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
