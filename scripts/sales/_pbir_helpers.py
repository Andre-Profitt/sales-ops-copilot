"""Pure JSON builders for Power BI PBIR-Legacy report.json.

No network, no auth, no side effects. Functions return dict shapes
that get base64-encoded into report.json `visualContainers`."""

from __future__ import annotations

import json
import uuid


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
