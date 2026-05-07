"""Add a single visual to rpt_vp_ops_scorecard. Incremental — one visual at
a time, learn the schema by observation.

Run with `--probe` to add a test card (Total Closed Won ARR);
verify it renders in the browser; iterate from there.
"""

from __future__ import annotations

import argparse
import base64
import json
import time
import uuid

import requests
from azure.identity import AzureCliCredential

WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"
REPORT_ID = "d7362a11-f3dd-4bd1-a69a-68c941c2598b"  # rpt_vp_ops_scorecard
SEMANTIC_MODEL_ID = "3c58b5dd-b321-4aaa-a5cd-fb73e474edbb"

FABRIC = "https://api.fabric.microsoft.com"


def _b64(s: str | dict) -> str:
    if isinstance(s, dict):
        s = json.dumps(s, indent=2)
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _token() -> str:
    return AzureCliCredential().get_token("https://api.fabric.microsoft.com/.default").token


def _wait_lro(resp, token):
    if resp.status_code in (200, 201):
        return resp.json() if resp.text else None
    if resp.status_code != 202:
        print(f"  status {resp.status_code}: {resp.text[:600]}")
        resp.raise_for_status()
    op_id = resp.headers.get("x-ms-operation-id")
    location = resp.headers.get("Location") or f"{FABRIC}/v1/operations/{op_id}"
    print(f"  LRO accepted; polling op {op_id}")
    while True:
        time.sleep(int(resp.headers.get("Retry-After", 3)))
        r = requests.get(location, headers={"Authorization": f"Bearer {token}"})
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
                    headers={"Authorization": f"Bearer {token}"},
                )
                return rr.json() if rr.text else None
            print(f"  status={status}")
        else:
            print(f"  poll status {r.status_code}: {r.text[:200]}")
            return None


def get_current_report_json(token: str) -> dict:
    """Pull the current rpt_vp_ops_scorecard report.json."""
    r = requests.post(
        f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/reports/{REPORT_ID}/getDefinition",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    res = _wait_lro(r, token)
    for p in res["definition"]["parts"]:
        if p["path"] == "report.json":
            return json.loads(base64.b64decode(p["payload"]).decode("utf-8"))
    raise RuntimeError("no report.json in definition")


def build_card_visual(
    measure_table: str,
    measure_name: str,
    display_title: str,
    x: float,
    y: float,
    w: float = 280,
    h: float = 110,
) -> dict:
    """Construct a card visualContainer that references a model measure.

    Differs from SalesManager's pattern: SalesManager uses Aggregation+Column
    on raw fields. We use Measure on properly-defined DAX measures."""
    visual_name = uuid.uuid4().hex[:20]
    table_alias = "f"
    query_ref = f"{measure_table}.{measure_name}"

    config = {
        "name": visual_name,
        "layouts": [
            {
                "id": 0,
                "position": {
                    "x": x,
                    "y": y,
                    "z": 1000,
                    "width": w,
                    "height": h,
                    "tabOrder": 1000,
                },
            }
        ],
        "singleVisual": {
            "visualType": "card",
            "projections": {"Values": [{"queryRef": query_ref}]},
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": table_alias, "Entity": measure_table, "Type": 0}],
                "Select": [
                    {
                        "Measure": {
                            "Expression": {"SourceRef": {"Source": table_alias}},
                            "Property": measure_name,
                        },
                        "Name": query_ref,
                    }
                ],
            },
            "columnProperties": {query_ref: {"displayName": display_title}},
            "drillFilterOtherVisuals": True,
        },
    }
    return {
        "config": json.dumps(config),
        "filters": "[]",
        "height": h,
        "width": w,
        "x": x,
        "y": y,
        "z": 1000,
    }


def build_slicer_visual(
    table: str,
    column: str,
    title: str,
    x: float,
    y: float,
    w: float = 240,
    h: float = 90,
) -> dict:
    """Construct a slicer visualContainer for a column on a dim table."""
    visual_name = uuid.uuid4().hex[:20]
    table_alias = "d"
    query_ref = f"{table}.{column}"
    config = {
        "name": visual_name,
        "layouts": [
            {
                "id": 0,
                "position": {
                    "x": x,
                    "y": y,
                    "z": 500,
                    "width": w,
                    "height": h,
                    "tabOrder": 500,
                },
            }
        ],
        "singleVisual": {
            "visualType": "slicer",
            "projections": {"Values": [{"queryRef": query_ref}]},
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": table_alias, "Entity": table, "Type": 0}],
                "Select": [
                    {
                        "Column": {
                            "Expression": {"SourceRef": {"Source": table_alias}},
                            "Property": column,
                        },
                        "Name": query_ref,
                    }
                ],
            },
            "columnProperties": {query_ref: {"displayName": title}},
            "objects": {
                "general": [
                    {
                        "properties": {
                            "orientation": {"expr": {"Literal": {"Value": "1D"}}},
                        }
                    }
                ],
            },
        },
    }
    return {
        "config": json.dumps(config),
        "filters": "[]",
        "height": h,
        "width": w,
        "x": x,
        "y": y,
        "z": 500,
    }


def push_report(token: str, report_json: dict) -> None:
    parts = [
        {
            "path": "definition.pbir",
            "payload": _b64(
                {
                    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
                    "version": "4.0",
                    "datasetReference": {
                        "byConnection": {
                            "connectionString": (
                                'Data Source="powerbi://api.powerbi.com/v1.0/myorg/Salesforce Analytics - Sales Manager 1/6/2024, 1:06:06 PM";'
                                f"initial catalog=sm_sales_kpis_rw;integrated security=ClaimsToken;"
                                f"semanticmodelid={SEMANTIC_MODEL_ID}"
                            )
                        }
                    },
                }
            ),
            "payloadType": "InlineBase64",
        },
        {
            "path": "report.json",
            "payload": _b64(report_json),
            "payloadType": "InlineBase64",
        },
    ]
    r = requests.post(
        f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/reports/{REPORT_ID}/updateDefinition",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"definition": {"parts": parts}},
    )
    _wait_lro(r, token)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="Add a single test card")
    ap.add_argument("--build-cards", action="store_true", help="Add the 6 KPI cards + 2 YoY cards")
    ap.add_argument("--clear", action="store_true", help="Wipe all visuals first")
    ap.add_argument(
        "--year-filter", type=int, default=None, help="Set page-level filter on d_calendar[year]"
    )
    ap.add_argument(
        "--motion-breakout", action="store_true", help="Add Land vs Expand vs Renewal breakout row"
    )
    ap.add_argument(
        "--build-forecast",
        action="store_true",
        help="Add forecast-discipline row (slips, upgrades, days in category)",
    )
    ap.add_argument(
        "--build-slicers", action="store_true", help="Add region/FQ/motion slicers across the top"
    )
    ap.add_argument(
        "--build-stage-forward",
        action="store_true",
        help="Add 6 per-stage forward-rate cards (Stages 1-6, RW KPI stage_conversion target >70%)",
    )
    args = ap.parse_args()

    token = _token()
    print("getting current report.json...")
    rj = get_current_report_json(token)
    print(f"  current sections: {len(rj.get('sections', []))}")
    section = rj["sections"][0]
    print(
        f"  current visuals in '{section.get('displayName', section['name'])}': {len(section.get('visualContainers', []))}"
    )

    if args.clear:
        section["visualContainers"] = []
        print("  cleared all visuals")

    if args.probe:
        section["visualContainers"] = section.get("visualContainers", []) + [
            build_card_visual(
                "f_opportunity", "Total Closed Won ARR", "Closed Won ARR (FY26)", 20, 20
            )
        ]

    if args.build_cards:
        # 5 headline cards across the top row + 2 YoY cards below
        # Row 1: 5 KPI cards, 240px apart, y=20
        cards_top = [
            ("f_opportunity", "Total Closed Won ARR", "Closed Won ARR"),
            ("f_opportunity", "Win Rate ARR", "Win Rate (ARR)"),
            ("f_opportunity", "Avg Sales Cycle Days", "Avg Sales Cycle"),
            ("f_opportunity", "Renewal Retention Pct (Period)", "Renewal Retention"),
            ("f_stage_transition", "Stage Forward Pct", "Stage Forward Rate"),
        ]
        for i, (tbl, msr, title) in enumerate(cards_top):
            section["visualContainers"].append(
                build_card_visual(tbl, msr, title, x=20 + i * 240, y=20, w=220, h=110)
            )
        # Row 2: 2 YoY cards, wider
        yoy = [
            (
                "f_opportunity",
                "Closed Won ARR YTD YoY Pct",
                "Closed Won ARR — YTD YoY (+10% target)",
            ),
            ("f_opportunity", "Renewal ACV YTD YoY Pct", "Renewal ACV — YTD YoY"),
        ]
        for i, (tbl, msr, title) in enumerate(yoy):
            section["visualContainers"].append(
                build_card_visual(tbl, msr, title, x=20 + i * 480, y=150, w=460, h=130)
            )
        print(f"  added {len(cards_top) + len(yoy)} cards")

    if args.motion_breakout:
        # Row 3: Motion breakout — 6 cards (Land × 3 + Expand × 3) + Renewal-already-separate above
        # Row 3a (y=290): Land trio
        land = [
            ("f_opportunity", "Land Closed Won ARR", "Land — Won ARR"),
            ("f_opportunity", "Land Win Rate ARR", "Land — Win Rate"),
            ("f_opportunity", "Land Avg Sales Cycle Days", "Land — Cycle Days"),
        ]
        for i, (tbl, msr, title) in enumerate(land):
            section["visualContainers"].append(
                build_card_visual(tbl, msr, title, x=20 + i * 320, y=290, w=300, h=110)
            )
        # Row 3b (y=410): Expand trio
        expand = [
            ("f_opportunity", "Expand Closed Won ARR", "Expand — Won ARR"),
            ("f_opportunity", "Expand Win Rate ARR", "Expand — Win Rate"),
            ("f_opportunity", "Expand Avg Sales Cycle Days", "Expand — Cycle Days"),
        ]
        for i, (tbl, msr, title) in enumerate(expand):
            section["visualContainers"].append(
                build_card_visual(tbl, msr, title, x=20 + i * 320, y=410, w=300, h=110)
            )
        print("  added 6 motion-breakout cards (Land + Expand)")

    if args.build_forecast:
        # Row 4 (y=540): forecast discipline
        forecast = [
            ("f_forecast_transition", "Forecast Slip Pct", "Forecast Slip Rate (target <15%)"),
            ("f_forecast_transition", "Forecast Slips", "Total Slips"),
            ("f_forecast_transition", "Forecast Upgrades", "Total Upgrades"),
            ("f_forecast_transition", "Avg Days In Forecast Category", "Avg Days In Category"),
        ]
        for i, (tbl, msr, title) in enumerate(forecast):
            section["visualContainers"].append(
                build_card_visual(tbl, msr, title, x=20 + i * 240, y=540, w=220, h=110)
            )
        print("  added 4 forecast-discipline cards")

    if args.build_slicers:
        # Top-of-page slicer row (y=-90 above existing content; we shift cards down via redraw)
        # Place along the right side instead since canvas top is full
        slicers = [
            ("d_region", "region", "Region"),
            ("d_calendar", "fiscal_quarter", "Fiscal Quarter"),
            ("f_opportunity", "motion_type", "Motion"),
        ]
        # Place vertically along left side, before the cards
        for i, (tbl, col, title) in enumerate(slicers):
            section["visualContainers"].append(
                build_slicer_visual(tbl, col, title, x=1000, y=20 + i * 100, w=240, h=90)
            )
        print("  added 3 slicers (region, fiscal_quarter, motion)")

    if args.build_stage_forward:
        # Per-stage forward-rate cards — 6 across, slim row at y=660
        stage_cards = [
            ("Stage 1 Forward Pct", "S1 → S2 (Prospecting)"),
            ("Stage 2 Forward Pct", "S2 → S3 (Discovery)"),
            ("Stage 3 Forward Pct", "S3 → S4 (Engagement)"),
            ("Stage 4 Forward Pct", "S4 → S5 (Shortlisted)"),
            ("Stage 5 Forward Pct", "S5 → S6 (Preferred)"),
            ("Stage 6 Forward Pct", "S6 → Won (Contracting)"),
        ]
        for i, (msr, title) in enumerate(stage_cards):
            section["visualContainers"].append(
                build_card_visual(
                    "f_stage_transition", msr, title, x=20 + i * 160, y=660, w=150, h=90
                )
            )
        print("  added 6 per-stage forward-rate cards")

    if args.year_filter is not None:
        # Section-level filter on d_calendar[year]; matches SalesManager pattern (filters
        # is a JSON-encoded string of a filter array)
        year = args.year_filter
        page_filter = [
            {
                "name": "FilterYear",
                "expression": {
                    "Column": {
                        "Expression": {"SourceRef": {"Entity": "d_calendar"}},
                        "Property": "year",
                    }
                },
                "filter": {
                    "Version": 2,
                    "From": [{"Name": "d", "Entity": "d_calendar", "Type": 0}],
                    "Where": [
                        {
                            "Condition": {
                                "In": {
                                    "Expressions": [
                                        {
                                            "Column": {
                                                "Expression": {"SourceRef": {"Source": "d"}},
                                                "Property": "year",
                                            }
                                        }
                                    ],
                                    "Values": [[{"Literal": {"Value": f"{year}L"}}]],
                                }
                            }
                        }
                    ],
                },
                "type": "Categorical",
                "howCreated": 1,
            }
        ]
        section["filters"] = json.dumps(page_filter)
        print(f"  set page filter: d_calendar[year] = {year}")

    if (
        args.probe
        or args.build_cards
        or args.clear
        or args.year_filter is not None
        or args.motion_breakout
        or args.build_forecast
        or args.build_slicers
        or args.build_stage_forward
    ):
        print(f"\npushing; total visuals: {len(section['visualContainers'])}")
        push_report(token, rj)
        print(
            f"\ndone. open: https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{REPORT_ID}"
        )


if __name__ == "__main__":
    main()
