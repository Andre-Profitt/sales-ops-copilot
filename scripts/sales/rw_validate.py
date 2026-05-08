"""Pre-flight validate report.json visualContainer references against the
deployed semantic model. Catches typos in measure / column names before
the LRO push fails or renders blanks.

Usage:
    # Validate measure refs in the live report
    python3 -m scripts.sales.rw_validate --live

    # Validate measure refs in a local report.json file
    python3 -m scripts.sales.rw_validate --file /tmp/report.json

    # Validate a single visual dict (from build_card_visual etc) via stdin
    python3 -m scripts.sales.rw_validate --stdin <<EOF
    {"config": "..."}
    EOF

Exits non-zero on any unresolved measure or column ref.

Caveats:
- Column-level validation is not yet implemented (would need to also pull
  table column lists from TMDL). Only measure refs are checked today.
- Only the names on the f_opportunity / f_stage_transition / f_forecast_transition
  tables are inspected; extending to dim tables is trivial when needed.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time

import requests
from azure.identity import AzureCliCredential

from scripts.sales.rw_inventory_measures import fetch_measures_by_table

WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"
REPORT_ID = "d7362a11-f3dd-4bd1-a69a-68c941c2598b"
FABRIC = "https://api.fabric.microsoft.com"


def _token() -> str:
    return AzureCliCredential().get_token("https://api.fabric.microsoft.com/.default").token


def _wait_lro(resp, token: str) -> dict:
    if resp.status_code in (200, 201):
        return resp.json() if resp.text else {}
    if resp.status_code != 202:
        resp.raise_for_status()
    location = resp.headers.get("Location") or (
        f"{FABRIC}/v1/operations/{resp.headers['x-ms-operation-id']}"
    )
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


def fetch_live_report() -> dict:
    """Return the live rpt_vp_ops_scorecard report.json as a dict."""
    token = _token()
    r = requests.post(
        f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/reports/{REPORT_ID}/getDefinition",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    data = _wait_lro(r, token)
    rj_part = next(p for p in data["definition"]["parts"] if p["path"] == "report.json")
    return json.loads(base64.b64decode(rj_part["payload"]).decode("utf-8"))


def measure_refs_in_visual(vc: dict) -> list[tuple[str, str]]:
    """Extract (table, measure) refs from one visualContainer config."""
    cfg = json.loads(vc["config"]) if isinstance(vc.get("config"), str) else vc.get("config", {})
    select = cfg.get("singleVisual", {}).get("prototypeQuery", {}).get("Select", [])
    aliases = {
        e["Name"]: e["Entity"]
        for e in cfg.get("singleVisual", {}).get("prototypeQuery", {}).get("From", [])
    }
    out = []
    for s in select:
        if "Measure" in s:
            alias = s["Measure"].get("Expression", {}).get("SourceRef", {}).get("Source")
            prop = s["Measure"].get("Property")
            if alias and prop:
                out.append((aliases.get(alias, "?"), prop))
    return out


def validate_report(rj: dict, by_table: dict[str, list[str]]) -> list[str]:
    """Return list of error strings; empty = clean."""
    measure_set = {(t, m) for t, ms in by_table.items() for m in ms}
    errors: list[str] = []
    for section in rj.get("sections", []):
        page = section.get("displayName", section.get("name", "?"))
        for vc in section.get("visualContainers", []):
            for table, measure in measure_refs_in_visual(vc):
                if (table, measure) not in measure_set:
                    cfg = (
                        json.loads(vc["config"]) if isinstance(vc["config"], str) else vc["config"]
                    )
                    vname = cfg.get("name", "?")
                    errors.append(f"  [{page}] visual {vname}: missing {table}.{measure!r}")
    return errors


def validate_visual_dict(vc: dict, by_table: dict[str, list[str]]) -> list[str]:
    """Validate a single visualContainer dict (from build_*_visual)."""
    measure_set = {(t, m) for t, ms in by_table.items() for m in ms}
    errors: list[str] = []
    for table, measure in measure_refs_in_visual(vc):
        if (table, measure) not in measure_set:
            errors.append(f"  missing {table}.{measure!r}")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", action="store_true", help="Pull live report from Fabric")
    src.add_argument("--file", help="Local report.json path")
    src.add_argument("--stdin", action="store_true", help="Read a single visual dict from stdin")
    args = ap.parse_args()

    print("fetching deployed measures...")
    by_table = fetch_measures_by_table()
    total = sum(len(v) for v in by_table.values())
    print(f"  {total} measures across {len(by_table)} tables")

    if args.stdin:
        vc = json.load(sys.stdin)
        errors = validate_visual_dict(vc, by_table)
    else:
        if args.live:
            print("fetching live report...")
            rj = fetch_live_report()
        else:
            with open(args.file) as f:
                rj = json.load(f)
        sect = sum(1 for _ in rj.get("sections", []))
        vc_count = sum(len(s.get("visualContainers", [])) for s in rj.get("sections", []))
        print(f"  {sect} sections, {vc_count} total visualContainers")
        errors = validate_report(rj, by_table)

    if errors:
        print(f"\n{len(errors)} unresolved ref(s):")
        for e in errors:
            print(e)
        sys.exit(1)
    print("\nall measure refs resolve. ✓")


if __name__ == "__main__":
    main()
