"""Translate a `Recipe` (from rw_zebra_kg_recipe) into native-PBI
visualContainers using the deployed RW measure inventory.

Translation matrix:
    ZebraBITables*       -> tableEx (Category + measure columns)
    zebraBiCards* / card -> card (single measure per card)
    textbox              -> textbox (pass-through)
    waterfall*           -> textbox placeholder ("see PR3.1 for native bridge")
    columnChart / slicer / actionButton / basicShape / <none> -> dropped (v1)

Zebra measure -> RW measure mapping: exact name match against the deployed
RW model (via fetch_measures_by_table). Unmapped measures dropped from
the value list. A Zebra table whose value list drops to empty -> visual
dropped entirely.

Usage (from another module):
    from scripts.sales.rw_zebra_kg_recipe import extract_recipe
    from scripts.sales.rw_zebra_kg_native_emit import emit_native_visuals
    from scripts.sales.rw_inventory_measures import fetch_measures_by_table

    recipe = extract_recipe("sales-dashboard-power-bi-template", "Landing")
    rw_map = fetch_measures_by_table()
    visuals = emit_native_visuals(recipe, rw_map)
"""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_card_visual_with_objects,
    build_table_style_objects,
    build_table_visual,
    build_textbox_visual,
)
from scripts.sales.rw_zebra_kg_recipe import Recipe, VisualRecipe

# IBCS column order — Zebra renders Values then PreviousYear then Plan then Forecast.
# Native tableEx has no scenario grammar; we preserve the same column order so a
# swap-back to Zebra Tables (when tenant unblocks) is a one-line change.
_VALUE_ROLE_ORDER = ["Values", "PreviousYear", "Plan", "Forecast"]


def _flatten_rw_measures(rw_map: dict) -> dict[str, str]:
    """{measure_name: rw_table_name} for fast lookup."""
    return {name: table for table, names in rw_map.items() for name in names}


def _emit_zebra_table(v: VisualRecipe, rw_lookup: dict[str, str]) -> dict | None:
    """ZebraBITables -> native tableEx. Drops unmapped measures; drops
    visual entirely if no value columns survive."""
    cat_refs = v.role_bindings.get("Category") or []
    if not cat_refs or "." not in cat_refs[0]:
        return None
    cat_table, cat_field = cat_refs[0].split(".", 1)

    columns = [
        {
            "table": cat_table,
            "field": cat_field,
            "kind": "column",
            "title": cat_field,
        }
    ]
    value_cols_added = 0
    for role in _VALUE_ROLE_ORDER:
        for ref in v.role_bindings.get(role, []) or []:
            if "." not in ref:
                continue
            _, field = ref.split(".", 1)
            if field in rw_lookup:
                columns.append(
                    {
                        "table": rw_lookup[field],
                        "field": field,
                        "kind": "measure",
                        "title": field,
                    }
                )
                value_cols_added += 1

    if value_cols_added == 0:
        return None

    return build_table_visual(
        name=f"recipe_{v.visual_type[:8]}",
        columns=columns,
        x=v.position["x"],
        y=v.position["y"],
        w=v.position["w"],
        h=v.position["h"],
        objects=build_table_style_objects(font_size=9),
    )


def _emit_zebra_card(v: VisualRecipe, rw_lookup: dict[str, str]) -> dict | None:
    """zebraBiCards / card -> native card. Picks the first mapped measure
    from any role binding."""
    for refs in v.role_bindings.values():
        for ref in refs or []:
            if "." not in ref:
                continue
            _, field = ref.split(".", 1)
            if field in rw_lookup:
                return build_card_visual_with_objects(
                    measure_table=rw_lookup[field],
                    measure_name=field,
                    display_title=field,
                    x=v.position["x"],
                    y=v.position["y"],
                    w=v.position["w"],
                    h=v.position["h"],
                )
    return None


def _emit_textbox(v: VisualRecipe) -> dict:
    return build_textbox_visual(
        text=v.text or "(textbox)",
        x=v.position["x"],
        y=v.position["y"],
        w=v.position["w"],
        h=v.position["h"],
        font_size_pt=10,
        color="#666666",
    )


def _emit_waterfall_placeholder(v: VisualRecipe) -> dict:
    return build_textbox_visual(
        text=(
            "Waterfall (Zebra bridge) — native equivalent deferred to PR3.1. "
            "Source visual: " + v.visual_type
        ),
        x=v.position["x"],
        y=v.position["y"],
        w=v.position["w"],
        h=v.position["h"],
        font_size_pt=10,
        color="#666666",
    )


def emit_native_visuals(recipe: Recipe, rw_map: dict[str, list[str]]) -> list[dict]:
    """Translate every visual in the recipe to a native PBIR visualContainer.
    Returns list of native visualContainers; visuals that can't translate
    are dropped silently (caller can diff len(recipe.visuals) vs len(out)
    to detect drops)."""
    rw_lookup = _flatten_rw_measures(rw_map)
    out: list[dict] = []
    for v in recipe.visuals:
        vt = v.visual_type
        visual: dict | None
        if "ZebraBITables" in vt:
            visual = _emit_zebra_table(v, rw_lookup)
        elif "zebraBiCards" in vt or vt == "card":
            visual = _emit_zebra_card(v, rw_lookup)
        elif vt == "textbox":
            visual = _emit_textbox(v)
        elif "waterfall" in vt:
            visual = _emit_waterfall_placeholder(v)
        else:
            visual = None
        if visual is not None:
            out.append(visual)
    return out
