"""Print the measure list deployed to sm_sales_kpis_rw, grouped by table.

Usage:
    python3 -m scripts.sales.rw_inventory_measures
    python3 -m scripts.sales.rw_inventory_measures > /tmp/rw_measure_inventory.txt

DAX query API is tenant-disabled; this dumps the model.bim payload via
the Fabric REST getDefinition LRO and parses measure metadata only.
"""

from __future__ import annotations

import base64
import time

import requests
from azure.identity import AzureCliCredential

WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"
SEMANTIC_MODEL_ID = "3c58b5dd-b321-4aaa-a5cd-fb73e474edbb"
FABRIC = "https://api.fabric.microsoft.com"


def _token() -> str:
    return AzureCliCredential().get_token("https://api.fabric.microsoft.com/.default").token


def _wait_lro(resp, token: str) -> dict:
    if resp.status_code in (200, 201):
        return resp.json() if resp.text else {}
    if resp.status_code != 202:
        resp.raise_for_status()
    location = resp.headers.get("Location")
    op_id = resp.headers.get("x-ms-operation-id")
    if not location:
        location = f"{FABRIC}/v1/operations/{op_id}"
    while True:
        time.sleep(int(resp.headers.get("Retry-After", 3)))
        s = requests.get(location, headers={"Authorization": f"Bearer {token}"})
        s.raise_for_status()
        body = s.json()
        if body.get("status") == "Succeeded":
            r = requests.get(f"{location}/result", headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            return r.json()
        if body.get("status") == "Failed":
            raise RuntimeError(f"LRO failed: {body}")


_MEASURE_RE = __import__("re").compile(
    r"^\s*measure\s+'([^']+)'\s*=", flags=__import__("re").MULTILINE
)


def fetch_measures_by_table() -> dict[str, list[str]]:
    """Pull the deployed semantic model definition (TMDL) and return
    {table_name: [sorted measure names]}. Reusable by validators / tests.
    """
    token = _token()
    r = requests.post(
        f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/semanticModels/{SEMANTIC_MODEL_ID}/getDefinition",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    data = _wait_lro(r, token)
    parts = data["definition"]["parts"]

    by_table: dict[str, list[str]] = {}
    for part in parts:
        path = part["path"]
        if not path.startswith("definition/tables/") or not path.endswith(".tmdl"):
            continue
        table = path.removeprefix("definition/tables/").removesuffix(".tmdl")
        tmdl = base64.b64decode(part["payload"]).decode("utf-8")
        names = sorted(set(_MEASURE_RE.findall(tmdl)))
        if names:
            by_table[table] = names
    return by_table


def main() -> None:
    by_table = fetch_measures_by_table()
    total = sum(len(v) for v in by_table.values())
    print(f"Total measures: {total}")
    print(f"Tables with measures: {len(by_table)}")
    print()
    for tbl in sorted(by_table):
        print(f"[{tbl}] ({len(by_table[tbl])})")
        for n in by_table[tbl]:
            print(f"  {n}")
        print()


if __name__ == "__main__":
    main()
