"""Push a baseline Power BI report (PBIR-Legacy) to Fabric for the
RW Workforce dashboard, fully scripted. No PBI Desktop, no browser drag.

Visuals on a single page, bound to the existing `sm_workforce_rw`
semantic model. Mirrors the spec in `docs/workforce/POWER_BI_BUILD.md` §4:

  Slicers:    event_week_start, canonical_name
  KPI cards:  Total Effort, Avg Util P75 By Person,
              Overloaded Persons, Underloaded Persons
  Heatmap:    rows=canonical_name, cols=event_week_start,
              values=Mean Util P75 (cond fmt: red >1.5 / grey 0.5-1.5 / blue <0.5)
  Line:       x=event_week_start, y=Mean Util P75 4w, series=canonical_name
  Stacked bar:x=canonical_name, y=Total Effort, series=process_family
  Scatter:    x=Mean Availability, y=Total Effort Adj, dot=canonical_name
  Conc table: coverage_concentration[segment, process_family,
              top1_person_name, top1_share]  (highlight top1_share>0.5)

Plus a compliance text-box on page 1 with the AI Code of Conduct §8 wording
verbatim from `docs/workforce/POWER_BI_BUILD.md`.

Source-of-truth threshold values (1.5 / 0.5 / 0.5) are mirrored from
`scripts/workforce/wf_kpi_graph.py` (_THRESHOLDS). DO NOT invent new ones.

Usage:
    python3 scripts/workforce/wf_push_report.py
"""

from __future__ import annotations

import base64
import json
import time
import uuid

import requests
from azure.identity import AzureCliCredential

WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"
SEMANTIC_MODEL_ID = "3ddb779b-0240-42b3-9d1e-2c7eb310224a"  # sm_workforce_rw
REPORT_NAME = "rpt_workforce_rw"

# Workspace display name has a timestamp suffix in this tenant — must be
# verbatim or the byConnection string is rejected (matches sister script).
WORKSPACE_NAME_FOR_CONNECTION = "Salesforce Analytics - Sales Manager 1/6/2024, 1:06:06 PM"
SEMANTIC_MODEL_CATALOG = "sm_workforce_rw"

# Threshold constants — mirrored verbatim from wf_kpi_graph._THRESHOLDS.
# DO NOT diverge from the KG; it is the single source of truth.
THRESHOLD_OVERLOADED = 1.5  # load_overloaded
THRESHOLD_UNDERLOADED = 0.5  # load_underloaded
THRESHOLD_SPOF_POINT = 0.5  # concentration_spof_point

# Compliance block — verbatim from docs/workforce/POWER_BI_BUILD.md.
COMPLIANCE_TEXT = (
    "Methodology and constraints. Effort is a weighted-event proxy; no "
    "time-tracking exists. Roster is inferred (replace with authoritative "
    "source when available). Per AI Code of Conduct §8: do not use these "
    "KPIs for per-individual evaluative or predictive judgments. Forecast "
    "is at process-family granularity only. Static-pack data ends "
    "2025-12-15. Source: scripts/workforce/wf_kpi_graph.py (schema v1)."
)

FABRIC = "https://api.fabric.microsoft.com"
FABRIC_RES = "https://api.fabric.microsoft.com/.default"


# ──────────────────────────────────────────────────────────────────────────
# PBIR-Legacy builders — emit dicts; we base64-encode at the end
# ──────────────────────────────────────────────────────────────────────────


def _new_id() -> str:
    """20-char unique id for visual `name` collisions per research."""
    return uuid.uuid4().hex[:20]


def build_pbir_definition() -> dict:
    """definition.pbir — points to sm_workforce_rw via byConnection.

    Connection-string format reverse-engineered from working reports in
    this tenant: requires Data Source URL + initial catalog + ClaimsToken
    + semanticmodelid. byPath is rejected; semanticmodelid alone is rejected.
    """
    cs = (
        f'Data Source="powerbi://api.powerbi.com/v1.0/myorg/{WORKSPACE_NAME_FOR_CONNECTION}";'
        f"initial catalog={SEMANTIC_MODEL_CATALOG};"
        f"integrated security=ClaimsToken;"
        f"semanticmodelid={SEMANTIC_MODEL_ID}"
    )
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byConnection": {"connectionString": cs}},
    }


# ── Visual container builders for the PBIR-Legacy `report.json` shape ───
# In PBIR-Legacy, a section has visualContainers[] whose items carry
# stringified JSON in `config`, `query`, `filters`, `dataTransforms`. We
# emit minimal shells for each — Power BI Service will lay them out and
# the user can adjust position/size in browser if desired. The dataset
# binding ensures the semantic model is wired so the visuals render
# real data on first open.


def _vc_text(name: str, x: float, y: float, w: float, h: float, text: str) -> dict:
    """A textbox visualContainer — used for the compliance block."""
    cfg = {
        "name": name,
        "layouts": [
            {
                "id": 0,
                "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0},
            }
        ],
        "singleVisual": {
            "visualType": "textbox",
            "drillFilterOtherVisuals": True,
            "objects": {
                "general": [
                    {
                        "properties": {
                            "paragraphs": [
                                {
                                    "textRuns": [
                                        {
                                            "value": text,
                                            "textStyle": {"fontSize": "10pt"},
                                        }
                                    ],
                                    "horizontalTextAlignment": "left",
                                }
                            ]
                        }
                    }
                ]
            },
        },
    }
    return {
        "x": x,
        "y": y,
        "z": 0,
        "width": w,
        "height": h,
        "config": json.dumps(cfg),
    }


def _vc_slicer(name: str, x: float, y: float, w: float, h: float, entity: str, prop: str) -> dict:
    cfg = {
        "name": name,
        "layouts": [
            {
                "id": 0,
                "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0},
            }
        ],
        "singleVisual": {
            "visualType": "slicer",
            "projections": {
                "Values": [
                    {
                        "queryRef": f"{entity}.{prop}",
                        "active": True,
                    }
                ]
            },
            "drillFilterOtherVisuals": True,
        },
    }
    query = {
        "Commands": [
            {
                "SemanticQueryDataShapeCommand": {
                    "Query": {
                        "Version": 2,
                        "From": [{"Name": "t", "Entity": entity, "Type": 0}],
                        "Select": [
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "t"}},
                                    "Property": prop,
                                },
                                "Name": f"{entity}.{prop}",
                            }
                        ],
                    }
                }
            }
        ]
    }
    return {
        "x": x,
        "y": y,
        "z": 0,
        "width": w,
        "height": h,
        "config": json.dumps(cfg),
        "query": json.dumps(query),
        "filters": "[]",
    }


def _vc_card(
    name: str, x: float, y: float, w: float, h: float, table: str, measure: str, title: str
) -> dict:
    cfg = {
        "name": name,
        "layouts": [
            {
                "id": 0,
                "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0},
            }
        ],
        "singleVisual": {
            "visualType": "card",
            "projections": {
                "Values": [
                    {
                        "queryRef": f"{table}.{measure}",
                        "active": True,
                    }
                ]
            },
            "objects": {
                "title": [
                    {
                        "properties": {
                            "show": {"expr": {"Literal": {"Value": "true"}}},
                            "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
                        }
                    }
                ],
            },
            "drillFilterOtherVisuals": True,
        },
    }
    query = {
        "Commands": [
            {
                "SemanticQueryDataShapeCommand": {
                    "Query": {
                        "Version": 2,
                        "From": [{"Name": "t", "Entity": table, "Type": 0}],
                        "Select": [
                            {
                                "Measure": {
                                    "Expression": {"SourceRef": {"Source": "t"}},
                                    "Property": measure,
                                },
                                "Name": f"{table}.{measure}",
                            }
                        ],
                    }
                }
            }
        ]
    }
    return {
        "x": x,
        "y": y,
        "z": 0,
        "width": w,
        "height": h,
        "config": json.dumps(cfg),
        "query": json.dumps(query),
        "filters": "[]",
    }


def _vc_matrix_heatmap(
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    row_entity: str,
    row_prop: str,
    col_entity: str,
    col_prop: str,
    measure_entity: str,
    measure_prop: str,
) -> dict:
    """Matrix visual w/ conditional formatting on values cells.
    Thresholds mirror wf_kpi_graph._THRESHOLDS.load_overloaded / load_underloaded:
       value > 1.5 → red       (overloaded)
       0.5 <= v <= 1.5 → grey  (in-band)
       value < 0.5  → blue     (underloaded)
    """
    cfg = {
        "name": name,
        "layouts": [
            {
                "id": 0,
                "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0},
            }
        ],
        "singleVisual": {
            "visualType": "pivotTable",
            "projections": {
                "Rows": [{"queryRef": f"{row_entity}.{row_prop}", "active": True}],
                "Columns": [{"queryRef": f"{col_entity}.{col_prop}", "active": True}],
                "Values": [{"queryRef": f"{measure_entity}.{measure_prop}", "active": True}],
            },
            "objects": {
                "values": [
                    {
                        "properties": {
                            "backColor": {
                                "solid": {
                                    "color": {
                                        "expr": {
                                            "Conditional": {
                                                "Cases": [
                                                    {
                                                        "Condition": {
                                                            "Comparison": {
                                                                "ComparisonKind": 2,
                                                                "Left": {
                                                                    "Measure": {
                                                                        "Expression": {
                                                                            "SourceRef": {
                                                                                "Entity": measure_entity
                                                                            }
                                                                        },
                                                                        "Property": measure_prop,
                                                                    }
                                                                },
                                                                "Right": {
                                                                    "Literal": {
                                                                        "Value": f"{THRESHOLD_OVERLOADED}D"
                                                                    }
                                                                },
                                                            }
                                                        },
                                                        "Value": {
                                                            "Literal": {"Value": "'#E74C3C'"}
                                                        },
                                                    },
                                                    {
                                                        "Condition": {
                                                            "Comparison": {
                                                                "ComparisonKind": 1,
                                                                "Left": {
                                                                    "Measure": {
                                                                        "Expression": {
                                                                            "SourceRef": {
                                                                                "Entity": measure_entity
                                                                            }
                                                                        },
                                                                        "Property": measure_prop,
                                                                    }
                                                                },
                                                                "Right": {
                                                                    "Literal": {
                                                                        "Value": f"{THRESHOLD_UNDERLOADED}D"
                                                                    }
                                                                },
                                                            }
                                                        },
                                                        "Value": {
                                                            "Literal": {"Value": "'#3498DB'"}
                                                        },
                                                    },
                                                ],
                                                "Default": {"Literal": {"Value": "'#BDC3C7'"}},
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                ],
                "title": [
                    {
                        "properties": {
                            "show": {"expr": {"Literal": {"Value": "true"}}},
                            "text": {
                                "expr": {
                                    "Literal": {
                                        "Value": "'Utilization Heatmap (red >1.5 / grey 0.5-1.5 / blue <0.5)'"
                                    }
                                }
                            },
                        }
                    }
                ],
            },
            "drillFilterOtherVisuals": True,
        },
    }
    query = {
        "Commands": [
            {
                "SemanticQueryDataShapeCommand": {
                    "Query": {
                        "Version": 2,
                        "From": [
                            {"Name": "r", "Entity": row_entity, "Type": 0},
                            {"Name": "c", "Entity": col_entity, "Type": 0},
                            {"Name": "m", "Entity": measure_entity, "Type": 0},
                        ],
                        "Select": [
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "r"}},
                                    "Property": row_prop,
                                },
                                "Name": f"{row_entity}.{row_prop}",
                            },
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "c"}},
                                    "Property": col_prop,
                                },
                                "Name": f"{col_entity}.{col_prop}",
                            },
                            {
                                "Measure": {
                                    "Expression": {"SourceRef": {"Source": "m"}},
                                    "Property": measure_prop,
                                },
                                "Name": f"{measure_entity}.{measure_prop}",
                            },
                        ],
                    }
                }
            }
        ]
    }
    return {
        "x": x,
        "y": y,
        "z": 0,
        "width": w,
        "height": h,
        "config": json.dumps(cfg),
        "query": json.dumps(query),
        "filters": "[]",
    }


def _vc_line_chart(
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    axis_entity: str,
    axis_prop: str,
    measure_entity: str,
    measure_prop: str,
    series_entity: str,
    series_prop: str,
) -> dict:
    cfg = {
        "name": name,
        "layouts": [
            {
                "id": 0,
                "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0},
            }
        ],
        "singleVisual": {
            "visualType": "lineChart",
            "projections": {
                "Category": [{"queryRef": f"{axis_entity}.{axis_prop}", "active": True}],
                "Y": [{"queryRef": f"{measure_entity}.{measure_prop}", "active": True}],
                "Series": [{"queryRef": f"{series_entity}.{series_prop}", "active": True}],
            },
            "objects": {
                "title": [
                    {
                        "properties": {
                            "show": {"expr": {"Literal": {"Value": "true"}}},
                            "text": {
                                "expr": {
                                    "Literal": {"Value": "'Util P75 4w trend (top-N by activity)'"}
                                }
                            },
                        }
                    }
                ]
            },
            "drillFilterOtherVisuals": True,
        },
    }
    query = {
        "Commands": [
            {
                "SemanticQueryDataShapeCommand": {
                    "Query": {
                        "Version": 2,
                        "From": [
                            {"Name": "a", "Entity": axis_entity, "Type": 0},
                            {"Name": "m", "Entity": measure_entity, "Type": 0},
                            {"Name": "s", "Entity": series_entity, "Type": 0},
                        ],
                        "Select": [
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "a"}},
                                    "Property": axis_prop,
                                },
                                "Name": f"{axis_entity}.{axis_prop}",
                            },
                            {
                                "Measure": {
                                    "Expression": {"SourceRef": {"Source": "m"}},
                                    "Property": measure_prop,
                                },
                                "Name": f"{measure_entity}.{measure_prop}",
                            },
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "s"}},
                                    "Property": series_prop,
                                },
                                "Name": f"{series_entity}.{series_prop}",
                            },
                        ],
                    }
                }
            }
        ]
    }
    return {
        "x": x,
        "y": y,
        "z": 0,
        "width": w,
        "height": h,
        "config": json.dumps(cfg),
        "query": json.dumps(query),
        "filters": "[]",
    }


def _vc_stacked_bar(
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    cat_entity: str,
    cat_prop: str,
    measure_entity: str,
    measure_prop: str,
    series_entity: str,
    series_prop: str,
) -> dict:
    cfg = {
        "name": name,
        "layouts": [
            {
                "id": 0,
                "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0},
            }
        ],
        "singleVisual": {
            "visualType": "stackedColumnChart",
            "projections": {
                "Category": [{"queryRef": f"{cat_entity}.{cat_prop}", "active": True}],
                "Y": [{"queryRef": f"{measure_entity}.{measure_prop}", "active": True}],
                "Series": [{"queryRef": f"{series_entity}.{series_prop}", "active": True}],
            },
            "objects": {
                "title": [
                    {
                        "properties": {
                            "show": {"expr": {"Literal": {"Value": "true"}}},
                            "text": {
                                "expr": {
                                    "Literal": {
                                        "Value": "'Effort by person, stacked by process_family'"
                                    }
                                }
                            },
                        }
                    }
                ]
            },
            "drillFilterOtherVisuals": True,
        },
    }
    query = {
        "Commands": [
            {
                "SemanticQueryDataShapeCommand": {
                    "Query": {
                        "Version": 2,
                        "From": [
                            {"Name": "c", "Entity": cat_entity, "Type": 0},
                            {"Name": "m", "Entity": measure_entity, "Type": 0},
                            {"Name": "s", "Entity": series_entity, "Type": 0},
                        ],
                        "Select": [
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "c"}},
                                    "Property": cat_prop,
                                },
                                "Name": f"{cat_entity}.{cat_prop}",
                            },
                            {
                                "Measure": {
                                    "Expression": {"SourceRef": {"Source": "m"}},
                                    "Property": measure_prop,
                                },
                                "Name": f"{measure_entity}.{measure_prop}",
                            },
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "s"}},
                                    "Property": series_prop,
                                },
                                "Name": f"{series_entity}.{series_prop}",
                            },
                        ],
                    }
                }
            }
        ]
    }
    return {
        "x": x,
        "y": y,
        "z": 0,
        "width": w,
        "height": h,
        "config": json.dumps(cfg),
        "query": json.dumps(query),
        "filters": "[]",
    }


def _vc_scatter(
    name: str,
    x: float,
    y: float,
    w: float,
    h: float,
    x_table: str,
    x_measure: str,
    y_table: str,
    y_measure: str,
    dot_entity: str,
    dot_prop: str,
) -> dict:
    cfg = {
        "name": name,
        "layouts": [
            {
                "id": 0,
                "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0},
            }
        ],
        "singleVisual": {
            "visualType": "scatterChart",
            "projections": {
                "X": [{"queryRef": f"{x_table}.{x_measure}", "active": True}],
                "Y": [{"queryRef": f"{y_table}.{y_measure}", "active": True}],
                "Details": [{"queryRef": f"{dot_entity}.{dot_prop}", "active": True}],
            },
            "objects": {
                "title": [
                    {
                        "properties": {
                            "show": {"expr": {"Literal": {"Value": "true"}}},
                            "text": {
                                "expr": {"Literal": {"Value": "'Availability vs Adjusted Effort'"}}
                            },
                        }
                    }
                ]
            },
            "drillFilterOtherVisuals": True,
        },
    }
    query = {
        "Commands": [
            {
                "SemanticQueryDataShapeCommand": {
                    "Query": {
                        "Version": 2,
                        "From": [
                            {"Name": "x", "Entity": x_table, "Type": 0},
                            {"Name": "y", "Entity": y_table, "Type": 0},
                            {"Name": "d", "Entity": dot_entity, "Type": 0},
                        ],
                        "Select": [
                            {
                                "Measure": {
                                    "Expression": {"SourceRef": {"Source": "x"}},
                                    "Property": x_measure,
                                },
                                "Name": f"{x_table}.{x_measure}",
                            },
                            {
                                "Measure": {
                                    "Expression": {"SourceRef": {"Source": "y"}},
                                    "Property": y_measure,
                                },
                                "Name": f"{y_table}.{y_measure}",
                            },
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "d"}},
                                    "Property": dot_prop,
                                },
                                "Name": f"{dot_entity}.{dot_prop}",
                            },
                        ],
                    }
                }
            }
        ]
    }
    return {
        "x": x,
        "y": y,
        "z": 0,
        "width": w,
        "height": h,
        "config": json.dumps(cfg),
        "query": json.dumps(query),
        "filters": "[]",
    }


def _vc_concentration_table(name: str, x: float, y: float, w: float, h: float) -> dict:
    """Table over coverage_concentration with conditional fmt on top1_share>0.5."""
    cfg = {
        "name": name,
        "layouts": [
            {
                "id": 0,
                "position": {"x": x, "y": y, "z": 0, "width": w, "height": h, "tabOrder": 0},
            }
        ],
        "singleVisual": {
            "visualType": "tableEx",
            "projections": {
                "Values": [
                    {"queryRef": "coverage_concentration.segment", "active": True},
                    {"queryRef": "coverage_concentration.process_family", "active": True},
                    {"queryRef": "coverage_concentration.top1_person_name", "active": True},
                    {"queryRef": "coverage_concentration.top1_share", "active": True},
                ]
            },
            "objects": {
                "values": [
                    {
                        "properties": {
                            "backColor": {
                                "solid": {
                                    "color": {
                                        "expr": {
                                            "Conditional": {
                                                "Cases": [
                                                    {
                                                        "Condition": {
                                                            "Comparison": {
                                                                "ComparisonKind": 2,
                                                                "Left": {
                                                                    "Column": {
                                                                        "Expression": {
                                                                            "SourceRef": {
                                                                                "Entity": "coverage_concentration"
                                                                            }
                                                                        },
                                                                        "Property": "top1_share",
                                                                    }
                                                                },
                                                                "Right": {
                                                                    "Literal": {
                                                                        "Value": f"{THRESHOLD_SPOF_POINT}D"
                                                                    }
                                                                },
                                                            }
                                                        },
                                                        "Value": {
                                                            "Literal": {"Value": "'#F8D7DA'"}
                                                        },
                                                    }
                                                ],
                                                "Default": {"Literal": {"Value": "'#FFFFFF'"}},
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                ],
                "title": [
                    {
                        "properties": {
                            "show": {"expr": {"Literal": {"Value": "true"}}},
                            "text": {
                                "expr": {
                                    "Literal": {
                                        "Value": "'Concentration — segments where top1_share > 0.5 (point SPOF)'"
                                    }
                                }
                            },
                        }
                    }
                ],
            },
            "drillFilterOtherVisuals": True,
        },
    }
    query = {
        "Commands": [
            {
                "SemanticQueryDataShapeCommand": {
                    "Query": {
                        "Version": 2,
                        "From": [{"Name": "c", "Entity": "coverage_concentration", "Type": 0}],
                        "Select": [
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "c"}},
                                    "Property": "segment",
                                },
                                "Name": "coverage_concentration.segment",
                            },
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "c"}},
                                    "Property": "process_family",
                                },
                                "Name": "coverage_concentration.process_family",
                            },
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "c"}},
                                    "Property": "top1_person_name",
                                },
                                "Name": "coverage_concentration.top1_person_name",
                            },
                            {
                                "Column": {
                                    "Expression": {"SourceRef": {"Source": "c"}},
                                    "Property": "top1_share",
                                },
                                "Name": "coverage_concentration.top1_share",
                            },
                        ],
                    }
                }
            }
        ]
    }
    return {
        "x": x,
        "y": y,
        "z": 0,
        "width": w,
        "height": h,
        "config": json.dumps(cfg),
        "query": json.dumps(query),
        "filters": "[]",
    }


def build_visual_containers() -> list[dict]:
    """All visualContainers for the page, in spec order from POWER_BI_BUILD.md §4.

    Layout: 1280×720 page.
      Row 1 (y=20):     2 slicers (left)
      Row 2 (y=110):    4 KPI cards
      Row 3 (y=240):    heatmap (full width)
      Row 4 (y=420):    line chart | stacked bar
      Row 5 (y=580):    scatter | concentration table
      Footer (y=700):   compliance text-box
    """
    vcs: list[dict] = []

    # ── Row 1: Slicers (event_week_start + canonical_name) ─────────────
    vcs.append(_vc_slicer(_new_id(), 20, 20, 280, 80, "weekly_person_kpis", "event_week_start"))
    vcs.append(_vc_slicer(_new_id(), 320, 20, 280, 80, "weekly_person_kpis", "canonical_name"))

    # ── Row 2: 4 KPI cards (the spec calls for these names verbatim) ───
    # Spec says: "Total Effort, Avg Util P75, Overloaded Count, Underloaded Count"
    # Mapped to the actual measures published in sm_workforce_rw:
    #   Total Effort           → Total Effort
    #   Avg Util P75           → Avg Util P75 By Person
    #   Overloaded Count       → Overloaded Persons
    #   Underloaded Count      → Underloaded Persons
    cards = [
        ("weekly_person_kpis", "Total Effort", "Total Effort"),
        ("weekly_person_kpis", "Avg Util P75 By Person", "Avg Util P75"),
        ("weekly_person_kpis", "Overloaded Persons", "Overloaded Count"),
        ("weekly_person_kpis", "Underloaded Persons", "Underloaded Count"),
    ]
    for i, (tbl, msr, title) in enumerate(cards):
        vcs.append(_vc_card(_new_id(), 20 + i * 310, 110, 290, 110, tbl, msr, title))

    # ── Row 3: Heatmap (matrix) — full width ───────────────────────────
    vcs.append(
        _vc_matrix_heatmap(
            _new_id(),
            20,
            240,
            1240,
            170,
            row_entity="weekly_person_kpis",
            row_prop="canonical_name",
            col_entity="weekly_person_kpis",
            col_prop="event_week_start",
            measure_entity="weekly_person_kpis",
            measure_prop="Mean Util P75",
        )
    )

    # ── Row 4: Line chart | Stacked bar ────────────────────────────────
    vcs.append(
        _vc_line_chart(
            _new_id(),
            20,
            420,
            610,
            150,
            axis_entity="weekly_person_kpis",
            axis_prop="event_week_start",
            measure_entity="weekly_person_kpis",
            measure_prop="Mean Util P75 4w",
            series_entity="weekly_person_kpis",
            series_prop="canonical_name",
        )
    )
    # Stacked bar — spec wants `process_family` series. The published
    # `weekly_person_kpis` table has no `process_family` column (see
    # wf_push_semantic_model.py). Use `coverage_concentration.process_family`
    # as the series proxy since the model has no fact_activity table.
    vcs.append(
        _vc_stacked_bar(
            _new_id(),
            650,
            420,
            610,
            150,
            cat_entity="weekly_person_kpis",
            cat_prop="canonical_name",
            measure_entity="weekly_person_kpis",
            measure_prop="Total Effort",
            series_entity="coverage_concentration",
            series_prop="process_family",
        )
    )

    # ── Row 5: Scatter | Concentration table ───────────────────────────
    vcs.append(
        _vc_scatter(
            _new_id(),
            20,
            580,
            610,
            110,
            x_table="weekly_person_kpis",
            x_measure="Mean Availability",
            y_table="weekly_person_kpis",
            y_measure="Total Effort Adj",
            dot_entity="weekly_person_kpis",
            dot_prop="canonical_name",
        )
    )
    vcs.append(_vc_concentration_table(_new_id(), 650, 580, 610, 110))

    # ── Footer: Compliance text-box (AI Code §8 wording, verbatim) ─────
    vcs.append(_vc_text(_new_id(), 20, 700, 1240, 20, COMPLIANCE_TEXT))

    return vcs


# ──────────────────────────────────────────────────────────────────────────
# Push to Fabric REST
# ──────────────────────────────────────────────────────────────────────────


def _b64(s: str | dict) -> str:
    if isinstance(s, dict):
        s = json.dumps(s, indent=2)
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _token(resource: str) -> str:
    return AzureCliCredential().get_token(resource).token


def _wait_lro(response: requests.Response, fabric_token: str) -> dict | None:
    if response.status_code in (200, 201):
        return response.json() if response.text else None
    if response.status_code != 202:
        print(f"  status {response.status_code}: {response.text[:600]}")
        response.raise_for_status()
    op_id = response.headers.get("x-ms-operation-id")
    location = response.headers.get("Location") or f"{FABRIC}/v1/operations/{op_id}"
    print(f"  LRO accepted; polling op {op_id}")
    while True:
        time.sleep(int(response.headers.get("Retry-After", 3)))
        r = requests.get(location, headers={"Authorization": f"Bearer {fabric_token}"})
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
                    headers={"Authorization": f"Bearer {fabric_token}"},
                )
                return rr.json() if rr.text else None
            print(f"  status={status}")
        else:
            print(f"  poll status {r.status_code}: {r.text[:200]}")
            return None


def find_existing(fabric_token: str) -> str | None:
    r = requests.get(
        f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/reports",
        headers={"Authorization": f"Bearer {fabric_token}"},
    )
    r.raise_for_status()
    for rep in r.json().get("value", []):
        if rep.get("displayName") == REPORT_NAME:
            return rep["id"]
    return None


def deploy() -> str:
    fabric_token = _token(FABRIC_RES)
    visual_containers = build_visual_containers()

    # PBIR-Legacy single-file format (matches what this tenant accepts;
    # multi-file PBIR 4.0 with separate page/visual files is rejected here
    # for byConnection-bound reports). Visual configs are embedded directly
    # in sections[0].visualContainers via stringified `config` and `query`.
    minimal_report_json = {
        "config": json.dumps(
            {
                "version": "5.55",
                "themeCollection": {"baseTheme": {"name": "CY24SU10"}},
                "settings": {"useNewFilterPaneExperience": True},
            }
        ),
        "layoutOptimization": 0,
        "publicCustomVisuals": [],
        "resourcePackages": [],
        "sections": [
            {
                "name": "workforce_rw",
                "displayName": "Workforce — Richard Wyeth",
                "filters": "[]",
                "ordinal": 0,
                "visualContainers": visual_containers,
                "config": json.dumps({"visibility": 0}),
                "height": 720,
                "width": 1280,
            }
        ],
    }
    parts = [
        {
            "path": "definition.pbir",
            "payload": _b64(build_pbir_definition()),
            "payloadType": "InlineBase64",
        },
        {
            "path": "report.json",
            "payload": _b64(minimal_report_json),
            "payloadType": "InlineBase64",
        },
    ]
    print(
        f"  parts: {len(parts)} files (PBIR-Legacy: definition.pbir + report.json with "
        f"{len(visual_containers)} visualContainers)"
    )

    headers = {"Authorization": f"Bearer {fabric_token}", "Content-Type": "application/json"}
    existing = find_existing(fabric_token)

    if existing:
        print(f"Updating report {existing}")
        r = requests.post(
            f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/reports/{existing}/updateDefinition",
            headers=headers,
            json={"definition": {"parts": parts}},
        )
        _wait_lro(r, fabric_token)
        return existing

    print(f"Creating report {REPORT_NAME}")
    r = requests.post(
        f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/reports",
        headers=headers,
        json={
            "displayName": REPORT_NAME,
            "description": (
                "RW Workforce dashboard for Richard Wyeth (MD Sales Ops). "
                "Source: scripts/workforce/wf_kpi_graph.py (KG schema v1) + "
                "docs/workforce/POWER_BI_BUILD.md §4. Bound to sm_workforce_rw."
            ),
            "definition": {"parts": parts},
        },
    )
    if r.status_code in (200, 201):
        return r.json()["id"]
    if r.status_code == 202:
        result = _wait_lro(r, fabric_token)
        if result and isinstance(result, dict):
            return result.get("id", "")
    r.raise_for_status()
    return ""


def main() -> None:
    rid = deploy()
    if not rid:
        print("deploy returned no id")
        return
    print(f"\nreport id: {rid}")
    print(f"open: https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{rid}")


if __name__ == "__main__":
    main()
