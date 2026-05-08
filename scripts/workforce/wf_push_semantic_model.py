"""Create the `sm_workforce_rw` semantic model in Fabric, end-to-end.

Direct Lake on OneLake mode against `lkh_workforce_rw`. 6 tables, 1
relationship, 12 DAX measures matching wf_kpi_graph thresholds verbatim.

Path: GA Fabric Item REST API. No Power BI Desktop. macOS-friendly.

Usage:
    python3 scripts/workforce/wf_push_semantic_model.py

Re-runs are idempotent on display name: if the model exists, the script
updates the definition in-place via PATCH; otherwise creates fresh.
"""

from __future__ import annotations

import base64
import json
import time

import requests
from azure.identity import AzureCliCredential

WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"  # Salesforce Analytics - Sales Manager
LAKEHOUSE_ID = "34ea3a8c-6493-45ab-ab28-1d14bed9987f"  # lkh_workforce_rw
MODEL_NAME = "sm_workforce_rw"

FABRIC = "https://api.fabric.microsoft.com"
FABRIC_RES = "https://api.fabric.microsoft.com/.default"
PBI = "https://api.powerbi.com"
PBI_RES = "https://analysis.windows.net/powerbi/api/.default"


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
    """TMSL/JSON for the semantic model. Direct Lake on OneLake.

    Important: source.type=entity references the Delta table by name in the
    Lakehouse; expressionSource=DatabaseQuery references the shared M
    expression. compatibilityLevel >= 1604 is required for Direct Lake.
    """
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
    ) -> dict:
        c = {
            "name": name,
            "dataType": dtype,
            "sourceColumn": source or name,
            "summarizeBy": "none",
        }
        if key:
            c["isKey"] = True
        if fmt:
            c["formatString"] = fmt
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

    measures = [
        {
            "name": "Total Actions",
            "expression": "SUM ( weekly_person_kpis[actions] )",
            "formatString": "#,0",
        },
        {
            "name": "Total Actions Adj",
            "expression": "SUM ( weekly_person_kpis[actions_adj] )",
            "formatString": "#,0",
        },
        {
            "name": "Total Effort",
            "expression": "SUM ( weekly_person_kpis[effort_units] )",
            "formatString": "#,0",
        },
        {
            "name": "Total Effort Adj",
            "expression": "SUM ( weekly_person_kpis[effort_adj] )",
            "formatString": "#,0",
        },
        {
            "name": "Mean Availability",
            "expression": "AVERAGE ( weekly_person_kpis[availability_factor] )",
            "formatString": "0.000",
        },
        {
            "name": "Mean Util P75",
            "expression": "AVERAGE ( weekly_person_kpis[utilization_index_p75] )",
            "formatString": "0.000",
        },
        {
            "name": "Avg Util P75 By Person",
            "expression": "AVERAGEX ( VALUES ( weekly_person_kpis[person_id] ), [Mean Util P75] )",
            "formatString": "0.000",
        },
        {
            "name": "Mean Util P75 4w",
            "expression": "AVERAGE ( weekly_person_kpis[utilization_p75_4w_avg] )",
            "formatString": "0.000",
        },
        {
            "name": "Overloaded Persons",
            "expression": "CALCULATE ( DISTINCTCOUNT ( weekly_person_kpis[person_id] ), weekly_person_kpis[utilization_index_p75] > 1.5 )",
            "formatString": "#,0",
            "description": "KG threshold: load_overloaded (util_p75>1.5)",
        },
        {
            "name": "Underloaded Persons",
            "expression": "CALCULATE ( DISTINCTCOUNT ( weekly_person_kpis[person_id] ), weekly_person_kpis[utilization_index_p75] < 0.5 )",
            "formatString": "#,0",
            "description": "KG threshold: load_underloaded (util_p75<0.5)",
        },
        {
            "name": "Overloaded Person-Weeks",
            "expression": "CALCULATE ( COUNTROWS ( weekly_person_kpis ), weekly_person_kpis[utilization_index_p75] > 1.5 )",
            "formatString": "#,0",
        },
        {
            "name": "Point SPOF Count",
            "expression": "CALCULATE ( COUNTROWS ( coverage_concentration ), coverage_concentration[top1_share] > 0.5 )",
            "formatString": "#,0",
            "description": "KG threshold: concentration_spof_point (top1_share>0.5)",
        },
    ]

    return {
        "name": MODEL_NAME,
        "compatibilityLevel": 1604,
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "discourageImplicitMeasures": True,
            "expressions": [
                {
                    "name": "DatabaseQuery",
                    "kind": "m",
                    "expression": database_query,
                }
            ],
            "tables": [
                {
                    "name": "weekly_person_kpis",
                    "columns": [
                        col("person_id", "string"),
                        col("canonical_name", "string"),
                        col("event_week_start", "dateTime", fmt="yyyy-mm-dd"),
                        col("event_week", "string"),
                        col("actions", "double"),
                        col("actions_adj", "double"),
                        col("unique_records", "double"),
                        col("effort_units", "double"),
                        col("effort_adj", "double"),
                        col("availability_factor", "double"),
                        col("available_days", "double"),
                        col("leave_days", "double"),
                        col("actions_adj_per_avail_week", "double"),
                        col("effort_adj_per_avail_week", "double"),
                        col("utilization_index_p75", "double"),
                        col("utilization_p75_4w_avg", "double"),
                    ],
                    "partitions": [dl_partition("weekly_person_kpis")],
                    "measures": measures,
                },
                {
                    "name": "dim_people",
                    "columns": [
                        col("person_id", "string", key=True),
                        col("canonical_name", "string"),
                        col("role", "string"),
                    ],
                    "partitions": [dl_partition("dim_people")],
                },
                {
                    "name": "coverage_concentration",
                    "columns": [
                        col("segment", "string"),
                        col("process_family", "string"),
                        col("total_effort", "double"),
                        col("effective_contributors", "double"),
                        col("top1_share", "double", fmt="0.000"),
                        col("top1_person_name", "string"),
                        col("top2_share", "double", fmt="0.000"),
                    ],
                    "partitions": [dl_partition("coverage_concentration")],
                },
                {
                    "name": "weekly_team_kpis",
                    "columns": [],  # auto-detect at framing
                    "partitions": [dl_partition("weekly_team_kpis")],
                },
                {
                    "name": "anomalies_log",
                    "columns": [],
                    "partitions": [dl_partition("anomalies_log")],
                },
                {
                    "name": "forecast_output",
                    "columns": [],
                    "partitions": [dl_partition("forecast_output")],
                },
            ],
            "relationships": [
                {
                    "name": "rel_person",
                    "fromTable": "weekly_person_kpis",
                    "fromColumn": "person_id",
                    "toTable": "dim_people",
                    "toColumn": "person_id",
                    "crossFilteringBehavior": "oneDirection",
                }
            ],
        },
    }


def _token(resource: str) -> str:
    return AzureCliCredential().get_token(resource).token


def _wait_lro(headers: dict, response: requests.Response, fabric_token: str) -> dict | None:
    if response.status_code in (200, 201):
        return response.json() if response.text else None
    if response.status_code != 202:
        response.raise_for_status()
    location = response.headers.get("Location")
    op_id = response.headers.get("x-ms-operation-id")
    print(f"  LRO accepted; polling op {op_id}")
    poll_url = location or f"{FABRIC}/v1/operations/{op_id}"
    while True:
        time.sleep(int(response.headers.get("Retry-After", 3)))
        r = requests.get(poll_url, headers={"Authorization": f"Bearer {fabric_token}"})
        if r.status_code == 200:
            body = r.json() if r.text else {}
            status = body.get("status")
            if status in ("Succeeded", "Failed"):
                print(f"  LRO {status}")
                if status == "Failed":
                    print("  error:", body.get("error"))
                    return None
                # fetch result
                rr = requests.get(
                    f"{FABRIC}/v1/operations/{op_id}/result",
                    headers={"Authorization": f"Bearer {fabric_token}"},
                )
                return rr.json() if rr.text else None
            print(f"  status={status} ({body.get('percentComplete', 0)}%)")
        else:
            print(f"  poll status {r.status_code}: {r.text[:200]}")
            return None


def find_existing_model(fabric_token: str) -> str | None:
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

    pbism = json.dumps(build_pbism())
    bim = json.dumps(build_model_bim(), indent=2)

    parts = [
        {"path": "definition.pbism", "payload": _b64(pbism), "payloadType": "InlineBase64"},
        {"path": "model.bim", "payload": _b64(bim), "payloadType": "InlineBase64"},
    ]

    existing_id = find_existing_model(fabric_token)
    headers = {"Authorization": f"Bearer {fabric_token}", "Content-Type": "application/json"}

    if existing_id:
        print(f"Updating existing semantic model {existing_id}")
        url = f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/semanticModels/{existing_id}/updateDefinition"
        body = {"definition": {"parts": parts}}
        r = requests.post(url, headers=headers, json=body)
        result = _wait_lro(headers, r, fabric_token)
        return existing_id
    else:
        print("Creating semantic model sm_workforce_rw")
        url = f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/semanticModels"
        body = {
            "displayName": MODEL_NAME,
            "description": "RW workforce KPIs (Direct Lake on lkh_workforce_rw). Source of truth: scripts/workforce/wf_kpi_graph.py schema v2.",
            "definition": {"parts": parts},
        }
        r = requests.post(url, headers=headers, json=body)
        if r.status_code in (200, 201):
            return r.json()["id"]
        if r.status_code == 202:
            result = _wait_lro(headers, r, fabric_token)
            if result and isinstance(result, dict):
                return result.get("id", "")
        r.raise_for_status()
        return ""


def refresh_model(model_id: str) -> None:
    """Frame the Direct Lake partitions. Uses Power BI REST refresh endpoint."""
    pbi_token = _token(PBI_RES)
    url = f"{PBI}/v1.0/myorg/groups/{WORKSPACE_ID}/datasets/{model_id}/refreshes"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {pbi_token}", "Content-Type": "application/json"},
        json={"type": "Full", "commitMode": "transactional"},
    )
    if r.status_code in (200, 202):
        print(f"  refresh enqueued: {r.headers.get('Location') or 'OK'}")
    else:
        print(f"  refresh response {r.status_code}: {r.text[:300]}")


def main() -> None:
    model_id = deploy()
    if not model_id:
        print("deploy returned no id; aborting refresh")
        return
    print(f"\nsemantic model id: {model_id}")
    print("triggering Direct Lake framing refresh...")
    refresh_model(model_id)
    print("\ndone. Open in browser:")
    print(f"  https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/datasets/{model_id}")


if __name__ == "__main__":
    main()
