"""Translate a `Recipe` (from rw_zebra_kg_recipe) into native-PBI
visualContainers using the deployed RW measure inventory.

Delegates per-family translation to translate_visual so all family logic
lives in one place (rw_zebra_kg_translator).

Usage (from another module):
    from scripts.sales.rw_zebra_kg_recipe import extract_recipe
    from scripts.sales.rw_zebra_kg_native_emit import emit_native_visuals
    from scripts.sales.rw_inventory_measures import fetch_measures_by_table

    recipe = extract_recipe("sales-dashboard-power-bi-template", "Landing")
    rw_map = fetch_measures_by_table()
    visuals = emit_native_visuals(recipe, rw_map)
"""

from __future__ import annotations

import json

from scripts.sales.rw_zebra_kg_recipe import Recipe, VisualRecipe
from scripts.sales.rw_zebra_kg_translator import (
    BindMap,
    MeasureCatalog,
    translate_visual,
)


def _recipe_visual_to_layout_vc(v: VisualRecipe) -> dict:
    """Adapt a VisualRecipe to the Layout-shape vc that translate_visual expects."""
    pos = v.position
    projections = {
        role: [{"queryRef": ref} for ref in (refs or [])]
        for role, refs in (v.role_bindings or {}).items()
    }
    sv: dict = {"visualType": v.visual_type, "projections": projections}
    if v.text:
        sv["objects"] = {
            "general": [{"properties": {"paragraphs": [{"textRuns": [{"value": v.text}]}]}}]
        }
    return {
        "x": pos.get("x", 0),
        "y": pos.get("y", 0),
        "width": pos.get("w", 0),
        "height": pos.get("h", 0),
        "config": json.dumps({"name": "recipe", "singleVisual": sv}),
    }


def _bindmap_from_rw_map(rw_map: dict[str, list[str]]) -> BindMap:
    """rw_map shape is {rw_table: [measure_name, ...]}; flatten to a zebra-ref->rw-ref overlay."""
    flat: dict[str, str] = {}
    for tbl, names in (rw_map or {}).items():
        for n in names:
            flat[n] = f"{tbl}.{n}"
    return BindMap(zebra_to_rw=flat)


def _catalog_from_rw_map(rw_map: dict[str, list[str]]) -> MeasureCatalog:
    by_scenario: dict[str, str] = {}
    measure_to_table: dict[str, str] = {}
    for tbl, names in (rw_map or {}).items():
        for n in names:
            by_scenario[n] = n
            measure_to_table[n] = tbl
    return MeasureCatalog(by_scenario=by_scenario, measure_to_table=measure_to_table)


def emit_native_visuals(recipe: Recipe, rw_map: dict[str, list[str]]) -> list[dict]:
    """Translate every visual in the recipe to a native PBIR visualContainer.

    Wraps translate_visual so per-family logic stays in one place.

    Recipe-driven semantics: a synthetic Zebra-typed VisualRecipe whose
    measures don't resolve produces a useless passthrough (Zebra visualType
    blocked by SimCorp tenant policy). Drop those — callers detect via
    `if not visuals` and raise. PBIX-path callers (swap_layout) keep the
    passthrough because they're preserving real visuals, not synthesizing.
    """
    catalog = _catalog_from_rw_map(rw_map)
    bm = _bindmap_from_rw_map(rw_map)
    out: list[dict] = []
    for v in recipe.visuals:
        src = _recipe_visual_to_layout_vc(v)
        translated = translate_visual(src, catalog, bm)
        if len(translated) == 1 and translated[0] is src:
            continue
        out.extend(translated)
    return out
