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


def build_table_visual(
    name: str,
    columns: list[dict],
    x: float,
    y: float,
    w: float = 900,
    h: float = 240,
) -> dict:
    """Construct a tableEx visualContainer.

    columns: list of {"table": str, "field": str, "kind": "column"|"measure", "title": str}.
    Order of columns in the list = display order in the table.
    """
    visual_name = uuid.uuid4().hex[:20]
    aliases: dict[str, str] = {}
    for c in columns:
        aliases.setdefault(c["table"], chr(ord("a") + len(aliases)))

    select = []
    projections = []
    column_props: dict[str, dict] = {}
    for c in columns:
        alias = aliases[c["table"]]
        query_ref = f"{c['table']}.{c['field']}"
        node_key = "Measure" if c["kind"] == "measure" else "Column"
        select.append(
            {
                node_key: {
                    "Expression": {"SourceRef": {"Source": alias}},
                    "Property": c["field"],
                },
                "Name": query_ref,
            }
        )
        projections.append({"queryRef": query_ref})
        column_props[query_ref] = {"displayName": c["title"]}

    config = {
        "name": visual_name,
        "layouts": [
            {
                "id": 0,
                "position": {
                    "x": x,
                    "y": y,
                    "z": 800,
                    "width": w,
                    "height": h,
                    "tabOrder": 800,
                },
            }
        ],
        "singleVisual": {
            "visualType": "tableEx",
            "projections": {"Values": projections},
            "prototypeQuery": {
                "Version": 2,
                "From": [
                    {"Name": alias, "Entity": tbl, "Type": 0} for tbl, alias in aliases.items()
                ],
                "Select": select,
            },
            "columnProperties": column_props,
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
        "z": 800,
    }


def build_matrix_visual(
    rows: list[dict],
    columns: list[dict],
    values: list[dict],
    x: float,
    y: float,
    w: float = 900,
    h: float = 260,
) -> dict:
    """Construct a pivotTable (matrix) visualContainer.

    rows / columns: list of {"table": str, "field": str, "title": str} — column refs.
    values: list of {"table": str, "field": str, "title": str} — measure refs.
    """
    visual_name = uuid.uuid4().hex[:20]
    aliases: dict[str, str] = {}
    for c in rows + columns + values:
        aliases.setdefault(c["table"], chr(ord("a") + len(aliases)))

    def _col_node(c: dict) -> dict:
        alias = aliases[c["table"]]
        return {
            "Column": {
                "Expression": {"SourceRef": {"Source": alias}},
                "Property": c["field"],
            },
            "Name": f"{c['table']}.{c['field']}",
        }

    def _measure_node(c: dict) -> dict:
        alias = aliases[c["table"]]
        return {
            "Measure": {
                "Expression": {"SourceRef": {"Source": alias}},
                "Property": c["field"],
            },
            "Name": f"{c['table']}.{c['field']}",
        }

    select = (
        [_col_node(c) for c in rows]
        + [_col_node(c) for c in columns]
        + [_measure_node(v) for v in values]
    )
    projections = {
        "Rows": [{"queryRef": f"{c['table']}.{c['field']}"} for c in rows],
        "Columns": [{"queryRef": f"{c['table']}.{c['field']}"} for c in columns],
        "Values": [{"queryRef": f"{v['table']}.{v['field']}"} for v in values],
    }
    column_props: dict[str, dict] = {}
    for c in rows + columns + values:
        column_props[f"{c['table']}.{c['field']}"] = {"displayName": c["title"]}

    config = {
        "name": visual_name,
        "layouts": [
            {
                "id": 0,
                "position": {
                    "x": x,
                    "y": y,
                    "z": 800,
                    "width": w,
                    "height": h,
                    "tabOrder": 800,
                },
            }
        ],
        "singleVisual": {
            "visualType": "pivotTable",
            "projections": projections,
            "prototypeQuery": {
                "Version": 2,
                "From": [
                    {"Name": alias, "Entity": tbl, "Type": 0} for tbl, alias in aliases.items()
                ],
                "Select": select,
            },
            "columnProperties": column_props,
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
        "z": 800,
    }


def _new_section(name: str, display_name: str, ordinal: int) -> dict:
    return {
        "name": name,
        "displayName": display_name,
        "filters": "[]",
        "ordinal": ordinal,
        "visualContainers": [],
        "displayOption": 1,
        "height": 720,
        "width": 1280,
    }


def add_page(report: dict, name: str, display_name: str) -> dict:
    """Append a new page (section). Returns the section dict (existing or new)."""
    if any(s["name"] == name for s in report["sections"]):
        return next(s for s in report["sections"] if s["name"] == name)
    section = _new_section(name, display_name, ordinal=len(report["sections"]))
    report["sections"].append(section)
    return section


def remove_page(report: dict, name: str) -> None:
    """Remove a page (section) by name. No-op if not found."""
    report["sections"] = [s for s in report["sections"] if s["name"] != name]


def ensure_pages(report: dict, targets: list[tuple[str, str]]) -> None:
    """Idempotently ensure each (name, display_name) page exists.

    Existing pages are left untouched (visualContainers preserved).
    Missing pages are appended in the order given.
    """
    existing = {s["name"] for s in report["sections"]}
    for name, display in targets:
        if name not in existing:
            add_page(report, name, display)


def build_card_visual_with_objects(
    measure_table: str,
    measure_name: str,
    display_title: str,
    x: float,
    y: float,
    w: float = 280,
    h: float = 110,
    objects: dict | None = None,
) -> dict:
    """Card variant that accepts a singleVisual.objects block — for conditional
    formatting, theme overrides, font tuning, etc.

    The `objects` shape is browser-authored, not invented. Capture from a
    live-configured visual via:
        python3 -m scripts.sales.rw_capture_visual --extract <visual-name>
    and copy the singleVisual.objects subtree here as the kwarg.

    Common shapes (paste your captured shape — these are placeholders, NOT
    verified):
        # RAG by data-bar / background:
        objects={
            "dataLabels": [{"properties": {"color": {"solid": {"color": "#D32F2F"}}}}],
        }
    """
    vc = build_card_visual(measure_table, measure_name, display_title, x, y, w, h)
    if objects:
        config = json.loads(vc["config"])
        config["singleVisual"]["objects"] = objects
        vc["config"] = json.dumps(config)
    return vc
