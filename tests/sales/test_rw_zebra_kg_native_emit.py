"""Tests for scripts.sales.rw_zebra_kg_native_emit."""

from __future__ import annotations

import json

from scripts.sales import rw_zebra_kg_native_emit as emit
from scripts.sales.rw_zebra_kg_recipe import Recipe, VisualRecipe


def _vr(visual_type: str, **kwargs) -> VisualRecipe:
    """Helper: VisualRecipe with sane defaults for tests."""
    return VisualRecipe(
        visual_type=visual_type,
        position=kwargs.get("position", {"x": 0, "y": 0, "w": 100, "h": 100}),
        role_bindings=kwargs.get("role_bindings", {}),
        scenarios_used=kwargs.get("scenarios_used", []),
        tables_referenced=kwargs.get("tables_referenced", []),
        measure_refs=kwargs.get("measure_refs", []),
        text=kwargs.get("text", ""),
    )


def test_zebra_table_recipe_yields_tableex():
    v = _vr(
        "ZebraBITables98F88148E5424E949E69864664EE1860",
        position={"x": 0, "y": 80, "w": 1280, "h": 264},
        role_bindings={
            "Category": ["d_region.region"],
            "Values": ["f_opportunity.Exception ARR"],
        },
        scenarios_used=["AC"],
        tables_referenced=["d_region", "f_opportunity"],
        measure_refs=["Exception ARR"],
    )
    recipe = Recipe(source_template="t", source_page="p", visuals=[v])
    rw_map = {"f_opportunity": ["Exception ARR"]}
    visuals = emit.emit_native_visuals(recipe, rw_map)
    assert len(visuals) == 1
    config = json.loads(visuals[0]["config"])
    assert config["singleVisual"]["visualType"] == "tableEx"
    assert visuals[0]["x"] == 0
    assert visuals[0]["y"] == 80
    assert visuals[0]["width"] == 1280
    assert visuals[0]["height"] == 264


def test_zebra_table_drops_unmapped_measures_keeps_mapped():
    v = _vr(
        "ZebraBITables98F88148E5424E949E69864664EE1860",
        position={"x": 0, "y": 80, "w": 1280, "h": 264},
        role_bindings={
            "Category": ["d_region.region"],
            "Values": [
                "f_opportunity.Exception ARR",
                "f_opportunity.Sales.NotInRW",  # this measure doesn't exist in RW
            ],
        },
        measure_refs=["Exception ARR", "Sales.NotInRW"],
    )
    recipe = Recipe(source_template="t", source_page="p", visuals=[v])
    rw_map = {"f_opportunity": ["Exception ARR"]}
    visuals = emit.emit_native_visuals(recipe, rw_map)
    assert len(visuals) == 1
    config = json.loads(visuals[0]["config"])
    projections = config["singleVisual"]["projections"]["Values"]
    field_names = [p["queryRef"].split(".")[-1] for p in projections]
    # region (category) + Exception ARR (mapped). NotInRW dropped.
    assert field_names == ["region", "Exception ARR"]


def test_zebra_table_with_zero_mapped_measures_is_dropped():
    """A Zebra table whose Category resolves but ALL value columns drop —
    no point emitting a category-only useless table."""
    v = _vr(
        "ZebraBITables98F88148E5424E949E69864664EE1860",
        position={"x": 0, "y": 80, "w": 1280, "h": 264},
        role_bindings={
            "Category": ["d_region.region"],
            "Values": ["f_opportunity.OnlyZebraHasThis"],
        },
    )
    recipe = Recipe(source_template="t", source_page="p", visuals=[v])
    rw_map = {"f_opportunity": ["TotallyDifferentMeasure"]}
    visuals = emit.emit_native_visuals(recipe, rw_map)
    assert len(visuals) == 0


def test_zebra_card_recipe_yields_card():
    v = _vr(
        "zebraBiCards8085D508EB994C8081CA47C85ABD7C26",
        position={"x": 0, "y": 600, "w": 320, "h": 120},
        role_bindings={"Values": ["f_opportunity.Total Closed Won ARR"]},
        scenarios_used=["AC"],
        tables_referenced=["f_opportunity"],
        measure_refs=["Total Closed Won ARR"],
    )
    recipe = Recipe(source_template="t", source_page="p", visuals=[v])
    rw_map = {"f_opportunity": ["Total Closed Won ARR"]}
    visuals = emit.emit_native_visuals(recipe, rw_map)
    assert len(visuals) == 1
    config = json.loads(visuals[0]["config"])
    assert config["singleVisual"]["visualType"] == "card"


def test_textbox_recipe_drops():
    """Native types in a recipe drop — Recipe path is for translation, not
    passthrough preservation. (Real PBIX textboxes go through swap_layout.)"""
    v = _vr(
        "textbox",
        position={"x": 0, "y": 0, "w": 1280, "h": 64},
        text="VP Ops Scorecard",
    )
    recipe = Recipe(source_template="t", source_page="p", visuals=[v])
    visuals = emit.emit_native_visuals(recipe, {})
    assert visuals == []


def test_waterfall_without_bindings_drops():
    """Waterfall now translates to a real native waterfallChart when it has
    Category + Values bindings. Without bindings it drops — no v1 placeholder."""
    v = _vr(
        "waterfall0221D8FBE40445C1A4E598AA8EF8B506",
        position={"x": 0, "y": 360, "w": 1280, "h": 224},
    )
    recipe = Recipe(source_template="t", source_page="p", visuals=[v])
    visuals = emit.emit_native_visuals(recipe, {})
    assert visuals == []


def test_unsupported_visual_dropped():
    for vt in ("actionButton", "slicer", "basicShape", "<none>", "columnChart"):
        v = _vr(vt)
        recipe = Recipe(source_template="t", source_page="p", visuals=[v])
        assert emit.emit_native_visuals(recipe, {}) == [], f"{vt} should drop"


def test_garbage_role_ref_with_paren_does_not_crash():
    """Recipe extractor faithfully captures `Min(Comments.Comment)` — generator
    must tolerate that (split-on-dot would produce table 'Min(Comments')."""
    v = _vr(
        "ZebraBITables98F88148E5424E949E69864664EE1860",
        position={"x": 0, "y": 80, "w": 1280, "h": 264},
        role_bindings={
            "Category": ["d_region.region"],
            "Comments": ["Min(Comments.Comment)"],
            "Values": ["f_opportunity.Exception ARR"],
        },
    )
    recipe = Recipe(source_template="t", source_page="p", visuals=[v])
    rw_map = {"f_opportunity": ["Exception ARR"]}
    visuals = emit.emit_native_visuals(recipe, rw_map)
    # Should still emit the table (Category + Exception ARR), Comments is silently ignored
    assert len(visuals) == 1
    config = json.loads(visuals[0]["config"])
    field_names = [
        p["queryRef"].split(".")[-1] for p in config["singleVisual"]["projections"]["Values"]
    ]
    assert field_names == ["region", "Exception ARR"]
