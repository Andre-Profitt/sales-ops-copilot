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


def _column_expr(alias: str, field: str) -> dict:
    return {
        "Column": {
            "Expression": {"SourceRef": {"Source": alias}},
            "Property": field,
        }
    }


def _measure_expr(alias: str, measure: str) -> dict:
    return {
        "Measure": {
            "Expression": {"SourceRef": {"Source": alias}},
            "Property": measure,
        }
    }


def _stage_order_expr(aliases: dict[str, str], table: str, field: str) -> dict | None:
    """Return the safest available stage-order expression for a visual.

    Stage labels must follow the SimCorp handbook order: 1-6, Opt-out, Won.
    The semantic model carries explicit sort keys for opportunity and transition
    stage fields so visuals never fall back to alphabetical or raw numeric sort.
    """
    alias = aliases[table]
    if table == "f_stage_transition" and field == "from_stage_name":
        return _column_expr(alias, "from_stage_order")
    if table == "f_stage_transition" and field == "to_stage_name":
        return _column_expr(alias, "to_stage_order")
    if table == "f_opportunity" and field == "stage_name":
        return _column_expr(alias, "stage_order")
    return None


def _first_stage_order_by(columns: list[dict], aliases: dict[str, str]) -> list[dict]:
    for c in columns:
        if c["kind"] != "column":
            continue
        expr = _stage_order_expr(aliases, c["table"], c["field"])
        if expr is not None:
            return [{"Direction": 1, "Expression": expr}]
    return []


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
    *,
    font_size: int = 8,
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
                "header": [
                    {
                        "properties": {
                            "textSize": _literal(font_size),
                            "fontColor": _solid_color("#1A1D31"),
                            "background": _solid_color("#FFFFFF"),
                        }
                    }
                ],
                "items": [
                    {
                        "properties": {
                            "textSize": _literal(font_size),
                            "fontColor": _solid_color("#202124"),
                            "background": _solid_color("#FFFFFF"),
                        }
                    }
                ],
            },
            "vcObjects": {
                "title": [{"properties": {"show": _literal(False)}}],
                "visualHeader": [{"properties": {"show": _literal(False)}}],
                "border": [
                    {
                        "properties": {
                            "show": _literal(True),
                            "color": _solid_color("#D8DEE8"),
                            "radius": _literal(2),
                        }
                    }
                ],
                "background": [
                    {
                        "properties": {
                            "show": _literal(True),
                            "color": _solid_color("#FFFFFF"),
                            "transparency": _literal(0.0),
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
    objects: dict | None = None,
    vc_objects: dict | None = None,
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
        expr = _measure_expr(alias, c["field"]) if node_key == "Measure" else _column_expr(alias, c["field"])
        select.append({**expr, "Name": query_ref})
        projections.append({"queryRef": query_ref})
        column_props[query_ref] = {"displayName": c["title"]}

    prototype_query = {
        "Version": 2,
        "From": [{"Name": alias, "Entity": tbl, "Type": 0} for tbl, alias in aliases.items()],
        "Select": select,
    }
    order_by = _first_stage_order_by(columns, aliases)
    if order_by:
        prototype_query["OrderBy"] = order_by

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
            "prototypeQuery": prototype_query,
            "columnProperties": column_props,
            "drillFilterOtherVisuals": True,
        },
    }
    if objects:
        config["singleVisual"]["objects"] = objects
    if vc_objects:
        config["singleVisual"]["vcObjects"] = vc_objects
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
    objects: dict | None = None,
    vc_objects: dict | None = None,
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
        return {**_column_expr(alias, c["field"]), "Name": f"{c['table']}.{c['field']}"}

    def _measure_node(c: dict) -> dict:
        alias = aliases[c["table"]]
        return {**_measure_expr(alias, c["field"]), "Name": f"{c['table']}.{c['field']}"}

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

    prototype_query = {
        "Version": 2,
        "From": [{"Name": alias, "Entity": tbl, "Type": 0} for tbl, alias in aliases.items()],
        "Select": select,
    }
    order_by = _first_stage_order_by(
        [{**c, "kind": "column"} for c in rows + columns],
        aliases,
    )
    if order_by:
        prototype_query["OrderBy"] = order_by

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
            "prototypeQuery": prototype_query,
            "columnProperties": column_props,
            "drillFilterOtherVisuals": True,
        },
    }
    if objects:
        config["singleVisual"]["objects"] = objects
    if vc_objects:
        config["singleVisual"]["vcObjects"] = vc_objects
    return {
        "config": json.dumps(config),
        "filters": "[]",
        "height": h,
        "width": w,
        "x": x,
        "y": y,
        "z": 800,
    }


ZEBRA_BI_TABLES_VISUAL_TYPE = "ZebraBITables98F88148E5424E949E69864664EE1860"


def build_zebra_bi_table_visual(
    *,
    categories: list[dict],
    values: list[dict],
    x: float,
    y: float,
    w: float = 900,
    h: float = 320,
    visual_type: str = ZEBRA_BI_TABLES_VISUAL_TYPE,
    show_grand_total: bool = True,
    value_chart: int = 1,
) -> dict:
    """Construct a Zebra BI Tables visualContainer.

    The shape is mined from Zebra BI's downloadable PBIX templates, then reduced
    to the reusable, non-sensitive parts: visual type, projection roles,
    prototypeQuery, and conservative object settings. It intentionally does not
    embed a Zebra license key; activation belongs to the local Power BI/Zebra
    account state.

    categories: [{"table": str, "field": str, "title": str}]
    values: [{"table": str, "field": str, "title": str}]
    """
    visual_name = uuid.uuid4().hex[:20]
    aliases: dict[str, str] = {}
    for item in categories + values:
        aliases.setdefault(item["table"], chr(ord("a") + len(aliases)))

    select = []
    select_meta = []
    projections = {"Category": [], "Values": []}
    column_props: dict[str, dict] = {}

    for projection_index, item in enumerate(categories):
        alias = aliases[item["table"]]
        query_ref = f"{item['table']}.{item['field']}"
        select.append(
            {
                "Column": {
                    "Expression": {"SourceRef": {"Source": alias}},
                    "Property": item["field"],
                },
                "Name": query_ref,
            }
        )
        projections["Category"].append({"queryRef": query_ref, "active": True})
        column_props[query_ref] = {"displayName": item["title"]}
        select_meta.append(
            {
                "displayName": item["title"],
                "queryName": query_ref,
                "role": "Category",
                "projection": projection_index,
                "kind": "column",
                "table": item["table"],
                "field": item["field"],
            }
        )

    for value_index, item in enumerate(values, start=len(categories)):
        alias = aliases[item["table"]]
        query_ref = f"{item['table']}.{item['field']}"
        select.append(
            {
                "Measure": {
                    "Expression": {"SourceRef": {"Source": alias}},
                    "Property": item["field"],
                },
                "Name": query_ref,
            }
        )
        projections["Values"].append({"queryRef": query_ref})
        column_props[query_ref] = {"displayName": item["title"]}
        select_meta.append(
            {
                "displayName": item["title"],
                "queryName": query_ref,
                "role": "Values",
                "projection": value_index,
                "kind": "measure",
                "table": item["table"],
                "field": item["field"],
            }
        )

    prototype_query = {
        "Version": 2,
        "From": [{"Name": alias, "Entity": tbl, "Type": 0} for tbl, alias in aliases.items()],
        "Select": select,
    }
    all_projections = [item["projection"] for item in select_meta]
    binding = {
        "Primary": {"Groupings": [{"Projections": all_projections, "Subtotal": 2}]},
        "DataReduction": {
            "DataVolume": 3,
            "Primary": {"Bottom": {"Count": 30000}},
        },
        "Version": 1,
    }
    object_settings = {
        "version": [{"properties": {"version": _literal("7.4.1")}}],
        "proFeaturesSettings": [{"properties": {"show": _literal(True)}}],
        "chartSettings": [
            {
                "properties": {
                    "showGrandTotal": _literal(show_grand_total),
                    "showGridlines": _literal(False),
                    "firstTimeShowingColumnAdder": _literal(False),
                    "valueChart": _literal(value_chart),
                }
            }
        ],
        "titleSettings": [{"properties": {"show": _literal(False)}}],
    }
    data_transforms = {
        "objects": object_settings,
        "projectionOrdering": {
            "Category": [item["projection"] for item in select_meta if item["role"] == "Category"],
            "Values": [item["projection"] for item in select_meta if item["role"] == "Values"],
        },
        "projectionActiveItems": {
            "Category": [
                {"queryRef": item["queryName"], "suppressConcat": False}
                for item in select_meta
                if item["role"] == "Category"
            ]
        },
        "queryMetadata": {
            "Select": [
                {
                    "Restatement": item["displayName"],
                    "Name": item["queryName"],
                    "Type": 2048 if item["kind"] == "column" else 1,
                }
                for item in select_meta
            ]
        },
        "visualElements": [
            {
                "DataRoles": [
                    {
                        "Name": item["role"],
                        "Projection": item["projection"],
                        "isActive": item["role"] == "Category",
                    }
                    for item in select_meta
                ]
            }
        ],
        "selects": [
            {
                "displayName": item["displayName"],
                "queryName": item["queryName"],
                "roles": {item["role"]: True},
                "type": {
                    "category": None,
                    "underlyingType": 1 if item["kind"] == "column" else 259,
                },
                "expr": {
                    ("Column" if item["kind"] == "column" else "Measure"): {
                        "Expression": {"SourceRef": {"Entity": item["table"]}},
                        "Property": item["field"],
                    }
                },
            }
            for item in select_meta
        ],
        "expansionStates": [
            {
                "roles": ["Category"],
                "levels": [
                    {"queryRefs": [item["queryName"]], "isPinned": True}
                    for item in select_meta
                    if item["role"] == "Category"
                ],
                "root": {"identityValues": None},
            }
        ],
    }

    config = {
        "name": visual_name,
        "layouts": [
            {
                "id": 0,
                "position": {
                    "x": x,
                    "y": y,
                    "z": 820,
                    "width": w,
                    "height": h,
                    "tabOrder": 820,
                },
            }
        ],
        "singleVisual": {
            "visualType": visual_type,
            "projections": projections,
            "prototypeQuery": prototype_query,
            "columnProperties": column_props,
            "expansionStates": data_transforms["expansionStates"],
            "drillFilterOtherVisuals": True,
            "objects": object_settings,
        },
    }
    return {
        "config": json.dumps(config),
        "query": json.dumps(
            {
                "Commands": [
                    {
                        "SemanticQueryDataShapeCommand": {
                            "Query": prototype_query,
                            "Binding": binding,
                            "ExecutionMetricsKind": 1,
                        }
                    }
                ]
            }
        ),
        "dataTransforms": json.dumps(data_transforms),
        "filters": "[]",
        "height": h,
        "width": w,
        "x": x,
        "y": y,
        "z": 820,
    }


def build_clustered_bar_chart_visual(
    *,
    category_table: str,
    category_column: str,
    category_title: str,
    measure_table: str,
    measure_name: str,
    measure_title: str,
    x: float,
    y: float,
    w: float = 520,
    h: float = 220,
    fill: str = "#083EA7",
) -> dict:
    """Construct a clusteredBarChart for one category column and one measure."""
    visual_name = uuid.uuid4().hex[:20]
    aliases: dict[str, str] = {}
    aliases.setdefault(category_table, "c")
    aliases.setdefault(measure_table, "m" if category_table != measure_table else "c")
    category_alias = aliases[category_table]
    measure_alias = aliases[measure_table]
    category_ref = f"{category_table}.{category_column}"
    measure_ref = f"{measure_table}.{measure_name}"

    measure_expr = _measure_expr(measure_alias, measure_name)
    category_expr = _column_expr(category_alias, category_column)
    order_expr = _stage_order_expr(aliases, category_table, category_column)
    order_by = [{"Direction": 1, "Expression": order_expr}] if order_expr else [{"Direction": 2, "Expression": measure_expr}]
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
            "visualType": "clusteredBarChart",
            "projections": {
                "Category": [{"queryRef": category_ref, "active": True}],
                "Y": [{"queryRef": measure_ref}],
            },
            "prototypeQuery": {
                "Version": 2,
                "From": [
                    {"Name": alias, "Entity": tbl, "Type": 0} for tbl, alias in aliases.items()
                ],
                "Select": [
                    {**category_expr, "Name": category_ref},
                    {**measure_expr, "Name": measure_ref},
                ],
                "OrderBy": order_by,
            },
            "columnProperties": {
                category_ref: {"displayName": category_title},
                measure_ref: {"displayName": measure_title},
            },
            "drillFilterOtherVisuals": True,
            "objects": {
                "legend": [{"properties": {"show": _literal(False)}}],
                "categoryAxis": [
                    {
                        "properties": {
                            "labelColor": _solid_color("#252423"),
                            "fontSize": _literal(9),
                            "showAxisTitle": _literal(False),
                        }
                    }
                ],
                "valueAxis": [
                    {
                        "properties": {
                            "labelColor": _solid_color("#666666"),
                            "fontSize": _literal(9),
                            "showAxisTitle": _literal(False),
                        }
                    }
                ],
                "labels": [
                    {
                        "properties": {
                            "show": _literal(True),
                            "color": _solid_color("#252423"),
                            "fontSize": _literal(9),
                        }
                    }
                ],
                "dataPoint": [
                    {
                        "properties": {
                            "fill": _solid_color(fill),
                        }
                    }
                ],
            },
            "vcObjects": {
                "title": [{"properties": {"show": _literal(False)}}],
                "visualHeader": [{"properties": {"show": _literal(False)}}],
                "border": [
                    {
                        "properties": {
                            "show": _literal(False),
                        }
                    }
                ],
                "background": [
                    {
                        "properties": {
                            "show": _literal(False),
                            "transparency": _literal(100.0),
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


def build_table_style_objects(
    *,
    header_fill: str = "#f0f0f0",
    header_text: str = "#1A1D31",
    row_text: str = "#252423",
    grid: str = "#eeeeee",
    font_size: int = 9,
) -> dict:
    """Conservative tableEx formatting block for dense executive tables.

    These object names follow common Power BI table/matrix formatting groups.
    Desktop/Fabric may ignore unsupported properties, so visible panel chrome is
    still handled with `basicShape`; this block gives the renderer valid style
    hints and lets the harness distinguish intentionally formatted tables from
    plain table dumps.
    """
    return {
        "grid": [
            {
                "properties": {
                    "outlineColor": _solid_color(grid),
                    "gridVertical": _literal(False),
                    "gridHorizontal": _literal(True),
                    "rowPadding": _literal(4),
                    "textSize": _literal(font_size),
                }
            }
        ],
        "columnHeaders": [
            {
                "properties": {
                    "backColor": _solid_color(header_fill),
                    "fontColor": _solid_color(header_text),
                    "fontFamily": _literal("Segoe UI Semibold"),
                    "fontSize": _literal(font_size),
                    "alignment": _literal("Left"),
                }
            }
        ],
        "values": [
            {
                "properties": {
                    "fontColor": _solid_color(row_text),
                    "fontFamily": _literal("Segoe UI"),
                    "fontSize": _literal(font_size),
                    "backColorPrimary": _solid_color("#ffffff"),
                    "backColorSecondary": _solid_color("#fafafa"),
                    "showURLIcon": _literal(True),
                }
            }
        ],
    }


def build_matrix_style_objects(
    *,
    header_fill: str = "#f0f0f0",
    header_text: str = "#1A1D31",
    row_text: str = "#252423",
    grid: str = "#eeeeee",
    font_size: int = 9,
) -> dict:
    """Conservative pivotTable formatting block for stage/motion matrices."""
    return {
        "grid": [
            {
                "properties": {
                    "outlineColor": _solid_color(grid),
                    "gridVertical": _literal(False),
                    "gridHorizontal": _literal(True),
                    "rowPadding": _literal(4),
                    "textSize": _literal(font_size),
                }
            }
        ],
        "columnHeaders": [
            {
                "properties": {
                    "backColor": _solid_color(header_fill),
                    "fontColor": _solid_color(header_text),
                    "fontFamily": _literal("Segoe UI Semibold"),
                    "fontSize": _literal(font_size),
                }
            }
        ],
        "rowHeaders": [
            {
                "properties": {
                    "fontColor": _solid_color(header_text),
                    "fontFamily": _literal("Segoe UI Semibold"),
                    "fontSize": _literal(font_size),
                }
            }
        ],
        "values": [
            {
                "properties": {
                    "fontColor": _solid_color(row_text),
                    "fontFamily": _literal("Segoe UI"),
                    "fontSize": _literal(font_size),
                    "backColorPrimary": _solid_color("#ffffff"),
                    "backColorSecondary": _solid_color("#fafafa"),
                }
            }
        ],
    }


def build_rag_card_objects(
    *,
    tint: str,
    accent: str,
    value_color: str = "#222222",
    label_color: str | None = None,
    value_font_size: int = 28,
    label_font_size: int = 10,
    display_units: int | None = None,
    show_category_label: bool = True,
) -> dict:
    """Return a conservative legacy-card objects block for KPI cards.

    The labels/categoryLabels shape is based on the verified SalesManager card
    fixture. RAG status is intentionally expressed through accent typography
    instead of pastel tile fills, which reads closer to Zebra/IBCS executive
    reporting and avoids the AI-template look of red/amber/green card surfaces.
    """
    neutral_label_colors = {None, "#666666", "#5C6670"}
    category_label_color = accent if label_color in neutral_label_colors else label_color
    label_props = {
        "color": _solid_color(value_color),
        "fontSize": _literal(str(value_font_size)),
        "fontFamily": _literal("Segoe UI Semibold"),
    }
    return {
        "background": [
            {
                "properties": {
                    "show": _literal(True),
                    "color": _solid_color("#FFFFFF"),
                    "transparency": _literal(0.0),
                }
            }
        ],
        "border": [
            {
                "properties": {
                    "show": _literal(True),
                    "color": _solid_color("#D8DEE8"),
                    "radius": _literal(2),
                }
            }
        ],
        "labels": [{"properties": label_props}],
        "categoryLabels": [
            {
                "properties": {
                    "show": _literal(show_category_label),
                    "color": _solid_color(category_label_color),
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
    label_color: str | None = None,
    value_font_size: int = 28,
    label_font_size: int = 10,
    display_units: int | None = None,
    show_category_label: bool = True,
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
            show_category_label=show_category_label,
        ),
    )
