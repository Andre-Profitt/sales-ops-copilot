"""Pure JSON builders for Power BI PBIR-Legacy report.json.

No network, no auth, no side effects. Functions return dict shapes
that get base64-encoded into report.json `visualContainers`."""

from __future__ import annotations

import json
import uuid


def _literal(value: str | int | float | bool) -> dict:
    if isinstance(value, bool):
        encoded = "true" if value else "false"
    elif isinstance(value, int):
        encoded = f"{value}L"
    elif isinstance(value, float):
        encoded = f"{value}D"
    else:
        encoded = f"'{value}'"
    return {"expr": {"Literal": {"Value": encoded}}}


def _solid_color(color: str) -> dict:
    return {"solid": {"color": _literal(color)}}


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


def build_textbox_visual(
    text: str,
    x: float,
    y: float,
    w: float = 1200,
    h: float = 26,
    font_size_pt: int = 10,
    color: str = "#666666",
    bold: bool = True,
) -> dict:
    """Construct a textbox visualContainer for section labels and notes.

    This PBIR-Legacy shape matches textbox visuals already used elsewhere
    in this repo and the SalesManager fixture. It has no model binding.
    """
    visual_name = uuid.uuid4().hex[:20]
    text_style = {
        "fontFamily": "Segoe UI",
        "fontSize": f"{font_size_pt}pt",
        "color": color,
    }
    if bold:
        text_style["fontWeight"] = "bold"

    config = {
        "name": visual_name,
        "layouts": [
            {
                "id": 0,
                "position": {
                    "x": x,
                    "y": y,
                    "z": 900,
                    "width": w,
                    "height": h,
                    "tabOrder": 900,
                },
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
                                            "textStyle": text_style,
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
        "config": json.dumps(config),
        "filters": "[]",
        "height": h,
        "width": w,
        "x": x,
        "y": y,
        "z": 900,
    }


def build_shape_visual(
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    fill: str,
    line: str | None = None,
    z: int = 100,
    radius: int = 0,
) -> dict:
    """Construct a basicShape rectangle visualContainer.

    Shape config is based on the verified SalesManager fixture and is used for
    visible dashboard panels behind cards when card-level background objects are
    not honored consistently by the Power BI renderer.
    """
    visual_name = uuid.uuid4().hex[:20]
    line_color = line or fill
    config = {
        "name": visual_name,
        "layouts": [
            {
                "id": 0,
                "position": {
                    "x": x,
                    "y": y,
                    "z": z,
                    "width": w,
                    "height": h,
                    "tabOrder": z,
                },
            }
        ],
        "singleVisual": {
            "visualType": "basicShape",
            "drillFilterOtherVisuals": True,
            "objects": {
                "general": [
                    {
                        "properties": {
                            "shapeType": _literal("rectangle"),
                        }
                    }
                ],
                "fill": [
                    {
                        "properties": {
                            "fillColor": _solid_color(fill),
                        }
                    }
                ],
                "line": [
                    {
                        "properties": {
                            "lineColor": _solid_color(line_color),
                            "weight": _literal(1.0 if line else 0.0),
                        }
                    }
                ],
            },
            "vcObjects": {
                "visualHeader": [
                    {
                        "properties": {
                            "show": _literal(False),
                        }
                    }
                ],
                "border": [
                    {
                        "properties": {
                            "show": _literal(False),
                            "radius": _literal(float(radius)),
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
        "z": z,
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


def build_rag_card_objects(
    *,
    tint: str,
    accent: str,
    value_color: str = "#222222",
    label_color: str = "#666666",
    value_font_size: int = 28,
    label_font_size: int = 10,
    display_units: int | None = None,
) -> dict:
    """Return a conservative legacy-card objects block for RAG KPI cards.

    The labels/categoryLabels shape is based on the verified SalesManager card
    fixture. The background/border objects use standard Power BI container
    object names and are intentionally small so Desktop/Fabric can drop unknown
    subproperties without breaking the visual.
    """
    label_props = {
        "color": _solid_color(value_color),
        "fontSize": _literal(str(value_font_size)),
        "fontFamily": _literal("Segoe UI Semibold"),
    }
    if display_units is not None:
        label_props["labelDisplayUnits"] = _literal(float(display_units))

    return {
        "background": [
            {
                "properties": {
                    "show": _literal(True),
                    "color": _solid_color(tint),
                    "transparency": _literal(0.0),
                }
            }
        ],
        "border": [
            {
                "properties": {
                    "show": _literal(True),
                    "color": _solid_color(accent),
                    "radius": _literal(2),
                }
            }
        ],
        "labels": [{"properties": label_props}],
        "categoryLabels": [
            {
                "properties": {
                    "show": _literal(True),
                    "color": _solid_color(label_color),
                    "fontSize": _literal(str(label_font_size)),
                    "fontFamily": _literal("Segoe UI"),
                }
            }
        ],
    }


def build_rag_card_visual(
    measure_table: str,
    measure_name: str,
    display_title: str,
    x: float,
    y: float,
    w: float = 280,
    h: float = 110,
    *,
    tint: str,
    accent: str,
    value_color: str = "#222222",
    label_color: str = "#666666",
    value_font_size: int = 28,
    label_font_size: int = 10,
    display_units: int | None = None,
) -> dict:
    """Construct a card with the RW RAG visual treatment attached."""
    return build_card_visual_with_objects(
        measure_table=measure_table,
        measure_name=measure_name,
        display_title=display_title,
        x=x,
        y=y,
        w=w,
        h=h,
        objects=build_rag_card_objects(
            tint=tint,
            accent=accent,
            value_color=value_color,
            label_color=label_color,
            value_font_size=value_font_size,
            label_font_size=label_font_size,
            display_units=display_units,
        ),
    )
